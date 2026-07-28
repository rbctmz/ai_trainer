# ASR Catalog — единая точка истины по quality attributes

Статусы на 2026-07-28. Источник сценариев: `architecture_analysis_add3.md` §2.
Правило ведения: новый архитектурный трек (ExecPlan) обязан назвать задетые
ASR в секции «ASR / risk traceability» и обновить здесь статус/проверку.
Подтверждённые открытые улучшения ведутся по стабильным ID в
[`../technical_debt_register.md`](../technical_debt_register.md).

| ID | Сценарий | Приоритет | Как обеспечивается | Как проверяется | Статус |
|----|----------|-----------|--------------------|-----------------|--------|
| ASR-PERF-1 | «Сегодня» < 2 сек с 3 годами данных | High | локальный SQLite, canonical snapshot без provider-вызовов на рендере (`include_provider=False`, #228) | `test_today_snapshot_perf_gate.py` — p95 < 2с на 3 годах синтетических данных (#241) | ✅ |
| ASR-PERF-2 | Коуч: первый токен < 5 сек | High | стриминг SSE; native function calling (#190) убрал маркерный второй проход у поддерживающих провайдеров | `first_token_ms` в SSE `done`, покрыт смоуком (#241); 5с — наблюдение, авто-гейта на порог нет (недетерминизм провайдера) | 🟡 |
| ASR-PERF-3 | Инкрементальный provider-sync, дельта дня < 10 сек | Medium | Garmin incremental window; Intervals per-provider/per-domain cursors | smoke sync/cursor-сьюты | ✅ |
| ASR-PERF-4 | Planning preview 16 недель < 10 сек | Medium | детерминированный scheduler без БД внутри цикла (#205) | референс-сборки в smoke (секунды) | ✅ |
| ASR-REL-1 | Reconciliation: ни одна активность не теряется при перепланировании | High | content-derived session identity + lineage (`replaces_session_id`, #206/#209), append-only ledger | `test_recovery_transfer_identity_handoff.py`, twin-матрица identity | ✅ |
| ASR-REL-2 | Отсутствие данных → data gap, не падение | High | gate-исходы silence/data_gap (#154), `has_plan=false` пробросы (#228) | smoke-гейты loop/ribbon | ✅ |
| ASR-REL-3 | Обрыв sync/maintenance не портит частичные данные | Medium | атомарный common-ingest; cursor-after-clean-batch; независимые activity/wellness cursors; SQLite restore через validated temp + atomic replace + pre-restore rollback | M0/M1 ingest/cursor, M4 wellness rollback и `test_sqlite_backup_restore.py` fail-before-replace | ✅ |
| ASR-MOD-1 | Новый AI-провайдер без правки основного кода | High | `AIProvider` ABC + фабрика; capability-флаги (`supports_native_tools`, #190) делают расширения аддитивными | capability-матрица в `test_coach_native_tools.py` | ✅ |
| ASR-MOD-2 | Новый компонент дашборда без регрессии | Medium | canonical snapshot проекции (#152/#153) | trust-alignment smoke | ✅ |
| ASR-MOD-3 | Смена схемы — обратная совместимость | Medium | аддитивные поля чекпойнтов, migrate-on-read (#206), append-only журналы | legacy-byte-equivalence гейты | ✅ |
| ASR-SEC-1 | Ключи не в логах/UI/git | High | `.env` вне git, UI скрывает поля, env-fallback | ревью; авто-скана нет ([TD-002](../technical_debt_register.md#td-002--secret-scan-в-ci)) | 🟡 |
| ASR-SEC-2 | Basic Auth перед публичным доступом | High | Caddy + Basic Auth в self-hosted стеке | деплой-чеклист | ✅ |
| ASR-DEP-1 | `docker compose up` поднимает весь стек | High | compose + `/api/health` + healthcheck (уже реализованы) | самопроверка compose | ✅ |
| ASR-DEP-2 | Обновление без потери данных | High | SQLite в named volume; append-only чекпойнты; stopped-service Backup API snapshot, integrity check, atomic restore и pre-restore rollback (#293) | `test_sqlite_backup_restore.py`: clean-volume domain drill + rollback/failure gates | ✅ |

## Intervals-primary ingest (ADR-0008; ASR-REL-3, ASR-MOD-3, ASR-PERF-3; #269)

Трек «другой атлет на своих данных через Intervals.icu» (ExecPlan
`docs/intervals_primary_handoff_execplan.md`, ADR
`docs/architecture/adr_0008_intervals_activity_ingestion.md`) вводит provider-link
модель приёма активностей из нескольких источников. Задетые ASR:

- **ASR-REL-3** (обрыв sync не портит частичные данные): `ingest_provider_activity`
  пишет canonical + provider-link + `source_tss`-проекцию в ОДНОЙ
  SQLite-транзакции — сбой не оставляет ни полу-записи, ни orphan-link. Курсор
  двигается ОТДЕЛЬНО, лишь после успешного batch/window (`ingest_provider_batch`),
  не в per-activity транзакции — сбой в середине batch'а не оставляет данные за
  курсором, повтор идемпотентен. Проверка (M0): schema RED→GREEN + ingest-атомарность
  (no-orphan) + batch-failure (cursor).
- **ASR-MOD-3** (смена схемы обратно-совместима): миграция `activity_provider_links`
  аддитивна и идемпотентна; `canonical_activity_id` = существующий `activity_id`,
  потребители не ломаются. Проверка: `test_activity_provider_links_schema.py`
  (RED→GREEN, M0).
- **ASR-PERF-3** (инкрементальный sync): per-provider/per-domain курсоры не
  раздувают окно при activity-only Intervals-синке.

Статус: M0 (#269) — схема + CHECK-констрейнты + `PRIMARY_ACTIVITY_SOURCE` (fail-fast),
common-ingest (`services/activity_ingest.py`: `normalize_provider_activity`,
per-activity атомарный `ingest_provider_activity`, batch-level `ingest_provider_batch`
с cursor-after-batch, офлайн `backfill_provider_links`). Каноническая = детерминированная
ПРОЕКЦИЯ набора связей (per-link `provider_payload`), поэтому слияние/ambiguous/смена
identity — без потерь и order-independent; `source` → garmin только по точному whitelist.
Обязательные матрицы (`test_activity_ingest.py`, 33 tests): order-independence,
backfill-стабильность, batch-cursor на сбое, ingest no-orphan, ambiguous order-independent,
identity-change reproject, атомарный rollback. Подключение реальных источников — M1.

### M3 handoff: source-agnostic UI и Docker quickstart (#272)

M3 расширяет Intervals-primary трек на продуктовую и deploy-поверхность
(`docs/intervals_primary_m3_slice_spec.md`):

- **ASR-SEC-1**: `GET /api/sync/providers` возвращает только configuration flags
  и безопасную metadata; explicit Intervals probe возвращает bounded summary
  (`ok`, `source`, `calendar_count`). API key и ответы провайдера не попадают в
  UI. Проверка: `test_m3_sync_provider_api.py`.
- **ASR-DEP-1**: `docs/intervals_primary_quickstart.md` фиксирует воспроизводимый
  Intervals-only запуск через Docker Compose; конфигурация проверяется
  `docker compose config --quiet` и `test_m3_quickstart.py`.
- **ASR-DEP-2**: quickstart использует существующий named SQLite volume,
  документирует сохранение данных при обычном `down` и помечает `down -v` как
  destructive. Offline backup/restore и проверяемый restore drill завершены
  позднее в #293; актуальный runbook —
  [`sqlite_backup_restore.md`](../sqlite_backup_restore.md).
- **ASR-MOD-2**: reusable `web/components/sync/SyncControl.tsx` потребляет
  явный provider API contract; dashboard не выводит источник из несвязанных
  метрик и не дублирует Garmin-specific логику. Проверка:
  `test_m3_sync_ui_contract.py` и browser handoff.

Статус: M3 завершён; Intervals-only путь от пустой SQLite через sync и planning
onboarding до плана в `/planning` и `/today` подтверждён hermetic API-тестом и
изолированной browser-вертикалью.

### M4 wellness: metric provenance и атомарный доменный cursor (#273)

M4 добавляет bounded `GET /wellness` и чистую mapping-границу
`services/wellness_ingest.py`: `hrv` трактуется только как rMSSD (мс),
`sleepSecs` — как минуты сна, `restingHR` — как пульс покоя. `hrvSDNN`,
provider readiness и готовые CTL/ATL намеренно не входят в канон.

- **ASR-REL-2**: отсутствующие метрики остаются data gap; этапы сна не
  синтезируются. Readiness считается полным по каноническим sleep/HRV/RHR и не
  требует Garmin-only `training_readiness`.
- **ASR-REL-3**: HRV, сон, RHR и `(provider, wellness)` cursor коммитятся одной
  SQLite-транзакцией. Malformed/provider error держит только wellness cursor,
  не откатывая чистый activity-домен.
- **ASR-MOD-2**: Sleep/HRV API возвращают metric-scoped provenance;
  web-поверхности не ветвятся по Garmin как по обязательному источнику.
- **ASR-MOD-3**: `rmssd_source`, `total_sleep_source`,
  `resting_hr_source` добавляются migrate-on-read с
  `legacy_unknown`, без переписывания legacy-значений.
- **ASR-PERF-3**: отдельный per-provider/per-domain cursor ограничивает
  повторную выборку wellness.

Проверка: `test_m4_intervals_wellness.py` (mapping/fail-closed, legacy schema,
atomic rollback, order independence, independent cursors, readiness, API/UI)
и существующая Garmin/readiness regression.

### M5 Garmin demotion: source-aware presentation contract (#274)

M5 завершает Intervals-primary трек только на presentation-границе:
`services/sync_providers.py` выдаёт Intervals.icu первым и безопасное описание
роли каждого источника; `web/lib/sourceLabels.ts` является единой точкой
преобразования provenance в пользовательские подписи.

- **ASR-MOD-2**: Sleep/HRV/Dashboard/Profile больше не дублируют provider
  branches; новый canonical source label добавляется в одном formatter.
- **ASR-MOD-3**: схема, provider-links и backfill не меняются. История владельца
  сохраняется существующими M0/M1 ingest regression suites.
- **ASR-REL-2**: неизвестный или legacy source деградирует в
  «источник не сохранён», а не ломает UI и не раскрывает техническое значение.

Проверка: `test_m5_garmin_demotion.py`, M3/M4 source regressions, Next lint/build
и изолированная browser-приёмка пустого Dashboard. Статус: M5 завершён.

## SQLite backup/restore (ADR-0002; ASR-DEP-2, ASR-REL-3; #293)

TD-001 закрыт stopped-service CLI
`scripts/sqlite_backup_restore.py`. Snapshot создаётся стандартным SQLite
Backup API во временном файле рядом с назначением, проходит
`PRAGMA integrity_check`, `fsync` и публикуется через `os.replace`. Restore
существующего target сначала создаёт отдельный validated rollback; stale
`-wal`/`-shm`/`-journal` удаляются после замены.

- **ASR-DEP-2**: `test_sqlite_backup_restore.py` восстанавливает snapshot в
  отсутствующий файл чистого временного каталога и читает каноническую
  активность, provider-link, planning checkpoint, HRV, сон и resting HR.
- **ASR-REL-3**: invalid backup и injected final-replace failure не меняют
  target; существующий target имеет проверенный rollback до мутации.
- **Operational boundary**: CLI требует `--confirm-stopped`; Docker backup
  выводится через bind mount за пределы named volume. Команды и аварийная
  rollback-ветка находятся в
  [`docs/sqlite_backup_restore.md`](../sqlite_backup_restore.md).

## Контракт-тесты API-роутеров (ASR-MOD-2, issue #242)

Свип по `api/routers/*` (кодовый долг из ATAM-карты, `architecture_analysis_add3.md`
§4.1: «нет contract tests → рефакторинг ломает api молча»). Установленный
паттерн — прямой вызов router-функций с временной SQLite `Database` (без
`TestClient`/HTTP-слоя, без live-провайдеров), как в существующих
`tests/smoke/test_api_*.py`. Минимум на роутер: (а) успешный ответ с ключевыми
полями схемы, (б) пустое/degraded-состояние без 500, (в) неверный вход там, где
у роутера есть собственная validation-ветка (`HTTPException(422, …)`, маппинг
исключений вида `LookupError -> 404` / `ValueError -> 422`) или Pydantic-констрейнт
на request-модели.

Важно про (в): из-за прямого вызова router-функций проверяются два слоя — своя
validation/exception-ветка роутера и констрейнты request-моделей (то, что
FastAPI отклонит до хендлера). Настоящий HTTP-round-trip через валидацию FastAPI
(path/query `Query`-констрейнты) требует `TestClient` и смены паттерна; он закрыт
для `planning.py` в #248 отдельным файлом — см. ниже.

| Роутер | Тест-файл(ы) |
|--------|--------------|
| `activities.py` | `test_api_operational_states.py`, `test_api_phase1.py` |
| `adherence.py` | `test_adherence_ribbon.py` |
| `athlete_profile.py` | `test_api_athlete_profile_contract.py` |
| `coach.py` | `test_api_operational_states.py`, `test_api_phase1.py`, `test_coach_decisions.py`, `test_coach_native_tools.py`, `test_readiness_snapshot_contract.py`, `test_readiness_conflicts.py`, `test_coach_load_metrics_window.py` |
| `dashboard.py` | `test_api_dashboard.py`, `test_api_operational_states.py`, `test_readiness_snapshot_contract.py`, `test_signals_engine.py`, `test_dashboard_tsb_zones.py` |
| `decisions.py` | `test_coach_decisions.py`, `test_recovery_replan_loop.py`, `test_recovery_transfer_product_surface_web.py` |
| `hrv.py` | `test_api_operational_states.py`, `test_api_phase1.py` |
| `planning.py` | `test_api_planning.py`, `test_coach_constraints.py`, `test_planning_target_demand_history.py`, `test_api_planning_router_contract.py`, `test_api_planning_router_http_contract.py` |
| `recovery_analytics.py` | `test_api_recovery_analytics.py` |
| `session_feedback.py` | `test_post_workout_feedback.py`, `test_api_session_feedback_router_contract.py` |
| `session_quality.py` | `test_session_quality_forecast.py`, `test_api_session_quality_router_contract.py` |
| `settings.py` | `test_briefing_settings.py` |
| `sleep.py` | `test_api_operational_states.py`, `test_api_phase3.py`, `test_sleep_metric_provenance.py` |
| `system.py` | `test_api_operational_states.py`, `test_sync_job_api.py`, `test_api_phase3.py`, `test_session_quality_forecast.py` |
| `today.py` | `test_api_today.py`, `test_briefing_settings.py` |

Остаток #246 закрыт: 13 ранее непокрытых эндпоинтов `planning.py`
(`target-preview`, `demand` GET/POST, `events`, `plan`, `export/ics`,
`export/workout/{index}`, `reconciliation`, `reconciliation/matches`,
`rebalance/preview`, `rebalance/confirm`, `adjust`, `history`) теперь
исполняются на уровне роутера в `test_api_planning_router_contract.py`
(direct-call: happy-path со схемой, degraded без 500, маппинг исключений
`ValueError → 422` / `StalePlanningCheckpointError → 409` / `IntervalsICUError →
503`, `Response`-контракт export-роутов).

Остаток #248 закрыт: HTTP-слой валидации FastAPI (path/query `Query`-констрейнты
+ round-trip через реальный `Depends`) для `planning.py` теперь пинается в
`test_api_planning_router_http_contract.py` (`TestClient`, `get_database`
переопределён на временную БД): по каждому констрейнту — нарушение границы → 422
и включительная граница → не-422 (404 на пустой БД либо 200 через sentinel для
`/events`, что заодно пинует реальный DI + сериализацию dict). `planning.py` —
ЕДИНСТВЕННЫЙ роутер с path/query `Query`-констрейнтами (`events.days` `ge/le`,
`export/workout.fmt` `pattern`, `export/workout.leg` `ge/le`); у остальных
роутеров валидируется только тело запроса через Pydantic `Field(...)`, а оно уже
пинается при конструировании модели в direct-call свите (#242/#246). Поэтому
HTTP-слой свёлся к одному роутеру, а не к свипу по `api/routers/*`.

## Открытые долги (по 🟡)

Канонический backlog находится в
[`docs/technical_debt_register.md`](../technical_debt_register.md). Связанные
открытые пункты:

- PERF-2 → [TD-007](../technical_debt_register.md#td-007--детерминированный-latency-гейт-коуча);
- SEC-1 → [TD-002](../technical_debt_register.md#td-002--secret-scan-в-ci).

## Реестр ADR

| ADR | Тема |
|-----|------|
| [ADR-0001](adr_0001_web_primary_ui.md) | Web-first направление + критерии EOL Streamlit |
| [ADR-0002](adr_0002_sqlite_primary_store.md) | SQLite как primary store |
| [ADR-0003](adr_0003_canonical_signals_snapshot.md) | Канонический readiness/signals snapshot |
| [ADR-0004](adr_0004_coach_mutations_via_proposals.md) | Мутации коуча только через approval-gated proposals |
| [ADR-0005](adr_0005_execplan_driven_development.md) | ExecPlan-driven development |
| [ADR-0006](adr_0006_append_only_planning_versions.md) | Append-only версии плана |
| [ADR-0007](adr_0007_mock_ai_demo_acceptance.md) | Mock AI для demo/acceptance |
| [ADR-0008](adr_0008_intervals_activity_ingestion.md) | Multi-provider ingest, provider links и provenance |
