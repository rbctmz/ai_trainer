# План разработки персонального AI тренера с Garmin Connect

## 🎯 Цель проекта
Создать базовую версию персонального AI тренера на Python + Streamlit с интеграцией Garmin Connect, реализующую основные функции AI Endurance для личного использования.

## 📋 Этапы разработки

### Этап 1: Настройка окружения и базовая структура (1-2 недели)

#### 1.1 Установка и настройка
```bash
# Создание виртуального окружения
python -m venv ai_trainer_env
source ai_trainer_env/bin/activate  # Linux/Mac
# ai_trainer_env\Scripts\activate  # Windows

# Установка зависимостей
pip install streamlit pandas numpy scipy plotly
pip install garminconnect python-fitparse pyhrv
pip install scikit-learn openai python-dotenv
pip install sqlalchemy sqlite3
```

#### 1.2 Структура проекта
```
ai_trainer/
├── app.py                 # Главное Streamlit приложение
├── config/
│   ├── __init__.py
│   └── settings.py        # Настройки и константы
├── data/
│   ├── __init__.py
│   ├── garmin_client.py   # Клиент для Garmin Connect
│   ├── data_processor.py  # Обработка данных активностей
│   └── database.py        # Работа с БД
├── models/
│   ├── __init__.py
│   ├── banister.py        # Модель Банистера
│   ├── hrv_analyzer.py    # Анализ HRV
│   └── ai_coach.py        # AI рекомендации
├── utils/
│   ├── __init__.py
│   ├── metrics.py         # Расчёт метрик (TSS, NP, etc.)
│   └── visualizations.py  # Функции для графиков
├── requirements.txt
├── .env                   # Переменные окружения
└── README.md
```

#### 1.3 Базовое Streamlit приложение
```python
# app.py
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta

st.set_page_config(
    page_title="AI Trainer",
    page_icon="🏃‍♂️",
    layout="wide"
)

st.title("🏃‍♂️ Персональный AI Тренер")
st.sidebar.title("Навигация")

# Основные разделы
page = st.sidebar.selectbox("Выберите раздел:", [
    "Дашборд", "Активности", "Анализ HRV", 
    "Планирование", "AI Коучинг"
])

if page == "Дашборд":
    st.header("Дашборд тренировок")
    # Основные метрики и графики
    
elif page == "Активности":
    st.header("Ваши активности")
    # Таблица и детали активностей
    
# ... остальные разделы
```

### Этап 2: Интеграция с Garmin Connect (2-3 недели)

#### 2.1 Настройка Garmin Connect API
```python
# data/garmin_client.py
from garminconnect import Garmin
import os
from datetime import datetime, timedelta
import pandas as pd

class GarminClient:
    def __init__(self):
        self.client = None
        self.is_authenticated = False
    
    def authenticate(self, email, password):
        """Аутентификация в Garmin Connect"""
        try:
            self.client = Garmin(email, password)
            self.client.login()
            self.is_authenticated = True
            return True
        except Exception as e:
            st.error(f"Ошибка аутентификации: {e}")
            return False
    
    def get_activities(self, start_date, end_date, limit=100):
        """Получение активностей за период"""
        if not self.is_authenticated:
            return None
        
        activities = self.client.get_activities_by_date(
            start_date.strftime("%Y-%m-%d"),
            end_date.strftime("%Y-%m-%d"),
            activitytype=None
        )
        return activities[:limit]
    
    def get_activity_details(self, activity_id):
        """Детальная информация об активности"""
        return self.client.get_activity_by_id(activity_id)
    
    def get_hrv_data(self, date):
        """Получение HRV данных за день"""
        try:
            return self.client.get_hrv_data(date.strftime("%Y-%m-%d"))
        except:
            return None
    
    def get_sleep_data(self, date):
        """Данные сна"""
        try:
            return self.client.get_sleep_data(date.strftime("%Y-%m-%d"))
        except:
            return None
```

#### 2.2 Обработка данных активностей
```python
# data/data_processor.py
import pandas as pd
import numpy as np
from datetime import datetime

class ActivityProcessor:
    
    @staticmethod
    def process_activities(activities_data):
        """Преобразование данных активностей в DataFrame"""
        processed = []
        
        for activity in activities_data:
            processed.append({
                'activity_id': activity['activityId'],
                'date': datetime.strptime(activity['startTimeLocal'][:10], '%Y-%m-%d'),
                'sport': activity.get('activityType', {}).get('typeKey', 'unknown'),
                'duration_minutes': activity.get('duration', 0) / 60,
                'distance_km': activity.get('distance', 0) / 1000,
                'avg_hr': activity.get('averageHR'),
                'max_hr': activity.get('maxHR'),
                'avg_power': activity.get('avgPower'),
                'max_power': activity.get('maxPower'),
                'elevation_gain': activity.get('elevationGain'),
                'calories': activity.get('calories'),
                'training_effect': activity.get('aerobicTrainingEffect'),
                'anaerobic_effect': activity.get('anaerobicTrainingEffect')
            })
        
        return pd.DataFrame(processed)
    
    @staticmethod
    def calculate_tss(activity_data, ftp=None, lthr=None):
        """Расчёт Training Stress Score"""
        if ftp and activity_data.get('avg_power'):
            # TSS на основе мощности
            duration_hours = activity_data['duration_minutes'] / 60
            intensity_factor = activity_data['avg_power'] / ftp
            tss = duration_hours * intensity_factor ** 2 * 100
            return round(tss, 1)
        
        elif lthr and activity_data.get('avg_hr'):
            # hrTSS на основе пульса
            duration_hours = activity_data['duration_minutes'] / 60
            intensity_factor = activity_data['avg_hr'] / lthr
            hrTSS = duration_hours * intensity_factor ** 2 * 100
            return round(hrTSS, 1)
        
        return None
```

#### 2.3 База данных для кеширования
```python
# data/database.py
import sqlite3
import pandas as pd
from datetime import datetime

class Database:
    def __init__(self, db_path="ai_trainer.db"):
        self.db_path = db_path
        self.init_tables()
    
    def init_tables(self):
        """Создание таблиц"""
        conn = sqlite3.connect(self.db_path)
        
        # Таблица активностей
        conn.execute('''
            CREATE TABLE IF NOT EXISTS activities (
                activity_id TEXT PRIMARY KEY,
                date DATE,
                sport TEXT,
                duration_minutes REAL,
                distance_km REAL,
                avg_hr INTEGER,
                max_hr INTEGER,
                avg_power INTEGER,
                max_power INTEGER,
                elevation_gain REAL,
                calories INTEGER,
                tss REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Таблица HRV данных
        conn.execute('''
            CREATE TABLE IF NOT EXISTS hrv_data (
                date DATE PRIMARY KEY,
                rmssd REAL,
                stress_score REAL,
                recovery_score REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Таблица настроек пользователя
        conn.execute('''
            CREATE TABLE IF NOT EXISTS user_settings (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def save_activities(self, activities_df):
        """Сохранение активностей"""
        conn = sqlite3.connect(self.db_path)
        activities_df.to_sql('activities', conn, if_exists='replace', index=False)
        conn.close()
    
    def get_activities(self, days=30):
        """Получение активностей из БД"""
        conn = sqlite3.connect(self.db_path)
        query = f'''
            SELECT * FROM activities 
            WHERE date >= date('now', '-{days} days')
            ORDER BY date DESC
        '''
        df = pd.read_sql_query(query, conn)
        conn.close()
        return df
```

### Этап 3: Реализация модели Банистера (2-3 недели)

#### 3.1 Базовая модель Банистера
```python
# models/banister.py
import numpy as np
import pandas as pd
from scipy.optimize import minimize
from datetime import datetime, timedelta

class BanisterModel:
    def __init__(self):
        self.k1 = 1.0      # Фитнес константа
        self.k2 = 2.0      # Усталость константа  
        self.tau1 = 42.0   # Время спада фитнеса (дни)
        self.tau2 = 7.0    # Время спада усталости (дни)
        self.is_fitted = False
    
    def exponential_average(self, training_load, tau):
        """Экспоненциальное скользящее среднее"""
        alpha = 1 - np.exp(-1/tau)
        result = []
        ema = 0
        
        for load in training_load:
            ema = alpha * load + (1 - alpha) * ema
            result.append(ema)
        
        return np.array(result)
    
    def predict_performance(self, training_load):
        """Предсказание производительности"""
        fitness = self.k1 * self.exponential_average(training_load, self.tau1)
        fatigue = self.k2 * self.exponential_average(training_load, self.tau2)
        performance = fitness - fatigue
        return performance, fitness, fatigue
    
    def fit(self, training_load, performance_data):
        """Подгонка параметров модели"""
        def objective(params):
            self.k1, self.k2, self.tau1, self.tau2 = params
            pred_performance, _, _ = self.predict_performance(training_load)
            return np.mean((pred_performance - performance_data) ** 2)
        
        # Начальные параметры и ограничения
        x0 = [1.0, 2.0, 42.0, 7.0]
        bounds = [(0.1, 10), (0.1, 10), (1, 100), (1, 30)]
        
        result = minimize(objective, x0, bounds=bounds, method='L-BFGS-B')
        
        if result.success:
            self.k1, self.k2, self.tau1, self.tau2 = result.x
            self.is_fitted = True
            return True
        return False
    
    def calculate_training_zones(self, recent_fitness):
        """Расчёт рекомендуемых зон тренировок"""
        current_form = recent_fitness[-1] if len(recent_fitness) > 0 else 0
        
        if current_form > 50:
            return "Высокая интенсивность"
        elif current_form > 0:
            return "Умеренная интенсивность"
        else:
            return "Восстановление"
```

#### 3.2 Калькулятор метрик
```python
# utils/metrics.py
import numpy as np
import pandas as pd

class MetricsCalculator:
    
    @staticmethod
    def normalized_power(power_data, window=30):
        """Нормализованная мощность (NP)"""
        if len(power_data) == 0:
            return 0
        
        # 30-секундные скользящие средние
        rolling_avg = pd.Series(power_data).rolling(window).mean()
        # 4-я степень средних
        fourth_power = rolling_avg ** 4
        # Среднее и корень 4-й степени
        np_value = fourth_power.mean() ** 0.25
        return np_value
    
    @staticmethod
    def intensity_factor(normalized_power, ftp):
        """Фактор интенсивности"""
        if ftp > 0:
            return normalized_power / ftp
        return 0
    
    @staticmethod
    def training_stress_score(normalized_power, duration_seconds, ftp):
        """Training Stress Score"""
        if ftp > 0:
            intensity_factor = normalized_power / ftp
            duration_hours = duration_seconds / 3600
            tss = duration_hours * (intensity_factor ** 2) * 100
            return tss
        return 0
    
    @staticmethod
    def chronic_training_load(tss_data, days=42):
        """Хроническая тренировочная нагрузка (CTL)"""
        return pd.Series(tss_data).rolling(days).mean().iloc[-1]
    
    @staticmethod
    def acute_training_load(tss_data, days=7):
        """Острая тренировочная нагрузка (ATL)"""
        return pd.Series(tss_data).rolling(days).mean().iloc[-1]
    
    @staticmethod
    def training_stress_balance(ctl, atl):
        """Баланс тренировочного стресса (TSB)"""
        return ctl - atl
```

### Этап 4: Анализ HRV (2 недели)

#### 4.1 HRV анализатор
```python
# models/hrv_analyzer.py
import numpy as np
import pandas as pd
from scipy import signal
import pyhrv

class HRVAnalyzer:
    
    @staticmethod
    def calculate_rmssd(rr_intervals):
        """Root Mean Square of Successive Differences"""
        if len(rr_intervals) < 2:
            return None
        
        successive_diffs = np.diff(rr_intervals)
        rmssd = np.sqrt(np.mean(successive_diffs ** 2))
        return rmssd
    
    @staticmethod
    def calculate_dfa_alpha1(rr_intervals):
        """Detrended Fluctuation Analysis Alpha 1"""
        try:
            # Упрощённая реализация DFA α1
            # В полной версии использовать MFDFA библиотеку
            
            # Интегрирование RR интервалов
            y = np.cumsum(rr_intervals - np.mean(rr_intervals))
            
            # Диапазон окон для анализа (4-16 ударов для α1)
            scales = np.logspace(np.log10(4), np.log10(16), 10).astype(int)
            fluctuations = []
            
            for scale in scales:
                # Разделение на окна
                n_windows = len(y) // scale
                if n_windows < 4:
                    continue
                    
                # Детрендинг и расчёт флуктуаций
                local_fluctuations = []
                for i in range(n_windows):
                    start_idx = i * scale
                    end_idx = (i + 1) * scale
                    window = y[start_idx:end_idx]
                    
                    # Линейная регрессия для детрендинга
                    x = np.arange(len(window))
                    coeffs = np.polyfit(x, window, 1)
                    trend = np.polyval(coeffs, x)
                    
                    # Среднеквадратичная флуктуация
                    fluctuation = np.sqrt(np.mean((window - trend) ** 2))
                    local_fluctuations.append(fluctuation)
                
                fluctuations.append(np.mean(local_fluctuations))
            
            # Логарифмическая регрессия для получения α1
            log_scales = np.log10(scales[:len(fluctuations)])
            log_fluctuations = np.log10(fluctuations)
            
            alpha1, _ = np.polyfit(log_scales, log_fluctuations, 1)
            return alpha1
            
        except Exception as e:
            print(f"Ошибка расчёта DFA α1: {e}")
            return None
    
    @staticmethod
    def estimate_thresholds_from_alpha1(alpha1_values, heart_rates):
        """Оценка порогов из DFA α1"""
        thresholds = {}
        
        # Аэробный порог (α1 = 0.75)
        aerobic_idx = np.argmin(np.abs(np.array(alpha1_values) - 0.75))
        thresholds['aerobic_threshold'] = heart_rates[aerobic_idx]
        
        # Анаэробный порог (α1 = 0.5)
        anaerobic_idx = np.argmin(np.abs(np.array(alpha1_values) - 0.5))
        thresholds['anaerobic_threshold'] = heart_rates[anaerobic_idx]
        
        return thresholds
    
    @staticmethod
    def recovery_score(rmssd_current, rmssd_baseline):
        """Оценка восстановления на основе RMSSD"""
        if rmssd_baseline > 0:
            recovery_ratio = rmssd_current / rmssd_baseline
            # Нормализация в проценты
            recovery_score = min(100, max(0, recovery_ratio * 100))
            return recovery_score
        return 50  # Нейтральное значение
```

### Этап 5: AI коучинг с ChatGPT (1-2 недели)

#### 5.1 AI коуч
```python
# models/ai_coach.py
import openai
import json
from datetime import datetime, timedelta

class AICoach:
    def __init__(self, api_key):
        openai.api_key = api_key
        self.system_prompt = """
        Ты опытный тренер по выносливости с глубокими знаниями физиологии.
        Анализируй предоставленные данные тренировок и давай персонализированные рекомендации.
        Учитывай: TSS, CTL, ATL, TSB, HRV данные, тип активности.
        Отвечай кратко и практично.
        """
    
    def analyze_training_data(self, training_summary):
        """Анализ тренировочных данных"""
        user_prompt = f"""
        Данные тренировок за последние 7 дней:
        - Общий TSS: {training_summary.get('weekly_tss', 0)}
        - CTL: {training_summary.get('ctl', 0)}
        - ATL: {training_summary.get('atl', 0)}
        - TSB: {training_summary.get('tsb', 0)}
        - HRV Score: {training_summary.get('hrv_score', 'нет данных')}
        - Количество тренировок: {training_summary.get('workout_count', 0)}
        - Основной вид спорта: {training_summary.get('primary_sport', 'неизвестно')}
        
        Дай рекомендации на следующую неделю.
        """
        
        try:
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=300,
                temperature=0.7
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            return f"Ошибка получения рекомендаций: {e}"
    
    def workout_feedback(self, workout_data, subjective_feedback=""):
        """Анализ конкретной тренировки"""
        user_prompt = f"""
        Данные тренировки:
        - Вид спорта: {workout_data.get('sport', 'неизвестно')}
        - Продолжительность: {workout_data.get('duration_minutes', 0)} минут
        - TSS: {workout_data.get('tss', 0)}
        - Средний пульс: {workout_data.get('avg_hr', 'нет данных')}
        - Средняя мощность: {workout_data.get('avg_power', 'нет данных')}
        
        Субъективные ощущения: {subjective_feedback}
        
        Проанализируй тренировку и дай обратную связь.
        """
        
        try:
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=200,
                temperature=0.7
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            return f"Ошибка анализа тренировки: {e}"
```

### Этап 6: Финализация UI и интеграция (1-2 недели)

#### 6.1 Обновлённое главное приложение
```python
# app.py (обновлённая версия)
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import os

# Импорты наших модулей
from data.garmin_client import GarminClient
from data.database import Database
from data.data_processor import ActivityProcessor
from models.banister import BanisterModel
from models.hrv_analyzer import HRVAnalyzer
from models.ai_coach import AICoach
from utils.metrics import MetricsCalculator

# Настройка страницы
st.set_page_config(
    page_title="AI Trainer",
    page_icon="🏃‍♂️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Инициализация состояния
if 'garmin_client' not in st.session_state:
    st.session_state.garmin_client = GarminClient()
if 'database' not in st.session_state:
    st.session_state.database = Database()

# Боковая панель для навигации
st.sidebar.title("🏃‍♂️ AI Trainer")

# Аутентификация Garmin
if not st.session_state.garmin_client.is_authenticated:
    with st.sidebar.expander("Подключение к Garmin Connect"):
        email = st.text_input("Email Garmin", type="default")
        password = st.text_input("Пароль Garmin", type="password")
        
        if st.button("Подключиться"):
            if st.session_state.garmin_client.authenticate(email, password):
                st.success("Успешно подключено!")
                st.rerun()

# Главное меню
if st.session_state.garmin_client.is_authenticated:
    page = st.sidebar.selectbox("Выберите раздел:", [
        "📊 Дашборд", 
        "🏃‍♂️ Активности", 
        "💓 Анализ HRV", 
        "📈 Планирование", 
        "🤖 AI Коучинг"
    ])
    
    # Синхронизация данных
    if st.sidebar.button("🔄 Синхронизировать данные"):
        sync_data()
    
    # Основной контент
    if page == "📊 Дашборд":
        show_dashboard()
    elif page == "🏃‍♂️ Активности":
        show_activities()
    elif page == "💓 Анализ HRV":
        show_hrv_analysis()
    elif page == "📈 Планирование":
        show_planning()
    elif page == "🤖 AI Коучинг":
        show_ai_coaching()

else:
    st.title("🏃‍♂️ Персональный AI Тренер")
    st.markdown("""
    Добро пожаловать в ваш персональный AI тренер!
    
    Для начала работы подключитесь к Garmin Connect в боковой панели.
    """)

def sync_data():
    """Синхронизация данных с Garmin Connect"""
    with st.spinner("Синхронизация данных..."):
        # Получение активностей за последние 30 дней
        end_date = datetime.now()
        start_date = end_date - timedelta(days=30)
        
        activities = st.session_state.garmin_client.get_activities(start_date, end_date)
        
        if activities:
            df = ActivityProcessor.process_activities(activities)
            st.session_state.database.save_activities(df)
            st.success(f"Синхронизировано {len(activities)} активностей")

def show_dashboard():
    """Главный дашборд"""
    st.title("📊 Дашборд тренировок")
    
    # Получение данных
    activities_df = st.session_state.database.get_activities(30)
    
    if activities_df.empty:
        st.warning("Нет данных. Выполните синхронизацию с Garmin Connect.")
        return
    
    # Метрики в колонках
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        total_activities = len(activities_df)
        st.metric("Активности (30 дней)", total_activities)
    
    with col2:
        total_distance = activities_df['distance_km'].sum()
        st.metric("Общая дистанция", f"{total_distance:.1f} км")
    
    with col3:
        total_time = activities_df['duration_minutes'].sum()
        st.metric("Общее время", f"{total_time/60:.1f} ч")
    
    with col4:
        avg_tss = activities_df['tss'].mean() if 'tss' in activities_df.columns else 0
        st.metric("Средний TSS", f"{avg_tss:.1f}")
    
    # Графики
    col1, col2 = st.columns(2)
    
    with col1:
        # График активностей по дням
        daily_stats = activities_df.groupby('date').agg({
            'duration_minutes': 'sum',
            'distance_km': 'sum'
        }).reset_index()
        
        fig = px.bar(daily_stats, x='date', y='duration_minutes', 
                    title="Время тренировок по дням")
        st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        # Распределение по видам спорта
        sport_dist = activities_df['sport'].value_counts()
        fig = px.pie(values=sport_dist.values, names=sport_dist.index,
                    title="Распределение по видам спорта")
        st.plotly_chart(fig, use_container_width=True)

# ... остальные функции показа страниц
```

## 📦 Развёртывание и запуск

### Финальная структура requirements.txt
```txt
streamlit>=1.28.0
pandas>=1.5.0
numpy>=1.21.0
scipy>=1.9.0
plotly>=5.15.0
garminconnect>=0.1.55
python-fitparse>=1.2.0
pyhrv>=0.4.0
scikit-learn>=1.3.0
openai>=0.28.0
python-dotenv>=1.0.0
sqlalchemy>=2.0.0
```

### Переменные окружения (.env)
```env
OPENAI_API_KEY=your_openai_api_key_here
GARMIN_EMAIL=your_garmin_email
GARMIN_PASSWORD=your_garmin_password
```

### Запуск приложения
```bash
# Активация окружения
source ai_trainer_env/bin/activate

# Запуск Streamlit
streamlit run app.py
```

## 🎯 Ключевые особенности итогового продукта

1. **Интеграция с Garmin Connect** - автоматическая синхронизация активностей
2. **Модель Банистера** - предсказание фитнеса и усталости
3. **HRV анализ** - оценка восстановления и определение порогов
4. **AI коучинг** - персонализированные рекомендации через ChatGPT
5. **Интуитивный интерфейс** - удобный дашборд на Streamlit
6. **Локальное хранение** - кеширование данных в SQLite

## 📈 Возможности для расширения

- Добавление интеграции с другими платформами (Strava, TrainingPeaks)
- Реализация продвинутого DFA α1 анализа
- Создание автоматических планов тренировок
- Добавление уведомлений и напоминаний
- Экспорт данных в различные форматы
- Развёртывание в облаке для удалённого доступа