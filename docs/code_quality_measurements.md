# Инженерные измерения: покрытие и проверка типов

- **Статус:** Current
- **Снимок:** 2026-09-17, product-код на `07cfee6` (PR #588 меняет только `mypy.ini`,
  `requirements-dev.txt`, README и сам документ); mypy-числа обновлены срезом
  [#589](https://github.com/rbctmz/ai_trainer/issues/589)
- **Пересчёт после #589:** таблица покрытия выше — baseline PR #588; правки типов из
  #589 сдвигают счётчики в пределах единиц statements (на дереве #589 — 27494/5178,
  те же 81 %), отдельного пересмысла это не меняет
- **Issue:** [#587](https://github.com/rbctmz/ai_trainer/issues/587)

Документ фиксирует два измерения качества, которых в репозитории не было: покрытие
тестами и проверку типов. Оба — **измерения, а не гейты**: команды запускаются
вручную, CI их пока не проверяет. Правила классов изменений и review budget
описаны в [`AI_Feature_Development_Workflow.md`](AI_Feature_Development_Workflow.md).

## 1. Покрытие тестами (`pytest-cov`)

```bash
python -m pytest -m "not live and not debug and not e2e" tests/ -q \
  --cov=api --cov=models --cov=services --cov=data --cov=utils
```

Baseline contributor-safe прогона (2707 собранных тестов):

| Область | Statements | Missed | Покрытие |
|---|---:|---:|---:|
| `api/` | 4565 | 546 | 88 % |
| `models/` | 13869 | 2506 | 82 % |
| `services/` | 3658 | 371 | 90 % |
| `data/` | 4526 | 1214 | 73 % |
| `utils/` | 870 | 533 | 39 % |
| **product total** | **27488** | **5170** | **81 %** |

Крупнейшие слепые зоны (по числу непокрытых строк; `--cov-report=term-missing`):

| Модуль | Statements | Missed | Покрытие |
|---|---:|---:|---:|
| `data/garth_client.py` | 506 | 436 | 14 % |
| `models/ai_tools.py` | 843 | 395 | 53 % |
| `utils/modern_ui.py` | 304 | 304 | 0 % |
| `data/database.py` | 2347 | 284 | 88 % |
| `models/ai_data_context.py` | 326 | 276 | 15 % |
| `data/garmin_client.py` | 519 | 272 | 48 % |
| `models/training_planner.py` | 1296 | 271 | 79 % |
| `api/planning_service.py` | 1445 | 178 | 88 % |

Как читать:

- Низкое покрытие `utils/modern_ui.py` (Streamlit-хелпер) и `data/garth_client.py`
  (garth не установлен и отсутствует в `requirements.txt`; тесты этой пары
  пропускаются) — ожидаемое следствие legacy-статуса, а не дефект. Считать их
  ориентиром для нового кода нельзя.
- Большие проценты на больших модулях обманчивы: `data/database.py` при 88 %
  даёт 284 непокрытых строки — больше, чем любой models-модуль.
- `config/` и `state/` в отчёт не попадают: они не указаны в `--cov`, а
  `config.settings` импортируется корневым `tests/conftest.py` до старта измерений.
- Числа зависят от окружения, и это часть baseline. В чистом checkout (и в CI-джобе
  `contributor-safe-tests`, где npm-зависимости не ставятся) пропусков 38 против 13 в
  прогретом рабочем каталоге. Разница +25 складывается из: 20 тестов
  `test_contract_extractor.py` и 2 `test_api_call_inventory.py` (нет `web/node_modules`),
  3 теста (`test_final_app.py`, `test_hrv_logic.py`, `test_hrv_trend.py`) — нет локального
  `ai_trainer.db`. Остальные 13 пропусков одинаковы в обоих окружениях: 10 —
  `test_issue_562_acceptance.py` (`CAPTURE_FIXTURE_REGEN=1`), 2 — `test_garth_api.py`
  (нет `garth`), 1 — preflight (песочница без `ps`). Сравнивать прогоны можно только
  при одинаковом наборе пропусков.

## 2. Проверка типов (`mypy`)

```bash
python -m mypy      # конфиг: mypy.ini, files = api/routers, services
```

Команда должна завершаться успешно и проверять 51 файл. Это **инкрементальный
allowlist**, а не полная проверка репозитория: по умолчанию в `mypy.ini` стоит
`ignore_errors = True`, и включены только те пакеты, которые уже проходят чисто.

### Что включено

- `api/routers` — 16 из 17 файлов;
- `services` — 32 из 34 файлов.

Исключения — существующий долг внутри чистых пакетов, каждое помечено в
`mypy.ini`:

| Модуль | Ошибок | Причина |
|---|---:|---|
| `services/comparable_sessions` | 18 | крупный модуль, отдельный срез |
| `services/demo_mode` | 7 | демо-фикстуры, отдельный срез |
| `api.routers.decisions` | 2 | `int(params.get("base_checkpoint_id"))` без guard'а (строки 576, 617) |

`decisions.py` — пробел типизации, а не подтверждённый дефект: у предложений,
публикуемых циклом, ключ всегда есть (`api/recovery_replan_loop.py:231`). Правка
потребовала бы либо `cast`, либо смены класса ошибки на fail-closed — это отдельное
решение, а не механическая правка типов.

### Текущий долг (не входит в allowlist)

```bash
# --config-file= (пустое значение) отключает поиск mypy.ini: без него глобальный
# ignore_errors = True из allowlist-конфига подавил бы весь долг и команда вернула бы
# «Success». --python-version 3.10 держит замер на целевом рантайме деплоя.
python -m mypy --config-file= --python-version 3.10 \
  api models services data utils config --ignore-missing-imports
```

Ожидаемый вывод в окружении из `requirements-dev.txt` (Python 3.11, mypy 1.20.2):
`Found 287 errors in 42 files (checked 145 source files)`.
Срез [#589](https://github.com/rbctmz/ai_trainer/issues/589) снизил долг: 298 → **287**.

Замер зависит от окружения анализатора, а не только от кода: тот же mypy 1.20.2 на
Python 3.12 сообщает `286 errors in 51 files` и 176 ошибок в `models/` вместо 188
(**Observed**, ревью PR #588). `--python-version 3.10` фиксирует целевую семантику
языка, но не рантайм и не версии установленных стабов, поэтому числа в таблицах ниже
сравнимы только внутри одного окружения — фиксируйте Python и версию mypy вместе с
результатом.

| Область | Ошибок |
|---|---:|
| `models/` | 188 |
| `api/` | 66 |
| `services/` | 25 |
| `data/` | 8 |

По кодам: `arg-type` 108, `union-attr` 52, `call-overload` 29, `assignment` 29,
`attr-defined` 24, `operator` 12, `var-annotated` 8, остальные — единичные.

Топ файлов: `models/training_planner.py` (46), `models/ai_providers.py` (44),
`api/planning_service.py` (41), `services/comparable_sessions.py` (18),
`models/planning_checkpoints.py` (11), `models/ai_tools.py` (10),
`api/session_feedback.py` (9), `models/session_scheduler.py` (8),
`services/demo_mode.py` (7), `models/readiness.py` (7),
`models/plan_actual_reconciliation.py` (7), `api/today_snapshot.py` (7).

Долг концентрируется в тех же модулях, что и churn (см. TD-006 в
[`technical_debt_register.md`](technical_debt_register.md)): разрез модуля и
разбор его ошибок типов имеет смысл делать одним срезом, а не двумя.

## 3. Порядок расширения allowlist

1. Взять модуль с наименьшим числом ошибок из таблицы долга (или тот, который
   всё равно правится в текущем срезе).
2. Добавить модуль в корни проверки: `files = api/routers, services` в `[mypy]`
   перечисляет только стартовые пакеты, поэтому модуль вне них (например
   `api/planning_service.py` из `api/`) в проверку не попадает вообще — его нужно
   дописать в `files` (или расширить корень до `api`, если так честнее для слоя).
3. Включить проверку **позитивным** override: глобальный `ignore_errors = True`
   подавляет ошибки и у модуля, добавленного в `files`, поэтому нужна секция
   `[mypy-<module>]` с `ignore_errors = False`. Удаления старой секции недостаточно:
   у модуля вне стартовых корней её просто нет, и без позитивного override он
   останется «зелёным» при любом количестве ошибок.
   Проверено на `api/planning_service.py`: без override — `Success: no issues found
   in 1 source file`, с `[mypy-api.planning_service] ignore_errors = False` — 41 ошибка.