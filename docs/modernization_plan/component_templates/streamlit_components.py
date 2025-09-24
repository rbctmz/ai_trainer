# Готовые шаблоны компонентов для AI Trainer

## 🎯 Метрики восстановления - Streamlit версия

```python
import streamlit.components.v1 as components
import plotly.graph_objects as go

def circular_progress_metric(value, title, subtitle, color="#4285f4"):
    """
    Создает круговую метрику прогресса с правильным рендерингом
    
    Args:
        value (int): Значение в процентах (0-100)
        title (str): Заголовок метрики
        subtitle (str): Подзаголовок с дополнительной информацией
        color (str): Цвет прогресса в hex формате
    """
    html_code = f"""
    <div style="
        display: flex;
        flex-direction: column;
        align-items: center;
        padding: 20px;
        background: white;
        border-radius: 15px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.1);
        margin: 10px;
        min-height: 200px;
        justify-content: center;
    ">
        <!-- Круговой прогресс -->
        <div style="
            width: 120px;
            height: 120px;
            border-radius: 50%;
            background: conic-gradient(
                {color} 0% {value}%, 
                #e8e8e8 {value}% 100%
            );
            display: flex;
            align-items: center;
            justify-content: center;
            margin-bottom: 15px;
            position: relative;
        ">
            <!-- Внутренний круг с текстом -->
            <div style="
                width: 85px;
                height: 85px;
                background: white;
                border-radius: 50%;
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 24px;
                font-weight: bold;
                color: {color};
                box-shadow: inset 0 0 10px rgba(0,0,0,0.1);
            ">
                {value}%
            </div>
        </div>
        
        <!-- Заголовок -->
        <div style="
            font-size: 16px;
            font-weight: bold;
            color: #2c3e50;
            margin-bottom: 5px;
            text-align: center;
        ">
            {title}
        </div>
        
        <!-- Подзаголовок -->
        <div style="
            font-size: 12px;
            color: #7f8c8d;
            text-align: center;
            line-height: 1.4;
        ">
            {subtitle}
        </div>
    </div>
    """
    
    components.html(html_code, height=250)

def plotly_gauge_metric(value, title, subtitle, color="#4285f4"):
    """
    Альтернативная реализация метрики через Plotly
    """
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=value,
        number={'suffix': "%", 'font': {'size': 40, 'color': color}},
        title={'text': f"<b>{title}</b><br><span style='font-size:12px;color:#7f8c8d'>{subtitle}</span>"},
        gauge={
            'axis': {'range': [None, 100], 'tickwidth': 1},
            'bar': {'color': color},
            'bgcolor': "white",
            'borderwidth': 2,
            'bordercolor': "#e8e8e8",
            'steps': [
                {'range': [0, 25], 'color': '#ffebee'},
                {'range': [25, 50], 'color': '#f3e5f5'},
                {'range': [50, 75], 'color': '#e8f5e8'},
                {'range': [75, 100], 'color': '#e3f2fd'}
            ]
        }
    ))
    
    fig.update_layout(
        height=300,
        margin=dict(l=20, r=20, t=80, b=20),
        font={'color': "#2c3e50", 'family': "Inter, Arial, sans-serif"},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)"
    )
    
    return fig

# Использование компонентов
def create_recovery_dashboard():
    """Создает панель метрик восстановления"""
    st.markdown("### 📊 Connect your heart rate data to see your recovery")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        # Вариант 1: HTML компонент
        circular_progress_metric(78, "RMSSD", "39.0 ms", "#4285f4")
        
    with col2:
        # Вариант 2: Plotly график
        fig = plotly_gauge_metric(100, "HR Rest", "56 bpm", "#ff9500")
        st.plotly_chart(fig, use_container_width=True)
        
    with col3:
        circular_progress_metric(30, "ESS", "Aug 23, 2025", "#34a853")
    
    # Статус восстановления
    components.html("""
    <div style="
        background: linear-gradient(135deg, #3498db 0%, #2ecc71 100%);
        color: white;
        padding: 15px 30px;
        border-radius: 25px;
        text-align: center;
        margin: 20px auto;
        max-width: 300px;
        font-weight: bold;
        font-size: 16px;
        box-shadow: 0 4px 15px rgba(52, 152, 219, 0.3);
    ">
        🚀 Driving Aerobic Recovery
    </div>
    """, height=80)
```

## 📅 Календарь тренировок - Streamlit версия

```python
def training_calendar_component():
    """
    Создает календарь тренировок с правильной CSS Grid разметкой
    """
    # Данные тренировок
    training_data = {
        'Пн': {'type': 'rest', 'activity': 'Отдых', 'details': ''},
        'Вт': {'type': 'cardio', 'activity': 'Другое', 'details': 'Н/Д км<br>Н/Д'},
        'Ср': {'type': 'cardio', 'activity': 'Другое', 'details': 'Н/Д км<br>Н/Д'},
        'Чт': {'type': 'cardio', 'activity': 'Другое', 'details': 'Н/Д км<br>Н/Д'},
        'Пт': {'type': 'rest', 'activity': 'Отдых', 'details': ''},
        'Сб': {'type': 'cardio', 'activity': 'Другое', 'details': 'Н/Д км<br>Н/Д'},
        'Вс': {'type': 'rest', 'activity': 'Отдых', 'details': ''},
    }
    
    # Генерируем CSS и HTML
    css_styles = """
    <style>
    .training-calendar {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
        gap: 15px;
        padding: 20px;
        background: white;
        border-radius: 15px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.1);
        margin: 20px 0;
    }
    
    .day-card {
        border-radius: 12px;
        padding: 20px 15px;
        text-align: center;
        min-height: 120px;
        display: flex;
        flex-direction: column;
        justify-content: space-between;
        transition: all 0.3s ease;
        cursor: pointer;
        position: relative;
        overflow: hidden;
    }
    
    .day-card:hover {
        transform: translateY(-5px);
        box-shadow: 0 8px 25px rgba(0,0,0,0.15);
    }
    
    .day-card.rest {
        background: linear-gradient(135deg, #2c3e50 0%, #34495e 100%);
        color: white;
    }
    
    .day-card.cardio {
        background: linear-gradient(135deg, #27ae60 0%, #2ecc71 100%);
        color: white;
        border: 3px solid #00ff88;
        box-shadow: 0 0 20px rgba(0, 255, 136, 0.3);
    }
    
    .day-title {
        font-weight: bold;
        font-size: 18px;
        margin-bottom: 10px;
        text-transform: uppercase;
        letter-spacing: 1px;
    }
    
    .day-activity {
        font-size: 14px;
        margin-bottom: 8px;
        font-weight: 500;
    }
    
    .day-details {
        font-size: 11px;
        opacity: 0.9;
        line-height: 1.3;
    }
    
    .day-card::before {
        content: '';
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        background: linear-gradient(45deg, rgba(255,255,255,0.1) 0%, transparent 100%);
        pointer-events: none;
    }
    
    @media (max-width: 768px) {
        .training-calendar {
            grid-template-columns: repeat(auto-fit, minmax(100px, 1fr));
            gap: 10px;
            padding: 15px;
        }
        .day-card {
            min-height: 100px;
            padding: 15px 10px;
        }
        .day-title { font-size: 16px; }
    }
    </style>
    """
    
    # Генерируем HTML календаря
    calendar_html = '<div class="training-calendar">'
    
    for day, data in training_data.items():
        calendar_html += f'''
        <div class="day-card {data['type']}" onclick="alert('Тренировка на {day}: {data['activity']}')">
            <div class="day-title">{day}</div>
            <div class="day-activity">{data['activity']}</div>
            <div class="day-details">{data['details']}</div>
        </div>
        '''
    
    calendar_html += '</div>'
    
    # Отображение через components.html для поддержки JavaScript
    components.html(css_styles + calendar_html, height=200)

def enhanced_training_calendar():
    """
    Расширенная версия календаря с дополнительными функциями
    """
    st.markdown("### 📅 Тренировки на этой неделе")
    
    # Календарь
    training_calendar_component()
    
    # Статистика недели
    week_stats_html = """
    <div style="
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
        gap: 15px;
        margin-top: 20px;
    ">
        <div style="
            background: linear-gradient(135deg, #3498db 0%, #2980b9 100%);
            color: white;
            padding: 20px;
            border-radius: 12px;
            text-align: center;
            box-shadow: 0 4px 12px rgba(52, 152, 219, 0.3);
        ">
            <div style="font-size: 24px; font-weight: bold;">4</div>
            <div style="font-size: 12px; opacity: 0.9;">Тренировочных дня</div>
        </div>
        
        <div style="
            background: linear-gradient(135deg, #e74c3c 0%, #c0392b 100%);
            color: white;
            padding: 20px;
            border-radius: 12px;
            text-align: center;
            box-shadow: 0 4px 12px rgba(231, 76, 60, 0.3);
        ">
            <div style="font-size: 24px; font-weight: bold;">3</div>
            <div style="font-size: 12px; opacity: 0.9;">Дня отдыха</div>
        </div>
        
        <div style="
            background: linear-gradient(135deg, #f39c12 0%, #e67e22 100%);
            color: white;
            padding: 20px;
            border-radius: 12px;
            text-align: center;
            box-shadow: 0 4px 12px rgba(243, 156, 18, 0.3);
        ">
            <div style="font-size: 24px; font-weight: bold;">0</div>
            <div style="font-size: 12px; opacity: 0.9;">Пропущенных</div>
        </div>
    </div>
    """
    
    st.markdown(week_stats_html, unsafe_allow_html=True)
```

## 🔗 Статус Garmin Connect

```python
def garmin_status_card(is_connected=True, email="greg.kisel@yandex.ru", last_sync=None):
    """
    Создает карточку статуса подключения к Garmin Connect
    """
    from datetime import datetime
    
    if last_sync is None:
        last_sync = datetime.now().strftime("%d.%m.%Y %H:%M")
    
    status_color = "#2ecc71" if is_connected else "#e74c3c"
    status_text = "Подключено" if is_connected else "Не подключено"
    status_icon = "✅" if is_connected else "❌"
    border_color = "#2ecc71" if is_connected else "#e74c3c"
    
    html_code = f"""
    <div style="
        background: white;
        border-radius: 15px;
        padding: 25px;
        margin: 15px 0;
        box-shadow: 0 4px 20px rgba(0,0,0,0.1);
        border-left: 5px solid {border_color};
        transition: transform 0.2s ease;
    " onmouseover="this.style.transform='translateY(-2px)'" onmouseout="this.style.transform='translateY(0)'">
        
        <!-- Заголовок с иконкой -->
        <div style="display: flex; align-items: center; margin-bottom: 20px;">
            <div style="
                background: linear-gradient(135deg, {status_color} 0%, {status_color}dd 100%);
                border-radius: 50%;
                width: 50px;
                height: 50px;
                display: flex;
                align-items: center;
                justify-content: center;
                margin-right: 15px;
                font-size: 20px;
            ">
                {status_icon}
            </div>
            <div>
                <h3 style="margin: 0; color: #2c3e50; font-size: 18px;">Garmin Connect</h3>
                <p style="margin: 5px 0 0 0; color: {status_color}; font-weight: 600; font-size: 14px;">
                    {status_text}
                </p>
            </div>
        </div>
        
        <!-- Информация об аккаунте -->
        <div style="
            background: #f8f9fa;
            border-radius: 8px;
            padding: 15px;
            margin-bottom: 15px;
        ">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                <span style="font-weight: 500; color: #495057; font-size: 13px;">Email:</span>
                <span style="color: #6c757d; font-size: 13px;">{email}</span>
            </div>
            
            {f'''
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <span style="font-weight: 500; color: #495057; font-size: 13px;">Последняя синхронизация:</span>
                <span style="color: #28a745; font-size: 13px;">{last_sync}</span>
            </div>
            ''' if is_connected else ''}
        </div>
        
        <!-- Кнопки действий -->
        <div style="display: flex; gap: 10px; justify-content: center;">
            <button style="
                background: linear-gradient(135deg, #007bff 0%, #0056b3 100%);
                color: white;
                border: none;
                border-radius: 8px;
                padding: 10px 20px;
                font-size: 14px;
                font-weight: 500;
                cursor: pointer;
                transition: all 0.3s ease;
            " onmouseover="this.style.transform='translateY(-1px)'" onmouseout="this.style.transform='translateY(0)'">
                {'🔄 Синхронизировать' if is_connected else '🔐 Подключить'}
            </button>
        </div>
    </div>
    """
    
    components.html(html_code, height=200)
```

## 🎯 Блок рекомендаций

```python
def ai_recommendations_block(recommendations_data=None):
    """
    Создает блок с персональными рекомендациями AI
    """
    if recommendations_data is None:
        recommendations_data = [
            {
                'icon': '💖',
                'title': 'Восстановление',
                'text': 'Ваш показатель RMSSD в норме (78%). Продолжайте текущий режим тренировок.',
                'priority': 'high'
            },
            {
                'icon': '⚡',
                'title': 'Нагрузка',
                'text': 'HR Rest показывает отличное восстановление (100%). Можно увеличить интенсивность.',
                'priority': 'medium'
            },
            {
                'icon': '📈',
                'title': 'Планирование',
                'text': 'Рекомендуем добавить 1-2 силовые тренировки на этой неделе.',
                'priority': 'low'
            }
        ]
    
    # Генерация HTML для рекомендаций
    recommendations_html = """
    <style>
    .recommendations-container {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        border-radius: 20px;
        padding: 30px;
        margin: 20px 0;
        color: white;
        box-shadow: 0 12px 40px rgba(102, 126, 234, 0.3);
        position: relative;
        overflow: hidden;
    }
    
    .recommendations-container::before {
        content: '';
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        background: linear-gradient(135deg, rgba(255,255,255,0.1) 0%, rgba(255,255,255,0) 100%);
        pointer-events: none;
    }
    
    .recommendations-title {
        display: flex;
        align-items: center;
        font-size: 28px;
        font-weight: bold;
        margin-bottom: 25px;
        position: relative;
        z-index: 1;
    }
    
    .recommendations-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
        gap: 20px;
        position: relative;
        z-index: 1;
    }
    
    .recommendation-item {
        background: rgba(255,255,255,0.15);
        border-radius: 15px;
        padding: 20px;
        backdrop-filter: blur(10px);
        border: 1px solid rgba(255,255,255,0.2);
        transition: all 0.3s ease;
        cursor: pointer;
    }
    
    .recommendation-item:hover {
        background: rgba(255,255,255,0.25);
        transform: translateY(-2px);
        box-shadow: 0 8px 25px rgba(0,0,0,0.15);
    }
    
    .recommendation-header {
        display: flex;
        align-items: center;
        margin-bottom: 15px;
    }
    
    .recommendation-icon {
        font-size: 24px;
        margin-right: 12px;
    }
    
    .recommendation-title {
        font-size: 18px;
        font-weight: 600;
        margin: 0;
    }
    
    .recommendation-text {
        font-size: 14px;
        line-height: 1.5;
        opacity: 0.95;
    }
    
    .priority-indicator {
        width: 8px;
        height: 8px;
        border-radius: 50%;
        margin-left: auto;
    }
    
    .priority-high { background: #ff4757; }
    .priority-medium { background: #ffa502; }
    .priority-low { background: #2ed573; }
    
    @media (max-width: 768px) {
        .recommendations-container { padding: 20px; }
        .recommendations-grid { grid-template-columns: 1fr; }
    }
    </style>
    
    <div class="recommendations-container">
        <div class="recommendations-title">
            🎯 Персональные рекомендации
        </div>
        
        <div class="recommendations-grid">
    """
    
    # Добавляем каждую рекомендацию
    for rec in recommendations_data:
        priority_class = f"priority-{rec['priority']}"
        recommendations_html += f"""
            <div class="recommendation-item" onclick="alert('Подробнее: {rec['title']}')">
                <div class="recommendation-header">
                    <span class="recommendation-icon">{rec['icon']}</span>
                    <h4 class="recommendation-title">{rec['title']}</h4>
                    <div class="priority-indicator {priority_class}"></div>
                </div>
                <p class="recommendation-text">{rec['text']}</p>
            </div>
        """
    
    recommendations_html += """
        </div>
    </div>
    """
    
    components.html(recommendations_html, height=400)
```

## 🎨 Глобальные стили

```python
def apply_global_ai_trainer_styles():
    """
    Применяет глобальные стили для всего приложения AI Trainer
    """
    st.markdown("""
    <style>
    /* Импорт современного шрифта */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');
    
    /* Основные стили приложения */
    .stApp {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
        background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
        min-height: 100vh;
    }
    
    /* Скрыть стандартные элементы Streamlit */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    .stDeployButton {visibility: hidden;}
    
    /* Стилизация боковой панели */
    .css-1d391kg {
        background: rgba(255, 255, 255, 0.95);
        backdrop-filter: blur(10px);
        border-right: 1px solid rgba(0, 0, 0, 0.1);
        box-shadow: 4px 0 20px rgba(0, 0, 0, 0.1);
    }
    
    /* Заголовки */
    h1, h2, h3, h4, h5, h6 {
        color: #2c3e50;
        font-weight: 600;
        letter-spacing: -0.5px;
    }
    
    h1 { font-size: 2.5rem; margin-bottom: 1rem; }
    h2 { font-size: 2rem; margin-bottom: 0.8rem; }
    h3 { font-size: 1.5rem; margin-bottom: 0.6rem; }
    
    /* Стандартные метрики Streamlit */
    [data-testid="metric-container"] {
        background: white;
        border-radius: 15px;
        padding: 20px;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.1);
        border-left: 5px solid #3498db;
        transition: transform 0.2s ease;
    }
    
    [data-testid="metric-container"]:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 30px rgba(0, 0, 0, 0.15);
    }
    
    /* Кнопки */
    .stButton > button {
        background: linear-gradient(135deg, #3498db 0%, #2980b9 100%);
        color: white;
        border: none;
        border-radius: 12px;
        padding: 12px 30px;
        font-weight: 600;
        font-size: 14px;
        transition: all 0.3s ease;
        box-shadow: 0 4px 15px rgba(52, 152, 219, 0.3);
    }
    
    .stButton > button:hover {
        background: linear-gradient(135deg, #2980b9 0%, #21618c 100%);
        transform: translateY(-2px);
        box-shadow: 0 8px 25px rgba(52, 152, 219, 0.4);
    }
    
    /* Поля ввода */
    .stTextInput > div > div > input,
    .stPasswordInput > div > div > input {
        border-radius: 10px;
        border: 2px solid #e1e8ed;
        padding: 12px 16px;
        font-size: 14px;
        transition: all 0.3s ease;
    }
    
    .stTextInput > div > div > input:focus,
    .stPasswordInput > div > div > input:focus {
        border-color: #3498db;
        box-shadow: 0 0 0 3px rgba(52, 152, 219, 0.1);
    }
    
    /* Селектбоксы */
    .stSelectbox > div > div {
        border-radius: 10px;
        border: 2px solid #e1e8ed;
    }
    
    /* Прогресс бары */
    .stProgress > div > div > div {
        background: linear-gradient(90deg, #3498db 0%, #2ecc71 100%);
        border-radius: 10px;
    }
    
    /* Сообщения об ошибках и успехе */
    .stAlert > div {
        border-radius: 10px;
        border: none;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
    }
    
    /* Табы */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        background: white;
        border-radius: 10px;
        padding: 5px;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
    }
    
    .stTabs [data-baseweb="tab"] {
        border-radius: 8px;
        padding: 10px 20px;
        font-weight: 500;
        transition: all 0.3s ease;
    }
    
    /* Колонки */
    .block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
        max-width: 1200px;
    }
    
    /* Анимации загрузки */
    .stSpinner > div {
        border-color: #3498db;
    }
    
    /* Кастомные классы */
    .metric-card {
        background: white;
        border-radius: 15px;
        padding: 25px;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.08);
        transition: all 0.3s ease;
        border: 1px solid rgba(0, 0, 0, 0.05);
    }
    
    .metric-card:hover {
        transform: translateY(-3px);
        box-shadow: 0 8px 30px rgba(0, 0, 0, 0.12);
    }
    
    .section-header {
        background: white;
        border-radius: 15px;
        padding: 20px 30px;
        margin-bottom: 20px;
        box-shadow: 0 2px 10px rgba(0, 0, 0, 0.05);
        border-left: 5px solid #3498db;
    }
    
    /* Адаптивность */
    @media (max-width: 768px) {
        .block-container {
            padding: 1rem;
        }
        h1 { font-size: 2rem; }
        h2 { font-size: 1.5rem; }
    }
    </style>
    """, unsafe_allow_html=True)
```

## 📱 Мобильное меню

```python
def create_mobile_menu():
    """
    Создает адаптивное мобильное меню
    """
    mobile_menu_html = """
    <style>
    .mobile-menu {
        display: none;
        position: fixed;
        top: 20px;
        right: 20px;
        z-index: 1000;
        background: white;
        border-radius: 15px;
        box-shadow: 0 8px 30px rgba(0,0,0,0.15);
        padding: 15px;
    }
    
    .menu-toggle {
        background: linear-gradient(135deg, #3498db 0%, #2980b9 100%);
        color: white;
        border: none;
        border-radius: 10px;
        width: 50px;
        height: 50px;
        font-size: 20px;
        cursor: pointer;
        transition: all 0.3s ease;
    }
    
    .menu-toggle:hover {
        transform: scale(1.05);
    }
    
    .menu-items {
        display: none;
        margin-top: 15px;
        min-width: 200px;
    }
    
    .menu-items.active {
        display: block;
    }
    
    .menu-item {
        display: block;
        padding: 12px 16px;
        color: #2c3e50;
        text-decoration: none;
        border-radius: 8px;
        margin-bottom: 5px;
        transition: all 0.2s ease;
        font-weight: 500;
    }
    
    .menu-item:hover {
        background: #f8f9fa;
        color: #3498db;
    }
    
    @media (max-width: 768px) {
        .mobile-menu {
            display: block;
        }
    }
    </style>
    
    <div class="mobile-menu">
        <button class="menu-toggle" onclick="toggleMenu()">☰</button>
        <div class="menu-items" id="menuItems">
            <a href="#dashboard" class="menu-item">📊 Дашборд</a>
            <a href="#training" class="menu-item">📅 Тренировки</a>
            <a href="#recommendations" class="menu-item">🎯 Рекомендации</a>
            <a href="#settings" class="menu-item">⚙️ Настройки</a>
        </div>
    </div>
    
    <script>
    function toggleMenu() {
        const menuItems = document.getElementById('menuItems');
        menuItems.classList.toggle('active');
    }
    
    // Закрыть меню при клике вне его
    document.addEventListener('click', function(event) {
        const menu = document.querySelector('.mobile-menu');
        if (!menu.contains(event.target)) {
            document.getElementById('menuItems').classList.remove('active');
        }
    });
    </script>
    """
    
    components.html(mobile_menu_html, height=0)
```

## 🔧 Утилиты для компонентов

```python
def safe_component_render(component_func, fallback_message="Компонент временно недоступен", *args, **kwargs):
    """
    Безопасно рендерит компонент с обработкой ошибок
    """
    try:
        component_func(*args, **kwargs)
    except Exception as e:
        st.error(f"⚠️ {fallback_message}")
        if st.checkbox("Показать техническую информацию", key=f"error_{id(component_func)}"):
            st.code(f"Ошибка: {str(e)}\nТип: {type(e).__name__}")

def loading_component(text="Загрузка данных..."):
    """
    Создает красивый индикатор загрузки
    """
    loading_html = f"""
    <div style="
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        padding: 40px;
        background: white;
        border-radius: 15px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.1);
        margin: 20px 0;
    ">
        <div style="
            width: 40px;
            height: 40px;
            border: 4px solid #f3f3f3;
            border-top: 4px solid #3498db;
            border-radius: 50%;
            animation: spin 1s linear infinite;
        "></div>
        <p style="
            margin-top: 15px;
            color: #7f8c8d;
            font-size: 14px;
            font-weight: 500;
        ">{text}</p>
    </div>
    
    <style>
    @keyframes spin {{
        0% {{ transform: rotate(0deg); }}
        100% {{ transform: rotate(360deg); }}
    }}
    </style>
    """
    
    return components.html(loading_html, height=140)

# Использование всех компонентов в главном приложении
def main_ai_trainer_app():
    """
    Главная функция приложения, использующая все созданные компоненты
    """
    # Применяем глобальные стили
    apply_global_ai_trainer_styles()
    
    # Мобильное меню
    create_mobile_menu()
    
    # Заголовок приложения
    st.markdown('<div class="section-header"><h1>🏃‍♂️ Персональный AI Тренер</h1></div>', 
                unsafe_allow_html=True)
    
    # Статус Garmin Connect
    with st.container():
        safe_component_render(garmin_status_card, "Ошибка загрузки статуса Garmin", 
                            is_connected=True, email="greg.kisel@yandex.ru")
    
    # Метрики восстановления
    with st.container():
        safe_component_render(create_recovery_dashboard, "Ошибка загрузки метрик")
    
    # Календарь тренировок
    with st.container():
        safe_component_render(enhanced_training_calendar, "Ошибка загрузки календаря")
    
    # AI рекомендации
    with st.container():
        safe_component_render(ai_recommendations_block, "Ошибка загрузки рекомендаций")

if __name__ == "__main__":
    main_ai_trainer_app()
```

Эти готовые компоненты решают все основные проблемы с HTML рендерингом в вашем Streamlit приложении и предоставляют современный, адаптивный интерфейс.
