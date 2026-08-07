# Личные рекорды / power curve в карточке (#382)

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds. Maintain this document in accordance with `.agent/PLANS.md` from the repository root.

## Purpose / Big Picture

Закрывает gap #3/4 из `docs/competitive_analysis_intervalcoach.md` (power curve / eFTP / rider profile) и шаг 4 из #379: личные рекорды прямо в карточке тренировки — лучшая 5-сек, пиковая минута, 20-минутка и т.д. (как в Blocks/IntervalCoach «best efforts»). Без этого атлет не видит, побил ли он рекорд, а AI-тренер не имеет «профиль райдера».

**Ключевое решение спайка (2026-08-07):** строим **гибрид** (тот же паттерн, что TSS и интервалы в #390) — Intervals.icu первичный источник (готовые `best-efforts` / `power-curves` эндпоинты), локальный расчёт mean-max из стрима watts — фолбэк для активностей без Intervals-линка. Свой детектор не строим: провайдер уже считает кривые с контекстом устройства и многолетними данными.

После этого клина: клиент читает готовые best-efforts и power curve; нормализатор приводит ответ к компактной структуре; компактный результат кэшируется в SQLite при открытии карточки; карточка показывает блок «Рекорды» (5s/1min/5min/20min/60min against all-time best). Полные стримы в БД не копятся — фолбэк-расчёт on-demand по `streams.json`.

## Progress

- [x] (2026-08-07) Спайк. Все три эндпоинта подтверждены живыми запросами на `i172121399` (cycling) и `i172399181` (open_water_swimming, edge-case). Формы ответов зафиксированы ниже в Surprises. Обнаружен и пофиксен баг контракта `get_activity_streams` из #390 (ответ — list, не mapping): PR #392.
- [x] (2026-08-07) ExecPlan создан.
- [x] (2026-08-07) Milestone 1: клиентские методы + `IntervalsICUError.status_code` + контрактные тесты. Live-verified на cycling/swim (422→empty).
- [x] (2026-08-07) Milestone 2: нормализаторы (`models/best_efforts.py`, `models/power_curve.py`) + кэш `activity_power_curves` (ActivityStore + Database фасады) + тесты. Live-verified: cycling → 198/155/150/134/None W на 5s/1min/5min/20min/60min.
- [x] (2026-08-07) Milestone 3: сервис `fetch_activity_power_curve` (fetch-on-demand, фолбэк на кэш/None) + поле `power_curve` в карточке API + тесты.
- [x] (2026-08-07) Milestone 4 (пересмотрен): `MetricsCalculator.mean_max_power` добавлен как утилитный метод (локальная power curve из стрима watts). **Интеграция в сервис отложена** — без персистенции стримов (#390 decision) фолбэк не имеет источника данных для Garmin-only активностей (см. Decision Log). Метод пригодится в #383.
- [ ] Milestone 5: web-блок «Рекорды».
- [ ] Полный smoke + ruff + web lint/build; мердж PR (решает #382).

## Surprises & Discoveries

Подтверждено живыми запросами 2026-08-07 (key настроен, cycling `i172121399` 45min + swimming `i172399181`):

- Observation: **`GET /api/v1/activity/{id}/best-efforts`** — простая форма. Параметры: `stream` (watts/heartrate/...), `duration` (секунды), `count`.
  Evidence (200, `stream=watts&duration=60&count=3`):
  ```json
  {"efforts": [{"start_index": 2151, "end_index": 2211, "average": 155.71666, "duration": 60, "distance": null}, ...]}
  ```
  `count` — верхняя граница: при `duration=1200` в 45min-активности вернулся **1** effort (фактическое ≤ count). `distance` — null для watts/heartrate. Работает и для `heartrate`.

- Observation: **`best-efforts` возвращает 422 как «нет данных», а не 5xx-ошибку.** Это критически важный паттерн, новый относительно #390.
  Evidence:
  - Нет параметров → 422 `{"status":422,"error":"Stream [fixed_watts] not on activity"}` (дефолтный stream отсутствует).
  - Несуществующий stream → 422 `{"status":422,"error":"Invalid stream type [nonexistent]"}`.
  - Stream есть, но запрошен другой (swim-активность, `stream=watts`) → 422 `Stream [fixed_watts] not on activity`.
  → Вывод: клиент должен отличать 422 (нормальный «нет power-данных» → нет рекордов, не ошибка) от 5xx (сбой провайдера → кэш/фолбэк).

- Observation: **`GET /api/v1/activity/{id}/power-curves`** — богатый объект. Без параметров (суффикс `.json` опционален). Ответ — список из 1 объекта (PowerCurve):
  ```python
  [{"id": "i172121399", "stream_type": "watts", "weight": 95.4,
    "secs":   [1, 2, ..., 60, 65, ..., 2700],   # 135 стандартных длительностей
    "values": [234, 230, ..., 112],              # = watts, пиковая мощность на каждой длительности
    "watts":  [...],                             # дубликат values
    "watts_per_kg": [2.45, ...],                 # values / weight
    "start_index": [...], "end_index": [...],    # где в записи достигнут пик
    "vo2max_5m": 30.55, "compound_score_5m": 235.85,
    # null/0 для одиночной активности: submax_values, powerModels, ranks, percentile
   }]
  ```
  135 точек по фиксированной шкале Intervals.icu (плотнее на коротких, реже на длинных). На активности без power → `[]` (200, пусто).

- Observation: **`streams.json` — СПИСОК объектов, не словарь.** Ответ: `[{type, name, data, valueType, valueTypeIsArray, allNull, anomalies, custom, data2}, ...]`. `?types=watts` фильтрует список (1 элемент).
  Evidence: противоречит ExecPlan #390 (там утверждалось `Dict[str, list]`). Баг зафиксирован и пофиксен в PR #392 (контракт `get_activity_streams`).

- Observation: edge-case (swim-активность без power) корректен: `streams.json` отдаёт `time/cadence/heartrate/distance/latlng/velocity_smooth/temp` (нет watts); `power-curves` → `[]`; `best-efforts?stream=watts` → 422. Карточка должна показывать «рекорды недоступны», а не падать.

- Observation: «all-time best» для #382 — это агрегация power-curves по всем активностям атлета. Intervals.icu хранит её на уровне **athlete**, а не activity (поле `ranks` в power-curve, null для одиночной активности). Первый клин показывает best-efforts **данной активности** + пиковую мощность на ключевых длительностях; all-time best и «genuine efforts count»-фильтр (отсев дрейфа измерений / новой дистанции из IC-спецификации) — отдельный follow-up, не блокирует acceptance #382.

## Decision Log

- Decision: **гибрид** — Intervals.icu первичный источник, локальный mean-max — фолбэк для активностей без Intervals-линка (как TSS и интервалы #390).
  Rationale: минимум работы, лучшее качество детекции; не отламывает Garmin-only активности.
  Date/Author: 2026-08-07 / Codex.
  Update (2026-08-07): **интеграция локального фолбэка в сервис отложена.** В текущей архитектуре стримы не персистятся (#390 decision), а `get_activity_streams` требует Intervals-id — значит для Garmin-only активностей (нет линка) нет источника watts-стрима. В БД таких power-активностей практически нет (1 multi_sport). `MetricsCalculator.mean_max_power` оставлен как утилитный метод (полезен в #383, где стримы тянутся для авто-детекта); подключение к карточке — после решения о персистенции стримов.



- Decision: клиент **отличает 422 от 5xx**. 422 («Stream not on activity») → структурированный «нет данных» (None/empty, не raise). 5xx/сеть → кэш или фолбэк (как #390).
  Rationale: 422 — нормальное состояние для активностей без power (плавание/бег); raise ломал бы карточку.
  Date/Author: 2026-08-07 / Codex.

- Decision: кэшируем компактную power-curve (одна строка JSON на активность), не полные стримы. Best-efforts тянутся on-demand для избранных длительностей (5s/1min/5min/20min/60min).
  Rationale: объём; стримы — только источник для фолбэк-расчёта.
  Date/Author: 2026-08-07 / Codex.

- Decision: первый клин — best-efforts/peaks **данной активности** + пиковая мощность. All-time best, «genuine efforts count»-фильтр, rider profile/eFTP — follow-up (не блокируют acceptance #382).
  Rationale: скоуп; acceptance требует «видны лучшие усилия против all-time best» — all-time агрегируется на втором этапе из уже закэшированных per-activity кривых.
  Date/Author: 2026-08-07 / Codex.

## Context and Orientation

- Клиент Intervals.icu — `services/intervals_icu.py` (`IntervalsICUClient`, basic-auth, `_request_json`; fail-closed). Связь «каноническая активность ↔ Intervals id» — `activity_provider_links` (`provider='intervals'`).
- Карточный кластер persistence — `data/activity_store.py` (ActivityStore, TD-006; `Database` делегирует фасадами). `activity_intervals` из #390 — референсный паттерн для кэша.
- Карточку отдаёт `api/routers/activities.py` (`get_activity_card`), web-карточка — `web/app/activities/page.tsx` (модалка `ActivityCardModal`), типы — `web/lib/types.ts`.
- Локальные расчёты мощности — `utils/metrics.py` (`MetricsCalculator`: NP/IF/TSS/CTL/ATL/TSB; pandas/numpy). Сюда ляжет mean-max curve для фолбэка.
- `services/activity_intervals.py` — референсный fetch-on-demand-сервис с фолбэком на кэш (#390).
- Проверка без сети: autouse-фикстура `tests/conftest.py` обнуляет `Settings.INTERVALS_ICU_API_KEY` → `is_configured()=False`.

## Plan of Work

### Milestone 1: клиент + контрактные тесты (RED→GREEN)

В `services/intervals_icu.py`:
- `IntervalsICUClient.get_activity_best_efforts(activity_id, stream="watts", duration, count=1)` — `GET /api/v1/activity/{id}/best-efforts`. **422 → вернуть `{"efforts": []}` (или None), не raise**; 200-не-mapping → `IntervalsICUError` (fail-closed).
- `IntervalsICUClient.get_activity_power_curve(activity_id)` — `GET /api/v1/activity/{id}/power-curves`. 200-не-list → `IntervalsICUError`; пустой список → `[]`.
- Модульные обёртки `get_activity_best_efforts(...)` / `get_activity_power_curve(activity_id)`.
- Для 422 нужно либо расширить `_request_json` (различение HTTP-кодов), либо новый низкоуровневый хелпер. Решается в milestone (предпочесть минимальное изменение).

Тесты `tests/smoke/test_best_efforts.py` (новый): пути/параметры, fail-closed на не-mapping/не-list, **422→empty**, пустой список power-curves.

### Milestone 2: нормализаторы + кэш

В `models/best_efforts.py` (новый, чистый):
- `normalize_best_efforts_payload(payload)` → компактный dict (fail-closed как `normalize_intervals_payload`): избранные efforts + мета.
В `models/power_curve.py` (новый, чистый):
- `normalize_power_curve_payload(payload)` → компактный dict: `secs` + `values` + `watts_per_kg` + `weight` + ключевые summary (vo2max_5m/compound_score_5m). Округления.

В `data/activity_store.py`:
- DDL: `activity_power_curves (activity_id TEXT PRIMARY KEY, curve_json TEXT NOT NULL, fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)`.
- Методы `save_activity_power_curve` / `get_activity_power_curve` (как intervals). Фасады `Database`.

### Milestone 3: сервис + API

В `services/best_efforts.py` (новый):
- `fetch_activity_best_efforts(db, activity_id, client=None)` — резолв Intervals-id; нет/не настроено → кэш/None; fetch → normalize → cache; 422/5xx → кэш/None.
- `fetch_activity_power_curve(...)` — аналогично.

В `api/routers/activities.py`: поля `best_efforts` и `power_curve` в `get_activity_card`.

### Milestone 4: гибридный фолбэк

В `utils/metrics.py`:
- `MetricsCalculator.mean_max_power(power_data, durations_secs=(5,60,300,1200,3600))` — локальная power curve из стрима watts (rolling max average). Если нет Intervals-линка — сервис считает из `streams.json?types=watts → data`.
- Решение: фолбэк включается только при отсутствии Intervals-линка (как `match_status`-дискуссия в #390). При наличии — всегда провайдер.

### Milestone 5: web

В `web/lib/types.ts`: `ActivityBestEffort` / `ActivityPowerCurve`, поля в `Activity`.
В `web/app/activities/page.tsx`: блок «Рекорды» — пиковая мощность на 5s/1min/5min/20min/60min + best-efforts-строки, или «Рекорды недоступны». Fetch-on-demand при открытии модалки (как intervals в #390).

## Verification

- `python3 -m pytest tests/smoke/test_best_efforts.py -q`
- `python3 -m pytest tests/smoke -q` (без регрессии)
- `python3 -m ruff check services/intervals_icu.py services/best_efforts.py models/best_efforts.py models/power_curve.py data/activity_store.py api/routers/activities.py utils/metrics.py tests/smoke/test_best_efforts.py`
- `npm --prefix web run lint` и `npm --prefix web run build`
- Живая проверка (если key настроен, вне smoke): best-efforts + power-curves на cycling-активности; 422 на swim-активности.

## Outcomes & Retrospective

(заполняется по мере выполнения milestones)
