"""Hermetic contract for the one-off Intervals distance backfill (#417)."""
from __future__ import annotations

import json
import sqlite3

from config.settings import Settings
from data.database import Database
from scripts.backfill_intervals_distance import main


class _FakeIntervalsClient:
    def __init__(self) -> None:
        self.calls = []

    def is_configured(self) -> bool:
        return True

    def list_activities(self, oldest, newest):
        self.calls.append((oldest, newest))
        return [
            {"id": "intervals-only", "distance": 12_340},
            {"id": "paired-copy", "distance": 40_000},
        ]


def test_backfill_updates_intervals_payload_without_overwriting_garmin_primary(
    tmp_path,
    monkeypatch,
) -> None:
    db_path = str(tmp_path / "backfill.db")
    Database(db_path)
    monkeypatch.setattr(Settings, "PRIMARY_ACTIVITY_SOURCE", "garmin")
    conn = sqlite3.connect(db_path)
    try:
        conn.executemany(
            """INSERT INTO activities (activity_id, date, sport, distance_km)
               VALUES (?, '2026-07-10', 'cycling', ?)""",
            [("intervals-only-canonical", None), ("garmin-42", 42.5)],
        )
        conn.executemany(
            """INSERT INTO activity_provider_links
               (canonical_activity_id, provider, provider_activity_id,
                external_provider, external_id, provider_payload, match_status)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            [
                (
                    "intervals-only-canonical",
                    "intervals",
                    "intervals-only",
                    None,
                    None,
                    json.dumps({"date": "2026-07-10", "distance_km": None}),
                    "unmatched",
                ),
                (
                    "garmin-42",
                    "garmin",
                    "garmin-42",
                    "garmin",
                    "garmin-42",
                    None,
                    "matched",
                ),
                (
                    "garmin-42",
                    "intervals",
                    "paired-copy",
                    "garmin",
                    "garmin-42",
                    json.dumps({"date": "2026-07-10", "distance_km": None}),
                    "matched",
                ),
            ],
        )
        conn.commit()
    finally:
        conn.close()

    client = _FakeIntervalsClient()
    assert main(client=client, database_path=db_path) == 0

    conn = sqlite3.connect(db_path)
    try:
        distances = dict(
            conn.execute("SELECT activity_id, distance_km FROM activities").fetchall()
        )
        payloads = {
            provider_id: json.loads(payload)
            for provider_id, payload in conn.execute(
                """SELECT provider_activity_id, provider_payload
                   FROM activity_provider_links WHERE provider='intervals'"""
            ).fetchall()
        }
        first_snapshot = conn.execute(
            """SELECT activity_id, distance_km FROM activities ORDER BY activity_id"""
        ).fetchall(), conn.execute(
            """SELECT provider_activity_id, provider_payload
               FROM activity_provider_links ORDER BY provider, provider_activity_id"""
        ).fetchall()
    finally:
        conn.close()

    assert distances == {
        "intervals-only-canonical": 12.34,
        "garmin-42": 42.5,
    }
    assert payloads["intervals-only"]["distance_km"] == 12.34
    assert payloads["paired-copy"]["distance_km"] == 40.0

    assert main(client=client, database_path=db_path) == 0
    conn = sqlite3.connect(db_path)
    try:
        second_snapshot = conn.execute(
            """SELECT activity_id, distance_km FROM activities ORDER BY activity_id"""
        ).fetchall(), conn.execute(
            """SELECT provider_activity_id, provider_payload
               FROM activity_provider_links ORDER BY provider, provider_activity_id"""
        ).fetchall()
    finally:
        conn.close()
    assert second_snapshot == first_snapshot
