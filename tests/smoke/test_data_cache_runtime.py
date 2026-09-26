from __future__ import annotations

import sqlite3
from datetime import date

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
            ("activity-1", date.today().isoformat(), "running", 42.0, 10.0, 75.0),
        )

    # Шов — резолвер пути по умолчанию. Раньше тест патчил
    # data_cache.get_state_manager; этот импорт стал ленивым (#645), и модуль
    # больше не держит его атрибутом. Смысл теста тот же: кэш обязан быть
    # изолирован по пути базы, а путь по умолчанию берётся из активного
    # состояния.
    current = {"path": str(empty_db_path)}
    monkeypatch.setattr(data_cache, "_default_db_path", lambda: current["path"])
    data_cache.clear_data_caches()

    first_result = data_cache.load_activities(30)
    assert first_result.empty

    current["path"] = str(filled_db_path)
    second_result = data_cache.load_activities(30)

    assert len(second_result) == 1
    assert second_result.iloc[0]["activity_id"] == "activity-1"
