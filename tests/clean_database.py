#!/usr/bin/env python3
"""Preview or explicitly clean synthetic test rows from a selected SQLite DB."""
from __future__ import annotations

import argparse
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.database_paths import ScratchPathError  # noqa: E402
from config.maintenance_guard import validate_maintenance_target  # noqa: E402
from scripts.maintenance_runtime import writable_target  # noqa: E402


def analyze_database(database_path: str | Path | None = None) -> dict[str, int]:
    """Return aggregate preview only; never create a missing database."""
    path = validate_maintenance_target(database_path, apply=False)
    with sqlite3.connect(f'{path.as_uri()}?mode=ro', uri=True) as conn:
        total = conn.execute('SELECT COUNT(*) FROM activities').fetchone()[0]
        tests = conn.execute("SELECT COUNT(*) FROM activities WHERE activity_id GLOB 'test_*' OR activity_id GLOB 'date_test_*' OR activity_id GLOB 'test_df_*'").fetchone()[0]
        hrv = conn.execute('SELECT COUNT(*) FROM hrv_data').fetchone()[0]
    return {'total_activities': total, 'test_activities': tests, 'total_hrv': hrv}


def clean_database(confirm: bool = True, database_path: str | Path | None = None, *,
                   apply: bool = False, confirm_working_database: bool = False,
                   confirm_stopped: bool = False, backup: str | Path | None = None,
                   delete_all_hrv: bool = False) -> bool:
    """Refuse implicit target; deleting all HRV requires a separate option."""
    if not apply:
        raise ScratchPathError('operator_confirmation_required', purpose='bootstrap')
    path = validate_maintenance_target(database_path, apply=True, confirmed=confirm_working_database,
                                       stopped=confirm_stopped, backup=backup)
    if confirm and input('Подтвердить очистку? (yes/no): ').lower() not in {'yes', 'y', 'да'}:
        return False
    with sqlite3.connect(str(path)) as conn:
        for pattern in ('test_*', 'date_test_*', 'test_df_*'):
            conn.execute('DELETE FROM activities WHERE activity_id GLOB ?', (pattern,))
        if delete_all_hrv:
            conn.execute('DELETE FROM hrv_data')
        conn.commit()
    return True


def verify_cleanup(database_path: str | Path | None = None) -> dict[str, int]:
    return analyze_database(database_path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--confirm-working-database', action='store_true')
    parser.add_argument('--confirm-stopped', action='store_true')
    parser.add_argument('--confirm-delete-all-hrv', action='store_true')
    parser.add_argument('--backup')
    args = parser.parse_args(argv)
    try:
        if args.database is None:
            if args.apply:
                raise ScratchPathError('operator_confirmation_required', purpose='bootstrap')
            with writable_target() as target:
                from data.database import Database
                Database(str(target))
                print(analyze_database(target))
            return 0
        if args.apply:
            clean_database(confirm=False, database_path=args.database, apply=True,
                           confirm_working_database=args.confirm_working_database,
                           confirm_stopped=args.confirm_stopped, backup=args.backup,
                           delete_all_hrv=args.confirm_delete_all_hrv)
        print(analyze_database(args.database))
        return 0
    except (ScratchPathError, FileNotFoundError, sqlite3.Error) as exc:
        print(str(exc) if isinstance(exc, ScratchPathError) else 'scratch_identity_unknown: bootstrap', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
