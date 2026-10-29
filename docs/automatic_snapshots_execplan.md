# #623 — минимальные автоматические локальные снимки

Этот ExecPlan поддерживается по [.agent/PLANS.md](../.agent/PLANS.md).
M1 принят владельцем и merged #743 как 4230a9d. Текущий scope — M2:
явный snapshot core и synthetic проверки. Runtime hooks и включение на
личных данных относятся к следующим этапам. Merge owner — Greg.

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
- [ ] M2: bounded online snapshot, публикация, concurrency/faults.
- [ ] M3: shared post-commit hooks, lifecycle check, status/API/web/Streamlit.
- [ ] M4: retention и restore drill, полная synthetic приёмка и отдельный owner merge.

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
