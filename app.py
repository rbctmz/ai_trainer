import streamlit as st
from typing import Any, Dict

from config.settings import Settings
from state import get_state_manager
from utils.streamlit_compat import apply_streamlit_width_compat
from ui.components import render_chat_management, render_development_tools, render_garmin_connection
from ui.navigation import (
    render_primary_navigation,
    render_sidebar_navigation,
    render_sidebar_utilities,
)
from ui.pages import (
    render_activities_page,
    render_ai_coaching_page,
    render_data_management_page,
    render_dashboard_page,
    render_hrv_page,
    render_planning_page,
    render_sleep_page,
    render_sync_logs_page,
    render_welcome_page,
)
from ui.pages.ai_coaching import (
    create_chat_system_prompt_with_tools,
    format_tool_result,
    simulate_streaming_response,
)
from services import (
    acceptance_mode as acceptance_mode_service,
    demo_mode as demo_mode_service,
    garmin as garmin_service,
    sync as sync_service,
)

apply_streamlit_width_compat()

st.set_page_config(
    page_title="AI Trainer",
    page_icon="🏃‍♂️",
    layout="wide",
    initial_sidebar_state="expanded"
)

def render_garmin_profile(profile: Dict[str, Any]) -> None:
    """Отображает ключевую информацию профиля Garmin в удобном виде."""
    if not isinstance(profile, dict):
        st.caption("Не удалось прочитать профиль Garmin.")
        return

    display_name = (
        profile.get('displayName')
        or profile.get('display_name')
        or profile.get('fullName')
        or profile.get('full_name')
        or "Пользователь"
    )

    st.write(f"👤 **{display_name}**")

    fields = [
        ("Полное имя", ('fullName', 'full_name', 'userProfileFullName', 'user_profile_full_name')),
        ("Локация", ('location',)),
        ("Основной вид спорта", ('primaryActivity', 'primary_activity')),
        ("Дополнительная активность", ('otherActivity', 'other_activity')),
        ("Мотивация", ('motivation', 'otherMotivation', 'other_motivation')),
        ("Уровень Garmin", ('userLevel', 'user_level')),
    ]

    info_pairs = []
    for label, keys in fields:
        value = next((profile.get(key) for key in keys if profile.get(key)), None)
        if value is None:
            continue
        info_pairs.append((label, value))

    if info_pairs:
        col_left, col_right = st.columns(2)
        for index, (label, value) in enumerate(info_pairs):
            target_col = col_left if index % 2 == 0 else col_right
            target_col.markdown(f"**{label}:** {value}")
    elif profile:
        st.caption("Основные поля профиля не распознаны. Подробности доступны ниже.")
    else:
        st.caption("Garmin не вернул дополнительных данных профиля.")

    with st.expander("Детали профиля Garmin", expanded=False):
        st.json(profile)


def main():
    state = get_state_manager()
    acceptance_info = acceptance_mode_service.bootstrap_session(state)

    # Resolve the initial dark-mode preference (stored localStorage value >
    # OS prefers-color-scheme) via a one-shot JS roundtrip. The probe emits
    # only when no preference has been carried into the session yet, and the
    # resolved value is consumed by StateManager._bootstrap_defaults.
    from ui.theme_bootstrap import render_theme_probe
    render_theme_probe()

    from utils.modern_ui import ModernUI
    ModernUI.apply_modern_styles(dark_mode=state.dark_mode)

    header_status = "Acceptance sandbox" if acceptance_info.get("enabled") else "Training cockpit"
    ModernUI.render_app_header(status=header_status)

    if acceptance_info.get("enabled"):
        garmin_login_note = (
            "а реальный Garmin login отключён."
            if acceptance_mode_service.garmin_disabled()
            else "а реальный Garmin login разрешён."
        )
        st.info(
            "🧪 Acceptance mode активен. "
            "Приложение работает на изолированной временной БД, demo dataset может безопасно переинициализироваться, "
            + garmin_login_note
        )
        st.caption(f"Isolated DB: `{acceptance_info.get('database_path', Settings.DATABASE_PATH)}`")

    col1, col2 = st.sidebar.columns([4, 1])
    with col1:
        st.title("🏃‍♂️ AI Trainer")
    with col2:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🌙" if not state.dark_mode else "☀️",
                     help="Переключить тему",
                     width="stretch",
                     key="theme_toggle"):
            new_mode = state.toggle_dark_mode()
            from ui.theme_bootstrap import persist_theme_choice
            persist_theme_choice(new_mode)
            st.rerun()

    render_garmin_connection(state, render_profile=render_garmin_profile)

    if garmin_service.is_authenticated(state) or demo_mode_service.is_demo_mode(state):
        page = render_primary_navigation(state)
        sidebar_page = render_sidebar_navigation(state, page)
        if sidebar_page != page:
            page = sidebar_page

        render_sidebar_utilities(state)

        st.sidebar.markdown("---")

        _ = state.chat_manager  # Ensure chat manager initialised
        render_chat_management(state, expanded=page == "🤖 AI Коучинг")

        if Settings.SHOW_DEVELOPMENT_TOOLS:
            st.sidebar.markdown("---")
            render_development_tools(state)

        if page == "📊 Дашборд":
            render_dashboard_page(state, on_sync=lambda days: sync_data(days=days, state=state))
        elif page == "🏃‍♂️ Активности":
            render_activities_page(state)
        elif page == "💓 Анализ HRV":
            render_hrv_page(state)
        elif page == "😴 Анализ сна":
            render_sleep_page(state)
        elif page == "📈 Планирование":
            render_planning_page(state)
        elif page == "🤖 AI Коучинг":
            render_ai_coaching_page(state)
        elif page == "📋 Логи синхронизации":
            render_sync_logs_page()
        elif page == "⚙️ Управление данными":
            render_data_management_page(
                state,
                on_sync=lambda days: sync_data(days=days, state=state),
                on_clear_database=clear_database,
            )
    else:
        render_welcome_page(state)


def sync_data(days=30, state=None):
    """Синхронизация данных с Garmin Connect"""
    state = state or get_state_manager()
    state.syncing_in_progress = True

    if demo_mode_service.is_demo_mode(state) and not garmin_service.is_authenticated(state):
        state.syncing_in_progress = False
        st.info("🎮 Демо-режим использует временный локальный набор данных. Подключите Garmin, чтобы заменить демо-данные реальной синхронизацией.")
        return

    if demo_mode_service.is_demo_mode(state) and garmin_service.is_authenticated(state):
        demo_mode_service.deactivate_demo_mode(state)

    if not garmin_service.is_authenticated(state):
        state.syncing_in_progress = False
        st.error("Не подключен к Garmin Connect")
        return

    state.last_sync_status = None

    progress_container = st.empty()
    with progress_container.container():
        st.info("🔄 Начинаем синхронизацию...")
        progress_bar = st.progress(0, text="Подготовка...")
        status_text = st.empty()
        sync_stats = st.empty()

    def render_progress(update: sync_service.SyncProgressUpdate) -> None:
        status_text.text(update.message)
        if update.step_text:
            progress_bar.progress(update.percent, text=update.step_text)
        else:
            progress_bar.progress(update.percent)
        if update.stats_message:
            sync_stats.info(update.stats_message)

    try:
        result = sync_service.sync_garmin_data(state, days=days, on_progress=render_progress)
        state.last_sync_status = sync_service.build_sync_status_payload(result, days=days)
        state.selected_page = "📊 Дашборд"
        status_text.empty()
        sync_stats.empty()

        import time
        time.sleep(1)
        progress_container.empty()
        state.syncing_in_progress = False
        st.rerun()

    except Exception as e:
        progress_container.empty()
        state.syncing_in_progress = False
        st.error(f"❌ Ошибка синхронизации: {e}")

def clear_database():
    """Очистка базы данных с подтверждением"""
    state = get_state_manager()
    database = state.database

    if st.button("🗑️ Очистить базу данных", type="secondary", key="clear_db_btn"):
        if not state.confirm_clear:
            state.confirm_clear = True
            st.rerun()

    if state.confirm_clear:
        st.warning("⚠️ Это действие удалит ВСЕ данные из базы. Подтвердите удаление.")

        col1, col2 = st.columns(2)
        with col1:
            if st.button("✅ Да, удалить все данные", type="primary", key="confirm_clear_btn"):
                try:
                    database.clear_all_data()
                    st.success("✅ База данных очищена")
                except Exception as exc:
                    st.error(f"❌ Ошибка очистки БД: {exc}")
                finally:
                    state.confirm_clear = False
                    st.rerun()

        with col2:
            if st.button("❌ Отмена", type="secondary", key="cancel_clear_btn"):
                state.confirm_clear = False
                st.rerun()

if __name__ == "__main__":
    main()
