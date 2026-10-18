"""Explicit lifecycle commands on one writer connection; retries never reactivate."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import sqlite3
from typing import Any, Callable

from config.settings import Settings
from data.database import Database
from data.planning_cycles import PlanningCycleStore
from models.planning_build_confirmation import canonical_json, fingerprint
from models.planning_cycle import (
    CycleCommandError, CycleStateCorrupt, constraint_fingerprint, cycle_events, stored_day,
)
from services.planning_cycles import _read_context
from utils.athlete_time import athlete_local_date

_CONSTRAINT_COLUMNS = """id,date,kind,status,source,note,plan_id,session_id,
    metadata_json,resolved_at,created_at,sport,cycle_scope,cycle_id"""


def _cycle(store: PlanningCycleStore, cycle_id: str) -> dict[str, Any]:
    cycle = store.cycle(cycle_id)
    if cycle is None:
        raise CycleCommandError("cycle_not_found", "Цикл не найден.", status=404)
    return cycle


def _outcome_changes(store: PlanningCycleStore, cycle: dict[str, Any], declarations: list[dict], day) -> list[dict]:
    """Resolve event identity only in immutable versions owned by this cycle."""
    if not declarations:
        return []
    candidates: dict[str, dict] = {}
    ambiguous = set()
    for (checkpoint_id,) in store.conn.execute(
        "SELECT checkpoint_id FROM planning_cycle_versions WHERE cycle_id=? ORDER BY checkpoint_id",
        (cycle["id"],),
    ):
        for event in cycle_events(cycle, store.checkpoint(checkpoint_id)):
            if event["is_ambiguous"]:
                ambiguous.add(event["event_key"])
            candidates[event["event_key"]] = {"checkpoint_id": checkpoint_id, "event": event}
    changes = []
    for declaration in declarations:
        key, outcome = declaration["event_key"], declaration["outcome"]
        candidate = candidates.get(key)
        if candidate is None or key in ambiguous:
            raise CycleCommandError("event_not_found", "Сохранённый старт не найден однозначно.", status=404)
        event = candidate["event"]
        event_day = stored_day(event.get("date"))
        if outcome == "participated" and (event_day is None or event_day > day):
            raise CycleCommandError("invalid_event_outcome", "Участие можно указать только для прошедшего старта.", status=422)
        changes.append({"event_key": key, "checkpoint_id": candidate["checkpoint_id"],
                        "event_snapshot": {k: v for k, v in event.items()
                                           if k not in {"event_key", "outcome", "is_ambiguous"}},
                        "before": event["outcome"], "after": outcome})
    return changes


def _close(store: PlanningCycleStore, request: dict, day) -> dict:
    cycle = _cycle(store, request["cycle_id"])
    selection = store.state()
    if cycle["status"] == "closed":
        raise CycleCommandError("cycle_closed", "Цикл уже закрыт.")
    if selection["current_cycle_id"] != cycle["id"]:
        raise CycleCommandError("cycle_not_current", "Этот цикл больше не выбран.")
    if (selection["revision"], cycle["revision"], cycle["current_checkpoint_id"]) != (
        request["expected_selection_revision"], request["expected_cycle_revision"], request["expected_checkpoint_id"],
    ):
        raise CycleCommandError("cycle_stale", "Цикл изменился — обновите данные.")
    # Closing changes lifecycle metadata only: a missing/foreign checkpoint
    # must not prevent exiting an indeterminate selected cycle. Any optional
    # declarations still require their own verified cycle-owned snapshots.
    changes = _outcome_changes(store, cycle, request["event_outcomes"], day)
    # Closing an indeterminate cycle without declarations must not repair or
    # reinterpret corrupt historical outcome bytes.
    outcomes_json = cycle["event_outcomes_json"]
    if changes:
        outcomes = json.loads(outcomes_json)
        outcomes.update({change["event_key"]: change["after"] for change in changes})
        outcomes_json = canonical_json(outcomes)
    store.conn.execute("""UPDATE planning_cycles SET status='closed',closed_at=?,revision=revision+1,
        event_outcomes_json=? WHERE id=?""",
        (datetime.now(timezone.utc).isoformat(), outcomes_json, cycle["id"]))
    store.conn.execute("UPDATE planning_cycle_state SET current_cycle_id=NULL,revision=revision+1 WHERE id=1")
    return {"effect": "closed", "cycle_id": cycle["id"], "cycle_revision": cycle["revision"] + 1,
            "checkpoint_id": cycle["current_checkpoint_id"], "selection_revision": selection["revision"] + 1,
            "event_outcomes": changes, "constraint_scope": None}


def _set_outcome(store: PlanningCycleStore, request: dict, day) -> dict:
    cycle = _cycle(store, request["cycle_id"])
    if cycle["revision"] != request["expected_cycle_revision"]:
        raise CycleCommandError("cycle_stale", "Цикл изменился — обновите данные.")
    changes = _outcome_changes(store, cycle, [request], day)
    outcomes = json.loads(cycle["event_outcomes_json"])
    outcomes[request["event_key"]] = request["outcome"]
    store.conn.execute("UPDATE planning_cycles SET event_outcomes_json=?,revision=revision+1 WHERE id=?",
                       (canonical_json(outcomes), cycle["id"]))
    return {"effect": "event_outcome_set", "cycle_id": cycle["id"], "cycle_revision": cycle["revision"] + 1,
            "checkpoint_id": cycle["current_checkpoint_id"], "selection_revision": store.state()["revision"],
            "event_outcomes": changes, "constraint_scope": None}


def _resolve_scope(store: PlanningCycleStore, db: Database, request: dict) -> dict:
    raw = store.conn.execute(f"SELECT {_CONSTRAINT_COLUMNS} FROM coach_constraints WHERE id=?",
                             (request["constraint_id"],)).fetchone()
    if raw is None:
        raise CycleCommandError("constraint_scope_required", "Ограничение не найдено — обновите данные.")
    constraint = db._deserialize_coach_constraint_row(raw)
    before = constraint_fingerprint(constraint)
    if before != request["expected_constraint_fingerprint"]:
        raise CycleCommandError("cycle_stale", "Ограничение изменилось — обновите данные.")
    cycle_id = request["cycle_id"]
    cycle = _cycle(store, cycle_id) if cycle_id else None
    store.conn.execute("UPDATE coach_constraints SET cycle_scope=?,cycle_id=? WHERE id=?",
                       (request["scope"], cycle_id, request["constraint_id"]))
    after = constraint_fingerprint({**constraint, "cycle_scope": request["scope"], "cycle_id": cycle_id})
    return {"effect": "constraint_scope_resolved", "cycle_id": cycle_id,
            "cycle_revision": cycle["revision"] if cycle else None,
            "checkpoint_id": cycle["current_checkpoint_id"] if cycle else None,
            "selection_revision": store.state()["revision"], "event_outcomes": [],
            "constraint_scope": {"constraint_id": request["constraint_id"], "before_fingerprint": before,
                                 "after_fingerprint": after, "scope": request["scope"], "cycle_id": cycle_id}}


def _receipt(store: PlanningCycleStore, request: dict) -> dict | None:
    row = store._one("SELECT * FROM planning_cycle_commands WHERE command_id=?", (request["command_id"],))
    if row is None:
        return None
    try:
        saved_request, envelope = json.loads(row["request_json"]), json.loads(row["result_json"])
        digest = fingerprint(saved_request)
        if (row["request_digest"] != digest or row["command_id"] != saved_request["command_id"]
                or row["kind"] != saved_request["kind"] or row["cycle_id"] != saved_request.get("cycle_id")
                or row["event_key"] != saved_request.get("event_key")
                or set(envelope) != {"result", "digest"}
                or envelope["digest"] != fingerprint({"request_digest": digest, "result": envelope["result"]})):
            raise ValueError("Invalid retained receipt")
    except (ValueError, KeyError, TypeError) as exc:
        raise CycleStateCorrupt("Invalid retained cycle receipt") from exc
    if digest != fingerprint(request):
        raise CycleCommandError("idempotency_conflict", "Этот ID уже использован для другой команды.")
    return envelope["result"]


def execute_cycle_command(
    db: Database, kind: str, parameters: dict[str, Any], *, cycle_id: str | None = None,
    validate_response: Callable[[dict[str, Any]], Any],
) -> dict[str, Any]:
    """Accept validated API parameters; commit result, metadata and receipt together.

    The API supplies its response validator so serialization failure rolls back
    the state change. The domain service has no dependency on API schemas.
    """
    request = {**parameters, "kind": kind, "cycle_id": cycle_id or parameters.get("cycle_id")}
    conn = db._connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        store = PlanningCycleStore(conn)
        result = _receipt(store, request)  # BEFORE current selection/revision checks
        replayed = result is not None
        day = athlete_local_date()  # after lock acquisition, also used for the response
        if not replayed:
            if kind == "close":
                result = _close(store, request, day)
            elif kind == "set_event_outcome":
                result = _set_outcome(store, request, day)
            elif kind == "resolve_constraint_scope":
                result = _resolve_scope(store, db, request)
            else:
                raise ValueError("Unsupported internal cycle command")
            request_digest = fingerprint(request)
            envelope = {"result": result, "digest": fingerprint({"request_digest": request_digest, "result": result})}
            conn.execute("""INSERT INTO planning_cycle_commands
                (command_id,kind,request_digest,cycle_id,event_key,request_json,result_json)
                VALUES(?,?,?,?,?,?,?)""",
                (request["command_id"], kind, request_digest, request["cycle_id"], request.get("event_key"),
                 canonical_json(request), canonical_json(envelope)))
        selection = store.state()
        response = {"command_id": request["command_id"], "kind": kind, "replayed": replayed, "result": result,
                    "current_context": _read_context(store, selection, selection["current_cycle_id"], day,
                                                     Settings.ATHLETE_TIMEZONE, store.has_history())}
        validate_response(response)
        if replayed:
            conn.rollback()
        else:
            conn.commit()
        return response
    except sqlite3.OperationalError as exc:
        conn.rollback()
        if getattr(exc, "sqlite_errorcode", 0) & 255 in {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED}:
            raise CycleCommandError("planning_busy", "Хранилище занято — повторите ту же команду.", status=503, retryable=True) from exc
        raise
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
