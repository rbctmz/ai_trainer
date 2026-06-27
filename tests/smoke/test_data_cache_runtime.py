from __future__ import annotations

import sqlite3
from types import SimpleNamespace

import pytest

from data.database import Database
from services import data_cache


pytestmark = pytest.mark.smoke


def test_load_activities_cache_isolated_by_database_path(tmp_path, monkeypatch: pytest.MonkeyPatch):
    empty_db_path = tmp_path / "empty.db"
    filled_db_path = tmp_path / "filled.db"

    Database(str(empty_db_path))
    Database(str(filled_db_path))

    with sqlite3.connect(filled_db_path) as conn:
        conn.execute(
            """
            INSERT INTO activities (
                activity_id,
                date,
                sport,
                duration_minutes,
                distance_km,
                tss
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("activity-1", "2026-06-27", "running", 42.0, 10.0, 75.0),
        )

    state = SimpleNamespace(database=Database(str(empty_db_path)))
    monkeypatch.setattr(data_cache, "get_state_manager", lambda: state)
    data_cache.clear_data_caches()

    first_result = data_cache.load_activities(30)
    assert first_result.empty

    state.database = Database(str(filled_db_path))
    second_result = data_cache.load_activities(30)

    assert len(second_result) == 1
    assert second_result.iloc[0]["activity_id"] == "activity-1"
