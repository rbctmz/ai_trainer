# #623 M1 — автоматические локальные снимки SQLite

Статус: проект спецификации, runtime ещё не реализован. Владелец merge — Greg;
автор M1 — Spec/Architecture Owner; independent reviewer назначается отдельным
запросом. Change Class A: автоматическая запись и удаление backup artifacts,
новый operational state. Review manual, 0/2 раундов. Parent #622; #624/#625 merged.

## Результат и граница

При включённом backup сохранение важных данных заканчивается проверенным
локальным снимком либо явным сообщением «Данные сохранены, резервная копия не
обновлена». Пользователь может увидеть время последней проверенной копии и
восстановить её существующим operator restore. Ошибка backup не отменяет commit.
Это локальная защита: потеря устройства, encryption и off-device — #626.
M1 поставляет только контракт, план и synthetic characterization.

Минимальная реализация — один общий сервис, SQLite Backup API, каталог
неизменяемых снимков и небольшой файл состояния. Без очереди заданий, нового
backup engine, таблицы для каждой бизнес-операции, универсального event bus и
сервера планировщика. Raw SQL/сторонние writers не получают автоматических
хуков: они покрываются ближайшей периодической проверкой или ручным backup.

## Когда делать снимок

1. После завершения provider sync, включая partial/failed sync, если часть
   данных могла сохраниться. Один вызов после всех его записей и audit decision;
   не после каждой полученной активности. Нет изменений — нет новой версии.
2. После commit подтверждённого изменения плана/цикла, решения коуча, plan/actual
   match, feedback (включая correction/tombstone) и readiness evidence. Вызов
   на общей границе операции, используемой web и Streamlit; вложенные записи
   объединяются в один вызов внешней операции. Preview/read не запускает backup.
3. При старте приложения и далее раз в 60 секунд проверять наступление нового
   UTC-дня. Первый запуск в новом дне сверяет содержимое с последним снимком.
   Если приложение было выключено, проверка выполняется при следующем запуске;
   фоновой гарантии при выключенном приложении нет. После ошибки — одна попытка
   не чаще раза в 60 секунд; следующие операции видят degraded до успешной проверки.

Для важных операций нет отложенного окна: вызов snapshot идёт после commit,
до окончательного ответа; coalescing между отдельными командами = 0 секунд.
Ограничение частоты обеспечивают объединение вложенных записей и удаление
неизменившегося кандидата, а не потеря важных изменений в таймере. Пользователь
получает результат backup вместе с результатом сохранения. Периодическая
проверка низкоценных/внешних записей даёт до 24 часов + 60 секунд до попытки,
только пока приложение работает и backup исправен.

Падение между commit и snapshot возможно: atomic commit бизнес-данных и
backup на другом файле не обещается. До окончания операции покрытие этой
записи не подтверждено. При рестарте сравнение выполняется заново без зависимости
от потерянного memory flag. Ошибки/выключение/недоступный диск отменяют обещание
ограниченного RPO; статус явно degraded/unknown. RPO здесь — сколько последних
изменений может отсутствовать в последней проверенной копии. Ни «нулевой RPO
при любом падении», ни RPO потери машины из #622 этим срезом не заявляются.

## Что считать изменением

Готовый temporary snapshot проверяется и получает детерминированный логический
отпечаток: схема, SQLite schema version и типизированное содержимое всех таблиц.
Переиспользовать `inspect_relocation_database` с теми же отказами для неизвестных
schema objects; digest считается из канонического JSON его результата. Это
`source_generation`, а не wall clock, `mtime`, число строк или hash main-файла.
Сравнивать snapshot с последним проверенным snapshot того же source namespace,
не с движущейся source-БД. Простая первоначальная стратегия делает temp backup
даже при неизменившейся БД; одинаковый digest удаляет только этот свой temp и
обновляет время проверки. Нового опубликованного snapshot нет.

Нет source generation counter, per-table triggers или новой таблицы в source.
Цена полного копирования/проверки измеряется в M2; если не укладывается в бюджет,
M2 возвращает измерение в spec, а не вводит скрыто CDC/очередь.

## Snapshot, идентичность и публикация

`AUTO_BACKUP_ENABLED=false` по умолчанию для управляемого первого включения;
disabled виден как отдельное состояние. Включение на личной БД — отдельное
решение владельца после synthetic приёмки. `BACKUP_DIR` опционален, абсолютный;
default — platform application-data directory ai_trainer/backups, независимо
от явно заданного DATABASE_PATH. Ни default, ни explicit backup path внутри
любого checkout не разрешён. Demo/acceptance никогда не включает backup
реальной БД; synthetic acceptance выбирает собственный explicit каталог.

Namespace — SHA-256 канонического абсолютного выбранного source path с native
path identity. Путь не выводится в API/manifest; alias должен получать тот же
namespace, неизвестная identity отказывает. Замена содержимого/restore по тому
же пути продолжает историю этого выбранного store; его поколения всё равно
проверяются по содержимому. Перенос пути начинает новый namespace, старые копии
сохраняются; переназначать их молча нельзя. Один backup root — один владелец
OS-пользователь, private dirs 0700/files 0600 где поддержано. Hardlink/symlink
и пересечение SQLite families source/output/checkout отклоняются по #625.

Одна advisory OS-блокировка на namespace защищает snapshot + retention; при
падении освобождается OS. Lockfile TTL, удаление «зависшего» файла и ожидание
бесконечно запрещены. Конкурентный caller ждёт в пределах общего deadline,
затем получает `backup_busy`/degraded; никакого тихого пропуска. На неподдержанной
платформе отказ, без заявления успешного backup. Обычные DB writers этот lock
не держат; online consistency доказывается в M2. Существующий stopped-service
CLI backup/restore/migrate сохраняет свой контракт: нельзя обходить его флагом
`confirm_stopped=True` в автоматическом режиме.

Порядок: source read-only → SQLite Backup API в собственный temp → закрытие
connections → integrity_check + logical fingerprint + SHA-256 snapshot →
fsync → atomic no-clobber публикация каталога snapshot с manifest → fsync parent.
Snapshot DB и manifest публикуются одним rename собственного temp-каталога,
так что пара не разделяется. Manifest version 1: snapshot_id, source_namespace,
source_generation, created_at_utc, SQLite user/schema version, size, sha256,
integrity result, table row counts/digests. Никаких персональных строк/payload.
Неизвестные manifest versions/invalid digests не являются restore candidates.
До публикации любой отказ сохраняет source и предыдущую копию. После публикации
сбой записи state не удаляет валидный snapshot: restart восстанавливает состояние
по проверенным manifests. Частичный каталог не становится кандидатом.

Общий deadline одной попытки — 10 секунд, включая lock/copy/check/hash; проверки
должны уметь прерываться между порциями работы. Busy/retry не бесконечны.
Превышение времени — degraded, свой temp очищается. Это лимит будущей реализации,
не результат проверки размера реальной БД. В web операция не блокирует event
loop; использовать существующий execution context либо threadpool.

## Состояние и сообщение пользователю

Общий `BackupStatus`: state = disabled / unknown / ready / degraded,
last_checked_at, last_snapshot_at, last_snapshot_id, reason_code. `ready` означает
последнюю успешную проверку на указанное время, не доказательство отсутствия
более поздних изменений. Минимальные причины: backup_busy, backup_timeout,
backup_io_error, backup_integrity_failed, backup_identity_unknown,
backup_state_unwritable. Не возвращать raw exception/путь/SQL в ответ.

Один атомарно заменяемый `status.json` вне source DB хранит последнюю проверку
и ошибку; это не очередь. При сбое записи status нельзя показывать stale ready:
текущий ответ degraded, startup перепроверяет каталог. Ошибки event backup не
меняют `saved=true`, но возвращают backup status/warning. Для sync его данные
остаются сохранёнными, итог становится partial со стабильным warning
`backup_failed`; исходная provider-ошибка не затирается. Последующее чтение
operational state показывает предупреждение до успешной проверки. Проверенный
snapshot и ошибка retention различаются: копия может быть готова, а maintenance
сообщает отдельный warning, не объявляя её потерянной.

API M3: GET `/api/backup/status` возвращает BackupStatus; POST
`/api/backup/check` с пустым телом выполняет bounded retry backup, без бизнес-
записи и без произвольного database path в запросе; demo получает disabled.
Добавить типизированный `backup` в общий operational envelope и ответы
защищаемых mutation; точный inventory routes и mirrors в web/lib/types.ts,
registry/extractor входит в M3 перед кодом. UI использует существующий warning
pattern с временем копии и действием «Повторить проверку резервной копии».
Это действие делает тот же bounded check, не повторяет бизнес-команду.
Web — основной интерфейс; Streamlit через общий сервис показывает тот же статус.
Оба endpoint и envelope проверяются контрактными тестами M3.

## Retention, reset и restore

После новой валидной публикации оставлять последний снимок каждого из последних
14 непустых UTC-дней и последних 8 непустых ISO-недель; объединение наборов,
плюс последний валидный snapshot безусловно. Промежуточные версии в одном
дне/неделе могут удаляться лишь после проверки нового кандидата. Если изменений
в день не было, новую физическую копию ради календарной даты не создавать:
последняя валидная копия остаётся защищённой. Удалять только каталоги текущего
namespace с распознанным manifest; manual backups/rollback и чужие файлы
никогда не участвуют. Ошибка проверки текущего каталога останавливает pruning;
corrupt artifacts не кандидаты и не замена последней копии, автоматически не
удаляются. Ошибка удаления даёт warning, следующий запуск повторяем.

Полный product reset очищает source данные, но backup history намеренно сохраняет
до-reset копии и публикует новое поколение после успешной очистки. Его warning
при сбое видим. Изолированные demo/test reset удаляют только свои artifacts.
Удаление всей истории — только отдельная явная operator процедура с preview,
не кнопка очистки кэша. Restore остаётся stopped-service CLI из runbook; оператор
выбирает валидный снимок, проверяет hash/integrity, извлекает DB в private temp,
использует существующий restore с rollback и после запуска выполняет check.
Выкатка кода назад оставляет копии и не подменяет source. Копии при schema upgrade
не удаляются до подтверждённого нового snapshot; автоматического downgrade нет.

## Приёмка: будущие RED → GREEN

| Наблюдаемый критерий | Проверка M2–M4 |
| --- | --- |
| Commit sync/важной операции → snapshot либо видимое degraded | реальные shared writer + API/Streamlit consumer, сбой после commit не теряет source |
| Нет изменений → нет новой опубликованной версии | repeated request, VACUUM без изменения rows, JSON generation stable |
| Важная операция завершена, process killed, restart | последний подтверждённый snapshot восстанавливает её; kill в commit/copy gap не выдаётся за покрытую запись, startup догоняет |
| WAL + concurrent writer | последовательности транзакций, согласованные инварианты snapshot; reader/writer не зависают за deadline |
| Copy/verify/hash/manifest/publish/state failure | ENOSPC, permission, corruption, subprocess kill на каждой границе; source и предыдущая валидная копия целы |
| New UTC day/offline/retry | fake clock: unchanged no publish, changed snapshot, restart после пропущенных дней, failed попытки ≤1/60s |
| Concurrent runtimes | два процесса одного namespace: сериализация, deadline и OS release после kill, никаких duplicate/pruning races |
| Retention и reset | fake dates 14d/8w, pinned latest, unchanged days, corrupt/unknown/foreign entries preserved; reset не теряет pre-reset backup |
| Restore | существующий #624 lifecycle drill с checkpoint/coach/match/feedback/readiness из auto snapshot |
| Безопасность/совместимость | #625 suite, foreign path до open, no secrets/rows/paths, обычный product DB и manual CLI работают |

M1 characterization: synthetic online Backup API с активным writer дала
integrity=ok, парный invariant сохранён, digest после VACUUM неизменен.
Это не GREEN автоматического сервиса: kill/fault/deadline/retention пока NOT RUN.

## Реализация и review

M2: один общий snapshot primitive + namespace lock, fingerprint, публикация и
failure tests; reuse helpers в scripts/sqlite_backup_restore.py через shared
service boundary без второго engine. M3: триггеры операций и lifecycle timer,
status + API/contracts/web warning; M4: retention/restore drill и общая приёмка.
Включение для пользователя допускается только после M4. Первый содержательный PR каждой границы имеет evidence и independent review;
M1 docs-only не разрешает runtime или включение на личной БД. Merge — Greg.

ASR-REL-3 / ASR-DEP-2 / ASR-SEC-1; ADR-0001 web-primary, ADR-0002 SQLite,
ADR-0007 isolated acceptance переиспользуются. Нового ADR/новых dependencies
пока не нужно; если M2 докажет необходимость — явный возврат к спецификации.
