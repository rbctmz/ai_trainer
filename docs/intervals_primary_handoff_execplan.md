# Intervals-primary + локальный Docker-handoff: другой атлет запускает AI Trainer на своих данных

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

This document must be maintained in accordance with `.agent/PLANS.md` (the ExecPlan authoring rules), located at the repository root.

## Purpose / Big Picture

После завершения UI-консолидации (`docs/ui_consolidation_beta_execplan.md`) интерфейс готов к бете. Остаётся настоящий продуктовый барьер: **сейчас AI Trainer может запустить на своих данных только владелец с аккаунтом Garmin.** Весь синк (`services/sync.py::sync_garmin_data`) требует Garmin-авторизации; без неё локальная база пуста.

Цель — чтобы **технический атлет с аккаунтом Intervals.icu (любое устройство) мог: склонировать репозиторий, задать свой Intervals-токен, синхронизировать активности и — задав цель/часы/дни — построить и увидеть СВОЙ план, без Garmin.** Intervals.icu — первичный источник, Garmin — вторичный/опциональный.

Центральный инженерный вопрос — **НЕ получение данных из API** (Intervals REST умеет activities/wellness/календарь/external IDs). Центральный вопрос — **честная граница `provider data → canonical activity → planning`**: как провайдерская активность становится нашей канонической записью с честной идентичностью (двух источников одновременно), провенансом и TSS-политикой, не ломая инварианты проекта и не смешивая источники. Этот слой контракта — суть работы.

Наблюдаемый результат (сценарий приёмки), двухступенчатый: (1) с одним Intervals-токеном синк наполняет канонические активности и появляются CTL/ATL; (2) тестер проходит онбординг параметров планирования (цель/дистанция/часы/дни; для event-goal — A-гонка) и строит первый план, который видит на `/planning` и `/today`. «Нажал синк → сразу план» — неверно: план требует явных входов.

Термины простым языком:

- **источник данных** — откуда приходят активности и wellness. Сейчас первичный — Garmin; цель — Intervals.icu.
- **каноническая активность** — наша внутренняя запись (`activities`), с нашим `tss`+`tss_method`, отдельной провайдерской нагрузкой (`source_tss`), и — после этого плана — с моделью связей на провайдерские идентичности (может иметь их несколько).
- **provider-link** — связь канонической активности с идентичностью в конкретном источнике (`provider`, `provider_activity_id`, `external_id`). Одна каноническая активность может иметь Garmin-идентичность И Intervals-идентичность одновременно.
- **provider_tss / source_tss** — нативная нагрузка провайдера (Garmin `trainingLoad`, Intervals `icu_training_load`). Проект хранит её отдельно и не подмешивает в `tss` при локальном расчёте (`docs/activity_tss_methodology.md:58`).
- **fail-closed matching** — если `external_id` отсутствует или неоднозначен, НЕ склеивать записи эвристикой; оставить раздельными и пометить для ревью.
- **cursor** — по какую дату синхронизирован конкретный домен (активности отдельно от wellness), per-provider.

## Progress

- [x] (2026-07-22) Разведка + два раунда ревью владельца («Request changes»). Подтверждены и учтены: TSS-контракт, identity/coexistence, «синк ≠ план», Garmin-специфичный sync-контур, wellness-mapping (см. `Surprises`, `Decision Log`).
- [x] (2026-07-22) Редакция 3: coexistence через provider-link модель; TSS-fallback назван явным исключением с обновлением методологии; backfill перенесён в M0; отдельный ADR сделан обязательным. Issues НЕ заведены — по указанию «сначала только ExecPlan»; заводятся после принятия этой редакции.
- [ ] M0: ADR + контракт приёма активности — canonical id + provider-link модель, безопасное (fail-closed) сопоставление, TSS-fallback как явное исключение (+ правка методологии), поведение при двух источниках, backfill+rollback исторических Garmin-строк, per-provider/per-domain cursors.
- [ ] M1: Intervals-адаптер → канонические активности → SQLite, без Garmin; идемпотентность и coexistence (Garmin↔Intervals через link-таблицу) доказаны тестами. Заканчивается на «активности и CTL/ATL появились».
- [ ] M2: онбординг параметров планирования → первый план (честный «увидел свой план»).
- [ ] M3: source-agnostic UI + Docker quickstart + проверяемый сценарий handoff.
- [ ] M4: wellness mapping-spec + импорт (HRV/сон/пульс покоя) → readiness.
- [ ] M5: демоушен Garmin в UI (только тексты/метки + опциональный вторичный источник). Backfill истории — уже в M0.

## Surprises & Discoveries

- Observation: TSS хранится с провенансом УЖЕ (`source_tss REAL`, `tss_method TEXT`), провайдерская нагрузка «никогда не подмешивается в `tss`», и в 2026-07-09 проект СОЗНАТЕЛЬНО отклонил `icu_training_load` как приоритетный TSS.
  Evidence: `data/database.py:230,238`; `docs/activity_tss_methodology.md:58,82`.

- Observation: `icu_training_load` — не гарантированно единообразная величина (Intervals допускает ручную/computed правку). Провайдерская оценка, не канон.
  Evidence: ревью владельца (Intervals forum: activity/computed fields).

- Observation: coexistence нельзя выразить колонками на строке `activities`. Одна каноническая тренировка может иметь ДВЕ идентичности сразу (Garmin `activity_id` И Intervals `id`+`external_id`); одна строка с одним `source`/`provider_activity_id` не удержит обе — при следующем импорте одна провенанс-запись вытеснит другую. Нужна отдельная таблица связей.
  Evidence: `data/database.py:211` (`activity_id` — единственный PK); ревью владельца.

- Observation: `external_id` — механизм внешнего сопоставления, НЕ глобальный идентификатор физической тренировки. Значит сопоставление должно быть fail-closed при отсутствии/неоднозначности, без эвристического склеивания.
  Evidence: ревью владельца (Intervals Open API).

- Observation: «синк → план» неверно в один шаг. `build_plan(...goal_type, distance, event_date, available_hours, available_days...)` требует явных входов; event-goal — подтверждённой A-гонки.
  Evidence: `api/planning_service.py:291,343`.

- Observation: sync-окно от «oldest across tables» — activity-only Intervals-синк с пустыми wellness-таблицами раздувает окно до full каждый раз. Плюс job Garmin-специфичен.
  Evidence: `services/sync.py:101`; `api/sync_jobs.py:28`.

- Observation: инфра handoff готова (Docker/Caddy/.env со шага 1); `sync_athlete_profile` из Intervals уже вызывается в Garmin-синке.
  Evidence: `services/sync.py:251`; `.env.example`.

## Decision Log

- Decision: Intervals.icu первичный, Garmin вторичный. Вертикальный M1 (активности→нагрузка→план), wellness — M4. Принято владельцем.
  Date/Author: 2026-07-22 / владелец + Claude Code.

- Decision: **TSS-политика как явное исключение (не «инвариант полностью сохранён»).** `provider_tss` (Intervals `icu_training_load` / Garmin load) НЕ участвует в локальном каскаде расчёта `tss`. НО при нехватке данных для локального расчёта `provider_tss` может стать каноническим `tss` как ЯВНО маркированный fallback `tss_method="intervals_icu_provider_fallback"`. Это сознательное исключение из политики `docs/activity_tss_methodology.md` — M0 ОБНОВЛЯЕТ этот документ (раздел «Решение», строка ~82), а не утверждает, что старый инвариант нетронут.
  Rationale: честно называем fallback исключением; переиспользуем `source_tss`/`tss_method`; не маскируем провайдерскую нагрузку под локальный TSS.
  Date/Author: 2026-07-22 / Claude Code (по ревью).

- Decision: **identity/coexistence через provider-link модель** (не три колонки на `activities`). Каноническая активность имеет `canonical_activity_id`; связи с источниками — в отдельной таблице:

      activity_provider_links(
        canonical_activity_id  FK → activities,
        provider               TEXT,   -- 'garmin' | 'intervals'
        provider_activity_id   TEXT,
        external_id            TEXT,
        UNIQUE(provider, provider_activity_id)
      )

  Одна каноническая активность может нести и Garmin-, и Intervals-связь. Сопоставление — fail-closed: точный `external_id` может связывать; отсутствие/неоднозначность → НЕ склеивать, оставить раздельными и пометить. Миграция аддитивна: существующий `activities.activity_id` становится `canonical_activity_id` (существующие потребители не ломаются), link-таблица добавляется поверх.
  Rationale: три колонки не удерживают две идентичности (блокер ревnю №2); для долгоживущего решения таблица связей корректнее, чем «один активный источник».
  Date/Author: 2026-07-22 / Claude Code.

- Decision: **backfill истории — в M0, не в M5.** M1 обязан доказывать Garmin↔Intervals coexistence, значит исторические Garmin-строки должны получить provider-link (`provider='garmin'`) и пройти проверку неоднозначности ДО M1. M5 оставляет только UI-тексты и финальный демоушен Garmin.
  Rationale: без раннего backfill старые строки без провенанса, coexistence в M1 недоказуема (блокер №3).
  Date/Author: 2026-07-22 / Claude Code.

- Decision: **cursor-семантика** — per-provider и per-domain (активности отдельно от wellness); `source` в состоянии/результате job; первый bootstrap ≥90 дней, далее инкрементально по доменному курсору.
  Rationale: чинит раздувание окна (блокер №4); домены синкаются в разных срезах.
  Date/Author: 2026-07-22 / Claude Code.

- Decision: **«синк ≠ план».** Онбординг параметров планирования — часть вертикали (M2), не побочный эффект синка. M1 кончается на «активности + CTL/ATL».
  Date/Author: 2026-07-22 / Claude Code.

- Decision: **wellness — отдельная mapping-spec (M4)**: HRV-метрика/единицы, сон, timezone, readiness, provenance; готовые CTL/ATL Intervals по умолчанию НЕ берём.
  Date/Author: 2026-07-22 / Claude Code.

- Decision: **отдельный ADR для M0 ОБЯЗАТЕЛЕН** (не «рекомендован»). `docs/architecture/adr_00XX_intervals_activity_ingestion.md` фиксирует: (1) канонический ID + provider-link модель; (2) безопасное (fail-closed) правило сопоставления; (3) TSS-fallback как явное исключение + правка методологии; (4) поведение при ДВУХ настроенных источниках (приоритет/дедуп); (5) backfill и rollback; (6) per-provider/per-domain cursors.
  Rationale: провенанс/identity/TSS — долгоживущие архитектурные решения, переживут этот план; ревью требует их зафиксировать до кода.
  Date/Author: 2026-07-22 / Claude Code (по ревью).

## Outcomes & Retrospective

Заполняется при закрытии milestone'ов. На момент авторинга (редакция 3): контракт данных вынесен в M0 с provider-link моделью, TSS-fallback назван явным исключением, backfill в M0; реализация M0–M5 предстоит.

## Context and Orientation

Состояние (проверено чтением кода 2026-07-22).

Синк — `services/sync.py::sync_garmin_data` (строка 228): требует Garmin-авторизации (238); обновляет профиль из Intervals (251); тянет активности из Garmin, затем HRV/сон/health. Окно — `resolve_sync_window` (~101, «oldest across tables»). Джоб-модель — `api/sync_jobs.py` (Garmin-специфична). Триггер — `POST /api/sync` (`api/routers/system.py`).

Intervals — `services/intervals_icu.py::IntervalsICUClient`: `get_athlete_profile`, `list_race_events`, `list_activities` (166 — сейчас только поля для джойна, включая `external_id`, `icu_training_load`), `push_planned_events`; модуль `is_configured`/`connection_info`/`test_connection`/`sync_athlete_profile`.

Хранилище — `data/database.py`. `activities` (CREATE 210): `activity_id TEXT PRIMARY KEY`, метрики, `source_tss REAL` (230), `tss_method TEXT` (238) — провенанс TSS есть, провенанса ИСТОЧНИКА нет. `save_activities` — upsert. TSS — резолвер/каскад (`docs/activity_tss_methodology.md`, `utils/metrics.py`); CTL/ATL — `models/banister.py`; план — `api/planning_service.py::build_plan`/`get_active_plan`.

Деплой шага 1 — `docs/self_hosted_deployment_execplan.md` (Docker/Caddy/.env); локально `./run_web.sh`.

## Plan of Work

Шесть milestone. M0 закладывает контракт+ADR+миграцию+backfill; M1–M2 вертикаль «данные→план»; M3 handoff; M4 wellness; M5 демоушен.

Milestone M0 — ADR + контракт приёма активности + миграция + backfill. Написать ADR (`docs/architecture/adr_00XX_intervals_activity_ingestion.md`) с шестью пунктами из Decision Log. Схема: ввести `canonical_activity_id` (= существующий `activity_id`, без ломки потребителей) и таблицу `activity_provider_links` (аддитивная ensure-column/create миграция, идемпотентная). Backfill: для каждой существующей Garmin-активности создать link (`provider='garmin'`, `provider_activity_id=activity_id`, `external_id` если известен из Intervals-джойна); строки с неоднозначной/отсутствующей идентичностью — пометить, не склеивать. TSS: обновить `docs/activity_tss_methodology.md` (назвать `intervals_icu_provider_fallback` явным исключением). Определить «каноническую активность» (поля, источники, провенанс) и модуль маппинга. Приёмка: миграция+backfill идемпотентны (двойной прогон безвреден); юнит-тесты маппинга и fail-closed сопоставления (без `external_id`, неоднозначность, коллизия id разных провайдеров); ADR закоммичен; методология обновлена.

Milestone M1 — Intervals-адаптер → канонические активности, без Garmin. Расширить чтение активностей Intervals до полей канона; маппинг по контракту M0; `provider_tss`←`icu_training_load`, локальный `tss` каскадом либо `intervals_icu_provider_fallback`. `sync_intervals_data(state, days, on_progress)` — не гейтить на Garmin; per-provider курсор; сохранять канонические записи + provider-link. `source` в job. Не трогать `sync_garmin_data`. Доказать ТЕСТАМИ: идемпотентность (повторный синк без дублей); coexistence (та же тренировка из Garmin и Intervals связана одной канонической через link-таблицу, не задвоена); fail-closed (нет `external_id`/неоднозначность → раздельно, помечено). Результат: только-Intervals синк наполняет активности; CTL/ATL считаются; плана НЕ обещает.

Milestone M2 — онбординг параметров → первый план. Явный поток: режим/цель/дистанция/часы/дни; event-goal без A-гонки — graceful (подсказать develop). `build_plan(persist=True)` строит план по Intervals-активностям; тестер видит его на `/planning` и `/today`. Честный «увидел свой план».

Milestone M3 — source-agnostic UI + handoff. Кнопка/статус синка не-Garmin-специфичны; статус Intervals; безопасный first-run. Сценарий «клон → токен в .env → поднял → синк → онбординг → план»; автотест где возможно; `docs/` quickstart для первого тестера.

Milestone M4 — wellness. Сначала mapping-spec (HRV-метрика/единицы/сон/timezone/readiness/provenance; готовые CTL/ATL Intervals — по умолчанию нет). Затем `/api/v1/athlete/{id}/wellness` → сохранение по провенанс-контракту; отдельный доменный курсор. `/today` readiness + Сон/HRV населены.

Milestone M5 — демоушен Garmin (только UI). Метки провенанса и тексты source-agnostic; Garmin — опциональный вторичный источник в онбординге. Backfill истории уже сделан в M0.

## Concrete Steps

Из корня. Локально `./run_web.sh` (:8000+:3000). Смоук: `source ai_trainer_env/bin/activate && python -m pytest -m "not live and not debug" tests/` (база 1039 passed).

Эмуляция тестера без Garmin (после M1–M3): в `.env` только `INTERVALS_ICU_API_KEY`+`INTERVALS_ICU_ATHLETE_ID` (Garmin пусто; временный `DATABASE_PATH`), `./run_web.sh`, синк (source=intervals) → `/planning` онбординг → план. Транскрипты — по мере реализации.

## Validation and Acceptance

M0: миграция+backfill идемпотентны (двойной прогон безвреден); тесты маппинга и fail-closed сопоставления зелёные; ADR закоммичен; `activity_tss_methodology.md` обновлён (fallback как исключение). Существующие Garmin-активности имеют `provider='garmin'` link.

M1: только-Intervals конфиг → `POST /api/sync` наполняет канонические активности с link; повтор без дублей (тест); та же тренировка из двух источников — одна каноническая (тест на link-дедуп); отсутствие `external_id` → fail-closed (тест); `tss` НЕ равен слепо `icu_training_load` (тест: `provider_tss`≠`tss`, либо явный `intervals_icu_provider_fallback`); CTL/ATL считаются. Смоук зелёный.

M2: онбординг → `get_active_plan` даёт план; `/planning`/`/today` показывают; event-goal без A-гонки не роняет поток.

M3: свежая копия + Intervals-токен → по quickstart тестер видит план; автотест красный до / зелёный после.

M4: `/today` readiness + Сон/HRV из Intervals-wellness по mapping-spec.

M5: UI не Garmin-специфичен; история цела (backfill из M0).

## Idempotence and Recovery

Миграции/backfill — аддитивны и повторяемы; ADR фиксирует rollback (как снять link-таблицу/вернуть поведение). `sync_intervals_data` аддитивен; `sync_garmin_data` не трогается. Идемпотентность и coexistence — тестами (M0/M1). Секреты — `.env`. Тесты/приёмка — временный `DATABASE_PATH`.

## Artifacts and Notes

Пять блокеров ревью-раунда 1 + три раунда 2 → куда легли:

    R1-1 TSS ≠ icu_training_load        → M0 (source_tss + каскад + ЯВНЫЙ intervals_icu_provider_fallback + правка методологии)
    R1-2 identity/coexistence           → M0 (canonical id + activity_provider_links, fail-closed)
    R1-3 «синк → план»                  → M2 (онбординг параметров)
    R1-4 sync Garmin-специфичен/окно     → M0/M1 (per-provider/per-domain курсоры, source в job, bootstrap ≥90д)
    R1-5 wellness без spec              → M4 (mapping-spec)
    R2-1 TSS-fallback как исключение     → Decision Log + M0 правит методологию (не «инвариант цел»)
    R2-2 coexistence ≠ 3 колонки        → provider-link таблица (M0)
    R2-3 backfill слишком поздно         → перенесён в M0 (M5 = только UI)

## Interfaces and Dependencies

Схема (M0), `data/database.py`: `canonical_activity_id` = существующий `activity_id` (потребители не ломаются); новая таблица `activity_provider_links(canonical_activity_id FK, provider, provider_activity_id, external_id, UNIQUE(provider, provider_activity_id))`, аддитивной миграцией. Backfill Garmin-истории в link-модель — там же (M0).

Маппинг (M0), новый модуль (напр. `services/activity_ingest.py`): `to_canonical_activity(provider_row, source) -> (canonical, link)` — единая точка «провайдер-строка → каноническая активность + provider-link», с TSS-политикой и fail-closed сопоставлением. Тестируется изолированно.

Intervals-чтение (M1): расширить `list_activities` до полей канона; wellness (M4) — `list_wellness(oldest, newest)` (`GET /api/v1/athlete/{id}/wellness`).

Синк (M1), `services/sync.py`: `sync_intervals_data(state, days=None, on_progress=None) -> SyncResult` — не гейтить на Garmin; per-provider курсор; писать канонические записи + link. `api/sync_jobs.py`: `source` в состоянии/результате. `POST /api/sync`: выбор источника, без изменения `sync_garmin_data`.

Планирование (M2): существующий `build_plan`; новое — только UI/поток онбординга.

Зависимости: стандартный Intervals REST (токен уже в клиенте); деплой — существующий Docker/Caddy.

---

Изменение (2026-07-22, редакция 3): по второму раунду ревью. (1) TSS-fallback назван ЯВНЫМ исключением `intervals_icu_provider_fallback`, M0 обновляет `activity_tss_methodology.md` (не «инвариант цел»). (2) coexistence переведён с трёх колонок на provider-link модель (`activity_provider_links`, fail-closed сопоставление; `canonical_activity_id` = существующий `activity_id`, аддитивно). (3) backfill истории перенесён из M5 в M0 (M5 = только UI-демоушен). Отдельный ADR для M0 сделан ОБЯЗАТЕЛЬНЫМ с шестью зафиксированными пунктами (вкл. поведение при двух источниках и rollback). Структура M0–M5 (границы M1/M2, доменные курсоры, wellness-spec) — по подтверждению ревью, верна. Issues — после принятия этой редакции.
