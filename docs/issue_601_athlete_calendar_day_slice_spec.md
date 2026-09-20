# Slice Spec — Issue #601: календарный день атлета в планировщике

- Issue / PR: #601 / (PR открывается этим слайсом)
- Author / checker / merge owner: Domain / API Implementer (DSH) / независимый checker — TBD / human merge owner (rbctmz)
- Date: 2026-09-20
- Candidate head SHA: TBD
- Parent: #607 (Daily decision loop v1), шаг 0 «Truth prerequisites»

## Change Class

- Class: **B — Standard**
- Rationale: дефект в существующем доменном решении. Публичный контракт не
  меняется: `athlete_local_date()` при дефолтной конфигурации возвращает ту же
  дату, что и host clock, поэтому поведение меняется только там, где
  `ATHLETE_TIMEZONE` расходится с зоной хоста. Нет миграций, нового
  persistent state, live-provider записи и новых архитектурных границ.
- Automatic escalation triggers checked: все шесть проверены, ни один не
  срабатывает (нет schema/persistence, identity/provenance, live-записи,
  security, необратимых действий и новых cross-module контрактов).
- Review budget used: 0 / 2
- Review trigger mode: manual

## Scope

Шесть сайтов в `api/planning_service.py` принимают решение о **календарном дне
атлета** и берут дату из host clock. Все шесть переводятся на уже существующий
канонический хелпер `utils.athlete_time.athlete_local_date()` (issue #577),
который в этом модуле уже импортирован и применён к якорю метрик в #599.

| Строка | Функция | Решение |
| --- | --- | --- |
| 452 | `_start_week` | начало недели атлета |
| 496 | `current_status` | окно активных ограничений `[today, today+30]` |
| 1035 | `active_plan_overview` | сегодняшний день атлета |
| 1371 | `build_plan` → `apply_race_event_overlays(as_of=...)` | `days_until` до старта; от него зависят тейпер и гоночная неделя |
| 1987 | `week_by_week_plan` | сегодняшний день атлета |
| 2514 | `_refresh_match_recovery` | окно восстановления |

## Non-goals

- **Не трогаем** `datetime.now().isoformat()` на строках 1488, 3397, 3543: это
  метки времени ревизии плана, а не календарный день атлета. Замена их на
  атлетскую дату была бы ошибкой.
- Не меняем `models/ai_tools.py` и `models/readiness.py` — там канон уже применён.
- Не вводим новых абстракций: хелпер существует, задача — привести к нему потребителей.
- Не аудируем остальные модули (ingest, api/routers) — отдельная задача.
- Po default-конфигурации (зоны совпадают) наблюдаемое поведение не меняется.

## Definition of Done

- [x] Acceptance criteria наблюдаемы.
- [x] Named checks: `ruff check .`, focused-тест `tests/smoke/test_planning_athlete_calendar.py`,
      contributor-safe набор.
- [ ] Merge и cleanup owner назначен.

## Public Contracts

| Contract | Status | Evidence |
| --- | --- | --- |
| API DTO планирования | unchanged — форма и типы те же | `tests/smoke/test_api_dashboard.py`, contract extractor |
| `api.planning_service.*` (внутренний Python) | changed compatibly — только источник даты | focused-тест |
| `web/lib/types.ts` | unchanged | `npm --prefix web run contract:extract -- --check` |

## Failure, Reset, Rollback, Idempotency

- Failure modes: недоступный `ATHLETE_TIMEZONE` → хелпер падает на дефолт
  `Europe/Moscow`; поведение остаётся детерминированным.
- Новое persistent state не добавляется; полный reset не требуется.
- Rollback: revert коммита; данные не менялись.

## Evidence Boundary Matrix

| Identity | Time/provenance | Evidence state | Fallback | Expected result / falsifier |
| --- | --- | --- | --- | --- |
| n/a | зоны хоста и атлета совпадают | present | allowed | поведение идентично прежнему |
| n/a | атлетский день впереди host на сутки | present | allowed | начало недели и окна сдвигаются на атлетский день |
| n/a | `ATHLETE_TIMEZONE` не задан | missing | fail closed | дефолт `Europe/Moscow`, исключения нет |

## RED Matrix

| Acceptance criterion / invariant | RED test | Expected failure до фикса | GREEN evidence |
| --- | --- | --- | --- |
| AC1: все решения об атлетском дне берут дату из `athlete_local_date()` | `test_start_week_follows_athlete_calendar` | начало недели считается от host-дня | понедельник атлетского дня |
| AC1: то же для окна ограничений | `test_current_status_constraint_window_follows_athlete_calendar` | окно начинается с host-дня | окно начинается с атлетского дня |
| AC2: в модуле не остаётся host-clock границ | `test_no_host_clock_athlete_boundaries_remain` | 6 совпадений `datetime.now().date()` / `date.today()` | 0 совпадений |
| AC4: при совпадении зон поведение не меняется | `test_matching_timezones_keep_behavior` | (зелёный до и после) | значения совпадают |

## Global Constraints (родительский #607)

- `ASR-REL-2`: отсутствие/недоступность таймзоны не приводит к неопределённому
  результату — есть детерминированный дефолт.
- `ASR-MOD-2`: решение принимается в Python, а не в браузере.
- `ADR-0001`: правка в shared Python; Streamlit своей копии логики не получает.