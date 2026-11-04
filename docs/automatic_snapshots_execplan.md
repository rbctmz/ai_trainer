# #623 — минимальные автоматические локальные снимки

Этот ExecPlan поддерживается по [.agent/PLANS.md](../.agent/PLANS.md).
M1 принят владельцем и merged #743 как4230a9d; M2 #744 merged e98b138.
Текущий scope — M4: retention, защита full reset и synthetic restore drill.
M3 #746 ещё не merged: review165a97a дал один P2, воспроизведённый и
исправленный1386c2c. M4 stacked поверх1386c2c в отдельной managed worktree.
Ни M3, ни M4 не включают backup на личной БД. Merge owner — Greg.

## Purpose / Big Picture

После реализации важных сохранений в AI Trainer пользователь увидит либо
проверенную резервную копию, либо явное предупреждение о том, что данные
сохранены, но копия не обновилась. Предыдущая копия должна пережить ошибку
записи, сбой процесса и неудачную очистку истории. Обычный restore уже есть;
нужно автоматическое создание снимков с измеримыми границами защиты.

## Progress

- [x] (2026-10-28) Сверены #623, main после #742, существующий backup, sync и operational state.
- [x] (2026-10-28) Synthetic online/WAL characterization и логический fingerprint после VACUUM PASS.
- [x] (2026-10-28) Подготовлен проект контракта с политикой, failure/reset/retention и RED matrix.
- [x] (2026-10-28) M1: два review-раунда, два P2 исправлены, owner accepted и merged #743.
- [x] (2026-11-04) M2 #744 merged e98b138: bounded online snapshot, публикация, concurrency/faults; owner review-budget-exception after main integration.
- [x] (2026-11-04) M3 code: shared post-commit hooks, lifecycle check, status/API/web/Streamlit; synthetic focused acceptance complete.
- [x] (2026-11-04) M3 draft #746: native4348/CI4322/E2E98 GREEN на165a97a; independent round1 завершён, P2 fixed1386c2c (50 focused PASS).
- [ ] M3: fix-head CI, review delta/owner acceptance и отдельный merge.
- [x] (2026-11-04) M4 implementation: retention union, durable reset pins, writer exclusion, maintenance warning и реальный auto-snapshot restore.
- [ ] M4: итоговые full/CI checks, draft PR, independent review и owner merge.


## Surprises & Discoveries

Observed: `scripts/sqlite_backup_restore.py::backup_database` требует
confirm_stopped, внутри `_copy_sqlite` использует Backup API; логический
инспектор `inspect_relocation_database` уже считает schema/table digests.
Inferred: можно переиспользовать primitive и инспектор для online режима,
но не использовать stopped CLI с ложным подтверждением. Verified by:
исходник и `docs/reports/issue-623-m1/online_backup_probe.py`: source WAL,
перекрывающийся writer, integrity и invariant PASS; fingerprint до/после
VACUUM одинаков. Скорость на личной БД и гарантии bounded online worker этим
не доказаны. Fault injection/kill/retention для будущего сервиса NOT RUN.

Observed: sync job записывает audit decision до terminal result в
`api/sync_jobs.py::_run_job`; shared operational envelope находится в
`api/operational_state.py`. Inferred: backup hook должен идти после последней
записи операции, иначе audit/readiness останутся вне копии. Verified by:
чтение `_run_job`, `_record_provider_sync_decision`; integration runtime NOT RUN.

## Decision Log

Decision 2026-10-28: нулевое отложенное окно важных операций; объединять
только вложенные записи одного действия. Причина: не строить durable queue,
не терять pending jobs при crash; commit/copy gap всё равно явно признаётся.

Decision 2026-10-28: generation — digest готового snapshot через существующий
инспектор. Причина: mtime/main hash не отражают WAL/логическое содержимое;
не нужны новые source таблицы, triggers или универсальная change tracking.
Повтор может сделать временную копию, но не публикует новую без изменений.

Decision 2026-10-28: rollout opt-in, два configuration поля, один общий сервис,
один небольшой status-файл с reset pins и OS-lock. Причина: включение на личных данных
требует решения владельца, а параллельные runtimes не должны удалять копии
друг друга. Распределённый scheduler и event bus не нужны.

## Outcomes & Retrospective

M1 определяет будущие обещания; автоматизация ещё не поставлена. Существующий
manual backup работает только по stopped-service контракту. Product UI/API
не меняются этим PR. #623 и #622 остаются открытыми. Копия на том же устройстве
не заменяет #626; off-device RPO из epic этим срезом не достигается.

## Context and Orientation

`config/database_paths.py` выбирает platform application-data path и валидирует
real/demo families. `scripts/sqlite_backup_restore.py` содержит WAL-aware copy,
integrity, atomic publication, restore с rollback и fingerprints. `services/sync.py`
и `services/intervals_icu.py` выполняют provider sync; `api/sync_jobs.py` формирует
terminal status и audit decision. `api/planning_service.py`, `api/session_feedback.py`,
shared database/domain writers и coach/recovery boundaries сохраняют важные
локальные данные. Streamlit остаётся поддерживаемым fallback: hooks размещаются
в shared Python orchestration, не только в FastAPI router. Подробный контракт:
[спецификация](automatic_snapshots_slice_spec.md).

## Plan of Work

В M2 добавить `services/automatic_snapshots.py` с одной операцией
`check_snapshot(database_path, backup_root, reason) -> BackupStatus`; вынести
переиспользуемые filesystem/Backup API helpers из CLI в shared модуль, сохранив
CLI signatures/stopped guard. Проверять snapshot после закрытия его writers,
считать generation по его содержимому, публиковать DB+manifest каталогом.
Первый RED должен воспроизвести отказ без повреждения предыдущего snapshot.
Проверить concurrent writer, lock release и deadline, прежде чем разрешать online.

В M3 добавить ровно два Settings параметра и общий post-commit вызов по
перечисленным в spec операциям. Выписать inventory всех write entrypoints до
изменений; tests должны доказывать web/Streamlit coverage, nested aggregation,
неповторение business commit при retry backup. Lifecycle service проверяет
UTC day и retry раз в минуту. Добавить typed backup status в operational state,
mutation contracts и web mirrors; UI Specialist использует существующий warning
pattern по утверждённому API. Интерфейс объясняет сохранность данных и копии
отдельно, без raw path. Нет автоматического включения на личной БД.

В M4 реализовать retention по union daily/weekly + pinned latest под тем же
lock, включая 14-суточную защиту pre-reset snapshot через reset_pins в status.
Перед destructive reset проверить snapshot и durable pin; отказ блокирует
очистку. После потери status не делать pruning, пока operator не разрешит.
Не удалять manual/unknown/corrupt artifacts. Прогнать существующий restore
lifecycle drill на автоматически созданной копии, включая локальные evidence
и reset. Включение feature для пользователя допускается только после M4.

## Concrete Steps

В изолированной копии репозитория, с Python runtime/dev dependencies и пустым
credential-free environment, выполнить:

    python docs/reports/issue-623-m1/online_backup_probe.py
    python -m ruff check .
    git diff --check

Ожидать JSON online_consistency=PASS, overlapping_writer=true,
unchanged_logical_generation=PASS. Probe создаёт и очищает только собственный
TemporaryDirectory; не читать .env/личную БД. В M2–M4 добавить dedicated
`tests/smoke/test_automatic_snapshots.py`; targeted test command и RED/GREEN
снять на каждой фактической стадии, затем contributor-safe по AGENTS.
API/web изменения проверяются contract:extract, lint/build и relevant E2E.

## Validation and Acceptance

Наблюдаемые Given/When/Then и fault matrix находятся в spec. Приёмка требует
реального writer плюс auto snapshot и последующего restore, не только mocked
вызова hook. Две команды без изменений публикуют одну версию; ENOSPC/kill на
publish сохраняет предыдущую копию; process restart догоняет commit/copy gap;
backup warning видим после успешного commit. Native Windows/ACL проверяются
там отдельно либо честно остаются NOT RUN. Personal runtime не используется.

## Idempotence and Recovery

M1 probe безопасно повторяется в новом owned temp. Runtime retry — проверка
копии, никогда повторное бизнес-сохранение. Startup читает только подтверждённые
manifests, не доверяет прежнему ready-флагу, проверяет каталог заново. Reset
сохраняет backup history; operator restore требует остановки и rollback. При
откате feature выключается, файлы копий сохраняются. Ничего не удалять по glob.

## Artifacts and Notes

Characterization source: `docs/reports/issue-623-m1/online_backup_probe.py`.
Положительный synthetic результат показывает возможность, а не готовый backup
service. Новые таймеры, API и файлы состояния в M1 отсутствуют. ASR-REL-3,
ASR-DEP-2, ASR-SEC-1 и ADR-0001/0002/0007 задают границы изоляции и shared logic.

## Interfaces and Dependencies

Использовать sqlite3 Backup API, существующие integrity/fingerprint/publish
helpers и stdlib OS advisory lock. Из публичного добавляются Settings flags,
BackupStatus и API envelope (M3); исходная DB schema не меняется. Очереди,
брокеры, CDC и новые runtime dependencies не требуются. Если M2 не подтверждает
online consistency/deadline на доступном механизме, вернуть evidence и пересмотреть
spec; не обходить stopped confirmation и не подменять критерии зелёными mocks.


## M1 review round 1 — 2026-10-28

Два P2 на 0d68b54 подтверждены. Observed: union daily/weekly для pre-reset
10:00 и post-reset 11:00 оставил только post; schema cookie на synthetic SQLite
после VACUUM изменился 1 → 2 при одинаковых rows. Inferred: исходный текст мог
удалить защищаемую копию и ошибочно включить cookie в generation. Verified by:
короткий stdlib synthetic расчёт/SQLite probe, оба противоречия воспроизведены.

Исправление: generation точно равен digest результата существующего инспектора,
без schema cookie; reset pins в существующем status.json защищают актуальную
pre-reset копию 14 суток независимо от union. Snapshot/check и durable pin —
precondition до очистки, failure не делает reset. Повреждённый status блокирует
pruning, health может восстанавливаться отдельно. Новый сервис или очередь для
этого не добавляются. Матрица приёмки расширена на same-day reset и expiry.
Второй review допускается только по этой delta; runtime acceptance NOT RUN.


## M2 implementation checkpoint — 2026-10-29

Domain/API Implementer продолжает принятый контракт по поручению владельца.
Новых lifecycle hooks, Settings, API или UI нет: core вызывается только явно.
`services/sqlite_snapshot_core.py` переиспользует логический инспектор и SQLite
copy; adapter в ручном CLI сохраняет stopped confirmation и monkeypatch seams.
`services/automatic_snapshots.py` реализует private namespace, OS-lock,
проверенный snapshot/manifest, no-clobber публикацию и логическую дедупликацию.

Для bounded copy/SQLite integrity/Python sort используется один дочерний процесс
на попытку, не очередь. Parent прекращает worker по deadline и удаляет только
свой идентифицированный staging directory. OS освобождает lock при kill.
Полная публикация snapshot+manifest идёт atomic rename поверх исключительно
своей пустой reservation, созданной mkdir без exist_ok; reservation без manifest
не является restore candidate. Любой чужой существующий destination сохраняется.
Read-only source не получает новую schema. Status хранится отдельно, reset_pins
сохраняются, но управление pins, hooks и retention будут в M3/M4.

Observed: первые новые тесты на baseline не импортировали отсутствующий модуль
(ModuleNotFoundError), ноль SQLite opens. Inferred: нового core ещё нет.
Verified by: isolated pytest RED, затем GREEN нового контракта и старого CLI.
Первый corrupt-source тест был некорректен из-за открытого WAL connection:
после закрытия фикстуры проверка отказа стала однозначной. Это исправление
тестового setup, не product regression claim.

Observed: native macOS firmlink не всегда даёт одинаковые DirEntry.inode() и
stat().st_ino. Verified by: namespace probe первоначально отказал для обычного
synthetic path; после сопоставления stat device/inode native alias tests GREEN.
Casefold/NFC не используется как identity разных файлов на case-sensitive FS.
Native Windows lock/ACL NOT RUN, unsupported paths/platform fail closed.

Focused checkpoint: 135 passed (18 new M2 + 101 relocation + 16 backup/restore),
включая kill до/после publish, busy/timeout/lock release, параллельных callers,
конкурентный writer, no-clobber и неизвестный namespace. Дополнительный combined
контур до последнего namespace test: 208 passed. Synthetic 10,280,960-byte DB:
0.119s first snapshot, 0.120s unchanged check, одна опубликованная версия.
Это не benchmark личной БД. Product seed/restart/demo-clear probe: 18 и 8
bounded SQLite opens PASS. Full final/CI и independent review записываются
отдельно; hooks/retention ещё NOT IMPLEMENTED и feature не включена.

M2 self-review: namespace initialization refuses pre-existing unknown private
folders, including an empty folder with the predicted name. It waits briefly
for a concurrent creator's marker rather than adopting the folder. Checkout
markers include dangling symlinks. Timeout returns degraded and attempts to
persist that result under the OS lock after terminating the worker; if the state
is unwritable/contended, the current result still reports the failure. Existing
reset pins are retained. Final dedicated contour: 18 passed; full suite running
on f703862 before the timeout-status delta, final exact-head CI is separate.

M2 sidecar self-review: a saved synthetic de79c75 core accepted an existing
snapshot with a journal symlink (reason_code=None), contradicting the family
boundary. The added actual child check reproduced RED without touching user
files; final helper validates the entire snapshot family before inspection.
Dedicated final contour: 19 passed, including unchanged external sentinel.
The exact final remote CI supersedes the earlier local full snapshots; no UI
or lifecycle hook is added by this correction.

## M2 native review round 1 — 2026-10-29

Два P2 на 25f344f подтверждены двумя RED regression tests в изолированной
synthetic копии: malformed status постоянно возвращал degraded вместо recovery,
а SQLite DatabaseError давал degraded ответ при persisted ready. Никаких личных
БД/сервисов не использовалось. Это подтверждённые reliability contradictions
к принятому контракту, а не расширение scope.

Исправлено: manifest health проверяется независимо от status; malformed/missing
status и malformed pins восстанавливаются со sticky `reset_pins_unknown=true`.
Этот признак хранится отдельно от snapshot readiness и запрещает pruning до
явного operator repair в будущем M4. Валидные известные pins сохраняются; recovery
никогда не превращает неизвестные pins в известный пустой набор. Identity
refusals (symlink/hardlink) не заглатываются. Timeout persistence также сохраняет
признак неизвестности. SQLite backup errors теперь ловятся под namespace lock;
NOTADB/CORRUPT дают backup_integrity_failed, другие SQLite failures — safe
backup_io_error, previous snapshot metadata сохраняется вместе с degraded.

GREEN: 25 dedicated tests, включая два исходных RED, повторный recovery,
изменение source после recovery, invalid JSON/list/pins, missing state и отказ
на state symlink. Ruff GREEN. Полный contributor-safe и related contour
записываются отдельно. Review budget 1/2; автоматический повтор не запрошен.
Runtime hooks/retention по-прежнему M3/M4 и не включены.


## M3 implementation checkpoint — 2026-11-04

Перед кодом зафиксирован [inventory/contract и Class A review record](automatic_snapshots_m3_inventory.md).
Новый shared runtime использует explicit committed Database writers и внешние
operation boundaries: sync после audit, plan/cycle, coach decision, match,
feedback/correction/tombstone, readiness capture. Вложенные записи одного store
объединяются, даже при разных handles. Preview и read-owned recovery projection
не запускают event backup. Копии для внешних/производных записей делает UTC-day
safety check; restart не полагается на memory pending flag. Failed retry ≥60s;
M2 advisory lock/deadline остаётся единственным lock на snapshot operation.

Ровно два новых Settings поля; default off. API lifespan запускает/останавливает
свой timer вне event loop. GET status/POST check строгие и path-free; typed backup
в operational/mutation/SSE responses не переписывает durable business receipts.
Streamlit использует тот же runtime; современный fragment обновляет warning раз
в минуту, старые версии — при rerun. UI handoff выполнен по этим contracts:
BackupStatusBanner + global mutation/stream refresh, copy time, safe bounded retry.
Скриншоты synthetic элемента 390/light и 1280/dark визуально проверены:
`docs/design/evidence/issue-623-m3/`. Никакого изменения личной БД/настроек/сервисов.

На этом checkpoint: dedicated runtime/API 16 PASS до отдельного read-derived
регрессионного случая; recovery/coach focused с ним 191 PASS. Contract conformance,
extractor/inventory 99 PASS на предыдущем контрактном checkpoint; после SSE delta
extractor обновлён, финальный broad/contract прогон впереди. Шесть isolated UI
scenarios PASS до final keyboard/stream delta; финальный rerun впереди. Web lint и
build GREEN. Первичный UI query/plan fixture mismatch описан в inventory, не
выдан за product regression. Current-head full, remote CI и независимое review
ещё не подтверждены. M4 retention/reset/restore и live activation не заявляются.

## M3 final author handoff — 2026-11-04

The implementation now has 24 dedicated runtime/API acceptance cases, including
actual fresh-interpreter FastAPI startup/shutdown, committed-gap capture, shared
legacy checkpoint and cycle close, feedback correction/tombstone, partial sync,
read suppression, disabled no-source-open, rejected confirm and delayed concurrent
receipt ordering. Evidence uses only owned synthetic stores; no user service was
restarted. Full local pre-final-boundary run: 4345 passed /16 skipped /122
deselected, 7 existing warnings, 299.97s. The four-file commit-boundary/timestamp
delta is separately checked with the whole Planning commit/cycle and contract
contour; final candidate full/remote results are recorded in the draft PR.
Full isolated browser suite: 98 passed (237.85s); final backup keyboard/retry
contour: 6 passed (6.82s). Web lint/build, contract extraction freshness, Ruff and
54 local Markdown links GREEN. Existing capture fixture values are unchanged,
with only new additive health fields; old receipt database invariance still
passes. No historical evidence images were added to this slice.

Independent native review remains a separate manual handoff (0/2); no review
acceptance/merge permission for M3 has been given. M4/live activation remain out
of scope. This is author implementation/draft delivery, not a claim that #623 or
#622 is complete. M2 post-merge metrics are recorded in this substantive change.

Final provenance delta: a real exclusive-lock probe reproduced waiting in the
ordinary Database writer connection before the snapshot deadline. Provenance
now reuses the shared readonly connection with immediate busy refusal, never
writer PRAGMAs. Unknown provenance remains degraded in the runtime until a
successful eligible check; no unauthorized namespace write is attempted. Final
combined protocol/runtime/API/contract contour: 214 passed, 7 existing warnings,
40.48s. Final candidate is frozen for full native + remote CI; no live enablement.


## M3 independent review round 1 — 2026-11-04

Observed: native review 5766719588 on 165a97a raised P2 thread4466238963.
Inferred: delayed ready can erase a later error that could not persist to disk.
Verified by: test_delayed_ready_never_hides_newer_unpersisted_failure reproduced
ready instead of degraded using actual initial snapshot + ENOSPC on later temp
creation; no mocks of the failure result. A short receipt assignment lock now
orders local receipts by core timestamp, without serializing/skipping backup.
Dedicated regression also checks timer retry after61s captures the new commit.
Delta core/runtime/API:50 passed (17.02s), Ruff/diff GREEN; remote CI pending.
An existing sync wait(2) assertion failed twice before the hook was entered; its
standalone diagnostic and final combined rerun pass. Cause not established;
assertion now includes terminal/progress state for any recurrence; timeout was
not increased. Round2 not requested automatically. M4 remains separate.


## M4 checkpoint — 2026-11-04

Implementation consumes accepted spec; bounded scope/role handoff is in
[acceptance inventory](automatic_snapshots_m4_acceptance.md). One existing
namespace lock covers copy, durable pin, full catalog validation and retention.
Keep union14 nonempty UTC days/8 ISO weeks/latest/pins. Validated SQLite family
files are allowed; unknown/foreign/manual artifacts are not deleted. Uncertain
pins or corrupt catalog halts pruning. A maintenance reason on ready explicitly
means the checked copy exists and cleanup needs attention; no new status model.

Database.clear_all_data now begins IMMEDIATE before pre-reset check/pin. The
source stays write-locked through DELETE/commit; post-reset copy runs after close.
No web reset endpoint was invented. Existing Streamlit admin and demo/test reset
call the same domain method. Disabled/demo/acceptance backup isolation remains.

Observed: initial M4 acceptance9 failures (retention absent, pre_reset keyword
absent, reset cleared despite failed backup). Inferred: implementation should
apply accepted policy under existing lock and place precondition before DELETE.
Verified by: after code,9 cases pass; combined core/runtime/reset/CLI restore81
pass (28.51s), including full #624 domain fixture restored in a fresh application
process and exact logical fingerprints plus reset-state rollback. Four additional
cases and contract contour44 PASS (8.97s); final full-suite snapshot/CI pending.

Observed: first retention prototype reported maintenance failure on valid copy;
cheap synthetic probe found snapshot.db-wal/shm generated by read-only SQLite
inspection, with matching hash/fingerprint. Verified by: allow only known SQLite
family plus manifest, keep regular/single-link validation;45 dated generations
exercise daily/weekly union. Same-day pin test originally reused identical fake
timestamps; corrected clock order (no production ordering workaround).

Observed: eight isolated browser checks PASS (9.83s); screenshots show checked
copy and cleanup warning separately, retry only posts backup/check. UI uses
existing component/geometry/tokens, text-only maintenance state and the same
keyboard button. Web lint/build/contracts GREEN before final text-color delta;
final lint/build and8 UI cases PASS (8.65s); screenshots refreshed/visually checked. No new dependency, source schema, second engine
or live activation. Native Windows/ACL NOT RUN. M3 review fix/merge and M4 review/
merge are separate; no approval or accepted labels implied by this checkpoint.

M4 final self-review: missing status with only corrupt history must still mark
reset pins unknown; checking only latest valid candidate would forget history.
History detection now counts any snapshot-ID entry; pruning remains prohibited.
Regression added (source/published copies remain unchanged except new valid
snapshot); final focused check pending. Retention scans/verifies the full owned
catalog within the existing10s worker deadline; real-data scale NOT MEASURED.

M4 validation checkpoint: native full4362 passed /16 skipped /124 deselected,
7 existing warnings (329.98s), before four extra additive tests and final
corrupt-only history hardening. Final combined114 passed (32.57s) includes all
17 retention/reset cases plus runtime/core/API/CLI restore/contracts. Final8 UI
cases, lint/build/Ruff/diff GREEN. Final exact-head full/CI still pending.


## M4 review round 1 — 2026-11-04

M3 round2 clean on1386c2c; no open threads, functional CI GREEN. Owner review
acceptance/merge still pending. M4 round1 on8b255fa raised two P2 findings.

Observed: thread4467194626: interrupted rmtree can leave an incomplete active
snapshot-ID directory. Inferred: later full catalog verification blocks pruning
forever. Verified by: actual unlink(snapshot.db) then synthetic OSError; next
check remained backup_retention_failed. Fix atomically moves a fully verified
obsolete candidate out of active catalog to unique .retired-ID-nonce, using the
existing no-clobber publication helper. Cleanup removes only regular known
SQLite family files, preserves original verified manifest until last, and resumes
recognized partial discards under the same namespace lock. Foreign/unknown or
corrupt artifacts are never deletion permission. Empty unknown shells left after
the final unlink are preserved, not adopted; unique names cannot block later
active retention. No extra queue/status schema, engine or repair endpoint.

Observed: thread4467194635: selected store demo marker disappears during reset.
Verified by: enabled real-path DB with dataset_origin=demo created backup root
after clear_all_data (RED). prepare_reset now returns whether backup protection
was required; the caller carries that decision across DELETE and never starts
post-reset backup for an excluded store. Actual HeadlessState/deactivate_demo_mode
entry is covered. This preserves rather than broadens eligibility policy.

Both initial regressions RED before fixes. Dedicated combined validation and
exact-head CI pending. Real worker os._exit after retired DB unlink tests restart
and OS lock release, alongside injected permission failure/retry, foreign retired
artifacts and original reset/pin/restore evidence. UI/API/config contracts are
unchanged by review delta. No third-party/personal data or services used. Round2
not requested automatically; budget used1/2 until an explicit verification request.

M4 review fix focused validation:97 passed (28.39s), Ruff/diff GREEN. Actual
worker exits74 after retired snapshot.db unlink; a fresh bounded worker acquires
the released OS lock, resumes cleanup and returns ready without maintenance
warning. Demo real-path direct reset and actual deactivate_demo_mode both keep
backup root absent. Unknown retired artifacts remain unchanged. Initial extended
demo fixture used plain dict instead of supported SessionDict factory; corrected
to make_headless_state without changing the facade. Full exact-head CI pending.

M4 full fix-head run f88127d:4373 passed/16 skipped/124 deselected,1 failed in
the existing sync happy-path test (315.81s). Its diagnostic captured degraded
backup_io_error before the expected callback. A bounded10-case probe reproduced
1 failure/9 pass with actual read-only provenance OperationalError codes261
(SQLITE_BUSY_RECOVERY) and5 (SQLITE_BUSY). Inferred: initial status-read and sync
writer overlap mixes an allowed fail-closed path into this success-only test.
Verified by: coordinate callback start after initial response reads finish;10/10
then PASS with0 provenance errors. Assertions/timeouts/guards unchanged; existing
locked-provenance test still covers the fail-closed product path. This is a test
scheduling correction, no product eligibility/concurrency change. Final-head
full/CI evidence remains pending. Earlier failure records are retained above.

Final ownership disproof: partial namespace recovery with only retired history
and missing status must still treat pins as unknown. RED reproduced that the
active-ID-only history detector allowed cleanup. Count retired-ID entries too;
no status/queue schema change. Original protected copy stays untouched and
backup_reset_pins_unknown persists. This extends existing lost-pin recovery to
the new discard phase rather than inventing a repair permission.

Final lost-pin delta related validation98 PASS (35.83s), Ruff/diff GREEN.
Final full CI on the published frozen head is authoritative; local full evidence
started before this last one-line history guard delta and is a checkpoint only.
