import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import os
import plotly.express as px
import plotly.graph_objects as go

# Импорты наших модулей
from data.garmin_client import GarminClient
from data.database import Database
from data.data_processor import ActivityProcessor
from models.banister import BanisterModel
from utils.visualizations import Visualizations
from config.settings import Settings

st.set_page_config(
    page_title="AI Trainer",
    page_icon="🏃‍♂️",
    layout="wide",
    initial_sidebar_state="expanded"
)

def main():
    st.title("🏃‍♂️ Персональный AI Тренер")
    
    # Инициализация состояния
    if 'garmin_client' not in st.session_state:
        st.session_state.garmin_client = GarminClient()
    if 'database' not in st.session_state:
        st.session_state.database = Database()
    
    # Боковая панель навигации
    st.sidebar.title("Навигация")
    
    # Блок подключения к Garmin Connect
    show_garmin_connection()
    
    # Главное меню (только если подключён)
    if st.session_state.garmin_client.is_authenticated:
        page = st.sidebar.selectbox("Выберите раздел:", [
            "📊 Дашборд", 
            "🏃‍♂️ Активности", 
            "💓 Анализ HRV", 
            "📈 Планирование", 
            "🤖 AI Коучинг"
        ])
        
        # Кнопка синхронизации
        if st.sidebar.button("🔄 Синхронизировать данные"):
            sync_data()
        
        # Основной контент
        if page == "📊 Дашборд":
            show_dashboard()
        elif page == "🏃‍♂️ Активности":
            show_activities()
        elif page == "💓 Анализ HRV":
            show_hrv_analysis()
        elif page == "📈 Планирование":
            show_planning()
        elif page == "🤖 AI Коучинг":
            show_ai_coaching()
    else:
        show_welcome_screen()

def show_garmin_connection():
    """Блок подключения к Garmin Connect"""
    with st.sidebar.expander("🔗 Garmin Connect", expanded=not st.session_state.garmin_client.is_authenticated):
        if not st.session_state.garmin_client.is_authenticated:
            st.write("Подключитесь для синхронизации данных:")
            
            # Поля для ввода учётных данных
            email = st.text_input("Email Garmin", value=Settings.GARMIN_EMAIL or "")
            password = st.text_input("Пароль Garmin", type="password", value=Settings.GARMIN_PASSWORD or "")
            
            col1, col2 = st.columns(2)
            
            with col1:
                if st.button("🔐 Подключиться"):
                    if email and password:
                        with st.spinner("Подключение к Garmin Connect..."):
                            if st.session_state.garmin_client.authenticate(email, password):
                                st.success("✅ Успешно подключено!")
                                st.rerun()
                            else:
                                st.error(f"❌ Ошибка подключения: {st.session_state.garmin_client.auth_error}")
                    else:
                        st.warning("Введите email и пароль")
            
        else:
            st.success("✅ Подключено к Garmin Connect")
            profile = st.session_state.garmin_client.get_user_profile()
            if profile:
                st.write(f"👤 {profile.get('displayName', 'Пользователь')}")
            
            if st.button("🔌 Отключиться"):
                st.session_state.garmin_client.disconnect()
                st.rerun()

def sync_data():
    """Синхронизация данных с Garmin Connect"""
    if not st.session_state.garmin_client.is_authenticated:
        st.error("Не подключен к Garmin Connect")
        return
    
    with st.spinner("Синхронизация данных..."):
        try:
            # Получение активностей за последние 30 дней
            end_date = datetime.now()
            start_date = end_date - timedelta(days=30)
            
            activities = st.session_state.garmin_client.get_activities(start_date, end_date)
            
            if activities:
                # Обработка и сохранение данных
                df = ActivityProcessor.process_activities(activities)
                
                # Расчёт TSS для активностей
                for idx, row in df.iterrows():
                    tss = ActivityProcessor.calculate_tss(row.to_dict(), 
                                                        ftp=Settings.USER_FTP, 
                                                        lthr=Settings.USER_LTHR)
                    df.at[idx, 'tss'] = tss
                
                st.session_state.database.save_activities(df)
                st.success(f"✅ Синхронизировано {len(activities)} активностей")
                st.rerun()
            else:
                st.warning("Активности не найдены")
                
        except Exception as e:
            st.error(f"Ошибка синхронизации: {e}")

def show_welcome_screen():
    """Экран приветствия для неподключённых пользователей"""
    st.markdown("""
    ## Добро пожаловать в персональный AI тренер! 🏃‍♂️
    
    Этот инструмент поможет вам:
    - 📊 Анализировать тренировочные данные из Garmin Connect
    - 💓 Отслеживать показатели HRV и восстановления  
    - 📈 Планировать тренировки с помощью модели Банистера
    - 🤖 Получать персонализированные рекомендации от AI
    
    ### Для начала работы:
    1. Подключитесь к Garmin Connect в боковой панели
    2. Синхронизируйте ваши тренировочные данные
    3. Начните анализировать и планировать тренировки!
    
    ---
    *Требуется аккаунт Garmin Connect с историей тренировок*
    """)

def show_dashboard():
    """Дашборд тренировок"""
    st.header("📊 Дашборд тренировок")
    
    # Получение данных из БД
    activities_df = st.session_state.database.get_activities(30)
    
    if activities_df.empty:
        st.warning("📭 Нет данных. Выполните синхронизацию с Garmin Connect.")
        if st.button("🔄 Синхронизировать сейчас"):
            sync_data()
        return
    
    # Основные метрики
    col1, col2, col3, col4, col5 = st.columns(5)
    
    with col1:
        total_activities = len(activities_df)
        st.metric("Активности (30 дней)", total_activities)
    
    with col2:
        total_distance = activities_df['distance_km'].sum()
        st.metric("Общая дистанция", f"{total_distance:.1f} км")
    
    with col3:
        total_time = activities_df['duration_minutes'].sum()
        st.metric("Общее время", f"{total_time/60:.1f} ч")
    
    with col4:
        avg_tss = activities_df['tss'].mean() if 'tss' in activities_df.columns and activities_df['tss'].notna().any() else 0
        st.metric("Средний TSS", f"{avg_tss:.1f}")
    
    with col5:
        # Добавляем текущий TSB из модели Банистера
        banister = BanisterModel()
        
        # Безопасная обработка TSS данных
        tss_data = []
        dates = []
        
        for idx, row in activities_df.iterrows():
            tss_val = row.get('tss', 0)
            # Обрабатываем NaN и None значения
            if pd.isna(tss_val) or tss_val is None:
                tss_val = 0
            tss_data.append(float(tss_val))
            dates.append(row['date'])
        
        current_metrics = banister.get_current_metrics(tss_data, dates)
        
        # Цвет для TSB
        tsb_value = current_metrics.get('tsb', 0)
        if tsb_value > 5:
            tsb_color = "🟢"
        elif tsb_value > -10:
            tsb_color = "🟡"
        elif tsb_value > -30:
            tsb_color = "🟠"
        else:
            tsb_color = "🔴"
        
        st.metric("Форма (TSB)", f"{tsb_color} {tsb_value}", help="Training Stress Balance - показатель формы")
    
    # Графики
    col1, col2 = st.columns(2)
    
    with col1:
        # График активностей по дням
        if not activities_df.empty:
            # Убеждаемся что дата в правильном формате для группировки
            activities_df_copy = activities_df.copy()
            if not pd.api.types.is_datetime64_any_dtype(activities_df_copy['date']):
                activities_df_copy['date'] = pd.to_datetime(activities_df_copy['date'])
            
            daily_stats = activities_df_copy.groupby(activities_df_copy['date'].dt.date).agg({
                'duration_minutes': 'sum',
                'distance_km': 'sum'
            }).reset_index()
            
            fig = px.bar(daily_stats, x='date', y='duration_minutes', 
                        title="⏱️ Время тренировок по дням",
                        labels={'duration_minutes': 'Время (мин)', 'date': 'Дата'})
            st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        # Распределение по видам спорта
        if not activities_df.empty:
            sport_dist = activities_df['sport'].value_counts()
            fig = px.pie(values=sport_dist.values, names=sport_dist.index,
                        title="🏃‍♂️ Распределение по видам спорта")
            st.plotly_chart(fig, use_container_width=True)
    
    # Таблица последних активностей
    st.subheader("📋 Последние активности")
    if not activities_df.empty:
        display_df = activities_df.head(10)[['date', 'sport', 'duration_minutes', 'distance_km', 'avg_hr', 'tss']].copy()
        
        # Безопасное форматирование даты
        if pd.api.types.is_datetime64_any_dtype(display_df['date']):
            display_df['date'] = display_df['date'].dt.strftime('%d.%m.%Y')
        else:
            # Если дата не в datetime формате, преобразуем её
            display_df['date'] = pd.to_datetime(display_df['date']).dt.strftime('%d.%m.%Y')
        
        display_df['duration_minutes'] = display_df['duration_minutes'].round(0).astype(int)
        display_df['distance_km'] = display_df['distance_km'].round(1)
        
        display_df.columns = ['Дата', 'Вид спорта', 'Время (мин)', 'Дистанция (км)', 'Ср. пульс', 'TSS']
        st.dataframe(display_df, use_container_width=True)

def show_activities():
    st.header("🏃‍♂️ Ваши активности")
    st.info("📋 Раздел активностей в разработке.")

def show_hrv_analysis():
    st.header("💓 Анализ HRV")
    st.info("📈 Анализ вариабельности сердечного ритма в разработке.")

def show_planning():
    """Страница планирования с моделью Банистера"""
    st.header("📈 Планирование тренировок")
    
    # Получаем данные активностей
    activities_df = st.session_state.database.get_activities(90)  # 90 дней для лучшего анализа
    
    if activities_df.empty:
        st.warning("📭 Нет данных для анализа. Синхронизируйте данные с Garmin Connect.")
        return
    
    # Инициализируем модель Банистера
    banister = BanisterModel()
    
    # Подготавливаем данные с безопасной обработкой
    tss_data = []
    dates = []
    
    for idx, row in activities_df.iterrows():
        tss_val = row.get('tss', 0)
        # Обрабатываем NaN и None значения
        if pd.isna(tss_val) or tss_val is None:
            tss_val = 0
        tss_data.append(float(tss_val))
        dates.append(row['date'])
    
    # Вычисляем метрики
    current_metrics = banister.get_current_metrics(tss_data, dates)
    
    # Отображаем текущие метрики
    st.subheader("🎯 Текущее состояние")
    col1, col2, col3, col4 = st.columns(4)
    
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
        st.metric("Состояние", f"{form_color.get(current_metrics['form'], '⚫')} {current_metrics['form']}")
    
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
            value=int(current_metrics.get('ctl', 50) * 7),
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

def show_ai_coaching():
    """Страница AI коучинга с поддержкой разных провайдеров"""
    st.header("🤖 AI Коучинг")
    
    # Импортируем необходимые модули
    from models.ai_providers import AIProviderFactory
    from models.ai_coach_universal import UniversalAICoach
    
    # Инициализация состояния
    if 'ai_coach' not in st.session_state:
        st.session_state.ai_coach = None
    if 'selected_provider' not in st.session_state:
        st.session_state.selected_provider = Settings.DEFAULT_AI_PROVIDER
    
    # Боковая панель с настройками AI
    with st.sidebar.expander("⚙️ Настройки AI", expanded=True):
        st.subheader("Выбор AI провайдера")
        
        # Проверка доступных провайдеров
        available = AIProviderFactory.get_available_providers()
        
        # Отображение статуса провайдеров
        for name, is_available in available.items():
            if is_available:
                st.success(f"✅ {name}")
            else:
                st.error(f"❌ {name}")
        
        # Выбор провайдера
        provider_options = {
            "OpenAI (GPT)": "openai",
            "Anthropic (Claude)": "anthropic", 
            "Google (Gemini)": "google",
            "Ollama (Локально)": "ollama"
        }
        
        selected_name = st.selectbox(
            "Провайдер:",
            options=list(provider_options.keys()),
            index=list(provider_options.values()).index(st.session_state.selected_provider)
        )
        
        selected_provider = provider_options[selected_name]
        
        # Настройки для выбранного провайдера
        provider_kwargs = {}
        
        # Функция для получения доступных моделей
        @st.cache_data(ttl=300)  # Кешируем на 5 минут
        def get_models_for_provider(provider_type, **kwargs):
            try:
                temp_provider = AIProviderFactory.create_provider(provider_type, **kwargs)
                return temp_provider.get_available_models()
            except:
                return []
        
        if selected_provider == "openai":
            api_key = st.text_input("API Key:", value=Settings.OPENAI_API_KEY or "", type="password")
            
            # Получаем список моделей
            if api_key:
                with st.spinner("Загрузка списка моделей OpenAI..."):
                    available_models = get_models_for_provider("openai", api_key=api_key)
            else:
                available_models = ["gpt-3.5-turbo", "gpt-4", "gpt-4-turbo-preview"]  # Fallback
            
            if available_models:
                # Находим индекс текущей модели
                current_model = Settings.OPENAI_MODEL
                try:
                    default_index = available_models.index(current_model) if current_model in available_models else 0
                except:
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
            
            # Для Anthropic используем известный список
            available_models = [
                "claude-3-haiku-20240307", 
                "claude-3-sonnet-20240229", 
                "claude-3-opus-20240229",
                "claude-2.1", 
                "claude-2.0"
            ]
            
            current_model = Settings.ANTHROPIC_MODEL
            try:
                default_index = available_models.index(current_model) if current_model in available_models else 0
            except:
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
            
            # Для Google используем известный список
            available_models = ["gemini-pro", "gemini-pro-vision", "gemini-1.5-pro", "gemini-1.5-flash"]
            
            current_model = Settings.GOOGLE_MODEL
            try:
                default_index = available_models.index(current_model) if current_model in available_models else 0
            except:
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
            
            # Получаем список моделей Ollama
            with st.spinner("Загрузка локальных моделей Ollama..."):
                available_models = get_models_for_provider("ollama", host=host, model="dummy")
            
            if available_models:
                current_model = Settings.OLLAMA_MODEL
                try:
                    default_index = available_models.index(current_model) if current_model in available_models else 0
                except:
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
        
        # Кнопки управления
        col1, col2 = st.columns(2)
        
        with col1:
            # Кнопка проверки подключения
            if st.button("🔍 Тест подключения", help="Проверить API ключ и подключение"):
                try:
                    provider = AIProviderFactory.create_provider(selected_provider, **provider_kwargs)
                    
                    with st.spinner("Проверка подключения..."):
                        test_result = provider.test_connection()
                    
                    if test_result.get('success'):
                        st.success(f"✅ {test_result.get('message')}")
                        
                        # Показываем дополнительную информацию
                        with st.expander("📋 Детали подключения"):
                            for key, value in test_result.items():
                                if key not in ['success', 'message']:
                                    st.write(f"**{key}:** {value}")
                    else:
                        st.error(f"❌ {test_result.get('error')}")
                        
                except Exception as e:
                    st.error(f"❌ Ошибка тестирования: {e}")
        
        with col2:
            # Кнопка подключения
            if st.button("🔌 Подключить AI", help="Подключиться к выбранному провайдеру"):
                try:
                    provider = AIProviderFactory.create_provider(selected_provider, **provider_kwargs)
                    if provider.is_available():
                        st.session_state.ai_coach = UniversalAICoach(provider)
                        st.session_state.selected_provider = selected_provider
                        st.success(f"✅ Подключено к {provider.get_model_name()}")
                        
                        # Показываем краткую информацию о подключении
                        st.info(f"🎯 Выбранная модель: **{provider_kwargs.get('model')}**")
                        
                    else:
                        st.error("❌ Не удалось подключиться к провайдеру")
                except Exception as e:
                    st.error(f"❌ Ошибка: {e}")
    
    # Основной контент
    if st.session_state.ai_coach is None:
        st.warning("👆 Настройте AI провайдера в боковой панели")
        return
    
    # Получаем данные для анализа
    activities_df = st.session_state.database.get_activities(30)
    
    if activities_df.empty:
        st.warning("📭 Нет данных для анализа. Синхронизируйте данные с Garmin Connect.")
        return
    
    # Подготовка метрик для AI
    banister = BanisterModel()
    tss_data = []
    dates = []
    
    for idx, row in activities_df.iterrows():
        tss_val = row.get('tss', 0)
        if pd.isna(tss_val) or tss_val is None:
            tss_val = 0
        tss_data.append(float(tss_val))
        dates.append(row['date'])
    
    current_metrics = banister.get_current_metrics(tss_data, dates)
    
    # Дополнительные метрики для AI
    week_activities = len(activities_df[activities_df['date'] >= (datetime.now() - timedelta(days=7))])
    week_tss = activities_df[activities_df['date'] >= (datetime.now() - timedelta(days=7))]['tss'].sum()
    avg_tss = activities_df['tss'].mean() if not activities_df['tss'].isna().all() else 0
    
    # Определяем основной вид спорта
    if not activities_df.empty:
        primary_sport = activities_df['sport'].mode()[0] if not activities_df['sport'].empty else 'смешанный'
    else:
        primary_sport = 'неизвестно'
    
    ai_metrics = {
        **current_metrics,
        'week_activities': week_activities,
        'week_tss': week_tss,
        'avg_tss': avg_tss,
        'primary_sport': primary_sport
    }
    
    # Табы для разных функций AI коуча
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📊 Анализ состояния",
        "📅 Недельный план", 
        "🏃 Анализ тренировки",
        "❓ Вопрос коучу",
        "📚 Объяснение метрик"
    ])
    
    with tab1:
        st.subheader("📊 Анализ текущего состояния")
        
        # Показываем текущие метрики
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("CTL", f"{current_metrics['ctl']:.1f}")
        with col2:
            st.metric("ATL", f"{current_metrics['atl']:.1f}")
        with col3:
            st.metric("TSB", f"{current_metrics['tsb']:.1f}")
        
        if st.button("🔍 Проанализировать состояние", key="analyze_state"):
            with st.spinner("AI анализирует ваши данные..."):
                analysis = st.session_state.ai_coach.analyze_current_state(ai_metrics)
                st.markdown("### 🤖 Анализ AI коуча:")
                st.markdown(analysis)
    
    with tab2:
        st.subheader("📅 Генерация недельного плана")
        
        goals = st.text_area(
            "Ваши цели на неделю:",
            placeholder="Например: подготовка к полумарафону, увеличение выносливости, восстановление после соревнований..."
        )
        
        if st.button("📝 Создать план", key="create_plan"):
            with st.spinner("AI создаёт персональный план..."):
                plan = st.session_state.ai_coach.generate_weekly_plan(ai_metrics, goals)
                st.markdown("### 📋 Ваш недельный план:")
                st.markdown(plan)
    
    with tab3:
        st.subheader("🏃 Анализ последней тренировки")
        
        # Выбор тренировки для анализа
        if not activities_df.empty:
            last_activities = activities_df.head(10)
            
            activity_options = []
            for idx, row in last_activities.iterrows():
                date_str = row['date'].strftime('%d.%m')
                activity_str = f"{date_str} - {row['sport']} - {row['distance_km']:.1f}км - TSS: {row['tss']:.0f}"
                activity_options.append(activity_str)
            
            selected_idx = st.selectbox("Выберите тренировку:", range(len(activity_options)),
                                       format_func=lambda x: activity_options[x])
            
            selected_activity = last_activities.iloc[selected_idx]
            
            # Субъективные ощущения
            feeling = st.text_area(
                "Как вы себя чувствовали?",
                placeholder="Опишите ваши ощущения: усталость, лёгкость, проблемы, успехи..."
            )
            
            if st.button("🔬 Анализировать тренировку", key="analyze_workout"):
                with st.spinner("AI анализирует тренировку..."):
                    workout_data = selected_activity.to_dict()
                    analysis = st.session_state.ai_coach.analyze_workout(workout_data, feeling)
                    st.markdown("### 🎯 Анализ тренировки:")
                    st.markdown(analysis)
    
    with tab4:
        st.subheader("❓ Задайте вопрос AI коучу")
        
        question = st.text_area(
            "Ваш вопрос:",
            placeholder="Любой вопрос о тренировках, восстановлении, питании, планировании..."
        )
        
        if st.button("💬 Получить ответ", key="ask_question"):
            if question:
                with st.spinner("AI формирует ответ..."):
                    answer = st.session_state.ai_coach.answer_question(question, ai_metrics)
                    st.markdown("### 💡 Ответ коуча:")
                    st.markdown(answer)
            else:
                st.warning("Введите вопрос")
    
    with tab5:
        st.subheader("📚 Объяснение метрик")
        
        metric_options = {
            "TSS (Training Stress Score)": "TSS",
            "CTL (Chronic Training Load)": "CTL",
            "ATL (Acute Training Load)": "ATL",
            "TSB (Training Stress Balance)": "TSB",
            "FTP (Functional Threshold Power)": "FTP",
            "LTHR (Lactate Threshold Heart Rate)": "LTHR",
            "HRV (Heart Rate Variability)": "HRV",
            "RMSSD": "RMSSD",
            "VO2max": "VO2max"
        }
        
        selected_metric_name = st.selectbox("Выберите метрику:", list(metric_options.keys()))
        
        if st.button("📖 Объяснить", key="explain_metric"):
            with st.spinner("AI готовит объяснение..."):
                explanation = st.session_state.ai_coach.explain_metrics(selected_metric_name)
                st.markdown("### 📘 Объяснение:")
                st.markdown(explanation)

if __name__ == "__main__":
    main()