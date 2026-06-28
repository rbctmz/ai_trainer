"""Shared dependencies for the FastAPI layer.

The key idea behind the web migration is that the backend stays Streamlit-free.
``StateManager`` already supports being constructed around any mapping, so the
API wraps a plain ``dict`` instead of ``st.session_state``. That gives the same
typed facade (``goal_plan``, ``latest_planning_checkpoint``,
``resolved_goal_plan_context`` …) while reading from the local SQLite database,
with no Streamlit runtime in the loop.

Demo mode: every read endpoint accepts ``?demo=1`` (resolved here), which routes
to a SEPARATE demo database file. The real ``ai_trainer.db`` is never touched by
demo seeding/clearing — important because the demo seeder wipes its database.
"""
from __future__ import annotations

import os
from functools import lru_cache
from typing import Any, Dict

from fastapi import Query

from config.settings import Settings
from data.database import Database
from state import StateManager


def _demo_db_path() -> str:
    real = Settings.DATABASE_PATH or "ai_trainer.db"
    base, ext = os.path.splitext(real)
    return os.getenv("DEMO_DATABASE_PATH", f"{base}_demo{ext or '.db'}")


DEMO_DB_PATH = _demo_db_path()


@lru_cache(maxsize=4)
def _db_for_path(path: str) -> Database:
    return Database(path)


def real_database() -> Database:
    return _db_for_path(Settings.DATABASE_PATH or "ai_trainer.db")


def demo_database() -> Database:
    return _db_for_path(DEMO_DB_PATH)


def get_database(demo: bool = Query(False)) -> Database:
    """Return the active Database for the request.

    ``?demo=1`` routes to the isolated demo database so the real cache is safe.
    """
    return demo_database() if demo else real_database()


class SessionDict(dict):
    """Dict with attribute access.

    StateManager.__setattr__ does ``setattr(self._session, key, value)`` (works
    for Streamlit's SessionState). A plain dict has no attributes, so headless
    *writes* (e.g. demo seeding) fail. This subclass maps attribute access to
    items so the same code path works without Streamlit.
    """

    def __getattr__(self, key: str) -> Any:
        try:
            return self[key]
        except KeyError as exc:
            raise AttributeError(key) from exc

    def __setattr__(self, key: str, value: Any) -> None:
        self[key] = value

    def __delattr__(self, key: str) -> None:
        try:
            del self[key]
        except KeyError as exc:
            raise AttributeError(key) from exc


def make_headless_state(database: Database | None = None) -> StateManager:
    """Build a StateManager backed by an attribute-accessible dict.

    Plain helper (NOT a FastAPI dependency, so it can take a ``database`` arg).
    Pass ``database`` to bind a specific handle, e.g. the demo DB.
    """
    session: Dict[str, Any] = SessionDict()
    if database is not None:
        session["database"] = database
    return StateManager(session)


def get_headless_state() -> StateManager:
    """FastAPI dependency: a fresh StateManager backed by an attribute dict.

    Stateless per request — heavy data lives in SQLite and is read lazily.
    """
    return make_headless_state()
