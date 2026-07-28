# Закрыть TD-001: проверяемый backup/restore SQLite

Этот ExecPlan является живым документом. Секции `Progress`, `Surprises &
Discoveries`, `Decision Log` и `Outcomes & Retrospective` поддерживаются в
актуальном состоянии по мере выполнения.

План ведётся в соответствии с `.agent/PLANS.md`. Он самодостаточен: новый
исполнитель должен суметь продолжить работу, имея только текущее дерево
репозитория и этот файл.

## Purpose / Big Picture

После изменения владелец self-hosted AI Trainer сможет остановить API, одной
командой создать проверенный снимок SQLite вне named volume и одной командой
восстановить этот снимок в пустую либо существующую БД. Восстановление
существующей БД сначала создаёт отдельный проверенный rollback-снимок и сообщает
его путь. Команда никогда не публикует частично скопированный файл: снимок
сначала создаётся и проверяется во временном файле рядом с назначением, затем
атомарно заменяет назначение.

Наблюдаемое доказательство — contributor-safe restore drill. Он создаёт
временную БД через настоящий `data.database.Database`, сохраняет каноническую
активность с provider-link, planning checkpoint и wellness, делает backup,
восстанавливает его в отсутствующий файл и читает те же данные из
восстановленной БД. Никакие реальные provider credentials, сеть, Docker volume
или пользовательский `ai_trainer.db` не используются.

## Progress

- [x] (2026-07-28 16:20+03) Подтверждены ADR-0002, ASR-DEP-2/REL-3, Compose
  volume `/data`, отсутствие backup/restore automation и smoke baseline
  `1269 passed, 1 skipped`.
- [x] (2026-07-28 16:23+03) Создан owner-issue #293 с acceptance-критериями и
  baseline.
- [x] (2026-07-28 16:30+03) Зафиксирован offline CLI/rollback/atomic replace
  контракт в этом плане.
- [x] (2026-07-28 16:38+03) Написаны RED-гейты CLI, fail-closed веток и
  полного restore drill; подтверждён RED:
  `ModuleNotFoundError: scripts.sqlite_backup_restore`.
- [x] (2026-07-28 16:49+03) Реализован stdlib-only
  `scripts/sqlite_backup_restore.py`; 10 RED-гейтов переведены в GREEN,
  `ruff check` проходит.
- [x] (2026-07-28 17:08+03) Написана операционная инструкция и обновлены
  README, ADR-0002,
  ASR-каталог и реестр долга.
- [ ] Выполнить self-review, targeted и полный contributor-safe прогон.
- [ ] Запушить ветку, открыть PR с `Closes #293` и дождаться зелёных
  merge-гейтов.

## Surprises & Discoveries

- Observation: текущая README-инструкция переноса БД использует `cp` и
  `docker compose cp`, но SQLite может иметь committed страницы в `-wal`.
  Evidence: ADR-0002 называет backup простой копией, однако TD-001 специально
  требует проверяемое восстановление; в дереве нет checkpoint/backup utility.

- Observation: проверка «сервис действительно остановлен» ненадёжна на уровне
  переносимого файлового CLI.
  Evidence: SQLite Backup API может читать согласованный снимок и при открытом
  читателе, а файловый lock не доказывает отсутствие будущих записей. Поэтому
  CLI требует осознанное подтверждение оператора и документация задаёт точную
  stop/start последовательность.

- Observation: повторное открытие текущей БД через `Database` запускает
  migrate-on-read repair TSS, поэтому это не является побайтово read-only
  проверкой backup.
  Evidence: исходная активность до повторного `Database(...)` имела
  `tss=64, tss_method=power_np`, а migrate-on-read пересчитал её в
  `tss=72, tss_method=heuristic_duration_bike`. Restore drill поэтому отдельно
  сравнивает raw canonical row до открытия и затем проверяет доступность всех
  доменов через публичные `Database` readers. Поведение TSS не меняется этим
  треком.

- Observation: ошибка filesystem после успешного `os.replace` отличается от
  fail-before-replace и требует отдельной операторской семантики.
  Evidence: удаление stale sidecars и финальный integrity check происходят
  после атомарной публикации. CLI теперь преобразует такой `OSError` в короткую
  ошибку «database was replaced», требует оставить сервис остановленным и
  называет заранее созданный rollback; отдельный smoke-гейт фиксирует границу.

## Decision Log

- Decision: не менять ADR-0002 и не добавлять Postgres, Alembic либо новый
  storage service.
  Rationale: TD-001 — operational hardening действующей single-athlete SQLite
  архитектуры; смена primary store является отдельным архитектурным решением.
  Date/Author: 2026-07-28 / Codex.

- Decision: создавать логический снимок через
  `sqlite3.Connection.backup`, а не `shutil.copy` главного файла.
  Rationale: Backup API включает видимые committed страницы независимо от
  journal mode и не зависит от того, остались ли данные в `-wal`. Решение
  stdlib-only и доступно в поддерживаемом Python 3.10+.
  Date/Author: 2026-07-28 / Codex.

- Decision: `backup` и `restore` требуют флаг `--confirm-stopped`.
  Rationale: восстановление поверх работающего процесса опасно, а переносимый
  CLI не может доказать остановку всех writers. Явное подтверждение превращает
  это в проверяемый operator contract и исключает случайный запуск.
  Date/Author: 2026-07-28 / Codex.

- Decision: назначение сначала материализуется во временном файле в том же
  каталоге, проходит `PRAGMA integrity_check`, синхронизируется на диск и только
  затем публикуется через `os.replace`.
  Rationale: один filesystem делает replace атомарным; потребитель не увидит
  полуфайл. Временный файл всегда удаляется при ошибке.
  Date/Author: 2026-07-28 / Codex.

- Decision: restore существующей БД fail-closed создаёт проверенный
  pre-restore snapshot до замены и не позволяет перезаписать существующий
  rollback artifact.
  Rationale: если текущую БД нельзя прочитать и сохранить, безопасной обратной
  операции нет; лучше остановить restore до мутации. Путь rollback возвращается
  в JSON и используется обычной командой `restore`.
  Date/Author: 2026-07-28 / Codex.

- Decision: backup-файлы получают mode `0600`, а CLI печатает SHA-256 и
  результат integrity check.
  Rationale: файл содержит персональные health/training данные; минимальные
  права и digest дают безопасный локальный audit trail без дополнительной
  зависимости или manifest-формата.
  Date/Author: 2026-07-28 / Codex.

## Outcomes & Retrospective

Пока не завершено. При закрытии здесь будут записаны итоговые команды,
количество тестов, merge evidence и оставшиеся границы. В частности,
шифрование off-host backup и расписание retention не входят в TD-001 и не
должны объявляться реализованными.

## Context and Orientation

`data/database.py` содержит схему и публичный класс `Database`. Его конструктор
принимает путь к SQLite-файлу и идемпотентно инициализирует/дополняет схему.
Канонические активности лежат в `activities`, происхождение — в
`activity_provider_links`, версии плана — в `planning_checkpoints`, wellness —
в `hrv_data`, `sleep_data` и `daily_health`.

`config/settings.py` задаёт `DATABASE_PATH`, по умолчанию `ai_trainer.db`.
`docker-compose.yml` переопределяет его на `/data/ai_trainer.db` и монтирует
named volume `ai_trainer_data:/data`. Обычный `docker compose down` сохраняет
volume; `down -v` его удаляет.

`docs/architecture/adr_0002_sqlite_primary_store.md` фиксирует SQLite как
single-athlete primary store. `docs/architecture/asr_catalog.md` оставляет
ASR-DEP-2 жёлтым именно из-за отсутствия автоматизации backup/restore.
`docs/technical_debt_register.md` содержит TD-001 и его критерий закрытия.

Новый `scripts/sqlite_backup_restore.py` является operator CLI и импортируемым
модулем для тестов. Он не импортирует `Settings`, чтобы проверка/восстановление
не зависели от unrelated provider-конфигурации; default path читается напрямую
из `DATABASE_PATH` либо равен `ai_trainer.db`.

Под «snapshot» здесь понимается новый самостоятельный SQLite-файл, в который
Backup API скопировал логическое committed-состояние исходной БД. Под
«rollback snapshot» понимается такой же снимок существующего target,
создаваемый до restore. Это не append-only rollback бизнес-плана из ADR-0006.

## Plan of Work

Сначала создать `tests/smoke/test_sqlite_backup_restore.py`. Тесты должны
импортировать функции и `main` из `scripts.sqlite_backup_restore`, использовать
только `tmp_path` и доказать RED до появления модуля. Набор фиксирует:
обязательное подтверждение остановки, отказ перезаписывать backup, отказ на
битом SQLite, неизменность target при невалидном restore и ошибке финального
replace, создание rollback snapshot, удаление старых `-wal`/`-shm`/`-journal`,
JSON-результат CLI и полный доменный restore drill.

Затем реализовать `scripts/sqlite_backup_restore.py` на стандартной библиотеке.
Публичные интерфейсы перечислены ниже. Внутренний helper открывает исходную БД
read-only, выполняет `PRAGMA integrity_check`, копирует её через
`Connection.backup` во временный файл, снова проверяет результат, делает
`fsync`, а затем атомарно публикует. Все исключения преобразуются в короткий
`SQLiteBackupRestoreError`; `main` возвращает код 2 и пишет сообщение в stderr,
не traceback.

Restore сначала полностью материализует backup во временный файл target
directory. Если target существует, до его замены создаётся отдельный rollback
snapshot тем же проверенным механизмом. После атомарной замены удаляются старые
sidecar-файлы `<database>-wal`, `<database>-shm` и `<database>-journal`, затем
target снова проходит integrity check. Путь rollback никогда не совпадает с
backup/target и не перезаписывается.

После GREEN добавить `docs/sqlite_backup_restore.md` с bare-metal и Compose
runbook. Docker backup должен монтировать host-каталог `/backup`, чтобы
единственная копия не жила в volume, который удаляет `down -v`. README получает
ссылку на runbook вместо небезопасного `cp` как рекомендуемого backup.

В `docs/architecture/adr_0002_sqlite_primary_store.md` обновить следствие
«скрипты — долг» на фактический offline CLI. В
`docs/architecture/asr_catalog.md` перевести ASR-DEP-2 в зелёный только после
restore drill и добавить evidence теста. ASR-REL-3 получает ссылку на
fail-before-replace/rollback гейты. В `docs/technical_debt_register.md` удалить
TD-001 из открытой сводки и подробных открытых пунктов, а в журнал добавить
TD-001, дату, issue #293 и проверяемый результат. TD-ID не переиспользуется.

## Concrete Steps

Рабочий каталог:

    /private/tmp/ai-trainer-td001

RED:

    /Users/gregkisel/Developer/ai_trainer/ai_trainer_env/bin/python \
      -m pytest tests/smoke/test_sqlite_backup_restore.py -q

Ожидается ошибка импорта `scripts.sqlite_backup_restore` либо поведенческие
assertion failures до реализации. После GREEN эта же команда должна завершиться
нулевым кодом.

Ручной bare-metal smoke на временных путях:

    python scripts/sqlite_backup_restore.py backup \
      --database /tmp/source.db \
      --output /tmp/source.backup.db \
      --confirm-stopped
    python scripts/sqlite_backup_restore.py restore \
      --database /tmp/restored.db \
      --backup /tmp/source.backup.db \
      --confirm-stopped

Обе команды печатают один JSON object с `action`, абсолютными путями,
`integrity_check: "ok"` и `sha256`. Restore в отсутствующий target возвращает
`rollback: null`; restore в существующий target возвращает путь валидного
rollback snapshot.

После реализации:

    python -m pytest tests/smoke/test_sqlite_backup_restore.py \
      tests/smoke/test_deployment_config.py -q
    python -m pytest tests/smoke -q
    python -m pytest -m "not live and not debug" tests/

Перед публикацией:

    git diff --check
    git status --short

Scope должен содержать только CLI, smoke tests, ExecPlan/runbook и связанные
README/ADR/ASR/debt-register правки.

## Validation and Acceptance

Happy path считается доказанным, когда restore drill создаёт source, backup и
отсутствующий target, а затем:

- `PRAGMA integrity_check` target возвращает ровно `ok`;
- `Database.get_activities_by_ids` возвращает исходную каноническую активность;
- SQL-чтение `activity_provider_links` возвращает связь этой активности;
- `Database.get_latest_planning_checkpoint` возвращает исходную цель/план;
- `Database.get_hrv_data`, `get_sleep_data` и `get_daily_health` возвращают
  исходные значения и provenance.

Existing-target path считается доказанным, когда restore заменяет target
содержимым backup, возвращённый rollback snapshot проходит integrity check и
содержит прежний marker target. Повторный restore с явно указанным новым
rollback path работает; существующий output или rollback path не
перезаписывается.

Fail-closed path считается доказанным, когда отсутствие
`--confirm-stopped`, malformed SQLite, одинаковые source/destination и ошибка
финального replace завершаются ненулевым результатом без изменения target.

CI acceptance — contributor-safe suite зелёный, PR связан с #293, а merge gate
показывает clean/ready-to-merge. Только после этого TD-001 считается закрытым.

## Idempotence and Recovery

Backup никогда не перезаписывает существующий output. Для нового запуска нужно
выбрать новый путь либо осознанно удалить старый artifact вручную после
проверки retention.

Restore можно повторить с тем же backup, но каждый запуск поверх существующего
target требует нового свободного rollback path. Если приложение после restore
не запускается, оставить сервис остановленным и выполнить `restore`, указав
возвращённый pre-restore snapshot как `--backup`; это создаёт ещё один rollback
текущего состояния и возвращает прежнюю БД атомарно.

При ошибке до `os.replace` target не меняется, временный файл удаляется.
Rollback snapshot, уже созданный перед ошибкой replace, сохраняется как
доказательство и безопасная обратная точка. CLI не удаляет operator backup.

При ошибке финализации после `os.replace` CLI сообщает, что target уже заменён,
и называет pre-restore rollback. Сервис остаётся остановленным; оператор
устраняет filesystem-проблему и выполняет обычный restore из rollback.

Если restore завершился успешно, старые sidecars удалены и не должны
копироваться обратно. Запуск API разрешён только после успешного JSON-результата
и integrity check.

## Artifacts and Notes

Owner-issue:

    https://github.com/rbctmz/ai_trainer/issues/293

Baseline:

    1269 passed, 1 skipped, 3 warnings in 47.72s

Ожидаемый сокращённый backup report:

    {
      "action": "backup",
      "integrity_check": "ok",
      "sha256": "<64 hex chars>"
    }

Ожидаемый сокращённый restore report:

    {
      "action": "restore",
      "integrity_check": "ok",
      "rollback": "/path/to/ai_trainer.db.pre-restore-<UTC>.db"
    }

## Interfaces and Dependencies

В `scripts/sqlite_backup_restore.py` определить:

    class SQLiteBackupRestoreError(RuntimeError): ...

    @dataclass(frozen=True)
    class BackupReport:
        action: str
        database: str
        artifact: str
        integrity_check: str
        sha256: str

    @dataclass(frozen=True)
    class RestoreReport:
        action: str
        database: str
        artifact: str
        integrity_check: str
        sha256: str
        rollback: str | None

    def check_sqlite_database(path: str | Path) -> str: ...

    def backup_database(
        database: str | Path,
        output: str | Path,
        *,
        confirm_stopped: bool,
    ) -> BackupReport: ...

    def restore_database(
        backup: str | Path,
        database: str | Path,
        *,
        confirm_stopped: bool,
        rollback_output: str | Path | None = None,
    ) -> RestoreReport: ...

    def build_parser() -> argparse.ArgumentParser: ...

    def main(argv: Sequence[str] | None = None) -> int: ...

Не добавлять third-party dependencies. Не импортировать `Database` в
production CLI: проверка общего SQLite-файла не должна запускать migrate-on-read.
`Database` используется только restore drill тестом для domain-level
доказательства.

## Revision Note

2026-07-28: создан первоначальный самодостаточный план после аудита ADR-0002,
Compose volume, ASR и существующих smoke-паттернов. Решения зафиксированы до
написания RED-тестов, потому что restore является destructive operator flow и
не должен эволюционировать из случайного implementation detail.

2026-07-28: после GREEN добавлено обнаружение о migrate-on-read TSS. Acceptance
разделён на точное raw-сравнение SQLite snapshot и последующее domain-read
доказательство, чтобы backup/restore не маскировал и не переопределял
существующую миграционную семантику `Database`.
