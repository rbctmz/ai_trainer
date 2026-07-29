# Preserve executable workouts after recovery replans

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`,
`Decision Log`, and `Outcomes & Retrospective` must stay current while the work proceeds.
This document is maintained according to `.agent/PLANS.md`.

## Purpose / Big Picture

A recovery or near-term plan adjustment must leave a workout that the athlete can inspect,
export, and deliver exactly as planned. Today those mutations replace catalog workouts with
`manual:*` placeholders that have TSS and an estimated duration but no saved steps or targets.
The UI consequently shows only a sport and phase, while export silently invents a different
generic workout from TSS. After this change, every changed non-rest session is rematerialized
through the same workout catalog used by initial planning, every session on a multi-session
day is visible and independently exportable, and an existing broken checkpoint can be repaired
by creating a new append-only checkpoint.

## Progress

- [x] (2026-07-29 06:30Z) Reproduced the defect against the active local checkpoint and traced it through recovery proposals 44-46.
- [x] (2026-07-29 06:45Z) Identified the shared materializer, API projection, export fallback, and compatibility boundaries.
- [x] (2026-07-29 07:05Z) Added six RED behavior gates for recovery rematerialization, duration parity, multi-session API/export, fail-closed modern placeholders, and append-only repair; all six fail against `main`.
- [x] (2026-07-29 08:10Z) Reused the initial-plan materializer from whole-day,
  targeted-session, and future-week near-term edit paths.
- [x] (2026-07-29 08:25Z) Extended the planning API/web contract to expose and
  export every leaf session and to block modern sessions without saved steps.
- [x] (2026-07-29 08:40Z) Added dry-run-first, append-only repair service and CLI.
- [x] (2026-07-29 09:15Z) Ran focused, smoke, full offline, web lint, and web
  production-build validation.
- [x] (2026-07-29 09:35Z) Completed final diff review, published RED commit
  `315af5f` plus GREEN commit `f13f842`, and opened PR #305 with `Closes #299`.

## Surprises & Discoveries

- Observation: The active plan was originally structured. Three approved `downgrade_today`
  proposals successively converted 2026-07-30, 2026-08-01, and 2026-08-03 into `manual:*`
  sessions without `materialized_steps`.
  Evidence: checkpoints 74, 75, and 76 each introduce one additional placeholder.

- Observation: The legacy export fallback is not presentation-only. It derives duration from
  TSS, so a planned 80-minute bike session exports as 40 minutes.
  Evidence: `build_delivery_events` produced 2400 seconds for the active 2026-08-01 session.

- Observation: 2026-08-03 contains both bike and swim leaves, but `plan_days` projects only
  the day primary. The web table therefore hides the swim while Intervals delivery emits both.

- Observation: The complete RED file fails in six independent ways rather than stopping at
  collection, which proves each missing behavior directly.
  Evidence: `6 failed in 1.48s` in `test_recovery_replan_materialization_p1.py`.

- Observation: Preserving the exact discipline budget exposed a missing low-load swim
  catalog envelope: a 30-minute, 9.8-TSS secondary swim had no feasible definition.
  Evidence: the direct catalog gate returned `legacy_role_fallback`; catalog v3 now
  materializes it as `swim_recovery_technique`.

- Observation: The future-week composite branch contained dormant undefined variables and
  would drop the brick's nested session after a weekly adjustment.
  Evidence: the new brick-rebalance gate failed with `NameError: target_sport`; it now
  rescales both legs and keeps their exact steps.

- Observation: A repair that merely selected any feasible `easy` template converted the
  active 2026-08-01 recovery cutback into neuromuscular sprints.
  Evidence: apply on a copied checkpoint selected `bike_neuromuscular_sprints`; recovery
  lineage now resolves broken `manual:*` leaves through recovery-role definitions.

## Decision Log

- Decision: Reuse a public day-session materialization helper shared with the initial planner,
  rather than duplicate catalog selection inside `planning_near_term.py`.
  Rationale: Initial and edited plans must have one executable-truth path.
  Date/Author: 2026-07-29 / Codex.

- Decision: Keep the legacy no-steps fallback only for genuinely legacy records. A modern
  `manual:*` session or an explicit non-materialized status fails closed.
  Rationale: Backward compatibility must not conceal corruption introduced by current code.
  Date/Author: 2026-07-29 / Codex.

- Decision: Add an explicit leaf-session selector to export while preserving the existing
  day-index route and default-primary behavior.
  Rationale: The API remains backward compatible and multi-session days become fully usable.
  Date/Author: 2026-07-29 / Codex.

- Decision: Repair is explicit and append-only, never migrate-on-read.
  Rationale: ADR-0006 requires plan history to remain auditable and reversible.
  Date/Author: 2026-07-29 / Codex.

- Decision: Bump the catalog provenance to `workout_catalog_v3` and add one bounded
  `swim_recovery_technique` definition rather than relaxing the existing aerobic-swim
  envelope or synthesizing steps at export time.
  Rationale: low-load discipline truth needs a real versioned prescription.
  Date/Author: 2026-07-29 / Codex.

- Decision: Repair `manual:*` leaves under `recovery_replan` lineage with recovery-role
  selection and explicit `repair_evidence`.
  Rationale: operational repair must preserve safety intent, not merely produce valid bytes.
  Date/Author: 2026-07-29 / Codex.

## Outcomes & Retrospective

The implementation now keeps recovery and near-term mutations executable through the same
catalog path as initial planning. API and web expose every leaf of a multi-session day;
export and Intervals delivery use saved prescriptions and fail closed on modern broken
records. A dry-run-first CLI repairs broken recovery checkpoints append-only.

Against a copy of the active local database, dry-run reported exactly 2026-07-30,
2026-08-01, and 2026-08-03. Apply created checkpoint 77 from parent 76; a repeated dry-run
reported no changes. The repaired days contain Recovery Run, Recovery Spin, and Recovery
Technique Swim prescriptions, and all four delivery events use the same persisted seconds.
The real `ai_trainer.db` remains untouched until this PR is merged. Publication is
reviewable in PR #305; the branch intentionally excludes the developer-owned untracked
`.zcode/` directory.

## Context and Orientation

`models/training_planner.py` builds initial session templates. Its day splitter calls
`models.workout_catalog.materialize_session_template`, which selects a catalog definition and
persists exact steps, duration, targets, provenance, and a prescription fingerprint.

`models/planning_near_term.py` applies confirmed near-term and recovery changes. Its current
`_sessions_from_parts` and targeted-edit branch create plain dictionaries with keys such as
sport, TSS, and `manual:<phase>:<role>:<sport>`, but do not call the catalog materializer.
`models.training_planner.project_day_scalars` correctly removes stale primary-session fields;
because the replacement has no materialization fields, the day becomes non-executable.

`api/planning_service.py::plan_days` projects one row per day, while
`web/app/planning/page.tsx` renders those rows. `api.planning_service.export_workout` and
`models.intervals_workout_delivery.build_delivery_events` currently synthesize generic steps
when saved steps are absent. A leaf session means one independently executable run, bike, or
swim record inside a day template's `sessions` list.

## Plan of Work

First add behavioral tests using a real generated plan and the existing recovery/near-term
mutation functions. The tests will prove that a changed session remains materialized, its step
seconds equal its displayed duration, and repeated edits never introduce a `manual:*` key.
Add contract tests showing that modern placeholders are rejected before export or delivery,
while the existing legacy fixture still receives its compatibility fallback.

Expose the initial planner's day-session materialization operation as a shared model helper.
Call it from whole-day and targeted near-term edit paths with the plan's persisted zone snapshot,
load state, and preceding catalog keys. Preserve lineage through the existing
`ensure_session_identities` call rather than copying stale prescription fields.

Extend `plan_days` additively with a `sessions` array for leaf records. Add an optional
`session_id` selector to the existing export function and API query contract. Update the web
table to render each leaf and use that selector for downloads. Existing callers that omit it
continue to export the primary session.

Add a pure repair operation that rematerializes only non-rest `manual:*` or explicitly
non-executable sessions. Wrap it in a database service/CLI action that saves a new planning
checkpoint with repair provenance only when changes exist. Default execution is a dry run;
the apply mode is explicit. Historical checkpoints remain untouched.

## Concrete Steps

Work from `/Users/gregkisel/Developer/ai_trainer`.

Run focused RED gates:

    ai_trainer_env/bin/python -m pytest \
      tests/smoke/test_recovery_replan_materialization_p1.py \
      tests/smoke/test_api_planning.py \
      tests/smoke/test_intervals_plan_delivery.py -q

After implementation, run:

    ai_trainer_env/bin/python -m pytest tests/smoke -q
    ai_trainer_env/bin/python -m pytest -m "not live and not debug" tests/
    npm --prefix web run lint
    npm --prefix web run build

Observed verification:

    focused planning/catalog/API/delivery/recovery: 160 passed
    smoke: 1305 collected, exit 0
    full offline: 1353 selected, exit 0
    web lint: no warnings or errors
    web production build: compiled and type-checked successfully

Before any repair of `ai_trainer.db`, run the repair command in dry-run mode and inspect the
reported dates. Apply only after the code PR is merged and a SQLite backup exists.

## Validation and Acceptance

The new recovery gate must fail before implementation because the edited session has no
`materialized_steps`, then pass with `materialization_status == "materialized"`. Repeating the
edit on subsequent dates must produce no `manual:*` sessions.

For every returned leaf, the sum of saved step seconds must equal `duration_minutes * 60`.
Export and Intervals delivery must use those exact saved seconds. A multi-session day must
return both leaves from `plan_days`, and each leaf must export using its own sport, name, and
steps. Passing no session selector must retain the existing primary export behavior.

A synthetic modern `manual:*` session without steps must raise before provider delivery or file
generation. The existing legacy compatibility fixture without a modern/manual marker must
continue to export.

Repair dry-run must report changes without writing a checkpoint. Apply must add exactly one
checkpoint with a parent pointing to the broken checkpoint, leave the parent byte-for-byte
unchanged, and be idempotent on a second invocation.

## Idempotence and Recovery

All tests use temporary SQLite databases. Plan repair is additive: dry-run is read-only, apply
creates a new checkpoint, and repeating apply on an already repaired active plan performs no
write. If validation fails, the previous checkpoint remains active and can be restored through
the existing append-only history. The developer-owned `.zcode/` directory remains untouched.

## Artifacts and Notes

Observed active-plan mismatch before the fix:

    2026-07-30 planned 35 min / delivered 31 min
    2026-08-01 planned 80 min / delivered 40 min
    2026-08-03 UI shows bike only / delivery emits bike and swim

## Interfaces and Dependencies

No new dependency is required. The implementation must use
`models.workout_catalog.materialize_session_template`,
`models.workout_catalog.extract_zone_snapshot`,
`models.session_identity.ensure_session_identities`, and the existing planning checkpoint
helpers. The planning API change is additive: `plan_days` gains leaf-session data and workout
export gains an optional stable `session_id` selector. Existing day-index consumers remain
valid.

Revision note (2026-07-29): Initial executable specification created after reproducing the
active-plan defect. Updated after the six-gate RED run to record direct pre-fix evidence.

Revision note (2026-07-29): Closed implementation and validation evidence after the
catalog-v3, API/web, fail-closed delivery, and append-only repair slices; recorded PR #305.
