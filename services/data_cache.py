"""Cached accessors for frequently used database queries."""
from __future__ import annotations

from typing import Optional

import pandas as pd
import streamlit as st

from data.database import Database
from state import get_state_manager


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


@st.cache_data(show_spinner=False)
def _load_activities_cached(db_path: str, days: int) -> pd.DataFrame:
    return _copy_df(Database(db_path).get_activities(days))


@st.cache_data(show_spinner=False)
def _load_hrv_cached(db_path: str, days: int) -> pd.DataFrame:
    return _copy_df(Database(db_path).get_hrv_data(days))


@st.cache_data(show_spinner=False)
def _load_sleep_cached(db_path: str, days: int) -> pd.DataFrame:
    return _copy_df(Database(db_path).get_sleep_data(days))


@st.cache_data(show_spinner=False)
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
    _load_activities_cached.clear()
    _load_hrv_cached.clear()
    _load_sleep_cached.clear()
    _load_daily_health_cached.clear()


__all__ = [
    "clear_data_caches",
    "load_activities",
    "load_daily_health",
    "load_hrv",
    "load_sleep",
]
