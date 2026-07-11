# ExecPlan: экран «Сегодня» — ежедневная web-поверхность агентного контура (issue #158)

## Зачем это нужно (для человека, который видит репозиторий впервые)

AI Trainer — тренировочный кокпит на данных Garmin: FastAPI-бэкенд (`api/`) поверх общей Python-логики (`models/`, `data/`, `services/`) и Next.js-фронтенд (`web/`). В проекте работает «агентный контур»: аналитика считает готовность атлета к нагрузке (readiness), детерминированный «salience-gate» сверяет её с плановыми тренировками, и при конфликте контур создаёт предложение снизить нагрузку, которое пользователь явно подтверждает или отклоняет. Все исходы (тишина / недостаток данных / конфликт) пишутся в журнал `recovery_decisions` (SQLite, `data/database.py`).

Проблема: продуктовая форма контура — журнал на странице `/decisions`. Утренний вопрос атлета «что мне сегодня делать?» не имеет поверхности: корень сайта `/` редиректит на `/dashboard` — сетку метрик. Этот план добавляет экран `/today`, который отвечает на утренний вопрос одним взглядом: вердикт контура, сессия дня, объяснение готовности на проверяемых числах и — только при конфликте — карточка предложения с подтверждением.

После реализации: пользователь открывает `http://localhost:3000/` и попадает на `/today`. В спокойный день видит «План в силе», сессию дня и раскрываемое объяснение готовности. В день конфликта — карточку «как есть vs рекомендация» с кнопками подтверждения. При нехватке данных — нейтральную строку с причиной. Без активного плана — приглашение на `/planning`.

Ключевой дизайн-принцип: в состоянии тишины экран почти пуст, и это осознанно — «молчание — дефолт» из философии контура должно быть видно буквально.

## Термины

- **Readiness (готовность)** — число 0–100 из `models/readiness.py::compute_readiness_today`: fusion сна, HRV, пульса покоя, Garmin readiness и баланса нагрузки (TSB) относительно личных 28-дневных базлайнов. Возвращает также `status` (low/limited/ready/unknown), `confidence`, `drivers` (топ-факторы с evidence-строками) и `factors`.
- **Canonical snapshot** — JSON-контракт готовности из `api/readiness_snapshot.py::build_readiness_snapshot`. Единственный источник числа готовности для всех поверхностей (урок багов #134/#152: пересчёт на своём окне даёт расхождения между экранами). Новая поверхность обязана читать его, а не считать сама.
- **Salience-gate / отчёт конфликтов** — `api/readiness_conflicts.py::build_readiness_conflict_report`: сверяет готовность с плановыми сессиями горизонта (база 3 дня + расширение до ближайшей quality-сессии в пределах 7). Отдаёт `silence`/`data_gap`/`conflicts`, `reason`, `sessions_evaluated`.
- **RecoveryReplanLoop** — `api/recovery_replan_loop.py::run_recovery_replan_loop`: headless-контур. Прогоняет gate, идемпотентно пишет исход в `recovery_decisions` (fingerprint UNIQUE, #154) и при конфликте создаёт ровно одно активное предложение в `coach_proposals` (дедуп по `active_key`, #156). Уже вызывается на каждое сообщение коуча (SSE, `api/routers/coach.py`).
- **Proposal / предложение** — строка `coach_proposals` со статусной машиной pending → applying → approved / rejected / failed → rolled_back. Подтверждение и откат — существующие эндпоинты `api/routers/decisions.py` (`/api/decisions/proposals/{id}/approve|reject|rollback`).
- **Planning checkpoint** — сериализованный снимок активного плана (`models/planning_checkpoints.py`), источник плановых сессий.

## Архитектурное решение

`GET /api/today` (новый роутер `api/routers/today.py`) собирает ответ из четырёх готовых источников и не содержит новой бизнес-логики:

1. `run_recovery_replan_loop(db)` — вердикт gate + журналирование + актуальное предложение. Осознанное решение: GET-эндпоинт **вызывает** контур (write-on-read). Обоснование: вызов идемпотентен по построению (fingerprint-дедуп решений #154, active_key-дедуп предложений #156), тот же вызов уже происходит на каждое сообщение коуча, а утренний экран обязан быть самодостаточным — атлет не должен открывать чат, чтобы контур отработал. Альтернатива (читать только журнал) оставляла бы экран пустым до первого чата за день и не давала кнопок подтверждения.
2. `build_readiness_snapshot(db)` — каноническое число готовности, drivers, факторы с evidence, confidence, TSB. В ответе `readiness_source: "canonical_snapshot"`.
3. `report["sessions_evaluated"]` с `days_until == 0` — сессия дня (имя, роль, TSS, спорт). Роль-лейблы уже локализованы в `models/readiness_conflicts.py::ROLE_LABELS_RU`.
4. `db.get_activities(3)` — one-liner факта за вчера (число активностей, суммарные минуты и TSS, виды спорта).

Состояние экрана (поле `state`) вычисляется приоритетным каскадом:

    no_plan   — нет активного planning checkpoint (db.get_latest_planning_checkpoint() пуст);
    data_gap  — report["data_gap"] истинен;
    conflict  — исход контура "conflict" И существует актуальное предложение
                (pending — кнопки confirm/reject; applying — бейдж «применяется»);
    silence   — всё остальное (включая конфликт, уже закрытый пользователем сегодня:
                предложение в терминальном статусе означает, что решение принято,
                и экран возвращается к спокойному виду с reason из журнала).

Web: новая страница `web/app/today/page.tsx`; `web/app/page.tsx` меняет `redirect("/dashboard")` на `redirect("/today")`; в `web/components/Nav.tsx` пункт «Сегодня» первым. Карточка предложения — существующий `web/components/ui/ProposalCard.tsx` без изменений (он уже умеет recovery_replan: preview с current/recommended session, кнопки, обработка ошибок). Типы ответа — аддитивно в `web/lib/types.ts`.

Demo-режим наследуется бесплатно: `api/deps.py::get_database` уже маршрутизирует `?demo=1` в отдельную демо-БД, а `web/lib/api.ts::withDemo` добавляет параметр ко всем fetch. Контур в demo-БД пишет в неё же — изоляция сохраняется.

## Контракт ответа GET /api/today

    {
      "date": "2026-07-11",                # as-of дата gate-отчёта
      "state": "silence|conflict|data_gap|no_plan",
      "reason": "человекочитаемая строка из gate/журнала",
      "readiness": {                        # null при no_plan-коротком пути НЕ является;
        "score": 75, "status": "ready",     # snapshot строится всегда, кроме пустой БД
        "confidence": 0.8,
        "drivers": [...],                   # как в snapshot: label/evidence/direction
        "factors": [...],                   # факторы с evidence-строками
        "tsb": {"ctl":…, "atl":…, "tsb":…, "window_days":90},
        "stale": false, "reason": "…"
      },
      "readiness_source": "canonical_snapshot",
      "session": {                          # null, если на сегодня нет плановой сессии
        "date": "2026-07-11", "name": "…", "role": "quality",
        "role_label": "качественная", "tss": 60, "sport_label": "вело",
        "is_key": true                      # роль quality/long
      },
      "pending_proposal": { … } | null,     # форма CoachProposal как в /api/decisions
      "yesterday": {                        # null, если вчера активностей нет
        "activities": 2, "minutes": 76, "tss": 37, "sports": ["cycling"]
      },
      "loop_outcome": "silence|data_gap|conflict",  # сырой исход контура для отладки
      "operational_state": { … }            # build_operational_state, как в других роутерах
    }

`readiness` может быть `null` только если snapshot вернул `score: null` (пустая/недоступная БД) — тогда `state` будет `data_gap` или `no_plan` и UI не рисует блок готовности.

## Milestone 1 — спецификация поведением (тесты)

Создать `tests/smoke/test_api_today.py` по образцу `tests/smoke/test_api_dashboard.py`: вызывать функцию роутера напрямую с `Database(str(tmp_path / "x.db"))`, без сети и Garmin. Данные сеются хелперами: `db.save_planning_checkpoint(...)` для плана (см. фикстуры в `tests/smoke/test_recovery_replan_loop.py` — там уже есть построение checkpoint с session_templates ролей), `db.save_sleep_data`/`save_hrv_data`/`save_daily_health` для готовности.

Сценарии (Given/When/Then из issue #158):

- пустая БД → `state: "no_plan"`, `has`-поля не падают, `operational_state.status == "empty"`;
- план есть, recovery-данных нет → `state: "data_gap"`, `reason` непустой, `pending_proposal is None`;
- план + здоровые данные, сессия дня recovery/easy при ready → `state: "silence"`, `session` заполнен, `readiness_source == "canonical_snapshot"`, `readiness["score"]` совпадает с `build_readiness_snapshot(db)["score"]`;
- план с quality-сессией сегодня + плохие данные (низкий сон/HRV/высокий RHR) → `state: "conflict"`, `pending_proposal` не None и связан с журналом; повторный вызов не создаёт второй proposal (идемпотентность через #154/#156);
- вчерашняя активность в БД → `yesterday` агрегирует минуты/TSS.

Тесты обязаны падать до реализации (роутера нет) и проходить после.

## Milestone 2 — API-роутер

`api/routers/today.py`: функция `today_view(db=Depends(get_database))` по архитектуре выше; регистрация в `api/main.py` (импорт + `app.include_router(today.router)`). Роутер тонкий: никакой математики, только выбор состояния, проекция полей и агрегация «вчера» (sum/count по DataFrame). Ошибки чтения БД не роняют ответ: как в соседних роутерах, деградация в `data_gap`/`no_plan` с reason.

Проверка: `ai_trainer_env/bin/python -m pytest tests/smoke/test_api_today.py -q` зелёный; `python -m pytest tests/smoke -q` целиком зелёный (база: 465 passed на fe37a70).

## Milestone 3 — web-страница

`web/app/today/page.tsx` (client component, SWR на `/api/today`):

- шапка: человекочитаемая дата (`Intl.DateTimeFormat("ru-RU", { weekday: "long", day: "numeric", month: "long" })`);
- вердикт: иконка+заголовок по `state` (silence → «План в силе», conflict → «Есть предложение», data_gap → «Данных недостаточно», no_plan → «Плана нет») + `reason` вторичным текстом;
- карточка сессии дня (`session`): имя, `role_label`, TSS, спорт; бейдж «ключевая» при `is_key`; при `session: null` в silence — строка «Сегодня по плану отдых»;
- раскрытие evidence (`<details>`): drivers + факторы из `readiness` («HRV 41 (+17% к базе)…»), confidence; рендерится во всех состояниях, где `readiness` не null;
- при `state == "conflict"`: `ProposalCard` с `onConfirmed`/`onCancelled`, после действия — `mutate()` SWR (экран сам перейдёт в silence);
- при `no_plan`: ссылка-приглашение на `/planning`;
- строка «Вчера: N активностей · M мин · K TSS» при наличии `yesterday`;
- `web/app/page.tsx`: `redirect("/today")`; `web/components/Nav.tsx`: пункт `{ href: "/today", label: "Сегодня" }` первым.

Проверка: `npm run lint` и `npm run build` в `web/` зелёные; вручную через dev-сервер (`./run_web.sh`) открыть `/`, увидеть редирект на `/today` и живое состояние текущего дня; число готовности на `/today` равно числу на `/dashboard`.

## Milestone 4 — финализация

Обновить этот ExecPlan по факту (living document), прогнать полный смоук + Ruff (`ruff check api tests`), опубликовать ветку `claude/issue-158-today-screen`, открыть draft PR с `Closes #158`.

## Out of scope (повторяет issue)

Лента план-vs-факт (adherence), блок «агент за месяц», shadow-прогноз качества (Issue D), push/scheduler, events A/B/C UI, изменения самого дашборда, изменения Streamlit.

## Прогресс

- [x] ExecPlan написан
- [ ] Milestone 1: tests/smoke/test_api_today.py красный → зелёный
- [ ] Milestone 2: api/routers/today.py + регистрация, смоук зелёный
- [ ] Milestone 3: web /today + nav + redirect, lint/build зелёные, ручная проверка
- [ ] Milestone 4: полный смоук + ruff, ExecPlan финализирован, draft PR открыт

## Журнал решений

- 2026-07-11: GET с write-on-read (вызов run_recovery_replan_loop) принят осознанно — идемпотентность гарантирована #154/#156, самодостаточность утреннего экрана важнее REST-пуризма; прецедент — тот же вызов на каждом сообщении коуча.
- 2026-07-11: конфликт с уже закрытым сегодня предложением показывается как silence с reason из журнала — решение пользователя принято, возвращать его в тревожное состояние нельзя.
- 2026-07-11: readiness в ответе — проекция build_readiness_snapshot без изменений контракта snapshot; поверхность не добавляет своих вычислений.
