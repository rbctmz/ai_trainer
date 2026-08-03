# AI Trainer — Web Migration Spec
**Версия:** 0.1 · **Дата:** 2026-06-27  
**Статус:** Historical baseline / superseded
**Автор:** rbctmz

> Документ сохраняет исходный снимок миграции и не является инструкцией по
> текущему состоянию продукта. Действующая политика — в
> [`ADR-0001`](architecture/adr_0001_web_primary_ui.md), текущие точки входа —
> в [`docs/README.md`](README.md) и корневом [`README.md`](../README.md).

---

## 1. Контекст и цель

AI Trainer — персональный тренировочный кокпит для триатлетов, велосипедистов и бегунов. Текущая реализация на Streamlit даёт работающую логику (Banister CTL/ATL/TSB, HRV-анализ, AI-коучинг с мульти-провайдерностью, planning execution), но ставит потолок на UX: Streamlit читается как "инструмент разработчика", а не продукт который хочется открывать каждое утро.

**Цель миграции:** сохранить весь Python-бэкенд и бизнес-логику, заменить Streamlit-фронт на Next.js, выйти на уровень UX сопоставимый с IntervalCoach и Bloks (оба на Next.js).

**Не цель:** переписать бизнес-логику, менять модели данных, менять AI-провайдеры.

---

## 2. Текущее состояние

### Что есть и работает
| Слой | Модуль | Статус |
|---|---|---|
| Данные | `data/garmin_client.py`, `garth_client.py` | Работает, прямой коннект к Garmin |
| БД | `data/database.py` — SQLite | Работает |
| Метрики | `models/banister.py` — CTL/ATL/TSB | Работает |
| HRV | `models/hrv_analyzer.py` | Работает, изолированно |
| AI | `models/ai_providers.py` — 5 провайдеров | Работает, уникальное преимущество |
| Planning | `models/planning_execution.py`, `training_planner.py` | Работает, 60K+60K строк |
| State | `state/manager.py` — StateManager | Работает |
| Demo/Acceptance | `services/demo_mode.py`, `acceptance_mode.py` | Работает |

### Технический долг (не блокирует миграцию)
- `ui/pages/planning.py` — 164K, монолит
- `ui/pages/dashboard.py` — 56K, монолит  
- `hrv_analyzer.py` + `sleep_metrics.py` — разрознены, нет единого signals engine
- Лейблы разработчика в UI ("Компактный план без длинных workout descriptions")

---

## 3. Целевая архитектура

```
ai_trainer/
├── app.py                    # Streamlit — остаётся как fallback/dev
├── api/                      # НОВОЕ: FastAPI бэкенд
│   ├── main.py               # FastAPI app, CORS, роутинг
│   ├── routers/
│   │   ├── dashboard.py      # GET /api/dashboard/summary
│   │   ├── coach.py          # POST /api/coach/chat, GET /api/coach/history
│   │   ├── planning.py       # GET/POST /api/planning/*
│   │   ├── activities.py     # GET /api/activities/*
│   │   ├── hrv.py            # GET /api/hrv/*
│   │   └── auth.py           # POST /api/auth/garmin
│   └── deps.py               # Shared dependencies (StateManager, DB)
├── web/                      # НОВОЕ: Next.js фронт
│   ├── app/                  # Next.js App Router
│   │   ├── layout.tsx
│   │   ├── page.tsx          # → redirect /dashboard
│   │   ├── dashboard/
│   │   ├── coach/
│   │   ├── planning/
│   │   ├── activities/
│   │   ├── hrv/
│   │   └── sleep/
│   ├── components/
│   │   ├── ui/               # shadcn/ui компоненты
│   │   ├── charts/           # Recharts обёртки
│   │   ├── dashboard/        # DashboardMetrics, WeekStrip, TodayCard
│   │   ├── coach/            # ChatMessages, InputBar, ContextSidebar
│   │   └── planning/         # PlanSetup, WeekTable, ForecastChart
│   ├── lib/
│   │   ├── api.ts            # API клиент (fetch обёртки)
│   │   └── types.ts          # TypeScript типы
│   └── package.json
├── models/                   # БЕЗ ИЗМЕНЕНИЙ
├── data/                     # БЕЗ ИЗМЕНЕНИЙ
├── services/                 # БЕЗ ИЗМЕНЕНИЙ
└── state/                    # БЕЗ ИЗМЕНЕНИЙ
```

### Стек

**Фронтенд:**
- Next.js 14 (App Router)
- TypeScript
- Tailwind CSS
- shadcn/ui — компонентная библиотека
- Recharts — графики
- SWR — data fetching и кэш

**Бэкенд (новый слой поверх существующего):**
- FastAPI
- Pydantic v2 — схемы ответов
- Uvicorn

**Dev:**
- Turbo (монорепо)
- ESLint + Prettier
- Vitest — unit тесты фронта

---

## 4. API контракт

### Dashboard

```
GET /api/dashboard/summary
```

```json
{
  "date": "2026-06-27",
  "today": {
    "state_label": "Сильная усталость",
    "tone": "danger",
    "readiness": 44,
    "tsb": -25.5,
    "ctl": 22.8,
    "atl": 38.1,
    "hrv": 32.0
  },
  "workout": {
    "title": "Лёгкое восстановление",
    "tss": 16,
    "sport": "вело",
    "duration_minutes": 60,
    "status": "planned"
  },
  "week": {
    "planned_tss": 99,
    "actual_tss": 329,
    "remaining_tss": 0,
    "forecast_tss": 329,
    "status": "цель недели закрыта"
  },
  "next_days": [
    {
      "date": "2026-06-27",
      "label": "Сб",
      "tss": 0,
      "sport": "—",
      "status": "today"
    }
  ],
  "plan": {
    "title": "Триатлон Олимпийка",
    "event_date": "2026-08-22",
    "peak_tss": 400,
    "total_tss": 1591,
    "status": "active"
  }
}
```

### Coach

```
POST /api/coach/chat
{
  "message": "Когда мне можно тренироваться интенсивно?",
  "chat_id": "uuid",
  "context_days": 30,
  "provider": "claude"
}

→ Server-Sent Events (streaming)
data: {"type": "token", "content": "Исходя из..."}
data: {"type": "tool_call", "name": "load_activities", "status": "done"}
data: {"type": "done", "message_id": "uuid"}
```

```
GET /api/coach/history
→ { "chats": [{ "id": "uuid", "title": "...", "date": "..." }] }

GET /api/coach/history/{chat_id}
→ { "messages": [{ "role": "user|assistant", "content": "...", "timestamp": "..." }] }
```

### Planning

```
GET /api/planning/status
→ { "checkpoint": {...}, "next_days": [...], "weekly_tss": {...} }

GET /api/planning/overview
→ { "has_plan": true, "goal": {...}, "roadmap": {...}, "form_projection": {...} }

GET /api/planning/week-by-week
→ { "state": "available", "weeks": [...], "chart": {...} }

POST /api/planning/build
{ "goal_type": "triathlon", "distance": "olympic", "event_date": "2026-08-22", "available_hours": 12, "available_days": ["mon","tue","wed","thu","fri","sat"] }
→ { "plan_id": "uuid", "weeks": [...], "forecast": {...} }
```

### HRV

```
GET /api/hrv/summary?days=30
→ { "latest": {...}, "trend": [...], "baseline": {...}, "signals": [...] }
```

---

## 5. Страницы и компоненты

### 5.1 Dashboard

**Задача страницы:** за 5 секунд ответить на вопрос "как я сегодня и что делать".

**Компоненты:**
- `StatusRow` — 4 карточки: Состояние/Readiness/CTL/TSB. Состояние занимает 2 колонки, имеет цветовую кодировку (danger/warning/success/neutral)
- `TodayCard` — тренировка сегодня с TSS, видом спорта, кнопкой "Спросить коуча"
- `WeekCard` — факт/план TSS, прогресс-бар, статус недели
- `WeekStrip` — 7 дней вперёд, карточки с датой/TSS/спортом, цветовое выделение today/planned/done/rest
- `ForecastChart` — CTL/ATL/TSB за 8 недель (Recharts LineChart)
- `FooterRow` — дата старта, кнопки "Прогноз к старту" / "Открыть план"

**Поведение:**
- Данные через SWR с revalidation каждые 5 минут
- При TSB < −20 показывать предупреждение в TodayCard
- При отсутствии плана — CTA "Собрать план" вместо WeekStrip

### 5.2 Coach

**Задача страницы:** разговор с тренером который знает все твои данные.

**Компоненты:**
- `ContextSidebar` — сигналы (TSB/Readiness/HRV/CTL/ATL), выбор модели, история чатов
- `ChatMessages` — пузыри с аватарами, tool_call индикаторы под ответом AI
- `SuggestionChips` — 3 контекстных подсказки, исчезают после первого сообщения
- `InputBar` — textarea (Enter = отправить, Shift+Enter = перенос), кнопка Отправить

**Поведение:**
- Стриминг через SSE
- Tool calls отображаются как inline индикаторы: "Загружены данные за 30 дней"
- Подсказки генерируются на основе текущего состояния (TSB, события)
- История персистится в localStorage + синкается с бэкендом

### 5.3 Planning

**Задача страницы:** собрать план к цели, скорректировать выполнение, экспортировать.

**Режимы (табы):** Собрать план / Скорректировать / Экспорт

**Компоненты (режим "Собрать план"):**
- `CurrentStatusPanel` — CTL/ATL/TSB/Состояние, раскрываемый "Контекст нагрузки"
- `GoalSelector` — тип цели (триатлон/вело/бег/плавание), дистанция, дата
- `ConstraintsPanel` — часов в неделю (слайдер), доступные дни (мультиселект), после пропуска
- `ForecastChart` — прогноз CTL/ATL/TSB до старта (интерактивный)
- `BuildButton` — "Собрать план" → loading → "Plan Ready" → переход в Экспорт

**Поведение:**
- History-based автонастройка: подставляет среднее/лучшее TSS из истории
- Локальная перепланировка без полной пересборки
- Реалтайм пересчёт прогноза при изменении параметров (debounce 500ms)

### 5.4 HRV

**Задача страницы:** понять тренд восстановления и качество адаптации.

**Компоненты:**
- `HRVMetrics` — RMSSD/HRV4T/DFA α1/базовая линия
- `TrendChart` — 30-дневный тренд с зонами (оптимум/норма/подавление)
- `SignalList` — список активных сигналов с severity
- `RecoveryInsight` — интерпретация тренда простым языком

---

## 6. Фазы реализации

### Фаза 0 — Скелет (1–2 дня) ✅
- [x] Создать `api/` с FastAPI (`api/main.py`, `deps.py`, `routers/dashboard.py`)
- [x] Обернуть `_build_dashboard_v2_summary()` в `GET /api/dashboard/summary` (headless StateManager поверх dict, без st.session_state)
- [x] Создать `web/` с Next.js 14 (App Router) + Tailwind (дизайн-токены из `docs/redesign_guide`; shadcn отложен — компоненты на Tailwind)
- [x] Dashboard страница с реальными данными через API (SWR, прокси `/api/*` → FastAPI)
- [x] `run_web.sh` — запускает FastAPI + Next.js dev
- Проверено: `npm run build` зелёный, `pytest tests/smoke` = 205 passed, E2E через прокси отдаёт реальные данные из `ai_trainer.db`.

### Фаза 1 — Основные страницы (1–2 недели) ✅
- [x] Coach страница со стримингом (SSE; `POST /api/coach/chat` + `/history`; переиспользует `models/ai_coach_runtime` и `ChatManager`; «симулированный» стриминг поверх синхронных провайдеров — как в Streamlit)
- [x] HRV страница (`GET /api/hrv/summary`; RMSSD/recovery/baseline + inline-SVG тренд)
- [x] Activities страница (`GET /api/activities`; итоги + таблица)
- [x] Навигация между страницами (`web/components/Nav.tsx`, активная подсветка)
- [x] Адаптация под мобильный (основные сценарии: responsive-гриды, скролл-навигация, таблица прячет колонки)
- Проверено: `npm run build` зелёный (4 страницы), `pytest tests/smoke` = 210 passed (+`test_api_phase1.py`), HTTP-прогон coach(SSE)/hrv/activities на реальной БД. Провайдер по умолчанию — DeepSeek; Recharts отложен (тренд на inline-SVG, без новых npm-зависимостей).

### Фаза 2 — Planning (1–2 недели) ✅
- [x] Режим «Собрать план» + прогноз: `GET /api/planning/status`, `POST /api/planning/build` (headless поверх `training_planner` + `BanisterModel.simulate_variable_load`; маппинг EN→RU целей/дистанций/дней). `persist=true` сохраняет checkpoint → план виден на Дашборде и в Коуч-сайдбаре.
- [x] Режим «Скорректировать выполнение»: `GET /api/planning/reconciliation`, `POST /api/planning/adjust` (`build_execution_reconciliation_rows` → `build_execution_plan_adjustment` → `rebuild_goal_plan_with_adjustment`). Редактируемые строки план/факт, пересборка + новый прогноз.
- [x] Режим «Экспорт» — FIT/TCX/ICS через бэкенд: `GET /api/planning/plan`, `/export/ics`, `/export/workout/{i}?fmt=tcx|fit_csv|tcx_activity` (переиспользует `fit_export`/`tcx_export`/`tcx_activity_export`/`create_ics_from_daily`).
- [x] Фронт `web/app/planning/page.tsx`: при активном checkpoint по умолчанию
  открывает reader-вкладки «Обзор / Недели / Выполнение»; «Изменить план»,
  «Скорректировать» и «Экспорт» остаются явными действиями. Обзор показывает
  цель, roadmap фаз/A-B-C и факт/прогноз CTL/ATL/TSB; недельный reader объединяет
  target/fact, внеплановую нагрузку, дни и leaf-сессии из одного bounded
  provider-free API-снимка. Без активного плана открывается прежний onboarding.
- Проверено: build зелёный (9 страниц), smoke 216 passed (+`test_api_planning.py`), HTTP-прогон всех эндпоинтов на реальной БД; связность persist→Дашборд подтверждена в браузере.

### Фаза 3 — Полировка (1 неделя) ✅
- [x] Sleep страница: `GET /api/sleep/summary` + `web/app/sleep/page.tsx` (метрики, фазы сна, bar-тренд).
- [x] Onboarding (первый запуск без данных): welcome-блок на дашборде с CTA «Синк» / «Демо».
- [x] Demo mode в веб-версии: изолированная demo-БД (`*_demo.db`, реальная не трогается), `POST /api/demo/seed`/`clear`, флаг `?demo=1` через `get_database`, переключатель в Nav (`lib/api.ts::withDemo`).
- [x] Кнопка синхронизации Garmin: `POST /api/sync` (обёртка `services/sync.py`, auth из .env) + кнопка на дашборде.
- [x] Живой стриминг коуча: `stream=True` для DeepSeek/OpenAI (`api/coach_service.stream_tokens`), по-токенный SSE + `replace` после резолва инструментов; mock остаётся на симуляции.
- [x] Dev-лейблы: веб-поверхность новая, Streamlit-лейблов в ней нет by construction.
- Фикс: headless `StateManager` теперь поверх attribute-dict (`SessionDict`) — поддерживает запись (нужно для demo seeding).
- Проверено: build зелёный (10 страниц), smoke 223 passed (+`test_api_phase3.py`), demo-изоляция проверена (реальная БД нетронута). Требуют живого окружения: реальный синк Garmin (creds/сеть, возможен 429) и по-токенный стрим DeepSeek (ключ).

### Фаза 4 — После MVP
- [ ] Деплой (Railway / Fly.io / VPS)
- [ ] Auth (если многопользовательский режим)
- [ ] PWA (иконка на домашнем экране)

---

## 7. Решения по спорным вопросам

| Вопрос | Решение | Причина |
|---|---|---|
| Streamlit убрать сразу? | Нет, оставить как fallback | Риск — оставить рабочий инструмент без замены |
| Монорепо или отдельный репо для web? | Монорепо, папка `/web` | Проще шарить типы и деплоить вместе |
| GraphQL или REST? | REST | Проще, вайбкодинг работает лучше |
| SSR или CSR? | CSR + SWR | Данные персональные, SEO не нужен |
| БД мигрировать с SQLite? | Нет, SQLite остаётся | Нет причины менять, работает |
| State management? | SWR + React Context | Без Redux — избыточно для этого масштаба |

---

## 8. Риски

| Риск | Вероятность | Митигация |
|---|---|---|
| Planning страница слишком сложна для переезда | Высокая | Переезжать последней, Streamlit как fallback |
| StateManager привязан к Streamlit session_state | Средняя | Создать `state/api_state.py` без st.session_state |
| Стриминг AI через SSE сложнее чем st.write_stream | Средняя | FastAPI + SSE хорошо задокументированы |
| Вайбкодинг Next.js — TypeScript ошибки | Низкая | Использовать shadcn/ui + строгие типы |

---

## 9. Определение готовности (DoD)

MVP считается готовым когда:
- [ ] Dashboard показывает реальные данные (CTL/ATL/TSB/HRV/план недели)
- [ ] Coach принимает сообщения и стримит ответы
- [ ] Planning позволяет собрать план и посмотреть прогноз
- [ ] Работает на мобильном (Chrome iOS/Android)
- [ ] Нет Streamlit-лейблов разработчика в UI
- [ ] `npm run build` проходит без ошибок

---

## 10. Следующий конкретный шаг

```bash
# В корне репозитория
mkdir api web
cd api && pip install fastapi uvicorn pydantic
# Создать api/main.py с первым эндпоинтом /api/dashboard/summary
# который вызывает существующий _build_dashboard_v2_summary()

cd ../web
npx create-next-app@latest . --typescript --tailwind --app --no-src-dir
npx shadcn-ui@latest init
```

После этого — Dashboard страница с реальными данными. Всё остальное строится поверх.
