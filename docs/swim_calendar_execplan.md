# Place and protect trainer workouts in the selected planning cycle

Issue #763. Contract [swim_calendar_slice_spec.md](swim_calendar_slice_spec.md).
This plan follows .agent/PLANS.md and the Class A workflow.

## Purpose / Big Picture

An athlete assigns their saved trainer workouts to actual dates, reviews the
calendar effects and confirms. Later adjustments preserve the exact intervals
and equipment until the athlete confirms an authored change. The calendar can
show a workout with unknown load or duration and retain that uncertainty.

## Progress

- [x] 18.11.2026: read #763/#668, the merged M2 baseline, ADR-0001, reliability
  and compatibility ASRs, and both selected-cycle publication paths.
- [x] Protect the additive assignment state at checkpoint boundaries. RED
  c844afa reproduced five cases. The checkpoint serializer lost the field,
  the adjustment writer accepted removal/substitution, and retained rebuild
  publication accepted omission/out-of-period references. All five pass after
  adding preservation and transaction guards. The wider cycle/demand/recovery
  suite passed 179 cases. Two added integration cases prove generic history
  restore keeps the current references and the new cycle leaves the old
  schedule in history. The latest focused run passed all seven cases.
- [x] Add authoritative date validation, retained preview/confirm, diff and
  history/rollback with owned SQLite proof. The command cases cover place,
  move, substitute, remove, rollback, actual concurrent stale confirm, replay,
  exact date override, explicit human action, unknown dose, expiry, full reset
  and a Backup API roundtrip. The eighth checkpoint test confirms an actual
  edit-current rebuild preserves the authored reference.
- [x] Project readbacks into Plan and add a library entry point and review UI.
  Browser RED c700d5a failed at the missing library link. Two expanded cases
  exercised appointment, exact steps, move and rollback in dark390/light1280.
  Initial expanded run reached move but timed out at the rollback selector.
  Explicit accessible labels and a history readback assertion produced two
  passes. Final M2/M3 focused browser run: 11 passed in 39.96s with no cleanup
  error. The last combined planning/Recovery/contract run passed 295 cases.
- [ ] Verify full flow, current CI, independent review and owner decision.

## Surprises & Discoveries

- **Observed**: normal adjustment writes call `append_cycle_child`. Exact
  edit-current build publications call `publish_cycle_checkpoint` separately.
  `build_planning_checkpoint` enumerates snapshot keys, so restore by itself
  does not ensure a new field survives the next serialization.
- **Inferred**: protecting one writer or one rescale function leaves paths that
  can omit calendar assignments. Test the two writer paths and roundtrip.
- **Verified by**: repository search of all insertion and association call
  sites, followed by five isolated pytest failures on the unmodified writers
  and five passes with the snapshot and transaction guards.
- **Observed**: #668 is open and Git has local candidate branches. A search of
  tracked main code returned no `allowed_sports_by_day`.
- **Inferred**: M3 needs the shared eligibility semantics from that candidate,
  with a small and explicit handoff before date validation is declared complete.
- **Verified by**: authenticated issue #668 and local branch/code inventory.
- **Observed**: a legacy checkpoint can contain a confirmed event without a
  generated protected-date list. The isolated HTTP check accepted placement on
  that event date.
- **Inferred**: the event declaration must protect its own date independently
  of a later race overlay calculation.
- **Verified by**: the same synthetic checkpoint gained a 409 refusal after
  including confirmed events through the existing event normalizer.

## Decision Log

- 18.11.2026: add typed references in cycle checkpoint snapshots. Existing
  immutable library versions provide source, series and equipment without a
  lossy conversion to generic TSS-based materialized steps. Generic snapshot
  history and cycle ownership remain the lifecycle authority.
- 18.11.2026: use a dedicated authored-calendar proposal with full cycle CAS.
  Existing general restore and rescale retain authored references. The authored
  rollback proposal restores only its own part of the historical checkpoint.
- 18.11.2026: retain ordinary plan numeric calculations and disclose the
  unmeasured authored load next to the chart and forecast context. Surface a
  dated review action from the existing Recovery readiness evidence. Only
  the user supplies a new date and confirms a reviewed move.

## Context and Orientation

`data/planning_cycle_writes.py` owns mutable-cycle CAS and appends generic
children. `data/planning_cycles.py` handles retained build publication.
`models/planning_checkpoints.py` serializes and restores the snapshot.
`data/swim_program_store.py` resolves an immutable program version.
`api/planning_service.py` and `web/app/planning/page.tsx` project the calendar.
The library route is `web/app/coach/swim/page.tsx`.

## Plan of Work

First implement protection at both SQLite writer paths with a synthetic
checkpoint roundtrip. Verify normal edits still commit with the same authored
array and that omission, substitution and out-of-cycle dates fail without
changing history. This is a model/data handoff within #763.

Then add the domain and API commands. Capture selected-cycle and source
version in one coherent preview, bind command and receipt to concrete state, and
exercise expiry, race, lost response, dates and history/rollback. Preserve
uncertainty and expose actionable reasons. Hand typed DTOs and fixtures to UI.

Finally render library-to-calendar and proposal/confirmation in Next using the
server rules. Capture the isolated browser journey, synchronize TS contracts,
run full CI and review the concrete PR. The owner decides merge for that head.

## Concrete Steps

From branch `codex/issue-763-swim-calendar` use the repository's Python
environment and `scripts/run_isolated_tests.py`. Start with the focused
`tests/smoke/test_swim_calendar_checkpoint.py` and cycle writer/build suites.
Run contributor-safe Python, Ruff, contract extraction/inventory, web lint/build,
then browser acceptance with an owned scratch database. Commit completed RED and
GREEN steps on the task branch. Keep production data and provider credentials
out of the isolated tests.

## Validation and Acceptance

Use three synthetic workouts, a missing-duration chart case, a cross-week move
and the prior checkpoint as rollback target. Verify identity, exact source and
structure lookup, no mutation in generic flows, proper CAS, exact replay and
independent cycle lifecycle. The issue and slice spec enumerate remaining gates.

## Idempotence and Recovery

Only the explicit confirmation publishes a new author-calendar snapshot.
Generic writers cannot change authored references. Confirm replay returns the
existing receipt with its original checkpoint ID. History and backup retain
both referenced library versions and their checkpoints.

## Artifacts and Notes

Starting main 1fd9d67. M2 documentation remains on its separate local branch.
Synthetic screenshots and source checksums are under
`docs/design/evidence/issue-763`. Tests use a temporary demo store and
leave no application instance running.

## Interfaces and Dependencies

Use additive Python snapshot state, selected-cycle writer token, immutable
swimming library versions, shared date eligibility and typed planning API/TS.

Domain/API to UI handoff. Consume the typed GET, POST preview and POST confirm
under `/api/planning/swim-calendar`. Preview has dated before/after rows with
exact library IDs, workouts, environment, distance and unknown duration/load.
Each exact prescription opens through the existing immutable library route.
The Plan weeks projection displays assignments from the same checkpoint as its
generated rows. The editing page makes date, source version and before/after
visible before confirmation. Reuse the existing planning and swimming card
tokens and disclose incomplete TSS near the weekly chart. Verify the controls
and preview on a narrow and wide synthetic acceptance viewport.

## Outcomes & Retrospective

Calendar and protection work locally through the user-facing entry points.
The latest progress and pending CI/review gates are tracked above.
