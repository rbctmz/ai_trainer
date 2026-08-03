# 🏃‍♂️ AI Trainer - Персональный тренер на базе ИИ

Персональный evidence-first AI-тренер: синхронизирует активности и восстановление
из Intervals.icu и, при необходимости, Garmin Connect, строит исполняемые планы
для бега, велоспорта и триатлона и предлагает объяснимые изменения с
подтверждением и откатом. Intervals.icu — рекомендуемый основной источник для
нового запуска; Garmin Connect сохраняется как совместимый необязательный
источник. Приложение запускается локально или self-hosted; основной продуктовый
стек — FastAPI + Next.js, Streamlit сохраняется как fallback на время миграции.

Репозиторий находится в активной миграции со Streamlit на web-стек FastAPI + Next.js. Новые продуктовые сценарии идут через `api/` + `web/`, при этом Streamlit остаётся рабочим fallback-контуром до полной parity.

## 📋 Требования

- Python 3.10+ (проект проверен на 3.11)
- `pip` и модуль `venv` для управления зависимостями
- Node.js и `npm` для web-интерфейса
- Хотя бы один источник данных: Intervals.icu рекомендуется для нового запуска,
  Garmin Connect можно подключить дополнительно; демо-режим работает без обоих
- API-ключ хотя бы одного AI‑провайдера из списка ниже (для реального AI; демо-режим использует Mock AI)
- Персональный API-ключ Intervals.icu — нужен для Intervals-primary сценария:
  активности, wellness, профиль, гонки, plan-fact evidence и плановые тренировки

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

# Intervals.icu (рекомендуемый основной источник)
INTERVALS_ICU_API_KEY=your_intervals_icu_api_key
INTERVALS_ICU_ATHLETE_ID=0
INTERVALS_ICU_BASE_URL=https://intervals.icu
PRIMARY_ACTIVITY_SOURCE=intervals
PRIMARY_WELLNESS_SOURCE=intervals

# Garmin Connect (необязательный дополнительный источник)
GARMIN_EMAIL=your_email@example.com
GARMIN_PASSWORD=your_password

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

Dev-поверхности (`/decisions`, `/recovery`, shadow-модуль на `/today`) скрыты по
умолчанию build-time флагом. Чтобы включить их в локальной разработке:

```bash
NEXT_PUBLIC_SHOW_DEV_TOOLS=true ./run_web.sh
```

Флаг инлайнится в клиентский бандл при сборке (runtime-переключатель не
создаётся), поэтому изменение требует перезапуска dev-сервера.

Скрипт также автоматически устанавливает `requirements-web.txt` и `web`-зависимости, если они ещё не установлены.

#### Self-hosted deployment (Docker)

Для однопользовательского запуска на домашнем сервере или VPS нужны Docker и
Compose plugin (`docker compose version`). В этой схеме наружу доступен только
Caddy: он запрашивает логин и пароль, проксирует web/API по внутренней Docker-сети
и автоматически включает HTTPS, если задан домен. SQLite хранится в named volume
и переживает пересборки контейнеров.

Для рекомендуемого нового запуска используйте пошаговый
[Intervals-primary quickstart](docs/intervals_primary_quickstart.md): он ведёт
от пустого клона и API key до синхронизации активностей и wellness, онбординга
и первого плана. Garmin для этого сценария не требуется.

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

Чтобы перенести существующую локальную `ai_trainer.db`, сначала остановите все
процессы AI Trainer и создайте проверенный SQLite snapshot:

```bash
mkdir -p backups
python scripts/sqlite_backup_restore.py backup \
  --database ai_trainer.db \
  --output backups/ai_trainer-migration.db \
  --confirm-stopped
docker compose down
docker compose run --rm --no-deps \
  --volume "$PWD/backups:/backup" \
  api python scripts/sqlite_backup_restore.py restore \
  --database /data/ai_trainer.db \
  --backup /backup/ai_trainer-migration.db \
  --confirm-stopped
docker compose up -d
```

Если target в volume уже существует, restore сначала создаёт проверенный
rollback; его рекомендуется вывести в host-каталог через
`--rollback-output /backup/<name>.db`. Обычный `docker compose down` сохраняет
данные; опция `-v` удаляет volume вместе с тренировочной историей и должна
использоваться только намеренно.

Полные bare-metal/Docker команды, rollback и аварийная ветка для повреждённого
target описаны в
[`docs/sqlite_backup_restore.md`](docs/sqlite_backup_restore.md). Обычный `cp`
одного `ai_trainer.db` не является рекомендуемым backup: committed страницы
могут находиться в SQLite `-wal`.

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

- **Intervals.icu** — основной путь нового запуска: синхронизация активностей,
  HRV, сна и пульса покоя, чтение гонок A/B/C, provider evidence для plan-fact
  и экспорт плановых событий. FTP, вес и LTHR пока не импортируются
  Intervals-синком: без Garmin используются явно заданные `USER_*` значения.
- **Garmin Connect** — необязательный дополнительный источник активностей, сна,
  HRV, пульса покоя, training readiness/status, Body Battery и доступных
  recovery bio-signals.
- **Единый readiness fusion** — личные 28-дневные базлайны HRV/RHR, сон,
  локальная readiness и TSB с confidence, evidence, provenance и явными data
  gaps; Garmin-only сигналы используются, если источник подключён.
- **Нагрузка и форма** — TSS/NP, CTL/ATL/TSB, канонические зоны TSB и модель
  Банистера; bike TSS учитывает normalized power и актуальный профиль атлета.
- **Recovery observations** — append-only эпизоды связывают конкретную
  плановую сессию, подтверждённый факт, feedback и readiness D0–D3. Поздняя
  коррекция старого match/feedback точечно обновляет только затронутую сессию,
  не расширяя обычную 12-недельную пост-синхронизацию на всю историю.
- **Web-поверхности** — «Сегодня», дашборд, HRV, сон и журнал активностей.
- **Демо-режим** — изолированная БД и Mock AI без Garmin/API-ключей.

### Планирование и агентный контур

- Планы для бега, велоспорта и триатлона по цели, дистанции, доступным
  дням/часам, текущей нагрузке и выбранной требовательности.
- Режимы `event_goal`, rolling `training_goal` и ручные фазы; приоритеты гонок
  A/B/C, taper/Race Week, локальные race overlays и защищённые даты.
- Preview/confirm перед сохранением, append-only версии плана и защита от
  подтверждения устаревшего preview.
- Исполняемые `sessions[]` — единый источник истины: детерминированный scheduler
  размещает недельный бюджет по доступным слотам, поддерживает несколько
  тренировок в день и гарантирует совпадение sport/TSS в плане, календаре и
  экспорте. Каждая сессия имеет устойчивый content-derived `session_id`.
- Plan-fact reconciliation с устойчивыми session identities, явным исправлением
  спорных совпадений и evidence-first недельной перебалансировкой только будущих
  сессий.
- Reader-first `/planning`: сохранённый активный план открывается обзором цели,
  фаз и прогноза формы; отдельные вкладки показывают недельный plan/fact и
  выполнение. Построение, корректировка и экспорт остаются явными действиями,
  а при отсутствии плана сохраняется onboarding первого плана.
- Версионированный каталог из 22 тренировочных стимулов материализует точные
  шаги и честные FTP/LTHR/relative targets; триатлонные Build/Peak-недели
  поддерживают единый bike-to-run brick с раздельным экспортом обеих ног.
- Readiness conflict gate: корректное «молчание», data gap или предложение
  ослабить конфликтующую ключевую сессию.
- RecoveryReplan v2 предлагает `keep`, `downgrade_today` или безопасный
  атомарный перенос ключевой сессии на D+1…D+3. Кандидаты проверяются по
  доступности, protected dates, hard-load spacing, числу сессий, TSS/времени и
  границе недели; подтверждение и rollback создают новые версии плана.
- Долговременные ограничения коуча (`sick`, `unavailable`, `forced_rest` и др.)
  защищают даты от повторного появления тренировки при replanning.
- Экспорт календаря и тренировок в ICS/TCX/FIT-compatible CSV; web Planning
  доставляет выбранное окно через Intervals.icu, обновляя только события
  AI Trainer с защищённым `external_id`. Чужие тренировки и гонки не меняются.
- Перенос RecoveryReplan v2 намеренно остаётся локальным до отдельного
  подтверждённого delivery-контракта: он не отправляется провайдеру фоном.

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
- **Intervals.icu API** — рекомендуемый основной источник активностей и
  wellness для нового запуска; также профиль атлета, A/B/C события, plan-fact
  evidence и плановые workout events
- **Garmin Connect** — совместимый необязательный источник активностей,
  здоровья и дополнительных recovery-сигналов
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
- Полный Intervals-primary путь: активности и wellness → онбординг → первый
  подтверждённый план → source-aware Today/Sleep/HRV
- Web-контур FastAPI + Next.js: Today, Dashboard, Coach, Decisions, Planning,
  HRV, Sleep и Activities
- Интерактивный дашборд тренировок
- Расчёт всех ключевых метрик (TSS, NP, CTL, ATL, TSB)
- Единый signals/readiness engine с личными базлайнами, evidence и confidence
- Универсальная система AI провайдеров
- Динамический выбор AI моделей с автообнаружением
- Demo/acceptance режимы с изолированной БД и Mock AI
- Planning V2: preview/confirm, append-only версии, детерминированный scheduler,
  несколько исполняемых сессий в день и долговременные ограничения
- Race-aware периодизация: event/training/manual режимы, гонки A/B/C и
  защищённые race/recovery даты
- Evidence-first plan-fact reconciliation, ручное исправление совпадений,
  targeted refresh старых recovery-наблюдений и безопасная недельная
  перебалансировка будущего плана
- Каталог из 22 структурированных стимулов, точные prescription snapshots и
  атомарные bike-to-run brick-сессии с отдельным экспортом ног
- RecoveryReplan v2: readiness gate, варианты keep/downgrade/transfer D+1…D+3,
  явная защита соседних дней, approve/reject и append-only rollback
- Shadow-прогноз качества ближайшей ключевой сессии для калибровки
- Intervals.icu: профиль атлета, чтение гонок и plan-fact evidence, защищённая
  доставка запланированных тренировок из web Planning при наличии API key
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
- Единый приоритизированный реестр: [docs/technical_debt_register.md](docs/technical_debt_register.md)
- Доведение parity между web и legacy Streamlit поверхностями
- Декомпозиция крупных модулей Planning/Dashboard
- История/статус доставки и post-delivery reconciliation в основном web-контуре
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
