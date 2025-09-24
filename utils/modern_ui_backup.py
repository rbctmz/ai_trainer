"""
Современные UI компоненты для AI Trainer
Модуль содержит класс ModernUI с методами для создания современного интерфейса
"""

import streamlit as st
import plotly.graph_objects as go

class ModernUI:
    """Современные UI компоненты для AI Trainer"""
    
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
    def apply_modern_styles(dark_mode=False):
        """Применяет современную CSS-стилизацию с поддержкой темной темы"""
        
        # JavaScript для управления темой
        theme_script = f"""
        <script>
        // Установка темы
        if ({'true' if dark_mode else 'false'}) {{
            document.body.classList.add('dark-mode');
        }} else {{
            document.body.classList.remove('dark-mode');
        }}
        </script>
        """
        st.markdown(theme_script, unsafe_allow_html=True)
        
        st.markdown("""
        <style>
        /* Импорт современного шрифта */
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
        
        /* Базовые переменные AIEndurance */
        :root {
            /* Основные цвета AIEndurance */
            --primary-gradient: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            --surface-light-blue: #E8F0FF;
            --surface-dark-blue: #1A2B4D;
            --surface-darker-blue: #2D3E5F;
            
            /* Метрики */
            --metric-excellent: #10B981;  /* Зеленый */
            --metric-good: #667eea;       /* Фиолетовый */
            --metric-warning: #F59E0B;    /* Оранжевый */
            --metric-critical: #EF4444;   /* Красный */
            
            /* Фоны */
            --bg-primary: #F8FAFF;
            --bg-cards: #E8F0FF;
            --border-radius: 20px;
            
            /* Legacy compatibility */
            --primary-blue: #667eea;
            --primary-blue-dark: #5A6DD8;
            --secondary-gray: #64748B;
            --success-green: #10B981;
            --warning-yellow: #F59E0B;
            --danger-red: #EF4444;
            --background-gray: #F8FAFF;
            --surface-white: #FFFFFF;
            --border-gray: #E2E8F0;
            --text-primary: #1E293B;
            --text-secondary: #475569;
            --shadow-sm: 0 1px 2px 0 rgba(0, 0, 0, 0.05);
            --shadow-md: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
            --shadow-lg: 0 10px 15px -3px rgba(0, 0, 0, 0.1);
        }
        
        /* Темная тема - применяется когда есть класс dark-mode на body */
        body.dark-mode {
            --bg-primary: #121212;
            --bg-cards: #1E1E1E;
            --surface-white: #1E1E1E;
            --surface-light-blue: #1A2B4D;
            --surface-dark-blue: #0F172A;
            --text-primary: #F5F5F5;
            --text-secondary: #A0A0A0;
            --border-gray: #2B2B2B;
            --background-gray: #1A1A1A;
            
            /* Переопределение градиентов для темной темы */
            --primary-gradient: linear-gradient(135deg, #4C5FD5 0%, #5E3B8E 100%);
        }
        
        body.dark-mode .stApp {
            background-color: var(--bg-primary) !important;
            color: var(--text-primary) !important;
        }
        
        body.dark-mode .modern-card, 
        body.dark-mode .metric-card,
        body.dark-mode .status-card {
            background: var(--surface-white) !important;
            color: var(--text-primary) !important;
            border-color: var(--border-gray) !important;
        }
        
        body.dark-mode .ai-panel {
            background: linear-gradient(135deg, #2D3E5F 0%, #1A2B4D 100%) !important;
        }
        
        body.dark-mode .metric-label {
            color: var(--text-secondary) !important;
        }
        
        body.dark-mode .metric-value {
            color: var(--text-primary) !important;
        }
        
        /* Обновленная типографика */
        .stApp {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            transition: background-color 0.3s ease, color 0.3s ease;
        }
        
        /* Переходы для всех элементов при смене темы */
        * {
            transition: background-color 0.3s ease, color 0.3s ease, border-color 0.3s ease;
        }
        
        /* Современные карточки */
        .modern-card {
            background: var(--surface-white);
            border-radius: 16px;
            box-shadow: var(--shadow-sm);
            border: 1px solid var(--border-gray);
            padding: 24px;
            margin-bottom: 16px;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }
        
        .modern-card:hover {
            box-shadow: var(--shadow-md);
            transform: translateY(-2px);
        }
        
        /* Статус-карточки */
        .status-card {
            position: relative;
            overflow: hidden;
        }
        
        .status-card::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            width: 4px;
            height: 100%;
            background: var(--accent-color, #3B82F6);
        }
        
        .status-excellent::before { background: var(--success-green); }
        .status-good::before { background: var(--warning-yellow); }
        .status-warning::before { background: var(--danger-red); }
        .status-critical::before { background: #991B1B; }
        
        /* Метрики */
        .metric-card {
            background: var(--surface-white);
            border-radius: 12px;
            padding: 20px;
            box-shadow: var(--shadow-sm);
            border: 1px solid var(--border-gray);
            height: 100%;
            transition: all 0.2s ease;
        }
        
        .metric-card:hover {
            box-shadow: var(--shadow-md);
        }
        
        .metric-value {
            font-size: 2.25rem;
            font-weight: 700;
            line-height: 1;
            margin-bottom: 0.5rem;
        }
        
        .metric-label {
            font-size: 0.875rem;
            color: var(--secondary-gray);
            font-weight: 500;
            margin-bottom: 0.75rem;
        }
        
        .metric-description {
            font-size: 0.75rem;
            color: var(--text-secondary);
        }
        
        /* AI-панель */
        .ai-panel {
            background: var(--primary-gradient, linear-gradient(135deg, #667eea 0%, #764ba2 100%));
            border-radius: 20px;
            padding: 32px;
            color: white;
            margin: 24px 0;
            box-shadow: var(--shadow-lg);
        }
        
        .ai-recommendation {
            background: rgba(255, 255, 255, 0.15);
            border: 1px solid rgba(255, 255, 255, 0.2);
            border-radius: 12px;
            padding: 16px;
            margin: 12px 0;
            backdrop-filter: blur(10px);
        }
        
        /* Critical alert */
        .critical-alert {
            background: linear-gradient(135deg, #fee2e2 0%, #fecaca 100%);
            border: 1px solid #f87171;
            border-radius: 12px;
            padding: 20px;
            margin: 16px 0;
            color: #991b1b;
        }
        
        .critical-alert h3 {
            margin: 0 0 8px 0;
            color: #991b1b;
        }
        
        .critical-alert p {
            margin: 0;
            color: #b91c1c;
        }
        
        /* Кнопки */
        .modern-button {
            background: var(--primary-blue);
            color: white;
            border: none;
            border-radius: 8px;
            padding: 12px 24px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s ease;
            box-shadow: var(--shadow-sm);
        }
        
        .modern-button:hover {
            background: var(--primary-blue-dark);
            box-shadow: var(--shadow-md);
            transform: translateY(-1px);
        }
        
        .modern-button-secondary {
            background: white;
            color: var(--primary-blue);
            border: 2px solid var(--primary-blue);
        }
        
        .modern-button-secondary:hover {
            background: var(--primary-blue);
            color: white;
        }
        
        /* Быстрые действия */
        .quick-actions-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 16px;
            margin: 24px 0;
        }
        
        .quick-action-btn {
            background: var(--surface-white);
            border: 2px solid var(--border-gray);
            border-radius: 12px;
            padding: 20px;
            text-align: center;
            cursor: pointer;
            transition: all 0.3s ease;
            box-shadow: var(--shadow-sm);
        }
        
        .quick-action-btn:hover {
            border-color: var(--primary-blue);
            box-shadow: var(--shadow-md);
            transform: translateY(-2px);
        }
        
        .quick-action-icon {
            font-size: 2rem;
            margin-bottom: 12px;
        }
        
        .quick-action-title {
            font-weight: 600;
            margin-bottom: 8px;
            color: var(--text-primary);
        }
        
        .quick-action-desc {
            font-size: 0.875rem;
            color: var(--text-secondary);
        }
        
        /* Анимации */
        @keyframes slideIn {
            from {
                opacity: 0;
                transform: translateY(10px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }
        
        .animate-slide-in {
            animation: slideIn 0.3s ease-out;
        }
        
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.7; }
        }
        
        .animate-pulse {
            animation: pulse 2s infinite;
        }
        
        /* Critical alert */
        .critical-alert {
            background: linear-gradient(135deg, #fee2e2 0%, #fecaca 100%);
            border: 1px solid #f87171;
            border-radius: 12px;
            padding: 20px;
            margin: 16px 0;
            color: #991b1b;
        }
        
        .critical-alert h3 {
            margin: 0 0 8px 0;
            color: #991b1b;
        }
        
        .critical-alert p {
            margin: 0;
            color: #b91c1c;
        }
        
        .critical-alert ul {
            margin: 8px 0 0 0;
            padding-left: 20px;
        }
        
        .critical-alert li {
            margin-bottom: 4px;
            color: #b91c1c;
        }
        
        /* Intensity indicator */
        .intensity-zones {
            background: var(--surface-white);
            border: 1px solid var(--border-gray);
            border-radius: 8px;
            padding: 12px;
        }
        
        .zone-allowed {
            color: var(--success-green);
            font-weight: 500;
        }
        
        .zone-restricted {
            color: var(--secondary-gray);
            opacity: 0.7;
        }
        
        /* Progress indicators for zones */
        .zone-progress {
            display: flex;
            align-items: center;
            gap: 8px;
            margin: 4px 0;
        }
        
        .zone-progress .zone-dot {
            width: 12px;
            height: 12px;
            border-radius: 50%;
            border: 2px solid var(--border-gray);
        }
        
        .zone-progress .zone-dot.active {
            background: var(--success-green);
            border-color: var(--success-green);
        }
        
        /* Enhanced quick actions */
        .quick-action-btn {
            background: var(--surface-white);
            border: 2px solid var(--border-gray);
            border-radius: 12px;
            padding: 20px;
            text-align: center;
            cursor: pointer;
            transition: all 0.3s ease;
            box-shadow: var(--shadow-sm);
        }
        
        .quick-action-btn:hover {
            border-color: var(--primary-blue);
            box-shadow: var(--shadow-md);
            transform: translateY(-2px);
        }
        
        .quick-action-icon {
            font-size: 2rem;
            margin-bottom: 12px;
        }
        
        .quick-action-title {
            font-weight: 600;
            margin-bottom: 8px;
            color: var(--text-primary);
        }
        
        .quick-action-desc {
            font-size: 0.875rem;
            color: var(--text-secondary);
        }
        
        /* Адаптивность */
        @media (max-width: 768px) {
            .modern-card {
                padding: 16px;
                margin-bottom: 12px;
            }
            
            .ai-panel {
                padding: 20px;
                margin: 16px 0;
            }
            
            .quick-actions-grid {
                grid-template-columns: 1fr;
                gap: 12px;
            }
            
            .metric-value {
                font-size: 1.75rem;
            }
            
            .critical-alert {
                padding: 16px;
                margin: 12px 0;
            }
            
            .intensity-zones {
                padding: 8px;
            }
        }
        /* Стили кнопки анализа в карточке тренировки */
        button[key="workout_analysis"] {
            background: white !important;
            color: #1A2B4D !important;
            border: none !important;
            border-radius: 25px !important;
            font-weight: bold !important;
            padding: 10px 30px !important;
            font-size: 14px !important;
            transition: all 0.2s ease !important;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1) !important;
        }
        
        button[key="workout_analysis"]:hover {
            transform: translateY(-2px) !important;
            box-shadow: 0 4px 12px rgba(0,0,0,0.2) !important;
        }
        
        /* Общие стили кнопок навигации */
        .stButton > button {
            background: transparent !important;
            color: rgba(255, 255, 255, 0.8) !important;
            border: none !important;
            border-radius: 8px !important;
            font-weight: 500 !important;
            transition: all 0.3s ease !important;
            font-size: 11px !important;
            padding: 12px 8px !important;
            height: 60px !important;
            white-space: pre-line !important;
            text-align: center !important;
            line-height: 1.2 !important;
        }
        
        .stButton > button:hover {
            background: rgba(255, 255, 255, 0.15) !important;
            color: white !important;
            transform: translateY(-1px) !important;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1) !important;
        }
        
        .stButton > button:focus {
            background: rgba(255, 255, 255, 0.25) !important;
            color: white !important;
            font-weight: 600 !important;
            box-shadow: 0 0 0 2px rgba(255, 255, 255, 0.3) !important;
        }
        
        .stButton > button:active {
            transform: translateY(0) !important;
        }
        </style>
        """, unsafe_allow_html=True)
    
    @staticmethod
    def status_card(title, value, status_type, trend=None, description=None):
        """Карточка статуса с цветовыми индикаторами с автоопределением темы"""
        
        # Пытаемся определить темную тему через streamlit session state
        import streamlit as st
        dark_mode = st.session_state.get('dark_mode', False) if hasattr(st, 'session_state') else False
        
        # Безопасное преобразование значения в число
        try:
            if isinstance(value, str) and value.replace('-', '').replace('.', '').isdigit():
                numeric_value = float(value)
            elif isinstance(value, (int, float)):
                numeric_value = float(value)
            else:
                numeric_value = 0.0
        except (ValueError, TypeError):
            numeric_value = 0.0
        
        # Определяем цвет и статус на основе типа и значения
        if status_type == 'tsb':
            if numeric_value > 5:
                status = 'excellent'
                text_class = 'text-green-600'
            elif numeric_value > -10:
                status = 'good'
                text_class = 'text-yellow-600'
            elif numeric_value > -30:
                status = 'warning'
                text_class = 'text-orange-600'
            else:
                status = 'critical'
                text_class = 'text-red-600'
        elif status_type == 'hrv':
            if numeric_value > 40:
                status = 'excellent'
                text_class = 'text-green-600'
            elif numeric_value > 30:
                status = 'good'
                text_class = 'text-yellow-600'
            else:
                status = 'warning'
                text_class = 'text-red-600'
        elif status_type == 'readiness':
            if numeric_value > 80:
                status = 'excellent'
                text_class = 'text-blue-600'
            elif numeric_value > 60:
                status = 'good'
                text_class = 'text-green-600'
            else:
                status = 'warning'
                text_class = 'text-yellow-600'
        else:  # ctl
            status = 'good'
            text_class = 'text-purple-600'
        
        trend_html = ""
        if trend is not None:
            try:
                trend_value = float(trend) if trend != 0 else 0
                trend_direction = "📈" if trend_value > 0 else "📉" if trend_value < 0 else "➡️"
                trend_color = "text-green-500" if trend_value > 0 else "text-red-500" if trend_value < 0 else "text-gray-500"
                trend_html = f'''
                <div class="absolute top-4 right-4">
                    <div class="text-xs {trend_color} font-medium">
                        {trend_direction} {abs(trend_value):.1f}
                    </div>
                </div>
                '''
            except (ValueError, TypeError):
                trend_html = ""
        
        desc_html = ""
        if description:
            desc_html = f'<div class="metric-description">{description}</div>'
        
        # Адаптация цветов для темной темы
        if dark_mode:
            bg_style = f"background: var(--surface-white); border-left: 4px solid {text_class.replace('text-', '#')};"
        else:
            bg_style = ""
        
        card_html = f"""
        <div class="metric-card status-{status} relative" style="{bg_style}">
            <div class="metric-label mb-3" style="color: var(--text-secondary)">{title}</div>
            <div class="metric-value" style="color: var(--text-primary); font-weight: bold;">{value}</div>
            {desc_html}
            {trend_html}
        </div>
        """
        
        st.markdown(card_html, unsafe_allow_html=True)
    
    @staticmethod
    def ai_recommendation_panel(recommendations):
        """Панель AI рекомендаций с современным дизайном"""
        
        if not recommendations:
            return
        
        st.markdown("### 🤖 Персональные рекомендации")
        
        # Контейнер для AI-панели
        st.markdown("""
        <div class="ai-panel">
            <div class="flex items-center gap-3 mb-4">
                <div class="w-12 h-12 bg-white bg-opacity-20 rounded-full flex items-center justify-center">
                    <span class="text-2xl">🧠</span>
                </div>
                <div>
                    <h3 class="text-xl font-bold">AI Тренер</h3>
                    <p class="text-sm opacity-90">Анализ на основе ваших данных</p>
                </div>
            </div>
        """, unsafe_allow_html=True)
        
        # Отображаем рекомендации
        for rec in recommendations:
            priority_colors = {"high": "#EF4444", "medium": "#F59E0B", "low": "#10B981"}
            priority_color = priority_colors.get(rec['priority'], '#667eea')
            
            st.markdown(f"""
            <div class="ai-recommendation" style="border-left: 3px solid {priority_color};">
                <div class="mb-2">
                    <strong>{rec['title']}</strong>
                </div>
                <p class="text-sm mb-3">{rec['description']}</p>
            </div>
            """, unsafe_allow_html=True)
        
        st.markdown("</div>", unsafe_allow_html=True)
    
    @staticmethod
    def create_mini_trend_chart(data, title, color="#3B82F6", height=100):
        """Создание мини-графика тренда"""
        
        fig = go.Figure()
        
        # Основная линия тренда
        fig.add_trace(go.Scatter(
            y=data,
            mode='lines+markers',
            line=dict(color=color, width=2),
            marker=dict(size=4, color=color),
            showlegend=False,
            hovertemplate='%{y:.1f}<extra></extra>'
        ))
        
        # Заливка под линией
        fig.add_trace(go.Scatter(
            y=data,
            fill='tozeroy',
            mode='none',
            fillcolor=f'rgba({int(color[1:3], 16)}, {int(color[3:5], 16)}, {int(color[5:7], 16)}, 0.1)',
            showlegend=False,
            hoverinfo='skip'
        ))
        
        # Минималистичное оформление
        fig.update_layout(
            height=height,
            margin=dict(l=0, r=0, t=25, b=0),
            xaxis=dict(
                showticklabels=False, 
                showgrid=False,
                showline=False,
                zeroline=False
            ),
            yaxis=dict(
                showticklabels=False, 
                showgrid=True,
                gridcolor='rgba(0,0,0,0.1)',
                showline=False,
                zeroline=False
            ),
            title=dict(
                text=title, 
                font=dict(size=12, color='#64748B'),
                x=0.5,
                y=0.95
            ),
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)'
        )
        
        return fig
    
    @staticmethod
    def metric_card_html(title, value, status, trend=None, description=None):
        """HTML для современной карточки метрики"""
        
        # Конфигурации статусов
        status_configs = {
            'success': {
                'bg': 'bg-green-50', 'border': 'border-green-200', 
                'text': 'text-green-700', 'emoji': '🟢'
            },
            'warning': {
                'bg': 'bg-yellow-50', 'border': 'border-yellow-200',
                'text': 'text-yellow-700', 'emoji': '🟡'
            },
            'danger': {
                'bg': 'bg-red-50', 'border': 'border-red-200',
                'text': 'text-red-700', 'emoji': '🔴'
            },
            'info': {
                'bg': 'bg-blue-50', 'border': 'border-blue-200',
                'text': 'text-blue-700', 'emoji': '🔵'
            }
        }
        
        config = status_configs.get(status, status_configs['info'])
        
        trend_html = ""
        if trend is not None:
            try:
                trend_value = float(trend) if trend != 0 else 0
                trend_direction = "📈" if trend_value > 0 else "📉" if trend_value < 0 else "➡️"
                trend_color = "text-green-500" if trend_value > 0 else "text-red-500" if trend_value < 0 else "text-gray-500"
                trend_html = f'''
                <div class="absolute top-4 right-4">
                    <div class="text-xs {trend_color} font-medium">
                        {trend_direction} {abs(trend_value):.1f}
                    </div>
                </div>
                '''
            except (ValueError, TypeError):
                trend_html = ""
        
        desc_html = ""
        if description:
            desc_html = f'<div class="metric-description">{description}</div>'
        
        return f"""
        <div class="metric-card {config['bg']} border {config['border']} relative">
            <div class="flex items-center gap-2 mb-3">
                <span class="text-lg">{config['emoji']}</span>
                <div class="metric-label">{title}</div>
            </div>
            <div class="metric-value {config['text']}">{value}</div>
            {desc_html}
            {trend_html}
        </div>
        """
    
    @staticmethod
    def show_horizontal_nav(current_page="Dashboard"):
        """Горизонтальная навигация в стиле AIEndurance с Streamlit компонентами"""
        
        # Создаем градиентный фон для навигации
        st.markdown("""
        <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                   border-radius: 20px; padding: 20px; margin-bottom: 30px;
                   box-shadow: 0 10px 25px rgba(102, 126, 234, 0.3);">
        """, unsafe_allow_html=True)
        
        # Создаем колонки для навигации
        nav_col, user_col = st.columns([4, 1])
        
        with nav_col:
            # Создаем кнопки навигации в одной строке
            nav_cols = st.columns(7)
            
            nav_items = [
                {"name": "Дашборд", "key": "dashboard"},
                {"name": "Календарь", "key": "calendar"},  
                {"name": "Питание", "key": "nutrition"},
                {"name": "План", "key": "plan"},
                {"name": "Восстановление", "key": "recovery"},
                {"name": "Данные", "key": "data"},
                {"name": "Чат", "key": "chat"}
            ]
            
            for i, item in enumerate(nav_items):
                with nav_cols[i]:
                    # Используем стили для активных/неактивных кнопок
                    if item["name"] == current_page:
                        button_style = """
                        background: rgba(255, 255, 255, 0.25) !important;
                        color: white !important;
                        border: none !important;
                        border-radius: 8px !important;
                        font-weight: 600 !important;
                        """
                    else:
                        button_style = """
                        background: transparent !important;
                        color: rgba(255, 255, 255, 0.8) !important;
                        border: none !important;
                        border-radius: 8px !important;
                        font-weight: 500 !important;
                        """
                    
                    # Применяем стили для каждой кнопки индивидуально
                    button_key = f"nav_{item['key']}"
                    st.markdown(f"""
                    <style>
                    button[data-testid="baseButton-secondary"][key="{button_key}"] {{
                        {button_style}
                        transition: all 0.3s ease !important;
                        width: 100% !important;
                        padding: 12px 8px !important;
                        font-size: 11px !important;
                        height: 60px !important;
                        white-space: pre-line !important;
                        text-align: center !important;
                    }}
                    button[data-testid="baseButton-secondary"][key="{button_key}"]:hover {{
                        background: rgba(255, 255, 255, 0.15) !important;
                        color: white !important;
                        transform: translateY(-1px) !important;
                    }}
                    </style>
                    """, unsafe_allow_html=True)
                    
                    if st.button(item['name'], key=f"nav_{item['key']}", use_container_width=True):
                        st.session_state.selected_page = item['name']
                        st.rerun()
        
        with user_col:
            # Пользовательская секция
            st.markdown("""
            <div style="display: flex; justify-content: flex-end; align-items: center; 
                       gap: 15px; color: white; height: 60px;">
                <span style="font-size: 20px; cursor: pointer; 
                           transition: transform 0.2s ease;"
                      onmouseover="this.style.transform='scale(1.1)'"
                      onmouseout="this.style.transform='scale(1)'">🔔</span>
                <div style="width: 40px; height: 40px; border-radius: 50%; 
                           background: white; display: flex; align-items: center; 
                           justify-content: center; color: #667eea; font-weight: bold;
                           font-size: 16px; cursor: pointer; box-shadow: 0 2px 8px rgba(0,0,0,0.1);
                           transition: all 0.2s ease;"
                     onmouseover="this.style.transform='scale(1.05)'; this.style.boxShadow='0 0 0 3px rgba(255,255,255,0.3)'"
                     onmouseout="this.style.transform='scale(1)'; this.style.boxShadow='0 2px 8px rgba(0,0,0,0.1)'">
                    Г
                </div>
            </div>
            """, unsafe_allow_html=True)
        
        # Закрываем градиентный контейнер
        st.markdown("</div>", unsafe_allow_html=True)
    
    @staticmethod
    def create_circular_indicator(value, max_value, title, subtitle, color="#667eea"):
        """Круговой индикатор в стиле AIEndurance"""
        
        percentage = (value / max_value) * 100 if max_value > 0 else 0
        
        fig = go.Figure(go.Indicator(
            mode="gauge+number",
            value=percentage,
            number={'suffix': "%", 'font': {'size': 40, 'color': color}},
            domain={'x': [0, 1], 'y': [0, 1]},
            title={'text': f"{title}<br><span style='font-size:14px'>{subtitle}</span>"},
            gauge={
                'axis': {'range': [None, 100], 'visible': False},
                'bar': {'color': color, 'thickness': 0.15},
                'bgcolor': "rgba(0,0,0,0)",
                'borderwidth': 0,
                'bordercolor': "rgba(0,0,0,0)",
                'steps': [
                    {'range': [0, 100], 'color': 'rgba(102, 126, 234, 0.1)'}
                ]
            }
        ))
        
        fig.update_layout(
            height=250,
            margin=dict(l=20, r=20, t=50, b=20),
            paper_bgcolor='rgba(232, 240, 255, 0.5)',
            font={'family': 'Inter, sans-serif'}
        )
        
        return fig
    
    @staticmethod
    def create_hrv_card_with_trend(value, max_value, title, subtitle, trend_data, color="#667eea", badge_text=None):
        """Карточка HRV с трендом внизу в стиле AI Endurance"""
        percentage = (value / max_value) * 100 if max_value > 0 else 0
        
        # Создаем фигуру с двумя subplot'ами
        from plotly.subplots import make_subplots
        
        fig = make_subplots(
            rows=2, cols=1,
            row_heights=[0.7, 0.3],  # 70% для круга, 30% для тренда
            vertical_spacing=0.05,
            specs=[[{"type": "indicator"}], [{"type": "scatter"}]]
        )
        
        # Круговой индикатор
        fig.add_trace(go.Indicator(
            mode="gauge+number",
            value=percentage,
            number={'suffix': "%", 'font': {'size': 32, 'color': color}},
            domain={'x': [0, 1], 'y': [0, 1]},
            gauge={
                'axis': {'range': [None, 100], 'visible': False},
                'bar': {'color': color, 'thickness': 0.2},
                'bgcolor': "rgba(0,0,0,0)",
                'borderwidth': 0,
                'steps': [
                    {'range': [0, 100], 'color': 'rgba(102, 126, 234, 0.15)'}
                ]
            }
        ), row=1, col=1)
        
        # График тренда
        if trend_data and len(trend_data) > 0:
            fig.add_trace(go.Scatter(
                x=list(range(len(trend_data))),
                y=trend_data,
                mode='lines',
                line=dict(color=color, width=2),
                fill='tonexty',
                fillcolor=f'rgba(102, 126, 234, 0.2)',
                showlegend=False,
                hoverinfo='skip'
            ), row=2, col=1)
        
        # Настройка layout
        fig.update_layout(
            height=400,
            margin=dict(l=10, r=10, t=80, b=20),
            paper_bgcolor='rgba(232, 240, 255, 0.8)',
            plot_bgcolor='rgba(232, 240, 255, 0.8)',
            font={'family': 'Inter, sans-serif'},
            title={
                'text': f"<b>{title}</b><br><span style='font-size:14px; color:#64748B'>{subtitle}</span>",
                'x': 0.5,
                'y': 0.95,
                'font': {'size': 16, 'color': '#1E293B'}
            }
        )
        
        # Убираем оси у графика тренда
        fig.update_xaxes(visible=False, row=2, col=1)
        fig.update_yaxes(visible=False, row=2, col=1)
        
        return fig
    
    @staticmethod
    def create_hrv_dashboard_grid(hrv_data, current_status):
        """Создает сетку HRV карточек в стиле AI Endurance"""
        st.markdown("### Connect your heart rate data to see your recovery")
        
        # 4 карточки в ряд
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            # DFA α1 - пока заглушка
            st.markdown("""
            <div style="background: linear-gradient(135deg, #E8F0FF 0%, #E0E8FF 100%); 
                       padding: 20px; border-radius: 15px; text-align: center; height: 400px;">
                <h4 style="color: #64748B;">DFA α₁</h4>
                <div style="margin: 50px 0;">
                    <div style="font-size: 48px; color: #64748B;">N/A</div>
                </div>
                <div style="height: 120px; background: linear-gradient(to top, rgba(102,126,234,0.1), rgba(102,126,234,0.05)); 
                           border-radius: 10px; margin-top: 50px; position: relative;">
                    <svg style="width: 100%; height: 100%;">
                        <path d="M10,80 Q30,60 50,70 T90,85 T130,75 T170,80" 
                              stroke="rgba(102,126,234,0.4)" stroke-width="2" fill="none"/>
                    </svg>
                </div>
            </div>
            """, unsafe_allow_html=True)
        
        with col2:
            # RMSSD карточка в едином стиле
            rmssd_value = current_status.get('hrv', 39)
            trend_data = hrv_data['rmssd'].tail(14).tolist() if not hrv_data.empty else []
            
            # Генерируем SVG линию тренда
            if trend_data and len(trend_data) > 1:
                # Нормализуем данные для SVG (высота 80px, ширина 280px)
                min_val, max_val = min(trend_data), max(trend_data)
                range_val = max_val - min_val if max_val > min_val else 1
                
                points = []
                for i, val in enumerate(trend_data):
                    x = (i / (len(trend_data) - 1)) * 280
                    y = 80 - ((val - min_val) / range_val) * 60  # 60px рабочая высота
                    points.append(f"{x:.1f},{y:.1f}")
                
                path = f"M{' L'.join(points)}"
                
                # Создаем область заливки
                fill_points = points + ["280,80", "0,80"]
                fill_path = f"M{' L'.join(fill_points)}Z"
            else:
                path = "M10,40 Q70,30 140,45 T270,40"  # Заглушка
                fill_path = "M10,40 Q70,30 140,45 T270,40 L270,80 L10,80 Z"
            
            st.markdown(f"""
            <div style="position: relative; background: linear-gradient(135deg, #E8F0FF 0%, #E0E8FF 100%); 
                       padding: 20px; border-radius: 15px; text-align: center; height: 400px;">
                <div style="position: absolute; top: 10px; right: 10px; 
                           background: #667eea; color: white; padding: 4px 8px; 
                           border-radius: 12px; font-size: 11px; font-weight: 600;">
                    Driving Aerobic Recovery
                </div>
                <h4 style="color: #64748B; margin-top: 10px;">RMSSD</h4>
                <div style="font-size: 12px; color: #64748B; margin-bottom: 10px;">{rmssd_value}.0 ms</div>
                
                <div style="position: relative; width: 140px; height: 140px; margin: 20px auto;">
                    <svg width="140" height="140" style="transform: rotate(-90deg);">
                        <circle cx="70" cy="70" r="60" stroke="rgba(102,126,234,0.15)" stroke-width="12" fill="none"/>
                        <circle cx="70" cy="70" r="60" stroke="#667eea" stroke-width="12" fill="none"
                                stroke-dasharray="{(rmssd_value/50)*377:.1f} 377" stroke-linecap="round"/>
                    </svg>
                    <div style="position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%) rotate(0deg);">
                        <div style="font-size: 32px; font-weight: bold; color: #667eea;">{int((rmssd_value/50)*100)}%</div>
                    </div>
                </div>
                <div style="height: 100px; margin-top: 20px; position: relative;">
                    <svg style="width: 100%; height: 100%;" viewBox="0 0 280 80">
                        <defs>
                            <linearGradient id="rmssdGradient" x1="0%" y1="0%" x2="0%" y2="100%">
                                <stop offset="0%" style="stop-color:rgba(102,126,234,0.3);stop-opacity:1" />
                                <stop offset="100%" style="stop-color:rgba(102,126,234,0.05);stop-opacity:1" />
                            </linearGradient>
                        </defs>
                        <path d="{fill_path}" fill="url(#rmssdGradient)"/>
                        <path d="{path}" stroke="#667eea" stroke-width="2" fill="none"/>
                    </svg>
                </div>
            </div>
            """, unsafe_allow_html=True)
        
        with col3:
            # HR Rest карточка в едином стиле
            hr_rest = 56  # Можно получить из данных
            trend_data_hr = [55, 57, 56, 58, 56, 57, 55, 56, 57, 55, 56] if not hrv_data.empty else []
            
            # Генерируем SVG линию тренда для HR
            if trend_data_hr and len(trend_data_hr) > 1:
                min_val, max_val = min(trend_data_hr), max(trend_data_hr)
                range_val = max_val - min_val if max_val > min_val else 1
                
                points = []
                for i, val in enumerate(trend_data_hr):
                    x = (i / (len(trend_data_hr) - 1)) * 280
                    y = 80 - ((val - min_val) / range_val) * 60
                    points.append(f"{x:.1f},{y:.1f}")
                
                path = f"M{' L'.join(points)}"
                fill_points = points + ["280,80", "0,80"]
                fill_path = f"M{' L'.join(fill_points)}Z"
            else:
                path = "M10,50 Q70,45 140,55 T270,50"  # Заглушка
                fill_path = "M10,50 Q70,45 140,55 T270,50 L270,80 L10,80 Z"
            
            st.markdown(f"""
            <div style="background: linear-gradient(135deg, #E8F0FF 0%, #E0E8FF 100%); 
                       padding: 20px; border-radius: 15px; text-align: center; height: 400px;">
                <h4 style="color: #64748B; margin-top: 10px;">HR Rest</h4>
                <div style="font-size: 12px; color: #64748B; margin-bottom: 10px;">{hr_rest} bpm</div>
                
                <div style="position: relative; width: 140px; height: 140px; margin: 20px auto;">
                    <svg width="140" height="140" style="transform: rotate(-90deg);">
                        <circle cx="70" cy="70" r="60" stroke="rgba(245,158,11,0.15)" stroke-width="12" fill="none"/>
                        <circle cx="70" cy="70" r="60" stroke="#F59E0B" stroke-width="12" fill="none"
                                stroke-dasharray="377 377" stroke-linecap="round"/>
                    </svg>
                    <div style="position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%) rotate(0deg);">
                        <div style="font-size: 32px; font-weight: bold; color: #F59E0B;">100%</div>
                    </div>
                </div>
                <div style="height: 100px; margin-top: 20px;">
                    <svg style="width: 100%; height: 100%;" viewBox="0 0 280 80">
                        <defs>
                            <linearGradient id="hrGradient" x1="0%" y1="0%" x2="0%" y2="100%">
                                <stop offset="0%" style="stop-color:rgba(245,158,11,0.3);stop-opacity:1" />
                                <stop offset="100%" style="stop-color:rgba(245,158,11,0.05);stop-opacity:1" />
                            </linearGradient>
                        </defs>
                        <path d="{fill_path}" fill="url(#hrGradient)"/>
                        <path d="{path}" stroke="#F59E0B" stroke-width="2" fill="none"/>
                    </svg>
                </div>
            </div>
            """, unsafe_allow_html=True)
        
        with col4:
            # ESS (Exercise Strain Score) - заглушка
            st.markdown("""
            <div style="background: linear-gradient(135deg, #E8F0FF 0%, #E0E8FF 100%); 
                       padding: 20px; border-radius: 15px; text-align: center; height: 400px;">
                <h4 style="color: #64748B;">ESS on Aug 23, 2025</h4>
                <div style="margin: 50px 0;">
                    <div style="font-size: 48px; color: #64748B;">30</div>
                </div>
                <div style="height: 120px; background: linear-gradient(to top, rgba(102,126,234,0.1), rgba(102,126,234,0.05)); 
                           border-radius: 10px; margin-top: 50px;">
                    <svg style="width: 100%; height: 100%;">
                        <path d="M10,100 L20,80 L30,90 L40,70 L50,75 L60,60 L70,85 L80,90 L90,75 L100,80" 
                              stroke="rgba(102,126,234,0.6)" stroke-width="2" fill="none"/>
                    </svg>
                </div>
            </div>
            """, unsafe_allow_html=True)
    
    @staticmethod
    def show_recent_workout_card(activity_data=None):
        """Карточка последней тренировки в стиле AIEndurance с Streamlit компонентами"""
        
        if not activity_data:
            # Заглушка для демонстрации
            activity_data = {
                'activity_name': 'Утренняя пробежка',
                'start_time': '08:00',
                'distance': '10.5',
                'duration': '45:32',
                'avg_power': '285',
                'elevation': '156',
                'ess': '128'
            }
        
        # Создаем контейнер с градиентным фоном
        st.markdown("""
        <div style="background: linear-gradient(135deg, #1A2B4D 0%, #2D3E5F 100%);
                   border-radius: 20px; padding: 25px; color: white; margin-bottom: 20px;
                   box-shadow: 0 10px 25px rgba(26, 43, 77, 0.3);">
        """, unsafe_allow_html=True)
        
        # Заголовок
        st.markdown("""
        <div style="font-size: 12px; opacity: 0.8; margin-bottom: 10px; color: white;">
            Последняя тренировка
        </div>
        """, unsafe_allow_html=True)
        
        # Название активности
        st.markdown(f"""
        <h2 style="margin: 10px 0 20px 0; font-size: 24px; font-weight: bold; color: white;">
            {activity_data['activity_name']}
        </h2>
        """, unsafe_allow_html=True)
        
        # Создаем сетку для метрик
        metric_col1, metric_col2 = st.columns(2)
        
        with metric_col1:
            st.markdown(f"""
            <div style="color: white; margin-bottom: 15px;">
                <div style="opacity: 0.6; font-size: 12px;">Время начала</div>
                <div style="font-size: 16px; font-weight: bold;">{activity_data['start_time']}</div>
            </div>
            """, unsafe_allow_html=True)
            
            st.markdown(f"""
            <div style="color: white; margin-bottom: 15px;">
                <div style="opacity: 0.6; font-size: 12px;">Время</div>
                <div style="font-size: 16px; font-weight: bold;">{activity_data['duration']}</div>
            </div>
            """, unsafe_allow_html=True)
            
            st.markdown(f"""
            <div style="color: white; margin-bottom: 15px;">
                <div style="opacity: 0.6; font-size: 12px;">Набор высоты</div>
                <div style="font-size: 16px; font-weight: bold;">{activity_data['elevation']} м</div>
            </div>
            """, unsafe_allow_html=True)
        
        with metric_col2:
            st.markdown(f"""
            <div style="color: white; margin-bottom: 15px;">
                <div style="opacity: 0.6; font-size: 12px;">Дистанция</div>
                <div style="font-size: 16px; font-weight: bold;">{activity_data['distance']} км</div>
            </div>
            """, unsafe_allow_html=True)
            
            st.markdown(f"""
            <div style="color: white; margin-bottom: 15px;">
                <div style="opacity: 0.6; font-size: 12px;">Средняя мощность</div>
                <div style="font-size: 16px; font-weight: bold;">{activity_data['avg_power']} Вт</div>
            </div>
            """, unsafe_allow_html=True)
            
            st.markdown(f"""
            <div style="color: white; margin-bottom: 15px;">
                <div style="opacity: 0.6; font-size: 12px;">ESS</div>
                <div style="font-size: 16px; font-weight: bold;">{activity_data['ess']}</div>
            </div>
            """, unsafe_allow_html=True)
        
        # Кнопка с использованием Streamlit
        st.markdown("<div style='text-align: center; margin-top: 20px;'>", unsafe_allow_html=True)
        if st.button("Анализ", key="workout_analysis", use_container_width=False):
            st.session_state.selected_page = "Активности"
            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)
        
        # Закрываем контейнер
        st.markdown("</div>", unsafe_allow_html=True)
    
    @staticmethod
    def show_weekly_training_calendar():
        """Недельный календарь тренировок с реальными данными"""
        
        st.markdown("### Тренировки на этой неделе")
        
        days = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']
        cols = st.columns(7)
        
        # Получаем реальные данные тренировок за текущую неделю
        import datetime
        from datetime import timedelta
        
        # Находим понедельник текущей недели
        today = datetime.date.today()
        monday = today - timedelta(days=today.weekday())
        
        # Получаем тренировки за неделю
        activities_df = st.session_state.database.get_activities(7)
        
        week_workouts = [None] * 7  # Инициализируем пустую неделю
        
        if not activities_df.empty:
            for _, activity in activities_df.iterrows():
                activity_date = activity['date']
                if isinstance(activity_date, str):
                    activity_date = datetime.datetime.strptime(activity_date, '%Y-%m-%d').date()
                elif hasattr(activity_date, 'date'):
                    activity_date = activity_date.date()
                
                # Определяем день недели (0=понедельник, 6=воскресенье)
                if monday <= activity_date < monday + timedelta(days=7):
                    day_index = (activity_date - monday).days
                    
                    # Определяем тип тренировки
                    sport_type = activity.get('sport', 'Другое')
                    type_mapping = {
                        'running': 'Бег',
                        'cycling': 'Велосипед', 
                        'swimming': 'Плавание',
                        'triathlon': 'Триатлон',
                        'walking': 'Ходьба',
                        'Бег': 'Бег',
                        'Велосипед': 'Велосипед',
                        'Плавание': 'Плавание',
                        'Ходьба': 'Ходьба'
                    }
                    workout_type = type_mapping.get(sport_type, sport_type if sport_type else 'Другое')
                    
                    # Форматируем длительность (в базе хранится в минутах)
                    duration_minutes = activity.get('duration_minutes', 0)
                    if duration_minutes and duration_minutes > 0:
                        hours = int(duration_minutes // 60)
                        minutes = int(duration_minutes % 60)
                        if hours > 0:
                            duration_str = f"{hours}ч {minutes}м"
                        else:
                            duration_str = f"{minutes}м"
                    else:
                        duration_str = "Н/Д"
                    
                    # Форматируем дистанцию (в базе уже в км)
                    distance_km = activity.get('distance_km', 0)
                    if distance_km and distance_km > 0:
                        distance_str = f"{distance_km:.1f}км"
                    else:
                        distance_str = "Н/Д"
                    
                    week_workouts[day_index] = {
                        'type': workout_type,
                        'distance': distance_str,
                        'duration': duration_str,
                        'completed': True,  # Все загруженные активности считаются завершенными
                        'tss': activity.get('tss', 0)
                    }
        
        colors = {
            'Бег': '#E8F0FF',
            'Велосипед': '#F0E8FF', 
            'Плавание': '#FFE8E8',
            'Ходьба': '#E8FFF0',
            'Другое': '#FFF8E8'
        }
        
        for i, day in enumerate(days):
            with cols[i]:
                workout = week_workouts[i]
                
                if workout:
                    status_color = "#10B981" if workout['completed'] else "#F59E0B"
                    bg_color = colors.get(workout['type'], '#E8F0FF')
                    
                    st.markdown(f"""
                    <div style="background: {bg_color};
                               border-radius: 15px; padding: 12px; height: 130px;
                               border-left: 4px solid {status_color}; position: relative;
                               box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                               transition: all 0.3s ease;"
                         onmouseover="this.style.transform='translateY(-2px)'; this.style.boxShadow='0 4px 8px rgba(0,0,0,0.15)'"
                         onmouseout="this.style.transform='translateY(0)'; this.style.boxShadow='0 2px 4px rgba(0,0,0,0.1)'">
                        <div style="text-align: center; font-weight: bold; margin-bottom: 8px;">{day}</div>
                        <div style="margin-bottom: 8px; font-weight: 500;">
                            {workout['type']}
                        </div>
                        <div style="font-size: 12px; color: #666;">
                            {workout['distance']} км<br>
                            {workout['duration']}
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    # Пустой день (отдых)
                    st.markdown(f"""
                    <div style="background: #1A2B4D; border-radius: 15px; 
                               padding: 12px; height: 130px;
                               box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                        <div style="text-align: center; color: white; 
                                   font-weight: bold; margin-top: 30px;">{day}</div>
                        <div style="text-align: center; color: #8A92A5; 
                                   margin-top: 15px; font-size: 12px;">Отдых</div>
                    </div>
                    """, unsafe_allow_html=True)