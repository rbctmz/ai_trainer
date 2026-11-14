# Облачные снимки: операторский контур M2 (#626 / #754)

M2 добавляет отправку и проверку готового снимка через restic. По умолчанию
контур выключен. Этот документ и пример LaunchAgent не устанавливают задание,
не создают рабочий repository и не разрешают личное включение. API/web status
и ежемесячный full-domain drill остаются M3. Контракт:
[cloud_backup_slice_spec.md](cloud_backup_slice_spec.md); локальные копии и
остановленное восстановление: [sqlite_backup_restore.md](sqlite_backup_restore.md).

## Что запускается

Один существующий checkout тренера и его Python, отдельная короткая команда:

```text
/absolute/ai_trainer/ai_trainer_env/bin/python /absolute/ai_trainer/scripts/cloud_backup.py status --config /absolute/private/cloud/config.json
/absolute/ai_trainer/ai_trainer_env/bin/python /absolute/ai_trainer/scripts/cloud_backup.py run --config /absolute/private/cloud/config.json
```

`status` читает только операционные метаданные. Он не открывает SQLite, не
загружает ключи, не обращается к сети и не создаёт отсутствующие пути. `run`
требует явный opt-in, совпадение выбранной real SQLite и включённых локальных
снимков. Demo/acceptance отказывают до чтения cloud config. Сначала выполняется
существующий `check_snapshot(reason='cloud_upload')`, затем готовые `snapshot.db`
и `manifest.json` копируются под локальной блокировкой в приватный staging.
Сеть начинается после освобождения блокировки и проверки самой staging SQLite.
Изменение config во время подготовки прекращает попытку до загрузки ключей.

Repository ID проверяется до отправки. Успех публикуется после no-cache restore
точного restic snapshot ID и сравнения manifest, SHA-256, схемы и типизированных
строк. Неизменившийся локальный снимок повторно проверяется из облака без новой
отправки. Сбой после отправки до receipt может дать дубликат при повторе.

## Приватная конфигурация

Один отдельный каталог вне checkout и BACKUP_DIR: владелец текущий пользователь,
режим `0700`; config/receipt `0600`, без symlink/hardlink. Минимальный config:

```json
{"version": 1, "enabled": false}
```

После отдельного решения о включении оператор заполняет все поля:

```json
{
  "version": 1,
  "enabled": true,
  "database_path": "/absolute/selected/ai_trainer.db",
  "backup_root": "/absolute/local/backups",
  "source_namespace": "<64 lowercase hex from the checked local manifest>",
  "repository_url": "s3:https://s3.cloud.ru/ai-trainer-backups/<dedicated-prefix>",
  "expected_repository_id": "<64 lowercase hex from the existing restic config>",
  "aws_profile": "ai-trainer-backups",
  "keychain_service": "ai-trainer-cloud-backup"
}
```

Плейсхолдеры намеренно не проходят валидацию. `database_path`/`backup_root` должны
совпадать с выбранными `Settings.DATABASE_PATH`/`Settings.BACKUP_DIR`; local
`AUTO_BACKUP_ENABLED` должен быть включён. `source_namespace` берётся из
проверенного локального manifest, а не угадывается. Источник и снимок должны
содержать `user_settings.dataset_origin=real`. Unknown provenance отказывает.
Путь `Settings.CLOUD_BACKUP_CONFIG` разрешается независимо от пути SQLite;
CLI всегда требует явный `--config` и ничего не создаёт при импорте Settings.

Для одного repository используется один config/каталог и один LaunchAgent.
Каталог содержит `receipt.json`, lock и временные каталоги только своей попытки.
Чужие, подменённые и повреждённые данные не дают разрешения на cleanup/adoption.
Автоматического удаления старых orphan-каталогов нет.

## Зависимость и ключи

Проверенная версия — restic **0.19.1** по `/opt/homebrew/bin/restic` (macOS
Apple Silicon). Другие версии/платформы этим контуром пока не заявлены.
Repository version 2 должен уже существовать в отдельно согласованном prefix.
Продукт не выполняет `init`, `unlock`, `forget` или `prune`. Создание рабочего
repository и независимого recovery kit — отдельный операторский шаг с владельцем.

S3 key ID/secret читаются только из явно выбранного раздела приватного
`~/.aws/credentials`; fallback на DEFAULT, session token и inherited AWS keys
не используются. AWS CLI продукту не нужен. Сам файл ключей не попадает в
payload. Не добавляйте ключи или пароль в Git, SQLite, plist, аргументы команды
или журналы.

Отдельный пароль restic хранится в macOS Keychain как generic password:
service = `keychain_service`, account = `ai-trainer-cloud-backup`. Оператор
создаёт запись через Keychain Access и разрешает доступ выбранному Python.
Чтение выполняется с отключённым интерактивным UI: locked/missing/ACL denial
даёт `cloud_credentials_unavailable`, а не диалог фонового задания. Реальное
Keychain provisioning/ACL в M2 автоматически не проверяется и не меняется.

Независимо от единственного Mac сохраните пароль restic, repository URL/ID
и инструкцию получения новых S3 ключей. Без пароля зашифрованные копии не
восстановить. Проверка хранения recovery kit остаётся личной приёмкой.

При согласованной ротации S3 ключа оператор обновляет только выбранный профиль,
проверяет явный `run` с readback и затем отзывает старый ключ. При утрате ключа
получают новый у провайдера; история repository и пароль restic сохраняются.
Смена пароля restic/recovery kit — отдельная операция; M2 не выполняет её и
не меняет ключи автоматически.

## Расписание после отдельного включения

[Шаблон LaunchAgent](../deploy/macos/ai-trainer-cloud-backup.plist.example)
содержит только абсолютные плейсхолдеры. Оператор подставляет существующие
Python/script/config/WorkingDirectory. Отдельный runtime clone не требуется.
Заданы `RunAtLoad` и каждый час на минуте 0; `KeepAlive` отсутствует. Шаблон
не устанавливается из приложения или тестов. Команды `launchctl` здесь не
выполнялись. Перед ручной установкой требуется согласованная проверка config,
ключей, recovery kit, стоимости и успешного readback.

Сон/выключение Mac пропускают запуски. RPO оценивается по покрытой локальной
проверке, а не по времени upload. Пропущенный запуск не считается успехом.
Отключение: сначала выгрузить известное задание, затем поставить `enabled:false`;
историю repository, password и локальные снимки сохранить.

## Результат и отказы

CLI печатает безопасный JSON, без путей, URL, ID repository и секретов.
`degraded` возвращает exit 2. Состояния: disabled, unknown, ready, stale,
degraded; даты last attempt/verified/covered check/drill сохраняют разные смыслы.
До M3 `last_drill_at` не обновляется; `cloud_drill_due` честно остаётся warning.
`ready` требует текущий локальный generation и обе даты verified/covered не
старше 24 часов. Ошибка сохраняет предыдущие успешные даты, но не зелёный статус.

`cloud_busy` — занята локальная/restic блокировка; не удалять lock принудительно.
`cloud_config_invalid`/`cloud_identity_unknown` — проверить привязку и metadata,
не выполнять автоматический init/adoption. `cloud_local_backup_unavailable`/
`cloud_snapshot_invalid` — проверить выбранный real store и локальные снимки.
`cloud_credentials_unavailable`/`cloud_auth_failed` — оператор проверяет профиль
и Keychain. `cloud_network_failed`/`cloud_timeout` — следующая явная попытка
безопасна; `cloud_state_unwritable` требует проверки приватного каталога.
Raw restic stdout/stderr не публикуются.

Весь операторский запуск ограничен 600 секундами, staging под local lock —
10 секундами. При timeout уничтожается группа процессов этой попытки и удаляется
лишь её собственный временный каталог с прежней идентичностью. Успех не
публикуется до полной readback-проверки. Локальная retention остаётся 14 daily /
8 weekly / latest / reset pins. Облачного prune в v1 нет: объём и стоимость
растут; наличие Free Tier не доказывает нулевую стоимость.

## Проверенная граница

M2 проверяется синтетическими SQLite и fake transport; отдельный тест использует
настоящий restic с локальным зашифрованным repository, если бинарник установлен.
В CI без restic этот тест явно skipped. Это не live Cloud.ru, не реальный
Keychain/LaunchAgent и не full-domain disaster drill. Ранее выполненный маленький
Cloud.ru probe описан в #626 comment 6879508968 и не заменяет эти приёмки.
