# Active planning overview and information architecture

This ExecPlan is a living document. It is maintained under `.agent/PLANS.md`.

## Purpose / Big Picture

When an athlete already has a saved training plan, opening `/planning` should first explain that plan rather than open a new-plan form. The athlete can see the confirmed goal, the current phase and week, and a bounded execution status; editing, adjustment, and export remain deliberate actions. An athlete with no plan still begins with the existing first-plan onboarding and form.

## Progress

- [x] (2026-08-02) Inspected issue #301, the existing `/api/planning/status` and `/api/planning/plan` contracts, checkpoint projection, reader page, and relevant ASR risks.
- [x] (2026-08-02) Added failing API and source-level UI acceptance gates for the active-plan overview, then made them green.
- [x] (2026-08-02) Implemented M1: a read-only overview projection and reader-first `/planning` information architecture.
- [x] (2026-08-02) Reviewing agent completed focused API/UI gates, lint, production build, full smoke, and isolated active/no-plan browser acceptance at 1280px and 390px.
- [ ] M2 (future): deepen the Weeks reader view without changing the M1 overview contract.
- [ ] M3 (future): improve the Execution reader view and adjustment guidance without altering checkpoint semantics.
- [ ] M4 (future): complete parent #300 roadmap/visualisation work only after separate scope approval.

## Surprises & Discoveries

- Observation: `/api/planning/status` intentionally contains only a compact checkpoint summary, while `/api/planning/plan` is an export-oriented daily prescription payload. Neither can truthfully supply event vs rolling-horizon hero data without browser-side reconstruction.
  Evidence: `api/planning_service.py:206` and `api/routers/planning.py:151`.
- Observation: the existing adjustment history is already rendered once, but it is always expanded and its English heading is inconsistent with the Russian product surface.
  Evidence: `web/app/planning/page.tsx:760`.
- Observation: the browser runtime did not trigger the native `<summary>` action through synthetic Enter/Space presses.
  Evidence: replacing it with a button-backed disclosure and an explicit keyboard handler made Enter open and Space close deterministically while preserving `aria-expanded` and `aria-controls`.

## Decision Log

- Decision: add `GET /api/planning/overview` rather than extending the export payload or deriving dates/phases in TypeScript.
  Rationale: the endpoint is an additive, read-only projection of the persisted checkpoint. It keeps calendar and plan-state interpretation in Python, protects API compatibility, and lets every unavailable detail remain a local data-gap field.
  Date/Author: 2026-08-02 / Codex.
- Decision: use a button-backed disclosure for Adjustment History.
  Rationale: it is collapsed by default, exposes `aria-expanded`/`aria-controls`, and its keyboard activation is verifiable in the supported browser acceptance runtime.
  Date/Author: 2026-08-02 / Codex.

## Outcomes & Retrospective

M1 adds `GET /api/planning/overview`, a checkpoint-only projection that distinguishes confirmed event goals from training-goal rolling horizons and reports local data gaps. `/planning` now resolves to Overview only when `has_plan=true`; no-plan still resolves to BuildMode and its FirstPlanCard. Overview, Weeks, and Execution are reader tabs. Edit plan, Adjust, and Export retain existing flows as explicit actions. Adjustment History is one collapsed, button-backed disclosure.

Final evidence: 24 focused API/router/deep-link tests passed; the full contributor-safe smoke suite passed with `1360 passed, 1 skipped`; Next lint and production build passed from an isolated web copy. Browser acceptance against isolated copies of the active and empty databases verified the event overview as the 1280px default with no build form, the Weeks and Execution readers, explicit Edit, the `session_id` adjustment deep-link, no horizontal overflow at 390px, no-plan onboarding, and deterministic Enter/Space history disclosure. No provider write or planning confirmation was made.

## Context and Orientation

`api/planning_service.py` orchestrates existing planning models and restores the latest append-only checkpoint. `api/routers/planning.py` exposes its stable FastAPI contracts. The current `web/app/planning/page.tsx` is a client-side page containing the planning form, execution adjustment, export, and history; it currently defaults to the form regardless of `has_plan`.

An active plan is the latest persisted planning checkpoint. A reader view only fetches and displays data. A mutating action can eventually write a checkpoint or a provider delivery and must therefore remain an explicit button. The M1 overview must never call a provider or a mutation while it renders.

The affected quality scenarios are ASR-REL-2 (missing data is a local gap, not a page failure), ASR-MOD-2 (a reusable reader projection), ASR-MOD-3 (an additive API contract), plus ATAM R3/R4 (contract tests and web-primary scope). No Streamlit code, planning formula, identity/lineage, reconciliation calculation, delivery behavior, or checkpoint storage schema changes are in scope.

## Plan of Work

First add tests that prove the new endpoint returns an empty envelope for no checkpoint, an event-goal overview with a confirmed A event and countdown, and a training-goal overview with a rolling horizon and no invented race date. The tests also pin the route registration and the reader-first source structure that preserves the existing `session_id` adjustment deep link.

Add `active_plan_overview` to `api/planning_service.py`. It will restore the existing checkpoint snapshot and produce only display-ready, bounded values: goal, event or rolling timeline, current week, plan progress, and persisted execution status. Date parsing is defensive. Fields that cannot be derived are `null` or explicit `data_gap` values instead of exceptions. Expose it at `GET /api/planning/overview`.

Extend `web/lib/types.ts` with the additive DTO and rework only the top-level page state. When status reports a plan, the first resolved view is Overview. The reader navigation contains Overview, Weeks, and Execution. Explicit actions open the retained form, adjustment flow, or export flow. The no-plan path keeps BuildMode and therefore the existing FirstPlanCard onboarding. Render one collapsed button-backed Adjustment History outside the selected reader/action content.

## Concrete Steps

From `/Users/gregkisel/Developer/ai_trainer`, run:

    python -m pytest tests/smoke/test_planning_active_plan_overview.py -q
    python -m pytest tests/smoke/test_api_planning_router_contract.py -q
    python -m pytest tests/smoke/test_feedback_planning_handoff.py -q
    python -m pytest tests/smoke -q
    npm --prefix web run lint
    npm --prefix web run build

For browser acceptance, start the local stack with `./run_web.sh` and use an isolated temporary database or the app's safe/demo state. Verify desktop width 1280 and mobile width 390. Do not click confirmation, adjustment confirmation, or Intervals delivery.

## Validation and Acceptance

The focused API tests must show that no plan produces `{has_plan: false}`, an event plan has a confirmed A-goal with the persisted date and non-negative time remaining, and a training plan returns `timeline.kind == "rolling"` without an event date/countdown. The UI source gate and browser check must show the form only after Edit plan, keep the first-plan card as the no-plan default, retain `session_id` focusing in adjustment, and show the history collapsed.

## Idempotence and Recovery

All M1 reads are derived from already persisted checkpoints and make no writes. Re-running tests is safe. If a browser fixture has no active plan, use the existing preview/confirm flow only in a temporary local database; do not use a provider-backed account. Reverting this work only removes an additive endpoint and web reader shell, leaving checkpoints intact.

## Artifacts and Notes

The primary implementation files are `api/planning_service.py`, `api/routers/planning.py`, `web/lib/types.ts`, and `web/app/planning/page.tsx`. The focused acceptance test will be `tests/smoke/test_planning_active_plan_overview.py`.

## Interfaces and Dependencies

`GET /api/planning/overview` returns a JSON object with `has_plan`. When true it also returns `goal`, `timeline`, `current_week`, `progress`, and `execution`. `timeline.kind` is either `event` (with confirmed A-event data and remaining time) or `rolling` (with only the saved horizon); missing values use `null` and `execution.state == "data_gap"` when no persisted execution projection exists. It depends only on `Database.get_latest_planning_checkpoint`, `restore_goal_plan_from_checkpoint`, and existing checkpoint summary functions.

Plan revision 2026-08-02: M1 implementation and independent acceptance are complete; M2-M4 remain separate future scope.
