"""
Современные UI компоненты для AI Trainer
Модуль содержит класс ModernUI с методами для создания современного интерфейса
"""

import streamlit as st
import plotly.graph_objects as go

class ModernUI:
    """Современные UI компоненты для AI Trainer"""
    
    @staticmethod
    def apply_modern_styles():
        """Применяет современную CSS-стилизацию"""
        st.markdown("""
        <style>
        /* Импорт современного шрифта */
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
        
        /* Базовые переменные */
        :root {
            --primary-blue: #3B82F6;
            --primary-blue-dark: #2563EB;
            --secondary-gray: #64748B;
            --success-green: #10B981;
            --warning-yellow: #F59E0B;
            --danger-red: #EF4444;
            --background-gray: #F8FAFC;
            --surface-white: #FFFFFF;
            --border-gray: #E2E8F0;
            --text-primary: #1E293B;
            --text-secondary: #475569;
            --shadow-sm: 0 1px 2px 0 rgba(0, 0, 0, 0.05);
            --shadow-md: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
            --shadow-lg: 0 10px 15px -3px rgba(0, 0, 0, 0.1);
        }
        
        /* Обновленная типографика */
        .stApp {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
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
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
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
        </style>
        """, unsafe_allow_html=True)
    
    @staticmethod
    def status_card(title, value, status_type, trend=None, description=None):
        """Карточка статуса с цветовыми индикаторами"""
        
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
                emoji = '🟢'
                text_class = 'text-green-600'
            elif numeric_value > -10:
                status = 'good'
                emoji = '🟡'
                text_class = 'text-yellow-600'
            elif numeric_value > -30:
                status = 'warning'
                emoji = '🟠'
                text_class = 'text-orange-600'
            else:
                status = 'critical'
                emoji = '🔴'
                text_class = 'text-red-600'
        elif status_type == 'hrv':
            if numeric_value > 40:
                status = 'excellent'
                emoji = '💚'
                text_class = 'text-green-600'
            elif numeric_value > 30:
                status = 'good'
                emoji = '💛'
                text_class = 'text-yellow-600'
            else:
                status = 'warning'
                emoji = '❤️'
                text_class = 'text-red-600'
        elif status_type == 'readiness':
            if numeric_value > 80:
                status = 'excellent'
                emoji = '🚀'
                text_class = 'text-blue-600'
            elif numeric_value > 60:
                status = 'good'
                emoji = '👍'
                text_class = 'text-green-600'
            else:
                status = 'warning'
                emoji = '⚠️'
                text_class = 'text-yellow-600'
        else:  # ctl
            status = 'good'
            emoji = '💪'
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
        
        card_html = f"""
        <div class="metric-card status-{status} relative">
            <div class="flex items-center gap-2 mb-3">
                <span class="text-lg">{emoji}</span>
                <div class="metric-label">{title}</div>
            </div>
            <div class="metric-value {text_class}">{value}</div>
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
            priority_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}
            
            st.markdown(f"""
            <div class="ai-recommendation">
                <div class="flex items-center gap-2 mb-2">
                    <span>{priority_emoji.get(rec['priority'], '🔵')}</span>
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