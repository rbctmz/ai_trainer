# Облачный бэкап v1 — #626, спецификация M1 #752

Дата: 2026-11-14. Статус: **предложение, рабочее включение не разрешено**.
Автор: Spec / Architecture Owner; checker: независимый read-only;
merge owner и владелец рабочих ключей: Greg.
План: [cloud_backup_execplan.md](cloud_backup_execplan.md).

## Change Class и результат для пользователя

Class A: передача персональных данных, секреты и восстановление после потери
устройства. M1 меняет только документы. После реализации пользователь продолжает
запускать один тренер на Mac; проверенные локальные снимки дополнительно
сохраняются зашифрованными в выбранном Cloud.ru STANDARD-бакете.
Показываются отдельно локальная копия, подтверждённая облачная копия и её давность.
Нет второй папки приложения, VM, нового backup engine, собственной криптографии,
multi-cloud, очереди заданий или автоматического восстановления поверх рабочей БД.

## Что уже доказано

14.11.2026 restic 0.19.1 и AWS CLI 2.40.3 arm64 выполнили настоящий Cloud.ru
round-trip на маленькой искусственной SQLite: 3 activities / 2 таблицы.
Snapshot и экспериментальный manifest после no-cache restore совпали по SHA-256;
schema/typed rows/integrity и штатный operator restore прошли. Неверный пароль
дал exit 12. Шесть объектов / 11 301 байт имели STANDARD; после проверки удалены
ровно эти объекты. Restore занял 1.651 с, весь эксперимент 16.142 с.
[Публичное evidence](https://github.com/rbctmz/ai_trainer/issues/626#issuecomment-6879508968).
Это characterization транспорта, **не RED продукта, не full-domain drill,
не доказательство RTO для личной БД**. Private evidence/секреты в PR не входят.

## Минимальный контракт отправки

Один внешне установленный restic 0.19.1 (проверенный baseline) выполняет encryption
и S3 transport; Python не реализует шифрование. Endpoint `https://s3.cloud.ru`,
region `ru-central-1`, path-style, явный `s3.storage-class=STANDARD`; TLS validation
не отключается. Рабочий repository создаётся один раз отдельным operator init.
Config привязывает конкретные repository URL/ID к source_namespace выбранной БД.
Missing/wrong repository, новый путь БД или неизвестная identity дают отказ;
автоматически создавать/перепривязывать историю вместо потерянной запрещено.

Отправляется только последняя опубликованная пара `snapshot.db` + `manifest.json`
version 1 из services/automatic_snapshots.py. Namespace, snapshot_id, size,
sha256, fingerprint и source_generation перепроверяются. Live DB, WAL/SHM,
`.env`, AWS config, status.json и пароль никогда не входят в payload.
Под существующим namespace_lock пара копируется в собственный private staging;
исходные файлы неизменяемы, поэтому это копирование готового файла, не второй
SQLite backup engine. Lock/staging ограничены 10 с; lock освобождается **до сети**.
С staging сравниваются hash и shared inspect_database. Retention может затем
удалить локальный оригинал, но уже не повлияет на отправляемую пару.

После `restic backup` именно возвращённый restic snapshot ID скачивается
с `--no-cache`, извлекается в новый owned temp и сверяется с исходным manifest
по bytes/hash/schema/typed rows. Только это публикует успешный cloud receipt.
При неизменном snapshot_id/hash повтор переиспользует ранее подтверждённый remote
snapshot, снова проверяет его чтение и не создаёт календарных дублей.
Падение после upload до receipt допускает лишний restic snapshot при повторе,
но не ложный успех и не удаление прежнего. Exactly-once не обещается.

## Запуск, состояние и давность

Предлагается opt-in macOS LaunchAgent: `RunAtLoad` и `StartCalendarInterval`
с Minute=0, без KeepAlive. Часовая попытка работает независимо от открытого UI,
пока пользователь вошёл в Mac. Sleep/offline/выключение не дают фоновой гарантии;
после wake/login запускается ближайшая доступная попытка, без пачки пропусков.
Два caller одного repository не работают одновременно: отдельный OS lock,
при занятом lock — bounded `cloud_busy`; принудительный restic unlock запрещён.
Вся попытка ≤10 минут, включая дочерние процессы и cleanup; timeout останавливает
свою process group, не сервисы тренера. Следующий retry — следующий час либо
явная operator-команда; бизнес-команда, GET status и рендер не запускают сеть.

Отдельный CloudBackupStatus: `disabled / unknown / ready / stale / degraded`,
`last_attempt_at`, `last_verified_at`, `last_covered_check_at`, `last_drill_at`
(UTC или null), `reason_code`: cloud_busy, cloud_config_invalid,
cloud_identity_unknown, cloud_snapshot_invalid, cloud_credentials_unavailable,
cloud_auth_failed, cloud_network_failed, cloud_timeout, cloud_state_unwritable
или null. Для drill отдельный `drill_warning`: cloud_drill_due /
cloud_drill_failed / null. Raw exceptions, пути,
repository/namespace IDs, credentials и строки БД в API/UI/log не выводятся.
Receipt хранит private identity/hash/restic ID и атомарно заменяется вне БД.
Отсутствующий config или enabled=false — disabled; enabled config без receipt —
unknown. Повреждение/несовпадение identity — отказ, не готовая копия.

`last_covered_check_at` — время успешной локальной проверки **того же** snapshot,
взятое под namespace lock из согласованного local status. Оно переносится в receipt
лишь после remote verification; время upload не подменяет время покрытия данных.
`ready` требует local ready, совпадения текущего local generation с receipt,
давности covered check и remote verification ≤24 ч, без последней ошибки.
Устаревшее покрытие/новое локальное поколение — stale, не выдуманный успех;
последняя ошибка — degraded с сохранением дат предыдущей копии. Неизвестные,
будущие timestamps или нечитаемое состояние — unknown/degraded.
Фраза «проверено в …» не обещает отсутствие более поздних записей.
RPO ≤24 ч — целевая потеря последних изменений только при исправных local checks,
доступном Mac/сети/ключах; при нарушении условий явно показывается stale/degraded.

## Секреты, хранение и reset

AWS credentials берутся из уже выделенного owner profile вне Git/SQLite/logs;
cloud key не является паролем расшифрования. Рабочий пароль restic создаёт Greg
интерактивно, хранит в macOS Keychain для job и **в независимо доступном менеджере
паролей** вместе с repository URL/ID. Потеря одного Mac не должна уничтожить ключ.
Locked/missing Keychain — отказ без интерактивного запроса из фонового job.
Пароль не передаётся аргументом команды, не пишется в plist/receipt/.env/backup.
Тестовый пароль transport experiment никогда не становится рабочим.
Ротация operator-only: новый AWS key проверяется до отзыва старого; новый restic
password/key проверяется чтением до удаления старого. Удалять потерянную историю
или создавать вместо неё новую при auth/password failure нельзя.

**Предложение retention v1:** сохранять все успешные cloud snapshots; автоматических
`forget/prune/delete`, bucket lifecycle expiry и облачного удаления по product reset
нет. Это исключает второй retention engine и не меняет local union 14 daily /
8 weekly + latest/reset pins из #623. Прежние облачные копии переживают local reset;
синхронная off-device копия каждого pre-reset/intermediate состояния не обещается.
До первого upload данные облаком не защищены. Local pins не означают cloud receipt.
Размер/стоимость контролируются владельцем в Cloud.ru; 15 ГБ free tier относится
к общему account quota, не является hard cost cap или гарантией вечной бесплатности.
При нехватке квоты upload отказывает, локальные копии сохраняются. Политика
сроков/удаления и автоматический контроль расходов — отдельное расширение после
измерения роста; v1 не выдаёт наличие свободной квоты за проверенный backup.

До live activation Greg подтверждает именно эту retention/cost policy,
доступность recovery kit вне Mac и macOS-only scheduler. Destination уже выбран;
повторно выбирать провайдера не требуется. Согласование spec/merge не является
согласованием личной миграции, смены runtime/.env или включения job.

## Restore drill и отказ

При включении и далее каждые 30 дней job выполняет isolated drill из remote
repository в новый private temp без зависимости от local snapshot/receipt.
Проверяются manifest version/binding/hash, integrity, схема и fingerprints всех
таблиц. Last drill обновляется только после полного успеха; просрочка видна
как отдельный warning и не подменяет last_verified_at. Повреждённый объект,
неверный пароль, full disk, timeout, interruption и failed receipt не меняют
production и не удаляют прежние cloud/local copies; частичный staging не кандидат.
Cleanup касается только artifacts данного запуска; неизвестные каталоги не удаляются.

Runbook потери ноутбука: получить recovery kit и новые S3 credentials из Cloud.ru,
проверить repository ID, скачать выбранный snapshot в новый temp, сверить manifest,
проверить домены и лишь потом отдельно согласовать stopped-service restore с rollback
по [штатному runbook](sqlite_backup_restore.md). Потеря всех restic passwords
означает невосстановимость; Cloud.ru secret её не исправляет. Corrupt snapshot
не подменяется молча другим: оператор выбирает предыдущую проверяемую копию.
RTO ≤30 минут измеряется от доступа к recovery kit/network до verified temp DB
на репрезентативной synthetic domain fixture, не включает получение нового Mac.

## Public Contracts и границы ролей

M1: API/TS/schema/runtime unchanged. Предлагаются services/cloud_backups.py и
operator CLI scripts/cloud_backup.py: `status`, `run`, `drill` с явным абсолютным
`--config`; никакого implicit выбора/создания личной DB и автоматического init.
Private config v1: enabled=false по умолчанию, backup_root, source_namespace,
repository_url, expected_repository_id, aws_profile, keychain_service; секретов нет.
Один config управляет одним repository/source binding; receipt и lock рядом в
private cloud data dir, staging/restore leaf принадлежат запуску, вне checkout.
Права owner-only, отсутствие symlink/hardlink/SQLite family overlap по #625.

M3: новый read-only GET `/api/backup/cloud/status` и CloudBackupStatus в
api/backup_contract.py + mirror web/lib/types.ts; старые BackupStatus/envelopes
и POST local check unchanged. Shared Python считает freshness; web показывает
локальное и облачное время существующим warning pattern. UI Specialist меняет
только consumer после contract handoff; CSS/layout здесь не проектируются.
Demo/acceptance возвращают disabled без чтения owner config/Keychain/сети.
Продуктовый reset не удаляет config/receipt/cloud history; scratch reset удаляет
только собственные данные. Uninstall job/disable сохраняет все снимки и секреты.

## Evidence boundary / RED matrix

| Случай | Наблюдаемый критерий будущей приёмки |
| --- | --- |
| Новое/неизменное поколение; current/history/новый namespace | Передаётся только bound valid pair; повтор без лишнего backup; rebind требует оператора |
| Retention после staging; два процесса; interruption upload/receipt | Согласованная пара, bounded lock; source и предыдущие копии неизменны; restart не invent ready |
| Старый/нет/foreign/corrupt manifest или state; clock drift | Никаких fallback к live DB, ложного нуля/ready, неявного init или удаления |
| Sleep/offline/locked keychain/auth/quota/deadline | stable degraded/stale, даты успеха сохранены; retry не повторяет бизнес-запись |
| Local data меняется/сбрасывается, старый snapshot уже remote | Локальная защита unchanged; cloud history сохранена, текущий receipt не утверждает покрытие нового generation |
| Потеря local files/receipt; remote corrupt/wrong password | Restore в новый owned temp, без production writes; отказ до operator activation |
| Полная domain fixture + restart | checkpoint/cycle, coach decisions, matches, feedback, readiness и provider/manual identity совпали через реальные readers; RTO измерен |
| Default/demo/test; API/UI serialization; secrets-canary | Нет Keychain/network до opt-in; нет ключей/путей/payload; cloud/local freshness не смешаны |

Каждая новая ветка M2/M3 получает реальные failing tests до реализации.
M1 docs-only: RED/TDD, full pytest и browser checks N/A — executable поведение не
меняется; нужны link/diff checks и независимое spec review.

## ASR / ADR, delivery, DoD и review

ASR-DEP-2/REL-3: verified restore и failure isolation; SEC-1: encryption + secret
boundary; MOD-2: Python-owned freshness. [ADR-0002](architecture/adr_0002_sqlite_primary_store.md)
получает **предложенное opt-in исключение** из local-only пункта; ADR-0001/0007
переиспользуются. Ограниченный внешний restic + macOS LaunchAgent заменяет
crypto/scheduler frameworks; цена — platform-specific setup и рост без prune.

M1 (#752): этот контракт, ExecPlan, independent checker, draft PR. M2: shared
transport/CLI/config/status + launchd template, local restic doubles/fault/lifecycle
tests и повтор synthetic Cloud.ru probe без owner credentials в CI. M3: status
API/TS/web, monthly domain restore drill/runbook и общая приёмка. #626 закрывается
только после M2/M3 и owner-accepted evidence; live activation всё равно отдельна.

DoD M1: observable AC и роли назначены; docs checks GREEN; checker findings
disposition письменно; pushed candidate и draft PR связаны с #752/#626.
Review mode manual, native 0/2, acceptance SHA/exception N/A. Local independent
review pending. Evidence bundle/CI/current head — в PR; новые source invariants
в M1 отсутствуют. Findings и Final Verdict обновляются после checker;
native acceptance, merge/cleanup — Greg, не автоматический следующий шаг.
