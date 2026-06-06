"""Administrative and diagnostics pages for the Streamlit UI."""
from __future__ import annotations

import glob
import os
from typing import TYPE_CHECKING, Callable

import streamlit as st

if TYPE_CHECKING:
    from state import StateManager


def render_sync_logs_page(log_dir: str = "logs") -> None:
    """Показывает логи синхронизации для отладки."""
    st.title("📋 Логи синхронизации")
    st.write("Детальные логи процесса синхронизации с Garmin Connect")

    if not os.path.exists(log_dir):
        st.warning("📁 Папка с логами не найдена. Логи будут создаваться при следующей синхронизации.")
        return

    log_files = glob.glob(os.path.join(log_dir, "garmin_sync_*.log"))
    log_files.sort(reverse=True)

    if not log_files:
        st.info("📝 Файлы логов пока не созданы. Выполните синхронизацию для создания логов.")
        return

    col1, col2 = st.columns([2, 1])

    with col1:
        selected_file = st.selectbox(
            "Выберите файл лога:",
            log_files,
            format_func=os.path.basename,
        )

    with col2:
        if st.button("🔄 Обновить"):
            st.rerun()

    if not selected_file:
        return

    try:
        st.subheader("🔍 Фильтры")
        col1, col2, col3 = st.columns(3)

        with col1:
            level_filter = st.multiselect(
                "Уровень логов:",
                ["INFO", "DEBUG", "WARNING", "ERROR"],
                default=["INFO", "WARNING", "ERROR"],
            )

        with col2:
            search_term = st.text_input("Поиск по тексту:")

        with col3:
            max_lines = st.number_input("Максимум строк:", min_value=10, max_value=1000, value=100)

        with open(selected_file, "r", encoding="utf-8") as file_handle:
            lines = file_handle.readlines()

        filtered_lines = []
        for line in lines:
            if level_filter and not any(level in line for level in level_filter):
                continue
            if search_term and search_term.lower() not in line.lower():
                continue
            filtered_lines.append(line)

        display_lines = filtered_lines[-max_lines:] if len(filtered_lines) > max_lines else filtered_lines

        st.subheader(f"📄 Логи ({len(display_lines)} из {len(lines)} строк)")

        if st.checkbox("Группировать по типам"):
            errors = [line for line in display_lines if "ERROR" in line]
            warnings = [line for line in display_lines if "WARNING" in line]
            infos = [line for line in display_lines if "INFO" in line and "ERROR" not in line and "WARNING" not in line]
            debugs = [line for line in display_lines if "DEBUG" in line]

            if errors:
                st.error(f"❌ Ошибки ({len(errors)}):")
                st.code("\n".join(errors), language=None)

            if warnings:
                st.warning(f"⚠️ Предупреждения ({len(warnings)}):")
                st.code("\n".join(warnings), language=None)

            if infos:
                st.info(f"ℹ️ Информация ({len(infos)}):")
                st.code("\n".join(infos), language=None)

            if debugs and "DEBUG" in level_filter:
                with st.expander(f"🔍 Отладка ({len(debugs)})"):
                    st.code("\n".join(debugs), language=None)
        else:
            st.code("".join(display_lines), language=None)

        st.subheader("📊 Статистика логов")
        col1, col2 = st.columns(2)
        col3, col4 = st.columns(2)

        total_lines = len(lines)
        errors_count = len([line for line in lines if "ERROR" in line])
        warnings_count = len([line for line in lines if "WARNING" in line])
        success_count = len([line for line in lines if "✅" in line])

        col1.metric("Всего строк", total_lines)
        col2.metric("Ошибок", errors_count)
        col3.metric("Предупреждений", warnings_count)
        col4.metric("Успешных операций", success_count)

    except Exception as exc:
        st.error(f"Ошибка чтения файла лога: {exc}")


def render_data_management_page(
    state: "StateManager",
    on_sync: Callable[[int], None],
    on_clear_database: Callable[[], None],
) -> None:
    """Показывает страницу управления данными."""
    database = state.database
    st.title("⚙️ Управление данными")
    st.write("Управление синхронизацией и данными в базе")

    st.subheader("🔄 Синхронизация данных")
    col1, col2 = st.columns([2, 1])

    with col1:
        sync_days = st.selectbox(
            "Период загрузки:",
            options=[7, 14, 30, 60, 90],
            index=2,
            format_func=lambda value: f"{value} дней",
            help="Количество дней для синхронизации с Garmin Connect",
        )

    with col2:
        if st.button("🔄 Синхронизировать данные", use_container_width=True):
            on_sync(sync_days)

    st.divider()
    st.subheader("📊 Данные в БД")

    if hasattr(state, "database"):
        stats = database.get_database_stats()

        col1, col2, col3 = st.columns(3)
        col4, col5 = st.columns(2)

        with col1:
            st.metric("🏃‍♂️ Активности", stats["activities"])

        with col2:
            st.metric("💓 HRV записи", stats["hrv_data"])

        with col3:
            st.metric("😴 Данные сна", stats.get("sleep_data", 0))

        with col4:
            st.metric("🏥 Показатели здоровья", stats.get("daily_health", 0))

        with col5:
            st.metric("📈 Статус тренированности", stats.get("training_status", 0))

        if stats["activities"] > 0:
            try:
                activities_df = database.get_activities(1)
                if not activities_df.empty:
                    st.info(f"📅 Последняя активность: {activities_df.iloc[0]['date']}")
            except Exception:
                pass

    st.divider()
    on_clear_database()
