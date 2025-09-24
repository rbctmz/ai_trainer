# Детальные решения для HTML рендеринга в Streamlit

## 🔧 Исправление конкретных проблем

### 1. Круговые диаграммы метрик (RMSSD, HR Rest)

**Проблема**: Кастомные HTML/CSS круги не рендерятся корректно

**Решение 1: Использование st.components.v1.html()**
```python
import streamlit.components.v1 as components

def create_circular_metric(value, label, subtitle, color="#4285f4"):
    html_code = f"""
    <div style="text-align: center; padding: 20px;">
        <div style="
            width: 120px; 
            height: 120px; 
            border-radius: 50%; 
            background: conic-gradient({color} 0% {value}%, #e0e0e0 {value}% 100%);
            display: flex; 
            align-items: center; 
            justify-content: center;
            margin: 0 auto 15px auto;
            position: relative;
        ">
            <div style="
                width: 80px; 
                height: 80px; 
                background: white; 
                border-radius: 50%;
                display: flex; 
                align-items: center; 
                justify-content: center;
                font-size: 24px; 
                font-weight: bold; 
                color: {color};
            ">
                {value}%
            </div>
        </div>
        <div style="font-size: 14px; font-weight: bold; color: #333; margin-bottom: 5px;">
            {label}
        </div>
        <div style="font-size: 12px; color: #666;">
            {subtitle}
        </div>
    </div>
    """
    
    components.html(html_code, height=200)

# Использование:
col1, col2, col3 = st.columns(3)
with col1:
    create_circular_metric(78, "RMSSD", "39.0 ms", "#4285f4")
with col2:
    create_circular_metric(100, "HR Rest", "56 bpm", "#ff9500")
with col3:
    create_circular_metric(30, "ESS", "Aug 23, 2025", "#34a853")
```

**Решение 2: Использование Plotly (рекомендуемое)**
```python
import plotly.graph_objects as go
import streamlit as st

def create_gauge_metric(value, title, subtitle, color_scheme="Blues"):
    fig = go.Figure(go.Indicator(
        mode = "gauge+number",
        value = value,
        title = {'text': f"<b>{title}</b><br><span style='font-size:12px;color:gray'>{subtitle}</span>"},
        number = {'suffix': "%", 'font': {'size': 40}},
        gauge = {
            'axis': {'range': [None, 100], 'tickwidth': 1, 'tickcolor': "darkblue"},
            'bar': {'color': color_scheme},
            'bgcolor': "white",
            'borderwidth': 2,
            'bordercolor': "gray",
            'steps': [
                {'range': [0, 50], 'color': '#f0f0f0'},
                {'range': [50, 80], 'color': '#e0e0e0'}
            ],
            'threshold': {
                'line': {'color': "red", 'width': 4},
                'thickness': 0.75,
                'value': 90
            }
        }
    ))

    fig.update_layout(
        height=300,
        margin=dict(l=20, r=20, t=60, b=20),
        font={'color': "darkblue", 'family': "Arial"}
    )
    
    return fig

# Использование:
col1, col2, col3 = st.columns(3)
with col1:
    st.plotly_chart(create_gauge_metric(78, "RMSSD", "39.0 ms", "#4285f4"), use_container_width=True)
with col2:
    st.plotly_chart(create_gauge_metric(100, "HR Rest", "56 bpm", "#ff9500"), use_container_width=True)
with col3:
    st.plotly_chart(create_gauge_metric(30, "ESS", "Aug 23, 2025", "#34a853"), use_container_width=True)
```

### 2. Календарь тренировок

**Проблема**: Сетка дней недели с непоследовательным стилем

**Решение: CSS Grid с правильной структурой**
```python
def create_training_calendar():
    # Определяем данные тренировок
    training_data = {
        'Пн': {'type': 'rest', 'activity': 'Отдых', 'details': ''},
        'Вт': {'type': 'cardio', 'activity': 'Другое', 'details': 'Н/Д км\nН/Д'},
        'Ср': {'type': 'cardio', 'activity': 'Другое', 'details': 'Н/Д км\nН/Д'},
        'Чт': {'type': 'cardio', 'activity': 'Другое', 'details': 'Н/Д км\nН/Д'},
        'Пт': {'type': 'rest', 'activity': 'Отдых', 'details': ''},
        'Сб': {'type': 'cardio', 'activity': 'Другое', 'details': 'Н/Д км\nН/Д'},
        'Вс': {'type': 'rest', 'activity': 'Отдых', 'details': ''},
    }
    
    # CSS стили
    css = """
    <style>
    .training-calendar {
        display: grid;
        grid-template-columns: repeat(7, 1fr);
        gap: 15px;
        padding: 20px 0;
        max-width: 100%;
    }
    
    .day-card {
        border-radius: 12px;
        padding: 20px 15px;
        text-align: center;
        min-height: 100px;
        display: flex;
        flex-direction: column;
        justify-content: space-between;
        box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        transition: transform 0.2s ease;
    }
    
    .day-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
    }
    
    .day-card.rest {
        background: linear-gradient(135deg, #2c3e50 0%, #34495e 100%);
        color: white;
    }
    
    .day-card.cardio {
        background: linear-gradient(135deg, #27ae60 0%, #2ecc71 100%);
        color: white;
        border: 2px solid #00ff88;
    }
    
    .day-title {
        font-weight: bold;
        font-size: 16px;
        margin-bottom: 10px;
    }
    
    .day-activity {
        font-size: 14px;
        margin-bottom: 8px;
    }
    
    .day-details {
        font-size: 12px;
        opacity: 0.9;
        white-space: pre-line;
    }
    
    @media (max-width: 768px) {
        .training-calendar {
            grid-template-columns: repeat(3, 1fr);
        }
    }
    
    @media (max-width: 480px) {
        .training-calendar {
            grid-template-columns: repeat(2, 1fr);
        }
    }
    </style>
    """
    
    # HTML структура
    html_content = '<div class="training-calendar">'
    
    for day, data in training_data.items():
        html_content += f'''
        <div class="day-card {data['type']}">
            <div class="day-title">{day}</div>
            <div class="day-activity">{data['activity']}</div>
            <div class="day-details">{data['details']}</div>
        </div>
        '''
    
    html_content += '</div>'
    
    # Отображение
    st.markdown(css, unsafe_allow_html=True)
    st.markdown(html_content, unsafe_allow_html=True)

# Использование:
st.markdown("### 📅 Тренировки на этой неделе")
create_training_calendar()
```

### 3. Градиентный блок рекомендаций

**Проблема**: Обрезается градиентный фон

**Решение: Правильное позиционирование и размеры**
```python
def create_recommendations_block():
    recommendations_html = """
    <style>
    .recommendations-container {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        border-radius: 20px;
        padding: 30px;
        margin: 20px 0;
        color: white;
        box-shadow: 0 8px 32px rgba(0,0,0,0.1);
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
        font-size: 24px;
        font-weight: bold;
        margin-bottom: 20px;
        position: relative;
        z-index: 1;
    }
    
    .recommendations-content {
        position: relative;
        z-index: 1;
        line-height: 1.6;
    }
    
    .recommendation-item {
        background: rgba(255,255,255,0.1);
        border-radius: 10px;
        padding: 15px;
        margin-bottom: 15px;
        backdrop-filter: blur(10px);
    }
    </style>
    
    <div class="recommendations-container">
        <div class="recommendations-title">
            🎯 Персональные рекомендации
        </div>
        <div class="recommendations-content">
            <div class="recommendation-item">
                <strong>Восстановление:</strong> Ваш показатель RMSSD в норме (78%). Продолжайте текущий режим тренировок.
            </div>
            <div class="recommendation-item">
                <strong>Нагрузка:</strong> HR Rest показывает отличное восстановление (100%). Можно увеличить интенсивность.
            </div>
            <div class="recommendation-item">
                <strong>Планирование:</strong> Рекомендуем добавить 1-2 силовые тренировки на этой неделе.
            </div>
        </div>
    </div>
    """
    
    st.markdown(recommendations_html, unsafe_allow_html=True)

# Использование:
create_recommendations_block()
```

## 🎨 Общие улучшения дизайна

### 1. Глобальные CSS стили
```python
def apply_global_styles():
    st.markdown("""
    <style>
    /* Импорт шрифтов */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
    
    /* Основные стили */
    .stApp {
        font-family: 'Inter', sans-serif;
        background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
    }
    
    /* Скрыть элементы Streamlit */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    
    /* Улучшение боковой панели */
    .css-1d391kg {
        background: white;
        box-shadow: 2px 0 10px rgba(0,0,0,0.1);
    }
    
    /* Стилизация заголовков */
    h1, h2, h3 {
        color: #2c3e50;
        font-weight: 600;
    }
    
    /* Улучшение метрик */
    [data-testid="metric-container"] {
        background: white;
        border-radius: 10px;
        padding: 15px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        border-left: 4px solid #3498db;
    }
    
    /* Кнопки */
    .stButton > button {
        background: linear-gradient(135deg, #3498db 0%, #2980b9 100%);
        color: white;
        border: none;
        border-radius: 25px;
        padding: 10px 25px;
        font-weight: 500;
        transition: all 0.3s ease;
    }
    
    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 5px 15px rgba(52, 152, 219, 0.4);
    }
    
    /* Прогресс бары */
    .stProgress .st-bo {
        background: linear-gradient(90deg, #3498db 0%, #2ecc71 100%);
    }
    </style>
    """, unsafe_allow_html=True)
```

### 2. Компонент для статуса подключения Garmin
```python
def create_garmin_status_card(is_connected=True, email="greg.kisel@yandex.ru"):
    status_color = "#2ecc71" if is_connected else "#e74c3c"
    status_text = "Подключено" if is_connected else "Не подключено"
    status_icon = "✅" if is_connected else "❌"
    
    html_code = f"""
    <div style="
        background: white;
        border-radius: 15px;
        padding: 20px;
        margin: 10px 0;
        box-shadow: 0 4px 12px rgba(0,0,0,0.1);
        border-left: 5px solid {status_color};
    ">
        <div style="display: flex; align-items: center; margin-bottom: 15px;">
            <span style="font-size: 24px; margin-right: 10px;">{status_icon}</span>
            <span style="font-size: 18px; font-weight: 600; color: #2c3e50;">Garmin Connect</span>
        </div>
        
        <div style="color: {status_color}; font-weight: 500; margin-bottom: 10px;">
            Статус: {status_text}
        </div>
        
        <div style="font-size: 14px; color: #7f8c8d;">
            Email: {email}
        </div>
        
        {f'<div style="margin-top: 15px; padding: 10px; background: #f8f9fa; border-radius: 8px; font-size: 12px; color: #6c757d;">Последняя синхронизация: {datetime.now().strftime("%d.%m.%Y %H:%M")}</div>' if is_connected else ''}
    </div>
    """
    
    components.html(html_code, height=150)
```

## 🚨 Критические исправления

### 1. Замена всех st.html() на правильные методы
```python
# ❌ Неправильно:
st.html("<div>Контент</div>")

# ✅ Правильно для статического HTML:
st.markdown("<div>Контент</div>", unsafe_allow_html=True)

# ✅ Правильно для интерактивного контента:
components.html("<div onclick='alert()'>Контент</div>", height=100)
```

### 2. Обработка ошибок рендеринга
```python
def safe_render_component(component_func, fallback_text="Компонент недоступен"):
    try:
        component_func()
    except Exception as e:
        st.error(f"{fallback_text}: {str(e)}")
        st.info("Попробуйте обновить страницу или обратитесь к администратору.")
```

### 3. Проверка совместимости браузера
```python
def check_browser_compatibility():
    js_code = """
    <script>
    const isCompatible = 'fetch' in window && 'Promise' in window;
    if (!isCompatible) {
        document.body.innerHTML = '<div style="padding: 20px; text-align: center; color: red;">Ваш браузер не поддерживает все функции приложения. Пожалуйста, обновите браузер.</div>';
    }
    </script>
    """
    components.html(js_code, height=0)
```

Эти решения должны полностью устранить проблемы с HTML рендерингом в вашем Streamlit приложении.
