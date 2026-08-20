# ASR Catalog — единая точка истины по quality attributes

Статусы на 2026-08-03. Источник сценариев: `architecture_analysis_add3.md` §2.
Правило ведения: новый архитектурный трек (ExecPlan) обязан назвать задетые
ASR в секции «ASR / risk traceability» и обновить здесь статус/проверку.
Подтверждённые открытые улучшения ведутся по стабильным ID в
[`../technical_debt_register.md`](../technical_debt_register.md).

| ID | Сценарий | Приоритет | Как обеспечивается | Как проверяется | Статус |
|----|----------|-----------|--------------------|-----------------|--------|
| ASR-PERF-1 | «Сегодня» < 2 сек с 3 годами данных | High | локальный SQLite, canonical snapshot без provider-вызовов на рендере (`include_provider=False`, #228) | `test_today_snapshot_perf_gate.py` — p95 < 2с на 3 годах синтетических данных (#241) | ✅ |
| ASR-PERF-2 | Коуч: первый токен < 5 сек | High | стриминг SSE; native function calling (#190) убрал маркерный второй проход у поддерживающих провайдеров | `first_token_ms` в SSE `done` (#241) + детерминированный гейт на локальном mock-runtime (TD-007, #352, `COACH_FIRST_TOKEN_BUDGET_MS`); live-провайдер остаётся наблюдением | 🟡→✅ (локальный overhead гейтится; live-недетерминизм остаётся метрикой) |
| ASR-PERF-3 | Инкрементальный provider-sync, дельта дня < 10 сек | Medium | Garmin incremental window; Intervals per-provider/per-domain cursors | smoke sync/cursor-сьюты | ✅ |
| ASR-PERF-4 | Planning preview 16 недель < 10 сек | Medium | детерминированный scheduler без БД внутри цикла (#205); week-by-week reader делает один provider-free reconciliation read на bounded 16-недельном окне (#303) | референс-сборки в smoke; `test_planning_week_by_week.py` пинует cap, isolated browser acceptance — отсутствие disclosure N+1 | ✅ |
| ASR-REL-1 | Reconciliation: ни одна активность или исполнимая тренировка не теряется при перепланировании | High | content-derived session identity + lineage (`replaces_session_id`, #206/#209), append-only match/feedback/delivery ledgers; recovery/near-term мутации повторно материализуют точный catalog prescription; user unmatch retire-ит активный feedback всей superseded match-линии; reader сохраняет leaf/composite IDs и покрывает факт всех 16 отображаемых недель без расширения provider-I/O (#303); multisport read-проекция сохраняет envelope и все provider-linked этапы без двойного агрегата (#433); modern broken sessions fail closed | `test_recovery_transfer_identity_handoff.py`, twin-матрица identity, `test_recovery_replan_materialization_p1.py`, `test_planning_week_by_week.py`, `test_reconciliation_service_migration.py`, `test_api_planning.py`, `test_intervals_plan_delivery.py`, `test_api_activities_multisport.py` | ✅ |
| ASR-REL-2 | Отсутствие данных → data gap, не падение | High | gate-исходы silence/data_gap (#154), `has_plan=false` пробросы (#228/#301–#303); readiness salience учитывает persisted fatigue/recovery и legacy-safe fallback (#315); power-curve enrichment сохраняет кэш при provider failure; неполный multisport lineage оставляет envelope авторитетным и не теряет полученные этапы (#433); execution-role принимает только закрытый planner vocabulary | smoke-гейты loop/ribbon + `test_readiness_conflicts.py`, `test_planning_active_plan_overview.py`, `test_planning_phase_roadmap.py`, `test_planning_week_by_week.py`, `test_best_efforts.py`, `test_actual_role_contract.py`, `test_api_activities_multisport.py` | ✅ |
| ASR-REL-3 | Обрыв sync/maintenance не портит частичные данные | Medium | атомарный common-ingest; cursor-after-clean-batch; независимые activity/wellness cursors; SQLite restore через validated temp + atomic replace + pre-restore rollback; единая WAL/busy-timeout политика с race-гейтом (TD-003, #347) | M0/M1 ingest/cursor, M4 wellness rollback, `test_sqlite_backup_restore.py` fail-before-replace и `test_sqlite_concurrency_policy.py` writer+reader | ✅ |
| ASR-MOD-1 | Новый AI-провайдер без правки основного кода | High | `AIProvider` ABC + фабрика; capability-флаги (`supports_native_tools`, #190) делают расширения аддитивными | capability-матрица в `test_coach_native_tools.py` | ✅ |
| ASR-MOD-2 | Новый компонент дашборда без регрессии | Medium | canonical snapshot проекции (#152/#153); `/planning` читает server-owned overview/week DTO без расчёта доменных метрик в TypeScript (#301–#303); `/activities` получает server-owned multisport group DTO вместо lineage-логики в React (#433) | trust-alignment smoke + planning reader browser/API gates + `test_activities_multisport_ui_contract.py` | ✅ |
| ASR-MOD-3 | Смена схемы — обратная совместимость | Medium | аддитивные поля чекпойнтов, migrate-on-read (#206), append-only журналы; `intervals_plan_deliveries` добавлен через idempotent DDL и читается вместе с legacy proposal evidence; planning reader добавлен отдельными GET-контрактами без изменения checkpoint schema (#301–#303) | legacy-byte-equivalence + planning router/service contracts + `test_intervals_plan_delivery.py` | ✅ |
| ASR-SEC-1 | Ключи не в логах/UI/git | High | `.env` вне git, UI скрывает поля, env-fallback; contributor-safe Gitleaks блокирует event range и текущее дерево, runtime probe проверяет detector | `test_secret_scanning_ci.py`; live `Secret scan` в PR #296; revoked historical finding требует отдельной policy ([TD-008](../technical_debt_register.md#td-008--политика-для-отозванного-credential-в-git-history)) | 🟡 |
| ASR-SEC-2 | Basic Auth перед публичным доступом | High | Caddy + Basic Auth в self-hosted стеке | деплой-чеклист | ✅ |
| ASR-DEP-1 | `docker compose up` поднимает весь стек | High | compose + `/api/health` + healthcheck (уже реализованы) | самопроверка compose | ✅ |
| ASR-DEP-2 | Обновление без потери данных | High | SQLite в named volume; append-only чекпойнты; stopped-service Backup API snapshot, integrity check, atomic restore и pre-restore rollback (#293) | `test_sqlite_backup_restore.py`: clean-volume domain drill + rollback/failure gates | ✅ |

## Active Planning reader (ASR-REL-1/2, ASR-PERF-4, ASR-MOD-2/3; #301–#303)

`/planning` разделяет чтение и мутации: активный append-only checkpoint
открывается через reader-вкладки Overview, Weeks и Execution, а build/edit,
adjust и export остаются явными действиями. При отсутствии checkpoint UI
возвращается к onboarding первого плана.

- **ASR-REL-1**: week DTO переиспользует `plan_days` и канонический
  `reconciliation_at`, сохраняя parent index, `session_id`, composite/brick
  legs и export semantics. Локальный provider-disabled снимок покрывает все 16
  отображаемых недель; provider-backed reconciliation сохраняет cap 12 недель.
- **ASR-REL-2**: no-plan, malformed checkpoint, rest, unplanned и ambiguous
  evidence выражены отдельными состояниями; отсутствующий факт не превращается
  в синтетическое выполнение. Roadmap принимает только семидневный post-plan
  bridge, поэтому далёкая B/C-цель не растягивает текущий план.
- **ASR-PERF-4**: `GET /api/planning/week-by-week` bounded до 16 недель и делает
  один reconciliation read без provider I/O; раскрытие прошлых недель не
  запускает новые API-запросы.
- **ASR-MOD-2/3**: `GET /api/planning/overview` и
  `GET /api/planning/week-by-week` — аддитивные server-owned проекции над
  существующим checkpoint, без новой схемы хранения и без дублирования
  training/reconciliation math в браузере.

Проверка: `test_planning_active_plan_overview.py`,
`test_planning_phase_roadmap.py`, `test_planning_week_by_week.py`,
`test_api_planning_router_contract.py`, `test_plan_actual_reconciliation.py`,
`test_reconciliation_service_migration.py`; Next lint/build и изолированная
browser-приёмка 1280/390 px без overflow, console errors и disclosure N+1.

## TD-002: contributor-safe secret scanning (ASR-SEC-1; #295, закрыт)

PR #296 добавил отдельный least-privilege workflow: immutable SHA для
`actions/checkout` и `gitleaks/gitleaks-action`, только `contents: read`, без
`pull_request_target`, application secrets и write-разрешений. Gitleaks
проверяет полный commit range события и текущее дерево; runtime-only synthetic
probe доказывает, что scanner действительно возвращает leak-detection exit code,
не сохраняя тестовый токен в git.

Одноразовый full-history audit обнаружил legacy password-shaped candidate без
доказательств false positive. Значение не выводилось и не добавлено в baseline;
credential ротирован, две текущие archived debug-копии удалены после отдельного
binary-attributes prerequisite PR #297. Атрибуты подавляют local diff, но
GitHub всё равно показывает удаление; оно опубликовано только после ротации.
Четыре current-tree исключения ограничены точными fingerprint и проверены как
пустой env assignment,
placeholder, документационный Basic Auth пример и error-kind assertion.
Preventive CI смержен в `557cfe9`; post-merge push в `main` прошёл в run
`30382483216`. TD-002 закрыт, а решение по уже отозванному значению в истории
перенесено в TD-008. Поэтому ASR-SEC-1 остаётся 🟡.

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

### Data coverage inventory: local aggregate diagnostic (#427)

`GET /api/sync/coverage?days=30|90` и постоянная карточка Dashboard показывают
покрытие канонического локального набора без чтения provider API на рендере.

- **ASR-PERF-1**: запрос ограничен выбранным 30/90-дневным окном и читает только
  SQLite presence/provenance; на локальной 90-дневной истории контрольный замер
  выполняется за единицы миллисекунд.
- **ASR-SEC-1**: контракт содержит только counts, календарные даты и source labels;
  значения health-метрик, имена/ID активностей, provider payload и credentials не
  сериализуются.
- **ASR-MOD-2**: активности имеют event-grain (`canonical_count`, пересекающиеся
  `provider_link_counts`), а ежедневные сигналы — day-grain (`observed_days`,
  `missing_days`, `coverage_pct`). UI не смешивает отсутствие тренировки с
  пропуском ежедневной метрики.
- **ASR-REL-2**: день считается покрытым только при non-null каноническом значении;
  `steps=0` остаётся валидным наблюдением. Источник берётся из metric-scoped
  provenance полей, поэтому карточка описывает сохранённый канон, а не сырой
  ответ провайдера.

Проверка: `test_data_coverage.py`, `test_data_coverage_ui_contract.py`, Next
lint/build и contributor-safe smoke suite.

### Multisport activity grouping: event-grain list and stage disclosure (#433)

`models/activity_lineage.py` является общей read-only границей для Garmin
multisport envelope и явно связанных Intervals.icu этапов. `GET /api/activities`
выдаёт одно событие верхнего уровня, сохраняет этапы в аддитивном `segments`, а
web раскрывает их без provider-вызова. Сырые canonical/provider-link строки не
переписываются.

- **ASR-REL-1**: ни envelope, ни linked stages не теряются; полная положительная
  тройка swim/bike/run использует сумму этапов TSS один раз, в том числе transitions.
- **ASR-REL-2**: partial lineage не подменяет load неполной суммой — envelope
  остаётся авторитетным, а полученные этапы всё равно видимы. Unlinked same-day
  тренировка не группируется по эвристике даты или спорта.
- **ASR-MOD-2**: completeness и lineage определяет Python-проекция, а React
  потребляет типизированные `group_kind`, `group_label`, `segments`; CTL/ATL и
  list totals используют одну shared-дефиницию provider lineage.

Проверка: `test_api_activities_multisport.py`,
`test_multisport_training_load.py`, `test_activities_multisport_ui_contract.py`,
Next lint/build и browser acceptance 1280/390 px.

### Garmin activity structure without Intervals.icu (ASR-PERF-3, ASR-REL-2, ASR-MOD-3)

Garmin-синхронизация сохраняет компактные круги `lapDTOs` в общем локальном
кэше структуры активности. Карточка `/activities` читает их без provider-вызова,
поэтому Intervals.icu больше не обязателен для базовой структуры факта.
Круги Garmin и определённые интервалы Intervals.icu хранятся раздельно и
показываются вместе: ни один источник не скрывает структуру другого.

- **ASR-PERF-3**: используется ограниченная точка API кругов, а не секундные
  потоки; отдельно сохранённые круги исключают повторные запросы.
- **ASR-REL-2**: ошибка или пустой ответ не отменяет сохранение основной
  активности и не удаляет предыдущую структуру.
- **ASR-MOD-3**: общий JSON-контракт расширен полями `source`,
  `intensity_type` и `garmin_laps` без миграции таблицы и с поддержкой старого
  кэша.

Проверка: `test_garmin_activity_intervals.py`, `test_activity_intervals.py`,
Garmin/common-ingest/plan-vs-fact regression suites, полный smoke-набор,
Next lint/build и браузерная приёмка реальной Garmin-only активности с 7 кругами.

### Сопоставление этапов плана с кругами устройства (ASR-REL-1/2, ASR-MOD-3)

Карточка активности сопоставляет непрерывную временную шкалу факта со всеми
этапами плана. Несколько соседних кругов Garmin или участков Intervals.icu могут
составлять один плановый этап: границы выбираются по порядку и минимальному
суммарному отклонению длительности. Если источник вернул только отдельные
усилия без непрерывных временных смещений, сохраняется осторожное
сопоставление рабочих этапов один-к-одному.

- **ASR-REL-1**: автоматические круги внутри длинного этапа не превращают
  выполненную работу в «нет факта».
- **ASR-REL-2**: разреженные или неполные данные не растягиваются искусственно
  на разминку и заминку; интерфейс показывает ограниченный режим сравнения.
- **ASR-MOD-3**: контракт расширен полями `alignment_mode`, `step_matches` и
  сводкой по всем этапам, при этом прежние `matches` и `summary.matched`
  сохранены для существующих потребителей.

Интенсивность сравнивается в метрике планового этапа: скорость относительно
порогового темпа для бега/плавания, мощность относительно FTP для велосипеда
или пульс относительно LTHR для пульсового назначения. Полосы плана и факта
используют эту единую шкалу высоты; цвет факта показывает попадание в целевой
диапазон, а исходные круги внутри сгруппированного этапа остаются видны как
тонкие разделители. При отсутствии нужного порога оценка интенсивности явно
недоступна и не подменяется номером зоны провайдера.

Проверка: `test_plan_vs_fact.py`, включая живой сценарий 5:15 / 19:15 /
5:15 / 5:15 против шести непрерывных участков, Next lint/build и браузерная
приёмка активности `23958642824`.

### Running threshold pace: единицы, provenance и safe fallback (#308)

Профиль Intervals.icu теперь отделяет provider-unit от planning-unit:
`sportSettings[Run].threshold_pace` принимается как м/с, строго валидируется и
хранится в явном каноническом поле
`threshold_pace_seconds_per_km`. Планировщик преобразует это поле в существующий
catalog-input `threshold_pace` только в момент явной сборки нового плана.

- **ASR-MOD-3**: три nullable поля athlete-profile добавляются migrate-on-start
  без переписывания legacy-снимков; тест поднимает реальную старую схему и
  проверяет повторную инициализацию.
- **ASR-REL-1**: profile-sync не вызывает build/repair/delivery и не меняет
  append-only planning checkpoint. Частичный ответ сохраняет последнее валидное
  значение вместе с его исходными `source`/`synced_at`, не выдавая carry-forward
  за свежую provider-наблюдаемость.
- **ASR-REL-2**: строгая цепочка остаётся
  `threshold pace → LTHR → relative RPE`; malformed, ambiguous или
  неправдоподобный темп не ломает построение плана и не затирает валидный.

Проверка: `test_athlete_profile.py` (mapping, bounds, migration,
carry-forward/no-checkpoint-mutation), `test_api_planning.py` (вертикальная
матрица pace/LTHR/RPE), `test_intervals_plan_delivery.py` (`/km Pace` round-trip) и
`test_running_threshold_pace_ui.py` (проверяемое основание цели до отправки).

### Swim TSS по темпу (sTSS) и CSS-порог (#362)

Плавание оценивается TrainingPeaks-style sTSS: `hours × IF³ × 100`, где
`IF = CSS-темп / средний темп` (обе в секундах на 100 м). Порог (CSS) приходит
из `sportSettings[Swim].threshold_pace` Intervals.icu (скорость в м/с) и
хранится в явном каноническом поле `swim_threshold_pace_seconds_per_100m` с
provenance `_source`/`_synced_at`. Каскад swim: `pace_tss_swim` →
`hr_zone_tss_swim` → `hr_tss_swim` → `heuristic_duration_swim`.

- **ASR-MOD-3**: три nullable swim-поля athlete-profile добавляются
  migrate-on-start без переписывания legacy-снимков; реальная старая схема
  поднимается в тесте повторной инициализации.
- **ASR-REL-1**: отсутствие/невалидность CSS не ломает расчёт — каскад честно
  остаётся на HR-ветках; частичный ответ профиля сохраняет последний валидный
  CSS с исходными `source`/`synced_at`.
- **ASR-REL-2**: средний темп считается локально из moving-duration и дистанции
  (оффлайн, детерминированно); физически невозможный темп (< 30 с/100м)
  отбрасывается, а не превращается в бессмысленную нагрузку. Статичного
  `.env`-дефолта для CSS нет — выдуманный порог искажал бы TSS тихо.

Проверка: `test_swim_pace_tss.py` (каскад и формула IF³),
`test_athlete_profile.py` (swim mapping/bounds/migration/carry-forward),
`test_api_athlete_profile_contract.py` (поля API) и
`test_swim_threshold_pace_ui.py` (карточка профиля).

### Intervals pace delivery fidelity (#322)

Native workout parser Intervals.icu требует явный маркер `Pace` после
абсолютного диапазона. Delivery сериализует беговой шаг как
`5:30-5:50/km Pace`, а после bulk-upsert повторно читает то же bounded окно и
сверяет каждый обязательный диапазон с `workout_doc.steps[].pace`
(`start`/`end`/`units`). Наличие одних только steps больше не доказывает
исполнение плановой цели.

- **ASR-REL-1**: потерянный или искажённый pace-target даёт retryable `partial`,
  не считается executable и блокирует stale cleanup; локальный checkpoint
  остаётся авторитетным.
- **ASR-MOD-3**: результат доставки расширен аддитивным
  `target_mismatch_count`; power/HR/RPE и legacy fallback сохраняют прежнюю
  семантику.
- **Boundedness**: дополнительный provider GET выполняется только когда в
  выбранном payload есть pace-target, в том же диапазоне дат.

Проверка: `test_intervals_plan_delivery.py` (обычный Run, mismatch,
эквивалентный read-back, Recovery Transfer, power-регрессия),
`test_workout_catalog_v2.py` (provider syntax) и reversible catalog live
acceptance с Run/pace probe.

### Fatigue-aware readiness salience (#315)

Readiness-gate сохраняет публичную роль сессии, но больше не принимает
structured `easy` за обычную лёгкую нагрузку, если materialized prescription
имеет любой fatigue-компонент ≥3 или требует ≥30 часов восстановления.
Day-level проекция берёт component-wise maximum и максимальное recovery по всем
`sessions[]`, поэтому вторая тренировка дня не скрывается за primary session.

- **ASR-REL-2**: legacy/malformed metadata сохраняет прежний role-only fallback
  без false positive; валидная structured цена формирует explainable conflict.
- **ASR-MOD-3**: форма checkpoint не меняется, читаются уже существующие
  аддитивные поля workout catalog; публичная role не переписывается.
- **Boundedness**: базовый горизонт остаётся 3 дня, cap — 7 дней; расширение
  идёт только до ближайшей quality или structured high-load easy session.

Проверка: `test_readiness_conflicts.py` (multi-session aggregation,
fatigue/recovery thresholds, legacy silence, bounded lookahead/API contract) и
Recovery Replan regression suites.

## SQLite backup/restore (ADR-0002; ASR-DEP-2, ASR-REL-3; #293)

TD-001 закрыт stopped-service CLI
`scripts/sqlite_backup_restore.py`. Snapshot создаётся стандартным SQLite
Backup API во временном файле рядом с назначением, проходит
`PRAGMA integrity_check`, `fsync` и публикуется atomic no-clobber hard-link.
Restore существующего target сначала создаёт отдельный validated rollback;
stale `-wal`/`-shm`/`-journal` карантинируются до `os.replace`, возвращаются
при ошибке публикации и удаляются после успешной замены.

- **ASR-DEP-2**: `test_sqlite_backup_restore.py` восстанавливает snapshot в
  отсутствующий файл чистого временного каталога и читает каноническую
  активность, provider-link, planning checkpoint, HRV, сон и resting HR.
- **ASR-REL-3**: invalid backup и injected final-replace failure не меняют
  target; sidecars восстанавливаются, существующий target имеет проверенный
  rollback до мутации, конкурентный artifact не перезаписывается.
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
| `planning.py` | `test_api_planning.py`, `test_coach_constraints.py`, `test_planning_target_demand_history.py`, `test_planning_active_plan_overview.py`, `test_planning_phase_roadmap.py`, `test_planning_week_by_week.py`, `test_api_planning_router_contract.py`, `test_api_planning_router_http_contract.py` |
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
`export/workout.fmt` `pattern`, `export/workout.leg` `ge/le`,
`export/workout.session_id` `min_length`); у остальных
роутеров валидируется только тело запроса через Pydantic `Field(...)`, а оно уже
пинается при конструировании модели в direct-call свите (#242/#246). Поэтому
HTTP-слой свёлся к одному роутеру, а не к свипу по `api/routers/*`.

## Версионированная научная проверка плана (ADR-0009)

Конечные исполнимые сессии активного плана проверяются чистой локальной
политикой после materialization. Blocks служит источником курирования, но не
вызывается в пути построения или чтения плана. Новые checkpoints сохраняют
результат и `policy_version`; старые checkpoints получают явно помеченную
проверку текущей политикой без записи новой версии плана.

- **ASR-PERF-4**: проверка ограничена сохранённым горизонтом и не выполняет
  сетевых вызовов.
- **ASR-REL-2**: отсутствие подтверждённой A-цели или нужного горизонта даёт
  `data_gap`, а не ложное прохождение.
- **ASR-MOD-3**: `science_audit` добавляется к JSON checkpoint и overview
  аддитивно; SQLite migration не требуется.
- **ADR-0004/0006**: v1 только объясняет план. Будущая автопоправка обязана
  стать отдельным preview и новой подтверждённой append-only версией.

Проверка: `test_plan_science_audit.py` (шесть правил, пробелы данных,
иммутабельность) и `test_planning_active_plan_overview.py` (сохранённый снимок,
legacy fallback без записи, web-контракт).

## Открытые долги (по 🟡)

Канонический backlog находится в
[`docs/technical_debt_register.md`](../technical_debt_register.md). Связанные
открытые пункты:

- PERF-2 → [TD-007](../technical_debt_register.md#td-007--детерминированный-latency-гейт-коуча);
- SEC-1 → [TD-008](../technical_debt_register.md#td-008--политика-для-отозванного-credential-в-git-history).

## Граница автономии коуча (ADR-0010; ASR-REL-1/3, ASR-MOD-2/3; #466)

Действия коуча классифицируются по Reversibility, Blast radius и Agency creep;
самая рискованная ось задаёт gate. Обратимая локальная non-executable
заметка/node может быть автономной, но mutation исполнимого плана требует
bounded proposal и DDA-confirm. «Согласен», «ок» и другие vague-assent фразы не
считаются авторизацией; LLM tool call также не заменяет действие пользователя.

#483 закрыл найденный аудитом обход: `create_plan_constraint`,
`retract_plan_constraint` и `repair_plan_day` теперь только строят bounded
proposal. Approval повторно проверяет base/fingerprint и под одним
`BEGIN IMMEDIATE` меняет constraint ledger вместе с child checkpoint; stale,
missing donor, validation/insert failure и replay не оставляют partial state.
Native и marker tool-calling используют один и тот же gate. Внешняя доставка
плана остаётся отдельным A4-действием. Архитектурный статус границы 🟢.

Проверка: `test_coach_autonomy_boundary_docs.py`,
`test_coach_constraint_mutation_gate.py` и
`test_coach_constraint_mutation_product_surface_web.py`.

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
| [ADR-0009](adr_0009_versioned_scientific_plan_policy.md) | Версионированная научная проверка плана без runtime-зависимости от Blocks |
| [ADR-0010](adr_0010_coach_autonomy_boundary.md) | Три оси автономии коуча и DDA для мутаций |
