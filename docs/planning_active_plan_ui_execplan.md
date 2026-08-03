# Active planning overview and information architecture

This ExecPlan is a living document. It is maintained under `.agent/PLANS.md`.

## Purpose / Big Picture

When an athlete already has a saved training plan, opening `/planning` should first explain that plan rather than open a new-plan form. The athlete can see the confirmed goal, the current phase and week, and a bounded execution status; editing, adjustment, and export remain deliberate actions. An athlete with no plan still begins with the existing first-plan onboarding and form.

## Progress

- [x] (2026-08-02) Inspected issue #301, the existing `/api/planning/status` and `/api/planning/plan` contracts, checkpoint projection, reader page, and relevant ASR risks.
- [x] (2026-08-02) Added failing API and source-level UI acceptance gates for the active-plan overview, then made them green.
- [x] (2026-08-02) Implemented M1: a read-only overview projection and reader-first `/planning` information architecture.
- [x] (2026-08-02) Reviewing agent completed focused API/UI gates, lint, production build, full smoke, and isolated active/no-plan browser acceptance at 1280px and 390px.
- [x] (2026-08-02) M2 scope and current checkpoint/forecast contracts inspected for #302.
- [x] (2026-08-02) Added RED contract/component gates for server-owned roadmap and form projection, then made them green.
- [x] (2026-08-02) Implemented M2: additive active-checkpoint `roadmap` and `form_projection` fields plus Overview rendering.
- [x] (2026-08-02) Passed focused event/rolling/data-gap API gates, the full contributor-safe smoke suite, Next lint, production build, diff whitespace validation, and independent browser review at 1280px and 390px.
- [x] (2026-08-02) Inspected #303, canonical PlanWeek/export/adherence/reconciliation contracts, and #299/#267/#268 dependences before M3 implementation.
- [x] (2026-08-02) Added RED contract/component gates for one bounded week-by-week reader projection, then made them green.
- [x] (2026-08-02) Implemented M3 composite DTO and responsive week/day/leaf-session reader without changing matching or delivery semantics.
- [x] (2026-08-03) Validated no-plan, past/current/future, unplanned, ambiguous, rest, event, and composite-session states through focused contracts and independent browser acceptance at 1280px and 390px.
- [x] (2026-08-03) Addressed PR review: the provider-disabled reader now receives all 16 displayed fact weeks, while provider-backed reconciliation remains capped at 12; roadmap extension accepts only the existing seven-day post-plan event bridge.
- [ ] M4 (future): complete parent #300 roadmap/visualisation work only after separate scope approval.

## Surprises & Discoveries

- Observation: `/api/planning/status` intentionally contains only a compact checkpoint summary, while `/api/planning/plan` is an export-oriented daily prescription payload. Neither can truthfully supply event vs rolling-horizon hero data without browser-side reconstruction.
  Evidence: `api/planning_service.py:206` and `api/routers/planning.py:151`.
- Observation: the existing adjustment history is already rendered once, but it is always expanded and its English heading is inconsistent with the Russian product surface.
  Evidence: `web/app/planning/page.tsx:760`.
- Observation: the browser runtime did not trigger the native `<summary>` action through synthetic Enter/Space presses.
  Evidence: replacing it with a button-backed disclosure and an explicit keyboard handler made Enter open and Space close deterministically while preserving `aria-expanded` and `aria-controls`.
- Observation: the established forecast helper consumes persisted daily-plan triples, including the metadata field, rather than date/load pairs.
  Evidence: M2 projection passes only future persisted triples to `_forecast`, preserving the planner's existing input contract and race-load handling.
- Observation: browser automation was unavailable to the implementing agent but available during independent review.
  Evidence: the reviewer exercised `/planning` against an isolated database at 1280px and 390px, confirmed the roadmap and form chart, found no horizontal overflow or console errors, and made no provider writes.
- Observation: `plan_days` is the existing public/export projection that preserves session IDs, materialized steps, composite legs, and per-leaf exportability; it deliberately excludes rest days.
  Evidence: `api/planning_service.py::plan_days` skips zero-TSS rows while `daily_plan` retains every calendar day.
- Observation: browser automation was unavailable to the implementing agent but available during independent M3 review.
  Evidence: the reviewer exercised the isolated `/planning` Weeks reader at 1280px and 390px, confirmed one initially open current week, visible in-chart event markers and phase encoding, no body overflow or console errors, and no disclosure-triggered API read.
- Observation: a plan can end on Sunday while a saved A/B/C start falls on the next Monday; treating only daily-plan dates as the reader horizon drops that legitimate marker and its forecast target.
  Evidence: M3 regression run on 2026-08-03 exercised this calendar boundary; roadmap and form-projection tests passed after adding a bounded zero-load bridge to the already saved target date.

## Decision Log

- Decision: add `GET /api/planning/overview` rather than extending the export payload or deriving dates/phases in TypeScript.
  Rationale: the endpoint is an additive, read-only projection of the persisted checkpoint. It keeps calendar and plan-state interpretation in Python, protects API compatibility, and lets every unavailable detail remain a local data-gap field.
  Date/Author: 2026-08-02 / Codex.
- Decision: use a button-backed disclosure for Adjustment History.
  Rationale: it is collapsed by default, exposes `aria-expanded`/`aria-controls`, and its keyboard activation is verifiable in the supported browser acceptance runtime.
  Date/Author: 2026-08-02 / Codex.
- Decision: extend the existing read-only `/api/planning/overview` projection for M2 instead of changing `/api/planning/plan`.
  Rationale: `/plan` remains export-oriented. The overview is already the active-checkpoint reader boundary and can add roadmap and form fields without breaking existing consumers or reconstructing domain values in TypeScript.
  Date/Author: 2026-08-02 / Codex.
- Decision: create an additive `/api/planning/week-by-week` M3 reader endpoint rather than joining export and reconciliation payloads in the browser.
  Rationale: the endpoint can reuse canonical plan days and the existing read-only reconciliation snapshot while preserving session identity, today-pending semantics, boundedness, and one request on disclosure. It changes neither reconciliation matching nor checkpoints.
  Date/Author: 2026-08-02 / Codex.
- Decision: cap the M3 reader and its one canonical reconciliation read to 16 weeks around the current/future boundary.
  Rationale: this bounds one response and preserves current-week context, while a longer saved horizon remains explicitly reported in `window.total_weeks` rather than silently treated as absent.
  Date/Author: 2026-08-02 / Codex.
- Decision: use the same 16-week bound for the provider-disabled reconciliation read as for displayed weeks, retain the existing 12-week provider-I/O cap, retain original week ordinals, and scale the chart by the maximum of target and actual TSS.
  Rationale: a shorter local fact window would manufacture missed load for displayed past weeks; external I/O must not expand incidentally; display indices must remain traceable to the saved plan; and an actual above target must never be visually clipped. The change remains a read-only presentation projection.
  Date/Author: 2026-08-03 / Codex.

## Outcomes & Retrospective

M1 adds `GET /api/planning/overview`, a checkpoint-only projection that distinguishes confirmed event goals from training-goal rolling horizons and reports local data gaps. `/planning` now resolves to Overview only when `has_plan=true`; no-plan still resolves to BuildMode and its FirstPlanCard. Overview, Weeks, and Execution are reader tabs. Edit plan, Adjust, and Export retain existing flows as explicit actions. Adjustment History is one collapsed, button-backed disclosure.

M2 extends that same read-only projection. It returns contiguous, date-bounded phase segments and separately persisted A/B/C event markers, plus sampled actual and planner-forecast CTL/ATL/TSB series separated by a server-owned today boundary. The UI renders the roadmap proportionally and the chart with solid factual paths, dashed forecast paths, a target marker, textual legend, and an explicit local data-gap state. The browser only maps server values to coordinates; it does not calculate training metrics. Focused tests cover event, rolling-horizon, missing-history, target sampling, and source-level accessibility/legend expectations. The focused suite (35 tests), lint, build, `git diff --check`, and full smoke suite (`1365 passed, 1 skipped`) passed. Independent browser acceptance against an isolated database verified desktop and 390px mobile rendering, no horizontal overflow, and no console errors.

M3 adds one bounded read-only endpoint, `GET /api/planning/week-by-week`, and replaces the compact Weeks table with its responsive reader. The response preserves plan-day indices, session IDs, composite legs, steps, and existing export semantics; it enriches them only with the canonical reconciliation snapshot read without provider I/O. The server owns actual/unplanned totals, progress, remaining load, chart scale, and session states. The page opens the current week, exposes rest/unplanned/event context and leaf downloads, and routes ambiguous evidence to the existing correction flow. Independent review fixes keep event markers inside the chart clipping boundary, add phase colour plus text/ARIA equivalents, use one 16-week local fact read for the 16-week display without expanding the 12-week provider-I/O cap, preserve full plan ordinals, bound the post-plan event bridge to seven days, and scale bars against both plan and fact. New focused M3 plus adjacent planning/adherence contracts passed (`66 passed`); full smoke passed (`1374 passed, 1 skipped`); lint, production build, and `git diff --check` passed. Independent browser acceptance at 1280px and 390px confirmed the reader layout, visible event/phase encodings, exactly one initially open current week, no body overflow or console errors, and no disclosure-triggered API read.

Final evidence: 24 focused API/router/deep-link tests passed; the full contributor-safe smoke suite passed with `1360 passed, 1 skipped`; Next lint and production build passed from an isolated web copy. Browser acceptance against isolated copies of the active and empty databases verified the event overview as the 1280px default with no build form, the Weeks and Execution readers, explicit Edit, the `session_id` adjustment deep-link, no horizontal overflow at 390px, no-plan onboarding, and deterministic Enter/Space history disclosure. No provider write or planning confirmation was made.

## Context and Orientation

`api/planning_service.py` orchestrates existing planning models and restores the latest append-only checkpoint. `api/routers/planning.py` exposes its stable FastAPI contracts. `web/app/planning/page.tsx` is now reader-first: an active checkpoint opens Overview, while Weeks and Execution are sibling reader tabs; build/edit, adjustment, export, and history remain explicit actions. With no active checkpoint it opens the existing first-plan onboarding.

An active plan is the latest persisted planning checkpoint. A reader view only fetches and displays data. A mutating action can eventually write a checkpoint or a provider delivery and must therefore remain an explicit button. The M1 overview must never call a provider or a mutation while it renders.

The affected quality scenarios are ASR-REL-2 (missing data is a local gap, not a page failure), ASR-MOD-2 (a reusable reader projection), ASR-MOD-3 (an additive API contract), plus ATAM R3/R4 (contract tests and web-primary scope). No Streamlit code, planning formula, identity/lineage, reconciliation calculation, delivery behavior, or checkpoint storage schema changes are in scope.

### M2: Phase Roadmap and form projection

Issue #302 adds reader-only context to the M1 Overview. A roadmap is a sequence of contiguous phase segments derived from the persisted `weekly_summary`; each segment has its concrete date range, proportional position in the saved plan horizon, and the server-selected current marker. Existing saved A, B, and C events are returned separately and retain their stored priority; B/C do not become an A goal. A form projection contains separate `actual_points` and `forecast_points` plus a server-owned `boundary_date` equal to today. The historical points use the existing Banister model over local activity history. The future points reuse the existing planner forecast helper over future saved daily loads. No browser calculation changes CTL, ATL, or TSB.

M2 touches ASR-PERF-4 by sampling bounded historical and future series, ASR-REL-2 by returning data-gap envelopes instead of zero charts, ASR-MOD-2 and ASR-MOD-3 through one additive API field set, and ATAM R3 through direct router/service contract tests. It does not call a provider, write a checkpoint, or change scheduler/forecast mathematics.

### M3: unified week-by-week plan and fact reader

Issue #303 replaces the compact M1 Weeks table with a reader projection whose one response contains weekly target and actual load, phase and A/B/C event context, daily plan rows, and independently visible leaf sessions. The backend combines the persisted `weekly_summary`/`daily_plan`, `plan_days` export projection, and read-only canonical reconciliation snapshot with `include_provider=False`. It exposes exact matching output rather than introducing another reconciliation algorithm. A session dated today without a match is labelled `in_progress`; only an unmatched past session is `missed`. Unplanned load remains a separate field on its day and week.

M3 is constrained by ASR-REL-1 (never collapse composite/brick leaves or their IDs), ASR-REL-2 (explicit no-plan/data-gap/rest/unplanned states), ASR-PERF-4 (one bounded read projection, no N+1 disclosure reads), ASR-MOD-2/MOD-3 (reusable additive DTO), and ATAM R3 (direct service/router contracts). The endpoint is read-only and makes no provider request, checkpoint mutation, provider delivery, or frontend adherence calculation.

## Plan of Work

First add tests that prove the new endpoint returns an empty envelope for no checkpoint, an event-goal overview with a confirmed A event and countdown, and a training-goal overview with a rolling horizon and no invented race date. The tests also pin the route registration and the reader-first source structure that preserves the existing `session_id` adjustment deep link.

Add `active_plan_overview` to `api/planning_service.py`. It will restore the existing checkpoint snapshot and produce only display-ready, bounded values: goal, event or rolling timeline, current week, plan progress, and persisted execution status. Date parsing is defensive. Fields that cannot be derived are `null` or explicit `data_gap` values instead of exceptions. Expose it at `GET /api/planning/overview`.

Extend `web/lib/types.ts` with the additive DTO and rework only the top-level page state. When status reports a plan, the first resolved view is Overview. The reader navigation contains Overview, Weeks, and Execution. Explicit actions open the retained form, adjustment flow, or export flow. The no-plan path keeps BuildMode and therefore the existing FirstPlanCard onboarding. Render one collapsed button-backed Adjustment History outside the selected reader/action content.

For M2, add a planning-service helper used only by `active_plan_overview`. It must assemble phase ranges and event positions from the restored checkpoint, derive a sampled factual series from local activities, and call the existing `_forecast` helper for future plan dates. Its response must make boundary and data availability explicit. Extend `ActivePlanOverview` with an SVG/CSS roadmap and an SVG form chart. Both must include text equivalents and legends; no external chart package is added.

For M3, add `week_by_week_plan(db)` in `api/planning_service.py` and expose it at `GET /api/planning/week-by-week`. It must restore one checkpoint, use `plan_days` as the leaf/export source, call existing `reconciliation_at(..., include_provider=False)` once for the bounded past window, and return presentation-ready weekly, daily, session, actual, unplanned, event, and status fields. `web/app/planning/page.tsx` fetches this only for the Weeks reader tab and renders an accessible proportional TSS chart plus mobile-safe week cards. The current calendar week opens by default; other week details remain closed. Leaf export links use their persisted parent index and session ID/leg exactly as the existing export reader does.

## Concrete Steps

From `/Users/gregkisel/Developer/ai_trainer`, run:

    python -m pytest tests/smoke/test_planning_active_plan_overview.py -q
    python -m pytest tests/smoke/test_api_planning_router_contract.py -q
    python -m pytest tests/smoke/test_feedback_planning_handoff.py -q
    python -m pytest tests/smoke/test_planning_week_by_week.py -q
    python -m pytest tests/smoke -q
    npm --prefix web run lint
    npm --prefix web run build

For browser acceptance, start the local stack with `./run_web.sh` and use an isolated temporary database or the app's safe/demo state. Verify desktop width 1280 and mobile width 390. Do not click confirmation, adjustment confirmation, or Intervals delivery.

## Validation and Acceptance

The focused API tests must show that no plan produces `{has_plan: false}`, an event plan has a confirmed A-goal with the persisted date and non-negative time remaining, and a training plan returns `timeline.kind == "rolling"` without an event date/countdown. The UI source gate and browser check must show the form only after Edit plan, keep the first-plan card as the no-plan default, retain `session_id` focusing in adjustment, and show the history collapsed.

M3 acceptance additionally proves a past week reports plan, fact, and separately unplanned load; a future week renders no actual percentage; an unmatched current-day session is in progress rather than missed; ambiguous rows retain their existing correction action; brick/composite leaves retain independent session IDs and export links; A/B/C starts occur in their week; and no-plan/data-gap responses do not synthesize metrics. At 390px, week cards and SVG scale to the viewport without body overflow; no disclosure triggers another API request.

## Idempotence and Recovery

All M1 reads are derived from already persisted checkpoints and make no writes. Re-running tests is safe. If a browser fixture has no active plan, use the existing preview/confirm flow only in a temporary local database; do not use a provider-backed account. Reverting this work only removes an additive endpoint and web reader shell, leaving checkpoints intact.

## Artifacts and Notes

The primary implementation files are `api/planning_service.py`, `api/routers/planning.py`, `web/lib/types.ts`, and `web/app/planning/page.tsx`. The focused acceptance test will be `tests/smoke/test_planning_active_plan_overview.py`.

## Interfaces and Dependencies

`GET /api/planning/overview` returns a JSON object with `has_plan`. When true it also returns `goal`, `timeline`, `current_week`, `progress`, and `execution`. `timeline.kind` is either `event` (with confirmed A-event data and remaining time) or `rolling` (with only the saved horizon); missing values use `null` and `execution.state == "data_gap"` when no persisted execution projection exists. It depends only on `Database.get_latest_planning_checkpoint`, `restore_goal_plan_from_checkpoint`, and existing checkpoint summary functions.

After M2, the same endpoint additionally returns `roadmap` and `form_projection`. `roadmap` has a state, bounded phase segments, event markers, and a current marker. `form_projection` has a state, `boundary_date`, `actual_points`, `forecast_points`, and a ready-to-render numerical summary. A missing activity history, malformed date, or absent saved future plan returns `state: "data_gap"` with no synthetic zero path.

M3 adds `GET /api/planning/week-by-week`. For an active plan it returns `state: "available"`, `as_of`, bounded `weeks`, and a server-calculated chart scale. A week has target/actual/unplanned TSS, server-calculated completion/remaining values, phase/events, an adherence aggregate, and seven calendar days. A non-rest day contains the `plan_days` leaf sessions enriched only with the already canonical match status/actual fields. `state: "no_plan"` returns no weeks; malformed checkpoint dates return `state: "data_gap"`, never a fabricated rest or zero-completion plan.

Plan revision 2026-08-03: M1 (#301), M2 (#302), and M3 (#303) are merged to `main` through PRs #327–#329. Independent-review regressions are fixed; automated and browser validation are green. This ExecPlan is complete through M3; any M4 work requires a separately approved scope.
