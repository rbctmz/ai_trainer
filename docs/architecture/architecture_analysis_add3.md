# Архитектурный анализ ai_trainer через призму ADD 3.0

> Обновление 2026-07-20 (Issue #201): каталог ASR вынесен в живой
> [`asr_catalog.md`](asr_catalog.md) (единая точка истины, статусы там),
> недостающие ADR записаны (ADR-0002…0007, реестр в каталоге), EOL-критерии
> Streamlit добавлены в ADR-0001. Таблицы ниже — снимок на момент анализа.

> **Дата:** 2026-07-15
> **Цель:** Проверить текущую архитектуру на полноту по методологии ADD 3.0 (Attribute-Driven Design) и смежным практикам — BDD, QAW, ASR, ADR, ATAM.
> **Для кого:** команда агентов (Claude Code, Codex) и человек-архитектор.

---

## 1. Сводка: что в проекте уже есть

| Этап | Статус | Что есть |
|------|--------|----------|
| **BDD** — поведение системы | ✅ | README, Issues, acceptance-тесты, ExecPlans |
| **Доменное моделирование** | ✅ | `data/` → `services/` → `models/` → `api/` → `web/` |
| **QAW / ASR** — quality attributes | 🟡 | Есть неявно, нет явного каталога сценариев |
| **ADD** — итеративное проектирование | 🟡 | Архитектура хорошая, цикл ADD не отслежен |
| **ADR** — причины решений | 🟡 | Один ADR (web migration). Нужно больше |
| **ATAM** — риски и компромиссы | 🟡 | Нет карты рисков |
| **Прототипы** | 🟡 | api/web прототип есть, нагрузочных тестов нет |

---

## 2. ASR (Architecturally Significant Requirements)

ADD 3.0 начинается с ASR. Вот какие ASR **неявно** заложены в текущую архитектуру, но нигде не записаны.

### 2.1. Производительность и latency

| ID | Сценарий | Приоритет |
|----|----------|-----------|
| ASR-PERF-1 | **Дашборд «Сегодня»** загружается < 2 сек с 3 годами ежедневных данных | High |
| ASR-PERF-2 | **AI-коуч** — первый токен ответа < 5 сек (включая вызов 1–3 инструментов) | High |
| ASR-PERF-3 | **Синхронизация Garmin** инкрементальная: дельта за 1 день < 10 сек | Medium |
| ASR-PERF-4 | **Planning preview** — расчёт 16-недельного плана < 10 сек | Medium |

**Как обеспечивается сейчас:**
- SQLite локально — нет latency сети к БД ✅
- AI-провайдеры асинхронно стримят ответ ✅
- Инкрементальная синхронизация Garmin ✅
- Кэш данных (data_cache.py) 🟡 — есть, но без TTL/invalidation стратегии

**Риски:**
- Planning V2 `planning_execution.py` (59K) — потенциально тяжёлый синхронный расчёт
- Нет performance-регрессионных тестов
- Нет SLA метрик в prometheus/метриках

### 2.2. Надёжность и consistency

| ID | Сценарий | Приоритет |
|----|----------|-----------|
| ASR-REL-1 | **Plan-fact reconciliation** — ни одна завершённая активность не теряется при перепланировании | High |
| ASR-REL-2 | **Readiness fusion** — при отсутствии HRV данных система не падает, а показывает data gap | High |
| ASR-REL-3 | **Синхронизация** — обрыв соединения с Garmin не портит частично загруженные данные | Medium |

**Как обеспечивается сейчас:**
- Evidence-first plan-fact reconciliation ✅
- read-only AI coach (не может испортить данные) ✅
- Session identity с ручным исправлением совпадений ✅
- Append-only версии плана ✅
- Mock/demo режимы без реальных данных ✅

**Риски:**
- Нет транзакционности на границе `sync → database` (SQLite не в WAL? проверить)
- Нет тестов на race condition (параллельный sync + coach)
- Нет автоматического восстановления после частичной синхронизации

### 2.3. Модифицируемость (Modifiability)

| ID | Сценарий | Приоритет |
|----|----------|-----------|
| ASR-MOD-1 | **Добавление AI-провайдера** — через конфиг, без изменения основного кода | High |
| ASR-MOD-2 | **Новый тип графика на дашборде** — добавление компонента без регрессии | Medium |
| ASR-MOD-3 | **Смена схемы данных** (новое поле в активности) — обратная совместимость | Medium |

**Как обеспечивается сейчас:**
- Абстрактный `BaseAIProvider` с фабрикой ✅
- signals_engine отделён от UI ✅
- FastAPI как contract layer между UI и domain ✅
- config/settings.py централизован ✅

**Риски:**
- Streamlit + web параллельно — двойная работа при изменении логики
- Нет API versioning (v1/v2) — разрыв при изменении контракта
- Нет feature flags для регрессии

### 2.4. Безопасность

| ID | Сценарий | Приоритет |
|----|----------|-----------|
| ASR-SEC-1 | **API-ключи** не должны появляться в логах, UI, git history | High |
| ASR-SEC-2 | **Self-hosted** — Basic Auth перед публичным доступом | High |

**Как обеспечивается сейчас:**
- .env не в git ✅
- UI скрывает поля ключей ✅
- Docker с Caddy + Basic Auth ✅
- .gitignore правильный ✅

**Риски:**
- Нет audit-лога доступа к данным
- Нет rate limiting на API (`/api/coach/chat`)
- plain HTTP в dev — перехват ключей в одной локальной сети

### 2.5. Deployability

| ID | Сценарий | Приоритет |
|----|----------|-----------|
| ASR-DEP-1 | **Одна команда** (`docker compose up`) поднимает весь стек | High |
| ASR-DEP-2 | **Обновление** без потери данных (SQLite в named volume) | High |

**Как обеспечивается сейчас:**
- Docker Compose + Dockerfile.api + Dockerfile.web ✅
- SQLite в named volume ✅
- `run_web.sh` для bare-metal ✅
- Self-hosted deployment execplan ✅

**Риски:**
- Нет healthcheck endpoint для orchestration
- Нет миграций схемы (alembic или аналоги)
- Нет backup/restore скриптов для SQLite

---

## 3. Тактики — что уже используется

ADD 3.0 оперирует тактиками. Вот какие **уже есть** в проекте:

| Категория | Тактика | Где в проекте |
|-----------|---------|---------------|
| **Availability** | Redundancy | Docker compose — несколько контейнеров |
| | Exception handling | try/except в sync, Garmin client |
| **Performance** | Scheduling | Инкрементальная синхронизация |
| | Caching | data_cache.py |
| | Async I/O | FastAPI async routes |
| **Security** | Authentication | Basic Auth в Caddy |
| | Secret management | .env файл |
| **Modifiability** | Abstract interfaces | BaseAIProvider, signals_engine |
| | Layers | api → models/services → data → db |
| | Separate interface from implementation | FastAPI contract → domain → data |
| **Testability** | Mock objects | MockAIProvider, demo_mode |
| | Isolation | Acceptance mode с temp DB |

### 3.1. Какие тактики стоит добавить

| Тактика | Где нужна |
|---------|-----------|
| **Heartbeat** | Healthcheck endpoint для Docker orchestration |
| **Ping/echo** | `/api/health` для мониторинга |
| **Active redundancy** | Подумать warm standby для long-running биллинга (пока не актуально) |
| **Transaction** | Для plan-fact reconciliation — атомарность нескольких записей |
| **State resynchronization** | После обрыва Garmin sync |
| **Rate limiting** | Для `/api/coach/chat` — защита от случайного runaway billing |
| **API versioning** | Когда будет внешний consumer API |

---

## 4. ATAM: Карта рисков и компромиссов (Tradeoffs)

### 4.1. Риски высокого приоритета

| Риск | Описание | Вероятность | Влияние | Митигация |
|------|----------|-------------|---------|-----------|
| **R1** | SQLite как единая точка отказа — contention при параллельном sync + coach + planning | Low сейчас → Medium при росте | Потеря данных | WAL mode, retry logic, рассмотреть SQLite concurrent access стратегию |
| **R2** | AI-provider latency — синхронный вызов блокирует UI | Medium | UX деградация | Timeout, fallback на Mock, кэширование частых запросов |
| **R3** | Нет API tests — рефакторинг models ломает api молча | Medium | Регрессия в web | Contract tests: FastAPI TestClient на каждый роутер |
| **R4** | Streamlit + web параллельно — забыли что-то починить в одном из двух | Medium | Баги на legacy surface | Чёткий EOL для Streamlit в ADR |

### 4.2. Архитектурные tradeoffs

| Решение | Выигрыш | Платим |
|---------|---------|--------|
| SQLite vs Postgres | Zero ops, портативность, простота backup'а | Нет конкурентного доступа, нет репликации |
| Streamlit как fallback | Быстрый прототип, живая логика | Двойная работа, путаница «где фича» |
| Multi AI-provider | Нет vendor lock-in | Сложность тестирования (5 провайдеров), blowing API budget |
| Planning V2 preview/confirm | Безопасность изменений | Сложность UI (два состояния: preview vs confirmed) |
| Все данные локально (SQLite) | Приватность, offline | Нет мульти-девайс синхронизации |

---

## 5. Conway's Law в контексте ai_trainer

Архитектура ai_trainer отражает способ разработки:

> **«Система, разрабатываемая роем агентов (Claude Code + Codex) через ExecPlans, будет иметь архитектуру, состоящую из хорошо изолированных, документированных модулей с сильной границей по данным, но слабой связностью через контракты.»**

Что это значит:

| Наблюдение | Хорошо | Плохо |
|------------|--------|-------|
| 60+ ExecPlans в docs/ | Отличная документация | ExecPlans живут дольше, чем нужно (мёртвый груз) |
| Сильная изоляция models/* | Можно менять модуль без страха | Нет cross-cutting concerns (метрики, logging, tracing) |
| README/CLAUDE.md/AGENTS.md | Много точек входа для агента | Тройное дублирование правил |
| .agent/PLANS.md | Чёткий формат спецификации | ExecPlan может устареть, если агент его не обновит |

---

## 6. Что добавить в следующие итерации ADD

### 6.1. Недостающие ADR

Нужно записать причины ключевых решений:

| ADR | Тема | Проблема |
|-----|------|----------|
| ADR-0002 | **SQLite как primary store** | Почему не Postgres? Какие ограничения приняли? |
| ADR-0003 | **Signals engine как единый источник** | Альтернатива: каждый модуль сам читает данные. Почему нет? |
| ADR-0004 | **Read-only AI coach** | Коуч не может менять план — безопасность vs autonomy tradeoff |
| ADR-0005 | **ExecPlan-driven development** | Почему SpecDD/ExecPlan, а не Issues/PRs в одиночку? |
| ADR-0006 | **Append-only planning versions** | Git-style vs мутация строки. Почему дороже сохранять все версии? |
| ADR-0007 | **Mock AI для demo/acceptance** | Почему isolation важнее, чем fidelity тестов на реальном AI? |

### 6.2. Что проверить архитектурными тестами

ADD требует *проверить предположения*. Вот какие:

1. **Load test dashboard API** — `/api/today/snapshot` с 3 годами данных: < 2 сек?
2. **Plan-fact reconciliation consistency** — параллельный вызов sync + get_plan не deadlock?
3. **AI coach tool timeout** — один инструмент завис, остальные работают?
4. **SQLite WAL contention** — чтение во время записи sync не блокируется?

### 6.3. Какие ASR записать явно

Самый быстрый win — превратить неявные ASR выше (раздел 2) в машиночитаемый формат рядом с кодом:
- Файл `docs/architecture/asr_catalog.md` с таблицей ASR
- Связать каждый ключевой модуль с его ASR в docstring

---

## 7. Итог: что сделать прямо сейчас

| # | Действие | Затраты | Эффект |
|---|----------|---------|--------|
| 1 | Записать ADR на SQLite | 20 мин | Поймём границы текущего хранилища |
| 2 | Записать ADR на read-only coach | 15 мин | Зафиксируем безопасность vs функциональность |
| 3 | Написать load-тест на dashboard | 1 час | Узнаем, держит ли SQLite 3 года данных |
| 4 | Написать health endpoint + docker healthcheck | 30 мин | Docker-compose без головной боли |
| 5 | Создать asr_catalog.md | 30 мин | Единая точка truth для quality attributes |
| 6 | Оценить EOL Streamlit и записать в ADR-0001 | 15 мин | Чёткое направление для агентов |

---

## Приложение: сводная карта «ASR → Модуль → Тактика»

| ASR | Модуль | Тактика | Статус |
|-----|--------|---------|--------|
| PERF-1 (дашборд < 2 сек) | today_snapshot.py | Caching (data_cache) | 🟡 Нет TTL |
| PERF-2 (coach latency) | ai_coach_runtime.py | Async streaming | ✅ |
| PERF-3 (Garmin sync) | services/sync.py | Incremental sync | ✅ |
| REL-1 (plan-fact no loss) | plan_actual_reconciliation.py | Evidence-first, append-only | ✅ |
| REL-2 (readiness graceful) | readiness.py | Data gap detection | ✅ |
| MOD-1 (add provider) | ai_providers.py | Abstract interface + factory | ✅ |
| SEC-1 (keys in logs) | — | env, not in UI | ✅ |
| DEP-1 (docker up) | — | docker-compose | ✅ |
