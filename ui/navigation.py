"""Navigation widgets for the Streamlit UI."""
from __future__ import annotations

from typing import List, Tuple

import streamlit as st

from state import StateManager

NavItem = Tuple[str, str, str]

_PRIMARY_NAV_ITEMS: List[NavItem] = [
    ("📊", "Дашборд", "📊 Дашборд"),
    ("🤖", "AI Коучинг", "🤖 AI Коучинг"),
    ("🏃‍♂️", "Активности", "🏃‍♂️ Активности"),
    ("📈", "Планирование", "📈 Планирование"),
    ("💓", "Анализ HRV", "💓 Анализ HRV"),
    ("😴", "Анализ сна", "😴 Анализ сна"),
    ("⚙️", "Управление", "⚙️ Управление данными"),
]

_ALL_PAGES: List[str] = [item[2] for item in _PRIMARY_NAV_ITEMS]
_ALL_PAGES.append("📋 Логи синхронизации")


def render_primary_navigation(state: StateManager) -> str:
    """Render the horizontal navigation bar and return the active page."""
    st.markdown("### 🧭 Навигация")

    selected_page = state.selected_page or "📊 Дашборд"
    cols = st.columns(len(_PRIMARY_NAV_ITEMS))

    for idx, (icon, short_name, full_name) in enumerate(_PRIMARY_NAV_ITEMS):
        with cols[idx]:
            is_active = selected_page == full_name
            button_type = "primary" if is_active else "secondary"
            if st.button(f"{icon}\n{short_name}", key=f"nav_{idx}", help=full_name, width="stretch", type=button_type):
                state.selected_page = full_name
                st.rerun()

    return state.selected_page or "📊 Дашборд"


def render_sidebar_navigation(state: StateManager, current_page: str) -> str:
    """Render the compact sidebar navigation for smaller screens."""
    st.sidebar.markdown("### 📱 Мобильное меню")
    pages = [item for item in _ALL_PAGES if item != "📋 Логи синхронизации"]
    index = pages.index(current_page) if current_page in pages else 0
    sidebar_page = st.sidebar.selectbox(
        "Выберите раздел:",
        pages,
        index=index,
        label_visibility="collapsed",
    )

    if sidebar_page != current_page:
        state.selected_page = sidebar_page
        st.rerun()

    return sidebar_page


def render_sidebar_utilities(state: StateManager) -> None:
    """Render extra navigation utilities in the sidebar."""
    with st.sidebar.expander("🔧 Дополнительные инструменты"):
        if st.button("📋 Логи синхронизации"):
            state.selected_page = "📋 Логи синхронизации"
            st.rerun()


__all__ = [
    "render_primary_navigation",
    "render_sidebar_navigation",
    "render_sidebar_utilities",
]
