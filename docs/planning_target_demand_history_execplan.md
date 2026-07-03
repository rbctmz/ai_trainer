# Planning Target, Demand, and Adjustment History ExecPlan

This ExecPlan is a living document for GitHub issue #23:
`feat(planning): weekly target math + demand setting + adjustment history`.
It follows `.agent/PLANS.md` and `docs/AI_Feature_Development_Workflow.md`.

## Purpose

Make the web planning surface explain how weekly TSS is chosen, let the athlete
choose a demand level that affects the next generated plan, and show recent
planning adjustments from persisted checkpoints.

The current planner already generates weekly TSS from goal ranges, recent load,
availability, and constraints, but the API exposes only a single weekly target
number. Adjustment checkpoints are persisted, but the Plan page has no history
endpoint and the adjustment provenance uses a source name that is not summarized
by the existing execution-feedback helper.

## Progress

- [x] Read issue #23 and repository workflow docs.
- [x] Created branch `codex/issue-23-planning-targets`.
- [x] Audited current planning service, routes, checkpoint helpers, and web Plan page.
- [x] Add contract-first smoke tests for target math, demand persistence, and history.
- [x] Implement shared target breakdown and demand helpers.
- [x] Wire backend routes and planning service.
- [x] Add minimal web Plan page rendering for Weekly Target, Demand, and History.
- [x] Run targeted smoke tests, contributor-safe smoke contour, and web build.
- [ ] Commit, push, and open PR with `Closes #23`.

## Surprises & Discoveries

- Issue #23 references `models/planning.py` and `web/app/plan/page.tsx`, but the
  active migration path is `api/planning_service.py`,
  `models/training_planner.py`, and `web/app/planning/page.tsx`.
- The database already has `user_settings`, so the demand setting can be saved
  without a schema migration.
- Adjustment checkpoints currently use `source="execution_adjustment"` while
  `summarize_execution_feedback_transition` accepts `execution_feedback` and
  `legacy_checkpoint`. History must either normalize this source or support both.
- The existing `suggest_target_weekly_tss` uses recent average/best/load caps,
  but issue #23 explicitly asks for recent-load median in the displayed math.

## Decision Log

- Demand levels are a small fixed contract: `easy`, `moderate`, `demanding`,
  `aggressive`. Multipliers are 0.90, 1.00, 1.10, and 1.20.
- The Weekly Target section exposes four rows: goal need, availability cap,
  recent load median, and resulting base weekly TSS. Demand is shown separately
  and also included in the API payload.
- The final build target is the base weekly TSS after demand multiplier, capped
  by availability. Availability remains a hard cap because the user supplied it.
- Adjustment History reuses `planning_checkpoints`; no new table is needed for
  issue #23.

## Acceptance Criteria

Given the Plan page loads,
when planning data is available or empty,
then a Weekly Target section shows goal need, availability cap, recent load, and
base weekly TSS from the API contract.

Given the user changes Demand,
when the next plan is generated,
then the demand multiplier changes the generated target and the selected level is
saved in user settings.

Given at least one adjustment checkpoint exists,
when `/api/planning/history` is requested,
then it lists the adjustment date, type, and outcome note.

Given the branch is ready,
when verification runs,
then contributor-safe smoke tests and the web build pass.

## Implementation Plan

1. Add `models/planning_targets.py`:
   - fixed demand profiles and normalization
   - recent weekly TSS median summary
   - target breakdown using goal range, availability cap, recent median, and demand
2. Update `api/planning_service.py`:
   - persist/read demand setting via `user_settings`
   - expose target preview and history helpers
   - include target breakdown and demand in `build_plan`
3. Update `api/routers/planning.py`:
   - extend `BuildRequest` with `demand`
   - add `/api/planning/target-preview`, `/api/planning/demand`, and `/api/planning/history`
4. Update checkpoint summarization:
   - support `execution_adjustment` as execution feedback history
5. Update `web/lib/types.ts` and `web/app/planning/page.tsx`:
   - demand selector
   - target math rows
   - adjustment history list

## Verification

Run results:

```bash
python3 -m pytest tests/smoke/test_planning_target_demand_history.py -q
# 4 passed

python3 -m pytest tests/smoke/test_planning_target_demand_history.py tests/smoke/test_api_planning.py tests/smoke/test_planning_checkpoint_history.py -q
# 17 passed

python3 -m pytest tests/smoke -q
# 305 passed

npm run build --prefix web
# Next.js build completed successfully; existing ESLint option warning still prints.

git diff --check
# clean
```

## Outcomes & Retrospective

Implemented a minimal backend-first contract:

- `/api/planning/target-preview` exposes the target math rows.
- `/api/planning/demand` exposes and saves the current demand profile.
- `/api/planning/history` lists persisted checkpoint history.
- `POST /api/planning/build` accepts `demand` and stores the selected level.
- Plan page renders the demand selector, target rows, and history without
  duplicating planning math in TypeScript.

Residual risk: the target formula is now explicit and test-covered, but it is
still a product heuristic. Future calibration should compare generated targets
against validated training outcomes, not only against UI acceptance criteria.
