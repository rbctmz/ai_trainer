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
) -> dict[str, Any]:
    """Run the repair against an existing SQLite file; dry-run by default."""
    path = Path(database_path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"database does not exist: {path}")
    db = Database(str(path)) if apply else _ReadOnlyPlanningStore(path)
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
        default="ai_trainer.db",
        help="existing SQLite database path (default: ai_trainer.db)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="append the repair checkpoint; omitted means read-only dry-run",
    )
    args = parser.parse_args(argv)
    print(
        json.dumps(
            repair_database(args.database, apply=args.apply),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
