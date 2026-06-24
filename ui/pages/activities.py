"""Activities page renderer."""
from __future__ import annotations

from datetime import datetime

import pandas as pd
import plotly.express as px
import streamlit as st

from services.data_cache import load_activities
from state import StateManager
from ui.plotly_theme import create_dark_table_html, get_plotly_theme


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
    st.header("🏃‍♂️ Ваши активности")

    activities_df = load_activities(30)
    if activities_df.empty:
        st.warning("📭 Нет активностей за последние 30 дней. Синхронизируйте данные с Garmin Connect.")
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
    st.subheader("📊 Статистика")

    col1, col2 = st.columns(2)
    col3, col4 = st.columns(2)

    with col1:
        st.metric("Всего тренировок", len(filtered_df))

    with col2:
        st.metric("Общая дистанция", f"{filtered_df['distance_km'].sum():.1f} км")

    with col3:
        st.metric("Общее время", f"{filtered_df['duration_minutes'].sum() / 60:.1f} ч")

    with col4:
        avg_tss = filtered_df["tss"].mean() if "tss" in filtered_df.columns else 0
        st.metric("Средний TSS", f"{avg_tss:.0f}")


def _render_daily_chart(filtered_df: pd.DataFrame, state: StateManager) -> None:
    if filtered_df.empty:
        return

    st.subheader("📈 Активность по дням")

    filtered_df["date"] = pd.to_datetime(filtered_df["date"])
    daily_stats = filtered_df.groupby("date").agg(
        {
            "tss": "sum",
            "duration_minutes": "sum",
            "distance_km": "sum",
        }
    ).reset_index()

    if state.use_custom_theme:
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
    else:
        fig_tss = px.bar(
            daily_stats,
            x="date",
            y="tss",
            title="Training Stress Score по дням",
            labels={"tss": "TSS", "date": "Дата"},
        )
        fig_tss.update_layout(height=400)

    st.plotly_chart(fig_tss, width="stretch")


def _render_activity_table(filtered_df: pd.DataFrame, state: StateManager) -> pd.DataFrame:
    st.subheader("📋 Список тренировок")

    display_df = filtered_df.copy()
    display_df["date"] = pd.to_datetime(display_df["date"]).dt.strftime("%d.%m.%Y")
    display_df["duration_minutes"] = display_df["duration_minutes"].round(0).astype(int)
    display_df["distance_km"] = display_df["distance_km"].round(2)

    columns_to_show = [column for column in _DISPLAY_COLUMNS if column in display_df.columns]
    table_df = display_df[columns_to_show].rename(columns=_DISPLAY_COLUMNS)

    if state.use_custom_theme and state.dark_mode:
        st.markdown(create_dark_table_html(table_df), unsafe_allow_html=True)
    else:
        st.dataframe(table_df, width="stretch", hide_index=True)

    return table_df


def _render_activity_details(filtered_df: pd.DataFrame) -> None:
    if filtered_df.empty:
        return

    st.subheader("🔍 Детали тренировки")

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
        st.write("**Основные показатели:**")
        st.write(f"📅 Дата: {activity['date']}")
        st.write(f"🏃 Вид спорта: {activity['sport']}")
        st.write(f"⏱️ Время: {activity['duration_minutes']:.0f} мин")
        st.write(f"📏 Дистанция: {activity['distance_km']:.2f} км")

    with col2:
        st.write("**Показатели интенсивности:**")
        if "avg_hr" in activity and pd.notna(activity["avg_hr"]):
            st.write(f"💓 Средний пульс: {activity['avg_hr']:.0f} уд/мин")
        if "avg_power" in activity and pd.notna(activity["avg_power"]):
            st.write(f"⚡ Средняя мощность: {activity['avg_power']:.0f} W")
        if "tss" in activity and pd.notna(activity["tss"]):
            st.write(f"📊 TSS: {activity['tss']:.0f}")
        if "calories" in activity and pd.notna(activity["calories"]):
            st.write(f"🔥 Калории: {activity['calories']:.0f}")


def _render_export_actions(table_df: pd.DataFrame, filtered_df: pd.DataFrame) -> None:
    if filtered_df.empty:
        return

    st.subheader("📤 Экспорт данных")

    col1, col2 = st.columns(2)

    with col1:
        if st.button("📊 Скачать CSV"):
            csv = table_df.to_csv(index=False)
            st.download_button(
                label="💾 Загрузить CSV файл",
                data=csv,
                file_name=f"activities_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv",
            )

    with col2:
        if st.button("📈 Создать отчет"):
            st.info("📋 Функция создания отчетов будет добавлена в следующих версиях.")


__all__ = ["render_activities_page"]
