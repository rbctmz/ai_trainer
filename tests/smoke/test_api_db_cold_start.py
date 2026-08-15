"""Холодный старт одного пути БД: строительство Database сериализовано (issue #439).

До фикса ``lru_cache`` в ``api/deps.py`` не сериализовал вызовы: параллельные
первые запросы строили ``Database`` одновременно, обе конструкции выполняли
``PRAGMA journal_mode = WAL`` → «database is locked» → HTTP 500 (наблюдалось
E2E-тестом web-стека, PR #438).
"""

from __future__ import annotations

import threading

import pytest

pytestmark = pytest.mark.smoke

from api import deps as api_deps  # noqa: E402
from data.database import Database  # noqa: E402


def test_db_for_path_cold_start_is_serialized(tmp_path, monkeypatch) -> None:
    """Параллельный холодный старт: ровно одна конструкция Database, без ошибок."""
    constructed: list[int] = []

    class CountingDatabase(Database):
        def __init__(self, path):
            constructed.append(1)
            super().__init__(path)

    monkeypatch.setattr(api_deps, "Database", CountingDatabase)
    path = str(tmp_path / "cold-start.db")

    errors: list[BaseException] = []

    def worker() -> None:
        try:
            api_deps._db_for_path(path)
        except BaseException as exc:  # noqa: BLE001 - собираем всё, включая OperationalError
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(16)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert not errors, f"ошибки холодного старта: {errors!r}"
    assert len(constructed) == 1, (
        f"Database построен {len(constructed)} раз — строительство не сериализовано"
    )


def test_db_for_path_returns_same_instance(tmp_path, monkeypatch) -> None:
    """Повторные обращения к одному пути дают один и тот же экземпляр."""

    class MarkerDatabase(Database):
        pass

    monkeypatch.setattr(api_deps, "Database", MarkerDatabase)
    path = str(tmp_path / "same-instance.db")

    first = api_deps._db_for_path(path)
    assert first is api_deps._db_for_path(path)
    assert isinstance(first, MarkerDatabase)
