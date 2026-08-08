# Отмена/переназначение подтверждённого сопоставления (#405)

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds. Maintain this document in accordance with `.agent/PLANS.md` from the repository root.

## Purpose / Big Picture

Подтверждённый матч (user_confirmed) нельзя отменить или переназначить из UI — кнопки есть только у ambiguous/matched-строк с unknown-adherence. Живой кейс 2026-08-04: заплыв 33.6 TSS подтверждён против плановой bike-сессии (кросс-спорт), а swim-сессия осталась без факта.

После этого клина: у user_confirmed-строк есть «Отменить сопоставление» — создаётся ревизия `user_unmatched` (supersedes), активность освобождается и снова становится кандидатом/несопоставленной; далее её можно подтвердить правильной сессии (роль — как в #401).

## Progress

- [x] (2026-08-08) Разведка: `record_plan_actual_match` поддерживает confirm/reject; reject уже пишет unmatched-ревизию, но без понятной семантики «отменить подтверждение» и без UI-входа на user_confirmed-строках. Кейс 08-04.
- [x] (2026-08-08) Milestone 1: backend — action `unmatch` (user_unmatched, supersedes) + `user_unmatched` в признаваемых ledger-методах `build_reconciliation` (иначе эвристика снова матчила бы активность).
- [x] (2026-08-08) Milestone 2: web — кнопка «Отменить сопоставление» у user_confirmed-строк; метка `user_unmatched`.
- [x] (2026-08-08) Тесты (unmatch → user_unmatched + активность свободна), smoke 1606 passed, lint/build/ruff зелёные. PR.

## Surprises & Discoveries

- Observation: `build_reconciliation` признаёт только `{user_confirmed, user_rejected, admin_resolve}` — без добавления `user_unmatched` эвристика после отмены снова матчила бы активность (matched вместо unmatched).
  Evidence: RED-прогон `test_unmatch_creates_user_unmatched_and_frees_activity` → `row["match_status"] == "matched"`; фикс — добавить метод в признаваемый набор.
- Observation (review P2): признание `user_unmatched` как ledger-метода гасит эвристику и кандидатов — сессия «запирается» в «отменено пользователем», даже если есть другие активности дня.
  Evidence: после unmatch `candidate_activities` пуст; фикс — для `user_unmatched` наполнять кандидатов из day_activities (без авто-матчинга).

## Decision Log

- Decision: «Отменить» — отдельный action `unmatch` (не переиспользуем `reject`): reject семантически «это не кандидат на сессию», unmatch — «снять ранее подтверждённое соответствие». Оба пишут unmatched-ревизию.
  Rationale: понятные evidence/match_method для истории (`user_unmatched` + «Пользователь отменил сопоставление»).
  Date/Author: 2026-08-08 / Codex.
- Decision: переназначение = отмена + подтверждение целевой сессии (два шага), без атомарного «move».
  Rationale: переиспользуем существующий confirm-флоу с ролью (#401); атомарный move добавляет конфликт-логику без пользы для кейса.
  Date/Author: 2026-08-08 / Codex.
- Decision (review P1): при unmatch фидбек, привязанный к отменяемой ревизии матча, томбстонится.
  Rationale: иначе `session_quality_evaluations` продолжают считаться по отменённому сопоставлению и загрязняют эксперименты.
  Date/Author: 2026-08-08 / Codex.

## Context and Orientation

- `api/planning_service.py::record_plan_actual_match` — единая точка записи ревизий (confirm/reject/unmatch), `supersedes_match_id` из последней ревизии той же сессии.
- `web/app/planning/page.tsx` — таблица «План и факт», `resolveMatch(row, action)`.
- Конфликт-проверка при confirm: активность, уже `matched` другой сессии, блокируется — поэтому перед переназначением нужна отмена.

## Plan of Work

### Milestone 1: backend (RED→GREEN)

`record_plan_actual_match`: разрешённые action `{confirm, reject, unmatch}`; для `unmatch` — activity_ids игнорируются, match_status `unmatched`, match_method `user_unmatched`, evidence «Пользователь отменил сопоставление».

Тесты: unmatch создаёт ревизию user_unmatched (supersedes), активность освобождается (reconciliation: сессия unmatched, активность снова кандидат); после unmatch confirm другой сессии проходит (без «already matched»).

### Milestone 2: web

- `resolveMatch` action `"unmatch"` (activity_ids [], actual_role null).
- Кнопка «Отменить сопоставление» у user_confirmed-строк.
- `matchMethodLabels[user_unmatched] = "отменено пользователем"`.

## Verification

- `python3 -m pytest tests/smoke/test_api_planning.py tests/smoke/test_api_planning_router_contract.py -q`
- `python3 -m pytest tests/smoke -q` (базелайн 1605 passed, 1 skipped)
- `npm --prefix web run lint` / `npm --prefix web run build`
- `ruff check` по изменённым файлам

## Outcomes & Retrospective

2026-08-08: клин #405 реализован (с review-фиксами). У user_confirmed-строк кнопка «Отменить сопоставление» → ревизия `user_unmatched`; сессия «Нет факта», кандидаты остаются видимыми (P2); фидбек от отменённого матча томбстонится (P1); legacy user_confirmed без роли получают контроль роли (P1 #406). Smoke 1607 passed, 1 skipped; ruff/ESLint/build зелёные.
