# Архив: техническое предложение Phase 1 расширения данных

> Статус на 2026-06-26: историческое предложение. Текущая реализация уже
> разнесена по `services/sync.py`, `data/data_processor_phase1.py`,
> `data/database.py` и `ui/pages/*`; инструкции ниже про изменения в `app.py`
> не соответствуют текущей архитектуре.

## 🎯 Цель фазы 1
Добавить 4 критически важных типа данных для существенного улучшения качества анализа тренировок и восстановления.

## 📋 Что будет добавлено

### 1. 😴 Данные сна
**Зачем:** Качество сна - главный фактор восстановления  
**Метрики:**
- Общее время сна
- Глубокий/лёгкий/REM сон
- Качество сна (индекс)
- Количество пробуждений

### 2. 🫀 Пульс покоя  
**Зачем:** Ранний индикатор перетренированности  
**Метрики:**
- Ежедневный пульс покоя
- 7-дневное скользящее среднее
- Отклонения от нормы

### 3. 🎯 Статус тренированности Garmin
**Зачем:** Готовые алгоритмы от профессионалов  
**Метрики:**
- VO2 max
- Фитнес-возраст
- Статус тренированности
- Готовность к тренировке

### 4. 📱 Ежедневная активность
**Зачем:** Контекст общей нагрузки вне тренировок  
**Метрики:**
- Шаги, калории, активные минуты
- Подъёмы по лестнице
- Общая дневная активность

## 🗄️ Изменения в базе данных

### Новые таблицы
```sql
-- Данные сна
CREATE TABLE sleep_data (
    date DATE PRIMARY KEY,
    total_sleep_minutes INTEGER,
    deep_sleep_minutes INTEGER,
    light_sleep_minutes INTEGER,
    rem_sleep_minutes INTEGER,
    awakenings_count INTEGER,
    sleep_score REAL,
    bedtime TEXT,
    wakeup_time TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Ежедневные показатели здоровья
CREATE TABLE daily_health (
    date DATE PRIMARY KEY,
    resting_hr INTEGER,
    steps INTEGER,
    floors_climbed INTEGER,
    calories_active INTEGER,
    calories_bmr INTEGER,
    distance_meters INTEGER,
    active_minutes INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Статус тренированности
CREATE TABLE training_status (
    date DATE PRIMARY KEY,
    vo2_max REAL,
    fitness_age INTEGER,
    training_load_7d REAL,
    training_status TEXT,
    training_readiness REAL,
    recovery_time_hours INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## 🔧 Обновления кода

### 1. Расширение GarminClient
```python
# Новые методы в data/garmin_client.py

def get_sleep_data(self, date):
    """Получение данных сна за конкретную ночь"""
    if not self.is_authenticated:
        return None
    try:
        return self.client.get_sleep_data(date.strftime("%Y-%m-%d"))
    except Exception:
        return None

def get_resting_heart_rate(self, date):
    """Пульс покоя за день"""
    if not self.is_authenticated:
        return None
    try:
        return self.client.get_resting_heart_rate(date.strftime("%Y-%m-%d"))
    except Exception:
        return None

def get_daily_steps(self, date):
    """Шаги и общая активность за день"""
    if not self.is_authenticated:
        return None
    try:
        return self.client.get_steps_data(date.strftime("%Y-%m-%d"))
    except Exception:
        return None

def get_training_status(self):
    """Текущий статус тренированности"""
    if not self.is_authenticated:
        return None
    try:
        return self.client.get_training_status()
    except Exception:
        return None

def get_vo2_max(self):
    """Текущий VO2 max"""
    if not self.is_authenticated:
        return None
    try:
        return self.client.get_vo2_max()
    except Exception:
        return None
```

### 2. Обновление Database класса
```python
# Новые методы в data/database.py

def sync_sleep_data(self, sleep_data):
    """Синхронизация данных сна"""
    # Аналогично HRV - умная синхронизация без дублей
    
def sync_daily_health(self, health_data):
    """Синхронизация ежедневных показателей здоровья"""
    
def sync_training_status(self, status_data):
    """Синхронизация статуса тренированности"""

def get_sleep_data(self, days=30):
    """Получение данных сна за период"""
    
def get_daily_health(self, days=30):
    """Получение ежедневных показателей"""
    
def get_training_status_history(self, days=90):
    """История статуса тренированности"""
```

### 3. Обновление процесса синхронизации
```python
# Изменения в app.py - функция sync_data()

def sync_data(days=30):
    # ... существующий код ...
    
    # Добавляем новые типы данных
    progress_bar.progress(75)
    status_text.text("Загрузка данных сна...")
    
    sleep_data = {}
    daily_health_data = {}
    training_status_data = {}
    
    for date in date_list:
        # Данные сна
        sleep_info = st.session_state.garmin_client.get_sleep_data(date)
        if sleep_info:
            sleep_data[date.strftime('%Y-%m-%d')] = process_sleep_data(sleep_info)
        
        # Ежедневные показатели
        daily_info = st.session_state.garmin_client.get_daily_steps(date)
        resting_hr = st.session_state.garmin_client.get_resting_heart_rate(date)
        
        if daily_info or resting_hr:
            daily_health_data[date.strftime('%Y-%m-%d')] = {
                'steps': daily_info.get('steps') if daily_info else None,
                'calories': daily_info.get('calories') if daily_info else None,
                'resting_hr': resting_hr,
                # ... другие метрики
            }
    
    # Статус тренированности (один раз)
    training_status = st.session_state.garmin_client.get_training_status()
    if training_status:
        training_status_data[datetime.now().strftime('%Y-%m-%d')] = training_status
    
    # Сохранение новых данных
    progress_bar.progress(90)
    status_text.text("Сохранение расширенных данных...")
    
    if sleep_data:
        st.session_state.database.sync_sleep_data(sleep_data)
    if daily_health_data:
        st.session_state.database.sync_daily_health(daily_health_data)
    if training_status_data:
        st.session_state.database.sync_training_status(training_status_data)
```

## 📊 Новые разделы интерфейса

### 1. Страница "🛌 Анализ сна"
```python
def show_sleep_analysis():
    st.header("🛌 Анализ сна и восстановления")
    
    # Текущее состояние сна
    st.subheader("😴 Последняя ночь")
    # Метрики качества сна
    
    # График динамики сна
    st.subheader("📈 Динамика сна")
    # Тренды качества сна
    
    # Корреляция сон-тренировки
    st.subheader("🔗 Влияние сна на тренировки")
    # Анализ зависимостей
```

### 2. Обновление дашборда
```python
def show_dashboard():
    # ... существующий код ...
    
    # Добавляем новые метрики
    col1, col2, col3, col4, col5 = st.columns(5)
    
    with col4:
        # Качество сна за последнюю ночь
        sleep_score = get_latest_sleep_score()
        st.metric("Качество сна", f"{sleep_score}%")
    
    with col5:
        # Пульс покоя
        resting_hr = get_latest_resting_hr()
        baseline_hr = get_baseline_resting_hr()
        delta = resting_hr - baseline_hr if baseline_hr else 0
        st.metric("Пульс покоя", f"{resting_hr} уд/мин", f"{delta:+d}")
```

### 3. Интегральный индекс готовности
```python
def calculate_readiness_index():
    """Комплексный индекс готовности к тренировке"""
    factors = {
        'hrv': get_latest_hrv_score(),           # 25%
        'sleep': get_latest_sleep_score(),       # 25% 
        'resting_hr': get_resting_hr_score(),    # 20%
        'stress': get_stress_score(),            # 15%
        'body_battery': get_body_battery(),      # 15%
    }
    
    # Взвешенная сумма
    readiness = sum(score * weight for score, weight in factors.items())
    return min(100, max(0, readiness))

def show_readiness_widget():
    """Виджет готовности к тренировке"""
    readiness = calculate_readiness_index()
    
    if readiness >= 80:
        color, emoji, recommendation = "🟢", "💪", "Отличная готовность к интенсивной тренировке"
    elif readiness >= 60:
        color, emoji, recommendation = "🟡", "🚶", "Умеренная нагрузка рекомендуется"
    else:
        color, emoji, recommendation = "🔴", "😴", "Сосредоточьтесь на восстановлении"
    
    st.metric(
        "Готовность к тренировке", 
        f"{emoji} {readiness}%",
        help=recommendation
    )
```

## 🧪 План тестирования

### 1. Модульные тесты
```python
# tests/test_phase1_expansion.py

def test_sleep_data_sync():
    """Тест синхронизации данных сна"""
    
def test_daily_health_sync():
    """Тест синхронизации ежедневных показателей"""
    
def test_readiness_calculation():
    """Тест расчёта индекса готовности"""
    
def test_new_ui_components():
    """Тест новых компонентов интерфейса"""
```

### 2. Интеграционные тесты
```python
def test_full_sync_with_new_data():
    """Тест полной синхронизации с новыми типами данных"""
    
def test_performance_with_extended_data():
    """Тест производительности с расширенными данными"""
```

## 📅 План реализации

### Неделя 1: Базовая инфраструктура
- [ ] Создание новых таблиц БД
- [ ] Расширение GarminClient новыми методами
- [ ] Обновление процесса синхронизации

### Неделя 2: Интерфейс и анализ
- [ ] Новая страница анализа сна
- [ ] Обновление дашборда
- [ ] Интегральный индекс готовности

### Неделя 3: Тестирование и оптимизация
- [ ] Модульные тесты
- [ ] Интеграционные тесты
- [ ] Оптимизация производительности

### Неделя 4: Документация и релиз
- [ ] Обновление документации
- [ ] Создание migration скриптов
- [ ] Релиз фазы 1

## 🎯 Ожидаемые результаты

### Количественные улучшения
- ⬆️ **Точность рекомендаций: +35%** (больше факторов)
- ⬇️ **Ложные тревоги: -50%** (комплексный анализ)
- ⬆️ **Полнота анализа: +60%** (круглосуточный мониторинг)

### Качественные улучшения
- 🎯 **Персонализация:** Индивидуальные модели восстановления
- 🔮 **Предиктивность:** Прогноз готовности на основе сна
- 🧠 **Интеллект:** Многофакторный анализ состояния
- 📱 **UX:** Более информативные и полезные рекомендации

## 💡 Следующие шаги

После успешной реализации фазы 1:
1. **Сбор обратной связи** от пользователей
2. **Анализ эффективности** новых метрик
3. **Планирование фазы 2** (SpO2, дыхание, расширенные метрики)
4. **ML-модели** на основе богатых данных

Фаза 1 заложит solid foundation для превращения приложения в профессиональный инструмент спортивного анализа! 🚀
