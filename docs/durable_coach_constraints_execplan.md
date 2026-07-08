# Durable Coach Constraints Ledger

This ExecPlan is a living document. It follows `.agent/PLANS.md` and must keep `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` current as the work proceeds.

## Purpose / Big Picture

AI Trainer can already propose plan adjustments, but it does not have one durable place to remember that a user is sick, unavailable, taking a forced rest day, or manually removed a planned session. Without that ledger, later sync or replanning work can accidentally recreate a workout that the athlete explicitly removed. After this change, backend clients can persist those constraints, list active constraints for a date window, deactivate them, and apply them to a goal plan in a predictable way.

The visible proof is API-level: `/api/planning/status` includes `active_constraints` and `active_constraint_count`, and new planning constraint endpoints can create, list, and deactivate constraint rows. Contributor-safe smoke tests prove persistence and plan protection without Garmin credentials.

## Progress

- [x] (2026-07-08 22:00+03:00) Created GitHub issue #114 and branch `codex/issue-114-durable-coach-constraints`.
- [x] (2026-07-08 22:07+03:00) Audited current planning checkpoints, coach proposals, decisions API, and execution feedback helpers.
- [x] (2026-07-08 22:12+03:00) Added failing smoke tests for DB ledger persistence, planning status exposure, API lifecycle, and plan-day protection helper. First run failed on missing `save_coach_constraint`, `ConstraintRequest`, and `models.coach_constraints`.
- [x] (2026-07-08 22:18+03:00) Implemented SQLite table and Database lifecycle methods for `coach_constraints`.
- [x] (2026-07-08 22:22+03:00) Implemented `models/coach_constraints.py` helper that protects matching goal-plan days without mutating the input plan.
- [x] (2026-07-08 22:27+03:00) Wired planning API create/list/deactivate endpoints and planning status `active_constraints` summary.
- [x] (2026-07-08 22:33+03:00) Added TypeScript contract types in `web/lib/types.ts`.
- [x] (2026-07-08 22:37+03:00) Validation passed: `test_coach_constraints.py` 5 passed, focused planning/decisions smoke 22 passed, `web` build passed, full smoke `377 passed, 1 skipped`.
- [ ] Publish PR that closes #114.

## Surprises & Discoveries

- Observation: The repository already has execution outcomes like `unavailable`, but those are transient reconciliation facts, not durable future constraints.
  Evidence: `models/planning_execution.py` summarizes row outcomes into an adjustment preview, while `data/database.py` has no table for active user or coach constraints.

- Observation: The local environment still skips the socket preflight smoke test.
  Evidence: `python3 -m pytest tests/smoke -q` reported `SKIPPED [1] tests/smoke/test_run_web_preflight.py:52: environment does not allow opening a local listening socket`, with all other smoke tests passing.

## Decision Log

- Decision: Keep this slice backend-first and additive.
  Rationale: The current risk is lack of durable contract. A small table plus API lifecycle and helper gives future planner/UI work a stable foundation without redesigning the planner in this issue.
  Date/Author: 2026-07-08 / Codex.

- Decision: Do not automatically inject constraints into every replan/build path in this first PR.
  Rationale: Existing plan rebuild logic has multiple paths. Wiring all of them would expand scope and regression risk. This issue provides the ledger and a tested application helper; the next slice can use that helper inside specific mutation paths.
  Date/Author: 2026-07-08 / Codex.

- Decision: Expose constraint lifecycle under `/api/planning/constraints`.
  Rationale: Constraints are planning facts, even when created by coach or user interactions. Keeping them under planning keeps the API discoverable and avoids coupling them to the decisions audit page.
  Date/Author: 2026-07-08 / Codex.

## Outcomes & Retrospective

Implemented. The backend now has durable coach constraints stored in SQLite, planning API endpoints to create/list/deactivate them, planning status metadata for active constraints, and a tested helper that can apply active constraints to exact goal-plan dates by turning them into protected zero-load days. The implementation is intentionally additive; automatic use inside all future replan/build mutation paths remains a follow-up.

## Context and Orientation

The active product surface is FastAPI under `api/` and Next.js under `web/`. Planning orchestration lives in `api/planning_service.py`, durable local persistence lives in `data/database.py`, and plan mutation helpers live under `models/`. Existing coach proposals are stored in `coach_proposals`, and planning checkpoints are stored in `planning_checkpoints`.

A constraint in this plan means a durable row saying that a specific date should be protected from normal plan generation or replanning. Supported kinds are `sick`, `unavailable`, `forced_rest`, `manual_delete`, and `disabled_plan_day`. Active constraints should be listed and applied; inactive constraints remain audit history.

## Plan of Work

First, add smoke tests under `tests/smoke/test_coach_constraints.py`. The tests should cover saving constraints, listing active constraints inside a date window, deactivating one row, exposing active constraints from planning status, creating and deactivating constraints through the planning router, and applying constraints to a simple goal plan.

Next, extend `data/database.py` with a `coach_constraints` table and methods `save_coach_constraint`, `get_coach_constraints`, `get_coach_constraint`, `deactivate_coach_constraint`, and `_deserialize_coach_constraint_row`. Keep rows append-friendly and JSON-safe. The table should not delete historical rows when a constraint is deactivated.

Then add `models/coach_constraints.py` with `apply_constraints_to_goal_plan(goal_plan, constraints)`. It should copy a goal plan, find matching dates in `daily_plan`, set those day totals and sport parts to zero, and mark corresponding `session_templates` as protected/off with a constraint note. It should return the updated plan and an application summary.

Finally, wire API endpoints in `api/routers/planning.py` and status metadata in `api/planning_service.current_status()`. Add TypeScript types only if web contract files need them.

## Concrete Steps

Run focused tests from the repository root:

    python3 -m pytest tests/smoke/test_coach_constraints.py -q

Run nearby planning and decisions smoke:

    python3 -m pytest tests/smoke/test_coach_constraints.py tests/smoke/test_api_planning.py tests/smoke/test_coach_decisions.py -q

Run full smoke before PR:

    python3 -m pytest tests/smoke -q

## Validation and Acceptance

The work is accepted when a temporary database can persist a sick or unavailable day, `/api/planning/status` reports it as active, API calls can create and deactivate it, and applying the constraint to a goal plan marks only matching dates as zero-load protected days. Existing planning and decisions tests must still pass.

## Idempotence and Recovery

Creating multiple constraints for the same date is allowed because different sources can record different facts. Deactivation changes only the selected row status and resolved timestamp. Tests use temporary SQLite databases, so they are safe to rerun.

## Artifacts and Notes

The GitHub issue for this work is #114: `Backend: durable coach constraints ledger for replanning`.

## Interfaces and Dependencies

In `data/database.py`, add methods:

    save_coach_constraint(...)
    get_coach_constraints(...)
    get_coach_constraint(...)
    deactivate_coach_constraint(...)

In `models/coach_constraints.py`, add:

    apply_constraints_to_goal_plan(goal_plan, constraints) -> tuple[dict[str, Any], dict[str, Any]]

Revision note (2026-07-08): initial plan created for issue #114 as the next backend contract after the readiness snapshot contract merged in PR #113.
