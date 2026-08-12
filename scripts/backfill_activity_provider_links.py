#!/usr/bin/env python3
"""Preview or apply the offline provider-link reconciliation from ADR-0008."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


if __package__ in {None, ""}:  # pragma: no cover - direct script execution
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.settings import Settings  # noqa: E402
from data.database import Database  # noqa: E402
from services.activity_ingest import (  # noqa: E402
    backfill_provider_links,
    classify_activity_id,
)
from services.activity_provider_backfill import preview_provider_link_backfill  # noqa: E402


def repair_database(
    database_path: str | Path,
    *,
    apply: bool = False,
    primary_source: str | None = None,
) -> dict[str, Any]:
    """Dry-run by default; apply performs one atomic offline reconciliation."""
    path = Path(database_path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"database does not exist: {path}")
    resolved_primary = str(
        primary_source or Settings.PRIMARY_ACTIVITY_SOURCE
    ).strip().lower()
    if resolved_primary not in {"garmin", "intervals"}:
        raise ValueError("primary_source must be 'garmin' or 'intervals'")

    before = preview_provider_link_backfill(path, classify_activity_id)
    result: dict[str, Any] = {
        "mode": "apply" if apply else "dry-run",
        "database": str(path),
        "before": before,
    }
    if not apply:
        return result

    db = Database(str(path))
    result["applied"] = backfill_provider_links(
        db,
        primary_source=resolved_primary,
    )
    result["after"] = preview_provider_link_backfill(path, classify_activity_id)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database",
        default=Settings.DATABASE_PATH or "ai_trainer.db",
        help="existing SQLite database path",
    )
    parser.add_argument(
        "--primary-source",
        choices=("garmin", "intervals"),
        default=Settings.PRIMARY_ACTIVITY_SOURCE,
        help="authoritative canonical projection source",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="write provider links and reconcile canonicals; omitted means read-only dry-run",
    )
    args = parser.parse_args(argv)
    print(
        json.dumps(
            repair_database(
                args.database,
                apply=args.apply,
                primary_source=args.primary_source,
            ),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
