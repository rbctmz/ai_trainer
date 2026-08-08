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
- [x] (2026-08-08) Полный smoke — 1596 passed, 1 skipped; ruff/ESLint/build зелёные. Мердж PR (решает #383).

## Surprises & Discoveries

- Observation: **структурированные плановые интервалы уже существуют** как `materialized_steps`. НЕ нужно парсить `_build_session_description` (он генерирует только метаданные: Фаза/Роль/TSS — не «3×12'/4'»).
  Evidence: `models/workout_catalog.py:907-925` — каждый шаг несёт `{intensity: work|easy|steady, duration_seconds, tss, target:{type,low,high,relative_low,relative_high}, segment_kind: warmup|work|recovery|cooldown|stage, repeat_index}`. Это почти то, что нужно для матчинга — проекция, а не генерация.

- Observation: `_REPEAT_PRESCRIPTIONS` (`workout_catalog.py:365-472`) — таблицы «3×8'/4'» по стимулам (threshold/vo2/tempo). `_RepeatTier` (`:53-59`) = `{repeat_count, work_seconds, recovery_seconds}`. Пример `bike_threshold` (`:379`): short=3×5'/3', medium=3×8'/4', long=4×8'/4'. Это уже машиночитаемые репетиции.

- Observation: плановые шаги **уже персистятся** в БД. `planning_checkpoints.checkpoint_data → goal_plan_snapshot.session_templates[].materialized_steps`. Подтверждено живым запросом (5 steps, sample: `{intensity:"easy", duration_seconds:405, target:{type:"power", low:72, high:100, relative_low:0.42, ...}}`).

- Observation: `plan_actual_matches.planned_snapshot_json` — **минимальная** проекция (`{index, session_id, date, sport, role, phase, name, tss, duration_minutes, parts}`), БЕЗ интервалов. JSON-колонка → расширение без миграции БД (`data/database.py:516`).
  Evidence: `models/plan_actual_reconciliation.py:149-166`.

- Observation: есть **реальные bike plan-actual-матчи** с intervals-линками для матчинга. `2026-07-28` act `23765394202` ↔ Intervals `i170127087`; `2026-07-27` act `23751063360` ↔ `i169725694`. Факт доступен через `get_activity_intervals` (#390).

- Observation: матчинг «по репетициям» должен сопоставлять **по порядку + длительности**, не по таймстемпам. Плановый шаг «12' work @90%» → фактический интервал с `moving_time ≈ 720s` и высокой intensity. Разминка/заминка (`segment_kind`) участвуют, но главный фокус — work-репетиции.

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
- Decision: матчер живёт в `models/plan_vs_fact.py`, а не в `services/plan_vs_fact.py` (как планировалось в ExecPlan).
  Rationale: чистая функция без I/O/БД — консистентно с соседями `models/activity_card.py`, `models/activity_intervals.py`, `models/plan_intervals.py`; сервисный слой не нужен, вызов — из API-роутера.
  Date/Author: 2026-08-08 / Codex.

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

- `python3 -m pytest tests/smoke/test_plan_vs_fact.py -q`
- `python3 -m pytest tests/smoke -q` (без регрессии;特别注意 не сломать `test_workout_catalog*.py`, `test_session_scheduler.py`)
- `python3 -m ruff check` по изменённым файлам
- `npm --prefix web run lint` и `npm --prefix web run build`
- Живая проверка: bike-матч `2026-07-28` (act `23765394202` ↔ `i170127087`) — плановые steps vs фактические интервалы.

## Outcomes & Retrospective

2026-08-08: клин #383 завершён. Плановые интервалы проецируются из `materialized_steps` (Milestone 1), несутся в `_planned_snapshot` и карточку API (Milestone 2), матчер `match_plan_vs_fact` сопоставляет work-шаги с фактическими интервалами Intervals.icu по порядку + длительности (±30%, greedy-потребление, fail-open) (Milestone 3), web-карточка показывает секцию «План vs факт» (Milestone 4). Live-проверка на bike-матчах (2026-07-27/28) доступна после мерджа. Smoke 1596 passed, 1 skipped; ruff/ESLint/build зелёные.
