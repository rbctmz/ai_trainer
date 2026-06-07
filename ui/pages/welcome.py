"""Welcome page renderer for unauthenticated users."""
from __future__ import annotations

from typing import TYPE_CHECKING

import streamlit as st
from services import demo_mode as demo_mode_service

if TYPE_CHECKING:
    from state import StateManager


def render_welcome_page(state: "StateManager") -> None:
    """Экран приветствия для неподключённых пользователей."""
    stats = state.database.get_database_stats()
    has_local_cache = any(stats.values())

    st.markdown("## Добро пожаловать в персональный AI тренер!")
    st.markdown("Выберите, как хотите войти в продукт: с реальными данными Garmin или на временном демо-наборе.")

    feature_col, path_col = st.columns([1, 2])

    with feature_col:
        st.markdown("### Что вы получите")
        st.markdown("- 📊 Анализ тренировочной нагрузки")
        st.markdown("- 💓 HRV и восстановление")
        st.markdown("- 😴 Качество сна")
        st.markdown("- 📈 Планирование тренировок")
        st.markdown("- 🤖 Следующие шаги от AI коуча")

    with path_col:
        garmin_col, demo_col = st.columns(2)

        with garmin_col:
            st.markdown("### 🔗 Garmin Connect")
            st.markdown("Для реального сценария:")
            st.markdown("1. Введите email и пароль Garmin в боковой панели")
            st.markdown("2. Подключитесь и синхронизируйте последние 30 дней")
            st.markdown("3. Откройте dashboard и AI coaching на своих данных")
            st.caption("Подходит, если вы хотите сразу работать со своей историей тренировок.")

        with demo_col:
            st.markdown("### 🎮 Демо-режим")
            st.markdown("Для быстрого знакомства:")
            st.markdown("1. Загрузится временный локальный набор sample data")
            st.markdown("2. Сразу откроется dashboard с метриками, сном и планированием")
            st.markdown("3. AI coaching будет доступен без подключения Garmin")
            st.caption("Демо-режим очищает локальный кэш и не смешивается с реальными данными.")

            if has_local_cache:
                st.warning("Запуск демо-режима заменит текущий локальный кэш данных на временный sample dataset.")

            if st.button(
                "🎮 Запустить демо-режим",
                type="primary",
                width="stretch",
                key="start_demo_mode_btn",
            ):
                result = demo_mode_service.activate_demo_mode(state)
                st.success(
                    "✅ Демо-режим активирован: "
                    f"{result['activities']} активностей, {result['hrv_days']} дней HRV, "
                    f"{result['sleep_days']} дней сна."
                )
                st.rerun()

    st.markdown("---")
    st.caption("Garmin onboarding требует аккаунт Garmin Connect. Демо-режим использует временные локальные данные и подходит для первого знакомства с интерфейсом.")
