# Intervals-primary + локальный Docker-handoff: другой атлет запускает AI Trainer на своих данных

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

This document must be maintained in accordance with `.agent/PLANS.md` (the ExecPlan authoring rules), located at the repository root.

## Purpose / Big Picture

После завершения UI-консолидации (`docs/ui_consolidation_beta_execplan.md`) интерфейс готов к бете. Остаётся настоящий продуктовый барьер: **сейчас AI Trainer может запустить на своих данных только владелец с аккаунтом Garmin.** Весь синк (`services/sync.py::sync_garmin_data`) требует Garmin-авторизации; без неё локальная база пуста.

Цель — чтобы **технический атлет с аккаунтом Intervals.icu (любое устройство) мог: склонировать репозиторий, задать свой Intervals-токен, синхронизировать активности и — задав цель/часы/дни — построить и увидеть СВОЙ план, без Garmin.** Intervals.icu — первичный источник, Garmin — вторичный/опциональный.

Центральный инженерный вопрос — **НЕ получение данных из API**, а **честная граница `provider data → canonical activity → planning`**: как провайдерская активность становится нашей канонической записью, которая может нести идентичность и нагрузку ДВУХ источников одновременно, с честной TSS-политикой, не ломая инварианты проекта. Этот слой контракта — суть работы.

Наблюдаемый результат (двухступенчатый): (1) с одним Intervals-токеном синк наполняет канонические активности и появляются CTL/ATL; (2) тестер проходит онбординг параметров планирования (цель/дистанция/часы/дни; event-goal — A-гонка) и строит первый план, который видит на `/planning` и `/today`. «Синк → сразу план» — неверно.

Термины:

- **каноническая активность** — наша запись (`activities`) с каноническим `tss`+`tss_method`; идентичности и провайдерская нагрузка источников — в `activity_provider_links` (может быть несколько на одну каноническую).
- **provider-link** — строка связи: `provider`, `provider_activity_id`, `external_provider`, `external_id`, `provider_tss`, `imported_at`. Одна каноническая активность может иметь Garmin-link И Intervals-link.
- **provider_tss** — нативная нагрузка провайдера (Garmin `trainingLoad`, Intervals `icu_training_load`), теперь ПО КАЖДОЙ связи (у Garmin и Intervals она разная). Не участвует в локальном каскаде расчёта `tss`.
- **common ingest** — единственный путь записи активности (для ОБОИХ источников): `provider row → to_canonical_activity → activities + provider link`. Без него новые активности одного источника писались бы без link и ломали coexistence.
- **fail-closed matching** — нет/неоднозначен `external_id` → НЕ склеивать эвристикой; раздельно + пометить.
- **cursor** — по какую дату синхронизирован домен (активности отдельно от wellness), per-provider.

## Progress

- [x] (2026-07-25) **M2 завершён (#271).** Персистентный профиль планирования в
  `user_settings`, предложения из истории с явным `basis`, graceful отсутствие/сбой
  A-гонки без фиктивной даты, карточка первого плана в пустом `/planning`. Тонкий
  `/api/onboarding/planning` делегирует в `services/`; sync план не строит. Сквозной
  M2-T7/T8: профиль → preview → confirm → план виден в Planning и Today на временной
  SQLite. Дополнительный fail-closed web-гейт: B/C или неподтверждённая A-гонка не
  разблокирует event-goal. Проверки: M2/Planning 100 passed; smoke 1222 passed,
  1 skipped; полный offline 1265 passed, 6 skipped, 24 deselected; web lint/build green.
- [x] (2026-07-24) **M1 завершён — шаг 6 (D6) закрывает срез.** Демо-сид (`services/demo_mode.activate_demo_mode`) писал активности напрямую через `save_activities`, минуя ingest, и оставался единственной поверхностью БЕЗ provider-link'ов; теперь после сидирования идёт офлайновый `backfill_provider_links` (классификация `demo`, ADR-0008 п.7). Гейты `tests/smoke/test_m1_demo_backfill.py`: M1-T9 (ровно одна `demo`-связь на активность, ноль `garmin`/`legacy_unknown`, ноль сирот), M1-T9b (повторный сид и повторный backfill идемпотентны, поля активностей не портятся проекцией), M1-T9c (деактивация не оставляет осиротевших связей), M1-T9d (изоляция чужой БД). Стаб `_StubDatabase` в `test_demo_mode_service.py` доведён до нового контракта и фиксирует порядок «save_activities → backfill». Полный офлайн — 1199 passed, 5 skipped.
- [x] (2026-07-23) M1 исполнен инкрементально, по срезам §11 slice-спеки (юзер мержит каждый принятый срез, ревью Codex через PR-комментарии): D1 — Garmin-персистенс через common ingest, success-path идентичен кроме единственного поля `source`, failure-path намеренно per-activity (#278); персистентные `sync_cursors` + generic windowed runner, курсор двигается только после полного чистого batch (#280); `sync_intervals_data` — Intervals-адаптер с provider-fallback `icu_training_load` (#281); coexistence/регресс M1-T1/T2 + fail-closed M1-T6 через реальные пути (#282); `source` в `SyncJobManager` и `POST/GET /api/sync` — дефолт `garmin`, неизвестный → 422, single-flight по всем провайдерам (#283).
- [x] (2026-07-22) Разведка + три раунда ревью владельца. Учтены: TSS-контракт, identity/coexistence (provider-link), «синк ≠ план», Garmin-специфичный sync-контур, wellness-mapping, кардинальность `source_tss`, common-ingest для обоих источников.
- [x] (2026-07-22) Редакция 4: `provider_tss`/`imported_at`/`external_provider` перенесены в link-таблицу, `activities.source_tss` — legacy-проекция (ADR определяет выбор); оба источника через common ingest (внутренний persistence Garmin учит создавать link, внешнее поведение `sync_garmin_data` неизменно). Issues заводятся после принятия этой редакции.
- [x] (2026-07-22) M0 ревью-раунд 5 (2 локальных дефекта идемпотентности). (1) Backfill после Intervals-ingest плодил ложную `legacy_unknown`-связь для проекционной канонической `intervals_<id>` — фикс: backfill пропускает активность, уже покрытую любой provider-связью (id = чей-то `canonical_activity_id`), а не сверяет только `(provider, provider_activity_id)`. (2) Повтор идентичного ingest менял `activities.created_at` из-за `INSERT OR REPLACE` в проекции — фикс: create-or-UPDATE (created_at не трогается). Два RED→GREEN гейта: `test_backfill_after_intervals_ingest_adds_no_spurious_link`, `test_repeat_identical_ingest_preserves_created_at`. Полный офлайн — 1075 passed.
- [x] (2026-07-22) M0 ревью-раунд 4 (1 блокер закрыт). Backfill-Garmin-link имеет `external_id=NULL`, а резолвер искал только по `external_provider='garmin'` → первая Intervals-копия не присоединялась к backfill-истории (две активности, двойная нагрузка). Фикс: `_resolve_garmin_coordinate` опознаёт Garmin-активность по `provider_activity_id` (Garmin-id ЕСТЬ координата), а не по self-referential `external_id`. Регресс-гейт `test_backfilled_garmin_activity_merges_with_intervals_copy`: existing → backfill → Intervals-копия → одна каноническая, две matched-связи. Полный офлайн — 1073 passed.
- [x] (2026-07-22) M0 ревью-раунд 3 (3 блокера закрыты). Корень трёх раундов — каноническая строка хранила поля одного источника, а link-модели нужно перепроецировать поля на слияние/демоушен/смену identity. Фикс в корне: связь несёт `provider_payload` (снимок полей источника; колонка добавлена в CREATE непринятой таблицы — без миграции), каноническая = ДЕТЕРМИНИРОВАННАЯ проекция набора связей. Следствия: (1) ambiguous order-independent — ДВА претендента на координату → ОБА `ambiguous`, без произвольного winner; (2) смена external identity перепроецирует старую каноническую (ушедший источник не оставляет полей/TSS); (3) namespace `source` — точный whitelist Garmin (`NOT_GARMIN`/Strava/пусто → standalone). `test_activity_ingest.py` 33 tests; полный офлайн — 1072 passed.
- [x] (2026-07-22) M0 ревью-раунд 2 (6 блокеров закрыты). Fail-closed сопоставление: `external_provider` берётся из Intervals `source` (не предполагается garmin) — Strava-id не склеивается с Garmin-id, неизвестный source → standalone; `ambiguous` реально реализован (второй претендент на координату → standalone + флаг); смена external identity удаляет осиротевшую каноническую (нет двойного учёта) / пересчитывает непустую; `clear_all_data` чистит provider-links; `started_at_utc` — только из настоящего UTC-поля (`start_date`), не из local wall-clock; TSS local-first (fallback лишь при отсутствии локального результата). Постоянный тест атомарного rollback (`0 activities / 0 links`). `test_activity_ingest.py` 20 tests; полный офлайн — 1065 passed.
- [x] (2026-07-22) M0 исполняемый контракт. Guardrail владельца учтён: cursor вынесен из per-activity транзакции (advance-after-batch, ADR п.5/п.8). `services/activity_ingest.py` — `normalize_provider_activity`/`to_canonical_activity` (чистое), атомарный `ingest_provider_activity`, `ingest_provider_batch` (cursor-after-batch), офлайн `backfill_provider_links`, `classify_activity_id`; атомарные `Database.write_provider_activity`/`backfill_activity_provider_links` (SQL в data-слое). ADR ред. 4 (cursor-after-batch + no-orphan) и `activity_tss_methodology.md` (provider-fallback как исключение) обновлены. Матрицы зелёные (`test_activity_ingest.py`, 10 tests): order-independence `Garmin↔Intervals`, backfill-стабильность, batch-cursor на сбое, ingest no-orphan. Полный офлайн-прогон 1055 passed.
- [x] M0: ADR + контракт — canonical id + provider-link модель (с `provider_tss` per-link), fail-closed сопоставление, TSS-исключение (+ правка методологии), `source_tss` legacy-проекция, поведение при двух источниках, backfill+rollback истории, per-provider/per-domain cursors (контракт; персистентность — M1), common-ingest контракт.
- [x] M1 (#270, срезы PR #278/#280/#281/#282/#283 + D6): common ingest для ОБОИХ источников; Intervals-адаптер + внутренний persistence Garmin создают link; `sync_intervals_data` без Garmin; идемпотентность и coexistence доказаны тестами (вкл. регресс: новая Garmin-активность → link, затем Intervals-копия присоединяется к той же канонической). Кончается на «активности + CTL/ATL».
- [x] M2 (#271): онбординг параметров → первый план; без A-гонки graceful, без
  выдуманной даты; профиль и checkpoint разделены.
- [ ] M3: source-agnostic UI + Docker quickstart + сценарий handoff.
- [ ] M4: wellness mapping-spec + импорт → readiness.
- [ ] M5: демоушен Garmin в UI (только тексты/метки).

## Surprises & Discoveries

- Observation: TSS уже с провенансом (`source_tss`, `tss_method`), провайдер не подмешивается в `tss`, решение 2026-07-09 отклонило `icu_training_load` как приоритет.
  Evidence: `data/database.py:230,238`; `docs/activity_tss_methodology.md:58,82`.

- Observation: `source_tss` — single, а связей теперь две (Garmin `provider_tss` ≠ Intervals `provider_tss`). Провайдерскую нагрузку надо хранить ПО СВЯЗИ; `activities.source_tss` остаётся legacy-проекцией выбранного источника.
  Evidence: ревью владельца (кардинальность).

- Observation: backfill покрывает только СТАРУЮ Garmin-историю. Новые Garmin-активности после M0 старым persistence-путём пишутся БЕЗ link → coexistence снова ломается. Значит оба источника должны идти через common ingest.
  Evidence: ревью владельца; `services/sync.py` пишет через `save_activities` напрямую.

- Observation: `external_id` — механизм внешнего сопоставления, не глобальный ID; без namespace (`external_provider`) `external_id="123"` нельзя считать уникальным.
  Evidence: ревью владельца (Intervals Open API).

- Observation: coexistence нельзя выразить колонками на строке `activities` (две идентичности сразу); `activity_id` — единственный PK.
  Evidence: `data/database.py:211`.

- Observation: «синк → план» неверно (build_plan требует входов + A-гонку); sync-окно от «oldest across tables» раздувается при пустых wellness; job Garmin-специфичен.
  Evidence: `api/planning_service.py:291,343`; `services/sync.py:101`; `api/sync_jobs.py:28`.

## Decision Log

- Decision: Intervals первичный, Garmin вторичный; вертикальный M1 (активности→план), wellness M4. Принято владельцем.

- Decision: **TSS-политика — явное исключение.** `provider_tss` НЕ участвует в локальном каскаде расчёта `tss`. При нехватке данных `provider_tss` может стать каноническим `tss` как ЯВНО маркированный `tss_method="intervals_icu_provider_fallback"` — сознательное исключение; **M0 обновляет `docs/activity_tss_methodology.md`** (строка ~82), не утверждая «инвариант цел». `provider_tss` хранится ПО КАЖДОЙ provider-связи (Garmin и Intervals различаются). `activities.source_tss` остаётся legacy-проекцией выбранного источника — ADR определяет, КАК выбирается и КОГДА обновляется. Канонический `tss` — отдельно.
  Date/Author: 2026-07-22 / Claude Code (по ревью).

- Decision: **identity/coexistence — provider-link модель.** Каноническая активность — `canonical_activity_id` (= существующий `activity_id`, потребители не ломаются); связи — в отдельной таблице:

      activity_provider_links(
        canonical_activity_id  FK → activities,
        provider               TEXT,   -- 'garmin' | 'intervals'
        provider_activity_id   TEXT,
        external_provider      TEXT,   -- namespace для external_id
        external_id            TEXT,
        provider_tss           REAL,   -- нативная нагрузка ЭТОГО источника
        imported_at            TEXT,
        UNIQUE(provider, provider_activity_id)
      )

  Одна каноническая несёт и Garmin-, и Intervals-link. Сопоставление fail-closed: точный (`external_provider`,`external_id`) может связывать; отсутствие/неоднозначность → не склеивать, пометить. Миграция аддитивна.
  Date/Author: 2026-07-22 / Claude Code.

- Decision: **common ingest для обоих источников** (нельзя обещать coexistence и «не трогать `sync_garmin_data`»). Единая точка записи `to_canonical_activity(provider_row, source) → (canonical, link)`; и Intervals-адаптер, и внутренний persistence-путь Garmin создают provider-link. Внешнее поведение `sync_garmin_data` (сообщения/результат/окно) сохраняется байт-в-байт, меняется только внутренняя запись активностей. Регресс-тест обязателен: новая Garmin-активность после миграции получает link, затем Intervals-копия присоединяется к той же канонической.
  Rationale: backfill покрывает лишь старую историю; без общего ingest новые Garmin-строки снова без link (блокер R3-2).
  Date/Author: 2026-07-22 / Claude Code.

- Decision: **backfill истории — в M0** (M1 обязан доказывать coexistence). M5 — только UI-демоушен.

- Decision: **cursor** per-provider/per-domain; `source` в job; bootstrap ≥90 дней.

- Decision: **«синк ≠ план»** — онбординг параметров в M2, не побочный эффект синка.

- Decision: **wellness — отдельная mapping-spec (M4)**; готовые CTL/ATL Intervals по умолчанию не берём.

- Decision: **ADR для M0 ОБЯЗАТЕЛЕН** (`docs/architecture/adr_00XX_intervals_activity_ingestion.md`), фиксирует: (1) canonical id + provider-link модель (с `provider_tss` per-link, `external_provider` namespace); (2) fail-closed сопоставление; (3) TSS-исключение + правка методологии; (4) `source_tss` legacy-проекция — правило выбора/обновления; (5) common-ingest контракт (оба источника); (6) поведение при двух настроенных источниках (приоритет/дедуп); (7) backfill и rollback; (8) per-provider/per-domain cursors.
  Date/Author: 2026-07-22 / Claude Code.

## Outcomes & Retrospective

Заполняется при закрытии milestone'ов. Редакция 4: provider-link модель доведена до конца (`provider_tss` per-link, common ingest обоих источников); реализация M0–M5 предстоит.

**M0 + M1 закрыты (2026-07-24).** Достигнуто: оба источника идут через один funnel `services/activity_ingest`, только-Intervals синк наполняет `activities` provider-link'ами и питает CTL/ATL без Garmin-кред; персистентный курсор двигается только после полного чистого batch; `source` доехал до job и `POST/GET /api/sync`; демо-поверхность живёт в той же link-модели (D6). Что сработало процессно: инкрементальный мерж по срезам вместо одного PR (каждый срез — свои RED-гейты и отдельный раунд ревью), а компат-контракт Garmin формулировался как «идентично КРОМЕ явного списка новых ключей», а не буквальное равенство — иначе аддитивное поле `source` было бы неотличимо от регресса. Что стоило раундов: идемпотентность при повторных проходах (created_at, ложные `legacy_unknown`-связи, курсор при частичном сбое) — каждый раз корень был в том, что каноническая строка воспринималась как хранилище, а не как проекция набора связей. Не сделано осознанно: локальный пересчёт TSS по потокам Intervals (D2), Garmin на курсор-таблицу (D3), удаление deprecated-shim `database.sync_activities` (D4) — отдельные поздние срезы. Следующее — M2 (#271): онбординг параметров → первый план.

**M2 закрыт (2026-07-25).** Достигнуто: первый план требует явного подтверждения
параметров, но не заставляет атлета заполнять всё с нуля — предложения выводятся из
истории и маркируются `derived/fallback`. Профиль остаётся входным состоянием, а план —
отдельным checkpoint-решением; preview/confirm-гейт сохранён. Главный найденный угол:
«выбрано событие» не равно «есть A-гонка» — B/C или неподтверждённая A больше не
разблокирует event-goal. Следующее — M3 (#272): source-agnostic UI, quickstart и
сквозной handoff.

## Context and Orientation

Синк — `services/sync.py::sync_garmin_data` (228): Garmin-авторизация (238); профиль из Intervals (251); активности из Garmin через `save_activities`; окно `resolve_sync_window` (~101). Джоб — `api/sync_jobs.py`. Триггер — `POST /api/sync`.

Intervals — `services/intervals_icu.py::IntervalsICUClient`: `list_activities` (166, поля для джойна вкл. `external_id`,`icu_training_load`), `sync_athlete_profile`, `connection_info`/`test_connection`.

Хранилище — `data/database.py`: `activities` (210) `activity_id TEXT PK`, `source_tss REAL` (230), `tss_method TEXT` (238). `save_activities` — upsert. TSS — каскад (`docs/activity_tss_methodology.md`); CTL/ATL — `models/banister.py`; план — `api/planning_service.py::build_plan`.

Деплой шага 1 — Docker/Caddy/.env; локально `./run_web.sh`.

## Plan of Work

Milestone M0 — ADR + контракт + миграция + backfill. ADR (`docs/architecture/adr_00XX_intervals_activity_ingestion.md`) с восемью пунктами Decision Log. Схема: `canonical_activity_id` (= `activity_id`); таблица `activity_provider_links` (с `provider_tss`, `external_provider`, `imported_at`), аддитивно/идемпотентно; `activities.source_tss` документируется как legacy-проекция. Common-ingest контракт: `to_canonical_activity(provider_row, source)` — единая точка. Backfill: каждой существующей Garmin-активности — link (`provider='garmin'`, `provider_activity_id=activity_id`, `provider_tss` из текущего `source_tss`, `external_id` если известен); неоднозначные — пометить. Обновить методологию TSS. Приёмка: миграция+backfill идемпотентны; тесты маппинга и fail-closed; ADR + методология закоммичены.

Milestone M1 — common ingest + Intervals-адаптер, без Garmin. Провести ОБА источника через `to_canonical_activity`: Intervals-адаптер (новый) и внутренний persistence Garmin (научить создавать link, внешнее поведение `sync_garmin_data` неизменно). `sync_intervals_data(state, days, on_progress)` — не гейтить на Garmin; per-provider курсор; `provider_tss←icu_training_load`, `tss` каскадом либо `intervals_icu_provider_fallback`. `source` в job. Тесты: идемпотентность; coexistence (Garmin+Intervals одной тренировки → одна каноническая через link, без задвоения); **регресс: новая Garmin-активность после миграции получает link, затем Intervals-копия присоединяется к той же канонической**; fail-closed. Результат: только-Intervals синк наполняет активности; CTL/ATL; плана не обещает.

Milestone M2 — онбординг параметров → первый план. Поток: режим/цель/дистанция/часы/дни; event-goal без A-гонки graceful. `build_plan(persist=True)` по Intervals-активностям; план виден на `/planning`/`/today`.

Milestone M3 — source-agnostic UI + handoff. Кнопка/статус синка не-Garmin; статус Intervals; сценарий «клон → токен → синк → онбординг → план»; автотест; quickstart-инструкция.

Milestone M4 — wellness. Mapping-spec (HRV/сон/timezone/readiness/provenance; CTL/ATL Intervals по умолчанию нет), затем `/wellness` → сохранение; доменный курсор. `/today` readiness + Сон/HRV.

Milestone M5 — демоушен Garmin (только UI-тексты/метки; вторичный источник). Backfill — уже в M0.

## Concrete Steps

Локально `./run_web.sh`; смоук `python -m pytest -m "not live and not debug" tests/` (база 1039). Эмуляция тестера без Garmin (после M1–M3): `.env` только `INTERVALS_ICU_*` (Garmin пусто, временный `DATABASE_PATH`), синк (source=intervals) → онбординг → план.

## Validation and Acceptance

M0: миграция+backfill идемпотентны; тесты маппинга и fail-closed зелёные; ADR + методология обновлены; Garmin-история имеет link с `provider_tss`.

M1: только-Intervals → активности с link; повтор без дублей; та же тренировка из двух источников → одна каноническая (link-дедуп, тест); **новая Garmin-активность → Garmin-link, затем Intervals-копия → та же каноническая (регресс-тест)**; нет `external_id` → fail-closed; `tss`≠слепой `icu_training_load` (тест); CTL/ATL. Смоук зелёный; внешнее поведение `sync_garmin_data` не изменилось (тест-снапшот сообщений/результата).

M2: онбординг → план виден; event-goal без A-гонки graceful.

M3: свежая копия + токен → по quickstart виден план; автотест красный до/зелёный после.

M4: readiness + Сон/HRV из Intervals-wellness.

M5: UI не Garmin-специфичен; история цела.

## Idempotence and Recovery

Миграции/backfill аддитивны и повторяемы; ADR фиксирует rollback (снять link-таблицу/вернуть поведение). Common ingest не меняет внешнее поведение `sync_garmin_data` (снапшот-тест). Идемпотентность/coexistence — тестами (M0/M1). Секреты — `.env`; тесты — временный `DATABASE_PATH`.

## Artifacts and Notes

Блокеры ревью → куда легли:

    R1-1 TSS ≠ icu_training_load     → M0 (source_tss + каскад + intervals_icu_provider_fallback + правка методологии)
    R1-2 identity/coexistence        → M0 (canonical id + activity_provider_links, fail-closed)
    R1-3 «синк → план»               → M2 (онбординг параметров)
    R1-4 sync Garmin-специфичен/окно  → M0/M1 (per-provider/per-domain курсоры, source в job, bootstrap ≥90д)
    R1-5 wellness без spec           → M4 (mapping-spec)
    R2-1 TSS-fallback как исключение  → Decision Log + M0 правит методологию
    R2-2 coexistence ≠ 3 колонки     → provider-link таблица (M0)
    R2-3 backfill слишком поздно      → M0 (M5 = только UI)
    R3-1 source_tss кардинальность    → provider_tss per-link; source_tss legacy-проекция (ADR)
    R3-2 coexistence ломается новыми Garmin → common ingest обоих источников + регресс-тест (M1)

## Interfaces and Dependencies

Схема (M0), `data/database.py`: `canonical_activity_id` = существующий `activity_id`; таблица `activity_provider_links(canonical_activity_id FK, provider, provider_activity_id, external_provider, external_id, provider_tss REAL, imported_at, UNIQUE(provider, provider_activity_id))`, аддитивно. `activities.source_tss` — legacy-проекция (правило в ADR). Backfill Garmin-истории в link — там же.

Common ingest (M0/M1), новый модуль (напр. `services/activity_ingest.py`): `to_canonical_activity(provider_row, source) -> (canonical, link)` — единственная точка записи для ОБОИХ источников; TSS-политика + fail-closed. Внутренний persistence Garmin в `services/sync.py` перенаправляется сюда (внешнее поведение неизменно).

Intervals-чтение (M1): расширить `list_activities` до полей канона; wellness (M4) — `list_wellness(oldest, newest)`.

Синк (M1): `sync_intervals_data(state, days=None, on_progress=None)` — не гейтить на Garmin; per-provider курсор. `api/sync_jobs.py`: `source` в состоянии/результате. `POST /api/sync`: выбор источника.

Планирование (M2): существующий `build_plan`; новое — UI/онбординг.

Зависимости: стандартный Intervals REST; деплой — существующий Docker/Caddy.

---

Изменение (2026-07-22, редакция 4): третий раунд ревью, две поправки в provider-link модель (структура M0–M5 не менялась). (R3-1) `provider_tss` перенесён в `activity_provider_links` (по связи), `activities.source_tss` — legacy-проекция выбранного источника (правило в ADR); + `external_provider` namespace, `imported_at`. (R3-2) введён common ingest: ОБА источника пишут через `to_canonical_activity`; внутренний persistence Garmin учится создавать link (внешнее поведение `sync_garmin_data` байт-в-байт неизменно), + регресс-тест на присоединение Intervals-копии к Garmin-канонической. ADR-пункты расширены до 8. По словам ревьюера — после этих поправок вердикт финальный (принять и заводить M0–M5).
