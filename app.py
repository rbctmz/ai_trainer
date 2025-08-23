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
    format_type: 'display' для UI (дд.мм.гггг), 'db' для БД (гггг-мм-дд)
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
    else:
        return str(date_obj)

def get_plotly_theme():
    """Получение темы для графиков Plotly"""
    if st.session_state.get('dark_mode', False):
        return {
            'template': 'plotly_dark',
            'paper_bgcolor': '#121212',  # Material Design dark background
            'plot_bgcolor': '#1E1E1E',   # Surface color
            'font_color': '#F5F5F5',     # High contrast text
            'gridcolor': '#2B2B2B'       # Proper divider color
        }
    else:
        return {
            'template': 'plotly_white',
            'paper_bgcolor': 'white',
            'plot_bgcolor': 'white',
            'font_color': '#262730',
            'gridcolor': '#e0e0e0'
        }

def create_dark_table_html(df, max_height=400):
    """Создает HTML таблицу для темной темы"""
    html_table = f"""
    <div style="background-color: #1E1E1E; border: 1px solid #2B2B2B; border-radius: 8px; padding: 10px; max-height: {max_height}px; overflow-y: auto;">
    <table style="width: 100%; color: #F5F5F5; border-collapse: collapse;">
    <thead>
    <tr style="background-color: #2B2B2B;">
    """
    
    # Добавляем заголовки
    for col in df.columns:
        html_table += f'<th style="padding: 8px; border: 1px solid #2B2B2B; color: #F5F5F5; font-weight: bold; text-align: left;">{col}</th>'
    html_table += "</tr></thead><tbody>"
    
    # Добавляем строки данных
    for idx, row in df.iterrows():
        bg_color = "#1A1A1A" if idx % 2 == 1 else "#1E1E1E"
        html_table += f'<tr style="background-color: {bg_color};">'
        for value in row:
            html_table += f'<td style="padding: 8px; border: 1px solid #2B2B2B; color: #F5F5F5;">{value}</td>'
        html_table += "</tr>"
    
    html_table += "</tbody></table></div>"
    return html_table

def apply_plotly_theme(fig):
    """Применяет тему к графику Plotly"""
    theme = get_plotly_theme()
    fig.update_layout(
        template=theme['template'],
        paper_bgcolor=theme['paper_bgcolor'],
        plot_bgcolor=theme['plot_bgcolor'],
        font=dict(color=theme['font_color']),
        xaxis=dict(gridcolor=theme['gridcolor']),
        yaxis=dict(gridcolor=theme['gridcolor'])
    )
    return fig

def apply_theme():
    """Применение темной или светлой темы"""
    if 'dark_mode' not in st.session_state:
        # Пытаемся загрузить сохраненное предпочтение
        st.session_state.dark_mode = False
        
    # JavaScript для сохранения/загрузки темы из localStorage
    st.markdown(f"""
    <script>
        // Сохраняем текущую тему
        localStorage.setItem('aitrainer_dark_mode', '{str(st.session_state.dark_mode).lower()}');
    </script>
    """, unsafe_allow_html=True)
    
    if st.session_state.dark_mode:
        # Темная тема
        st.markdown("""
        <style>
        :root {
            /* Material Design темная палитра - WCAG AA совместимая */
            --background-color: #121212;     /* Material Dark background */
            --surface-1-color: #1E1E1E;     /* Surface elevation 1 */
            --surface-2-color: #262626;     /* Surface elevation 2 */
            --surface-3-color: #2D2D2D;     /* Surface elevation 3 */
            --border-color: #2B2B2B;        /* Dividers/borders */
            --hover-color: #333333;         /* Hover state */
            
            --accent-color: #5C6BC0;        /* Material indigo accent */
            --accent-color-hover: #7986CB;  /* Lighter indigo for hover */
            --accent-secondary: #4F83CC;    /* Secondary accent blue */
            
            --text-primary-color: #F5F5F5;  /* High contrast primary text */
            --text-secondary-color: #A0A0A0; /* Secondary text */
            --text-disabled-color: #707070; /* Disabled text */
            
            --success-bg-color: #1B5E20;    /* Material green dark */
            --warning-bg-color: #E65100;    /* Material orange dark */
            --error-bg-color: #C62828;      /* Material red dark */
            --info-bg-color: #1565C0;       /* Material blue dark */
        }

        /* Основные стили */
        .stApp {
            background-color: var(--background-color);
            color: var(--text-primary-color);
        }
        
        /* Боковая панель */
        section[data-testid="stSidebar"] {
            background-color: var(--surface-1-color);
            border-right: 1px solid var(--border-color);
        }
        
        /* Метрики */
        [data-testid="metric-container"] {
            background-color: var(--surface-1-color);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 12px;
        }
        [data-testid="metric-container"] .stMetricValue {
            color: var(--accent-color); /* Акцентный цвет для значения метрики */
        }
        
        /* Эк��пандеры */
        .streamlit-expanderHeader {
            background-color: var(--surface-1-color);
            color: var(--text-primary-color) !important;
            border-radius: 8px;
        }
        .streamlit-expanderContent {
            background-color: var(--surface-1-color) !important;
            border: 1px solid var(--border-color) !important;
        }
        
        /* Таблицы */
        .dataframe, div[data-testid="stDataFrame"] {
            background-color: var(--surface-1-color) !important;
            border: 1px solid var(--border-color) !important;
            border-radius: 8px !important;
        }
        
        /* Заголовки таблиц */
        .dataframe thead tr th,
        div[data-testid="stDataFrame"] thead tr th,
        .stDataFrame thead tr th {
            background-color: var(--surface-2-color) !important;
            color: var(--text-primary-color) !important;
            border-bottom: 1px solid var(--border-color) !important;
            border-right: 1px solid var(--border-color) !important;
        }
        
        /* Строки таблиц */
        .dataframe tbody tr,
        div[data-testid="stDataFrame"] tbody tr,
        .stDataFrame tbody tr {
            background-color: var(--surface-1-color) !important;
            color: var(--text-primary-color) !important;
        }
        
        /* Ячейки таблиц */
        .dataframe tbody tr td,
        div[data-testid="stDataFrame"] tbody tr td,
        .stDataFrame tbody tr td {
            background-color: var(--surface-1-color) !important;
            color: var(--text-primary-color) !important;
            border-right: 1px solid var(--border-color) !important;
            border-bottom: 1px solid var(--border-color) !important;
        }
        
        /* Hover эффект */
        .dataframe tbody tr:hover,
        div[data-testid="stDataFrame"] tbody tr:hover,
        .stDataFrame tbody tr:hover {
            background-color: var(--hover-color) !important;
        }
        
        .dataframe tbody tr:hover td,
        div[data-testid="stDataFrame"] tbody tr:hover td,
        .stDataFrame tbody tr:hover td {
            background-color: var(--hover-color) !important;
        }
        
        /* Альтернативные строки */
        .dataframe tbody tr:nth-child(even),
        div[data-testid="stDataFrame"] tbody tr:nth-child(even),
        .stDataFrame tbody tr:nth-child(even) {
            background-color: #1A1A1A !important;
        }
        
        .dataframe tbody tr:nth-child(even) td,
        div[data-testid="stDataFrame"] tbody tr:nth-child(even) td,
        .stDataFrame tbody tr:nth-child(even) td {
            background-color: #1A1A1A !important;
        }
        
        /* Специальная стилизация для Streamlit dataframes */
        div[data-testid="stDataFrame"] {
            background-color: var(--surface-1-color) !important;
            border-radius: 8px !important;
            border: 1px solid var(--border-color) !important;
        }
        
        div[data-testid="stDataFrame"] > div {
            background-color: var(--surface-1-color) !important;
            color: var(--text-primary-color) !important;
        }
        
        /* Все элементы внутри dataframe */
        div[data-testid="stDataFrame"] *,
        div[data-testid="stDataFrame"] table,
        div[data-testid="stDataFrame"] thead,
        div[data-testid="stDataFrame"] tbody,
        div[data-testid="stDataFrame"] tr,
        div[data-testid="stDataFrame"] th,
        div[data-testid="stDataFrame"] td {
            background-color: var(--surface-1-color) !important;
            color: var(--text-primary-color) !important;
            border-color: var(--border-color) !important;
        }
        
        /* Заголовки dataframe */
        div[data-testid="stDataFrame"] thead th,
        div[data-testid="stDataFrame"] .stDataFrame th {
            background-color: var(--surface-2-color) !important;
            color: var(--text-primary-color) !important;
            font-weight: 600 !important;
        }
        
        /* Строки с данными */
        div[data-testid="stDataFrame"] tbody tr:nth-child(odd) td {
            background-color: var(--surface-1-color) !important;
        }
        
        div[data-testid="stDataFrame"] tbody tr:nth-child(even) td {
            background-color: #1A1A1A !important;
        }
        
        /* Принудительное переопределение всех стилей таблицы */
        .stDataFrame, .stDataFrame * {
            background-color: var(--surface-1-color) !important;
            color: var(--text-primary-color) !important;
        }
        
        .stDataFrame thead th {
            background-color: var(--surface-2-color) !important;
            color: var(--text-primary-color) !important;
        }
        
        /* Самые агрессивные правила для dataframe */
        div[data-testid="stDataFrame"] div,
        div[data-testid="stDataFrame"] div div,
        div[data-testid="stDataFrame"] div div div {
            background-color: var(--surface-1-color) !important;
            color: var(--text-primary-color) !important;
        }
        
        /* Переопределение цветов текста и фона для всех вложенных элементов */
        [data-testid="stDataFrame"] span,
        [data-testid="stDataFrame"] p,
        [data-testid="stDataFrame"] div,
        [data-testid="stDataFrame"] * {
            color: var(--text-primary-color) !important;
            background-color: transparent !important;
        }
        
        /* Специфичные правила для ячеек таблицы в темной теме */
        div[data-testid="stDataFrame"] [role="gridcell"],
        div[data-testid="stDataFrame"] [role="columnheader"] {
            background-color: var(--surface-1-color) !important;
            color: var(--text-primary-color) !important;
        }
        
        /* Дополнительное принудительное переопределение для Streamlit dataframes */
        section[data-testid="stDataFrame"] {
            background-color: var(--surface-1-color) !important;
            border-radius: 8px !important;
        }
        
        /* Переопределение всех возможных селекторов для dataframe */
        .stDataFrame table tbody tr td,
        .stDataFrame table thead tr th,
        div[data-testid="stDataFrame"] table tbody tr td,
        div[data-testid="stDataFrame"] table thead tr th {
            background-color: var(--surface-1-color) !important;
            color: var(--text-primary-color) !important;
            border: 1px solid var(--border-color) !important;
        }
        
        .stDataFrame table thead tr th,
        div[data-testid="stDataFrame"] table thead tr th {
            background-color: var(--surface-2-color) !important;
        }
        
        /* Переопределение цветов для чередующихся строк */
        .stDataFrame table tbody tr:nth-child(even) td,
        div[data-testid="stDataFrame"] table tbody tr:nth-child(even) td {
            background-color: #1A1A1A !important;
        }
        
        /* Кнопки */
        .stButton > button {
            background-color: var(--surface-2-color);
            color: var(--text-primary-color);
            border: 1px solid var(--border-color);
        }
        .stButton > button:hover {
            background-color: var(--hover-color);
            border: 1px solid var(--accent-color);
        }
        .stButton > button:focus {
            box-shadow: 0 0 0 2px var(--accent-color);
        }
        
        /* Поля ввода */
        .stTextInput > div > div > input,
        .stSelectbox > div > div,
        .stTextArea > div > div > textarea,
        .stNumberInput > div > div > input {
            background-color: var(--surface-1-color) !important;
            color: var(--text-primary-color) !important;
            border: 1px solid var(--border-color) !important;
        }
        
        /* Вкладки */
        .stTabs [data-baseweb="tab-list"] {
            background-color: var(--surface-1-color);
            border-radius: 8px;
        }
        .stTabs [data-baseweb="tab"] {
            background-color: var(--surface-2-color);
            color: var(--text-primary-color);
            border: 1px solid var(--border-color);
        }
        .stTabs [aria-selected="true"] {
            background-color: var(--accent-color);
            border: 1px solid var(--accent-color);
        }
        
        /* Текст и типография */
        .stMarkdown, .stMarkdown p, .stMarkdown li, .stMarkdown h1, .stMarkdown h2, .stMarkdown h3 {
            color: var(--text-primary-color) !important;
        }
        .stCaption {
            color: var(--text-secondary-color) !important;
        }
        a, .stMarkdown a {
            color: var(--accent-color) !important;
        }
        a:hover, .stMarkdown a:hover {
            color: var(--accent-color-hover) !important;
        }
        
        /* Уведомления */
        .stAlert {
            background-color: var(--surface-1-color);
            border: 1px solid var(--border-color);
        }
        .stInfo { background-color: var(--info-bg-color) !important; }
        .stWarning { background-color: var(--warning-bg-color) !important; }
        .stError { background-color: var(--error-bg-color) !important; }
        .stSuccess { background-color: var(--success-bg-color) !important; }
        
        /* Чат */
        .stChatInput > div > div > textarea,
        .stChatInputContainer textarea {
            background-color: var(--surface-1-color) !important;
            color: var(--text-primary-color) !important;
            border: 1px solid var(--border-color) !important;
        }
        div[data-testid="stChatInput"] {
            background-color: var(--surface-1-color) !important;
            border: 1px solid var(--border-color) !important;
            border-radius: 25px !important;
        }
        .stChatMessage {
            background-color: var(--surface-1-color);
            border-radius: 10px !important;
        }
        [data-testid="chatAvatarIcon-assistant"] {
            background-color: var(--accent-color) !important;
        }
        </style>
        """, unsafe_allow_html=True)
    else:
        # Светлая тема (стандартная)
        st.markdown("""
        <style>
        /* Сброс к светлой теме */
        .stApp {
            background-color: white;
            color: #262730;
        }
        
        section[data-testid="stSidebar"] {
            background-color: #f0f2f6;
        }
        
        [data-testid="metric-container"] {
            background-color: #ffffff;
            border: 1px solid #e0e0e0;
            border-radius: 8px;
            padding: 10px;
        }
        </style>
        """, unsafe_allow_html=True)

def main():
    st.title("🏃‍♂️ Персональный AI Тренер")
    
    # Инициализация состояния
    if 'garmin_client' not in st.session_state:
        st.session_state.garmin_client = GarminClient()
    if 'database' not in st.session_state:
        st.session_state.database = Database()
    
    # Применяем тему
    apply_theme()
    
    # Боковая панель навигации
    col1, col2 = st.sidebar.columns([4, 1])
    with col1:
        st.title("🏃‍♂️ AI Trainer")
    with col2:
        # Переключатель темы
        st.markdown("<br>", unsafe_allow_html=True)  # Отступ сверху
        if st.button("🌙" if not st.session_state.get('dark_mode', False) else "☀️", 
                     help="Переключить тему",
                     use_container_width=True,
                     key="theme_toggle"):
            st.session_state.dark_mode = not st.session_state.get('dark_mode', False)
            st.rerun()
    
    # Блок подключения к Garmin Connect
    show_garmin_connection()
    
    # Главное меню (только если подключён)
    if st.session_state.garmin_client.is_authenticated:
        # Используем радио-кнопки для лучшей навигации на мобильных
        st.sidebar.markdown("### 📍 Основные разделы")
        
        # Определяем текущую страницу
        pages = [
            "📊 Дашборд", 
            "🤖 AI Коучинг",
            "🏃‍♂️ Активности", 
            "📈 Планирование",
            "⚙️ Управление данными"
        ]
        
        # Если есть выбранная страница из session state, используем её
        default_index = 0
        if "selected_page" in st.session_state and st.session_state.selected_page in pages:
            default_index = pages.index(st.session_state.selected_page)
        
        page = st.sidebar.radio("", pages, 
                               index=default_index,
                               label_visibility="collapsed")
        
        # Обновляем selected_page в session state
        st.session_state.selected_page = page
        
        # Дополнительные разделы в отдельном экспандере
        with st.sidebar.expander("📂 Дополнительно"):
            additional_page = st.selectbox("Анализ данных:", [
                "Основной раздел",
                "💓 Анализ HRV",
                "😴 Анализ сна",
                "📋 Логи синхронизации"
            ], label_visibility="collapsed")
            
            if additional_page != "Основной раздел":
                page = additional_page
        
        st.sidebar.markdown("---")
        
        # Инициализация и отображение управления чатами
        # Инициализация менеджера чатов
        if "chat_manager" not in st.session_state:
            from models.chat_manager import ChatManager
            st.session_state.chat_manager = ChatManager()
        
        # Инициализация текущего чата
        if "current_chat_id" not in st.session_state:
            st.session_state.current_chat_id = None
        
        # Показываем управление чатами
        show_chat_management()
        
        st.sidebar.markdown("---")
        
        # Тестовые данные в отдельном экспандере
        with st.sidebar.expander("🧪 Разработка", expanded=False):
            st.caption("Тестовые функции для демонстрации")
            add_test_phase1_data()
        
        # Основной контент
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
            
            # Информация о типе подключения
            connection_info = st.session_state.garmin_client.get_connection_info()
            if connection_info.get('using_garth'):
                st.info("🚀 Используется garth (улучшенный API)")
            else:
                st.info("📡 Используется garminconnect")
            
            profile = st.session_state.garmin_client.get_user_profile()
            if profile:
                st.write(f"👤 {profile.get('displayName', 'Пользователь')}")
            
            # Дополнительная диагностика garth
            if connection_info.get('garth_available') and connection_info.get('using_garth'):
                if st.button("🔍 Тест garth", help="Проверить расширенные возможности garth"):
                    with st.spinner("Тестирование garth..."):
                        test_results = st.session_state.garmin_client.test_garth_connection()
                        if test_results.get('authenticated'):
                            st.success("✅ Garth работает корректно")
                            with st.expander("📋 Детали garth тестирования"):
                                for method, status in test_results.get('test_results', {}).items():
                                    st.write(f"• **{method}**: {status}")
                        else:
                            st.warning(f"⚠️ Проблема с garth: {test_results.get('error', 'Неизвестно')}")
            
            if st.button("🔌 Отключиться"):
                st.session_state.garmin_client.disconnect()
                st.rerun()

def sync_data(days=30):
    """Синхронизация данных с Garmin Connect"""
    if not st.session_state.garmin_client.is_authenticated:
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
        
        activities = st.session_state.garmin_client.get_activities(start_date, end_date)
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
            sync_result = st.session_state.database.sync_activities(activities_list)
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
                hrv_day_data = st.session_state.garmin_client.get_hrv_data(date)
                rmssd_value = None
                
                # Debug вывод
                print(f"DEBUG HRV: Получены данные HRV для {date_str}: {type(hrv_day_data)}")
                if hrv_day_data:
                    print(f"DEBUG HRV: Структура данных: {hrv_day_data}")
                
                if isinstance(hrv_day_data, dict):
                    # Новый garth_client может возвращать {'hrvSummary': {'rmssd': ...}}
                    if 'hrvSummary' in hrv_day_data and isinstance(hrv_day_data['hrvSummary'], dict):
                        hrv_summary = hrv_day_data['hrvSummary']
                        rmssd_value = hrv_summary.get('rmssd') or hrv_summary.get('lastNightAvg')
                        print(f"DEBUG HRV: Извлечено RMSSD из hrvSummary: {rmssd_value}")
                    # Также может возвращать {'daily_rmssd': ...} напрямую
                    elif 'daily_rmssd' in hrv_day_data:
                        rmssd_value = hrv_day_data['daily_rmssd']
                        print(f"DEBUG HRV: Извлечено RMSSD из daily_rmssd: {rmssd_value}")
                    elif 'rmssd' in hrv_day_data:
                        rmssd_value = hrv_day_data['rmssd']
                        print(f"DEBUG HRV: Извлечено RMSSD напрямую: {rmssd_value}")

                # Получаем данные о стрессе
                stress_score = None
                stress_data = st.session_state.garmin_client.get_stress_data(date)
                print(f"DEBUG STRESS SYNC: Получены данные стресса для {date_str}: {type(stress_data)}")
                if stress_data:
                    print(f"DEBUG STRESS SYNC: Структура данных стресса: {stress_data}")
                
                if isinstance(stress_data, dict):
                    stress_score = stress_data.get('avgStressLevel') or stress_data.get('overallStressLevel')
                    print(f"DEBUG STRESS SYNC: Извлечен stress_score из словаря: {stress_score}")
                elif isinstance(stress_data, (int, float)): # Иногда API может вернуть просто число
                    stress_score = stress_data
                    print(f"DEBUG STRESS SYNC: stress_score - простое число: {stress_score}")
                
                # Получаем данные Body Battery (восстановление)
                recovery_score = None
                body_battery_data = st.session_state.garmin_client.get_body_battery_data(date)
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
                    print(f"DEBUG HRV: Сохранены данные для {date_str}: {hrv_data[date_str]}")
                    print(f"DEBUG HRV: RMSSD={rmssd_value}, Stress={stress_score}, Recovery={recovery_score}")
            
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
        
        for date in date_list[:min(len(date_list), days)]:  # Ограничиваем количество запросов
            date_str = format_date(date, 'db')
            
            # Получаем и обрабатываем данные сна
            try:
                sleep_raw = st.session_state.garmin_client.get_sleep_data(date)
                print(f"DEBUG SYNC: Получены данные сна для {date_str}: {type(sleep_raw)}")
                
                if sleep_raw:
                    print(f"DEBUG SYNC: === ДЕТАЛЬНАЯ СТРУКТУРА ДАННЫХ СНА для {date_str} ===")
                    
                    # Подробное логирование структуры данных
                    if isinstance(sleep_raw, dict):
                        print(f"DEBUG SYNC: Ключи верхнего уровня: {list(sleep_raw.keys())}")
                        
                        # Проверяем dailySleepDTO
                        if 'dailySleepDTO' in sleep_raw:
                            dto = sleep_raw['dailySleepDTO']
                            print(f"DEBUG SYNC: dailySleepDTO ключи: {list(dto.keys()) if isinstance(dto, dict) else 'НЕ СЛОВАРЬ'}")
                            if isinstance(dto, dict):
                                print(f"DEBUG SYNC: sleepTimeSeconds: {dto.get('sleepTimeSeconds', 'НЕТ')}")
                                print(f"DEBUG SYNC: deepSleepSeconds: {dto.get('deepSleepSeconds', 'НЕТ')}")
                                print(f"DEBUG SYNC: lightSleepSeconds: {dto.get('lightSleepSeconds', 'НЕТ')}")
                                print(f"DEBUG SYNC: remSleepSeconds: {dto.get('remSleepSeconds', 'НЕТ')}")
                                print(f"DEBUG SYNC: awakeCount: {dto.get('awakeCount', 'НЕТ')}")
                        
                        # Проверяем sleepScores
                        if 'sleepScores' in sleep_raw:
                            scores = sleep_raw['sleepScores']
                            print(f"DEBUG SYNC: sleepScores ключи: {list(scores.keys()) if isinstance(scores, dict) else 'НЕ СЛОВАРЬ'}")
                            if isinstance(scores, dict):
                                if 'deepPercentage' in scores:
                                    print(f"DEBUG SYNC: deepPercentage: {scores['deepPercentage']}")
                                if 'lightPercentage' in scores:
                                    print(f"DEBUG SYNC: lightPercentage: {scores['lightPercentage']}")
                                if 'remPercentage' in scores:
                                    print(f"DEBUG SYNC: remPercentage: {scores['remPercentage']}")
                                if 'overall' in scores:
                                    print(f"DEBUG SYNC: overall: {scores['overall']}")
                        
                        # Проверяем другие возможные структуры
                        for key in sleep_raw.keys():
                            if key not in ['dailySleepDTO', 'sleepScores']:
                                print(f"DEBUG SYNC: Дополнительный ключ {key}: {type(sleep_raw[key])}")
                    
                    print(f"DEBUG SYNC: === ПЕРЕДАЕМ В ПРОЦЕССОР ===")
                    processed_sleep = Phase1DataProcessor.process_sleep_data(sleep_raw)
                    print(f"DEBUG SYNC: Обработанные данные сна для {date_str}: {processed_sleep}")
                    
                    if processed_sleep:
                        sleep_data[date_str] = processed_sleep
                        print(f"DEBUG SYNC: ✅ Данные сна добавлены для {date_str}")
                        
                        # Проверяем что именно сохранили
                        total = processed_sleep.get('total_sleep_minutes', 0)
                        deep = processed_sleep.get('deep_sleep_minutes', 0)
                        light = processed_sleep.get('light_sleep_minutes', 0)
                        rem = processed_sleep.get('rem_sleep_minutes', 0)
                        score = processed_sleep.get('sleep_score', 0)
                        
                        print(f"DEBUG SYNC: 📊 Сохраненные значения: total={total}, deep={deep}, light={light}, rem={rem}, score={score}")
                        
                        if deep == 0 and light == 0 and rem == 0:
                            print(f"DEBUG SYNC: ⚠️ КРИТИЧНО: Все фазы сна равны 0!")
                    else:
                        print(f"DEBUG SYNC: ❌ Обработка данных сна вернула None для {date_str}")
                else:
                    print(f"DEBUG SYNC: Нет данных сна для {date_str}")
                    
            except Exception as e:
                print(f"DEBUG SYNC: ❌ Ошибка обработки данных сна для {date_str}: {e}")
                import traceback
                traceback.print_exc()
                pass  # Данные сна могут быть недоступны
            
            # Получаем и обрабатываем ежедневные показатели здоровья
            try:
                # Общие показатели активности
                daily_summary = st.session_state.garmin_client.get_daily_summary(date)
                # Пульс покоя
                resting_hr = st.session_state.garmin_client.get_resting_heart_rate(date)
                
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
            training_status = st.session_state.garmin_client.get_training_status()
            # VO2 max
            vo2_data = st.session_state.garmin_client.get_vo2_max()
            # Готовность к тренировке
            readiness_data = st.session_state.garmin_client.get_training_readiness()
            
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
        print(f"DEBUG HRV SYNC: Сохранение HRV данных в базу: {len(hrv_data)} записей")
        print(f"DEBUG HRV SYNC: Ключи данных HRV: {list(hrv_data.keys()) if hrv_data else 'Нет данных'}")
        if hrv_data:
            hrv_result = st.session_state.database.sync_hrv_data(hrv_data)
            print(f"DEBUG HRV SYNC: Результат сохранения HRV: {hrv_result}")
        else:
            print("DEBUG HRV SYNC: Нет данных HRV для сохранения")
        
        # Сохраняем новые типы данных
        sleep_result = {'new': 0, 'updated': 0}
        print(f"DEBUG SYNC: Сохранение данных сна в базу: {len(sleep_data)} записей")
        print(f"DEBUG SYNC: Ключи данных сна: {list(sleep_data.keys()) if sleep_data else 'Нет данных'}")
        if sleep_data:
            sleep_result = st.session_state.database.sync_sleep_data(sleep_data)
            print(f"DEBUG SYNC: Результат сохранения сна: {sleep_result}")
        else:
            print("DEBUG SYNC: Нет данных сна для сохранения")
        
        health_result = {'new': 0, 'updated': 0}
        if daily_health_data:
            health_result = st.session_state.database.sync_daily_health(daily_health_data)
        
        status_result = {'new': 0, 'updated': 0}
        if training_status_data:
            status_result = st.session_state.database.sync_training_status(training_status_data)
        
        progress_bar.progress(100, text="✅ Синхронизация завершена!")
        status_text.empty()
        sync_stats.empty()
        
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
    if st.button("🗑️ Очистить базу данных", type="secondary", key="clear_db_btn"):
        if 'confirm_clear' not in st.session_state:
            st.session_state.confirm_clear = False
        
        if not st.session_state.confirm_clear:
            st.session_state.confirm_clear = True
            st.rerun()
    
    if st.session_state.get('confirm_clear', False):
        st.warning("⚠️ Это действие удалит ВСЕ данные из базы. Подтвердите удаление.")
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("✅ Да, удалить все данные", type="primary", key="confirm_clear_btn"):
                try:
                    result = st.session_state.database.clear_all_data()
                    st.success("✅ База данных очищена")
                    st.session_state.confirm_clear = False
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Ошибка очистки БД: {e}")
                    st.session_state.confirm_clear = False
        
        with col2:
            if st.button("❌ Отмена", type="secondary", key="cancel_clear_btn"):
                st.session_state.confirm_clear = False
                st.rerun()

def add_test_phase1_data():
    """Добавление тестовых данных Фазы 1 для демонстрации"""
    if st.button("🧪 Добавить тестовые данные Фазы 1", type="primary", key="add_test_data_btn"):
        try:
            from datetime import datetime, timedelta
            from data.data_processor_phase1 import Phase1DataProcessor
            
            # Создаем тестовые данные за последние 7 дней
            sleep_data = {}
            health_data = {}
            status_data = {}
            
            for i in range(7):
                date = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
                
                # Тестовые данные сна (варьируем качество)
                base_quality = 75 + (i % 3) * 5  # 75-85
                sleep_data[date] = {
                    'total_sleep_minutes': 420 + (i % 2) * 30,  # 7-7.5 часов
                    'deep_sleep_minutes': 80 + (i % 3) * 10,
                    'light_sleep_minutes': 280 + (i % 2) * 20,
                    'rem_sleep_minutes': 60 + (i % 3) * 10,
                    'awakenings_count': 1 + (i % 3),
                    'sleep_score': base_quality + (i % 2) * 5,
                    'bedtime': f"23:{15 + (i % 3) * 15:02d}",
                    'wakeup_time': f"0{6 + (i % 2)}:{30 + (i % 2) * 15:02d}",
                    'sleep_efficiency': 88.0 + (i % 3) * 3
                }
                
                # Тестовые данные здоровья
                health_data[date] = {
                    'resting_hr': 48 + (i % 4) * 2,  # 48-54
                    'steps': 8000 + i * 500,  # 8000-11000
                    'floors_climbed': 8 + (i % 3) * 2,
                    'calories_active': 350 + i * 30,
                    'calories_bmr': 1580,
                    'distance_meters': 6000 + i * 400,
                    'active_minutes': 40 + (i % 3) * 10,
                    'intensity_minutes': 15 + (i % 3) * 5
                }
            
            # Статус тренированности (один на сегодня)
            today = datetime.now().strftime('%Y-%m-%d')
            status_data[today] = {
                'vo2_max': 48.5,
                'fitness_age': 32,
                'training_load_7d': 285.0,
                'training_status': 'PRODUCTIVE',
                'training_readiness': 75.0,
                'recovery_time_hours': 14,
                'load_ratio': 1.05
            }
            
            # Синхронизируем тестовые данные
            sleep_result = st.session_state.database.sync_sleep_data(sleep_data)
            health_result = st.session_state.database.sync_daily_health(health_data)
            status_result = st.session_state.database.sync_training_status(status_data)
            
            success_msg = f"✅ Тестовые данные добавлены:\n"
            success_msg += f"• 😴 Сон: {sleep_result['new']} новых записей\n"
            success_msg += f"• 🏃 Здоровье: {health_result['new']} новых записей\n"
            success_msg += f"• 🎯 Статус: {status_result['new']} новых записей\n\n"
            success_msg += "Теперь вы можете проверить:\n"
            success_msg += "• Страницу \"😴 Анализ сна\"\n"
            success_msg += "• Индекс готовности на дашборде\n"
            success_msg += "• Комплексный анализ готовности"
            st.success(success_msg)
            
            # Обновляем страницу через 2 секунды
            import time
            time.sleep(2)
            st.rerun()
            
        except Exception as e:
            st.error(f"❌ Ошибка добавления тестовых данных: {e}")

def show_welcome_screen():
    """Экран приветствия для неподключённых пользователей"""
    st.markdown("## Добро пожаловать в персональный AI тренер! 🏃‍♂️")
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
    """Дашборд тренировок"""
    st.header("📊 Дашборд тренировок")
    
    # Получение данных из БД
    activities_df = st.session_state.database.get_activities(30)
    
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
                processor = Phase1DataProcessor(st.session_state.database)
                processed_sleep = processor.process_sleep_data(sleep_data)
                processed_health = processor.process_health_data(health_data)
                
                st.session_state.database.save_phase1_data(
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
    
    # Основные метрики
    # Используем адаптивную сетку: 2 строки по 3 колонки
    col1, col2, col3 = st.columns(3)
    col4, col5, col6 = st.columns(3)
    
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
            tss_val = row['tss'] if 'tss' in row and pd.notna(row['tss']) else 0
            # Обрабатываем NaN и None значения
            if pd.isna(tss_val) or tss_val is None:
                tss_val = 0
            tss_data.append(float(tss_val))
            dates.append(row['date'])
        
        current_metrics = banister.get_current_metrics(tss_data, dates)
        
        # Цвет для TSB
        tsb_value = current_metrics['tsb'] if 'tsb' in current_metrics else 0
        if tsb_value > 5:
            tsb_color = "🟢"
        elif tsb_value > -10:
            tsb_color = "🟡"
        elif tsb_value > -30:
            tsb_color = "🟠"
        else:
            tsb_color = "🔴"
        
        st.metric("Форма (TSB)", f"{tsb_color} {tsb_value}", help="Training Stress Balance - показатель формы")
    
    with col6:
        # Расчет комплексного индекса готовности
        from data.data_processor_phase1 import Phase1DataProcessor
        
        # Получаем последние данные для расчета индекса
        sleep_df = st.session_state.database.get_sleep_data(7)
        hrv_df = st.session_state.database.get_hrv_data(7)
        health_df = st.session_state.database.get_daily_health(7)
        training_df = st.session_state.database.get_training_status_history(7)
        
        readiness_data = None
        if not sleep_df.empty or not hrv_df.empty or not health_df.empty:
            # Берем последние данные
            latest_sleep = sleep_df.iloc[0].to_dict() if not sleep_df.empty else {}
            latest_hrv = hrv_df.iloc[0].to_dict() if not hrv_df.empty else {}
            latest_health = health_df.iloc[0].to_dict() if not health_df.empty else {}
            latest_training = training_df.iloc[0].to_dict() if not training_df.empty else {}
            
            readiness_data = Phase1DataProcessor.calculate_comprehensive_readiness(
                latest_sleep, latest_hrv, latest_health, latest_training
            )
        
        if readiness_data and 'readiness_score' in readiness_data:
            score = readiness_data['readiness_score']
            if score >= 80:
                score_color = "🟢"
            elif score >= 60:
                score_color = "🟡"
            elif score >= 40:
                score_color = "🟠"
            else:
                score_color = "🔴"
            
            factors_count = len(readiness_data.get('factors_used', []))
            st.metric(
                "Готовность", 
                f"{score_color} {score:.0f}",
                help=f"Комплексный индекс готовности (на основе {factors_count} факторов)"
            )
        else:
            st.metric("Готовность", "Н/Д", help="Недостаточно данных для расчета. Выполните синхронизацию.")
    
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
            
            theme = get_plotly_theme()
            fig = px.bar(daily_stats, x='date', y='duration_minutes', 
                        title="⏱️ Время тренировок по дням",
                        labels={'duration_minutes': 'Время (мин)', 'date': 'Дата'},
                        template=theme['template'])
            fig.update_layout(
                paper_bgcolor=theme['paper_bgcolor'],
                plot_bgcolor=theme['plot_bgcolor'],
                font_color=theme['font_color']
            )
            st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        # Распределение по видам спорта
        if not activities_df.empty:
            sport_dist = activities_df['sport'].value_counts()
            theme = get_plotly_theme()
            fig = px.pie(values=sport_dist.values, names=sport_dist.index,
                        title="🏃‍♂️ Распределение по видам спорта",
                        template=theme['template'])
            fig.update_layout(
                paper_bgcolor=theme['paper_bgcolor'],
                plot_bgcolor=theme['plot_bgcolor'],
                font_color=theme['font_color']
            )
            st.plotly_chart(fig, use_container_width=True)
    
    # Таблица последних активностей
    st.subheader("📋 Последние активности")
    if not activities_df.empty:
        display_df = activities_df.head(10)[['date', 'sport', 'duration_minutes', 'distance_km', 'avg_hr', 'tss']].copy()
        
        # Безопасное форматирование даты
        if pd.api.types.is_datetime64_any_dtype(display_df['date']):
            display_df['date'] = display_df['date'].apply(lambda x: format_date(x, 'display'))
        else:
            # Если дата не в datetime формате, преобразуем её
            display_df['date'] = pd.to_datetime(display_df['date']).apply(lambda x: format_date(x, 'display'))
        
        display_df['duration_minutes'] = display_df['duration_minutes'].round(0).astype(int)
        display_df['distance_km'] = display_df['distance_km'].round(1)
        
        display_df.columns = ['Дата', 'Вид спорта', 'Время (мин)', 'Дистанция (км)', 'Ср. пульс', 'TSS']
        
        # Отображаем таблицу с учетом темы
        if st.session_state.get('dark_mode', False):
            st.markdown(create_dark_table_html(display_df, 400), unsafe_allow_html=True)
        else:
            st.dataframe(display_df, use_container_width=True, height=400)
        
    else:
        st.info("Нет данных об активностях. Синхронизируйтесь с Garmin Connect.")
    
    # Детальный анализ готовности
    st.subheader("🎯 Комплексный анализ готовности")
    
    # Получаем данные снова для детального анализа
    sleep_df = st.session_state.database.get_sleep_data(7)
    hrv_df = st.session_state.database.get_hrv_data(7)
    health_df = st.session_state.database.get_daily_health(7)
    training_df = st.session_state.database.get_training_status_history(7)
    
    if not sleep_df.empty or not hrv_df.empty or not health_df.empty:
        from data.data_processor_phase1 import Phase1DataProcessor
        
        # Берем последние данные
        latest_sleep = sleep_df.iloc[0].to_dict() if not sleep_df.empty else {}
        latest_hrv = hrv_df.iloc[0].to_dict() if not hrv_df.empty else {}
        latest_health = health_df.iloc[0].to_dict() if not health_df.empty else {}
        latest_training = training_df.iloc[0].to_dict() if not training_df.empty else {}
        
        readiness_data = Phase1DataProcessor.calculate_comprehensive_readiness(
            latest_sleep, latest_hrv, latest_health, latest_training
        )
        
        if readiness_data and 'readiness_score' in readiness_data:
            col1, col2 = st.columns([1, 2])
            
            with col1:
                score = readiness_data['readiness_score']
                if score >= 80:
                    status_text = "🟢 Отлично"
                    status_desc = "Готовы к интенсивным тренировкам"
                elif score >= 60:
                    status_text = "🟡 Хорошо"
                    status_desc = "Умеренные нагрузки"
                elif score >= 40:
                    status_text = "🟠 Средне"
                    status_desc = "Легкие тренировки"
                else:
                    status_text = "🔴 Низко"
                    status_desc = "Отдых и восстановление"
                
                st.metric("Общая готовность", f"{score:.1f}/100")
                st.write(f"**Статус:** {status_text}")
                st.write(f"**Рекомендация:** {status_desc}")
            
            with col2:
                st.write("**Факторы влияния:**")
                
                factor_scores = readiness_data.get('factor_scores', {})
                factors_used = readiness_data.get('factors_used', [])
                
                # Создаем прогресс-бары для каждого фактора
                for factor in factors_used:
                    factor_score = factor_scores.get(factor, 0)
                    
                    factor_names = {
                        'sleep': '😴 Качество сна',
                        'hrv': '💓 Вариабельность ритма',
                        'resting_hr': '💗 Пульс покоя',
                        'training_readiness': '🎯 Готовность Garmin',
                        'stress': '😌 Уровень стресса'
                    }
                    
                    factor_name = factor_names.get(factor, factor)
                    st.write(f"{factor_name}: {factor_score:.1f}/100")
                    st.progress(factor_score / 100)
        else:
            st.info("💡 Для расчета индекса готовности нужны данные сна, HRV или пульса покоя. Выполните синхронизацию с Garmin Connect.")
    else:
        st.info("💡 Нет данных для анализа готовности. Синхронизируйте данные с Garmin Connect для получения комплексного анализа.")

def show_activities():
    """Страница активностей"""
    st.header("🏃‍♂️ Ваши активности")
    
    # Получаем данные активностей
    activities_df = st.session_state.database.get_activities(30)  # За последние 30 дней
    
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
        
        # График TSS
        theme = get_plotly_theme()
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
    if st.session_state.get('dark_mode', False):
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
    """Страница анализа HRV"""
    st.header("💓 Анализ вариабельности сердечного ритма (HRV)")
    
    # Получаем HRV данные за максимальный период для корректной фильтрации
    hrv_df = st.session_state.database.get_hrv_data(90)  # Получаем больше данных для фильтрации
    
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
    latest_data = hrv_df.iloc[0]  # Самая свежая запись (данные сортированы по убыванию)
    # Базовый уровень рассчитываем от выбранного периода анализа
    baseline_rmssd = hrv_df['rmssd'].mean() # hrv_df не может быть пустым на этом этапе
    
    latest_date = latest_data['date'] if 'date' in latest_data else 'Н/Д'
    st.subheader(f"📊 Текущее состояние (данные от {latest_date})")
    
    # Адаптивная сетка: 2x2 на мобильных
    col1, col2 = st.columns(2)
    col3, col4 = st.columns(2)
    
    with col1:
        current_rmssd = latest_data['rmssd'] if pd.notna(latest_data['rmssd']) else 0
        delta_rmssd = current_rmssd - baseline_rmssd if baseline_rmssd > 0 else 0
        st.metric(
            "RMSSD (мс)", 
            f"{current_rmssd:.1f}",
            f"{delta_rmssd:+.1f} от среднего"
        )
    
    with col2:
        # Проверяем стресс-индекс
        stress_score = None
        if 'stress_score' in latest_data and latest_data['stress_score'] is not None and not pd.isna(latest_data['stress_score']):
            stress_score = latest_data['stress_score']
            stress_color = "🟢" if stress_score < 30 else "🟡" if stress_score < 60 else "🔴"
            st.metric("Стресс-индекс", f"{stress_color} {stress_score:.0f}")
        else:
            st.metric("Стресс-индекс", "Н/Д", help="Данные о стрессе недоступны. Синхронизируйте с Garmin Connect.")
    
    with col3:
        # Проверяем индекс восстановления
        recovery_score = None
        if 'recovery_score' in latest_data and latest_data['recovery_score'] is not None and not pd.isna(latest_data['recovery_score']):
            recovery_score = latest_data['recovery_score']
            recovery_color = "🟢" if recovery_score > 70 else "🟡" if recovery_score > 40 else "🔴"
            st.metric("Восстановление", f"{recovery_color} {recovery_score:.0f}%")
        else:
            # Рассчитываем на основе RMSSD если HRV анализатор доступен
            try:
                calculated_recovery = hrv_analyzer.recovery_score(current_rmssd, baseline_rmssd) if current_rmssd > 0 else 50
                recovery_color = "🟢" if calculated_recovery > 70 else "🟡" if calculated_recovery > 40 else "🔴"
                st.metric("Восстановление", f"{recovery_color} {calculated_recovery:.0f}%", help="Расчет на основе RMSSD")
            except:
                st.metric("Восстановление", "Н/Д", help="Данные Body Battery недоступны. Синхронизируйте с Garmin Connect.")
    
    with col4:
        # Рекомендация на основе последних данных
        if current_rmssd > baseline_rmssd * 1.1:
            recommendation = "🟢 Интенсивная тренировка"
        elif current_rmssd > baseline_rmssd * 0.9:
            recommendation = "🟡 Умеренная нагрузка"
        else:
            recommendation = "🔴 Отдых/восстановление"
        
        st.metric("Рекомендация", recommendation)
    
    # Графики динамики
    if len(hrv_df) > 1:
        st.subheader("📈 Динамика показателей")
        
        # График RMSSD
        fig_rmssd = go.Figure()
        
        # Основная линия RMSSD
        fig_rmssd.add_trace(go.Scatter(
            x=hrv_df['date'],
            y=hrv_df['rmssd'],
            mode='lines+markers',
            name='RMSSD',
            line=dict(color='blue', width=2),
            marker=dict(size=6)
        ))
        
        # Добавляем среднее и/или тренд
        if trend_option in ["Среднее", "Среднее + Тренд"]:
            avg_rmssd = hrv_df['rmssd'].mean()
            fig_rmssd.add_hline(
                y=avg_rmssd, 
                line_dash="dash", 
                line_color="red",
                annotation_text=f"Среднее: {avg_rmssd:.1f} мс"
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
                
                # Добавляем линию тренда
                fig_rmssd.add_trace(go.Scatter(
                    x=valid_data['date'],
                    y=trend_values,
                    mode='lines',
                    name=f'Тренд {trend_direction} ({trend_change:+.1f} мс)',
                    line=dict(color='green', width=2, dash='dot'),
                    hovertemplate="Тренд: %{y:.1f} мс<extra></extra>"
                ))
        
        fig_rmssd.update_layout(
            title="Динамика RMSSD",
            xaxis_title="Дата",
            yaxis_title="RMSSD (мс)",
            height=400
        )
        
        st.plotly_chart(fig_rmssd, use_container_width=True)
    
    # График корреляции с тренировками
    if not hrv_df.empty:
        st.subheader("🔍 Анализ взаимосвязей")
        
        # Получаем данные активностей за тот же период
        activities_df = st.session_state.database.get_activities(period_days)
        
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
            
            # График HRV vs нагрузка
            fig_correlation = go.Figure()
            
            # RMSSD
            fig_correlation.add_trace(go.Scatter(
                x=combined_df['date'],
                y=combined_df['rmssd'],
                mode='lines+markers',
                name='RMSSD',
                yaxis='y',
                line=dict(color='blue')
            ))
            
            # TSS (инвертированная шкала для лучшей визуализации)
            fig_correlation.add_trace(go.Scatter(
                x=combined_df['date'],
                y=combined_df['tss'],
                mode='lines+markers',
                name='TSS (нагрузка)',
                yaxis='y2',
                line=dict(color='orange')
            ))
            
            fig_correlation.update_layout(
                title="Взаимосвязь HRV и тренировочной нагрузки",
                xaxis_title="Дата",
                yaxis=dict(
                    title="RMSSD (мс)",
                    side="left"
                ),
                yaxis2=dict(
                    title="TSS (нагрузка)",
                    side="right",
                    overlaying="y"
                ),
                height=400
            )
            
            st.plotly_chart(fig_correlation, use_container_width=True)
            
            # Улучшенный анализ корреляции с запаздыванием
            if len(combined_df) > 5:
                col1, col2 = st.columns(2)
                
                with col1:
                    st.write("**📊 Анализ корреляции HRV и нагрузки:**")
                    
                    # Корреляция в тот же день
                    correlation_same_day = combined_df[['rmssd', 'tss']].corr().iloc[0, 1]
                    
                    # Корреляция с запаздыванием (HRV следующего дня vs TSS предыдущего)
                    combined_shifted = combined_df.copy()
                    combined_shifted['tss_prev'] = combined_shifted['tss'].shift(1)  # TSS предыдущего дня
                    correlation_lag1 = combined_shifted[['rmssd', 'tss_prev']].corr().iloc[0, 1]
                    
                    # Кумулятивная нагрузка за последние 3 дня
                    combined_shifted['tss_3day'] = combined_shifted['tss'].rolling(window=3, min_periods=1).sum()
                    correlation_cumulative = combined_shifted[['rmssd', 'tss_3day']].corr().iloc[0, 1]
                    
                    if not pd.isna(correlation_same_day):
                        st.metric("Тот же день", f"{correlation_same_day:.3f}")
                    
                    if not pd.isna(correlation_lag1):
                        st.metric("С запаздыванием (1 день)", f"{correlation_lag1:.3f}")
                    
                    if not pd.isna(correlation_cumulative):
                        st.metric("Кумулятивная (3 дня)", f"{correlation_cumulative:.3f}")
                
                with col2:
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
        if st.session_state.get('dark_mode', False):
            st.markdown(create_dark_table_html(table_df), unsafe_allow_html=True)
        else:
            st.dataframe(table_df, use_container_width=True, hide_index=True)
    
    # Рекомендации
    st.subheader("💡 Рекомендации по HRV")
    
    if not hrv_df.empty and len(hrv_df) > 7:
        # Анализ тенденций за последнюю неделю
        recent_data = hrv_df.tail(7)
        rmssd_trend = recent_data['rmssd'].pct_change(fill_method='pad').mean() * 100
        
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
    """Страница анализа сна"""
    st.header("😴 Анализ качества сна")
    
    # Получаем данные сна из БД
    sleep_df = st.session_state.database.get_sleep_data(90)
    
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
    
    # Текущее состояние сна (последние данные)
    latest_sleep = filtered_df.iloc[0] if not filtered_df.empty else None
    
    if latest_sleep is not None:
        st.subheader(f"🌙 Последний сон ({format_date(latest_sleep['date'], 'display')})")
        
        # Адаптивная сетка: 2x2 на мобильных
        col1, col2 = st.columns(2)
        col3, col4 = st.columns(2)
        
        with col1:
            total_minutes = latest_sleep.get('total_sleep_minutes', 0)
            hours = total_minutes // 60
            minutes = total_minutes % 60
            st.metric("Продолжительность", f"{hours}ч {minutes}м")
        
        with col2:
            sleep_score = latest_sleep.get('sleep_score', 0)
            score_color = "🟢" if sleep_score >= 80 else "🟡" if sleep_score >= 60 else "🔴"
            st.metric("Качество сна", f"{score_color} {sleep_score:.1f}")
        
        with col3:
            efficiency = latest_sleep.get('sleep_efficiency', 0)
            st.metric("Эффективность", f"{efficiency:.1f}%")
        
        with col4:
            awakenings = latest_sleep.get('awakenings_count', 0)
            st.metric("Пробуждения", f"{awakenings:.0f}")
        
        # Детали фаз сна
        st.subheader("🌀 Фазы сна")
        col1, col2, col3 = st.columns(3)
        
        with col1:
            deep_min = latest_sleep.get('deep_sleep_minutes', 0)
            deep_pct = (deep_min / total_minutes * 100) if total_minutes > 0 else 0
            st.metric(
                "Глубокий сон", 
                f"{deep_min}мин",
                f"{deep_pct:.1f}% от сна"
            )
        
        with col2:
            light_min = latest_sleep.get('light_sleep_minutes', 0)
            light_pct = (light_min / total_minutes * 100) if total_minutes > 0 else 0
            st.metric(
                "Легкий сон", 
                f"{light_min}мин",
                f"{light_pct:.1f}% от сна"
            )
        
        with col3:
            rem_min = latest_sleep.get('rem_sleep_minutes', 0)
            rem_pct = (rem_min / total_minutes * 100) if total_minutes > 0 else 0
            st.metric(
                "REM сон", 
                f"{rem_min}мин",
                f"{rem_pct:.1f}% от сна"
            )
        
        # Время сна
        if latest_sleep.get('bedtime') and latest_sleep.get('wakeup_time'):
            col1, col2 = st.columns(2)
            with col1:
                st.metric("🌙 Время засыпания", latest_sleep['bedtime'])
            with col2:
                st.metric("🌅 Время пробуждения", latest_sleep['wakeup_time'])
    
    # Тренды и графики
    st.subheader("📈 Тренды сна")
    
    if len(filtered_df) > 1:
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots
        
        # График качества сна во времени
        fig = make_subplots(
            rows=2, cols=2,
            subplot_titles=[
                'Качество сна', 'Продолжительность сна',
                'Эффективность сна', 'Пробуждения'
            ],
            vertical_spacing=0.15
        )
        
        dates = filtered_df['date']
        
        # Качество сна
        fig.add_trace(
            go.Scatter(
                x=dates, 
                y=filtered_df['sleep_score'],
                mode='lines+markers',
                name='Качество сна',
                line=dict(color='#1f77b4', width=2),
                marker=dict(size=6)
            ),
            row=1, col=1
        )
        
        # Продолжительность
        sleep_hours = filtered_df['total_sleep_minutes'] / 60
        fig.add_trace(
            go.Scatter(
                x=dates, 
                y=sleep_hours,
                mode='lines+markers',
                name='Часы сна',
                line=dict(color='#ff7f0e', width=2),
                marker=dict(size=6)
            ),
            row=1, col=2
        )
        
        # Эффективность
        fig.add_trace(
            go.Scatter(
                x=dates, 
                y=filtered_df['sleep_efficiency'],
                mode='lines+markers',
                name='Эффективность %',
                line=dict(color='#2ca02c', width=2),
                marker=dict(size=6)
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
                line=dict(color='#d62728', width=2),
                marker=dict(size=6)
            ),
            row=2, col=2
        )
        
        fig.update_layout(
            height=500,
            showlegend=False,
            title_text=f"Тренды сна за {period_label}"
        )
        
        # Добавляем средние линии
        avg_score = filtered_df['sleep_score'].mean()
        avg_hours = filtered_df['total_sleep_minutes'].mean() / 60
        avg_efficiency = filtered_df['sleep_efficiency'].mean()
        avg_awakenings = filtered_df['awakenings_count'].mean()
        
        # Горизонтальные линии средних значений
        for row, col, avg_val, color in [
            (1, 1, avg_score, '#1f77b4'),
            (1, 2, avg_hours, '#ff7f0e'),
            (2, 1, avg_efficiency, '#2ca02c'),
            (2, 2, avg_awakenings, '#d62728')
        ]:
            fig.add_hline(
                y=avg_val, 
                line_dash="dash", 
                line_color=color,
                opacity=0.5,
                row=row, col=col
            )
        
        st.plotly_chart(fig, use_container_width=True)
        
        # Статистика за период
        st.subheader("📊 Статистика за период")
        
        # Адаптивная сетка: 2x2 на мобильных
        col1, col2 = st.columns(2)
        col3, col4 = st.columns(2)
        
        with col1:
            avg_quality = filtered_df['sleep_score'].mean()
            # Проверяем на NaN значения
            if pd.isna(avg_quality):
                avg_quality = 0
            quality_trend = "📈" if len(filtered_df) > 0 and not pd.isna(filtered_df['sleep_score'].iloc[0]) and filtered_df['sleep_score'].iloc[0] > avg_quality else "📉"
            st.metric(
                "Среднее качество", 
                f"{avg_quality:.1f}",
                f"{quality_trend} тренд"
            )
        
        with col2:
            avg_duration = filtered_df['total_sleep_minutes'].mean() / 60
            st.metric(
                "Средняя длительность", 
                f"{avg_duration:.1f}ч"
            )
        
        with col3:
            avg_eff = filtered_df['sleep_efficiency'].mean()
            st.metric(
                "Средняя эффективность", 
                f"{avg_eff:.1f}%"
            )
        
        with col4:
            avg_awake = filtered_df['awakenings_count'].mean()
            st.metric(
                "Среднее пробуждений", 
                f"{avg_awake:.1f}"
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
                title=f"Среднее распределение фаз сна за {period_label}",
                color_discrete_sequence=['#1f77b4', '#ff7f0e', '#2ca02c']
            )
            
            fig_pie.update_traces(textinfo='percent+label')
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
    # Боковая панель с управлением чатами
    with st.sidebar:
        st.subheader("💬 Управление чатами")
        
        # Кнопки управления чатом
        col1, col2 = st.columns(2)
        with col1:
            if st.button("➕ Новый чат", use_container_width=True, type="primary"):
                new_chat_id = st.session_state.chat_manager.create_new_chat()
                st.session_state.current_chat_id = new_chat_id
                st.rerun()
        
        with col2:
            # Кнопка очистки текущего чата
            if st.session_state.current_chat_id and st.button("🧹 Очистить", use_container_width=True):
                if st.session_state.chat_manager.clear_chat(st.session_state.current_chat_id):
                    st.success("Чат очищен")
                    st.rerun()
        
        # Список чатов
        chats = st.session_state.chat_manager.get_chat_list()
        
        if chats:
            st.markdown('<div class="sidebar-chat-list">', unsafe_allow_html=True)
            
            for chat in chats:
                is_current = chat["id"] == st.session_state.current_chat_id
                
                col1, col2 = st.columns([4, 1])
                
                with col1:
                    # Кнопка выбора чата
                    chat_title = chat['title'][:30] + ("..." if len(chat['title']) > 30 else "")
                    button_text = f"{'🔵' if is_current else '💬'} {chat_title}"
                    
                    if st.button(
                        button_text,
                        key=f"chat_{chat['id']}",
                        use_container_width=True,
                        help=f"Сообщений: {chat['message_count']} • {chat['updated_at'][:16].replace('T', ' ')}"
                    ):
                        st.session_state.current_chat_id = chat["id"]
                        # Переключаемся на страницу AI коучинга
                        st.session_state.selected_page = "🤖 AI Коучинг"
                        # Устанавливаем флаг для автоматического переключения на чат
                        st.session_state.switch_to_chat_tab = True
                        st.success(f"Выбран чат: {chat['title'][:20]}...")
                        st.rerun()
                
                with col2:
                    # Кнопка удаления чата
                    if st.button("🗑️", key=f"delete_{chat['id']}", help="Удалить чат"):
                        if st.session_state.chat_manager.delete_chat(chat["id"]):
                            if st.session_state.current_chat_id == chat["id"]:
                                st.session_state.current_chat_id = None
                            st.success("Чат удален")
                            st.rerun()
            
            st.markdown('</div>', unsafe_allow_html=True)
        else:
            st.info("Пока нет сохраненных чатов")

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
            
            # Для Google используем только работающие модели (протестированы с protobuf fix)
            available_models = [
                "models/gemini-2.5-flash",  # Самая новая и быстрая
                "models/gemini-2.0-flash-exp",  # Экспериментальная 2.0
                "models/gemini-2.0-flash",  # Стабильная 2.0
                "models/gemini-1.5-flash-latest",  # Последняя 1.5 Flash
                "models/gemini-1.5-flash",  # Стабильная 1.5 Flash
                "models/gemini-1.5-flash-8b",  # Компактная версия
            ]
            
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
    
    # Проверяем, нужно ли сразу показать чат
    if st.session_state.get('switch_to_chat_tab', False):
        # Сбрасываем флаг
        st.session_state.switch_to_chat_tab = False
        # Показываем кнопку возврата к вкладкам
        col1, col2 = st.columns([1, 4])
        with col1:
            if st.button("← Назад к вкладкам", key="back_to_tabs"):
                st.rerun()
        # Показываем чат сразу без вкладок
        st.markdown("### 💬 AI Чат")
        show_ai_chat()
    else:
        # Показываем обычные табы
        tab_chat, tab1, tab2, tab3, tab4, tab5 = st.tabs([
            "💬 AI Чат",
            "📊 Анализ состояния",
            "📅 Недельный план", 
            "🏃 Анализ тренировки",
            "❓ Вопрос коучу",
            "📚 Объяснение метрик"
        ])
        with tab_chat:
            show_ai_chat()
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
    

def show_ai_chat():
    """Современный интерфейс AI чата с сохранением и управлением"""
    # Проверяем подключение к AI
    if st.session_state.ai_coach is None:
        st.warning("👆 Настройте AI провайдера для использования чата")
        return
    
    # Менеджер чатов уже инициализирован в main()
    
    # Инициализация AI инструментов
    if "ai_tools" not in st.session_state:
        from models.ai_tools import AITools
        st.session_state.ai_tools = AITools(st.session_state.database)
    
    # Инициализация контекста данных
    if "data_context" not in st.session_state:
        st.session_state.data_context = None
        st.session_state.context_loaded = False
    
    # Текущий чат
    if "current_chat_id" not in st.session_state:
        st.session_state.current_chat_id = None
    
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
                data_context = AIDataContext(st.session_state.database)
                st.session_state.data_context = data_context.get_full_context(context_days)
                st.session_state.context_loaded = True
                st.success(f"✅ Данные обновлены")
        
        # Расширенная диагностика контекста
        st.divider()
        st.subheader("🔍 Диагностика данных")
        
        if st.session_state.context_loaded and st.session_state.data_context:
            context = st.session_state.data_context
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
                    system_prompt = create_chat_system_prompt_with_tools(st.session_state.data_context)
                    st.code(system_prompt, language="markdown")
                    
                with st.expander("🗄️ Полный контекст данных"):
                    from models.ai_data_context import AIDataContext
                    context_formatter = AIDataContext(None)
                    formatted_context = context_formatter.format_context_for_ai(st.session_state.data_context)
                    st.code(formatted_context, language="markdown")
        
        # Статистика чатов
        chats = st.session_state.chat_manager.get_chat_list()
        if chats:
            stats = st.session_state.chat_manager.get_stats()
            st.divider()
            st.subheader("📊 Статистика")
            col1, col2 = st.columns(2)
            col1.metric("Чатов", stats["total_chats"])
            col2.metric("Сообщений", stats["total_messages"])
    
    # Основная область чата
    st.title("🤖 AI Тренер")
    
    # Загрузка контекста при первом запуске
    if not st.session_state.context_loaded:
        with st.spinner("Загрузка данных для AI..."):
            from models.ai_data_context import AIDataContext
            data_context = AIDataContext(st.session_state.database)
            st.session_state.data_context = data_context.get_full_context(context_days)
            st.session_state.context_loaded = True
    
    # Контейнер для чата с улучшенным стилем
    with st.container():
        st.markdown('<div class="chat-container">', unsafe_allow_html=True)
        
        # Загружаем сообщения текущего чата
        current_messages = []
        if st.session_state.current_chat_id:
            current_messages = st.session_state.chat_manager.get_chat_messages(st.session_state.current_chat_id)
        
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

def process_modern_chat_message(user_input):
    """Обрабатывает сообщение в современном чате с сохранением"""
    # Создаем новый чат если его нет
    if not st.session_state.current_chat_id:
        st.session_state.current_chat_id = st.session_state.chat_manager.create_new_chat()
    
    # Добавляем сообщение пользователя в чат
    st.session_state.chat_manager.add_message(
        st.session_state.current_chat_id, 
        "user", 
        user_input
    )
    
    # Отображаем сообщение пользователя
    with st.chat_message("user"):
        st.write(user_input)
    
    # Генерируем ответ AI
    with st.chat_message("assistant"):
        # Создаем placeholder для стриминга
        response_placeholder = st.empty()
        
        try:
            # Создаем системный промпт с инструментами
            system_prompt = create_chat_system_prompt_with_tools(st.session_state.data_context)
            
            # Получаем историю разговора
            chat_messages = st.session_state.chat_manager.get_chat_messages(st.session_state.current_chat_id)
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
            ai_response = st.session_state.ai_coach.provider.generate_response(full_prompt, "")
            
            # Показываем состояние обработки инструментов
            response_placeholder.markdown("🔧 *Обрабатываю данные...*")
            
            # Обрабатываем инструменты в ответе
            final_response = process_tool_calls(ai_response)
            
            # Симулируем стриминг финального ответа
            simulate_streaming_response(response_placeholder, final_response)
            
            # Сохраняем ответ в чат
            st.session_state.chat_manager.add_message(
                st.session_state.current_chat_id,
                "assistant", 
                final_response
            )
            
            # Обновляем интерфейс для отображения нового сообщения
            st.rerun()
            
        except Exception as e:
            error_msg = f"❌ Ошибка AI: {e}"
            response_placeholder.markdown(error_msg)
            # Сохраняем ошибку в чат
            st.session_state.chat_manager.add_message(
                st.session_state.current_chat_id,
                "assistant", 
                error_msg
            )

def process_chat_message(user_input):
    """Обрабатывает сообщение пользователя в чате с поддержкой инструментов"""
    # Добавляем сообщение пользователя
    st.session_state.chat_messages.append({"role": "user", "content": user_input})
    
    # Отображаем сообщение пользователя
    with st.chat_message("user"):
        st.write(user_input)
    
    # Генерируем ответ AI
    with st.chat_message("assistant"):
        with st.spinner("AI тренер анализирует данные..."):
            try:
                # Создаем системный промпт с инструментами
                system_prompt = create_chat_system_prompt_with_tools(st.session_state.data_context)
                
                # Собираем историю разговора
                conversation_history = ""
                for msg in st.session_state.chat_messages[:-1]:  # Исключаем последнее сообщение
                    conversation_history += f"\n{msg['role'].upper()}: {msg['content']}"
                
                # Создаем полный промпт
                full_prompt = f"""
{system_prompt}

ИСТОРИЯ РАЗГОВОРА:{conversation_history}

НОВЫЙ ВОПРОС ПОЛЬЗОВАТЕЛЯ: {user_input}

Используй инструменты для получения точных данных. ОБЯЗАТЕЛЬНО завершай задачу полностью - если просят план, составляй конкретный план, а не только анализируй данные. Отвечай персонально, конкретно и полезно. Используй эмодзи.
"""
                
                # Получаем ответ от AI (может содержать запросы инструментов)
                ai_response = st.session_state.ai_coach.provider.generate_response(full_prompt, "")
                
                # Обрабатываем инструменты в ответе
                final_response = process_tool_calls(ai_response)
                
                # Отображаем финальный ответ
                st.markdown(final_response)
                
                # Сохраняем в историю
                st.session_state.chat_messages.append({"role": "assistant", "content": final_response})
                
            except Exception as e:
                st.error(f"❌ Ошибка AI: {e}")

def create_chat_system_prompt_with_tools(data_context):
    """Создает системный промпт с инструментами для доступа к данным"""
    
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
"""
    
    # Добавляем описание инструментов
    tools_description = st.session_state.ai_tools.format_tool_descriptions_for_ai()
    
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
            result = st.session_state.ai_tools.execute_tool(tool_name, **params)
            
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
    
    elif tool_name == "analyze_training_load":
        return f"""
**⚡ Анализ нагрузки:**
• Тренд нагрузки: {data['load_trend']}
• Распределение интенсивности:
  - Низкая: {data['intensity_distribution']['low_intensity_percent']:.1f}%
  - Умеренная: {data['intensity_distribution']['moderate_intensity_percent']:.1f}%
  - Высокая: {data['intensity_distribution']['high_intensity_percent']:.1f}%
"""
    
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
    
    if hasattr(st.session_state, 'database'):
        stats = st.session_state.database.get_database_stats()
        
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
                activities_df = st.session_state.database.get_activities(1)
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