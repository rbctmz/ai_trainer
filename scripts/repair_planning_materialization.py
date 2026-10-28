#!/usr/bin/env python3
"""Preview or append an executable-materialization repair checkpoint."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3
import sys
from typing import Any


if __package__ in {None, ""}:  # pragma: no cover - direct script execution
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api.planning_service import repair_active_plan_materialization  # noqa: E402
from data.database import Database  # noqa: E402


class _ReadOnlyPlanningStore:
    """Minimal immutable adapter used by the default preview path."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def _connect(self):
        return sqlite3.connect(f"{self.database_path.as_uri()}?mode=ro", uri=True)

    def planning_write_context(self, *, allow_inactive=False):
        from contextlib import closing
        from data.planning_cycle_writes import read_write_context
        from data.planning_cycles import PlanningCycleStore
        with closing(self._connect()) as conn:
            conn.execute("BEGIN")
            context = read_write_context(conn, allow_inactive=allow_inactive)
            context["_checkpoint"] = PlanningCycleStore(conn).checkpoint(context["checkpoint_id"])
            return context

    def _get_planning_checkpoint(
        self,
        checkpoint_id: int | None = None,
    ) -> dict[str, Any] | None:
        uri = f"{self.database_path.as_uri()}?mode=ro"
        with sqlite3.connect(uri, uri=True) as conn:
            if checkpoint_id is None:
                query = """
                SELECT id, goal_type, distance, weeks_to_race,
                       checkpoint_data, created_at
                FROM planning_checkpoints
                ORDER BY id DESC
                LIMIT 1
                """
                params: tuple[Any, ...] = ()
            else:
                query = """
                SELECT id, goal_type, distance, weeks_to_race,
                       checkpoint_data, created_at
                FROM planning_checkpoints
                WHERE id = ?
                LIMIT 1
                """
                params = (int(checkpoint_id),)
            row = conn.execute(query, params).fetchone()
        if not row:
            return None
        try:
            payload = json.loads(row[4]) if row[4] else {}
        except (TypeError, json.JSONDecodeError):
            payload = {}
        result = dict(payload) if isinstance(payload, dict) else {}
        result.update(
            {
                "id": row[0],
                "goal_type": row[1] or result.get("goal_type"),
                "distance": row[2] or result.get("distance"),
                "weeks_to_race": (
                    row[3] if row[3] is not None else result.get("weeks_to_race")
                ),
                "created_at": row[5],
            }
        )
        return result

    def get_latest_planning_checkpoint(self) -> dict[str, Any] | None:
        return self._get_planning_checkpoint()

    def get_planning_checkpoint(
        self,
        checkpoint_id: int,
    ) -> dict[str, Any] | None:
        return self._get_planning_checkpoint(checkpoint_id)


def repair_database(
    database_path: str | Path,
    *,
    apply: bool = False,
    confirm_working_database: bool = False,
    confirm_stopped: bool = False,
    backup: str | Path | None = None,
) -> dict[str, Any]:
    """Run the repair against an existing SQLite file; dry-run by default."""
    from config.maintenance_guard import validate_maintenance_target
    path = validate_maintenance_target(database_path, apply=apply, confirmed=confirm_working_database,
                                       stopped=confirm_stopped, backup=backup)
    db = Database(str(path)) if apply else _ReadOnlyPlanningStore(path)
    legacy_preview = False
    if not apply:
        from contextlib import closing
        with closing(db._connect()) as conn:
            legacy_preview = conn.execute("SELECT 1 FROM sqlite_master WHERE name='planning_cycle_state'").fetchone() is None
    if legacy_preview:
        # Explicit read-only diagnosis of a pre-migration file, never a selected
        # cycle or executable write proposal. Unknown ancestry cannot be a donor.
        from api.planning_service import _recovery_replan_session_ids_from_history
        from models.planning_checkpoints import restore_goal_plan_from_checkpoint
        from models.planning_near_term import rematerialize_non_executable_sessions
        checkpoint = db.get_latest_planning_checkpoint()
        if not checkpoint:
            raise ValueError("no checkpoint to inspect")
        root = {**checkpoint, "checkpoint_parent_id": None, "goal_plan_snapshot": {
            **checkpoint.get("goal_plan_snapshot", {}), "checkpoint_parent_id": None}}
        _, dates = rematerialize_non_executable_sessions(restore_goal_plan_from_checkpoint(checkpoint),
            recovery_session_ids=_recovery_replan_session_ids_from_history(db, root))
        result = {"plan_id": None, "base_checkpoint_id": checkpoint["id"], "changed_dates": dates,
                  "confirmation_required": bool(dates), "historical_preview": True}
    else:
        result = repair_active_plan_materialization(db, persist=apply)
    return {
        "mode": "apply" if apply else "dry-run",
        "database": str(path),
        **result,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database",
        required=True,
        help="explicit existing SQLite database path",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="append the repair checkpoint; omitted means read-only dry-run",
    )
    parser.add_argument("--confirm-working-database", action="store_true")
    parser.add_argument("--confirm-stopped", action="store_true")
    parser.add_argument("--backup", help="verified offline backup")
    args = parser.parse_args(argv)
    from config.database_paths import ScratchPathError
    try:
        result = repair_database(args.database, apply=args.apply,
                                 confirm_working_database=args.confirm_working_database,
                                 confirm_stopped=args.confirm_stopped, backup=args.backup)
    except (ScratchPathError, FileNotFoundError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
