#!/usr/bin/env python3
"""Explicit, offline-backed operator-only Garmin sleep diagnostic."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config.database_paths import ScratchPathError  # noqa: E402
from config.maintenance_guard import validate_maintenance_target  # noqa: E402


def force_sync_yesterday(database_path: str | Path | None = None, *, apply: bool = False,
                         confirm_working_database: bool = False, confirm_stopped: bool = False,
                         backup: str | Path | None = None, confirm_live_provider: bool = False) -> bool:
    """Perform live sync only after DB/backup and live access are authorised."""
    if not apply or not confirm_live_provider:
        return False
    try:
        target = validate_maintenance_target(database_path, apply=True, confirmed=confirm_working_database,
                                             stopped=confirm_stopped, backup=backup)
    except (ScratchPathError, FileNotFoundError):
        return False
    # Credentials and provider code are loaded only after the write gate.
    from config.settings import Settings
    from data.garmin_client import GarminClient
    from data.data_processor_phase1 import Phase1DataProcessor
    from data.database import Database

    if not Settings.GARMIN_EMAIL or not Settings.GARMIN_PASSWORD:
        return False
    try:
        client = GarminClient()
        if not client.authenticate(Settings.GARMIN_EMAIL, Settings.GARMIN_PASSWORD):
            return False
        yesterday = datetime.now() - timedelta(days=1)
        raw = client.get_sleep_data(yesterday)
        if not raw:
            return False
        processed = Phase1DataProcessor.process_sleep_data(raw)
        if not processed or not any(processed.get(key, 0) > 0 for key in
                                    ('deep_sleep_minutes', 'light_sleep_minutes', 'rem_sleep_minutes')):
            return False
        date = yesterday.strftime('%Y-%m-%d')
        Database(str(target)).sync_sleep_data({date: processed})
        with sqlite3.connect(f'{target.as_uri()}?mode=ro', uri=True) as conn:
            saved = conn.execute(
                'SELECT deep_sleep_minutes, light_sleep_minutes, rem_sleep_minutes FROM sleep_data WHERE date = ?',
                (date,),
            ).fetchone()
        return bool(saved and any(value is not None and value > 0 for value in saved))
    except Exception:
        # Do not print provider errors or data, which may contain credentials.
        return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', required=True)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--confirm-working-database', action='store_true')
    parser.add_argument('--confirm-stopped', action='store_true')
    parser.add_argument('--confirm-live-provider', action='store_true')
    parser.add_argument('--backup')
    args = parser.parse_args(argv)
    ok = force_sync_yesterday(args.database, apply=args.apply,
                              confirm_working_database=args.confirm_working_database,
                              confirm_stopped=args.confirm_stopped, backup=args.backup,
                              confirm_live_provider=args.confirm_live_provider)
    if not ok:
        print('operator_confirmation_required: bootstrap', file=sys.stderr)
        return 2
    print('Синхронизация выполнена')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
