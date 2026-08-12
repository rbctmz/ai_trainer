"""Bounded SQLite reads for the aggregate data-coverage inventory (#427)."""
from __future__ import annotations

import sqlite3
from typing import Any


class DataCoverageStore:
    """Read aggregate presence/provenance without exposing metric values."""

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def load(self, start_date: str, end_date: str) -> dict[str, Any]:
        canonical_count, latest_date = self._conn.execute(
            """SELECT COUNT(*), MAX(date)
               FROM activities
               WHERE date BETWEEN ? AND ?""",
            (start_date, end_date),
        ).fetchone()

        provider_rows = self._conn.execute(
            """SELECT links.provider, COUNT(DISTINCT links.canonical_activity_id)
               FROM activity_provider_links AS links
               JOIN activities AS activity
                 ON CAST(activity.activity_id AS TEXT) =
                    CAST(links.canonical_activity_id AS TEXT)
               WHERE activity.date BETWEEN ? AND ?
                 AND links.provider IN ('garmin', 'intervals')
               GROUP BY links.provider""",
            (start_date, end_date),
        ).fetchall()

        unattributed_count = self._conn.execute(
            """SELECT COUNT(*)
               FROM activities AS activity
               WHERE activity.date BETWEEN ? AND ?
                 AND NOT EXISTS (
                     SELECT 1
                     FROM activity_provider_links AS links
                     WHERE CAST(links.canonical_activity_id AS TEXT) =
                           CAST(activity.activity_id AS TEXT)
                       AND links.provider IN ('garmin', 'intervals')
                 )""",
            (start_date, end_date),
        ).fetchone()[0]

        metric_rows = self._conn.execute(
            """SELECT 'sleep_duration', date, total_sleep_source
               FROM sleep_data
               WHERE date BETWEEN ? AND ? AND total_sleep_minutes IS NOT NULL
               UNION ALL
               SELECT 'sleep_score', date, sleep_score_source
               FROM sleep_data
               WHERE date BETWEEN ? AND ? AND sleep_score IS NOT NULL
               UNION ALL
               SELECT 'hrv', date, rmssd_source
               FROM hrv_data
               WHERE date BETWEEN ? AND ? AND rmssd IS NOT NULL
               UNION ALL
               SELECT 'resting_hr', date, resting_hr_source
               FROM daily_health
               WHERE date BETWEEN ? AND ? AND resting_hr IS NOT NULL
               UNION ALL
               SELECT 'steps', date, steps_source
               FROM daily_health
               WHERE date BETWEEN ? AND ? AND steps IS NOT NULL
               ORDER BY 1, 2""",
            (start_date, end_date) * 5,
        ).fetchall()

        return {
            "activities": {
                "canonical_count": int(canonical_count or 0),
                "latest_date": str(latest_date) if latest_date else None,
                "provider_rows": provider_rows,
                "unattributed_count": int(unattributed_count or 0),
            },
            "metric_rows": metric_rows,
        }

