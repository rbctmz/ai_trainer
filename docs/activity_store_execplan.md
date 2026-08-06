# Первый churn-first срез TD-006: ActivityStore для кластера активности

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

This document must be maintained in accordance with `.agent/PLANS.md` at the repository root.

## Purpose / Big Picture

`data/database.py` (4330 строк) концентрирует churn: за последние 50 коммитов его трогали 50 раз, а свежий кластер активности (карточка тренировки #379) снова добавил в него методы. Цель этого среза — вынести связный кластер «карточка активности» (чтение одной активности, теги, заметка тренера) в отдельный store-модуль по уже утверждённому паттерну `data/athlete_profile_store.py`, оставив публичные методы `Database` тонкими фасадами. Поведение не меняется; связанность `database.py` уменьшается измеримо (минус ~160 строк и 8 методов), а для следующих срезов появляется готовый образец.

Проверить работу можно так: `python -m pytest tests/smoke/test_activity_card.py tests/smoke/test_threshold_drift.py -q` зелёные (те же контракты через фасады), полный smoke не регрессирует, `wc -l data/database.py` уменьшился.

## Progress

- [x] (2026-08-06) Создан ExecPlan; прочитан эталон `data/athlete_profile_store.py`, измерен churn `data/database.py` (50/50 коммитов, activity-card кластер — самый свежий).
- [x] (2026-08-06) Milestone 1: создан `data/activity_store.py` (ACTIVITY_COLUMN_ORDER, create_activity_card_tables, ActivityStore); DDL карточных таблиц переехала туда; `database.py` реэкспортирует константу и делегирует 8 методов.
- [x] (2026-08-06) Milestone 2: фокусные тесты 91 passed (карточка, thresholds, readiness, recovery loop, planning, TSS reconciliation); ruff чист.
- [x] (2026-08-06) Milestone 3: полный smoke 1505 passed / 0 failed; owner-issue #387; реестр TD-006 обновлён; коммит/push/PR с `Closes #387`.

## Surprises & Discoveries

- Observation: константу `ACTIVITY_COLUMN_ORDER` нельзя читать как атрибут класса (`ActivityStore.ACTIVITY_COLUMN_ORDER` → AttributeError): это модульная глобальная константа, а не атрибут класса.
  Evidence: первый прогон упал на `AttributeError: type object 'ActivityStore' has no attribute 'ACTIVITY_COLUMN_ORDER'`; фикс — импорт модульной константы в `database.py`.
- Observation: churn `database.py` распределён широко (максимум 3 касания на функцию за 50 коммитов), но activity-card кластер — единственная свежая связная группа; срез по нему безопасен, потому что покрыт контрактными тестами (#379, #374).
  Evidence: скрипт по `git log/show` — методы `get_activity`/tags/notes появились и менялись в коммитах карточки тренировки.

## Decision Log

- Decision: выносим только activity-card кластер (get_activity, теги, coach notes), а не весь activity CRUD (`save_activities`/`get_activities`/`get_activities_between` остаются в Database).
  Rationale: минимальный безопасный срез с готовыми контрактными тестами; крупный перенос затронул бы десятки внутренних вызовов и schema DDL.
  Date/Author: 2026-08-06 / Codex.
- Decision: `_ACTIVITY_COLUMN_ORDER` в `database.py` становится реэкспортом `ACTIVITY_COLUMN_ORDER` из store (без дублирования списка).
  Rationale: один источник истины для порядка колонок; `_ACTIVITY_COLUMN_TYPES` (schema DDL) пока остаётся в Database.
  Date/Author: 2026-08-06 / Codex.
- Decision: транзакции (commit) остаются у `Database`-фасадов, store работает с caller-owned connection — ровно как `AthleteProfileStore`.
  Rationale: единый паттерн хранения; фасад сохраняет текущую семантику коммитов для внешних вызовов.
  Date/Author: 2026-08-06 / Codex.

## Outcomes & Retrospective

2026-08-06: первый churn-first срез TD-006 выполнен. `data/activity_store.py`
содержит константу порядка колонок, DDL карточных таблиц и 8 методов кластера;
`data/database.py` реэкспортирует константу и делегирует методам через фасады
(commit — у фасадов, как у AthleteProfileStore). Контракты #379/#374 не
изменились: фокусные тесты 91 passed, полный smoke 1505 passed / 0 failed.
Урок: модульную константу нельзя читать через класс (`ActivityStore.CONST` →
AttributeError), импортировать нужно имя модуля. Открыт PR с `Closes #387`.

## Context and Orientation

`data/database.py` — монолитная обёртка SQLite (4330 строк): schema DDL, миграции, CRUD для активностей/wellness/планов/фидбека. Паттерн декомпозиции задан `data/athlete_profile_store.py` (TD-006, #371): store получает caller-owned connection и `clean_value`, DDL-функция вынесена отдельно, `Database` оставляет тонкие фасады.

Кластер «карточка активности»: `Database.get_activity`, `get_activity_tags`, `add_activity_tag`, `remove_activity_tag`, `get_all_activity_tags`, `get_activity_coach_notes`, `save_activity_coach_notes`, `get_all_activity_coach_notes` + таблицы `activity_tags`/`activity_coach_notes` (добавлены в #379). Потребители: `api/routers/activities.py` (карточка/теги/заметки), `tests/smoke/test_activity_card.py`, `tests/smoke/test_threshold_drift.py` (через `db.get_activity`).

## Plan of Work

### Milestone 1: store-модуль и фасады

Создан `data/activity_store.py`: модульная константа `ACTIVITY_COLUMN_ORDER`, `create_activity_card_tables(conn)` (DDL двух таблиц), класс `ActivityStore(conn, clean_value)` с 8 методами (чтение активности словарём, теги add/remove/get-all, coach notes get/save/get-all). В `data/database.py`: импорт `ACTIVITY_COLUMN_ORDER`/`ActivityStore`/`create_activity_card_tables`; DDL-блок заменён вызовом `create_activity_card_tables(conn)`; `_ACTIVITY_COLUMN_ORDER = ACTIVITY_COLUMN_ORDER`; тела 8 методов заменены фасадами вида `ActivityStore(conn, self.clean_value).<method>(...)` с commit в мутациях и close в finally.

### Milestone 2: проверки

Фокусные тесты: `python -m pytest tests/smoke/test_activity_card.py tests/smoke/test_threshold_drift.py tests/smoke/test_api_athlete_profile_contract.py tests/smoke/test_readiness_plan_purity.py tests/smoke/test_readiness_model.py tests/smoke/test_recovery_replan_loop.py tests/smoke/test_planning_week_by_week.py tests/smoke/test_activity_tss_reconciliation.py -q` → 91 passed. Ruff: `python -m ruff check data/activity_store.py data/database.py`.

### Milestone 3: полный smoke, issue, PR, реестр

Полный smoke `python -m pytest tests/smoke -q` без регрессий. Owner-issue по правилам реестра (churn-доказательство и acceptance). Коммит, push, PR с `Closes #<issue>`. В реестре `docs/technical_debt_register.md` — запись в журнал TD-006 о первом срезе и обновление «Следующее действие».

## Validation

Команды, которые должны быть зелёными:

    python -m pytest tests/smoke/test_activity_card.py tests/smoke/test_threshold_drift.py -q
    python -m pytest tests/smoke -q
    python -m ruff check data/activity_store.py data/database.py

Плюс подтверждение уменьшения: `wc -l data/database.py` меньше, чем было до среза (4330), а `data/activity_store.py` содержит вынесенные методы.
