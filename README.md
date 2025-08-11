# 🏃‍♂️ AI Trainer - Персональный тренер на базе ИИ

Интеллектуальный анализатор тренировочных данных с интеграцией Garmin Connect для персонализированного планирования тренировок.

## 🚀 Быстрый старт

### 1. Установка зависимостей

```bash
# Создание виртуального окружения
python -m venv ai_trainer_env

# Активация окружения
source ai_trainer_env/bin/activate  # macOS/Linux
# или
ai_trainer_env\Scripts\activate     # Windows

# Установка зависимостей
pip install -r requirements.txt
```

### 2. Настройка окружения

```bash
# Копирование шаблона конфигурации
cp .env.example .env

# Редактирование .env с вашими данными:
# - OPENAI_API_KEY (для AI рекомендаций)
# - GARMIN_EMAIL и GARMIN_PASSWORD (опционально)
```

### 3. Запуск приложения

#### Быстрый запуск (рекомендуется)
```bash
./run.sh
```

#### Альтернативный запуск
```bash
export PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=python
streamlit run app.py
```

#### Если возникает ошибка с Google Gemini
```bash
# Запустите один раз для постоянного исправления
./setup_env.sh

# Или используйте временное решение перед запуском
export PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=python
streamlit run app.py
```

Приложение откроется в браузере по адресу: http://localhost:8501

## 📊 Возможности

- **🔗 Интеграция с Garmin Connect** - Автоматическая синхронизация активностей
- **📈 Дашборд тренировок** - Визуализация прогресса и метрик
- **💓 Анализ HRV** - Мониторинг восстановления (в разработке)
- **🤖 AI Коучинг** - Персонализированные рекомендации (в разработке)
- **📋 Анализ TSS** - Расчёт тренировочного стресса

## 🏗️ Архитектура проекта

```
ai_trainer/
├── app.py                 # Главное Streamlit приложение
├── config/
│   └── settings.py        # Настройки приложения
├── data/
│   ├── garmin_client.py   # Клиент Garmin Connect
│   ├── data_processor.py  # Обработка данных активностей
│   └── database.py        # Локальная БД SQLite
├── models/
│   ├── banister.py        # Модель Банистера
│   ├── hrv_analyzer.py    # Анализ HRV
│   └── ai_coach.py        # AI рекомендации
└── utils/
    ├── metrics.py         # Расчёт метрик (TSS, NP)
    └── visualizations.py  # Графики и визуализации
```

## 🔧 Разработка

Проект использует:
- **Streamlit** - веб-интерфейс
- **garminconnect** - API Garmin Connect
- **pandas/numpy** - обработка данных
- **plotly** - визуализации
- **SQLite** - локальное хранение данных

## 📝 Статус разработки

- ✅ Базовая структура проекта
- ✅ Интеграция с Garmin Connect
- ✅ Дашборд тренировок
- ✅ Расчёт TSS
- 🔄 Анализ HRV (в разработке)
- 🔄 Модель Банистера (в разработке)
- 🔄 AI коучинг (в разработке)

## 🤝 Вклад в проект

Проект находится в активной разработке. Ваши предложения и pull request'ы приветствуются!

## 📄 Лицензия

MIT License - см. [LICENSE](LICENSE)