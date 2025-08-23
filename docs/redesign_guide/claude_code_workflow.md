# 🤖 CLAUDE CODE WORKFLOW GUIDE
> Пошаговое руководство для эффективной работы

## 📋 Рабочий процесс

### 1️⃣ НАЧАЛО РАБОТЫ
```bash
# 1. Открой файл с задачами
cat /Users/gregkisel/Documents/GitHub/ai_trainer/docs/redesign_guide/claude_code_tasks.md

# 2. Найди первую задачу в TODO

# 3. Обнови статус на IN PROGRESS
```

### 2️⃣ ВЫПОЛНЕНИЕ ЗАДАЧИ
```bash
# 1. Прочитай детали задачи
# 2. Открой нужные файлы
# 3. Внеси изменения
# 4. Проверь на ошибки
# 5. Протестируй если возможно
```

### 3️⃣ ЗАВЕРШЕНИЕ
```bash
# 1. Обнови claude_code_tasks.md
# 2. Перемести задачу в DONE
# 3. Добавь что именно сделано
# 4. Запиши в лог
```

---

## 🎯 ТЕКУЩАЯ ЗАДАЧА #1: Объединение AI функций

### Детальные шаги:

#### Шаг 1: Анализ текущего кода
```python
# Найти в app.py:
- show_ai_coaching()
- show_ai_chat() 
- show_ai_analysis()
- show_ai_weekly_plan()
- show_ai_workout_analysis()
- show_ai_metrics_explanation()
```

#### Шаг 2: Создать единую функцию
```python
def show_ai_coaching():
    """Объединенный интерфейс AI-коучинга"""
    
    st.header("🤖 AI Коучинг")
    
    # Проверка настройки провайдера
    if not check_ai_provider_configured():
        st.warning("⚙️ Настройте AI провайдера в боковой панели")
        return
    
    # Создать 5 табов
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
    
    # и так далее...
```

#### Шаг 3: Улучшить AI чат
```python
def show_ai_chat_interface():
    """Улучшенный интерфейс чата с AI"""
    
    # Добавить быстрые вопросы
    st.markdown("#### 💡 Быстрые вопросы:")
    
    quick_questions = [
        "Как мое восстановление?",
        "Стоит ли тренироваться сегодня?",
        "Что показывает мой HRV?",
        "Как улучшить форму?",
        "План на эту неделю?"
    ]
    
    cols = st.columns(3)
    for i, question in enumerate(quick_questions):
        with cols[i % 3]:
            if st.button(f"💭 {question}", key=f"quick_q_{i}"):
                st.session_state.pending_question = question
                st.rerun()
```

#### Шаг 4: Тестирование
```bash
# Запустить приложение
streamlit run app.py

# Проверить:
- Все табы отображаются
- Переключение работает
- Функции внутри табов работают
```

---

## 📊 ТЕКУЩАЯ ЗАДАЧА #2: Модернизация графиков

### Детальные шаги:

#### Шаг 1: Открыть visualizations.py
```python
# Файл: utils/visualizations.py
```

#### Шаг 2: Добавить современный график дашборда
```python
@staticmethod
def create_modern_dashboard_chart(activities_df, metric='tss'):
    """Современный график для дашборда"""
    
    fig = go.Figure()
    
    # Добавить градиентную заливку
    fig.add_trace(go.Scatter(
        x=dates,
        y=values,
        fill='tozeroy',
        fillcolor='rgba(59, 130, 246, 0.1)',
        line=dict(color='#3B82F6', width=2)
    ))
    
    return fig
```

#### Шаг 3: Обновить график Банистера
```python
@staticmethod
def create_modern_banister_chart(dates, ctl, atl, tsb):
    """Модернизированный график Банистера"""
    
    # Использовать subplots
    fig = make_subplots(rows=2, cols=1)
    
    # Добавить цветовые зоны для TSB
    fig.add_hrect(y0=5, y1=30, fillcolor="#10B981", opacity=0.1)
    fig.add_hrect(y0=-10, y1=5, fillcolor="#F59E0B", opacity=0.1)
    fig.add_hrect(y0=-30, y1=-10, fillcolor="#EF4444", opacity=0.1)
    
    return fig
```

---

## 🚀 ТЕКУЩАЯ ЗАДАЧА #3: Горизонтальная навигация

### Детальные шаги:

#### Шаг 1: Обновить main()
```python
def main():
    st.set_page_config(
        page_title="AI Trainer",
        page_icon="🏃‍♂️",
        layout="wide",
        initial_sidebar_state="collapsed"  # Скрыть sidebar
    )
```

#### Шаг 2: Создать горизонтальную навигацию
```python
def show_horizontal_navigation():
    """Горизонтальная навигация"""
    
    sections = {
        'dashboard': {'title': 'Обзор', 'icon': '📊'},
        'activities': {'title': 'Активности', 'icon': '🏃‍♂️'},
        'planning': {'title': 'Планирование', 'icon': '📈'},
        'ai_coaching': {'title': 'AI Коучинг', 'icon': '🤖'},
        'data': {'title': 'Данные', 'icon': '⚙️'}
    }
    
    cols = st.columns(len(sections))
    for i, (key, value) in enumerate(sections.items()):
        with cols[i]:
            if st.button(f"{value['icon']} {value['title']}"):
                st.session_state.current_section = key
                st.rerun()
```

---

## ✅ Чеклист проверки

После выполнения каждой задачи проверь:

- [ ] Код работает без ошибок
- [ ] Визуально выглядит хорошо
- [ ] Все импорты добавлены
- [ ] Обработка ошибок есть
- [ ] Файл tasks обновлен
- [ ] Лог записан

---

## 📝 Шаблон для обновления лога

```markdown
### 2024-01-23 [время]
- ✅ DONE: [Название задачи]
  - Что сделано: [описание]
  - Файлы: [список файлов]
  - Проблемы: [если были]
  - Время: [сколько заняло]
```

---

## 🆘 Если нужна помощь

1. Перемести задачу в BLOCKED
2. Опиши проблему в tasks.md
3. Добавь сообщение об ошибке
4. Жди инструкций от Greg или Claude

---

*Используй этот файл как справочник при работе над задачами*
