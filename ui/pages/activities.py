"""Activities page renderer."""
from __future__ import annotations

from datetime import datetime

import pandas as pd
import plotly.express as px
import streamlit as st

from services.data_cache import load_activities
from state import StateManager
from ui.plotly_theme import get_plotly_theme


_SORT_LABELS = {
    "date": "Дате",
    "distance_km": "Дистанции",
    "duration_minutes": "Времени",
    "tss": "TSS",
}

_DISPLAY_COLUMNS = {
    "date": "Дата",
    "sport": "Спорт",
    "duration_minutes": "Время (мин)",
    "distance_km": "Дистанция (км)",
    "avg_hr": "Ср. ЧСС",
    "avg_power": "Ср. мощность",
    "tss": "TSS",
}


def render_activities_page(state: StateManager) -> None:
    """Render the activities page."""
    from utils.modern_ui import ModernUI

    ModernUI.apply_modern_styles(dark_mode=state.dark_mode)
    ModernUI.render_page_hero(
        "Активности",
        subtitle="Ваши тренировки за последние 30 дней",
        eyebrow="Activities cockpit",
    )

    activities_df = load_activities(30)
    if activities_df.empty:
        ModernUI.render_text_card(
            "Нет активностей",
            "За последние 30 дней активности не найдены. Синхронизируйте данные с Garmin Connect.",
            tone="warning",
        )
        return

    selected_sports, date_range, sort_by = _render_filters(activities_df)
    filtered_df = (
        activities_df[activities_df["sport"].isin(selected_sports)]
        .tail(date_range * 3)
        .sort_values(sort_by, ascending=False)
        .copy()
    )

    _render_summary_metrics(filtered_df)
    _render_daily_chart(filtered_df, state)

    table_df = _render_activity_table(filtered_df, state)
    _render_activity_details(filtered_df)
    _render_export_actions(table_df, filtered_df)


def _render_filters(activities_df: pd.DataFrame) -> tuple[list[str], int, str]:
    col1, col2, col3 = st.columns(3)

    with col1:
        selected_sports = st.multiselect(
            "Виды спорта:",
            options=activities_df["sport"].unique(),
            default=activities_df["sport"].unique(),
        )

    with col2:
        date_range = st.slider(
            "Период (дней):",
            min_value=7,
            max_value=90,
            value=30,
        )

    with col3:
        sort_by = st.selectbox(
            "Сортировать по:",
            options=list(_SORT_LABELS.keys()),
            format_func=_SORT_LABELS.get,
        )

    return list(selected_sports), date_range, sort_by


def _render_summary_metrics(filtered_df: pd.DataFrame) -> None:
    from utils.modern_ui import ModernUI

    ModernUI.render_section_title("Статистика", caption="Сводка по выбранным тренировкам")

    col1, col2 = st.columns(2)
    col3, col4 = st.columns(2)

    with col1:
        ModernUI.render_stat_card("Всего тренировок", len(filtered_df), tone="info")
    with col2:
        ModernUI.render_stat_card("Общая дистанция", f"{filtered_df['distance_km'].sum():.1f} км", tone="success")
    with col3:
        ModernUI.render_stat_card("Общее время", f"{filtered_df['duration_minutes'].sum() / 60:.1f} ч", tone="neutral")
    with col4:
        avg_tss = filtered_df["tss"].mean() if "tss" in filtered_df.columns else 0
        ModernUI.render_stat_card("Средний TSS", f"{avg_tss:.0f}", tone="info")


def _render_daily_chart(filtered_df: pd.DataFrame, state: StateManager) -> None:
    from utils.modern_ui import ModernUI

    if filtered_df.empty:
        return

    ModernUI.render_section_title("Активность по дням", caption="Training Stress Score")

    filtered_df["date"] = pd.to_datetime(filtered_df["date"])
    daily_stats = filtered_df.groupby("date").agg(
        {
            "tss": "sum",
            "duration_minutes": "sum",
            "distance_km": "sum",
        }
    ).reset_index()

    # Single cockpit-themed path (use_custom_theme branching removed — cockpit
    # is now the only theme engine, and get_plotly_theme already aligns to --ic-*).
    theme = get_plotly_theme(state.dark_mode)
    fig_tss = px.bar(
        daily_stats,
        x="date",
        y="tss",
        title="Training Stress Score по дням",
        labels={"tss": "TSS", "date": "Дата"},
        template=theme["template"],
    )
    fig_tss.update_layout(
        height=400,
        paper_bgcolor=theme["paper_bgcolor"],
        plot_bgcolor=theme["plot_bgcolor"],
        font_color=theme["font_color"],
    )

    st.plotly_chart(fig_tss, width="stretch")


def _render_activity_table(filtered_df: pd.DataFrame, state: StateManager) -> pd.DataFrame:
    from utils.modern_ui import ModernUI

    ModernUI.render_section_title("Список тренировок", caption="Выбранные активности")

    display_df = filtered_df.copy()
    display_df["date"] = pd.to_datetime(display_df["date"]).dt.strftime("%d.%m.%Y")
    display_df["duration_minutes"] = display_df["duration_minutes"].round(0).astype(int)
    display_df["distance_km"] = display_df["distance_km"].round(2)

    columns_to_show = [column for column in _DISPLAY_COLUMNS if column in display_df.columns]
    table_df = display_df[columns_to_show].rename(columns=_DISPLAY_COLUMNS)

    # Single unified path: st.dataframe is globally restyled to the cockpit
    # surface by apply_modern_styles, so the dark-only create_dark_table_html
    # branch is no longer needed.
    st.dataframe(table_df, width="stretch", hide_index=True)

    return table_df


def _render_activity_details(filtered_df: pd.DataFrame) -> None:
    from utils.modern_ui import ModernUI

    if filtered_df.empty:
        return

    ModernUI.render_section_title("Детали тренировки", caption="Разбор выбранной активности")

    selected_activity = st.selectbox(
        "Выберите тренировку:",
        options=range(len(filtered_df)),
        format_func=lambda index: (
            f"{filtered_df.iloc[index]['date']} - "
            f"{filtered_df.iloc[index]['sport']} "
            f"({filtered_df.iloc[index]['distance_km']:.1f} км)"
        ),
    )

    activity = filtered_df.iloc[selected_activity]

    col1, col2 = st.columns(2)

    with col1:
        body_main = (
            f"📅 Дата: {activity['date']}\n"
            f"🏃 Вид спорта: {activity['sport']}\n"
            f"⏱️ Время: {activity['duration_minutes']:.0f} мин\n"
            f"📏 Дистанция: {activity['distance_km']:.2f} км"
        )
        ModernUI.render_text_card("Основные показатели", body_main, tone="neutral")

    with col2:
        intensity_lines = []
        if "avg_hr" in activity and pd.notna(activity["avg_hr"]):
            intensity_lines.append(f"💓 Средний пульс: {activity['avg_hr']:.0f} уд/мин")
        if "avg_power" in activity and pd.notna(activity["avg_power"]):
            intensity_lines.append(f"⚡ Средняя мощность: {activity['avg_power']:.0f} W")
        if "tss" in activity and pd.notna(activity["tss"]):
            intensity_lines.append(f"📊 TSS: {activity['tss']:.0f}")
        if "calories" in activity and pd.notna(activity["calories"]):
            intensity_lines.append(f"🔥 Калории: {activity['calories']:.0f}")
        ModernUI.render_text_card(
            "Показатели интенсивности",
            "\n".join(intensity_lines) if intensity_lines else "нет данных",
            tone="info",
        )


def _render_export_actions(table_df: pd.DataFrame, filtered_df: pd.DataFrame) -> None:
    from utils.modern_ui import ModernUI

    if filtered_df.empty:
        return

    ModernUI.render_section_title("Экспорт данных", caption="Выгрузка выбранных активностей")

    col1, col2 = st.columns(2)

    with col1:
        if st.button("📊 Скачать CSV", type="primary", width="stretch"):
            csv = table_df.to_csv(index=False)
            st.download_button(
                label="💾 Загрузить CSV файл",
                data=csv,
                file_name=f"activities_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv",
            )

    with col2:
        if st.button("📈 Создать отчет", width="stretch"):
            ModernUI.render_text_card(
                "В разработке",
                "Функция создания отчетов будет добавлена в следующих версиях.",
                tone="info",
            )


__all__ = ["render_activities_page"]
