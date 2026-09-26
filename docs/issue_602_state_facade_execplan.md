# ExecPlan: issue #602 — разорвать зависимость api → state → streamlit

Это живой ExecPlan по требованиям `.agent/PLANS.md`. Разделы `Progress`,
`Surprises & Discoveries`, `Decision Log` и `Outcomes & Retrospective` обязаны
обновляться по ходу работы. Документ самодостаточен: читатель, не знающий
репозитория, должен суметь выполнить работу целиком, имея только этот файл и
рабочее дерево.

Связанные артефакты: issue
[#602](https://github.com/rbctmz/ai_trainer/issues/602); черновик
[PR #640](https://github.com/rbctmz/ai_trainer/pull/640) и ветка
`refactor/issue-602-state-facade` — предшествующая реализация, взятая за основу
(см. «Context and Orientation»).

## Purpose / Big Picture

После этой работы продукт-API перестаёт зависеть от Streamlit на уровне импорта.
Пользователь-разработчик получает возможность запустить FastAPI-бэкенд на
машине, где Streamlit вообще не установлен, и это станет первым шагом к
возможному удалению legacy-контура. Наблюдаемое поведение формулируется одной
командой: импорт `api.main` при недоступном Streamlit завершается успешно, а в
`sys.modules` после импорта нет ни `streamlit`, ни `state`, ни `ui`.

Сегодня это не так, и это проверено, а не предположено:

    $ PYTHONPATH=. python - <<'PY'
    import sys, api.main
    print([m for m in ("streamlit", "state", "state.manager", "ui") if m in sys.modules])
    PY
    baseline: legacy modules pulled into sys.modules: ['streamlit', 'state', 'state.manager']

    $ PYTHONPATH=. python - <<'PY'
    import sys; sys.modules["streamlit"] = None
    import api.main
    PY
    ImportError: import of streamlit halted; None in sys.modules

Заметьте: `ui` в графе уже нет — эта часть архитектурного контракта выполнена
раньше. Проблема ровно в `state`.

## Progress

- [x] (2026-09-26) Собран ExecPlan: прочитаны `.agent/PLANS.md`,
  `docs/AI_Feature_Development_Workflow.md`, issue #602 и тело PR #640.
- [x] (2026-09-26) Подтверждён дефект на живом дереве: импорт `api.main`
  тянет `streamlit`, `state`, `state.manager`; при недоступном Streamlit
  импорт падает с `ImportError`.
- [x] (2026-09-26) Найден уже существующий headless-контур: `SessionDict`,
  `make_headless_state`, `get_headless_state` в `api/deps.py` и
  `_state_with_db` в `api/routers/system.py`.
- [x] (2026-09-26) M1, M2, M4 — реализованы в ветке
  `refactor/issue-602-state-facade` до появления этого плана: фасад в
  `utils/app_state.py`, схема в `utils/app_state_schema.py`,
  `services/cache_registry.py`, `api/` больше не импортирует `state`
  (`grep -rn "from state\|import state" api/` пуст), `state/manager.py` сжат
  с 386 до 55 строк. Проверено на слитом дереве.
- [x] (2026-09-26) M3 — расширен `tests/smoke/test_api_architecture.py`:
  добавлены проверки на `state` и на `streamlit` под `api/`. Проверка не
  пустая: на `origin/main` `api/deps.py` импортирует `state`, и тест его бы
  flagged.
- [x] (2026-09-26) M6 — ветка сведена с `main` (`b8c28d3`, 105 коммитов).
  Два конфликта разрешены: `api/routers/dashboard.py` (сохранён импорт
  `load_metrics_window_bounds` из main и headless-тип из ветки) и
  `services/data_cache.py` (версия ветки с безопасным `getattr`-сбросом плюс
  новый кэш `_load_activities_between_cached` из main). Прогон: 2881 passed,
  13 skipped; `ruff check .` чистый.
- [ ] M0 / AC4. Пробником снять и запинить фактический набор атрибутов
  состояния, который использует API. **Не сделано.** Существующий
  `tests/smoke/test_api_state_boundary.py` проверяет граф импортов и работу
  фасада на plain mapping, но набора нужных API атрибутов не фиксирует.
- [ ] M5. Differential parity: payload-контракты и русские тексты эндпоинтов
  не изменились (AC3). Косвенно подтверждено зелёным contributor-safe
  набором и `contract:extract --check`, но отдельного сравнения «до/после»
  по эндпоинтам не проводилось.
- [ ] M7. Закрыть issue #602 после закрытия M0 и M5; обновить
  `Outcomes & Retrospective`.

## Surprises & Discoveries

- **Observed**: `api/deps.py:79-122` уже содержит `SessionDict` (dict с
  доступом по атрибутам), `make_headless_state()` и `get_headless_state()`, а
  `api/routers/system.py:38-40` — `_state_with_db(db)` с докстрокой «Headless
  StateManager whose lazy .database is the given handle». Источник —
  прочитанный код.
  **Inferred**: API уже не пользуется Streamlit в рантайме; блокирует только
  импорт модуля. Дешёвая проверка — заблокировать `streamlit` и убедиться, что
  падает именно импорт, а не обращение к атрибуту.
  **Verified by**: прогон выше — падает `ImportError` на импорте, до любого
  обращения к состоянию. Гипотеза «нужно переписать рантайм-логику»
  **отклонена**: переписывать нечего, рантайм уже headless.

- **Observed**: `sys.modules` после `import api.main` содержит `streamlit`,
  `state`, `state.manager`, но не содержит `ui`. Источник — вывод пробника.
  **Inferred**: архитектурный тест `tests/smoke/test_api_architecture.py`
  проверяет только `ui`, поэтому дефект не был виден. Дешёвая проверка —
  прочитать тест.
  **Verified by**: в файле две проверки на `ui` (`test_coach_api_does_not_depend_on_legacy_ui`,
  `test_api_modules_do_not_depend_on_legacy_ui`) и ни одной на `state`. То есть
  AC2 формулирует реальный пробел в контракте, а не перестраховку.

- **Observed**: `state/manager.py` использует Streamlit ровно в двух местах —
  значение по умолчанию `st.session_state` в `__init__` (строка 66) и
  `st.get_option("theme.base")` в `_bootstrap_defaults` (строка 84). Источник
  — чтение файла и `grep -n "st\."`.
  **Inferred**: для legacy-UI достаточно оставить в адаптере эти две точки;
  основной объём файла — типизированные свойства над `_session`, которые от
  Streamlit не зависят.
  **Verified by**: NOT YET — подтверждается на M4, когда адаптер будет собран и
  legacy-тесты останутся зелёными.

## Decision Log

- Decision: фасад выносится из пакета `state/` в `utils/app_state.py`, а не
  делается «ленивый импорт streamlit» внутри `state/manager.py`.
  Rationale: AC2 требует, чтобы **ни один модуль под `api/` не импортировал
  `state`**. Ленивый импорт убрал бы `streamlit` из графа, но оставил бы
  зависимость API от legacy-пакета и не выполнил бы критерий. Вынос фасада —
  единственный путь, удовлетворяющий AC2 буквально.
  Date/Author: 2026-09-26, автор ExecPlan.

- Decision: `state/manager.py` не удаляется и не переписывается целиком, а
  становится адаптером над фасадом.
  Rationale: `state` импортируют не менее 15 модулей под `ui/` (включая
  `ui/pages/ai_coaching.py`, `ui/navigation.py`, `ui/plotly_theme.py`).
  Удаление сломало бы legacy-контур, а его судьба — отдельное решение после
  ADR об удалении Streamlit (см. non-goals в #602).
  Date/Author: 2026-09-26, автор ExecPlan.

- Decision: ветка `refactor/issue-602-state-facade` (PR #640) берётся за
  основу, а не пишется с нуля.
  Rationale: она уже реализует выбранную архитектуру (фасад в `utils/`, схема
  переехала, `state/manager.py` сжат с 386 до 55 строк) и несёт тесты
  `tests/smoke/test_api_state_boundary.py`. Цена — сведение с `main` и два
  конфликта.
  Date/Author: 2026-09-26, автор ExecPlan.

## Outcomes & Retrospective

(2026-09-26) Сведение с `main` выполнено. Что подтверждено на слитом дереве:

    $ PYTHONPATH=. python -c "import sys; sys.modules['streamlit']=None; import api.main; print('api_imported=True')"
    api_imported=True

    $ PYTHONPATH=. python -c "import sys, api.main; print([m for m in ('streamlit','state','state.manager','ui') if m in sys.modules])"
    legacy in sys.modules: []

    $ grep -rn "from state\|import state" api/ --include=*.py
    (пусто)

    $ pytest -m "not live and not debug and not e2e" tests/ -q
    2881 passed, 13 skipped

То есть AC1 и AC2 выполнены, AC3 подтверждён косвенно (зелёный набор и
актуальный контрактный артефакт), а AC4 — нет.

Уроки. Первое: исходная постановка «разорвать зависимость» читалась как
необходимость переписать рантайм, тогда как проблема была только в импорте —
это стоило проверить до проектирования, и стоило это одной команды. Второе:
конфликты сведе́ния оказались ровно там, где предсказал план (два файла), но
один из них был содержательным, а не механическим: `main` успел добавить
пятый кэш, и слепое взятие любой из сторон потеряло бы либо сброс нового
кэша, либо headless-безопасность. Третье: ветка жила больше недели, и её
тесты устарели относительно `main` молча — AC2 выполнялся отдельным файлом,
тогда как issue просил расширить существующий контракт.

## Context and Orientation

**Что такое этот репозиторий.** AI Trainer — приложение для планирования
тренировок на выносливость. Исторически UI был на Streamlit (каталоги `ui/` и
`state/`, точка входа `app.py`). Идёт миграция на FastAPI (`api/`) плюс
Next.js (`web/`); политика зафиксирована в
`docs/architecture/adr_0001_web_primary_ui.md`. Streamlit остаётся
поддерживаемым до паритета, поэтому `ui/` и `state/` — не мусор, а живой
контур.

**В чём именно проблема.** Термин «зависимость» здесь означает зависимость по
импорту, а не по поведению. Цепочка такая:

    api/deps.py:24                  from state import StateManager
    api/routers/system.py:33        from state import StateManager
    api/routers/dashboard.py:21     from state import StateManager
            ↓
    state/__init__.py:2             from .manager import StateManager, get_state_manager
            ↓
    state/manager.py:6              import streamlit as st

Пока `state/manager.py` импортирует Streamlit на уровне модуля, любой импорт
`api.main` требует установленного Streamlit — даже если ни одна строка API его
не вызывает. Именно это и проверяет AC1.

**Что уже сделано в правильную сторону.** `api/deps.py` описывает замысел так:
бэкенд остаётся Streamlit-free, а `StateManager` умеет строиться вокруг любого
mapping. Поэтому там уже есть `SessionDict` (dict с доступом по атрибутам,
потому что `StateManager.__setattr__` пишет через `setattr(self._session, key,
value)`), `make_headless_state(database)` и FastAPI-зависимость
`get_headless_state`. `api/routers/system.py` переиспользует это через
`_state_with_db`. Вывод: рантайм API уже headless, не хватает только
развязки импорта.

**Где живёт состояние.** `state/schema.py` (43 строки) уже headless —
Streamlit в нём не упоминается. `state/manager.py` (386 строк) — типизированный
фасад над `_session` с ленивыми свойствами, читающими БД
(`database`, `goal_plan`, `resolved_goal_plan_context` и другие).
`state/__init__.py` (12 строк) реэкспортирует `StateManager`,
`get_state_manager` и типы схемы.

**Архитектурный контракт.** `tests/smoke/test_api_architecture.py` обходит AST
целиком (включая импорты внутри функций) и уже проверяет, что `api/` не
импортирует `ui`, что `models/dashboard_summary.py` headless и что
`services/` не импортирует `api`. Проверки на `state` там нет — это и есть
AC2.

**Про предшествующую реализацию.** Ветка `refactor/issue-602-state-facade`
(PR #640, коммиты от 2026-09-18) реализует выбранный дизайн: новый
`utils/app_state.py` (~455 строк) как headless-фасад, переезд
`state/schema.py` → `utils/app_state_schema.py`, сжатие `state/manager.py`
до ~55 строк, новый `services/cache_registry.py` (реестр сброса кэшей без
Streamlit и pandas), правки `api/deps.py`, `api/routers/system.py`,
`api/routers/dashboard.py`, `services/data_cache.py`, `services/sync.py`,
`services/demo_mode.py`, `services/garmin.py` и новый тест
`tests/smoke/test_api_state_boundary.py` (~238 строк). Суммарно 16 файлов,
+892/−460. Ветка отстала от `main` более чем на сотню коммитов; сведение даёт
конфликты в `api/routers/dashboard.py` и `services/data_cache.py`
(`services/sync.py` сливается автоматически).

## Plan of Work

Работа идёт по восьми шагам, каждый из которых проверяем отдельно.

**M0 — снять фактическую поверхность.** Прежде чем что-то переносить, нужно
знать, какие именно атрибуты `StateManager` использует API. По `grep` видно
`state.database` в `api/routers/system.py:179,181,249`, но ленивые свойства
(`resolved_goal_plan_context`, `goal_plan`) читают БД шире, и `grep` этого не
покажет. В `api/routers/dashboard.py:376` объект передаётся в
`get_dashboard_goal_plan(state)`. Поэтому M0 — это пробник: обернуть
`StateManager` в объект, записывающий каждое обращение к атрибуту, прогнать
существующие контрактные тесты API и получить список реально востребованных
имён. Результат M0 фиксируется в этом разделе и становится списком того, что
обязан предоставлять фасад.

**M1 — вынести фасад.** В `utils/app_state.py` переносится типизированный
фасад над mapping: всё, что в `state/manager.py` не зависит от Streamlit.
Схема из `state/schema.py` переезжает в `utils/app_state_schema.py`, чтобы
фасад не импортировал legacy-пакет. `state/schema.py` сохраняется как
реэкспорт на время миграции — так legacy-код продолжает работать без правок.

**M2 — перевести API.** `api/deps.py` перестаёт импортировать `state`:
`SessionDict`, `make_headless_state` и `get_headless_state` начинают
возвращать фасад из `utils/app_state.py`. `api/routers/system.py` и
`api/routers/dashboard.py` получают тип фасада вместо `StateManager`. После
M2 команда `grep -rn "from state\|import state" api/` не должна находить
ничего.

**M3 — зафиксировать контракт тестом.** В
`tests/smoke/test_api_architecture.py` добавляются две проверки: модули под
`api/` не импортируют `state` (по образцу существующих проверок на `ui`) и
импорт `api.main` в подпроцессе с недоступным Streamlit завершается успешно,
а `sys.modules` не содержит `streamlit`, `state`, `state.manager`, `ui`.
Обе проверки пишутся до правки и должны падать (RED), затем проходить (GREEN).

**M4 — оставить legacy рабочим.** `state/manager.py` становится адаптером:
наследует или оборачивает фасад, оставляя ровно две Streamlit-точки — значение
по умолчанию `st.session_state` и `st.get_option("theme.base")`. Критерий
шага: набор тестов legacy-поверхности зелёный.

**M5 — доказать отсутствие поведенческих изменений.** Differential parity:
эндпоинты должны отдавать те же payload-контракты и те же русские тексты.
Практически — прогнать контрактные smoke-тесты API и сравнить с базой до
изменения.

**M6 — свести с main.** Ветка перебазируется (или сливается) с текущим
`main`; разрешаются конфликты в `api/routers/dashboard.py` и
`services/data_cache.py`; повторяется полный прогон. Затем PR переводится из
черновика в готовый к ревью.

**M7 — закрыть.** Issue закрывается, ExecPlan получает запись в
`Outcomes & Retrospective`.

## Concrete Steps

Все команды выполняются из корня репозитория. Виртуальное окружение —
`ai_trainer_env`.

Проверить исходное состояние (должно показать `streamlit`, `state`,
`state.manager`):

    PYTHONPATH=. ai_trainer_env/bin/python -c "import sys, api.main; print(sorted(m for m in ('streamlit','state','state.manager','ui') if m in sys.modules))"

Проверить, что импорт падает без Streamlit (до работы — падает; после работы —
печатает `api_imported=True`):

    PYTHONPATH=. ai_trainer_env/bin/python -c "import sys; sys.modules['streamlit']=None; import api.main; print('api_imported=True')"

Убедиться, что в `api/` не осталось импортов legacy-пакета:

    grep -rn "from state\|import state" api/ --include=*.py

Прогнать профильные тесты границы:

    PYTHONPATH=. ai_trainer_env/bin/python -m pytest tests/smoke/test_api_architecture.py tests/smoke/test_api_state_boundary.py -q

Прогнать contributor-safe набор и линтер:

    PYTHONPATH=. ai_trainer_env/bin/python -m pytest -m "not live and not debug and not e2e" tests/ -q
    PYTHONPATH=. ai_trainer_env/bin/python -m ruff check .

Проверить, что веб-контракт не поехал:

    npm --prefix web run contract:extract -- --check

Свести ветку с `main`:

    git fetch origin
    git switch refactor/issue-602-state-facade
    git merge origin/main

## Validation and Acceptance

Критерии берутся из #602 дословно и формулируются как наблюдаемое поведение.

Первый: после `import api.main` в `sys.modules` нет `streamlit`, `state` и
`ui`. Проверка — команда из раздела выше; ожидаемый вывод — пустой список.

Второй: ни один модуль под `api/` не импортирует `state`, `ui` и
`streamlit`; контракт в `tests/smoke/test_api_architecture.py` расширен на
`state`. Проверка — `pytest tests/smoke/test_api_architecture.py -q`,
ожидается `passed`, причём новая проверка падает на дереве до изменения
(RED) и проходит после (GREEN).

Третий: поведение эндпоинтов не меняется — payload-контракты и русские тексты
идентичны. Проверка — существующий набор smoke-тестов API и
`npm --prefix web run contract:extract -- --check` (артефакт должен остаться
актуальным).

Четвёртый: тест фиксирует, какие атрибуты `StateManager` реально нужны API,
чтобы разрыв не сломался молча при следующей правке. Набор снимается пробником
на M0 и переносится в регрессионный тест.

Пятый: `ruff check` и contributor-safe набор зелёные.

Дополнительно, поскольку это архитектурная правка: legacy-контур остаётся
работоспособным — тесты `ui/`-поверхности не регрессируют.

## Idempotence and Recovery

Все шаги идемпотентны: пробники только читают, тесты изолированы через
`tmp_path`, `git merge` повторяем. Сведение с `main` — единственный шаг,
который может оставить конфликтные маркеры: безопасный откат — `git merge
--abort`, повторная попытка после разбора конфликта. Никаких миграций БД и
destructive-операций план не содержит; рабочая база `ai_trainer.db` не
затрагивается. Если M4 покажет, что адаптер ломает legacy, откат — вернуть
`state/manager.py` из `git` и оставить API на фасаде: эти две части
независимы.

## Artifacts and Notes

Исходное состояние, снятое 2026-09-26 на `main`:

    baseline: import api.main OK
    baseline: legacy modules pulled into sys.modules: ['streamlit', 'state', 'state.manager']

    === now with streamlit made unavailable ===
    api_imported=False
    ImportError: import of streamlit halted; None in sys.modules

Существующий headless-контур, который нужно переиспользовать, а не изобретать:

    api/deps.py:104  def make_headless_state(database: Database | None = None) -> StateManager
    api/deps.py:116  def get_headless_state(db: Database = Depends(get_database)) -> StateManager
    api/routers/system.py:38  def _state_with_db(db) -> StateManager

## Interfaces and Dependencies

В `utils/app_state.py` должен появиться headless-фасад состояния. Точное имя
класса фиксируется на M1; требования к нему:

    class AppState:                      # имя уточняется на M1
        def __init__(self, session: MutableMapping[str, Any]) -> None: ...
        # свойства из списка M0, каждое — чтение/запись в session
        # ленивые свойства, читающие БД, сохраняют текущее поведение

В `api/deps.py` сигнатуры не меняются по смыслу, меняется только тип:

    def make_headless_state(database: Database | None = None) -> AppState
    def get_headless_state(db: Database = Depends(get_database)) -> AppState

В `utils/app_state_schema.py` переносятся `AppState`, `DataState`,
`IntegrationState`, `UIState` из `state/schema.py` без изменения состава
полей; `state/schema.py` реэкспортирует их. `services/cache_registry.py`
содержит headless-реестр сброса кэшей и не импортирует ни Streamlit, ни pandas,
чтобы `services/sync.py` и `services/demo_mode.py` могли сбрасывать кэш, не
затягивая legacy-UI.

Библиотеки не добавляются. Внешние зависимости остаются прежними; цель — их не
расширять, а сузить граф импортов.

---

Изменение 2026-09-26: создан документ. Причина — issue #602 помечен как Class A
и требует ExecPlan; черновик PR #640 существует без плана, из-за чего не может
двигаться в ревью. План составлен после проверки дефекта на живом дереве, а не
по тексту issue.

Изменение 2026-09-26 (ревизия 2): обновлены `Progress` и
`Outcomes & Retrospective` после сведения ветки с `main`. Причина — ExecPlan
живой документ и обязан отражать фактическое состояние: M1, M2, M4 реализованы
в ветке до появления плана, M3 и M6 выполнены сегодня, M0 (AC4) и M5 остаются
открытыми. Раздел `Outcomes` дополнен снятыми на слитом дереве доказательствами
и тремя выводами; ни одно утверждение не помечено выполненным без прогона.
