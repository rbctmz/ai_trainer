"""Connection-bound cycle storage and conservative, transactional legacy import."""
from __future__ import annotations

import json
import sqlite3
from typing import Any
from uuid import UUID, uuid4

from models.planning_cycle import CycleStateCorrupt, checkpoint_period

_VERSION_DELETE_GUARD = """CREATE TRIGGER IF NOT EXISTS planning_cycle_versions_no_delete
    BEFORE DELETE ON planning_cycle_versions
    BEGIN SELECT RAISE(ABORT, 'Cycle version associations are immutable'); END"""

_COMMAND_GUARDS = (
    """CREATE TRIGGER IF NOT EXISTS planning_cycle_commands_no_update
       BEFORE UPDATE ON planning_cycle_commands
       BEGIN SELECT RAISE(ABORT, 'Cycle command receipts are immutable'); END""",
    """CREATE TRIGGER IF NOT EXISTS planning_cycle_commands_no_delete
       BEFORE DELETE ON planning_cycle_commands
       BEGIN SELECT RAISE(ABORT, 'Cycle command receipts are immutable'); END""",
    """CREATE TRIGGER IF NOT EXISTS planning_cycle_commands_no_replace
       BEFORE INSERT ON planning_cycle_commands
       WHEN EXISTS(SELECT 1 FROM planning_cycle_commands WHERE command_id=NEW.command_id)
       BEGIN SELECT RAISE(ABORT, 'Cycle command receipts are immutable'); END""",
)


class PlanningCycleStore:
    """Use the caller's transaction; ordinary reads never initialize or commit."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def _one(self, query: str, params: tuple = ()) -> dict[str, Any] | None:
        cursor = self.conn.execute(query, params)
        row = cursor.fetchone()
        return dict(zip((item[0] for item in cursor.description), row)) if row is not None else None

    def state(self) -> dict[str, Any]:
        row = self._one("SELECT * FROM planning_cycle_state WHERE id=1")
        if not row or row["legacy_migration_complete"] != 1 or row["revision"] < 0:
            raise CycleStateCorrupt("Cycle selection is not initialized")
        try:
            UUID(row["namespace"])
            if row["current_cycle_id"] is not None:
                UUID(row["current_cycle_id"])
        except (ValueError, TypeError, AttributeError) as exc:
            raise CycleStateCorrupt("Cycle namespace is invalid") from exc
        return row

    def cycle(self, cycle_id: str) -> dict[str, Any] | None:
        return self._one("SELECT * FROM planning_cycles WHERE id=?", (cycle_id,))

    def checkpoint(self, checkpoint_id: int | None) -> dict[str, Any] | None:
        row = self._one("SELECT * FROM planning_checkpoints WHERE id=?", (checkpoint_id,))
        if row is None:
            return None
        try:
            payload = json.loads(row["checkpoint_data"])
        except (ValueError, TypeError):
            payload = {}
        return {**(payload if isinstance(payload, dict) else {}), "id": row["id"]}

    def version_cycle(self, checkpoint_id: int | None) -> str | None:
        row = self._one("SELECT cycle_id FROM planning_cycle_versions WHERE checkpoint_id=?", (checkpoint_id,))
        return row["cycle_id"] if row else None

    def has_history(self) -> bool:
        return self.conn.execute("SELECT EXISTS(SELECT 1 FROM planning_checkpoints)").fetchone()[0] == 1

    def cycle_ids(self, limit: int = 50) -> list[str]:
        return [row[0] for row in self.conn.execute(
            "SELECT id FROM planning_cycles ORDER BY created_at DESC, id DESC LIMIT ?",
            (max(1, min(int(limit), 50)),),
        )]


def initialize_cycle_store(conn: sqlite3.Connection) -> None:
    """Initialize once inside the caller's BEGIN IMMEDIATE, without committing."""
    if not conn.in_transaction:
        raise RuntimeError("Cycle initialization requires a writer transaction")
    for statement in (
        """CREATE TABLE IF NOT EXISTS planning_cycles (
            id TEXT PRIMARY KEY, current_checkpoint_id INTEGER REFERENCES planning_checkpoints(id),
            revision INTEGER NOT NULL CHECK(revision>=1),
            status TEXT NOT NULL CHECK(status IN ('open','closed')),
            start_date TEXT, end_date TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            closed_at TEXT, origin TEXT NOT NULL CHECK(origin IN ('explicit','legacy_import')),
            event_outcomes_json TEXT NOT NULL DEFAULT '{}')""",
        """CREATE TABLE IF NOT EXISTS planning_cycle_state (
            id INTEGER PRIMARY KEY CHECK(id=1), namespace TEXT NOT NULL,
            current_cycle_id TEXT REFERENCES planning_cycles(id),
            revision INTEGER NOT NULL CHECK(revision>=0),
            legacy_migration_complete INTEGER NOT NULL CHECK(legacy_migration_complete IN (0,1)))""",
        """CREATE TABLE IF NOT EXISTS planning_cycle_versions (
            checkpoint_id INTEGER PRIMARY KEY REFERENCES planning_checkpoints(id),
            cycle_id TEXT NOT NULL REFERENCES planning_cycles(id),
            action TEXT NOT NULL CHECK(action IN ('initial','edit','restore','adjustment')))""",
        """CREATE TABLE IF NOT EXISTS planning_cycle_commands (
            command_id TEXT PRIMARY KEY,
            kind TEXT NOT NULL CHECK(kind IN ('close','set_event_outcome','resolve_constraint_scope')),
            request_digest TEXT NOT NULL, cycle_id TEXT REFERENCES planning_cycles(id),
            event_key TEXT, request_json TEXT NOT NULL, result_json TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""",
        "CREATE INDEX IF NOT EXISTS idx_planning_cycle_versions_cycle ON planning_cycle_versions(cycle_id)",
        """CREATE TRIGGER IF NOT EXISTS planning_cycle_versions_immutable
            BEFORE UPDATE ON planning_cycle_versions
            BEGIN SELECT RAISE(ABORT, 'Cycle version associations are immutable'); END""",
        """CREATE TRIGGER IF NOT EXISTS planning_cycle_versions_no_replace
            BEFORE INSERT ON planning_cycle_versions
            WHEN EXISTS(SELECT 1 FROM planning_cycle_versions WHERE checkpoint_id=NEW.checkpoint_id)
            BEGIN SELECT RAISE(ABORT, 'Cycle version associations are immutable'); END""",
        _VERSION_DELETE_GUARD,
        *_COMMAND_GUARDS,
    ):
        conn.execute(statement)
    columns = {row[1] for row in conn.execute("PRAGMA table_info(coach_constraints)")}
    for name in ("cycle_scope", "cycle_id"):
        if name not in columns:
            conn.execute(f"ALTER TABLE coach_constraints ADD COLUMN {name} TEXT")
    state = conn.execute("SELECT legacy_migration_complete FROM planning_cycle_state WHERE id=1").fetchone()
    if state and state[0] == 1:
        return
    if conn.execute("SELECT EXISTS(SELECT 1 FROM planning_cycles)").fetchone()[0]:
        raise CycleStateCorrupt("Unfinished cycle migration contains unexpected rows")
    if state:
        conn.execute("DELETE FROM planning_cycle_state WHERE id=1")
    row = conn.execute("SELECT id,checkpoint_data FROM planning_checkpoints ORDER BY id DESC LIMIT 1").fetchone()
    selected = None
    if row:
        selected = str(uuid4())
        try:
            checkpoint = json.loads(row[1])
        except (ValueError, TypeError):
            checkpoint = {}
        period = checkpoint_period(checkpoint if isinstance(checkpoint, dict) else {})
        conn.execute("""INSERT INTO planning_cycles
            (id,current_checkpoint_id,revision,status,start_date,end_date,origin)
            VALUES (?,?,1,'open',?,?,'legacy_import')""",
                     (selected, row[0], period.start.isoformat() if period.start else None,
                      period.end.isoformat() if period.end else None))
        conn.execute("INSERT INTO planning_cycle_versions VALUES (?,?,'initial')", (row[0], selected))
    _migrate_constraint_scope(conn)
    conn.execute("INSERT INTO planning_cycle_state VALUES (1,?,?,?,1)",
                 (str(uuid4()), selected, 1 if selected else 0))


def _migrate_constraint_scope(conn: sqlite3.Connection) -> None:
    store = PlanningCycleStore(conn)
    constraints = conn.execute(
        "SELECT id,kind,plan_id,session_id FROM coach_constraints WHERE cycle_scope IS NULL"
    ).fetchall()
    if not constraints:
        return
    # Only mapped checkpoints can establish ownership. Earlier legacy rows
    # deliberately remain unassigned even if labels or session IDs coincide.
    session_owners: dict[str, set[str | None]] = {}
    sessions_by_checkpoint: dict[int, set[str]] = {}
    checkpoints = conn.execute(
        "SELECT pc.id,v.cycle_id FROM planning_checkpoints pc "
        "LEFT JOIN planning_cycle_versions v ON v.checkpoint_id=pc.id"
    ).fetchall() if any(row[3] for row in constraints) else []
    for checkpoint_id, cycle_id in checkpoints:
        snapshot = (store.checkpoint(checkpoint_id) or {}).get("goal_plan_snapshot") or {}
        if not isinstance(snapshot, dict):
            continue
        sessions_by_checkpoint[checkpoint_id] = set()
        templates = snapshot.get("session_templates")
        if not isinstance(templates, list):
            continue
        for template in templates:
            if not isinstance(template, dict):
                continue
            nested = template.get("sessions")
            for session in [template, *(nested if isinstance(nested, list) else [])]:
                if isinstance(session, dict) and session.get("session_id"):
                    ids = {str(session["session_id"])}
                    legs = session.get("legs")
                    ids.update(str(leg["leg_id"]) for leg in (legs if isinstance(legs, list) else [])
                               if isinstance(leg, dict) and leg.get("leg_id"))
                    for session_id in ids:
                        sessions_by_checkpoint[checkpoint_id].add(session_id)
                        session_owners.setdefault(session_id, set()).add(cycle_id)
    for row_id, kind, plan_id, session_id in constraints:
        candidates, unresolved, bound_checkpoint = [], False, None
        if plan_id is not None and str(plan_id).strip():
            try:
                bound_checkpoint = int(plan_id)
                owner = store.version_cycle(bound_checkpoint)
            except (ValueError, TypeError):
                owner = None
            if owner:
                candidates.append(owner)
            else:
                unresolved = True
        if session_id is not None and str(session_id).strip():
            owners = session_owners.get(str(session_id), set())
            if bound_checkpoint is not None:
                if str(session_id) not in sessions_by_checkpoint.get(bound_checkpoint, set()):
                    unresolved = True
            elif len(owners) == 1 and None not in owners:
                candidates.append(next(iter(owners)))
            else:
                unresolved = True
        if unresolved or len(set(candidates)) > 1:
            scope, cycle_id = "unknown", None
        elif candidates:
            scope, cycle_id = "cycle", candidates[0]
        else:
            scope = "athlete" if kind in {"sick", "unavailable", "forced_rest"} else "unknown"
            cycle_id = None
        conn.execute("UPDATE coach_constraints SET cycle_scope=?,cycle_id=? WHERE id=?",
                     (scope, cycle_id, row_id))


def reset_cycle_store(conn: sqlite3.Connection) -> None:
    """Remove lifecycle state in the existing full-reset transaction."""
    if not conn.in_transaction:
        raise RuntimeError("Cycle reset requires a writer transaction")
    # Full reset is the only lifecycle deletion operation. Transactional DDL
    # restores the guard and old rows together if any later reset step fails.
    conn.execute("DROP TRIGGER IF EXISTS planning_cycle_versions_no_delete")
    conn.execute("DROP TRIGGER IF EXISTS planning_cycle_commands_no_delete")
    conn.execute("DELETE FROM planning_cycle_commands")
    conn.execute("DELETE FROM planning_cycle_versions")
    conn.execute("DELETE FROM planning_cycle_state")
    conn.execute("DELETE FROM planning_cycles")
    conn.execute("INSERT INTO planning_cycle_state VALUES (1,?,NULL,0,1)", (str(uuid4()),))
    conn.execute(_VERSION_DELETE_GUARD)
    for statement in _COMMAND_GUARDS:
        conn.execute(statement)
