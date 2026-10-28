#!/usr/bin/env python3
"""Synthetic SQLite characterization; not the automatic backup implementation."""
from pathlib import Path
import hashlib
import json
import sqlite3
import sys
import tempfile
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from scripts.sqlite_backup_restore import inspect_relocation_database  # noqa: E402


def main():
    with tempfile.TemporaryDirectory(prefix='snapshot-policy-probe-') as raw:
        root = Path(raw)
        source, output = root / 'source.db', root / 'snapshot.db'
        with sqlite3.connect(source) as conn:
            conn.execute('PRAGMA journal_mode=WAL')
            conn.execute('CREATE TABLE activities(activity_id TEXT PRIMARY KEY,date TEXT,sport TEXT,duration_minutes REAL)')
            conn.execute('CREATE TABLE pairs(id INTEGER PRIMARY KEY,a INTEGER,b INTEGER,pad TEXT)')
            conn.executemany('INSERT INTO pairs VALUES (?,0,0,?)', ((i, 'x'*2000) for i in range(1000)))
        started, stop = threading.Event(), threading.Event()
        writes = []
        failures = []
        def writer():
            try:
                with sqlite3.connect(source, timeout=2) as conn:
                    started.set()
                    for i in range(80):
                        if stop.is_set(): break
                        conn.execute('UPDATE pairs SET a=a+1,b=b+1 WHERE id=?', (i,))
                        conn.commit()
                        writes.append(i)
                        time.sleep(.002)
            except Exception as exc:
                failures.append(type(exc).__name__)
        thread = threading.Thread(target=writer)
        thread.start()
        assert started.wait(2)
        overlap = []
        deadline = time.monotonic()+5
        def progress(*_):
            assert time.monotonic()<deadline
            overlap.append(thread.is_alive() and bool(writes))
            time.sleep(.0001)
        try:
            with sqlite3.connect(source.as_uri()+'?mode=ro', uri=True) as src, sqlite3.connect(output) as dst:
                src.backup(dst, pages=32, progress=progress, sleep=.001)
        finally:
            stop.set()
            thread.join(3)
        assert not thread.is_alive() and not failures and writes and any(overlap)
        with sqlite3.connect(output) as conn:
            assert conn.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
            assert conn.execute('SELECT COUNT(*) FROM pairs WHERE a<>b').fetchone()[0]==0
            assert conn.execute('SELECT COUNT(*) FROM pairs').fetchone()[0]==1000
        first = inspect_relocation_database(output)
        with sqlite3.connect(output) as conn:
            conn.execute('VACUUM')
        assert first == inspect_relocation_database(output)
        generation=hashlib.sha256(json.dumps(first,sort_keys=True).encode()).hexdigest()
        print(json.dumps({'online_consistency':'PASS','overlapping_writer':True,
                          'unchanged_logical_generation':'PASS','generation_length':len(generation)}))


if __name__ == '__main__':
    main()
