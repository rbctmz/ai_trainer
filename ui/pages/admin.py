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
    from utils.modern_ui import ModernUI

    ModernUI.render_page_hero(
        "Логи синхронизации",
        subtitle="Детальные логи процесса синхронизации с Garmin Connect",
        eyebrow="Diagnostics",
    )

    if not os.path.exists(log_dir):
        ModernUI.render_text_card(
            "Папка с логами не найдена",
            "Логи будут создаваться при следующей синхронизации.",
            tone="warning",
        )
        return

    log_files = glob.glob(os.path.join(log_dir, "garmin_sync_*.log"))
    log_files.sort(reverse=True)

    if not log_files:
        ModernUI.render_text_card(
            "Файлы логов пока не созданы",
            "Выполните синхронизацию для создания логов.",
            tone="info",
        )
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
        ModernUI.render_section_title("Фильтры", caption="Отбор строк лога")
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

        ModernUI.render_section_title(f"Логи ({len(display_lines)} из {len(lines)} строк)")

        if st.checkbox("Группировать по типам"):
            errors = [line for line in display_lines if "ERROR" in line]
            warnings = [line for line in display_lines if "WARNING" in line]
            infos = [line for line in display_lines if "INFO" in line and "ERROR" not in line and "WARNING" not in line]
            debugs = [line for line in display_lines if "DEBUG" in line]

            if errors:
                ModernUI.render_text_card(f"❌ Ошибки ({len(errors)})", "\n".join(errors), tone="danger")
            if warnings:
                ModernUI.render_text_card(f"⚠️ Предупреждения ({len(warnings)})", "\n".join(warnings), tone="warning")
            if infos:
                ModernUI.render_text_card(f"ℹ️ Информация ({len(infos)})", "\n".join(infos), tone="info")
            if debugs and "DEBUG" in level_filter:
                with st.expander(f"🔍 Отладка ({len(debugs)})"):
                    st.code("\n".join(debugs), language=None)
        else:
            st.code("".join(display_lines), language=None)

        ModernUI.render_section_title("Статистика логов")
        col1, col2 = st.columns(2)
        col3, col4 = st.columns(2)

        total_lines = len(lines)
        errors_count = len([line for line in lines if "ERROR" in line])
        warnings_count = len([line for line in lines if "WARNING" in line])
        success_count = len([line for line in lines if "✅" in line])

        with col1:
            ModernUI.render_stat_card("Всего строк", total_lines, tone="neutral")
        with col2:
            ModernUI.render_stat_card("Ошибок", errors_count, tone="danger" if errors_count else "neutral")
        with col3:
            ModernUI.render_stat_card("Предупреждений", warnings_count, tone="warning" if warnings_count else "neutral")
        with col4:
            ModernUI.render_stat_card("Успешных операций", success_count, tone="success")

    except Exception as exc:
        ModernUI.render_text_card("Ошибка чтения файла лога", str(exc), tone="danger")


def render_data_management_page(
    state: "StateManager",
    on_sync: Callable[[int], None],
    on_clear_database: Callable[[], None],
) -> None:
    """Показывает страницу управления данными."""
    from utils.modern_ui import ModernUI

    database = state.database
    ModernUI.render_page_hero(
        "Управление данными",
        subtitle="Синхронизация с Garmin Connect и данные в базе",
        eyebrow="Data cockpit",
    )

    ModernUI.render_section_title("Синхронизация данных", caption="Загрузка из Garmin Connect")
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
        if st.button("🔄 Синхронизировать данные", type="primary", width="stretch"):
            on_sync(sync_days)

    ModernUI.render_section_title("Данные в БД", caption="Содержимое локального кэша")

    if hasattr(state, "database"):
        stats = database.get_database_stats()

        col1, col2, col3 = st.columns(3)
        col4, col5 = st.columns(2)

        with col1:
            ModernUI.render_stat_card("🏃‍♂️ Активности", stats["activities"], tone="success" if stats["activities"] else "empty")
        with col2:
            ModernUI.render_stat_card("💓 HRV записи", stats["hrv_data"], tone="info" if stats["hrv_data"] else "empty")
        with col3:
            ModernUI.render_stat_card("😴 Данные сна", stats.get("sleep_data", 0), tone="info" if stats.get("sleep_data", 0) else "empty")
        with col4:
            ModernUI.render_stat_card("🏥 Здоровье", stats.get("daily_health", 0), tone="neutral")
        with col5:
            ModernUI.render_stat_card("📈 Training status", stats.get("training_status", 0), tone="neutral")

        if stats["activities"] > 0:
            try:
                activities_df = database.get_activities(1)
                if not activities_df.empty:
                    ModernUI.render_text_card(
                        "Последняя активность",
                        f"📅 {activities_df.iloc[0]['date']}",
                        tone="info",
                    )
            except Exception:
                pass

    st.divider()
    on_clear_database()
