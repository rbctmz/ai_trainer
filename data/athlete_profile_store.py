"""SQLite persistence for the athlete_profile snapshot table (TD-006, #371).

Extracted from ``data/database.py``: table DDL, additive pace-column migration,
append-only save and latest-row read live here. ``Database`` keeps the same
public methods as thin facades, so existing importers keep working unchanged.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any, Callable, Dict, Mapping, Optional


CleanValue = Callable[[Any], Any]

# Pace columns added by migration for databases created before #308/#362.
_PACE_COLUMN_TYPES = {
    "threshold_pace_seconds_per_km": "REAL",
    "threshold_pace_source": "TEXT",
    "threshold_pace_synced_at": "TIMESTAMP",
    "swim_threshold_pace_seconds_per_100m": "REAL",
    "swim_threshold_pace_source": "TEXT",
    "swim_threshold_pace_synced_at": "TIMESTAMP",
}


def create_athlete_profile_table(conn: sqlite3.Connection) -> None:
    """Create the append-only athlete_profile table if it does not exist."""
    conn.execute(
        '''
        CREATE TABLE IF NOT EXISTS athlete_profile (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ftp REAL,
            weight_kg REAL,
            lthr REAL,
            threshold_pace_seconds_per_km REAL,
            threshold_pace_source TEXT,
            threshold_pace_synced_at TIMESTAMP,
            swim_threshold_pace_seconds_per_100m REAL,
            swim_threshold_pace_source TEXT,
            swim_threshold_pace_synced_at TIMESTAMP,
            source TEXT,
            synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        '''
    )


def ensure_athlete_profile_columns(conn: sqlite3.Connection) -> None:
    """Add issue #308/#362 pace fields to databases created before the features."""
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(athlete_profile)")
    existing_columns = {row[1] for row in cursor.fetchall()}
    for column, column_type in _PACE_COLUMN_TYPES.items():
        if column in existing_columns:
            continue
        try:
            cursor.execute(
                f'ALTER TABLE athlete_profile ADD COLUMN {column} {column_type}'
            )
        except sqlite3.OperationalError as exc:
            # Concurrent API/test initialization can race on additive
            # migrations. Only the duplicate-column winner is harmless.
            if "duplicate column name" not in str(exc).lower():
                raise
    conn.commit()


class AthleteProfileStore:
    """SQLite persistence for athlete_profile snapshots.

    Operates over a caller-owned connection and the same scalar cleaner the
    Database uses; transaction ownership (commit/close) stays with the caller.
    """

    def __init__(self, conn: sqlite3.Connection, clean_value: CleanValue):
        self._conn = conn
        self._clean_value = clean_value

    def save(self, profile: Mapping[str, Any]) -> None:
        """Insert a new append-only snapshot."""
        threshold_pace = self._clean_value(
            profile.get('threshold_pace_seconds_per_km')
        )
        swim_threshold_pace = self._clean_value(
            profile.get('swim_threshold_pace_seconds_per_100m')
        )
        self._conn.execute(
            '''
            INSERT INTO athlete_profile (
                ftp,
                weight_kg,
                lthr,
                threshold_pace_seconds_per_km,
                threshold_pace_source,
                threshold_pace_synced_at,
                swim_threshold_pace_seconds_per_100m,
                swim_threshold_pace_source,
                swim_threshold_pace_synced_at,
                source
            )
            VALUES (
                ?, ?, ?, ?, ?,
                CASE
                    WHEN ? IS NOT NULL THEN COALESCE(?, CURRENT_TIMESTAMP)
                    ELSE NULL
                END,
                ?, ?, CASE
                    WHEN ? IS NOT NULL THEN COALESCE(?, CURRENT_TIMESTAMP)
                    ELSE NULL
                END,
                ?
            )
            ''',
            (
                self._clean_value(profile.get('ftp')),
                self._clean_value(profile.get('weight_kg')),
                self._clean_value(profile.get('lthr')),
                threshold_pace,
                profile.get('threshold_pace_source'),
                threshold_pace,
                profile.get('threshold_pace_synced_at'),
                swim_threshold_pace,
                profile.get('swim_threshold_pace_source'),
                swim_threshold_pace,
                profile.get('swim_threshold_pace_synced_at'),
                profile.get('source'),
            ),
        )

    def get(self) -> Optional[Dict[str, Any]]:
        """Return the newest snapshot, or None if nothing has been saved."""
        cursor = self._conn.cursor()
        cursor.execute(
            '''
            SELECT
                ftp,
                weight_kg,
                lthr,
                threshold_pace_seconds_per_km,
                threshold_pace_source,
                threshold_pace_synced_at,
                swim_threshold_pace_seconds_per_100m,
                swim_threshold_pace_source,
                swim_threshold_pace_synced_at,
                source,
                synced_at
            FROM athlete_profile
            ORDER BY synced_at DESC, id DESC
            LIMIT 1
            '''
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return {
            'ftp': row[0],
            'weight_kg': row[1],
            'lthr': row[2],
            'threshold_pace_seconds_per_km': row[3],
            'threshold_pace_source': row[4],
            'threshold_pace_synced_at': row[5],
            'swim_threshold_pace_seconds_per_100m': row[6],
            'swim_threshold_pace_source': row[7],
            'swim_threshold_pace_synced_at': row[8],
            'source': row[9],
            'synced_at': row[10],
        }

    def ftp_history(self) -> list[tuple]:
        """Return [(sync_date, ftp), ...] sorted ascending, non-NULL ftp only.

        The date-accurate FTP resolution (#451/#453) and the shadow bike
        power+HR pair features (#444 S1) both read this append-only history;
        rows without a parseable synced_at or a numeric ftp are skipped.
        """
        cursor = self._conn.cursor()
        cursor.execute(
            '''
            SELECT synced_at, ftp
            FROM athlete_profile
            WHERE ftp IS NOT NULL
            ORDER BY synced_at, id
            '''
        )
        history = []
        for synced_at, ftp in cursor.fetchall():
            try:
                sync_date = datetime.strptime(str(synced_at)[:10], "%Y-%m-%d").date()
                ftp_value = float(ftp)
            except (TypeError, ValueError):
                continue
            history.append((sync_date, ftp_value))
        return history

    def ftp_timeline(self) -> list[tuple]:
        """Return ``(synced_at_utc, ftp)`` entries for absolute provenance.

        SQLite's naive ``CURRENT_TIMESTAMP`` is interpreted as UTC by the
        shared parser. Rows without a parseable timestamp or numeric FTP are
        omitted; callers retain :meth:`ftp_history` for legacy date fallback.
        """
        from data.data_processor import parse_utc_instant

        cursor = self._conn.cursor()
        cursor.execute(
            '''
            SELECT synced_at, ftp
            FROM athlete_profile
            WHERE ftp IS NOT NULL
            ORDER BY synced_at, id
            '''
        )
        timeline = []
        for synced_at, ftp in cursor.fetchall():
            sync_at_utc = parse_utc_instant(synced_at)
            try:
                ftp_value = float(ftp)
            except (TypeError, ValueError):
                continue
            if sync_at_utc is not None:
                timeline.append((sync_at_utc, ftp_value))
        timeline.sort(key=lambda entry: entry[0])
        return timeline
