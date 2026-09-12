# Slice Spec And Review Template — issue #562 (post-sync readiness snapshot capture parity)

Рабочая спецификация по `docs/templates/slice_spec_review_template.md`; связана с живым ExecPlan `docs/recovery_snapshot_capture_parity_execplan.md` (issue #562) и не дублирует формат `.agent/PLANS.md`.

- Issue / PR: [#562](https://github.com/rbctmz/ai_trainer/issues/562) (PR: plan-only этап — см. ветку плана)
- Author / checker / merge owner: agent (Spec / Architecture Owner на plan-only этапе; реализация M1–M4 — Domain / API Implementer, M5 — UI / Design Specialist) / независимый checker на PR (`@codex review`) / rbctmz
- Date: 2026-09-12
- Candidate head SHA: раунд 1 отревьюил `4ae3f4b`, раунд 2 — `20f9dcb` (неизменяемые факты; правки раунда 1 — `3a4a39d`). Код не менялся: диф состоит только из этого файла и ExecPlan

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
- Review budget used: **1 / 2 rounds** (раунд 1 на `4ae3f4b`: 6 находок — 1 P1 + 5 P2, все `fixed-in 3a4a39d`)
- Review trigger mode: automatic (`@codex review` на PR)
- Review acceptance head SHA: TBD — фиксируется в момент acceptance (отревьюенные раунды: `4ae3f4b`, затем `20f9dcb`)
- Review budget exception: N/A — бюджет не превышен

**Устаревшая зависимость issue.** В теле issue сказано «Related but deliberately separate from **open** #557». На дату плана #557 **закрыт** (смержен PR #563, merge-коммит `a82be7b`), и в main уже живут его семантики: metric-scoped provenance (`sleep_score_observed_at`, `total_sleep_observed_at`, `rmssd_observed_at`, `resting_hr_observed_at`, `training_readiness_observed_at`), аддитивный канал `freshness`/`intervention_*`, fail-closed гейт и athlete-local (а не серверные) anchor'ы дат. План **опирается** на эти семантики и не дублирует их: capture по-прежнему строит канонический snapshot через `services/readiness_snapshot.py`, а `freshness`/`intervention_*` — часть этого snapshot'а. Разделение из issue сохраняется: #562 отвечает за *паритет и видимость capture*, а не за свежесть входов readiness.

## Scope

- Behavior that changes: post-sync derived capture выполняется **обоими** sync-путями через один provider-neutral вход; результат capture становится структурным (`recovery_capture`) и видимым в terminal response синхронизации и в веб-строке синка; пять состояний capture сообщаются пользователю машинно-читаемо; ошибка capture не откатывает основной sync.
- Files/modules in scope:
  - `services/recovery_analytics.py` — общий вход capture + вычисление пяти состояний;
  - `services/sync.py` — Garmin-путь через общий контракт, без двойной записи;
  - `services/intervals_sync.py` — parity-вызов и аддитивное поле результата;
  - `api/sync_jobs.py` — генерация **полного UUID** `capture_run_id` рядом с коротким `job_id` (display handle) и прокидывание его в раннер и сервисы;
  - `api/routers/system.py` — аддитивный блок в payload обоих провайдеров;
  - `web/lib/types.ts` (+ `tests/contracts/ts_contract.json` регенерация) — контракт;
  - `web/components/sync/SyncControl.tsx` — readback (роль UI / Design Specialist);
  - `tests/smoke/*`, `tests/e2e/*` — RED/GREEN, паритет, идемпотентность, приёмка;
  - `docs/recovery_snapshot_capture_parity_execplan.md`, этот файл, `docs/architecture/asr_catalog.md`.

## Non-goals

- Behavior deliberately unchanged: правило pre-anchor (снимок обязан существовать до cutoff), формула readiness, пороги confidence, D+1/D+2/D+3, maturity gates, обучение `k_fitness`/`k_fatigue`/`tau_fitness`/`tau_fatigue`; исторические `missing_pre_anchor` не переклассифицируются и не backfill-ятся; провайдерский writeback и автокоррекция плана отсутствуют; схема БД и миграции не меняются; нового эндпоинта не появляется.
- Deferred work and owner: **cron/фоновое расписание**, **polling-надстройки**, **backfill исторических снимков**, **автоматическая коррекция плана** — вне scope по прямому non-goal issue и указанию владельца; расширение `web/app/recovery/` — только если понадобится уже существующий статус дневного capture, отдельным решением владельца; настоящий provider E2E на фейковом провайдере — подтверждённо вне scope (владелец выбрал browser contract/UX acceptance); вводится только отдельным решением.

## Definition of Done

- [ ] Acceptance criteria наблюдаемы (RED Matrix ниже, по одной строке на каждый AC issue).
- [ ] Required tests/checks названы и пройдены: focused capture/sync/API/UI-контракт, широкий Python-контур, `ruff`, web `lint`/`build`/`contract:extract -- --check`, синтетическая browser-приёмка обоих провайдеров.
- [ ] Merge and cleanup owner назначен: rbctmz (мерж — отдельное действие владельца; после мержа — удаление ветки/worktree).

## Public Contracts

- `POST /api/sync` / `GET /api/sync` → `SyncResult` — **changed compatibly**: аддитивный ключ `recovery_capture` (объект или `null`); существующие ключи (`sync_state`, `severity`, `title`, `summary`, `counts`, `notices`, `source`, …) сохраняют смысл. Тесты: `tests/smoke/test_sync_job_api.py` (форма ответа для обоих источников). Уточнение по покрытию: реестр `tests/contracts/registry.json:145-150` связывает `/api/sync` с `SyncJobResponse`, но drift-харнесс делает только `GET` (`test_web_contract_drift.py:194`), в demo-сценарии `result` отсутствует, а `POST /api/sync` не покрыт вовсе; лишние поля API печатаются как INFO, а не как нарушение (`tests/contracts/conformance.py:9-13`; импортируется в `tests/smoke/test_web_contract_drift.py:35`), поэтому форма терминального ответа с новым блоком проверяется явным тестом, а не гейтом дрейфа.
- `web/lib/types.ts` — **changed compatibly**: новый `RecoveryCapture` и аддитивное поле в `SyncResult`; `tests/contracts/ts_contract.json` перегенерируется (`contract:extract`), гейт `--check` остаётся зелёным; инвентарь API обновляется (`contract:inventory`, `test_api_call_inventory.py`).
- `services/sync.py::sync_garmin_data`, `services/intervals_sync.py::sync_intervals_data` — **changed compatibly**: аддитивный keyword `capture_run_id: str | None = None`; прямой вызов без него сохраняет прежнее поведение (внутренняя генерация identity).
- `GarminSyncResult` / `IntervalsSyncResult` — **changed compatibly**: аддитивное поле `recovery_capture`.
- `services/recovery_analytics.py` — **changed compatibly**: публичный вход `capture_post_sync_recovery_state(...)`; существующий `record_post_sync_recovery_state(...)` получает аддитивный keyword `capture_provider: str | None = None` и пишет провайдера в уже существующий JSON провенансы (`input_provenance.capture_provider`), поэтому провайдер восстанавливается из журнала без новой колонки и миграции; остальное поведение и все существующие вызовы сохраняются. Тест: сохранённая строка журнала несёт провайдера.
- DB schema, таблицы, миграции — **unchanged**; новый эндпоинт — **не добавляется**; событий/CLI/конфигурации — **unchanged**.

## Failure, Reset, Rollback, Idempotency

- Failure modes and safe result: ошибка derived capture → данные провайдера сохранены, `sync_state="partial"` и warning **сохраняются**, а `recovery_capture.status = "capture_failed"` с причиной объясняет, какая производная операция не выполнилась (решение владельца по D4: fail-open — это отсутствие отката, а не ложный `succeeded`); отсутствие provenance старта активности → `activity_start_missing` (fail-closed, без утверждения о pre-anchor); непригодный снимок → `ineligible` + причины eligibility без приватных значений.
- Retry/idempotency key: `capture_run_id` — **полный UUID**, генерируемый на job (короткий `job_id` остаётся display handle и в идентичность не попадает: 32-битное пространство при глобальном дедупе по `(capture_mode, capture_run_id)` дало бы молчаливую потерю дневной ревизии). Повтор того же рана → `created: false`, новая ревизия не создаётся; новый job в тот же день → новая монотонная ревизия в `target_key = readiness:prospective:<local_date>`; `fingerprint = sha256({capture_run_id, capture_mode})` остаётся неизменным по смыслу.
- Rollback procedure and proof: revert коммитов слайсов; журнал append-only, исторические строки не переписываются; доказательство — тест «после отката/повторного sync состояние читается и совпадает с ожидаемым» + отсутствие миграций в диффе.
- [x] Does this add **new persistent state**? **Да, аддитивно**: в существующую строку журнала `readiness_snapshots` добавляется провенанса провайдера (`input_provenance.capture_provider` внутри `provenance_json`) — новых колонок, таблиц и курсоров нет, владелец состояния тот же журнал, отдельного age-out не вводится; состояние capture по-прежнему вычисляется, а не хранится.
- [x] Does **full reset** remove every row/artifact/cursor introduced here? Новых артефактов и курсоров нет; провенанса живёт и умирает вместе со строкой снимка, поэтому reset/export обязан сохранять читаемость `provenance_json` — существующее поведение журнала, покрывается тестом «сохранённая строка несёт провайдера».
- [x] Restart and partial-failure recovery are covered **с явной границей**: запись снимка атомарна (`BEGIN IMMEDIATE`), обновление эпизодов изолировано `try/except`; дурабельна только сама строка снимка с её провенансой. Терминальный `recovery_capture` в ответе job'а **эфемерен** (`SyncJobManager` process-local, новый процесс стартует с idle-снимком), а `capture_failed` не пишет ни строки в журнал — поэтому «переживает рестарт» здесь не заявляется; для успешных capture статус детерминированно пересчитывается из журнала и активностей, для провалов — нет (персистенция исходов вынесена в non-goals, решение владельца).

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
| AC8 terminal response виден в `SyncControl` для обоих источников, включая все пять состояний | `test_m3_sync_ui_contract` (расширение) + параметризованные браузерные сценарии (5 состояний × 2 источника) | UI читает только `title`/`counts`/`notices`, «плохие» состояния падают в общий текст | статический контракт расширен; браузерный текст содержит корректный статус и причину для каждого из пяти состояний на обоих источниках |
| AC9 контракт: types.ts, `ts_contract.json`, инвентарь согласованы | `test_sync_payload_carries_recovery_capture_for_both_sources`, `contract:extract -- --check`, `test_api_call_inventory.py` | ключа нет; артефакт не содержит `RecoveryCapture` | ключ присутствует в форме ответа; артефакт свежий; инвентарь без дрейфа |
| AC10 существующие снимки/эпизоды читаемы, история не мутируется | `test_existing_snapshots_and_episodes_remain_readable` | новая логика пишет в те же строки иначе | старые строки читаются, число строк истории не меняется, `revision` не переписывается |
| Инвариант: статус **ревизии** ⇔ её собственное время относительно cutoff | `test_capture_status_is_per_revision`, `test_late_revision_does_not_steal_the_day_anchor` | статус выводится из наличия дневного anchor'а → при нескольких ревизиях новая помечается неверно | ревизия 05:00 = `saved_before_load`, ревизия 11:00 после активности 10:00 = `saved_too_late`, anchor дня остаётся у 05:00 |
| Приоритет статусов при пересечении предикатов | `test_status_precedence_on_overlapping_predicates` | непригодная ревизия в день с нечитаемым стартом помечается `ineligible`, хотя `select_daily_anchor` сообщает `activity_start_missing` | `activity_start_missing` побеждает: порядок `capture_failed` → `activity_start_missing` → `ineligible` → before/too_late |
| Дневной инвариант: anchor существует ⇔ есть ревизия `saved_before_load` | `test_day_anchor_matches_revision_set` | дневное правило и статусы расходятся | anchor = последняя eligible-ревизия с `t_r ≤ cutoff`; при отсутствии таких ревизий anchor'а нет с той же причиной |
| Паритет провайдеров по форме | `test_provider_payload_shapes_match` | формы расходятся (у Intervals нет `details`) | обе формы несут одинаковый набор ключей `recovery_capture` |

## ASR / ADR Traceability

- ASRs affected: **ASR-REL-3** — «обрыв sync/maintenance не портит частичные данные» (`docs/architecture/asr_catalog.md:17`): именно этот контур отвечает за fail-open границу, cursor-after-clean-batch и независимость производной аналитики от основной синхронизации; **ASR-REL-2** — «отсутствие данных → data gap, не падение» (:16): fail-closed `activity_start_missing`/`ineligible` и честная причина вместо маскировки; **ASR-MOD-2** — server-owned проекция (Python считает состояния, React только рендерит); **ASR-MOD-3** — аддитивный контракт без схемы и миграций. **ASR-REL-1** (reconciliation плана и факта, :15) этот контур не затрагивает: ни одна reconcilation-инварианта не меняется.
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
6. Slice M6 расщеплён по ролевым границам (review P2) — у каждой части свой владелец и критерий:
   - **M6a — Domain / API Implementer (продолжает после M4):** тест «фикстура ↔ форма ответа» (pinning), паритетный payload-тест обоих источников, `test_existing_snapshots_and_episodes_remain_readable`, идемпотентность/монотонность, fail-open, инвариант «статус ревизии ⇔ время относительно cutoff», приоритет статусов.
   - **M6b — UI / Design Specialist (продолжает после M5):** browser contract/UX acceptance — каталог `tests/e2e/fixtures/` отсутствует и создаётся здесь; `PRIMARY_ACTIVITY_SOURCE` и `ACCEPTANCE_*` в web-стенд не подключены (только Streamlit), поэтому сценарий строится на перехвате маршрутов; параметризованные сценарии на все пять состояний × оба провайдера (D5; это не provider E2E) с утверждением видимого варианта строки.
   - **M6c — Spec / Architecture Owner:** обновление `docs/architecture/asr_catalog.md` (ASR-REL-3/REL-2/MOD-2/3) и сборка итогового evidence bundle в PR реализации.
   - Verification: `pytest -m e2e tests/e2e -q` (M6b) + широкий Python-контур (M6a) + запись метрик после мержа (M6c).

## Evidence Bundle

- Head SHA плана: отревьюенные раундами head'ы — `4ae3f4b` и `20f9dcb` (неизменяемо); реализация идёт отдельной веткой от обновлённого `main` — D8, там же будет её собственный evidence bundle
- Changed invariants: capture выполняется обоими провайдерами через один контракт; идентичность рана стабильна на job; пять состояний выводимы и согласованы с дневным anchor'ом; ошибка capture не откатывает основной sync.
- Focused and broad tests: N/A на plan-этапе — заполняется в M1–M6 на ветке реализации (D8)
- CI checks/reruns/flakes: N/A на plan-этапе; проверки плана — `pytest tests/smoke/test_dev_workflow_v2_docs.py` (`6 passed`), `ruff check .` (чисто), диф только из двух docs-файлов; прогоны реализации — в её PR
- Lifecycle/probe evidence: N/A на plan-этапе — прогоны до/после по каждому слайсу и тексты browser contract/UX acceptance будут в ветке реализации
- Changed contracts: аддитивный `recovery_capture` в ответе синхронизации + `RecoveryCapture` в `web/lib/types.ts` + регенерированный `tests/contracts/ts_contract.json`
- Unresolved review-thread count: 0 (6 тредов раунда 1 закрыто, новых нет)
- Residual risks and follow-ups: решения владельца получены — D4 отклонён в первоначальном виде (сохраняются `sync_state="partial"` и warning), D5 подтверждён (browser contract/UX acceptance, не provider E2E); разделение ролей на UI-слайсе (D6); **эфемерность терминального readback** — исход capture (включая `capture_failed`) не переживает рестарт API и не хранится в журнале, персистенция вынесена в non-goals и требует решения владельца (review P2)

## Review Findings

| Severity | Evidence and falsifying check | Gate | Owner/status |
| --- | --- | --- | --- |
| **P1** | D3: статус `saved_before_load` выводился из наличия дневного anchor'а и ломался при нескольких ревизиях в один день (AC3) — falsifier: 05:00-ревизия «прикрывала» 11:00-ревизию после активности 10:00 | fixed-in `3a4a39d`: состояние привязано к ревизии, дневное правило вынесено в отдельный инвариант + 3 теста | agent / closed |
| **P2** | D2: `job_id = uuid4()[:8]` (32 бита) при глобальном дедупе по `(capture_mode, capture_run_id)` мог молча потерять дневную ревизию — falsifier: две записи с одним run id на разные даты дали `created: false` | fixed-in `3a4a39d`: устойчивая идентичность — полный UUID, короткий id остаётся display handle | agent / closed |
| **P2** | spec: «переживает рестарт» противоречило process-local `SyncJobManager`, а `capture_failed` не пишет в журнал — falsifier: новый менеджер вернул `idle` с `result=None` | fixed-in `3a4a39d`: readback объявлен эфемерным, персистенция исходов — в `Non-goals` | agent / closed |
| **P2** | M1: провайдер заявлялся в аудите, но места хранения нет (`readiness_snapshots` без колонки, запись внутри рекордера) | fixed-in `3a4a39d`: `input_provenance.capture_provider` в существующем JSON, без миграции; снято противоречие про неизменную сигнатуру | agent / closed |
| **P2** | traceability: надёжность sync/fail-open приписана `ASR-REL-1` (reconciliation) вместо `ASR-REL-3` | fixed-in `3a4a39d`: маппинг исправлен на REL-3/REL-2/MOD-2/3, REL-1 явно не затрагивается | agent / closed |
| **P2** | приёмка: обещаны пять состояний, исполняемо проверялись два; статическая проверка не исполняет `formatSyncJob` | fixed-in `3a4a39d`: параметризованные browser-сценарии на все пять состояний × оба провайдера | agent / closed |

## Native Review Rounds

| Round | Reviewed head SHA | Trigger | Findings disposition | Stop / exception decision |
| ---: | --- | --- | --- | --- |
| 1 | `4ae3f4b` | automatic (`@codex review` при открытии PR) | 6 находок (1 P1 + 5 P2), все `fixed-in 3a4a39d`, 6/6 тредов закрыто | continue: запрошен scoped delta-раунд 2 |
| 2 | `20f9dcb` | verification (scoped delta since `4ae3f4b`) | **9 находок (8 P2 + 1 P3)**: приоритет статусов, несогласованность D2 со spec, `capture_provider` как persistent state, двойной идентификатор, незакрытый D5, отсутствие неизменяемого reviewed SHA, неверный путь `conformance.py`, устаревшая ревизия плана, нерасщеплённый M6 | правки внесены; бюджет 2/2 — дальнейший раунд только по решению владельца |

## Final Verdict

- Verdict: PLAN REVISED — ожидает раунда 2 (код не изменён; реализация не начата)
- Blocking findings remaining: нет — все шесть находок раунда 1 закрыты письменно; решения владельца получены: **D4 отклонён в первоначальном виде** (сохраняются `sync_state="partial"` и warning), **D5 подтверждён** (browser contract/UX acceptance)
- Review rounds used: 1 / 2 (раунд 2 запрошен)
- Accepted risk or follow-up issue: расширения (cron, polling, backfill, автокоррекция плана, provider E2E на фейковом провайдере) — вне scope; эфемерность терминального readback принята осознанно (решение владельца)
- Merge owner final gate: rbctmz
- Post-merge cleanup (D8): plan-PR мержится **отдельно** и под реализацию **не переиспользуется** — M1–M6 идут новой веткой от обновлённого `main` со своим review budget; план-ветка и её worktree удаляются после мержа плана; запись метрик Class A — после мержа реализации
