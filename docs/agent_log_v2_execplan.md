# Agent Log v2: trigger, scope, outcome, revisit для решений коуча (#501)

Этот ExecPlan — живой документ. Разделы `Progress`, `Surprises & Discoveries`, `Decision Log` и `Outcomes & Retrospective` обязаны поддерживаться в актуальном состоянии по мере работы. Требования к формату ExecPlan описаны в `.agent/PLANS.md` (корень репозитория); документ ведётся в соответствии с ними.

## Purpose / Big Picture

Сейчас журнал решений коуча (`/decisions`) показывает **что** коуч решил (Push/Moderate/Recovery/Monitor) и **почему** (reason), но не отвечает на четыре вопроса: **что запустило** решение (coach-запрос, синк, чек, смена настроек, утверждённое предложение), **насколько далеко** ему позволено влиять (сегодня / неделя / весь план), **что реально произошло** (включая осознанное «без изменений», которое сейчас выглядит как отсутствующее событие) и **когда/почему** решение будет пересмотрено.

После этого изменения каждая строка журнала несёт стабильные поля `trigger`, `scope`, `outcome` и `revisit`, а повторный прогон (retry/replay) не создаёт дубль логического решения. Человек, открыв `/decisions`, видит полную причинно-следственную цепочку решения: запуск → допустимая зона влияния → фактический исход → план пересмотра. Устаревшие строки остаются видимыми с пометкой «unknown», ничего не стирается и не досочиняется.

## Progress

- [x] (2026-09-05) Изучены `models/coach_decisions.py`, таблица `coach_decisions`, `api/routers/decisions.py`, `web/app/decisions/page.tsx`, `web/lib/types.ts`, `services/coach_drift.py`, вызовы `save_coach_decision`/`save_coach_proposal`, issue #501.
- [x] (2026-09-05) Написан ExecPlan (этот документ).
- [x] (2026-09-05) Ветка `codex/issue-501-agent-log-v2` создана; префлайт публикации пройден (origin = rbctmz/ai_trainer, gh auth как rbctmz). Зафиксированы уточнения дизайна (Decision Log #5–#8): read-time derivation outcome, sentinel `no_revisit_required`, action→scope маппинг, `rolled_back` в enum.
- [x] (2026-09-05) Реализована schema/модель: значения/наборы `DECISION_TRIGGERS`/`DECISION_SCOPES`/`DECISION_OUTCOMES` (включая `rolled_back`), `NO_REVISIT_REQUIRED`, `SCOPE_BY_PROPOSAL_ACTION` + `scope_for_proposal_actions`, `derive_decision_outcome` (read-time refresh), поля `CoachDecision`. Коммит `71acdfb`.
- [x] (2026-09-05) Аддитивная миграция `coach_decisions` (6 nullable TEXT-колонок: fresh CREATE + `_COACH_DECISION_COLUMN_TYPES`) + идемпотентность по `decision_event_id` в `save_coach_decision` (SELECT-then-return, без unique-индекса — legacy-дубликаты не должны ломать init) + расширенные SELECT/десериализация (индексы 16–21 с len-guards). Коммит `71acdfb`.
- [x] (2026-09-05) Точка записи `api/routers/coach.py::_save_decision`: `trigger="coach_request"`, `scope` по actions сохранённых proposal события (`scope_for_proposal_actions`; совет-без-proposal → `today`), снапшот `outcome` (`proposed` при наличии proposal события, иначе `no_change`), `revisit_reason=NO_REVISIT_REQUIRED`; `coach_chat` собирает `event_proposal_actions` (включая pending recovery-proposal из replan-лупа). Коммит `71acdfb`.
- [x] (2026-09-05) Проекция `api/routers/decisions.py`: `_project_agent_log_v2_row` — `trigger`/`scope` нормализуют NULL → `"unknown"`, `outcome` пересчитывается через `derive_decision_outcome` по текущему жизненному циклу proposal. Коммит `71acdfb`.
- [x] (2026-09-05) UI: `web/lib/types.ts` (юнионы `DecisionTrigger`/`DecisionScope`/`DecisionOutcome`, 6 полей `CoachDecision`), `web/components/ui/DecisionEntry.tsx` (чипы trigger · scope · outcome + revisit-заметка; отсутствующие ключи до-#501 payload → без чипов). Артефакт `tests/contracts/ts_contract.json` перегенерирован (`contract:extract`, `-- --check` зелёный). Коммит `19946a0`.
- [x] (2026-09-05) `tests/smoke/test_agent_log_v2.py` — 10 тестов RED (10 failed на базе) → GREEN (10 passed); регрессии test_coach_decisions/test_coach_drift/test_recovery_replan_loop/test_api_today/test_contract_extractor/test_api_call_inventory/test_ai_coach_chat_shell/test_ai_coaching_demo_flow/test_api_operational_states зелёные; Ruff чист.
- [x] (2026-09-05) Первичная реализация прошла contributor-safe pytest (`2318 passed, 2 skipped`), Ruff, web lint/build и contract freshness; ветка опубликована как PR #551.
- [x] (2026-09-05) Независимый первичный разбор PR #551 воспроизвёл четыре blocking-дефекта: конкурентный replay создавал дубли; четыре заявленных trigger не имели production producers; proposal записывался как `proposed` + `no_revisit_required`; группировка скрывала различающиеся v2-события.
- [x] (2026-09-05) Добавлены шесть RED-регрессий: детерминированный 16-поточный replay и реальные producer/lifecycle/grouping сценарии. До исправлений итог был `6 failed, 9 passed`; отдельный concurrency-тест наблюдал 16 разных id.
- [x] (2026-09-05) GREEN-срез реализован через атомарную запись, общий `services/agent_log.py`, production producers и metadata-aware группировку. `test_agent_log_v2.py`: `15 passed`; смежные recovery/coach/settings/sync/today тесты: `121 passed`.
- [x] (2026-09-05) На behavior head `aec862b` финальные локальные проверки зелёные: contributor-safe `2322 passed, 3 skipped, 26 deselected`; Ruff clean; web lint/build clean; contract artifact current.
- [ ] Независимый read-only OpenCode delta-аудит, disposition находок, финальный evidence commit/push и обновление PR #551.

## Surprises & Discoveries

- **Observed**: таблица `coach_decisions` уже имеет поле `decision_event_id`, которое генерируется один раз на ход коуча (`api/routers/coach.py::coach_chat`, `str(uuid.uuid4())`) и передаётся и в `save_coach_decision`, и в `save_coach_proposal`; `services/coach_drift.py::_event_id` извлекает этот id и связывает решения и предложения. Источник: чтение `api/routers/coach.py` и `services/coach_drift.py`.
- **Inferred**: `decision_event_id` — готовый ключ идемпотентности и событийной связи; его нужно только сделать уникальным (сейчас `save_coach_decision` вставляет без проверки на дубль). Самая дешёвая проверка-опровержение — два вызова `save_coach_decision` с одинаковым `decision_event_id` на временной БД: если появится две строки, гипотеза «уникальность не гарантирована» верна.
- **Verified by**: `save_coach_decision` не содержит `SELECT`-проверки на существующий `decision_event_id` перед `INSERT` (чтение кода); полноценный RED-тест добавим в `Concrete Steps`.

- **Observed**: status proposal меняется ПОСЛЕ записи решения — `approve_proposal`/`reject_proposal`/`rollback_proposal` вызывают только `update_coach_proposal_status`, строку `coach_decisions` не трогают (`api/routers/decisions.py`, чтение кода).
- **Inferred**: снапшот `outcome` на момент записи устаревает (решение записано как `proposed`, а через час применено); read-time refresh по связанным proposal покажет актуальный исход без новой машины состояний. Дешёвая проверка — RED-тест жизненного цикла (proposed → applied → rejected через `update_coach_proposal_status` без перезаписи решения).
- **Verified by**: `test_decisions_api_refreshes_outcome_from_proposal_lifecycle` падал до проекции (`KeyError: 'trigger'`) и проходит после (`10 passed in 0.93s` на финальном дереве); special-case approved `keep` → `no_change` закрыт `test_decisions_api_shows_approved_keep_as_no_change`.

- **Observed**: legacy-строка и новая строка «без пересмотра» неразличимы, если отсутствие `revisit_at`/`revisit_reason` трактовать как «пересмотр не требуется» — у legacy метаданные просто не записывались (проектирование #501, AC7 «не фабриковать»).
- **Inferred**: нужен явный sentinel для новых строк, а NULL резервировать под legacy. Проверка — unit-тест, сохраняющий обе категории и читающий их обратно.
- **Verified by**: `test_legacy_database_migrates_and_reads_metadata_as_null` (NULL после миграции) и запись sentinel `no_revisit_required` в write-site-тестах; UI различает «Пересмотр не требуется» (sentinel) и отсутствие чипа (NULL).

- **Observed**: `save_coach_decision` (2026-09-05, реализация) сперва упал с `sqlite3.OperationalError: 21 values for 20 columns` — рассинхрон плейсхолдеров при расширении INSERT (вывод pytest).
- **Inferred**: арифметическая ошибка при добавлении шести колонок; уникальный-индекс вариант идемпотентности отклонён до тестов legacy-дублей.
- **Verified by**: после правки числа `?` (20) тест `test_database_persists_agent_log_v2_fields` проходит; полный прогон ниже.

- **Observed**: 16 конкурентных вызовов `save_coach_decision` с одним `decision_event_id` вернули 16 разных id после синхронного старта непосредственно перед lookup.
- **Inferred**: отдельные `SELECT` и `INSERT` не владеют одним SQLite write transaction, поэтому каждый retry успевает увидеть отсутствие строки. Дешёвая проверка-опровержение — тот же барьерный тест после `BEGIN IMMEDIATE`: если гипотеза неверна, дубли останутся.
- **Verified by**: `test_database_concurrent_replay_creates_one_logical_decision` падал `16 == 1`, а после переноса нормализации ключа перед атомарным `BEGIN IMMEDIATE` проходит и возвращает один id.

- **Observed**: production-поиск находил только один `save_coach_decision` в `api/routers/coach.py` с hard-coded `coach_request`; два v2-события с одинаковыми reason/type, но разными trigger/scope/outcome, API сворачивал в один item с `count=2`.
- **Inferred**: enum и persistence fixtures не обеспечивают acceptance без реальных producer boundaries, а старая группировка стирает provenance. Фальсификаторы — вызвать recovery loop, sync manager, settings PUT и proposal approval на temp DB, затем прочитать Agent Log; отдельно подать две различающиеся строки в `list_decisions`.
- **Verified by**: четыре producer-сценария и grouping-тест падали до изменения; после подключения общего writer и расширения grouping key все входят в `15 passed`.

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

- Decision (review correction, 2026-09-05): атомарность replay обеспечивается `BEGIN IMMEDIATE` вокруг lookup+insert, без UNIQUE-миграции существующей таблицы.
  Rationale: transaction сериализует все новые writers через официальный Database boundary, а legacy-дубликаты остаются нетронутыми согласно non-goal. Детерминированный 16-поточный тест является lifecycle gate.
  Date/Author: 2026-09-05 / agent.

- Decision (review correction, 2026-09-05): новые product producers используют общий `services/agent_log.py`; standalone recovery evaluation пишет `scheduled_check`, terminal sync job — `provider_sync`, briefing PUT — `settings_change`, успешный approval — отдельный `proposal_approved`. Recovery loop внутри coach-turn не пишет конкурирующий scheduled-event: внешняя строка `coach_request` остаётся владельцем общего proposal linkage.
  Rationale: acceptance требует реальные источники, но один proposal должен сохранять одного origin owner. Отдельная standalone/embedded семантика предотвращает collision одного `decision_event_id` между двумя строками.
  Date/Author: 2026-09-05 / agent.

- Decision (review correction, 2026-09-05): pending proposal получает revisit condition `proposal_resolved`; scheduled data-gap/no-change — `next_scheduled_check`; failed provider sync — `provider_available`; terminal applied/no-change events — `no_revisit_required`. Повторные строки группируются только при совпадении всей v2 provenance-семантики.
  Rationale: outcome и revisit не должны противоречить друг другу, а aggregate presentation не может скрывать trigger/source/scope/outcome другой записи.
  Date/Author: 2026-09-05 / agent.

## Outcomes & Retrospective

(2026-09-05, завершение реализации на `codex/issue-501-agent-log-v2`)

Сделано: строки `coach_decisions` теперь несут стабильные поля trigger/scope/outcome/revisit (nullable TEXT, аддитивная миграция); `save_coach_decision` идемпотентен по `decision_event_id`; точки записи coach-чата заполняют метаданные; `GET /api/decisions` нормализует legacy-строки в `unknown` и освежает outcome по жизненному циклу proposal; web-слой показывает чипы trigger · scope · outcome и revisit-заметку; контракт-артефакт перегенерирован.

Проверки на финальном дереве: `python -m ruff check .` — чисто; полный contributor-safe прогон `python -m pytest -m "not live and not debug and not e2e" tests/` — 2318 passed, 2 skipped (garth не установлен — до-существующий skip), 0 failed (базовый сценарий issue: «не добавлять регрессий»); `npm --prefix web run lint` и `npm --prefix web run build` — зелёные; `npm --prefix web run contract:extract -- --check` — артефакт актуален; регрессии test_coach_decisions/test_coach_drift/test_recovery_replan_loop/test_api_today/test_contract_extractor/test_api_call_inventory — зелёные.

Первичный retrospective выше был уточнён после blocking review. Recovery-решения сохраняют собственную таблицу, но standalone recovery evaluation дополнительно создаёт sourced Agent Log event; `provider_sync`, `settings_change` и `proposal_approved` теперь имеют реальные producers. Автономного планировщика пересмотра по-прежнему нет: revisit хранит стабильное условие следующего уже существующего product event, а не обещание нового scheduler.

(2026-09-05, review-correction milestone) Четыре найденных acceptance-дефекта исправлены и защищены воспроизводимыми тестами. Атомарность достигнута без переписывания legacy data; producer-границы используют один contract writer; embedded recovery не конкурирует с coach-request ownership; API больше не агрегирует семантически разные v2 rows. Behavior head `aec862b` прошёл contributor-safe `2322 passed, 3 skipped, 26 deselected`, Ruff, web lint/build и contract freshness. Внешний delta-review ещё не завершён, поэтому итоговый verdict пока не READY.

Уроки: снапшоты метаданных на записи и поздние мутации статуса (approve/reject/rollback) — разные источники истины; read-time derivation с явным fallback на stored-значение оказалась дешевле машины состояний и повторила special-case `keep` из drift-отчёта без расхождения. NULL как «нет данных» и sentinel как «нет пересмотра» — обязательная пара для честного legacy-режима (AC7). Числовые плейсхолдеры вручную расширяемых INSERT — источник ошибок (21 values for 20 columns); на будущее — генерировать списки колонок/плейсхолдеров из одного кортежа.

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

3. **Запись (`services/agent_log.py` и producers).** Все новые product events проходят через `record_agent_decision`, который требует event id, source evidence и revisit. `api/routers/coach.py` пишет `coach_request`; standalone `api/recovery_replan_loop.py` пишет `scheduled_check`; `api/sync_jobs.py` пишет terminal `provider_sync`; `api/routers/settings.py` пишет briefing `settings_change`; успешный `approve_proposal` пишет отдельный `proposal_approved`. Embedded recovery внутри coach-turn не создаёт вторую decision row с тем же origin id.

4. **Проекция (`api/routers/decisions.py`).** Пробрасывать новые поля в выдачу как есть (`item = dict(row)` уже копирует всё), нормализовать legacy `None` → `"unknown"` для `trigger`/`scope`/`outcome` и агрегировать повторения только при совпадении trigger/source/scope/outcome/revisit.

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

- `ai_trainer_env/bin/python -m pytest tests/smoke/test_agent_log_v2.py -q` → `15 passed`; concurrency idempotency падает ДО review correction (16 строк) и проходит ПОСЛЕ (одна строка).
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

---

Изменение плана 2026-09-05: после первичного blocking review добавлены атомарная concurrency-семантика, реальные producer boundaries, proposal-aware revisit и provenance-aware grouping. Progress, discoveries, decisions, outcomes, plan steps и acceptance обновлены, потому что первоначальный retrospective ошибочно считал enum-only triggers и SELECT-then-INSERT достаточным завершением #501. Детальная Class A RED/review матрица вынесена в `docs/agent_log_v2_slice_spec.md` согласно шаблону процесса.
