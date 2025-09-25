"""Theme helpers for the Streamlit UI layer."""
from __future__ import annotations

from typing import Optional

import streamlit as st

from state import get_state_manager

def get_plotly_theme(dark_mode: Optional[bool] = None):
    """Получение темы для графиков Plotly"""
    if dark_mode is None:
        dark_mode = get_state_manager().dark_mode
    if dark_mode:
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

def apply_plotly_theme(fig, dark_mode: Optional[bool] = None):
    """Применяет тему к графику Plotly"""
    theme = get_plotly_theme(dark_mode)
    fig.update_layout(
        template=theme['template'],
        paper_bgcolor=theme['paper_bgcolor'],
        plot_bgcolor=theme['plot_bgcolor'],
        font=dict(color=theme['font_color']),
        xaxis=dict(gridcolor=theme['gridcolor']),
        yaxis=dict(gridcolor=theme['gridcolor'])
    )
    return fig

def apply_theme(dark_mode: Optional[bool] = None):
    """Применение темной или светлой темы"""
    state = get_state_manager()

    if not state.use_custom_theme:
        base_theme = st.get_option("theme.base") if callable(getattr(st, "get_option", None)) else "light"
        state.dark_mode = (base_theme or "light").lower() == "dark"
        return

    if dark_mode is None:
        dark_mode = state.dark_mode

    state.dark_mode = dark_mode

    # JavaScript для сохранения/загрузки темы из localStorage
    st.markdown(f"""
    <script>
        // Сохраняем текущую тему
        localStorage.setItem('aitrainer_dark_mode', '{str(dark_mode).lower()}');
    </script>
    """, unsafe_allow_html=True)

    if dark_mode:
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
        :root {
            /* Светлая тема - Material Design палитра */
            --background-color: #ffffff;
            --surface-1-color: #f5f5f5;
            --surface-2-color: #e8e8e8;
            --surface-3-color: #d4d4d4;
            --border-color: #e0e0e0;
            --hover-color: #f0f0f0;
            
            --accent-color: #1976d2;
            --accent-color-hover: #1565c0;
            --accent-secondary: #1e88e5;
            
            --text-primary-color: #212121;
            --text-secondary-color: #757575;
            --text-disabled-color: #bdbdbd;
            
            --success-bg-color: #c8e6c9;
            --warning-bg-color: #ffecb3;
            --error-bg-color: #ffcdd2;
            --info-bg-color: #bbdefb;
        }

        /* Основные стили */
        .stApp {
            background-color: var(--background-color);
            color: var(--text-primary-color);
        }
        
        /* Боковая панель - ИСПРАВЛЕНИЕ ДЛЯ СВЕТЛОЙ ТЕМЫ */
        section[data-testid="stSidebar"] {
            background-color: var(--surface-1-color) !important;
            border-right: 1px solid var(--border-color) !important;
        }
        
        /* Весь текст в сайдбаре должен быть тёмным */
        section[data-testid="stSidebar"] * {
            color: var(--text-primary-color) !important;
        }
        
        /* Заголовки в сайдбаре */
        section[data-testid="stSidebar"] h1,
        section[data-testid="stSidebar"] h2, 
        section[data-testid="stSidebar"] h3,
        section[data-testid="stSidebar"] .stMarkdown h1,
        section[data-testid="stSidebar"] .stMarkdown h2,
        section[data-testid="stSidebar"] .stMarkdown h3 {
            color: var(--text-primary-color) !important;
        }
        
        /* Параграфы и обычный текст в сайдбаре */
        section[data-testid="stSidebar"] p,
        section[data-testid="stSidebar"] .stMarkdown p,
        section[data-testid="stSidebar"] .stMarkdown,
        section[data-testid="stSidebar"] span,
        section[data-testid="stSidebar"] div {
            color: var(--text-primary-color) !important;
        }
        
        /* Selectbox в сайдбаре */
        section[data-testid="stSidebar"] .stSelectbox label,
        section[data-testid="stSidebar"] .stSelectbox > div > div,
        section[data-testid="stSidebar"] .stSelectbox select,
        section[data-testid="stSidebar"] .stSelectbox [data-baseweb="select"] {
            color: var(--text-primary-color) !important;
            background-color: var(--background-color) !important;
        }
        
        /* Выпадающий список в selectbox */
        section[data-testid="stSidebar"] .stSelectbox [role="listbox"],
        section[data-testid="stSidebar"] .stSelectbox [role="option"] {
            color: var(--text-primary-color) !important;
            background-color: var(--background-color) !important;
        }
        
        /* Expander в сайдбаре */
        section[data-testid="stSidebar"] .streamlit-expanderHeader {
            color: var(--text-primary-color) !important;
            background-color: var(--surface-2-color) !important;
        }
        
        section[data-testid="stSidebar"] .streamlit-expanderContent {
            background-color: var(--background-color) !important;
            border: 1px solid var(--border-color) !important;
        }
        
        /* Все элементы внутри expander в сайдбаре */
        section[data-testid="stSidebar"] .streamlit-expanderHeader *,
        section[data-testid="stSidebar"] .streamlit-expanderContent * {
            color: var(--text-primary-color) !important;
        }
        
        /* Специальные правила для expander заголовков */
        section[data-testid="stSidebar"] details summary {
            color: var(--text-primary-color) !important;
            background-color: var(--surface-1-color) !important;
        }
        
        section[data-testid="stSidebar"] details summary:hover {
            background-color: var(--hover-color) !important;
        }
        
        /* АГРЕССИВНЫЕ ПРАВИЛА для всех expander элементов */
        section[data-testid="stSidebar"] [data-testid="stExpander"],
        section[data-testid="stSidebar"] [data-testid="stExpander"] *,
        section[data-testid="stSidebar"] .streamlit-expander,
        section[data-testid="stSidebar"] .streamlit-expander * {
            color: var(--text-primary-color) !important;
        }
        
        section[data-testid="stSidebar"] [data-testid="stExpanderToggleIcon"] {
            color: var(--text-primary-color) !important;
        }
        
        /* Кнопки в сайдбаре */
        section[data-testid="stSidebar"] .stButton > button {
            color: var(--text-primary-color) !important;
            background-color: var(--background-color) !important;
            border: 1px solid var(--border-color) !important;
        }
        
        section[data-testid="stSidebar"] .stButton > button:hover {
            background-color: var(--hover-color) !important;
            border: 1px solid var(--accent-color) !important;
            color: var(--text-primary-color) !important;
        }
        
        /* Кнопка переключения темы - МАКСИМАЛЬНО АГРЕССИВНЫЕ ПРАВИЛА */
        section[data-testid="stSidebar"] button[title="Переключить тему"],
        section[data-testid="stSidebar"] .stButton button[title="Переключить тему"],
        section[data-testid="stSidebar"] .stButton > button[title="Переключить тему"],
        section[data-testid="stSidebar"] button[data-testid*="theme"],
        section[data-testid="stSidebar"] button[key="theme_toggle"] {
            color: var(--text-primary-color) !important;
            background: var(--background-color) !important;
            background-color: var(--background-color) !important;
            border: 1px solid var(--border-color) !important;
            box-shadow: none !important;
        }
        
        section[data-testid="stSidebar"] button[title="Переключить тему"]:hover,
        section[data-testid="stSidebar"] .stButton button[title="Переключить тему"]:hover,
        section[data-testid="stSidebar"] .stButton > button[title="Переключить тему"]:hover,
        section[data-testid="stSidebar"] button[data-testid*="theme"]:hover,
        section[data-testid="stSidebar"] button[key="theme_toggle"]:hover {
            background: var(--hover-color) !important;
            background-color: var(--hover-color) !important;
            border: 1px solid var(--accent-color) !important;
            color: var(--text-primary-color) !important;
            box-shadow: none !important;
        }
        
        /* СУПЕР-АГРЕССИВНОЕ правило для кнопки переключения темы */
        section[data-testid="stSidebar"] div:nth-child(2) button {
            color: var(--text-primary-color) !important;
            background: var(--background-color) !important;
            background-color: var(--background-color) !important;
            border: 1px solid var(--border-color) !important;
        }
        
        /* TextInput в сайдбаре */
        section[data-testid="stSidebar"] .stTextInput > div > div > input,
        section[data-testid="stSidebar"] .stTextInput label {
            color: var(--text-primary-color) !important;
            background-color: var(--background-color) !important;
        }
        
        /* Кнопка показать/скрыть пароль - МАКСИМАЛЬНО АГРЕССИВНЫЕ ПРАВИЛА */
        section[data-testid="stSidebar"] .stTextInput button,
        section[data-testid="stSidebar"] .stTextInput [data-baseweb="button"],
        section[data-testid="stSidebar"] .stTextInput div button,
        section[data-testid="stSidebar"] .stTextInput > div > div > button,
        section[data-testid="stSidebar"] input[type="password"] + button,
        section[data-testid="stSidebar"] [data-testid="baseButton-secondary"],
        section[data-testid="stSidebar"] [role="button"] {
            color: var(--text-primary-color) !important;
            background: var(--background-color) !important;
            background-color: var(--background-color) !important;
            border: 1px solid var(--border-color) !important;
            box-shadow: none !important;
        }
        
        section[data-testid="stSidebar"] .stTextInput button:hover,
        section[data-testid="stSidebar"] .stTextInput [data-baseweb="button"]:hover,
        section[data-testid="stSidebar"] .stTextInput div button:hover,
        section[data-testid="stSidebar"] .stTextInput > div > div > button:hover,
        section[data-testid="stSidebar"] input[type="password"] + button:hover,
        section[data-testid="stSidebar"] [data-testid="baseButton-secondary"]:hover,
        section[data-testid="stSidebar"] [role="button"]:hover {
            background: var(--hover-color) !important;
            background-color: var(--hover-color) !important;
            color: var(--text-primary-color) !important;
            box-shadow: none !important;
        }
        
        /* Дополнительные правила для любых SVG иконок в кнопках */
        section[data-testid="stSidebar"] button svg,
        section[data-testid="stSidebar"] [role="button"] svg,
        section[data-testid="stSidebar"] .stTextInput svg {
            fill: var(--text-primary-color) !important;
            color: var(--text-primary-color) !important;
        }
        
        /* Уведомления в сайдбаре */
        section[data-testid="stSidebar"] .stSuccess,
        section[data-testid="stSidebar"] .stError,
        section[data-testid="stSidebar"] .stWarning,
        section[data-testid="stSidebar"] .stInfo {
            color: var(--text-primary-color) !important;
        }
        
        /* Метрики */
        [data-testid="metric-container"] {
            background-color: var(--background-color);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 12px;
        }
        [data-testid="metric-container"] .stMetricValue {
            color: var(--accent-color);
        }
        
        /* Эспандеры */
        .streamlit-expanderHeader {
            background-color: var(--surface-1-color);
            color: var(--text-primary-color) !important;
            border-radius: 8px;
        }
        .streamlit-expanderContent {
            background-color: var(--background-color) !important;
            border: 1px solid var(--border-color) !important;
        }
        
        /* Таблицы */
        .dataframe, div[data-testid="stDataFrame"] {
            background-color: var(--background-color) !important;
            border: 1px solid var(--border-color) !important;
            border-radius: 8px !important;
        }
        
        .dataframe thead tr th,
        div[data-testid="stDataFrame"] thead tr th,
        .stDataFrame thead tr th {
            background-color: var(--surface-2-color) !important;
            color: var(--text-primary-color) !important;
            border-bottom: 1px solid var(--border-color) !important;
            border-right: 1px solid var(--border-color) !important;
        }
        
        .dataframe tbody tr,
        div[data-testid="stDataFrame"] tbody tr,
        .stDataFrame tbody tr {
            background-color: var(--background-color) !important;
            color: var(--text-primary-color) !important;
        }
        
        .dataframe tbody tr td,
        div[data-testid="stDataFrame"] tbody tr td,
        .stDataFrame tbody tr td {
            background-color: var(--background-color) !important;
            color: var(--text-primary-color) !important;
            border-right: 1px solid var(--border-color) !important;
            border-bottom: 1px solid var(--border-color) !important;
        }
        
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
        
        .dataframe tbody tr:nth-child(even),
        div[data-testid="stDataFrame"] tbody tr:nth-child(even),
        .stDataFrame tbody tr:nth-child(even) {
            background-color: var(--surface-1-color) !important;
        }
        
        .dataframe tbody tr:nth-child(even) td,
        div[data-testid="stDataFrame"] tbody tr:nth-child(even) td,
        .stDataFrame tbody tr:nth-child(even) td {
            background-color: var(--surface-1-color) !important;
        }
        
        /* Кнопки */
        .stButton > button {
            background-color: var(--background-color);
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
            background-color: var(--background-color) !important;
            color: var(--text-primary-color) !important;
            border: 1px solid var(--border-color) !important;
        }
        
        /* Вкладки */
        .stTabs [data-baseweb="tab-list"] {
            background-color: var(--surface-1-color);
            border-radius: 8px;
        }
        .stTabs [data-baseweb="tab"] {
            background-color: var(--background-color);
            color: var(--text-primary-color);
            border: 1px solid var(--border-color);
        }
        .stTabs [aria-selected="true"] {
            background-color: var(--accent-color);
            color: white;
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
            color: var(--text-primary-color);
        }
        .stInfo { 
            background-color: var(--info-bg-color) !important; 
            color: var(--text-primary-color) !important;
        }
        .stWarning { 
            background-color: var(--warning-bg-color) !important;
            color: var(--text-primary-color) !important; 
        }
        .stError { 
            background-color: var(--error-bg-color) !important;
            color: var(--text-primary-color) !important; 
        }
        .stSuccess { 
            background-color: var(--success-bg-color) !important;
            color: var(--text-primary-color) !important; 
        }
        
        /* Чат */
        .stChatInput > div > div > textarea,
        .stChatInputContainer textarea {
            background-color: var(--background-color) !important;
            color: var(--text-primary-color) !important;
            border: 1px solid var(--border-color) !important;
        }
        div[data-testid="stChatInput"] {
            background-color: var(--background-color) !important;
            border: 1px solid var(--border-color) !important;
            border-radius: 25px !important;
        }
        .stChatMessage {
            background-color: var(--surface-1-color);
            border-radius: 10px !important;
            color: var(--text-primary-color);
        }
        [data-testid="chatAvatarIcon-assistant"] {
            background-color: var(--accent-color) !important;
        }
        
        /* ФИНАЛЬНОЕ СУПЕР-АГРЕССИВНОЕ правило для всех кнопок в сайдбаре */
        section[data-testid="stSidebar"] button,
        section[data-testid="stSidebar"] [role="button"],
        section[data-testid="stSidebar"] [data-baseweb="button"] {
            color: var(--text-primary-color) !important;
            background: var(--background-color) !important;
            background-color: var(--background-color) !important;
            border: 1px solid var(--border-color) !important;
            box-shadow: none !important;
        }
        
        section[data-testid="stSidebar"] button:hover,
        section[data-testid="stSidebar"] [role="button"]:hover,
        section[data-testid="stSidebar"] [data-baseweb="button"]:hover {
            background: var(--hover-color) !important;
            background-color: var(--hover-color) !important;
            color: var(--text-primary-color) !important;
            border: 1px solid var(--accent-color) !important;
            box-shadow: none !important;
        }
        
        /* Убираем любые focus состояния */
        section[data-testid="stSidebar"] button:focus,
        section[data-testid="stSidebar"] [role="button"]:focus,
        section[data-testid="stSidebar"] [data-baseweb="button"]:focus {
            background: var(--background-color) !important;
            background-color: var(--background-color) !important;
            color: var(--text-primary-color) !important;
            border: 1px solid var(--border-color) !important;
            box-shadow: none !important;
            outline: none !important;
        }
        
        /* Убираем любые active состояния */
        section[data-testid="stSidebar"] button:active,
        section[data-testid="stSidebar"] [role="button"]:active,
        section[data-testid="stSidebar"] [data-baseweb="button"]:active {
            background: var(--hover-color) !important;
            background-color: var(--hover-color) !important;
            color: var(--text-primary-color) !important;
            border: 1px solid var(--accent-color) !important;
            box-shadow: none !important;
        }
        
        /* ВЫПАДАЮЩИЕ СПИСКИ SELECTBOX - ГЛОБАЛЬНЫЕ ПРАВИЛА */
        [data-baseweb="popover"],
        [data-baseweb="menu"],
        [role="listbox"],
        [role="option"],
        .stSelectbox [data-baseweb="popover"],
        .stSelectbox [data-baseweb="menu"],
        .stSelectbox [role="listbox"],
        .stSelectbox [role="option"] {
            background-color: var(--background-color) !important;
            color: var(--text-primary-color) !important;
            border: 1px solid var(--border-color) !important;
        }
        
        /* Выпадающие списки - элементы опций */
        [role="option"]:hover,
        .stSelectbox [role="option"]:hover,
        [data-baseweb="menu-item"]:hover {
            background-color: var(--hover-color) !important;
            color: var(--text-primary-color) !important;
        }
        
        /* Выпадающие списки - выбранные элементы */
        [role="option"][aria-selected="true"],
        .stSelectbox [role="option"][aria-selected="true"],
        [data-baseweb="menu-item"][aria-selected="true"] {
            background-color: var(--accent-color) !important;
            color: white !important;
        }
        
        /* ДОПОЛНИТЕЛЬНЫЕ ПРАВИЛА ДЛЯ ВСЕХ ВОЗМОЖНЫХ ВЫПАДАЮЩИХ ЭЛЕМЕНТОВ */
        /* Streamlit использует разные библиотеки для dropdown */
        [data-baseweb="select"] [role="listbox"],
        [data-baseweb="select"] [data-baseweb="list"],
        [data-baseweb="select"] ul,
        [data-baseweb="select"] li,
        [data-testid="stSelectbox-results"],
        .stSelectbox ul,
        .stSelectbox li,
        div[data-baseweb*="select"] > div,
        div[data-baseweb*="dropdown"] > div {
            background-color: var(--background-color) !important;
            color: var(--text-primary-color) !important;
            border-color: var(--border-color) !important;
        }
        
        /* Для всех элементов списков */
        [data-baseweb="select"] li:hover,
        [data-baseweb="list-item"]:hover,
        .stSelectbox li:hover {
            background-color: var(--hover-color) !important;
            color: var(--text-primary-color) !important;
        }
        
        /* Портальные элементы (которые рендерятся вне DOM структуры) */
        body > div[data-baseweb="popover"],
        body > div[data-baseweb="menu"],
        body > div[role="dialog"],
        body > div[data-baseweb="layer"] {
            background-color: var(--background-color) !important;
            border: 1px solid var(--border-color) !important;
        }
        
        /* Все текстовые элементы в портальных компонентах */
        body > div[data-baseweb="popover"] *,
        body > div[data-baseweb="menu"] *,
        body > div[role="dialog"] *,
        body > div[data-baseweb="layer"] * {
            color: var(--text-primary-color) !important;
            background-color: transparent !important;
        }
        
        /* Элементы опций в портальных компонентах */
        body > div[data-baseweb="popover"] [role="option"],
        body > div[data-baseweb="menu"] [role="option"],
        body > div[data-baseweb="popover"] li,
        body > div[data-baseweb="menu"] li {
            background-color: var(--background-color) !important;
            color: var(--text-primary-color) !important;
        }
        
        body > div[data-baseweb="popover"] [role="option"]:hover,
        body > div[data-baseweb="menu"] [role="option"]:hover,
        body > div[data-baseweb="popover"] li:hover,
        body > div[data-baseweb="menu"] li:hover {
            background-color: var(--hover-color) !important;
            color: var(--text-primary-color) !important;
        }
        </style>
        """, unsafe_allow_html=True)

__all__ = [
    'apply_theme',
    'create_dark_table_html',
    'get_plotly_theme',
    'apply_plotly_theme',
]
