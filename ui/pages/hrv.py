"""HRV analysis page renderer."""
from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from services.data_cache import load_activities, load_hrv
from state import StateManager
from ui.plotly_theme import create_dark_table_html


def render_hrv_page(state: StateManager) -> None:
    """Render the HRV analysis page."""
    from utils.modern_ui import ModernUI
    from utils.visualizations import Visualizations

    if state.use_custom_theme:
        ModernUI.apply_modern_styles(dark_mode=state.dark_mode)

    st.header("💓 Анализ вариабельности сердечного ритма (HRV)")

    hrv_df = load_hrv(90)

    from models.hrv_analyzer import HRVAnalyzer

    hrv_analyzer = HRVAnalyzer()

    col1, col2 = st.columns(2)

    with col1:
        period_days = st.selectbox(
            "Период анализа:",
            options=[7, 14, 30, 60, 90],
            index=2,
            format_func=lambda x: f"Последние {x} дней",
        )

    with col2:
        trend_option = st.selectbox(
            "Отображение:",
            options=["Только данные", "Среднее", "Тренд", "Среднее + Тренд"],
            index=1,
        )

    hrv_df["date"] = pd.to_datetime(hrv_df["date"])
    cutoff_date = datetime.now() - timedelta(days=period_days)
    hrv_df = hrv_df[hrv_df["date"] >= cutoff_date].copy()
    hrv_df.sort_values("date", ascending=False, inplace=True)

    if hrv_df.empty:
        st.warning(f"📭 Нет данных HRV за последние {period_days} дней. Синхронизируйте данные с Garmin Connect.")
        with st.expander("❓ Что такое HRV?", expanded=True):
            st.markdown("**HRV (Heart Rate Variability)** - вариабельность сердечного ритма - это изменение времени между ударами сердца.")
            st.markdown("")
            st.markdown("**Основные показатели:**")
            st.markdown("- **RMSSD** - основной показатель HRV, отражает активность парасимпатической нервной системы")
            st.markdown("- **Стресс-индекс** - оценка текущего уровня стресса организма")
            st.markdown("- **Индекс восстановления** - готовность организма к нагрузкам")
            st.markdown("")
            st.markdown("**Как интерпретировать:**")
            st.markdown("- 🟢 **Высокий HRV** = хорошее восстановление, готовность к интенсивным тренировкам")
            st.markdown("- 🟡 **Средний HRV** = нормальное состояние, умеренные нагрузки")
            st.markdown("- 🔴 **Низкий HRV** = усталость/стресс, нужен отдых или лёгкие тренировки")
        return

    latest_data = hrv_df.iloc[0]
    baseline_rmssd = hrv_df["rmssd"].mean()

    latest_date = latest_data.get("date") if isinstance(latest_data, pd.Series) else None
    display_date = _format_date(latest_date, "display") if latest_date is not None and not pd.isna(latest_date) else "Н/Д"
    st.subheader(f"📊 Текущее состояние (данные от {display_date})")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        current_rmssd = latest_data["rmssd"] if pd.notna(latest_data["rmssd"]) else 0
        delta_rmssd = current_rmssd - baseline_rmssd if baseline_rmssd > 0 else 0

        rmssd_status = "success" if current_rmssd > 40 else "warning" if current_rmssd > 30 else "danger"
        trend_arrow = "↗️" if delta_rmssd > 0 else "↘️" if delta_rmssd < 0 else "➡️"

        ModernUI.status_card(
            "💓 RMSSD",
            f"{current_rmssd:.1f} мс",
            rmssd_status,
            trend=trend_arrow,
            description=f"{delta_rmssd:+.1f} от среднего",
        )

    with col2:
        stress_score = None
        if "stress_score" in latest_data and latest_data["stress_score"] is not None and not pd.isna(latest_data["stress_score"]):
            stress_score = latest_data["stress_score"]
            stress_status = "success" if stress_score < 30 else "warning" if stress_score < 60 else "danger"

            ModernUI.status_card(
                "😰 Стресс-индекс",
                f"{stress_score:.0f}",
                stress_status,
                description="Уровень стресса",
            )
        else:
            ModernUI.status_card(
                "😰 Стресс-индекс",
                "Н/Д",
                "secondary",
                description="Синхронизируйте с Garmin",
            )

    with col3:
        recovery_score = None
        if "recovery_score" in latest_data and latest_data["recovery_score"] is not None and not pd.isna(latest_data["recovery_score"]):
            recovery_score = latest_data["recovery_score"]
            recovery_status = "success" if recovery_score > 70 else "warning" if recovery_score > 40 else "danger"

            ModernUI.status_card(
                "🔄 Восстановление",
                f"{recovery_score:.0f}%",
                recovery_status,
                description="Готовность к нагрузке",
            )
        else:
            try:
                calculated_recovery = hrv_analyzer.recovery_score(current_rmssd, baseline_rmssd) if current_rmssd > 0 else 50
                recovery_status = "success" if calculated_recovery > 70 else "warning" if calculated_recovery > 40 else "danger"

                advanced_info = ""
                try:
                    advanced_score, info = hrv_analyzer.recovery_score_advanced(df_hrv)  # type: ignore[name-defined]
                    if advanced_score is not None:
                        advanced_info = f" | AI Endurance: {advanced_score:.0f}% ({info})"
                except Exception:
                    pass

                ModernUI.status_card(
                    "🔄 Восстановление",
                    f"{calculated_recovery:.0f}%",
                    recovery_status,
                    description=f"Простой RMSSD{advanced_info}",
                )
            except Exception:
                ModernUI.status_card(
                    "🔄 Восстановление",
                    "Н/Д",
                    "secondary",
                    description="Данные недоступны",
                )

    with col4:
        if current_rmssd > baseline_rmssd * 1.1:
            recommendation = "Интенсивная тренировка"
            rec_status = "success"
            rec_icon = "🟢"
        elif current_rmssd > baseline_rmssd * 0.9:
            recommendation = "Умеренная нагрузка"
            rec_status = "warning"
            rec_icon = "🟡"
        else:
            recommendation = "Отдых/восстановление"
            rec_status = "danger"
            rec_icon = "🔴"

        ModernUI.status_card(
            "🎯 Рекомендация",
            rec_icon,
            rec_status,
            description=recommendation,
        )

    if len(hrv_df) > 1:
        st.subheader("📈 Динамика показателей")

        hrv_dates = hrv_df["date"].tolist()
        hrv_values = hrv_df["rmssd"].tolist()

        fig_rmssd = Visualizations.create_hrv_trend(hrv_values, hrv_dates)

        if trend_option in ["Среднее", "Среднее + Тренд"]:
            avg_rmssd = hrv_df["rmssd"].mean()
            fig_rmssd.add_hline(
                y=avg_rmssd,
                line_dash="dash",
                line_color="#EF4444",
                line_width=2,
                annotation_text=f"Среднее: {avg_rmssd:.1f} мс",
                annotation_position="right",
            )

        if trend_option in ["Тренд", "Среднее + Тренд"]:
            valid_data = hrv_df[hrv_df["rmssd"].notna()].copy()
            if len(valid_data) >= 2:
                import numpy as np
                from sklearn.linear_model import LinearRegression

                x_numeric = np.arange(len(valid_data)).reshape(-1, 1)
                y_values = valid_data["rmssd"].values

                model = LinearRegression()
                model.fit(x_numeric, y_values)
                trend_values = model.predict(x_numeric)

                trend_slope = model.coef_[0]
                trend_direction = "📈" if trend_slope > 0 else "📉" if trend_slope < 0 else "➡️"
                trend_change = abs(trend_slope) * len(valid_data)

                fig_rmssd.add_trace(
                    go.Scatter(
                        x=valid_data["date"],
                        y=trend_values,
                        mode="lines",
                        name=f"Тренд {trend_direction} ({trend_change:+.1f} мс)",
                        line=dict(color="#8B5CF6", width=3, dash="dot"),
                        hovertemplate="<b>Тренд</b><br>%{y:.1f} мс<br>%{x}<extra></extra>",
                    )
                )

        fig_rmssd.update_layout(
            title={
                "text": "💓 Динамика HRV с зонами восстановления",
                "x": 0.5,
                "xanchor": "center",
                "font": {"size": 18, "color": "#1F2937"},
            }
        )

        st.plotly_chart(fig_rmssd, width="stretch")

    if not hrv_df.empty:
        st.subheader("🔍 Анализ взаимосвязей")

        activities_df = load_activities(period_days)

        if not activities_df.empty:
            activities_df["date"] = pd.to_datetime(activities_df["date"])

            daily_training = activities_df.groupby("date").agg({"tss": "sum", "duration_minutes": "sum"}).reset_index()

            combined_df = pd.merge(hrv_df, daily_training, on="date", how="left")
            combined_df["tss"] = combined_df["tss"].fillna(0)

            fig_correlation = go.Figure()

            fig_correlation.add_trace(
                go.Scatter(
                    x=combined_df["date"],
                    y=combined_df["rmssd"],
                    mode="lines+markers",
                    name="RMSSD (восстановление)",
                    yaxis="y",
                    line=dict(color="#10B981", width=3),
                    marker=dict(size=8, color="#10B981", line=dict(width=2, color="white")),
                    fill="tonexty",
                    fillcolor="rgba(16, 185, 129, 0.1)",
                    hovertemplate="<b>RMSSD</b><br>%{y:.1f} мс<br>%{x}<extra></extra>",
                )
            )

            fig_correlation.add_trace(
                go.Scatter(
                    x=combined_df["date"],
                    y=combined_df["tss"],
                    mode="lines+markers",
                    name="TSS (нагрузка)",
                    yaxis="y2",
                    line=dict(color="#EF4444", width=3),
                    marker=dict(size=8, color="#EF4444", line=dict(width=2, color="white")),
                    fill="tonexty",
                    fillcolor="rgba(239, 68, 68, 0.1)",
                    hovertemplate="<b>TSS</b><br>%{y:.0f}<br>%{x}<extra></extra>",
                )
            )

            fig_correlation.update_layout(
                title={
                    "text": "🔍 Взаимосвязь HRV и тренировочной нагрузки",
                    "x": 0.5,
                    "xanchor": "center",
                    "font": {"size": 18, "color": "#1F2937"},
                },
                xaxis_title="Дата",
                yaxis=dict(
                    title="RMSSD (мс)",
                    side="left",
                    showgrid=True,
                    gridwidth=1,
                    gridcolor="rgba(156, 163, 175, 0.2)",
                ),
                yaxis2=dict(
                    title="TSS (нагрузка)",
                    side="right",
                    overlaying="y",
                    showgrid=False,
                ),
                height=450,
                font=dict(family="Inter, -apple-system, sans-serif", size=12),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                legend=dict(
                    orientation="h",
                    yanchor="bottom",
                    y=1.02,
                    xanchor="right",
                    x=1,
                ),
                hovermode="x unified",
            )

            st.plotly_chart(fig_correlation, width="stretch")

            if len(combined_df) > 5:
                st.write("**📊 Анализ корреляции HRV и нагрузки:**")
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    correlation_same_day = combined_df[["rmssd", "tss"]].corr().iloc[0, 1]
                    if not pd.isna(correlation_same_day):
                        corr_status = "success" if abs(correlation_same_day) > 0.4 else "warning" if abs(correlation_same_day) > 0.2 else "secondary"
                        ModernUI.status_card("📅 Тот же день", f"{correlation_same_day:.3f}", corr_status)
                with col2:
                    combined_shifted = combined_df.copy()
                    combined_shifted["tss_prev"] = combined_shifted["tss"].shift(1)
                    correlation_lag1 = combined_shifted[["rmssd", "tss_prev"]].corr().iloc[0, 1]
                    if not pd.isna(correlation_lag1):
                        lag_status = "success" if abs(correlation_lag1) > 0.4 else "warning" if abs(correlation_lag1) > 0.2 else "secondary"
                        ModernUI.status_card("⏭️ Запаздывание (1 день)", f"{correlation_lag1:.3f}", lag_status)
                with col3:
                    combined_shifted["tss_3day"] = combined_shifted["tss"].rolling(window=3, min_periods=1).sum()
                    correlation_cumulative = combined_shifted[["rmssd", "tss_3day"]].corr().iloc[0, 1]
                    if not pd.isna(correlation_cumulative):
                        cum_status = "success" if abs(correlation_cumulative) > 0.4 else "warning" if abs(correlation_cumulative) > 0.2 else "secondary"
                        ModernUI.status_card("📈 Кумулятивная (3 дня)", f"{correlation_cumulative:.3f}", cum_status)
                with col4:
                    st.write("**🎯 Интерпретация:**")

                    correlations = {
                        "same_day": correlation_same_day,
                        "lag1": correlation_lag1,
                        "cumulative": correlation_cumulative,
                    }
                    valid_correlations = {k: v for k, v in correlations.items() if not pd.isna(v)}

                    if valid_correlations:
                        max_corr_key = max(valid_correlations, key=lambda k: abs(valid_correlations[k]))
                        max_corr_value = valid_correlations[max_corr_key]

                        if abs(max_corr_value) > 0.4:
                            if max_corr_value < 0:
                                st.success(f"✅ **Сильная обратная связь** ({max_corr_key.replace('_', ' ')})")
                                st.write("Высокая нагрузка приводит к снижению HRV")
                            else:
                                st.warning("⚠️ **Неожиданная прямая связь**")
                                st.write("Возможно недовосстановление или особенности тренировок")
                        elif abs(max_corr_value) > 0.2:
                            if max_corr_value < 0:
                                st.info(f"📈 **Умеренная обратная связь** ({max_corr_key.replace('_', ' ')})")
                                st.write("Заметное влияние нагрузки на HRV")
                            else:
                                st.info("📊 Умеренная прямая связь")
                        else:
                            st.info("ℹ️ **Слабая корреляция**")
                            training_days = len(combined_df[combined_df["tss"] > 0])
                            st.write(f"Дней с тренировками: {training_days}")
                            if training_days < 20:
                                st.write("💡 Для лучшего анализа нужно больше тренировочных данных")
                    else:
                        st.warning("⚠️ Недостаточно данных для анализа корреляции")

    if not hrv_df.empty:
        st.subheader("📋 Таблица данных")

        display_df = hrv_df.copy()
        display_df = display_df.sort_values("date", ascending=False)
        display_df["date"] = display_df["date"].apply(lambda x: _format_date(x, "display"))
        display_df["rmssd"] = display_df["rmssd"].round(1)

        display_columns = {
            "date": "Дата",
            "rmssd": "RMSSD (мс)",
            "stress_score": "Стресс-индекс",
            "recovery_score": "Восстановление (%)",
        }

        columns_to_show = [col for col in display_columns.keys() if col in display_df.columns]
        table_df = display_df[columns_to_show].rename(columns=display_columns)

        if state.use_custom_theme and state.dark_mode:
            st.markdown(create_dark_table_html(table_df), unsafe_allow_html=True)
        else:
            st.dataframe(table_df, width="stretch", hide_index=True)

    st.subheader("💡 Рекомендации по HRV")

    if not hrv_df.empty and len(hrv_df) > 7:
        recent_data = hrv_df.tail(7)
        rmssd_trend = recent_data["rmssd"].ffill().pct_change().mean() * 100

        col1, col2 = st.columns(2)

        with col1:
            st.write("**Тенденция за неделю:**")
            if rmssd_trend > 2:
                st.success("📈 HRV растет - отличное восстановление!")
                st.write("- Можно увеличивать интенсивность тренировок")
                st.write("- Организм хорошо адаптируется к нагрузкам")
            elif rmssd_trend < -2:
                st.warning("📉 HRV снижается - признак накопления усталости")
                st.write("- Рекомендуется снизить интенсивность")
                st.write("- Уделить больше внимания восстановлению")
            else:
                st.info("➡️ HRV стабильна - продолжайте текущий режим")

        with col2:
            st.write("**Советы по улучшению HRV:**")
            st.write("- 😴 Качественный сон 7-9 часов")
            st.write("- 🧘 Медитация и дыхательные практики")
            st.write("- 🥗 Сбалансированное питание")
            st.write("- 💧 Достаточная гидратация")
            st.write("- ⚖️ Баланс нагрузки и отдыха")
    else:
        st.info(
            """
        **Для полноценного анализа HRV рекомендуется:**
        - Регулярные измерения (ежедневно утром)
        - Минимум 7-14 дней данных
        - Постоянство условий измерения
        - Учёт факторов образа жизни
        """
        )

    if not hrv_df.empty:
        st.subheader("📤 Экспорт данных HRV")

        if st.button("📊 Скачать данные HRV"):
            csv = table_df.to_csv(index=False) if "table_df" in locals() else hrv_df.to_csv(index=False)
            st.download_button(
                label="💾 Загрузить CSV файл",
                data=csv,
                file_name=f"hrv_data_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv",
            )


def _format_date(date_obj, format_type="display"):
    """Стандартизированное форматирование дат."""
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
