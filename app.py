import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import os
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Импорты наших модулей
from models.banister import BanisterModel
from utils.visualizations import Visualizations
from config.settings import Settings
from state import StateManager, get_state_manager
from ui.components import render_chat_management, render_development_tools, render_garmin_connection
from ui.theme import apply_theme, create_dark_table_html, get_plotly_theme
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
    render_sync_logs_page,
    render_welcome_page,
)
from ui.pages.ai_coaching import (
    create_chat_system_prompt_with_tools,
    format_tool_result,
    simulate_streaming_response,
)
from services import garmin as garmin_service, sync as sync_service
from services.data_cache import (
    load_activities,
    load_hrv,
    load_sleep,
)
from utils.sleep_metrics import compute_sleep_regularity

st.set_page_config(
    page_title="AI Trainer",
    page_icon="🏃‍♂️",
    layout="wide",
    initial_sidebar_state="expanded"
)

logger = logging.getLogger(__name__)

def responsive_columns(num_items, mobile_cols=1, desktop_cols=None):
    """
    Create responsive columns based on screen size.
    Returns columns that work well on both mobile and desktop.
    """
    if desktop_cols is None:
        desktop_cols = num_items
    
    # Use container to check available width
    container = st.container()
    
    # For mobile: stack items vertically or use fewer columns
    # For desktop: use specified number of columns
    if desktop_cols <= 2:
        return st.columns(desktop_cols)
    elif desktop_cols <= 4:
        # For 3-4 columns, use 2x2 grid on mobile
        return st.columns(min(2, desktop_cols))
    else:
        # For 5-6 columns, use 3x2 grid
        return st.columns(min(3, desktop_cols))

def format_date(date_obj, format_type='display'):
    """
    Стандартизированное форматирование дат
    format_type: 'display' для UI (дд.мм.гггг), 'db' для БД (гггг-мм-дд), 'short' для компактного вида (дд.мм)
    """
    if pd.isna(date_obj):
        return ""
    
    if isinstance(date_obj, str):
        # Попытка распарсить строку
        try:
            date_obj = pd.to_datetime(date_obj)
        except:
            return date_obj
    
    if format_type == 'display':
        return date_obj.strftime('%d.%m.%Y')
    elif format_type == 'db':
        return date_obj.strftime('%Y-%m-%d')
    elif format_type == 'short':
        return date_obj.strftime('%d.%m')
    else:
        return str(date_obj)

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
    else:
        st.caption("Garmin не вернул дополнительных данных профиля.")

    with st.expander("Детали профиля Garmin", expanded=False):
        st.json(profile)


def main():
    state = get_state_manager()
    st.title("🏃‍♂️ Персональный AI Тренер")

    from utils.modern_ui import ModernUI
    if state.use_custom_theme:
        ModernUI.apply_modern_styles(dark_mode=state.dark_mode)

    apply_theme(state.dark_mode)

    col1, col2 = st.sidebar.columns([4, 1])
    with col1:
        st.title("🏃‍♂️ AI Trainer")
    with col2:
        st.markdown("<br>", unsafe_allow_html=True)
        if state.use_custom_theme:
            if st.button("🌙" if not state.dark_mode else "☀️",
                         help="Переключить тему",
                         use_container_width=True,
                         key="theme_toggle"):
                state.toggle_dark_mode()
                st.rerun()

    custom_theme_enabled = st.sidebar.checkbox("🎨 Кастомная тема", value=state.use_custom_theme, key="use_custom_theme_checkbox")
    if custom_theme_enabled != state.use_custom_theme:
        state.use_custom_theme = custom_theme_enabled
        st.rerun()

    render_garmin_connection(state, render_profile=render_garmin_profile)

    if garmin_service.is_authenticated(state):
        page = render_primary_navigation(state)
        sidebar_page = render_sidebar_navigation(state, page)
        if sidebar_page != page:
            page = sidebar_page

        render_sidebar_utilities(state)

        st.sidebar.markdown("---")

        _ = state.chat_manager  # Ensure chat manager initialised
        render_chat_management(state)

        st.sidebar.markdown("---")

        render_development_tools(state)

        if page == "📊 Дашборд":
            render_dashboard_page(state, on_sync=lambda days: sync_data(days=days, state=state))
        elif page == "🏃‍♂️ Активности":
            render_activities_page(state)
        elif page == "💓 Анализ HRV":
            show_hrv_analysis()
        elif page == "😴 Анализ сна":
            show_sleep_analysis()
        elif page == "📈 Планирование":
            show_planning()
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

    if not garmin_service.is_authenticated(state):
        st.error("Не подключен к Garmin Connect")
        return

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
        status_text.empty()
        sync_stats.empty()

        for warning in result.warnings:
            st.error(warning)

        if result.details:
            st.info("ℹ️ **Информация о данных:**\n" + "\n".join([f"• {detail}" for detail in result.details]))

        if result.success_messages:
            st.success("✅ " + " | ".join(result.success_messages))
        else:
            st.info("ℹ️ Новых данных не найдено")

        import time
        time.sleep(2)
        progress_container.empty()

    except Exception as e:
        progress_container.empty()
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

def show_hrv_analysis():
    """Современная страница анализа HRV"""
    state = get_state_manager()
    database = state.database
    from utils.modern_ui import ModernUI
    if state.use_custom_theme:
        ModernUI.apply_modern_styles(dark_mode=state.dark_mode)
    
    st.header("💓 Анализ вариабельности сердечного ритма (HRV)")
    
    # Получаем HRV данные за максимальный период для корректной фильтрации
    hrv_df = load_hrv(90)  # Получаем больше данных для фильтрации
    
    # Импортируем анализатор HRV
    from models.hrv_analyzer import HRVAnalyzer
    hrv_analyzer = HRVAnalyzer()
    
    # Период анализа
    col1, col2 = st.columns(2)
    
    with col1:
        period_days = st.selectbox(
            "Период анализа:",
            options=[7, 14, 30, 60, 90],
            index=2,
            format_func=lambda x: f"Последние {x} дней"
        )
    
    with col2:
        trend_option = st.selectbox(
            "Отображение:",
            options=["Только данные", "Среднее", "Тренд", "Среднее + Тренд"],
            index=1
        )
    
    # Фильтруем данные по выбранному периоду (надежный метод)
    hrv_df['date'] = pd.to_datetime(hrv_df['date'])
    cutoff_date = datetime.now() - timedelta(days=period_days)
    hrv_df = hrv_df[hrv_df['date'] >= cutoff_date].copy()
    # Гарантируем сортировку по дате (сначала самые свежие)
    hrv_df.sort_values('date', ascending=False, inplace=True)

    if hrv_df.empty:
        st.warning(f"📭 Нет данных HRV за последние {period_days} дней. Синхронизируйте данные с Garmin Connect.")
        # Информационный блок о HRV
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
    
    # Текущие показатели - всегда берём самые последние данные из уже загруженного DataFrame
    latest_data = hrv_df.iloc[0]  # Самая свежая запись
    # Базовый уровень рассчитываем от выбранного периода анализа
    baseline_rmssd = hrv_df['rmssd'].mean() # hrv_df не может быть пустым на этом этапе
    
    latest_date = latest_data.get('date') if isinstance(latest_data, pd.Series) else None
    display_date = format_date(latest_date, 'display') if latest_date is not None and not pd.isna(latest_date) else 'Н/Д'
    st.subheader(f"📊 Текущее состояние (данные от {display_date})")
    
    # Современные карточки состояния
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        current_rmssd = latest_data['rmssd'] if pd.notna(latest_data['rmssd']) else 0
        delta_rmssd = current_rmssd - baseline_rmssd if baseline_rmssd > 0 else 0
        
        # Определяем цветовой индикатор для RMSSD
        rmssd_status = "success" if current_rmssd > 40 else "warning" if current_rmssd > 30 else "danger"
        rmssd_icon = "🟢" if current_rmssd > 40 else "🟡" if current_rmssd > 30 else "🔴"
        
        trend_arrow = "↗️" if delta_rmssd > 0 else "↘️" if delta_rmssd < 0 else "➡️"
        
        ModernUI.status_card(
            "💓 RMSSD", 
            f"{current_rmssd:.1f} мс",
            rmssd_status,
            trend=trend_arrow,
            description=f"{delta_rmssd:+.1f} от среднего"
        )
    
    with col2:
        # Стресс-индекс с цветовыми индикаторами
        stress_score = None
        if 'stress_score' in latest_data and latest_data['stress_score'] is not None and not pd.isna(latest_data['stress_score']):
            stress_score = latest_data['stress_score']
            stress_status = "success" if stress_score < 30 else "warning" if stress_score < 60 else "danger"
            stress_icon = "🟢" if stress_score < 30 else "🟡" if stress_score < 60 else "🔴"
            
            ModernUI.status_card(
                "😰 Стресс-индекс", 
                f"{stress_score:.0f}",
                stress_status,
                description="Уровень стресса"
            )
        else:
            ModernUI.status_card(
                "😰 Стресс-индекс", 
                "Н/Д",
                "secondary",
                description="Синхронизируйте с Garmin"
            )
    
    with col3:
        # Восстановление
        recovery_score = None
        if 'recovery_score' in latest_data and latest_data['recovery_score'] is not None and not pd.isna(latest_data['recovery_score']):
            recovery_score = latest_data['recovery_score']
            recovery_status = "success" if recovery_score > 70 else "warning" if recovery_score > 40 else "danger"
            
            ModernUI.status_card(
                "🔄 Восстановление", 
                f"{recovery_score:.0f}%",
                recovery_status,
                description="Готовность к нагрузке"
            )
        else:
            # Рассчитываем на основе RMSSD
            try:
                # Простой метод
                calculated_recovery = hrv_analyzer.recovery_score(current_rmssd, baseline_rmssd) if current_rmssd > 0 else 50
                recovery_status = "success" if calculated_recovery > 70 else "warning" if calculated_recovery > 40 else "danger"
                
                # Продвинутый метод AI Endurance
                advanced_recovery = None
                advanced_info = ""
                try:
                    advanced_score, info = hrv_analyzer.recovery_score_advanced(df_hrv)
                    if advanced_score is not None:
                        advanced_recovery = advanced_score
                        advanced_info = f" | AI Endurance: {advanced_score:.0f}% ({info})"
                except:
                    pass
                
                ModernUI.status_card(
                    "🔄 Восстановление", 
                    f"{calculated_recovery:.0f}%",
                    recovery_status,
                    description=f"Простой RMSSD{advanced_info}"
                )
            except:
                ModernUI.status_card(
                    "🔄 Восстановление", 
                    "Н/Д",
                    "secondary",
                    description="Данные недоступны"
                )
    
    with col4:
        # Тренировочная рекомендация
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
            description=recommendation
        )
    
    # Графики динамики
    if len(hrv_df) > 1:
        st.subheader("📈 Динамика показателей")
        
        # Современный график RMSSD с зонами восстановления
        from utils.visualizations import Visualizations
        
        # Используем модернизированный график HRV
        hrv_dates = hrv_df['date'].tolist()
        hrv_values = hrv_df['rmssd'].tolist()
        
        fig_rmssd = Visualizations.create_hrv_trend(hrv_values, hrv_dates)
        
        # Добавляем среднее и/или тренд поверх современного графика
        if trend_option in ["Среднее", "Среднее + Тренд"]:
            avg_rmssd = hrv_df['rmssd'].mean()
            fig_rmssd.add_hline(
                y=avg_rmssd, 
                line_dash="dash", 
                line_color="#EF4444",
                line_width=2,
                annotation_text=f"Среднее: {avg_rmssd:.1f} мс",
                annotation_position="right"
            )
        
        if trend_option in ["Тренд", "Среднее + Тренд"]:
            # Вычисляем линейный тренд (линейная регрессия)
            valid_data = hrv_df[hrv_df['rmssd'].notna()].copy()
            if len(valid_data) >= 2:
                import numpy as np
                from sklearn.linear_model import LinearRegression
                
                # Подготавливаем данные для регрессии
                x_numeric = np.arange(len(valid_data)).reshape(-1, 1)
                y_values = valid_data['rmssd'].values
                
                # Строим линейную регрессию
                model = LinearRegression()
                model.fit(x_numeric, y_values)
                trend_values = model.predict(x_numeric)
                
                # Вычисляем направление тренда
                trend_slope = model.coef_[0]
                trend_direction = "📈" if trend_slope > 0 else "📉" if trend_slope < 0 else "➡️"
                trend_change = abs(trend_slope) * len(valid_data)  # Изменение за весь период
                
                # Добавляем линию тренда с современным стилем
                fig_rmssd.add_trace(go.Scatter(
                    x=valid_data['date'],
                    y=trend_values,
                    mode='lines',
                    name=f'Тренд {trend_direction} ({trend_change:+.1f} мс)',
                    line=dict(color='#8B5CF6', width=3, dash='dot'),
                    hovertemplate="<b>Тренд</b><br>%{y:.1f} мс<br>%{x}<extra></extra>"
                ))
        
        # Обновляем заголовок для более подробного описания
        fig_rmssd.update_layout(
            title={
                'text': "💓 Динамика HRV с зонами восстановления",
                'x': 0.5,
                'xanchor': 'center',
                'font': {'size': 18, 'color': '#1F2937'}
            }
        )
        
        st.plotly_chart(fig_rmssd, use_container_width=True)
    
    # График корреляции с тренировками
    if not hrv_df.empty:
        st.subheader("🔍 Анализ взаимосвязей")
        
        # Получаем данные активностей за тот же период
        activities_df = load_activities(period_days)
        
        if not activities_df.empty:
            activities_df['date'] = pd.to_datetime(activities_df['date'])
            
            # Агрегируем тренировки по дням
            daily_training = activities_df.groupby('date').agg({
                'tss': 'sum',
                'duration_minutes': 'sum'
            }).reset_index()
            
            # Объединяем с HRV данными
            combined_df = pd.merge(hrv_df, daily_training, on='date', how='left')
            combined_df['tss'] = combined_df['tss'].fillna(0)
            
            # Современный график корреляции HRV vs нагрузка
            fig_correlation = go.Figure()
            
            # RMSSD с современным стилем
            fig_correlation.add_trace(go.Scatter(
                x=combined_df['date'],
                y=combined_df['rmssd'],
                mode='lines+markers',
                name='RMSSD (восстановление)',
                yaxis='y',
                line=dict(color='#10B981', width=3),
                marker=dict(size=8, color='#10B981', line=dict(width=2, color='white')),
                fill='tonexty',
                fillcolor='rgba(16, 185, 129, 0.1)',
                hovertemplate='<b>RMSSD</b><br>%{y:.1f} мс<br>%{x}<extra></extra>'
            ))
            
            # TSS с современным стилем
            fig_correlation.add_trace(go.Scatter(
                x=combined_df['date'],
                y=combined_df['tss'],
                mode='lines+markers',
                name='TSS (нагрузка)',
                yaxis='y2',
                line=dict(color='#EF4444', width=3),
                marker=dict(size=8, color='#EF4444', line=dict(width=2, color='white')),
                fill='tonexty',
                fillcolor='rgba(239, 68, 68, 0.1)',
                hovertemplate='<b>TSS</b><br>%{y:.0f}<br>%{x}<extra></extra>'
            ))
            
            fig_correlation.update_layout(
                title={
                    'text': "🔍 Взаимосвязь HRV и тренировочной нагрузки",
                    'x': 0.5,
                    'xanchor': 'center',
                    'font': {'size': 18, 'color': '#1F2937'}
                },
                xaxis_title="Дата",
                yaxis=dict(
                    title="RMSSD (мс)",
                    side="left",
                    showgrid=True,
                    gridwidth=1,
                    gridcolor='rgba(156, 163, 175, 0.2)'
                ),
                yaxis2=dict(
                    title="TSS (нагрузка)",
                    side="right",
                    overlaying="y",
                    showgrid=False
                ),
                height=450,
                font=dict(family="Inter, -apple-system, sans-serif", size=12),
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                legend=dict(
                    orientation="h",
                    yanchor="bottom",
                    y=1.02,
                    xanchor="right",
                    x=1
                ),
                hovermode='x unified'
            )
            
            st.plotly_chart(fig_correlation, use_container_width=True)
            
            # Улучшенный анализ корреляции с запаздыванием
            if len(combined_df) > 5:
                st.write("**📊 Анализ корреляции HRV и нагрузки:**")
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    # Корреляция в тот же день
                    correlation_same_day = combined_df[['rmssd', 'tss']].corr().iloc[0, 1]
                    # Современные карточки корреляции
                    if not pd.isna(correlation_same_day):
                        corr_status = "success" if abs(correlation_same_day) > 0.4 else "warning" if abs(correlation_same_day) > 0.2 else "secondary"
                        ModernUI.status_card("📅 Тот же день", f"{correlation_same_day:.3f}", corr_status)
                with col2:
                    # Корреляция с запаздыванием (HRV следующего дня vs TSS предыдущего)
                    combined_shifted = combined_df.copy()
                    combined_shifted['tss_prev'] = combined_shifted['tss'].shift(1)  # TSS предыдущего дня
                    correlation_lag1 = combined_shifted[['rmssd', 'tss_prev']].corr().iloc[0, 1]
                    if not pd.isna(correlation_lag1):
                        lag_status = "success" if abs(correlation_lag1) > 0.4 else "warning" if abs(correlation_lag1) > 0.2 else "secondary"
                        ModernUI.status_card("⏭️ Запаздывание (1 день)", f"{correlation_lag1:.3f}", lag_status)
                with col3:
                    # Кумулятивная нагрузка за последние 3 дня
                    combined_shifted['tss_3day'] = combined_shifted['tss'].rolling(window=3, min_periods=1).sum()
                    correlation_cumulative = combined_shifted[['rmssd', 'tss_3day']].corr().iloc[0, 1]
     
                    if not pd.isna(correlation_cumulative):
                        cum_status = "success" if abs(correlation_cumulative) > 0.4 else "warning" if abs(correlation_cumulative) > 0.2 else "secondary"
                        ModernUI.status_card("📈 Кумулятивная (3 дня)", f"{correlation_cumulative:.3f}", cum_status)
                with col4:
                    st.write("**🎯 Интерпретация:**")
                    
                    # Находим наиболее значимую корреляцию
                    correlations = {
                        'same_day': correlation_same_day,
                        'lag1': correlation_lag1, 
                        'cumulative': correlation_cumulative
                    }
                    
                    # Убираем NaN значения
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
                            training_days = len(combined_df[combined_df['tss'] > 0])
                            st.write(f"Дней с тренировками: {training_days}")
                            if training_days < 20:
                                st.write("💡 Для лучшего анализа нужно больше тренировочных данных")
                    else:
                        st.warning("⚠️ Недостаточно данных для анализа корреляции")
    
    # Таблица данных
    if not hrv_df.empty:
        st.subheader("📋 Таблица данных")
        
        # Форматируем данные ПОСЛЕ сортировки для корректного отображения дат
        display_df = hrv_df.copy()
        
        # Сначала сортируем по datetime (данные уже отсортированы, но для безопасности)
        display_df = display_df.sort_values('date', ascending=False)
        
        # Потом форматируем дату в строку
        display_df['date'] = display_df['date'].apply(lambda x: format_date(x, 'display'))
        display_df['rmssd'] = display_df['rmssd'].round(1)
        
        # Переименовываем колонки
        display_columns = {
            'date': 'Дата',
            'rmssd': 'RMSSD (мс)',
            'stress_score': 'Стресс-индекс',
            'recovery_score': 'Восстановление (%)'
        }
        
        columns_to_show = [col for col in display_columns.keys() if col in display_df.columns]
        table_df = display_df[columns_to_show].rename(columns=display_columns)
        
        # Отображаем таблицу с учетом темы
        if state.use_custom_theme and state.dark_mode:
            st.markdown(create_dark_table_html(table_df), unsafe_allow_html=True)
        else:
            st.dataframe(table_df, use_container_width=True, hide_index=True)
    
    # Рекомендации
    st.subheader("💡 Рекомендации по HRV")
    
    if not hrv_df.empty and len(hrv_df) > 7:
        # Анализ тенденций за последнюю неделю
        recent_data = hrv_df.tail(7)
        rmssd_trend = recent_data['rmssd'].ffill().pct_change().mean() * 100
        
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
        st.info("""
        **Для полноценного анализа HRV рекомендуется:**
        - Регулярные измерения (ежедневно утром)
        - Минимум 7-14 дней данных
        - Постоянство условий измерения
        - Учёт факторов образа жизни
        """)
    
    # Экспорт данных
    if not hrv_df.empty:
        st.subheader("📤 Экспорт данных HRV")
        
        if st.button("📊 Скачать данные HRV"):
            csv = table_df.to_csv(index=False) if 'table_df' in locals() else hrv_df.to_csv(index=False)
            st.download_button(
                label="💾 Загрузить CSV файл",
                data=csv,
                file_name=f"hrv_data_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv"
            )

def show_sleep_analysis():
    """Современная страница анализа сна"""
    state = get_state_manager()
    database = state.database
    from utils.modern_ui import ModernUI
    if state.use_custom_theme:
        ModernUI.apply_modern_styles(dark_mode=state.dark_mode)
    
    st.header("😴 Анализ качества сна")
    
    # Получаем данные сна из БД
    sleep_df = load_sleep(90)
    
    if sleep_df.empty:
        st.warning("📊 Данные сна отсутствуют. Выполните синхронизацию с Garmin Connect.")
        if st.button("🔄 Синхронизировать данные"):
            st.rerun()
        return
    
    # Селектор периода
    period_options = {
        "7 дней": 7,
        "14 дней": 14, 
        "30 дней": 30,
        "60 дней": 60,
        "90 дней": 90
    }
    
    period_label = st.selectbox(
        "📅 Период анализа:",
        options=list(period_options.keys()),
        index=2,  # По умолчанию 30 дней
        key="sleep_period_selector"
    )
    period_days = period_options[period_label]
    
    # Фильтруем данные по выбранному периоду
    cutoff_date = datetime.now() - timedelta(days=period_days)
    filtered_df = sleep_df[sleep_df['date'] >= cutoff_date].copy()
    
    if filtered_df.empty:
        st.warning(f"📊 Нет данных сна за последние {period_days} дней.")
        return
    
    # Текущее состояние сна (последние данные) - явно сортируем по дате
    latest_sleep = None
    if not filtered_df.empty:
        sorted_df = filtered_df.sort_values('date', ascending=False)
        latest_sleep = sorted_df.iloc[0]
    
    if latest_sleep is not None:
        st.subheader(f"🌙 Последний сон ({format_date(latest_sleep['date'], 'display')})")
        
        # Карточки метрик сна в стиле AI Endurance
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            total_minutes = latest_sleep.get('total_sleep_minutes', 0)
            hours = total_minutes // 60
            minutes = total_minutes % 60
            
            # Цветовые зоны продолжительности (оптимально 7-9 часов)
            duration_hours = total_minutes / 60
            duration_status = "success" if 7 <= duration_hours <= 9 else "warning" if 6 <= duration_hours <= 10 else "danger"
            duration_description = "Оптимально" if 7 <= duration_hours <= 9 else "Приемлемо" if 6 <= duration_hours <= 10 else "Недостаточно" if duration_hours < 7 else "Слишком много"
            
            ModernUI.status_card(
                "⏰ Продолжительность", 
                f"{hours}ч {minutes}м",
                duration_status,
                description=duration_description
            )
        
        with col2:
            sleep_score = latest_sleep.get('sleep_score', 0)
            sleep_status = "success" if sleep_score >= 80 else "warning" if sleep_score >= 60 else "danger"
            sleep_icon = "🟢" if sleep_score >= 80 else "🟡" if sleep_score >= 60 else "🔴"
            
            ModernUI.status_card(
                "💤 Sleep Score", 
                f"{sleep_score:.1f}",
                sleep_status,
                description="Качество сна"
            )
        
        with col3:
            efficiency = latest_sleep.get('sleep_efficiency', 0)
            efficiency_status = "success" if efficiency >= 85 else "warning" if efficiency >= 75 else "danger"
            
            ModernUI.status_card(
                "⚡ Эффективность", 
                f"{efficiency:.1f}%",
                efficiency_status,
                description="Время сна от времени в постели"
            )
        
        with col4:
            awakenings = latest_sleep.get('awakenings_count', 0)
            awakenings_status = "success" if awakenings <= 2 else "warning" if awakenings <= 4 else "danger"
            
            ModernUI.status_card(
                "🌅 Пробуждения", 
                f"{awakenings:.0f}",
                awakenings_status,
                description="Количество пробуждений"
            )

        regularity_metrics = compute_sleep_regularity(filtered_df)
        bedtime_metric = (regularity_metrics or {}).get('bedtime')
        wake_metric = (regularity_metrics or {}).get('wakeup')
        if (
            regularity_metrics.get('count', 0) >= 3
            and bedtime_metric
            and wake_metric
            and bedtime_metric.get('status') != 'secondary'
            and wake_metric.get('status') != 'secondary'
        ):
            st.subheader("⏱ Регулярность режима")
            reg_col1, reg_col2 = st.columns(2)

            with reg_col1:
                ModernUI.status_card(
                    "🛏️ Время отбоя",
                    f"σ {bedtime_metric['std_text']}",
                    bedtime_metric['status'],
                    description=f"Среднее: {bedtime_metric['mean_text']} • Δ±{bedtime_metric['mad_text']} ({bedtime_metric['label']})"
                )
                st.caption(bedtime_metric['recommendation'])

            with reg_col2:
                ModernUI.status_card(
                    "🌅 Пробуждение",
                    f"σ {wake_metric['std_text']}",
                    wake_metric['status'],
                    description=f"Среднее: {wake_metric['mean_text']} • Δ±{wake_metric['mad_text']} ({wake_metric['label']})"
                )
                st.caption(wake_metric['recommendation'])
        elif regularity_metrics.get('count', 0) > 0:
            st.caption("Недостаточно данных, чтобы сформировать метрику регулярности сна — нужно минимум 3 записи с временем отбоя и подъёма.")

        weekday_profile_df = (regularity_metrics or {}).get('weekday_profile')
        if weekday_profile_df is not None and not weekday_profile_df.empty:
            st.subheader("📊 Засыпание и пробуждение по дням недели")

            plot_df = weekday_profile_df.copy()
            bedtime_hours = plot_df['bedtime_hours']
            wake_hours = plot_df['wakeup_hours']
            duration_hours = plot_df['sleep_duration_hours']
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
            tick_text = [f"{(h % 24):02d}:00" for h in tick_vals]

            fig_weekday = go.Figure()
            fig_weekday.add_trace(
                go.Bar(
                    x=plot_df['weekday_label'],
                    y=duration_hours,
                    base=bedtime_hours,
                    width=0.55,
                    marker=dict(
                        color='rgba(148,163,184,0.75)',
                        line=dict(color='rgba(148,163,184,0.95)', width=1.4),
                        pattern=dict(shape='', solidity=0.7),
                    ),
                    hovertemplate=(
                        'Отбой: %{customdata[0]}<br>'
                        'Подъём: %{customdata[1]}<br>'
                        'Средняя длительность: %{customdata[2]}<br>'
                        'Замеров: %{customdata[3]}<extra></extra>'
                    ),
                    customdata=plot_df[[
                        'bedtime_text',
                        'wakeup_text',
                        'sleep_duration_text',
                        'count'
                    ]],
                    name='Сон',
                )
            )

            earliest_bed = float(bedtime_hours.min()) if not bedtime_hours.empty else lower
            latest_wake = float(wake_hours.max()) if not wake_hours.empty else upper

            fig_weekday.update_layout(
                xaxis_title='День недели',
                legend_title='',
                hovermode='x',
                bargap=0.4,
                bargroupgap=0.2,
                shapes=[
                    dict(
                        type='line',
                        xref='paper',
                        x0=0,
                        x1=1,
                        y0=earliest_bed,
                        y1=earliest_bed,
                        line=dict(color='rgba(148,163,184,0.6)', dash='dash')
                    ),
                    dict(
                        type='line',
                        xref='paper',
                        x0=0,
                        x1=1,
                        y0=latest_wake,
                        y1=latest_wake,
                        line=dict(color='rgba(148,163,184,0.6)', dash='dash')
                    ),
                ],
            )
            fig_weekday.update_yaxes(
                title_text='Время суток',
                range=[lower, upper],
                tickmode='array',
                tickvals=tick_vals,
                ticktext=tick_text,
            )

            st.plotly_chart(fig_weekday, use_container_width=True)
            st.caption("Столбики показывают средний интервал сна по дням. Чем ровнее высота, тем стабильнее режим.")
        
        # Детали фаз сна с современными карточками
        st.subheader("🌀 Фазы сна")
        col1, col2, col3 = st.columns(3)
        
        with col1:
            deep_min = latest_sleep.get('deep_sleep_minutes', 0)
            deep_pct = (deep_min / total_minutes * 100) if total_minutes > 0 else 0
            # Нормальный глубокий сон: 15-20% от общего времени сна
            deep_status = "success" if 15 <= deep_pct <= 25 else "warning" if 10 <= deep_pct <= 30 else "danger"
            
            ModernUI.status_card(
                "🛌 Глубокий сон", 
                f"{deep_min}мин",
                deep_status,
                description=f"{deep_pct:.1f}% от сна"
            )
        
        with col2:
            light_min = latest_sleep.get('light_sleep_minutes', 0)
            light_pct = (light_min / total_minutes * 100) if total_minutes > 0 else 0
            # Нормальный легкий сон: 45-55% от общего времени сна
            light_status = "success" if 45 <= light_pct <= 65 else "warning" if 35 <= light_pct <= 75 else "danger"
            
            ModernUI.status_card(
                "💤 Легкий сон", 
                f"{light_min}мин",
                light_status,
                description=f"{light_pct:.1f}% от сна"
            )
        
        with col3:
            rem_min = latest_sleep.get('rem_sleep_minutes', 0)
            rem_pct = (rem_min / total_minutes * 100) if total_minutes > 0 else 0
            # Нормальный REM сон: 20-25% от общего времени сна
            rem_status = "success" if 20 <= rem_pct <= 30 else "warning" if 15 <= rem_pct <= 35 else "danger"
            
            ModernUI.status_card(
                "🧠 REM сон", 
                f"{rem_min}мин",
                rem_status,
                description=f"{rem_pct:.1f}% от сна"
            )
        
        # Время сна
        if latest_sleep.get('bedtime') and latest_sleep.get('wakeup_time'):
            col1, col2 = st.columns(2)
            with col1:
                st.metric("🌙 Время засыпания", latest_sleep['bedtime'])
            with col2:
                st.metric("🌅 Время пробуждения", latest_sleep['wakeup_time'])
            # Пояснение часового пояса для времени сна
            try:
                tz_name = datetime.now().astimezone().tzname()
                st.caption(f"Время отображается в локальной зоне: {tz_name}")
            except Exception:
                st.caption("Время отображается в локальной часовой зоне устройства/сервера")
    
    # Тренды и графики
    st.subheader("📈 Тренды сна")
    
    if len(filtered_df) > 1:
        # Современный график трендов сна с градиентами
        fig = make_subplots(
            rows=2, cols=2,
            subplot_titles=[
                '💤 Качество сна', '⏰ Продолжительность сна',
                '⚡ Эффективность сна', '🌅 Пробуждения'
            ],
            vertical_spacing=0.15,
            horizontal_spacing=0.1
        )
        
        dates = filtered_df['date']
        
        # Качество сна с градиентной заливкой
        fig.add_trace(
            go.Scatter(
                x=dates, 
                y=filtered_df['sleep_score'],
                mode='lines+markers',
                name='Качество сна',
                line=dict(color='#3B82F6', width=3),
                marker=dict(size=8, color='#3B82F6', line=dict(width=2, color='white')),
                fill='tonexty',
                fillcolor='rgba(59, 130, 246, 0.2)',
                hovertemplate='<b>Sleep Score</b><br>%{y:.1f}<br>%{x}<extra></extra>'
            ),
            row=1, col=1
        )
        
        # Продолжительность с цветовыми зонами
        sleep_hours = filtered_df['total_sleep_minutes'] / 60
        fig.add_trace(
            go.Scatter(
                x=dates, 
                y=sleep_hours,
                mode='lines+markers',
                name='Часы сна',
                line=dict(color='#10B981', width=3),
                marker=dict(size=8, color='#10B981', line=dict(width=2, color='white')),
                fill='tonexty',
                fillcolor='rgba(16, 185, 129, 0.2)',
                hovertemplate='<b>Продолжительность</b><br>%{y:.1f}ч<br>%{x}<extra></extra>'
            ),
            row=1, col=2
        )
        
        # Эффективность сна
        fig.add_trace(
            go.Scatter(
                x=dates, 
                y=filtered_df['sleep_efficiency'],
                mode='lines+markers',
                name='Эффективность %',
                line=dict(color='#8B5CF6', width=3),
                marker=dict(size=8, color='#8B5CF6', line=dict(width=2, color='white')),
                fill='tonexty',
                fillcolor='rgba(139, 92, 246, 0.2)',
                hovertemplate='<b>Эффективность</b><br>%{y:.1f}%<br>%{x}<extra></extra>'
            ),
            row=2, col=1
        )
        
        # Пробуждения
        fig.add_trace(
            go.Scatter(
                x=dates, 
                y=filtered_df['awakenings_count'],
                mode='lines+markers',
                name='Пробуждения',
                line=dict(color='#EF4444', width=3),
                marker=dict(size=8, color='#EF4444', line=dict(width=2, color='white')),
                fill='tonexty',
                fillcolor='rgba(239, 68, 68, 0.2)',
                hovertemplate='<b>Пробуждения</b><br>%{y:.0f}<br>%{x}<extra></extra>'
            ),
            row=2, col=2
        )
        
        fig.update_layout(
            height=550,
            showlegend=False,
            title={
                'text': f"📈 Тренды сна за {period_label}",
                'x': 0.5,
                'xanchor': 'center',
                'font': {'size': 18, 'color': '#1F2937'}
            },
            font=dict(family="Inter, -apple-system, sans-serif", size=12),
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            hovermode='x unified'
        )
        
        # Добавляем оптимальные зоны и средние линии
        avg_score = filtered_df['sleep_score'].mean()
        avg_hours = filtered_df['total_sleep_minutes'].mean() / 60
        avg_efficiency = filtered_df['sleep_efficiency'].mean()
        avg_awakenings = filtered_df['awakenings_count'].mean()
        
        # Оптимальные зоны для продолжительности (7-9 часов)
        fig.add_hrect(
            y0=7, y1=9, fillcolor="rgba(16, 185, 129, 0.1)", 
            line_width=0, row=1, col=2
        )
        fig.add_hline(
            y=8, line_dash="dot", line_color="#10B981", line_width=2,
            annotation_text="Оптимально", annotation_position="right",
            row=1, col=2
        )
        
        # Оптимальная эффективность (>85%)
        fig.add_hline(
            y=85, line_dash="dot", line_color="#8B5CF6", line_width=2,
            annotation_text="Хорошо", annotation_position="right",
            row=2, col=1
        )
        
        # Линии качества сна
        fig.add_hline(
            y=80, line_dash="dot", line_color="#10B981", line_width=1,
            annotation_text="Отлично", annotation_position="right",
            row=1, col=1
        )
        fig.add_hline(
            y=60, line_dash="dot", line_color="#F59E0B", line_width=1,
            annotation_text="Удовлетворительно", annotation_position="right",
            row=1, col=1
        )
        
        # Средние линии с современным стилем
        fig.add_hline(
            y=avg_score, line_dash="dash", line_color="#6B7280", line_width=2,
            annotation_text=f"Среднее: {avg_score:.1f}", annotation_position="left",
            row=1, col=1
        )
        fig.add_hline(
            y=avg_hours, line_dash="dash", line_color="#6B7280", line_width=2,
            annotation_text=f"Среднее: {avg_hours:.1f}ч", annotation_position="left",
            row=1, col=2
        )
        fig.add_hline(
            y=avg_efficiency, line_dash="dash", line_color="#6B7280", line_width=2,
            annotation_text=f"Среднее: {avg_efficiency:.1f}%", annotation_position="left",
            row=2, col=1
        )
        fig.add_hline(
            y=avg_awakenings, line_dash="dash", line_color="#6B7280", line_width=2,
            annotation_text=f"Среднее: {avg_awakenings:.1f}", annotation_position="left",
            row=2, col=2
        )
        
        # Обновляем оси для современного вида
        fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor='rgba(156, 163, 175, 0.2)')
        fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor='rgba(156, 163, 175, 0.2)')
        
        st.plotly_chart(fig, use_container_width=True)
        
        # Статистика за период с современными карточками
        st.subheader("📊 Статистика за период")
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            avg_quality = filtered_df['sleep_score'].mean()
            if pd.isna(avg_quality):
                avg_quality = 0
            
            quality_status = "success" if avg_quality >= 80 else "warning" if avg_quality >= 60 else "danger"
            quality_trend = "📈" if len(filtered_df) > 0 and not pd.isna(filtered_df['sleep_score'].iloc[0]) and filtered_df['sleep_score'].iloc[0] > avg_quality else "📉"
            
            ModernUI.status_card(
                "💤 Среднее качество", 
                f"{avg_quality:.1f}",
                quality_status,
                trend=quality_trend,
                description=f"За {period_label.lower()}"
            )
        
        with col2:
            avg_duration = filtered_df['total_sleep_minutes'].mean() / 60
            duration_status = "success" if 7 <= avg_duration <= 9 else "warning" if 6 <= avg_duration <= 10 else "danger"
            
            ModernUI.status_card(
                "⏰ Средняя длительность", 
                f"{avg_duration:.1f}ч",
                duration_status,
                description="Рекомендуется 7-9ч"
            )
        
        with col3:
            avg_eff = filtered_df['sleep_efficiency'].mean()
            eff_status = "success" if avg_eff >= 85 else "warning" if avg_eff >= 75 else "danger"
            
            ModernUI.status_card(
                "⚡ Средняя эффективность", 
                f"{avg_eff:.1f}%",
                eff_status,
                description="Норма >85%"
            )
        
        with col4:
            avg_awake = filtered_df['awakenings_count'].mean()
            awake_status = "success" if avg_awake <= 2 else "warning" if avg_awake <= 4 else "danger"
            
            ModernUI.status_card(
                "🌅 Среднее пробуждений", 
                f"{avg_awake:.1f}",
                awake_status,
                description="Норма ≤2"
            )
    
    # Распределение фаз сна
    if len(filtered_df) > 0:
        st.subheader("🥧 Распределение фаз сна")
        
        # Среднее распределение фаз за период
        avg_deep = filtered_df['deep_sleep_minutes'].mean()
        avg_light = filtered_df['light_sleep_minutes'].mean()
        avg_rem = filtered_df['rem_sleep_minutes'].mean()
        
        total_avg = avg_deep + avg_light + avg_rem
        
        if total_avg > 0:
            import plotly.express as px
            
            phases_data = {
                'Фаза': ['Глубокий сон', 'Легкий сон', 'REM сон'],
                'Минуты': [avg_deep, avg_light, avg_rem],
                'Процент': [
                    avg_deep / total_avg * 100,
                    avg_light / total_avg * 100,
                    avg_rem / total_avg * 100
                ]
            }
            
            fig_pie = px.pie(
                values=phases_data['Минуты'],
                names=phases_data['Фаза'],
                title=f"🥧 Среднее распределение фаз сна за {period_label}",
                color_discrete_sequence=['#3B82F6', '#10B981', '#8B5CF6'],  # Современная палитра
                hole=0.4  # Создаем кольцевую диаграмму
            )
            
            # Обновляем стиль пайчарта
            fig_pie.update_traces(
                textinfo='percent+label',
                textposition='inside',
                textfont_size=12,
                marker=dict(line=dict(color='white', width=2))
            )
            
            fig_pie.update_layout(
                title={
                    'x': 0.5,
                    'xanchor': 'center',
                    'font': {'size': 16, 'color': '#1F2937'}
                },
                font=dict(family="Inter, -apple-system, sans-serif"),
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                showlegend=True,
                legend=dict(
                    orientation="h",
                    yanchor="bottom",
                    y=-0.1,
                    xanchor="center",
                    x=0.5
                )
            )
            
            st.plotly_chart(fig_pie, use_container_width=True)
        
        # Таблица с рекомендациями (вынесена из условного блока)
        st.subheader("💡 Рекомендации по сну")
        
        recommendations = []
        
        # Получаем переменные для анализа, убеждаемся что они определены
        avg_quality = filtered_df['sleep_score'].mean()
        avg_duration = filtered_df['total_sleep_minutes'].mean() / 60
        avg_deep = filtered_df['deep_sleep_minutes'].mean()
        avg_rem = filtered_df['rem_sleep_minutes'].mean()
        total_avg = avg_deep + avg_light + avg_rem
        avg_awake = filtered_df['awakenings_count'].mean()
        
        # Проверяем на NaN значения
        if pd.isna(avg_quality):
            avg_quality = 0
        if pd.isna(avg_duration):
            avg_duration = 0
        if pd.isna(total_avg):
            total_avg = 0
        if pd.isna(avg_awake):
            avg_awake = 0
        
        # Анализ качества сна
        if avg_quality < 60:
            recommendations.append("🔴 Низкое качество сна. Рекомендуется улучшить режим и гигиену сна.")
        elif avg_quality < 80:
            recommendations.append("🟡 Удовлетворительное качество сна. Есть возможности для улучшения.")
        else:
            recommendations.append("🟢 Отличное качество сна! Продолжайте в том же духе.")
        
        # Анализ продолжительности
        if avg_duration < 7:
            recommendations.append("🔴 Недостаточная продолжительность сна. Рекомендуется спать 7-9 часов.")
        elif avg_duration > 9:
            recommendations.append("🟡 Избыточная продолжительность сна. Проверьте качество восстановления.")
        else:
            recommendations.append("🟢 Оптимальная продолжительность сна.")
        
        # Анализ фаз (только если есть данные)
        if total_avg > 0:
            deep_pct = avg_deep / total_avg * 100
            rem_pct = avg_rem / total_avg * 100
            
            if deep_pct < 15:
                recommendations.append("🔴 Недостаточно глубокого сна. Избегайте кофеина и стресса перед сном.")
            if rem_pct < 20:
                recommendations.append("🔴 Недостаточно REM сна. Регулярный режим сна поможет улучшить REM фазы.")
        
        # Анализ пробуждений
        if avg_awake > 3:
            recommendations.append("🟡 Частые пробуждения. Проверьте температуру и освещение в спальне.")
        
        # Отображаем рекомендации
        for rec in recommendations:
            st.write(f"• {rec}")
    
    # Экспорт данных
    st.subheader("📁 Экспорт данных")
    if st.button("📊 Скачать данные сна"):
        csv = filtered_df.to_csv(index=False)
        st.download_button(
            label="💾 Загрузить CSV файл",
            data=csv,
            file_name=f"sleep_data_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv"
        )

def show_planning():
    """Страница планирования с моделью Банистера"""
    state = get_state_manager()
    database = state.database
    st.header("📈 Планирование тренировок")
    
    # Получаем данные активностей
    activities_df = load_activities(90)  # 90 дней для лучшего анализа
    
    if activities_df.empty:
        st.warning("📭 Нет данных для анализа. Синхронизируйте данные с Garmin Connect.")
        return
    
    # Инициализируем модель Банистера
    banister = BanisterModel()
    
    # Подготавливаем данные с безопасной обработкой
    tss_data = []
    dates = []
    
    for idx, row in activities_df.iterrows():
        tss_val = row['tss'] if 'tss' in row and pd.notna(row['tss']) else 0
        # Обрабатываем NaN и None значения
        if pd.isna(tss_val) or tss_val is None:
            tss_val = 0
        tss_data.append(float(tss_val))
        dates.append(row['date'])
    
    # Вычисляем метрики
    current_metrics = banister.get_current_metrics(tss_data, dates)
    
    # Отображаем текущие метрики
    st.subheader("🎯 Текущее состояние")
    # Адаптивная сетка: 2x2 на мобильных
    col1, col2 = st.columns(2)
    col3, col4 = st.columns(2)
    
    with col1:
        st.metric("CTL (Фитнес)", current_metrics['ctl'])
    with col2:
        st.metric("ATL (Усталость)", current_metrics['atl'])
    with col3:
        st.metric("TSB (Форма)", current_metrics['tsb'])
    with col4:
        form_color = {
            "Отличная форма": "🟢",
            "Хорошая форма": "🟡", 
            "Усталость": "🟠",
            "Переутомление": "🔴",
            "Недостаточно данных": "⚫"
        }
        form_status = current_metrics['form'] if 'form' in current_metrics else 'Недостаточно данных'
        st.metric("Состояние", f"{form_color.get(form_status, '⚫')} {form_status}")
    
    # График модели Банистера
    st.subheader("📊 Анализ фитнеса и усталости")
    
    # Расчёт CTL, ATL, TSB
    dates_full, ctl_values, atl_values, tsb_values = banister.calculate_ctl_atl_tsb(tss_data, dates)
    
    if dates_full and ctl_values:
        fig_banister = Visualizations.create_banister_chart(dates_full, ctl_values, atl_values, tsb_values)
        st.plotly_chart(fig_banister, use_container_width=True)
    
    # Рекомендации
    st.subheader("💡 Рекомендации по тренировкам")
    recommendation = banister.get_training_recommendation(current_metrics)
    
    # Цветовая карта для интенсивности
    intensity_colors = {
        "Высокая": "🔴",
        "Умеренная": "🟡",
        "Низкая": "🟢", 
        "Очень низкая/Отдых": "🔵"
    }
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.markdown(f"""
        **{recommendation['recommendation']}**
        
        {recommendation['description']}
        
        **Рекомендуемый диапазон TSS:** {recommendation['suggested_tss']}
        """)
    
    with col2:
        st.markdown(f"""
        **Интенсивность:** {intensity_colors.get(recommendation['intensity'], '⚫')} {recommendation['intensity']}
        """)
    
    # Планирование нагрузки
    st.subheader("🎲 Симулятор планирования")
    
    col1, col2 = st.columns(2)
    
    with col1:
        planned_weekly_tss = st.slider(
            "Планируемый недельный TSS:",
            min_value=0,
            max_value=1000,
            value=int((current_metrics['ctl'] if 'ctl' in current_metrics else 50) * 7),
            step=50,
            help="Планируемая тренировочная нагрузка на неделю"
        )
    
    with col2:
        simulation_weeks = st.slider(
            "Период симуляции (недели):",
            min_value=1,
            max_value=12,
            value=4,
            step=1
        )
    
    # Симуляция будущих значений
    if st.button("🚀 Показать прогноз"):
        future_dates, future_ctl, future_atl, future_tsb = banister.simulate_training_load(
            current_metrics, planned_weekly_tss, simulation_weeks
        )
        
        if future_dates:
            # Создаём график прогноза
            fig_future = Visualizations.create_banister_chart(
                future_dates, future_ctl, future_atl, future_tsb
            )
            fig_future.update_layout(title="Прогноз при планируемой нагрузке")
            st.plotly_chart(fig_future, use_container_width=True)
            
            # Анализ прогноза
            final_tsb = future_tsb[-1]
            if final_tsb > 5:
                forecast_message = "🟢 Отличный прогноз! Вы будете в пиковой форме."
            elif final_tsb > -10:
                forecast_message = "🟡 Хорошая нагрузка для поддержания формы."
            elif final_tsb > -30:
                forecast_message = "🟠 Внимание: возможно накопление усталости."
            else:
                forecast_message = "🔴 Предупреждение: высокий риск переутомления!"
            
            st.info(f"**Прогноз через {simulation_weeks} недель:** TSB = {final_tsb:.1f} - {forecast_message}")

    # Планирование от цели
    st.subheader("🎯 План под цель (дата старта)")

    from models.training_planner import (
        goal_target_weekly_tss,
        create_weekly_tss_plan,
        compute_phase_schedule,
        expand_weekly_to_daily_triathlon,
        flatten_daily_total,
        weeks_until,
    )

    colg1, colg2, colg3 = st.columns(3)
    with colg1:
        goal_type = st.selectbox(
            "Тип цели:",
            ["Триатлон", "Бег", "Вело"],
            index=0,
        )
        if goal_type == "Триатлон":
            distance_options = ["Спринт", "Олимпийка", "Half (70.3)", "Ironman"]
            default_index = 1
        elif goal_type == "Бег":
            distance_options = ["5 км", "10 км", "Полумарафон", "Марафон", "Ультра"]
            default_index = 2
        else:  # Вело
            distance_options = ["40 км TT", "100 км", "100 миль", "200 км (бревет)", "Этапная гонка"]
            default_index = 1
        distance = st.selectbox("Дистанция:", distance_options, index=default_index)
    with colg2:
        goal_date = st.date_input(
            "Дата старта:",
            value=datetime.now().date() + timedelta(weeks=8),
        )
        weeks_to_race = weeks_until(goal_date)
        st.caption(f"До старта: ~{weeks_to_race} нед.")
    with colg3:
        start_weekly_tss_guess = int((current_metrics.get('ctl', 50)) * 7)
        from models.training_planner import suggest_target_weekly_tss
        auto = suggest_target_weekly_tss(goal_type, distance, activities_df)
        t_min, t_max = goal_target_weekly_tss(goal_type, distance)
        st.caption(f"Автонастройка: последняя неделя {auto['last_week']}, среднее 4н {auto['avg_4']}, лучшая 8н {auto['best_8']}")
        target_weekly_tss = st.slider(
            "Целевой недельный TSS к пику:",
            min_value=max(100, t_min),
            max_value=max(300, t_max),
            value=int(auto['suggested'] or int((t_min + t_max) / 2)),
            step=25,
            help="Ориентир под дистанцию; можно скорректировать",
        )

    # Настройки распределения
    with st.expander("⚙️ Настроить распределение (фазы, проценты, дни)", expanded=False):
        import json
        phases_all = ['Base', 'Build', 'Peak', 'Taper']
        # Инициализация в session_state
        if 'planner_mix' not in state:
            state.planner_mix = {}
        if 'planner_weights' not in state:
            state.planner_weights = {}
        # Сброс пресетов и значений слайдеров при смене типа цели
        prev_goal = state.planner_goal_type
        if prev_goal != goal_type:
            state.planner_goal_type = goal_type
            state.planner_mix = {}
            state.planner_weights = {}
            # Сбрасываем значения слайдеров и инпутов дней, чтобы дефолты применились визуально
            for ph in phases_all:
                for key in (f"mix_bike_{ph}", f"mix_run_{ph}", f"mix_swim_{ph}"):
                    state.pop(key, None)
                for i in range(7):
                    for key in (f"w_run_{ph}_{i}", f"w_bike_{ph}_{i}", f"w_swim_{ph}_{i}"):
                        state.pop(key, None)

        tabs = st.tabs(phases_all)
        from models.training_planner import triathlon_weekly_mix, daily_weights_for_phase
        for phase, tab in zip(phases_all, tabs):
            with tab:
                st.caption("Проценты TSS по видам спорта (нормализуются автоматически)")
                # Текущие значения или дефолт
                if goal_type == "Бег":
                    default_mix = {'run': 1.0, 'bike': 0.0, 'swim': 0.0}
                elif goal_type == "Вело":
                    default_mix = {'run': 0.0, 'bike': 1.0, 'swim': 0.0}
                else:
                    default_mix = triathlon_weekly_mix(distance, phase)
                stored_mix = state.planner_mix.get(phase, default_mix)
                bike = st.slider(f"{phase} • Bike %", 0, 100, int(round(stored_mix.get('bike', default_mix['bike']) * 100)), key=f"mix_bike_{phase}")
                run = st.slider(f"{phase} • Run %", 0, 100, int(round(stored_mix.get('run', default_mix['run']) * 100)), key=f"mix_run_{phase}")
                swim = st.slider(f"{phase} • Swim %", 0, 100, int(round(stored_mix.get('swim', default_mix['swim']) * 100)), key=f"mix_swim_{phase}")
                total = bike + run + swim
                if total == 0:
                    # Если пользователь выставил все нули — вернёмся к дефолту цели
                    mix_norm = default_mix
                else:
                    mix_norm = {'bike': bike/total, 'run': run/total, 'swim': swim/total}
                state.planner_mix[phase] = mix_norm
                st.caption(f"Сумма: {bike+run+swim}% → будет нормализовано до 100%")

                st.divider()
                st.caption("Дневные веса (Пн..Вс) для каждого вида спорта. Значения нормализуются к 100% на неделю.")
                default_w = daily_weights_for_phase(phase)
                stored_w = state.planner_weights.get(phase, default_w)
                days = ['Пн','Вт','Ср','Чт','Пт','Сб','Вс']
                cols_run = st.columns(7)
                run_vals = []
                for i, c in enumerate(cols_run):
                    with c:
                        val = c.number_input(f"Run {days[i]}", min_value=0.0, max_value=1.0, step=0.05,
                                             value=float(stored_w.get('run', default_w['run'])[i]), key=f"w_run_{phase}_{i}")
                        run_vals.append(val)
                cols_bike = st.columns(7)
                bike_vals = []
                for i, c in enumerate(cols_bike):
                    with c:
                        val = c.number_input(f"Bike {days[i]}", min_value=0.0, max_value=1.0, step=0.05,
                                             value=float(stored_w.get('bike', default_w['bike'])[i]), key=f"w_bike_{phase}_{i}")
                        bike_vals.append(val)
                cols_swim = st.columns(7)
                swim_vals = []
                for i, c in enumerate(cols_swim):
                    with c:
                        val = c.number_input(f"Swim {days[i]}", min_value=0.0, max_value=1.0, step=0.05,
                                             value=float(stored_w.get('swim', default_w['swim'])[i]), key=f"w_swim_{phase}_{i}")
                        swim_vals.append(val)
                state.planner_weights[phase] = {'run': run_vals, 'bike': bike_vals, 'swim': swim_vals}

    if st.button("🧭 Построить план до старта"):
        weekly_tss_plan = create_weekly_tss_plan(
            start_weekly_tss=start_weekly_tss_guess,
            weeks_total=weeks_to_race,
            target_weekly_tss=target_weekly_tss,
            deload_every=4,
            taper_weeks=2,
            max_ramp=0.10,
        )

        # Старт с ближайшего понедельника
        today = datetime.now().date()
        start_week = today - timedelta(days=today.weekday())
        phases = compute_phase_schedule(weeks_to_race)
        mix_overrides = state.planner_mix or None
        # Для целей Бег/Вело по умолчанию зададим соответствующий микс (если пользователь не задал свой)
        if not mix_overrides:
            if goal_type == "Бег":
                mix_overrides = {ph: {'run': 1.0, 'bike': 0.0, 'swim': 0.0} for ph in phases}
            elif goal_type == "Вело":
                mix_overrides = {ph: {'run': 0.0, 'bike': 1.0, 'swim': 0.0} for ph in phases}
        weights_overrides = state.planner_weights or None
        daily_plan, weekly_summary = expand_weekly_to_daily_triathlon(
            weekly_tss_plan, phases, distance, start_week,
            mix_overrides=mix_overrides, weights_overrides=weights_overrides
        )
        daily_seq = flatten_daily_total(daily_plan)

        # Кешируем план, чтобы не терялся при экспорте
        state.goal_plan = {
            'goal_type': goal_type,
            'distance': distance,
            'weeks_to_race': weeks_to_race,
            'start_week': start_week,
            'weekly_tss_plan': weekly_tss_plan,
            'phases': phases,
            'daily_plan': daily_plan,
            'weekly_summary': weekly_summary,
        }
        state._just_built_plan = True

        # Прогноз по переменной нагрузке
        future_dates, future_ctl, future_atl, future_tsb = banister.simulate_variable_load(
            current_metrics, daily_seq, start_date=datetime.combine(start_week, datetime.min.time())
        )

        fig_future = Visualizations.create_banister_chart(
            future_dates, future_ctl, future_atl, future_tsb
        )
        fig_future.update_layout(title=f"Прогноз до старта ({goal_type} • {distance})")
        st.plotly_chart(fig_future, use_container_width=True)

        # Сводка по неделям с фазами и разбивкой по видам спорта
        df_plan = pd.DataFrame(weekly_summary)
        df_plan['Неделя от'] = df_plan['week_start'].apply(lambda d: d.strftime('%d.%m'))
        df_plan = df_plan[['Неделя от', 'phase', 'weekly_tss', 'bike', 'run', 'swim']]
        df_plan.rename(columns={'phase': 'Фаза', 'weekly_tss': 'Weekly TSS', 'bike': 'Bike', 'run': 'Run', 'swim': 'Swim'}, inplace=True)
        st.dataframe(df_plan, use_container_width=True, hide_index=True)

        # Экспорт CSV/ICS
        # Weekly CSV
        csv_weekly = df_plan.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="💾 Экспорт недельного плана (CSV)",
            data=csv_weekly,
            file_name="weekly_plan.csv",
            mime="text/csv",
        )

        # Daily CSV
        daily_rows = []
        for dt, total, parts in daily_plan:
            daily_rows.append({
                'date': dt.strftime('%Y-%m-%d'),
                'total_tss': total,
                'run_tss': parts.get('run', 0.0),
                'bike_tss': parts.get('bike', 0.0),
                'swim_tss': parts.get('swim', 0.0),
            })
        df_daily = pd.DataFrame(daily_rows)
        csv_daily = df_daily.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="💾 Экспорт дневного плана (CSV)",
            data=csv_daily,
            file_name="daily_plan.csv",
            mime="text/csv",
        )

        # ICS Calendar
        from models.training_planner import create_ics_from_daily
        ics_content = create_ics_from_daily(daily_plan, title_prefix=f"{goal_type} {distance}")
        st.download_button(
            label="📅 Экспорт в календарь (ICS)",
            data=ics_content,
            file_name="training_plan.ics",
            mime="text/calendar",
        )

        # После построения плана сделаем перерисовку, чтобы показать стабильный UI из кеша
        st.rerun()
    
    # Отрисовка плана из кеша, чтобы экспорт не сбрасывал страницу
    # Показываем сразу при наличии goal_plan (после st.rerun() из кнопки)
    if state.goal_plan:
        # Очистим флаг, если он остался
        state.pop('_just_built_plan', None)
        gp = state.goal_plan
        daily_plan = gp['daily_plan']
        weekly_summary = gp['weekly_summary']
        start_week = gp['start_week']
        goal_type_cached = gp.get('goal_type', goal_type)
        distance_cached = gp.get('distance', distance)

        future_dates, future_ctl, future_atl, future_tsb = banister.simulate_variable_load(
            current_metrics, flatten_daily_total(daily_plan), start_date=datetime.combine(start_week, datetime.min.time())
        )
        fig_future = Visualizations.create_banister_chart(
            future_dates, future_ctl, future_atl, future_tsb
        )
        fig_future.update_layout(title=f"Прогноз до старта ({goal_type_cached} • {distance_cached})")
        st.plotly_chart(fig_future, use_container_width=True)

        df_plan = pd.DataFrame(weekly_summary)
        df_plan['Неделя от'] = df_plan['week_start'].apply(lambda d: d.strftime('%d.%m'))
        df_plan = df_plan[['Неделя от', 'phase', 'weekly_tss', 'bike', 'run', 'swim']]
        df_plan.rename(columns={'phase': 'Фаза', 'weekly_tss': 'Weekly TSS', 'bike': 'Bike', 'run': 'Run', 'swim': 'Swim'}, inplace=True)
        st.dataframe(df_plan, use_container_width=True, hide_index=True)

        csv_weekly = df_plan.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="💾 Экспорт недельного плана (CSV)",
            data=csv_weekly,
            file_name="weekly_plan.csv",
            mime="text/csv",
        )

        daily_rows = []
        for dt, total, parts in daily_plan:
            daily_rows.append({
                'date': dt.strftime('%Y-%m-%d'),
                'total_tss': total,
                'run_tss': parts.get('run', 0.0),
                'bike_tss': parts.get('bike', 0.0),
                'swim_tss': parts.get('swim', 0.0),
            })
        df_daily = pd.DataFrame(daily_rows)
        csv_daily = df_daily.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="💾 Экспорт дневного плана (CSV)",
            data=csv_daily,
            file_name="daily_plan.csv",
            mime="text/csv",
        )

        from models.training_planner import create_ics_from_daily
        ics_content = create_ics_from_daily(daily_plan, title_prefix=f"{goal_type_cached} {distance_cached}")
        st.download_button(
            label="📅 Экспорт в календарь (ICS)",
            data=ics_content,
            file_name="training_plan.ics",
            mime="text/calendar",
        )

        # Экспорт тренировки (FIT-CSV / FIT / TCX) для выбранного дня
        st.markdown("### 🧩 Экспорт тренировки (FIT-CSV / FIT / TCX)")
        day_idx = st.number_input("День недели (1=Пн … 7=Вс)", min_value=1, max_value=7, value=1, key="fit_day")
        if st.button("⬇️ Экспортировать выбранный день в FIT-CSV / FIT", key="export_fit_day"):
            from models.fit_export import build_steps_for_sport, generate_fit_csv, try_convert_fit_verbose
            from models.tcx_export import generate_tcx_workout
            from models.tcx_activity_export import generate_tcx_activity
            from config.settings import Settings

            day = daily_plan[day_idx - 1]
            dt, total, parts = day
            # Определяем вид спорта дня по максимальной доле
            sport = 'run'
            if parts.get('bike', 0) >= max(parts.get('run', 0), parts.get('swim', 0)):
                sport = 'bike'
            elif parts.get('swim', 0) >= max(parts.get('run', 0), parts.get('bike', 0)):
                sport = 'swim'
            steps = build_steps_for_sport(total, sport)
            workout_name = f"{goal_type_cached} {distance_cached} — {dt.strftime('%Y-%m-%d')}"
            csv_text = generate_fit_csv(workout_name, sport, steps, created=dt)
            csv_bytes = csv_text.encode('utf-8')

            colf1, colf2, colf3, colf4 = st.columns(4)
            with colf1:
                st.download_button(
                    label="💾 Скачать FIT-CSV",
                    data=csv_bytes,
                    file_name=f"workout_{dt.strftime('%Y%m%d')}.csv",
                    mime="text/csv",
                )
            with colf2:
                jar = Settings.FIT_SDK_JAR
                fit_bytes, out_s, err_s, rc = try_convert_fit_verbose(csv_bytes, 'java', jar) if jar else (None, '', 'FIT_SDK_JAR не задан', 127)
                if fit_bytes and rc == 0:
                    st.download_button(
                        label="💾 Скачать FIT",
                        data=fit_bytes,
                        file_name=f"workout_{dt.strftime('%Y%m%d')}.fit",
                        mime="application/octet-stream",
                    )
                else:
                    if rc != 0:
                        st.warning("FIT не собран. Логи FitCSVTool:")
                        if out_s:
                            st.code(out_s)
                        if err_s:
                            st.code(err_s)
                    else:
                        st.info("Чтобы собрать .FIT внутри приложения, укажите путь к FitCSVTool.jar в переменной окружения FIT_SDK_JAR.")
            with colf3:
                # Генерация TCX как альтернатива для импорта в Garmin Connect
                tcx_text = generate_tcx_workout(workout_name, sport, steps, created=dt)
                st.download_button(
                    label="💾 Скачать TCX",
                    data=tcx_text.encode('utf-8'),
                    file_name=f"workout_{dt.strftime('%Y%m%d')}.tcx",
                    mime="application/vnd.garmin.tcx+xml",
                )
            with colf4:
                # TCX Activity — для импорта в разделе "Импорт данных" (активности)
                tcx_act = generate_tcx_activity(workout_name, sport, steps, start_time=datetime.combine(dt.date(), datetime.min.time()))
                st.download_button(
                    label="💾 TCX Activity (импорт)",
                    data=tcx_act.encode('utf-8'),
                    file_name=f"activity_{dt.strftime('%Y%m%d')}.tcx",
                    mime="application/vnd.garmin.tcx+xml",
                    help="Используйте этот файл на странице Импорт данных в Garmin Connect",
                )

        with st.expander("📦 Экспорт всей недели (ZIP)", expanded=False):
            # Выбор недели относительно start_week из goal_plan
            total_days = len(daily_plan)
            total_weeks = max(1, (total_days + 6) // 7)
            week_idx = st.number_input("Номер недели (1=первая)", min_value=1, max_value=total_weeks, value=1, key="fit_week_idx")
            if st.button("⬇️ Собрать ZIP с FIT-CSV/FIT/TCX", key="export_fit_week_zip"):
                import io, zipfile
                from models.fit_export import build_steps_for_sport, generate_fit_csv, try_convert_fit_verbose
                from models.tcx_export import generate_tcx_workout
                from config.settings import Settings
                jar = Settings.FIT_SDK_JAR

                start = (week_idx - 1) * 7
                end = min(start + 7, total_days)
                week_days = daily_plan[start:end]

                csv_zip = io.BytesIO()
                tcx_zip = io.BytesIO()
                with zipfile.ZipFile(csv_zip, 'w', zipfile.ZIP_DEFLATED) as zc, \
                     zipfile.ZipFile(tcx_zip, 'w', zipfile.ZIP_DEFLATED) as zt:
                    for dt, total, parts in week_days:
                        # Определяем вид спорта по максимальной доле
                        sport = 'run'
                        if parts.get('bike', 0) >= max(parts.get('run', 0), parts.get('swim', 0)):
                            sport = 'bike'
                        elif parts.get('swim', 0) >= max(parts.get('run', 0), parts.get('bike', 0)):
                            sport = 'swim'
                        steps = build_steps_for_sport(total, sport)
                        csv_text = generate_fit_csv(f"{goal_type_cached} {distance_cached} — {dt.strftime('%Y-%m-%d')}", sport, steps, created=dt)
                        zc.writestr(f"workout_{dt.strftime('%Y%m%d')}.csv", csv_text)
                        tcx_text = generate_tcx_workout(f"{goal_type_cached} {distance_cached} — {dt.strftime('%Y-%m-%d')}", sport, steps, created=dt)
                        zt.writestr(f"workout_{dt.strftime('%Y%m%d')}.tcx", tcx_text)
                st.download_button(
                    label="💾 Скачать все FIT-CSV (ZIP)",
                    data=csv_zip.getvalue(),
                    file_name=f"week_{week_idx:02d}_fitcsv.zip",
                    mime="application/zip",
                    key="dl_fitcsv_week_zip",
                )
                st.download_button(
                    label="💾 Скачать все TCX (ZIP)",
                    data=tcx_zip.getvalue(),
                    file_name=f"week_{week_idx:02d}_tcx.zip",
                    mime="application/zip",
                    key="dl_tcx_week_zip",
                )

                if jar:
                    fit_zip = io.BytesIO()
                    failed_days = 0
                    with zipfile.ZipFile(fit_zip, 'w', zipfile.ZIP_DEFLATED) as zf:
                        for dt, total, parts in week_days:
                            sport = 'run'
                            if parts.get('bike', 0) >= max(parts.get('run', 0), parts.get('swim', 0)):
                                sport = 'bike'
                            elif parts.get('swim', 0) >= max(parts.get('run', 0), parts.get('bike', 0)):
                                sport = 'swim'
                            steps = build_steps_for_sport(total, sport)
                            csv_text = generate_fit_csv(f"{goal_type_cached} {distance_cached} — {dt.strftime('%Y-%m-%d')}", sport, steps, created=dt)
                            fit_bytes, _, _, rc = try_convert_fit_verbose(csv_text.encode('utf-8'), 'java', jar)
                            if fit_bytes and rc == 0:
                                zf.writestr(f"workout_{dt.strftime('%Y%m%d')}.fit", fit_bytes)
                            else:
                                failed_days += 1
                    if fit_zip.getbuffer().nbytes > 0:
                        st.download_button(
                            label="💾 Скачать все FIT (ZIP)",
                            data=fit_zip.getvalue(),
                            file_name=f"week_{week_idx:02d}_fit.zip",
                            mime="application/zip",
                            key="dl_fit_week_zip",
                        )
                    if failed_days:
                        st.info(f"Не удалось собрать FIT для {failed_days} дн. Проверьте FIT_SDK_JAR/Java или структуру CSV.")

        # Кнопка сброса плана
        if st.button("♻️ Сбросить план"):
            state.reset_planner_overrides()
            st.success("План сброшен")
            st.rerun()

    # Дополнительная статистика
    st.subheader("📈 Дополнительная статистика")
    
    col1, col2 = st.columns(2)
    
    with col1:
        # График распределения TSS
        if not activities_df.empty and 'tss' in activities_df.columns:
            fig_tss_dist = Visualizations.create_tss_distribution_chart(activities_df)
            st.plotly_chart(fig_tss_dist, use_container_width=True)
    
    with col2:
        # Недельная статистика TSS
        if not activities_df.empty:
            fig_weekly = Visualizations.create_weekly_tss_chart(activities_df)
            st.plotly_chart(fig_weekly, use_container_width=True)

if __name__ == "__main__":
    main()
