# План vs факт по репетициям (#383)

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds. Maintain this document in accordance with `.agent/PLANS.md` from the repository root.

## Purpose / Big Picture

Шаг 3 из #379 и самый крупный пункт: AI-тренер «слеп» к структуре выполненной работы — видит только суммарные метрики. После этого клина карточка показывает «план vs факт по репетициям»: плановая структура (3×(12' @90% / 4' @55')) сопоставляется с детектированными интервалами факта из Intervals.icu, и атлет/тренер видят отклонения.

**Ключевое решение разведки (2026-08-07):** структурированные плановые интервалы **уже существуют** как `materialized_steps` (`workout_catalog.py:907`) — парсить текст описания НЕ нужно. Нужно лишь спроецировать steps → компактные `intervals` и связать с фактом. Спорт-скоуп первого клина — cycling/бег (там фактическая структура по power/HR наиболее надёжна и materialized_steps наиболее структурированы).

После этого клина: `_finalize` материализует компактные плановые `intervals`; `_planned_snapshot` несёт их в `plan_actual_matches`; сервис матчит плановые шаги с фактическими интервалами (#390) по порядку/длительности; карточка показывает «план 3×(12'/4') → факт 3×(11'40\"/4'10\")».

## Progress

- [x] (2026-08-07) Разведка. `materialized_steps` уже персистятся в `planning_checkpoints.checkpoint_data → goal_plan_snapshot.session_templates[].materialized_steps` (каждый шаг: `{index, name, intensity, duration_seconds, target:{type,low,high,relative_low,relative_high}, segment_kind, repeat_index}`). Точки интеграции подтверждены своими глазами: `_finalize` (`training_planner.py:2099`), `_planned_snapshot` (`plan_actual_reconciliation.py:155`).
- [x] (2026-08-07) Подтверждено на живых данных: есть bike plan-actual-матчи (`2026-07-28` act `23765394202` ↔ Intervals `i170127087`; `2026-07-27` ↔ `i169725694`) с intervals-линками → фактические интервалы (#390) доступны для матчинга.
- [x] (2026-08-07) Milestone 1: проекция materialized_steps → компактные плановые `intervals` (чистый нормализатор `models/plan_intervals.py`).
- [x] (2026-08-07) Milestone 2: расширение `_planned_snapshot` + `planned_intervals` в карточке API (read-side reconciliation).
- [x] (2026-08-08) Milestone 3: матчинг план-шаг ↔ факт-интервал по репетициям (`models/plan_vs_fact.py::match_plan_vs_fact`; работа по порядку + длительность, tolerance ±30%, greedy-потребление, fail-open на пустых/мусорных входах).
- [x] (2026-08-08) Milestone 4: web-секция «План vs факт» в карточке (сумма по плану/факту/совпадениям + строки «план → факт → отклонение/зона»; скрыта без плана).
- [x] (2026-08-08) P1 (Codex review): резолв вложенных сессий `template["sessions"]` до date-фолбэка — иначе на multi-session дне проецировалась бы не та сессия. Live-проверка на 07-27/28; PR #395.
- [x] (2026-08-08) Полный smoke — 1601 passed, 1 skipped; ruff/ESLint/build зелёные. Мерджи #394 и #395 (решают #383).
- [x] (2026-08-13) На живой пробежке выявлено ограничение greedy-матчера: плановый этап 19:15 был выполнен тремя последовательными кругами 7:45 + 7:33 + 3:57, но показывался как отсутствующий.
- [x] (2026-08-13) Добавлено временное сопоставление всех этапов плана с непрерывными группами фактических участков; осторожный прежний режим сохранён для разреженных интервалов.
- [x] (2026-08-13) Web-секция переработана: русские названия этапов, длительность плана/факта, количество объединённых участков и раздельные подписи цели/фактической зоны.
- [x] (2026-08-13) Целевые проверки: 57 passed; полный smoke: 1711 passed, 1 skipped; Next lint/build и compileall зелёные. Браузерная проверка активности `23958642824`: 4/4 этапа, 2/2 рабочих, длинный этап 19:15 объединяет 3 участка.
- [x] (2026-08-13) Продолжение: факт сгруппирован в те же четыре этапа, высота обеих полос приведена к единой шкале интенсивности относительно порога, цвет факта показывает попадание в цель, а внутренние Auto Lap отмечены тонкими разделителями.
- [x] (2026-08-13) Интенсивность проверена для pace/power/heart-rate и безопасного отсутствия порога; 1718 smoke passed, 1 skipped; Next lint/build, compileall и повторная браузерная приёмка зелёные.

## Surprises & Discoveries

- Observation: **структурированные плановые интервалы уже существуют** как `materialized_steps`. НЕ нужно парсить `_build_session_description` (он генерирует только метаданные: Фаза/Роль/TSS — не «3×12'/4'»).
  Evidence: `models/workout_catalog.py:907-925` — каждый шаг несёт `{intensity: work|easy|steady, duration_seconds, tss, target:{type,low,high,relative_low,relative_high}, segment_kind: warmup|work|recovery|cooldown|stage, repeat_index}`. Это почти то, что нужно для матчинга — проекция, а не генерация.

- Observation: `_REPEAT_PRESCRIPTIONS` (`workout_catalog.py:365-472`) — таблицы «3×8'/4'» по стимулам (threshold/vo2/tempo). `_RepeatTier` (`:53-59`) = `{repeat_count, work_seconds, recovery_seconds}`. Пример `bike_threshold` (`:379`): short=3×5'/3', medium=3×8'/4', long=4×8'/4'. Это уже машиночитаемые репетиции.

- Observation: плановые шаги **уже персистятся** в БД. `planning_checkpoints.checkpoint_data → goal_plan_snapshot.session_templates[].materialized_steps`. Подтверждено живым запросом (5 steps, sample: `{intensity:"easy", duration_seconds:405, target:{type:"power", low:72, high:100, relative_low:0.42, ...}}`).

- Observation: `plan_actual_matches.planned_snapshot_json` — **минимальная** проекция (`{index, session_id, date, sport, role, phase, name, tss, duration_minutes, parts}`), БЕЗ интервалов. JSON-колонка → расширение без миграции БД (`data/database.py:516`).
  Evidence: `models/plan_actual_reconciliation.py:149-166`.

- Observation: есть **реальные bike plan-actual-матчи** с intervals-линками для матчинга. `2026-07-28` act `23765394202` ↔ Intervals `i170127087`; `2026-07-27` act `23751063360` ↔ `i169725694`. Факт доступен через `get_activity_intervals` (#390).

- Observation: матчинг «по репетициям» должен сопоставлять **по порядку + длительности**, не по таймстемпам. Плановый шаг «12' work @90%» → фактический интервал с `moving_time ≈ 720s` и высокой intensity. Разминка/заминка (`segment_kind`) участвуют, но главный фокус — work-репетиции.

- Observation: один этап плана может законно состоять из нескольких кругов устройства. Garmin сохраняет Auto Lap внутри этапа структурированной тренировки; Intervals.icu в режиме Use Laps вернул непрерывную последовательность 5:16, 7:45, 7:33, 3:57, 5:15, 5:21 для плана 5:15, 19:15, 5:15, 5:15.
  Evidence: три средних круга суммируются ровно в 19:15, однако старый алгоритм искал один интервал около 19:15 и возвращал `actual=None`.

- Observation: **все 8 существующих plan-actual-матчей живой БД созданы до #383-M2** и не несут `intervals` в `planned_snapshot_json` — без read-time recovery секция не появлялась ни у одной тренировки.
  Evidence: `plan_actual_matches.planned_snapshot_json` за 2026-07-13…08-04 — ключа `intervals` нет.

- Observation: на **multi-session дне** `session_id` матча живёт во вложенной сессии `template["sessions"]`, а не на day-level template; date-фолбэк проекцировал бы day-level шаги (не ту сессию). P1 от Codex review.
  Evidence: чекпоинт 76 — 2026-07-27 day-level `ats_06a8…` vs matched `ats_3eaf…` внутри `sessions[]`; reconciliation резолвит именно вложенные (`find_planned_session`).

## Decision Log

- Decision: плановые интервалы берём из `materialized_steps` (проекция), не парсим описание.
  Rationale: данные уже машиночитаемы и персистятся; парсинг текста хрупок.
  Date/Author: 2026-08-07 / Codex.

- Decision: спорт-скоуп первого клина — cycling/бег. Плавание/зал — later (distance-based / sRPE-based матчинг требует другой логики; sRPE/grade уже покрывают их).
  Rationale: там фактическая структура по power/HR наиболее надёжна и materialized_steps наиболее структурированы.
  Date/Author: 2026-08-07 / Codex.

- Decision: матчинг «по репетициям» — сопоставление плановых work-шагов с фактическими интервалами по порядку + длительности. Полный reasoner с grade A–E — follow-up.
  Rationale: наш выбор глубины (issue #383); минимум, закрывающий acceptance.
  Date/Author: 2026-08-07 / Codex.

- Decision: расширение `_planned_snapshot` без миграции БД (JSON-колонка `planned_snapshot_json`).
  Rationale: минимальная инвазивность; checkpoints уже несут materialized_steps.
  Date/Author: 2026-08-07 / Codex.

- Decision: legacy-матчи (без `intervals` в snapshot) восстанавливаются **на чтении** из чекпоинта (`base_checkpoint_id` → `goal_plan_snapshot.session_templates`); точная сессия ищется сначала во вложенных `sessions[]`, затем по дате.
  Rationale: snapshot'ы иммутабельны, а re-run reconciliation не пересоздаёт существующие ревизии. Не восстановимо → `None` (секция скрыта, а не врёт «0 работы»).
  Date/Author: 2026-08-08 / Codex.
- Decision: матчер живёт в `models/plan_vs_fact.py`, а не в `services/plan_vs_fact.py` (как планировалось в ExecPlan).
  Rationale: чистая функция без I/O/БД — консистентно с соседями `models/activity_card.py`, `models/activity_intervals.py`, `models/plan_intervals.py`; сервисный слой не нужен, вызов — из API-роутера.
  Date/Author: 2026-08-08 / Codex.

- Decision: для непрерывного фактического таймлайна сопоставлять все плановые этапы с непрерывными группами фактических участков посредством минимизации суммарного относительного отклонения длительности. Для разреженного факта без надёжных `start_index` оставить прежнее сопоставление рабочих интервалов один-к-одному.
  Rationale: группировка решает Auto Lap без ложного растягивания произвольной тренировки на план; fallback сохраняет обратную совместимость с provider-ответами, содержащими только выделенные усилия.
  Date/Author: 2026-08-13 / Codex.

- Decision: API аддитивно получает `alignment_mode`, `step_matches` и сводку по всем этапам; `matches` и `summary.matched` остаются рабочим подмножеством для обратной совместимости.
  Rationale: web может честно показать разминку/работу/заминку, не ломая существующих потребителей контракта.
  Date/Author: 2026-08-13 / Codex.

- Decision: высота плановой и фактической полос кодирует одну величину — долю пороговой скорости, FTP или LTHR в зависимости от метрики планового этапа. Пульс не используется как универсальная высота и остаётся дополнительной подписью, кроме планов, заданных непосредственно по пульсу.
  Rationale: пульс запаздывает и зависит от внешних условий; сравнение в метрике назначения делает геометрию плана и факта сопоставимой.
  Date/Author: 2026-08-13 / Codex.

- Decision: нижняя полоса показывает те же сгруппированные этапы, что верхняя, а границы исходных кругов сохраняет тонкими внутренними линиями.
  Rationale: одинаковые четыре блока позволяют сравнить этапы напрямую, не теряя объяснения, из каких Auto Lap собран длинный этап.
  Date/Author: 2026-08-13 / Codex.

## Context and Orientation

- Плановая структура: `models/workout_catalog.py` (`materialize_workout` → steps; `_REPEAT_PRESCRIPTIONS`); `models/training_planner.py::_finalize` (`:2099`) — `**catalog` спред в итоговую сессию; `materialized_steps` персистятся в `planning_checkpoints`.
- План-vs-факт матчинг: `models/plan_actual_reconciliation.py::_planned_snapshot` (`:155`) — проекция в `plan_actual_matches.planned_snapshot_json`; `build_reconciliation` (`:207`); `data/database.py::save_plan_actual_match` (`:1843`).
- Фактические интервалы: `services/activity_intervals.py::fetch_activity_intervals` (#390) — детектированные интервалы из Intervals.icu (`icu_intervals`: `{start_index, moving_time, elapsed_time, distance_km, average_watts, average_heartrate, zone, training_load}`). Связь каноническая↔Intervals — `activity_provider_links`.
- Карточка: `api/routers/activities.py::get_activity_card`; web — `web/app/activities/page.tsx` (модалка `ActivityCardModal`, секция «Структура тренировки» из #390).
- Проверка без сети: autouse-фикстура `tests/conftest.py`.

## Plan of Work

### Milestone 1: проекция materialized_steps → плановые intervals (RED→GREEN)

В `models/plan_intervals.py` (новый, чистый):
- `project_planned_intervals(session) -> list[dict]` — проекция `materialized_steps` (и brick `legs[].materialized_steps`) в компактные `{type: work|rest, duration_seconds, target_zone, segment_kind, repeat_index}`. `intensity`/`segment_kind` → `type`; `target.relative_high` → `target_zone`; агрегация репетиций (повторяющихся work-шагов) опциональна на первом шаге.
- Тесты: projection из steps; brick legs; пустые steps; fail-closed на мусоре.

### Milestone 2: planned_intervals в snapshot + карточка API

В `models/plan_actual_reconciliation.py::_planned_snapshot`:
- добавить `intervals: project_planned_intervals(session)`.
В `api/routers/activities.py`:
- при наличии `plan_actual_match` для активности — добавить `planned_intervals` (из snapshot) в карточку.

### Milestone 3: сервис матчинга

В `services/plan_vs_fact.py` (новый):
- `match_plan_vs_fact(planned_intervals, actual_intervals) -> {matches: [...], summary}` — сопоставление work-шагов с фактом по порядку + длительности (`moving_time` ≈ `duration_seconds` ± tolerance); отклонения (длительность/зона). Чистая функция, тестируется изолированно.

### Milestone 4: web

В `web/lib/types.ts` + `web/app/activities/page.tsx`: секция «План vs факт» — плановые шаги ↔ фактические интервалы с подсветкой отклонений, или скрыта при отсутствии плана/интервалов.

## Verification

Новый acceptance-сценарий: план состоит из этапов 5:15 / 19:15 / 5:15 / 5:15, а факт — из непрерывных кругов 5:16 / 7:45 / 7:33 / 3:57 / 5:15 / 5:21. Сравнение должно сопоставить четыре этапа по порядку, объединить три средних круга в длинную работу 19:15 и показать 4 из 4 этапов по длительности и 2 из 2 рабочих этапов. Если provider вернул только отдельные усилия без непрерывных временных смещений, должен сохраниться прежний осторожный режим без ложной оценки разминки и заминки.

В карточке названия этапов и пояснения должны быть по-русски. Плановая относительная цель и фактическая номерная зона показываются раздельно, а не стрелкой как одна шкала.

Высота плановой и фактической полосы должна иметь одну шкалу. Для текущего бега фактический темп переводится в процент пороговой скорости из профиля; ожидаются 70%, 74%, 79% и 66%, все четыре значения внутри соответствующих плановых диапазонов. Цвет факта зелёный для попадания в диапазон, а три исходных участка длинной работы видны внутренними разделителями.

- `python3 -m pytest tests/smoke/test_plan_vs_fact.py -q`
- `python3 -m pytest tests/smoke -q` (без регрессии;特别注意 не сломать `test_workout_catalog*.py`, `test_session_scheduler.py`)
- `python3 -m ruff check` по изменённым файлам
- `npm --prefix web run lint` и `npm --prefix web run build`
- Живая проверка: бег `2026-08-13` (act `23958642824` ↔ `i175371720`) — четыре этапа плана против шести непрерывных фактических участков.

## Outcomes & Retrospective

2026-08-08: клин #383 завершён и смержен (#394 + #395). Плановые интервалы проецируются из `materialized_steps` (M1), несутся в `_planned_snapshot` и карточку API (M2), матчер `match_plan_vs_fact` сопоставляет work-шаги с фактическими интервалами Intervals.icu по порядку + длительности (±30%, greedy-потребление, fail-open) (M3), web-карточка показывает секцию «План vs факт» (M4). Legacy-матчи восстанавливаются на чтении из чекпоинта с резолвом вложенных сессий (P1-фикс). Live-данные: 2026-07-27 → 5 интервалов плана (3 работы), 2026-07-28 → 4 (2 работы); по кэшу факта 07-28 «совпало 1» (22:00 → 16:28, −25%). Smoke 1601 passed, 1 skipped; ruff/ESLint/build зелёные.

2026-08-13: живой сценарий Auto Lap закрыл главный пробел прежнего матчера. Для непрерывной шкалы факт теперь разбивается на соседние группы по длительности всех этапов, а разреженные ответы по-прежнему обрабатываются осторожно. На пробежке `23958642824` результат изменился с ошибочных 1/2 рабочих этапов на 4/4 всех и 2/2 рабочих: длинная аэробная работа 19:15 собрана из трёх участков. Интерфейс получил русские названия, самостоятельные подписи плановой цели и фактической зоны и карточки этапов вместо компактной, но двусмысленной строки. Полный smoke: 1711 passed, 1 skipped; Next lint/build и браузерная приёмка зелёные. Ruff отсутствует в локальном virtualenv; синтаксис Python проверен через compileall.

2026-08-13 (продолжение): плановая и фактическая полосы приведены к одинаковым четырём этапам и единой шкале высоты. Фактическая интенсивность рассчитывается в метрике назначения по сохранённому порогу профиля; для пробежки получены 70%, 74%, 79% и 66%, все внутри целей. Цвет нижней полосы теперь означает качество попадания, Auto Lap остаются видны внутренними разделителями, средний пульс показан как дополнительный контекст. Проверены бег/плавание по темпу, велосипед по мощности, назначение по пульсу и отсутствие порога. Smoke 1718 passed, 1 skipped; Next lint/build, compileall и браузерная приёмка зелёные.
