#!/usr/bin/env python3
"""Read-only aggregate check of HRV date storage and ordering."""
from __future__ import annotations

import argparse
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config.database_paths import ScratchPathError  # noqa: E402
from config.maintenance_guard import validate_maintenance_target  # noqa: E402
from scripts.maintenance_runtime import writable_target  # noqa: E402


def check_data_types_and_sorting(database_path: str | Path | None = None) -> dict[str, object]:
    """Inspect only an explicitly selected existing store in SQLite read-only mode."""
    target = validate_maintenance_target(database_path, apply=False)
    with sqlite3.connect(f'{target.as_uri()}?mode=ro', uri=True) as conn:
        schema = conn.execute('PRAGMA table_info(hrv_data)').fetchall()
        count = conn.execute('SELECT COUNT(*) FROM hrv_data').fetchone()[0]
        date_types = [row[0] for row in conn.execute('SELECT DISTINCT typeof(date) FROM hrv_data')]
        # Compare the display-formatted order to SQLite's chronological order
        # without printing any athlete dates or measurements.
        dates = [row[0] for row in conn.execute(
            "SELECT date FROM hrv_data WHERE date IS NOT NULL ORDER BY date DESC")]
        formatted = [f'{value[8:10]}.{value[5:7]}.{value[0:4]}' for value in dates
                     if isinstance(value, str) and len(value) >= 10]
        return {'rows': count, 'date_storage_types': date_types,
                'date_column_present': any(row[1] == 'date' for row in schema),
                'formatted_sort_matches_chronological': (
                    formatted == sorted(formatted, reverse=True) if len(formatted) == len(dates) else None)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database')
    args = parser.parse_args(argv)
    try:
        if args.database:
            print(check_data_types_and_sorting(args.database))
        else:
            with writable_target() as target:
                from data.database import Database
                Database(str(target))
                print(check_data_types_and_sorting(target))
        return 0
    except (ScratchPathError, FileNotFoundError, sqlite3.Error) as exc:
        print(str(exc) if isinstance(exc, ScratchPathError) else 'scratch_identity_unknown: bootstrap', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
