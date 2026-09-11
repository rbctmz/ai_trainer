# Slice Spec And Review Template — issue #565 (training readiness write guard)

Рабочая спецификация по `docs/templates/slice_spec_review_template.md`; связана с
живым ExecPlan `docs/readiness_input_freshness_execplan.md` (раздел
`Follow-up #565`) и не дублирует его формат `.agent/PLANS.md`.

- Issue / PR: [#565](https://github.com/rbctmz/ai_trainer/issues/565) (PR: TBD)
- Author / checker / merge owner: agent (Domain / API Implementer) / независимый checker на PR (`@codex review`) / rbctmz
- Date: 2026-09-11
- Candidate head SHA: TBD

## Change Class

- Class: **A**
- Rationale: изменение меняет семантику persistent-записи `training_status.training_readiness` и правило владения провенансой (какое наблюдение владеет значением строки), а через `freshness`/`intervention_score` влияет на downstream Recovery Replan. Два автоматических триггера Class A срабатывают, поэтому уменьшается объём артефактов, но не класс.
- Automatic escalation triggers checked:
  - identity/provenance, cursor ownership, dedup rules — **да**: правило приоритета между двумя наблюдениями одной метрики внутри строки;
  - data migration или изменение schema/persistence semantics — **да** (persistence semantics: более старая датированная запись отклоняется). Схема и миграции не меняются;
  - live-provider write / платный вызов — нет: новых provider-вызовов нет, writer вызывается существующим sync-путём;
  - security boundary/permissions/secrets — нет;
  - irreversible action или rollback без дешёвой проверки — нет: откат = revert коммита, данные не мигрируются, повторный sync с корректной датой восстанавливает метрику;
  - новый cross-module public contract или архитектурная граница — нет: аддитивный ключ в существующем dict-результате и текст warning.
- Review budget used: 0 / 2 rounds
- Review trigger mode: automatic (`@codex review` на PR)
- Review acceptance head SHA: TBD
- Review budget exception: N/A — бюджет не превышен

## Scope

- Behavior that changes: `Database.sync_training_status` перестаёт принимать датированную запись readiness, если её `training_readiness_observed_at` **старше** сохранённой даты измерения той же строки. Значение и дата readiness сохраняются; остальные поля композитной строки (training status, VO₂ max, load balance и т. д.) обновляются как прежде. Факт отклонения учитывается: аддитивный ключ `stale_readiness_rejected` в результате и warning в `GarminSyncResult.warnings`. Одинаковые и более новые даты измерения пишутся как раньше; строки без сохранённой даты и недатированные записи сохраняют семантику #557.
- Фактическое решение по гонке: инвариант «метрика не откатывается назад по дате измерения» обеспечивается **в самом write-заявлении**: для двух readiness-колонок `UPDATE` подставляет `CASE WHEN date(?) IS NOT NULL AND date(training_readiness_observed_at) IS NOT NULL AND date(training_readiness_observed_at) > date(?) THEN training_readiness ELSE ? END` (и симметрично для даты). Так решение принимает текущая строка, а не предварительное чтение, и окно TOCTOU между `SELECT` и `UPDATE` не существует. Python-решение из предварительного чтения используется только для счётчика и warning.
- Files/modules in scope:
  - `data/database.py` (`sync_training_status`: guard + счётчик);
  - `services/sync.py` (warning в `warnings` после записи);
  - `tests/smoke/test_hrv_training_readiness_provenance.py` (RED/GREEN провенансы);
  - `tests/smoke/test_garmin_sync_service.py` (warning синк-слоя);
  - `docs/issue_565_readiness_write_guard_slice_spec.md` (этот файл), `docs/readiness_input_freshness_execplan.md` (follow-up раздел), `docs/architecture/asr_catalog.md` (одно уточнение в ASR-REL-2).

## Non-goals

- Behavior deliberately unchanged:
  - ключевание композитной строки по дню синка (#563);
  - ретроактивная правка уже сохранённых строк (#565 non-goal);
  - семантика недатированной записи (#557: значение не изменилось → дата сохраняется; изменилось → дата очищается);
  - писатели и провенанса остальных метрик (сон, HRV, RHR): у них строки ключуются собственной датой наблюдения, запись «в прошлое» чужой день не затрагивает;
  - пороги, веса `FACTOR_WEIGHTS`, базлайны, матрица severity;
  - схема БД, миграции, `api/`, `web/`, `tests/contracts/ts_contract.json`;
  - формат существующих sync-warnings и `SyncCounts`-ключей `new`/`updated`.
- Deferred work and owner: валидация **неформатных** дат наблюдения (например `2026-9-1`) в этом writer'е — сознательно вне scope (см. Residual risks); follow-up [#564](https://github.com/rbctmz/ai_trainer/issues/564) (evidence цитирует описательный канал) остаётся за своим issue.

## Definition of Done

- [x] Acceptance criteria наблюдаемы (см. RED Matrix).
- [ ] Required tests/checks названы и пройдены: focused provenance/readiness-контур, широкий Python-контур, `ruff` (Evidence Bundle).
- [x] Merge and cleanup owner назначен: rbctmz (мерж — отдельное действие владельца; после мержа — удаление ветки/worktree).

## Public Contracts

- `Database.sync_training_status(status_data) -> dict` — **changed compatibly**: добавлен ключ `stale_readiness_rejected: int`; `new`/`updated` сохраняют смысл. Тесты: новые кейсы в `test_hrv_training_readiness_provenance.py`; контур `test_garmin_sync_service.py`.
- `services/sync.py` → `GarminSyncResult.warnings` — **changed compatibly**: при отклонении добавляется одна предупреждающая строка; существующие строки и их порядок для сценариев без отклонения не меняются (проверяется существующим `result.warnings == ["partial Garmin warning"]`).
- DB schema / migrations — **unchanged** (колонки `training_readiness`, `training_readiness_observed_at` уже существуют, #557).
- `api/`, `web/lib/types.ts`, `tests/contracts/ts_contract.json` — **unchanged**: проекция `/today` и типы не меняются, регенерация артефакта не требуется, web-сборка не запускается.
- Readiness snapshot / gate — **unchanged по контракту**: тот же фактор, те же колонки; меняется только то, какие значения в них попадают.

## Failure, Reset, Rollback, Idempotency

- Failure modes and safe result:
  - неформатная или нечитаемая дата (входящая либо сохранённая) → `date()` в SQLite даёт `NULL`, сравнение не срабатывает, применяется прежняя семантика #557 (fail-open к уже принятому поведению; см. Residual risks);
  - сохранённая дата есть, значения readiness нет → при более старой входящей дате сохраняется `NULL` (метрика не «оживает» от устаревшей записи);
  - строка отсутствует → обычный `INSERT`, guard неприменим.
- Retry/idempotency key: (день синка, дата измерения). Повторный sync с тем же более старым payload состояние не меняет и снова сообщает отклонение; повторный sync с более новой датой обновляет значение и дату.
- Rollback procedure and proof: revert коммита возвращает прежнее поведение без миграций; испорченная до фикса строка восстанавливается штатным sync с корректной (более новой) датой — тест `test_newer_observation_after_a_rejected_stale_payload_restores_the_metric`.
- [x] Does this add **new persistent state**? Нет: новых таблиц, колонок, курсоров и файлов нет.
- [x] Does **full reset** remove every row/artifact/cursor introduced here? N/A — новых артефактов нет.
- [x] Restart and partial-failure recovery are covered: writer остаётся однокоммитным, guard вычисляется до `UPDATE`/`INSERT`, частичной записи не создаёт.

## State Boundaries and Identity

- Source of truth and owner: строка `training_status` принадлежит **дню синка** (`sync_garmin_data` / demo-сид); метрика `training_readiness` принадлежит **провайдерскому наблюдению** и несёт собственную дату в `training_readiness_observed_at`.
- Stable identity/provenance keys: `training_status.date` (день синка) + `training_readiness_observed_at` (дата измерения метрики). Новое правило: дата измерения метрики **монотонна** в пределах строки.
- Cursor/checkpoint lifecycle: не затрагивается (sync-курсоры и provider-revision не меняются).
- Concurrency and stale-write behavior: решение принимает сама строка внутри однократного `UPDATE` (`CASE` по `date(training_readiness_observed_at)`), поэтому конкурентная более старая запись не перезапишет более новую; `commit` — один на весь payload, частичных состояний нет.

## Evidence Boundary Matrix

| Identity | Time/provenance | Evidence state | Fallback | Expected result / falsifier |
| --- | --- | --- | --- | --- |
| строка = день синка, хранимое наблюдение новее | incoming **before** stored | present/dated | reject | readiness сохраняет хранимые значение и дату; `stale_readiness_rejected += 1`; falsifier: значение стало входящим |
| та же строка | incoming **equal** stored | present/dated | allow | обновляется значение, дата та же; счётчик не растёт |
| та же строка | incoming **after** stored | present/dated | allow | обновляются значение и дата (легитимный апгрейд) |
| та же строка | incoming **unknown** (нет даты), значение изменилось | present/undated | fail closed | дата очищается (#557), значение пишется |
| та же строка | incoming **unknown** (нет даты), значение прежнее | present/undated | keep | дата сохраняется (#557) |
| хранимая дата отсутствует | incoming dated (любая) | partial | allow | значение и дата пишутся как раньше |
| хранимая дата нечитаема | incoming dated | malformed | allow (прежняя семантика) | запись как раньше; входящая дата сохраняется как пришла |
| хранимое значение `NULL`, дата новее входящей | incoming **before** | partial | reject | значение остаётся `NULL`, дата не откатывается |
| другой день синка | любая | present | n/a | строки независимы, guard не влияет |

## RED Matrix

| Acceptance criterion / invariant | RED test or probe | Expected failure | GREEN evidence |
| --- | --- | --- | --- |
| Более старая датированная запись не откатывает метрику | `test_stale_dated_readiness_does_not_roll_back_the_stored_measurement` | до фикса строка становится `30 / 2026-09-11` | значение `80` и дата `2026-09-12` сохранены |
| Значение и дата двигаются только вместе | `test_rejected_stale_readiness_keeps_value_and_date_atomic` | до фикса обе колонки меняются на устаревшие | ни одна из колонок не приняла входящее наблюдение |
| Отклонение не теряется молча | `test_repeated_stale_resync_reports_the_rejection` | до фикса ключа `stale_readiness_rejected` нет | счётчик равен числу отклонённых записей при повторном sync |
| Апгрейд даты после отклонения работает | `test_newer_observation_after_a_rejected_stale_payload_restores_the_metric` | до фикса промежуточный откат ломает состояние | после `80/09-12 → 30/09-11 → 85/09-13` строка = `85 / 2026-09-13` |
| Композитные поля строки продолжают обновляться | `test_rejected_stale_readiness_still_updates_the_composite_fields` | до фикса readiness тоже меняется (falsifier по значению) | `training_status`/`vo2_max` обновились, readiness сохранён |
| Равная и более новая дата пишутся (регрессия) | `test_equal_and_newer_dated_readiness_still_write` | уже зелёный (characterization) | оба случая пишут значение и дату |
| Dateless-семантика #557 сохранена | `test_dateless_resync_semantics_are_preserved_next_to_the_guard` | уже зелёный (characterization) | unchanged → дата сохраняется; changed → дата очищается |
| Синк-слой сообщает об отклонении | `test_sync_warns_when_stale_readiness_is_rejected` | до фикса warning отсутствует | в `result.warnings` есть строка про пропущенные записи |

## ASR / ADR Traceability

- ASRs affected из `docs/architecture/asr_catalog.md`: ASR-REL-2 (честное состояние вместо подмены свежих данных устаревшими; провенанса следует за значением — правило усиливается монотонностью даты измерения) и ASR-MOD-3 (схема и миграции не меняются, читаемость legacy-строк сохраняется).
- ADRs reused or required: ADR-0008 (multi-provider ingest / provenance) — переиспользуется; новый ADR не требуется, новая архитектурная граница не появляется.
- Tactic and trade-off: metric-scoped provenance ownership, отклонение устаревшей записи вместо «последняя запись побеждает». Плата — редкий сценарий, когда провайдер корректирует дату измерения в прошлое, не будет принят; это осознанный fail-closed выбор в пользу сохранения подтверждённого наблюдения.
- New architecture boundary discovered during review: нет на момент написания спеки; если checker назовёт такую границу, раунд ревью может быть продолжен по правилам бюджета.

## Delivery Slices

1. Slice: «датированная более старая запись readiness не откатывает метрику» (#565).
   - RED: новые тесты в `tests/smoke/test_hrv_training_readiness_provenance.py` (строки 1–5 RED Matrix) + warning-тест в `tests/smoke/test_garmin_sync_service.py`; ожидаемое падение — откат значения/даты и отсутствие счётчика.
   - GREEN: guard в `data/database.py::sync_training_status` (CASE внутри `UPDATE` + счётчик) и warning в `services/sync.py`.
   - Refactor/contract refresh: не требуется — контракты аддитивны, `ts_contract.json` и web не затронуты.
   - Verification: focused-контур провенансы/readiness + широкий Python-контур + `ruff`.

## Evidence Bundle

- Head SHA: TBD
- Changed invariants: дата измерения `training_readiness` монотонна в пределах строки дня синка; значение и дата двигаются атомарно.
- Focused and broad tests: TBD
- CI checks/reruns/flakes: TBD
- Lifecycle/probe evidence: TBD
- Changed contracts: аддитивный ключ результата + текст warning (см. Public Contracts).
- Unresolved review-thread count: TBD
- Residual risks and follow-ups: неформатные даты наблюдения (fail-open к семантике #557) — кандидат в отдельный issue, если checker подтвердит риск; #564 остаётся отдельным follow-up.

## Review Findings

| Severity | Evidence and falsifying check | Gate | Owner/status |
| --- | --- | --- | --- |
| — | Findings появятся после раунда независимого checker'а | — | — |

## Native Review Rounds

| Round | Reviewed head SHA | Trigger | Findings disposition | Stop / exception decision |
| ---: | --- | --- | --- | --- |
| 1 | TBD | automatic (`@codex review`) | TBD | continue / stop |
| 2 | — | verification | — | — |

## Final Verdict

- Verdict: READY (до раунда checker'а)
- Blocking findings remaining: нет на момент написания
- Review rounds used: 0 / 2
- Accepted risk or follow-up issue: неформатные даты — вне scope, зафиксировано в Residual risks
- Merge owner final gate: rbctmz
- Post-merge sync/branch/worktree/progress cleanup: удалить ветку и worktree после мержа; запись метрик Class A — по правилу `docs/engineering_process_metrics.md`
