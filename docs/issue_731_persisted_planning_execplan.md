# Finish the persisted Planning revision handoff (#731 / #733)

This living ExecPlan follows `.agent/PLANS.md`. Keep Progress, Surprises &
Discoveries, Decision Log, and Outcomes & Retrospective current. The owner
handed implementation from the stopped ZCode agent to Codex on 2026-10-26.

## Purpose / Big Picture

Planning must display the selected saved readiness/load capture consistently:
the load numbers, their interpretation, readiness evidence, and revision dates
must agree even when activities change before the next capture. A capture is
an immutable readiness row recorded after a sync. This work finishes the
scoped fixes from `7abe865`; it does not complete all of #731.

## Progress

- [x] 2026-10-26: read the shared ZCode handoff and inspect the clean branch.
  Inherited unpublished commits `a84282e` and `4e97b61`; no source changes lost.
- [x] Verify inherited baseline: 50 targeted tests passed on an archived source
  tree with synthetic data, temporary HOME and cleared environment.
- [x] RED: extend the three-phase HTTP probe to validate PlanningStatus and
  captured readiness drivers. Inherited HEAD fails on missing computed_at/reason.
- [x] Preserve the captured public snapshot, reuse canonical readiness
  projection, and mirror additive metrics provenance in TypeScript/extraction.
- [ ] Finish isolated focused/broad checks, web lint/build, and final replay.
- [ ] Push the inherited and completion commits to the existing PR #733;
  update the PR evidence and classification without closing #731/#660.
- [ ] Independent scoped checker and human merge decision remain external gates.

## Context and Orientation

The branch is `claude/issue-731-20261025-1930`. Remote PR #733 initially points
to `7abe865`; local work already contains `a84282e` (chronological day selection)
and `4e97b61` (consistent Planning load interpretation and provenance).
`data/database.py::get_latest_readiness_snapshot` reads the append-only journal.
Its revision counter belongs to `readiness:<capture_mode>:<local_date>`, so
revision numbers from different dates are not globally comparable.

`models/load_metrics.py` selects a prospective row on/before the athlete date
and extracts its saved CTL/ATL/TSB. CTL and ATL are the long/short load averages;
TSB is their difference. `api/planning_service.py::current_status` assembles the
response. `models/signals_engine.py::apply_persisted_load_revision` updates
TSB-dependent labels, state and recommendations, preserving the separate ACWR
history policy. ACWR is the short/long load ratio and is not redefined here.

The journal row contains a `snapshot` object with the original public readiness
response. Returning the database row itself loses fields required by
`web/lib/types.ts::ReadinessSnapshot`, including computed_at and reason, and
leaves captured freshness/intervention evidence nested inside snapshot.

## Plan of Work

Retain both inherited commits. Restore the original captured public shape in
`services/readiness_snapshot.py::project_persisted_readiness_snapshot`: start
from stored snapshot JSON, overlay the saved columns and selected identity, and
use only saved columns for legacy rows without snapshot JSON. Never recompute
historical recovery measurements while projecting a row.

In Planning, project captured readiness through the existing
`models/dashboard_summary.py::project_readiness_snapshot` helper before applying
the inherited TSB projection. This aligns score and drivers with the selected
capture while preserving live HRV diagnostics and ACWR as explicitly separate
signals. Mirror metrics source/date/id/revision/capture_mode in
`web/lib/types.ts`, retaining the existing ReadinessSnapshot required shape,
then regenerate `tests/contracts/ts_contract.json`.

Keep #616 separate. Dashboard/Today migration, A2 provider comparison, threshold
changes, UI layout, sync writes and merge are outside this handoff. In
particular, do not claim cross-screen equality after only fixing Planning.

## Concrete Steps

Use an archived source tree under a task-specific temporary directory. Clear
the environment with env -i, set temporary HOME, TMPDIR, DATABASE_PATH,
DEMO_DATABASE_PATH and CHATS_DIR, and run Python from ai_trainer_env. Do not run
tests against personal databases or load .env from the runtime checkout.

    python -m pytest -p no:cacheprovider tests/smoke/test_load_metrics_canonical.py tests/smoke/test_api_planning.py tests/smoke/test_dashboard_metrics_anchor.py tests/smoke/test_web_contract_drift.py -q
    python -m pytest -p no:cacheprovider -m "not live and not debug and not e2e" tests/ -q -W error::pytest.PytestReturnNotNoneWarning
    python -m ruff check --no-cache .
    npm --prefix web run contract:extract
    npm --prefix web run contract:extract -- --check
    npm --prefix web run lint
    npm --prefix web run build

Preserve the real Git author/commits, merge current main without rewriting
history if required, push the same PR branch, and verify the remote head and CI.
No review-accepted/ready label or merge is authorized by this handoff.

## Validation and Acceptance

The multidate probe records three captures yesterday and one today, and selects
today's revision 1 rather than yesterday's revision 3. The boundary probe reads
91 daily activities via the inclusive legacy reader and 90 through the shared
reader; all live load tools must agree on the canonical series.

The HTTP probe verifies three phases: immediately after capture, after a 300 TSS
synthetic same-day activity without capture, and after a new capture. During
the middle phase all selected TSB numbers/labels/readiness drivers stay captured;
after the new capture they all change together. The response validates against
the extracted TypeScript PlanningStatus and retains captured freshness and
intervention fields. Fresh installs keep live fallback before first capture.

Also check capture-mode/date exclusion, repeated read immutability, and legacy
stored rows without snapshot JSON. No schema, migration, new stored state or
provider operation is introduced. Independent review is scoped to the delta
after `7abe865`, not another full-diff scan.

## Surprises & Discoveries

Observed: inherited `4e97b61` passes 50 tests but returns the database row as
readiness_snapshot. Inferred: shallow number-only tests miss public shape and
captured-driver drift. Verified by: the extended HTTP test fails validation on
computed_at and reason before the completion changes.

Observed: one initial completion verification used the runtime checkout as cwd
despite temporary database paths. This could load .env; that run is excluded
from isolated verification evidence. Repeat from the archived temporary cwd
with cleared environment. No personal database path was supplied to the tests.

## Decision Log

Decision: treat the persisted/provenance slice as Class A under the automatic
provenance/public-contract triggers. The initial extraction was Class B; this
classification correction records scope already introduced by prior commits,
not a new feature. Date/author: 2026-10-26, Codex applying repository workflow.

Decision: reuse canonical readiness presentation instead of creating a second
readiness scale. Preserve the capture's timestamp and evidence. Date/author:
2026-10-26, Codex, within the owner's request to finish both audit fixes.

## Idempotence and Recovery

All product changes are reads/projections. Capture rows, schema and fingerprints
are unchanged. Repeated reads must not append records. Revert the completion
commit to undo its contract/projection changes; retain the inherited history.
Tests create only synthetic temporary data. Do not stop services, modify runtime
configuration, restore user databases or call provider APIs.

## Interfaces and Dependencies

Use existing pandas/Banister, SQLite readers, readiness presentation and contract
extractor. PlanningLoadMetrics adds source (live/persisted), as_of,
observed_at_utc, snapshot_id, revision and capture_mode. PlanningReadinessSnapshot
extends the existing readiness contract with optional capture identity and TSB.
No new dependency is needed. ASR-REL-2 and ASR-MOD-2/3, ADR-0001 and ADR-0003 apply.

## Outcomes & Retrospective

Implementation verification and publication are in progress. A2, real-screen
acceptance, cross-screen persisted migration, independent checker and owner
merge are not claimed complete. The companion slice spec records findings and
final validation evidence.

Revision note (2026-10-26): reconstructed the bounded execution plan from the
stopped agent's committed work and the owner's handoff before final delivery.
