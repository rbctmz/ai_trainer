# 🏃‍♂️ AI Trainer - Персональный тренер на базе ИИ

Персональный evidence-first AI-тренер: синхронизирует данные Garmin, объединяет
нагрузку и восстановление, строит планы для бега, велоспорта и триатлона и
предлагает объяснимые изменения с подтверждением и откатом. Приложение можно
запускать локально или self-hosted; Intervals.icu подключается как опциональный
источник профиля/событий, plan-fact evidence и канал экспорта тренировок.

Репозиторий находится в активной миграции со Streamlit на web-стек FastAPI + Next.js. Новые продуктовые сценарии идут через `api/` + `web/`, при этом Streamlit остаётся рабочим fallback-контуром до полной parity.

## 📋 Требования

- Python 3.10+ (проект проверен на 3.11)
- `pip` и модуль `venv` для управления зависимостями
- Node.js и `npm` для web-интерфейса
- Учётная запись Garmin Connect (нужна для реальной синхронизации данных; демо-режим работает без неё)
- API-ключ хотя бы одного AI‑провайдера из списка ниже (для реального AI; демо-режим использует Mock AI)
- Персональный API-ключ Intervals.icu — опционально, для синхронизации профиля,
  чтения гонок/plan-fact evidence и отправки плановых тренировок

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

# Intervals.icu (опционально)
INTERVALS_ICU_API_KEY=your_intervals_icu_api_key
INTERVALS_ICU_ATHLETE_ID=0
INTERVALS_ICU_BASE_URL=https://intervals.icu

# Настройки пользователя и fallback-пороги
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

Если один из портов уже занят, скрипт остановится до запуска web stack и подскажет
override. Например:

```bash
API_PORT=8010 WEB_PORT=3010 ./run_web.sh
```

Скрипт также автоматически устанавливает `requirements-web.txt` и `web`-зависимости, если они ещё не установлены.

#### Self-hosted deployment (Docker)

Для однопользовательского запуска на домашнем сервере или VPS нужны Docker и
Compose plugin (`docker compose version`). В этой схеме наружу доступен только
Caddy: он запрашивает логин и пароль, проксирует web/API по внутренней Docker-сети
и автоматически включает HTTPS, если задан домен. SQLite хранится в named volume
и переживает пересборки контейнеров.

1. Сгенерируйте bcrypt-хэш пароля (сам пароль в `.env` не хранится):

```bash
docker run --rm caddy:2 caddy hash-password --plaintext 'chosen-password'
```

2. Скопируйте `.env.example` в `.env`, заполните нужные ключи и параметры:

```dotenv
# Пустое значение включает локальный HTTP на http://localhost:8080.
# Для VPS укажите DNS-имя, например trainer.example.com.
DOMAIN=
BASIC_AUTH_USER=trainer
# Одинарные кавычки обязательны: bcrypt-хэш содержит символы `$`.
BASIC_AUTH_HASH='$2a$14$replace_with_generated_hash'
```

3. Соберите и запустите сервисы:

```bash
docker compose up -d --build
docker compose ps
```

4. Откройте `http://localhost:8080` в локальном режиме или
`https://<DOMAIN>` на сервере и введите созданные credentials. FastAPI и Next.js
на портах `8000`/`3000` напрямую не публикуются.

Чтобы перенести существующую локальную `ai_trainer.db`, сначала остановите
локально запущенный AI Trainer и сделайте резервную копию. Команды ниже создают
контейнер без запуска API, копируют базу в named volume и затем запускают стек:

```bash
cp ai_trainer.db ai_trainer.db.backup
docker compose create api
docker compose cp ai_trainer.db api:/data/ai_trainer.db
docker compose up -d
```

Повторный `docker compose cp` перезапишет базу в volume, поэтому не выполняйте
миграцию поверх уже накопленных контейнером данных без свежей резервной копии.
Обычный `docker compose down` сохраняет данные; опция `-v` удаляет volume вместе
с тренировочной историей и должна использоваться только намеренно.

Полный контракт, HTTPS-режим и сценарии приёмки описаны в
[`docs/self_hosted_deployment_execplan.md`](docs/self_hosted_deployment_execplan.md).

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

### Данные, нагрузка и восстановление

- **Garmin Connect** — инкрементальная синхронизация активностей, сна, HRV,
  пульса покоя, training readiness/status, Body Battery и доступных
  recovery bio-signals.
- **Intervals.icu** — опциональная синхронизация FTP/веса/LTHR, чтение гонок
  A/B/C, provider evidence для plan-fact и экспорт плановых событий.
- **Единый readiness fusion** — личные 28-дневные базлайны HRV/RHR, сон,
  Garmin readiness и TSB с confidence, evidence и явными data gaps.
- **Нагрузка и форма** — TSS/NP, CTL/ATL/TSB, канонические зоны TSB и модель
  Банистера; bike TSS учитывает normalized power и актуальный профиль атлета.
- **Web-поверхности** — «Сегодня», дашборд, HRV, сон и журнал активностей.
- **Демо-режим** — изолированная БД и Mock AI без Garmin/API-ключей.

### Планирование и агентный контур

- Планы для бега, велоспорта и триатлона по цели, дистанции, доступным
  дням/часам, текущей нагрузке и выбранной требовательности.
- Режимы `event_goal`, rolling `training_goal` и ручные фазы; приоритеты гонок
  A/B/C, taper/Race Week, локальные race overlays и защищённые даты.
- Preview/confirm перед сохранением, append-only версии плана и защита от
  подтверждения устаревшего preview.
- Plan-fact reconciliation с устойчивыми session identities, явным исправлением
  спорных совпадений и evidence-first недельной перебалансировкой только будущих
  сессий.
- Версионированный каталог из 19 тренировочных стимулов материализует точные
  шаги и честные FTP/LTHR/relative targets; триатлонные Build/Peak-недели
  поддерживают единый bike-to-run brick с раздельным экспортом обеих ног.
- Readiness conflict gate: корректное «молчание», data gap или предложение
  ослабить конфликтующую ключевую сессию.
- Предложения можно подтвердить или отклонить; применённый recovery replan
  журналируется и откатывается новой версией плана.
- Долговременные ограничения коуча (`sick`, `unavailable`, `forced_rest` и др.)
  защищают даты от повторного появления тренировки при replanning.
- Экспорт календаря и тренировок в ICS/TCX/FIT-compatible CSV; legacy Planning
  также умеет отправлять события в Intervals.icu.

### 🤖 Универсальная система AI коучинга

- **Мультипровайдерность** — OpenAI, Anthropic Claude, DeepSeek, Google Gemini,
  локальный Ollama и Mock AI; выбор моделей и проверка подключения.
- **Tool-using coach** — анализирует фактические активности, нагрузку,
  восстановление, сон и активный план, а затем синтезирует ответ с опорой на
  полученные данные.
- **Управляемые действия** — коуч создаёт сохраняемые предложения построения или
  изменения плана; мутация выполняется только после явного подтверждения.
- **Журнал решений** — история ответов, recovery-решений, предложений и их
  lifecycle вместо непрозрачных фоновых изменений.
- **Shadow quality forecast** — детерминированный прогноз ближайшей ключевой
  сессии сохраняется для последующей калибровки, но не влияет на решение или
  план автоматически.

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
├── services/                  # Garmin/Intervals.icu sync, demo и orchestration
├── state/                     # Streamlit-oriented state helpers
├── ui/
│   ├── pages/                 # Legacy Streamlit pages
│   └── components/            # Legacy Streamlit components
├── models/
│   ├── ai_providers.py        # Универсальная архитектура AI провайдеров
│   ├── ai_coach_universal.py  # Универсальная система коучинга
│   ├── banister.py            # Модель Банистера (fitness/fatigue)
│   ├── hrv_analyzer.py        # Анализ HRV (RMSSD, DFA α1)
│   ├── readiness.py           # Канонический readiness fusion
│   ├── signals_engine.py      # Общие сигналы для API/web/legacy
│   ├── training_planner.py    # Периодизация и дневной план
│   ├── workout_catalog.py     # Версионированные стимулы, шаги и brick-сессии
│   ├── plan_actual_reconciliation.py # Evidence-first plan/fact
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
- **Garmin Connect** — основной источник активностей, здоровья и recovery-данных
- **Intervals.icu API** — профиль атлета, A/B/C события, plan-fact evidence и
  плановые workout events; интеграция опциональна и работает по персональному ключу
- **python-fitparse** — парсинг FIT-файлов
- **pyhrv** — анализ вариабельности сердечного ритма

### AI провайдеры
- **openai** - OpenAI GPT модели
- **anthropic** - Anthropic Claude
- **DeepSeek** - OpenAI-compatible DeepSeek API
- **google-genai** - Google Gemini
- **ollama** - Локальные LLM модели

## 📝 Статус разработки

### ✅ Завершённые функции
- Инкрементальная интеграция с Garmin Connect, включая recovery bio-signals
- Web-контур FastAPI + Next.js: Today, Dashboard, Coach, Decisions, Planning,
  HRV, Sleep и Activities
- Интерактивный дашборд тренировок
- Расчёт всех ключевых метрик (TSS, NP, CTL, ATL, TSB)
- Единый signals/readiness engine с личными базлайнами, evidence и confidence
- Универсальная система AI провайдеров
- Динамический выбор AI моделей с автообнаружением
- Demo/acceptance режимы с изолированной БД и Mock AI
- Planning V2: preview/confirm, append-only версии, execution feedback и
  долговременные ограничения
- Race-aware периодизация: event/training/manual режимы, гонки A/B/C и
  защищённые race/recovery даты
- Evidence-first plan-fact reconciliation, ручное исправление совпадений и
  безопасная недельная перебалансировка будущего плана
- Каталог из 19 структурированных стимулов, точные prescription snapshots и
  атомарные bike-to-run brick-сессии с отдельным экспортом ног
- Recovery Replan: readiness gate, журналируемые предложения,
  approve/reject и rollback
- Shadow-прогноз качества ближайшей ключевой сессии для калибровки
- Intervals.icu: профиль атлета, чтение гонок и plan-fact evidence, экспорт
  запланированных тренировок при наличии API key
- Тестирование подключения к провайдерам
- Анализ HRV (RMSSD, DFA α1)
- Регулярность режима сна с рекомендациями
- Модель Банистера для fitness/fatigue
- AI-коучинг:
  - Анализ текущего состояния
  - Недельное планирование
  - Анализ тренировок
  - Экспертные ответы на вопросы
  - Образовательный контент

### 🔄 В разработке / ближайший долг
- Доведение parity между web и legacy Streamlit поверхностями
- Декомпозиция крупных модулей Planning/Dashboard
- Last-mile доставка тренировок и статус синхронизации в основном web-контуре
- Proactive morning/push/messaging канал поверх готового readiness/replan backend
- Калибровка session-quality forecast и персональных recovery-кривых по мере
  накопления достаточного числа наблюдений
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
