# Готовые шаблоны компонентов для AI Trainer - Gradio версия

import gradio as gr
import plotly.graph_objects as go
import pandas as pd
from datetime import datetime, timedelta

## 🎯 Метрики восстановления - Gradio версия

def create_recovery_gauge(value, title, subtitle, color="#4285f4"):
    """
    Создает Plotly gauge для метрик восстановления
    """
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=value,
        number={'suffix': "%", 'font': {'size': 35, 'color': color}},
        title={
            'text': f"<b style='font-size:16px'>{title}</b><br><span style='font-size:12px;color:#7f8c8d'>{subtitle}</span>",
            'font': {'size': 14}
        },
        gauge={
            'axis': {'range': [None, 100], 'tickwidth': 1, 'tickcolor': "lightgray"},
            'bar': {'color': color, 'thickness': 0.8},
            'bgcolor': "white",
            'borderwidth': 2,
            'bordercolor': "#e8e8e8",
            'steps': [
                {'range': [0, 25], 'color': 'rgba(255, 235, 238, 0.8)'},
                {'range': [25, 50], 'color': 'rgba(243, 229, 245, 0.8)'},
                {'range': [50, 75], 'color': 'rgba(232, 245, 232, 0.8)'},
                {'range': [75, 100], 'color': 'rgba(227, 242, 253, 0.8)'}
            ],
            'threshold': {
                'line': {'color': "red", 'width': 4},
                'thickness': 0.75,
                'value': 90
            }
        }
    ))
    
    fig.update_layout(
        height=280,
        margin=dict(l=20, r=20, t=80, b=20),
        font={'color': "#2c3e50", 'family': "Inter, Arial, sans-serif"},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)"
    )
    
    return fig

def create_recovery_metrics_interface():
    """
    Создает интерфейс метрик восстановления для Gradio
    """
    with gr.Group():
        gr.Markdown("### 📊 Показатели восстановления")
        
        with gr.Row():
            rmssd_plot = gr.Plot(
                create_recovery_gauge(78, "RMSSD", "39.0 ms", "#4285f4"),
                label="Вариабельность ЧСС"
            )
            hr_rest_plot = gr.Plot(
                create_recovery_gauge(100, "HR Rest", "56 bpm", "#ff9500"),
                label="ЧСС покоя"
            )
            ess_plot = gr.Plot(
                create_recovery_gauge(30, "ESS", "Aug 23, 2025", "#34a853"),
                label="Показатель нагрузки"
            )
        
        # Статус восстановления
        gr.HTML("""
        <div style="
            background: linear-gradient(135deg, #3498db 0%, #2ecc71 100%);
            color: white;
            padding: 20px;
            border-radius: 15px;
            text-align: center;
            margin: 20px 0;
            font-weight: bold;
            font-size: 18px;
            box-shadow: 0 6px 20px rgba(52, 152, 219, 0.3);
        ">
            🚀 Driving Aerobic Recovery
        </div>
        """)
    
    return rmssd_plot, hr_rest_plot, ess_plot

## 🏃‍♂️ Полное приложение AI Trainer

def create_full_ai_trainer_app():
    """
    Создает полное приложение AI Trainer с использованием всех компонентов
    """
    # Кастомная тема
    custom_theme = gr.themes.Soft(
        primary_hue="blue",
        secondary_hue="green",
        neutral_hue="slate",
        font=["Inter", "Arial", "sans-serif"]
    ).set(
        body_background_fill="linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%)",
        panel_background_fill="rgba(255, 255, 255, 0.9)",
        button_primary_background_fill="linear-gradient(135deg, #3498db 0%, #2980b9 100%)"
    )
    
    with gr.Blocks(
        title="🏃‍♂️ AI Trainer",
        theme=custom_theme,
        css="""
        .gradio-container {
            font-family: 'Inter', sans-serif !important;
        }
        .main-header {
            text-align: center;
            padding: 40px 20px;
            background: white;
            border-radius: 25px;
            margin-bottom: 30px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.1);
        }
        """
    ) as app:
        
        # Заголовок приложения
        gr.HTML(f"""
        <div class="main-header">
            <h1 style="margin: 0 0 15px 0; color: #2c3e50; font-size: 3rem; font-weight: 800;">
                🏃‍♂️ Персональный AI Тренер
            </h1>
            <h2 style="margin: 0 0 25px 0; color: #7f8c8d; font-size: 1.5rem; font-weight: 400;">
                Добро пожаловать в будущее персонального тренинга!
            </h2>
        </div>
        """)
        
        # Навигация по табам
        with gr.Tabs():
            # Главная панель
            with gr.Tab("🏠 Главная"):
                # Метрики восстановления
                recovery_components = create_recovery_metrics_interface()
    
    return app

# Функция для запуска приложения
def launch_ai_trainer():
    """
    Запускает приложение AI Trainer
    """
    app = create_full_ai_trainer_app()
    
    app.launch(
        server_name="0.0.0.0",
        server_port=8502,
        share=False,
        debug=True,
        show_error=True,
        quiet=False
    )

if __name__ == "__main__":
    launch_ai_trainer()
