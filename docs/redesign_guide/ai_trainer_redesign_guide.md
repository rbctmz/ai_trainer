# AI Trainer - Руководство по редизайну интерфейса

## 🎯 Цель модернизации

Трансформировать текущий функциональный интерфейс Streamlit в современный, интуитивно понятный дизайн с улучшенным UX/UI.

## 🔍 Анализ текущего состояния

### Сильные стороны проекта:
- ✅ Богатая функциональность (HRV, TSS, модель Банистера)
- ✅ Интеграция с Garmin Connect через garth
- ✅ AI-коучинг с несколькими провайдерами
- ✅ Комплексная база данных (SQLite)
- ✅ Модульная архитектура

### Проблемы UX:
- ❌ Информационная перегрузка без приоритизации
- ❌ Слабая визуальная иерархия
- ❌ Разбросанные AI-функции по разным вкладкам
- ❌ Отсутствие контекстных рекомендаций
- ❌ Неинтуитивная навигация

## 🎨 Концепция нового дизайна

### 1. Принципы улучшения:
- **Статусно-ориентированный подход** - показать текущее состояние сразу
- **Контекстные действия** - предлагать что делать дальше
- **Объединенный AI** - единый интерфейс для всех AI-функций
- **Визуальная иерархия** - важное выделено, второстепенное скрыто
- **Прогрессивное раскрытие** - показывать детали по запросу

### 2. Новая структура навигации:
```
📊 Обзор (Dashboard)
├── Статус-панель с критическими показателями
├── AI-рекомендации на основе данных
├── Быстрые действия
└── Краткая аналитика

🏃‍♂️ Активности
├── Фильтры и поиск
├── Интерактивные графики
├── Детальный анализ тренировки
└── Экспорт данных

📈 Планирование
├── Модель Банистера (улучшенная визуализация)
├── Прогноз формы
├── Рекомендации по нагрузке
└── Планы тренировок

⚙️ Данные
├── Синхронизация Garmin
├── Статистика БД
├── AI-настройки
└── Экспорт/импорт
```

## 🛠 Конкретные рекомендации по улучшению

### 1. Файл: `app.py` - Основные улучшения

#### Новая функция `show_dashboard()`:
```python
def show_dashboard():
    """Улучшенный дашборд с фокусом на статус и действия"""
    
    # 1. СТАТУС-ПАНЕЛЬ (приоритет #1)
    st.markdown("### 🎯 Ваш статус сегодня")
    
    # Получаем ключевые метрики
    current_metrics = calculate_current_status()
    
    # Отображаем критический статус (если есть)
    if current_metrics['critical_status']:
        st.error(f"🚨 {current_metrics['critical_status']}")
        st.markdown(f"**Рекомендация:** {current_metrics['critical_action']}")
    
    # 2. КОМПАКТНЫЕ МЕТРИКИ (4 ключевые)
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        display_metric_with_context("TSB", current_metrics['tsb'], "Форма")
    with col2:
        display_metric_with_context("HRV", current_metrics['hrv'], "Восстановление")
    with col3:
        display_metric_with_context("Готовность", current_metrics['readiness'], "Общая")
    with col4:
        display_metric_with_context("Фитнес", current_metrics['ctl'], "CTL")
    
    # 3. AI-РЕКОМЕНДАЦИИ (центральный блок)
    show_ai_recommendations_panel(current_metrics)
    
    # 4. БЫСТРЫЕ ДЕЙСТВИЯ
    show_quick_actions()
    
    # 5. КРАТКАЯ АНАЛИТИКА (сворачиваемая)
    with st.expander("📊 Подробная аналитика"):
        show_compact_charts()
```

#### Новая функция статус-панели:
```python
def calculate_current_status():
    """Расчет текущего статуса с приоритизацией проблем"""
    
    # Получаем все данные
    activities_df = st.session_state.database.get_activities(30)
    hrv_df = st.session_state.database.get_hrv_data(7)
    sleep_df = st.session_state.database.get_sleep_data(7)
    
    status = {
        'critical_status': None,
        'critical_action': None,
        'tsb': 0,
        'hrv': 0,
        'readiness': 0,
        'ctl': 0
    }
    
    # Расчет TSB
    if not activities_df.empty:
        banister = BanisterModel()
        current_metrics = banister.get_current_metrics(...)
        status['tsb'] = current_metrics['tsb']
        status['ctl'] = current_metrics['ctl']
        
        # Критический статус
        if status['tsb'] < -30:
            status['critical_status'] = "Критическое переутомление"
            status['critical_action'] = "Полный отдых 2-3 дня"
        elif status['tsb'] < -20:
            status['critical_status'] = "Сильная усталость"
            status['critical_action'] = "Только легкие восстановительные тренировки"
    
    # HRV анализ
    if not hrv_df.empty:
        latest_hrv = hrv_df.iloc[0]['rmssd']
        baseline_hrv = hrv_df['rmssd'].mean()
        status['hrv'] = latest_hrv
        
        # Дополнительная проверка критического состояния
        if latest_hrv < baseline_hrv * 0.8 and status['critical_status'] is None:
            status['critical_status'] = "Низкий HRV - стресс или недовосстановление"
            status['critical_action'] = "Проверьте качество сна и уровень стресса"
    
    return status
```

### 2. Новый файл: `utils/ui_components.py`

```python
import streamlit as st
import plotly.graph_objects as go

class UIComponents:
    
    @staticmethod
    def status_card(title, value, status_type, trend=None, description=None):
        """Карточка статуса с цветовыми индикаторами"""
        
        # Определяем цвет и иконку на основе типа и значения
        color_config = {
            'tsb': {
                'good': ('🟢', 'text-green-600', 'bg-green-50'),
                'warning': ('🟡', 'text-yellow-600', 'bg-yellow-50'),
                'critical': ('🔴', 'text-red-600', 'bg-red-50')
            },
            'hrv': {
                'good': ('💚', 'text-green-600', 'bg-green-50'),
                'warning': ('💛', 'text-yellow-600', 'bg-yellow-50'),
                'critical': ('❤️', 'text-red-600', 'bg-red-50')
            }
        }
        
        # Логика определения статуса
        if status_type == 'tsb':
            if value > 5:
                status = 'good'
            elif value > -10:
                status = 'warning'
            else:
                status = 'critical'
        elif status_type == 'hrv':
            if value > 40:
                status = 'good'
            elif value > 30:
                status = 'warning'
            else:
                status = 'critical'
        
        config = color_config.get(status_type, {}).get(status, ('⚫', 'text-gray-600', 'bg-gray-50'))
        
        # HTML карточки
        card_html = f"""
        <div class="status-card {config[2]} border-l-4 border-{config[1].split('-')[1]}-500 p-4 rounded-lg">
            <div class="flex items-center justify-between">
                <div>
                    <div class="flex items-center gap-2">
                        <span class="text-lg">{config[0]}</span>
                        <h3 class="font-semibold text-gray-800">{title}</h3>
                    </div>
                    <div class="flex items-end gap-2">
                        <span class="text-2xl font-bold {config[1]}">{value}</span>
                        {f'<span class="text-sm text-gray-500">{description}</span>' if description else ''}
                    </div>
                </div>
                {f'<div class="text-sm {config[1]}">{trend}</div>' if trend else ''}
            </div>
        </div>
        """
        
        st.markdown(card_html, unsafe_allow_html=True)
    
    @staticmethod
    def ai_recommendation_panel(recommendations):
        """Панель AI рекомендаций"""
        
        if not recommendations:
            return
        
        st.markdown("### 🤖 AI Рекомендации")
        
        for rec in recommendations:
            priority_colors = {
                'high': ('🔴', 'bg-red-50', 'border-red-200'),
                'medium': ('🟡', 'bg-yellow-50', 'border-yellow-200'),
                'low': ('🟢', 'bg-green-50', 'border-green-200')
            }
            
            color_config = priority_colors.get(rec['priority'], priority_colors['low'])
            
            st.markdown(f"""
            <div class="{color_config[1]} border {color_config[2]} rounded-lg p-4 mb-3">
                <div class="flex items-center gap-2 mb-2">
                    <span>{color_config[0]}</span>
                    <strong>{rec['title']}</strong>
                </div>
                <p class="text-sm mb-2">{rec['description']}</p>
                <div class="flex gap-2">
                    {' '.join([f'<button class="bg-blue-500 text-white px-3 py-1 rounded text-sm">{action}</button>' for action in rec['actions']])}
                </div>
            </div>
            """, unsafe_allow_html=True)
    
    @staticmethod
    def mini_chart_with_trend(data, title, color="#3B82F6"):
        """Мини-график с трендом для метрик"""
        
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            y=data,
            mode='lines',
            line=dict(color=color, width=2),
            showlegend=False
        ))
        
        fig.update_layout(
            height=80,
            margin=dict(l=0, r=0, t=20, b=0),
            xaxis=dict(showticklabels=False, showgrid=False),
            yaxis=dict(showticklabels=False, showgrid=False),
            title=dict(text=title, font=dict(size=10)),
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)'
        )
        
        return fig
```

### 3. Улучшения файла `utils/visualizations.py`

```python
# Добавить в класс Visualizations:

@staticmethod
def create_modern_dashboard_chart(activities_df, metric='tss'):
    """Современный график для дашборда с акцентом на последние данные"""
    
    if activities_df.empty:
        return go.Figure()
    
    # Подготовка данных
    activities_df['date'] = pd.to_datetime(activities_df['date'])
    daily_stats = activities_df.groupby('date')[metric].sum().reset_index()
    
    fig = go.Figure()
    
    # Основные данные
    fig.add_trace(go.Scatter(
        x=daily_stats['date'],
        y=daily_stats[metric],
        mode='lines+markers',
        name=metric.upper(),
        line=dict(color='#3B82F6', width=2),
        marker=dict(size=6, color='#3B82F6'),
        hovertemplate=f'<b>%{{x}}</b><br>{metric.upper()}: %{{y}}<extra></extra>'
    ))
    
    # Выделяем последнюю точку
    if len(daily_stats) > 0:
        last_point = daily_stats.iloc[-1]
        fig.add_trace(go.Scatter(
            x=[last_point['date']],
            y=[last_point[metric]],
            mode='markers',
            name='Сегодня',
            marker=dict(size=12, color='#EF4444', line=dict(width=2, color='white')),
            showlegend=False
        ))
    
    # Средняя линия
    avg_value = daily_stats[metric].mean()
    fig.add_hline(
        y=avg_value,
        line_dash="dash",
        line_color="#94A3B8",
        annotation_text=f"Среднее: {avg_value:.1f}"
    )
    
    fig.update_layout(
        height=250,
        margin=dict(l=0, r=0, t=30, b=0),
        xaxis=dict(showgrid=True, gridcolor='#F1F5F9'),
        yaxis=dict(showgrid=True, gridcolor='#F1F5F9'),
        plot_bgcolor='white',
        paper_bgcolor='white',
        title=None,
        showlegend=False
    )
    
    return fig

@staticmethod
def create_status_indicator_chart(current_value, baseline, thresholds):
    """Круговой индикатор статуса (как спидометр)"""
    
    # Определяем зону
    if current_value >= thresholds['excellent']:
        color = '#10B981'  # green
        zone = 'Отлично'
    elif current_value >= thresholds['good']:
        color = '#F59E0B'  # yellow
        zone = 'Хорошо'
    elif current_value >= thresholds['fair']:
        color = '#EF4444'  # red
        zone = 'Плохо'
    else:
        color = '#991B1B'  # dark red
        zone = 'Критично'
    
    fig = go.Figure(go.Indicator(
        mode = "gauge+number+delta",
        value = current_value,
        domain = {'x': [0, 1], 'y': [0, 1]},
        title = {'text': zone},
        delta = {'reference': baseline},
        gauge = {
            'axis': {'range': [None, 100]},
            'bar': {'color': color},
            'steps': [
                {'range': [0, thresholds['fair']], 'color': "#FEE2E2"},
                {'range': [thresholds['fair'], thresholds['good']], 'color': "#FEF3C7"},
                {'range': [thresholds['good'], thresholds['excellent']], 'color': "#D1FAE5"},
                {'range': [thresholds['excellent'], 100], 'color': "#A7F3D0"}
            ],
            'threshold': {
                'line': {'color': "red", 'width': 4},
                'thickness': 0.75,
                'value': baseline
            }
        }
    ))
    
    fig.update_layout(height=200, margin=dict(l=20, r=20, t=40, b=20))
    
    return fig
```

### 4. Новый файл: `utils/modern_ui.py`

```python
import streamlit as st
import plotly.graph_objects as go

class ModernUI:
    """Современные UI компоненты для AI Trainer"""
    
    @staticmethod
    def apply_modern_styles():
        """Применяет современные CSS стили"""
        st.markdown("""
        <style>
        /* Современная цветовая палитра */
        :root {
            --primary-blue: #3B82F6;
            --secondary-gray: #64748B;
            --success-green: #10B981;
            --warning-yellow: #F59E0B;
            --danger-red: #EF4444;
            --background-gray: #F8FAFC;
            --surface-white: #FFFFFF;
            --border-gray: #E2E8F0;
        }
        
        /* Убираем стандартные отступы Streamlit */
        .block-container {
            padding-top: 2rem;
            padding-bottom: 2rem;
        }
        
        /* Карточки */
        .modern-card {
            background: var(--surface-white);
            border-radius: 12px;
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
            border: 1px solid var(--border-gray);
            padding: 1.5rem;
            margin-bottom: 1rem;
            transition: all 0.2s ease;
        }
        
        .modern-card:hover {
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
            transform: translateY(-1px);
        }
        
        /* Статус-индикаторы */
        .status-excellent { border-left: 4px solid var(--success-green); }
        .status-good { border-left: 4px solid var(--warning-yellow); }
        .status-poor { border-left: 4px solid var(--danger-red); }
        .status-critical { border-left: 4px solid #991B1B; }
        
        /* Метрики с улучшенной типографикой */
        .metric-value {
            font-size: 2.5rem;
            font-weight: 700;
            line-height: 1;
            margin-bottom: 0.25rem;
        }
        
        .metric-label {
            font-size: 0.875rem;
            color: var(--secondary-gray);
            font-weight: 500;
        }
        
        .metric-trend {
            font-size: 0.75rem;
            font-weight: 600;
        }
        
        /* AI панель */
        .ai-panel {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            border-radius: 16px;
            padding: 2rem;
            color: white;
            margin: 1.5rem 0;
        }
        
        .ai-recommendation {
            background: rgba(255, 255, 255, 0.1);
            border-radius: 8px;
            padding: 1rem;
            margin: 0.5rem 0;
            backdrop-filter: blur(10px);
        }
        
        /* Кнопки быстрых действий */
        .quick-action-btn {
            background: var(--surface-white);
            border: 2px solid var(--border-gray);
            border-radius: 8px;
            padding: 1rem;
            text-align: center;
            cursor: pointer;
            transition: all 0.2s ease;
            width: 100%;
        }
        
        .quick-action-btn:hover {
            border-color: var(--primary-blue);
            box-shadow: 0 2px 4px rgba(59, 130, 246, 0.1);
        }
        
        /* Навигация */
        .modern-nav {
            background: var(--surface-white);
            border-radius: 12px;
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
            padding: 1rem;
            margin-bottom: 2rem;
        }
        
        .nav-item {
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
            padding: 0.75rem 1rem;
            border-radius: 8px;
            font-weight: 500;
            transition: all 0.2s ease;
            cursor: pointer;
        }
        
        .nav-item.active {
            background: var(--primary-blue);
            color: white;
        }
        
        .nav-item:hover:not(.active) {
            background: var(--background-gray);
        }
        </style>
        """, unsafe_allow_html=True)
    
    @staticmethod
    def metric_card_html(title, value, status, trend=None, description=None):
        """HTML для карточки метрики"""
        
        trend_html = ""
        if trend:
            trend_color = "text-green-500" if trend > 0 else "text-red-500"
            trend_icon = "↗️" if trend > 0 else "↘️"
            trend_html = f'<div class="metric-trend {trend_color}">{trend_icon} {abs(trend):.1f}</div>'
        
        desc_html = ""
        if description:
            desc_html = f'<div class="metric-label">{description}</div>'
        
        return f"""
        <div class="modern-card status-{status}">
            <div class="metric-label">{title}</div>
            <div class="metric-value">{value}</div>
            {desc_html}
            {trend_html}
        </div>
        """
    
    @staticmethod
    def navigation_bar(sections, active_section, on_change_callback=None):
        """Горизонтальная навигация"""
        
        nav_html = '<div class="modern-nav"><div class="flex gap-1">'
        
        for section_id, section_data in sections.items():
            active_class = "active" if section_id == active_section else ""
            nav_html += f"""
            <div class="nav-item {active_class}" onclick="setActiveSection('{section_id}')">
                <span>{section_data['icon']}</span>
                <span>{section_data['title']}</span>
            </div>
            """
        
        nav_html += '</div></div>'
        
        # JavaScript для обработки кликов
        nav_html += """
        <script>
        function setActiveSection(sectionId) {
            // Streamlit callback логика
            window.parent.postMessage({
                type: 'streamlit:setActiveSection',
                section: sectionId
            }, '*');
        }
        </script>
        """
        
        st.markdown(nav_html, unsafe_allow_html=True)
```

## 🚀 План внедрения для Claude Code

### Этап 1: Подготовка инфраструктуры (1-2 часа)
1. **Создать файл `utils/modern_ui.py`** с компонентами
2. **Обновить `utils/visualizations.py`** - добавить современные графики
3. **Создать CSS файл** `static/modern_styles.css` (если нужен)

### Этап 2: Редизайн главной страницы (2-3 часа)
1. **Переписать функцию `show_dashboard()`** в `app.py`
2. **Добавить `calculate_current_status()`** - логика определения критических состояний
3. **Создать `show_ai_recommendations_panel()`** - объединенные AI рекомендации
4. **Добавить `show_quick_actions()`** - быстрые действия

### Этап 3: Улучшение навигации (1 час)
1. **Заменить `st.sidebar.radio`** на горизонтальную навигацию
2. **Группировать AI-функции** в единый раздел
3. **Добавить breadcrumbs** для ориентации

### Этап 4: Модернизация остальных страниц (3-4 часа)
1. **Обновить `show_activities()`** - карточки вместо таблиц
2. **Улучшить `show_planning()`** - интерактивные элементы
3. **Переделать `show_hrv_analysis()`** - статус-индикаторы
4. **Модернизировать `show_data_management()`** - современные формы

### Этап 5: Финальная полировка (1 час)
1. **Добавить анимации и transitions**
2. **Протестировать на разных разрешениях**
3. **Оптимизировать производительность**

## 📋 Конкретные задачи для Claude Code

### Приоритет 1 (Критические улучшения):

**Задача 1.1: Статус-панель**
```python
# Заменить текущий блок метрик в show_dashboard() на:
def show_dashboard():
    # Рассчитываем текущий статус
    status = calculate_current_status()
    
    # Отображаем критические предупреждения
    if status['critical_status']:
        st.error(f"🚨 {status['critical_status']}")
        st.info(f"💡 Рекомендация: {status['critical_action']}")
    
    # Компактные метрики с визуальными индикаторами
    cols = st.columns(4)
    
    with cols[0]:
        UIComponents.status_card("Форма (TSB)", status['tsb'], 'tsb', 
                               description="Баланс нагрузки")
    
    with cols[1]:
        UIComponents.status_card("HRV", status['hrv'], 'hrv',
                               description="Восстановление")
    
    # ... остальные метрики
```

**Задача 1.2: Объединение AI-функций**
```python
# Создать новую функцию в app.py:
def show_unified_ai_coaching():
    """Объединенный AI-коучинг интерфейс"""
    
    st.header("🤖 AI Коучинг")
    
    # Табы для разных AI-функций
    tabs = st.tabs([
        "💬 Чат с тренером", 
        "📊 Анализ состояния", 
        "📋 Недельный план",
        "🔍 Анализ тренировки",
        "❓ Объяснение метрик"
    ])
    
    with tabs[0]:
        show_ai_chat_interface()
    
    with tabs[1]:
        show_ai_status_analysis()
    
    # ... остальные табы
```

**Задача 1.3: Современные графики**
```python
# Обновить Visualizations.create_banister_chart():
@staticmethod
def create_banister_chart(dates, ctl_values, atl_values, tsb_values):
    """Модернизированный график Банистера"""
    
    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.05,
        row_heights=[0.6, 0.4],
        subplot_titles=("", "")  # Убираем стандартные заголовки
    )
    
    # CTL с заливкой
    fig.add_trace(go.Scatter(
        x=dates, y=ctl_values,
        fill='tonexty',
        mode='lines',
        name='CTL (Фитнес)',
        line=dict(color='#3B82F6', width=2),
        fillcolor='rgba(59, 130, 246, 0.1)'
    ), row=1, col=1)
    
    # ATL с заливкой
    fig.add_trace(go.Scatter(
        x=dates, y=atl_values,
        fill='tozeroy',
        mode='lines',
        name='ATL (Усталость)',
        line=dict(color='#EF4444', width=2),
        fillcolor='rgba(239, 68, 68, 0.1)'
    ), row=1, col=1)
    
    # TSB с цветовыми зонами
    for i, tsb in enumerate(tsb_values):
        color = ('#10B981' if tsb > 5 else '#F59E0B' if tsb > -10 
                else '#EF4444' if tsb > -30 else '#991B1B')
        
        fig.add_trace(go.Scatter(
            x=[dates[i]], y=[tsb],
            mode='markers',
            marker=dict(size=8, color=color),
            showlegend=False,
            hovertemplate=f'TSB: {tsb:.1f}<extra></extra>'
        ), row=2, col=1)
    
    # Зоны TSB
    fig.add_hrect(y0=5, y1=25, fillcolor="green", opacity=0.1, 
                  annotation_text="Отличная форма", row=2, col=1)
    fig.add_hrect(y0=-10, y1=5, fillcolor="yellow", opacity=0.1,
                  annotation_text="Хорошая форма", row=2, col=1)
    fig.add_hrect(y0=-30, y1=-10, fillcolor="orange", opacity=0.1,
                  annotation_text="Усталость", row=2, col=1)
    fig.add_hrect(y0=-50, y1=-30, fillcolor="red", opacity=0.1,
                  annotation_text="Переутомление", row=2, col=1)
    
    # Современное оформление
    fig.update_layout(
        height=600,
        showlegend=True,
        legend=dict(x=0, y=1, bgcolor='rgba(255,255,255,0.8)'),
        margin=dict(l=0, r=0, t=40, b=0),
        plot_bgcolor='white',
        paper_bgcolor='white'
    )
    
    return fig
```

## 🎨 Дизайн-система

### Цветовая палитра:
- **Основной синий:** `#3B82F6` (индикаторы состояния, кнопки)
- **Серый нейтральный:** `#64748B` (вторичный текст)
- **Зеленый успех:** `#10B981` (хорошие показатели)
- **Желтый предупреждение:** `#F59E0B` (средние показатели)  
- **Красный опасность:** `#EF4444` (плохие показатели)
- **Темно-красный критический:** `#991B1B` (критические состояния)

### Типографика:
- **Заголовки:** 2rem, font-weight: 700
- **Метрики:** 2.5rem, font-weight: 700
- **Основной текст:** 1rem, font-weight: 400
- **Описания:** 0.875rem, color: gray-600

### Компоненты:
- **Карточки:** border-radius: 12px, shadow: soft
- **Кнопки:** border-radius: 8px, hover-эффекты
- **Графики:** минималистичный стиль, цветовые зоны
- **Индикаторы:** круговые прогресс-бары, цветовое кодирование

## ✅ Чеклист для внедрения

### Готово к внедрению:
- [ ] Создать `utils/modern_ui.py`
- [ ] Обновить `show_dashboard()` в `app.py`
- [ ] Добавить `calculate_current_status()`
- [ ] Модернизировать `create_banister_chart()`
- [ ] Объединить AI-функции в tabs
- [ ] Добавить статус-индикаторы для метрик
- [ ] Создать AI-рекомендации панель
- [ ] Улучшить мобильную адаптивность

### Дополнительные улучшения:
- [ ] Добавить анимации переходов
- [ ] Создать темную тему
- [ ] Добавить кастомные иконки
- [ ] Внедрить Progressive Web App функции
- [ ] Оптимизировать производительность графиков

---

**💡 Совет для Claude Code:** Начните с Этапа 1 и 2 - это даст максимальный эффект с минимальными изменениями. Сосредоточьтесь на статус-панели и объединении AI-функций - это решит основные UX проблемы.