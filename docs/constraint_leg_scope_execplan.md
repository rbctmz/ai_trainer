# Scoped coach constraints: per-sport day constraints + leg recovery + incident repair (#473)

This ExecPlan is a living document. Sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` are maintained as work proceeds, per `.agent/PLANS.md` (path from repo root: `.agent/PLANS.md`).

## Purpose / Big Picture

Вечером 18/08 пользователь отменил только плавание в чате коуча («бассейн закрыт») — а день целиком превратился в «отдых 0 TSS»: выполненная вело-тренировка (подтверждённый матч, 28.2 TSS) перестала видна в плане, в план-vs-факт ушла как «вне плана», и запрос на её оценку исчез с экрана «Сегодня» (issue #473). После этого изменения пользователь может сказать «забудь про плавание завтра» — и из дня пропадёт только плавательная нога: другие ноги (вело/бег) сохранятся со своими матчами и feedback-промптами. Появляется штатный путь отката ограничения (`retract_plan_constraint` + API), который возвращает случайно стёртую ногу из ближайшей родительской версии плана. Наконец, разовым скриптом репарации восстанавливается конкретный инцидент 18/08 в реальной БД.

How to see it working: локальный веб-стек (или прямой вызов сервисных функций) → GET `/api/planning/reconciliation?weeks=1` показывает для 2026-08-18 «План 36.5 (bike) · Матч 1/1 · факт 28.2 TSS» вместо «0/0 вне плана 28»; GET `/api/session-feedback/prompts` возвращает `state: "ready"` по сессии `ats_9b34b56a1542f2d95fd69b5c`; план показывает день 18/08 с вело-тренировкой, а плавание помечено отменённым пользователем.

## Progress

- [x] (2026-08-19) Issue #473 открыт с фиксированным корнем (данные: `coach_constraints#1`, чекпоинты 119/120, матчи/фидбек).
- [x] (2026-08-19) M2 RED: новые сценарии в `tests/smoke/test_coach_constraints.py` падают перед реализацией (коммит d16b8c1).
- [x] (2026-08-19) M2 GREEN: колонка `coach_constraints.sport` + миграция; scoped application (per-sport ноги / whole-day / composite fallback / canceled_legs audit); `ConstraintRequest.sport` pydantic-валидатор (422) + мгновенное применение к активному плану (`apply_constraint_to_active_plan`, stale-base → 409); AI tool `create_plan_constraint(sport=...)` + правило выбора даты; `_rebalance_protected_dates` учитывает scope. Замечания review #474 учтены (единственная карта алиасов, rationale canceled_legs, API-валидация, дата фикстуры отсортирована, date→list группировка, 2 тест-кейса добавлены). Коммит f028376 pushed; локальный contributor-safe: 1924 passed, ruff green.
- [x] (2026-08-19) M3 RED: `tests/smoke/test_constraint_retraction.py` (donor walk, без исключений, no-op идемпотентность, stale-base, no-donor, route-кейсы) — 7 failed до реализации.
- [x] (2026-08-19) M3 GREEN: `recover_day_after_constraint_retraction` (donor walk по `checkpoint_parent_id`, stale-base guard первым, no-op идемпотентность, `NoDonorCheckpointError`, `repair_evidence`, пересчёт daily-row и weekly totals через `recalc_goal_plan_weekly_totals`); ребинд сохранённых матчей на ре-стампнутые id (append-only ревизии `supersedes_match_id`); маршруты `POST /constraints/{id}/retract` + `POST /repair-day`; AI tools `get_coach_constraints` / `retract_plan_constraint(id|date+sport)` / `repair_plan_day(date, exclude_sports)` + директивы промпта. Локальный contributor-safe: 1932 passed, ruff green, contract-артефакт неизменён.
- [x] (2026-08-19) M1 выполнен: бэкап `backups/ai_trainer-pre-issue473-20260819.db` (integrity ok); `recover_day_after_constraint_retraction(base=120, date=2026-08-18, exclude_sports=["swim"])` → чекпоинт **121** из донора **119**, вело-нога возвращена, id перешел `ats_9b34…→ats_a163a48c…` (handoff в результате); матч #24 перебинд append-only ревизией (`supersedes_match_id=24`); ограничение **#1 деактивировано** (append-only), новая строка **#2** `sport="swim"` с аннотацией о rewrite. Верификация поверх живой БД (in-process TestClient, те же хендлеры): reconciliation 18/08 — bike tss 36.5, matched/user_confirmed, факт 28.2 (activity 24026706443); feedback-промпт восстановленной сессии `state=ready`; активный план несёт день с вело-тренировкой.
- [x] (2026-08-19) По итогам review #2 (GREEN M2) закрыты две новые находки фикс-срезом: partial-путь пересчитывает `duration_minutes` шаблона дня по выжившим ногам (fixture 40+35→40 + assertion); audit `canceled_legs` обогащён `constraint_id/kind/note` причиной каждой вычеркнутой ноги (причина привязывается к точной строке ограничения, выбравшей именно этот спорт). 1932 passed, ruff green.
- [ ] (pending) Self-review + `ruff` + contributor-safe pytest + contract regen при изменении типов + draft PR.

## Surprises & Discoveries

- Observation: `DELETE /api/planning/constraints/{id}` (deactivate) существует давно, но ничего не делает с уже написанном чекпоинтом: активный план читается из последнего чекпоинта напрямую (`get_active_plan` без накладывания ограничений), поэтому «снятие» не возвращало тренировку. Деактивация влияет только на будущие построения/ребалансы.
  Evidence: `api/planning_service.py::get_active_plan` (только `restore_goal_plan_from_checkpoint(latest)`), `apply_constraints_to_goal_plan` вызывается в `build_plan` и preview-путях, а не в read-маршрутах.
- Observation: Разница между чекпоинтами 119 и 120 полностью ограничена днём 2026-08-18 (template + daily entry + текстовая пометка `adjustment_note` недель, числа недель не менялись кроме недели 17/08). Иными словами, восстановление дня из чекпоинта родителя точечно.
  Evidence: каноническое сравнение JSON двух чекпоинтов: единственные отличия в содержимом — шаблон/день 08-18 и строки `adjustment_note` в `weekly_summary`.
- Observation: Сохранённые матчи привязываются к плану по `target_key = "session:{session_id}"`, а не по базовому чекпоинту (`latest_ledger.get(target_key)` в `build_reconciliation`). Поэтому если вернуть ту же сессию в план, подтверждённый матч снова подсвечет её, без повторного подтверждения.
  Evidence: `models/plan_actual_reconciliation.py` — строение `latest_ledger` и цикл по `parent_sessions`.
- Observation: Fedback id 38 («бассейн закрыт») указывает на сессию `ats_ed65…`, которая в чекпоинте 119 не является ногой 08-18; ограничение создано по поводу swims на 17/08, но датой закреплено 18/08 («сегодня»). Подтверждает: LLM выбрал дату-«неизвестное» плохо и механизм его не подхватил ещё и усилил (см. Decision D5 про hint по выбору даты в описании инструмента).
   Evidence: поиск `ats_ed65b8e442ad17eb38f1df50` по JSON чекпоинта 119 (найдена в другом дне), `coach_constraints.note/created_at`, текст фидбека.
- Observation: движок идентичностей (#205) ставит метки при КАЖДОМ сохранении плана: день из одной сессии наследует **day-fingerprint** — поэтому сужение дня 2 ноги → 1 ре-штампит выжившую ногу на новый id (хотя её `session_material_fingerprint` неизменен), а восстановление целого дня (2→2, одинаковая кардинальность донора и результата) сохраняет исходные id дословно. Значит «вернуть ногу» ≠ «id совпадёт», и сохранённые plan-vs-fact матчи (`target_key=session:{id}`) после перестановки дней зависают — без ребинда нога снова уходит в «вне плана».
  Evidence: `models/session_identity.py` (ветка single-session day), живая БД инцидента, тест `test_rerecover_rebinds_preserved_plan_fact_matches`.

## Decision Log

- Decision: нормализация `sport` живёт ЕДИНИЧНО в `models/coach_constraints.py::CONSTRAINT_SPORT_ALIASES/normalize_constraint_sport`; `data/database.py` тянет их ленивым импортом внутри `save_coach_constraint` (не дублирует карту, не нарушает правило «data/ не импортирует models/ на верхнем уровне»). Фразовые алиасы (`беги`, `в воде`) удалены — на явном параметре только существительные/имена видов (review PR #474). Валидация на API-слое (`ConstraintRequest.sport` → pydantic `field_validator`, 422 на неизвестный спорт); БД-слой — вторая линия обороны для прямых вызовов.
  Date/Author: 2026-08-19, opencode (по замечанию review PR #474).
- Decision: M2 вводит скоуп ограничения через новую nullable колонку `coach_constraints.sport` (пусто = целый день), а не через расшифровку текста `note`.
  Rationale: машинно проверяемо существующий путь применения работает целиком по полям; разбор естественного языка ненадёжен; обратно совместимо (старые строки = whole-day).
  Date/Author: 2026-08-19, opencode.
- Decision: per-sport применение удаляет затронутую ногу списка `sessions[]` конкретного дня (метаданные `canceled_legs` для аудита), пересчитывает `allocated_parts`, `total_tss`, `duration_minutes`; если ног не остаётся — деградирует в классический whole-day `constraint_off`. Не вводится новая форма «плейсхолдер-сессия» внутри `sessions[]`.
  Rationale: все потребители (реконсиляция, fubedback-прмпты, exports, scheduler) уже правильно игнорируют отсутствующие сессии; новый маркер-сессия рисковал бы сломать их молча. Консервативно: для дней `kind=composite`(brick) переспорт невозможен по структуре — такие дни остаются whole-day zeroing. Аудит вычеркнутой ноги ведётся отдельной структурой `canceled_legs` (не переиспользуя `replaced_session_ids` из #205) сознательно: у них разные контракты — `replaced_session_ids` это плоский список id для маппинга идентичностей «кто кого заменил», а `canceled_legs` строка аудита `{session_id, sport, duration_minutes, total_tss, reason}` (что именно было отменено и сколько груза ушло); смешение форм ломало бы один из двух потребителей (review PR #474).
  Date/Author: 2026-08-19, opencode.
- Decision: `retract` (M3) возвращает день из ближайшего предка в дереве чекпоинтов, где день был исполняемым (donor walk по `checkpoint_parent_id`), исключая явно указанные ноги. Новый дочерний чекпоинт с `source="constraint_repair"`, stale-base guard как в `restore_history_version`.
  Rationale: история append-only (чекпоинты никогда не перезапишются); donor walk гарантирует, что вернутся материализованные шаги оригинала, а не пересоздание от шаблонов (потеряли бы идентичности/ссылки `replaces_session_id`).
  Date/Author: 2026-08-19, opencode.
- Decision: случай «донор не найден» в M3 определён явно (review #474): если ни у одного предка цепочки нет дня с исполняемой ногой (план построен уже с активным ограничением), примитив бросает `NoDonorCheckpointError(ValueError)` с reason вида `<date>: no executable ancestor found`, ничего не сохраняя; отдельный тест на этот исход.
  Date/Author: 2026-08-19, opencode (по замечанию review PR #474).
- Decision: при re-stamp выжившей ноги (сужение 2→1) сохранённые `plan_actual_matches` НЕ пересоздаются с нуля — для каждого зависшего матча пишется НОВАЯ immutable-ревизия под новым id со ссылкой `supersedes_match_id` на старую строку и записью `constraint_repair_rebind` в `evidence` (append-only, та же дисциплина, что и дереву чекпоинтов). Handoff-карта `{старый id: новый id}` всегда возвращается в результате репарации (даже при пустой книге матчей), чтобы lineage был виден.
  Rationale: пользовательские подтверждения и ссылки на активности переживают репарацию; история ребиндов читается по цепочке supersedes; ничего не перезаписывается.
  Date/Author: 2026-08-19, opencode.
- Decision: семантика отмены через UI/chat: ограничение c `sport=X`, снятое через **retract**, восстанавливает день БЕЗ спорта X (нога реально отменена пользователем); whole-day restraint снимает день целиком; запрос «забудь про <спорт>» по дате, где стоит только whole-day строка, тоже оставляет этот спорт вне восстановленного дня (строка остаётся деактивированной, скоуп задаёт exclude).
  Rationale: retract = «верни всё, что реально отменил тот факт, который я снимаю»; плавание закрытым бассейном после снятия «забудьте про плавание» возвращать было бы ошибкой. Зафиксено тестом M3 + поведение инструмента `retract_plan_constraint`.
  Date/Author: 2026-08-19, opencode.
- Decision: M1 (ремонт инцидентa) выполняется тем же shared primitive M3, а не ручным SQL-катанием: `recover_day_after_constraint_retraction(base=?, date="2026-08-18", exclude_sports=("swim",))` + **деактивация** `coach_constraints#1` и **новая строка** с `sport="swim"` и note «per-sport rewrite after incident #473; original constraint id=1». Историческая строка НЕ апдейтится: append-only аудит важнее компактности. Решение финализировано ДО запуска M1 (по рекомендации review PR #474, снят статус «уточнить к моменту выполнения»).
  Rationale: один путь исполнения для инцидента и будущих отмен; минимум одноразового кода; неразмывание аудита.
  Date/Author: 2026-08-19, opencode.
- Decision: Изменения UI (кнопка снять ограничение, выбор спорта в форме ограничения) вне этого PR — отдельно по готовности скоупа ядра; контракт web обновляется регенерацией артефакта.
  Rationale: принцип минимальной сложности workflow (Minimal Complexity); пользовательские пути уже открываются через chat коуча и API.
  Date/Author: 2026-08-19, opencode.
- Decision: Описание инструмента `create_plan_constraint` дополняется правилом выбора даты: «определяй дату из контекста сообщения; если речь о прошедшем событии, подтверждай дату перед созданием будущего ограничения».
  Rationale: наблюдение Surprise #4 — половина бага была в неверном выборе даты LLM, вторая — в механизме.
  Date/Author: 2026-08-19, opencode.

## Outcomes & Retrospective

(заполняется по завершении)

## Context and Orientation

Ключевые файлы (пути от корня репо):

- `models/coach_constraints.py` — чистое применение ограничений к goal plan: `apply_constraints_to_goal_plan(goal_plan, constraints)` обнуляет целые дни (шаг текущего поведения), `_refresh_weekly_totals` пересчитывает суммы недель. Goal plan — словарь с `daily_plan` (кортежи `(datetime, total_tss, parts)`) и `session_templates` (карты по дням; у каждой карты `sessions[]` — исполняемые сессии с внутренним кодом вида `bike|run|swim|off|brick`, `total_tss`, `materialized_steps`, устойчивым `session_id`).
- `data/database.py` — `save_coach_constraint` (~стр. 3054), `get_coach_constraints` (~3142), `deactivate_coach_constraint` (~3179); миграции колонок добавляются паттерном `PRAGMA table_info(...) + ALTER TABLE ADD COLUMN` (пример ~861). Таблица `coach_constraints` имеет неиспользуемую пока колонку `session_id`.
- `models/planning_checkpoints.py` — сериализация/восстановление чекпоинтов: `build_planning_checkpoint`, `restore_goal_plan_from_checkpoint`, `with_checkpoint_provenance(source, parent_checkpoint_id, ...)`. Чекпоинты append-only: изменение плана = новая строка `planning_checkpoints`.
- `api/planning_service.py` — `get_active_plan` (read без overlay ограничений), `_apply_active_coach_constraints` (наложение активных ограничений в `build_plan` и rebuild-путь), `_rebalance_protected_dates` (ограничения добавляют дни в защиты ребаланса), `restore_history_version` (паттерн stale-base guard).
- `api/routers/planning.py` — маршруты ограничений (`GET/POST /constraints`, `DELETE /constraints/{id}`), `HistoryRestoreRequest` и `POST /history/restore` как образец контракта восстановления.
- `models/ai_tools.py` — инструмент коуча `create_plan_constraint` (~1239) с описанием; `models/ai_coach_runtime.py` (~93) — директива в системном промите.
- `models/post_workout_feedback.py::build_feedback_prompts` — состояния запроса оценки из реконсиляции-снимака; `services/reconciliation.py::reconciliation_at` + `models/plan_actual_reconciliation.py::build_reconciliation` — сборка «план vs факт» (матчи по `target_key=session:{id}`).
- `tests/smoke/test_coach_constraints.py` — текущие smoke-сценарии ограничений (база для новых тестов).

Terminology: «нога (leg)» — одна исполняемая сессия дня; день может иметь несколько ног разных видов спорта (триатлоновый день: вело+плавание). «Oграничение (constraint)» — durable запись `coach_constraints`, защищающая дату при повторном построении плана. «Чекпоинт» — append-only версия активного плана в `planning_checkpoints`.

## Plan of Work

M2 (механика скоупа), порядок:

1. RED: в `tests/smoke/test_coach_constraints.py` добавить сценарии (см. Validation), запускаем: `python -m pytest tests/smoke/test_coach_constraints.py -q` — ожидаем падения по новым кейсам.
2. Миграция и слой данных в `data/database.py`: колонка `sport TEXT` (nullable; `NULL`=целый день); `ALTER TABLE` по существующему паттерну; `save_coach_constraint(..., sport=None)`, нормализация видов спорта через единый `models.coach_constraints.normalize_constraint_sport` (`swim/swimming/плавание -> swim`, `run/running/бег -> run`, `bike/cycling/velo/вело -> bike`; фразовые алиасы не используются), поле `sport` в результат `get_coach_constraints`.
3. Применение в `models/coach_constraints.py`: замена `_active_constraints_by_date` (date→один constraint через `setdefault`) на группировку **date → список ограничений** с детерминированным порядком (порядок записи из БД: date ASC, id ASC) — это требуется для кейса двух per-sport ограничений одной даты (swim+bike → whole-day off, review PR #474). Ветвление на scope: per-sport — удаление затронутых ног, пересчёт дня; whole-day — без изменений (регрессия защищена существующими тестами); если ног не остаётся — деградация в classic whole-day zeroing. `_refresh_weekly_totals` вызывать всегда. Новая метаданные-пометка `canceled_legs` на шаблоне дня (список `{session_id, sport, duration_minutes, total_tss, reason}` — строки аудита, НЕ переиспользование `replaced_session_ids`, см. Decision Log).
4. API: `ConstraintRequest.sport: Optional[str]` в `api/routers/planning.py`, передача в `db.save_coach_constraint` и немедленное применение к активному плану (как у AI tool: restore + apply + save child checkpoint), ответ с `scope` в сообщении.
5. AI tool: опциональный параметр `sport` в `create_plan_constraint` (schema-описание и инструкция: пусто = весь день; «не могу плавать» = swim); обновление директивы в `ai_coach_runtime.py` + правило выбора даты (Decision D5).
6. Защита ребалансов: в `_rebalance_protected_dates` добавлять дату ограничения только если оно whole-day.
7. Contract: `npm --prefix web run contract:extract` (при изменении типов артефакт будет меняться); `web/lib/types.ts` регенерируемой частью не трогают, кроме автогенерации.

M3 (откат): shared примитив в `api/planning_service.py` — `recover_day_after_constraint_retraction(db, *, base_checkpoint_id, date, exclude_sports=())`:
- Проверка актуальности `base_checkpoint_id` (StalePlanningCheckpointError иначе — образец `restore_history_version`).
- Donor walk: начиная с родителя базового чекпоинта вверх, первый предок, где день имел >=1 исполняемую сессию (и не `constraint_off`), является донором. Если цепочка исчерпана и донора нет (план построен уже с активным ограничением) — `NoDonorCheckpointError(ValueError)` с reason `<date>: no executable ancestor found`, чекпоинт НЕ сохраняется (review PR #474).
- Объединение: день заменяется шаблон/записью донора, за вычетом ног `exclude_sports`; дневные части/TSS/duration пересчитываются; метаданные `repair_evidence` на шаблоне; `with_checkpoint_provenance(source="constraint_repair", parent_checkpoint_id=base)`; сохранить дочерний чекпоинт. Возвращает `{restored_session_ids, changed_date, applied_checkpoint_id}`. Идемпотентность: если день уже имеет исполняемые сессии (кроме исключённых), — вернуть no-op с флагом.
- API endpoint `POST /planning/constraints/{id}/retract` (деактивирует ограничение + вызывает примитив с `exclude_sports` = sport ограничения) и аналог `POST /planning/repair-day` для разового вызова (используется одним M1-скриптом).
- AI tool `retract_plan_constraint(constraint_id?)` (или date+sport) в `models/ai_tools.py` + описание: «возвращает тренировку после ошибочной отмены».
- Тесты: фикстура двух чекпоинтов (родитель с двумя ногами, потомок collapsed); assert восстановленные `session_id` идентичны родителю; stale-base; no-op; whole-day retract возвращает обе ноги; **no-donor** → `NoDonorCheckpointError` без сохранения (review PR #474).

M1 (инцидент 18/08), после M2/M3 green:
1. Попросить пользователя закрыть веб-стек (BД пишется).
2. `python scripts/sqlite_backup_restore.py backup --database ai_trainer.db --output backups/ai_trainer-pre-issue473-YYYYMMDD.db --confirm-stopped`.
3. Скрипт одного вызова (вызывается из python REPL/shell, код не коммитится кроме helper'а, если нужен): создать БД-клиент `Database("ai_trainer.db")`; вызвать `recover_day_after_constraint_retraction(db, base_checkpoint_id=<latest>, date="2026-08-18", exclude_sports=["swim"], persist=True)`; затем по зафиксированному решению D3/M1 (Decision Log): `db.deactivate_coach_constraint(1)` + новая строка `save_coach_constraint(date="2026-08-18", kind="unavailable", source="user", sport="swim", note="per-sport rewrite after incident #473; original constraint id=1")`. Историческая строка #1 не редактируется.
4. Рестарт стека, curl трёх проверок (Validation), запись результата в Progress и Artifacts.

## Concrete Steps

Все команды из корня репо, venv активирован (`source ai_trainer_env/bin/activate`).

- RED: `python -m pytest tests/smoke/test_coach_constraints.py -q` (новые кейсы падают).
- GREEN: там же зелёный; затем `python -m ruff check .` и шире `python -m pytest -m "not live and not debug and not e2e" tests/ -q`.
- Contract: `npm --prefix web run contract:extract && git status` (коммитнуть изменившийся `tests/contracts/ts_contract.json` и типы, если генератор их трогает).
- M1: см. шаги выше; curl:
  - `curl -s localhost:8000/api/planning/reconciliation?weeks=1 | python3 -m json.tool` → найти день 2026-08-18: план bike TSS 36.5, матч 1/1, факт 28.2.
  - `curl -s "localhost:8000/api/session-feedback/prompts?as_of=2026-08-19" | python3 -m json.tool` → промпт по `ats_9b34b56a1542f2d95fd69b5c` со статусом `ready`.
  - `curl -s localhost:8000/api/planning/plan` → в днях есть 2026-08-18 с вело-тренировкой 36.5 TSS.

## Validation and Acceptance

BDD (новые сценарии в `tests/smoke/test_coach_constraints.py`, плюс расширение фикстуры):

- Given цель-план с двумя ногами дня (bike easy 36.5 + swim easy 27.5, `kind:"single"`) и When сохранено ограничение `sport="swim"` на эту дату, Then day сохраняет bike-ногу (`session_id`, `materialized_steps`, `total_tss` не изменяются), swim-нога отсутствует из `sessions[]`, `allocated_parts["swim"] == 0.0`, дневной `total_tss == bike only`, weekly sum отражает уменьшение, шаблон несёт `canceled_legs` с данными старой swim-ноги.
- Given тот же день и When whole-day `kind="sick"` (без sport), Then поведение совпадает с текущим: `sessions: []`, `constraint_off`, `TSS 0` (регрессия, покрыто существующими кейсами).
- Given два per-sport ограничения (swim и bike) одной даты, Then день становится whole-day off (оба исчерпаны).
- Given composite (brick)-день с `kind="composite"` и When per-sport ограничение, Then консервативный whole-day zeroing (ограничение применимо, день ноль) — документированное ограничение.
- Given `save_coach_constraint(sport="плавание")` and When читать обратно, Then `sport == "swim"`; `sport=None` сохраняется как NULL.
- Given ограничение sport=swim активно и When `_rebalance_protected_dates`, Then дата дня НЕ входит в защищённый набор (в отличие от whole-day).
- M3: Given цепочка чекпоинтов A(две ноги) -> B(collapsed) и When `recover_day_after_constraint_retraction(base=B, date, exclude_sports=("swim",))`, Then новый чекпоинт C: bike-нога с оригинальными `session_id`/steps, swim отсутствует, `checkpoint_source=="constraint_repair"`, `checkpoint_parent_id==B.id`; повтор вызов по C — no-op; другой base — `StalePlanningCheckpointError`.
- Инцидент (E2E вручную, M1): после ремонта реального инцидента — три curl выше показывают ожидаемое (план bike 36.5 / матч 1/1 / факт 28.2; промпт ready; день виден в плане).

DoD: smoke зелёный + полный contributor-safe проход зелёный, ruff green, contract-артефакт свежий (CI job web-contract проходит), нет regressions в `test_coach_constraints.py`/`test_planning_execution.py`/`test_api_planning*.py`, инцидент подтверждён живыми curl'ами, PR связан с #473.

## Idempotence and Recovery

- Каждый milestone коммитится отдельным RED/GREEN срезом (правила @claude action из AGENTS.md).
- Миграция additive (Nullable column) — ретро-совместима; повторный запуск безопасен (паттерн `IF NOT EXISTS`/`ALTER TABLE` при отсутствии колонки).
- Репарация инцидентов всегда создаёт новый дочерний чекпоинт: исходные чекпоинты неизменяемы; rollback — восстановление любой предыдущей версии через существующий `POST /planning/history/restore`.
- Бэкап БД до любого прямого writes хранится в `backups/` (уже gitignored) и называется с датой.

## Artifacts and Notes

- Данные инцидента: `coach_constraints#1` (date 2026-08-18, whole-day, note про плавание), чекпоинты 119->120 (diff ограничен днём 08-18), `plan_actual_matches#24` (user_confirmed, bike), активность 24026706443 (indoor_cycling 28.2 TSS), фидбек 38 (swim `did_not_start`).
- (дополняется транскриптами тестов/curl по мере выполнения)

## Interfaces and Dependencies

- `data.database.Database.save_coach_constraint(date, kind, source, note, plan_id=None, session_id=None, sport=None, metadata=None)` — новый optional kwarg `sport`; допустимые значения нормализуются в `{"bike","run","swim"}` (алиасы см. Plan of Work шаг 2); `NULL`/`None` = whole-day.
- `models.coach_constraints.apply_constraints_to_goal_plan(goal_plan, constraints)` — сигнатура не меняется; поведение расширяется по `constraint.get("sport")`.
- `api.routers.planning.planning_create_constraint(ConstraintRequest{date,kind,source,note,plan_id,session_id,sport?})`.
- `ai_tools.create_plan_constraint(date="", kind="unavailable", note="", sport="")`.
- Новое: `api.planning_service.recover_day_after_constraint_retraction(db, *, base_checkpoint_id: int, date: str, exclude_sports: Sequence[str] = ()) -> Dict` и маршрут `POST /api/planning/constraints/{constraint_id}/retract` и `POST /api/planning/repair-day`.
- Зависимости: никаких внешних библиотек не требуется; Python stdlib + FastAPI/pydantic уже есть.

---

Изменение документа от 2026-08-19 (opencode): первая ревизия из исследования инцидента — добавлены Decision D3/D5, M1 переопределён через shared primive M3 (вместо ручной правки JSON чекпоинта), найден и зафиксирован путь `target_key`-привязки матчей, что делает восстановление матча автоматикой. Причина: первоначальный черновик планировал ad-hoc JSON-patch чекпоинта; аудит кода показал штатный append-only примитив (checkpoints provenance + donor) как более безопасный путь, устраняющий риск рассинхронизации идентичностей сессий.
