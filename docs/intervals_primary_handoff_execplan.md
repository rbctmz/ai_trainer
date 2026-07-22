# Intervals-primary + локальный Docker-handoff: другой атлет запускает AI Trainer на своих данных

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

This document must be maintained in accordance with `.agent/PLANS.md` (the ExecPlan authoring rules), located at the repository root.

## Purpose / Big Picture

После завершения UI-консолидации (ExecPlan `docs/ui_consolidation_beta_execplan.md`) интерфейс готов к бете. Но остаётся настоящий продуктовый барьер: **сейчас AI Trainer может запустить на своих данных только владелец с аккаунтом Garmin.** Весь синк данных (`services/sync.py::sync_garmin_data`) требует авторизации в Garmin Connect; без неё локальная база пуста, и продукт нечего показать.

Цель этого плана — сделать так, чтобы **технический атлет-тестер с аккаунтом Intervals.icu (и любым устройством — Garmin/Wahoo/Polar/Coros/Suunto) мог: склонировать репозиторий, задать свой Intervals-токен, синхронизироваться и увидеть СВОЙ план — без Garmin.** Intervals.icu становится первичным источником данных, Garmin — вторичным/опциональным.

Почему Intervals как первичный источник (решение владельца, зафиксировано в UI-ExecPlan и [[project-service-readiness]]): Intervals.icu агрегирует активности и wellness с многих марок устройств, работает по API-ключу (никакого хрупкого логина/пароля, как у неофициального `garminconnect`), и это обходит худший SaaS-блокер. Для беты это разница между «запустить может один человек» и «запустить может любой технический атлет».

Наблюдаемый результат, которого мы добиваемся (сценарий приёмки): человек, у которого НЕТ Garmin-доступа, но есть Intervals.icu API-ключ, выполняет короткую последовательность (склонировал → вписал токен → поднял стек → нажал синк) и на `/planning` видит построенный по СВОИМ активностям план, а на `/today` — сессию дня. Реальные данные владельца при этом не затронуты (изоляция локальной БД).

Термины в простом языке:

- **источник данных (data source)** — откуда приходят активности и wellness-метрики (HRV/сон/пульс покоя). Сейчас первичный источник — Garmin; цель — сделать первичным Intervals.icu.
- **Intervals.icu** — сторонний веб-сервис, куда атлеты синкают тренировки с разных устройств; отдаёт данные по REST API с токеном. У нас уже есть частичная интеграция в `services/intervals_icu.py`.
- **wellness** — суточные метрики восстановления (HRV/RMSSD, сон, пульс покоя), которые Intervals отдаёт по эндпоинту `/api/v1/athlete/{id}/wellness`.
- **CTL/ATL/TSB** — стандартные метрики нагрузки; строятся из тренировочной нагрузки активностей (Intervals отдаёт `icu_training_load` на каждую активность — это готовый TSS-эквивалент).
- **handoff** — передача продукта тестеру: инструкция + безопасная первичная настройка, чтобы «другой человек запустил у себя».

## Progress

- [x] (2026-07-22) Разведка текущего состояния: синк Garmin-gated, Intervals читает профиль/события/частично активности, wellness не читается; деплой шага 1 (Docker/Caddy/.env) готов (см. `Surprises & Discoveries`).
- [x] (2026-07-22) Заведён ExecPlan (этот файл). Issues по срезам НЕ заводились — по указанию владельца «сначала только ExecPlan»; заводятся после ревью и выбора scope M1.
- [ ] РЕШЕНИЕ ВЛАДЕЛЬЦА (открыто): scope M1 — вертикальный спайн (активности→план) с wellness в M4, ЛИБО полный первый проход (активности+wellness в M1). См. `Decision Log`.
- [ ] M1: Garmin-free синк активностей из Intervals → CTL/ATL → план виден тестеру.
- [ ] M2: онбординг «подключить Intervals» (source-agnostic) + изоляция БД/секретов + безопасный first-run.
- [ ] M3: проверяемый сценарий handoff (приёмка + тест) + quickstart-инструкция для первого тестера.
- [ ] M4 (follow-up / scope-fork): импорт wellness (HRV/сон/пульс покоя) из Intervals → readiness на `/today` и дашборд у тестера.
- [ ] M5 (follow-up): демоушен Garmin в UI/метках (source-agnostic provenance).

Отметки времени нужны, чтобы видеть темп.

## Surprises & Discoveries

- Observation: весь синк завязан на Garmin-авторизацию. `services/sync.py::sync_garmin_data` первой строкой делает `if not garmin_service.is_authenticated(state): raise ValueError("Не подключен к Garmin Connect")`. Значит тестер без Garmin не синкнется вообще — это и есть барьер №1.
  Evidence: `services/sync.py:238`.

- Observation: Intervals уже частично интегрирован, но ВТОРИЧНО. `services/intervals_icu.py` умеет: `sync_athlete_profile` (FTP/LTHR/вес), `list_race_events` (события для планирования), `push_planned_events` (доставка плана в календарь), и `list_activities` — но «только поля для джойна к локальным активностям», не полный импорт.
  Evidence: `services/intervals_icu.py:166` docstring «Read only the provider fields required to join local completed activities».

- Observation: активности Intervals УЖЕ несут `icu_training_load` (готовый TSS-эквивалент) и `moving_time`. То есть для CTL/ATL и построения плана достаточно расширить набор читаемых полей — считать нагрузку заново не нужно.
  Evidence: `services/intervals_icu.py:174-183` — поля включают `icu_training_load`, `moving_time`, `type`, `start_date_local`.

- Observation: wellness (HRV/сон/пульс покоя) из Intervals НЕ читается. Эндпоинт `/api/v1/athlete/{id}/wellness` не используется. Значит readiness/HRV/сон у тестера без Garmin будут пусты, пока не добавим импорт wellness (M4).
  Evidence: `grep wellness services/intervals_icu.py` — пусто.

- Observation: `sync_athlete_profile` из Intervals УЖЕ вызывается внутри Garmin-синка (`services/sync.py:251`) — то есть профиль тестера подтянется, как только появится любой путь синка.
  Evidence: `services/sync.py:251`.

- Observation: инфраструктура handoff (шаг 1) готова — `docker-compose.yml`, `Dockerfile.api`, `web/Dockerfile`, `deploy/Caddyfile`, `.env.example`, `run_web.sh` на месте; `.env.example` уже содержит `INTERVALS_ICU_API_KEY`/`INTERVALS_ICU_ATHLETE_ID`. Разрыв не в инфре, а в Garmin-free пути синка + онбординге + инструкции.
  Evidence: файлы существуют; `.env.example:37-39`.

## Decision Log

- Decision: Intervals.icu — первичный источник данных для беты; Garmin — вторичный/опциональный.
  Rationale: Intervals покрывает много марок устройств по API-ключу, без хрупкого логина `garminconnect`; это разница между «запустит один владелец» и «запустит любой технический атлет». Согласовано владельцем (см. UI-ExecPlan, [[project-service-readiness]]).
  Date/Author: 2026-07-22 / владелец + Claude Code.

- Decision (ОТКРЫТО — решается владельцем на ревью этого плана): scope первого milestone.
  Вариант A (РЕКОМЕНДУЮ) — **вертикальный спайн**: M1 = только активности из Intervals → CTL/ATL → план виден; wellness (HRV/сон/readiness) — отдельный M4. Кратчайший путь к наблюдаемому «другой атлет запустил и увидел план». `/today` покажет сессию дня и план, но карточки readiness/HRV/сон будут «нет данных», пока не сделан M4 — это честное «частично», а не сломанное.
  Вариант B — **полный первый проход**: M1 включает и wellness, чтобы readiness/дашборд жили у тестера сразу. Больше работы до первой передачи.
  Rationale за A: продукт-барьер — «увидел свой план», а он строится из активностей+профиля; wellness обогащает, но не блокирует «запустил». Меньший срез быстрее проверяем и передаваем.
  Date/Author: 2026-07-22 / Claude Code (рекомендация; финал — за владельцем).

- Decision: не гейтить синк на Garmin. Ввести Garmin-free путь (`sync_intervals_data`) ЛИБО сделать источник выбираемым, не ломая существующий `sync_garmin_data` (он остаётся для владельца).
  Rationale: аддитивно и обратимо; владелец с Garmin продолжает работать как раньше, тестер получает новый путь. Параллельная реализация снижает риск (PLANS.md: additive changes + parallel paths во время миграции).
  Date/Author: 2026-07-22 / Claude Code.

- Decision: секреты (Intervals-токен) — только в `.env`/локальном рантайме тестера; БД тестера — локальный файл (`DATABASE_PATH`), изолированный от чего-либо чужого.
  Rationale: single-tenant локальный запуск совпадает с текущей архитектурой; auth/мультитенант (шаг 2 SaaS) не нужны для технической беты. Никаких токенов в трекаемых файлах.
  Date/Author: 2026-07-22 / Claude Code.

## Outcomes & Retrospective

Заполняется при закрытии milestone'ов. На момент авторинга: выполнена разведка и написан план; scope M1 ждёт решения владельца; реализация M1–M5 предстоит.

## Context and Orientation

Реальное состояние (проверено чтением кода 2026-07-22; читатель может ничего не знать о репозитории).

Синк данных живёт в `services/sync.py`. Единственная точка входа — `sync_garmin_data(state, days=None, on_progress=None)` (строка 228). Она: (1) требует Garmin-авторизации (`garmin_service.is_authenticated(state)`, иначе `raise ValueError`); (2) обновляет athlete-профиль из Intervals (`intervals_icu_service.sync_athlete_profile(database)`, строка 251) — это уже работает и не зависит от Garmin; (3) тянет активности из Garmin (`garmin_service.get_activities_with_error`, строка 269); (4) далее в 5 шагов собирает HRV/сон/health из Garmin. Триггерится синк из веба кнопкой «Синк» → `POST /api/sync` (`api/routers/system.py`, функция `sync`).

Интеграция Intervals живёт в `services/intervals_icu.py`. Класс `IntervalsICUClient` (строка 119) с токен-аутентификацией (`INTERVALS_ICU_API_KEY`, `INTERVALS_ICU_ATHLETE_ID`). Методы: `get_athlete_profile`, `list_race_events`, `list_activities` (строка 166 — сейчас читает только `id, external_id, paired_event_id, start_date_local, type, name, icu_training_load, moving_time`), `list_workout_events`, `push_planned_events`. Модульные функции: `is_configured()`, `connection_info()`, `test_connection()`, `sync_athlete_profile(database)`, `normalize_athlete_profile()`. Важно: активности Intervals уже отдают `icu_training_load` — это TSS-эквивалент, которого достаточно для CTL/ATL и построения плана.

Локальное хранилище — `data/database.py` (`Database`), SQLite. Активности сохраняются через `save_activities(...)`; athlete-профиль — `save_athlete_profile(...)`. Метрики нагрузки (CTL/ATL/TSB) считаются из активностей моделью Banister (`models/banister.py`), план строится `api/planning_service.py::build_plan(db, ..., persist=True)` и читается `get_active_plan(db)`.

Деплой шага 1 (self-hosted Docker, ExecPlan `docs/self_hosted_deployment_execplan.md`): `docker-compose.yml`, `Dockerfile.api`, `web/Dockerfile`, `deploy/Caddyfile`. Локальный запуск без Docker — `./run_web.sh` (FastAPI :8000 + Next :3000). Переменные окружения — `.env` (шаблон `.env.example`): `INTERVALS_ICU_API_KEY`, `INTERVALS_ICU_ATHLETE_ID`, `INTERVALS_ICU_BASE_URL`, `DATABASE_PATH`, а также (для владельца) `GARMIN_EMAIL`/`GARMIN_PASSWORD`.

## Plan of Work

Работа — независимо проверяемые milestone. M1–M3 составляют минимальный handoff (вариант A); M4 добавляет wellness (или вливается в M1 по варианту B); M5 — косметика источника.

Milestone M1 — Garmin-free синк активностей из Intervals. Расширить `IntervalsICUClient.list_activities` (или добавить `list_activities_full`) так, чтобы читать полный набор полей активности, нужный для сохранения локально (дата, тип/спорт, длительность из `moving_time`, `icu_training_load` как TSS, дистанция, средний пульс/мощность если есть). Добавить в `services/sync.py` путь `sync_intervals_data(state, days=None, on_progress=None)`, который НЕ требует Garmin: тянет профиль (уже есть `sync_athlete_profile`) + активности из Intervals и сохраняет их через `database.save_activities(...)` тем же контрактом, что Garmin-путь. Пробросить источник в `POST /api/sync` (`api/routers/system.py`) — параметром `source=intervals|garmin` либо автовыбором «если Garmin не сконфигурирован, а Intervals сконфигурирован → Intervals». Не трогать `sync_garmin_data` (остаётся для владельца). Результат: с одним Intervals-токеном (без Garmin) синк наполняет активности, `build_plan` строит план, `/planning` и `/today` показывают его.

Milestone M2 — онбординг и изоляция. Сделать кнопку синка и статус подключения source-agnostic: сейчас кнопка подписана «Синхронизировать с Garmin Connect» (`web/app/dashboard/page.tsx`), а онбординг предлагает только Garmin/демо. Показать статус Intervals (`connection_info()`/`test_connection()`), дать понятный first-run «подключите Intervals: токен + athlete_id → синк». Убедиться, что токен читается только из `.env`/рантайма, а БД тестера — локальный файл (`DATABASE_PATH`), изолированный; демо-режим (готов) остаётся безопасной песочницей до первого реального синка.

Milestone M3 — проверяемый сценарий и инструкция. Оформить приёмку «клонировал → вписал токен в .env → поднял (`./run_web.sh` или `docker compose up`) → нажал синк → увидел план». Где возможно — автотест (напр. smoke, дергающий `sync_intervals_data` на замоканном Intervals-ответе и проверяющий, что активности сохранились и план строится). Написать короткий `docs/` quickstart для первого технического тестера (шаги, где взять Intervals API-ключ и athlete_id, что нажать, что должен увидеть).

Milestone M4 — wellness из Intervals (follow-up или часть M1 по варианту B). Добавить чтение `/api/v1/athlete/{id}/wellness` в `IntervalsICUClient` и сохранение HRV/сна/пульса покоя в локальную БД тем же контрактом, что Garmin-wellness. Тогда `/today` readiness и дашборд-карточки (Сон/HRV) оживают у тестера.

Milestone M5 — демоушен Garmin в UI (follow-up). Метки провенанса («оценка · Garmin») и тексты сделать source-agnostic; Garmin — как опциональный вторичный источник в онбординге.

## Concrete Steps

Все команды — из корня репозитория. Локальный запуск: `./run_web.sh` (FastAPI :8000 + Next :3000). Смоук: `source ai_trainer_env/bin/activate && python -m pytest -m "not live and not debug" tests/` (базовая линия на момент авторинга — 1039 passed).

Ручная проверка сценария handoff (после M1–M3), эмулируя тестера без Garmin: в `.env` задать только `INTERVALS_ICU_API_KEY` и `INTERVALS_ICU_ATHLETE_ID` (Garmin-переменные пусты), поднять `./run_web.sh`, в вебе нажать синк (source=intervals), затем открыть `/planning` — ожидается построенный план по своим активностям; `/today` — сессия дня.

Точные команды и транскрипты добавляются по мере реализации каждого milestone.

## Validation and Acceptance

Приёмка — как наблюдаемое поведение.

M1: при заданном только Intervals-токене (Garmin не сконфигурирован) `POST /api/sync` (source=intervals) наполняет `activities`; после этого `build_plan`/`get_active_plan` дают активный план; `/planning` и `/today` показывают его. Смоук зелёный; браузерная проверка на изолированной БД.

M2: в вебе видно подключение Intervals и source-agnostic синк; first-run понятен без Garmin; токен не в трекаемых файлах; демо-режим не затрагивает реальную БД.

M3: свежая копия репозитория + только Intervals-токен → по quickstart-инструкции тестер за N шагов видит свой план. Автотест (если добавлен) падает до реализации и проходит после.

M4: с wellness `/today` readiness и карточки Сон/HRV населены у тестера из Intervals-данных.

## Idempotence and Recovery

Синк идемпотентен по построению (upsert активностей по id, как в Garmin-пути). Новый путь `sync_intervals_data` — аддитивный; `sync_garmin_data` не трогается, откат = не вызывать новый путь. Секреты только в `.env` (не в git). БД — локальный файл; для тестов/приёмки использовать временный `DATABASE_PATH`, чтобы не трогать рабочую базу. Ветки/worktree — по правилу репо (issue → ветка → PR).

## Artifacts and Notes

Карта «что есть / чего нет» для Intervals как источника (из разведки 2026-07-22):

    Профиль (FTP/LTHR/вес)   ЕСТЬ   sync_athlete_profile (вызывается уже в Garmin-синке)
    События гонок            ЕСТЬ   list_race_events (планирование)
    Доставка плана           ЕСТЬ   push_planned_events (в календарь Intervals)
    Активности (джойн)       ЧАСТИЧНО list_activities — только поля для матчинга
    Активности (полный импорт) НЕТ  → M1 (расширить поля + сохранить локально)
    Garmin-free путь синка   НЕТ    → M1 (sync_intervals_data)
    Wellness (HRV/сон/RHR)   НЕТ    → M4 (эндпоинт /wellness)
    Онбординг без Garmin     НЕТ    → M2
    Quickstart тестера       НЕТ    → M3

## Interfaces and Dependencies

В `services/intervals_icu.py`, расширить чтение активностей (M1). Либо доработать `list_activities`, либо добавить:

    def list_activities_full(self, oldest: date, newest: date) -> List[Dict[str, Any]]:
        # тот же GET /api/v1/athlete/{id}/activities, но полный набор полей:
        # date (start_date_local), sport (type), duration (moving_time),
        # tss (icu_training_load), distance, avg_hr, avg_power, ...
        ...

В `services/sync.py`, добавить Garmin-free путь (M1):

    def sync_intervals_data(
        state: StateManager,
        days: int | None = None,
        on_progress: SyncProgressCallback | None = None,
    ) -> SyncResult:
        # НЕ требует Garmin. Тянет sync_athlete_profile + активности из Intervals,
        # сохраняет через database.save_activities(...) тем же контрактом.
        ...

В `api/routers/system.py`, `POST /api/sync` — пробросить источник (M1): параметр `source: "intervals" | "garmin"` или автовыбор по конфигурации. Не менять существующий `sync_garmin_data`.

В `services/intervals_icu.py`, wellness (M4):

    def list_wellness(self, oldest: date, newest: date) -> List[Dict[str, Any]]:
        # GET /api/v1/athlete/{id}/wellness — HRV/сон/пульс покоя, сохранить
        # тем же контрактом, что Garmin-wellness (save_hrv_data/sync_sleep_data/
        # sync_daily_health).
        ...

Зависимости: используем стандартный Intervals REST (токен `INTERVALS_ICU_API_KEY`, `INTERVALS_ICU_ATHLETE_ID`), уже поднятый в `IntervalsICUClient`. Никаких новых внешних библиотек. Deploy — существующий Docker/Caddy шага 1.

---

Изменение (2026-07-22): документ создан по итогам разведки data-слоя после закрытия UI-консолидации. Причина — следующий продуктовый барьер не UI, а «другой атлет запускает AI Trainer на своих данных»: синк сейчас Garmin-gated, Intervals вторичен. План строит Garmin-free путь из Intervals (первичный источник) + онбординг + handoff-инструкцию. Scope первого milestone (вертикальный спайн vs полный проход с wellness) оставлен как открытое решение владельца в `Decision Log` — по указанию «сначала только ExecPlan». Issues по срезам заводятся после ревью.
