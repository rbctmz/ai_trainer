"""BDD gates for TD-003 (#347): unified SQLite concurrency policy.

Every Database connection must go through one factory with WAL journal mode
and a bounded busy timeout, and a writer+reader race on a temporary database
must show no lost data and bounded latency. TD-001 restore stays sidecar-safe.
"""
from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path

import pytest

from data.database import Database


pytestmark = pytest.mark.smoke
REPO_ROOT = Path(__file__).resolve().parents[2]
_ROWS = 200


def test_journal_mode_is_wal_after_init(tmp_path):
    Database(str(tmp_path / "concurrency.db"))

    conn = sqlite3.connect(str(tmp_path / "concurrency.db"))
    try:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    finally:
        conn.close()


def test_factory_connection_sets_bounded_busy_timeout(tmp_path):
    db = Database(str(tmp_path / "concurrency.db"))

    conn = db._connect()
    try:
        assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 30000
    finally:
        conn.close()


def test_race_writer_reader_loses_no_data_and_stays_bounded(tmp_path):
    db = Database(str(tmp_path / "race.db"))
    writer_done = threading.Event()
    observed = []

    def writer():
        conn = db._connect()
        try:
            for index in range(_ROWS):
                conn.execute(
                    "INSERT OR REPLACE INTO activities "
                    "(activity_id, date, sport, tss) VALUES (?, ?, ?, ?)",
                    (f"race-{index}", "2026-08-03", "running", 50.0),
                )
                conn.commit()
        finally:
            conn.close()
            writer_done.set()

    def reader():
        conn = db._connect()
        try:
            while not writer_done.is_set():
                row = conn.execute("SELECT COUNT(*) FROM activities").fetchone()
                observed.append(int(row[0]))
        finally:
            conn.close()

    started = time.monotonic()
    threads = [threading.Thread(target=writer), threading.Thread(target=reader)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    elapsed = time.monotonic() - started

    assert elapsed < 60
    final = db._connect().execute("SELECT COUNT(*) FROM activities").fetchone()[0]
    assert final == _ROWS
    assert observed


def test_all_database_connections_use_the_factory():
    source = (REPO_ROOT / "data/database.py").read_text(encoding="utf-8")

    assert "sqlite3.connect(self.db_path)" not in source
    assert "self._connect()" in source
