"""Utilities for working with Streamlit session state."""
from __future__ import annotations

from typing import Any, Callable, Dict, MutableMapping, Optional, TYPE_CHECKING, cast

import streamlit as st

from .schema import AppState, DataState, IntegrationState, UIState

if TYPE_CHECKING:  # pragma: no cover - only for type checking
    from data.database import Database
    from data.garmin_client import GarminClient
    from models.chat_manager import ChatManager
    from models.ai_coach_universal import UniversalAICoach
    from models.ai_tools import AITools
    from streamlit.runtime.state import SessionState


class StateManager:
    """Wraps access to Streamlit session state with a typed facade."""

    def __getattr__(self, item):
        if item.startswith('_'):
            raise AttributeError(item)
        return getattr(self._session, item)

    def __setattr__(self, key, value):
        if key.startswith('_') or key in {"_session"}:
            object.__setattr__(self, key, value)
        else:
            setattr(self._session, key, value)

    def __contains__(self, key):
        return key in self._session

    _PRIMITIVE_DEFAULTS: Dict[str, Any] = {
        "ai_coach_handoff": None,
        "dark_mode": False,
        "demo_mode": False,
        "selected_page": "📊 Дашборд",
        "confirm_clear": False,
        "context_loaded": False,
        "current_chat_id": None,
        "goal_plan": None,
        "last_ai_weekly_plan_text": None,
        "page": "📊 Дашборд",
        "planner_goal_type": None,
        "selected_provider": None,
        "switch_to_chat_tab": False,
        "use_custom_theme": True,
    }

    _MUTABLE_DEFAULT_FACTORIES: Dict[str, Callable[[], Any]] = {
        "chat_messages": list,
        "planner_mix": dict,
        "planner_weights": dict,
    }

    def __init__(self, session_state: Optional["SessionState"] = None) -> None:
        raw_session = session_state if session_state is not None else st.session_state
        self._session: MutableMapping[str, Any] = cast(MutableMapping[str, Any], raw_session)
        self._bootstrap_defaults()

    # ------------------------------------------------------------------
    # Bootstrap helpers
    # ------------------------------------------------------------------
    def _bootstrap_defaults(self) -> None:
        if "dark_mode" not in self._session:
            theme_state = self._session.get("_theme")
            base_theme = None
            if isinstance(theme_state, dict):
                base_theme = theme_state.get("base")
            if base_theme is None and callable(getattr(st, "get_option", None)):
                base_theme = st.get_option("theme.base")
            self._session["dark_mode"] = (base_theme or "light").lower() == "dark"

        for key, value in self._PRIMITIVE_DEFAULTS.items():
            if key == "dark_mode":
                continue
            self._session.setdefault(key, value)

        for key, factory in self._MUTABLE_DEFAULT_FACTORIES.items():
            if key not in self._session:
                self._session[key] = factory()

    # ------------------------------------------------------------------
    # Lazy dependency providers
    # ------------------------------------------------------------------
    @property
    def database(self) -> "Database":
        from data.database import Database

        database = self._session.get("database")
        if database is None:
            database = Database()
            self._session["database"] = database
        return database

    @property
    def garmin_client(self) -> "GarminClient":
        from data.garmin_client import GarminClient

        client = self._session.get("garmin_client")
        if client is None:
            client = GarminClient()
            self._session["garmin_client"] = client
        return client

    @property
    def chat_manager(self) -> "ChatManager":
        from models.chat_manager import ChatManager

        manager = self._session.get("chat_manager")
        if manager is None:
            manager = ChatManager()
            self._session["chat_manager"] = manager
        return manager

    @property
    def ai_coach(self) -> Optional["UniversalAICoach"]:
        return self._session.get("ai_coach")

    @ai_coach.setter
    def ai_coach(self, value: Optional["UniversalAICoach"]) -> None:
        self._session["ai_coach"] = value

    @property
    def ai_tools(self) -> "AITools":
        from models.ai_tools import AITools

        tools = self._session.get("ai_tools")
        if tools is None:
            tools = AITools(self.database)
            self._session["ai_tools"] = tools
        return tools

    # ------------------------------------------------------------------
    # UI convenience helpers
    # ------------------------------------------------------------------
    @property
    def dark_mode(self) -> bool:
        return bool(self._session.get("dark_mode", False))

    @dark_mode.setter
    def dark_mode(self, value: bool) -> None:
        self._session["dark_mode"] = bool(value)

    def toggle_dark_mode(self) -> bool:
        new_value = not self.dark_mode
        self.dark_mode = new_value
        return new_value

    @property
    def selected_page(self) -> str:
        return self._session.get("selected_page", "📊 Дашборд")

    @selected_page.setter
    def selected_page(self, value: str) -> None:
        self._session["selected_page"] = value

    @property
    def confirm_clear(self) -> bool:
        return bool(self._session.get("confirm_clear", False))

    @confirm_clear.setter
    def confirm_clear(self, value: bool) -> None:
        self._session["confirm_clear"] = value

    @property
    def selected_provider(self) -> Optional[str]:
        return self._session.get("selected_provider")

    @selected_provider.setter
    def selected_provider(self, value: Optional[str]) -> None:
        self._session["selected_provider"] = value

    @property
    def use_custom_theme(self) -> bool:
        return bool(self._session.get("use_custom_theme", True))

    @use_custom_theme.setter
    def use_custom_theme(self, value: bool) -> None:
        self._session["use_custom_theme"] = bool(value)

    @property
    def demo_mode(self) -> bool:
        return bool(self._session.get("demo_mode", False))

    @demo_mode.setter
    def demo_mode(self, value: bool) -> None:
        self._session["demo_mode"] = bool(value)

    @property
    def current_chat_id(self):
        return self._session.get("current_chat_id")

    @current_chat_id.setter
    def current_chat_id(self, value):
        self._session["current_chat_id"] = value

    @property
    def planner_mix(self):
        return self._session.get("planner_mix", {})

    @planner_mix.setter
    def planner_mix(self, value):
        self._session["planner_mix"] = value

    @property
    def planner_weights(self):
        return self._session.get("planner_weights", {})

    @planner_weights.setter
    def planner_weights(self, value):
        self._session["planner_weights"] = value

    @property
    def goal_plan(self):
        return self._session.get("goal_plan")

    @goal_plan.setter
    def goal_plan(self, value):
        self._session["goal_plan"] = value

    @property
    def planner_goal_type(self):
        return self._session.get("planner_goal_type")

    @planner_goal_type.setter
    def planner_goal_type(self, value):
        self._session["planner_goal_type"] = value

    @property
    def last_ai_weekly_plan_text(self):
        return self._session.get("last_ai_weekly_plan_text")

    @last_ai_weekly_plan_text.setter
    def last_ai_weekly_plan_text(self, value):
        self._session["last_ai_weekly_plan_text"] = value

    @property
    def chat_messages(self):
        return self._session.get("chat_messages", [])

    @chat_messages.setter
    def chat_messages(self, value) -> None:
        self._session["chat_messages"] = value

    @property
    def data_context(self):
        return self._session.get("data_context")

    @data_context.setter
    def data_context(self, value) -> None:
        self._session["data_context"] = value

    @property
    def context_loaded(self) -> bool:
        return bool(self._session.get("context_loaded", False))

    @context_loaded.setter
    def context_loaded(self, value: bool) -> None:
        self._session["context_loaded"] = value

    @property
    def switch_to_chat_tab(self) -> bool:
        return bool(self._session.get("switch_to_chat_tab", False))

    @switch_to_chat_tab.setter
    def switch_to_chat_tab(self, value: bool) -> None:
        self._session["switch_to_chat_tab"] = value

    @property
    def ai_coach_handoff(self):
        return self._session.get("ai_coach_handoff")

    @ai_coach_handoff.setter
    def ai_coach_handoff(self, value) -> None:
        self._session["ai_coach_handoff"] = value

    # ------------------------------------------------------------------
    # Snapshot helpers
    # ------------------------------------------------------------------
    def snapshot(self) -> AppState:
        """Return a typed snapshot of the current session state."""
        ui_state = UIState(
            dark_mode=self.dark_mode,
            selected_page=self.selected_page,
            confirm_clear=self.confirm_clear,
            sidebar_expanded=self._session.get("sidebar_expanded", True),
        )

        integrations_state = IntegrationState(
            garmin_authenticated=getattr(self.garmin_client, "is_authenticated", False),
            demo_mode=self.demo_mode,
            last_sync_status=self._session.get("last_sync_status"),
            syncing_in_progress=self._session.get("syncing_in_progress", False),
        )

        data_state = DataState(
            activities_range_days=self._session.get("activities_range_days", 30),
            hrv_range_days=self._session.get("hrv_range_days", 90),
            sleep_range_days=self._session.get("sleep_range_days", 7),
            cache=self._session.get("data_cache", {}),
        )

        return AppState(ui=ui_state, integrations=integrations_state, data=data_state)

    # ------------------------------------------------------------------
    # Convenience helpers for transient data
    # ------------------------------------------------------------------
    def reset_planner_overrides(self) -> None:
        self._session.pop("planner_mix", None)
        self._session.pop("planner_weights", None)
        self._session.pop("goal_plan", None)

    def clear_cached_context(self) -> None:
        self._session["context_loaded"] = False
        self._session["data_context"] = None


_manager: Optional[StateManager] = None


def get_state_manager() -> StateManager:
    """Get a singleton-ish state manager tied to st.session_state."""
    global _manager
    if _manager is None:
        _manager = StateManager()
    return _manager


__all__ = ["StateManager", "get_state_manager"]
