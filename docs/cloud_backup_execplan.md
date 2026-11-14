# Подключить проверенные облачные копии без второго runtime (#626 / #752)


Живой ExecPlan по `.agent/PLANS.md`; контракт —
[cloud_backup_slice_spec.md](cloud_backup_slice_spec.md). Текущая работа — только
M1 specification; M2/M3 ниже ещё не реализованы и не разрешают live activation.

## Purpose / Big Picture


После потери Mac атлет сможет получить проверенную SQLite из зашифрованного
Cloud.ru repository. Тренер запускается как раньше; отдельное фоновое задание
копирует только готовые локальные снимки и сообщает давность защиты. Repository —
набор зашифрованных объектов restic, а manifest — описание конкретного SQLite
snapshot с hash и отпечатками таблиц. Вместо самописной криптографии используется
restic, вместо сервера задач — штатное расписание macOS.

## Progress


- [x] 2026-11-14: synthetic Cloud.ru/restic round-trip завершён, exact objects
  удалены; evidence в #626 comment 6879508968. Это не full acceptance.
- [x] 2026-11-14: current main a661c802584f проверен; создана ветка
  codex/issue-626-cloud-backup-spec, M1 issue #752, сформулирован контракт.
- [ ] M1: docs/link checks, независимый checker, pushed draft PR и owner review.
- [ ] M2: RED → shared transport/CLI и macOS schedule template → GREEN.
- [ ] M3: shared status API/web, domain drill и итоговая synthetic приёмка.
- [ ] Отдельное решение Greg о retention/recovery custody и live activation.

## Surprises & Discoveries


Observed: restic 0.19.1 вернул успешный no-cache restore synthetic snapshot за
1.651 с; wrong-password exit 12, 6 remote objects STANDARD. Inferred: transport
совместим с выбранным Cloud.ru для малого artifact; cheap falsifier — скачать
и сравнить bytes/schema/rows, не ограничиться upload exit. Verified by: сравнения
и штатный SQLite restore прошли, результат записан в issue. Реальная БД/RTO и
domain evidence этим не доказаны.

Observed: services/automatic_snapshots.py держит namespace_lock вокруг publication
и retention, сохраняет version-1 manifest с fingerprint; snapshot_runtime.py
обновляет last_checked_at даже без нового generation. Inferred: независимый
uploader может переиспользовать ready pair без live SQLite/нового engine, но
нельзя держать lock во время сети или считать upload временем покрытия данных.
Verified by: прочитаны _run/_retain/namespace_lock и BackupRuntime.check;
concurrent staging/freshness integration tests пока NOT RUN (M2).

Observed: ADR-0002 запрещает вынос данных за Mac, а владелец выбрал cloud backup.
Inferred: нужно явное узкое opt-in исключение для ciphertext, не молчаливое
переопределение privacy. Verified by: пункт 4 ADR и owner scope; addendum Proposed,
его принятие/live activation ещё не заявлены.

## Decision Log


2026-11-14, Spec Owner: один restic S3 transport; native LaunchAgent запускает
короткую команду, а не ещё один тренер. Owner отверг второй runtime.

2026-11-14, Spec Owner proposal: последний validated snapshot раз в час; отдельная
remote readback verification; monthly isolated drill. RPO измеряется по local
checked generation, а не upload timestamp. Это сохраняет честное состояние при
остановленном локальном backup и при отсутствии новых строк.

2026-11-14, Spec Owner proposal: нет автоматического cloud prune в v1. Локальная
14-day/8-week/reset protection unchanged; ранние cloud copies не исчезают при reset.
Рост и стоимость требуют явного owner acceptance перед рабочим включением.

## Context and Orientation


services/sqlite_snapshot_core.py содержит inspect_database и SQLite Backup API.
services/automatic_snapshots.py создаёт immutable snapshot.db/manifest.json в
BACKUP_DIR/<source_namespace>/snapshots/<snapshot_id>, защищает каталог OS lock
и применяет local retention. Source namespace идентифицирует выбранный локальный
путь; generation — fingerprint схемы/типизированных строк, а не дата файла.
services/snapshot_runtime.py вызывает этот сервис после важных commits и при
периодических проверках. Их договорённость не меняется.

api/routers/backup.py и api/backup_contract.py обслуживают local status/check,
web/components/BackupStatusBanner.tsx показывает существующий warning.
scripts/sqlite_backup_restore.py восстанавливает выбранный снимок лишь при
operator stopped confirmation и сохраняет rollback существующей цели.
tests/smoke/test_database_relocation_drill.py и test_snapshot_retention.py
содержат actual domain fixtures/readers; заимствовать их, не заменять голыми
COUNT(*) искусственных таблиц. #625 guards изолируют тесты до imports.

## Plan of Work


M1 заканчивается проверяемым документом и draft PR. Не читать user .env/SQLite/
Keychain, не менять запущенные сервисы, не создавать рабочий repository.
Перед реализацией согласовать policy в companion spec; разработка не является
личным rollout. Native review запрашивается отдельно, максимум два раунда.

M2 добавляет services/cloud_backups.py с prepare/run/read-status/drill boundary
и scripts/cloud_backup.py с explicit config; CLI не импортирует personal defaults.
Config/receipt/lock/staging — private operator data вне Git и SQLite. Settings
лишь разрешает путь cloud config без создания файлов. Сначала RED на no-opt-in,
foreign paths, bad manifest/binding, retention race и timeout; затем reuse пары
под namespace lock, restic subprocess вне lock, readback и atomic receipt.
Метаданные не дают разрешения на чтение произвольного пути. Child env содержит
только выбранные credentials в памяти; diagnostic output фиксирован и очищен.

В том же M2 добавить deploy/macos/ai-trainer-cloud-backup.plist.example и runbook
ручной установки. RunAtLoad + hourly calendar, explicit executable/config paths,
без секретов в plist и KeepAlive. Пропуски при sleep/off не обещают coverage;
никакой автоматической установки job, init или чтения working config в CI.

M3 добавляет CloudBackupStatus отдельно от BackupStatus в api/backup_contract.py,
GET /api/backup/cloud/status в api/routers/backup.py, TypeScript mirror/scenarios
и существующий web warning consumer после Domain → UI handoff. Shared reader
сверяет current namespace/generation и timestamps; GET не делает network/write.
Затем acceptance восстанавливает actual domains из remote fixture при удалённых
локальных originals/receipt, через fresh readers в новой owned DB. Monthly drill
сверяет весь manifest и обновляет отдельный last_drill_at; failed drill явно виден.

## Concrete Steps


Команды выполняются в корне отдельного checkout. M1: git diff --check и проверка
relative Markdown links четырёх изменённых документов; product tests N/A.
До push зафиксировать independent checker и dispositions. Draft PR закрывает
только #752, ссылается на #626 и не закрывает общую задачу преждевременно.

Для M2/M3 следующие команды — будущий план, а не выполненные проверки:

    python scripts/run_isolated_tests.py tests/smoke/test_cloud_backups.py -q
    python scripts/run_isolated_tests.py tests/smoke/test_cloud_backup_drill.py -q
    python scripts/run_isolated_tests.py tests/smoke/test_automatic_snapshots.py tests/smoke/test_snapshot_retention.py tests/smoke/test_backup_api.py tests/smoke/test_database_relocation_drill.py -q
    python -m ruff check .
    python scripts/run_isolated_tests.py -m "not live and not debug and not e2e" tests/

Web slice также требует npm --prefix web run contract:extract, lint/build и
изолированный Playwright scenario нового status. Runtime CLI в M2: python
scripts/cloud_backup.py status|run|drill --config /absolute/private/config.json;
status read-only, run/drill — explicit operator operations. Все test children
используют scripts.scratch_pytest.child_environment/fresh_child_environment;
никаких owner credentials, launchctl или real Cloud.ru по умолчанию.

## Validation and Acceptance


M1 проверяется против scope/AC #752 и companion matrix. Независимый reviewer
читает exact diff и repository contracts, не private evidence/credentials.
Будущие M2 failures должны наблюдаться до implementation; guards/default-off,
race/kill/state loss и safe diagnostics проверяются synthetic subprocess tests.
Проверенный внешний restic — dependency characterization, не новый product RED.

M3 full-domain drill сохраняет IDs/raw JSON/checkpoint/cycle/decision/match/
feedback/readiness/provider evidence через shared readers после restore/restart;
hash/integrity alone недостаточны для overall acceptance. RPO ≤24ч и RTO ≤30мин
имеют условия/измерение из companion spec. Сравнить source/rollback sentinels
до/после failure и reset. Live Cloud.ru probe выполняется только с owner-approved
synthetic prefix; fake S3/transport doubles в CI не считаются live evidence.

## Idempotence and Recovery


Upload/retry не удаляет source, local snapshots и remote history. Успех хранится
после exact snapshot readback; kill до receipt даёт unknown/degraded и допускает
безопасный повтор. Missing/corrupt receipt не даёт init/adoption/cleanup permission.
Config disable/unload job останавливает будущие попытки и сохраняет repository,
password и снимки. Restic lock contention не лечится автоматическим unlock.
Все процессы/deadlines и staging принадлежат только текущему запуску.

Потеря ноутбука использует независимо сохранённые URL/ID/password и новые S3 keys;
restore идёт в новый temp. Личная activation требует отдельного конкретного
preview/backup/rollback и owner confirmation, не команды из этого плана.

## Artifacts and Notes


14.11.2026 synthetic experiment: 2-table fixture, bytes/hash/schema equality,
wrong password refused, 6 STANDARD objects removed. Полный receipt находится
только у оператора; public summary — #626 comment 6879508968. Не публиковать
local filenames/Key ID/Key Secret/password/request headers из private logs.
M1 exact SHA/CI/checker/PR outcomes добавляются при завершении документа.

## Interfaces and Dependencies / ASR traceability


Единственная новая внешняя runtime dependency — установленный restic, initial
tested version 0.19.1. AWS CLI используется оператором, продукт не требует его
для transport. macOS Keychain/LaunchAgent — dogfood v1; Windows/Linux/Docker
scheduling не заявляются. Shared Python выдаёт CloudBackupStatus/receipt и
стабильные reason codes; UI не вычисляет freshness и не читает секреты.
ASR-DEP-2/REL-3/SEC-1/MOD-2, ADR-0001/0002/0007; изменение privacy boundary
предложено в ADR-0002, не объявлено принятым. Новый общий framework не нужен.

## Outcomes & Retrospective


M1 draft подготовлен, independent verdict/push/PR пока pending. M2/M3, рабочие
password/schedule, personal DB migration и activation не выполнены. Стоимость
и recovery ownership не подменяются успешным маленьким transport probe.

Revision 2026-11-14: начальный v1 plan после synthetic совместимости; выбран
один transport и no-prune policy proposal, чтобы исключить лишние engines/сервисы.
