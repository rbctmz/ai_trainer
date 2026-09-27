"""Streamlit-обёртка над headless-фасадом состояния.

Вся логика состояния живёт в :mod:`utils.app_state` (issue #602): продуктовый
API не должен зависеть от Streamlit, поэтому фасад вынесен в модуль без
``import streamlit``. Здесь остаётся только Streamlit-специфика:

- ``st.session_state`` как источник mapping по умолчанию;
- подсказка темы оформления из ``st.get_option("theme.base")``.

Фасад намеренно лежит в ``utils/``, а не в ``state/``: обращение к
``state.<что угодно>`` исполняет ``state/__init__.py``, который импортирует этот
модуль, а значит и Streamlit. Пакет ``state`` целиком является Streamlit-слоем.

``st`` остаётся атрибутом модуля: тесты подменяют его
(``tests/smoke/test_state_manager_runtime.py``), поэтому обращение к нему —
часть контракта, а не деталь реализации.
"""
from __future__ import annotations

from typing import Any, MutableMapping, Optional, TYPE_CHECKING, cast

import streamlit as st

from utils.app_state import HeadlessState

if TYPE_CHECKING:  # pragma: no cover - only for type checking
    from streamlit.runtime.state import SessionState


class StateManager(HeadlessState):
    """Wraps access to Streamlit session state with a typed facade."""

    def __init__(self, session_state: Optional["SessionState"] = None) -> None:
        raw_session = session_state if session_state is not None else st.session_state
        self._session: MutableMapping[str, Any] = cast(MutableMapping[str, Any], raw_session)
        self._bootstrap_defaults()

    def _theme_base(self) -> Optional[str]:
        """Подсказка темы из Streamlit.

        С ``.streamlit/config.toml`` ``[theme] base = "light"`` (или выбор
        пользователя в настройках) это уважает системную схему через штатную
        обработку Streamlit, а не через хрупкий JS-обход.
        """
        if callable(getattr(st, "get_option", None)):
            return st.get_option("theme.base")
        return None


def get_state_manager() -> StateManager:
    """Return a fresh wrapper around the current Streamlit session state."""
    return StateManager()


__all__ = ["StateManager", "get_state_manager"]
