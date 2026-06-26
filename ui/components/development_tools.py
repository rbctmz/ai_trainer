"""Development-only sidebar helpers."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING

import streamlit as st

from services.data_cache import clear_data_caches

if TYPE_CHECKING:
    from state import StateManager


def render_development_tools(state: "StateManager") -> None:
    """Render development helpers in the sidebar."""
    with st.sidebar.expander("🧪 Разработка", expanded=False):
        st.caption("Тестовые функции для демонстрации")
        _render_phase1_seed_button(state)


def _render_phase1_seed_button(state: "StateManager") -> None:
    """Add demo Phase 1 data for local development and demos."""
    database = state.database

    if st.button("🧪 Добавить тестовые данные Фазы 1", type="primary", key="add_test_data_btn"):
        try:
            sleep_data: dict[str, dict] = {}
            health_data: dict[str, dict] = {}
            status_data: dict[str, dict] = {}

            for i in range(7):
                date = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")

                sleep_data[date] = {
                    "total_sleep_minutes": 420 + (i % 2) * 30,
                    "deep_sleep_minutes": 80 + (i % 3) * 10,
                    "light_sleep_minutes": 280 + (i % 2) * 20,
                    "rem_sleep_minutes": 60 + (i % 3) * 10,
                    "awakenings_count": 1 + (i % 3),
                    "sleep_score": 75 + (i % 3) * 5,
                    "bedtime": f"23:{15 + (i % 3) * 15:02d}",
                    "wakeup_time": f"0{6 + (i % 2)}:{30 + (i % 2) * 15:02d}",
                    "sleep_efficiency": 88.0 + (i % 3) * 3,
                }

                health_data[date] = {
                    "resting_hr": 48 + (i % 4) * 2,
                    "steps": 8000 + i * 500,
                    "floors_climbed": 8 + (i % 3) * 2,
                    "calories_active": 350 + i * 30,
                    "calories_bmr": 1580,
                    "distance_meters": 6000 + i * 400,
                    "active_minutes": 40 + (i % 3) * 10,
                    "intensity_minutes": 15 + (i % 3) * 5,
                }

            today = datetime.now().strftime("%Y-%m-%d")
            status_data[today] = {
                "vo2_max": 48.5,
                "fitness_age": 32,
                "training_load_7d": 285.0,
                "training_status": "PRODUCTIVE",
                "training_readiness": 75.0,
                "recovery_time_hours": 14,
                "load_ratio": 1.05,
            }

            database.save_phase1_data(
                sleep_data=sleep_data,
                health_data=health_data,
                training_status=status_data,
            )

            st.success("✅ Тестовые данные добавлены")
            clear_data_caches()
        except Exception as exc:
            st.error(f"❌ Ошибка добавления тестовых данных: {exc}")
