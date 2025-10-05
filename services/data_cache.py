"""Cached accessors for frequently used database queries."""
from __future__ import annotations

from typing import Optional

import pandas as pd
import streamlit as st

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


@st.cache_data(show_spinner=False)
def load_activities(days: int) -> pd.DataFrame:
    db = get_state_manager().database
    return _copy_df(db.get_activities(days))


@st.cache_data(show_spinner=False)
def load_hrv(days: int) -> pd.DataFrame:
    db = get_state_manager().database
    return _copy_df(db.get_hrv_data(days))


@st.cache_data(show_spinner=False)
def load_sleep(days: int) -> pd.DataFrame:
    db = get_state_manager().database
    return _copy_df(db.get_sleep_data(days))


@st.cache_data(show_spinner=False)
def load_daily_health(days: int) -> pd.DataFrame:
    db = get_state_manager().database
    return _copy_df(db.get_daily_health(days))


def clear_data_caches() -> None:
    load_activities.clear()
    load_hrv.clear()
    load_sleep.clear()
    load_daily_health.clear()


__all__ = [
    "clear_data_caches",
    "load_activities",
    "load_daily_health",
    "load_hrv",
    "load_sleep",
]
