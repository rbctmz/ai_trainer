# Garmin Connect Personal API: исследование и граница внедрения

Актуализировано **16.11.2026**. PR #737 поставляет исследование и отдельный
операторский smoke; runtime sync, схема БД, UI, зависимости и TSS не меняются.
Доработка диагностического инструмента — Class A из-за credentials/read-only
SQLite; [контракт](garmin_personal_smoke_slice_spec.md) и
[ExecPlan](garmin_personal_api_study_execplan.md). Решение владельца **A**
зафиксировано в [#736](https://github.com/rbctmz/ai_trainer/issues/736).

## Вывод для AI Trainer

Garmin опубликовал официальный Personal API для собственных данных пользователя.
Его можно добавить как ещё один транспорт существующего провайдера `garmin`.
Сейчас приложение использует `garminconnect` с login/password; `garth` оставлен
для диагностики. Новый транспорт не должен менять provider namespace, canonical
IDs, историю, source priority или локальный каскад TSS.

Вариант A выбран, но **не реализован этим PR**. Обновление ключа в `.env` не
должно само переключать рабочий sync. Для будущей интеграции нужны явный выбор
транспорта, проверка доступных данных и отдельная приёмка. Intervals остаётся
рекомендованным основным источником; backward-compatible defaults не меняются.

## Источники и воспроизводимость

Проверены напрямую 16.11.2026 без authenticated-запросов и личных ключей:

- [Garmin Personal API](https://developer.garmin.com/gc-developer-program/personal/personal-api/).
- [Garmin FAQ](https://developer.garmin.com/gc-developer-program/personal/personal-faq/).
- [Garmin Swagger](https://developer.garmin.com/gc-developer-program/personal/swagger-docs/).
- [Официальный Python SDK](https://github.com/garmin/connect-personal-api-python),
  его [README](https://raw.githubusercontent.com/garmin/connect-personal-api-python/main/README.md)
  и [pyproject](https://raw.githubusercontent.com/garmin/connect-personal-api-python/main/pyproject.toml).

OpenAPI 3.0.1 встроен как JSON в публичный JS-компонент Swagger-страницы. Снимок
содержит **26 paths и 109 schemas**, info.version 1.0.0. Прежнее число 60 схем
не описывает текущий снимок. URL компонентов и SHA-256 публичных артефактов — в
[contract receipt](reports/issue-737-public-contract.json). Это датированная
фиксация документации, не обещание неизменности внешнего API. README SDK
предупреждает, что convenience wrappers могут отставать от доступных API.
Обнаруженное ниже обратное расхождение фиксируем отдельно.

Локальный контекст: `services/garmin.py`, `utils/app_state.py`,
`services/sync.py`, `services/sync_providers.py`, `services/readiness_snapshot.py`,
`config/settings.py`, [ADR-0008](architecture/adr_0008_intervals_activity_ingestion.md).
Существующие factory/configured checks завязаны на login-клиент; отдельного
Personal API runtime-клиента в приложении нет.

## Ключ и bearer-токен

Ключ создаётся пользователем в Garmin Connect Web, показывается один раз и имеет
выбранный срок 30/90/180 дней или один год. FAQ описывает уведомление примерно за
неделю до истечения. По ключу выполняется POST на
`/personalapitoken-service/personal-api/personal-api-key/token` с Authorization
ApiKey; результат — access token для поддерживаемых API. Токен действует 24 часа
или до истечения ключа, если оно раньше. Refresh token не предусмотрен: новый
access token получают тем же key→token обменом. Отзыв ключа инвалидирует и токены.

Следствие для будущего адаптера: истечение/отзыв ключа должны давать явное
состояние подключения; повторный token exchange не продлевает сам ключ. Ключи
и токены остаются вне Git/SQLite/logs; включение runtime и их хранение требуют
собственного контракта. Исследовательский smoke держит токен только в памяти и
не создаёт token cache. Флаг --api-key совместим, но предупреждает о видимости
аргумента в shell history/process list; нормальный operator input — окружение.

## Покрытие опубликованного контракта

| Область | Опубликованные пути / форма | Граница вывода |
| --- | --- | --- |
| Активности | search, activity/{id}, workouts, activityTypes; ZIP download | Пагинация и полное историческое покрытие ещё требуют runtime-тестов |
| Daily summary | daily?calendarDate; v2/dailysummaries с диапазоном до 1 года | HTTP 200 не доказывает наличие данных за каждый день |
| Сон | dailySleep → корневой DailySleepDTO; summaries → массив DTO, максимум 31 день | Форму требуется адаптировать к существующим потребителям |
| HRV | дневной endpoint и daily/{from}/{to} | Максимум диапазона в описании не указан; это не гарантия безлимитности |
| Body Battery | reports/daily, максимум 31 день, chunks | Сохранять provenance и неполноту |
| Остальное wellness | heart rate, stress, steps, hydration, SpO2, wellness activity summary | Поля проверяются отдельно, missing не превращается в 0 |
| Body/profile | weight, goals, profile settings, HR zones, Fitness Age | Наличие пути не означает заполненность на любом аккаунте |
| Women's health | menstrual summary/dayview | За пределами будущего первого среза AI Trainer |
| Device Training Readiness/Status, devices, skin temperature, Courses/Training | Не найдены в опубликованном снимке 26 путей | Не обещать паритет login-клиента по этому контракту |
| VO2 max | vO2MaxValue есть в SummarizedActivityDTO; SDK также содержит get_daily_vo2_max | Отдельный maxmet-путь SDK отсутствует в текущем Swagger; статус требует проверки |

**VO2: исправление прежнего вывода.** README официального SDK перечисляет
`GET /metrics-service/metrics/maxmet/daily/{start_date}/{end_date}`, но извлечённый
снимок Swagger этот путь не содержит. Поэтому неверно без оговорки утверждать
как полное отсутствие VO2, так и доказанную доступность max-metrics. В старой
личной выборке поле было пустым; она не устанавливает общий контракт. Реальный
ответ аккаунта по новому пути сейчас не запрашивался.

## Что было проверено живьём 26.10.2026

Ниже **исторический отчёт автора**, а не повторный live-run 16.11. Скрипт тогда
сообщил 11 PASS, 0 WARN/SKIP/FAIL. Личные записи и ключи повторно не читались.

| Наблюдение | Что оно поддерживает | Чего не доказывает |
| --- | --- | --- |
| key→token, около24 часов | token exchange работал на выбранном ключе | текущую валидность ключа |
| 10/10 ID из API встретились в локальных links; 3 ID читались напрямую | совместимость ID на этой выборке | универсальный namespace/безопасность любого будущего ingest |
| 90-дневный daily summary запрос вернул 90 строк | этот диапазон/аккаунт работал тогда | фактическую доступность всего заявленного года |
| 31-дневное sleep окно 200; 40-дневное 400 | более длинный запрос был отклонён | точную границу 31 без 32-дневного boundary check/причины400 |
| dailySleep был плоским DTO со стадиями/score | наблюдаемую форму на выборке | корректный ingest без mapper-тестов |
| HRV 14 дней, Body Battery 31 день | ответы соответствующих endpoint тогда | отсутствие ограничений/пропусков вообще |
| FIT скачался ZIP и читался fitparse | download/формат работали тогда | готовый FIT ingest или необходимость хранить raw streams |
| vO2MaxValue был пуст в 8 активностях | отсутствие значений в тех ответах | отсутствие VO2 в программе/на других датах |

На четырёх типах старых наблюдений нельзя строить абсолютные обещания:
заполненность полей, совпадение ID, лимит диапазона и доступность max-metrics.
Особенно важно не смешивать Garmin Training Load с локальным TSS.

## Исправления исследовательского smoke

`scripts/garmin_personal_smoke.py` остаётся самостоятельным read-only CLI.
Он использует stdlib и уже имеющийся fitparse; сервисы приложения его не импортируют.
Его 11 проб проверяются локальным HTTP-двойником и временными SQLite.

Ошибки больше не публикуют raw HTTP body: статус/путь достаточны для безопасной
диагностики, а секреты маскируются во всех результатах. Текст неизвестного
исключения не переносится в вывод. Автоматический redirect на другой origin
не должен передавать выбранный key/token. Для секрета, пересекавшего прежний
160-символьный cut, есть регрессия с фиктивным canary.

Sleep probe сравнивает **31 и 32 включительных календарных дня** с одним end date.
PASS требует принятого 31 и recognizable range-specific HTTP 400 для 32.
401/403/429/5xx — сбой, а generic 400 — недостаточное доказательство; они не
подтверждают лимит. Принятое 32-дневное окно даёт WARN, без обещания произвольного
расширения. Исторический 31/40 результат выше не переименовывается в новый тест.

Для DB сверки --db имеет приоритет. Без него используется DATABASE_PATH либо
платформенный application-data default через общий pure resolver. Старую БД
в checkout скрипт не выбирает автоматически. Чтение — mode=ro/query_only,
без Database constructor, schema initialization или создания отсутствующего
файла. --skip-db отключает открытие SQLite. Namespace вывод ограничен выборкой;
HTTP 200 с другим activityId не считается совпадением.

Операторские команды (живой запуск требует собственного ключа и разрешения):

```text
python scripts/garmin_personal_smoke.py --skip-db --skip-fit
python scripts/garmin_personal_smoke.py --db /absolute/selected.sqlite --json
```

В репозитории проверяются только fake credentials и owned temp data:

```text
python scripts/run_isolated_tests.py tests/smoke/test_garmin_personal_smoke.py -q
python -m ruff check .
```

Коды выхода: 0 — нет FAIL (WARN/SKIP остаются видны), 1 — есть FAIL, 2 — конфигурация.
`ok:true` в JSON означает отсутствие FAIL, а не полный runtime/data parity.
Один успешный smoke не заменяет будущий normalizer/ingest/rollback contract.

## SDK и реалистичная стоимость внедрения

SDK опубликован самой Garmin, включает auth/cache, GET wrappers и CLI. Его
pyproject 16.11 требует **Python >=3.12**; текущий CI AI Trainer использует 3.11,
Dockerfile.api — 3.10. Прямое добавление зависимости сейчас несовместимо с этим
baseline. Официальный API можно использовать и собственным совместимым HTTP-
адаптером; выбор SDK/Python upgrade — отдельное архитектурное решение.

README SDK описывает обязательный bearer cache, plain-text credential files,
0600 для нового POSIX cache и только предупреждение для уже небезопасных прав;
также явное восстановление после раннего 401. Поэтому S1 не «почти ноль»: нужно
согласовать наш secret/state boundary, retries, конфигурацию и supported versions.
В #737 dependency/Python/cache изменения отсутствуют.

## Решение A и отдельная будущая реализация

Владелец выбрал A в #736: Personal API добавляется как официальный транспорт
Garmin; login-путь сохраняется как отдельно выбираемый режим на время проверки
покрытия. Автоматического fallback при 401, неявного переключения по наличию ключа
или нового provider=`garmin_personal` решение не требует.

Будущий Class A контракт должен охватить factory клиента и configured/status
projection, mapping wellness и activities, idempotent ingest, pagination/chunks,
UTC/local-date границы и курсоры после полного успешного окна. Требуются состояния
missing/unsupported/expired, сохранение старой истории, canonical TSS и wellness
source priority. Отсутствующие device metrics не должны молча затирать историю.
Эти требования не разрешают reimport или repair личной БД сейчас.

Прежние S1–S4 остаются последовательностью, а не оценкой в часах:
S1 — auth/config/transport contract; S2 — wellness mapping; S3 — activities/identity;
S4 — integration/status и отдельный rollout. Это будет отдельный implementation
issue; пользователь остановил текущую работу на завершении #737.

Вариант B (полная замена login) пока не принят: полное покрытие не доказано.
Personal FAQ ориентирует API на собственный аккаунт, не на коммерческое
приложение для нескольких конечных пользователей. Для изменения продуктового
формата требуется отдельно сверить соответствующую программу Garmin; описание
Personal не является общим заключением о лицензировании любого self-hosted проекта.

## Definition of done #737

Исследование отражает датированные первичные источники и их расхождения;
диагностические ошибки воспроизводятся и исправлены на stubs; выбранная БД
читается без создания/изменения; новые credentials/data dependency отсутствуют.
Точный финальный head проходит изолированные tests, Ruff, CI и manual independent
review. #737 ссылается на #736 через Refs; будущая интеграция остаётся открытой.
