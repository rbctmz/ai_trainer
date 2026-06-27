# Архив: задачи для Claude Code по модернизации AI Trainer

> Статус на 2026-06-26: исторический task list. Он инструктирует редактировать
> старые функции в `app.py`; текущая архитектура использует `ui/pages/*`,
> `ui/components/*`, `services/*` и `state/*`.

## 🎯 Цель
Модернизировать интерфейс AI Trainer, взяв лучшие UI/UX решения из AIEndurance.

## 📸 Референсы из AIEndurance
- Градиентная навигация (фиолетово-синий)
- Круговые индикаторы для метрик (RMSSD 99%, HR Rest 62%)
- Темная карточка последней тренировки
- Недельный календарь с цветовым кодированием
- Светло-голубые карточки метрик

---

## ✅ ЗАДАЧА 1: Создание modern_ui.py с стилями AIEndurance

### 📍 Путь: 
`/Users/gregkisel/Documents/GitHub/ai_trainer/utils/modern_ui.py`

### 📝 Требования:
1. Создать новый файл `modern_ui.py` в папке `utils/`
2. Реализовать класс `ModernUI` со следующими методами:
   - `apply_aiendurance_styles()` - CSS стили
   - `create_circular_indicator()` - круговые индикаторы
   - `gradient_nav_bar()` - навигация
   - `workout_card()` - карточка тренировки
   - `weekly_calendar()` - недельный календарь

### 💻 Код для реализации:
```python
import streamlit as st
import plotly.graph_objects as go
from datetime import datetime, timedelta
import pandas as pd

class ModernUI:
    """UI компоненты в стиле AIEndurance"""
    
    # Цветовая схема AIEndurance
    COLORS = {
        'primary_gradient': 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
        'surface_light': '#E8F0FF',
        'surface_dark': '#1A2B4D',
        'accent_purple': '#667eea',
        'accent_violet': '#764ba2',
        'success': '#10B981',
        'warning': '#F59E0B',
        'danger': '#EF4444'
    }
    
    @staticmethod
    def apply_aiendurance_styles():
        """Применяет стили в стиле AIEndurance"""
        # CSS код здесь
        pass
    
    @staticmethod
    def create_circular_indicator(value, max_value, title, subtitle=""):
        """Круговой индикатор как в AIEndurance"""
        # Код индикатора здесь
        pass
```

### ✔️ Критерии проверки:
- [ ] Файл создан в правильной директории
- [ ] Класс ModernUI импортируется без ошибок
- [ ] CSS стили применяются корректно
- [ ] Градиенты отображаются правильно

---

## ✅ ЗАДАЧА 2: Обновление show_dashboard() в app.py

### 📍 Путь:
`/Users/gregkisel/Documents/GitHub/ai_trainer/app.py`

### 📝 Требования:
1. Найти функцию `show_dashboard()` (примерно строки 200-300)
2. Заменить на новую версию с использованием ModernUI
3. Структура дашборда:
   - Верхний баннер с критическими уведомлениями
   - Левая колонка: карточка последней тренировки
   - Правая колонка: метрики восстановления (2x2 сетка)
   - Нижняя секция: недельный календарь

### 💻 Код для реализации:
```python
def show_dashboard():
    """Модернизированный дашборд в стиле AIEndurance"""
    
    # Импортируем новый UI
    from utils.modern_ui import ModernUI
    
    # Применяем стили
    ModernUI.apply_aiendurance_styles()
    
    # Получаем статус
    status = calculate_current_status()
    
    # Критический баннер (если нужен)
    if status.get('critical_status'):
        st.markdown(f'''
        <div style="background: linear-gradient(135deg, #EF4444, #DC2626); 
                    color: white; padding: 15px; border-radius: 20px; 
                    margin-bottom: 20px; text-align: center;">
            <strong>⚠️ {status['critical_status']}</strong> - {status['critical_action']}
        </div>
        ''', unsafe_allow_html=True)
    
    # Основная сетка (60/40)
    col_left, col_right = st.columns([3, 2])
    
    with col_left:
        show_recent_workout_card()
    
    with col_right:
        show_recovery_metrics()
    
    # Недельный календарь
    show_weekly_training_calendar()
```

### ✔️ Критерии проверки:
- [ ] Дашборд загружается без ошибок
- [ ] Стили применяются корректно
- [ ] Структура соответствует AIEndurance
- [ ] Данные отображаются правильно

---

## ✅ ЗАДАЧА 3: Создание карточки последней тренировки

### 📍 Место добавления:
В файле `app.py`, после функции `show_dashboard()`

### 📝 Требования:
1. Темный фон (градиент от #1A2B4D до #2D3E5F)
2. Белый текст
3. Метрики тренировки в сетке 2x3
4. График мощности/ЧСС
5. Кнопка "Analysis"

### 💻 Код для реализации:
```python
def show_recent_workout_card():
    """Карточка последней тренировки в стиле AIEndurance"""
    
    # Получаем последнюю активность
    activities_df = st.session_state.database.get_activities(1)
    
    if activities_df.empty:
        st.info("Нет данных о тренировках")
        return
    
    activity = activities_df.iloc[0]
    
    # HTML карточки
    st.markdown(f'''
    <div class="workout-card">
        <div style="font-size: 12px; opacity: 0.8;">Most Recent Workout</div>
        <h2 style="margin: 10px 0; color: white;">
            {activity.get('name', 'Тренировка')}
        </h2>
        
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 15px; 
                    margin: 20px 0; color: white;">
            <div>
                <span style="opacity: 0.7;">Start Time:</span><br>
                <strong>{activity['date']}</strong>
            </div>
            <div>
                <span style="opacity: 0.7;">Distance:</span><br>
                <strong>{activity['distance_km']:.1f} km</strong>
            </div>
            <div>
                <span style="opacity: 0.7;">Time:</span><br>
                <strong>{activity['duration_minutes']:.0f} min</strong>
            </div>
            <div>
                <span style="opacity: 0.7;">Avg Power:</span><br>
                <strong>{activity.get('avg_power', 0):.0f} W</strong>
            </div>
            <div>
                <span style="opacity: 0.7;">Elevation:</span><br>
                <strong>{activity.get('elevation_gain', 0):.0f} m</strong>
            </div>
            <div>
                <span style="opacity: 0.7;">TSS:</span><br>
                <strong>{activity.get('tss', 0):.0f}</strong>
            </div>
        </div>
    </div>
    ''', unsafe_allow_html=True)
    
    # График (если есть данные)
    if st.button("📊 Analysis", key="workout_analysis"):
        st.session_state.selected_page = "🏃‍♂️ Активности"
        st.rerun()
```

### ✔️ Критерии проверки:
- [ ] Карточка отображается с темным фоном
- [ ] Все метрики видны и читаемы
- [ ] Кнопка Analysis работает
- [ ] Адаптивность на мобильных

---

## ✅ ЗАДАЧА 4: Метрики восстановления с круговыми индикаторами

### 📍 Место добавления:
В файле `app.py`, после `show_recent_workout_card()`

### 📝 Требования:
1. Сетка 2x2 для 4 метрик
2. Круговые индикаторы для RMSSD и HR Rest
3. Простые карточки для DFA a1 и ESS
4. Цвета: фиолетовый для хороших значений, оранжевый для средних

### 💻 Код для реализации:
```python
def show_recovery_metrics():
    """Метрики восстановления в стиле AIEndurance"""
    
    from utils.modern_ui import ModernUI
    
    # Заголовок
    st.markdown('''
    <div style="text-align: center; padding: 15px; 
               background: linear-gradient(135deg, #E8F0FF, #F0E8FF);
               border-radius: 15px; margin-bottom: 20px;">
        Connect your heart rate data to see your recovery
    </div>
    ''', unsafe_allow_html=True)
    
    # Получаем данные HRV
    hrv_df = st.session_state.database.get_hrv_data(7)
    
    # Сетка 2x2
    col1, col2 = st.columns(2)
    
    with col1:
        # DFA a1
        st.markdown('''
        <div class="ai-card" style="height: 200px; text-align: center;">
            <div style="display: flex; justify-content: space-between; margin-bottom: 10px;">
                <span>DFA a₁</span>
                <span>ℹ️</span>
            </div>
            <div class="metric-value" style="margin-top: 30px;">N/A</div>
        </div>
        ''', unsafe_allow_html=True)
    
    with col2:
        # RMSSD
        if not hrv_df.empty:
            rmssd = hrv_df.iloc[0].get('rmssd', 0)
            fig = ModernUI.create_circular_indicator(
                rmssd, 50, "RMSSD", f"{rmssd:.0f} ms", "#667eea"
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Нет данных HRV")
    
    # Второй ряд
    col3, col4 = st.columns(2)
    
    with col3:
        # HR Rest
        hr_rest = 60  # Заглушка, нужно получить реальные данные
        fig = ModernUI.create_circular_indicator(
            hr_rest, 100, "HR Rest", f"{hr_rest} bpm", "#F59E0B"
        )
        st.plotly_chart(fig, use_container_width=True)
    
    with col4:
        # ESS последней тренировки
        activities_df = st.session_state.database.get_activities(1)
        ess = activities_df.iloc[0].get('training_load', 0) if not activities_df.empty else 0
        
        st.markdown(f'''
        <div class="ai-card" style="height: 200px; text-align: center;">
            <div>ESS on {datetime.now().strftime("%b %d, %Y")}</div>
            <div class="metric-value" style="margin-top: 30px;">{ess:.0f}</div>
        </div>
        ''', unsafe_allow_html=True)
```

### ✔️ Критерии проверки:
- [ ] Все 4 метрики отображаются
- [ ] Круговые индикаторы работают
- [ ] Цвета соответствуют значениям
- [ ] Подсказки (ℹ️) видны

---

## ✅ ЗАДАЧА 5: Недельный календарь тренировок

### 📍 Место добавления:
В файле `app.py`, после `show_recovery_metrics()`

### 📝 Требования:
1. 7 колонок для дней недели
2. Цветовое кодирование по типу активности
3. Показ дистанции и времени
4. Выделение сегодняшнего дня

### 💻 Код для реализации:
```python
def show_weekly_training_calendar():
    """Недельный календарь в стиле AIEndurance"""
    
    st.markdown("### This Week's Training")
    
    # Получаем активности за неделю
    activities_df = st.session_state.database.get_activities(7)
    
    # Дни недели
    days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
    today = datetime.now().weekday()
    
    # Цвета для разных видов спорта
    sport_colors = {
        'cycling': '#E8F0FF',
        'running': '#F0E8FF',
        'swimming': '#FFE8E8',
        'other': '#FFF8E8'
    }
    
    cols = st.columns(7)
    
    for i, day in enumerate(days):
        with cols[i]:
            # Проверяем, есть ли тренировка в этот день
            day_activities = get_activities_for_weekday(activities_df, i)
            
            if day_activities:
                activity = day_activities.iloc[0]
                sport = activity.get('sport', 'other').lower()
                color = sport_colors.get(sport, '#E8F0FF')
                
                # Карточка с тренировкой
                st.markdown(f'''
                <div class="calendar-day" style="background: {color}; 
                     border: 2px solid {'#667eea' if i == today else 'transparent'};">
                    <div style="text-align: center; font-weight: bold; margin-bottom: 10px;">
                        {day}
                    </div>
                    <div style="font-size: 12px;">
                        <span style="color: green;">✓</span> {sport.title()}<br>
                        {activity['distance_km']:.1f} km<br>
                        {activity['duration_minutes']:.0f} min
                    </div>
                </div>
                ''', unsafe_allow_html=True)
            else:
                # Пустой день
                st.markdown(f'''
                <div class="calendar-day calendar-day-empty" 
                     style="border: 2px solid {'#667eea' if i == today else 'transparent'};">
                    <div style="text-align: center; color: white; font-weight: bold;">
                        {day}
                    </div>
                </div>
                ''', unsafe_allow_html=True)
```

### ✔️ Критерии проверки:
- [ ] Календарь отображает 7 дней
- [ ] Цветовое кодирование работает
- [ ] Сегодняшний день выделен
- [ ] Данные тренировок видны

---

## ✅ ЗАДАЧА 6: Градиентная навигация

### 📍 Место обновления:
В файле `app.py`, функция `main()`

### 📝 Требования:
1. Горизонтальная навигация вместо sidebar
2. Градиентный фон (фиолетово-синий)
3. Активная вкладка подсвечена
4. Профиль пользователя справа

### 💻 Код для реализации:
```python
def show_horizontal_navigation():
    """Горизонтальная навигация в стиле AIEndurance"""
    
    sections = {
        'dashboard': {'title': 'Dashboard', 'icon': '📊'},
        'calendar': {'title': 'Calendar', 'icon': '📅'},
        'activities': {'title': 'Activities', 'icon': '🏃‍♂️'},
        'recovery': {'title': 'Recovery', 'icon': '💓'},
        'planning': {'title': 'Plan', 'icon': '📈'},
        'data': {'title': 'Data', 'icon': '📁'},
        'chat': {'title': 'Chat', 'icon': '💬'}
    }
    
    current = st.session_state.get('current_section', 'dashboard')
    
    # HTML навигации
    nav_items = []
    for key, section in sections.items():
        active = 'active' if key == current else ''
        nav_items.append(f'''
            <a href="#" class="nav-item {active}" onclick="return false;">
                {section['icon']} {section['title']}
            </a>
        ''')
    
    st.markdown(f'''
    <div class="nav-bar">
        <div style="display: flex; justify-content: space-between; align-items: center;">
            <div style="display: flex; gap: 20px;">
                {''.join(nav_items)}
            </div>
            <div style="display: flex; gap: 15px; align-items: center; color: white;">
                <span>🔔</span>
                <div style="width: 35px; height: 35px; border-radius: 50%; 
                           background: white; display: flex; align-items: center; 
                           justify-content: center; color: #667eea; font-weight: bold;">
                    {st.session_state.get('user_initials', 'AI')}
                </div>
            </div>
        </div>
    </div>
    ''', unsafe_allow_html=True)
    
    # Fallback кнопки Streamlit
    cols = st.columns(len(sections))
    for i, (key, section) in enumerate(sections.items()):
        with cols[i]:
            if st.button(f"{section['icon']}", key=f"nav_{key}", help=section['title']):
                st.session_state.current_section = key
                st.rerun()
```

### ✔️ Критерии проверки:
- [ ] Навигация отображается горизонтально
- [ ] Градиент применен
- [ ] Переключение разделов работает
- [ ] Профиль виден справа

---

## 🧪 ТЕСТИРОВАНИЕ

### Запуск приложения:
```bash
cd /Users/gregkisel/Documents/GitHub/ai_trainer
streamlit run app.py
```

### Чек-лист проверки:
1. **Визуальное соответствие AIEndurance:**
   - [ ] Градиентная навигация
   - [ ] Круговые индикаторы
   - [ ] Темная карточка тренировки
   - [ ] Светлые карточки метрик
   - [ ] Недельный календарь

2. **Функциональность:**
   - [ ] Данные загружаются корректно
   - [ ] Навигация работает
   - [ ] Графики отображаются
   - [ ] Кнопки реагируют

3. **Адаптивность:**
   - [ ] Корректно на десктопе (1920x1080)
   - [ ] Корректно на планшете (768px)
   - [ ] Корректно на мобильном (375px)

4. **Производительность:**
   - [ ] Страница загружается < 3 сек
   - [ ] Переключение вкладок < 1 сек
   - [ ] Графики рендерятся плавно

---

## 📊 МЕТРИКИ УСПЕХА

- ✅ Все 6 задач выполнены
- ✅ Визуальное соответствие AIEndurance > 80%
- ✅ Нет критических ошибок
- ✅ Улучшение UX подтверждено

---

## 🔄 СЛЕДУЮЩИЕ ШАГИ

После выполнения всех задач:
1. Сделать скриншоты нового интерфейса
2. Сравнить с AIEndurance
3. Собрать фидбек
4. Итерировать дизайн

---

## 📝 ПРИМЕЧАНИЯ

- Используем Streamlit компоненты где возможно
- CSS встраиваем через st.markdown
- Plotly для круговых индикаторов
- Градиенты через linear-gradient CSS

---

**Автор:** AI Assistant  
**Дата:** 2024-12-22  
**Версия:** 1.0
