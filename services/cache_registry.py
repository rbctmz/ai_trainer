"""Headless-реестр сброса кэшей данных.

Зачем отдельный модуль (issue #602). ``services/data_cache`` импортирует
Streamlit ради ``st.cache_data``, а ``services.sync`` и ``services/demo_mode``
нужен от него только сброс кэша. Импорт ``data_cache`` на уровне модуля затягивал
Streamlit в граф продуктового API: ``api/routers/system.py`` → ``services.demo_mode``
→ ``services.data_cache`` → ``streamlit``.

Здесь нет ни Streamlit, ни pandas — только реестр вызываемых объектов, поэтому
импорт безопасен для API. ``data_cache`` регистрирует свою очистку при импорте,
а ``sync`` и ``demo_mode`` дёргают реестр.

Реестр может быть пуст: если ``data_cache`` не импортировался (headless-процесс
без Streamlit), кэшей и нет — сброс становится no-op, а не падением.
"""
from __future__ import annotations

from typing import Any, Callable

# Список, а не set: порядок сброса предсказуем, а дубликаты исключает
# регистрация по одному разу на модуль.
_CACHE_CLEARERS: list[Callable[[], Any]] = []


def register_cache_clearer(clearer: Callable[[], Any]) -> None:
    """Зарегистрировать функцию сброса кэша.

    Вызывается ``services.data_cache`` при импорте. Повторная регистрация того же
    объекта игнорируется, чтобы повторный импорт не накапливал дубликаты.
    """
    if clearer not in _CACHE_CLEARERS:
        _CACHE_CLEARERS.append(clearer)


def clear_caches() -> None:
    """Сбросить все зарегистрированные кэши.

    No-op, когда ничего не зарегистрировано (headless-режим без Streamlit).
    """
    for clearer in list(_CACHE_CLEARERS):
        clearer()


def registered_clearers() -> tuple[Callable[[], Any], ...]:
    """Снимок реестра — для диагностики и тестов."""
    return tuple(_CACHE_CLEARERS)


def reset_registry() -> None:
    """Очистить реестр. Только для тестов."""
    _CACHE_CLEARERS.clear()


__all__ = [
    "clear_caches",
    "register_cache_clearer",
    "registered_clearers",
    "reset_registry",
]
