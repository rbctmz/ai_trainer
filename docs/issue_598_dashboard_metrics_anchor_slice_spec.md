# Slice Spec — Issue #598: якорь CTL/ATL/TSB на дашборде

- Issue / PR: #598 / (PR открывается этим слайсом)
- Author / checker / merge owner: Domain / API Implementer (DSH) / независимый checker — TBD / human merge owner (rbctmz)
- Date: 2026-09-20
- Candidate head SHA: TBD (заполняется перед review)
- Parent: #607 (Daily decision loop v1), шаг 0 «Truth prerequisites»

## Change Class

- Class: **B — Standard**
- Rationale: исправление дефекта в существующем доменном расчёте. Публичный
  контракт (API DTO и `web/lib/types.ts`) не меняется — меняются значения
  `ctl/atl/tsb` внутри уже существующих полей. Нет миграций, нет нового
  persistent state, нет live-provider записи.
- Automatic escalation triggers checked:
  - data migration / schema / persistence semantics — **нет** (только чтение);
  - identity or provenance, cursor ownership, dedup — **нет**;
  - live-provider write, платный вызов, destructive sync — **нет**
    (`dashboard_summary` читает локальную SQLite);
  - security boundary, permissions, secrets, personal data — **нет**;
  - irreversible action / rollback — **нет** (diff обратим, метрики
    пересчитываются из тех же данных);
  - новый cross-module public contract или архитектурная граница — **нет**
    (добавляются keyword-параметры со значением по умолчанию `None` во
    внутренние Python-функции; поведение существующих вызывающих не меняется).
- Review budget used: 0 / 2
- Review trigger mode: manual
- Review acceptance head SHA: TBD
- Review budget exception: N/A

## Scope

- Behavior that changes: `models.dashboard_summary.calculate_current_status`
  считает CTL/ATL/TSB по каноническому окну `LOAD_METRICS_WINDOW_DAYS` (90
  дней) и с якорем `athlete_local_date()`, вместо 30-дневного кадра
  отображения без якоря.
- Files/modules in scope:
  - `models/signals_engine.py` — `assemble_signals` принимает отдельный
    длинный кадр для метрик нагрузки;
  - `models/dashboard_summary.py` — `calculate_current_status` пробрасывает
    окно и якорь;
  - `api/routers/dashboard.py` — оба эндпоинта (`/summary`, `/widgets`)
    передают каноническое окно и якорь;
  - `ui/pages/dashboard.py` — легаси-страница передаёт то же окно и якорь;
  - `tests/smoke/test_dashboard_metrics_anchor.py` — новый RED→GREEN контракт.

### Решение по вопросам из issue

Issue #598 просил решить три вопроса. Ответы опираются на уже существующий
канонический контур (`models/readiness.py`), а не на новый выбор:

1. **Какой якорь корректен для короткого окна.** Расширить окно до
   канонического `LOAD_METRICS_WINDOW_DAYS` = 90 и якорить на
   `athlete_local_date()`. Вариант «якорь от последней доступной даты данных»
   — это текущее поведение (`_daily_load_series` при `as_of=None` уже берёт
   `frame["date"].max()`), поэтому он не устраняет дефект по построению.
   Константа 90 уже существует ровно с этой семантикой: «метрики не должны
   зависеть от того, за сколько дней запрошен отчёт» (issue #134).
2. **Как согласовать два окна в одном эндпоинте.** Кадр отображения (30 дней)
   не трогаем — он остаётся входом для display-полей и readiness-фузии.
   Длинный кадр передаётся отдельным параметром, ровно как это уже сделано для
   ACWR в #595 (`acwr_activities_df` / `acwr_as_of`). Параметры остаются
   раздельными: смена ACWR-минимума не должна молча менять окно метрик.
3. **Что показывать, когда данных нет.** Ветка «Fresh/empty account» не
   меняется: `/summary` по-прежнему отдаёт `has_data: False` и
   `summary: None`, `/widgets` — `has_data: False` и `None` вместо
   производных виджетов. Пустой кадр даёт нули, как и раньше.

## Non-goals

- Поведение, которое сознательно не меняется: математика EWMA, значения
  `tau_CTL`/`tau_ATL`, пороги `TSB_ZONES`, окно ACWR и `models/acwr.py`
  (non-goal самого #598).
- Не меняется схема БД, не добавляется персистентное состояние, не пишутся
  `training_status`.
- Не меняются 30-дневный кадр отображения и readiness-фузия: они получают тот
  же вход, что и раньше.
- Deferred work and owner: host-clock якорь в `api/planning_service.py` и
  host-часы у `acwr_as_of` — #601 (отдельный слайс; здесь не трогаем, чтобы
  не расширять diff и не менять ACWR-поведение).

## Definition of Done

- [x] Acceptance criteria наблюдаемы (см. RED Matrix).
- [x] Named checks: `python -m ruff check .`,
      `python -m pytest tests/smoke/test_dashboard_metrics_anchor.py -q`,
      `python -m pytest -m "not live and not debug and not e2e" tests/`.
- [ ] Merge и cleanup owner назначен (human merge owner).

## Public Contracts

| Contract | Status | Evidence |
| --- | --- | --- |
| `GET /api/dashboard/summary` DTO | unchanged — форма не меняется, меняются значения `ctl/atl/tsb/form/critical/recommendations` | `tests/smoke/test_api_dashboard.py`, новый `test_api_summary_payload_agrees_with_itself` |
| `GET /api/dashboard/widgets` DTO | unchanged | `tests/smoke/test_api_dashboard.py` |
| `web/lib/types.ts` | unchanged — поля и типы те же | `npm --prefix web run contract:extract -- --check` |
| `models.signals_engine.assemble_signals` | changed compatibly — новые keyword-параметры со значением по умолчанию `None` | существующие 13 вызывающих не меняют поведение |
| `models.dashboard_summary.calculate_current_status` | changed compatibly — то же | `tests/smoke/test_dashboard_v2_shell.py` |

## Failure, Reset, Rollback, Idempotency

- Failure modes and safe result: пустой/нечитаемый кадр → прежние нули и
  `form` «Недостаточно данных»; отсутствие `metrics_activities_df` →
  прежнее поведение (`activities_df`), полная обратная совместимость.
- Retry/idempotency key and duplicate behavior: расчёт чистый и без I/O
  (кроме чтения SQLite в роутере); повторный вызов даёт тот же результат.
- Rollback procedure and proof: revert коммита; значения возвращаются к
  прежним, поскольку источник данных не менялся.
- [x] Новое persistent state не добавляется.
- [x] Full reset не требуется: новых строк/артефактов/курсоров нет.
- [x] Restart и partial-failure recovery: не применимо, состояние не пишется.

## State Boundaries and Identity

- Source of truth and owner: дневной ряд нагрузки из `activities`
  (владелец — `models/signals_engine._daily_load_series`).
- Stable identity/provenance keys: не затрагиваются (identity живёт в
  reconciliation-контуре, #609).
- Cursor/checkpoint lifecycle: не применимо.
- Concurrency and stale-write behavior: только чтение.

## Evidence Boundary Matrix

| Identity | Time/provenance | Evidence state | Fallback | Expected result / falsifier |
| --- | --- | --- | --- | --- |
| n/a (агрегат, не сущность) | последняя активность сегодня | present | allowed | CTL/ATL/TSB совпадают с `_tsb_metrics`; фальсификатор — расхождение с каноническим snapshot |
| n/a | разрыв 14 дней после блока | present, stale по времени | allowed | ATL гаснет, TSB > 0; фальсификатор — ATL на уровне блока |
| n/a | 30-дневный кадр как единственный вход | partial (обрезанный разогрев) | **fail closed → расширить окно** | CTL не занижен; фальсификатор — CTL ≈ 25.5 вместо 38.0 |
| n/a | данных нет вовсе | missing | fail closed | нули и «Недостаточно данных», `has_data: False` не меняется |
| n/a | активность в будущем относительно якоря | out-of-window | fail closed | `_daily_load_series` отсекает `date > anchor` (существующее поведение) |

## RED Matrix

| Acceptance criterion / invariant | RED test or probe | Expected failure до фикса | GREEN evidence |
| --- | --- | --- | --- |
| AC1: метрики не замерзают на дате последней тренировки | `test_rest_days_decay_dashboard_metrics` | ATL = 106.2, TSB = −68.5 при истинных 15.4 / +18.4 | ATL < 60, TSB > 0 |
| AC1/AC2: дашборд совпадает с каноническим snapshot | `test_dashboard_load_path_matches_canonical_readiness_tsb` | `calculate_current_status` не принимает `metrics_activities_df`/`as_of` | CTL/ATL/TSB равны `_tsb_metrics(history, anchor)` |
| AC2: витринный CTL не занижен | `test_steady_load_is_not_understated_by_display_window` | CTL = 25.5 на 30-дневном кадре против канонических 38.0 | CTL ≈ 38.0 |
| AC1/AC2 на API-потребителе: payload не противоречит сам себе | `test_api_summary_payload_agrees_with_itself` | `load.tsb` = +16.4 «Свежесть» рядом с `load.form` = «Высокая усталость» и `critical` = «Критическое переутомление / Полный отдых 2-3 дня» | `form == label`, `critical` не «Критическое переутомление», нет рекомендации «TSB критически низкий» |
| AC3: легаси-страница (второй потребитель) | `test_legacy_dashboard_status_is_anchored` | легаси-вызов даёт TSB = −68.5 | ATL < 60, TSB > 0 |
| AC4: «Fresh/empty account» не сломан | `test_empty_account_keeps_zero_metrics` | (зелёный и до фикса) | нули сохраняются |
| Регрессия: значения канонического пути не меняются | `test_canonical_snapshot_values_unchanged` | (зелёный и до фикса) | `_tsb_metrics` = 33.8 / 15.4 / +18.4 |

### Воспроизведение до фикса (Observed)

Одна и та же локальная SQLite, один и тот же день: блок 3 недели
(100/110/120 TSS) с окончанием 14 дней назад.

| Путь | CTL | ATL | TSB | Что видит атлет |
| --- | --- | --- | --- | --- |
| Канонический snapshot (`_tsb_metrics`, окно 90, якорь) | 31.3 | 14.9 | **+16.4** | «Готов к работе», tone success |
| `/api/dashboard/summary` → `signals.load` (спроецировано) | 31.3 | 14.9 | +16.4 | «Свежесть» |
| `/api/dashboard/summary` → `signals.load.form` | — | — | (frozen) | **«Высокая усталость»** |
| `/api/dashboard/summary` → `signals.critical` | — | — | (frozen) | **«Критическое переутомление» / «Полный отдых 2-3 дня»** |
| `/api/dashboard/summary` → `signals.recommendations[0]` | — | — | (frozen) | **«🚨 Немедленный отдых. TSB критически низкий (-30+)»** |
| Легаси `ui/pages/dashboard.py` (без проекции) | 37.7 | 106.2 | **−68.5** | «Глубокая усталость» у отдохнувшего |

Корень один: `signals.load.ctl/atl/tsb` перекрываются проекцией из
канонического snapshot, а `signals.critical`, `signals.recommendations` и
`signals.load.form` вычисляются внутри `assemble_signals` **от
замороженного значения** и проекцией не перекрываются.
`project_readiness_snapshot` к тому же возвращает вход без проекции, если
`readiness_snapshot["score"] is None` — латентный путь утечки замороженных
значений на API (в трёх проверенных сценариях score был не `None`, поэтому это
**Inferred**, а не воспроизведённый дефект; фикс закрывает его по построению).

### Проверено после фикса (Verified by)

Один и тот же payload `/api/dashboard/summary`, блок 3 недели + 14 дней отдыха:

| Поле | До | После |
| --- | --- | --- |
| `signals.load.tsb` | +16.4 | +16.4 |
| `signals.load.form` | «Высокая усталость» | «Свежесть» (= `label`, tone success) |
| `signals.critical` | «Критическое переутомление» / «Полный отдых 2-3 дня» | `null` / `null` |
| `signals.recommendations[0]` | «🚨 Немедленный отдых. TSB критически низкий (-30+)» | «🚀 Пиковая форма! TSB выше +5» |
| Легаси `_calculate_current_status` (как в `ui/pages/dashboard.py`) | ATL 106.2, TSB −68.5 | ATL 14.9, TSB +16.4 |

Обратная совместимость: вызов `calculate_current_status` **без** новых
параметров даёт прежний результат (CTL 37.7 / ATL 106.2 / TSB −68.5), поэтому
существующие вызывающие не меняют поведение — параметры аддитивны.

## Deferred (измерено, вне scope этого слайса)

`_readiness_signal` по-прежнему получает кадр отображения (30 дней) — это
сознательно не меняется, чтобы не трогать вход readiness-фузии (non-goal #598).
Измеренный остаточный эффект:

| Кадр readiness-фузии | Значение score | `drivers[tsb].evidence` |
| --- | --- | --- |
| 30 дней (текущий) | 85.0 | **«TSB +12.6 (свежесть)»** |
| 90 дней (канонический) | 85.0 | «TSB +16.4 (свежесть)» |

Score совпадает (полоса насыщена), но текст доказательства внутри legacy-страницы
называет +12.6 там, где заголовочный `signals.load.tsb` показывает +16.4. На API
это не наблюдаемо: `project_readiness_snapshot` подменяет `signals.readiness.drivers`
каноническими. Дефект не внесён этим слайсом (выход `_readiness_signal` до и после
фикса побитово совпадает) и требует отдельного решения о readiness-окне —
follow-up issue с владельцем Domain / API Implementer.

## Global Constraints (родительский #607)

- `ASR-REL-2` (missing/stale/partial fail closed): пустой и обрезанный вход
  дают детерминированный безопасный результат, а не «уверенное» значение.
- `ASR-MOD-2` (server-owned projection): значение считается в Python и
  отдаётся в DTO; браузер ничего не пересчитывает.
- `ASR-PERF-1` (Today без провайдера): расчёт остаётся локальным.
- `ASR-MOD-3` (аддитивные контракты): новые параметры аддитивны, форма DTO не
  меняется.
- `ADR-0001`: исправление живёт в shared Python + API; Streamlit только
  потребляет, своей копии логики не получает.
