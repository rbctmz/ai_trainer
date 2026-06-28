# 🏃‍♂️ AI Trainer - Персональный тренер на базе ИИ

Интеллектуальный анализатор тренировочных данных с интеграцией Garmin Connect для персонализированного планирования тренировок.

Репозиторий находится в активной миграции со Streamlit на web-стек FastAPI + Next.js. Новые продуктовые сценарии идут через `api/` + `web/`, при этом Streamlit остаётся рабочим fallback-контуром до полной parity.

## 📋 Требования

- Python 3.10+ (проект проверен на 3.11)
- `pip` и модуль `venv` для управления зависимостями
- Node.js и `npm` для web-интерфейса
- Учётная запись Garmin Connect (нужна для реальной синхронизации данных; демо-режим работает без неё)
- API-ключ хотя бы одного AI‑провайдера из списка ниже (для реального AI; демо-режим использует Mock AI)

## 🚀 Быстрый старт

### 1. Установка зависимостей

```bash
# Создание виртуального окружения
python -m venv ai_trainer_env

# Активация окружения
source ai_trainer_env/bin/activate  # macOS/Linux
# или
ai_trainer_env\Scripts\activate     # Windows

# Установка runtime-зависимостей
pip install -r requirements.txt

# Web/API слой
pip install -r requirements-web.txt

# Для разработки и тестов
pip install -r requirements-dev.txt

# One-time browser install for Playwright-based acceptance probes
python -m playwright install chromium
```

### 2. Настройка окружения

Создайте файл `.env` в корне проекта со следующими переменными. Для реального AI обязателен только ключ провайдера, которого вы планируете использовать (OpenAI/Anthropic/DeepSeek/Gemini или локальный Ollama). Остальные параметры можно оставить пустыми или удалить, если они вам не нужны.

> 💡 Для совместной работы удобно держать шаблон `.env.example` без секретных данных и копировать его в `.env` при настройке.

```bash
# AI Провайдеры (выберите один или несколько)
OPENAI_API_KEY=your_openai_key         # OpenAI GPT
ANTHROPIC_API_KEY=your_anthropic_key   # Claude
DEEPSEEK_API_KEY=your_deepseek_key     # DeepSeek
GOOGLE_API_KEY=your_google_key         # Gemini
OLLAMA_HOST=http://localhost:11434     # Локальные модели
DEFAULT_AI_PROVIDER=deepseek           # openai/anthropic/deepseek/google/ollama

# Garmin Connect (опционально)
GARMIN_EMAIL=your_email@example.com
GARMIN_PASSWORD=your_password

# Настройки пользователя
USER_FTP=250                           # Функциональная мощность (Вт)
USER_LTHR=170                          # Лактатный порог (уд/мин)
USER_MAX_HR=185                        # Максимальный пульс (уд/мин)
```

### 3. Запуск приложения

#### Web stack (основной вектор миграции)
```bash
./run_web.sh
```

Если скрипт не исполняется, сделайте его исполняемым: `chmod +x run_web.sh`.

`run_web.sh` поднимает:
- web UI: http://localhost:3000
- FastAPI docs: http://localhost:8000/docs

Скрипт также автоматически устанавливает `requirements-web.txt` и `web`-зависимости, если они ещё не установлены.

#### Legacy Streamlit fallback
```bash
./run.sh
```

Если скрипт не исполняется, сделайте его исполняемым: `chmod +x run.sh`.

#### Альтернативный запуск Streamlit
```bash
export PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=python
streamlit run app.py
```

```powershell
# Windows PowerShell
$env:PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION = "python"
streamlit run app.py

# Windows Command Prompt (cmd)
set PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=python
streamlit run app.py
```

#### Если возникает ошибка с Google Gemini
```bash
# Проверьте runtime-зависимости
python scripts/doctor_env.py check --runtime

# При необходимости выполните одноразовое восстановление
python scripts/doctor_env.py repair --runtime
```

#### Если `./run.sh` сообщает о поврежденных runtime-зависимостях
```bash
# Одноразовая диагностика
python scripts/doctor_env.py check --runtime

# Одноразовое восстановление
python scripts/doctor_env.py repair --runtime
```

#### Если проект лежит в iCloud/`~/Documents` и Streamlit/pytest подвисают
```bash
# Проверка локальной доступности workspace
python scripts/doctor_env.py check --workspace
```

Если проверка сообщает про `dataless/offloaded workspace files` или iCloud-backed workspace:
- В Finder выполните `Download Now` или `Keep Downloaded` для папки репозитория.
- Лучше перенесите проект в локальную директорию вроде `~/Code/ai_trainer` или `~/GitHub/ai_trainer`.

Во время миграции обе поверхности поддерживаются:
- `http://localhost:3000` — web UI
- `http://localhost:8501` — legacy Streamlit UI

## 📊 Возможности

### Основной функционал
- **🔗 Интеграция с Garmin Connect** - Автоматическая синхронизация активностей и HRV данных
- **🎮 Демо-режим** - Изолированный локальный набор данных и Mock AI для безопасного знакомства без Garmin/API
- **📈 Дашборд тренировок** - Интерактивная визуализация прогресса и метрик
- **💓 Анализ HRV** - Мониторинг восстановления через RMSSD и DFA α1
- **📋 Анализ TSS** - Расчёт тренировочного стресса и баланса CTL/ATL/TSB
- **🛌 Анализ сна** - Карточки регулярности режима с рекомендациями и профилем по дням недели
- **⚙️ Модель Банистера** - Прогнозирование fitness/fatigue баланса

### 🤖 Универсальная система AI коучинга
- **Мультипровайдерная архитектура** - Поддержка OpenAI, Anthropic Claude, DeepSeek, Google Gemini, Ollama и Mock AI
- **Интерактивный выбор моделей** - Динамические dropdown-списки с автообнаружением
- **Тестирование подключения** - Валидация API ключей перед использованием
- **Персонализированные рекомендации**:
  - 📊 Анализ текущего состояния
  - 📅 Недельное планирование тренировок
  - 🏃 Анализ выполненных тренировок
  - ❓ Ответы на вопросы о тренировках
  - 📚 Объяснение метрик простым языком

## 🏗️ Архитектура проекта

```text
ai_trainer/
├── api/                       # FastAPI контракты для web-фронта
├── web/                       # Next.js UI, миграционный product surface
├── app.py                     # Legacy Streamlit shell: fallback/dev/acceptance surface
├── config/
│   └── settings.py            # Конфигурация и константы
├── data/
│   ├── garmin_client.py       # API клиент Garmin Connect
│   ├── data_processor.py      # Обработка данных активностей
│   └── database.py            # SQLite для локального кеширования
├── services/                  # Garmin/sync/demo/acceptance orchestration
├── state/                     # Streamlit-oriented state helpers
├── ui/
│   ├── pages/                 # Legacy Streamlit pages
│   └── components/            # Legacy Streamlit components
├── models/
│   ├── ai_providers.py        # Универсальная архитектура AI провайдеров
│   ├── ai_coach_universal.py  # Универсальная система коучинга
│   ├── banister.py            # Модель Банистера (fitness/fatigue)
│   ├── hrv_analyzer.py        # Анализ HRV (RMSSD, DFA α1)
│   └── mock_ai_provider.py    # Mock провайдер для тестирования
├── utils/
│   ├── modern_ui.py           # Streamlit UI helpers and shared CSS
│   ├── metrics.py             # Расчёт метрик (TSS, NP, CTL, ATL)
│   ├── sleep_metrics.py       # Регулярность сна, агрегация по дням недели
│   └── visualizations.py      # Plotly визуализации
├── tests/                     # Тесты и отладочные скрипты
├── debug/                     # Скрипты отладки
├── examples/                  # Демо и примеры использования
└── docs/                      # Документация
```

## 🔧 Технологический стек

### Product surfaces
- **FastAPI** - Контрактный backend для product/web flows
- **Next.js 14** - Основной web UI во время миграции
- **Streamlit** - Legacy fallback/admin/acceptance surface

### Основные библиотеки
- **pandas/numpy** - Обработка и анализ данных
- **scipy** - Научные вычисления (оптимизация, обработка сигналов)
- **plotly** - Интерактивные визуализации
- **SQLAlchemy** - ORM для работы с базой данных

### Интеграции
- **garminconnect** - API клиент Garmin Connect
- **python-fitparse** - Парсинг FIT файлов
- **pyhrv** - Анализ вариабельности сердечного ритма

### AI провайдеры
- **openai** - OpenAI GPT модели
- **anthropic** - Anthropic Claude
- **DeepSeek** - OpenAI-compatible DeepSeek API
- **google-genai** - Google Gemini
- **ollama** - Локальные LLM модели

## 📝 Статус разработки

### ✅ Завершённые функции
- Полная интеграция с Garmin Connect
- Web migration MVP: FastAPI + Next.js dashboard/coach/hrv/activities/planning
- Интерактивный дашборд тренировок
- Расчёт всех ключевых метрик (TSS, NP, CTL, ATL, TSB)
- Универсальная система AI провайдеров
- Динамический выбор AI моделей с автообнаружением
- Demo/acceptance режимы с изолированной БД и Mock AI
- Planning V2: версии планов, execution feedback, Garmin plan/fact review
- Intervals.icu экспорт запланированных тренировок (при наличии API key)
- Тестирование подключения к провайдерам
- Анализ HRV (RMSSD, DFA α1)
- Регулярность режима сна с рекомендациями
- Модель Банистера для fitness/fatigue
- Полнофункциональный AI коучинг:
  - Анализ текущего состояния
  - Недельное планирование
  - Анализ тренировок
  - Экспертные ответы на вопросы
  - Образовательный контент

### 🔄 В разработке / ближайший долг
- Доведение parity между web и legacy Streamlit поверхностями
- Декомпозиция крупных модулей Planning/Dashboard
- Единый signals engine для dashboard/planning/AI
- Уточнение и очистка старых диагностических тестов

## 🛠️ Команды разработки

### Тестирование
```bash
# Перед запуском тестов активируйте виртуальное окружение с зависимостями
# source ai_trainer_env/bin/activate  (macOS/Linux)
# ai_trainer_env\Scripts\activate     (Windows)

# Contributor-safe smoke path
python -m pytest tests/smoke -q

# Более широкий локальный прогон без live/debug сценариев
python -m pytest -m "not live and not debug" tests/

# Изолированный acceptance-запуск с временной БД
ACCEPTANCE_PORT=8510 ./run_acceptance.sh

# Live acceptance probes against a running acceptance instance
ACCEPTANCE_BASE_URL=http://localhost:8510/ python tests/e2e_acceptance_live.py
ACCEPTANCE_BASE_URL=http://localhost:8510/ python tests/e2e_acceptance_flows.py

# Тестирование AI провайдеров
python tests/test_ai_providers_advanced.py
python tests/test_provider_features.py

# Отладочные скрипты
python debug/debug_ollama.py

# Примеры использования
python examples/demo_ai_features.py
```

### Установка Ollama для локальных моделей
```bash
# macOS/Linux
curl -fsSL https://ollama.com/install.sh | sh

# Запуск сервера
ollama serve

# Загрузка моделей
ollama pull llama2
ollama pull gemma2:2b
ollama pull mistral
```

## 🐛 Решение проблем

### Ошибка Google Gemini runtime
```bash
# Стандартный запуск уже применяет runtime defaults
./run.sh

# Диагностика и восстановление зависимостей
python scripts/doctor_env.py check --runtime
python scripts/doctor_env.py repair --runtime
```

### Ошибка `ImportError: cannot import name 'Dataframe_pb2'`
- Причина: некоторые версии `streamlit` на macOS могут устанавливаться с конфликтом имён файлов в `streamlit/proto`.
- Решение: выполните `python scripts/doctor_env.py repair --runtime`, затем повторите `./run.sh`.

### `python -m pytest` не запускается
- Причина: dev-зависимости установлены не полностью или пакет `pytest` в текущем `venv` повреждён.
- Решение:
```bash
pip install -r requirements-dev.txt
python scripts/doctor_env.py repair --dev
python -m pytest tests/smoke -q
```

### Playwright просит установить браузер
- Причина: Python-пакет `playwright` установлен, но Chromium не скачан для текущего окружения.
- Решение:
```bash
python -m playwright install chromium
```

### Проблемы с AI провайдерами
- **Провайдер показывает ❌**: Проверьте API ключ в `.env`
- **Медленные ответы**: Используйте более быстрые модели (GPT-3.5, Claude-haiku) или локальный Ollama
- **Ollama не подключается**: Убедитесь что `ollama serve` запущен

## 🗺️ Roadmap & Feedback

Мы разрабатываем проект открыто. Голосуйте за фичи, сообщайте о багах или предлагайте свои идеи!

| | | |
|---|---|---|
| 📋 **Roadmap** | [github.com/rbctmz/ai_trainer/projects/2](https://github.com/rbctmz/ai_trainer/projects/2) | Текущие приоритеты и статус разработки |
| 💡 **Feature Requests** | [Discussions](https://github.com/rbctmz/ai_trainer/discussions/new?category=Feature%20Requests) | Предложите идею или проголосуйте 👍 |
| 🐛 **Bug Reports** | [Open an issue](https://github.com/rbctmz/ai_trainer/issues/new/choose) | Сообщите о проблеме через шаблон |
| ❓ **Q&A** | [Discussions](https://github.com/rbctmz/ai_trainer/discussions/new?category=Q%20%26%20A) | Задайте вопрос сообществу |

## 🤝 Вклад в проект

Проект находится в активной разработке. Ваши предложения и pull request'ы приветствуются!

### Руководство по разработке
- Все тесты должны быть в директории `tests/`
- Используйте соглашение `test_<component>.py` для тестов
- Отладочные скрипты: `debug_<feature>.py`
- Следуйте существующим паттернам кода

## 📄 Лицензия

MIT License - см. [LICENSE](LICENSE)
