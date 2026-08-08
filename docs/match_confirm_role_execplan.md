# Подтверждение matched-сопоставлений с ролью — adherence оценивается (#401)

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds. Maintain this document in accordance with `.agent/PLANS.md` from the repository root.

## Purpose / Big Picture

В «План и факт» (/planning) matched-строки (date_sport_heuristic / ai_trainer_external_id) нельзя подтвердить, а даже подтверждённые без роли матчи остаются «не оценено» (кейс 08-04: user_confirmed, actual_role None). Причина: `actual_role` кладётся в `actual_snapshot` при подтверждении, но web всегда шлёт `actual_role: null`, а кнопка подтверждения есть только у ambiguous-строк.

После этого клина: matched-строка получает кнопку «Подтвердить»; при подтверждении роль по умолчанию берётся из плановой сессии (пользователь явно связывает активность с этой сессией — роль установлена подтверждением, а не фабрикацией); adherence оценивается честно (exact/substituted/major_deviation), «не оценено — подтвердите сопоставление» снова становится осмысленным.

## Progress

- [x] (2026-08-08) Разведка. Эндпоинт `POST /api/planning/reconciliation/matches` (MatchCorrectionRequest) уже есть; `record_plan_actual_match` пишет `actual_snapshot.role` из переданного `actual_role`; web (`resolveMatch`) шлёт `actual_role: null` и рендерит кнопки только для ambiguous. Тесты: `test_api_planning.py` (record + adherence).
- [x] (2026-08-08) Milestone 1: backend — дефолт роли к плановой сессии при confirm (`resolved_role = actual_role or session.session_role or template.session_role`).
- [x] (2026-08-08) Milestone 2: web — кнопка «Подтвердить» для matched-строк с unknown-adherence (activity_ids из `actual_activity_ids`, роль = плановая); hint «подтвердите сопоставление» возвращён.
- [x] (2026-08-08) Тесты (новый контракт: confirm без роли → role=planned → exact), smoke 1604 passed, lint/build/ruff зелёные. PR.

## Surprises & Discoveries

- Observation: даже ambiguous-резолв (кнопка «Сопоставить N акт.») шлёт `actual_role: null` — поэтому ВСЕ подтверждённые матчи без роли, и adherence у них «не оценено».
  Evidence: `web/app/planning/page.tsx::resolveMatch` — `actual_role: null`; живой матч 08-04 `user_confirmed` с `actual_snapshot.role=None`.
- Observation: `record_plan_actual_match` уже находит плановую сессию (`find_planned_session` → template/session) — роль для дефолта доступна без новых запросов.
  Evidence: `api/planning_service.py:2350-2360`.

## Decision Log

- Decision: при confirm без явной роли роль по умолчанию = роль плановой сессии (session_role, фолбэк template.session_role).
  Rationale: пользователь явно подтверждает «эта активность — та самая плановая сессия»; роль установлена подтверждением, а не выдумана (в отличие от регрессионного P1 из #399). Нагрузка/спорт считаются по-прежнему честно из факта.
  Date/Author: 2026-08-08 / Codex.

## Context and Orientation

- Эндпоинт: `api/routers/planning.py::planning_record_match` → `api/planning_service.py::record_plan_actual_match` (пишет `plan_actual_matches` ревизией, supersedes предыдущую).
- Adherence: `models/plan_actual_reconciliation.py::_adherence` (role из ledger → exact/substituted/major_deviation; без роли → unknown, кроме out-of-bounds → major_deviation).
- UI: `web/app/planning/page.tsx` — таблица «План и факт», `resolveMatch(row, action)`.

## Plan of Work

### Milestone 1: backend (RED→GREEN)

В `api/planning_service.py::record_plan_actual_match`:
- `resolved_role = actual_role or session.session_role or template.session_role` (только для confirm).
- `actual_snapshot["role"] = resolved_role`.

Тест в `tests/smoke/test_api_planning.py`: confirm эвристического same-sport матча с `actual_role=None` → роль = плановой, adherence = substituted (тот же сценарий, что существующий тест с явной ролью).

### Milestone 2: web

В `web/app/planning/page.tsx`:
- `resolveMatch`: для confirm `activity_ids = row.actual_activity_ids ?? row.candidate_activities`; `actual_role = row.role ?? null`.
- Кнопка «Подтвердить» для `match_status === "matched" && adherence === "unknown"` (и legacy user_confirmed без роли — повторное подтверждение добавляет роль).
- Вернуть hint «— подтвердите сопоставление» для того же условия.

## Verification

- `python3 -m pytest tests/smoke/test_api_planning.py tests/smoke/test_api_planning_router_contract.py -q`
- `python3 -m pytest tests/smoke -q` (базелайн 1603 passed, 1 skipped)
- `npm --prefix web run lint` / `npm --prefix web run build`
- `ruff check` по изменённым файлам

## Outcomes & Retrospective

2026-08-08: клин #401 реализован. Подтверждение matched-строки теперь устанавливает роль факта (по умолчанию — роль плановой сессии, потому что подтверждение = явное «эта активность — та самая сессия»), и adherence оценивается честно (exact/substituted/major_deviation), а не «не оценено». Legacy user_confirmed-матчи без роли (кейс 08-04) можно переподтвердить — кнопка появляется у всех matched-строк с unknown-adherence. Smoke 1604 passed, 1 skipped; ruff/ESLint/build зелёные.
