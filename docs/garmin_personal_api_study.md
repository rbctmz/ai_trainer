# Garmin Connect Personal API — исследование для AI Trainer

> Дата: 2026-10-26
> Статус: исследование (Class C, docs-only). Решение о внедрении не принято, кода не менялось.
> Роль: Spec / Architecture Owner (изучение внешнего контракта, без выбора UI/стиля).
> Related: #736 (research/decision issue)

## Источники

Внешние (проверены 2026-10-26):

- [Personal API](https://developer.garmin.com/gc-developer-program/personal/personal-api) — страница программы
- [Personal API FAQ](https://developer.garmin.com/gc-developer-program/personal/personal-faq/)
- [Personal API Swagger](https://developer.garmin.com/gc-developer-program/personal/swagger-docs/) — OpenAPI 3.0.1 встроен в JS-бандл страницы, извлечён целиком (26 путей, 60 схем)
- [Program Overview](https://developer.garmin.com/gc-developer-program/overview/) — сравнение Personal / Starter / Enterprise
- [garmin/connect-personal-api-python](https://github.com/garmin/connect-personal-api-python) — официальный клиент (Apache 2.0) и CLI `gc-personal`

Локальные: `data/garmin_client.py`, `data/garth_client.py`, `services/sync.py`, `services/sync_providers.py`, `services/readiness_snapshot.py`, `config/settings.py`, `docs/architecture/adr_0008_intervals_activity_ingestion.md`, `requirements.txt`.

## TL;DR

1. **Это официальный self-service доступ к данным собственного аккаунта**: ключ создаётся в веб-кабинете Garmin Connect, обменивается на 24-часовой bearer-токен, дальше — обычные GET к `https://personal.connectapi.garmin.com`.
2. **Ключевое преимущество для нас:** исчезает хранение пароля Garmin и весь класс ошибок `portal login 403` / `429` из `data/garmin_client.py:_summarize_auth_error` (Observed: этот код существует именно для их разбора).
3. **Ключевой разрыв:** в Personal API **нет** Training Readiness, Training Status (aggregated), max-metrics/VO2 max, Race Predictions, Endurance/Hill Score, списка устройств и skin temperature (Observed: в извлечённом OpenAPI этих путей и полей 0). Это как раз часть сигналов, которые мы сейчас тянем через логин.
4. **Юридическое ограничение:** Personal API — только «personal use», не для коммерческих multi-user приложений (FAQ, дословно). Наш current продукт — single-athlete self-hosted SQLite (Observed: таблицы `athlete_profile`, `user_settings`, без `users`), поэтому мы в рамках; SaaS — вне рамок.
5. **Рекомендация:** не заменять, а **добавить как опциональный официальный транспорт** (`GARMIN_PERSONAL_API_KEY`) рядом с текущим login-путём, и сначала сделать дешёвый live-smoke на 20 минут (нужен ключ владельца).

## 1. Что это такое

Garmin открыл self-service API для собственных данных пользователя. Три режима программы (Observed, страница Overview):

| | Personal | Business Starter | Business Enterprise |
|---|---|---|---|
| Кто | индивид, свой аккаунт | организация, много пользователей | компания в масштабе |
| Доступ | свой ключ, свой аккаунт | регистрация приложения + OAuth | по договору |
| Данные | Activity (JSON + FIT), Health (JSON), Women's Health | Activity, Courses, Health, Training, Women's Health | + Golf |
| Доставка | **Pull only** | Push only | Push или Ping/Pull |
| История | по диапазонам дат (см. §3) | **не включена** | 1 месяц+ |
| Пользователи | 1 (свой аккаунт) | ограничено | не ограничено |

Для нас практически важны два следствия: Personal API даёт **pull по датам** (то есть фактически историю — в отличие от Starter), но **один аккаунт на ключ** и **без push**.

## 2. Ключ, токен, жизненный цикл

Наблюдаемые факты (FAQ + страница + код официального клиента):

- **Создание**: только через веб-кабинет под своим логином — `connect.garmin.com/app/settings/personalApiToken` → Create Key → принять условия → выбрать срок → ключ **показывается один раз**.
- **Срок ключа**: 30 / 90 / 180 / 365 дней. За ~неделю Garmin присылает письмо с напоминанием.
- **Потеря ключа** = удалить и создать новый; **удаление ключа** инвалидирует связанные токены.
- **Обмен ключа на токен**:
  ```
  POST https://personal.connectapi.garmin.com/personalapitoken-service/personal-api/personal-api-key/token
  Authorization: ApiKey <your-api-key>
  ```
  Тело ответа — **голая JWT-строка** (`text/plain`), не JSON. Это ловушка для реализации: официальный клиент читает `response.text.strip()` и берёт `exp` из payload (Observed: `auth.py`).
- **Токен**: живёт 24 часа или до истечения ключа; **refresh token не поддерживается** — просто запрашивается новый тем же POST.
- **К данным**: `Authorization: Bearer <jwt>` (Observed: `client.py`).
- **Кэш токена** у официального клиента: `~/.config/garmin/connect-personal-api-bearer-token.json`, права `0600`, переиспользование только если до `exp` больше часа.

Вывод (Inferred): сервер-сайт-сайт обмен возможен без браузера — ключ это обычный статический секрет в заголовке. То есть sync-джоб может работать headless, как сейчас работает Intervals.

## 3. Покрытие данных: 26 GET-эндпоинтов

Полный список из извлечённого OpenAPI (Observed), с лимитами диапазонов:

| Домен | Эндпоинт | Ограничение |
|---|---|---|
| activities | `/activitylist-service/activities/search/activities` | пагинация `start`/`limit` (default 99), фильтры: даты, тип, дистанция, длительность, мощность, bbox |
| activities | `/activity-service/activity/{activityId}` | сводка + metadata + split summary (188 полей в `SummaryDTO`, 224 в `SplitSummaryDTO`) |
| activities | `/activity-service/activity/{activityId}/workouts` | выполненные workout-структуры |
| activities | `/download-service/files/activity/{activityId}` | **FIT/ZIP байты** (оригинальный файл) |
| wellness | `/usersummary-service/v2/dailysummaries` | до **1 года** |
| wellness | `/usersummary-service/usersummary/daily` | 1 день, v1-формат |
| wellness | `/usersummary-service/stats/steps/daily/{from}/{to}` | до **28 дней** |
| wellness | `/usersummary-service/stats/stress/daily/{from}/{to}` | до **28 дней** |
| wellness | `/usersummary-service/stats/hydration/daily/{from}/{to}` | до **31 дня** |
| wellness | `/wellness-service/wellness/dailyHeartRate` | 1 день (min/max/resting HR, аномалии) |
| wellness | `/wellness-service/wellness/bodyBattery/reports/daily` | до **31 дня**, параметр `chunks` |
| wellness | `/wellness-service/wellness/daily/spo2acclimation/{date}` | 1 день |
| wellness | `/wellnessactivity-service/activity/summary/range/{from}/{to}` | диапазон |
| sleep | `/sleep-service/sleep/dailySleep` | 1 день (стадии, score, SpO2) |
| sleep | `/sleep-service/sleep/dailySleepSummariesByDate` | до **31 дня** |
| hrv | `/hrv-service/hrv/{calendarDate}` | 1 день (ночные readings, baseline) |
| hrv | `/hrv-service/hrv/daily/{from}/{to}` | диапазон (weekly avg, last night, baseline, status) |
| body | `/weight-service/weight/range/{from}/{to}`, `/all/{from}/{to}` | вес + состав тела (BMI, жир, вода, мышцы, visceral fat) |
| body | `/goal-service/goal/user/effective/weightgoal/{from}/{to}` | цели по весу |
| profile | `/userprofile-service/userprofile/settings` | единицы, локаль, таймзона |
| profile | `/biometric-service/heartRateZones/v2` | пульсовые зоны (порог/resting/max) |
| profile | `/fitnessage-service/fitnessage/v2/{date}` | Fitness Age + компоненты |
| nutrition | `/nutrition-service/food/logs/{date}` | дневник питания |
| women's health | `/periodichealth-service/menstrualcycle/{summary,dayview}/{date}` | цикл |

Полей, которых достаточно для наших метрик: `trainingEffect`, `aerobic/anaerobicTrainingEffect`, `trainingStressScore`, `activityTrainingLoad`, `normalizedPower`, `functionalThresholdPower`, `lactateThresholdHeartRate`, `lactateThresholdSpeed`, `avgRespirationRate`, `avgSpo2`, `avgStress`, `differenceBodyBattery`, `vO2MaxValue` (только per-activity).

## 4. Ограничения программы

- **Personal use only.** «It is not intended for commercial applications serving multiple end users» (FAQ). Один ключ — один аккаунт; в путях нет `username`/`userProfileId` — скоуп неявный.
- **Pull only.** Никаких push-уведомлений/webhook: только периодический опрос. Наш sync и так pull-based — не блокер.
- **Нет Training/Courses API.** Планы и структурированные тренировки в Garmin через Personal API не поставляются (Observed: путей нет). Для нас не критично — доставка плана идёт в Intervals (`intervals_plan_deliveries`).
- **Ключ истекает** — статический секрет, который надо периодически менять человеком; авто-продления нет.

## 5. Что это даёт нашему проекту

Сопоставление с текущим login-путём (`garminconnect` + legacy `garth`):

| Наш сигнал / таблица | Сейчас (Observed) | Personal API | Итог |
|---|---|---|---|
| Активности (`activities`, `activity_provider_links`) | `get_activities` | search + activity | ✅ есть |
| Сплиты сессии | `get_activity_splits` | `splitSummaries` | ✅ есть |
| Стримы (мощность/HR) | через Intervals `streams.json`, не персистятся | **FIT-файл (ZIP)** | ✅ даже лучше по полноте |
| Сон (`sleep_data`) | `get_sleep_data` | dailySleep + summaries | ✅ есть, но **плоско** — обёртку `dailySleepDTO` делает адаптер |
| HRV (`hrv_data`) | `get_hrv_data` | `/hrv-service/hrv` | ✅ есть, включая baseline/status |
| Пульс покоя (`daily_health`) | `get_resting_heart_rate` | dailyHeartRate + v2 summary | ✅ есть |
| Стресс, Body Battery | `get_stress_data`, `get_body_battery` | stress stats + bodyBattery/reports | ✅ есть |
| Дыхание, SpO2 | `get_respiration_data` | v2 dailysummaries, spo2acclimation | ✅ есть |
| Шаги | `get_steps_data` | steps stats | ✅ есть |
| Вес/состав тела | `get_stats_and_body` | weight range | ✅ есть |
| VO2 max | `get_vo2_max` → `get_max_metrics` | `vO2MaxValue` есть в схеме `SummarizedActivityDTO`, но **пусто в 8/8 проверенных активностях** | ❌ фактически нет |
| **Training Readiness (устройства)** | `get_training_readiness` | — | ❌ **нет** |
| **Training Status (aggregated)** | `get_training_status` | — | ❌ **нет** |
| Race predictions, Endurance/Hill Score | не используем | — | ➖ не важно |
| Список устройств | `get_devices` | — | ❌ нет |
| Skin temperature | `get_skin_temperature_data` | — | ❌ нет |
| Fitness Age / HR-зоны / цели по весу | не используем | есть | ➕ бонус |

Про readiness важная деталь (Observed, `services/readiness_snapshot.py`): `PRIMARY_INPUTS = ("sleep", "hrv", "resting_hr")` — все три Personal API покрывает. `training_readiness` («Готовность устройства») — **вторичный** фактор наряду со `stress` и `tsb`. То есть потеря Garmin Training Readiness не ломает наш readiness-расчёт, а понижает его «богатство» — ровно тот gap, что уже зафиксирован в `docs/competitive_analysis_intervalcoach.md`.

## 6. Разрывы, которые надо принять осознанно

1. **Training Status / VO2 max max-metrics** — таблица `training_status` (поля `training_status`, `training_readiness`, `vo2_max`, `training_readiness_observed_at`) перестанет пополняться из Garmin; останется история + demo. Композитный статус («PRODUCTIVE») без Garmin придётся считать самим либо не показывать.
2. **Activity details / streams** — эндпоинта `get_activity_details` нет; вместо него FIT. Требует FIT-парсера: `python-fitparse>=1.2.0` **уже в `requirements.txt`**, но в коде **не используется** (Observed: 0 вызовов) — то есть работа новая.
3. **VO2 max** — хуже, чем выглядело по схеме: поле `vO2MaxValue` в `SummarizedActivityDTO` есть, но живой прогон 26.10.2026 показал его пустым во **всех 8** проверенных активностях (бег, велосипед, ходьба), а max-metrics эндпоинта нет вовсе. Считать VO2 max перешедшим в разряд недоступных (Observed).
4. **Devices / skin temperature** — уходят. Влияние: косметика в UI и один wellness-сигнал.
5. **Training Stress Score и trainingLoad не взаимозаменяемы** (Observed, 8/8 активностей): `trainingStressScore` заполнен только у power-активности (`virtual_ride`), а `activityTrainingLoad` — только у остальных. Адаптер должен читать их раздельно и не выводить один из другого (это же согласуется с ADR-0008 п.3: Garmin load ≠ TSS).

## 7. Технические ловушки для реализации

1. **Формы путей не совпадают с `garminconnect`.** Наш клиент зовёт `/usersummary-service/usersummary/daily/{username}` и `/usersummary-service/usersummary/daily/{date_str}`; в Personal API это `/usersummary-service/usersummary/daily?calendarDate=...` без username. `garminconnect` нельзя просто перенаправить на `personal.connectapi.garmin.com` — нужен тонкий адаптер (Observed: сравнение нашего кода и OpenAPI).
2. **Окна диапазонов** (подтверждено живьём): daily summaries держат **90 дней одним запросом** (заявлено «до 1 года»), sleep — **31 день**, 40 дней отбивается HTTP 400, body battery — 31 день, HRV — диапазон без ограничения в описании. Наш bootstrap ≥90 дней (ADR-0008 п.8) укладывается в 1 запрос для сводок и 3 запроса для сна/Body Battery.
3. **Лимиты запросов публично не документированы** (Observed: ни на страницах, ни в OpenAPI; официальный клиент ретраев/backoff не имеет). Нужен свой backoff на 429 и последовательные, не параллельные запросы.
4. **Истечение ключа** — неисправимо программно: нужно fail-closed предупреждение в sync-результате + операторская напоминалка (письмо Garmin приходит за неделю).
5. **Токен-эндпоинт отдаёт JWT-строку**, не JSON — парсить `text`, `exp` из payload.
6. **FIT download — ZIP-байты** в памяти (стриминга нет); наш клиент должен уметь распаковать и распарсить. **Проверено живьём:** эндпоинт отдаёт файл только при `Accept`, содержащем `application/x-zip-compressed` (или `*/*`); с `Accept: application/json` — HTTP **406 NotAcceptableException**. Наивный JSON-клиент сломается именно на скачивании.
7. **Совместимость `activityId` — подтверждена (Observed, live 26.10.2026):** 10/10 последних id совпали с локальными `activity_provider_links`, а три id прямо из БД читаются через `/activity-service/activity/{id}` с HTTP 200. Namespace один, дедуп Garmin↔Intervals (ADR-0008 п.2) безопасен.
8. **Сон приходит плоско (Observed, live).** `/sleep-service/sleep/dailySleep` возвращает `DailySleepDTO` **в корне ответа**, а `garminconnect` (и наш `Phase1DataProcessor`, см. `tests/smoke/test_sleep_metric_provenance.py`) ждут обёртку `{"dailySleepDTO": {...}}`. Без обёртки в адаптере сон молча запишется нулями — это тихая ошибка, а не падение.
9. **Секреты**: ключ — в `.env` (`GARMIN_PERSONAL_API_KEY`), кэш токена — файл `0600` вне репозитория или таблица состояния; не логировать ни ключ, ни токен (у нас уже правило: `logs/` не публиковать).

## 8. Варианты решения

**A. Опциональный официальный транспорт (рекомендуется).**
`GARMIN_PERSONAL_API_KEY` в `config/settings.py`; `services/garmin_personal.py` — адаптер с bearer-кэшем; `services/sync.py` выбирает транспорт (personal, если ключ задан, иначе login). Login-путь остаётся для Training Readiness/Status/VO2max/устройств, пока он работает. Плюс: убирает пароль и 403/429-класс сбоев для 80% данных, не теряя ничего. Минус: два пути к Garmin поддерживать.

**B. Полная замена login-пути.** Максимально чисто юридически и эксплуатационно (нет пароля вообще), но теряем Training Readiness/Status, VO2max max-metrics, устройства и skin temp; `training_status` становится «историческим». Требует продуктового решения, что показывать вместо статуса устройства.

**C. Business Program (Starter/Enterprise).** Единственный легальный путь для multi-user SaaS; но Starter — push only, без исторических данных и с лимитом пользователей, а Enterprise — контракт. Для текущего single-athlete self-hosted продукта это оверкилл.

**Рекомендация: A, поэтапно.** И до кода — дешёвая live-проверка (см. §11), потому что два критичных факта (совместимость `activityId` и фактические лимиты/окна) проверяются только реальным ключом.

## 9. Оценка работ (вариант A)

| Слайс | Содержание | Оценка |
|---|---|---|
| S1 | `PersonalApiAuthenticator` + кэш токена (файл/БД), `GarminPersonalApiClient.get()`, конфиг, `.env.example`, unit-тесты на HTTP-двойниках | ~1 RED→GREEN, небольшой |
| S2 | Адаптер wellness-подмножества (daily summaries, sleep, HRV, body battery, stress, steps) + чанкинг окон + запись в существующие таблицы | средний |
| S3 | Activity ingest через Personal API + сверка `external_id` с существующими линками + FIT download/парсинг (опционально) | крупнейший |
| S4 | Транспортный выбор в `services/sync.py`, `sync_providers.connection_overview()`, warning при истёкшем ключе, ADR-0011 | небольшой |

Официальный клиент (`garmin-connect-personal-api-python`, Apache 2.0) можно взять как зависимость вместо своего кода — тогда S1 схлопывается почти в ноль (остаётся обёртка + кэш в нашем состоянии).

## 10. Риски

- **Юридический**: если проект когда-нибудь станет multi-user SaaS на Personal API — нарушение условий. Сейчас рамки соблюдены только пока продукт single-athlete (Observed по схеме БД).
- **Операционный**: ключ на 90 дней без авто-продления → тихая остановка данных через квартал, если оператор не сменит ключ. Нужен явный warning, а не пустой дашборд.
- ~~**Регрессионный**: `external_id` из другого namespace сломает дедуп Garmin↔Intervals (ADR-0008)~~ — **снят** живым прогоном 26.10.2026 (namespace совпадает, см. §7 п.7).
- **Дублирующиеся пути**: два транспорта к Garmin = дублирование маппинга; частично снимается тестами на нормализацию (у нас уже есть `normalize_provider_activity`).
- **Неизвестные лимиты** запросов: всплеск 429 в проде без документированных квот.

## 11. План проверки (20–30 минут, нужен ключ владельца)

Проверка автоматизирована: `scripts/garmin_personal_smoke.py` (read-only, без записи в БД, без вывода секретов и значений health-метрик; коды выхода 0 — нет FAIL, 1 — есть FAIL, 2 — нет ключа).

```bash
source ai_trainer_env/bin/activate
export GARMIN_PERSONAL_API_KEY=...          # или строка в .env
python scripts/garmin_personal_smoke.py      # человекочитаемо
python scripts/garmin_personal_smoke.py --json
```

Что он проверяет (по одной пробе на пункт):

| Проба | Что подтверждает |
|---|---|
| `token` | ключ меняется на JWT-строку, срок жизни действительно ~24 ч |
| `profile` | запросы скоупятся на аккаунт владельца ключа |
| `activities` | поиск активностей работает, id и типы читаются |
| `activity_id_namespace` | **наши `provider_activity_id` из `activity_provider_links` читаются напрямую** — namespace совпадает (ADR-0008) |
| `activity_summary` | какие из 11 нужных полей сводки реально заполнены |
| `daily_summaries_90d` | держит ли эндпоинт заявленный диапазон «до 1 года» |
| `sleep_window_cap` | реальный лимит сна: 31 день проходит, 40 — отклоняется |
| `sleep_daily_fields` | форма ответа сна: стадии (`deepSleepSeconds` и др.) и наличие обёртки `dailySleepDTO` |
| `hrv_14d`, `body_battery_31d` | диапазонные wellness-эндпоинты отдают данные |
| `fit_download` | FIT скачивается как ZIP и парсится `fitparse` (записи и поля `heart_rate`/`power`/`cadence`) |

Флаги: `--skip-db` (нет локального кэша), `--skip-fit`, `--activity-id N`, `--days N`, `--json`.

Ручной минимум, если скрипт недоступен:

1. `curl -X POST 'https://personal.connectapi.garmin.com/personalapitoken-service/personal-api/personal-api-key/token' -H 'Authorization: ApiKey <key>'` — тело ответа должно быть JWT-строкой, не JSON.
2. `GET /activitylist-service/activities/search/activities?limit=5` с `Authorization: Bearer <jwt>` → сверить `activityId` с `activity_provider_links`.
3. `GET /activity-service/activity/{id}` → сверить поля из таблицы §5.

Результат прогона фиксируется в этом документе (Observed) до написания кода.

### Результат живого прогона (Observed, 2026-10-26)

`python scripts/garmin_personal_smoke.py` — 11 PASS, 0 WARN, 0 SKIP, 0 FAIL:

| Проба | Факт |
|---|---|
| `token` | токен получен, срок 24.0 ч |
| `profile` | 200, `measurementSystem=metric` |
| `activities` | 10 активностей за 60 дней (running, virtual_ride, walking) |
| `activity_id_namespace` | **148 Garmin-связей в БД; пересечение 10/10; три id из БД читаются напрямую → 200** |
| `activity_summary` | 9/11 полей заполнено; пусто `trainingStressScore`, `vO2MaxValue` |
| `daily_summaries_90d` | 90 дней одним запросом → 90 строк |
| `sleep_window_cap` | 31 день → 200, 40 дней → 400 (лимит подтверждён) |
| `sleep_daily_fields` | форма — плоский DTO; стадии 5/5; `sleepScores` есть |
| `hrv_14d` | 14 дневных наблюдений (baseline, lastNightAvg, status) |
| `body_battery_31d` | 31 дневной отчёт |
| `fit_download` | ZIP 97 КБ → `24842779126_ACTIVITY.fit` 260 КБ, 2703 записи, поля `heart_rate`, `power`, `cadence`, `enhanced_speed`, `distance`, `position_lat` |

Дополнительный разовый скан (не входит в скрипт), 8 последних активностей:

- `trainingStressScore` заполнен только у `virtual_ride` (power), `activityTrainingLoad` — у остальных; вместе не встречаются;
- `vO2MaxValue` пуст во всех 8;
- v2 daily summary содержит `heartRate.restingValue`, `stress.avgLevel`, `bodyBattery.endOfDayValue`, `respiration.avgValue`, `pulseOx.avgValue` — всё, что пишется в `daily_health`;
- HRV-сводка содержит `lastNightAvg`, `baseline`, `weeklyAvg`, `status` — всё, что пишется в `hrv_data`.

Вывод: **вариант A подтверждён как реализуемый**, а вариант B стал дешевле, чем казалось (Training Readiness/Status/VO2 max всё равно частично недоступны — но Training Status остаётся только в login-пути).

## 12. Открытые вопросы

1. Готовы ли мы потерять Garmin Training Readiness / Training Status ради ухода от пароля (вариант B), или держим оба пути (вариант A)? VO2 max уже почти не наш: живой прогон не нашёл его ни в одном из 8 активностей.
2. Нужен ли FIT-пайплайн (собственные стримы) или достаточно текущего: сводка активности + стримы из Intervals?
3. Кто отвечает за ротацию ключа раз в 90 дней в self-hosted сценарии — оператор вручную или напоминание в UI?
4. Если продукт пойдёт в multi-user, принимаем ли сейчас решение «Personal API — только self-hosted профиль», с явным запретом включать его в SaaS-конфигурации?
