"""Retained calendar proposals and receipts in the planning database."""

import sqlite3


def initialize(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS swim_calendar_previews (
            preview_id TEXT PRIMARY KEY NOT NULL,
            request_digest TEXT NOT NULL,
            preview_json TEXT NOT NULL,
            preview_digest TEXT NOT NULL,
            applied_checkpoint_id INTEGER REFERENCES planning_checkpoints(id)
        )
    """)
