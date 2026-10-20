# S3 M3: final load consistency and atomic build readiness (#677)

This living ExecPlan follows `.agent/PLANS.md`, the approved M1 contract in
`docs/planning_build_readiness_slice_spec.md` and M2 implementation `5aa8f6e` /
draft #706. The human explicitly authorized Domain/API M3 on 2026-10-20.
Class A: prescription validation, additive API contracts and publication semantics.
Independent read-only checking is required by repository workflow; merge owner is
human. Work occurs on codex/issue-677-s3-m3 in the existing managed worktree.

## Purpose / Big Picture

A new plan may be previewed and saved only when its future assigned sessions
contain executable instructions and all delivered loads/times agree. A technically
ready plan does not prove personal training suitability. Invalid preparation
returns 422 plan_not_ready with reasons and creates no token; invalid pending
confirmation refuses before active writes. Historical receipts replay as before.

## Progress

- [x] (2026-10-20) Verified M1/M2 handoff, branch and parent issue; role Domain/API, Class A.
- [x] (2026-10-20) Read M1 AC1–AC7, ADD3/ASR/ADR, workflow and transaction ownership.
- [x] (2026-10-20) Synthetic final-candidate probe: typical leaf loads/steps already agree; final totals currently sum rounded weeks.
- [x] (2026-10-20) Add behavioral RED for final assessor, aggregate/time/target boundaries and both-origin atomic guards.
- [x] (2026-10-20) Implement pure normalization/assessment and frozen input binding; prepare/confirm and historical compatibility.
- [x] (2026-10-20) API/TS/contracts, targeted/rollback/replay/performance tests; 117 latest focused GREEN.
- [ ] Full contributor, final lint/build and independent exact-diff verdict.
- [ ] Independent bounded review, stacked draft PR and parent evidence readback.

## Surprises & Discoveries

Observed: M2 future event-free candidate has no leaf-vs-parameter/step TSS mismatch.
Inferred: the remaining load issue is aggregate lineage/rounding, not a reason to
rewrite prescriptions. Verified by: temporary SQLite pure _calculate_plan_build
probe at identical frozen inputs; zero mismatches over the generated leaves.

Observed: _calculate_plan_build sums int weekly displays, and checkpoint builder
also derives header totals from rounded weeks. Inferred: rounding can accumulate
into a different whole-plan total. Verified by: upcoming small two-week boundary
fixture compares round(sum(raw)) with sum(round(weeks)); execution RED recorded
before replacement. No scientific dose or periodicity formula changes are needed.

Observed: apply_preview owns BEGIN IMMEDIATE and replays applied receipts before
pending eligibility. Inferred: adding bounded retained validation before insertion
can preserve transaction and replay guarantees. Verified by: existing commit,
rollback and receipt tests plus the new malicious retained-artifact controls.

## Decision Log

Use original effective leaf TSS once. Normalize new future daily rows from
sessions/legs, weekly rows by calendar date, and whole-plan total from unrounded
daily values. Weekly display remains integer; discipline display rounds each
column independently. Preserve past daily/session JSON during edit_current.
Allocated/requested/base TSS are budgets, not asserted equal to delivered TSS.
Date/author: 2026-10-20 / Domain/API, implementing M1 AC2.

Persist forecast input rows (planned and race-effort TSS separate), initial load
metrics and an input fingerprint. Build forecast from that final daily sequence;
assessor checks inputs and frozen output binding without rerunning Banister under
the writer lock. Race effort is forecast-only, never an exportable exercise or
part of weekly training totals. Date/author: 2026-10-20 / Domain/API.

Assess serialized final checkpoint snapshot, public response and frozen context.
Fingerprint excludes assessment, assigned plan ID and receipt/parameters decoration;
includes full remaining plan/response and captured parameters/context. Add readiness
policy to dependency versions. Existing v1/v2 response models keep readiness optional
only for old applied receipts; every new prepare enforces assessment server-side.
Missing old pending assessment requests fresh preview. Honest blocked assessment
returns 409; malformed/false-ready/fingerprint mismatch is 500 preview_corrupt.
Date/author: 2026-10-20 / Domain/API, implementing M1 AC5/AC6.

Assessment and forecast evidence are attached only by this build path after normal
checkpoint serialization. Other writers do not inherit a stale ready assessment:
new non-build checkpoints remain unassessed. Historical reader projects stored
assessment or explicit unassessed without database writes. No new table/backfill.
Date/author: 2026-10-20 / Domain/API.

## Context and Orientation

api/planning_service.py captures dependencies, calculates outside transactions,
then data/planning_build_preview_store.py retains and atomically applies bytes.
models/planning_checkpoints.py serializes a whitelist, so assessment is attached to
the final serialized goal_plan_snapshot in the build path. New
models/planning_build_readiness.py owns pure validation and normalization.
api/planning_build_contract.py and web/lib/types.ts mirror additive DTOs; no CSS
or UI interaction work. tests/smoke/_planning_build_confirmation.py supplies pinned
synthetic fixtures. All database paths are temporary; no athlete DB/provider calls.

## Milestones

First, add direct and public-HTTP RED tests against M2. Keep M1 four strict XFAIL
until implementation; record --runxfail failures and remove marks only on GREEN.
Exercise malformed target/unit/finite/provenance, bad composite leg and transition,
last-day inclusivity, unchanged past legacy, explicit zero/rest, rounding and
aggregate mismatches. No missing-module error is represented as a behavioral bug.

Second, implement pure final projections and readiness. Every single/leg must have
materialized status, steps, valid finite ranges/units/provenance and consistent
load/time. Composite duration equals legs plus explicit transition. Validate final
future weekly hours and declared available days; this request schema has no daily
minute-limit field, so none is invented (#668 remains separate). Historical past
assignments are not newly assessed or counted as new availability commitments.
Budget/base arrays are intentionally not effective-load assertions.

Third, integrate prepare refusal before store_pending and pending validation inside
apply_preview before active writes, after old applied replay. Validate both origins,
frozen signatures, stale/CAS/closed/expiry guards and rollback. Add no provider or
Banister call to confirm. Mirror contracts and historical unassessed read projection.

Finally run focused, contract and broad contributor checks with venv in PATH and a
writable isolated checkout. Check actual 16-week candidate, total guard latency,
reset/restore/restart and every-table snapshots. Independent checker gets exact
ref/diff and approved read-only checks; at most two rounds, second scoped delta.
Publish a draft stacked on M2 and record evidence in #677; no native/merge implied.

## Concrete Steps

From worktree root, with source venv and temporary DATABASE_PATH / DEMO_DATABASE_PATH
and CHATS_DIR, run these commands, retaining logs outside the repo:

    python -m pytest tests/smoke/test_planning_build_readiness_spec.py --runxfail -q
    python -m pytest tests/smoke/test_planning_build_readiness_m3.py -q
    npm --prefix web run contract:extract
    npm --prefix web run lint
    npm --prefix web run build
    python -m pytest tests/smoke/test_planning_build_commit.py tests/smoke/test_planning_build_preparation.py tests/smoke/test_planning_build_coach_confirmation.py -q
    python -m pytest -m "not live and not debug and not e2e" tests/ -W error::pytest.PytestReturnNotNoneWarning
    python -m ruff check .
    git diff --check

Expected outcome: new valid plans return ready and identical retained/confirmed
assessment; blocked prepare returns no token and all-table state is unchanged.
M1 XFAIL are removed once four cases are actual passing assertions. CI and native
review are separate from local author/checker evidence.

## ASR / ADR and non-goals

ASR-REL-1/2 protects complete prescription and historical identity; ASR-MOD-2/3
keeps Python-owned policy and old receipt compatibility; ASR-PERF-4 bounds pure
validation under lock; ASR-DEP-2 reuses reset/backup ownership. ADR-0001 reused.
M4 sport-specific return-to-training dose, clinical suitability, #703 thresholds,
#668 sport availability and S4 design are outside scope. Public target norms and
scientific training formulas are unchanged. Runtime work is not a main rollout.

## Idempotence and Recovery

All experiments are temporary synthetic SQLite or pure functions. Pending refusal
has no active writes; confirm transaction rolls back. Existing applied receipt is
read before new eligibility and must not republish/reopen historical cycles.
Missing historical assessment is unassessed, never backfilled by a GET. Reverting
code leaves additive JSON readable; policy/version changes stale pending artifacts.

## Outcomes & Retrospective

Implementation and targeted controls complete; final results, failures and review dispositions will be recorded in
`docs/reports/2026-10-20-planning-readiness-m3/README.md`. Do not claim personalized
training suitability or all plan mutation paths protected by this build-only slice.

Revision 2026-10-20: explicit M2→M3 handoff; materialization already repaired,
publication and final load lineage now authorized. No scope extension into UI/M4.

Implementation decisions 2026-10-20: use math.fsum at rounding boundaries; explicit
load_provenance distinguishes estimates/derived/leg sums. Known immutable catalog
policy prevents a forged RPE map using a valid policy name. Added a capped light
Recovery dose and activation NP TSS after separate behavioral RED. Original SQL
fixture timestamps were not frozen; pin synthetic inputs rather than weaken the
candidate binding. Demo fixture uses declared manual phases so the guard stays
active. See slice review matrix and report for verified evidence and remaining
unallocated pre-race activation refusals.
