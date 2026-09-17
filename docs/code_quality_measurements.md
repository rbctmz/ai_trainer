# Инженерные измерения: покрытие и проверка типов

- **Статус:** Current
- **Снимок:** 2026-09-17 (ветка `fix/issue-585-p1-hygiene` = `main` + PR #586)
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
| `models/` | 13869 | 2175 | 84 % |
| `services/` | 3658 | 372 | 90 % |
| `data/` | 4526 | 1215 | 73 % |
| `utils/` | 870 | 533 | 39 % |
| **product total** | **27488** | **4841** | **82 %** |

Крупнейшие слепые зоны (по числу непокрытых строк; `--cov-report=term-missing`):

| Модуль | Statements | Missed | Покрытие |
|---|---:|---:|---:|
| `data/garth_client.py` | 506 | 436 | 14 % |
| `models/ai_tools.py` | 843 | 353 | 58 % |
| `utils/modern_ui.py` | 304 | 304 | 0 % |
| `data/database.py` | 2347 | 288 | 88 % |
| `models/training_planner.py` | 1296 | 277 | 79 % |
| `data/garmin_client.py` | 519 | 272 | 48 % |
| `api/planning_service.py` | 1445 | 178 | 88 % |
| `models/coach_tool_presenter.py` | 451 | 168 | 63 % |
| `models/ai_providers.py` | 593 | 164 | 72 % |
| `data/data_processor_phase1.py` | 624 | 159 | 75 % |

Как читать:

- Низкое покрытие `utils/modern_ui.py` (Streamlit-хелпер) и `data/garth_client.py`
  (garth не установлен и отсутствует в `requirements.txt`; тесты этой пары
  пропускаются) — ожидаемое следствие legacy-статуса, а не дефект. Считать их
  ориентиром для нового кода нельзя.
- Большие проценты на больших модулях обманчивы: `data/database.py` при 88 %
  даёт 288 непокрытых строк — больше, чем любой models-модуль.
- `config/` и `state/` в отчёт не попадают: они не указаны в `--cov`, а
  `config.settings` импортируется корневым `tests/conftest.py` до старта измерений.

## 2. Проверка типов (`mypy`)

```bash
python -m mypy      # конфиг: mypy.ini, files = api/routers, services
```

Команда должна завершаться успешно и проверять 51 файл. Это **инкрементальный
allowlist**, а не полная проверка репозитория: по умолчанию в `mypy.ini` стоит
`ignore_errors = True`, и включены только те пакеты, которые уже проходят чисто.

### Что включено

- `api/routers` — 14 из 17 файлов;
- `services` — 26 из 34 файлов.

Исключения — существующий долг внутри чистых пакетов, каждое помечено в
`mypy.ini`: `api.routers.decisions` (2), `api.routers.planning` (1),
`api.routers.session_quality` (1), `services.comparable_sessions` (18),
`services.demo_mode` (7), `services.bike_hr_tss_eval` (2), `services.sync` (1),
`services.activity_ingest` (1), `services.bike_hr_pairs` (1),
`services.planning_onboarding` (1), `services.recovery_analytics` (1).

### Текущий долг (не входит в allowlist)

`python -m mypy api models services data utils config --ignore-missing-imports` →
**298 ошибок**:

| Область | Ошибок |
|---|---:|
| `models/` | 188 |
| `api/` | 70 |
| `services/` | 32 |
| `data/` | 8 |

По кодам: `arg-type` 115, `union-attr` 52, `assignment` 31, `call-overload` 29,
`attr-defined` 24, `operator` 12, остальные — единичные.

Топ файлов: `models/training_planner.py` (46), `models/ai_providers.py` (44),
`api/planning_service.py` (41), `services/comparable_sessions.py` (18),
`models/planning_checkpoints.py` (11), `models/ai_tools.py` (10),
`api/session_feedback.py` (10).

Долг концентрируется в тех же модулях, что и churn (см. TD-006 в
[`technical_debt_register.md`](technical_debt_register.md)): разрез модуля и
разбор его ошибок типов имеет смысл делать одним срезом, а не двумя.

## 3. Порядок расширения allowlist

1. Взять модуль с наименьшим числом ошибок из таблицы долга (или тот, который
   всё равно правится в текущем срезе).
2. Убрать его секцию `ignore_errors = True` из `mypy.ini`.
3. `python -m mypy` — разобрать ошибки как обычную правку типов (не менять
   поведение; при сомнении оставить `Any` и завести отдельный срез).
4. Обновить таблицы в этом документе: перенести модуль из долга в allowlist и
   пересчитать числа.
5. Когда `api/` и `services/` целиком окажутся в allowlist, ставить вопрос о
   CI-гейте (`python -m mypy` в `ci.yml`) отдельным решением — не в рамках
   среза измерений.

## 4. Чего здесь сознательно нет

- CI-гейтов для `mypy` и покрытия: сначала измерение и ratchet, потом политика.
- Порогов покрытия (`--cov-fail-under`): при 39 % в `utils/` любой порог либо
  бесполезен, либо требует отдельного среза по legacy.
- Проверки типов в `web/`: там работает `next build` (TypeScript) и ESLint;
  отдельный инструмент не добавлялся.
