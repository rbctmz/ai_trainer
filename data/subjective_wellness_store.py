"""Provider-owned daily self-report projection in the caller's transaction."""
from __future__ import annotations

import json
import sqlite3
from typing import Any


def create_subjective_wellness_table(conn: sqlite3.Connection) -> None:
    conn.execute('''CREATE TABLE IF NOT EXISTS subjective_wellness (
        provider TEXT NOT NULL CHECK(provider = 'intervals'),
        date TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        provider_updated_at TEXT,
        received_at TEXT NOT NULL,
        PRIMARY KEY(provider, date)
    )''')


def save_subjective_wellness(
    cursor: sqlite3.Cursor, day: str, observation: dict[str, Any], received_at: str,
) -> str | None:
    """Reject delayed reads and older provider revisions under the write lock."""
    payload = json.dumps(observation, sort_keys=True, ensure_ascii=False)
    updated = observation.get('provider_updated_at')
    row = cursor.execute(
        "SELECT payload_json, provider_updated_at, received_at FROM subjective_wellness "
        "WHERE provider='intervals' AND date=?", (day,),
    ).fetchone()
    if row and (received_at < row[2] or (updated and row[1] and updated < row[1])):
        return None
    cursor.execute('''INSERT INTO subjective_wellness
        (provider,date,payload_json,provider_updated_at,received_at)
        VALUES ('intervals',?,?,?,?)
        ON CONFLICT(provider,date) DO UPDATE SET
        payload_json=excluded.payload_json,
        provider_updated_at=excluded.provider_updated_at,
        received_at=excluded.received_at''', (day, payload, updated, received_at))
    return 'new' if row is None else 'updated' if row[0] != payload else None
