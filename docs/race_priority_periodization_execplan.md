# Make planning event-priority aware

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

This document must be maintained in accordance with `.agent/PLANS.md` at the repository root.

## Purpose / Big Picture

After this change an athlete can build one of three explicit kinds of plan: a plan anchored to an A race, a rolling fitness plan without a race, or a manually phased plan. Earlier B and C events become bounded local overlays instead of accidentally ending the macrocycle. Events discovered from Intervals.icu are read-only previews with source and confidence, including Olympic triathlons stored as `RACE_A` plus `type=Other`. A user sees the resulting phases, weekly load and event changes before confirming a new checkpoint; cancelling the preview changes neither SQLite nor Intervals.icu.

The live-shaped regression is a B Olympic triathlon on 2026-07-26 followed by an A Olympic triathlon on 2026-10-04. The plan must show a short B-race reduction, no ordinary workout on 26 July, two protected recovery days, and a resumed macrocycle toward 4 October. The behavior is demonstrated with synthetic fixtures only.

## Progress

- [x] (2026-07-13 09:26Z) Read issue #169, its two owner clarifications, repository workflow, `.agent/PLANS.md`, and the existing event/planning/checkpoint/export paths.
- [x] (2026-07-13 09:26Z) Completed publish preflight, created `codex/issue-169-race-priority-periodization` in `/private/tmp/ai_trainer_issue169`, and recorded the wider product sequence in roadmap issue #170.
- [x] (2026-07-13 09:26Z) Pre-registered the event/provenance contract, three planning modes, overlay precedence and bounded A/B/C rules in this ExecPlan.
- [x] (2026-07-13 09:32Z) Added contract-first smoke tests for event normalization, Intervals.icu discovery, planning modes and A/B/C overlays. The pre-implementation run failed during collection on the intentionally absent `macrocycle_event` and `apply_race_event_overlays` interfaces.
- [x] (2026-07-13 09:58Z) Added API/checkpoint preview-confirm tests, including zero-write previews and a stale-checkpoint 409 guard.
- [x] (2026-07-13 09:44Z) Implemented provenance-aware event normalization, confirmed-A macrocycle selection, bounded Intervals.icu GET discovery, three phase modes, `race-overlay-v1`, checkpoint metadata, API preview/confirm enforcement, and the protected-date RecoveryReplan guard.
- [x] (2026-07-13 09:44Z) Focused domain/API/checkpoint/recovery contour passes: 74 tests in 1.48s.
- [x] (2026-07-13 09:45Z) Wired the web Planning mode selector, read-only Intervals event choices, rolling/manual controls, preview diff, cancel and explicit confirmation. Next.js production build passes.
- [x] (2026-07-13 09:58Z) Final full smoke passes with 522 passed and one environment socket skip; the production Next.js build passes with type checking.
- [x] (2026-07-13 09:59Z) Broader contributor-safe contour passes with 565 passed, 6 environment/data-dependent skips and 24 deselected live/debug tests.
- [x] (2026-07-13 09:45Z) Synthetic live-shaped acceptance proves preview leaves SQLite untouched, 04.10 anchors the plan, final phases are Taper/Race Week, 26–28.07 are zero/protected, and load resumes 29.07.
- [x] (2026-07-13 09:58Z) Completed self-review: persisted phases now drive current-phase consumers, execution feedback reapplies event overlays, previews do not alter demand settings, and confirmation rejects a stale base checkpoint.
- [x] (2026-07-13 10:03Z) Committed in docs/test/feat/workflow order, pushed the isolated branch, and opened draft PR #171 with `Closes #169`; merge remains at the human gate.

## Surprises & Discoveries

- Observation: `compute_phase_schedule(3)` first constructs Base, Build, Peak and Taper, then truncates the tail, so Taper disappears.
  Evidence: `models/training_planner.py::compute_phase_schedule` creates at least one of every phase and executes `phases[:weeks_total]`.

- Observation: event persistence is already JSON-native and append-only, so provenance and overlay metadata require no SQLite schema migration.
  Evidence: `models/planning_checkpoints.py::build_planning_checkpoint` copies `events` into `goal_plan_snapshot`, and every accepted plan creates a new checkpoint.

- Observation: recovery proposals only reduce one existing session and use stale-checkpoint guards, but race protection is not yet a shared plan invariant.
  Evidence: `api/recovery_replan_loop.py` delegates to `models.recovery_replan.build_recovery_replan_variant`; event dates are not currently represented in its input contract.

- Observation: the Intervals.icu client already owns authenticated request construction and event writes, but has no bounded event-listing method.
  Evidence: `services/intervals_icu.py::IntervalsICUClient` exposes calendars/profile/create-event only.

- Observation: the isolated worktree does not contain the ignored virtualenv directory.
  Evidence: `./ai_trainer_env/bin/python` returned “no such file or directory”; tests use `/Users/gregkisel/Developer/ai_trainer/ai_trainer_env/bin/python` while keeping the worktree as cwd.

- Observation: the contract-first run is red for the intended missing public interfaces, not for fixture or environment failures.
  Evidence: pytest collection reports `cannot import name 'macrocycle_event'` and `cannot import name 'apply_race_event_overlays'`.

- Observation: the real Intervals.icu event endpoint and query contract work, but both current races are now explicitly B, including 2026-10-04 whose description still says “А-гонка”.
  Evidence: the read-only acceptance returned `RACE_B` for IDs 102286932 and 104750840; normalization correctly trusts category for priority and text only for triathlon discipline.

- Observation: execution-feedback replanning rebuilt daily sessions from weekly totals and would have discarded event caps if only checkpoint serialization were changed.
  Evidence: `models/planning_execution.py::rebuild_goal_plan_with_adjustment` called `expand_weekly_to_daily_triathlon` and rebuilt templates without event overlays. Self-review added overlay reapplication and a regression test.

- Observation: the original preview path wrote the selected demand level even with `persist=false`, and confirmation did not prove that the viewed checkpoint was still current.
  Evidence: self-review traced `build_plan` through `db.set_user_setting` and the web confirm request. The API now treats preview as fully read-only, returns `base_checkpoint_id`, and responds with 409 if another checkpoint appeared before confirmation.

## Decision Log

- Decision: Keep `events` as the canonical list, add provenance fields additively, and retain `event_date` only as a compatibility alias.
  Rationale: checkpoints and consumers already understand `events`; additive dictionaries preserve old readers while exposing whether a priority was explicit or assumed.
  Date/Author: 2026-07-13 / Codex.

- Decision: Define `macrocycle_event_date` separately from the nearest event overlay. It is the selected confirmed A event in `event_goal`; it is empty in `training_goal` and `manual`.
  Rationale: a B or C race can affect nearby days without terminating long-term training. This is the root defect in the current single-date coordinate system.
  Date/Author: 2026-07-13 / Codex.

- Decision: Use planning modes `event_goal`, `training_goal`, and `manual`. Existing requests containing only `event_date` remain `event_goal` and create a confirmed user A event.
  Rationale: backward compatibility is necessary, while no-race development must not invent a date or taper.
  Date/Author: 2026-07-13 / Codex.

- Decision: Pre-register overlay rule version `race-overlay-v1`. A uses D-7 through D-1 load caps of 65%, 60%, 55%, 50%, 40%, 30%, and 20%; B uses D-4 through D-1 caps of 75%, 60%, 45%, and 25%; C has no weekly taper and caps D-1 at 70%. A/B/C event day is immutable with no ordinary workout. A and B protect D+1 and D+2 at zero planned load; C caps D+1 at 50% and marks it recovery. Caps can only reduce the already constrained plan.
  Rationale: the issue requires exact bounded rules before implementation. These conservative values preserve frequency before A/B starts, train through C, and cannot increase load or bypass availability/readiness constraints.
  Date/Author: 2026-07-13 / Codex.

- Decision: A-anchored phase schedules always reserve the final two materialized weeks as `Taper` and `Race Week`; a one-week horizon is `Race Week`. Training goals use rolling Base/Build/Recovery or Maintenance/Recovery cycles and never emit race phases. Manual phases are preserved verbatim.
  Rationale: list truncation can no longer remove taper, while rolling and manual plans keep their distinct meaning.
  Date/Author: 2026-07-13 / Codex.

- Decision: Intervals.icu discovery is GET-only and bounded to at most 365 days. `RACE_A`, `RACE_B`, and `RACE_C` are the only imported race priorities. `type=Other` becomes triathlon only when structured metadata or name/description contains strong multi-sport evidence; otherwise discipline remains unknown and `requires_confirmation=true`.
  Rationale: priority and sport are independent. A guessed sport must never be written back or silently used as certainty.
  Date/Author: 2026-07-13 / Codex.

- Decision: The web Planning builder first calls `/api/planning/build` with `persist=false`; confirmation repeats the same request with `persist=true` and `confirm=true`. Imported or assumed event changes cannot persist without `confirm=true`.
  Rationale: this is the smallest contract-first preview flow compatible with the existing append-only checkpoint mechanism. No server-side mutable draft store is necessary for v1.
  Date/Author: 2026-07-13 / Codex.

- Decision: Bind every confirmation to the active checkpoint ID returned with its preview, using zero for an empty history. Reject a mismatch with HTTP 409 and require a fresh preview.
  Rationale: a coach, recovery proposal, or second browser can append a checkpoint while the preview is open; persisting an obsolete comparison would silently overwrite the user's mental model even though checkpoint history remains append-only.
  Date/Author: 2026-07-13 / Codex.

## Outcomes & Retrospective

The shared domain, additive API and web preview/confirm flow are implemented in draft PR #171. Macrocycle intent, event overlays and daily readiness are ordered layers rather than competing phase sources. Event protection survives execution-feedback replans, current phase consumers use persisted phases, and preview/confirm is both zero-write and concurrency-safe. Final smoke is 522 passed plus one environment-dependent skip, the broader contour is 565 passed with expected skips, and the Next.js production build succeeds. The implementation is published; only review and the human merge gate remain.

## Context and Orientation

`models/plan_events.py` currently normalizes each event to only `date`, `priority`, and `label`. When a legacy checkpoint has only `event_date`, it synthesizes an A event without marking that assumption. `primary_event` selects A before B before C and `synchronize_goal_plan_events` writes that date back to the compatibility alias.

`api/planning_service.py::build_plan` is the headless product planner. It accepts exactly one date, computes `weeks_to_race`, generates weekly TSS, calls `models/training_planner.py::compute_phase_schedule`, expands weeks into daily load, builds session templates, and optionally persists a checkpoint. `api/routers/planning.py` and `web/app/planning/page.tsx` expose that flow. New behavior belongs here and in shared Python, not in legacy Streamlit.

`models/planning_checkpoints.py` serializes full goal-plan snapshots. `models/planning_execution.py` and `models/planning_near_term.py` rebuild future load and must preserve the same event/protection metadata. `api/recovery_replan_loop.py` creates suggestion-only reductions and must not be able to add a session on a protected event/rest date.

`services/intervals_icu.py` is the existing API-key client. A bounded read uses `GET /api/v1/athlete/{athlete_id}/events` with `oldest` and `newest` ISO-date parameters. Discovery never calls the existing create-event method.

An event gains additive fields: `source` (`user`, `intervals_icu`, or `legacy_checkpoint`), `source_id`, `category`, `discipline`, `discipline_provenance`, `discipline_confidence`, `priority_provenance`, `confirmed`, and `requires_confirmation`. Older events lacking them remain valid. A synthesized legacy A has `priority_provenance=legacy_assumed`, `confirmed=false`, and `requires_confirmation=true`.

Planning precedence is fixed. User availability and weekly capacity create the unconstrained plan. Planning mode creates the macrocycle phases. A/B/C overlays may only reduce or protect the resulting daily load. Durable coach constraints apply next. Readiness and RecoveryReplan may reduce a remaining session but cannot remove protection or increase a capped day. All surfaces consume the persisted result.

## BDD Scenarios

Given Intervals.icu returns `RACE_B` on 2026-07-26, when events are discovered, then the event is B with explicit-category and Intervals.icu provenance and is never promoted to A.

Given `RACE_A`, `type=Other`, and text containing Olympic triathlon plus swim, bike, and run segments, when the event is normalized, then discipline is triathlon with evidence provenance and nonzero confidence.

Given an `Other` event without multi-sport evidence, when it is normalized, then discipline is unknown, confirmation is required, and no write occurs.

Given a B event and a rolling develop goal, when an eight-week plan crosses the event, then D-4 through D-1 are capped, event day and D+1/D+2 are protected, and normal rolling phases resume afterward.

Given an A event after an earlier B event, when an event-goal plan is built, then A supplies `macrocycle_event_date`, the last weeks are Taper and Race Week, and B remains a local overlay.

Given a C event, when a plan crosses it, then weekly phases do not change, event day contains no ordinary workout, D-1 is capped, and D+1 is recovery-capped.

Given maintain or develop without an A event, when a training goal is built, then it has a four-to-eight-week rolling horizon, planned recovery weeks, no synthetic event, no `weeks_to_race`, and no Taper or Race Week.

Given manual phases, when a plan is built, then automatic event-goal or rolling phase allocation does not replace those phases; event-day safety overlays still apply to supplied A/B/C events.

Given a legacy checkpoint with only `event_date`, when restored, then its synthesized A is visibly assumed. Given a matching explicit Intervals.icu B in a preview, then the preview shows the correction and persistence requires confirmation.

Given any unconfirmed preview, when the user cancels or simply does not confirm, then checkpoint count is unchanged and no Intervals.icu mutation is invoked.

## Plan of Work

First extend smoke tests before implementation. `tests/smoke/test_plan_events.py` will pin provenance, macrocycle-anchor selection, triathlon classification and ambiguity. `tests/smoke/test_intervals_icu_service.py` will pin the bounded GET contract and normalization. A new `tests/smoke/test_race_priority_periodization.py` will exercise phase schedules and synthetic A/B/C overlays. `tests/smoke/test_api_planning.py` and checkpoint tests will pin the three modes, preview/confirm, legacy round trips and the live-shaped B-then-A scenario.

Then extend `models/plan_events.py` with additive normalization and anchor helpers. Add pure event-aware phase and overlay functions to `models/training_planner.py`; they accept serializable events and return copied daily/weekly structures plus versioned overlay metadata. Update phase helpers so `Race Week`, `Recovery`, and `Maintenance` have explicit behavior rather than falling into an accidental default.

Next add bounded event reads and pure response normalization to `services/intervals_icu.py`. Expose a read-only discovery endpoint in `api/routers/planning.py`. Extend the build request and `api/planning_service.py::build_plan` with planning mode fields, explicit events, preview metadata and confirmation. Preserve the old direct Python signature and one-date behavior.

Thread `planning_mode`, `macrocycle_event_date`, event provenance, `overlay_rule_version`, `event_overlays`, and `protected_dates` through checkpoints and execution replans. The persisted daily plan and session templates are the only phase/session truth consumed by dashboard, coach and exports.

Finally update `web/lib/types.ts` and `web/app/planning/page.tsx`. The user selects a mode, previews before persistence, sees event provenance and phase/load differences, and confirms or cancels. Keep the UI minimal and reuse existing cards/buttons.

## Concrete Steps

Work from `/private/tmp/ai_trainer_issue169`.

Run the new event and periodization tests before implementation and record failures:

    ./ai_trainer_env/bin/python -m pytest tests/smoke/test_plan_events.py tests/smoke/test_intervals_icu_service.py tests/smoke/test_race_priority_periodization.py tests/smoke/test_api_planning.py -q

After each domain slice, rerun the focused files. After API/web wiring, run:

    ./ai_trainer_env/bin/python -m pytest tests/smoke -q
    cd web && npm run build

Use a temporary SQLite database for the acceptance probe. Build an eight-week training goal containing synthetic B 2026-07-26 and A 2026-10-04 events, assert the A anchor and B protection, preview without persistence, then confirm and verify exactly one new checkpoint.

## Validation and Acceptance

Acceptance requires every issue scenario to be observable through public functions or the API, not only internal helpers. The new focused tests must fail before implementation and pass afterward. Full smoke must not regress below the baseline of 501 passed plus one environment-dependent skip. The Next.js production build must pass.

The synthetic 26 July scenario must prove that no ordinary session survives on event day, D+1/D+2 remain protected after a RecoveryReplan proposal, and training load is nonzero again after the protected window. A short A horizon must contain `Race Week` and, when at least two weeks exist, `Taper` immediately before it.

Discovery tests must inspect the HTTP method and query parameters and prove that no POST/PUT/DELETE request is made. Preview cancellation must leave the checkpoint count unchanged. Confirmation must append a checkpoint whose snapshot carries the event and overlay provenance and whose previous checkpoint remains restorable.

## Idempotence and Recovery

All event normalization, phase scheduling and overlay functions are pure and safe to repeat. Intervals.icu discovery is read-only. A preview never persists. Confirmation appends a new checkpoint and does not rewrite history. If implementation is abandoned, delete only the isolated worktree after preserving any wanted commits; there is no database migration to roll back.

## Artifacts and Notes

Roadmap issue #170 contains the later sequence: plan/fact reconciliation, structured catalog and brick, daily decision card, RPE feedback, recovery curves, then last-mile delivery #168. Those are explicitly outside this PR except where #169 creates stable contracts they will consume.

## Interfaces and Dependencies

`models.plan_events` must expose normalized event dictionaries plus helpers equivalent to:

    def macrocycle_event(events: Any) -> dict[str, Any] | None: ...
    def normalize_intervals_event(payload: Mapping[str, Any]) -> dict[str, Any] | None: ...

`models.training_planner` must expose pure helpers equivalent to:

    def compute_event_aware_phase_schedule(weeks_total: int, *, planning_mode: str, intent: str, manual_phases: Sequence[str] | None = None) -> list[str]: ...
    def apply_race_event_overlays(daily_plan, weekly_summary, events, *, start_date: date) -> tuple[list, list, dict]: ...

`services.intervals_icu.IntervalsICUClient` must add a bounded GET method and the module must expose a configured wrapper that returns normalized A/B/C events.

`POST /api/planning/build` gains additive fields `planning_mode`, `intent`, `focus`, `horizon_weeks`, `manual_phases`, `events`, and `confirm`. Its response gains `preview`, `confirmation_required`, `planning_mode`, `macrocycle_event_date`, and event-overlay metadata. Existing clients that send only the old fields continue to build the same confirmed A-event plan.

Plan revision note: 2026-07-13, initial self-contained design written after source audit; exact overlay caps, precedence, provenance and preview semantics were resolved before tests or implementation.

Plan revision note: 2026-07-13, implementation update after TDD and self-review; added real endpoint evidence, persisted-phase consumption and event-overlay reapplication during execution feedback.
