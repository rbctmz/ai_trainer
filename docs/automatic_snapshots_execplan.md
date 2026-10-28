# #623 — минимальные автоматические локальные снимки

Этот ExecPlan поддерживается по [.agent/PLANS.md](../.agent/PLANS.md).
Текущий scope — M1: спецификация и characterization. Runtime и включение на
личных данных требуют следующих этапов. Merge owner — Greg.

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
- [ ] M1: проверки документов, draft PR, independent review и owner acceptance.
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
один небольшой status-файл и OS-lock. Причина: включение на личных данных
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
lock, не удалять manual/unknown/corrupt artifacts. Прогнать существующий restore
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
