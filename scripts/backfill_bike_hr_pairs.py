"""Preview or apply an offline backfill of bike power/HR quality pairs."""
from __future__ import annotations

import argparse
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.database_paths import ScratchPathError  # noqa: E402
from config.maintenance_guard import validate_maintenance_target  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', '--db', dest='database', required=True)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--confirm-working-database', action='store_true')
    parser.add_argument('--confirm-stopped', action='store_true')
    parser.add_argument('--backup')
    args = parser.parse_args(argv)
    try:
        target = validate_maintenance_target(args.database, apply=args.apply,
                                             confirmed=args.confirm_working_database,
                                             stopped=args.confirm_stopped, backup=args.backup)
        with sqlite3.connect(f'{target.as_uri()}?mode=ro', uri=True) as conn:
            conn.row_factory = sqlite3.Row
            if not args.apply:
                count = conn.execute('SELECT COUNT(*) FROM activities').fetchone()[0]
                print(f'Read-only preview: {count} activities')
                return 0
            rows = conn.execute('SELECT * FROM activities ORDER BY date, activity_id').fetchall()
        from data.database import Database
        from services.bike_hr_pairs import record_bike_hr_pair
        database = Database(str(target))
        recorded = skipped = failed = 0
        for row in rows:
            try:
                if record_bike_hr_pair(database, dict(row)):
                    recorded += 1
                else:
                    skipped += 1
            except Exception:  # best-effort per activity; never emit row content
                failed += 1
        print(f'Готово: пар записано={recorded}, пропущено={skipped}, ошибок={failed}')
        return 0
    except (ScratchPathError, FileNotFoundError, sqlite3.Error):
        print('operator_confirmation_required: bootstrap', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
