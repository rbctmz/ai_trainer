# SQLite backup and restore runbook

- **Статус:** Current
- **Контракт:** ADR-0002, ASR-DEP-2 / ASR-REL-3
- **Реализация:** `scripts/sqlite_backup_restore.py`

Этот runbook относится к single-athlete SQLite-хранилищу AI Trainer. Команды
создают логический снимок через стандартный SQLite Backup API, проверяют
`PRAGMA integrity_check`, записывают временный файл рядом с назначением и
публикуют его атомарной заменой. Обычное копирование только
`ai_trainer.db` не является рекомендуемым backup: committed данные могут
находиться в SQLite `-wal`.

## Обязательная граница: сервис остановлен

CLI не умеет надёжно доказать, что другой процесс не начнёт запись. Поэтому
`backup` и `restore` требуют `--confirm-stopped`. Флаг является подтверждением
оператора, а не механизмом остановки.

Перед командой остановите все процессы AI Trainer, которые используют эту БД:
FastAPI/web stack, Streamlit и ручные sync/maintenance scripts. Не запускайте
их снова, пока CLI не вернул код `0` и JSON с
`"integrity_check": "ok"`.

CLI:

- не перезаписывает существующий backup или rollback-файл;
- проверяет источник и получившийся snapshot;
- создаёт файлы с правами `0600`;
- выводит SHA-256 для operator audit;
- при restore существующего target сначала создаёт проверенный rollback;
- до замены карантинирует старые `<database>-wal`, `<database>-shm` и
  `<database>-journal`, возвращает их при fail-before-replace и удаляет
  карантин только после атомарной замены target.

Backup не шифруется. Перед переносом off-host используйте отдельное
шифрованное хранилище и не публикуйте файл: он содержит персональные показатели
здоровья и тренировок.

## Runtime path и upgrade (#624, M1)

Без `--database` CLI использует тот же выбор, что API и `Database()`:
macOS `~/Library/Application Support/ai_trainer/ai_trainer.db`; Linux
`$XDG_DATA_HOME/ai_trainer/ai_trainer.db` с fallback `~/.local/share`; Windows
`%LOCALAPPDATA%\ai_trainer\ai_trainer.db` с fallback `~/AppData/Local`.
Docker использует явный `/data/ai_trainer.db`. Непустой `DATABASE_PATH` имеет
приоритет; пустой/whitespace override — configuration error. Относительный
explicit override закрепляется как абсолютный при импорте Settings, без создания
SQLite и без сворачивания symlink-sensitive `..`. Для fresh implicit restore
application dir создаётся с 0700 после проверки backup и stopped confirmation;
target заранее не создаётся, поэтому чистый restore не требует rollback.

При implicit default найденный **отдельный** legacy main/WAL/SHM/journal в
launch cwd, checkout или primary checkout linked worktree блокирует startup
до открытия новой БД. Сам platform store с его sidecars не считается legacy
при запуске из data directory. Не выбирайте файл по mtime. После осознанного
выбора оператор может задать абсолютный `DATABASE_PATH` или `--database`;
явные offline paths остаются доступны при runtime refusal.

M1 не перемещает данные; явная команда `migrate` добавлена в M2 ниже. Существующие `backup`/`restore` ниже сохраняют stopped-service boundary.
Не удаляйте старую БД и не переключайте конфигурацию ради устранения отказа
без отдельного плана переноса. Alias real/demo отвергается до demo seeding.
Реальный перенос и остановка сервисов в рамках разработки M1 не выполнялись.

## Offline relocation (#624, M2)

`migrate` расширяет этот же CLI; Settings/default startup не импортируются.
Все пути задаются явно и абсолютно. Пример ниже — шаблон с вымышленными путями,
а не разрешение выполнить перенос личной БД.

Сначала read-only план, без остановки сервиса и без создания output файлов:

    python scripts/sqlite_backup_restore.py migrate \
      --source /absolute/legacy/ai_trainer.db \
      --target /absolute/private-data/ai_trainer.db \
      --rollback-output /absolute/private-backups/pre-migration.db

Ожидается JSON `status=planned`, `configuration_changed=false`: integrity,
counts и SHA-256 логического содержимого каждой таблицы, schema digest,
user_version/application_id/encoding. Строки данных и SQL не печатаются.
`--rollback-output` в dry-run опционален; без него путь snapshot ещё не проверен.
SQLite читается через `mode=ro`, без DDL/DML; read-lock/SHM metadata могут меняться.

После отдельного решения оператора остановить **всех** writers (API, Streamlit,
sync/CLI, другие экземпляры); flag ниже — подтверждение оператора, не детектор
процессов. Повторный apply заново проверяет source и пути:

    python scripts/sqlite_backup_restore.py migrate \
      --source /absolute/legacy/ai_trainer.db \
      --target /absolute/private-data/ai_trainer.db \
      --rollback-output /absolute/private-backups/pre-migration.db \
      --apply --confirm-stopped

Команда использует существующий SQLite Backup API: committed WAL pages входят
в rollback snapshot; target копируется из проверенного snapshot. Сравниваются
полный catalog таблиц/indexes/views/triggers, **все** сохранённые таблицы и типы
их значений, IDs, NULL/BLOB, raw JSON и дубликаты строк без PK. Новые домены не
создаются, schema/JSON не обновляются. Минимум распознавания — обычная таблица
activities с activity_id TEXT PRIMARY KEY, date, sport, duration_minutes;
пустая по строкам application DB допустима. Нужна SQLite с `PRAGMA table_list`
(3.37+); virtual/shadow или недоступные для полного чтения объекты вызывают
именованный отказ, а не частичную проверку.

Source разрешён в legacy checkout. Target и rollback — вне любого checkout,
включая resolved parent aliases. Существующие outputs, даже пустые, и их
sidecars запрещены. Проверяются symlink/inode aliases и пересечения будущих
семейств `p`, `p-wal`, `p-shm`, `p-journal`; например, target `new.db` и rollback
`new.db-wal` недопустимы. Case/Unicode ambiguity отклоняется консервативно даже
на case-sensitive FS. POSIX новые files 0600, конечные новые parent dirs 0700;
права существующих dirs не меняются. Native Windows/ACL acceptance ещё не выполнен.

Exit 0: `planned` либо `copied_not_activated`. Последнее означает **копия
проверена и опубликована, но активный путь не переключён**. Отдельно проверьте
JSON, сохраните rollback; затем оператор задаёт абсолютный `DATABASE_PATH`
на target и перезапускает сервис. `.env` команда не меняет, source не удаляет.
Synthetic CLI→restart/reset/rollback drill ниже принят в M3 #728 (merge b75d510); реальная owner activation остаётся отдельной.

Exit 2: JSON `blocked` с `reason`, например `target_exists`,
`endpoint_namespace_overlap`, `unsupported_source_schema`, `source_changed`,
`logical_verification_failed` или `relocation_io_failed`. Не удаляйте найденные
файлы ради повтора. При отказе до публикации final target отсутствует, source
и config не изменены; уже опубликованный валидный rollback сохраняется.
Удаляются только собственные temp files. При ошибке после atomic publication
(например, fsync/ответ) final файл уже может существовать: повтор не перезапишет
его и откажет `target_exists`; сохраните artifacts для отдельной проверки.

После активации **не возвращайтесь автоматически к legacy source**: новые
записи есть только в target. Откат кода сохраняет выбранный target path.
Для смены пути снова остановите writers, снимите свежий validated snapshot
текущей активной БД и используйте отдельный operator restore в проверенный путь.
Backup retention остаётся ручным до #623; source и rollback не удаляются reset.
Никакой live migration/остановки сервисов в ходе разработки M1–M3 не выполняется.

## Synthetic acceptance и operator handoff (#624, M3)

Contributor-safe lifecycle drill — `tests/smoke/test_database_relocation_drill.py`.
Он создаёт временную application DB через domain methods, переносит committed
WAL и запускает новые Python-процессы приложения с явным DATABASE_PATH. Внутри
них проверяются FastAPI lifespan/current-cycle route, план, связи провайдеров,
ручная identity, выполнение, feedback, readiness/provenance и решение коуча.
Затем идут новые записи → повторный запуск → fresh backup/restore → reset →
restore с сохранением reset-state snapshot. Старый source и operator backups
не удаляются и не становятся автоматически активными. Сбой default startup
при legacy file и CLI refusals проверяются отдельно. Узкие disk/copy/publish
faults и races — в M2 regression suite.

Это воспроизводимая synthetic acceptance, не выполнение переноса личной БД,
OS/service restart, Docker-volume drill, UI/browser check или native Windows
ACL certification. Test audit hooks не являются поставляемым runtime guard
(#625). API/схема и default правила M1/M2 не меняются.

Для реального handoff оператор отдельно выбирает source, target и rollback
**абсолютные пути**, проверяет dry-run и согласует остановку writers. После
apply сохранить JSON/проверенный rollback, отдельно задать DATABASE_PATH на
новый target и перезапустить приложение. Проверить ожидаемые записи и цикл.
Данные, добавленные после активации, восстанавливаются из свежего backup
**активного target**, а не из legacy source или pre-migration snapshot.
Retaining/удаление старых snapshots — отдельное решение до #623; никакого
автоматического fallback/retention/off-device transport здесь нет.

## Bare-metal backup

Остановите запущенный через `run_web.sh`, `run.sh`, Uvicorn или Streamlit
процесс. Затем из корня репозитория:

    mkdir -p backups
    ./ai_trainer_env/bin/python scripts/sqlite_backup_restore.py backup \
      --output "backups/ai_trainer-$(date -u +%Y%m%dT%H%M%SZ).db" \
      --confirm-stopped

Успех печатает JSON:

    {
      "action": "backup",
      "artifact": "/absolute/path/backups/ai_trainer-....db",
      "database": "/absolute/path/ai_trainer.db",
      "integrity_check": "ok",
      "sha256": "<64 hex chars>"
    }

Скопируйте `artifact` в выбранное защищённое хранилище. Не храните
единственную копию рядом с рабочей БД.

## Bare-metal restore

Оставьте сервис остановленным. Для существующего target рекомендуется явно
задать rollback вне рабочего каталога БД:

    ./ai_trainer_env/bin/python scripts/sqlite_backup_restore.py restore \
      --backup "backups/ai_trainer-20260728T120000Z.db" \
      --rollback-output "backups/pre-restore-$(date -u +%Y%m%dT%H%M%SZ).db" \
      --confirm-stopped

Если target отсутствует (чистая установка), не передавайте
`--rollback-output`: в результате будет `"rollback": null`.

При существующем target JSON содержит путь `rollback`. Не удаляйте этот файл,
пока приложение не запущено и ключевые экраны/healthcheck не проверены.

## Docker Compose backup

Backup должен выйти на host, а не остаться единственной копией в named volume:
`docker compose down -v` удаляет volume. Из корня репозитория:

    mkdir -p backups
    docker compose down
    docker compose run --rm --no-deps \
      --volume "$PWD/backups:/backup" \
      api python scripts/sqlite_backup_restore.py backup \
      --database /data/ai_trainer.db \
      --output "/backup/ai_trainer-$(date -u +%Y%m%dT%H%M%SZ).db" \
      --confirm-stopped
    docker compose up -d
    docker compose ps

`docker compose down` без `-v` сохраняет `ai_trainer_data`. One-off контейнер
монтирует тот же volume, но не запускает Uvicorn.

## Docker Compose restore or migration into the volume

Сначала положите проверенный backup в host-каталог `backups/`. Затем:

    docker compose down
    docker compose run --rm --no-deps \
      --volume "$PWD/backups:/backup" \
      api python scripts/sqlite_backup_restore.py restore \
      --database /data/ai_trainer.db \
      --backup /backup/ai_trainer-20260728T120000Z.db \
      --rollback-output /backup/pre-restore-20260728T130000Z.db \
      --confirm-stopped
    docker compose up -d
    docker compose ps

Для пустого volume уберите `--rollback-output`. Этот путь также заменяет
прежнюю миграцию через `docker compose cp`: сначала создайте CLI-backup
локальной БД, затем restore этого snapshot в `/data/ai_trainer.db`.

## Rollback после неудачного обновления

Не запускайте writers. Используйте путь `rollback` из успешного restore как
новый `--backup`, а текущее неудачное состояние сохраните в отдельный новый
rollback-файл:

    ./ai_trainer_env/bin/python scripts/sqlite_backup_restore.py restore \
      --database ai_trainer.db \
      --backup backups/pre-restore-20260728T130000Z.db \
      --rollback-output backups/failed-restore-20260728T131500Z.db \
      --confirm-stopped

Команда идемпотентна по содержимому, но намеренно не перезаписывает artifacts:
для каждого запуска выбирайте свободный output.

## Если существующий target повреждён

Restore существующего target сначала обязан создать **валидный** rollback.
Если integrity check текущей БД не проходит, CLI завершится до замены. Это
fail-closed поведение: повреждённые байты нельзя выдавать за рабочий rollback.

При аварийном восстановлении:

1. оставьте сервис остановленным;
2. сохраните рабочий `ai_trainer.db` и все существующие `-wal`, `-shm`,
   `-journal` как forensic-копию вне volume;
3. переместите эти файлы с canonical path, не удаляя forensic-копию;
4. выполните restore в теперь отсутствующий target без `--rollback-output`;
5. запускайте сервис только после `"integrity_check": "ok"`.

Ручное перемещение повреждённых файлов является осознанной аварийной операцией
и не заменяет регулярный backup. Если валидного backup нет, не очищайте volume:
сохраните его для последующей диагностики.

## Что означает ошибка

До финального atomic replace любая ошибка оставляет target неизменным, а
временный файл удаляется. Если rollback уже был создан, он сохраняется.
Если ошибка произошла **после** replace во время удаления карантина или
финальной проверки, команда явно сообщает, что target уже заменён, возвращает
ненулевой код и указывает `rollback=<path>` для существовавшего target.
Не запускайте сервис: устраните причину и восстановите названный rollback
обычной командой `restore`. Для чистого target rollback равен `none`; сохраните
новый target для диагностики и повторите restore из исходного backup после
исправления filesystem-проблемы.

Распространённые причины:

- нет `--confirm-stopped`;
- source отсутствует, является symlink или не является SQLite;
- integrity check вернул не `ok`;
- output/rollback уже существует;
- backup, target и rollback указывают на один путь;
- недостаточно места или прав в destination filesystem.

Исправьте причину и повторите команду с новым свободным artifact path. Не
удаляйте исходный backup ради повторного запуска.

Backup и rollback публикуются atomic no-clobber операцией: даже если другой
процесс создаст выбранный output во время копирования, CLI не перезапишет его.
Если выполнение было прервано после карантина sidecars и до JSON-успеха, не
запускайте приложение. Сохраните canonical DB и файлы
`.*.pre-restore-sidecar`, затем повторите restore либо верните quarantine к
исходным именам `-wal`/`-shm`/`-journal` до открытия SQLite.

## Автоматическое доказательство

Contributor-safe drill:

    python -m pytest tests/smoke/test_sqlite_backup_restore.py -q

Он использует только временные пути и проверяет integrity, canonical activity,
provider-link, planning checkpoint, HRV, сон, resting HR, rollback и
fail-before-replace. Отдельные гейты доказывают quarantine-before-replace,
восстановление sidecars при ошибке публикации, atomic no-clobber и короткую
operator error при невозможности создать destination. Реальная БД и Docker
volume не открываются.

## Защищённые acceptance и служебные команды (#625 M3)

`./run_acceptance.sh` создаёт собственную временную БД; внешние пути DB/demo
и chats отклоняются до запуска приложения. Не используйте acceptance для
работы с личной БД. E2E и standalone-тесты также используют свои временные
области. Старые генераторы данных без аргументов работают с временной БД.

Для явной работы с существующей БД сначала остановите все процессы записи и
создайте свежую проверенную копию SQLite Backup API, например:

    python scripts/sqlite_backup_restore.py backup --database /absolute/path/working.db \
      --output /absolute/path/fresh-backup.db --confirm-stopped

Пути в примере нужно заменить. Preview выполняется только для чтения:

    python scripts/backfill_activity_provider_links.py --database /absolute/path/working.db

Для записи отдельно укажите `--apply --confirm-working-database
--confirm-stopped --backup /absolute/path/fresh-backup.db`. Проверка сравнивает
содержимое и структуру БД с backup до операции; после изменения БД нужна новая
копия. Остановка writers подтверждается оператором, автоматически не проверяется.
Эти же флаги действуют для repair/backfill и генераторов, которые допускают
явную рабочую БД. Удаление всех HRV дополнительно требует отдельного флага.
Сетевой backfill выполняется только при явном apply после проверки; live browser
acceptance требует `--base-url` и `--confirm-live-acceptance`. Не передавайте
credentials в scratch-запуски.
