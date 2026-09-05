# Agent Log v2: trigger, scope, outcome, revisit для решений коуча (#501)

Этот ExecPlan — живой документ. Разделы `Progress`, `Surprises & Discoveries`, `Decision Log` и `Outcomes & Retrospective` обязаны поддерживаться в актуальном состоянии по мере работы. Требования к формату ExecPlan описаны в `.agent/PLANS.md` (корень репозитория); документ ведётся в соответствии с ними.

## Purpose / Big Picture

Сейчас журнал решений коуча (`/decisions`) показывает **что** коуч решил (Push/Moderate/Recovery/Monitor) и **почему** (reason), но не отвечает на четыре вопроса: **что запустило** решение (coach-запрос, синк, чек, смена настроек, утверждённое предложение), **насколько далеко** ему позволено влиять (сегодня / неделя / весь план), **что реально произошло** (включая осознанное «без изменений», которое сейчас выглядит как отсутствующее событие) и **когда/почему** решение будет пересмотрено.

После этого изменения каждая строка журнала несёт стабильные поля `trigger`, `scope`, `outcome` и `revisit`, а повторный прогон (retry/replay) не создаёт дубль логического решения. Человек, открыв `/decisions`, видит полную причинно-следственную цепочку решения: запуск → допустимая зона влияния → фактический исход → план пересмотра. Устаревшие строки остаются видимыми с пометкой «unknown», ничего не стирается и не досочиняется.

## Progress

- [x] (2026-09-05) Изучены `models/coach_decisions.py`, таблица `coach_decisions`, `api/routers/decisions.py`, `web/app/decisions/page.tsx`, `web/lib/types.ts`, `services/coach_drift.py`, вызовы `save_coach_decision`/`save_coach_proposal`, issue #501.
- [x] (2026-09-05) Написан ExecPlan (этот документ).
- [x] (2026-09-05) Ветка `codex/issue-501-agent-log-v2` создана; префлайт публикации пройден (origin = rbctmz/ai_trainer, gh auth как rbctmz). Зафиксированы уточнения дизайна (Decision Log #5–#8): read-time derivation outcome, sentinel `no_revisit_required`, action→scope маппинг, `rolled_back` в enum.
- [ ] Реализовать schema/модель (enums trigger/scope/outcome + поля revisit).
- [ ] Аддитивная миграция `coach_decisions` + idempotency-защита по `decision_event_id`.
- [ ] Прогнать trigger/scope/outcome через существующие точки записи (coach-чат и recovery-replan loop).
- [ ] Проекция в `api/routers/decisions.py` + legacy-совместимость.
- [ ] UI `web/app/decisions/page.tsx` + `web/lib/types.ts` + contract artifact.
- [ ] Тесты, smoke, Ruff, web lint/build, contract:extract.

## Surprises & Discoveries

- **Observed**: таблица `coach_decisions` уже имеет поле `decision_event_id`, которое генерируется один раз на ход коуча (`api/routers/coach.py::coach_chat`, `str(uuid.uuid4())`) и передаётся и в `save_coach_decision`, и в `save_coach_proposal`; `services/coach_drift.py::_event_id` извлекает этот id и связывает решения и предложения. Источник: чтение `api/routers/coach.py` и `services/coach_drift.py`.
- **Inferred**: `decision_event_id` — готовый ключ идемпотентности и событийной связи; его нужно только сделать уникальным (сейчас `save_coach_decision` вставляет без проверки на дубль). Самая дешёвая проверка-опровержение — два вызова `save_coach_decision` с одинаковым `decision_event_id` на временной БД: если появится две строки, гипотеза «уникальность не гарантирована» верна.
- **Verified by**: `save_coach_decision` не содержит `SELECT`-проверки на существующий `decision_event_id` перед `INSERT` (чтение кода); полноценный RED-тест добавим в `Concrete Steps`.

## Decision Log

- Decision: расширяем таблицу `coach_decisions` **аддитивно** nullable-колонками, ничего не переписывая и не удаляя в старых строках.
  Rationale: acceptance-критерий #501 прямо требует «legacy decision row остаётся видимой с unknown/not-captured», а не миграцию с фабрикацией значений.
  Date/Author: 2026-09-05 / agent.

- Decision: `trigger`, `scope`, `outcome` — стабильные строковые enum'ы с явным значением `unknown` для legacy; храним как TEXT, а не INTEGER-коды.
  Rationale: строковые enum'ы читабельны в SQL/JSON, устойчивы к репорядку числовых кодов и совпадают с существующим стилем (`decision_type` уже TEXT: Push/Moderate/Recovery/Monitor).
  Date/Author: 2026-09-05 / agent.

- Decision: `outcome` выводим из связки «decision → proposal по `decision_event_id` → status proposal», а не вводим отдельную машину состояний.
  Rationale: drift-отчёт уже различает `no_change` (нет связанного proposal) и «предложение применено/откачено»; переиспользуем этот факт, чтобы не дублировать бизнес-логику.
  Date/Author: 2026-09-05 / agent.

- Decision: `revisit` кодируем двумя nullable-полями `revisit_at` (ISO-дата) и `revisit_reason` (текст условия/причины); отсутствие обоих = «пересмотр не требуется» (явно помечаем в UI как «нет пересмотра», а не «неизвестно»).
  Rationale: критерий различает «решение требует пересмотра» от «пересмотр не нужен» — нужно уметь выразить оба, а не только дату.
  Date/Author: 2026-09-05 / agent.

- Decision (amends #4, 2026-09-05): `NULL` в `revisit_reason`/`revisit_at` резервируется под legacy/незафиксированные строки и показывает в UI «не зафиксировано», а новые продуктовые строки явно пишут sentinel `revisit_reason="no_revisit_required"` («пересмотр не требуется»).
  Rationale: «отсутствие обоих = нет пересмотра» из #4 неотличимо на уровне строки от legacy-строки, где пересмотр просто не записывался; AC7 запрещает фабриковать значения для legacy. Sentinel-значение — стабильная строка-константа, сравнимая в TS и Python.
  Date/Author: 2026-09-05 / agent.

- Decision (refines #3, 2026-09-05): `outcome` хранится снапшотом на момент записи (как знал прогон: `proposed`/`no_change`), но в проекции `GET /api/decisions` пересчитывается по текущему статусу связанных proposal того же `decision_event_id` (read-time refresh): `approved` (кроме recovery `keep`) → `applied`, recovery `keep` approved → `no_change`, `rolled_back` → `rolled_back`, `pending`/`applying` → `proposed`, `failed` → `failed`, `rejected` → `rejected`. Если у строки нет `decision_event_id` — outcome `unknown` (linkage невозможен); есть event id, но нет proposal — используется сохранённое значение, иначе `unknown`.
  Rationale: статус proposal меняется позже записи решения (approve/reject/rollback — отдельные вызовы), поэтому снапшот устаревает; read-time derivation повторяет special-case `keep` из `services/coach_drift.py`, не вводя отдельной машины состояний. `rolled_back` добавлен в enum: откат — наблюдаемый финальный статус, честнее показывать его, чем маскировать под `applied`/`no_change`.
  Date/Author: 2026-09-05 / agent.

- Decision (2026-09-05): `scope` вычисляется один раз на записи по actions сохранённых proposal этого события; для совет-строк без proposal — `today`. Маппинг action→scope: `build_plan`/`adjust_plan`/`create_plan_constraint`/`retract_plan_constraint` → `plan`; `recovery_replan` → `week` (варианты могут трогать дни в пределах ближайшей недели, включая перенос 1–3 дня); `repair_plan_day` → `today`. Изменений в событиях нет, поэтому read-time refresh для scope не нужен.
  Rationale: proposal action — самый сильный доступный сигнал допустимой зоны влияния; инструмент-имена из ExecPlan §3 (get_upcoming_workouts и т.п.) не детерминированы для маркерных путей, а сохранённый proposal уже прошёл allowlist `save_coach_proposal`.
  Date/Author: 2026-09-05 / agent.

## Outcomes & Retrospective

(Заполняется по завершении реализации.)

## Context and Orientation

Ключевые файлы и их роль:

- `models/coach_decisions.py` — dataclass `CoachDecision` (`decision_type`, `reason`, `workout_id`) и `build_coach_decision(final_response, db=None)` — детерминированный классификатор интента (Push/Moderate/Recovery/Monitor). Здесь добавятся enum'ы и поля `trigger`/`scope`/`outcome`/`revisit`.
- `data/database.py` — таблица `coach_decisions` (колонки `id, date, decision_type, reason, workout_id, chat_id, message_id, metrics_window_days, as_of_date, decision_event_id, narrative_gate_outcome, narrative_gate_reason_codes_json, narrative_gate_rule_version, narrative_evidence_version, narrative_evidence_fingerprint, created_at`); методы `save_coach_decision` и `get_coach_decisions`. Таблица `coach_proposals` уже хранит `decision_event_id`, `base_checkpoint_id`, `applied_checkpoint_id`, `rollback_checkpoint_id`, `source`.
- `api/routers/coach.py` — основной путь записи: `coach_chat` генерирует `decision_event_id` на ход, вызывает `save_coach_proposal` (предложение) и `_save_decision` → `save_coach_decision`. Это триггер `coach_request`.
- `api/recovery_replan_loop.py` — второй путь записи: `run_recovery_replan_loop` вызывает `save_coach_proposal` для восстановительного перепланирования. Это триггер `scheduled_check` (или `proposal`).
- `api/routers/decisions.py` — эндпоинт `GET /api/decisions`, который группирует решения/предложения/recovery-решения по дням и собирает `drift_report` через `services/coach_drift.py`.
- `services/coach_drift.py::build_coach_drift_report` — уже умеет связывать решения и предложения по `decision_event_id` и отличать `no_change` от применённого изменения.
- `web/app/decisions/page.tsx` + `web/lib/types.ts` — UI-поверхность и TypeScript-контракт.

Термины: «триггер» — что запустило прогон (стабильный enum + источник-доказательство); «scope» — допустимая зона влияния решения (today/week/plan); «outcome» — фактический исход (applied/no_change/proposed/…); «revisit» — когда и почему решение пересмотреть (или явное «пересмотр не нужен»); «legacy row» — строка, записанная до этого изменения и не имеющая новых полей.

## Plan of Work

Работа идёт по слоям, каждый слой заканчивается зелёным прогоном.

1. **Модель (`models/coach_decisions.py`).** Добавить модульные константы-строки:
   - `DecisionTrigger = "coach_request" | "scheduled_check" | "provider_sync" | "settings_change" | "proposal_approved" | "manual" | "unknown"`;
   - `DecisionScope = "today" | "week" | "plan" | "unknown"`;
   - `DecisionOutcome = "applied" | "no_change" | "proposed" | "rejected" | "failed" | "unknown"`.
   Расширить `CoachDecision` полями `trigger: str | None = None`, `trigger_source: str | None = None`, `scope: str | None = None`, `outcome: str | None = None`, `revisit_at: str | None = None`, `revisit_reason: str | None = None`.

2. **Хранилище (`data/database.py`).** Аддитивно добавить колонки `trigger`, `trigger_source`, `scope`, `outcome`, `revisit_at`, `revisit_reason` в `coach_decisions` (через `ALTER TABLE ADD COLUMN` с проверкой существования колонки, чтобы метод оставался идемпотентным для существующих БД). Расширить `save_coach_decision` новыми keyword-аргументами и — главное — добавить идемпотентность: перед `INSERT` искать существующую строку с тем же `decision_event_id` (если он непустой) и возвращать её, а не создавать дубль. Расширить `get_coach_decisions` и `_deserialize_coach_decision_row`, чтобы читать новые колонки и отдавать их как `None`, когда они отсутствуют.

3. **Запись (`api/routers/coach.py`).** В `_save_decision` передавать `trigger="coach_request"`, `scope` (вывести из вызванных инструментов: `get_upcoming_workouts` → `today`, `get_active_plan`/rebalance → `plan`, иначе `unknown`), `outcome` (если для этого `decision_event_id` есть proposal → `proposed`/`applied` по его статусу, иначе `no_change` для `Monitor`/`Recovery`-без-изменений, иначе `unknown`), и `revisit_reason` по умолчанию `None` (пересмотр не требуется) с возможностью задать позже. В `api/recovery_replan_loop.py` при записи proposal-решения передавать `trigger="scheduled_check"`.

4. **Проекция (`api/routers/decisions.py`).** Пробрасывать новые поля в выдачу как есть (`item = dict(row)` уже копирует всё), добавив для legacy-строк нормализацию: `None` → `"unknown"` для `trigger`/`scope`/`outcome` на уровне API, чтобы web не падал.

5. **UI (`web/lib/types.ts`, `web/app/decisions/page.tsx`).** Дополнить `CoachDecision` полями `trigger`, `trigger_source`, `scope`, `outcome`, `revisit_at`, `revisit_reason` (все optional/nullable). В `DecisionEntry` (или рядом) выводить строку `trigger · scope · outcome` и, при наличии, `revisit_at`/`revisit_reason`; для `None` показывать «unknown»/«нет пересмотра» без сбоя.

6. **Контракт.** Обновить `web/lib/types.ts`; прогнать `npm --prefix web run contract:extract` (артефакт `tests/contracts/ts_contract.json` обновится), и `contract:extract -- --check` в CI должен остаться зелёным.

## Concrete Steps

Рабочая директория — корень репозитория `/Users/gregkisel/Developer/ai_trainer` (venv `ai_trainer_env`).

Сначала RED-тесты, затем GREEN. Ориентировочные команды:

    ai_trainer_env/bin/python -m pytest tests/smoke/test_agent_log_v2.py -q
    ai_trainer_env/bin/python -m ruff check models/coach_decisions.py data/database.py api/routers/decisions.py api/routers/coach.py
    npm --prefix web run lint && npm --prefix web run build
    npm --prefix web run contract:extract

Тесты (новый файл `tests/smoke/test_agent_log_v2.py`) обязаны покрыть:
- idempotency: два `save_coach_decision` с одинаковым `decision_event_id` дают одну строку;
- новые поля сохраняются и читаются (`trigger`, `scope`, `outcome`, `revisit_at`, `revisit_reason`);
- legacy-строка без новых колонок читается и отдаёт `None`/`"unknown"` без исключения;
- `GET /api/decisions` возвращает новые поля и не падает на старых строках.

## Validation and Acceptance

Acceptance формулируется как наблюдаемое поведение:

- `ai_trainer_env/bin/python -m pytest tests/smoke/test_agent_log_v2.py -q` → `<N> passed`; тест idempotency падает ДО реализации (две строки) и проходит ПОСЛЕ (одна строка).
- `ai_trainer_env/bin/python -m pytest tests/smoke -q` — без новых регрессий.
- `npm --prefix web run lint && npm --prefix web run build` — зелёно; `contract:extract -- --check` — артефакт актуален.
- На `/decisions` (при `NEXT_PUBLIC_SHOW_DEV_TOOLS=true`) строка решения показывает `trigger · scope · outcome`, а старая строка показывает `unknown` и не ломает страницу.

## Idempotence and Recovery

Миграция аддитивная и идемпотентная: `ALTER TABLE ADD COLUMN` выполняется только если колонки ещё нет, поэтому повторный запуск безопасен. Нового удаления или перезаписи данных нет; откат — удаление добавленных колонок/полей не требуется (nullable-колонки безвредны). `decision_event_id` остаётся ключом идемпотентности: повторная запись с тем же id возвращает существующую строку, а не создаёт дубль.

## Artifacts and Notes

(Появятся после реализации: вывод тестов и short-diff миграции.)

## Interfaces and Dependencies

В `models/coach_decisions.py`:

    DecisionTrigger = "coach_request" | "scheduled_check" | "provider_sync" | "settings_change" | "proposal_approved" | "manual" | "unknown"
    DecisionScope = "today" | "week" | "plan" | "unknown"
    DecisionOutcome = "applied" | "no_change" | "proposed" | "rejected" | "failed" | "rolled_back" | "unknown"

    # Константы-значения для записи/сравнения:
    NO_REVISIT_REQUIRED = "no_revisit_required"   # явный «пересмотр не требуется»
    SCOPE_BY_PROPOSAL_ACTION = {"build_plan": "plan", "adjust_plan": "plan",
        "create_plan_constraint": "plan", "retract_plan_constraint": "plan",
        "recovery_replan": "week", "repair_plan_day": "today"}

    def derive_decision_outcome(decision_row, proposal_rows) -> str   # read-time refresh

    @dataclass(frozen=True)
    class CoachDecision:
        decision_type: DecisionType
        reason: str
        workout_id: str | None = None
        trigger: str | None = None
        trigger_source: str | None = None
        scope: str | None = None
        outcome: str | None = None
        revisit_at: str | None = None
        revisit_reason: str | None = None

В `data/database.py::save_coach_decision` добавить keyword-аргументы `trigger=None, trigger_source=None, scope=None, outcome=None, revisit_at=None, revisit_reason=None` и idempotency-проверку по `decision_event_id`. Зависимости: `services/coach_drift.py` (связь decision↔proposal), `api/planning_service` (checkpoint-линковка proposal). Новых внешних библиотек нет.
