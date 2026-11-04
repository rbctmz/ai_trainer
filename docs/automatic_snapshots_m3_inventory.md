# #623 M3 — границы записи и контракт

Domain/API Implementer реализует принятую M1 спецификацию; Class A,
ASR-REL-3 / ASR-DEP-2 / ASR-SEC-1. База: M2 #744, merge e98b138.
Новый scope/ADR/очередь не добавляются. Включение на личной БД — после M4.

## Границы

| Данные / boundary | Общая запись | Внешняя операция / consumers |
| --- | --- | --- |
| План / checkpoint / coach mutation | Database.save_planning_checkpoint, commit_coach_plan_mutation; planning_build_preview_store.apply_preview | planning_service confirm/apply/restore, planning и decisions routes; legacy planning/dashboard |
| Цикл / исход события | services.planning_cycle_commands.execute_cycle_command | planning_cycles close/outcome/scope routes / shared cycle command |
| Решение коуча | Database.save_coach_decision, save_recovery_decision, proposal/status writers | services.agent_log и coach proposal orchestration / API + Streamlit |
| Plan/actual | Database.save_plan_actual_match | planning_service.record_plan_actual_match, feedback resolution / API + Streamlit |
| Feedback/correction/tombstone | Database.save_session_feedback | api.session_feedback public commands / API + Streamlit |
| Readiness evidence | Database.save_readiness_snapshot | recovery_analytics capture + provider sync |
| Provider sync | sync_garmin_data / sync_intervals_data | API SyncJobManager после terminal audit; Streamlit sync_data после mark_real_dataset |
| Внешние/низкоценные SQL writers | Без DB._connect/commit hook | startup + UTC-day check; ручной backup |

DB public writer hooks покрывают direct shared/legacy callers; внешние scope
объединяют вложенные записи одного действия. Snapshot после закрытия transaction,
до возврата внешней команды. Не писать backup state в source DB. При частичном
исключении проверка делает snapshot уже committed данных и не подменяет exception.
Preview/read routes не являются backup boundaries. Preview store_pending не hook.
Reset и retention принадлежат M4, здесь их разрушительная семантика не меняется.

## API до кода

- `BackupStatus`: state disabled/unknown/ready/degraded; last_checked_at,
  last_snapshot_at, last_snapshot_id, reason_code (nullable). Только разрешённые
  коды M1, никаких paths/raw exceptions/SQL.
- GET `/api/backup/status`: чтение последнего статуса, без snapshot/source write.
- POST `/api/backup/check`: только пустой объект; повторяет backup, не business
  command. БД выбирается сервером, `demo=1` всегда disabled.
- Аддитивный `backup: BackupStatus` в operational_state и mutation responses;
  исторические payloads/receipts допускают отсутствие. Stored build receipt не
  переписывается: backup добавляется в текущий ответ после транзакции.
- Sync: backup failure добавляет warning code `backup_failed`, делает succeeded
  partial; исходные failed/partial и provider error сохраняются. Status после
  final audit. Обычные mutation saved/IDs не меняются.
- Web mirrors `BackupStatus`, `OperationalState`, backup на mutation interfaces;
  registry + extractor проверяют endpoints/envelope. API sync routes выполняют
  bounded check в worker context; lifespan — threadpool, не event loop.

## Lifecycle / retry

Settings: AUTO_BACKUP_ENABLED=false, BACKUP_DIR (absolute optional, default из
platform data directory независимо от explicit source). Только выбранная real
БД; demo/acceptance disabled. Один process-local runtime на source/root, OS lock
остаётся M2. Startup делает check, затем daemon раз в 60s проверяет UTC day и
failed/unknown. Failed retry не чаще 60s, включая важные операции. Lifecycle stop
закрывает только свой timer, не services. State читается с диска для другого runtime;
нечитаемый state не превращается в stale ready. Неизвестные reset pins сохраняются.

## UI handoff / brief

После backend/contracts Domain/API Implementer передаёт UI/Design Specialist:
BackupStatus + endpoints выше. Глобальное существующее warning оформление,
время последней проверенной копии, честные disabled/unknown; retry с текстом
«Повторить проверку резервной копии», pending/ошибка без повтора бизнес-команды.
Streamlit fallback использует общий status/check, без второго движка. Сценарии:
disabled, unknown, ready, degraded с/без прежней копии, retry pending/failure/recovery,
demo. Нет нового экрана/настроек включения/путей на клиенте.

## Class A review record (slice_spec_review_template)

Issue #623; M2 #744 merged e98b138. Author: Domain/API Implementer → explicit
API/TypeScript handoff above → UI/Design Specialist → Supervisor/Integrator.
Checker: independent native review by separate owner request, NOT RUN. Merge
owner: Greg. Date: 2026-11-04. Candidate SHA and final CI are recorded in draft
PR/evidence checkpoint. Manual review mode, budget 0/2; acceptance/exception N/A.
No automatic reviewer trigger or live feature activation.

Scope: shared hooks/lifecycle, additive status/contracts, global warning/retry.
Non-goals: M4 retention, reset pins/restore drill, #626 off-device/encryption,
provider/scientific changes, other checkouts. Public API/config/events changed
compatibly; source DB schema and stopped CLI unchanged. Existing status.json
and immutable snapshot ownership/age-out remain M2/M4; no new source table,
queue or generation counter. Full reset preserves backup history per M1;
pre-reset pin/retention acceptance is M4 and not claimed here. Keep live backup
disabled until that acceptance. Rollback disables hooks and leaves snapshots;
existing stopped restore remains available, no reverse schema migration.

| Identity / evidence | Time | Observable result / falsifier |
| --- | --- | --- |
| selected real store, committed writer | before response | snapshot contains final IDs/rows; failure cannot undo commit |
| same file, separate handles / nested writes | one operation | one final snapshot, no per-row copies |
| concurrent operations | bounded M2 lock | both callers check, unchanged generation deduplicates |
| preview / read-owned recovery audit | any | no event snapshot; derived rows covered by daily check |
| prior copy + lost/corrupt status | later read | no cached ready; unknown/degraded until check |
| failed attempt | <60s / ≥60s | no immediate retry / one eligible retry |
| external write / process gap | new UTC day / startup | new snapshot without a lost memory flag |
| demo marker / demo path / acceptance / other DB | any | disabled, zero attempts/artifacts |
| UI warning / request failure | pending / retry / recovery | only backup/check POST, no business replay or raw paths/codes |

Observed RED: initial runtime test collection failed (module absent, 0 DB opens).
Observed second RED: enabled Today projection created a snapshot from its derived
audit and returned ready. Verified by test_today_projection_can_persist_derivations_without_event_backup.
Fix: explicit defer_derived_backup boundary on run_recovery_replan_loop; actual
user/coach decisions remain protected by the ordinary shared writer. These
read-owned rows stay covered by the daily safety check. No generic GET middleware.

Initial UI fixture run: 4 states passed; 2 retry tests failed only because the
request included the harness's expected demo=1 query. Normalize path for the
no-business-replay assertion; 6 scenarios then GREEN. Plan confirmation fixture
initially failed entry policy with both backup enabled and disabled; current-day
assignment was ambiguous. Reused the established rested=True protocol fixture;
no product or entry-policy change. These are fixture corrections, not product
bug/RED→GREEN claims.

ASR-REL-3/DEP-2: post-commit verified copy and honest degraded. ASR-SEC-1:
server-only paths, no raw error/row values, demo/scratch disjointness. ADR-0001,
0002,0007 reused. M2 OS lock/deadline reused; no extra runtime lock/queue.
Ready means last successful check, not an assertion that no later writes exist.
Native Windows/ACL, personal runtime, actual service restart, retention/reset and
full auto-restore lifecycle NOT RUN in M3. M2/related lifecycle tests are regression
coverage, not a claim of M4 acceptance.

Self-review fixes: corrupt/missing disk status cannot be hidden by an in-memory
ready; ready receipt requires snapshot identity/time. Unknown dataset provenance
is degraded without authorizing a copy. Concurrent operations reuse M2's lock
rather than silently skipping a second command. SSE done reports backup and
refreshes the global status; client retry catches its own refresh failure.

Additional acceptance/self-review before final freeze:

- Two RED cases confirmed stale nested sync backup/sync_state and lost last-copy
  metadata on an early core refusal. The shared projection now updates its
  operational envelope, deduplicates backup_failed notice/code, and preserves
  previously verified copy identity/time on failure. Provider error stays intact.
- Disabled status/check initially initialized a missing synthetic source through
  get_database. A RED absence assertion reproduced it; disabled/demo/acceptance
  now resolve no Database handle, avoiding a new source open/migration on a poll.
- Fresh Python child (owned receipt, credential-free env, dotenv disabled) starts
  FastAPI lifespan, catches a committed external-write gap, verifies the copy via
  HTTP + SQLite, stops only its own timer and leaves the prior copy unchanged.
  This is not an actual user-service restart. Shared legacy checkpoint and cycle
  close are separately verified in the final auto-snapshot contents.
- Full initial contributor-safe pass exposed 10 frozen sync envelopes missing
  the new backup/warning_codes fields and one historical HTTP receipt assertion.
  Added only those fields to synthetic fixtures, asserting every previous value
  unchanged; the legacy test still verifies the exact historical business receipt
  and unchanged database, separately asserting transient disabled backup health.
- A local sandbox-only E2E attempt failed before application startup at localhost
  socket.bind; the owned-stack allowed run passed all 98 cases. Historical images
  regenerated by that suite were restored to HEAD in this isolated worktree;
  only the new issue-623-m3 status images belong to this change.

Final boundary delta:

- RED: confirming an unknown preview token created an event backup without a
  business commit. apply_preview/cycle command now mark only a successful
  commit; their declared boundary flushes after connection close. Rejected and
  read-only replay paths do not mark a save. Sync keeps its conservative partial-
  commit boundary because providers may have already written batches on failure.
- RED: a first caller paused after publishing, a second verified a newer source,
  then the delayed first return replaced the visible receipt with the old copy.
  Preserve core last_checked_at rather than restamping parent response time;
  the reader now selects the later verified disk receipt. Deterministic two-
  caller test uses real synthetic snapshots, not fabricated snapshot IDs.

- RED: provenance used the product writer connection/30s busy timeout. A real
  exclusive lock exceeded the bounded read check, and forbidding writer PRAGMAs
  broke status. The shared read-only primitive now refuses busy immediately;
  no copy is authorized while provenance is unknown. The runtime retains the
  warning/last known copy until an eligible successful check. Final focused
  contour: 214 PASS; final candidate full/CI is the PR evidence checkpoint.
