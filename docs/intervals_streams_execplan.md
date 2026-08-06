# Интервалы и стримы из Intervals.icu — фундамент для авто-детекта интервалов и power curve (#390)

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds. Maintain this document in accordance with `.agent/PLANS.md` from the repository root.

## Purpose / Big Picture

Intervals.icu — **первичный** источник данных (Garmin — compatibility-путь). Сейчас мы храним только суммарные поля активности и «слепы» к структуре выполненной работы: нет ни лапов/интервалов, ни потоков (power/HR-серий). Из-за этого не реализуемы #383 (авто-детект интервалов, «план vs факт») и #382 (личные рекорды / power curve).

После этого клина: клиент умеет читать готовые интервалы (`GET /api/v1/activity/{id}?intervals=true`) и стримы (`GET /api/v1/activity/{id}/streams.json?types=...`); нормализатор превращает ответ в компактную структуру репетиций; компактный результат кэшируется в SQLite (`activity_intervals`) при открытии карточки активности; карточка показывает структуру (репетиции/восстановление). Полные стримы в БД не копим — они нужны только для power curve (#382) и тянутся on-demand.

Ключевое решение спайка: **свой детектор интервалов не строим** — Intervals.icu уже детектит интервалы (лапы/пары), мы потребляем результат. Тот же паттерн, что с TSS: берём `icu_training_load`, а не пересчитываем локально.

## Progress

- [x] (2026-08-06) Спайк. Эндпоинты подтверждены официальной OpenAPI-спецификацией (`https://intervals.icu/api/v1/docs`, v1.0.0) и форумом: интервалы — `GET /api/v1/activity/{id}?intervals=true` (или `/intervals`) → `IntervalsDTO` с `icu_intervals`/`icu_groups`; стримы — `GET /api/v1/activity/{id}/streams.json?types=watts` → объект «имя стрима → массив значений». Отдельно подтверждены готовые `best-efforts` и `power-curves` эндпоинты для #382.
- [x] (2026-08-06) Создан issue #390.
- [x] (2026-08-06) ExecPlan создан; прочитаны `services/intervals_icu.py`, `data/activity_store.py`, `data/database.py` (схема `activity_provider_links`), `api/routers/activities.py`, `web/app/activities/page.tsx`, `web/lib/types.ts`.
- [x] (2026-08-06) Milestone 1: клиент (`get_activity_intervals` / `get_activity_streams`) + чистый нормализатор `models/activity_intervals.py` + контрактные тесты (19 passed).
- [x] (2026-08-06) Milestone 2: кэш-таблица `activity_intervals` + резолв Intervals-id через provider-links + сервис fetch-on-demand с фолбэком на кэш + поле `intervals` в карточке API.
- [x] (2026-08-06) Milestone 3: web-секция «Структура тренировки» в карточке; ESLint и production build зелёные.
- [x] (2026-08-06) Полный smoke — 1526 passed, 1 skipped (socket preflight); ruff чистый.
- [ ] Мердж PR (решает #390); затем #383 (план vs факт в карточке) и #382 (power curve / best efforts).

## Surprises & Discoveries

- Observation: у Intervals.icu есть **готовый** эндпоинт интервалов, отдельный от «всей активности».
  Evidence: OpenAPI v1.0.0 — `GET /api/v1/activity/{id}/intervals` → `IntervalsDTO {id, analyzed, icu_intervals: Interval[], icu_groups: IntervalGroup[]}`; `GET /api/v1/activity/{id}` принимает query `intervals=true` («Include interval data»). Forum 126341 подтверждает `?intervals=true`.
- Observation: поле `Interval` из коробки несёт всё нужное для «структуры» — `start_index`, `moving_time`, `elapsed_time`, `distance`, `average_heartrate`, `average_watts`, `average_cadence`, `zone`, `training_load`, `average_speed`.
  Evidence: `#/components/schemas/Interval` в официальной спецификации.
- Observation: для #382 Intervals.icu уже считает best efforts и power curves на сервере.
  Evidence: `GET /api/v1/activity/{id}/best-efforts?stream=watts&duration=1200&count=8` → `{efforts: [{start_index, end_index, average, duration, distance}]}`; `GET /api/v1/activity/{id}/power-curves{ext}` → `PowerCurve[]` с `secs`/`values`. Это может удешевить #382 (вопрос — считаем ли локально по стримам или потребляем серверные кривые; решается в #382, не в этом клине).
- Observation: стримы в OpenAPI описаны только для PUT (`UpdateStreamsResult`), но GET подтверждён форумом и используется веб-приложением.
  Evidence: forum 101065 — `GET /api/v1/activity/{id}/streams.json` (+ фильтр `?types=watts`, `.csv` для CSV). Формат ответа — объект, где ключ = имя стрима (`watts`, `heart_rate`, `cadence`, `time`, …), значение = массив.
- Observation: у локальной канонической активности нет поля «Intervals id» — он живёт в `activity_provider_links` (`provider='intervals'`, `provider_activity_id`).
  Evidence: `data/database.py` схема `activity_provider_links`; `services/activity_ingest.py::_normalize_intervals` создаёт link с `provider="intervals"` и `provider_activity_id=intervals_id`. Для Garmin-only активностей Intervals-id нет → интервалы корректно недоступны.
- Observation: GET-стримы не обязаны иметь одинаковую длину/ключи во всех активностях; нормализатор и UI должны быть устойчивы к отсутствию стрима (например, нет `watts` у плавания).
  Evidence: `stream_types` в списке активностей меняется от активности к активности (`heartrate`, `watts`, `cadence`, …).

## Decision Log

- Decision: свой детектор интервалов не строим; интервалы ингестим из Intervals.icu (`?intervals=true`), как `icu_training_load`.
  Rationale: Intervals.icu уже детектит интервалы/лапы; дублировать детектор — дорого и хуже по качеству (у них есть контекст устройства и многолетние данные).
  Date/Author: 2026-08-06 / Codex.
- Decision: в БД храним компактную структуру репетиций (`activity_intervals`, одна строка на активность, JSON), а не полные стримы.
  Rationale: объём; стримы нужны только для power curve (#382) и тянутся on-demand; карточке нужна структура, а не сырые массивы.
  Date/Author: 2026-08-06 / Codex.
- Decision: fetch-on-demand при открытии карточки с кэшем; при сбое сети/провайдера отдаём кэш, иначе `null` (карточка не падает).
  Rationale: карточка должна открываться офлайн/при недоступном провайдере; интервалы — обогащение, не блокер.
  Date/Author: 2026-08-06 / Codex.
- Decision: `streams`-метод добавляем в клиент сейчас (контракт), но в карточку и БД не вшиваем — он задействуется в #382.
  Rationale: фундамент issue #390 покрывает оба эндпоинта; включать power curve сейчас — разрастание скоупа.
  Date/Author: 2026-08-06 / Codex.

## Context and Orientation

Активности лежат в SQLite (`activities`), список и карточку отдаёт `api/routers/activities.py` (`list_activities` / `get_activity_card`), web-карточка — `web/app/activities/page.tsx` (модалка `ActivityCardModal`), типы — `web/lib/types.ts` (`Activity`). Persistence карточного кластера — `data/activity_store.py` (ActivityStore, TD-006; `Database` делегирует фасадами).

Клиент Intervals.icu — `services/intervals_icu.py` (`IntervalsICUClient`, basic-auth, `_request_json`; fail-closed: не-JSON → `IntervalsICUError`, не-список в `list_activities` → ошибка). Связь «каноническая активность ↔ Intervals id» — таблица `activity_provider_links` (`provider='intervals'`, `provider_activity_id`).

Проверка без сети: autouse-фикстура `tests/conftest.py` обнуляет `Settings.INTERVALS_ICU_API_KEY` → `is_configured()=False`, клиент не ходит в сеть.

## Plan of Work

### Milestone 1: клиент + нормализатор (RED→GREEN)

В `services/intervals_icu.py`:
- `IntervalsICUClient.get_activity_intervals(activity_id)` — `GET /api/v1/activity/{id}?intervals=true`, fail-closed: не-mapping → `IntervalsICUError`.
- `IntervalsICUClient.get_activity_streams(activity_id, types=None)` — `GET /api/v1/activity/{id}/streams.json`, необязательный `types` (строка через запятую), fail-closed: не-mapping → `IntervalsICUError`.
- Модульные обёртки `get_activity_intervals(activity_id)` / `get_activity_streams(activity_id, types=None)` (как `list_race_events`).

В `models/activity_intervals.py` (новый, чистый):
- `normalize_intervals_payload(payload)` → компактный dict: `analyzed`, `intervals` (выбранные поля: `start_index`, `moving_time`, `elapsed_time`, `distance`, `average_watts`, `average_heartrate`, `average_cadence`, `zone`, `training_load`, `average_speed`, `min_heartrate`, `max_heartrate`), `groups`. Не-mapping/не-список `icu_intervals` → fail-closed `ValueError`; отсутствие ключа → пустой список.
- Тесты `tests/smoke/test_activity_intervals.py`: нормализация, округления, fail-closed, пустой payload, клиентские методы (stub `_request_json`).

### Milestone 2: кэш + резолв + сервис + API

В `data/activity_store.py`:
- DDL в `create_activity_card_tables`: `activity_intervals (activity_id TEXT PRIMARY KEY, intervals_json TEXT NOT NULL, fetched_at TEXT NOT NULL)`.
- Методы `ActivityStore.save_activity_intervals(activity_id, intervals: dict)`, `get_activity_intervals(activity_id) -> dict | None`, `get_intervals_provider_activity_id(canonical_activity_id) -> str | None` (запрос по `activity_provider_links`).
- Фасады `Database` (как для tags/notes).

В `services/activity_intervals.py` (новый):
- `fetch_activity_intervals(db, activity_id, client=None) -> dict | None` — резолв Intervals-id; если нет/не настроено → кэш или `None`; иначе fetch → normalize → cache → отдать. Ошибки клиента → кэш или `None`.

В `api/routers/activities.py`:
- `get_activity_card` добавляет `item["intervals"]`.

### Milestone 3: web

В `web/lib/types.ts`: `ActivityInterval`/`ActivityIntervals`, поле `intervals` в `Activity`.
В `web/app/activities/page.tsx`: при открытии модалки — `GET /api/activities/{id}` (обновляет интервалы), секция «Структура тренировки»: компактные строки `#N · длительность · дистанция · HR · зона` или «Интервалы недоступны».

## Verification

- `python3 -m pytest tests/smoke/test_activity_intervals.py -q`
- `python3 -m pytest tests/smoke -q` (базелайн 1507 passed, 1 skipped; без регресса)
- `python3 -m ruff check services/intervals_icu.py services/activity_intervals.py models/activity_intervals.py data/activity_store.py api/routers/activities.py tests/smoke/test_activity_intervals.py`
- `npm --prefix web run lint` и `npm --prefix web run build`

## Outcomes & Retrospective

2026-08-06: фундамент #390 реализован. Клиент читает интервалы (`?intervals=true`) и стримы (`streams.json`), нормализатор приводит ответ к компактной структуре (fail-closed), компактный результат кэшируется в `activity_intervals` при открытии карточки, карточка API и web показывают «Структуру тренировки» (репетиции/восстановление) с фолбэком на кэш/`null` при сбое провайдера. Полные стримы в БД не пишутся — они задействуются в #382. Smoke: 1526 passed, 1 skipped; ruff/ESLint/build зелёные.
