# Архив: пошаговый план модернизации AI Trainer

> Статус на 2026-06-26: исторический roadmap. Он содержит инструкции для
> старого монолитного `app.py`, абсолютные локальные пути и устаревшие
> Streamlit API. Не использовать как текущий roadmap без нового ExecPlan.

## 📋 Краткое резюме изменений

**Текущая проблема:** Функциональное, но не интуитивное приложение с разбросанной информацией
**Решение:** Современный статусно-ориентированный интерфейс с приоритизацией данных

**Ключевые улучшения:**
- 🎯 Статус-панель с критическими уведомлениями
- 🤖 Объединенный AI-коучинг интерфейс  
- ⚡ Быстрые действия на основе состояния
- 📊 Современные графики и визуализации
- 📱 Горизонтальная навигация

---

## 🎯 ЭТАП 1: Создание инфраструктуры (30 мин)

### Задача 1.1: Создать файл `utils/modern_ui.py`

```bash
# Создать новый файл в папке utils
touch /Users/gregkisel/Documents/GitHub/ai_trainer/utils/modern_ui.py
```

**Что добавить в файл:**
- Класс ModernUI с методами для современных компонентов
- CSS стили для карточек, метрик, AI-панели
- Методы для статус-карточек, мини-графиков, индикаторов

**Основная структура класса:**
```python
class ModernUI:
    @staticmethod
    def apply_modern_styles()
    @staticmethod
    def status_card(title, value, status_type, trend=None, description=None)
    @staticmethod
    def ai_recommendation_panel(recommendations)
    @staticmethod
    def mini_chart_with_trend(data, title, color="#3B82F6")
    @staticmethod
    def metric_card_html(title, value, status, trend=None, description=None)
```

### Задача 1.2: Импортировать необходимые библиотеки

В начало `app.py` добавить:
```python
from utils.modern_ui import ModernUI
import plotly.graph_objects as go
from plotly.subplots import make_subplots
```

---

## 🏠 ЭТАП 2: Модернизация главной страницы (45 мин)

### Задача 2.1: Добавить функцию `calculate_current_status()` в `app.py`

**Место добавления:** После импортов, перед функцией `show_dashboard()`

```python
def calculate_current_status():
    """Расчет текущего статуса с приоритизацией проблем"""
    
    # Получаем данные за последние 30 дней
    activities_df = st.session_state.database.get_activities(30)
    hrv_df = st.session_state.database.get_hrv_data(7)
    sleep_df = st.session_state.database.get_sleep_data(7)
    
    status = {
        'critical_status': None,
        'critical_action': None,
        'recommendations': [],
        'tsb': 0,
        'hrv': 0,
        'readiness': 0,
        'ctl': 0,
        'trends': {}
    }
    
    # Расчет TSB через модель Банистера
    if not activities_df.empty:
        banister = BanisterModel()
        
        # Безопасная подготовка данных
        tss_data = []
        dates = []
        
        for idx, row in activities_df.iterrows():
            tss_val = row['tss'] if 'tss' in row and pd.notna(row['tss']) else 0
            tss_data.append(float(tss_val))
            dates.append(row['date'])
        
        current_metrics = banister.get_current_metrics(tss_data, dates)
        status['tsb'] = current_metrics.get('tsb', 0)
        status['ctl'] = current_metrics.get('ctl', 0)
        
        # Определение критических состояний
        if status['tsb'] < -30:
            status['critical_status'] = "Критическое переутомление"
            status['critical_action'] = "Полный отдых 2-3 дня"
            status['recommendations'].append({
                'title': 'Немедленные действия',
                'description': 'Ваш организм в состоянии переутомления',
                'actions': ['День отдыха', 'Легкая прогулка', 'Массаж'],
                'priority': 'high'
            })
        elif status['tsb'] < -20:
            status['critical_status'] = "Сильная усталость"
            status['critical_action'] = "Только легкие восстановительные тренировки"
    
    # HRV анализ
    if not hrv_df.empty:
        latest_hrv = hrv_df.iloc[0]['rmssd'] if pd.notna(hrv_df.iloc[0]['rmssd']) else 0
        baseline_hrv = hrv_df['rmssd'].mean()
        status['hrv'] = latest_hrv
        
        # Тренд HRV
        if len(hrv_df) >= 3:
            recent_trend = hrv_df.head(3)['rmssd'].pct_change().mean() * 100
            status['trends']['hrv'] = recent_trend
    
    return status
```

### Задача 2.2: Заменить функцию `show_dashboard()` 

**Найти:** Старую функцию `show_dashboard()` (примерно строки 200-300)
**Заменить на:** Новую версию с статус-панелью

```python
def show_dashboard():
    """Модернизированный дашборд с фокусом на статус и действия"""
    
    # Применяем современные стили
    ModernUI.apply_modern_styles()
    
    # Рассчитываем текущий статус
    status = calculate_current_status()
    
    # БЛОК 1: Критические уведомления
    if status['critical_status']:
        st.markdown(f"""
        <div class="critical-alert">
            <h3>🚨 {status['critical_status']}</h3>
            <p>{status['critical_action']}</p>
        </div>
        """, unsafe_allow_html=True)
    
    # БЛОК 2: Ключевые метрики (только 4 важнейшие)
    st.markdown("### 📊 Текущее состояние")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        ModernUI.status_card(
            "Форма (TSB)", 
            f"{status['tsb']:.1f}", 
            "tsb", 
            trend=status['trends'].get('tsb'),
            description="Баланс нагрузки"
        )
    
    with col2:
        ModernUI.status_card(
            "HRV", 
            f"{status['hrv']:.1f} мс",
            "hrv",
            trend=status['trends'].get('hrv'),
            description="Восстановление"
        )
    
    with col3:
        ModernUI.status_card(
            "Готовность", 
            f"{status['readiness']:.0f}%",
            "readiness",
            description="Общий индекс"
        )
    
    with col4:
        ModernUI.status_card(
            "Фитнес", 
            f"{status['ctl']:.1f}",
            "ctl",
            trend=status['trends'].get('ctl'),
            description="CTL"
        )
    
    # БЛОК 3: AI-рекомендации
    show_ai_recommendations_panel(status)
    
    # БЛОК 4: Быстрые действия
    show_quick_actions(status)
    
    # БЛОК 5: Аналитика (свернутая)
    with st.expander("📈 Подробная аналитика", expanded=False):
        show_compact_analytics()
```

### Задача 2.3: Добавить функцию AI-рекомендаций

**Место:** После `show_dashboard()`

```python
def show_ai_recommendations_panel(status):
    """Панель AI рекомендаций с современным дизайном"""
    
    st.markdown("### 🤖 Персональные рекомендации")
    
    # Контейнер для AI-панели
    st.markdown("""
    <div class="ai-panel">
        <div style="display: flex; align-items: center; gap: 1rem; margin-bottom: 1.5rem;">
            <div style="width: 48px; height: 48px; background: rgba(255,255,255,0.2); 
                        border-radius: 50%; display: flex; align-items: center; 
                        justify-content: center;">
                <span style="font-size: 1.5rem;">🧠</span>
            </div>
            <div>
                <h3 style="margin: 0; color: white;">AI Тренер</h3>
                <p style="margin: 0; opacity: 0.9; font-size: 0.875rem;">
                    Анализ на основе ваших данных
                </p>
            </div>
        </div>
    """, unsafe_allow_html=True)
    
    # Отображаем рекомендации
    for rec in status['recommendations']:
        priority_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}
        
        st.markdown(f"""
        <div class="ai-recommendation">
            <div style="display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.5rem;">
                <span>{priority_emoji.get(rec['priority'], '🔵')}</span>
                <strong>{rec['title']}</strong>
            </div>
            <p style="margin: 0 0 0.75rem 0; font-size: 0.875rem;">{rec['description']}</p>
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown("</div>", unsafe_allow_html=True)
    
    # Быстрые AI-действия
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("💬 Задать вопрос AI", use_container_width=True):
            st.session_state.ai_chat_open = True
            st.rerun()
    
    with col2:
        if st.button("📋 Создать план", use_container_width=True):
            st.session_state.selected_page = "📈 Планирование"
            st.rerun()
    
    with col3:
        if st.button("🔍 Анализ метрик", use_container_width=True):
            st.session_state.show_metrics_explanation = True
            st.rerun()
```

### Задача 2.4: Добавить быстрые действия

```python
def show_quick_actions(status):
    """Контекстные быстрые действия на основе статуса"""
    
    st.markdown("### ⚡ Быстрые действия")
    
    # Определяем действия на основе статуса
    if status['critical_status']:
        actions = [
            {"title": "🛌 План восстановления", "desc": "Создать план отдыха", "action": "recovery_plan"},
            {"title": "💊 Советы по восстановлению", "desc": "Питание, сон, стресс", "action": "recovery_tips"},
            {"title": "📱 Настроить уведомления", "desc": "Напоминания об отдыхе", "action": "notifications"}
        ]
    elif status['tsb'] > 5:
        actions = [
            {"title": "🚀 Интенсивная тренировка", "desc": "Воспользоваться формой", "action": "intense_workout"},
            {"title": "🎯 FTP тест", "desc": "Проверить текущий уровень", "action": "ftp_test"},
            {"title": "📈 Увеличить нагрузку", "desc": "Прогрессия тренировок", "action": "increase_load"}
        ]
    else:
        actions = [
            {"title": "📊 Анализ тренировки", "desc": "Разобрать последнюю", "action": "analyze_workout"},
            {"title": "📅 Планирование недели", "desc": "Создать план", "action": "weekly_plan"},
            {"title": "💓 Проверить HRV", "desc": "Состояние восстановления", "action": "check_hrv"}
        ]
    
    # Отображаем действия
    cols = st.columns(len(actions))
    
    for i, action in enumerate(actions):
        with cols[i]:
            st.markdown(f"""
            <div class="quick-action-btn">
                <div style="font-size: 1.125rem; margin-bottom: 0.5rem;">{action['title']}</div>
                <div style="font-size: 0.75rem; color: #64748B;">{action['desc']}</div>
            </div>
            """, unsafe_allow_html=True)
            
            if st.button(f"Выполнить", key=f"action_{i}"):
                handle_quick_action(action['action'])

def handle_quick_action(action_type):
    """Обработка быстрых действий"""
    
    if action_type == "recovery_plan":
        st.session_state.selected_page = "📈 Планирование"
        st.session_state.planning_focus = "recovery"
    elif action_type == "intense_workout":
        st.session_state.selected_page = "📈 Планирование"
        st.session_state.planning_focus = "intensity"
    elif action_type == "analyze_workout":
        st.session_state.selected_page = "🏃‍♂️ Активности"
    elif action_type == "check_hrv":
        st.session_state.selected_page = "💓 Анализ HRV"
    
    st.rerun()
```

### Задача 2.5: Добавить компактную аналитику

```python
def show_compact_analytics():
    """Компактная аналитика для экспандера на дашборде"""
    
    activities_df = st.session_state.database.get_activities(30)
    hrv_df = st.session_state.database.get_hrv_data(14)
    
    col1, col2 = st.columns(2)
    
    with col1:
        if not activities_df.empty:
            st.markdown("**📊 Активности за месяц**")
            
            # Мини-статистика
            total_activities = len(activities_df)
            total_time = activities_df['duration_minutes'].sum() / 60
            avg_tss = activities_df['tss'].mean() if 'tss' in activities_df.columns else 0
            
            st.metric("Тренировок", total_activities)
            st.metric("Часов", f"{total_time:.1f}")
            st.metric("Средний TSS", f"{avg_tss:.0f}")
    
    with col2:
        if not hrv_df.empty:
            st.markdown("**💓 Восстановление (HRV)**")
            
            current_hrv = hrv_df.iloc[0]['rmssd']
            avg_hrv = hrv_df['rmssd'].mean()
            hrv_trend = (current_hrv - avg_hrv) / avg_hrv * 100
            
            st.metric("Текущий RMSSD", f"{current_hrv:.1f}")
            st.metric("От среднего", f"{hrv_trend:+.1f}%")
```

---

## 🤖 ЭТАП 3: Объединение AI-функций (30 мин)

### Задача 3.1: Заменить `show_ai_coaching()` на табированный интерфейс

**Найти:** Функцию `show_ai_coaching()` 
**Заменить на:**

```python
def show_ai_coaching():
    """Объединенный интерфейс AI-коучинга"""
    
    st.header("🤖 AI Коучинг")
    
    # Проверяем настройку AI провайдера
    if not check_ai_provider_configured():
        st.warning("⚙️ Настройте AI провайдера в боковой панели")
        return
    
    # Табы для разных AI-функций (вместо отдельных страниц)
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "💬 AI Чат", 
        "📊 Анализ состояния", 
        "📋 Недельный план",
        "🔍 Анализ тренировки",
        "❓ Объяснение метрик"
    ])
    
    with tab1:
        show_ai_chat_interface()
    
    with tab2:
        show_ai_status_analysis()
    
    with tab3:
        show_ai_weekly_planning()
    
    with tab4:
        show_ai_workout_analysis()
    
    with tab5:
        show_ai_metrics_explanation()
```

### Задача 3.2: Улучшить AI чат интерфейс

```python
def show_ai_chat_interface():
    """Улучшенный интерфейс чата с AI"""
    
    # Контекстные быстрые вопросы
    st.markdown("#### 💡 Быстрые вопросы:")
    
    quick_questions = [
        "Как мое восстановление?",
        "Стоит ли тренироваться сегодня?", 
        "Что показывает мой HRV?",
        "Как улучшить форму?",
        "План на эту неделю?"
    ]
    
    # Отображаем быстрые вопросы как кнопки
    cols = st.columns(3)
    for i, question in enumerate(quick_questions):
        with cols[i % 3]:
            if st.button(f"💭 {question}", key=f"quick_q_{i}", use_container_width=True):
                st.session_state.pending_question = question
                st.rerun()
    
    st.markdown("---")
    
    # Основной интерфейс чата
    st.markdown("#### 💬 Чат с AI тренером")
    
    # Инициализируем чат
    if "ai_chat_history" not in st.session_state:
        st.session_state.ai_chat_history = []
    
    # Отображаем историю чата
    for message in st.session_state.ai_chat_history:
        if message["role"] == "user":
            st.chat_message("user").write(message["content"])
        else:
            st.chat_message("assistant").write(message["content"])
    
    # Обработка отложенного вопроса
    if "pending_question" in st.session_state:
        user_input = st.session_state.pending_question
        del st.session_state.pending_question
        process_ai_chat_message(user_input)
        st.rerun()
    
    # Поле ввода
    user_input = st.chat_input("Задайте вопрос AI тренеру...")
    if user_input:
        process_ai_chat_message(user_input)
        st.rerun()

def process_ai_chat_message(user_input):
    """Обработка сообщения для AI чата"""
    
    # Добавляем сообщение пользователя
    st.session_state.ai_chat_history.append({
        "role": "user",
        "content": user_input
    })
    
    # Получаем контекст данных
    from models.ai_data_context import AIDataContext
    context = AIDataContext.get_training_context(st.session_state.database)
    
    # Отправляем в AI
    try:
        from models.ai_coach_universal import UniversalAICoach
        ai_coach = UniversalAICoach()
        
        response = ai_coach.get_response(
            user_input, 
            context=context,
            chat_history=st.session_state.ai_chat_history[-10:]
        )
        
        st.session_state.ai_chat_history.append({
            "role": "assistant", 
            "content": response
        })
        
    except Exception as e:
        st.session_state.ai_chat_history.append({
            "role": "assistant",
            "content": f"Извините, произошла ошибка: {str(e)}"
        })
```

### Задача 3.3: Добавить вспомогательную функцию проверки AI

```python
def check_ai_provider_configured():
    """Проверка настройки AI провайдера"""
    
    from config.settings import Settings
    
    provider = st.session_state.get('ai_provider', Settings.DEFAULT_AI_PROVIDER)
    
    if provider == 'openai' and Settings.OPENAI_API_KEY:
        return True
    elif provider == 'anthropic' and Settings.ANTHROPIC_API_KEY:
        return True
    elif provider == 'google' and Settings.GOOGLE_API_KEY:
        return True
    elif provider == 'ollama':
        return True  # Локальный, не требует ключа
    
    return False
```

---

## 📊 ЭТАП 4: Модернизация визуализаций (20 мин)

### Задача 4.1: Обновить `utils/visualizations.py`

**Добавить в класс Visualizations:**

```python
@staticmethod
def create_modern_dashboard_chart(activities_df, metric='tss'):
    """Современный график для дашборда с акцентом на последние данные"""
    
    if activities_df.empty:
        return go.Figure()
    
    # Подготовка данных
    activities_df['date'] = pd.to_datetime(activities_df['date'])
    daily_stats = activities_df.groupby('date')[metric].sum().reset_index()
    
    fig = go.Figure()
    
    # Основные данные с заливкой
    fig.add_trace(go.Scatter(
        x=daily_stats['date'],
        y=daily_stats[metric],
        mode='lines+markers',
        name=metric.upper(),
        line=dict(color='#3B82F6', width=2),
        marker=dict(size=6, color='#3B82F6'),
        fill='tozeroy',
        fillcolor='rgba(59, 130, 246, 0.1)',
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
        showlegend=False,
        hovermode='x unified'
    )
    
    return fig

@staticmethod
def create_modern_banister_chart(dates, ctl_values, atl_values, tsb_values):
    """Модернизированный график модели Банистера"""
    
    from plotly.subplots import make_subplots
    
    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.08,
        row_heights=[0.65, 0.35],
        specs=[[{"secondary_y": False}], [{"secondary_y": False}]]
    )
    
    # Верхний график: CTL и ATL
    fig.add_trace(go.Scatter(
        x=dates, y=ctl_values,
        fill='tozeroy',
        mode='lines',
        name='CTL (Фитнес)',
        line=dict(color='#3B82F6', width=3),
        fillcolor='rgba(59, 130, 246, 0.15)',
        hovertemplate='<b>Фитнес (CTL)</b><br>%{x}<br>%{y:.1f}<extra></extra>'
    ), row=1, col=1)
    
    fig.add_trace(go.Scatter(
        x=dates, y=atl_values,
        fill='tozeroy',
        mode='lines',
        name='ATL (Усталость)',
        line=dict(color='#EF4444', width=3),
        fillcolor='rgba(239, 68, 68, 0.15)',
        hovertemplate='<b>Усталость (ATL)</b><br>%{x}<br>%{y:.1f}<extra></extra>'
    ), row=1, col=1)
    
    # Нижний график: TSB с цветовыми зонами
    fig.add_hrect(y0=5, y1=30, fillcolor="#10B981", opacity=0.1, 
                  annotation_text="Отличная форма", annotation_position="top right",
                  row=2, col=1)
    fig.add_hrect(y0=-10, y1=5, fillcolor="#F59E0B", opacity=0.1,
                  annotation_text="Хорошая форма", annotation_position="top right",
                  row=2, col=1)
    fig.add_hrect(y0=-30, y1=-10, fillcolor="#EF4444", opacity=0.1,
                  annotation_text="Усталость", annotation_position="top right",
                  row=2, col=1)
    fig.add_hrect(y0=-50, y1=-30, fillcolor="#991B1B", opacity=0.2,
                  annotation_text="Переутомление", annotation_position="top right",
                  row=2, col=1)
    
    # TSB линия
    fig.add_trace(go.Scatter(
        x=dates, y=tsb_values,
        mode='lines+markers',
        name='TSB (Форма)',
        line=dict(color='#8B5CF6', width=4),
        marker=dict(size=6, color='#8B5CF6', line=dict(width=1, color='white')),
        hovertemplate='<b>Форма (TSB)</b><br>%{x}<br>%{y:.1f}<extra></extra>'
    ), row=2, col=1)
    
    # Нулевая линия для TSB
    fig.add_hline(y=0, line_dash="dot", line_color="#64748B", opacity=0.7, row=2, col=1)
    
    # Современное оформление
    fig.update_layout(
        height=600,
        title={
            'text': "Модель Банистера: Анализ фитнеса и формы",
            'x': 0.5,
            'font': {'size': 20, 'family': 'Inter, Arial, sans-serif'}
        },
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="center",
            x=0.5,
            bgcolor='rgba(255,255,255,0.8)',
            bordercolor='#E2E8F0',
            borderwidth=1
        ),
        hovermode='x unified',
        plot_bgcolor='white',
        paper_bgcolor='white',
        margin=dict(l=0, r=0, t=80, b=0)
    )
    
    # Стилизация осей
    fig.update_yaxes(
        title_text="Тренировочная нагрузка", 
        row=1, col=1,
        gridcolor='#F1F5F9',
        title_font=dict(size=14)
    )
    fig.update_yaxes(
        title_text="TSB (Форма спортсмена)", 
        row=2, col=1,
        gridcolor='#F1F5F9',
        title_font=dict(size=14)
    )
    fig.update_xaxes(
        title_text="Дата", 
        row=2, col=1,
        gridcolor='#F1F5F9',
        title_font=dict(size=14)
    )
    
    return fig
```

---

## 📱 ЭТАП 5: Горизонтальная навигация (15 мин)

### Задача 5.1: Обновить функцию `main()` в `app.py`

```python
def main():
    """Обновленная главная функция с современной навигацией"""
    
    st.set_page_config(
        page_title="AI Trainer",
        page_icon="🏃‍♂️",
        layout="wide",
        initial_sidebar_state="collapsed"  # Скрываем боковую панель по умолчанию
    )
    
    # Применяем современные стили
    ModernUI.apply_modern_styles()
    
    # Инициализация состояния
    if 'garmin_client' not in st.session_state:
        st.session_state.garmin_client = GarminClient()
    if 'database' not in st.session_state:
        st.session_state.database = Database()
    if 'current_section' not in st.session_state:
        st.session_state.current_section = 'dashboard'
    
    # Горизонтальная навигация (вместо sidebar)
    if st.session_state.garmin_client.is_authenticated:
        show_horizontal_navigation()
    
    # Компактная боковая панель (только настройки)
    with st.sidebar:
        show_compact_sidebar()
    
    # Основной контент
    if st.session_state.garmin_client.is_authenticated:
        show_main_content()
    else:
        show_welcome_screen()
```

### Задача 5.2: Создать горизонтальную навигацию

```python
def show_horizontal_navigation():
    """Горизонтальная навигация в стиле современных веб-приложений"""
    
    # Определяем разделы
    sections = {
        'dashboard': {'title': 'Обзор', 'icon': '📊'},
        'activities': {'title': 'Активности', 'icon': '🏃‍♂️'},
        'planning': {'title': 'Планирование', 'icon': '📈'},
        'ai_coaching': {'title': 'AI Коучинг', 'icon': '🤖'},
        'data': {'title': 'Данные', 'icon': '⚙️'}
    }
    
    # Текущий раздел
    current = st.session_state.get('current_section', 'dashboard')
    
    # Создаем колонки для навигации
    cols = st.columns(len(sections))
    
    for i, (section_id, section_data) in enumerate(sections.items()):
        with cols[i]:
            # Стилизованная кнопка навигации
            if current == section_id:
                st.markdown(f"""
                <div style="text-align: center; padding: 10px; 
                           background: #3B82F6; color: white; 
                           border-radius: 8px; font-weight: 600;">
                    {section_data['icon']} {section_data['title']}
                </div>
                """, unsafe_allow_html=True)
            else:
                if st.button(f"{section_data['icon']} {section_data['title']}", 
                           key=f"nav_{section_id}", use_container_width=True):
                    st.session_state.current_section = section_id
                    st.rerun()

def show_main_content():
    """Отображение основного контента в зависимости от выбранного раздела"""
    
    section = st.session_state.get('current_section', 'dashboard')
    
    if section == 'dashboard':
        show_dashboard()
    elif section == 'activities':
        show_activities()
    elif section == 'planning':
        show_planning()
    elif section == 'ai_coaching':
        show_ai_coaching()
    elif section == 'data':
        show_data_management()

def show_compact_sidebar():
    """Компактная боковая панель только с настройками"""
    
    st.markdown("### ⚙️ Настройки")
    
    # Подключение к Garmin
    with st.expander("🔗 Garmin Connect"):
        show_garmin_connection()
    
    # AI настройки
    with st.expander("🤖 AI Провайдер"):
        show_ai_settings()
    
    # Синхронизация
    with st.expander("🔄 Синхронизация"):
        if st.button("🔄 Синхронизировать", use_container_width=True):
            sync_data(30)
        
        if st.button("🧪 Тестовые данные", use_container_width=True):
            add_test_phase1_data()
```

---

## ✅ ЭТАП 6: Тестирование и отладка (15 мин)

### Чеклист проверки:

1. **Запустить приложение:**
   ```bash
   cd /Users/gregkisel/Documents/GitHub/ai_trainer
   streamlit run app.py
   ```

2. **Проверить основные функции:**
   - [ ] Отображение статус-панели
   - [ ] Работа критических уведомлений при TSB < -30
   - [ ] Корректность метрик (TSB, HRV, Готовность, CTL)
   - [ ] Функционирование AI-табов
   - [ ] Быстрые действия реагируют на клики
   - [ ] Горизонтальная навигация переключает разделы
   - [ ] Адаптивность на мобильных устройствах

3. **Исправить типичные ошибки:**
   ```python
   # Проверить импорты в app.py
   from utils.modern_ui import ModernUI
   from models.banister_model import BanisterModel
   from data.data_processor_phase1 import Phase1DataProcessor
   
   # Убедиться в наличии данных
   if activities_df.empty:
       st.info("Нет данных. Синхронизируйте с Garmin или загрузите тестовые данные.")
       return
   
   # Обработка NaN значений
   status['tsb'] = current_metrics.get('tsb', 0) if not pd.isna(current_metrics.get('tsb')) else 0
   ```

4. **Протестировать с разными состояниями:**
   - Пустая база данных
   - Только активности без HRV
   - Полные данные
   - Критическое переутомление (TSB < -30)

---

## 🎨 Дополнительные улучшения (опционально)

### После основной модернизации можно добавить:

1. **Темная тема:**
   ```python
   # В ModernUI.apply_modern_styles() добавить:
   if st.session_state.get('dark_mode', False):
       st.markdown("""
       <style>
       :root {
           --surface-white: #1E293B;
           --text-primary: #F1F5F9;
           --background-gray: #0F172A;
       }
       </style>
       """, unsafe_allow_html=True)
   ```

2. **Анимации:**
   ```css
   @keyframes fadeIn {
       from { opacity: 0; transform: translateY(20px); }
       to { opacity: 1; transform: translateY(0); }
   }
   
   .modern-card {
       animation: fadeIn 0.5s ease-out;
   }
   ```

3. **Экспорт отчетов:**
   ```python
   def export_dashboard_report():
       """Экспорт дашборда в PDF"""
       from reportlab.pdfgen import canvas
       # ... логика генерации PDF ...
   ```

4. **Push-уведомления:**
   ```python
   def check_critical_status_and_notify():
       """Проверка критических состояний и отправка уведомлений"""
       if status['tsb'] < -30:
           send_notification("Критическое переутомление! Требуется отдых.")
   ```

---

## 📝 Итоговый результат

После выполнения всех этапов вы получите:

✅ **Современный интерфейс** с чистым дизайном и приоритизацией информации
✅ **Статус-ориентированный дашборд** с критическими уведомлениями и рекомендациями
✅ **Объединенный AI-коучинг** в едином интерфейсе с табами
✅ **Контекстные быстрые действия** адаптирующиеся к текущему состоянию
✅ **Улучшенную навигацию** горизонтальную и интуитивную
✅ **Современные визуализации** с цветовыми зонами и интерактивностью
✅ **Мобильную адаптивность** для использования на всех устройствах

**Время выполнения:** ~2-3 часа
**Сложность:** Средняя
**Результат:** Кардинальное улучшение UX и удобства использования

---

## 🚀 Команды для быстрого старта

```bash
# Перейти в директорию проекта
cd /Users/gregkisel/Documents/GitHub/ai_trainer

# Активировать виртуальное окружение
source ai_trainer_env/bin/activate

# Установить зависимости (если нужно)
pip install -r requirements.txt

# Запустить приложение
streamlit run app.py

# Открыть в браузере
# http://localhost:8501
```

---

## 📞 Поддержка

Если возникнут вопросы или проблемы при внедрении:

1. Проверьте логи в консоли
2. Убедитесь что все импорты корректны
3. Проверьте наличие данных в БД
4. Откатитесь к предыдущей версии через git если что-то сломалось

**Успехов в модернизации!** 🎉
