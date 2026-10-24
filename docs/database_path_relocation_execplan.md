# #624 — отдельный путь рабочей БД и явная offline миграция


Этот living ExecPlan следует `.agent/PLANS.md`. Контракт и матрицы находятся в [slice spec](database_path_relocation_slice_spec.md); обновлять оба документа при изменении поведения.

## Purpose / Big Picture


Рабочая SQLite должна переживать удаление checkout. Пользователь увидит стабильный абсолютный путь, явный отказ при неоднозначном upgrade и проверенный перенос, который не стирает старую базу. Class A implementation следует уже принятому контракту; текущий slice — M1 path/default/preflight, без live DB/process операций. Offline migrate и его full drill остаются M2–M3.

## Progress


- [x] 2026-10-24 Europe/Moscow: owner возобновил #624, поручил спецификацию переноса/проверки/отката; роль Spec / Architecture Owner.
- [x] Проверены #622 owner decision, #624/#625, Settings/API/default consumers и offline backup primitives на main d977618.
- [x] Относительный default подтверждён без SQLite opens; 16 существующих backup/restore tests passed на временных БД.
- [x] Подготовлены path/upgrade/CLI/activation/rollback contract и будущая RED matrix.
- [x] Первое независимое native spec review на ae554b23ab: два blocking P2; оба подтверждены pure-path probe и исправлены в контракте/матрицах.
- [x] Scoped native verification clean на 9ae7676431 (2/2); owner слил #724 как 276eec6 2026-10-24T20:56:29Z.
- [x] 2026-10-25: handoff Spec/Architecture → Domain/API Implementer по принятому контракту; M1 в codex/issue-624-m1-database-path, без live writes.
- [x] M1 path/default/preflight: RED → GREEN, explicit path compatibility; 54 new path/integration cases, full contributor-safe 4067 passed / 18 skipped / 116 deselected.
- [ ] M1 runtime PR: remote CI, independent native review и отдельный owner merge (0/2 review rounds).
- [ ] M2 offline migrate: RED → GREEN, all-domain/WAL/failure/no-clobber proof.
- [ ] M3 synthetic acceptance, final checks/native review и явный owner merge.
- [ ] Отдельный operator handoff; реальный перенос не авторизован этой подготовкой.

## Surprises & Discoveries


Observed: Settings и backup CLI сейчас независимо содержат относительный `ai_trainer.db`; API имеет дополнительный fallback, а два backfill scripts берут Settings напрямую. Inferred: правка только Settings оставит рассогласованные defaults. Verified by: scoped inventory исходников и AST/cwd probe, без личной БД.

Observed: #622 owner decision отменил прежний широкий стек #627/#628/#629 и поставил #624 перед #625. Inferred: нельзя возвращать old guard в горячий `Database._connect` или вводить весь durability track за один slice. Verified by: issue #622 comment5752163534; API explicit/temp/legacy compatibility включена в spec.

Observed: existing backup атомарно публикует новый artifact без clobber, а restore умеет заменять target. Inferred: direct restore на final migration target нарушил бы refusal-on-existing invariant. Verified by: source reading и 16 existing temporary-DB tests; будущий migration-specific race test NOT YET.

Observed: review #724 показал пересечение future sidecar names и ложный legacy detection при cwd=data dir. Inferred: проверок только существующих файлов/endpoint aliases недостаточно, а выбранную SQLite family нельзя считать отдельным legacy store. Verified by: pure-path probe без filesystem/SQLite — все 18 направленных endpoint/suffix комбинаций пересекаются; candidate из data-dir равен target, отдельный checkout candidate отличается. Это проверка логики spec, не runtime GREEN.

## Decision Log


2026-10-24 / Spec Owner: platform data directory + explicit override; pure resolution и отдельный default-selection preflight. Это сохраняет explicit operator/test paths и не прячет пустую установку за upgrade.

2026-10-24 / Spec Owner: copy и activation раздельны. CLI не редактирует `.env`; successful output — `copied_not_activated`. После activation старый source становится stale и не может быть автоматическим rollback.

2026-10-24 / Spec Owner: reuse #293 в существующем operator module, no-clobber publication после logical validation. Без новых runtime dependencies, DB schema/receipt/selector, provider writes и automatic retention.

2026-10-24 / Spec Owner after native round 1: до любых artifacts проверять непересекаемость F(p)={p,p-wal,p-shm,p-journal} всех переданных endpoints, а при apply полной тройки source/target/rollback. Исключать сам selected platform store и его sidecars из legacy candidates по нормализованной identity; неоднозначный hardlink family отвергать. Это сохраняет snapshot независимым и разрешает запуск из data directory.

## Outcomes & Retrospective


M0 завершён: два P2 исправлены, scoped review clean, owner merge #724 подтверждён. M1 реализован в candidate branch: focused и contributor-safe GREEN, runtime review/owner merge ещё pending. M2–M3 остаются. Работающий runtime и личные данные не изменены. Проверки Windows native/полной migration ещё не выполнялись; не подменять их baseline backup tests.

## Context and Orientation


`config/settings.py` владеет env/defaults. `data/database.py::Database` открывает/инициализирует SQLite, обычно через API dependencies или `utils/app_state.py::HeadlessState.database`. `api/deps.py` разделяет real/demo, но имеет raw fallback. `docker-compose.yml` уже задаёт `/data/ai_trainer.db`. `run_acceptance.sh` экспортирует временный DATABASE_PATH. `scripts/sqlite_backup_restore.py` содержит readonly SQLite connection, Backup API, integrity checking, no-clobber snapshot publish и operator-confirmed restore. WAL — файл ещё не перенесённых в main SQLite committed pages; plain copy main-файла недостаточен.

## Plan of Work


M1: в `config/database_paths.py` добавить чистый resolver, принимающий platform/env/home/cwd, и узкий read-only legacy/default preflight. Environment reads/defaults остаются в config. В Settings сохранить строковый DATABASE_PATH и явное происхождение выбора. До legacy refusal исключить выбранный platform store с его sidecars: запуск из data directory не требует миграции самого target; отдельный legacy продолжает блокировать, неоднозначный hardlink/sidecar alias — явный отказ. В `Database.__init__` проверять только implicit selection до init, не `_connect`; explicit path не блокировать. API startup и real/demo dependencies используют тот же выбор и alias policy. У operator scripts заменить только default fallback, сохранив explicit аргументы. Не добавлять универсальный cleanup guard из #625.

M2: добавить `migrate` к существующему SQLite CLI. Наиболее ранние проверки — absolute endpoints, aliases, наличие target/sidecars, stopped acknowledgement и непересекаемость будущих SQLite families F(p)={p,p-wal,p-shm,p-journal} для всех переданных endpoints независимо от наличия файлов. Dry-run может не задавать rollback-output: тогда snapshot path не проверен; apply проверяет полную тройку до первой записи. Read-only plan распознаёт legacy application schema по минимуму `activities` из spec и проверяет schema/aggregates без output files. Source может находиться в checkout; target/snapshot — вне checkout, с pairwise alias/no-clobber проверкой. Apply создаёт private rollback snapshot и temporary target, сравнивает schema/ID/raw values, затем публикует no-clobber. Вынести необходимые маленькие reusable функции внутри этого модуля, не дублировать Backup API. Migration path не должен требовать успешного runtime preflight: он нужен как раз для исправления legacy-present.

M3: один синтетический application DB с provider links/manual links, planning/decision/match/feedback/readiness evidence и committed WAL marker проходит CLI plan → apply → explicit restart → сравнение. Затем inject failures, target race, retry/reset и post-activation rollback proof. Обновить существующий runbook, quickstart и ADR-0002; раскрыть фактически проверенные ОС. Опубликовать evidence bundle на final head, затем native review и owner merge; никаких live migration команд автоматически.

## Concrete Steps


Работать только в изолированном worktree. До кода читать linked spec и проверить source SHA/чистоту. Для любых pytest установить DATABASE_PATH/DEMO_DATABASE_PATH/CHATS_DIR и user-data homes в уникальный temp root **до импорта Settings**, очистить provider credentials. Не запускать baseline tests в окружении личной БД. Fixtures создают только synthetic SQLite; `.env`, backups и реальные data directories не читать.

    python -m pytest -q tests/smoke/test_database_paths.py tests/smoke/test_database_relocation.py
    python -m pytest -q tests/smoke/test_sqlite_backup_restore.py tests/smoke/test_sqlite_concurrency_policy.py
    python -m ruff check .
    python -m pytest -m "not live and not debug and not e2e" tests/

Первая команда относится к будущим tests: сейчас их нет, это не выполненный RED. Перед изменением поведения получить meaningful assertions, которые падают на старом контракте; после — GREEN. Contributor-safe broad run выполняется в описанной изоляции. Web build/lint — только если фактический scope затронет web; текущий план его не меняет. Если API/TS DTO неожиданно меняется, остановить slice для Spec handoff, а не скрыть расширение.

На временных абсолютных путях выполнить два примера `migrate` из spec. Ожидать dry-run без output artifact, затем `copied_not_activated`, integrity=ok и равные logical digests. Отдельно задать DATABASE_PATH=target в тестовом subprocess: он должен прочитать те же IDs. В реальном runbook сначала отдельное owner решение на остановку/перенос; команды ниже не подразумевают его.

## Validation and Acceptance


Матрица spec покрывает три ОС, два cwd и cwd=platform data dir с existing main/sidecars, отдельный legacy store, все 18 направленных endpoint/sidecar пересечений с ещё отсутствующими файлами, explicit overrides/Docker, real/demo aliases, legacy-only/both, WAL, существующий/появившийся target, corrupt schema/data, disk/permission/publish failures, restart/retry/reset и rollback после новых записей. Проход — поведение, а не только тест-count: source/config не меняются при отказе; финальный target появляется только проверенным; старые IDs и raw JSON не переписаны; нельзя потерять новые записи возвратом к stale source. Указать реальные команды/счётчики/платформы после исполнения, не заранее обещать число GREEN.

## Idempotence and Recovery


Dry-run повторяем. Повтор apply при существующем target — отказ без clobber. Failed preparation оставляет source и валидный rollback, удаляет только свои temp artifacts. После activation code rollback сохраняет explicit target; смена пути требует snapshot текущей активной БД. Full reset не удаляет operator backups. Сбой остановки/квиесцентности — операторская граница, CLI не притворяется OS-level lock.

## Artifacts and Notes


M0 baseline d977618: AST default `ai_trainer.db`; два temp cwd разрешают его в разные файлы; SQLite не открывалась. Existing temporary backup/restore suite: 16 passed in 0.56s. Приватная evidence-папка записана в `/private/tmp/ai-trainer-624-spec-current.txt`; её БД/логи не публиковать. Это исходный M0 record. M1 добавляет config resolver/preflight, default consumers и synthetic tests; новой migration и live approval по-прежнему нет.

## Interfaces and Dependencies


Использовать standard library pathlib/os/sys/sqlite3; без platformdirs/new dependency. Будущие seams в config: `resolve_database_paths(env, platform, home, cwd)` возвращает normalized real/demo paths + origin, `runtime_database_path()` выполняет узкий implicit-selection preflight и возвращает строку либо именованную configuration error. Import Settings сам не открывает/создаёт SQLite. CLI-facing `plan_database_relocation(...)` и `migrate_database(..., apply, confirm_stopped)` находятся рядом с существующим backup/restore; result/exit contract описан spec. Public REST/TypeScript и схема не меняются. Независимый reviewer проверяет resolved paths/upgrade/default consumers и failure boundaries до Domain/API implementation; merge/live authority остаётся у rbctmz.


Revision 2026-10-24: по независимому review ae554b23ab уточнены selected-store identity и будущие SQLite namespaces; добавлены M1/M2 cases, evidence и review budget. Изменены только документы, новые runtime tests пока planned.

Revision 2026-10-25: подтверждены clean spec verification и owner merge #724; начат только M1. RED: default ai_trainer.db относительный и relative override не закреплён (2 meaningful failures; explicit Database(tmp) characterization GREEN). Новые pure resolver/preflight checks проверяют будущий config seam отдельно; отсутствие модуля до реализации не выдаётся за behavioral RED.

M1 self-review: pure-path probe воспроизвёл main-only symlink, ошибочно исключавший целое SQLite family, и NotADirectoryError вместо именованного отказа. Исправлено сравнением resolved parent/base identity и отдельной обработкой создания parent; добавлены точные synthetic regressions. Для нестандартного XDG path внутри checkout implicit default также отказывает до artifacts, explicit override не ограничивается.

M1 acceptance 2026-10-25: ruff check всего source tree — GREEN. Contributor-safe
`python -m pytest -m "not live and not debug and not e2e" tests/ -q
-W error::pytest.PytestReturnNotNoneWarning` — 4067 passed / 18 skipped /
116 deselected in 280.13s. Запускался exact tracked-source snapshot в
`/private/tmp/ai-trainer-624-m1-qipy1b1y/source` с текущей working delta; равенство
всех 9 runtime/test Python files проверено. Все DATABASE_PATH/DEMO_DATABASE_PATH,
CHATS_DIR/HOME/XDG/TMPDIR заданы под owned temp root до import, dotenv отключён,
audit hook запрещает SQLite вне root и внешние sockets. Existing TypeScript
переиспользован read-only для contract checks; UI не менялся, web build/lint N/A.
Native Windows/ACL, migration M2/M3, live user data — NOT RUN.

Первые broad attempts не являются product failures: temp cwd ломал относительные
source-file tests; отсутствие TMPDIR нарушало собственный isolation audit;
после этого 4035 passed + 5 failures из-за отсутствующего Git HEAD во snapshot.
После добавления локального synthetic Git HEAD и установленных TS dependencies
все эти проверки прошли; повторный full run GREEN, как указано выше. Подробные
приватные логи/runner — `/private/tmp/ai-trainer-624-m1-qipy1b1y`, их SQLite
и output не публикуются. Это тестовая Git history, не merge/review evidence.


CI correction 2026-10-25 (до первого native runtime review): run 40133680451
на 883a39d выявил два новых subprocess-test failures, ModuleNotFoundError: config.
Observed: child cwd — tmp_path, inherited PYTHONPATH отсутствует на CI.
Inferred: локальный runner экспортировал source root и маскировал зависимость
тестов от окружения. Verified by: локальный запуск ровно этих двух assertions
после удаления PYTHONPATH повторил 2 failures. Исправлен только test bootstrap:
явный source root в child PYTHONPATH, whitelist environment без credentials,
dotenv disabled до Settings import, все home/data paths временные. Runtime code
не менялся. Green на исправленном bootstrap и CI фиксируются в PR metadata;
исторические 4067 GREEN выше не объявляются повторным full run этого head.
