"""Sleep analysis page renderer."""
from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from services.data_cache import load_sleep
from state import StateManager
from utils.sleep_metrics import compute_sleep_regularity


def render_sleep_page(state: StateManager) -> None:
    """Render the sleep analysis page."""
    from utils.modern_ui import ModernUI

    if state.use_custom_theme:
        ModernUI.apply_modern_styles(dark_mode=state.dark_mode)

    st.header("😴 Анализ качества сна")

    sleep_df = load_sleep(90)

    if sleep_df.empty:
        st.warning("📊 Данные сна отсутствуют. Выполните синхронизацию с Garmin Connect.")
        if st.button("🔄 Синхронизировать данные"):
            st.rerun()
        return

    period_options = {
        "7 дней": 7,
        "14 дней": 14,
        "30 дней": 30,
        "60 дней": 60,
        "90 дней": 90,
    }

    period_label = st.selectbox(
        "📅 Период анализа:",
        options=list(period_options.keys()),
        index=2,
        key="sleep_period_selector",
    )
    period_days = period_options[period_label]

    cutoff_date = datetime.now() - timedelta(days=period_days)
    filtered_df = sleep_df[sleep_df["date"] >= cutoff_date].copy()

    if filtered_df.empty:
        st.warning(f"📊 Нет данных сна за последние {period_days} дней.")
        return

    latest_sleep = None
    if not filtered_df.empty:
        sorted_df = filtered_df.sort_values("date", ascending=False)
        latest_sleep = sorted_df.iloc[0]

    if latest_sleep is not None:
        st.subheader(f"🌙 Последний сон ({_format_date(latest_sleep['date'], 'display')})")

        col1, col2, col3, col4 = st.columns(4)

        with col1:
            total_minutes = latest_sleep.get("total_sleep_minutes", 0)
            hours = total_minutes // 60
            minutes = total_minutes % 60

            duration_hours = total_minutes / 60
            duration_status = "success" if 7 <= duration_hours <= 9 else "warning" if 6 <= duration_hours <= 10 else "danger"
            duration_description = (
                "Оптимально"
                if 7 <= duration_hours <= 9
                else "Приемлемо"
                if 6 <= duration_hours <= 10
                else "Недостаточно"
                if duration_hours < 7
                else "Слишком много"
            )

            ModernUI.status_card(
                "⏰ Продолжительность",
                f"{hours}ч {minutes}м",
                duration_status,
                description=duration_description,
            )

        with col2:
            sleep_score = latest_sleep.get("sleep_score", 0)
            sleep_status = "success" if sleep_score >= 80 else "warning" if sleep_score >= 60 else "danger"

            ModernUI.status_card(
                "💤 Sleep Score",
                f"{sleep_score:.1f}",
                sleep_status,
                description="Качество сна",
            )

        with col3:
            efficiency = latest_sleep.get("sleep_efficiency", 0)
            efficiency_status = "success" if efficiency >= 85 else "warning" if efficiency >= 75 else "danger"

            ModernUI.status_card(
                "⚡ Эффективность",
                f"{efficiency:.1f}%",
                efficiency_status,
                description="Время сна от времени в постели",
            )

        with col4:
            awakenings = latest_sleep.get("awakenings_count", 0)
            awakenings_status = "success" if awakenings <= 2 else "warning" if awakenings <= 4 else "danger"

            ModernUI.status_card(
                "🌅 Пробуждения",
                f"{awakenings:.0f}",
                awakenings_status,
                description="Количество пробуждений",
            )

        regularity_metrics = compute_sleep_regularity(filtered_df) or {}
        bedtime_metric = regularity_metrics.get("bedtime")
        wake_metric = regularity_metrics.get("wakeup")
        if (
            regularity_metrics.get("count", 0) >= 3
            and bedtime_metric
            and wake_metric
            and bedtime_metric.get("status") != "secondary"
            and wake_metric.get("status") != "secondary"
        ):
            st.subheader("⏱ Регулярность режима")
            reg_col1, reg_col2 = st.columns(2)

            with reg_col1:
                ModernUI.status_card(
                    "🛏️ Время отбоя",
                    f"σ {bedtime_metric['std_text']}",
                    bedtime_metric["status"],
                    description=f"Среднее: {bedtime_metric['mean_text']} • Δ±{bedtime_metric['mad_text']} ({bedtime_metric['label']})",
                )
                st.caption(bedtime_metric["recommendation"])

            with reg_col2:
                ModernUI.status_card(
                    "🌅 Пробуждение",
                    f"σ {wake_metric['std_text']}",
                    wake_metric["status"],
                    description=f"Среднее: {wake_metric['mean_text']} • Δ±{wake_metric['mad_text']} ({wake_metric['label']})",
                )
                st.caption(wake_metric["recommendation"])
        elif regularity_metrics.get("count", 0) > 0:
            st.caption("Недостаточно данных, чтобы сформировать метрику регулярности сна — нужно минимум 3 записи с временем отбоя и подъёма.")

        weekday_profile_df = regularity_metrics.get("weekday_profile")
        if weekday_profile_df is not None and not weekday_profile_df.empty:
            st.subheader("📊 Засыпание и пробуждение по дням недели")

            plot_df = weekday_profile_df.copy()
            bedtime_hours = plot_df["bedtime_hours"]
            wake_hours = plot_df["wakeup_hours"]
            duration_hours = plot_df["sleep_duration_hours"]
            all_hours = pd.concat([bedtime_hours, wake_hours])

            if not all_hours.empty:
                lower = float(all_hours.min()) - 0.5
                upper = float(all_hours.max()) + 0.5
            else:
                lower, upper = 18.0, 34.0

            lower = max(min(lower, 18.0), 0.0)
            upper = min(max(upper, 32.0), 36.0)
            if upper - lower < 4:
                upper = lower + 4

            tick_vals = list(range(int(lower), int(upper) + 1))
            tick_text = [f"{(hour % 24):02d}:00" for hour in tick_vals]

            fig_weekday = go.Figure()
            fig_weekday.add_trace(
                go.Bar(
                    x=plot_df["weekday_label"],
                    y=duration_hours,
                    base=bedtime_hours,
                    width=0.55,
                    marker=dict(
                        color="rgba(148,163,184,0.75)",
                        line=dict(color="rgba(148,163,184,0.95)", width=1.4),
                        pattern=dict(shape="", solidity=0.7),
                    ),
                    hovertemplate=(
                        "Отбой: %{customdata[0]}<br>"
                        "Подъём: %{customdata[1]}<br>"
                        "Средняя длительность: %{customdata[2]}<br>"
                        "Замеров: %{customdata[3]}<extra></extra>"
                    ),
                    customdata=plot_df[
                        [
                            "bedtime_text",
                            "wakeup_text",
                            "sleep_duration_text",
                            "count",
                        ]
                    ],
                    name="Сон",
                )
            )

            earliest_bed = float(bedtime_hours.min()) if not bedtime_hours.empty else lower
            latest_wake = float(wake_hours.max()) if not wake_hours.empty else upper

            fig_weekday.update_layout(
                xaxis_title="День недели",
                legend_title="",
                hovermode="x",
                bargap=0.4,
                bargroupgap=0.2,
                shapes=[
                    dict(
                        type="line",
                        xref="paper",
                        x0=0,
                        x1=1,
                        y0=earliest_bed,
                        y1=earliest_bed,
                        line=dict(color="rgba(148,163,184,0.6)", dash="dash"),
                    ),
                    dict(
                        type="line",
                        xref="paper",
                        x0=0,
                        x1=1,
                        y0=latest_wake,
                        y1=latest_wake,
                        line=dict(color="rgba(148,163,184,0.6)", dash="dash"),
                    ),
                ],
            )
            fig_weekday.update_yaxes(
                title_text="Время суток",
                range=[lower, upper],
                tickmode="array",
                tickvals=tick_vals,
                ticktext=tick_text,
            )

            st.plotly_chart(fig_weekday, use_container_width=True)
            st.caption("Столбики показывают средний интервал сна по дням. Чем ровнее высота, тем стабильнее режим.")

        st.subheader("🌀 Фазы сна")
        col1, col2, col3 = st.columns(3)

        with col1:
            deep_min = latest_sleep.get("deep_sleep_minutes", 0)
            deep_pct = (deep_min / total_minutes * 100) if total_minutes > 0 else 0
            deep_status = "success" if 15 <= deep_pct <= 25 else "warning" if 10 <= deep_pct <= 30 else "danger"

            ModernUI.status_card(
                "🛌 Глубокий сон",
                f"{deep_min}мин",
                deep_status,
                description=f"{deep_pct:.1f}% от сна",
            )

        with col2:
            light_min = latest_sleep.get("light_sleep_minutes", 0)
            light_pct = (light_min / total_minutes * 100) if total_minutes > 0 else 0
            light_status = "success" if 45 <= light_pct <= 65 else "warning" if 35 <= light_pct <= 75 else "danger"

            ModernUI.status_card(
                "💤 Легкий сон",
                f"{light_min}мин",
                light_status,
                description=f"{light_pct:.1f}% от сна",
            )

        with col3:
            rem_min = latest_sleep.get("rem_sleep_minutes", 0)
            rem_pct = (rem_min / total_minutes * 100) if total_minutes > 0 else 0
            rem_status = "success" if 20 <= rem_pct <= 30 else "warning" if 15 <= rem_pct <= 35 else "danger"

            ModernUI.status_card(
                "🧠 REM сон",
                f"{rem_min}мин",
                rem_status,
                description=f"{rem_pct:.1f}% от сна",
            )

        if latest_sleep.get("bedtime") and latest_sleep.get("wakeup_time"):
            col1, col2 = st.columns(2)
            with col1:
                st.metric("🌙 Время засыпания", latest_sleep["bedtime"])
            with col2:
                st.metric("🌅 Время пробуждения", latest_sleep["wakeup_time"])
            try:
                tz_name = datetime.now().astimezone().tzname()
                st.caption(f"Время отображается в локальной зоне: {tz_name}")
            except Exception:
                st.caption("Время отображается в локальной часовой зоне устройства/сервера")

    st.subheader("📈 Тренды сна")

    if len(filtered_df) > 1:
        fig = make_subplots(
            rows=2,
            cols=2,
            subplot_titles=[
                "💤 Качество сна",
                "⏰ Продолжительность сна",
                "⚡ Эффективность сна",
                "🌅 Пробуждения",
            ],
            vertical_spacing=0.15,
            horizontal_spacing=0.1,
        )

        dates = filtered_df["date"]

        fig.add_trace(
            go.Scatter(
                x=dates,
                y=filtered_df["sleep_score"],
                mode="lines+markers",
                name="Качество сна",
                line=dict(color="#3B82F6", width=3),
                marker=dict(size=8, color="#3B82F6", line=dict(width=2, color="white")),
                fill="tonexty",
                fillcolor="rgba(59, 130, 246, 0.2)",
                hovertemplate="<b>Sleep Score</b><br>%{y:.1f}<br>%{x}<extra></extra>",
            ),
            row=1,
            col=1,
        )

        sleep_hours = filtered_df["total_sleep_minutes"] / 60
        fig.add_trace(
            go.Scatter(
                x=dates,
                y=sleep_hours,
                mode="lines+markers",
                name="Часы сна",
                line=dict(color="#10B981", width=3),
                marker=dict(size=8, color="#10B981", line=dict(width=2, color="white")),
                fill="tonexty",
                fillcolor="rgba(16, 185, 129, 0.2)",
                hovertemplate="<b>Продолжительность</b><br>%{y:.1f}ч<br>%{x}<extra></extra>",
            ),
            row=1,
            col=2,
        )

        fig.add_trace(
            go.Scatter(
                x=dates,
                y=filtered_df["sleep_efficiency"],
                mode="lines+markers",
                name="Эффективность %",
                line=dict(color="#8B5CF6", width=3),
                marker=dict(size=8, color="#8B5CF6", line=dict(width=2, color="white")),
                fill="tonexty",
                fillcolor="rgba(139, 92, 246, 0.2)",
                hovertemplate="<b>Эффективность</b><br>%{y:.1f}%<br>%{x}<extra></extra>",
            ),
            row=2,
            col=1,
        )

        fig.add_trace(
            go.Scatter(
                x=dates,
                y=filtered_df["awakenings_count"],
                mode="lines+markers",
                name="Пробуждения",
                line=dict(color="#EF4444", width=3),
                marker=dict(size=8, color="#EF4444", line=dict(width=2, color="white")),
                fill="tonexty",
                fillcolor="rgba(239, 68, 68, 0.2)",
                hovertemplate="<b>Пробуждения</b><br>%{y:.0f}<br>%{x}<extra></extra>",
            ),
            row=2,
            col=2,
        )

        fig.update_layout(
            height=550,
            showlegend=False,
            title={
                "text": f"📈 Тренды сна за {period_label}",
                "x": 0.5,
                "xanchor": "center",
                "font": {"size": 18, "color": "#1F2937"},
            },
            font=dict(family="Inter, -apple-system, sans-serif", size=12),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            hovermode="x unified",
        )

        avg_score = filtered_df["sleep_score"].mean()
        avg_hours = filtered_df["total_sleep_minutes"].mean() / 60
        avg_efficiency = filtered_df["sleep_efficiency"].mean()
        avg_awakenings = filtered_df["awakenings_count"].mean()

        fig.add_hrect(y0=7, y1=9, fillcolor="rgba(16, 185, 129, 0.1)", line_width=0, row=1, col=2)
        fig.add_hline(
            y=8,
            line_dash="dot",
            line_color="#10B981",
            line_width=2,
            annotation_text="Оптимально",
            annotation_position="right",
            row=1,
            col=2,
        )
        fig.add_hline(
            y=85,
            line_dash="dot",
            line_color="#8B5CF6",
            line_width=2,
            annotation_text="Хорошо",
            annotation_position="right",
            row=2,
            col=1,
        )
        fig.add_hline(
            y=80,
            line_dash="dot",
            line_color="#10B981",
            line_width=1,
            annotation_text="Отлично",
            annotation_position="right",
            row=1,
            col=1,
        )
        fig.add_hline(
            y=60,
            line_dash="dot",
            line_color="#F59E0B",
            line_width=1,
            annotation_text="Удовлетворительно",
            annotation_position="right",
            row=1,
            col=1,
        )
        fig.add_hline(
            y=avg_score,
            line_dash="dash",
            line_color="#6B7280",
            line_width=2,
            annotation_text=f"Среднее: {avg_score:.1f}",
            annotation_position="left",
            row=1,
            col=1,
        )
        fig.add_hline(
            y=avg_hours,
            line_dash="dash",
            line_color="#6B7280",
            line_width=2,
            annotation_text=f"Среднее: {avg_hours:.1f}ч",
            annotation_position="left",
            row=1,
            col=2,
        )
        fig.add_hline(
            y=avg_efficiency,
            line_dash="dash",
            line_color="#6B7280",
            line_width=2,
            annotation_text=f"Среднее: {avg_efficiency:.1f}%",
            annotation_position="left",
            row=2,
            col=1,
        )
        fig.add_hline(
            y=avg_awakenings,
            line_dash="dash",
            line_color="#6B7280",
            line_width=2,
            annotation_text=f"Среднее: {avg_awakenings:.1f}",
            annotation_position="left",
            row=2,
            col=2,
        )

        fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor="rgba(156, 163, 175, 0.2)")
        fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor="rgba(156, 163, 175, 0.2)")

        st.plotly_chart(fig, use_container_width=True)

        st.subheader("📊 Статистика за период")

        col1, col2, col3, col4 = st.columns(4)

        with col1:
            avg_quality = filtered_df["sleep_score"].mean()
            if pd.isna(avg_quality):
                avg_quality = 0

            quality_status = "success" if avg_quality >= 80 else "warning" if avg_quality >= 60 else "danger"
            quality_trend = (
                "📈"
                if len(filtered_df) > 0 and not pd.isna(filtered_df["sleep_score"].iloc[0]) and filtered_df["sleep_score"].iloc[0] > avg_quality
                else "📉"
            )

            ModernUI.status_card(
                "💤 Среднее качество",
                f"{avg_quality:.1f}",
                quality_status,
                trend=quality_trend,
                description=f"За {period_label.lower()}",
            )

        with col2:
            avg_duration = filtered_df["total_sleep_minutes"].mean() / 60
            duration_status = "success" if 7 <= avg_duration <= 9 else "warning" if 6 <= avg_duration <= 10 else "danger"

            ModernUI.status_card(
                "⏰ Средняя длительность",
                f"{avg_duration:.1f}ч",
                duration_status,
                description="Рекомендуется 7-9ч",
            )

        with col3:
            avg_eff = filtered_df["sleep_efficiency"].mean()
            eff_status = "success" if avg_eff >= 85 else "warning" if avg_eff >= 75 else "danger"

            ModernUI.status_card(
                "⚡ Средняя эффективность",
                f"{avg_eff:.1f}%",
                eff_status,
                description="Норма >85%",
            )

        with col4:
            avg_awake = filtered_df["awakenings_count"].mean()
            awake_status = "success" if avg_awake <= 2 else "warning" if avg_awake <= 4 else "danger"

            ModernUI.status_card(
                "🌅 Среднее пробуждений",
                f"{avg_awake:.1f}",
                awake_status,
                description="Норма ≤2",
            )

    if len(filtered_df) > 0:
        st.subheader("🥧 Распределение фаз сна")

        avg_deep = filtered_df["deep_sleep_minutes"].mean()
        avg_light = filtered_df["light_sleep_minutes"].mean()
        avg_rem = filtered_df["rem_sleep_minutes"].mean()

        total_avg = avg_deep + avg_light + avg_rem

        if total_avg > 0:
            phases_data = {
                "Фаза": ["Глубокий сон", "Легкий сон", "REM сон"],
                "Минуты": [avg_deep, avg_light, avg_rem],
                "Процент": [
                    avg_deep / total_avg * 100,
                    avg_light / total_avg * 100,
                    avg_rem / total_avg * 100,
                ],
            }

            fig_pie = px.pie(
                values=phases_data["Минуты"],
                names=phases_data["Фаза"],
                title=f"🥧 Среднее распределение фаз сна за {period_label}",
                color_discrete_sequence=["#3B82F6", "#10B981", "#8B5CF6"],
                hole=0.4,
            )

            fig_pie.update_traces(
                textinfo="percent+label",
                textposition="inside",
                textfont_size=12,
                marker=dict(line=dict(color="white", width=2)),
            )

            fig_pie.update_layout(
                title={
                    "x": 0.5,
                    "xanchor": "center",
                    "font": {"size": 16, "color": "#1F2937"},
                },
                font=dict(family="Inter, -apple-system, sans-serif"),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                showlegend=True,
                legend=dict(
                    orientation="h",
                    yanchor="bottom",
                    y=-0.1,
                    xanchor="center",
                    x=0.5,
                ),
            )

            st.plotly_chart(fig_pie, use_container_width=True)

        st.subheader("💡 Рекомендации по сну")

        recommendations = []

        avg_quality = filtered_df["sleep_score"].mean()
        avg_duration = filtered_df["total_sleep_minutes"].mean() / 60
        avg_deep = filtered_df["deep_sleep_minutes"].mean()
        avg_rem = filtered_df["rem_sleep_minutes"].mean()
        total_avg = avg_deep + avg_light + avg_rem
        avg_awake = filtered_df["awakenings_count"].mean()

        if pd.isna(avg_quality):
            avg_quality = 0
        if pd.isna(avg_duration):
            avg_duration = 0
        if pd.isna(total_avg):
            total_avg = 0
        if pd.isna(avg_awake):
            avg_awake = 0

        if avg_quality < 60:
            recommendations.append("🔴 Низкое качество сна. Рекомендуется улучшить режим и гигиену сна.")
        elif avg_quality < 80:
            recommendations.append("🟡 Удовлетворительное качество сна. Есть возможности для улучшения.")
        else:
            recommendations.append("🟢 Отличное качество сна! Продолжайте в том же духе.")

        if avg_duration < 7:
            recommendations.append("🔴 Недостаточная продолжительность сна. Рекомендуется спать 7-9 часов.")
        elif avg_duration > 9:
            recommendations.append("🟡 Избыточная продолжительность сна. Проверьте качество восстановления.")
        else:
            recommendations.append("🟢 Оптимальная продолжительность сна.")

        if total_avg > 0:
            deep_pct = avg_deep / total_avg * 100
            rem_pct = avg_rem / total_avg * 100

            if deep_pct < 15:
                recommendations.append("🔴 Недостаточно глубокого сна. Избегайте кофеина и стресса перед сном.")
            if rem_pct < 20:
                recommendations.append("🔴 Недостаточно REM сна. Регулярный режим сна поможет улучшить REM фазы.")

        if avg_awake > 3:
            recommendations.append("🟡 Частые пробуждения. Проверьте температуру и освещение в спальне.")

        for recommendation in recommendations:
            st.write(f"• {recommendation}")

    st.subheader("📁 Экспорт данных")
    if st.button("📊 Скачать данные сна"):
        csv = filtered_df.to_csv(index=False)
        st.download_button(
            label="💾 Загрузить CSV файл",
            data=csv,
            file_name=f"sleep_data_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv",
        )


def _format_date(date_obj, format_type="display"):
    """Format dates for the sleep page."""
    if pd.isna(date_obj):
        return ""

    if isinstance(date_obj, str):
        try:
            date_obj = pd.to_datetime(date_obj)
        except Exception:
            return date_obj

    if format_type == "display":
        return date_obj.strftime("%d.%m.%Y")
    elif format_type == "db":
        return date_obj.strftime("%Y-%m-%d")
    elif format_type == "short":
        return date_obj.strftime("%d.%m")
    else:
        return str(date_obj)
