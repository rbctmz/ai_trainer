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

# Карты отображения статусов тренированности и ACWR
TRAINING_STATUS_TITLES = {
    "PRODUCTIVE": "Продуктивно",
    "UNPRODUCTIVE": "Непродуктивно",
    "RECOVERY": "Восстановление",
    "MAINTAINING": "Поддержание",
    "DETRAINING": "Потеря формы",
    "PEAK": "Пик",
    "BASE": "База",
    "BUILD": "Билд",
    "OVERREACHING": "Перегрузка",
    "IMPROVING": "Улучшение",
}

TRAINING_STATUS_COLORS = {
    "PRODUCTIVE": "#10B981",
    "MAINTAINING": "#3B82F6",
    "BASE": "#6366F1",
    "BUILD": "#F59E0B",
    "PEAK": "#8B5CF6",
    "RECOVERY": "#22D3EE",
    "OVERREACHING": "#F97316",
    "UNPRODUCTIVE": "#EF4444",
    "DETRAINING": "#F97316",
}

ACWR_STATUS_STYLES = {
    "OPTIMAL": {"label": "Оптимально", "color": "#10B981"},
    "BALANCED": {"label": "Баланс", "color": "#10B981"},
    "LOW": {"label": "Ниже нормы", "color": "#F59E0B"},
    "VERY_LOW": {"label": "Сильно ниже нормы", "color": "#F97316"},
    "HIGH": {"label": "Выше нормы", "color": "#F97316"},
    "VERY_HIGH": {"label": "Сильно выше нормы", "color": "#EF4444"},
}

# Импорты наших модулей
from data.data_processor import ActivityProcessor
from models.banister import BanisterModel
from utils.visualizations import Visualizations
from config.settings import Settings
from state import StateManager, get_state_manager
from ui.theme import apply_theme, create_dark_table_html, get_plotly_theme
from ui.navigation import (
    render_primary_navigation,
    render_sidebar_navigation,
    render_sidebar_utilities,
)
from services import garmin as garmin_service
from services.data_cache import (
    clear_data_caches,
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


def calculate_current_status():
    """Расчет текущего статуса с приоритизацией проблем"""

    state = get_state_manager()

    activities_df = load_activities(30)
    hrv_df = load_hrv(90)
    sleep_df = load_sleep(7)

    status = {
        "critical_status": None,
        "critical_action": None,
        "recommendations": [],
        "tsb": 0,
        "hrv": 0,
        "readiness": 0,
        "ctl": 0,
        "trends": {},
    }

    if not activities_df.empty:
        from models.banister import BanisterModel

        banister = BanisterModel()
        tss_data = []
        dates = []

        for _, row in activities_df.iterrows():
            tss_val = row.get("tss")
            if pd.isna(tss_val):
                tss_val = 0
            tss_data.append(float(tss_val or 0))
            dates.append(row["date"])

        current_metrics = banister.get_current_metrics(tss_data, dates)
        status["tsb"] = current_metrics.get("tsb", 0)
        status["ctl"] = current_metrics.get("ctl", 0)

        if status["tsb"] < -30:
            status["critical_status"] = "Критическое переутомление"
            status["critical_action"] = "Полный отдых 2-3 дня без тренировок"
            status["recommendations"].extend(
                [
                    {
                        "title": "🚨 Немедленный отдых",
                        "description": "TSB критически низкий (-30+). Организм в состоянии переутомления.",
                        "priority": "high",
                    },
                    {
                        "title": "😴 Качество сна",
                        "description": "Увеличьте сон до 8-9 часов, соблюдайте режим.",
                        "priority": "high",
                    },
                    {
                        "title": "💧 Восстановление",
                        "description": "Массаж, баня, легкие прогулки. Никаких интенсивных нагрузок.",
                        "priority": "medium",
                    },
                ]
            )
        elif status["tsb"] < -20:
            status["critical_status"] = "Сильная усталость"
            status["critical_action"] = "Только легкие восстановительные тренировки в Зоне 1"
            status["recommendations"].extend(
                [
                    {
                        "title": "🔄 Активное восстановление",
                        "description": "TSB -20 до -30. Только тренировки в аэробной зоне 1.",
                        "priority": "high",
                    },
                    {
                        "title": "🍎 Питание",
                        "description": "Увеличьте потребление белка и углеводов для восстановления.",
                        "priority": "medium",
                    },
                ]
            )
        elif status["tsb"] > 5:
            status["recommendations"].extend(
                [
                    {
                        "title": "🚀 Пиковая форма!",
                        "description": "TSB выше +5. Отличное время для соревнований или тестов.",
                        "priority": "low",
                    },
                    {
                        "title": "🎯 Интенсивные тренировки",
                        "description": "Можно проводить FTP-тесты, интервалы, темповые работы.",
                        "priority": "low",
                    },
                ]
            )
        else:
            status["recommendations"].append(
                {
                    "title": "💪 Стандартный режим",
                    "description": "TSB в норме. Поддерживайте текущий объем тренировок.",
                    "priority": "low",
                }
            )

    if not hrv_df.empty:
        latest_hrv = hrv_df.iloc[0]["rmssd"] if pd.notna(hrv_df.iloc[0]["rmssd"]) else 0
        baseline_hrv = hrv_df["rmssd"].mean()
        status["hrv"] = latest_hrv

        try:
            from models.hrv_analyzer import HRVAnalyzer

            advanced_score, info = HRVAnalyzer.recovery_score_advanced(hrv_df)
            if advanced_score is not None:
                status["hrv_advanced"] = {"score": advanced_score, "info": info}
        except Exception:
            pass

        if len(hrv_df) >= 3:
            recent_trend = hrv_df.head(3)["rmssd"].ffill().pct_change().mean() * 100
            status["trends"]["hrv"] = recent_trend

        if latest_hrv < baseline_hrv * 0.8 and status["critical_status"] is None:
            status["critical_status"] = "Низкий HRV - стресс или недовосстановление"
            status["critical_action"] = "Проверьте качество сна и уровень стресса"
            status["recommendations"].append(
                {
                    "title": "💓 Низкий HRV",
                    "description": f"HRV ({latest_hrv:.1f}) ниже базового ({baseline_hrv:.1f}) на 20%+",
                    "priority": "medium",
                }
            )

        if latest_hrv < 30:
            status["recommendations"].append(
                {
                    "title": "⚠️ HRV требует внимания",
                    "description": "Низкая вариабельность сердечного ритма. Фокус на восстановлении.",
                    "priority": "medium",
                }
            )
        elif latest_hrv > 50:
            status["recommendations"].append(
                {
                    "title": "✨ Отличный HRV",
                    "description": "Высокая вариабельность - организм готов к нагрузкам.",
                    "priority": "low",
                }
            )

    if not sleep_df.empty or not hrv_df.empty:
        try:
            from data.data_processor_phase1 import Phase1DataProcessor

            latest_sleep = {}
            latest_hrv_entry = {}
            if not sleep_df.empty:
                latest_sleep = sleep_df.sort_values("date", ascending=False).iloc[0].to_dict()
            if not hrv_df.empty:
                latest_hrv_entry = hrv_df.sort_values("date", ascending=False).iloc[0].to_dict()

            readiness_data = Phase1DataProcessor.calculate_comprehensive_readiness(
                latest_sleep,
                latest_hrv_entry,
                {},
                {},
            )

            if readiness_data and "readiness_score" in readiness_data:
                status["readiness"] = readiness_data["readiness_score"]
        except Exception:
            if status["hrv"] > 40 and status["tsb"] > -10:
                status["readiness"] = 80
            elif status["hrv"] > 30 and status["tsb"] > -20:
                status["readiness"] = 60
            else:
                status["readiness"] = 40

    logger.debug("Текущий статус: %s", status)
    return status


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

    show_garmin_connection(state)

    if state.garmin_client.is_authenticated:
        page = render_primary_navigation(state)
        sidebar_page = render_sidebar_navigation(state, page)
        if sidebar_page != page:
            page = sidebar_page

        render_sidebar_utilities(state)

        st.sidebar.markdown("---")

        _ = state.chat_manager  # Ensure chat manager initialised
        show_chat_management()

        st.sidebar.markdown("---")

        with st.sidebar.expander("🧪 Разработка", expanded=False):
            st.caption("Тестовые функции для демонстрации")
            add_test_phase1_data()

        if page == "📊 Дашборд":
            show_dashboard()
        elif page == "🏃‍♂️ Активности":
            show_activities()
        elif page == "💓 Анализ HRV":
            show_hrv_analysis()
        elif page == "😴 Анализ сна":
            show_sleep_analysis()
        elif page == "📈 Планирование":
            show_planning()
        elif page == "🤖 AI Коучинг":
            show_ai_coaching()
        elif page == "📋 Логи синхронизации":
            show_sync_logs()
        elif page == "⚙️ Управление данными":
            show_data_management()
    else:
        show_welcome_screen()


def show_garmin_connection(state: StateManager):
    """Блок подключения к Garmin Connect"""
    client = state.garmin_client
    with st.sidebar.expander("🔗 Garmin Connect", expanded=not client.is_authenticated):
        if not client.is_authenticated:
            st.write("Подключитесь для синхронизации данных:")

            email = st.text_input("Email Garmin", value=Settings.GARMIN_EMAIL or "")
            password = st.text_input("Пароль Garmin", type="password", value=Settings.GARMIN_PASSWORD or "")

            col1, col2 = st.columns(2)

            with col1:
                if st.button("🔐 Подключиться"):
                    if email and password:
                        with st.spinner("Подключение к Garmin Connect..."):
                            if garmin_service.authenticate(state, email, password):
                                st.success("✅ Успешно подключено!")
                                st.rerun()
                            else:
                                error = getattr(client, 'auth_error', 'Неизвестно')
                                st.error(f"❌ Ошибка подключения: {error}")
                    else:
                        st.warning("Введите email и пароль")
        else:
            st.success("✅ Подключено к Garmin Connect")

            connection_info = garmin_service.connection_info(state)
            if connection_info.get('using_garth'):
                st.info("🚀 Используется garth (улучшенный API)")
            else:
                st.info("📡 Используется garminconnect")

            profile = garmin_service.user_profile(state)
            if profile is not None:
                render_garmin_profile(profile)

            if connection_info.get('garth_available') and connection_info.get('using_garth'):
                if st.button("🔍 Тест garth", help="Проверить расширенные возможности garth"):
                    with st.spinner("Тестирование garth..."):
                        test_results = client.test_garth_connection()
                        if test_results.get('authenticated'):
                            st.success("✅ Garth работает корректно")
                            with st.expander("📋 Детали garth тестирования"):
                                for method, status in test_results.get('test_results', {}).items():
                                    st.write(f"• **{method}**: {status}")
                        else:
                            st.warning(f"⚠️ Проблема с garth: {test_results.get('error', 'Неизвестно')}")

            if st.button("🔌 Отключиться"):
                garmin_service.disconnect(state)
                st.rerun()


def sync_data(days=30, state=None):
    """Синхронизация данных с Garmin Connect"""
    state = state or get_state_manager()
    client = state.garmin_client
    database = state.database

    if not client.is_authenticated:
        st.error("Не подключен к Garmin Connect")
        return
    
    # Улучшенный прогресс с контейнером
    progress_container = st.container()
    with progress_container:
        st.info("🔄 Начинаем синхронизацию...")
        progress_bar = st.progress(0, text="Подготовка...")
        status_text = st.empty()
        
        # Счетчики для отображения прогресса
        sync_stats = st.empty()
    
    try:
        # Получение активностей
        status_text.text(f"📊 Загрузка активностей за {days} дней...")
        progress_bar.progress(10, text="Шаг 1/5: Получение активностей...")
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        activities = client.get_activities(start_date, end_date)
        activities_synced = False
        
        progress_bar.progress(30, text="Шаг 2/5: Обработка активностей...")
        
        if activities:
            status_text.text(f"⚙️ Обработка {len(activities)} активностей...")
            sync_stats.info(f"Найдено активностей: {len(activities)}")
            # Обработка и сохранение данных
            df = ActivityProcessor.process_activities(activities)
            
            # Расчёт TSS для активностей - оптимизированно
            status_text.text("📈 Расчёт Training Stress Score...")
            progress_bar.progress(50, text="Шаг 3/5: Расчет метрик...")
            
            tss_values = []
            for idx, row in df.iterrows():
                activity_dict = row.to_dict()
                tss = ActivityProcessor.calculate_tss(activity_dict, 
                                                    ftp=Settings.USER_FTP, 
                                                    lthr=Settings.USER_LTHR)
                tss_values.append(tss)
            
            df['tss'] = tss_values
            
            # Конвертируем DataFrame в список словарей для умной синхронизации
            activities_list = df.to_dict('records')
            sync_result = database.sync_activities(activities_list)
            activities_synced = True
        else:
            sync_result = {'new': 0, 'updated': 0, 'skipped': 0}
            
        progress_bar.progress(70, text="Шаг 4/5: Загрузка HRV...")
        
        # Синхронизация HRV данных - оптимизированно батчами
        status_text.text("💓 Загрузка HRV и данных восстановления...")
        hrv_data = {}
        
        # Создаём список дат для пакетной обработки
        date_list = []
        current_date = start_date
        while current_date <= end_date:
            date_list.append(current_date)
            current_date += timedelta(days=1)
        
        # Обрабатываем по 5 дней за раз для ускорения
        batch_size = 5
        total_batches = len(date_list) // batch_size + (1 if len(date_list) % batch_size else 0)
        
        for batch_idx in range(0, len(date_list), batch_size):
            batch_dates = date_list[batch_idx:batch_idx + batch_size]
            
            for date in batch_dates:
                date_str = format_date(date, 'db')
                
                # Получаем HRV данные
                hrv_day_data = client.get_hrv_data(date)
                rmssd_value = None
                
                # Debug вывод
                logger.debug(f"DEBUG HRV: Получены данные HRV для {date_str}: {type(hrv_day_data)}")
                if hrv_day_data:
                    logger.debug(f"DEBUG HRV: Структура данных: {hrv_day_data}")
                
                if isinstance(hrv_day_data, dict):
                    # Новый garth_client может возвращать {'hrvSummary': {'rmssd': ...}}
                    if 'hrvSummary' in hrv_day_data and isinstance(hrv_day_data['hrvSummary'], dict):
                        hrv_summary = hrv_day_data['hrvSummary']
                        rmssd_value = hrv_summary.get('rmssd') or hrv_summary.get('lastNightAvg')
                        logger.debug(f"DEBUG HRV: Извлечено RMSSD из hrvSummary: {rmssd_value}")
                    # Также может возвращать {'daily_rmssd': ...} напрямую
                    elif 'daily_rmssd' in hrv_day_data:
                        rmssd_value = hrv_day_data['daily_rmssd']
                        logger.debug(f"DEBUG HRV: Извлечено RMSSD из daily_rmssd: {rmssd_value}")
                    elif 'rmssd' in hrv_day_data:
                        rmssd_value = hrv_day_data['rmssd']
                        logger.debug(f"DEBUG HRV: Извлечено RMSSD напрямую: {rmssd_value}")

                # Получаем данные о стрессе
                stress_score = None
                stress_data = client.get_stress_data(date)
                logger.debug(f"DEBUG STRESS SYNC: Получены данные стресса для {date_str}: {type(stress_data)}")
                if stress_data:
                    logger.debug(f"DEBUG STRESS SYNC: Структура данных стресса: {stress_data}")
                
                if isinstance(stress_data, dict):
                    stress_score = stress_data.get('avgStressLevel') or stress_data.get('overallStressLevel')
                    logger.debug(f"DEBUG STRESS SYNC: Извлечен stress_score из словаря: {stress_score}")
                elif isinstance(stress_data, (int, float)): # Иногда API может вернуть просто число
                    stress_score = stress_data
                    logger.debug(f"DEBUG STRESS SYNC: stress_score - простое число: {stress_score}")
                
                # Получаем данные Body Battery (восстановление)
                recovery_score = None
                body_battery_data = client.get_body_battery_data(date)
                if body_battery_data and isinstance(body_battery_data, list) and len(body_battery_data) > 0:
                    entry = body_battery_data[0]
                    if 'bodyBatteryValuesArray' in entry and entry['bodyBatteryValuesArray']:
                        battery_values = entry['bodyBatteryValuesArray']
                        if battery_values:
                            recovery_score = battery_values[-1][1]
                
                # Сохраняем данные если есть хотя бы один показатель
                if rmssd_value is not None or stress_score is not None or recovery_score is not None:
                    hrv_data[date_str] = {
                        'rmssd': rmssd_value,
                        'stress_score': stress_score,
                        'recovery_score': recovery_score
                    }
                    logger.debug(f"DEBUG HRV: Сохранены данные для {date_str}: {hrv_data[date_str]}")
                    logger.debug(f"DEBUG HRV: RMSSD={rmssd_value}, Stress={stress_score}, Recovery={recovery_score}")
            
            # Обновляем прогресс после каждого батча
            progress = 70 + (batch_idx // batch_size + 1) / total_batches * 10
            progress_bar.progress(min(int(progress), 80))
        
        # =================== НОВЫЕ ДАННЫЕ ФАЗА 1 ===================
        
        # Синхронизация данных сна
        progress_bar.progress(80)
        status_text.text("Загрузка данных сна...")
        
        from data.data_processor_phase1 import Phase1DataProcessor
        
        sleep_data = {}
        daily_health_data = {}
        
        dates_to_process = date_list[:min(len(date_list), days + 1)]
        for date in dates_to_process:  # Обрабатываем последнюю доступную дату включительно
            date_str = format_date(date, 'db')
            
            # Получаем и обрабатываем данные сна
            try:
                sleep_raw = client.get_sleep_data(date)
                logger.debug(f"DEBUG SYNC: Получены данные сна для {date_str}: {type(sleep_raw)}")
                
                if sleep_raw:
                    logger.debug(f"DEBUG SYNC: === ДЕТАЛЬНАЯ СТРУКТУРА ДАННЫХ СНА для {date_str} ===")
                    
                    # Подробное логирование структуры данных
                    if isinstance(sleep_raw, dict):
                        logger.debug(f"DEBUG SYNC: Ключи верхнего уровня: {list(sleep_raw.keys())}")
                        
                        # Проверяем dailySleepDTO
                        if 'dailySleepDTO' in sleep_raw:
                            dto = sleep_raw['dailySleepDTO']
                            logger.debug(f"DEBUG SYNC: dailySleepDTO ключи: {list(dto.keys()) if isinstance(dto, dict) else 'НЕ СЛОВАРЬ'}")
                            if isinstance(dto, dict):
                                logger.debug(f"DEBUG SYNC: sleepTimeSeconds: {dto.get('sleepTimeSeconds', 'НЕТ')}")
                                logger.debug(f"DEBUG SYNC: deepSleepSeconds: {dto.get('deepSleepSeconds', 'НЕТ')}")
                                logger.debug(f"DEBUG SYNC: lightSleepSeconds: {dto.get('lightSleepSeconds', 'НЕТ')}")
                                logger.debug(f"DEBUG SYNC: remSleepSeconds: {dto.get('remSleepSeconds', 'НЕТ')}")
                                logger.debug(f"DEBUG SYNC: awakeCount: {dto.get('awakeCount', 'НЕТ')}")
                        
                        # Проверяем sleepScores
                        if 'sleepScores' in sleep_raw:
                            scores = sleep_raw['sleepScores']
                            logger.debug(f"DEBUG SYNC: sleepScores ключи: {list(scores.keys()) if isinstance(scores, dict) else 'НЕ СЛОВАРЬ'}")
                            if isinstance(scores, dict):
                                if 'deepPercentage' in scores:
                                    logger.debug(f"DEBUG SYNC: deepPercentage: {scores['deepPercentage']}")
                                if 'lightPercentage' in scores:
                                    logger.debug(f"DEBUG SYNC: lightPercentage: {scores['lightPercentage']}")
                                if 'remPercentage' in scores:
                                    logger.debug(f"DEBUG SYNC: remPercentage: {scores['remPercentage']}")
                                if 'overall' in scores:
                                    logger.debug(f"DEBUG SYNC: overall: {scores['overall']}")
                        
                        # Проверяем другие возможные структуры
                        for key in sleep_raw.keys():
                            if key not in ['dailySleepDTO', 'sleepScores']:
                                logger.debug(f"DEBUG SYNC: Дополнительный ключ {key}: {type(sleep_raw[key])}")
                    
                    logger.debug(f"DEBUG SYNC: === ПЕРЕДАЕМ В ПРОЦЕССОР ===")
                    processed_sleep = Phase1DataProcessor.process_sleep_data(sleep_raw)
                    logger.debug(f"DEBUG SYNC: Обработанные данные сна для {date_str}: {processed_sleep}")
                    
                    if processed_sleep:
                        # Используем дату окончания сна (wakeup) если доступна, иначе исходную дату запроса
                        date_key = processed_sleep.get('sleep_date') or date_str
                        sleep_data[date_key] = processed_sleep
                        logger.debug(f"DEBUG SYNC: ✅ Данные сна добавлены для {date_key}")
                        
                        # Проверяем что именно сохранили
                        total = processed_sleep.get('total_sleep_minutes', 0)
                        deep = processed_sleep.get('deep_sleep_minutes', 0)
                        light = processed_sleep.get('light_sleep_minutes', 0)
                        rem = processed_sleep.get('rem_sleep_minutes', 0)
                        score = processed_sleep.get('sleep_score', 0)
                        
                        logger.debug(f"DEBUG SYNC: 📊 Сохраненные значения: total={total}, deep={deep}, light={light}, rem={rem}, score={score}")
                        
                        if deep == 0 and light == 0 and rem == 0:
                            logger.debug(f"DEBUG SYNC: ⚠️ КРИТИЧНО: Все фазы сна равны 0!")
                    else:
                        logger.debug(f"DEBUG SYNC: ❌ Обработка данных сна вернула None для {date_str}")
                else:
                    logger.debug(f"DEBUG SYNC: Нет данных сна для {date_str}")
                    
            except Exception as e:
                logger.debug(f"DEBUG SYNC: ❌ Ошибка обработки данных сна для {date_str}: {e}")
                import traceback
                traceback.print_exc()
                pass  # Данные сна могут быть недоступны
            
            # Получаем и обрабатываем ежедневные показатели здоровья
            try:
                # Общие показатели активности
                daily_summary = client.get_daily_summary(date)
                # Пульс покоя
                resting_hr = client.get_resting_heart_rate(date)
                
                if daily_summary or resting_hr:
                    processed_health = Phase1DataProcessor.process_daily_health_data(
                        daily_summary, resting_hr
                    )
                    if processed_health:
                        daily_health_data[date_str] = processed_health
            except Exception as e:
                pass  # Данные могут быть недоступны
        
        progress_bar.progress(85)
        
        # Получаем текущий статус тренированности (один раз)
        status_text.text("Загрузка статуса тренированности...")
        training_status_data = {}
        
        try:
            # Статус тренированности
            training_status = client.get_training_status()
            # VO2 max
            vo2_data = client.get_vo2_max()
            # Готовность к тренировке
            readiness_data = client.get_training_readiness()
            
            if training_status or vo2_data:
                processed_status = Phase1DataProcessor.process_training_status_data(
                    training_status, vo2_data, readiness_data
                )
                if processed_status:
                    training_status_data[datetime.now().strftime('%Y-%m-%d')] = processed_status
        except Exception as e:
            pass  # Данные могут быть недоступны
        
        progress_bar.progress(90)
        
        # Сохранение всех данных
        status_text.text("Сохранение расширенных данных...")
        progress_bar.progress(95)
        
        hrv_result = {'new': 0, 'updated': 0}
        logger.debug(f"DEBUG HRV SYNC: Сохранение HRV данных в базу: {len(hrv_data)} записей")
        logger.debug(f"DEBUG HRV SYNC: Ключи данных HRV: {list(hrv_data.keys()) if hrv_data else 'Нет данных'}")
        if hrv_data:
            hrv_result = database.sync_hrv_data(hrv_data)
            logger.debug(f"DEBUG HRV SYNC: Результат сохранения HRV: {hrv_result}")
        else:
            logger.debug("DEBUG HRV SYNC: Нет данных HRV для сохранения")
        
        # Сохраняем новые типы данных
        sleep_result = {'new': 0, 'updated': 0}
        logger.debug(f"DEBUG SYNC: Сохранение данных сна в базу: {len(sleep_data)} записей")
        logger.debug(f"DEBUG SYNC: Ключи данных сна: {list(sleep_data.keys()) if sleep_data else 'Нет данных'}")
        if sleep_data:
            sleep_result = database.sync_sleep_data(sleep_data)
            logger.debug(f"DEBUG SYNC: Результат сохранения сна: {sleep_result}")
        else:
            logger.debug("DEBUG SYNC: Нет данных сна для сохранения")
        
        health_result = {'new': 0, 'updated': 0}
        if daily_health_data:
            health_result = database.sync_daily_health(daily_health_data)
        
        status_result = {'new': 0, 'updated': 0}
        if training_status_data:
            status_result = database.sync_training_status(training_status_data)
        
        progress_bar.progress(100, text="✅ Синхронизация завершена!")
        status_text.empty()
        sync_stats.empty()
        
        clear_data_caches()

        # Показываем результат
        success_msgs = []
        if sync_result['new'] > 0:
            success_msgs.append(f"🆕 {sync_result['new']} новых активностей")
        if sync_result['updated'] > 0:
            success_msgs.append(f"🔄 {sync_result['updated']} активностей обновлено")
        if sync_result['skipped'] > 0:
            success_msgs.append(f"⏭️ {sync_result['skipped']} активностей пропущено")
            
        if hrv_result['new'] > 0:
            success_msgs.append(f"💓 {hrv_result['new']} новых HRV записей")
        if hrv_result['updated'] > 0:
            success_msgs.append(f"💓 {hrv_result['updated']} HRV записей обновлено")
        
        # Новые типы данных
        if sleep_result['new'] > 0:
            success_msgs.append(f"😴 {sleep_result['new']} новых записей сна")
        if sleep_result['updated'] > 0:
            success_msgs.append(f"😴 {sleep_result['updated']} записей сна обновлено")
        
        if health_result['new'] > 0:
            success_msgs.append(f"🏃 {health_result['new']} новых записей здоровья")
        if health_result['updated'] > 0:
            success_msgs.append(f"🏃 {health_result['updated']} записей здоровья обновлено")
        
        if status_result['new'] > 0 or status_result['updated'] > 0:
            success_msgs.append(f"🎯 Статус тренированности обновлён")
        
        # Детальная информация о том, что было найдено/не найдено
        details = []
        if len(sleep_data) == 0:
            details.append("😴 Данные сна: не найдены (возможно, недоступны в Garmin Connect)")
        if len(daily_health_data) == 0:
            details.append("🏃 Данные здоровья: не найдены")
        if len(training_status_data) == 0:
            details.append("🎯 Статус тренированности: не найден (возможно, требуется Premium подписка Garmin)")
        
        # Показываем детали, если есть проблемы
        if details:
            st.info("ℹ️ **Информация о данных:**\n" + "\n".join([f"• {detail}" for detail in details]))
        
        if success_msgs:
            st.success("✅ " + " | ".join(success_msgs))
        else:
            st.info("ℹ️ Новых данных не найдено")
        
        # Очищаем прогресс через 2 секунды
        import time
        time.sleep(2)
        progress_bar.empty()
        status_text.empty()
        
    except Exception as e:
        progress_bar.empty()
        status_text.empty()
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


def add_test_phase1_data():
    """Добавление тестовых данных Фазы 1 для демонстрации"""
    state = get_state_manager()
    database = state.database

    if st.button("🧪 Добавить тестовые данные Фазы 1", type="primary", key="add_test_data_btn"):
        try:
            from datetime import datetime, timedelta

            sleep_data: dict[str, dict] = {}
            health_data: dict[str, dict] = {}
            status_data: dict[str, dict] = {}

            for i in range(7):
                date = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')

                sleep_data[date] = {
                    'total_sleep_minutes': 420 + (i % 2) * 30,
                    'deep_sleep_minutes': 80 + (i % 3) * 10,
                    'light_sleep_minutes': 280 + (i % 2) * 20,
                    'rem_sleep_minutes': 60 + (i % 3) * 10,
                    'awakenings_count': 1 + (i % 3),
                    'sleep_score': 75 + (i % 3) * 5,
                    'bedtime': f"23:{15 + (i % 3) * 15:02d}",
                    'wakeup_time': f"0{6 + (i % 2)}:{30 + (i % 2) * 15:02d}",
                    'sleep_efficiency': 88.0 + (i % 3) * 3,
                }

                health_data[date] = {
                    'resting_hr': 48 + (i % 4) * 2,
                    'steps': 8000 + i * 500,
                    'floors_climbed': 8 + (i % 3) * 2,
                    'calories_active': 350 + i * 30,
                    'calories_bmr': 1580,
                    'distance_meters': 6000 + i * 400,
                    'active_minutes': 40 + (i % 3) * 10,
                    'intensity_minutes': 15 + (i % 3) * 5,
                }

            today = datetime.now().strftime('%Y-%m-%d')
            status_data[today] = {
                'vo2_max': 48.5,
                'fitness_age': 32,
                'training_load_7d': 285.0,
                'training_status': 'PRODUCTIVE',
                'training_readiness': 75.0,
                'recovery_time_hours': 14,
                'load_ratio': 1.05,
            }

            database.save_phase1_data(
                sleep_data=sleep_data,
                health_data=health_data,
                training_status=status_data,
            )

            st.success("✅ Тестовые данные добавлены")
            clear_data_caches()
        except Exception as exc:
            st.error(f"❌ Ошибка добавления тестовых данных: {exc}")


def show_welcome_screen():
    """Экран приветствия для неподключённых пользователей"""
    st.markdown("## Добро пожаловать в персональный AI тренер!")
    st.markdown("")
    st.markdown("Этот инструмент поможет вам:")
    st.markdown("- 📊 Анализировать тренировочные данные из Garmin Connect")
    st.markdown("- 💓 Отслеживать показатели HRV и восстановления")
    st.markdown("- 📈 Планировать тренировки с помощью модели Банистера")
    st.markdown("- 🤖 Получать персонализированные рекомендации от AI")
    st.markdown("")
    st.markdown("### Для начала работы:")
    st.markdown("1. Подключитесь к Garmin Connect в боковой панели")
    st.markdown("2. Синхронизируйте ваши тренировочные данные")
    st.markdown("3. Начните анализировать и планировать тренировки!")
    st.markdown("")
    st.markdown("---")
    st.markdown("*Требуется аккаунт Garmin Connect с историей тренировок*")

def show_dashboard():
    """Современный дашборд тренировок в стиле AIEndurance"""
    from utils.modern_ui import ModernUI

    state = get_state_manager()
    database = state.database
    dark_mode = state.dark_mode

    if state.use_custom_theme:
        ModernUI.apply_modern_styles(dark_mode=dark_mode)

    ModernUI.show_horizontal_nav("Dashboard")
    
    theme = ModernUI.get_theme()
    badge_bg_light = "rgba(232,240,255,0.8)"
    badge_bg_dark = theme['surface_light']
    badge_text_color = theme['text_primary']
    badge_border = theme['metric_border']
    
    activities_df = load_activities(30)
    
    if activities_df.empty:
        # Улучшенное приветствие для новых пользователей
        st.info("👋 Добро пожаловать в AI Trainer!")
        
        # Карточки с инструкциями
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("### 🚀 Быстрый старт")
            st.markdown("")
            st.markdown("1. **Подключитесь к Garmin** (уже выполнено ✅)")
            st.markdown("2. **Синхронизируйте данные** - загрузите тренировки")
            st.markdown("3. **Изучите метрики** - TSS, HRV, сон")
            st.markdown("4. **Получите рекомендации** от AI коуча")
            
            if st.button("🔄 Синхронизировать данные", type="primary", use_container_width=True):
                sync_data(days=30)
        
        with col2:
            st.markdown("### 💡 Что умеет AI Trainer?")
            st.markdown("")
            st.markdown("- 📊 Анализ тренировочной нагрузки")
            st.markdown("- 💓 Мониторинг восстановления по HRV")
            st.markdown("- 😴 Оценка качества сна")
            st.markdown("- 🤖 Персональные рекомендации AI")
            st.markdown("- 📈 Планирование тренировок")
            
            if st.button("🎮 Загрузить демо-данные", use_container_width=True):
                # Вызываем функцию добавления тестовых данных
                from datetime import datetime, timedelta
                from data.data_processor_phase1 import Phase1DataProcessor
                
                # Создаем тестовые данные за последние 7 дней
                sleep_data = {}
                health_data = {}
                
                for i in range(7):
                    date = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
                    
                    # Тестовые данные сна
                    base_quality = 75 + (i % 3) * 5
                    sleep_data[date] = {
                        'total_sleep_minutes': 420 + (i % 2) * 30,
                        'deep_sleep_minutes': 80 + (i % 3) * 10,
                        'light_sleep_minutes': 280 + (i % 2) * 20,
                        'rem_sleep_minutes': 60 + (i % 3) * 10,
                        'awakenings_count': 1 + (i % 3),
                        'sleep_score': base_quality + (i % 2) * 5,
                    }
                    
                    # Тестовые данные здоровья
                    health_data[date] = {
                        'resting_hr': 48 + (i % 4) * 2,
                        'steps': 8000 + i * 500,
                    }
                
                # Обрабатываем и сохраняем
                processor = Phase1DataProcessor(database)
                processed_sleep = processor.process_sleep_data(sleep_data)
                processed_health = processor.process_health_data(health_data)
                
                database.save_phase1_data(
                    sleep_data=processed_sleep,
                    health_data=processed_health,
                    training_status={}
                )
                
                st.success("✅ Демо-данные загружены!")
                st.rerun()
        
        # Подсказка внизу
        st.markdown("---")
        st.caption("💡 **Совет:** Начните с синхронизации последних 30 дней тренировок или попробуйте демо-данные")
        return
    
    # Статус-ориентированный дашборд
    st.title("🏃‍♂️ Статус тренировок")
    
    # Расчет текущего статуса
    current_status = calculate_current_status()
    
    # Последний статус тренированности из БД
    training_status_df = database.get_training_status_history(days=30)
    latest_training_status = {}
    if isinstance(training_status_df, pd.DataFrame) and not training_status_df.empty:
        latest_training_status = (
            training_status_df.sort_values("date", ascending=False).iloc[0].to_dict()
        )
    
    training_status_code = (latest_training_status.get('training_status') or "").upper()
    training_status_display = TRAINING_STATUS_TITLES.get(training_status_code, training_status_code or "Нет данных")
    training_load_7d = latest_training_status.get('training_load_7d')
    training_load_chronic = latest_training_status.get('training_load_chronic')
    recovery_time_hours = latest_training_status.get('recovery_time_hours')
    garmin_readiness = latest_training_status.get('training_readiness')
    if garmin_readiness is None or pd.isna(garmin_readiness):
        garmin_readiness = None
    acwr_status_value = (latest_training_status.get('acwr_status') or "").upper()
    acwr_percent = latest_training_status.get('acwr_percent')
    training_feedback_text = latest_training_status.get('training_feedback')
    if not training_feedback_text and latest_training_status.get('training_feedback_code'):
        training_feedback_text = latest_training_status['training_feedback_code'].replace('_', ' ').title()
    balance_feedback_text = latest_training_status.get('training_balance_feedback')
    if not balance_feedback_text and latest_training_status.get('training_balance_feedback_code'):
        balance_feedback_text = latest_training_status['training_balance_feedback_code'].replace('_', ' ').title()
    training_since_date = latest_training_status.get('training_since_date')
    last_primary_sync_date = latest_training_status.get('last_primary_sync_date')
    
    # Критические уведомления
    if current_status.get('critical_status'):
        st.error(f"🚨 {current_status['critical_status']}")
        if current_status.get('critical_action'):
            st.info(f"💡 Рекомендация: {current_status['critical_action']}")
        
        # Дополнительные советы для критических состояний
        if current_status['tsb'] < -30:
            st.markdown("""
            <div class="critical-alert">
                <h3>🛌 Немедленные действия при переутомлении:</h3>
                <ul>
                    <li>• Полный отдых 2-3 дня (никаких тренировок)</li>
                    <li>• Увеличьте продолжительность сна до 8+ часов</li>
                    <li>• Легкие прогулки или стретчинг максимум</li>
                    <li>• Обратите внимание на питание и гидратацию</li>
                    <li>• Рассмотрите массаж или физиотерапию</li>
                </ul>
            </div>
            """, unsafe_allow_html=True)
    
    # Основные статус-карточки (компактный ряд)
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        tsb_value = current_status.get('tsb', 0)
        fig_tsb = ModernUI.create_circular_indicator(tsb_value, 100, "TSB", f"{tsb_value:.1f}", "#10B981")
        st.plotly_chart(fig_tsb, use_container_width=True)
        badge_bg = badge_bg_dark if theme['is_dark'] else badge_bg_light
        badge_style = (
            f"background: {badge_bg};"
            f" color: {badge_text_color}; padding: 4px 8px; border-radius: 12px;"
            f" font-size: 11px; display: inline-block;"
        )
        if theme['is_dark']:
            badge_style += f" border: 1px solid {badge_border};"
        st.markdown(
            f'<div style="text-align: center;"><span style="{badge_style}">Training Stress Balance<br>Тренировочный стресс баланс</span></div>',
            unsafe_allow_html=True
        )
        
    with col2:
        ctl_value = current_status.get('ctl', 0)
        fig_ctl = ModernUI.create_circular_indicator(ctl_value, 150, "CTL", f"{ctl_value:.1f}", "#10B981")
        st.plotly_chart(fig_ctl, use_container_width=True)
        st.markdown(
            f'<div style="text-align: center;"><span style="{badge_style}">Chronic Training Load<br>Хроническая тренировочная нагрузка</span></div>',
            unsafe_allow_html=True
        )
    
    with col3:
        status_color = TRAINING_STATUS_COLORS.get(training_status_code, theme['text_primary'])
        load_text = f"{float(training_load_7d):.0f}" if training_load_7d is not None and not pd.isna(training_load_7d) else "—"
        chronic_text = f"{float(training_load_chronic):.0f}" if training_load_chronic is not None and not pd.isna(training_load_chronic) else "—"
        load_ratio_value = latest_training_status.get('load_ratio')
        load_ratio_text = f"{float(load_ratio_value):.2f}" if load_ratio_value is not None and not pd.isna(load_ratio_value) else "—"
        acwr_style = ACWR_STATUS_STYLES.get(acwr_status_value)
        load_ratio_color = acwr_style['color'] if acwr_style else theme['text_primary']
        acwr_label = acwr_style['label'] if acwr_style else (acwr_status_value.title() if acwr_status_value else "")
        if acwr_percent is not None and not pd.isna(acwr_percent):
            acwr_suffix = f"({float(acwr_percent):.0f}%)"
        else:
            acwr_suffix = ""
        status_date = latest_training_status.get('date')
        caption_parts = []
        if status_date is not None and not pd.isna(status_date):
            try:
                caption_parts.append(f"Обновлено: {format_date(status_date, 'display')}")
            except Exception:
                pass
        if training_since_date:
            try:
                caption_parts.append(f"С {format_date(training_since_date, 'display')}")
            except Exception:
                caption_parts.append(f"С {training_since_date}")
        if last_primary_sync_date and last_primary_sync_date != status_date:
            try:
                caption_parts.append(f"Синхронизировано: {format_date(last_primary_sync_date, 'display')}")
            except Exception:
                caption_parts.append(f"Синхронизировано: {last_primary_sync_date}")
        feedback_messages = []
        if training_feedback_text:
            feedback_messages.append(training_feedback_text)
        if balance_feedback_text and balance_feedback_text != training_feedback_text:
            feedback_messages.append(balance_feedback_text)
        load_ratio_details = {
            "label": "Load ratio",
            "value": load_ratio_text,
            "color": load_ratio_color,
            "badge": acwr_label,
            "suffix": acwr_suffix,
        }
        ModernUI.training_status_card(
            # Training Status
            title="Статус тренировки",
            status_text=training_status_display,
            status_color=status_color,
            metrics=[
                ("Нагрузка 7д", load_text),
                ("Хроническая", chronic_text),
            ],
            load_ratio=load_ratio_details,
            feedback=feedback_messages,
        )
        if caption_parts:
            st.caption(" • ".join(caption_parts))
        ModernUI.training_status_description()

    with col4:
        readiness_fallback = current_status.get('readiness', 0) or 0
        readiness_value = garmin_readiness if garmin_readiness is not None else readiness_fallback
        try:
            readiness_value = float(readiness_value)
        except (ValueError, TypeError):
            readiness_value = 0.0
        readiness_value = max(0.0, min(100.0, readiness_value))
        readiness_source = "Garmin" if garmin_readiness is not None else "AI индекс"
        readiness_subtitle = f"{readiness_value:.0f}% • {readiness_source}"
        readiness_color = "#3B82F6" if garmin_readiness is not None else "#8B5CF6"
        fig_readiness = ModernUI.create_circular_indicator(readiness_value, 100, "Readiness", readiness_subtitle, readiness_color)
        st.plotly_chart(fig_readiness, use_container_width=True)
        readiness_bg = badge_bg_dark if theme['is_dark'] else "rgba(59,130,246,0.85)"
        readiness_style = (
            f"background: {readiness_bg}; color: {badge_text_color if theme['is_dark'] else '#FFFFFF'};"
            f" padding: 4px 8px; border-radius: 12px; font-size: 11px; display: inline-block;"
        )
        if theme['is_dark']:
            readiness_style += f" border: 1px solid {badge_border};"
        st.markdown(
            f'<div style="text-align: center;"><span style="{readiness_style}">Готовность</span></div>',
            unsafe_allow_html=True
        )

    # Отступ между блоками карточек
    st.markdown("<br><br>", unsafe_allow_html=True)

    # AI рекомендации
    recommendations = current_status.get('recommendations', [])
    if recommendations:
        ModernUI.ai_recommendation_panel(recommendations)
    
    # Быстрые действия (компактные)
    show_quick_actions(current_status)

    # Недельный календарь тренировок
    ModernUI.show_weekly_training_calendar(activities_df)
    
    # Компактная аналитика в раскрывающемся блоке
    show_compact_analytics(activities_df, latest_training_status)

def show_quick_actions(current_status):
    """Быстрые действия на основе текущего статуса"""
    from utils.modern_ui import ModernUI

    st.markdown("### ⚡ Быстрые действия")

    # Краткая рекомендация по интенсивности на основе TSB
    try:
        tsb_val = float(current_status.get('tsb', 0) or 0)
    except (ValueError, TypeError):
        tsb_val = 0.0

    if tsb_val < -30:
        intensity_status = "danger"
        intensity_label = "🔴 Отдых"
        intensity_desc = "Полный отдых и восстановление — избегайте тренировок."
    elif tsb_val < -20:
        intensity_status = "warning"
        intensity_label = "🟡 Очень легко"
        intensity_desc = "Только восстановительные сессии в Zone 1 и мягкий сон."
    elif tsb_val < -10:
        intensity_status = "warning"
        intensity_label = "🟠 Легко"
        intensity_desc = "Аэробные тренировки в Zone 1-2, избегайте интенсивных блоков."
    elif tsb_val < 5:
        intensity_status = "success"
        intensity_label = "🟢 Средне"
        intensity_desc = "Можно выполнять стандартные тренировки вплоть до Zone 4."
    else:
        intensity_status = "success"
        intensity_label = "🚀 Высоко"
        intensity_desc = "Готовность высокая — подключайте интенсивные интервалы и VO₂max."

    ModernUI.status_card(
        "Интенсивность сегодня",
        intensity_label,
        intensity_status,
        description=intensity_desc,
    )
    
    # Определяем действия на основе статуса
    actions = []
    
    try:
        tsb_val = float(current_status.get('tsb', 0))
        if tsb_val < -20:
            actions.append({
                "icon": "😴",
                "title": "План восстановления", 
                "desc": "Составить программу активного отдыха",
                "action": "recovery_plan"
            })
        elif tsb_val > 10:
            actions.append({
                "icon": "🔥", 
                "title": "Интенсивная тренировка",
                "desc": "Использовать пиковую форму",
                "action": "intense_workout"
            })
    except (ValueError, TypeError):
        pass
    
    try:
        hrv_val = float(current_status.get('hrv', 0)) if current_status.get('hrv') else 0
        if hrv_val > 0 and hrv_val < 30:
            actions.append({
                "icon": "💓",
                "title": "HRV-анализ",
                "desc": "Детальный разбор вариабельности",
                "action": "hrv_analysis"
            })
    except (ValueError, TypeError):
        pass
    
    actions.extend([
        {"icon": "📊", "title": "Синхронизация", "desc": "Обновить данные", "action": "sync"},
        {"icon": "🤖", "title": "AI Коуч", "desc": "Персональные рекомендации", "action": "ai_chat"},
        {"icon": "📈", "title": "Планирование", "desc": "Настроить тренировки", "action": "planning"}
    ])
    
    # Отображение в виде сетки
    st.markdown('<div class="quick-actions-grid">', unsafe_allow_html=True)
    
    cols = st.columns(3)
    for i, action in enumerate(actions[:6]):  # Максимум 6 действий
        with cols[i % 3]:
            if st.button(f"{action['icon']} {action['title']}", 
                        help=action['desc'], use_container_width=True):
                handle_quick_action(action['action'])
    
    st.markdown('</div>', unsafe_allow_html=True)

def handle_quick_action(action):
    """Обработка быстрых действий"""
    state = get_state_manager()

    if action == "recovery_plan":
        state.selected_page = "🤖 AI Коучинг"
        st.rerun()
    elif action == "intense_workout":
        state.selected_page = "📈 Планирование"
        st.rerun()
    elif action == "hrv_analysis":
        state.selected_page = "💓 Анализ HRV"
        st.rerun()
    elif action == "sync":
        sync_data(days=7)
    elif action == "ai_chat":
        state.selected_page = "🤖 AI Коучинг"
        st.rerun()
    elif action == "planning":
        state.selected_page = "📈 Планирование"
        st.rerun()


def show_compact_analytics(activities_df, training_status_info=None):
    """Компактная аналитика в раскрывающемся блоке"""
    with st.expander("📊 Подробная аналитика", expanded=False):
        if activities_df.empty:
            st.info("Нет данных для анализа")
            return
        
        # Основные метрики в компактном виде
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            total_activities = len(activities_df)
            st.metric("Активности", total_activities)
        
        with col2:
            total_distance = activities_df['distance_km'].sum()
            st.metric("Дистанция", f"{total_distance:.0f} км")
        
        with col3:
            total_time = activities_df['duration_minutes'].sum()
            st.metric("Время", f"{total_time/60:.0f}ч")
        
        with col4:
            avg_tss = activities_df['tss'].mean() if 'tss' in activities_df.columns and activities_df['tss'].notna().any() else 0
            st.metric("Ср. TSS", f"{avg_tss:.0f}")
        
        # Мини-графики
        col1, col2 = st.columns(2)
        
        with col1:
            # График активностей по дням
            activities_df_copy = activities_df.copy()
            if not pd.api.types.is_datetime64_any_dtype(activities_df_copy['date']):
                activities_df_copy['date'] = pd.to_datetime(activities_df_copy['date'])
            
            daily_stats = activities_df_copy.groupby(activities_df_copy['date'].dt.date).agg({
                'duration_minutes': 'sum'
            }).reset_index()
            
            from utils.modern_ui import ModernUI
            fig = ModernUI.create_mini_trend_chart(
                daily_stats['duration_minutes'].tolist(),
                "Время тренировок"
            )
            st.plotly_chart(fig, use_container_width=True)
        
        with col2:
            # Распределение по видам спорта
            sport_dist = activities_df['sport'].value_counts()
            theme = get_plotly_theme()
            fig = px.pie(values=sport_dist.values, names=sport_dist.index,
                        title="Виды спорта", template=theme['template'])
            fig.update_layout(
                height=200,
                margin=dict(l=0, r=0, t=30, b=0),
                paper_bgcolor=theme['paper_bgcolor'],
                plot_bgcolor=theme['plot_bgcolor'],
                font_color=theme['font_color'],
                showlegend=False
            )
            st.plotly_chart(fig, use_container_width=True)
        
        # Таблица последних активностей (компактная)
        st.markdown("**Последние тренировки:**")
        display_df = activities_df.head(5)[['date', 'sport', 'duration_minutes', 'distance_km', 'tss']].copy()
        
        # Безопасное форматирование
        if pd.api.types.is_datetime64_any_dtype(display_df['date']):
            display_df['date'] = display_df['date'].apply(lambda x: format_date(x, 'short'))
        else:
            display_df['date'] = pd.to_datetime(display_df['date']).apply(lambda x: format_date(x, 'short'))
        
        display_df['duration_minutes'] = display_df['duration_minutes'].round(0).astype(int)
        display_df['distance_km'] = display_df['distance_km'].round(1)
        display_df.columns = ['Дата', 'Спорт', 'Мин', 'Км', 'TSS']
        
        st.dataframe(display_df, use_container_width=True, height=200)

        if training_status_info:
            monthly_rows = []

            def _fmt_number(value):
                if value is None or (isinstance(value, float) and pd.isna(value)):
                    return "—"
                try:
                    return f"{float(value):.0f}"
                except (TypeError, ValueError):
                    return str(value)

            def _fmt_range(min_value, max_value):
                if min_value is None and max_value is None:
                    return "—"
                if min_value is None:
                    return f"≤ {_fmt_number(max_value)}"
                if max_value is None:
                    return f"≥ {_fmt_number(min_value)}"
                try:
                    min_val = float(min_value)
                    max_val = float(max_value)
                except (TypeError, ValueError):
                    return f"{_fmt_number(min_value)}–{_fmt_number(max_value)}"
                if abs(min_val - max_val) < 1e-3:
                    return _fmt_number(min_val)
                return f"{min_val:.0f}–{max_val:.0f}"

            monthly_low = training_status_info.get('monthly_load_aerobic_low')
            if monthly_low is not None:
                monthly_rows.append({
                    'Зона': 'Низкоаэробная',
                    'Текущее': _fmt_number(monthly_low),
                    'Цель': _fmt_range(
                        training_status_info.get('monthly_load_aerobic_low_target_min'),
                        training_status_info.get('monthly_load_aerobic_low_target_max')
                    )
                })

            monthly_high = training_status_info.get('monthly_load_aerobic_high')
            if monthly_high is not None:
                monthly_rows.append({
                    'Зона': 'Высокоаэробная',
                    'Текущее': _fmt_number(monthly_high),
                    'Цель': _fmt_range(
                        training_status_info.get('monthly_load_aerobic_high_target_min'),
                        training_status_info.get('monthly_load_aerobic_high_target_max')
                    )
                })

            monthly_ana = training_status_info.get('monthly_load_anaerobic')
            if monthly_ana is not None:
                monthly_rows.append({
                    'Зона': 'Анаэробная',
                    'Текущее': _fmt_number(monthly_ana),
                    'Цель': _fmt_range(
                        training_status_info.get('monthly_load_anaerobic_target_min'),
                        training_status_info.get('monthly_load_anaerobic_target_max')
                    )
                })

            if monthly_rows:
                st.markdown("**Баланс нагрузки Garmin:**")
                monthly_df = pd.DataFrame(monthly_rows)
                st.dataframe(monthly_df, use_container_width=True, hide_index=True)
                balance_feedback = training_status_info.get('training_balance_feedback')
                if balance_feedback:
                    st.caption(balance_feedback)

def show_activities():
    """Страница активностей"""
    state = get_state_manager()
    database = state.database
    st.header("🏃‍♂️ Ваши активности")
    
    # Получаем данные активностей
    activities_df = load_activities(30)  # За последние 30 дней
    
    if activities_df.empty:
        st.warning("📭 Нет активностей за последние 30 дней. Синхронизируйте данные с Garmin Connect.")
        return
    
    # Фильтры
    col1, col2, col3 = st.columns(3)
    
    with col1:
        selected_sports = st.multiselect(
            "Виды спорта:",
            options=activities_df['sport'].unique(),
            default=activities_df['sport'].unique()
        )
    
    with col2:
        date_range = st.slider(
            "Период (дней):",
            min_value=7,
            max_value=90,
            value=30
        )
    
    with col3:
        sort_by = st.selectbox(
            "Сортировать по:",
            options=["date", "distance_km", "duration_minutes", "tss"],
            format_func=lambda x: {
                "date": "Дате",
                "distance_km": "Дистанции", 
                "duration_minutes": "Времени",
                "tss": "TSS"
            }.get(x, x)
        )
    
    # Фильтруем данные
    filtered_df = activities_df[
        (activities_df['sport'].isin(selected_sports))
    ].tail(date_range * 3).sort_values(sort_by, ascending=False)  # Примерно 3 тренировки в день максимум
    
    # Статистика
    st.subheader("📊 Статистика")
    
    # Адаптивная сетка: 2x2 на мобильных
    col1, col2 = st.columns(2)
    col3, col4 = st.columns(2)
    
    with col1:
        st.metric("Всего тренировок", len(filtered_df))
    
    with col2:
        total_distance = filtered_df['distance_km'].sum()
        st.metric("Общая дистанция", f"{total_distance:.1f} км")
    
    with col3:
        total_time = filtered_df['duration_minutes'].sum()
        st.metric("Общее время", f"{total_time/60:.1f} ч")
    
    with col4:
        avg_tss = filtered_df['tss'].mean() if 'tss' in filtered_df.columns else 0
        st.metric("Средний TSS", f"{avg_tss:.0f}")
    
    # График активности по дням
    if len(filtered_df) > 0:
        st.subheader("📈 Активность по дням")

        # Подготовка данных для графика
        filtered_df['date'] = pd.to_datetime(filtered_df['date'])
        daily_stats = filtered_df.groupby('date').agg({
            'tss': 'sum',
            'duration_minutes': 'sum',
            'distance_km': 'sum'
        }).reset_index()

        if state.use_custom_theme:
            theme = get_plotly_theme(state.dark_mode)
            fig_tss = px.bar(
                daily_stats,
                x='date',
                y='tss',
                title="Training Stress Score по дням",
                labels={'tss': 'TSS', 'date': 'Дата'},
                template=theme['template']
            )
            fig_tss.update_layout(
                height=400,
                paper_bgcolor=theme['paper_bgcolor'],
                plot_bgcolor=theme['plot_bgcolor'],
                font_color=theme['font_color']
            )
        else:
            fig_tss = px.bar(
                daily_stats,
                x='date',
                y='tss',
                title="Training Stress Score по дням",
                labels={'tss': 'TSS', 'date': 'Дата'}
            )
            fig_tss.update_layout(height=400)

        st.plotly_chart(fig_tss, use_container_width=True)
    
    # Таблица активностей
    st.subheader("📋 Список тренировок")
    
    # Форматируем данные для отображения
    display_df = filtered_df.copy()
    display_df['date'] = pd.to_datetime(display_df['date']).apply(lambda x: format_date(x, 'display'))
    display_df['duration_minutes'] = display_df['duration_minutes'].round(0).astype(int)
    display_df['distance_km'] = display_df['distance_km'].round(2)
    
    # Переименовываем колонки
    display_columns = {
        'date': 'Дата',
        'sport': 'Спорт', 
        'duration_minutes': 'Время (мин)',
        'distance_km': 'Дистанция (км)',
        'avg_hr': 'Ср. ЧСС',
        'avg_power': 'Ср. мощность',
        'tss': 'TSS'
    }
    
    # Выбираем и переименовываем колонки
    columns_to_show = [col for col in display_columns.keys() if col in display_df.columns]
    table_df = display_df[columns_to_show].rename(columns=display_columns)
    
    # Отображаем таблицу с учетом темы
    if state.use_custom_theme and state.dark_mode:
        st.markdown(create_dark_table_html(table_df), unsafe_allow_html=True)
    else:
        st.dataframe(table_df, use_container_width=True, hide_index=True)
    
    # Детали выбранной тренировки
    if len(filtered_df) > 0:
        st.subheader("🔍 Детали тренировки")
        
        selected_activity = st.selectbox(
            "Выберите тренировку:",
            options=range(len(filtered_df)),
            format_func=lambda i: f"{filtered_df.iloc[i]['date']} - {filtered_df.iloc[i]['sport']} ({filtered_df.iloc[i]['distance_km']:.1f} км)"
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
            if 'avg_hr' in activity and pd.notna(activity['avg_hr']):
                st.write(f"💓 Средний пульс: {activity['avg_hr']:.0f} уд/мин")
            if 'avg_power' in activity and pd.notna(activity['avg_power']):
                st.write(f"⚡ Средняя мощность: {activity['avg_power']:.0f} W")
            if 'tss' in activity and pd.notna(activity['tss']):
                st.write(f"📊 TSS: {activity['tss']:.0f}")
            if 'calories' in activity and pd.notna(activity['calories']):
                st.write(f"🔥 Калории: {activity['calories']:.0f}")
    
    # Экспорт данных
    if len(filtered_df) > 0:
        st.subheader("📤 Экспорт данных")
        
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("📊 Скачать CSV"):
                csv = table_df.to_csv(index=False)
                st.download_button(
                    label="💾 Загрузить CSV файл",
                    data=csv,
                    file_name=f"activities_{datetime.now().strftime('%Y%m%d')}.csv",
                    mime="text/csv"
                )
        
        with col2:
            if st.button("📈 Создать отчет"):
                st.info("📋 Функция создания отчетов будет добавлена в следующих версиях.")

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

def show_chat_management():
    """Управление чатами в боковой панели"""
    state = get_state_manager()
    chat_manager = state.chat_manager

    with st.sidebar:
        st.subheader("💬 Управление чатами")

        col1, col2 = st.columns(2)
        with col1:
            if st.button("➕ Новый чат", use_container_width=True, type="primary"):
                new_chat_id = chat_manager.create_new_chat()
                state.current_chat_id = new_chat_id
                state.switch_to_chat_tab = True
                state.selected_page = "🤖 AI Коучинг"
                st.rerun()

        with col2:
            if state.current_chat_id and st.button("🧹 Очистить", use_container_width=True):
                if chat_manager.clear_chat(state.current_chat_id):
                    st.success("Чат очищен")
                    st.rerun()

        chats = chat_manager.get_chat_list()

        if chats:
            st.markdown('<div class="sidebar-chat-list">', unsafe_allow_html=True)

            for chat in chats:
                is_current = chat["id"] == state.current_chat_id

                col1, col2 = st.columns([4, 1])

                with col1:
                    chat_title = chat['title'][:30] + ("..." if len(chat['title']) > 30 else "")
                    button_text = f"{'🔵' if is_current else '💬'} {chat_title}"

                    if st.button(
                        button_text,
                        key=f"chat_{chat['id']}",
                        use_container_width=True,
                        help=f"Сообщений: {chat['message_count']} • {chat['updated_at'][:16].replace('T', ' ')}",
                    ):
                        state.current_chat_id = chat["id"]
                        state.selected_page = "🤖 AI Коучинг"
                        state.switch_to_chat_tab = True
                        st.success(f"Выбран чат: {chat['title'][:20]}...")
                        st.rerun()

                with col2:
                    if st.button("🗑️", key=f"delete_{chat['id']}", help="Удалить чат"):
                        if chat_manager.delete_chat(chat["id"]):
                            if state.current_chat_id == chat["id"]:
                                state.current_chat_id = None
                            st.success("Чат удален")
                            st.rerun()

            st.markdown('</div>', unsafe_allow_html=True)
        else:
            st.info("Пока нет сохраненных чатов")

def show_ai_coaching():
    """Страница AI коучинга: управление провайдерами и чат"""
    state = get_state_manager()
    st.header("🤖 AI Коучинг")

    from models.ai_providers import AIProviderFactory
    from models.ai_coach_universal import UniversalAICoach

    if not getattr(state, 'ai_coach', None):
        state.ai_coach = None
    if not state.selected_provider:
        state.selected_provider = Settings.DEFAULT_AI_PROVIDER

    with st.sidebar.expander("⚙️ Настройки AI", expanded=True):
        st.subheader("Выбор AI провайдера")
        available = AIProviderFactory.get_available_providers()
        for name, is_available in available.items():
            if is_available:
                st.success(f"✅ {name}")
            else:
                st.error(f"❌ {name}")

        provider_options = {
            "OpenAI (GPT)": "openai",
            "Anthropic (Claude)": "anthropic",
            "Google (Gemini)": "google",
            "Ollama (Локально)": "ollama"
        }

        selected_name = st.selectbox(
            "Провайдер:",
            options=list(provider_options.keys()),
            index=list(provider_options.values()).index(state.selected_provider)
        )
        selected_provider = provider_options[selected_name]

        provider_kwargs = {}

        @st.cache_data(ttl=300)
        def get_models_for_provider(provider_type, **kwargs):
            try:
                temp_provider = AIProviderFactory.create_provider(provider_type, **kwargs)
                return temp_provider.get_available_models()
            except Exception:
                return []

        if selected_provider == "openai":
            api_key = st.text_input("API Key:", value=Settings.OPENAI_API_KEY or "", type="password")
            if api_key:
                with st.spinner("Загрузка списка моделей OpenAI..."):
                    available_models = get_models_for_provider("openai", api_key=api_key)
            else:
                available_models = ["gpt-3.5-turbo", "gpt-4", "gpt-4-turbo-preview"]

            if available_models:
                current_model = Settings.OPENAI_MODEL
                try:
                    default_index = available_models.index(current_model)
                except ValueError:
                    default_index = 0
                model = st.selectbox(
                    f"Модель: ({len(available_models)} доступно)",
                    available_models,
                    index=default_index,
                    help=f"Выберите модель из {len(available_models)} доступных"
                )
            else:
                model = st.text_input("Модель:", value=Settings.OPENAI_MODEL)
                st.warning("⚠️ Не удалось загрузить список моделей. Введите название модели вручную.")
            provider_kwargs = {"api_key": api_key, "model": model}

        elif selected_provider == "anthropic":
            api_key = st.text_input("API Key:", value=Settings.ANTHROPIC_API_KEY or "", type="password")
            available_models = [
                "claude-3-haiku-20240307",
                "claude-3-sonnet-20240229",
                "claude-3-opus-20240229",
                "claude-2.1",
                "claude-2.0",
            ]
            current_model = Settings.ANTHROPIC_MODEL
            try:
                default_index = available_models.index(current_model)
            except ValueError:
                default_index = 0
            model = st.selectbox(
                f"Модель: ({len(available_models)} доступно)",
                available_models,
                index=default_index,
                help="Выберите модель Claude"
            )
            provider_kwargs = {"api_key": api_key, "model": model}

        elif selected_provider == "google":
            api_key = st.text_input("API Key:", value=Settings.GOOGLE_API_KEY or "", type="password")
            available_models = [
                "models/gemini-2.5-flash",
                "models/gemini-2.0-flash-exp",
                "models/gemini-2.0-flash",
                "models/gemini-1.5-flash-latest",
                "models/gemini-1.5-flash",
                "models/gemini-1.5-flash-8b",
            ]
            current_model = Settings.GOOGLE_MODEL
            try:
                default_index = available_models.index(current_model)
            except ValueError:
                default_index = 0
            model = st.selectbox(
                f"Модель: ({len(available_models)} доступно)",
                available_models,
                index=default_index,
                help="Выберите модель Gemini"
            )
            provider_kwargs = {"api_key": api_key, "model": model}

        elif selected_provider == "ollama":
            host = st.text_input("Host:", value=Settings.OLLAMA_HOST)
            with st.spinner("Загрузка локальных моделей Ollama..."):
                available_models = get_models_for_provider("ollama", host=host, model="dummy")
            if available_models:
                current_model = Settings.OLLAMA_MODEL
                try:
                    default_index = available_models.index(current_model)
                except ValueError:
                    default_index = 0
                model = st.selectbox(
                    f"Модель: ({len(available_models)} локальных)",
                    available_models,
                    index=default_index,
                    help=f"Выберите локальную модель из {len(available_models)} установленных"
                )
            else:
                model = st.text_input("Модель:", value=Settings.OLLAMA_MODEL)
                st.warning("⚠️ Не удалось загрузить список моделей Ollama. Убедитесь, что Ollama запущен.")
            provider_kwargs = {"host": host, "model": model}

        col1, col2 = st.columns(2)
        with col1:
            if st.button("🔍 Тест подключения", help="Проверить API ключ и подключение"):
                try:
                    provider = AIProviderFactory.create_provider(selected_provider, **provider_kwargs)
                    with st.spinner("Проверка подключения..."):
                        test_result = provider.test_connection()
                    if test_result.get('success'):
                        st.success(f"✅ {test_result.get('message')}")
                        with st.expander("📋 Детали подключения"):
                            for key, value in test_result.items():
                                if key not in ["success", "message"]:
                                    st.write(f"**{key}:** {value}")
                    else:
                        st.error(f"❌ {test_result.get('error')}")
                except Exception as exc:
                    st.error(f"❌ Ошибка тестирования: {exc}")
        with col2:
            if st.button("🔌 Подключить AI", help="Подключиться к выбранному провайдеру"):
                try:
                    provider = AIProviderFactory.create_provider(selected_provider, **provider_kwargs)
                    if provider.is_available():
                        state.ai_coach = UniversalAICoach(provider)
                        state.selected_provider = selected_provider
                        st.success(f"✅ Подключено к {provider.get_model_name()}")
                        st.info(f"🎯 Выбранная модель: **{provider_kwargs.get('model')}**")
                    else:
                        st.error("❌ Не удалось подключиться к провайдеру")
                except Exception as exc:
                    st.error(f"❌ Ошибка: {exc}")

    if state.ai_coach is None:
        st.warning("👆 Настройте AI провайдера в боковой панели")
        return

    if state.switch_to_chat_tab:
        state.switch_to_chat_tab = False

    show_ai_chat()

def show_ai_chat():
    """Современный интерфейс AI чата с сохранением и управлением"""
    state = get_state_manager()
    database = state.database
    # Проверяем подключение к AI
    if state.ai_coach is None:
        st.warning("👆 Настройте AI провайдера для использования чата")
        return
    
    # Менеджер чатов уже инициализирован в main()
    
    # Инициализация AI инструментов
    if "ai_tools" not in state:
        from models.ai_tools import AITools
        state.ai_tools = AITools(database)
    
    # Инициализация контекста данных
    if "data_context" not in state:
        state.data_context = None
        state.context_loaded = False
    
    # Текущий чат
    if "current_chat_id" not in state:
        state.current_chat_id = None
    
    # Если чат не выбран, пробуем открыть последний из списка
    if state.current_chat_id is None:
        existing_chats = state.chat_manager.get_chat_list()
        if existing_chats:
            state.current_chat_id = existing_chats[0]["id"]
    
    # CSS для улучшения интерфейса чата
    st.markdown("""
    <style>
    .main > div {
        max-width: 1200px;
        padding: 0 2rem;
    }
    
    .chat-container {
        max-width: 800px;
        margin: 0 auto;
    }
    
    /* Настройки ширины чата - мягкие стили без поломки форматирования */
    .stChatMessage {
        max-width: 800px !important;
    }
    
    .stChatMessage > div {
        max-width: 100% !important;
    }
    
    /* Контейнеры markdown используют полную ширину */
    .stChatMessage [data-testid="stMarkdownContainer"] {
        max-width: 100% !important;
    }
    
    .chat-input-fixed {
        position: sticky;
        bottom: 0;
        background: white;
        padding: 15px 0;
        border-top: 1px solid #ddd;
        z-index: 999;
        max-width: 800px;
        margin: 0 auto;
    }
    
    .quick-buttons {
        margin-bottom: 10px;
        max-width: 800px;
        margin: 0 auto 10px auto;
    }
    
    .sidebar-chat-list {
        max-height: 400px;
        overflow-y: auto;
    }
    
    .chat-title {
        font-size: 0.9rem;
        font-weight: 500;
        margin-bottom: 2px;
    }
    
    .chat-meta {
        font-size: 0.75rem;
        color: #666;
        margin: 0;
    }
    
    /* Улучшенный стиль для сообщений AI */
    [data-testid="stChatMessage"][data-testid*="assistant"] {
        background-color: #f8f9fa;
        border-radius: 10px;
        padding: 15px;
        margin: 10px 0;
    }
    
    /* Улучшенный стиль для сообщений пользователя */
    [data-testid="stChatMessage"][data-testid*="user"] {
        background-color: #e3f2fd;
        border-radius: 10px;
        padding: 15px;
        margin: 10px 0;
    }
    </style>
    """, unsafe_allow_html=True)
    
    # Настройки AI коучинга в боковой панели
    with st.sidebar:
        # Настройки
        st.divider()
        st.subheader("⚙️ Настройки")
        
        # Выбор периода для анализа данных
        context_days = st.selectbox(
            "📅 Период анализа",
            [30, 60, 90, 180],
            index=1,
            help="Количество дней данных для анализа AI"
        )
        
        # Кнопка обновления контекста
        if st.button("🔄 Обновить данные", help="Загрузить свежие данные"):
            with st.spinner("Загрузка данных..."):
                from models.ai_data_context import AIDataContext
                data_context = AIDataContext(database)
                state.data_context = data_context.get_full_context(context_days)
                state.context_loaded = True
                st.success(f"✅ Данные обновлены")
        
        # Расширенная диагностика контекста
        st.divider()
        st.subheader("🔍 Диагностика данных")
        
        if state.context_loaded and state.data_context:
            context = state.data_context
            def fmt_health(value, fmt_mask=".1f"):
                if value is None or (hasattr(pd, "isna") and pd.isna(value)):
                    return "н/д"
                return format(float(value), fmt_mask)
            summary = context['summary']
            
            # Показываем детальную информацию о доступных данных
            st.success(f"✅ Данные загружены: {context_days} дней")
            
            # Основная сводка
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Тренировок", summary.get('total_activities', 0))
            with col2:
                st.metric("HRV записей", summary.get('hrv_data_points', 0))
            with col3:
                st.metric("Общий TSS", f"{summary.get('total_tss', 0):.0f}")
            
            # Проверка доступности разных типов данных
            st.write("**Доступные модули данных:**")
            data_modules = []
            
            if context.get('activities', {}).get('has_data', False):
                data_modules.append("✅ Активности")
            else:
                data_modules.append("❌ Активности")
                
            if context.get('hrv', {}).get('has_data', False):
                data_modules.append("✅ HRV данные") 
            else:
                data_modules.append("❌ HRV данные")
                
            if context.get('performance_metrics', {}).get('has_data', False):
                data_modules.append("✅ Метрики (Banister)")
            else:
                data_modules.append("❌ Метрики (Banister)")
                
            if context.get('sleep', {}).get('has_data', False):
                data_modules.append("✅ Данные сна")
            else:
                data_modules.append("❌ Данные сна")
                
            if context.get('daily_health', {}).get('has_data', False):
                data_modules.append("✅ Ежедневное здоровье")
            else:
                data_modules.append("❌ Ежедневное здоровье")
                
            if context.get('training_status', {}).get('has_data', False):
                data_modules.append("✅ Garmin Training Status")
            else:
                data_modules.append("❌ Garmin Training Status")
                
            if context.get('user_profile', {}).get('has_data', False):
                data_modules.append("✅ Профиль пользователя")
            else:
                data_modules.append("❌ Профиль пользователя")
                
            st.write(" • ".join(data_modules))
            
            # Показываем последние активности если есть
            if context.get('activities', {}).get('recent_activities'):
                with st.expander("🏃 Последние активности"):
                    recent = context['activities']['recent_activities'][:5]
                    for activity in recent:
                        st.write(f"• {activity.get('date', 'N/A')} - {activity.get('sport', 'N/A')} ({activity.get('duration_minutes', 0)} мин, TSS: {activity.get('tss', 0)})")
            
            # Показываем метрики производительности если есть
            if context.get('performance_metrics', {}).get('has_data', False):
                with st.expander("📊 Текущие метрики"):
                    pm = context['performance_metrics']['banister_model']
                    st.write(f"• CTL: {pm.get('ctl', 0):.1f}")
                    st.write(f"• ATL: {pm.get('atl', 0):.1f}")
                    st.write(f"• TSB: {pm.get('tsb', 0):.1f}")
            
            if context.get('daily_health', {}).get('has_data', False):
                with st.expander("🏥 Ежедневное здоровье"):
                    dh_stats = context['daily_health']['stats']
                    st.write(f"• Шаги (средние): {fmt_health(dh_stats.get('avg_steps'), '.0f')}")
                    st.write(f"• ЧСС покоя: {fmt_health(dh_stats.get('avg_resting_hr'))}")
                    st.write(f"• Активные минуты: {fmt_health(dh_stats.get('avg_active_minutes'))}")
                    st.write(f"• Тренд шагов: {context['daily_health']['trend_steps'] or 'н/д'}")
            
            if context.get('training_status', {}).get('has_data', False):
                with st.expander("🎯 Garmin Training Status"):
                    latest = context['training_status']['latest']
                    summary = context['training_status']['summary']
                    st.write(f"• Последний статус: {latest.get('training_status', 'н/д')}")
                    readiness_avg = summary.get('avg_training_readiness')
                    st.write(f"• Readiness (среднее): {fmt_health(readiness_avg)}/100" if readiness_avg is not None else "• Readiness: данных нет")
                    load_avg = summary.get('avg_training_load_7d')
                    st.write(f"• Нагрузка 7д (средняя): {fmt_health(load_avg)}" if load_avg is not None else "• Нагрузка 7д: данных нет")
                    vo2_avg = summary.get('avg_vo2_max')
                    st.write(f"• VO₂max (средний): {fmt_health(vo2_avg)}" if vo2_avg is not None else "• VO₂max: данных нет")
                    
            # Показываем HRV статус если есть
            if context.get('hrv', {}).get('has_data', False):
                with st.expander("💓 HRV состояние"):
                    hrv_stats = context['hrv']['stats']
                    st.write(f"• Текущий RMSSD: {hrv_stats.get('current_rmssd', 0):.1f} мс")
                    st.write(f"• Состояние: {hrv_stats.get('recovery_state', 'unknown')}")
            
            # Показываем данные сна если есть
            if context.get('sleep', {}).get('has_data', False):
                with st.expander("😴 Состояние сна"):
                    sleep_stats = context['sleep']['stats']
                    st.write(f"• Среднее время сна: {sleep_stats.get('avg_total_sleep_hours', 0):.1f} ч/ночь")
                    st.write(f"• Оценка сна: {sleep_stats.get('avg_sleep_score', 0):.1f}/100")
                    st.write(f"• Качество: {context['sleep'].get('sleep_quality', 'unknown')}")
                    st.write(f"• Данных: {context['sleep'].get('data_points', 0)} записей")
                    
        else:
            st.warning("⚠️ Данные не загружены - нажмите '🔄 Обновить данные'")
            st.info("🤖 **AI имеет доступ ко ВСЕМ данным из Garmin Connect:**")
            st.markdown("""
            **Данные активностей:**
            • Тренировки (дата, спорт, длительность, расстояние)
            • Пульс (средний, максимальный, зоны)
            • Мощность и TSS (Training Stress Score)
            • Набор высоты и темп
            • Анализ по видам спорта
            
            **HRV (вариабельность сердечного ритма):**
            • RMSSD (основной показатель)
            • Стресс-индекс и уровень восстановления
            • Тренды и динамика
            • Корреляция с тренировочной нагрузкой
            
            **Данные сна:**
            • Общее время сна и эффективность сна
            • Фазы сна (глубокий, легкий, REM)
            • Оценка качества сна (Garmin Sleep Score)
            • Время засыпания и пробуждения
            • Количество пробуждений за ночь
            • Анализ паттернов и трендов сна
            
            **Ежедневное здоровье:**
            • Шаги и активные калории
            • ЧСС в покое и интенсивные минуты
            • Тренды активности по дням
            
            **Garmin Training Status:**
            • Readiness, тренированность и VO₂max
            • Недельная нагрузка и ACWR
            • История статусов Garmin
            
            **Модель Банистера:**
            • CTL (хроническая тренировочная нагрузка)
            • ATL (острая тренировочная нагрузка)  
            • TSB (баланс стресса тренировки)
            • Прогноз формы и рекомендации
            
            **Аналитика:**
            • Недельные и месячные тренды
            • Распределение интенсивности
            • Паттерны тренировок
            • Профиль спортсмена и уровень подготовки
            """)
            
            # Дополнительная диагностическая кнопка для показа полного контекста AI
            if st.button("🔬 Показать полный контекст для AI"):
                with st.expander("📋 Системный промпт AI", expanded=True):
                    system_prompt = create_chat_system_prompt_with_tools(state.data_context)
                    st.code(system_prompt, language="markdown")
                    
                with st.expander("🗄️ Полный контекст данных"):
                    from models.ai_data_context import AIDataContext
                    context_formatter = AIDataContext(None)
                    formatted_context = context_formatter.format_context_for_ai(state.data_context)
                    st.code(formatted_context, language="markdown")
        
        # Статистика чатов
        chats = state.chat_manager.get_chat_list()
        if chats:
            stats = state.chat_manager.get_stats()
            st.divider()
            st.subheader("📊 Статистика")
            col1, col2 = st.columns(2)
            col1.metric("Чатов", stats["total_chats"])
            col2.metric("Сообщений", stats["total_messages"])
    
    # Основная область чата
    st.title("🤖 AI Тренер")
    
    # Загрузка контекста при первом запуске
    if not state.context_loaded:
        with st.spinner("Загрузка данных для AI..."):
            from models.ai_data_context import AIDataContext
            data_context = AIDataContext(database)
            state.data_context = data_context.get_full_context(context_days)
            state.context_loaded = True
    
    # Контейнер для чата с улучшенным стилем
    with st.container():
        st.markdown('<div class="chat-container">', unsafe_allow_html=True)
        st.caption(f"ID текущего чата: {state.current_chat_id or '—'}")
        
        # Загружаем сообщения текущего чата
        current_messages = []
        if state.current_chat_id:
            current_messages = state.chat_manager.get_chat_messages(state.current_chat_id)
        st.caption(f"Сообщений в чате: {len(current_messages)}")
        
        # Отображение сообщений
        if current_messages:
            for message in current_messages:
                if message["role"] == "user":
                    with st.chat_message("user"):
                        st.write(message["content"])
                else:
                    with st.chat_message("assistant"):
                        st.markdown(message["content"])
        else:
            # Приветственное сообщение для нового чата
            with st.chat_message("assistant"):
                st.markdown("""
                👋 **Привет! Я ваш персональный AI тренер.**
                
                У меня есть доступ ко всем вашим тренировочным данным и мощные инструменты для анализа:
                
                **🎯 Что я могу:**
                • Анализировать ваши тренировки и прогресс
                • Давать рекомендации по восстановлению и нагрузкам  
                • Объяснять метрики и показатели простым языком
                • Составлять персональные планы тренировок
                • Отвечать на любые вопросы о ваших данных
                
                **💡 Попробуйте спросить:**
                - "Как мое восстановление сегодня?"
                - "Сколько тренировок у меня было в июле?"
                - "Покажи мой прогресс за последний месяц"
                - "Можно ли мне тренироваться интенсивно?"
                
                Начните диалог! 🚀
                """)
        
        st.markdown('</div>', unsafe_allow_html=True)
    
    # Фиксированная область ввода внизу
    st.markdown('<div class="chat-input-fixed">', unsafe_allow_html=True)
    
    # Быстрые кнопки (компактные)
    st.markdown('<div class="quick-buttons">', unsafe_allow_html=True)
    st.markdown("**⚡ Быстрые вопросы:**")
    # Адаптивная сетка: 2x2 на мобильных
    col1, col2 = st.columns(2)
    col3, col4 = st.columns(2)
    
    with col1:
        if st.button("💪 Форма", key="form_q", help="Как моя текущая форма?"):
            process_modern_chat_message("Проанализируй мою текущую форму (TSB, CTL, ATL) и состояние восстановления (HRV). Дай четкую оценку готовности к нагрузкам.")
    
    with col2:
        if st.button("📅 План", key="plan_q", help="План на неделю"):
            process_modern_chat_message("На основе моего текущего состояния (TSB, HRV, недавние тренировки) составь конкретный план тренировок на следующую неделю. ОБЯЗАТЕЛЬНО дай четкий план по дням с видами тренировок и интенсивностью.")
    
    with col3:
        if st.button("📊 Прогресс", key="progress_q", help="Анализ прогресса"):
            process_modern_chat_message("Покажи мой прогресс за месяц: тренды нагрузки, лучшие результаты, изменение формы. ОБЯЗАТЕЛЬНО дай конкретные выводы.")
    
    with col4:
        if st.button("💓 HRV", key="hrv_q", help="Анализ восстановления"):
            process_modern_chat_message("Проанализируй мое состояние восстановления: HRV тренды, нагрузка за неделю, качество сна. ОБЯЗАТЕЛЬНО дай рекомендации по тренировкам.")
    
    st.markdown('</div>', unsafe_allow_html=True)
    
    # Поле ввода сообщения
    user_input = st.chat_input("Задайте вопрос AI тренеру...")
    
    if user_input:
        process_modern_chat_message(user_input)
    
    st.markdown('</div>', unsafe_allow_html=True)

def handle_chat_command(command: str, state):
    """Обрабатывает команды чата (начинающиеся с /)"""
    # Парсим команду
    parts = command.strip().split(maxsplit=1)
    cmd = parts[0].lower()
    args = parts[1] if len(parts) > 1 else ""
    
    # Создаем новый чат если его нет
    if not state.current_chat_id:
        state.current_chat_id = state.chat_manager.create_new_chat()
    
    # Добавляем команду в чат
    state.chat_manager.add_message(state.current_chat_id, "user", command)
    
    # Отображаем команду пользователя
    with st.chat_message("user"):
        st.write(command)
    
    # Обрабатываем команду
    with st.chat_message("assistant"):
        response = ""
        
        if cmd == "/speechcore":
            response = handle_speechcore_command(args, state)
        else:
            response = f"❓ Неизвестная команда: `{cmd}`\n\nДоступные команды:\n- `/speechcore` - Управление речевыми функциями"
        
        st.markdown(response)
        state.chat_manager.add_message(state.current_chat_id, "assistant", response)
    
    st.rerun()

def handle_speechcore_command(args: str, state) -> str:
    """Обрабатывает команду /speechcore"""
    args = args.strip().lower()
    
    # Инициализируем состояние speechcore если его нет
    if "speechcore_enabled" not in state._session:
        state._session["speechcore_enabled"] = False
    if "speechcore_voice" not in state._session:
        state._session["speechcore_voice"] = "default"
    
    if args == "" or args == "help" or args == "?":
        # Показываем справку
        enabled_status = '✅ Включен' if state._session.get('speechcore_enabled', False) else '❌ Выключен'
        voice_name = state._session.get('speechcore_voice', 'default')
        return f"""🎤 **SpeechCore - Речевые функции AI тренера**

**Доступные команды:**
- `/speechcore` или `/speechcore help` - Показать эту справку
- `/speechcore on` - Включить речевой синтез (озвучивание ответов)
- `/speechcore off` - Выключить речевой синтез
- `/speechcore status` - Показать текущий статус
- `/speechcore voice <имя>` - Выбрать голос (например: `default`, `female`, `male`)

**Текущий статус:**
- Речевой синтез: {enabled_status}
- Голос: `{voice_name}`

**Примечание:** Речевой синтез будет озвучивать ответы AI тренера в чате."""
    
    elif args == "on" or args == "enable":
        state._session["speechcore_enabled"] = True
        return f"""✅ **Речевой синтез включен**

Ответы AI тренера теперь будут озвучиваться. Голос: `{state._session.get('speechcore_voice', 'default')}`

Используйте `/speechcore off` для отключения."""
    
    elif args == "off" or args == "disable":
        state._session["speechcore_enabled"] = False
        return """❌ **Речевой синтез выключен**

Ответы AI тренера больше не будут озвучиваться.

Используйте `/speechcore on` для включения."""
    
    elif args == "status":
        enabled = state._session.get("speechcore_enabled", False)
        voice = state._session.get("speechcore_voice", "default")
        return f"""📊 **Статус SpeechCore**

- Речевой синтез: {'✅ Включен' if enabled else '❌ Выключен'}
- Голос: `{voice}`

Используйте `/speechcore help` для списка команд."""
    
    elif args.startswith("voice "):
        voice_name = args.replace("voice ", "").strip()
        if voice_name:
            state._session["speechcore_voice"] = voice_name
            return f"""🎙️ **Голос изменен**

Новый голос: `{voice_name}`

Доступные варианты: `default`, `female`, `male`

Используйте `/speechcore on` для включения речевого синтеза."""
        else:
            return """❌ **Ошибка**

Укажите имя голоса. Например: `/speechcore voice female`"""
    
    else:
        return f"""❓ **Неизвестная подкоманда: `{args}`**

Используйте `/speechcore help` для списка доступных команд."""

def process_modern_chat_message(user_input):
    """Обрабатывает сообщение в современном чате с сохранением"""
    state = get_state_manager()
    
    # Обработка команд (начинающихся с /)
    if user_input.startswith('/'):
        handle_chat_command(user_input, state)
        return
    
    # Создаем новый чат если его нет
    if not state.current_chat_id:
        state.current_chat_id = state.chat_manager.create_new_chat()
    
    # Добавляем сообщение пользователя в чат
    if not state.chat_manager.add_message(state.current_chat_id, "user", user_input):
        st.error(f"❌ Не удалось сохранить сообщение пользователя (чат {state.current_chat_id}).")
        return
    
    # Отображаем сообщение пользователя
    with st.chat_message("user"):
        st.write(user_input)
    
    # Генерируем ответ AI
    with st.chat_message("assistant"):
        # Создаем placeholder для стриминга
        response_placeholder = st.empty()
        
        try:
            # Создаем системный промпт с инструментами
            system_prompt = create_chat_system_prompt_with_tools(state.data_context)
            
            # Получаем историю разговора
            chat_messages = state.chat_manager.get_chat_messages(state.current_chat_id)
            conversation_history = ""
            for msg in chat_messages[:-1]:  # Исключаем последнее сообщение
                conversation_history += f"\n{msg['role'].upper()}: {msg['content']}"
            
            # Создаем полный промпт
            full_prompt = f"""
{system_prompt}

ИСТОРИЯ РАЗГОВОРА:{conversation_history}

НОВЫЙ ВОПРОС ПОЛЬЗОВАТЕЛЯ: {user_input}

Используй инструменты для получения точных данных. ОБЯЗАТЕЛЬНО завершай задачу полностью - если просят план, составляй конкретный план, а не только анализируй данные. Отвечай персонально, конкретно и полезно. Используй эмодзи.
"""
            
            # Показываем начальное состояние генерации
            response_placeholder.markdown("🤖 *Генерирую ответ...*")
            
            # Получаем ответ от AI (может содержать запросы инструментов)
            ai_response = state.ai_coach.provider.generate_response(full_prompt, "")
            
            # Показываем состояние обработки инструментов
            response_placeholder.markdown("🔧 *Обрабатываю данные...*")
            
            # Обрабатываем инструменты в ответе
            final_response = process_tool_calls(ai_response)
            final_response = maybe_append_progress_report(state, user_input, final_response)
            
            # Симулируем стриминг финального ответа
            simulate_streaming_response(response_placeholder, final_response)
            
            # Сохраняем ответ в чат
            if not state.chat_manager.add_message(state.current_chat_id, "assistant", final_response):
                st.error(f"❌ Не удалось сохранить ответ AI в чат (чат {state.current_chat_id}).")
            
            # Озвучиваем ответ, если речевой синтез включен
            if state._session.get("speechcore_enabled", False):
                speak_text(final_response, state._session.get("speechcore_voice", "default"))
            
            # Гарантируем, что остаёмся на странице AI чата
            state.selected_page = "🤖 AI Коучинг"
            state.switch_to_chat_tab = True
            
            # Обновляем интерфейс для отображения нового сообщения
            st.rerun()
            
        except Exception as e:
            error_msg = f"❌ Ошибка AI: {e}"
            response_placeholder.markdown(error_msg)
            # Сохраняем ошибку в чат
            state.chat_manager.add_message(
                state.current_chat_id,
                "assistant", 
                error_msg
            )

def process_chat_message(user_input):
    """Обрабатывает сообщение пользователя в чате с поддержкой инструментов"""
    state = get_state_manager()
    # Добавляем сообщение пользователя
    state.chat_messages.append({"role": "user", "content": user_input})
    
    # Отображаем сообщение пользователя
    with st.chat_message("user"):
        st.write(user_input)
    
    # Генерируем ответ AI
    with st.chat_message("assistant"):
        with st.spinner("AI тренер анализирует данные..."):
            try:
                # Создаем системный промпт с инструментами
                system_prompt = create_chat_system_prompt_with_tools(state.data_context)
                
                # Собираем историю разговора
                conversation_history = ""
                for msg in state.chat_messages[:-1]:  # Исключаем последнее сообщение
                    conversation_history += f"\n{msg['role'].upper()}: {msg['content']}"
                
                # Создаем полный промпт
                full_prompt = f"""
{system_prompt}

ИСТОРИЯ РАЗГОВОРА:{conversation_history}

НОВЫЙ ВОПРОС ПОЛЬЗОВАТЕЛЯ: {user_input}

Используй инструменты для получения точных данных. ОБЯЗАТЕЛЬНО завершай задачу полностью - если просят план, составляй конкретный план, а не только анализируй данные. Отвечай персонально, конкретно и полезно. Используй эмодзи.
"""
                
                # Получаем ответ от AI (может содержать запросы инструментов)
                ai_response = state.ai_coach.provider.generate_response(full_prompt, "")
                
                # Обрабатываем инструменты в ответе
                final_response = process_tool_calls(ai_response)
                final_response = maybe_append_progress_report(state, user_input, final_response)
                
                # Отображаем финальный ответ
                st.markdown(final_response)
                
                # Сохраняем в историю
                state.chat_messages.append({"role": "assistant", "content": final_response})
                
            except Exception as e:
                st.error(f"❌ Ошибка AI: {e}")

def create_chat_system_prompt_with_tools(data_context):
    """Создает системный промпт с инструментами для доступа к данным"""
    state = get_state_manager()
    
    base_prompt = """
Ты — персональный AI тренер по выносливости с глубокими знаниями спортивной науки. 

У тебя есть доступ к мощным инструментам для анализа данных пользователя. Используй их для получения точной, актуальной информации.

ТВОИ ПРИНЦИПЫ:
• ВСЕГДА используй инструменты для получения конкретных данных
• ВСЕГДА завершай задачу полностью - не останавливайся на анализе
• Давай персонализированные, научно обоснованные советы
• Объясняй сложные концепции простым языком
• Предупреждай о рисках перетренированности и травм
• Поощряй постепенное развитие и терпение

ТВОИ ЭКСПЕРТИЗЫ:
• Анализ тренировочной нагрузки (TSS, CTL, ATL, TSB)
• Интерпретация HRV и состояния восстановления
• Планирование тренировок и периодизация
• Физиология выносливости и адаптации
• Предотвращение перетренированности

СТИЛЬ ОБЩЕНИЯ:
• Дружелюбный и мотивирующий
• Используй эмодзи для лучшего восприятия
• Структурируй ответы с заголовками и списками
• Будь конкретным с цифрами и фактами

ДАННЫЕ И ИНСТРУМЕНТЫ:
• Для запросов о шагах, калориях или ЧСС покоя ОБЯЗАТЕЛЬНО сначала вызывай инструмент **get_daily_health_stats** (укажи days при необходимости)
• Для readiness, VO₂max и статусов Garmin ОБЯЗАТЕЛЬНО сначала применяй **get_training_status** (для конкретных дат) или **analyze_training_status**
• Если вопрос требует период/дату, вызывай инструмент с параметром days/start/end, а затем цитируй фактические значения из результата
• Метрики CTL/ATL/TSB и анализ нагрузки получай через соответствующие инструменты, вместо общих оценок
• Если данных нет, явно сообщай об этом пользователю
"""
    
    # Добавляем описание инструментов
    tools_description = state.ai_tools.format_tool_descriptions_for_ai()
    
    return f"{base_prompt}\n\n{tools_description}"

def create_chat_system_prompt(data_context):
    """Создает системный промпт с полным контекстом данных пользователя (старая версия)"""
    from models.ai_data_context import AIDataContext
    
    base_prompt = """
Ты — персональный AI тренер по выносливости с глубокими знаниями спортивной науки. 

У тебя есть полный доступ к данным пользователя и ты должен давать персонализированные, научно обоснованные советы.

ТВОИ ПРИНЦИПЫ:
• Всегда основывайся на предоставленных данных пользователя
• Объясняй сложные концепции простым языком
• Давай конкретные, практические рекомендации
• Учитывай индивидуальные особенности и текущее состояние
• Предупреждай о рисках перетренированности и травм
• Поощряй постепенное развитие и терпение

ТВОИ ЭКСПЕРТИЗЫ:
• Анализ тренировочной нагрузки (TSS, CTL, ATL, TSB)
• Интерпретация HRV и состояния восстановления
• Планирование тренировок и периодизация
• Физиология выносливости и адаптации
• Предотвращение перетренированности
• Техника и тактика в видах спорта на выносливость

СТИЛЬ ОБЩЕНИЯ:
• Дружелюбный и мотивирующий
• Используй эмодзи для лучшего восприятия
• Структурируй ответы с заголовками и списками
• Будь конкретным, но не перегружай деталями
• Адаптируй сложность под уровень пользователя
"""
    
    if not data_context or not data_context['summary']['has_data']:
        return base_prompt + "\n\nВНИМАНИЕ: У пользователя нет данных тренировок. Давай общие рекомендации и объясни, как начать отслеживание тренировок."
    
    # Форматируем контекст данных
    context_formatter = AIDataContext(None)  # Не нужен database, только форматирование
    formatted_context = context_formatter.format_context_for_ai(data_context)
    
    return f"{base_prompt}\n\n{formatted_context}"

def process_tool_calls(ai_response):
    """Обрабатывает вызовы инструментов в ответе AI"""
    import re
    
    state = get_state_manager()
    
    # Ищем паттерны инструментов в формате [TOOL: tool_name, param=value]
    tool_pattern = r'\[TOOL:\s*([^,\]]+)(?:,\s*([^\]]*))?\]'
    
    def replace_tool_call(match):
        tool_name = match.group(1).strip()
        params_str = match.group(2).strip() if match.group(2) else ""
        
        # Парсим параметры
        params = {}
        if params_str:
            param_pairs = [p.strip() for p in params_str.split(',')]
            for pair in param_pairs:
                if '=' in pair:
                    key, value = pair.split('=', 1)
                    key = key.strip()
                    value = value.strip()
                    
                    # Пытаемся преобразовать в правильный тип
                    if value.isdigit():
                        params[key] = int(value)
                    elif value.replace('.', '').isdigit():
                        params[key] = float(value)
                    else:
                        params[key] = value.strip('"\'')
        
        # Выполняем инструмент
        try:
            result = state.ai_tools.execute_tool(tool_name, **params)
            
            if result.get('success'):
                # Форматируем результат для отображения
                data = result['result']
                formatted_result = format_tool_result(tool_name, data)
                return formatted_result
            else:
                return f"❌ Ошибка инструмента: {result.get('error', 'Неизвестная ошибка')}"
                
        except Exception as e:
            return f"❌ Ошибка выполнения {tool_name}: {str(e)}"
    
    # Заменяем все вызовы инструментов их результатами
    processed_response = re.sub(tool_pattern, replace_tool_call, ai_response)
    
    return processed_response

def speak_text(text: str, voice: str = "default"):
    """Озвучивает текст с помощью Web Speech API через JavaScript"""
    import re
    import json
    
    # Очищаем текст от markdown разметки для озвучивания
    # Удаляем markdown синтаксис, но оставляем читаемый текст
    clean_text = text
    
    # Удаляем markdown заголовки
    clean_text = re.sub(r'^#+\s+', '', clean_text, flags=re.MULTILINE)
    # Удаляем жирный текст
    clean_text = re.sub(r'\*\*(.+?)\*\*', r'\1', clean_text)
    # Удаляем курсив
    clean_text = re.sub(r'\*(.+?)\*', r'\1', clean_text)
    # Удаляем код
    clean_text = re.sub(r'`(.+?)`', r'\1', clean_text)
    # Удаляем ссылки
    clean_text = re.sub(r'\[(.+?)\]\(.+?\)', r'\1', clean_text)
    
    # Ограничиваем длину для озвучивания (слишком длинные тексты могут быть проблематичны)
    if len(clean_text) > 500:
        clean_text = clean_text[:500] + "..."
    
    # Экранируем текст для JavaScript
    clean_text_escaped = json.dumps(clean_text, ensure_ascii=False)
    
    # Создаем JavaScript код для озвучивания
    js_code = f"""
    <script>
    (function() {{
        if ('speechSynthesis' in window) {{
            // Останавливаем предыдущее озвучивание, если есть
            window.speechSynthesis.cancel();
            
            // Ждем загрузки голосов
            function speak() {{
                const utterance = new SpeechSynthesisUtterance({clean_text_escaped});
                
                // Настройка голоса
                utterance.lang = 'ru-RU';
                utterance.rate = 1.0;
                utterance.pitch = 1.0;
                utterance.volume = 1.0;
                
                // Пытаемся выбрать голос по предпочтению
                const voices = window.speechSynthesis.getVoices();
                if (voices.length > 0) {{
                    // Ищем русский голос
                    let selectedVoice = voices.find(v => v.lang.startsWith('ru'));
                    if (!selectedVoice) {{
                        // Если нет русского, берем первый доступный
                        selectedVoice = voices[0];
                    }}
                    utterance.voice = selectedVoice;
                }}
                
                window.speechSynthesis.speak(utterance);
            }}
            
            // Если голоса уже загружены, говорим сразу
            if (window.speechSynthesis.getVoices().length > 0) {{
                speak();
            }} else {{
                // Иначе ждем события загрузки голосов
                window.speechSynthesis.onvoiceschanged = speak;
            }}
        }} else {{
            console.warn('Speech synthesis not supported');
        }}
    }})();
    </script>
    """
    
    # Выполняем JavaScript через Streamlit
    import streamlit.components.v1 as components
    components.html(js_code, height=0)

def simulate_streaming_response(placeholder, text):
    """Симулирует стриминг вывода текста для лучшего UX"""
    import time
    import re
    
    # Разбиваем текст на "chunks" для имитации стриминга
    # Учитываем markdown разметку, чтобы не ломать форматирование
    
    # Сначала проверяем, нужно ли стримить (для коротких ответов можно сразу показать)
    if len(text) <= 100:
        placeholder.markdown(text)
        return
    
    # Разделяем на предложения и абзацы для более естественного стриминга
    # Улучшенный паттерн для сохранения markdown структуры
    sentences = re.split(r'(?<=[.!?])\s+|(?<=\n)(?=\n)|(?<=:)\n', text)
    current_text = ""
    
    for i, sentence in enumerate(sentences):
        current_text += sentence
        
        # Показываем текущий прогресс с курсором
        if i < len(sentences) - 1:
            display_text = current_text + " ▋"
        else:
            display_text = current_text
        
        # Используем обычный markdown для сохранения форматирования
        placeholder.markdown(display_text)
        
        # Добавляем небольшую задержку для эффекта печатания
        # Варьируем скорость в зависимости от длины предложения
        if len(sentence) > 50:
            time.sleep(0.25)  # Длинные предложения - больше пауза
        elif len(sentence) > 20:
            time.sleep(0.12) # Средние предложения
        else:
            time.sleep(0.04) # Короткие фразы
    
    # Финальное отображение без курсора
    placeholder.markdown(current_text)

PROGRESS_KEYWORDS = (
    "прогресс за месяц",
    "прогресс за последний месяц",
    "покажи прогресс за месяц",
    "итоги месяца",
    "итоги за месяц",
    "month progress",
    "monthly progress"
)


def format_tool_result(tool_name, data):
    """Форматирует результат инструмента для красивого отображения"""
    
    if tool_name == "get_performance_metrics":
        # Определяем эмодзи для TSB
        tsb_emoji = "🟢" if data['tsb'] > 5 else "🟡" if data['tsb'] > -10 else "🟠" if data['tsb'] > -25 else "🔴"
        
        return f"""
## 📊 Текущие метрики производительности

### 🎯 Модель Банистера:
• **CTL** (хроническая нагрузка): **{data['ctl']:.1f}** 📈
• **ATL** (острая нагрузка): **{data['atl']:.1f}** ⚡  
• **TSB** (баланс стресса): **{data['tsb']:+.1f}** {tsb_emoji}

### 🏃‍♂️ Анализ формы:
• **Текущая форма:** {data['form_state']}
• **Тренд фитнеса:** {data['fitness_trend']}
"""
    
    elif tool_name == "get_recent_activities":
        if data['count'] == 0:
            return "📭 **Нет недавних активностей**"
        
        # Эмодзи для спортов
        sport_emojis = {
            'cycling': '🚴', 'running': '🏃', 'swimming': '🏊', 
            'open_water_swimming': '🏊‍♂️', 'walking': '🚶'
        }
        
        activities_text = f"## 🏃‍♂️ Последние {min(5, data['count'])} тренировок:\n\n"
        for i, activity in enumerate(data['activities'][:5], 1):
            sport = activity.get('sport', 'unknown')
            emoji = sport_emojis.get(sport, '⚡')
            description = activity.get('description', f"{sport} - {activity.get('duration_minutes', 0):.0f}мин")
            activities_text += f"{i}. **{activity['date']}** {emoji} {description}\n"
        
        return activities_text
    
    elif tool_name == "get_activities":
        count = data.get("count", 0)
        period = data.get("period_days")
        activities = data.get("activities") or []
        
        if count == 0 or not activities:
            period_text = f"за {period} дней" if period is not None else ""
            return f"📭 **Нет тренировок {period_text}**"
        
        total_tss = sum(float(a.get("tss", 0) or 0) for a in activities)
        total_duration = sum(float(a.get("duration_minutes", 0) or 0) for a in activities)
        
        header = f"## 🏃‍♂️ Тренировки за {period} дней\n\n"
        summary = (
            f"- Всего занятий: **{count}**\n"
            f"- Суммарный TSS: **{total_tss:.0f}**\n"
            f"- Общее время: **{total_duration/60:.1f} ч**\n\n"
        )
        
        sport_emojis = {
            'cycling': '🚴', 'running': '🏃', 'swimming': '🏊',
            'open_water_swimming': '🏊‍♂️', 'walking': '🚶', 'strength': '💪',
        }
        
        rows = []
        for activity in activities[:7]:
            date = activity.get("date", "N/A")
            sport = activity.get("sport", "unknown")
            emoji = sport_emojis.get(sport.lower(), '⚡') if isinstance(sport, str) else '⚡'
            duration = activity.get("duration_minutes", 0) or 0
            tss = activity.get("tss", 0) or 0
            description = activity.get("description")
            if not description:
                description = f"{sport} — {duration:.0f} мин, TSS {tss:.0f}"
            rows.append(f"| {date} | {emoji} {description} |")
        
        table_header = "| Дата | Сессия |\n| --- | --- |\n"
        table_body = "\n".join(rows)
        
        return header + summary + table_header + table_body
    
    elif tool_name == "analyze_hrv_trends":
        recovery_emoji = {"отличное": "🟢", "хорошее": "🟡", "удовлетворительное": "🟠", "плохое": "🔴"}
        trend_emoji = {"improving": "📈", "declining": "📉"}
        
        return f"""
**💓 Анализ HRV:**
• Текущий RMSSD: {data['current_rmssd']:.1f} мс
• Среднее за 7 дней: {data['recent_avg_7days']:.1f} мс
• Базовый уровень: {data['baseline_median']:.1f} мс
• Тренд: {trend_emoji.get(data['trend_direction'], '')} {data['trend_direction']}
• Восстановление: {recovery_emoji.get(data['recovery_state'], '')} {data['recovery_state']}
"""
    
    elif tool_name == "get_activity_stats":
        return f"""
**📈 Статистика тренировок за {data['period_days']} дней:**
• Всего тренировок: {data['total_activities']}
• Общее время: {data['total_duration_hours']:.1f} ч
• Общий TSS: {data['total_tss']:.0f}
• Частота: {data['activities_per_week']:.1f} раз в неделю
• Средний TSS: {data['avg_tss_per_session']:.1f}
"""
    
    elif tool_name == "compare_periods":
        message = data.get("message")
        period1 = data.get("period1_days")
        period2 = data.get("period2_days")
        
        if message:
            fallback = data.get("fallback", {})
            summary_lines = [f"### {message}"]
            
            recent_stats = fallback.get("recent_activity_stats")
            if isinstance(recent_stats, dict):
                summary_lines.append(
                    f"- Последний период: {recent_stats.get('total_activities', 0)} тренировок, "
                    f"{recent_stats.get('total_duration_hours', 0):.1f} ч, TSS {recent_stats.get('total_tss', 0):.0f}"
                )
            
            load_summary = fallback.get("training_load")
            if isinstance(load_summary, dict):
                summary_lines.append(
                    f"- Тренд нагрузки: {load_summary.get('load_trend', 'н/д')}"
                )
            
            summary_lines.append(
                "Попробуй обновить данные, чтобы сравнить периоды заново."
            )
            
            return "## 📈 Прогресс за период\n\n" + "\n".join(summary_lines)
        
        recent = data.get("recent_period", {}) or {}
        previous = data.get("previous_period", {}) or {}
        comparison = data.get("comparison", {}) or {}
        
        def fmt_hours(minutes: float) -> str:
            return f"{(minutes or 0) / 60:.1f} ч"
        
        def fmt_delta(value: Optional[float], unit: str = "", precision: int = 0) -> str:
            if value is None:
                return "0"
            sign = "+" if value > 0 else ""
            formatted = f"{sign}{value:.{precision}f}" if precision > 0 else f"{sign}{int(value)}"
            return f"{formatted}{unit}"
        
        def arrow(value: Optional[float]) -> str:
            if value is None:
                return "→"
            if value > 0:
                return "↑"
            if value < 0:
                return "↓"
            return "→"
        
        recent_duration = recent.get("total_duration", 0.0)
        previous_duration = previous.get("total_duration", 0.0)
        volume_change = comparison.get("volume_change")
        duration_change_hours = (volume_change or 0) / 60 if volume_change is not None else None
        
        summary_block = [
            "## 📈 Прогресс за период",
            "",
            "**Итоги текущего периода**",
            f"- Тренировок: **{recent.get('activity_count', 0)}**",
            f"- Общее время: **{fmt_hours(recent_duration)}**",
            f"- Суммарный TSS: **{recent.get('total_tss', 0):.0f}**",
            f"- Частота: **{recent.get('activities_per_week', 0):.1f} / нед**"
        ]
        
        if not previous.get("no_data"):
            summary_block.extend([
                "",
                f"**Динамика vs предыдущие {period2 or 'предыдущие'} дней**",
                f"- Тренировок: {comparison.get('activity_count_change', 0):+d} {arrow(comparison.get('activity_count_change'))}",
                f"- Объём: {fmt_delta(duration_change_hours, ' ч', 1)} {arrow(duration_change_hours)}",
                f"- TSS: {fmt_delta(comparison.get('tss_change'), '', 0)} {arrow(comparison.get('tss_change'))}"
            ])
        else:
            summary_block.append("\nНет данных для сравнения с предыдущим периодом.")
        
        return "\n".join(summary_block)
    
    elif tool_name == "analyze_training_load":
        if data.get("message"):
            return f"ℹ️ **{data['message']}**"
        
        intensity = data.get("intensity_distribution", {})
        weekly = data.get("weekly_breakdown", []) or []
        
        intensity_lines = [
            f"- Низкая: {intensity.get('low_intensity_percent', 0):.1f}%",
            f"- Умеренная: {intensity.get('moderate_intensity_percent', 0):.1f}%",
            f"- Высокая: {intensity.get('high_intensity_percent', 0):.1f}%"
        ] if intensity else ["- Нет данных по зонам интенсивности"]
        
        if weekly:
            table_rows = [
                "| Неделя | Сессий | TSS | Часы |",
                "| --- | --- | --- | --- |"
            ]
            for week in weekly[:4]:
                hours = (week.get("total_duration", 0) or 0) / 60
                table_rows.append(
                    f"| {week.get('week', '—')} | {week.get('session_count', 0)} | "
                    f"{week.get('total_tss', 0):.0f} | {hours:.1f} |"
                )
            weekly_section = "\n".join(table_rows)
        else:
            weekly_section = "Нет разбивки по неделям."
        
    
    elif tool_name == "analyze_recovery_state":
        factors = data.get("factors", [])
        hrv_data = data.get("hrv", {})
        training_load = data.get("training_load", {})
        
        # Анализ HRV
        hrv_section = ""
        if hrv_data:
            current_rmssd = hrv_data.get("current_rmssd", 0)
            baseline_rmssd = hrv_data.get("baseline_rmssd", 0)
            deviation = hrv_data.get("deviation_percent", 0)
            
            if deviation > 10:
                hrv_emoji = "🟢"
                hrv_status = "отличное"
            elif deviation > -5:
                hrv_emoji = "🟡"
                hrv_status = "хорошее"
            elif deviation > -15:
                hrv_emoji = "🟠"
                hrv_status = "удовлетворительное"
            else:
                hrv_emoji = "🔴"
                hrv_status = "требует внимания"
            
            hrv_section = f"""
### 💓 HRV Анализ:
• **Текущий RMSSD:** {current_rmssd:.1f} мс {hrv_emoji}
• **Базовый уровень:** {baseline_rmssd:.1f} мс
• **Отклонение:** {deviation:+.1f}% ({hrv_status})"""
        
        # Анализ нагрузки
        load_section = ""
        if training_load:
            week_tss = training_load.get("week_tss", 0)
            session_count = training_load.get("session_count", 0)
            avg_tss = training_load.get("avg_tss_per_session", 0)
            
            if week_tss > 400:
                load_emoji = "🔴"
                load_status = "высокая"
            elif week_tss > 250:
                load_emoji = "🟡"
                load_status = "умеренная"
            else:
                load_emoji = "🟢"
                load_status = "низкая"
            
            load_section = f"""
### ⚡ Недельная нагрузка:
• **TSS за неделю:** {week_tss:.0f} {load_emoji} ({load_status})
• **Тренировок:** {session_count}
• **Средний TSS:** {avg_tss:.1f}"""
        
        # Рекомендации и факторы
        factors_section = ""
        if factors:
            factors_section = f"""
### 🎯 Анализ и рекомендации:
{chr(10).join([f"• {factor}" for factor in factors[:5]])}"""
        
        return f"""
## 🔋 Анализ состояния восстановления
{hrv_section}
{load_section}
{factors_section}"""
    
    elif tool_name == "get_training_status":
        if not isinstance(data, dict):
            return f"ℹ️ **{data}**"
        if data.get("message"):
            return f"ℹ️ **{data['message']}**"
        
        latest = data.get("latest", {})
        summary = data.get("summary", {})
        
        def fmt_number(value, fmt: str = ".1f", default: str = "н/д"):
            if value is None:
                return default
            try:
                if pd.isna(value):
                    return default
                return format(float(value), fmt)
            except (TypeError, ValueError):
                return default
        
        status_distribution = summary.get("status_distribution", {})
        distribution_lines = [
            f"• {status}: {count}" for status, count in list(status_distribution.items())[:5]
        ] if status_distribution else ["• Нет статистики по статусам"]

        history = data.get("history", [])
        readiness_rows = []
        for entry in history:
            readiness = entry.get("training_readiness")
            date_value = entry.get("date")
            if isinstance(date_value, str):
                date_str = date_value
            elif hasattr(date_value, "strftime"):
                date_str = date_value.strftime("%Y-%m-%d")
            else:
                date_str = str(date_value)
            if readiness is not None and not (hasattr(pd, "isna") and pd.isna(readiness)):
                readiness_rows.append((date_str, readiness))
        readiness_rows = readiness_rows[:7]
        if readiness_rows:
            readiness_table = "\n".join([
                f"| {date} | {fmt_number(value, '.0f')} / 100 |"
                for date, value in readiness_rows
            ])
            readiness_block = f"""
### 📅 Readiness по датам:
| Дата | Readiness |
| --- | --- |
{readiness_table}
"""
        else:
            readiness_block = "\n### 📅 Readiness по датам:\n• Нет данных по дням\n"
        
        return f"""
## 📈 Статус тренированности (последние {data.get('period_days', 30)} дней)

### 🔝 Последний статус:
• Статус Garmin: {latest.get('training_status', 'н/д')}
• Readiness: {fmt_number(latest.get('training_readiness'), '.0f')} / 100
• Нагрузка 7 дней: {fmt_number(latest.get('training_load_7d'), '.0f')}
• VO₂max: {fmt_number(latest.get('vo2_max'), '.1f')}

### 📊 Средние значения:
• Readiness: {fmt_number(summary.get('avg_training_readiness'), '.1f')} / 100
• Нагрузка (7д): {fmt_number(summary.get('avg_training_load_7d'), '.1f')}
• VO₂max: {fmt_number(summary.get('avg_vo2_max'), '.1f')}

### 🧭 Распределение статусов:
{chr(10).join(distribution_lines)}
{readiness_block}
"""
    
    elif tool_name == "analyze_training_status":
        if not isinstance(data, dict):
            return f"ℹ️ **{data}**"
        if data.get("message"):
            return f"ℹ️ **{data['message']}**"
        
        insights = data.get("insights", [])
        latest = data.get("latest", {})
        readiness = data.get("readiness_assessment", {})
        load = data.get("load_assessment", {})
        
        def fmt_section(section: Dict[str, Any], default: str) -> str:
            lines = [value for value in section.values() if isinstance(value, str)]
            return chr(10).join([f"• {line}" for line in lines]) if lines else default
        
        return f"""
## 🧠 Анализ статуса тренированности

### 🔝 Последний статус:
• {latest.get('summary', 'Нет данных')}

### 💡 Ключевые выводы:
{chr(10).join([f"• {item}" for item in insights]) if insights else "• Нет выводов — недостаточно данных"}

### 📈 Readiness:
{fmt_section(readiness, "• Недостаточно данных по readiness")}

### ⚙️ Нагрузка:
{fmt_section(load, "• Недостаточно данных по нагрузке")}
"""
    
    elif tool_name == "get_daily_health_stats":
        if not isinstance(data, dict):
            return f"ℹ️ **{data}**"
        if data.get("message"):
            return f"ℹ️ **{data['message']}**"
        
        stats = data.get("stats", {})
        trend = data.get("trend_steps", "н/д")
        recent = data.get("recent_entries", [])
        
        def fmt_number(value, fmt: str = ".1f", default: str = "н/д"):
            if value is None:
                return default
            try:
                if pd.isna(value):
                    return default
                return format(float(value), fmt)
            except (TypeError, ValueError):
                return default
        
        recent_lines = []
        for entry in recent[:5]:
            date = entry.get("date")
            steps = fmt_number(entry.get("steps"), ".0f")
            resting_hr = fmt_number(entry.get("resting_hr"), ".0f")
            active_minutes = fmt_number(entry.get("active_minutes"), ".0f")
            recent_lines.append(f"• {date}: шаги {steps}, ЧСС покоя {resting_hr}, активность {active_minutes} мин")
        
        return f"""
## 🏥 Ежедневные показатели здоровья ({data.get('period_days', 30)} дней)

### 📊 Средние значения:
• Шаги: {fmt_number(stats.get('avg_steps'), '.0f')} в день
• ЧСС покоя: {fmt_number(stats.get('avg_resting_hr'), '.1f')} уд/мин
• Активные минуты: {fmt_number(stats.get('avg_active_minutes'), '.1f')} мин/день
• Активные калории: {fmt_number(stats.get('avg_calories_active'), '.0f')} ккал/день

### 📈 Тренд шагов: {trend}

### 🗓️ Последние дни:
{chr(10).join(recent_lines) if recent_lines else "• Нет свежих записей"}
"""
    
    elif tool_name == "get_activities_by_date_range":
        if data['count'] == 0:
            return f"📭 **Нет тренировок в период {data['period']}**"
        
        stats = data['statistics']
        
        # Форматируем виды спорта с эмодзи
        sport_emojis = {
            'cycling': '🚴', 'running': '🏃', 'swimming': '🏊', 
            'open_water_swimming': '🏊‍♂️', 'walking': '🚶',
            'strength': '💪', 'yoga': '🧘', 'other': '⚡'
        }
        
        sports_text = []
        for sport, count in stats['sports_distribution'].items():
            emoji = sport_emojis.get(sport, '⚡')
            sports_text.append(f"{emoji} {sport}: {count}")
        
        # Топ-5 тренировок с хорошим форматированием
        activities_preview = ""
        if 'activities' in data and data['activities']:
            activities_preview = "\n\n**📋 Некоторые тренировки:**"
            for i, activity in enumerate(data['activities'][:5], 1):
                sport_emoji = sport_emojis.get(activity['sport'], '⚡')
                date_formatted = activity['date']
                activities_preview += f"\n{i}. **{date_formatted}** {sport_emoji} {activity['sport']} - {activity['duration_minutes']:.0f}мин (TSS: {activity['tss']:.0f})"
        
        return f"""
## 📊 Тренировки за период {data['period']}

### 📈 Основная статистика:
• **🏃‍♂️ Всего тренировок: {data['count']}**
• **⏱️ Общее время: {stats['total_duration_hours']:.1f} часов**
• **📈 Общий TSS: {stats['total_tss']:.0f}**
• **🎯 Средний TSS: {stats['avg_tss_per_session']:.1f}**
• **🏃 Дистанция: {stats['total_distance_km']:.1f} км**

### 🏆 Виды активности:
{chr(10).join([f"• {sport}" for sport in sports_text])}
{activities_preview}"""
    
    elif tool_name == "get_sleep_data":
        if not data.get('has_data', True):
            return f"😴 **{data.get('message', 'Нет данных сна')}**"
        
        # Рассчитываем средние значения из recent_sleep данных
        recent_sleep = data.get('recent_sleep', [])
        if recent_sleep:
            total_hours = []
            sleep_scores = []
            for record in recent_sleep:
                if record.get('total_sleep_hours') is not None:
                    total_hours.append(record['total_sleep_hours'])
                if record.get('sleep_score') is not None:
                    sleep_scores.append(record['sleep_score'])
            
            avg_hours = sum(total_hours) / len(total_hours) if total_hours else 0
            avg_score = sum(sleep_scores) / len(sleep_scores) if sleep_scores else 0
            
            # Форматируем последний сон
            latest_sleep = recent_sleep[0] if recent_sleep else {}
            recent_summary = f"Продолжительность: {latest_sleep.get('total_sleep_hours', 'н/д')}ч, "
            recent_summary += f"Качество: {latest_sleep.get('sleep_score', 'н/д')}/100, "
            recent_summary += f"Эффективность: {latest_sleep.get('sleep_efficiency', 'н/д')}%"
        else:
            avg_hours = 0
            avg_score = 0
            recent_summary = "Данные недоступны"
        
        return f"""
## 😴 Данные сна за последние {data.get('period_days', 30)} дней

### 📊 Основная информация:
• **Всего записей:** {data.get('data_points', 0)}
• **Среднее время сна:** {avg_hours:.1f} часов
• **Средняя оценка сна:** {avg_score:.1f}/100

### 🌙 Последний сон:
{recent_summary}"""
    
    elif tool_name == "get_sleep_stats":
        if not data.get('has_data', True):
            return f"😴 **{data.get('message', 'Нет данных сна')}**"
        
        stats = data.get('statistics', {})
        quality = stats.get('current_sleep_quality', 'не определено')
        
        # Эмодзи для качества сна
        quality_emoji = "🟢" if "отличное" in quality.lower() else "🟡" if "хорошее" in quality.lower() else "🟠" if "удовлетворительное" in quality.lower() else "🔴"
        
        # Рассчитываем проценты фаз сна
        avg_total = stats.get('avg_sleep_hours', 0) * 60  # переводим в минуты
        deep_pct = (stats.get('avg_deep_sleep_minutes', 0) / avg_total * 100) if avg_total > 0 else 0
        rem_pct = (stats.get('avg_rem_sleep_minutes', 0) / avg_total * 100) if avg_total > 0 else 0
        light_pct = 100 - deep_pct - rem_pct if (deep_pct + rem_pct) <= 100 else 0
        
        return f"""
## 😴 Статистика сна за {stats.get('period_days', 30)} дней

### 🎯 Общая оценка: {quality_emoji} {quality}

### 📈 Средние показатели:
• **Продолжительность:** {stats.get('avg_sleep_hours', 0):.1f} часов
• **Качество сна:** {stats.get('avg_sleep_score', 0):.1f}/100
• **Эффективность:** {stats.get('avg_sleep_efficiency', 0):.1f}%
• **Пробуждения:** {stats.get('avg_awakenings', 0):.1f} раз за ночь

### 🌀 Фазы сна:
• **Глубокий сон:** {stats.get('avg_deep_sleep_minutes', 0):.0f} мин ({deep_pct:.1f}%)
• **Легкий сон:** Расчетное ({light_pct:.1f}%)
• **REM сон:** {stats.get('avg_rem_sleep_minutes', 0):.0f} мин ({rem_pct:.1f}%)"""
    
    elif tool_name == "analyze_sleep_patterns":
        if not data.get('has_data', True):
            return f"😴 **{data.get('message', 'Нет данных для анализа сна')}**"
        
        patterns = data.get('patterns', {})
        recommendations = patterns.get('recommendations', [])
        
        # Форматируем основные паттерны
        main_patterns = []
        if patterns.get('avg_sleep_duration'):
            main_patterns.append(f"• **Средняя продолжительность:** {patterns['avg_sleep_duration']}")
        if patterns.get('sleep_consistency'):
            main_patterns.append(f"• **Постоянство сна:** {patterns['sleep_consistency']}")
        if patterns.get('optimal_sleep_adherence'):
            main_patterns.append(f"• **Следование рекомендациям:** {patterns['optimal_sleep_adherence']}")
        
        # Качество и тренды
        quality_trends = []
        if patterns.get('avg_sleep_score'):
            quality_trends.append(f"• **Средняя оценка качества:** {patterns['avg_sleep_score']}")
        if patterns.get('sleep_trend'):
            quality_trends.append(f"• **Тренд:** {patterns['sleep_trend']}")
        
        # Фазы сна
        phases_text = []
        if patterns.get('deep_sleep_percentage'):
            phases_text.append(f"• **Глубокий сон:** {patterns['deep_sleep_percentage']}")
        if patterns.get('rem_sleep_percentage'):
            phases_text.append(f"• **REM сон:** {patterns['rem_sleep_percentage']}")
        
        # Рекомендации
        recommendations_text = ""
        if recommendations:
            recommendations_text = f"""
### 💡 Рекомендации:
{chr(10).join([f"• {rec}" for rec in recommendations[:5]])}"""
        
        return f"""
## 😴 Анализ паттернов сна за {data.get('period_days', 30)} дней

### 📊 Основные паттерны:
{chr(10).join(main_patterns) if main_patterns else "• Недостаточно данных для анализа"}

### 📈 Качество и тренды:
{chr(10).join(quality_trends) if quality_trends else "• Данные о качестве недоступны"}

### 🌀 Фазы сна:
{chr(10).join(phases_text) if phases_text else "• Данные о фазах недоступны"}
{recommendations_text}"""
    
    else:
        # Общий формат для остальных инструментов
        if isinstance(data, dict):
            # Если есть ошибка или сообщение
            if 'message' in data:
                return f"ℹ️ **{data['message']}**"
            elif 'error' in data:
                return f"❌ **Ошибка:** {data['error']}"
            
            # Общий формат для сложных данных
            result_text = f"## 📊 Результат: {tool_name.replace('_', ' ').title()}\n\n"
            
            # Сортируем ключи для лучшего отображения  
            important_keys = ['count', 'total_tss', 'period_days', 'current_rmssd']
            other_keys = [k for k in data.keys() if k not in important_keys and not k.startswith('_')]
            
            for key in important_keys:
                if key in data:
                    result_text += f"• **{key.replace('_', ' ').title()}:** {data[key]}\n"
            
            for key in other_keys[:10]:  # Ограничиваем количество
                value = data[key]
                if isinstance(value, (dict, list)) and len(str(value)) > 100:
                    result_text += f"• **{key.replace('_', ' ').title()}:** [данные доступны]\n"
                else:
                    result_text += f"• **{key.replace('_', ' ').title()}:** {value}\n"
                    
            return result_text
        else:
            return f"**📊 {tool_name.replace('_', ' ').title()}:** {str(data)}"


def is_progress_request(text: Optional[str]) -> bool:
    """Определяет, просит ли пользователь отчёт по прогрессу за месяц."""
    if not text:
        return False
    lowered = text.lower()
    if "прогресс" in lowered and "меся" in lowered:
        return True
    return any(keyword in lowered for keyword in PROGRESS_KEYWORDS)


def maybe_append_progress_report(state, user_input: Optional[str], final_response: str) -> str:
    """Добавляет отчёт о прогрессе, если пользователь его запрашивал, а ответ его не содержит."""
    if not is_progress_request(user_input):
        return final_response
    
    filtered_existing = _filter_progress_sections(final_response)
    if filtered_existing and "## 📈 Прогресс" in filtered_existing:
        return filtered_existing
    
    progress_report = build_progress_report(state)
    if not progress_report:
        return filtered_existing or final_response
    
    base_text = filtered_existing.strip()
    if base_text and progress_report.strip() == base_text:
        return base_text
    
    if base_text:
        return f"{base_text}\n\n{progress_report}".strip()
    
    return progress_report.strip()


def build_progress_report(state, period_days: int = 30, previous_days: Optional[int] = None) -> Optional[str]:
    """Собирает структурированный отчёт о прогрессе, восстановлении и сне."""
    if state is None:
        return None
    
    ai_tools = getattr(state, "ai_tools", None)
    if ai_tools is None:
        return None
    
    previous_days = previous_days or period_days
    
    sections: List[str] = []
    compare_data: Optional[Dict[str, Any]] = None
    
    compare_result = ai_tools.execute_tool("compare_periods", period1_days=period_days, period2_days=previous_days)
    if compare_result.get("success"):
        compare_data = compare_result.get("result")
        if compare_data:
            compare_block = format_tool_result("compare_periods", compare_data)
            if compare_block:
                sections.append(compare_block.strip())
    else:
        error_msg = compare_result.get("error")
        if error_msg:
            sections.append(f"ℹ️ **Не удалось сформировать сравнение:** {error_msg}")
    
    load_data: Optional[Dict[str, Any]] = None
    load_result = ai_tools.execute_tool("analyze_training_load", days=period_days)
    if load_result.get("success"):
        potential_load = load_result.get("result")
        if isinstance(potential_load, dict) and potential_load:
            load_data = potential_load
    
    hrv_data: Optional[Dict[str, Any]] = None
    hrv_result = ai_tools.execute_tool("analyze_hrv_trends", days=period_days)
    if hrv_result.get("success"):
        potential_hrv = hrv_result.get("result")
        if isinstance(potential_hrv, dict) and potential_hrv:
            hrv_data = potential_hrv
    
    recovery_section = _format_recovery_section(load_data, hrv_data, period_days)
    if recovery_section:
        sections.append(recovery_section)
    
    sleep_data: Optional[Dict[str, Any]] = None
    sleep_result = ai_tools.execute_tool("get_sleep_stats", days=period_days)
    if sleep_result.get("success"):
        sleep_data = sleep_result.get("result")
        if isinstance(sleep_data, dict) and sleep_data.get("has_data"):
            sections.append(_format_sleep_section(sleep_data))
    
    recommendations = _generate_progress_recommendations(compare_data, load_data, hrv_data, sleep_data)
    if recommendations:
        bullet_lines = [f"{idx}. {rec}" for idx, rec in enumerate(recommendations, 1)]
        sections.append("### Что сделать дальше\n" + "\n".join(bullet_lines))
    
    sections.append("_Хочешь, составлю план на следующую неделю или разберу конкретный вид спорта?_")
    
    return "\n\n".join(section for section in sections if section and section.strip())


def _format_recovery_section(
    load_data: Optional[Dict[str, Any]],
    hrv_data: Optional[Dict[str, Any]],
    period_days: int
) -> str:
    """Формирует блок про нагрузку и восстановление в рамках периода."""
    if not load_data and not hrv_data:
        return ""
    
    lines: List[str] = [f"### Нагрузка и восстановление ({period_days} дней)"]
    
    if load_data:
        trend = load_data.get("load_trend", "н/д")
        weekly_breakdown = load_data.get("weekly_breakdown") or []
        total_week_tss = sum(float(week.get("total_tss", 0) or 0) for week in weekly_breakdown)
        avg_week_tss = total_week_tss / len(weekly_breakdown) if weekly_breakdown else 0.0
        avg_sessions = (
            sum(float(week.get("session_count", 0) or 0) for week in weekly_breakdown) / len(weekly_breakdown)
            if weekly_breakdown else 0.0
        )
        intensity = load_data.get("intensity_distribution", {})
        
        lines.append(f"- Тренд нагрузки: {trend}")
        if avg_week_tss > 0:
            lines.append(f"- Средний недельный TSS: {avg_week_tss:.0f} при {avg_sessions:.1f} тренировок/нед")
        if intensity:
            lines.append(
                "- Распределение интенсивности: "
                f"{intensity.get('low_intensity_percent', 0):.0f}% низк · "
                f"{intensity.get('moderate_intensity_percent', 0):.0f}% умер · "
                f"{intensity.get('high_intensity_percent', 0):.0f}% высок"
            )
    
    if hrv_data:
        current = hrv_data.get("current_rmssd")
        recent_avg = hrv_data.get("recent_avg_7days")
        baseline = hrv_data.get("baseline_median")
        trend = hrv_data.get("trend_direction")
        recovery_state = hrv_data.get("recovery_state")
        
        trend_text = _describe_hrv_trend(trend)
        recovery_label = _describe_recovery_state(recovery_state)
        
        lines.append(
            "- HRV (RMSSD): "
            f"{float(current or 0):.1f} мс (7д {float(recent_avg or 0):.1f} мс, "
            f"база {float(baseline or 0):.1f} мс) — {trend_text}, {recovery_label}"
        )
    
    return "\n".join(lines)


def _describe_hrv_trend(direction: Optional[str]) -> str:
    mapping = {
        "improving": "тренд растёт",
        "declining": "тренд снижается",
        "stable": "тренд стабильный"
    }
    return mapping.get(direction, "тренд не определён")


def _describe_recovery_state(state: Optional[str]) -> str:
    mapping = {
        "excellent": "восстановление отличное",
        "good": "восстановление хорошее",
        "fair": "восстановление умеренное",
        "poor": "восстановление требует внимания"
    }
    return mapping.get(state, "восстановление под контролем")


def _format_sleep_section(sleep_data: Dict[str, Any]) -> str:
    """Формирует блок про сон."""
    stats = sleep_data.get("statistics", {})
    if not stats:
        return ""
    
    lines = ["### Сон"]
    
    avg_hours = stats.get("avg_sleep_hours")
    if avg_hours is not None:
        lines.append(f"- Средняя продолжительность: {avg_hours:.1f} ч")
    
    avg_score = stats.get("avg_sleep_score")
    if avg_score is not None:
        lines.append(f"- Средняя оценка: {avg_score:.0f}/100")
    
    avg_efficiency = stats.get("avg_sleep_efficiency")
    if avg_efficiency is not None:
        lines.append(f"- Эффективность: {avg_efficiency:.1f}%")
    
    lines.append(f"- Текущее качество: {stats.get('current_sleep_quality', 'н/д')}")
    
    return "\n".join(lines)


def _generate_progress_recommendations(
    compare_data: Optional[Dict[str, Any]],
    load_data: Optional[Dict[str, Any]],
    hrv_data: Optional[Dict[str, Any]],
    sleep_data: Optional[Dict[str, Any]]
) -> List[str]:
    """Создаёт список рекомендуемых действий на основе данных."""
    recs: List[str] = []
    
    if compare_data:
        comparison = compare_data.get("comparison", {}) or {}
        tss_change = comparison.get("tss_change")
        duration_change = comparison.get("volume_change")
        activity_change = comparison.get("activity_count_change")
        
        if isinstance(tss_change, (int, float)):
            if tss_change < -40:
                recs.append("Верни одну интервальную сессию средней интенсивности, чтобы остановить спад нагрузки.")
            elif tss_change > 60:
                recs.append("Сохраняй объём, но закладывай лёгкий день после тяжёлых тренировок — нагрузка растёт.")
        
        if isinstance(duration_change, (int, float)) and duration_change < -120:
            recs.append("Добавь длительную тренировку на выносливость (60–75 мин), чтобы подтянуть объём.")
        
        if isinstance(activity_change, (int, float)) and activity_change < 0:
            recs.append("Планируй минимум 5 качественных сессий в неделю, чтобы удержать частоту тренировок.")
    
    if load_data:
        weekly_breakdown = load_data.get("weekly_breakdown") or []
        avg_week_tss = (
            sum(float(week.get("total_tss", 0) or 0) for week in weekly_breakdown) / len(weekly_breakdown)
            if weekly_breakdown else 0.0
        )
        trend = (load_data.get("load_trend") or "").lower()
        intensity = load_data.get("intensity_distribution", {})
        
        if avg_week_tss > 380:
            recs.append("Нагрузка за месяц высокая — планируй день восстановления после каждой тяжёлой сессии.")
        elif avg_week_tss < 220 and (trend in ("снижение", "низкий") or "decreasing" in trend):
            recs.append("Добавь интервальную работу средней интенсивности, чтобы вернуть растущий тренд нагрузки.")
        
        high_intensity = intensity.get("high_intensity_percent")
        if isinstance(high_intensity, (int, float)) and high_intensity < 10 and avg_week_tss >= 250:
            recs.append("Увеличь долю высокоинтенсивных блоков до 12–15%, чтобы ускорить прогресс.")
    
    if hrv_data:
        current = hrv_data.get("current_rmssd")
        baseline = hrv_data.get("baseline_median")
        if isinstance(current, (int, float)) and isinstance(baseline, (int, float)) and baseline > 0:
            deviation = (current - baseline) / baseline * 100
            if deviation < -5:
                recs.append("HRV ниже базы — включи активное восстановление и удлини сон на 30–45 минут.")
            elif deviation > 8:
                recs.append("HRV стабильно высокий — можно добавить качественную интервальную работу.")
    
    if sleep_data and sleep_data.get("has_data"):
        stats = sleep_data.get("statistics", {})
        avg_hours = stats.get("avg_sleep_hours")
        if isinstance(avg_hours, (int, float)) and avg_hours < 7:
            recs.append("Повысь среднюю продолжительность сна до 7–7.5 ч, это ускорит восстановление.")
    
    # Удаляем дубликаты, сохраняем порядок и ограничиваем до трёх пунктов
    unique_recs: List[str] = []
    seen = set()
    for rec in recs:
        if rec not in seen:
            unique_recs.append(rec)
            seen.add(rec)
        if len(unique_recs) >= 3:
            break
    
    if not unique_recs:
        unique_recs.append("Готов помочь составить персональный план — просто напомни, какие цели приоритетны.")
    
    return unique_recs


def _filter_progress_sections(text: str) -> str:
    """Удаляет инструментальные блоки, оставляя только прогресс и свободный текст."""
    if not text or not text.strip():
        return ""
    
    import re
    
    sections = re.split(r'(?=^## )', text, flags=re.MULTILINE)
    kept: List[str] = []
    
    for section in sections:
        stripped = section.strip()
        if not stripped:
            continue
        if stripped.startswith("## "):
            if "прогресс" in stripped.lower():
                kept.append(stripped)
        else:
            kept.append(stripped)
    
    return "\n\n".join(kept).strip()

def show_sync_logs():
    """Показывает логи синхронизации для отладки"""
    st.title("📋 Логи синхронизации")
    st.write("Детальные логи процесса синхронизации с Garmin Connect")
    
    import os
    import glob
    from datetime import datetime
    
    # Ищем файлы логов
    log_dir = "logs"
    if not os.path.exists(log_dir):
        st.warning("📁 Папка с логами не найдена. Логи будут создаваться при следующей синхронизации.")
        return
    
    # Получаем список файлов логов
    log_files = glob.glob(f"{log_dir}/garmin_sync_*.log")
    log_files.sort(reverse=True)  # Новые файлы сначала
    
    if not log_files:
        st.info("📝 Файлы логов пока не созданы. Выполните синхронизацию для создания логов.")
        return
    
    # Выбор файла лога
    col1, col2 = st.columns([2, 1])
    
    with col1:
        selected_file = st.selectbox(
            "Выберите файл лога:",
            log_files,
            format_func=lambda x: os.path.basename(x)
        )
    
    with col2:
        # Кнопка обновления
        if st.button("🔄 Обновить"):
            st.rerun()
    
    if selected_file:
        try:
            # Опции фильтрации
            st.subheader("🔍 Фильтры")
            col1, col2, col3 = st.columns(3)
            
            with col1:
                level_filter = st.multiselect(
                    "Уровень логов:",
                    ["INFO", "DEBUG", "WARNING", "ERROR"],
                    default=["INFO", "WARNING", "ERROR"]
                )
            
            with col2:
                search_term = st.text_input("Поиск по тексту:")
            
            with col3:
                max_lines = st.number_input("Максимум строк:", min_value=10, max_value=1000, value=100)
            
            # Читаем файл лога
            with open(selected_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            # Применяем фильтры
            filtered_lines = []
            for line in lines:
                # Фильтр по уровню
                if level_filter:
                    if not any(level in line for level in level_filter):
                        continue
                
                # Фильтр по поиску
                if search_term and search_term.lower() not in line.lower():
                    continue
                
                filtered_lines.append(line)
            
            # Показываем последние строки
            display_lines = filtered_lines[-max_lines:] if len(filtered_lines) > max_lines else filtered_lines
            
            st.subheader(f"📄 Логи ({len(display_lines)} из {len(lines)} строк)")
            
            # Группируем по типам для удобства
            if st.checkbox("Группировать по типам"):
                errors = [line for line in display_lines if "ERROR" in line]
                warnings = [line for line in display_lines if "WARNING" in line]
                infos = [line for line in display_lines if "INFO" in line and "ERROR" not in line and "WARNING" not in line]
                debugs = [line for line in display_lines if "DEBUG" in line]
                
                if errors:
                    st.error(f"❌ Ошибки ({len(errors)}):")
                    st.code('\n'.join(errors), language=None)
                
                if warnings:
                    st.warning(f"⚠️ Предупреждения ({len(warnings)}):")
                    st.code('\n'.join(warnings), language=None)
                
                if infos:
                    st.info(f"ℹ️ Информация ({len(infos)}):")
                    st.code('\n'.join(infos), language=None)
                
                if debugs and "DEBUG" in level_filter:
                    with st.expander(f"🔍 Отладка ({len(debugs)})"):
                        st.code('\n'.join(debugs), language=None)
            else:
                # Показываем все логи подряд
                log_text = ''.join(display_lines)
                st.code(log_text, language=None)
            
            # Статистика
            st.subheader("📊 Статистика логов")
            # Адаптивная сетка: 2x2 на мобильных
            col1, col2 = st.columns(2)
            col3, col4 = st.columns(2)
            
            total_lines = len(lines)
            errors_count = len([l for l in lines if "ERROR" in l])
            warnings_count = len([l for l in lines if "WARNING" in l])
            success_count = len([l for l in lines if "✅" in l])
            
            col1.metric("Всего строк", total_lines)
            col2.metric("Ошибок", errors_count)
            col3.metric("Предупреждений", warnings_count)
            col4.metric("Успешных операций", success_count)
            
        except Exception as e:
            st.error(f"Ошибка чтения файла лога: {e}")

def show_data_management():
    """Показывает страницу управления данными"""
    state = get_state_manager()
    database = state.database
    st.title("⚙️ Управление данными")
    st.write("Управление синхронизацией и данными в базе")
    
    # Выбор периода синхронизации
    st.subheader("🔄 Синхронизация данных")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        sync_days = st.selectbox(
            "Период загрузки:",
            options=[7, 14, 30, 60, 90],
            index=2,  # По умолчанию 30 дней
            format_func=lambda x: f"{x} дней",
            help="Количество дней для синхронизации с Garmin Connect"
        )
    
    with col2:
        if st.button("🔄 Синхронизировать данные", use_container_width=True):
            sync_data(days=sync_days)
    
    st.divider()
    
    # Статистика БД
    st.subheader("📊 Данные в БД")
    
    if hasattr(state, 'database'):
        stats = database.get_database_stats()
        
        # Показываем статистику в виде метрик
        col1, col2, col3 = st.columns(3)
        col4, col5 = st.columns(2)
        
        with col1:
            st.metric("🏃‍♂️ Активности", stats['activities'])
        
        with col2:
            st.metric("💓 HRV записи", stats['hrv_data'])
        
        with col3:
            st.metric("😴 Данные сна", stats.get('sleep_data', 0))
        
        with col4:
            st.metric("🏥 Показатели здоровья", stats.get('daily_health', 0))
        
        with col5:
            st.metric("📈 Статус тренированности", stats.get('training_status', 0))
        
        # Дополнительная информация
        if stats['activities'] > 0:
            try:
                # Получаем дату последней активности
                activities_df = database.get_activities(1)
                if not activities_df.empty:
                    last_activity_date = activities_df.iloc[0]['date']
                    st.info(f"📅 Последняя активность: {last_activity_date}")
            except Exception:
                pass
    
    st.divider()
    
    # Очистка БД
    clear_database()

if __name__ == "__main__":
    main()
