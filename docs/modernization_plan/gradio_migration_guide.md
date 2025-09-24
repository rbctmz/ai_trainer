# Руководство по миграции с Streamlit на Gradio

## 🎯 Почему Gradio лучше для AI Trainer

### Преимущества Gradio над Streamlit:
1. **Нативная поддержка HTML/CSS** - без iframe ограничений
2. **Лучший контроль над компонентами** - собственная система компонентов
3. **ML-ориентированность** - создан специально для AI/ML приложений
4. **Простота развертывания** - автоматическая интеграция с Hugging Face
5. **Меньше проблем с рендерингом** - стабильная отрисовка сложных интерфейсов

## 🔄 Пошаговая миграция

### Шаг 1: Установка и базовая настройка

```bash
pip install gradio
pip install plotly  # для графиков
pip install pandas  # если используется
```

### Шаг 2: Основная структура приложения

**Было в Streamlit:**
```python
import streamlit as st

st.title("🏃‍♂️ Персональный AI Тренер")
st.sidebar.title("Garmin Connect")
```

**Стало в Gradio:**
```python
import gradio as gr
import plotly.graph_objects as go

def create_ai_trainer_interface():
    with gr.Blocks(
        title="AI Trainer",
        theme=gr.themes.Soft(),
        css="""
        .gradio-container {
            background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
            font-family: 'Inter', sans-serif;
        }
        .header {
            text-align: center;
            padding: 20px;
            background: white;
            border-radius: 15px;
            margin-bottom: 20px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.1);
        }
        """
    ) as interface:
        
        # Заголовок
        gr.Markdown(
            """
            <div class="header">
                <h1>🏃‍♂️ Персональный AI Тренер</h1>
                <p>Добро пожаловать в персональный AI тренер!</p>
            </div>
            """,
            elem_classes=["header"]
        )
        
        return interface
```

### Шаг 3: Боковая панель → Accordion/Tabs

**Было в Streamlit:**
```python
with st.sidebar:
    st.header("Garmin Connect")
    email = st.text_input("Email Garmin")
    password = st.text_input("Пароль Garmin", type="password")
```

**Стало в Gradio:**
```python
with gr.Accordion("🔗 Garmin Connect", open=True):
    gr.Markdown("**Подключитесь для синхронизации данных:**")
    
    with gr.Row():
        email_input = gr.Textbox(
            label="Email Garmin",
            placeholder="greg.kisel@yandex.ru",
            value="greg.kisel@yandex.ru"
        )
        password_input = gr.Textbox(
            label="Пароль Garmin",
            type="password",
            placeholder="••••••••••••••••"
        )
    
    connect_btn = gr.Button("🔐 Подключить", variant="primary")
    status_text = gr.Markdown("**Статус:** Не подключено")
```

### Шаг 4: Миграция метрик восстановления

**Streamlit версия с проблемами:**
```python
# Проблемная реализация с st.html()
st.html(f"<div class='metric-circle'>{value}%</div>")
```

**Gradio версия (стабильная):**
```python
def create_recovery_metrics():
    # Создаем Plotly графики для метрик
    def create_gauge(value, title, subtitle, color):
        fig = go.Figure(go.Indicator(
            mode = "gauge+number",
            value = value,
            title = {'text': f"<b>{title}</b><br><span style='font-size:12px;color:gray'>{subtitle}</span>"},
            number = {'suffix': "%", 'font': {'size': 30}},
            gauge = {
                'axis': {'range': [None, 100]},
                'bar': {'color': color},
                'steps': [{'range': [0, 50], 'color': '#f0f0f0'}, 
                         {'range': [50, 100], 'color': '#e0e0e0'}],
                'threshold': {'line': {'color': "red", 'width': 4}, 'thickness': 0.75, 'value': 90}
            }
        ))
        fig.update_layout(height=250, margin=dict(l=20, r=20, t=60, b=20))
        return fig

    # Интерфейс метрик
    with gr.Row():
        with gr.Column():
            gr.Plot(create_gauge(78, "RMSSD", "39.0 ms", "#4285f4"))
        with gr.Column():
            gr.Plot(create_gauge(100, "HR Rest", "56 bpm", "#ff9500"))
        with gr.Column():
            gr.Plot(create_gauge(30, "ESS", "Aug 23, 2025", "#34a853"))
    
    # Статус восстановления
    gr.HTML("""
    <div style="
        text-align: center; 
        margin: 20px 0; 
        padding: 15px; 
        background: linear-gradient(135deg, #3498db 0%, #2ecc71 100%);
        color: white; 
        border-radius: 25px;
        font-weight: bold;
        font-size: 16px;
    ">
        🚀 Driving Aerobic Recovery
    </div>
    """)
```

### Шаг 5: Календарь тренировок

```python
def create_training_calendar():
    # Данные тренировок
    calendar_data = {
        'Пн': {'type': 'rest', 'activity': 'Отдых'},
        'Вт': {'type': 'cardio', 'activity': 'Другое', 'details': 'Н/Д км\nН/Д'},
        'Ср': {'type': 'cardio', 'activity': 'Другое', 'details': 'Н/Д км\nН/Д'},
        'Чт': {'type': 'cardio', 'activity': 'Другое', 'details': 'Н/Д км\nН/Д'},
        'Пт': {'type': 'rest', 'activity': 'Отдых'},
        'Сб': {'type': 'cardio', 'activity': 'Другое', 'details': 'Н/Д км\nН/Д'},
        'Вс': {'type': 'rest', 'activity': 'Отдых'},
    }
    
    # CSS для календаря
    calendar_css = """
    <style>
    .calendar-grid {
        display: grid;
        grid-template-columns: repeat(7, 1fr);
        gap: 15px;
        padding: 20px 0;
        max-width: 100%;
    }
    .day-card {
        border-radius: 12px;
        padding: 20px 10px;
        text-align: center;
        min-height: 100px;
        display: flex;
        flex-direction: column;
        justify-content: center;
        box-shadow: 0 4px 12px rgba(0,0,0,0.1);
        transition: transform 0.2s ease;
    }
    .day-card:hover {
        transform: translateY(-2px);
    }
    .day-card.rest {
        background: linear-gradient(135deg, #2c3e50 0%, #34495e 100%);
        color: white;
    }
    .day-card.cardio {
        background: linear-gradient(135deg, #27ae60 0%, #2ecc71 100%);
        color: white;
        border: 3px solid #00ff88;
    }
    .day-title { font-weight: bold; font-size: 16px; margin-bottom: 8px; }
    .day-activity { font-size: 14px; }
    </style>
    """
    
    # HTML календаря
    calendar_html = '<div class="calendar-grid">'
    for day, data in calendar_data.items():
        calendar_html += f'''
        <div class="day-card {data['type']}">
            <div class="day-title">{day}</div>
            <div class="day-activity">{data['activity']}</div>
        </div>
        '''
    calendar_html += '</div>'
    
    return calendar_css + calendar_html
```

### Шаг 6: Интеграция с Garmin Connect

```python
def setup_garmin_integration():
    def connect_garmin(email, password):
        """Функция подключения к Garmin Connect"""
        try:
            # Здесь ваша логика подключения к Garmin
            # from garmin import GarminConnect
            # garmin = GarminConnect(email, password)
            # garmin.login()
            
            return (
                "✅ **Статус:** Подключено успешно!", 
                "🔄 Синхронизация данных...",
                gr.update(interactive=False, value="🔗 Подключено")
            )
        except Exception as e:
            return (
                f"❌ **Статус:** Ошибка подключения - {str(e)}", 
                "",
                gr.update(interactive=True, value="🔐 Подключить")
            )
    
    def sync_garmin_data():
        """Синхронизация данных с Garmin"""
        try:
            # Здесь логика синхронизации
            return "✅ Данные синхронизированы успешно!"
        except Exception as e:
            return f"❌ Ошибка синхронизации: {str(e)}"
    
    return connect_garmin, sync_garmin_data
```

### Шаг 7: Полное приложение

```python
import gradio as gr
import plotly.graph_objects as go
from datetime import datetime

def create_full_ai_trainer():
    # Функции для работы с Garmin
    connect_garmin, sync_garmin_data = setup_garmin_integration()
    
    with gr.Blocks(
        title="AI Trainer",
        theme=gr.themes.Soft(),
        css="""
        .gradio-container { 
            font-family: 'Inter', sans-serif;
            background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
        }
        .main-header {
            text-align: center;
            padding: 30px;
            background: white;
            border-radius: 20px;
            margin-bottom: 30px;
            box-shadow: 0 8px 32px rgba(0,0,0,0.1);
        }
        .metrics-section {
            background: white;
            border-radius: 15px;
            padding: 20px;
            margin: 20px 0;
            box-shadow: 0 4px 12px rgba(0,0,0,0.1);
        }
        """
    ) as app:
        
        # Заголовок
        gr.Markdown(
            """
            <div class="main-header">
                <h1>🏃‍♂️ Персональный AI Тренер</h1>
                <h2>Добро пожаловать в персональный AI тренер!</h2>
                
                <p><strong>Этот инструмент поможет вам:</strong></p>
                <ul style="text-align: left; display: inline-block;">
                    <li>📊 Анализировать тренировочные данные из Garmin Connect</li>
                    <li>💖 Отслеживать показатели HRV и восстановления</li>
                    <li>📈 Планировать тренировки с помощью модели Банистера</li>
                    <li>🎯 Получать персонализированные рекомендации от AI</li>
                </ul>
            </div>
            """
        )
        
        # Подключение к Garmin Connect
        with gr.Accordion("🔗 Garmin Connect", open=True):
            gr.Markdown("**Подключитесь для синхронизации данных:**")
            
            with gr.Row():
                email_input = gr.Textbox(
                    label="Email Garmin",
                    value="greg.kisel@yandex.ru"
                )
                password_input = gr.Textbox(
                    label="Пароль Garmin",
                    type="password"
                )
            
            with gr.Row():
                connect_btn = gr.Button("🔐 Подключить", variant="primary")
                sync_btn = gr.Button("🔄 Синхронизировать", variant="secondary")
            
            status_display = gr.Markdown("**Статус:** Не подключено")
            sync_status = gr.Markdown("")
        
        # Метрики восстановления
        with gr.Group():
            gr.Markdown("### 📊 Connect your heart rate data to see your recovery")
            create_recovery_metrics()
        
        # Календарь тренировок
        with gr.Group():
            gr.Markdown("### 📅 Тренировки на этой неделе")
            gr.HTML(create_training_calendar())
        
        # Рекомендации
        with gr.Group():
            gr.Markdown("### 🎯 Персональные рекомендации")
            gr.HTML("""
            <div style="
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                border-radius: 20px;
                padding: 30px;
                color: white;
                text-align: center;
                margin: 20px 0;
            ">
                <h3>🧠 Анализ готовности к тренировкам</h3>
                <p>На основе ваших данных HRV и восстановления, вот рекомендации на сегодня:</p>
                
                <div style="background: rgba(255,255,255,0.1); border-radius: 10px; padding: 15px; margin-top: 15px;">
                    <strong>Рекомендация:</strong> Ваши показатели восстановления хорошие. 
                    Можете провести тренировку средней интенсивности.
                </div>
            </div>
            """)
        
        # Обработчики событий
        connect_btn.click(
            fn=connect_garmin,
            inputs=[email_input, password_input],
            outputs=[status_display, sync_status, connect_btn]
        )
        
        sync_btn.click(
            fn=sync_garmin_data,
            outputs=[sync_status]
        )
    
    return app

# Запуск приложения
if __name__ == "__main__":
    app = create_full_ai_trainer()
    app.launch(
        server_name="0.0.0.0",
        server_port=8502,
        share=False,
        debug=True
    )
```

## 🚀 Запуск миграции

### Команды для Claude Code:

```bash
# Создать новый файл Gradio приложения
claude-code create "gradio_ai_trainer.py" --template="Convert my Streamlit AI trainer to Gradio using the migration guide, maintaining all Garmin Connect functionality and improving the HTML rendering"

# Установить зависимости
claude-code run "pip install gradio plotly pandas"

# Протестировать новое приложение
claude-code test "Run the new Gradio AI trainer and check all components render correctly"
```

### Преимущества после миграции:

1. ✅ **Стабильное HTML рендеринг** - нет проблем с iframe
2. ✅ **Лучшая кастомизация** - полный контроль над CSS
3. ✅ **Адаптивный дизайн** - автоматически подстраивается под размер экрана
4. ✅ **Быстрая загрузка** - оптимизированный JavaScript
5. ✅ **Простое развертывание** - один файл для запуска
6. ✅ **ML-ориентированность** - встроенная поддержка для AI моделей

### Время миграции:
- **Простой интерфейс**: 2-4 часа
- **Средний сложности**: 1-2 дня  
- **Сложный с интеграциями**: 3-5 дней

Gradio предоставляет значительно лучший контроль над HTML/CSS рендерингом и является идеальным выбором для AI/ML приложений.
