"""Cached accessors for frequently used database queries.

Streamlit здесь только ради кэша (``st.cache_data``). Модуль обязан
импортироваться и в headless-режиме: его тянет ``services/demo_mode`` и
``services/sync``, а те — продуктовый API. Поэтому импорт Streamlit
необязателен, и при его отсутствии кэш просто выключается (issue #602).
"""
from __future__ import annotations

from typing import Any, Callable, Optional

import pandas as pd

from data.database import Database
from state import get_state_manager


def _passthrough(func: Callable[..., Any]) -> Callable[..., Any]:
    """Заглушка вместо ``st.cache_data``: считает, но не кэширует."""
    return func


try:  # pragma: no cover - ветка выбирается окружением, не логикой
    import streamlit as st
except ModuleNotFoundError:  # pragma: no cover - headless-окружение
    st = None  # type: ignore[assignment]


def _cache_data(func: Callable[..., Any]) -> Callable[..., Any]:
    """``st.cache_data`` при доступном Streamlit, иначе прозрачная обёртка."""
    if st is None:
        return _passthrough(func)
    return st.cache_data(show_spinner=False)(func)


def _copy_df(df: Optional[pd.DataFrame]) -> pd.DataFrame:
    if df is None:
        return pd.DataFrame()
    if isinstance(df, pd.DataFrame):
        return df.copy()
    try:
        return pd.DataFrame(df)
    except Exception:
        return pd.DataFrame()


def _resolve_db_path(explicit_db_path: Optional[str] = None) -> str:
    if explicit_db_path:
        return explicit_db_path
    return str(get_state_manager().database.db_path)


@_cache_data
def _load_activities_cached(db_path: str, days: int) -> pd.DataFrame:
    return _copy_df(Database(db_path).get_activities(days))


@_cache_data
def _load_hrv_cached(db_path: str, days: int) -> pd.DataFrame:
    return _copy_df(Database(db_path).get_hrv_data(days))


@_cache_data
def _load_sleep_cached(db_path: str, days: int) -> pd.DataFrame:
    return _copy_df(Database(db_path).get_sleep_data(days))


@_cache_data
def _load_daily_health_cached(db_path: str, days: int) -> pd.DataFrame:
    return _copy_df(Database(db_path).get_daily_health(days))


def load_activities(days: int, db_path: Optional[str] = None) -> pd.DataFrame:
    return _load_activities_cached(_resolve_db_path(db_path), days)


def load_hrv(days: int, db_path: Optional[str] = None) -> pd.DataFrame:
    return _load_hrv_cached(_resolve_db_path(db_path), days)


def load_sleep(days: int, db_path: Optional[str] = None) -> pd.DataFrame:
    return _load_sleep_cached(_resolve_db_path(db_path), days)


def load_daily_health(days: int, db_path: Optional[str] = None) -> pd.DataFrame:
    return _load_daily_health_cached(_resolve_db_path(db_path), days)


def clear_data_caches() -> None:
    """Сбросить кэши, если они есть.

    Без Streamlit загрузчики — прозрачные обёртки без ``.clear()``, поэтому
    проверяем наличие метода: headless-вызов должен быть no-op, а не падением.
    """
    for cached in (
        _load_activities_cached,
        _load_hrv_cached,
        _load_sleep_cached,
        _load_daily_health_cached,
    ):
        clear = getattr(cached, "clear", None)
        if callable(clear):
            clear()


__all__ = [
    "clear_data_caches",
    "load_activities",
    "load_daily_health",
    "load_hrv",
    "load_sleep",
]
