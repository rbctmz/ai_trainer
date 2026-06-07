"""Garmin connection sidebar component."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, Dict

import streamlit as st

from config.settings import Settings
from services import demo_mode as demo_mode_service, garmin as garmin_service

if TYPE_CHECKING:
    from state import StateManager


def get_garmin_form_defaults() -> Dict[str, str]:
    """Return safe defaults for the Garmin login form without exposing stored secrets."""
    return {"email": "", "password": ""}


def _clear_form_state() -> None:
    """Remove Garmin credential inputs from session state."""
    st.session_state.pop("garmin_email_input", None)
    st.session_state.pop("garmin_password_input", None)


def render_garmin_connection(
    state: "StateManager",
    render_profile: Callable[[Dict[str, Any]], None],
) -> None:
    """Render the Garmin sidebar connection widget."""
    connection_info = garmin_service.connection_info(state)
    authenticated = connection_info.get("authenticated", False)
    demo_mode = demo_mode_service.is_demo_mode(state)

    with st.sidebar.expander("🔗 Garmin Connect", expanded=not authenticated):
        if demo_mode and not authenticated:
            st.info("🎮 Демо-режим активен")
            st.caption("Сейчас приложение работает на временном sample dataset. Подключение Garmin отключит демо-режим и очистит временные данные.")
            if st.button("🚪 Выйти из демо-режима", width="stretch", key="exit_demo_mode_btn"):
                demo_mode_service.deactivate_demo_mode(state)
                _clear_form_state()
                st.rerun()
            st.markdown("---")

        if not authenticated:
            st.write("Подключитесь для синхронизации данных:")
            defaults = get_garmin_form_defaults()
            email = st.text_input("Email Garmin", value=defaults["email"], key="garmin_email_input")
            password = st.text_input("Пароль Garmin", type="password", value=defaults["password"], key="garmin_password_input")

            if Settings.GARMIN_EMAIL or Settings.GARMIN_PASSWORD:
                st.caption("Учётные данные Garmin из `.env` больше не подставляются в форму автоматически из соображений безопасности.")

            col1, _ = st.columns(2)
            with col1:
                if st.button("🔐 Подключиться"):
                    if email and password:
                        with st.spinner("Подключение к Garmin Connect..."):
                            if garmin_service.authenticate(state, email, password):
                                if demo_mode:
                                    demo_mode_service.deactivate_demo_mode(state)
                                _clear_form_state()
                                st.success("✅ Успешно подключено!")
                                st.rerun()
                            else:
                                error = garmin_service.auth_error(state) or "Неизвестно"
                                st.error(f"❌ Ошибка подключения: {error}")
                    else:
                        st.warning("Введите email и пароль")
            return

        st.success("✅ Подключено к Garmin Connect")

        connection_info = garmin_service.connection_info(state)
        if connection_info.get("using_garth"):
            st.info("🚀 Используется garth (улучшенный API)")
        else:
            st.info("📡 Используется garminconnect")

        profile, profile_error = garmin_service.user_profile_with_error(state)
        if profile is not None:
            render_profile(profile)
        elif profile_error:
            st.error(profile_error["message"])

        if connection_info.get("garth_available") and connection_info.get("using_garth"):
            if st.button("🔍 Тест garth", help="Проверить расширенные возможности garth"):
                with st.spinner("Тестирование garth..."):
                    test_results = garmin_service.test_garth_connection(state)
                    if test_results.get("authenticated"):
                        st.success("✅ Garth работает корректно")
                        with st.expander("📋 Детали garth тестирования"):
                            for method, status in test_results.get("test_results", {}).items():
                                st.write(f"• **{method}**: {status}")
                    else:
                        st.warning(f"⚠️ Проблема с garth: {test_results.get('error', 'Неизвестно')}")

        if st.button("🔌 Отключиться"):
            _clear_form_state()
            garmin_service.disconnect(state)
            st.rerun()
