# Slice Spec And Review Template — issue #562 (post-sync readiness snapshot capture parity)

Рабочая спецификация по `docs/templates/slice_spec_review_template.md`; связана с живым ExecPlan `docs/recovery_snapshot_capture_parity_execplan.md` (issue #562) и не дублирует формат `.agent/PLANS.md`.

- Issue / PR: [#562](https://github.com/rbctmz/ai_trainer/issues/562) (PR: plan-only этап — см. ветку плана)
- Author / checker / merge owner: agent (Spec / Architecture Owner на plan-only этапе; реализация M1–M4 — Domain / API Implementer, M5 — UI / Design Specialist) / независимый checker на PR (`@codex review`) / rbctmz
- Date: 2026-09-12
- Candidate head SHA: plan-only (SHA ветки плана фиксируется в PR; код не изменён)

## Change Class

- Class: **A**
- Rationale: изменение затрагивает live-sync/provider integration (оба провайдера), scientific provenance/identity производного снимка (run identity, eligibility, pre-anchor) и аддитивный API↔web контракт. Issue назначает Class A самостоятельно, и автоматические триггеры подтверждают: provider integration — да; provenance/identity — да; новый публичный контракт — да (аддитивный блок в ответе синхронизации).
- Automatic escalation triggers checked:
  - data migration или schema/persistence semantics — **нет**: новых колонок и таблиц не появляется, состояние capture вычисляется из существующего журнала `readiness_snapshots` и активностей;
  - identity/provenance либо dedup rules — **да**: run identity capture'а становится производной от sync-job'а, а не `uuid4()` внутри сервиса;
  - live-provider write, платный вызов, destructive sync — **нет**: новых обращений к провайдерам не добавляется, writeback отсутствует;
  - security boundary/permissions/secrets — **нет**;
  - irreversible action — **нет**: откат = revert коммита, исторические строки не мутируются;
  - новый cross-module public contract или архитектурная граница — **да**: `recovery_capture` в ответе синхронизации и в `web/lib/types.ts`; новая архитектурная граница не создаётся (провайдер-нейтральный владелец capture уже существует в `services/recovery_analytics.py`).
- Review budget used: 0 / 2 rounds
- Review trigger mode: automatic (`@codex review` на PR)
- Review acceptance head SHA: TBD
- Review budget exception: N/A — бюджет не превышен

**Устаревшая зависимость issue.** В теле issue сказано «Related but deliberately separate from **open** #557». На дату плана #557 **закрыт** (смержен PR #563, merge-коммит `a82be7b`), и в main уже живут его семантики: metric-scoped provenance (`sleep_score_observed_at`, `total_sleep_observed_at`, `rmssd_observed_at`, `resting_hr_observed_at`, `training_readiness_observed_at`), аддитивный канал `freshness`/`intervention_*`, fail-closed гейт и athlete-local (а не серверные) anchor'ы дат. План **опирается** на эти семантики и не дублирует их: capture по-прежнему строит канонический snapshot через `services/readiness_snapshot.py`, а `freshness`/`intervention_*` — часть этого snapshot'а. Разделение из issue сохраняется: #562 отвечает за *паритет и видимость capture*, а не за свежесть входов readiness.

## Scope

- Behavior that changes: post-sync derived capture выполняется **обоими** sync-путями через один provider-neutral вход; результат capture становится структурным (`recovery_capture`) и видимым в terminal response синхронизации и в веб-строке синка; пять состояний capture сообщаются пользователю машинно-читаемо; ошибка capture не откатывает основной sync.
- Files/modules in scope:
  - `services/recovery_analytics.py` — общий вход capture + вычисление пяти состояний;
  - `services/sync.py` — Garmin-путь через общий контракт, без двойной записи;
  - `services/intervals_sync.py` — parity-вызов и аддитивное поле результата;
  - `api/sync_jobs.py` — прокидывание стабильного `job_id` как `capture_run_id`;
  - `api/routers/system.py` — аддитивный блок в payload обоих провайдеров;
  - `web/lib/types.ts` (+ `tests/contracts/ts_contract.json` регенерация) — контракт;
  - `web/components/sync/SyncControl.tsx` — readback (роль UI / Design Specialist);
  - `tests/smoke/*`, `tests/e2e/*` — RED/GREEN, паритет, идемпотентность, приёмка;
  - `docs/recovery_snapshot_capture_parity_execplan.md`, этот файл, `docs/architecture/asr_catalog.md`.

## Non-goals

- Behavior deliberately unchanged: правило pre-anchor (снимок обязан существовать до cutoff), формула readiness, пороги confidence, D+1/D+2/D+3, maturity gates, обучение `k_fitness`/`k_fatigue`/`tau_fitness`/`tau_fatigue`; исторические `missing_pre_anchor` не переклассифицируются и не backfill-ятся; провайдерский writeback и автокоррекция плана отсутствуют; схема БД и миграции не меняются; нового эндпоинта не появляется.
- Deferred work and owner: **cron/фоновое расписание**, **polling-надстройки**, **backfill исторических снимков**, **автоматическая коррекция плана** — вне scope по прямому non-goal issue и указанию владельца; расширение `web/app/recovery/` — только если понадобится уже существующий статус дневного capture, отдельным решением владельца; настоящий end-to-end на фейковом провайдере (если владелец предпочтёт его перехвату маршрутов) — отдельный слайс M6.

## Definition of Done

- [ ] Acceptance criteria наблюдаемы (RED Matrix ниже, по одной строке на каждый AC issue).
- [ ] Required tests/checks названы и пройдены: focused capture/sync/API/UI-контракт, широкий Python-контур, `ruff`, web `lint`/`build`/`contract:extract -- --check`, синтетическая browser-приёмка обоих провайдеров.
- [ ] Merge and cleanup owner назначен: rbctmz (мерж — отдельное действие владельца; после мержа — удаление ветки/worktree).

## Public Contracts

- `POST /api/sync` / `GET /api/sync` → `SyncResult` — **changed compatibly**: аддитивный ключ `recovery_capture` (объект или `null`); существующие ключи (`sync_state`, `severity`, `title`, `summary`, `counts`, `notices`, `source`, …) сохраняют смысл. Тесты: `tests/smoke/test_sync_job_api.py` (форма ответа для обоих источников). Уточнение по покрытию: реестр `tests/contracts/registry.json:145-150` связывает `/api/sync` с `SyncJobResponse`, но drift-харнесс делает только `GET` (`test_web_contract_drift.py:194`), в demo-сценарии `result` отсутствует, а `POST /api/sync` не покрыт вовсе; лишние поля API печатаются как INFO, а не как нарушение (`tests/smoke/conformance.py:9-13`), поэтому форма терминального ответа с новым блоком проверяется явным тестом, а не гейтом дрейфа.
- `web/lib/types.ts` — **changed compatibly**: новый `RecoveryCapture` и аддитивное поле в `SyncResult`; `tests/contracts/ts_contract.json` перегенерируется (`contract:extract`), гейт `--check` остаётся зелёным; инвентарь API обновляется (`contract:inventory`, `test_api_call_inventory.py`).
- `services/sync.py::sync_garmin_data`, `services/intervals_sync.py::sync_intervals_data` — **changed compatibly**: аддитивный keyword `capture_run_id: str | None = None`; прямой вызов без него сохраняет прежнее поведение (внутренняя генерация identity).
- `GarminSyncResult` / `IntervalsSyncResult` — **changed compatibly**: аддитивное поле `recovery_capture`.
- `services/recovery_analytics.py` — **changed compatibly**: публичный вход `capture_post_sync_recovery_state(...)`; существующий `record_post_sync_recovery_state(...)` сохраняет сигнатуру и поведение (его продолжают использовать существующие тесты и вызывающие).
- DB schema, таблицы, миграции — **unchanged**; новый эндпоинт — **не добавляется**; событий/CLI/конфигурации — **unchanged**.

## Failure, Reset, Rollback, Idempotency

- Failure modes and safe result: ошибка derived capture → `recovery_capture.status = "capture_failed"` с причиной, данные провайдера и статус основного sync не откатываются (см. ExecPlan D4 — вынесено на подтверждение владельцу); отсутствие provenance старта активности → `activity_start_missing` (fail-closed, без утверждения о pre-anchor); непригодный снимок → `ineligible` + причины eligibility без приватных значений.
- Retry/idempotency key: `capture_run_id` (для API-пути — `job_id`). Повтор того же рана → `created: false`, новая ревизия не создаётся; новый job в тот же день → новая монотонная ревизия в `target_key = readiness:prospective:<local_date>`; `fingerprint = sha256({capture_run_id, capture_mode})` остаётся неизменным по смыслу.
- Rollback procedure and proof: revert коммитов слайсов; журнал append-only, исторические строки не переписываются; доказательство — тест «после отката/повторного sync состояние читается и совпадает с ожидаемым» + отсутствие миграций в диффе.
- [x] Does this add **new persistent state**? Нет: используется существующий журнал `readiness_snapshots`; состояние capture вычисляется.
- [x] Does **full reset** remove every row/artifact/cursor introduced here? N/A — новых артефактов и курсоров нет.
- [x] Restart and partial-failure recovery are covered: запись снимка атомарна (`BEGIN IMMEDIATE`), обновление эпизодов изолировано `try/except`; capture-блок в terminal response переживает рестарт процесса только как часть ответа джоба — после рестарта он пересчитывается из журнала и активностей тем же детерминированным правилом.

## State Boundaries and Identity

- Source of truth and owner: канонический snapshot — `services/readiness_snapshot.py`; журнал и монотонная ревизия — `data/database.py::save_readiness_snapshot`; дневной anchor и eligibility — `models/recovery_response.py`; владелец post-sync capture — `services/recovery_analytics.py` (общий вход для обоих провайдеров).
- Stable identity/provenance keys: `capture_run_id` (стабилен на job), `target_key = readiness:<capture_mode>:<local_date>`, `fingerprint = sha256({capture_run_id, capture_mode})`, `revision` (монотонна в пределах `target_key`), `observed_at_utc` (UTC) + `athlete_timezone` → локальное время для UI.
- Cursor/checkpoint lifecycle: sync-курсоры провайдеров не затрагиваются; capture не двигает курсоры и не влияет на порядок ingest'а.
- Concurrency and stale-write behavior: `SyncJobManager` — single-flight по всем провайдерам, повторный запрос возвращает running-job (`reused=True`) и не создаёт второй capture; запись снимка сериализуется `BEGIN IMMEDIATE`.

## Evidence Boundary Matrix

| Провайдер | Время capture vs cutoff | Provenance старта активности | Eligibility | Ожидаемый статус / falsifier |
| --- | --- | --- | --- | --- |
| garmin | до первой активности | есть | eligible | `saved_before_load`; falsifier: статус иной при валидном pre-anchor |
| intervals | до первой активности | есть | eligible | `saved_before_load` (паритет с garmin) |
| любой | после первой активности | есть | eligible | `saved_too_late`; снимок остаётся аудируемой записью |
| любой | любое | старт отсутствует/нечитаем | любая | `activity_start_missing` (fail-closed, без утверждения о pre-anchor) |
| любой | любое | есть | ineligible | `ineligible` + причины (`low_confidence`, `stale_snapshot`, `stale_factor`, `missing_score`, `missing_as_of`, `future_factor`) |
| любой | любое | любое | любое (исключение в capture) | `capture_failed` + причина; данные провайдера сохранены |
| garmin/intervals | повтор того же рана | — | — | `created: false`, ревизия не растёт |
| garmin/intervals | новый job в тот же день | — | — | новая ревизия (`revision + 1`) для того же `target_key` |
| не-API поверхность (Streamlit/demo) | прямой вызов сервиса | есть | eligible | capture выполняется без `capture_run_id` (внутренняя identity) |

## RED Matrix

| Acceptance criterion (issue #562) | RED test or probe | Expected failure | GREEN evidence |
| --- | --- | --- | --- |
| AC1 Garmin: ровно одна идемпотентная ревизия на run, ошибка derived analytics не откатывает sync | `test_garmin_sync_captures_one_revision_per_run`, `test_capture_failure_keeps_provider_data` | до реализации нет структурного результата и стабильной identity; ошибка capture помечает ответ partial | одна ревизия; данные и статус провайдера сохранены, `capture_failed` в блоке |
| AC2 Intervals: тот же provider-neutral контракт | `test_intervals_sync_captures_with_the_shared_contract` | в `sync_intervals_data` capture отсутствует (`IntervalsSyncResult` без поля) | паритетный набор полей и состояний с Garmin на одной фикстуре |
| AC3 повтор run'а не создаёт ревизию; отдельная синхронизация в тот же день — новая монотонная | `test_repeated_job_id_does_not_create_a_revision`, `test_new_job_same_day_creates_monotonic_revision` | identity берётся из `uuid4()` внутри сервиса → повтор создаёт ревизию | `created: false` на повторе; `revision + 1` на новом job |
| AC4 снимок до нагрузки → API и веб показывают локальное время и статус «снимок до нагрузки сохранён» | `test_payload_reports_local_time_and_pre_load_status` (+ браузерный сценарий M6) | в payload нет блока, в UI нет строки | блок с `observed_at_local` и статусом; UI-строка отрендерена |
| AC5 capture после старта → снимок аудируется, но pre-anchor недоступен, причина машинно-читаема | `test_late_capture_is_audited_but_not_pre_anchor` | статус не отличается от «до нагрузки» | `saved_too_late` + `cutoff_at_utc`, `no_eligible_pre_anchor_snapshot` у anchor'а |
| AC6 нет provenance старта → `activity_start_missing` | `test_missing_activity_start_fails_closed` | состояние не сообщается вовсе | `activity_start_missing` в блоке и в причине anchor'а |
| AC7 снимок не прошёл eligibility → «сохранён, но не пригоден» | `test_ineligible_snapshot_is_reported_with_safe_reasons` | причины не выводятся | `ineligible` + список причин без приватных значений |
| AC8 terminal response виден в `SyncControl` для обоих источников | `test_m3_sync_ui_contract` (расширение) + браузерный сценарий | UI читает только `title`/`counts`/`notices` | статический контракт расширен; браузерный текст содержит статус для `garmin` и `intervals` |
| AC9 контракт: types.ts, `ts_contract.json`, инвентарь согласованы | `test_sync_payload_carries_recovery_capture_for_both_sources`, `contract:extract -- --check`, `test_api_call_inventory.py` | ключа нет; артефакт не содержит `RecoveryCapture` | ключ присутствует в форме ответа; артефакт свежий; инвентарь без дрейфа |
| AC10 существующие снимки/эпизоды читаемы, история не мутируется | `test_existing_snapshots_and_episodes_remain_readable` | новая логика пишет в те же строки иначе | старые строки читаются, число строк истории не меняется, `revision` не переписывается |
| Инвариант: статус capture ⇔ дневной anchor | `test_capture_status_matches_daily_anchor_decision` | две реализации одного правила расходятся | `saved_before_load` ⇔ anchor найден; остальные состояния ⇔ anchor отсутствует с той же причиной |
| Паритет провайдеров по форме | `test_provider_payload_shapes_match` | формы расходятся (у Intervals нет `details`) | обе формы несут одинаковый набор ключей `recovery_capture` |

## ASR / ADR Traceability

- ASRs affected: **ASR-REL-1** (ни одна производная дневная запись не теряется и не переписывается — parity capture и append-only журнал), **ASR-REL-2** (провал derived analytics не превращается в потерю данных и не маскирует причину; fail-closed `activity_start_missing`/`ineligible`), **ASR-MOD-2** (server-owned проекция: Python считает состояния, React только рендерит), **ASR-MOD-3** (контракт аддитивен, схема и миграции не меняются).
- ADRs reused: **ADR-0008** (multi-provider ingest и provider links) — переиспользуется; новый ADR не требуется, новая архитектурная граница не появляется.
- Tactic and trade-off: единый provider-neutral владелец capture + аддитивный структурный блок вместо текстового «details»; плата — правка контракта и UI-слайс в чужой роли (D6).
- New architecture boundary discovered during review: нет на момент написания; если checker назовёт такую границу, раунд ревью продолжается по правилам бюджета.

## Delivery Slices

1. Slice M1 — provider-neutral capture и run identity (`services/recovery_analytics.py`).
   - RED: `test_capture_status_*` (пять состояний), `test_capture_status_matches_daily_anchor_decision`, `test_capture_failure_is_reported_not_raised`.
   - GREEN: общий вход `capture_post_sync_recovery_state` + вычисление состояний + `provider` в аудите.
   - Refactor/contract refresh: не требуется (внутренний API сервиса).
   - Verification: focused capture-контур, существующий тест идемпотентности остаётся зелёным.
2. Slice M2 — Garmin без двойной записи (`services/sync.py`).
   - RED: `test_garmin_sync_captures_one_revision_per_run`, `test_capture_failure_keeps_provider_data`.
   - GREEN: замена инлайн-блока общим контрактом; аддитивное поле результата.
   - Verification: `test_garmin_sync_service.py` целиком + broad-контур.
3. Slice M3 — Intervals parity (`services/intervals_sync.py`).
   - RED: `test_intervals_sync_captures_with_the_shared_contract`, `test_provider_payload_shapes_match`.
   - GREEN: parity-вызов и аддитивное поле `IntervalsSyncResult`.
   - Verification: focused intervals/sync-контур.
4. Slice M4 — API↔web контракт (`api/routers/system.py`, `web/lib/types.ts`, артефакт).
   - RED: `test_sync_payload_carries_recovery_capture_for_both_sources`.
   - GREEN: ключ `recovery_capture` в обоих payload'ах, типы, регенерация артефакта.
   - Verification: `contract:extract -- --check`, `contract:inventory`, `test_contract_extractor.py`, `test_api_call_inventory.py`, web `lint`/`build`.
5. Slice M5 — UI readback (роль UI / Design Specialist, D6). Точки монтирования: `web/app/dashboard/page.tsx:42` (компактно) и `:128` (подробно, пустое состояние); отдельная страница синка не создаётся.
   - RED: расширение статических проверок `tests/smoke/test_m3_sync_ui_contract.py` (в `web/` нет JS-раннера; `formatSyncJob` сегодня не покрыт ни одним тестом).
   - GREEN: рендер локального времени, статуса и причины в строке синка; утверждение целится в видимый вариант строки (`<p>` на `:147` против `hidden … sm:inline` на `:155`).
   - Verification: статический UI-контракт + web `lint`/`build`.
6. Slice M6 — приёмка и evidence bundle. Каталог `tests/e2e/fixtures/` отсутствует и создаётся этим слайсом; `PRIMARY_ACTIVITY_SOURCE` и `ACCEPTANCE_*` в web-стенд не подключены (только Streamlit), поэтому сценарий строится на перехвате маршрутов.
   - RED/GREEN: браузерные сценарии обоих провайдеров (D5), тест «фикстура ↔ форма ответа», `test_existing_snapshots_and_episodes_remain_readable`, обновление `asr_catalog.md`.
   - Verification: `pytest -m e2e tests/e2e -q` + широкий Python-контур + запись метрик после мержа.

## Evidence Bundle

- Head SHA: plan-only (SHA ветки плана — в PR)
- Changed invariants: capture выполняется обоими провайдерами через один контракт; идентичность рана стабильна на job; пять состояний выводимы и согласованы с дневным anchor'ом; ошибка capture не откатывает основной sync.
- Focused and broad tests: TBD (заполняется в M1–M6)
- CI checks/reruns/flakes: TBD
- Lifecycle/probe evidence: TBD (прогоны до/после по каждому слайсу; браузерные тексты для обоих провайдеров)
- Changed contracts: аддитивный `recovery_capture` в ответе синхронизации + `RecoveryCapture` в `web/lib/types.ts` + регенерированный `tests/contracts/ts_contract.json`
- Unresolved review-thread count: TBD
- Residual risks and follow-ups: изменение статуса синка при сбое capture (D4) — на подтверждении владельца; подход к browser-приёмке (D5) — на подтверждении владельца; разделение ролей на UI-слайсе (D6)

## Review Findings

| Severity | Evidence and falsifying check | Gate | Owner/status |
| --- | --- | --- | --- |
| — | Findings появятся после ревью плана владельцем и раунда независимого checker'а | — | — |

## Native Review Rounds

| Round | Reviewed head SHA | Trigger | Findings disposition | Stop / exception decision |
| ---: | --- | --- | --- | --- |
| 1 | TBD | manual (ревью плана владельцем) | TBD | continue / stop |
| 2 | TBD | automatic (`@codex review` после реализации) | TBD | continue / stop |

## Final Verdict

- Verdict: PLAN READY FOR OWNER REVIEW (код не изменён; реализация не начата)
- Blocking findings remaining: нет на момент написания; открытые вопросы — D4 (статус синка при сбое capture) и D5 (механизм browser-приёмки)
- Review rounds used: 0 / 2
- Accepted risk or follow-up issue: расширения (cron, polling, backfill, автокоррекция плана, фейковый провайдер для end-to-end) — вне scope, зафиксированы в `Non-goals`
- Merge owner final gate: rbctmz
- Post-merge sync/branch/worktree/progress cleanup: план-ветка удаляется после ревью или переиспользуется под реализацию (решение владельца); запись метрик Class A — после мержа реализации
