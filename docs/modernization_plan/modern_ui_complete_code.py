# Полный код для utils/modern_ui.py
# Стиль AIEndurance для AI Trainer

import streamlit as st
import plotly.graph_objects as go
from datetime import datetime, timedelta
import pandas as pd
from typing import Optional, Dict, List, Tuple

class ModernUI:
    """UI компоненты в стиле AIEndurance для AI Trainer"""
    
    # Цветовая схема AIEndurance
    COLORS = {
        'primary_gradient': 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
        'surface_light': '#E8F0FF',
        'surface_dark': '#1A2B4D',
        'surface_darker': '#2D3E5F',
        'accent_purple': '#667eea',
        'accent_violet': '#764ba2',
        'success': '#10B981',
        'warning': '#F59E0B',
        'danger': '#EF4444',
        'text_primary': '#1E293B',
        'text_secondary': '#64748B',
        'bg_primary': '#F8FAFF'
    }
    
    @staticmethod
    def apply_aiendurance_styles():
        """Применяет полный набор стилей AIEndurance"""
        st.markdown("""
        <style>
        /* Импорт шрифта Inter для современного вида */
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
        
        /* Основные CSS переменные */
        :root {
            --primary-gradient: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            --surface-light: #E8F0FF;
            --surface-dark: #1A2B4D;
            --surface-darker: #2D3E5F;
            --accent-purple: #667eea;
            --accent-violet: #764ba2;
            --success: #10B981;
            --warning: #F59E0B;
            --danger: #EF4444;
            --text-primary: #1E293B;
            --text-secondary: #64748B;
            --border-radius-lg: 20px;
            --border-radius-xl: 25px;
            --shadow-sm: 0 4px 15px rgba(102, 126, 234, 0.1);
            --shadow-md: 0 8px 25px rgba(102, 126, 234, 0.2);
            --shadow-lg: 0 15px 35px rgba(102, 126, 234, 0.3);
        }
        
        /* Основной контейнер приложения */
        .stApp {
            background: #F8FAFF;
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
        }
        
        /* Скрываем стандартный header Streamlit */
        header[data-testid="stHeader"] {
            background: transparent;
            height: 0;
        }
        
        /* Карточки в стиле AIEndurance */
        .ai-card {
            background: var(--surface-light);
            border-radius: var(--border-radius-lg);
            padding: 25px;
            box-shadow: var(--shadow-sm);
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            border: 1px solid rgba(102, 126, 234, 0.1);
        }
        
        .ai-card:hover {
            transform: translateY(-5px);
            box-shadow: var(--shadow-md);
            border-color: rgba(102, 126, 234, 0.2);
        }
        
        /* Темная карточка для тренировки */
        .workout-card {
            background: linear-gradient(135deg, #1A2B4D 0%, #2D3E5F 100%);
            border-radius: var(--border-radius-lg);
            padding: 30px;
            color: white;
            box-shadow: var(--shadow-md);
            position: relative;
            overflow: hidden;
        }
        
        .workout-card::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            height: 3px;
            background: var(--primary-gradient);
        }
        
        /* Градиентные кнопки */
        .gradient-button {
            background: var(--primary-gradient);
            color: white;
            border: none;
            border-radius: 25px;
            padding: 12px 30px;
            font-weight: 600;
            font-size: 14px;
            cursor: pointer;
            transition: all 0.3s ease;
            display: inline-flex;
            align-items: center;
            gap: 8px;
        }
        
        .gradient-button:hover {
            transform: scale(1.05);
            box-shadow: var(--shadow-md);
        }
        
        .gradient-button:active {
            transform: scale(0.98);
        }
        
        /* Белая кнопка (вторичная) */
        .white-button {
            background: white;
            color: var(--accent-purple);
            border: 2px solid var(--accent-purple);
            border-radius: 25px;
            padding: 10px 25px;
            font-weight: 600;
            font-size: 14px;
            cursor: pointer;
            transition: all 0.3s ease;
        }
        
        .white-button:hover {
            background: var(--accent-purple);
            color: white;
            transform: translateY(-2px);
        }
        
        /* Навигационная панель */
        .nav-bar {
            background: var(--primary-gradient);
            border-radius: var(--border-radius-lg);
            padding: 15px 25px;
            margin-bottom: 25px;
            box-shadow: var(--shadow-md);
        }
        
        .nav-item {
            color: rgba(255, 255, 255, 0.7);
            text-decoration: none;
            padding: 10px 18px;
            border-radius: 12px;
            transition: all 0.2s ease;
            font-weight: 500;
            font-size: 15px;
            display: inline-flex;
            align-items: center;
            gap: 8px;
        }
        
        .nav-item:hover {
            background: rgba(255, 255, 255, 0.15);
            color: white;
        }
        
        .nav-item.active {
            background: rgba(255, 255, 255, 0.25);
            color: white;
            font-weight: 600;
        }
        
        /* Календарь тренировок */
        .calendar-day {
            border-radius: 15px;
            padding: 15px;
            min-height: 130px;
            transition: all 0.2s ease;
            cursor: pointer;
            position: relative;
        }
        
        .calendar-day:hover {
            transform: scale(1.05);
            z-index: 10;
        }
        
        .calendar-day-empty {
            background: var(--surface-dark);
            color: white;
        }
        
        .calendar-day-run {
            background: #E8F0FF;
            border: 2px solid #667eea;
        }
        
        .calendar-day-ride {
            background: #F0E8FF;
            border: 2px solid #a855f7;
        }
        
        .calendar-day-swim {
            background: #FFE8E8;
            border: 2px solid #ef4444;
        }
        
        .calendar-day-other {
            background: #FFF8E8;
            border: 2px solid #f59e0b;
        }
        
        /* Метрики с градиентным текстом */
        .metric-value {
            font-size: 3.5rem;
            font-weight: 700;
            background: var(--primary-gradient);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            line-height: 1;
        }
        
        .metric-label {
            font-size: 0.875rem;
            color: var(--text-secondary);
            font-weight: 500;
            margin-bottom: 10px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        
        .metric-subtitle {
            font-size: 0.75rem;
            color: var(--text-secondary);
            margin-top: 5px;
        }
        
        /* Круговые индикаторы */
        .circular-metric {
            background: var(--surface-light);
            border-radius: var(--border-radius-lg);
            padding: 20px;
            text-align: center;
            height: 220px;
            display: flex;
            flex-direction: column;
            justify-content: center;
        }
        
        /* Критический баннер */
        .critical-banner {
            background: linear-gradient(135deg, #EF4444, #DC2626);
            color: white;
            padding: 18px;
            border-radius: var(--border-radius-lg);
            margin-bottom: 25px;
            text-align: center;
            font-weight: 600;
            box-shadow: var(--shadow-md);
            animation: pulse-danger 2s infinite;
        }
        
        @keyframes pulse-danger {
            0%, 100% { box-shadow: 0 4px 20px rgba(239, 68, 68, 0.3); }
            50% { box-shadow: 0 4px 30px rgba(239, 68, 68, 0.5); }
        }
        
        /* Trial/Info баннер */
        .info-banner {
            background: var(--primary-gradient);
            color: white;
            padding: 15px;
            border-radius: var(--border-radius-lg);
            margin-bottom: 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            box-shadow: var(--shadow-sm);
        }
        
        /* Анимации */
        @keyframes slideIn {
            from {
                opacity: 0;
                transform: translateY(20px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }
        
        .slide-in {
            animation: slideIn 0.5s ease-out;
        }
        
        @keyframes fadeIn {
            from { opacity: 0; }
            to { opacity: 1; }
        }
        
        .fade-in {
            animation: fadeIn 0.3s ease-out;
        }
        
        /* Прогресс бары */
        .progress-bar {
            width: 100%;
            height: 6px;
            background: rgba(102, 126, 234, 0.1);
            border-radius: 3px;
            overflow: hidden;
            margin-top: 10px;
        }
        
        .progress-fill {
            height: 100%;
            background: var(--primary-gradient);
            border-radius: 3px;
            transition: width 0.5s ease;
        }
        
        /* Стилизация Streamlit компонентов */
        .stButton > button {
            background: var(--primary-gradient);
            color: white;
            border: none;
            border-radius: 25px;
            padding: 10px 25px;
            font-weight: 600;
            transition: all 0.3s ease;
        }
        
        .stButton > button:hover {
            transform: translateY(-2px);
            box-shadow: var(--shadow-md);
        }
        
        /* Tabs стилизация */
        .stTabs [data-baseweb="tab-list"] {
            background: var(--surface-light);
            border-radius: 15px;
            padding: 5px;
            gap: 5px;
        }
        
        .stTabs [data-baseweb="tab"] {
            border-radius: 10px;
            padding: 10px 20px;
            background: transparent;
            color: var(--text-primary);
        }
        
        .stTabs [aria-selected="true"] {
            background: white;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }
        
        /* Метрики Streamlit */
        [data-testid="metric-container"] {
            background: var(--surface-light);
            border-radius: var(--border-radius-lg);
            padding: 20px;
            box-shadow: var(--shadow-sm);
        }
        
        /* Responsive design */
        @media (max-width: 768px) {
            .nav-bar {
                padding: 10px 15px;
                overflow-x: auto;
            }
            
            .nav-item {
                font-size: 13px;
                padding: 8px 12px;
            }
            
            .metric-value {
                font-size: 2.5rem;
            }
            
            .calendar-day {
                min-height: 100px;
                padding: 10px;
                font-size: 12px;
            }
        }
        </style>
        """, unsafe_allow_html=True)
    
    @staticmethod
    def create_circular_indicator(value: float, max_value: float, title: str, 
                                 subtitle: str = "", color: str = "#667eea") -> go.Figure:
        """
        Создает круговой индикатор в стиле AIEndurance
        
        Args:
            value: Текущее значение
            max_value: Максимальное значение
            title: Заголовок метрики
            subtitle: Подзаголовок (например, единицы измерения)
            color: Цвет индикатора
        
        Returns:
            Plotly figure с круговым индикатором
        """
        percentage = (value / max_value * 100) if max_value > 0 else 0
        percentage = min(100, max(0, percentage))  # Ограничиваем 0-100
        
        fig = go.Figure(go.Indicator(
            mode = "gauge+number",
            value = percentage,
            number = {
                'suffix': "%", 
                'font': {'size': 36, 'color': color, 'family': 'Inter, sans-serif'}
            },
            domain = {'x': [0, 1], 'y': [0, 1]},
            title = {
                'text': f"<b>{title}</b><br><span style='font-size:12px;color:#64748B'>{subtitle}</span>",
                'font': {'size': 14, 'family': 'Inter, sans-serif'}
            },
            gauge = {
                'axis': {'range': [0, 100], 'visible': False},
                'bar': {'color': color, 'thickness': 0.15},
                'bgcolor': "rgba(0,0,0,0)",
                'borderwidth': 0,
                'steps': [
                    {'range': [0, 100], 'color': f'{color}15'}  # 15% прозрачности
                ]
            }
        ))
        
        fig.update_layout(
            height=220,
            margin=dict(l=20, r=20, t=60, b=20),
            paper_bgcolor='#E8F0FF',
            font={'family': 'Inter, sans-serif'},
            showlegend=False
        )
        
        return fig
    
    @staticmethod
    def create_mini_chart(data: list, color: str = "#667eea", height: int = 80) -> go.Figure:
        """
        Создает мини-график для отображения трендов
        
        Args:
            data: Список значений для графика
            color: Цвет линии
            height: Высота графика
        
        Returns:
            Plotly figure с мини-графиком
        """
        fig = go.Figure()
        
        fig.add_trace(go.Scatter(
            y=data,
            mode='lines',
            line=dict(color=color, width=2),
            fill='tozeroy',
            fillcolor=f'{color}20',
            showlegend=False,
            hoverinfo='skip'
        ))
        
        fig.update_layout(
            height=height,
            margin=dict(l=0, r=0, t=0, b=0),
            xaxis=dict(visible=False),
            yaxis=dict(visible=False),
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)'
        )
        
        return fig
    
    @staticmethod
    def workout_card_html(activity: Dict) -> str:
        """
        Генерирует HTML для карточки тренировки
        
        Args:
            activity: Словарь с данными активности
        
        Returns:
            HTML строка карточки
        """
        return f"""
        <div class="workout-card slide-in">
            <div style="font-size: 12px; opacity: 0.8; margin-bottom: 5px;">
                Most Recent Workout
            </div>
            <h2 style="margin: 10px 0 20px 0; color: white; font-size: 28px;">
                {activity.get('name', activity.get('sport', 'Тренировка'))}
            </h2>
            
            <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 20px; 
                        margin: 25px 0; color: white;">
                <div>
                    <span style="opacity: 0.6; font-size: 12px;">Start Time</span><br>
                    <strong style="font-size: 16px;">
                        {activity.get('date', 'N/A')}
                    </strong>
                </div>
                <div>
                    <span style="opacity: 0.6; font-size: 12px;">Distance</span><br>
                    <strong style="font-size: 16px;">
                        {activity.get('distance_km', 0):.1f} km
                    </strong>
                </div>
                <div>
                    <span style="opacity: 0.6; font-size: 12px;">Time</span><br>
                    <strong style="font-size: 16px;">
                        {activity.get('duration_minutes', 0):.0f} min
                    </strong>
                </div>
                <div>
                    <span style="opacity: 0.6; font-size: 12px;">Average Power</span><br>
                    <strong style="font-size: 16px;">
                        {activity.get('avg_power', 0):.0f} W
                    </strong>
                </div>
                <div>
                    <span style="opacity: 0.6; font-size: 12px;">Elevation Gain</span><br>
                    <strong style="font-size: 16px;">
                        {activity.get('elevation_gain', 0):.0f} m
                    </strong>
                </div>
                <div>
                    <span style="opacity: 0.6; font-size: 12px;">TSS</span><br>
                    <strong style="font-size: 16px;">
                        {activity.get('tss', 0):.0f}
                    </strong>
                </div>
            </div>
            
            <div style="margin-top: 30px; text-align: center;">
                <button class="white-button">
                    📊 Analysis
                </button>
            </div>
        </div>
        """
    
    @staticmethod
    def metric_card_html(title: str, value: str, info_tooltip: str = "") -> str:
        """
        Генерирует HTML для карточки метрики
        
        Args:
            title: Заголовок метрики
            value: Значение метрики
            info_tooltip: Текст подсказки
        
        Returns:
            HTML строка карточки метрики
        """
        info_icon = "ℹ️" if info_tooltip else ""
        
        return f"""
        <div class="ai-card fade-in" style="height: 200px; 
             display: flex; flex-direction: column; justify-content: center;">
            <div style="display: flex; justify-content: space-between; 
                        align-items: center; margin-bottom: 20px;">
                <span class="metric-label">{title}</span>
                <span style="cursor: help;" title="{info_tooltip}">{info_icon}</span>
            </div>
            <div class="metric-value" style="text-align: center;">
                {value}
            </div>
        </div>
        """
    
    @staticmethod
    def calendar_day_html(day: str, activity: Optional[Dict] = None, 
                         is_today: bool = False) -> str:
        """
        Генерирует HTML для дня в календаре
        
        Args:
            day: Название дня недели
            activity: Данные активности (если есть)
            is_today: Является ли сегодняшним днем
        
        Returns:
            HTML строка дня календаря
        """
        if activity:
            sport = activity.get('sport', 'other').lower()
            sport_class = f"calendar-day-{sport}" if sport in ['run', 'ride', 'swim'] else "calendar-day-other"
            border = "3px solid #667eea" if is_today else "2px solid transparent"
            
            return f"""
            <div class="calendar-day {sport_class}" style="border: {border};">
                <div style="text-align: center; font-weight: bold; margin-bottom: 10px;">
                    {day}
                </div>
                <div style="font-size: 12px;">
                    <span style="color: #10B981;">✓</span> {sport.title()}<br>
                    <strong>{activity.get('distance_km', 0):.1f} km</strong><br>
                    <span style="opacity: 0.7;">{activity.get('duration_minutes', 0):.0f} min</span>
                </div>
            </div>
            """
        else:
            border = "3px solid #667eea" if is_today else "2px solid transparent"
            return f"""
            <div class="calendar-day calendar-day-empty" style="border: {border};">
                <div style="text-align: center; color: white; font-weight: bold;">
                    {day}
                </div>
            </div>
            """
    
    @staticmethod
    def progress_bar_html(value: float, max_value: float, label: str = "", 
                         color: str = "#667eea") -> str:
        """
        Генерирует HTML для прогресс-бара
        
        Args:
            value: Текущее значение
            max_value: Максимальное значение
            label: Подпись прогресс-бара
            color: Цвет заполнения
        
        Returns:
            HTML строка прогресс-бара
        """
        percentage = (value / max_value * 100) if max_value > 0 else 0
        percentage = min(100, max(0, percentage))
        
        return f"""
        <div style="margin: 15px 0;">
            {f'<div style="font-size: 12px; color: #64748B; margin-bottom: 5px;">{label}</div>' if label else ''}
            <div class="progress-bar">
                <div class="progress-fill" style="width: {percentage}%; background: {color};"></div>
            </div>
            <div style="font-size: 11px; color: #94A3B8; margin-top: 3px;">
                {value:.0f} / {max_value:.0f} ({percentage:.0f}%)
            </div>
        </div>
        """