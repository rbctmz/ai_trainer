"""Issue #557 review P2: every provenance migration must survive an init race.

Two processes (API workers, tests, a legacy database opened twice) can observe a
new column as absent and both issue `ALTER TABLE ... ADD COLUMN`; the loser must
not abort startup with `duplicate column name`. `_ensure_sleep_columns` already
tolerated this, so the guard is pinned here for every migration helper that adds
columns.
"""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import pytest

from data.database import Database

pytestmark = pytest.mark.smoke


class _RaceCursor:
    """Cursor that loses the ALTER race but delegates everything else."""

    def __init__(self, real: sqlite3.Cursor, *, error: str = "duplicate column name: x"):
        self._real = real
        self._error = error

    def execute(self, sql, params=()):  # noqa: A003 - mirror the sqlite3 API
        if sql.strip().upper().startswith("ALTER TABLE"):
            raise sqlite3.OperationalError(self._error)
        return self._real.execute(sql, params)


def test_add_missing_columns_survives_the_lost_alter_race(tmp_path):
    db = Database(str(tmp_path / "race.db"))
    conn = db._connect()
    try:
        cursor = conn.cursor()
        # Another initializer already added the column: the guard must swallow it.
        Database._add_missing_columns(
            _RaceCursor(cursor), "sleep_data", {"sleep_score_observed_at": "TEXT"}, set()
        )
        # Any other SQLite error still surfaces.
        with pytest.raises(sqlite3.OperationalError):
            Database._add_missing_columns(
                _RaceCursor(cursor, error="no such table: nope"),
                "sleep_data",
                {"sleep_score_observed_at": "TEXT"},
                set(),
            )
    finally:
        conn.close()


def test_migration_helpers_do_not_add_columns_without_the_guard():
    """Source-level contract: no ALTER ADD COLUMN without duplicate tolerance."""
    source = Path("data/database.py").read_text(encoding="utf-8")
    helpers = re.findall(
        r"def (_ensure_\w+_columns)\(self, conn.*?\n(.*?)(?=\n    def )", source, re.S
    )
    assert helpers, "migration helpers not found"

    offenders = [
        name
        for name, body in helpers
        if "ADD COLUMN" in body and "duplicate column name" not in body
    ]
    assert not offenders, (
        "these helpers add columns without duplicate-column tolerance: "
        + ", ".join(offenders)
    )
