"""SQLite persistence for the activity-card cluster (TD-006, первый срез).

Extracted from ``data/database.py``: card tables DDL (tags, coach notes) and
the read/write methods for a single activity, its tags and its coach note live
here. ``Database`` keeps the same public methods as thin facades, so existing
importers keep working unchanged. Pattern: ``data/athlete_profile_store.py``.
"""
from __future__ import annotations

import sqlite3
from typing import Any, Callable


CleanValue = Callable[[Any], Any]

# Единый порядок колонок таблицы activities; Database реэкспортирует его как
# `_ACTIVITY_COLUMN_ORDER` для остальных (schema DDL, save/get activities).
ACTIVITY_COLUMN_ORDER = [
    'activity_id',
    'date',
    'started_at_utc',
    'sport',
    'duration_minutes',
    'moving_duration_minutes',
    'distance_km',
    'avg_hr',
    'max_hr',
    'avg_power',
    'max_power',
    'normalized_power',
    'elevation_gain',
    'calories',
    'training_effect',
    'anaerobic_effect',
    'activity_name',
    'description',
    'garmin_training_load',
    'source_tss',
    'moderate_intensity_minutes',
    'vigorous_intensity_minutes',
    'hr_time_in_zone_1_seconds',
    'hr_time_in_zone_2_seconds',
    'hr_time_in_zone_3_seconds',
    'hr_time_in_zone_4_seconds',
    'hr_time_in_zone_5_seconds',
    'tss_method',
    'tss',
    'tss_ftp_used',
    'tss_pace_used',
]


def create_activity_card_tables(conn: sqlite3.Connection) -> None:
    """Create the activity tags and coach-notes tables if they do not exist."""
    conn.execute(
        '''
        CREATE TABLE IF NOT EXISTS activity_tags (
            activity_id TEXT NOT NULL,
            tag TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (activity_id, tag)
        )
        '''
    )

    conn.execute(
        '''
        CREATE TABLE IF NOT EXISTS activity_coach_notes (
            activity_id TEXT PRIMARY KEY,
            body TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'coach',
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        '''
    )


class ActivityStore:
    """SQLite persistence for the activity-card cluster.

    Operates over a caller-owned connection and the same scalar cleaner the
    Database uses; transaction ownership (commit/close) stays with the caller.
    """

    def __init__(self, conn: sqlite3.Connection, clean_value: CleanValue):
        self._conn = conn
        self._clean_value = clean_value

    def get_activity(self, activity_id: str) -> dict[str, Any] | None:
        columns = list(ACTIVITY_COLUMN_ORDER)
        row = self._conn.execute(
            f"SELECT {', '.join(columns)} FROM activities WHERE activity_id = ?",
            (str(activity_id),),
        ).fetchone()
        if row is None:
            return None
        return dict(zip(columns, row))

    def get_activity_tags(self, activity_id: str) -> list[str]:
        rows = self._conn.execute(
            "SELECT tag FROM activity_tags WHERE activity_id = ? ORDER BY tag",
            (str(activity_id),),
        ).fetchall()
        return [row[0] for row in rows]

    def add_activity_tag(self, activity_id: str, tag: str) -> None:
        tag = str(tag or "").strip().lower()
        if not tag:
            raise ValueError("tag must be a non-empty string")
        self._conn.execute(
            "INSERT OR IGNORE INTO activity_tags (activity_id, tag) VALUES (?, ?)",
            (str(activity_id), tag),
        )

    def remove_activity_tag(self, activity_id: str, tag: str) -> None:
        self._conn.execute(
            "DELETE FROM activity_tags WHERE activity_id = ? AND tag = ?",
            (str(activity_id), str(tag or "").strip().lower()),
        )

    def get_all_activity_tags(self) -> dict[str, list[str]]:
        rows = self._conn.execute(
            "SELECT activity_id, tag FROM activity_tags ORDER BY tag"
        ).fetchall()
        tags_by_activity: dict[str, list[str]] = {}
        for activity_id, tag in rows:
            tags_by_activity.setdefault(activity_id, []).append(tag)
        return tags_by_activity

    def get_activity_coach_notes(self, activity_id: str) -> str | None:
        row = self._conn.execute(
            "SELECT body FROM activity_coach_notes WHERE activity_id = ?",
            (str(activity_id),),
        ).fetchone()
        return row[0] if row else None

    def save_activity_coach_notes(
        self, activity_id: str, body: str, source: str = "coach"
    ) -> None:
        body = str(body or "").strip()
        self._conn.execute(
            """
            INSERT INTO activity_coach_notes (activity_id, body, source, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(activity_id) DO UPDATE SET
                body = excluded.body,
                source = excluded.source,
                updated_at = CURRENT_TIMESTAMP
            """,
            (str(activity_id), body, str(source or "coach")),
        )

    def get_all_activity_coach_notes(self) -> dict[str, str]:
        rows = self._conn.execute(
            "SELECT activity_id, body FROM activity_coach_notes"
        ).fetchall()
        return {activity_id: body for activity_id, body in rows}


__all__ = [
    "ACTIVITY_COLUMN_ORDER",
    "ActivityStore",
    "create_activity_card_tables",
]
