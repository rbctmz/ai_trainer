# #624 — безопасное размещение и перенос рабочей SQLite

Статус: **Draft / spec only**, 24 октября 2026. Runtime ещё не изменён.
Issue: [#624](https://github.com/rbctmz/ai_trainer/issues/624), parent [#622](https://github.com/rbctmz/ai_trainer/issues/622).
Author: Spec / Architecture Owner; checker: независимый native reviewer (round 1: ae554b23ab; verification pending); merge owner: rbctmz.
Baseline: `d977618804d63b43dbb1078be69dae5648f3dacb`. Candidate SHA — текущий docs PR, фиксируется в его evidence bundle.
[ExecPlan](database_path_relocation_execplan.md).

## Change Class

**Class A / Full** для реализации: меняются default конфигурации, выбор persistent data и operator migration boundary. Текущий срез только документирует контракт; проверка docs соразмерна Class C, это не понижение класса реализации. Первое независимое native spec review выполнено на `ae554b23ab`: два blocking P2, исправления описаны ниже; бюджет 1/2, manual only, acceptance SHA и exception: N/A. Scoped verification исправлений ещё не получена. Переход к коду — после независимого spec review, не по одному наличию этого файла.

## Scope

Пользователь может обновить код или удалить checkout, сохранив рабочую БД вне исходников. Обычный upgrade не должен молча показать пустую новую базу. Перенос — явный offline operator flow: проверить → сохранить rollback snapshot → подготовить target → проверить → отдельно активировать путь.

Файлы реализации: новый `config/database_paths.py`, `config/settings.py`; default selection в `data/database.py` (до открытия соединения), `api/deps.py` и startup `api/main.py`; defaults operator CLI `scripts/sqlite_backup_restore.py` и двух backfill scripts (`backfill_activity_provider_links.py`, `backfill_intervals_distance.py`). `utils/app_state.py` уже использует `Database()` и получает тот же default через него. Документация: существующий runbook, quickstart и ADR-0002. Новые focused tests: `test_database_paths.py`, `test_database_relocation.py`.

## Non-goals

Нет автоматического перемещения/удаления БД, правки `.env`, остановки/перезапуска сервисов, live/provider writes или миграции личных данных в этом срезе подготовки. Нет Postgres, новой схемы, переноса chats/credentials, autorefresh исторических payload, automatic snapshots/retention (#623), off-device transport (#626) или универсального path/cleanup guard (#625). Старые #627/#628/#629 не cherry-pick: закрыты без принятой реализации.

## Public Contracts

### Путь и совместимость

`Settings.DATABASE_PATH` остаётся строкой. Явный непустой `DATABASE_PATH` имеет приоритет, включая Docker `/data/ai_trainer.db`. Относительный override сохраняет прежнее значение относительно launch cwd, но нормализуется один раз в абсолютный путь; `~` раскрывается. Пустой/whitespace override — явная ошибка конфигурации, не тихий выбор другого файла. Обычный `Database(explicit_path)` сохраняет прежнее поведение. Глобальный guard в `Database._connect` запрещён.

При отсутствующем override default — `ai_trainer.db` в каталоге приложения:

| ОС | Default directory |
|---|---|
| macOS | `~/Library/Application Support/ai_trainer` |
| Linux | `$XDG_DATA_HOME/ai_trainer`, иначе `~/.local/share/ai_trainer` |
| Windows | `%LOCALAPPDATA%\ai_trainer`, иначе `~/AppData/Local/ai_trainer` |

Пустой/относительный XDG_DATA_HOME игнорируется; относительный LOCALAPPDATA также не становится cwd-based default. Нет fallback в cwd при неизвестной ОС/неопределимом home. Resolver сам не создаёт каталогов, не открывает SQLite и не переносит файлы. Native Windows filesystem acceptance пока NOT YET; parametrized path tests не выдаются за неё.

`DEMO_DATABASE_PATH` сохраняет override; без него — sibling `<real_stem>_demo<suffix>`, как сейчас. До demo seeding отвергать совпадение real/demo после resolve/samefile. Acceptance и тесты передают свои temp real/demo paths до импорта Settings; их defaults не становятся рабочей БД. Полная защита всех diagnostic/cleanup входов остаётся #625.

### Upgrade preflight

Перед **неявным** открытием real DB проверить известные legacy candidates `ai_trainer.db` и sidecars (`-wal`, `-shm`, `-journal`) в launch cwd и checkout. Для linked worktree также учитывать основной checkout из Git metadata, без рекурсивного поиска по home. Нечитаемое/неоднозначное metadata — именованный отказ, не выбор наугад. Сначала исключить из legacy candidates уже выбранное platform store и принадлежащие ему sidecars: сравнивать нормализованные абсолютные base paths, resolved parent paths и native case/file identity. При `cwd=platform_data_dir` кандидат `cwd/ai_trainer.db` — сам target, не отдельная legacy DB; его main/WAL/SHM/journal не вызывают migration_required. Один лишь hardlink main-файла при разных base names не доказывает идентичность SQLite family: при неоднозначной принадлежности sidecars — именованный отказ, не пропуск проверки. При наличии **отдельного** legacy artifact отказаться с `database_migration_required` **до создания новой БД**, независимо от возраста/размера файлов. Если legacy и target существуют, не выбирать «свежее». Явный override — осознанный выбор оператора, preflight не переопределяет его.

Preflight нужен в API startup, direct real dependency и default `Database()`; Settings import остаётся без открытия/создания БД. Явные temp/offline paths не блокируются наличием чужого legacy файла. Это default-selection проверка #624, не armed-guard framework #625. REST/TypeScript/DB schema — unchanged. Конфигурационный default — breaking с явным upgrade refusal и operator migration; explicit непустой override — compatible. CLI `migrate` — additive. API/TS DTO и endpoints не меняются; startup error — операторская диагностика, не новое экранное API.

### CLI relocation

Расширить существующий `scripts/sqlite_backup_restore.py` subcommand `migrate`; его явные source/target не требуют успешного обычного startup preflight. Никакого импорта приложения, который открывает default DB. Предлагаемый operator contract:

    python scripts/sqlite_backup_restore.py migrate --source /abs/legacy.db --target /abs/app-data/ai_trainer.db
    python scripts/sqlite_backup_restore.py migrate --source /abs/legacy.db --target /abs/app-data/ai_trainer.db --rollback-output /abs/backups/pre-migration.db --apply --confirm-stopped

Без `--apply` — read-only dry-run: paths, существование/alias checks, integrity/schema и агрегаты; target/snapshot/config не создаются. SQLite читается через `mode=ro`, без DDL/DML; dry-run не обещает неподвижность SQLite read-lock/SHM metadata. Apply заново проверяет источник после остановки, не доверяя устаревшему dry-run.

Apply требует `--confirm-stopped`, явных абсолютных source/target/rollback-output. Флаг — подтверждение оператора, не автоматическое обнаружение/остановка процессов. Отсутствует флаг — отказ до записей. Все существующие target/rollback-output (включая пустой файл), их sidecars, aliases между любыми двумя endpoints, symlink endpoints и directory/invalid source — отказ. Source разрешён внутри legacy checkout; target и rollback-output должны быть вне Git checkout. Проверять также разрешённые parent paths: symlink в родителе не должен обходить эту границу. Hardlink/case aliases проверяются native resolve/samefile до SQLite; неизвестный результат — отказ. Rollback snapshot также публикуется no-clobber; source, target и snapshot не могут подменять друг друга.

До открытия SQLite/создания artifacts проверить также будущие имена: для каждого endpoint `p` зарезервировано семейство `F(p)={p, p+"-wal", p+"-shm", p+"-journal"}`. Для любых двух из source/target/rollback-output семейства должны быть попарно непересекающимися, даже если файлы ещё отсутствуют; применять ту же нормализацию parent/case/alias, что к endpoints. Пересечение — `endpoint_namespace_overlap`, отказ без artifacts. Например, target=`/outside/new.db`, rollback-output=`/outside/new.db-wal` запрещены в обоих направлениях, как и пары с source и суффиксами `-shm`/`-journal`. Проверка обязательна и в dry-run для всех переданных endpoints; rollback-output без apply опционален, но такой plan не утверждает, что непереданный snapshot path проверен. Apply заново проверяет полную тройку до первой записи.

Порядок apply: validate source → WAL-aware private rollback snapshot через #293 → сравнить его logical schema/data с source → подготовить временный target рядом с назначением → integrity + logical validation → atomic **no-clobber** publication. Если target появился в гонке, не перезаписывать. Не вызывать `restore_database` непосредственно на final target: этот API умеет заменять существующий файл. Переиспользовать `_copy_sqlite`, `_publish_new_artifact` и связанные уже проверенные примитивы в том же модуле; не писать второй backup engine.

Минимальный признак поддерживаемой application DB: обычная таблица `activities` с `activity_id TEXT PRIMARY KEY`, `date`, `sport` и `duration_minutes`; пустая по строкам application DB допустима, пустой/чужой SQLite без этих признаков — отказ `unsupported_source_schema`. Это распознавание legacy store, не сертификат полной совместимости всех версий приложения. Не требовать наличия более новых доменов и не создавать их во время copy. Сравнивать полный сохранённый SQLite schema catalog (tables/indexes/triggers/views, включая extra objects) и каждую существующую таблицу: counts, стабильные identities и digest всех значений с сохранением SQLite types, NULL и raw JSON. Для таблиц без PK сравнивать детерминированное мультимножество строк, сохраняя дубликаты; также сохранить `sqlite_sequence`/`user_version`/`application_id`, если заданы. Особые fixtures: `activity_provider_links`, `activity_manual_links`, `planning_checkpoints`, `coach_decisions`, `plan_actual_matches`, `session_feedback`, `readiness_snapshots`. Неизвестные дополнительные таблицы сохранять, а неподдерживаемый для полного сравнения SQLite object/virtual table — именованный отказ, не пропуск проверки. File SHA снимка допустим для аудита, но не подменяет logical equality main/WAL source и target. Персональные строки не печатать.

JSON stdout: `planned`, `blocked` или `copied_not_activated`; paths, агрегаты/validation, reason и `configuration_changed=false`. Exit 0 для plan/copy, 2 для ожидаемого отказа; необработанного traceback для operator error нет. Миграция ещё не активирована: оператор после верификации отдельно устанавливает абсолютный `DATABASE_PATH=target` и перезапускает сервис. CLI не редактирует `.env` и не выбирает активную БД сам.

## Failure, Reset, Rollback, Idempotency

До activation source остаётся исходной рабочей базой. Любой fail-before-publish не оставляет final target и не меняет config; созданный валидный rollback snapshot сохраняется. После successful publication/сбоя ответа повторный apply безопасно отказывает `target_exists`, не перезаписывает target и не удаляет подтверждённый snapshot. Cleanup ограничен своими временными artifacts; не трогать существовавшие пути.

После activation откат кода сохраняет explicit target path: #624 не меняет schema. Нельзя молча переключаться на старый source после новых записей — это потеря новых данных. Если нужен другой путь: остановить сервис, снять свежий validated snapshot **текущей** активной БД и отдельным operator restore восстановить в новый проверенный путь. Исходный legacy source автоматически не переписывается.

Persistent artifacts: relocated DB и operator-owned rollback snapshot; нового selector/receipt/cursor в БД нет. Full reset сохраняет существующую semantics очистки активной БД; не удаляет legacy/rollback backups. Их age-out — ручное решение оператора до #623, не побочный эффект reset. POSIX artifacts 0600 / application dir 0700; Windows — user-profile permissions, без заявления эквивалентной POSIX/ACL-сертификации.

## State Boundaries and Identity

Истина выбора — explicit config либо детерминированный platform default, не mtime. Существующие IDs/provenance/checkpoints/raw payload сохраняются без backfill. Переходы: legacy-present → planned → copied-not-activated → operator-activated. Два populated пути без explicit выбора → blocked. SQL read transaction фиксирует агрегаты dry-run; apply требует quiescent source. Нет обещания запретить внешний процесс ОС после операторского подтверждения; источник и target нельзя использовать одновременно как два активных writer.

## Evidence Boundary Matrix

| Identity / provenance | State | Expected / falsifier |
|---|---|---|
| default / два cwd | fresh, нет legacy | один абсолютный platform path |
| cwd=platform data dir / тот же resolved store | target main/sidecars уже существуют | открыть выбранный store, без ложной migration_required; отдельный legacy по-прежнему блокирует |
| explicit absolute/relative; Docker | valid override | сохранить выбранный файл и origin |
| legacy main/WAL; default missing/exists | ambiguous | migration_required, никаких новых DB |
| source=target / symlink / hardlink / case alias | conflicting | отказ до записи |
| F(source), F(target), F(rollback-output) | future endpoint/sidecar names пересекаются | endpoint_namespace_overlap до открытия SQLite/создания artifacts |
| target/sidecar возник после preview | stale | no-clobber, чужой файл неизменён |
| snapshot + target | verified present | все IDs/payload и committed WAL pages сохранены |
| copied target с новыми user writes | newer than legacy | не возвращаться автоматически к stale source |

## RED Matrix

Новые проверки ниже **planned, NOT RUN**; текущий baseline не выдаётся за RED будущего поведения.

| AC / invariant | Required RED → GREEN |
|---|---|
| default cwd-independent; macOS/Linux/Windows | pure resolver fixtures, XDG/LOCALAPPDATA absent/empty/relative, unknown platform |
| compatibility + no implicit switch | explicit absolute/relative, Docker override, legacy-only/both/sidecar-only; no created target |
| selected platform store не legacy | cwd=data dir с target main/WAL/SHM/journal; тот же resolved store при parent alias/native case; отдельный legacy всё ещё блокирует, ambiguous hardlink family не пропускается |
| непересекаемые SQLite families | все 6 направленных пар endpoints × 3 sidecar suffixes (18 cases), файлы ещё отсутствуют; dry-run/apply отказывают до artifacts; distinct sibling DB names разрешены |
| real/demo/acceptance isolation | distinct files, alias refusal до seeding, explicit temp mode без доступа к user home |
| migration dry-run | unchanged logical source, нет target/snapshot/config artifacts; aggregates без personal rows |
| WAL + local evidence | committed marker ещё в WAL; all-domain IDs/raw values одинаковы после copy |
| failures + race | missing stopped flag, disk-full/permission, copy/integrity/domain validation/publish failure, target race; source/config сохранены |
| restart/retry/reset/rollback | target_exists, restart on explicit target, backup survives reset; post-activation writes не теряются |
| ordinary application remains usable | explicit `Database(temp)` read/write работает; `_connect` не получает глобальный guard |

## ASR / ADR Traceability

ASR-REL-1/3: сохранить local evidence и atomic publication; ASR-DEP-2: verified migration/rollback; ASR-MOD-3: schema неизменна; ASR-SEC-1: private artifacts, без personal payload в публичных логах. Reuse ADR-0002 (SQLite/offline backup), ADR-0006 (append-only), ADR-0008 (provider identity). Перед GREEN обновить ADR-0002 bare-metal path subsection и operator runbook; не переводить guarantee в delivered до runtime proof. Новый ADR не нужен: SQLite ownership/concurrency не меняются, путь и activation contract находятся здесь.

## Delivery Slices

M0 — эта спецификация и ExecPlan. M1 — RED→GREEN path/default/upgrade preflight и characterization explicit paths. M2 — RED→GREEN offline migrate и failure/rollback controls. M3 — synthetic CLI→restart/domain drill, совместимость, review/evidence и operator handoff. Каждый runtime milestone — bounded commit; live перенос не входит ни в один.

## Definition of Done

- [x] AC/режимы и отказ наблюдаемы; нужные tests названы.
- [x] Merge owner rbctmz; cleanup выполняет integrator после owner-authorized merge.
- [ ] Independent spec review завершён перед кодом.
- [ ] M1–M3 runtime evidence и final native/owner acceptance.

## Evidence Bundle

M0 baseline: AST inspection `config/settings.py:116` и два temp cwd подтвердили относительный default, SQLite не открывалась. Существующий `test_sqlite_backup_restore.py`: **16 passed / 0.56s**, только tmp_path. Это проверка reuse primitive, не реализованной migration. Проверены `git diff --check`, локальные Markdown links в трёх документах и обязательные sections/checkbox placement ExecPlan. Primary checkout clean на d977618; runtime source не менялся. Native rounds 1/2, manual; review `5639434571` на `ae554b23ab`, оба P2 исправлены в spec, independent verification pending. Pure-path probe подтвердил 18 endpoint/sidecar пересечений и равенство selected target/cwd candidate; файловые/SQLite операции не выполнялись, это не GREEN будущей реализации. Broad runtime/UI suites N/A для spec-only diff. Новый конфигурационный/CLI контракт не реализован. Остаточные риски: native Windows paths/ACL, распознавание legacy schema и unsupported SQLite objects, quiescence доверяется operator.

## Review Findings

Первое независимое review: два blocking P2 на `ae554b23ab`, оба приняты и исправлены документально. Commit disposition указан в PR threads; новая runtime implementation отсутствует.

| Finding | Observed / Inferred / Verified by | Gate / status |
|---|---|---|
| P2 [4368076843](https://github.com/rbctmz/ai_trainer/pull/724#discussion_r4368076843) | Distinct endpoints могут пересекаться с будущими sidecars → snapshot окажется SQLite-owned; pure-path probe подтвердил пример `new.db` / `new.db-wal` и все 18 направленных комбинаций | Исправлено: F(p) disjoint, отказ до artifacts; M2 RED cases planned; scoped verification pending |
| P2 [4368076850](https://github.com/rbctmz/ai_trainer/pull/724#discussion_r4368076850) | Cwd=data dir даёт legacy candidate == target → ложный migration_required; pure-path подстановка Linux default подтвердила равенство и отдельность checkout candidate | Исправлено: исключить выбранную SQLite family, сохранить отказ для отдельного legacy; M1 RED cases planned; scoped verification pending |

## Native Review Rounds

| Round | Reviewed SHA | Trigger | Findings / decision |
|---|---|---|---|
| 1 | `ae554b23ab` | manual | 2 blocking P2; spec corrected, scoped verification pending; used 1/2 |

## Final Verdict

**READY FOR SCOPED SPEC VERIFICATION; NOT READY FOR IMPLEMENTATION.** Два P2 исправлены автором; independent acceptance исправлений пока не получен. Следующий role handoff: independent spec reviewer → Domain/API implementer, только после закрытия blocking findings. Human merge/live migration остаются отдельными решениями. #624/#622 не закрываются по этому docs PR.

OS references для выбора каталогов: [Apple Application Support](https://developer.apple.com/library/archive/documentation/MacOSX/Conceptual/BPFileSystem/Articles/WhereToPutFiles.html), [XDG Base Directory 0.8](https://specifications.freedesktop.org/basedir/0.8/), [Windows LocalAppData](https://learn.microsoft.com/en-us/windows/win32/shell/knownfolderid). Это обоснование выбранного layout, не выполненная cross-platform runtime-проверка.
