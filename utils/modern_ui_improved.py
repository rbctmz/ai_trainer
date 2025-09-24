"""
Улучшенные UI компоненты с полной поддержкой темной темы
"""

import streamlit as st
import plotly.graph_objects as go

class ModernUI:
    """Современные UI компоненты для AI Trainer с улучшенной поддержкой тем"""
    
    # Цветовые схемы для светлой и темной тем
    LIGHT_THEME = {
        'primary_gradient': 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
        'surface_white': '#FFFFFF',
        'surface_light': '#E8F0FF',
        'surface_dark': '#1A2B4D',
        'text_primary': '#1E293B',
        'text_secondary': '#64748B',
        'border_gray': '#E2E8F0',
        'bg_primary': '#F8FAFF',
        'metric_bg': '#FFFFFF',
        'metric_border': '#E2E8F0'
    }
    
    DARK_THEME = {
        'primary_gradient': 'linear-gradient(135deg, #4C5FD5 0%, #5E3B8E 100%)',
        'surface_white': '#1E1E1E',
        'surface_light': '#2D2D2D',
        'surface_dark': '#0F172A',
        'text_primary': '#F5F5F5',
        'text_secondary': '#A0A0A0',
        'border_gray': '#2B2B2B',
        'bg_primary': '#121212',
        'metric_bg': '#1E1E1E',
        'metric_border': '#2B2B2B'
    }
    
    @classmethod
    def get_theme(cls):
        """Получить текущую тему из session state"""
        return cls.DARK_THEME if st.session_state.get('dark_mode', False) else cls.LIGHT_THEME
    
    @staticmethod
    def apply_modern_styles(dark_mode=False):
        """Применяет современную CSS-стилизацию с полной поддержкой тем"""
        
        theme = ModernUI.DARK_THEME if dark_mode else ModernUI.LIGHT_THEME
        
        # CSS с динамическими значениями из темы
        css = f"""
        <style>
        /* Импорт современного шрифта */
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
        
        /* Переменные темы */
        :root {{
            --primary-gradient: {theme['primary_gradient']};
            --surface-white: {theme['surface_white']};
            --surface-light: {theme['surface_light']};
            --surface-dark: {theme['surface_dark']};
            --text-primary: {theme['text_primary']};
            --text-secondary: {theme['text_secondary']};
            --border-gray: {theme['border_gray']};
            --bg-primary: {theme['bg_primary']};
            --metric-bg: {theme['metric_bg']};
            --metric-border: {theme['metric_border']};
            
            /* Совместимость со старым кодом */
            --primary-blue: #667eea;
            --success-green: #10B981;
            --warning-yellow: #F59E0B;
            --danger-red: #EF4444;
            --shadow-sm: 0 1px 2px 0 rgba(0, 0, 0, 0.05);
            --shadow-md: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
            --shadow-lg: 0 10px 15px -3px rgba(0, 0, 0, 0.1);
        }}
        
        /* Базовые стили приложения */
        .stApp {{
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            background-color: {theme['bg_primary']} !important;
            color: {theme['text_primary']} !important;
        }}
        
        /* Современные карточки */
        .modern-card {{
            background: {theme['metric_bg']} !important;
            border-radius: 16px;
            box-shadow: var(--shadow-sm);
            border: 1px solid {theme['metric_border']} !important;
            padding: 24px;
            margin-bottom: 16px;
            color: {theme['text_primary']} !important;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }}
        
        .modern-card:hover {{
            box-shadow: var(--shadow-md);
            transform: translateY(-2px);
        }}
        
        /* Метрические карточки */
        .metric-card {{
            background: {theme['metric_bg']} !important;
            border-radius: 12px;
            padding: 20px;
            box-shadow: var(--shadow-sm);
            border: 1px solid {theme['metric_border']} !important;
            color: {theme['text_primary']} !important;
            height: 100%;
            transition: all 0.2s ease;
        }}
        
        .metric-card:hover {{
            box-shadow: var(--shadow-md);
        }}
        
        .metric-value {{
            font-size: 2.25rem;
            font-weight: 700;
            line-height: 1;
            margin-bottom: 0.5rem;
            color: {theme['text_primary']} !important;
        }}
        
        .metric-label {{
            font-size: 0.875rem;
            color: {theme['text_secondary']} !important;
            font-weight: 500;
            margin-bottom: 0.75rem;
        }}
        
        .metric-description {{
            font-size: 0.75rem;
            color: {theme['text_secondary']} !important;
        }}
        
        /* AI панель с адаптивным градиентом */
        .ai-panel {{
            background: {theme['primary_gradient']};
            border-radius: 20px;
            padding: 32px;
            color: white !important;
            margin: 24px 0;
            box-shadow: var(--shadow-lg);
        }}
        
        .ai-recommendation {{
            background: rgba(255, 255, 255, {'0.1' if dark_mode else '0.15'});
            border: 1px solid rgba(255, 255, 255, 0.2);
            border-radius: 12px;
            padding: 16px;
            margin: 12px 0;
            backdrop-filter: blur(10px);
            color: white !important;
        }}
        
        /* Статус-карточки с цветными индикаторами */
        .status-card {{
            position: relative;
            overflow: hidden;
            background: {theme['metric_bg']} !important;
            color: {theme['text_primary']} !important;
        }}
        
        .status-card::before {{
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            width: 4px;
            height: 100%;
        }}
        
        .status-excellent::before {{ background: var(--success-green); }}
        .status-good::before {{ background: var(--warning-yellow); }}
        .status-warning::before {{ background: var(--danger-red); }}
        .status-critical::before {{ background: #991B1B; }}
        
        /* Кнопки с адаптацией к теме */
        .stButton > button {{
            background-color: {'#2D2D2D' if dark_mode else '#FFFFFF'} !important;
            color: {theme['text_primary']} !important;
            border: 1px solid {theme['border_gray']} !important;
            transition: all 0.2s ease;
        }}
        
        .stButton > button:hover {{
            background-color: {'#3D3D3D' if dark_mode else '#F5F5F5'} !important;
            border-color: var(--primary-blue) !important;
        }}
        
        /* Табы и селекторы */
        .stTabs [data-baseweb="tab"] {{
            background-color: {theme['metric_bg']} !important;
            color: {theme['text_primary']} !important;
        }}
        
        .stTabs [aria-selected="true"] {{
            background-color: var(--primary-blue) !important;
            color: white !important;
        }}
        
        /* Поля ввода */
        .stTextInput > div > div > input,
        .stSelectbox > div > div,
        .stTextArea > div > div > textarea {{
            background-color: {theme['metric_bg']} !important;
            color: {theme['text_primary']} !important;
            border: 1px solid {theme['border_gray']} !important;
        }}
        
        /* Expander */
        .streamlit-expanderHeader {{
            background-color: {theme['metric_bg']} !important;
            color: {theme['text_primary']} !important;
        }}
        
        /* Dataframe */
        .dataframe {{
            background-color: {theme['metric_bg']} !important;
            color: {theme['text_primary']} !important;
        }}
        
        /* Sidebar */
        section[data-testid="stSidebar"] {{
            background-color: {theme['surface_dark'] if dark_mode else '#F0F2F6'} !important;
        }}
        
        /* Быстрые действия */
        .quick-action-btn {{
            background: {theme['metric_bg']} !important;
            border: 2px solid {theme['border_gray']} !important;
            border-radius: 12px;
            padding: 20px;
            text-align: center;
            cursor: pointer;
            transition: all 0.3s ease;
            box-shadow: var(--shadow-sm);
            color: {theme['text_primary']} !important;
        }}
        
        .quick-action-btn:hover {{
            border-color: var(--primary-blue) !important;
            box-shadow: var(--shadow-md);
            transform: translateY(-2px);
        }}
        
        /* Анимации */
        @keyframes slideIn {{
            from {{
                opacity: 0;
                transform: translateY(10px);
            }}
            to {{
                opacity: 1;
                transform: translateY(0);
            }}
        }}
        
        .animate-slide-in {{
            animation: slideIn 0.3s ease-out;
        }}
        
        /* Адаптивность */
        @media (max-width: 768px) {{
            .modern-card {{
                padding: 16px;
                margin-bottom: 12px;
            }}
            
            .ai-panel {{
                padding: 20px;
                margin: 16px 0;
            }}
            
            .metric-value {{
                font-size: 1.75rem;
            }}
        }}
        </style>
        """
        
        st.markdown(css, unsafe_allow_html=True)
    
    @staticmethod
    def status_card(title, value, status_type, trend=None, description=None):
        """Карточка статуса с цветовыми индикаторами и автоматической адаптацией к теме"""
        
        # Получаем текущую тему
        theme = ModernUI.get_theme()
        
        # Безопасное преобразование значения в число для определения статуса
        try:
            if isinstance(value, str):
                # Убираем все не-числовые символы кроме точки и минуса
                numeric_str = ''.join(c for c in value if c.isdigit() or c in '.-')
                numeric_value = float(numeric_str) if numeric_str else 0
            else:
                numeric_value = float(value) if value else 0
        except:
            numeric_value = 0
        
        # Определяем статус и цвет
        if status_type == 'tsb':
            if numeric_value > 5:
                status = 'excellent'
                color = '#10B981'
            elif numeric_value > -10:
                status = 'good'
                color = '#F59E0B'
            elif numeric_value > -30:
                status = 'warning'
                color = '#EF4444'
            else:
                status = 'critical'
                color = '#991B1B'
        elif status_type == 'hrv':
            if numeric_value > 40:
                status = 'excellent'
                color = '#10B981'
            elif numeric_value > 30:
                status = 'good'
                color = '#F59E0B'
            else:
                status = 'warning'
                color = '#EF4444'
        elif status_type == 'readiness':
            if numeric_value > 80:
                status = 'excellent'
                color = '#3B82F6'
            elif numeric_value > 60:
                status = 'good'
                color = '#10B981'
            else:
                status = 'warning'
                color = '#F59E0B'
        else:  # ctl и другие
            status = 'good'
            color = '#8B5CF6'
        
        trend_html = ""
        if trend is not None:
            try:
                trend_value = float(trend) if trend != 0 else 0
                trend_direction = "📈" if trend_value > 0 else "📉" if trend_value < 0 else "➡️"
                trend_html = f'''
                <div style="position: absolute; top: 10px; right: 10px; font-size: 12px;">
                    {trend_direction} {abs(trend_value):.1f}
                </div>
                '''
            except:
                pass
        
        desc_html = f'<div class="metric-description">{description}</div>' if description else ''
        
        card_html = f"""
        <div class="metric-card status-{status}" style="position: relative; border-left: 4px solid {color};">
            <div class="metric-label">{title}</div>
            <div class="metric-value" style="color: {color};">{value}</div>
            {desc_html}
            {trend_html}
        </div>
        """
        
        st.markdown(card_html, unsafe_allow_html=True)
    
    @staticmethod
    def ai_recommendation_panel(recommendations):
        """Панель AI рекомендаций с адаптацией к теме"""
        
        if not recommendations:
            return
        
        st.markdown("### 🤖 Персональные рекомендации")
        
        st.markdown("""
        <div class="ai-panel">
            <div style="display: flex; align-items: center; gap: 15px; margin-bottom: 20px;">
                <div style="width: 48px; height: 48px; background: rgba(255,255,255,0.2); 
                           border-radius: 50%; display: flex; align-items: center; 
                           justify-content: center; font-size: 24px;">
                    🧠
                </div>
                <div>
                    <h3 style="margin: 0; color: white;">AI Тренер</h3>
                    <p style="margin: 0; opacity: 0.9; font-size: 14px; color: white;">
                        Анализ на основе ваших данных
                    </p>
                </div>
            </div>
        """, unsafe_allow_html=True)
        
        for rec in recommendations:
            priority_colors = {
                "high": "#EF4444",
                "medium": "#F59E0B", 
                "low": "#10B981"
            }
            color = priority_colors.get(rec['priority'], '#667eea')
            
            st.markdown(f"""
            <div class="ai-recommendation" style="border-left: 3px solid {color};">
                <div style="margin-bottom: 8px;">
                    <strong style="color: white;">{rec['title']}</strong>
                </div>
                <p style="margin: 0; font-size: 14px; color: white; opacity: 0.9;">
                    {rec['description']}
                </p>
            </div>
            """, unsafe_allow_html=True)
        
        st.markdown("</div>", unsafe_allow_html=True)
    
    @staticmethod
    def create_circular_indicator(value, max_value, title, subtitle, color="#667eea"):
        """Круговой индикатор с адаптацией к теме"""
        
        theme = ModernUI.get_theme()
        percentage = (value / max_value) * 100 if max_value > 0 else 0
        
        # Адаптируем цвет фона под тему
        bg_color = 'rgba(102, 126, 234, 0.1)' if not st.session_state.get('dark_mode', False) else 'rgba(76, 95, 213, 0.2)'
        
        fig = go.Figure(go.Indicator(
            mode="gauge+number",
            value=percentage,
            number={'suffix': "%", 'font': {'size': 40, 'color': color}},
            domain={'x': [0, 1], 'y': [0, 1]},
            title={
                'text': f"{title}<br><span style='font-size:14px'>{subtitle}</span>",
                'font': {'color': theme['text_primary']}
            },
            gauge={
                'axis': {'range': [None, 100], 'visible': False},
                'bar': {'color': color, 'thickness': 0.15},
                'bgcolor': "rgba(0,0,0,0)",
                'borderwidth': 0,
                'bordercolor': "rgba(0,0,0,0)",
                'steps': [
                    {'range': [0, 100], 'color': bg_color}
                ]
            }
        ))
        
        fig.update_layout(
            height=250,
            margin=dict(l=20, r=20, t=50, b=20),
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            font={'family': 'Inter, sans-serif', 'color': theme['text_primary']}
        )
        
        return fig
    
    @staticmethod
    def show_horizontal_nav(current_page="Dashboard"):
        """Горизонтальная навигация с адаптацией к теме"""
        
        theme = ModernUI.get_theme()
        
        st.markdown(f"""
        <div style="background: {theme['primary_gradient']};
                   border-radius: 20px; padding: 20px; margin-bottom: 30px;
                   box-shadow: 0 10px 25px rgba(102, 126, 234, 0.3);">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <h2 style="margin: 0; color: white;">AI Trainer</h2>
                <div style="color: white;">{current_page}</div>
            </div>
        </div>
        """, unsafe_allow_html=True)
    
    @staticmethod
    def show_weekly_training_calendar():
        """Недельный календарь тренировок с адаптацией к теме"""
        
        theme = ModernUI.get_theme()
        st.markdown("### Тренировки на этой неделе")
        
        days = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']
        cols = st.columns(7)
        
        # Получаем данные тренировок если есть база данных
        try:
            activities_df = st.session_state.database.get_activities(7)
        except:
            # Заглушка если нет базы данных
            import pandas as pd
            activities_df = pd.DataFrame()
        
        for i, day in enumerate(days):
            with cols[i]:
                # Определяем есть ли тренировка (заглушка для демо)
                has_workout = i % 3 != 2  # Тренировки в Пн, Вт, Чт, Пт, Вс
                
                if has_workout:
                    workout_type = ['Бег', 'Велосипед', 'Плавание'][i % 3]
                    bg_color = theme['surface_light']
                    text_color = theme['text_primary']
                    border_color = '#10B981'
                    
                    st.markdown(f"""
                    <div style="background: {bg_color}; border-radius: 15px; 
                               padding: 12px; height: 130px;
                               border-left: 4px solid {border_color};
                               box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                        <div style="text-align: center; font-weight: bold; 
                                   margin-bottom: 8px; color: {text_color};">{day}</div>
                        <div style="margin-bottom: 8px; font-weight: 500; color: {text_color};">
                            {workout_type}
                        </div>
                        <div style="font-size: 12px; color: {theme['text_secondary']};">
                            10 км<br>45 мин
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    # День отдыха
                    bg_color = theme['surface_dark']
                    text_color = 'white' if not st.session_state.get('dark_mode', False) else theme['text_secondary']
                    
                    st.markdown(f"""
                    <div style="background: {bg_color}; border-radius: 15px; 
                               padding: 12px; height: 130px;
                               box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                        <div style="text-align: center; color: {text_color}; 
                                   font-weight: bold; margin-top: 30px;">{day}</div>
                        <div style="text-align: center; color: {text_color}; 
                                   margin-top: 15px; font-size: 12px; opacity: 0.7;">Отдых</div>
                    </div>
                    """, unsafe_allow_html=True)
    
    @staticmethod
    def create_mini_trend_chart(data, title, color="#3B82F6", height=100):
        """Мини-график тренда с адаптацией к теме"""
        
        theme = ModernUI.get_theme()
        
        fig = go.Figure()
        
        # Основная линия
        fig.add_trace(go.Scatter(
            y=data,
            mode='lines+markers',
            line=dict(color=color, width=2),
            marker=dict(size=4, color=color),
            showlegend=False,
            hovertemplate='%{y:.1f}<extra></extra>'
        ))
        
        # Заливка
        fig.add_trace(go.Scatter(
            y=data,
            fill='tozeroy',
            mode='none',
            fillcolor=f'rgba({int(color[1:3], 16)}, {int(color[3:5], 16)}, {int(color[5:7], 16)}, 0.1)',
            showlegend=False,
            hoverinfo='skip'
        ))
        
        # Оформление
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
                gridcolor='rgba(0,0,0,0.05)',
                showline=False,
                zeroline=False
            ),
            title=dict(
                text=title, 
                font=dict(size=12, color=theme['text_secondary']),
                x=0.5,
                y=0.95
            ),
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)'
        )
        
        return fig
