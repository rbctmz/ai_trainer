"""Shared dependencies for the FastAPI layer.

The key idea behind the web migration is that the backend stays Streamlit-free.
``StateManager`` already supports being constructed around any mapping, so the
API wraps a plain ``dict`` instead of ``st.session_state``. That gives the same
typed facade (``goal_plan``, ``latest_planning_checkpoint``,
``resolved_goal_plan_context`` …) while reading from the local SQLite database,
with no Streamlit runtime in the loop.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any, Dict

from data.database import Database
from state import StateManager


@lru_cache(maxsize=1)
def get_database() -> Database:
    """Return a process-wide Database handle (SQLite, local cache)."""
    return Database()


def get_headless_state() -> StateManager:
    """Return a StateManager backed by a plain dict (no st.session_state).

    A fresh wrapper per request keeps things stateless: the heavy data lives in
    SQLite and is read lazily through the StateManager properties.
    """
    session: Dict[str, Any] = {}
    return StateManager(session)
