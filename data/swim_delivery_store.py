"""SQLite ownership for one authored provider write per calendar assignment."""

import sqlite3


def initialize(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS swim_delivery_previews (
            preview_id TEXT PRIMARY KEY,
            assignment_id TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            binding_json TEXT NOT NULL,
            binding_fingerprint TEXT NOT NULL,
            attempted INTEGER NOT NULL DEFAULT 0 CHECK (attempted IN (0, 1)),
            receipt_json TEXT
        )
    """)
    conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_swim_delivery_attempt
        ON swim_delivery_previews (assignment_id) WHERE attempted = 1
    """)
