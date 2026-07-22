# Intervals-primary + локальный Docker-handoff: другой атлет запускает AI Trainer на своих данных

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

This document must be maintained in accordance with `.agent/PLANS.md` (the ExecPlan authoring rules), located at the repository root.

## Purpose / Big Picture

После завершения UI-консолидации (`docs/ui_consolidation_beta_execplan.md`) интерфейс готов к бете. Остаётся настоящий продуктовый барьер: **сейчас AI Trainer может запустить на своих данных только владелец с аккаунтом Garmin.** Весь синк (`services/sync.py::sync_garmin_data`) требует Garmin-авторизации; без неё локальная база пуста.

Цель — чтобы **технический атлет с аккаунтом Intervals.icu (любое устройство) мог: склонировать репозиторий, задать свой Intervals-токен, синхронизировать активности и — задав цель/часы/дни — построить и увидеть СВОЙ план, без Garmin.** Intervals.icu — первичный источник, Garmin — вторичный/опциональный.

Центральный инженерный вопрос этого плана — **НЕ получение данных из API** (Intervals REST это умеет: activities, wellness, календарь, external IDs). Центральный вопрос — **честная граница `provider data → canonical activity → planning`**: как провайдерская активность становится нашей канонической активностью с честной идентичностью, провенансом и TSS-политикой, не ломая существующие инварианты проекта и не смешиваясь с данными другого источника. Именно этот слой контракта — суть работы; выкачка из API вторична.

Наблюдаемый результат (сценарий приёмки), поправленный против первой редакции плана: «нажал синк → увидел план» — НЕВЕРНО в один шаг. Синк даёт активности и CTL/ATL; план требует явного онбординга (цель, дистанция, часы, доступные дни; для event-goal — подтверждённая A-гонка). Поэтому честный сценарий — двухступенчатый: (1) с одним Intervals-токеном синк наполняет канонические активности и появляются CTL/ATL; (2) тестер проходит онбординг параметров планирования и строит первый план, который видит на `/planning` и `/today`.

Термины простым языком:

- **источник данных** — откуда приходят активности и wellness (HRV/сон/пульс покоя). Сейчас первичный — Garmin; цель — Intervals.icu.
- **каноническая активность** — наша внутренняя запись активности в таблице `activities`, с нашим TSS (`tss` + `tss_method`), отдельной провайдерской нагрузкой (`source_tss`) и — после этого плана — провенансом (`source`, `provider_activity_id`, `external_id`).
- **provider_tss / source_tss** — нативная нагрузка провайдера (Garmin `trainingLoad`, Intervals `icu_training_load`). Проект СПЕЦИАЛЬНО хранит её отдельно и НИКОГДА не подмешивает в `tss` (`docs/activity_tss_methodology.md:58`).
- **cursor (курсор синка)** — по какую дату уже синхронизирован конкретный домен данных (активности отдельно от wellness), чтобы инкрементальный синк не переспрашивал всё заново.
- **wellness** — суточные HRV/сон/пульс покоя (Intervals: `/api/v1/athlete/{id}/wellness`).

## Progress

- [x] (2026-07-22) Разведка + ревью (владелец, «Request changes» на первую редакцию). Подтверждены 5 блокеров против кода: TSS-контракт, идентичность активности, «синк ≠ план», Garmin-специфичный sync-контур, wellness-mapping. См. `Surprises & Discoveries`.
- [x] (2026-07-22) План переструктурирован под M0–M5 (контракт данных вынесен в M0 перед адаптером). Issues НЕ заведены — по указанию «сначала только ExecPlan»; заводятся после принятия этой редакции.
- [ ] РЕШЕНИЕ ВЛАДЕЛЬЦА (принято на ревью): вертикальный M1 (активности→нагрузка→план) вместо полного прохода; wellness — отдельным срезом (M4). Открытым остаётся объём M0-ADR (см. `Decision Log`).
- [ ] M0: контракт приёма активности — identity/provenance, TSS-политика, cursor-семантика, дедуп/приоритет источников (ADR + миграция схемы).
- [ ] M1: Intervals-адаптер → канонические активности → SQLite, без Garmin; идемпотентность и coexistence (Garmin↔Intervals) доказаны тестами. Заканчивается на «активности и CTL/ATL появились».
- [ ] M2: онбординг параметров планирования → первый план (честный «увидел свой план»).
- [ ] M3: source-agnostic UI (кнопка/статус синка) + Docker quickstart + проверяемый сценарий handoff.
- [ ] M4: wellness mapping-spec + импорт (HRV/сон/пульс покоя) → readiness у тестера.
- [ ] M5: демоушен Garmin в UI + миграция существующей (владельца) БД под новый провенанс.

## Surprises & Discoveries

- Observation: TSS хранится с провенансом УЖЕ. Схема `activities` содержит `source_tss REAL` и `tss_method TEXT`; провайдерская нагрузка «хранится для сравнения, никогда не подмешивается в `tss`». Более того, в 2026-07-09 проект СОЗНАТЕЛЬНО отклонил идею брать `icu_training_load` как приоритетный TSS, оставив локальный оффлайн-каскад.
  Evidence: `data/database.py:230,238`; `docs/activity_tss_methodology.md:58,82`. Значит план обязан НЕ объявлять `icu_training_load` каноническим TSS.

- Observation: `icu_training_load` — не гарантированно единообразная величина: Intervals допускает ручную/пользовательскую правку и computed-поля. То есть это провайдерская оценка, а не канон.
  Evidence: ревью владельца (Intervals forum: activity fields / computed fields).

- Observation: у активности нет провенанса. `activities.activity_id TEXT PRIMARY KEY` — единственный глобальный ключ; нет колонок `source`/`provider_activity_id`/`external_id`. Upsert «по Intervals id» не доказывает идемпотентность при Garmin→Intervals переключении, одной тренировке в двух источниках, отсутствии `external_id` или коллизии ID разных провайдеров.
  Evidence: `data/database.py:211`.

- Observation: «синк → план» неверно в один шаг. `build_plan(db, *, goal_type, distance, event_date, available_hours, available_days, ...)` требует явных параметров; event-goal требует подтверждённой A-гонки. `/api/sync` только синхронизирует данные.
  Evidence: `api/planning_service.py:291` (сигнатура), `:343` (A-событие).

- Observation: sync-окно считается по «самой старой из per-table latest dates» — при activity-only Intervals-синке пустые wellness-таблицы держат границу в прошлом и окно каждый раз раздувается до full.
  Evidence: `services/sync.py:101` (`resolve_sync_window`).

- Observation: sync-контур Garmin-специфичен по сообщениям/результату/имени job — нельзя просто параметризовать `source`.
  Evidence: `api/sync_jobs.py:28`; `services/sync.py` (5-шаговые Garmin-сообщения).

- Observation: инфраструктура handoff (шаг 1) готова (`docker-compose.yml`, `Dockerfile.api`, `web/Dockerfile`, `deploy/Caddyfile`, `.env.example` с `INTERVALS_ICU_*`); `sync_athlete_profile` из Intervals уже вызывается в Garmin-синке (`services/sync.py:251`).

## Decision Log

- Decision: направление — Intervals.icu первичный источник, Garmin вторичный. Вертикальный M1 (активности→нагрузка→план), wellness — отдельный M4.
  Rationale: снимает Garmin-зависимость беты; вертикаль быстрее проверяема; wellness обогащает, но не блокирует «запустил и увидел план». Принято владельцем на ревью 2026-07-22.

- Decision: **TSS-политика.** `icu_training_load` сохраняется как `source_tss` (провайдерская нагрузка, НИКОГДА не в `tss`). Локальный `tss` считается существующим каскадом (`utils/metrics`/резолвер) из доступных Intervals-агрегатов (напр. `icu_weighted_avg_watts` как NP, средний HR — для power/hr-каскада). Если данных для локального расчёта недостаточно — ЯВНЫЙ fallback `tss_method="intervals_icu"` (использующий `source_tss`), не маскируя под локальный TSS.
  Rationale: сохраняет инвариант `docs/activity_tss_methodology.md` (провайдер отдельно, `tss` детерминирован и оффлайн) и решение 2026-07-09; `source_tss`/`tss_method` уже есть в схеме — механизм переиспользуется, не изобретается.
  Date/Author: 2026-07-22 / Claude Code (по ревью владельца).

- Decision: **идентичность и провенанс активности.** Добавить в `activities` колонки `source` (`garmin`|`intervals`|…), `provider_activity_id`, `external_id`. Дедуп: одна физическая тренировка в двух источниках связывается по `external_id` (Intervals `external_id` ↔ Garmin `activity_id`), не дублируется; приоритет источника при конфликте — конфигурируемый (для беты: единственный сконфигурированный источник). Coexistence, не overwrite: миграция Garmin→Intervals не затирает историю.
  Rationale: без провенанса идемпотентность и сосуществование недоказуемы (блокер ревью №2). Это фундамент, поэтому — M0 перед адаптером.
  Date/Author: 2026-07-22 / Claude Code.

- Decision: **cursor-семантика.** Курсоры синка — per-domain (активности отдельно от wellness), а не общий «oldest across tables». `source` — в состоянии и результате job. Первый bootstrap — минимум 90 дней; далее инкрементально по доменному курсору.
  Rationale: чинит раздувание окна при activity-only синке (блокер №4); отделяет домены, синкаемые в разных срезах (активности в M1, wellness в M4).
  Date/Author: 2026-07-22 / Claude Code.

- Decision: **«синк ≠ план».** Онбординг параметров планирования (цель/дистанция/часы/дни; обработка A-гонки) — часть вертикального среза (M2), а НЕ побочный эффект синка. M1 заканчивается на «активности и CTL/ATL появились».
  Rationale: `build_plan` требует явных входов (блокер №3); честный сценарий двухступенчатый.
  Date/Author: 2026-07-22 / Claude Code.

- Decision: **wellness — отдельная mapping-spec (M4), не механическое копирование.** До реализации определить: какую HRV-метрику берём (RMSSD?), единицы, поля сна, timezone, определение readiness, provenance. Intervals отдаёт и готовые CTL/ATL — но использовать ли их вместо наших это отдельный архитектурный выбор (по умолчанию — НЕТ, свои).
  Rationale: блокер №5; те же грабли провенанса, что и с TSS.
  Date/Author: 2026-07-22 / Claude Code.

- Decision (ОТКРЫТО — уточнить на ревью этой редакции): объём M0-ADR — отдельный ADR-документ (`docs/architecture/adr_00XX_*`) + миграция, или контракт прямо в этом ExecPlan + миграция. Рекомендую отдельный ADR (провенанс/TSS/identity — долгоживущее архитектурное решение, переживёт этот план).
  Date/Author: 2026-07-22 / Claude Code.

## Outcomes & Retrospective

Заполняется при закрытии milestone'ов. На момент авторинга (редакция 2 по ревью): контракт данных вынесен в M0, сценарий исправлен на двухступенчатый; реализация M0–M5 предстоит.

## Context and Orientation

Состояние (проверено чтением кода 2026-07-22; читатель может не знать репозиторий).

Синк — `services/sync.py`, единственная точка входа `sync_garmin_data(state, days, on_progress)` (строка 228): требует Garmin-авторизации (строка 238, иначе `raise ValueError`); обновляет athlete-профиль из Intervals (`sync_athlete_profile`, строка 251 — не зависит от Garmin); тянет активности из Garmin, затем HRV/сон/health в 5 шагов. Окно синка — `resolve_sync_window` (строка ~101), «от самой старой из per-table latest dates». Джоб-модель синка — `api/sync_jobs.py` (Garmin-специфична). Веб триггерит `POST /api/sync` (`api/routers/system.py`).

Интеграция Intervals — `services/intervals_icu.py`, класс `IntervalsICUClient` (токен `INTERVALS_ICU_API_KEY`/`INTERVALS_ICU_ATHLETE_ID`): `get_athlete_profile`, `list_race_events`, `list_activities` (строка 166 — сейчас только поля для джойна: `id, external_id, paired_event_id, start_date_local, type, name, icu_training_load, moving_time`), `list_workout_events`, `push_planned_events`. Модуль: `is_configured()`, `connection_info()`, `test_connection()`, `sync_athlete_profile(database)`.

Хранилище — `data/database.py` (`Database`, SQLite). Таблица `activities` (CREATE на строке 210): `activity_id TEXT PRIMARY KEY`, поля метрик, `source_tss REAL` (строка 230), `tss_method TEXT` (строка 238) — провенанс TSS уже есть, провенанса ИСТОЧНИКА (source/provider id/external id) нет. `save_activities(...)` — upsert. TSS считается резолвером/каскадом (`docs/activity_tss_methodology.md`, `utils/metrics.py`), провайдерская нагрузка отделена (`source_tss`). CTL/ATL — Banister (`models/banister.py`). План — `api/planning_service.py::build_plan(...persist=True)` / `get_active_plan(db)`.

Деплой шага 1 — `docs/self_hosted_deployment_execplan.md`: `docker-compose.yml`, `Dockerfile.api`, `web/Dockerfile`, `deploy/Caddyfile`. Локально — `./run_web.sh` (:8000 API + :3000 web). Секреты — `.env` (шаблон `.env.example`).

## Plan of Work

Шесть независимо проверяемых milestone. M0 закладывает контракт; M1–M2 — вертикаль «данные → план»; M3 — handoff; M4 wellness; M5 демоушен+миграция.

Milestone M0 — контракт приёма активности (ADR + миграция схемы). Зафиксировать письменно и в схеме: (identity/provenance) добавить в `activities` `source`, `provider_activity_id`, `external_id`; правило дедупликации (одна тренировка в двух источниках связывается по `external_id`, не дублируется) и приоритет источников. (TSS-политика) `icu_training_load` → `source_tss`; локальный `tss` каскадом из Intervals-агрегатов; недостаточно данных → явный `tss_method="intervals_icu"`, не маскируя. (cursor) per-domain курсоры; `source` в job-состоянии/результате; bootstrap ≥90 дней. Миграция — аддитивная и идемпотентная (ALTER/ensure-column как уже делается для новых колонок). Результат: ADR-документ + мигрированная схема + определение «каноническая активность» (какие поля, откуда, с каким провенансом). Приёмка: миграция прогоняется повторно без вреда; юнит-тесты маппинга «Intervals-строка → каноническая активность» (включая случай без `external_id` и с недостаточными для локального TSS данными).

Milestone M1 — Intervals-адаптер → канонические активности → SQLite, без Garmin. Расширить чтение активностей Intervals до полей, нужных для канона (дата, спорт, длительность, дистанция, HR/мощность-агрегаты, `icu_training_load`→`source_tss`, `external_id`). Реализовать маппинг по контракту M0. Добавить `sync_intervals_data(state, days, on_progress)` — НЕ требует Garmin; тянет профиль + активности, сохраняет канонические записи с провенансом; per-domain курсор. Пробросить источник в `POST /api/sync` и job-модель (`source` в состоянии/результате; не ломать `sync_garmin_data`). Доказать ТЕСТАМИ: идемпотентность (повторный синк не плодит дубли), coexistence (та же тренировка из Garmin и Intervals дедупится по `external_id`; отсутствие `external_id` не роняет; коллизия id разных провайдеров разведена `source`). Результат: с одним Intervals-токеном (без Garmin) синк наполняет канонические активности; появляются CTL/ATL. НЕ обещает план.

Milestone M2 — онбординг параметров планирования → первый план. Дать тестеру явный поток: выбрать режим/цель/дистанцию/часы/доступные дни (для event-goal — обработать отсутствие подтверждённой A-гонки: подсказать/предложить develop-режим). После этого `build_plan(persist=True)` строит план по Intervals-активностям, тестер видит его на `/planning` и сессию дня на `/today`. Это и есть честный «увидел свой план». Результат: приёмка «токен → синк → онбординг → план виден» проходит на изолированной БД.

Milestone M3 — source-agnostic UI + handoff. Кнопку/статус синка сделать не-Garmin-специфичными (сейчас «Синхронизировать с Garmin Connect»); показать статус Intervals (`connection_info`/`test_connection`); безопасный first-run. Проверяемый сценарий «клонировал → вписал токен в .env → поднял (`./run_web.sh` или `docker compose up`) → синк → онбординг → план»; где возможно — автотест. Короткий `docs/` quickstart для первого технического тестера (где взять токен/athlete_id, что нажать, что увидеть).

Milestone M4 — wellness из Intervals (mapping-spec + импорт). Сначала spec: HRV-метрика/единицы, поля сна, timezone, readiness-определение, provenance; решить, берём ли готовые CTL/ATL Intervals (по умолчанию — нет). Затем чтение `/api/v1/athlete/{id}/wellness` и сохранение HRV/сна/пульса покоя тем же провенанс-контрактом. Отдельный доменный курсор. Результат: `/today` readiness и карточки Сон/HRV населены у тестера.

Milestone M5 — демоушен Garmin + миграция. Метки провенанса и тексты — source-agnostic; Garmin — опциональный вторичный источник. Мигрировать существующую (владельца) БД под новые колонки провенанса (backfill `source='garmin'` для исторических активностей). Результат: единый провенанс на обоих источниках; владелец не теряет историю.

## Concrete Steps

Из корня репозитория. Локально: `./run_web.sh` (:8000 + :3000). Смоук: `source ai_trainer_env/bin/activate && python -m pytest -m "not live and not debug" tests/` (база на момент авторинга — 1039 passed).

Эмуляция тестера без Garmin (после M1–M3): в `.env` задать только `INTERVALS_ICU_API_KEY` + `INTERVALS_ICU_ATHLETE_ID` (Garmin пусто, отдельный `DATABASE_PATH` во временный файл), поднять `./run_web.sh`, синк (source=intervals) → на `/planning` онбординг → план. Точные команды/транскрипты добавляются по мере реализации.

## Validation and Acceptance

M0: миграция идемпотентна (двойной прогон безвреден); юнит-тесты маппинга «провайдер-строка → каноническая активность» зелёные, включая без-`external_id` и intervals_icu-fallback TSS. ADR закоммичен.

M1: при только-Intervals конфиге `POST /api/sync` наполняет `activities` с провенансом; повторный синк не плодит дублей (тест); та же тренировка из двух источников не задваивается (тест); CTL/ATL считаются. `tss` НЕ равен слепо `icu_training_load` (тест: `source_tss` = провайдер, `tss` = каскад/явный fallback). Смоук зелёный.

M2: с наполненными активностями тестер проходит онбординг и `get_active_plan` даёт план; `/planning` и `/today` показывают его. Событийная цель без A-гонки не роняет поток (graceful).

M3: свежая копия + только Intervals-токен → по quickstart тестер видит план за N шагов; автотест (если есть) красный до и зелёный после.

M4: `/today` readiness и Сон/HRV населены из Intervals-wellness по mapping-spec.

M5: историческая Garmin-база помечена `source='garmin'`, ничего не потеряно; UI не Garmin-специфичен.

## Idempotence and Recovery

Миграции схемы — аддитивные/ensure-column, повторяемые. `sync_intervals_data` — аддитивный путь; `sync_garmin_data` не трогается (откат = не вызывать новый путь). Идемпотентность синка доказывается тестами (M1), не декларируется. Секреты — только `.env`. Тесты/приёмка — временный `DATABASE_PATH`. Ветки/worktree — по правилу репо.

## Artifacts and Notes

Пять блокеров ревью → куда легли (карта):

    1 TSS-контракт (icu_training_load ≠ tss)      → M0 (source_tss + каскад + явный intervals_icu fallback)
    2 идентичность активности (нет провенанса)     → M0 (source, provider_activity_id, external_id, дедуп, приоритет)
    3 «синк → план» неверно                        → M2 (онбординг параметров как часть вертикали)
    4 sync-контур Garmin-специфичен, окно раздувается → M0/M1 (per-domain курсоры, source в job, bootstrap ≥90д)
    5 wellness «тем же контрактом» без spec          → M4 (mapping-spec до импорта)

Карта Intervals как источника (разведка 2026-07-22):

    Профиль (FTP/LTHR)        ЕСТЬ     sync_athlete_profile (уже в Garmin-синке)
    События гонок             ЕСТЬ     list_race_events
    Доставка плана            ЕСТЬ     push_planned_events
    Активности (джойн)        ЧАСТИЧНО  list_activities — поля для матчинга
    Активности (канон+провенанс) НЕТ   → M0 контракт + M1 адаптер
    Garmin-free путь синка    НЕТ      → M1 (sync_intervals_data)
    Wellness (HRV/сон/RHR)    НЕТ      → M4 (spec + /wellness)

## Interfaces and Dependencies

Схема (M0), `data/database.py` — добавить в `activities`: `source TEXT`, `provider_activity_id TEXT`, `external_id TEXT` (аддитивной ensure-column миграцией, как уже делается). `activity_id` остаётся PK; уникальность/дедуп — по (`source`, `provider_activity_id`) и связка по `external_id`.

Маппинг (M0), новый модуль (напр. `services/activity_ingest.py` или в `data/`): `to_canonical_activity(provider_row, source) -> dict` — единая точка «провайдер-строка → каноническая активность», с TSS-политикой (см. Decision Log). Тестируется изолированно.

Intervals-чтение (M1), `services/intervals_icu.py`: расширить `list_activities` (или `list_activities_full`) до полей канона; для wellness (M4) — `list_wellness(oldest, newest)` (`GET /api/v1/athlete/{id}/wellness`).

Синк (M1), `services/sync.py`: `sync_intervals_data(state, days=None, on_progress=None) -> SyncResult` — не гейтить на Garmin; per-domain курсор; сохранять через `save_activities` в каноническом контракте. `api/sync_jobs.py`: `source` в состоянии/результате job. `POST /api/sync` (`api/routers/system.py`): выбор источника (`source` param или автовыбор по конфигурации), без изменения `sync_garmin_data`.

Планирование (M2) — переиспользуется существующий `api/planning_service.py::build_plan`; новый — только UI/поток онбординга параметров.

Зависимости: стандартный Intervals REST (токен уже в `IntervalsICUClient`), никаких новых библиотек; деплой — существующий Docker/Caddy.

---

Изменение (2026-07-22, редакция 2): переписано по ревью владельца («Request changes»). Введён M0 (контракт identity/provenance/TSS/cursor) ПЕРЕД адаптером; исправлен сценарий на двухступенчатый (синк ≠ план, онбординг параметров в M2); TSS-политика приведена в соответствие с `docs/activity_tss_methodology.md` (провайдер в `source_tss`, локальный каскад, явный `intervals_icu` fallback); добавлены дедуп/провенанс и per-domain курсоры; wellness требует mapping-spec (M4); добавлен M5 (демоушен Garmin + миграция БД). Центр тяжести смещён с «выкачки из API» на честную границу `provider data → canonical activity → planning`. Открыто: формат M0 (отдельный ADR vs контракт в этом плане). Issues — после принятия этой редакции.
