#!/usr/bin/env python3
"""Preview or append an executable-materialization repair checkpoint."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


if __package__ in {None, ""}:  # pragma: no cover - direct script execution
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api.planning_service import repair_active_plan_materialization  # noqa: E402
from data.database import Database  # noqa: E402


def repair_database(
    database_path: str | Path,
    *,
    apply: bool = False,
) -> dict[str, Any]:
    """Run the repair against an existing SQLite file; dry-run by default."""
    path = Path(database_path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"database does not exist: {path}")
    db = Database(str(path))
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
