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

> **Граница разрушительных операций.** Каноническая формулировка — в
> `AGENTS.md`, раздел «Destructive boundary for SQLite files» (#622/#625):
> рабочая БД, её `-wal`/`-shm`/`-journal` и их snapshots не читаются, не
> создаются и не удаляются тестами, acceptance-запусками и агентской
> диагностикой. Техническая реализация — `config/db_paths.py`. Ниже описано
> только то, как эта граница проявляется при backup/restore.

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

## Bare-metal backup

Остановите запущенный через `run_web.sh`, `run.sh`, Uvicorn или Streamlit
процесс. Затем из корня репозитория:

    mkdir -p backups
    ./ai_trainer_env/bin/python scripts/sqlite_backup_restore.py backup \
      --database "${DATABASE_PATH:-ai_trainer.db}" \
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
      --database "${DATABASE_PATH:-ai_trainer.db}" \
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

## Где живёт рабочая БД (#624)

До #624 дефолт был `ai_trainer.db` относительно текущего каталога, поэтому в
dogfood-checkout рабочая база лежала рядом с исходниками и делила с ними судьбу.
Теперь приоритет такой:

1. явный `DATABASE_PATH` (в `.env` или окружении) — всегда выигрывает;
2. платформенный application-data directory;
3. прежнее bare-имя `ai_trainer.db` — только если домашний каталог не определён.

| Платформа | Каталог по умолчанию |
|---|---|
| macOS | `~/Library/Application Support/ai_trainer/ai_trainer.db` |
| Linux | `$XDG_DATA_HOME/ai_trainer/ai_trainer.db` или `~/.local/share/ai_trainer/ai_trainer.db` |
| Windows | `%LOCALAPPDATA%\ai_trainer\ai_trainer.db` |
| Docker | без изменений — образ задаёт `DATABASE_PATH=/data/ai_trainer.db` |

`AI_TRAINER_APP_DATA` переопределяет каталог на всех платформах (используется
тестами и acceptance-запусками).

### Перенос существующей рабочей БД из checkout

Если `.env` (или окружение) уже указывает на БД внутри рабочего дерева,
приложение продолжит использовать именно её. Перенос — одна явная команда; она
**никогда** не удаляет и не изменяет источник:

```bash
# 1. Отчёт по агрегатам, ничего не пишет
python scripts/migrate_database_out_of_checkout.py --dry-run

# 2. Остановите все процессы AI Trainer, затем:
python scripts/migrate_database_out_of_checkout.py --confirm-stopped
```

Команда:

- читает источник через validated snapshot primitives #293 (SQLite Backup API),
  поэтому committed страницы `-wal` переносятся — обычный `cp` их теряет;
- сначала публикует pre-migration snapshot `<target>.pre-migration-<UTC>.db`;
- отказывается работать, если source и target совпадают, target — symlink на
  source, target уже содержит данные, source не проходит `integrity_check` или
  не содержит строк в ключевых доменах;
- сверяет после переноса ключевые домены (activities, provider links,
  checkpoints, coach decisions, plan/actual matches, feedback, readiness) и
  сообщает о нехватке строк вместо «успеха»;
- оставляет исходную БД на месте: удалять её нужно вручную и только после
  проверки, что приложение работает на новом пути.

Если `.env` закреплял старый путь, обновите и его (предыдущая версия файла
сохраняется рядом с timestamped-суффиксом):

```bash
python scripts/migrate_database_out_of_checkout.py --confirm-stopped --update-env .env
```

Автоматическое доказательство:
`python -m pytest tests/smoke/test_database_relocation.py -q` — перенос committed
WAL-страниц, отказ при неоднозначном и симлинковом target, сохранность источника
и rollback при инъецированном отказе, отсутствие персональных строк в dry-run.

## Автоматические validated snapshots (#623)

Ручной CLI выше остаётся аварийным инструментом. Штатная защита — автоматические
snapshots рядом с рабочей БД (вне Git checkout), в `<каталог БД>/snapshots/`
(`AI_TRAINER_SNAPSHOT_DIR` переопределяет каталог).

Политика:

| Триггер | Когда срабатывает |
|---|---|
| `post-sync` | после успешного provider sync (`data_durability` в ответе job) |
| `post-mutation` | после durable high-value мутаций, с coalescing-окном (по умолчанию 30 минут) |
| `scheduled-daily` | раз в сутки, если логическая generation изменилась |

Каждый snapshot создаётся только когда generation БД изменилась, поэтому повторный
sync без изменений не увеличивает набор backup'ов. Generation — это отпечаток
размера/mtime основной БД и `-wal` плюс счётчики ключевых доменов (никаких
персональных строк).

Snapshot и manifest:

- создаются теми же validated primitives #293 (SQLite Backup API, atomic publish,
  `PRAGMA integrity_check`), поэтому committed `-wal` страницы попадают внутрь;
- manifest содержит schema version, размер, sha256, оба timestamp, source
  generation, integrity и покрытие ключевых доменов — и **никаких** значений строк;
- retention: 14 дневных и 8 недельных валидированных версий; последняя валидная
  дневная и недельная версия не удаляются никогда; артефакты без manifest или с
  несовпавшим размером не считаются restore candidate и вычищаются.

Отказ backup виден и ничего не откатывает:

- сбой публикации не удаляет уже сохранённые provider/user данные;
- предыдущий валидный snapshot и исходная БД остаются restoreable (отдельные
  тесты на disk-full, permission denied, прерванную запись и corrupt snapshot);
- статус попадает в `data_durability` ответа sync job и в `health` ниже.

```bash
# снять snapshot вручную (например из cron вместо daily-триггера)
python -m services.durability snapshot

# состояние backup: healthy / partial / degraded / failed
python -m services.durability health
```

`degraded` означает, что последний валидный snapshot старше RPO-цели (24 часа),
`failed` — что доверенного snapshot'а нет вовсе, `partial` — что рядом лежат
недоверенные артефакты. Любой из этих статусов — повод разобраться, а не
игнорировать: успешный sync больше не маскирует проблемы backup.

## Границы этого трека

Автоматические snapshots (#623) защищают от потери каталога, ошибочного удаления
файла и порчи базы, но **не** от потери диска: копия живёт на том же устройстве.
Внешняя (off-device) зашифрованная копия и регулярный restore drill сознательно
**вне объёма** этой работы — по решению владельца от 2026-09-20, без облачных
аккаунтов и платных сервисов. Пока её нет, единственная защита от потери
устройства — перенос snapshot вручную на отдельный носитель.

Что это означает практически: если диск потерян, восстановить можно только те
snapshots, которые успели скопировать вне устройства. Поэтому периодический
ручной экспорт каталога snapshots на внешний носитель остаётся ответственностью
владельца, и он не автоматизирован.

## Автоматическое доказательство

Contributor-safe drill:

    python -m pytest tests/smoke/test_sqlite_backup_restore.py -q

Он использует только временные пути и проверяет integrity, canonical activity,
provider-link, planning checkpoint, HRV, сон, resting HR, rollback и
fail-before-replace. Отдельные гейты доказывают quarantine-before-replace,
восстановление sidecars при ошибке публикации, atomic no-clobber и короткую
operator error при невозможности создать destination. Реальная БД и Docker
volume не открываются.
