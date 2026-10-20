# S3 M3 final load/readiness: implementation and review record

Issue [#677](https://github.com/rbctmz/ai_trainer/issues/677), M2 base `5aa8f6e`
([#706](https://github.com/rbctmz/ai_trainer/pull/706)). Date 2026-10-20.
Author: Domain/API Implementer. Independent checker: read-only exact diff, no
posting or edits. Human owns merge and cleanup. M1 AC1–AC7 remain the authority:
[approved contract](planning_build_readiness_slice_spec.md).
[ExecPlan](planning_build_readiness_m3_execplan.md),
[evidence](reports/2026-10-20-planning-readiness-m3/README.md).

## Change Class / review

Class A: persistent artifact provenance and transactional publication gate.
Manual trigger. Independent full rounds 1/2, native rounds 0; scoped delta verdict pending.
No merge acceptance or review-budget exception is implied.

## Scope / non-goals

Final build normalization, pure readiness, shared UI/Coach prepare/confirm guard,
additive DTOs and historical unassessed read projection. Recovery at larger doses
has a demonstrated missing-materialization boundary; cap a light prescription
within original load/time rather than waive the guard. Bike activation now uses
the existing NP TSS method; every new composite leg records its status.

M4 personal entry dose, clinical suitability, #703 threshold sources, #668 daily
sport availability, S4 layout/interaction and provider delivery are excluded.
Other mutation writers are not newly guarded: their new checkpoints do not inherit
build-ready provenance. Existing saved assignments/receipts remain unchanged.

## Definition of Done

- [x] Observable valid and blocked paths, both origins and all-table state checks.
- [x] Pure/HTTP, replay/rollback/CAS, target/time/load/identity/rounding/performance tests named below.
- [x] Merge/cleanup owner assigned; final broad and independent verdict still required.

## Public contract

HTTP/TS compatibly adds BuildReadiness, reasons, scope and error DTO. Successful
new builds always carry ready; old applied v1/v2 responses may omit the field.
Pydantic optional field plus response_model_exclude_unset preserves their original
HTTP shape. Pending compatibility is enforced server-side, never by a client flag.
POST registry roots include the typed error union and a real blocked manual Peak
scenario. GET PlanningOverview adds stored readiness or explicit unassessed.
No DB table/schema/config/CLI change. TS extractor artifact is regenerated.

Assessment policy: plan-build-readiness-v1. New materializer v6 makes leg status
explicit, adds bounded Recovery dose handling and derives activation bike TSS;
absolute intensity and physiological dose formulas stay unchanged.

Candidate fingerprint covers final serialized snapshot, public result and frozen
parameters/context; excludes assessment, assigned plan ID and receipt decoration.
Capture versions include readiness policy. It is an integrity/freshness binding,
not a client-supplied security signature.

## Final load/time semantics

Effective single/leg TSS must agree with parameters, steps and defined power
method. Bike FTP is derived via prescription_np_tss_v1. Run/swim/relative targets
retain catalog_budget_estimate_v1 with explicit estimated provenance, not a power
conversion. Composite load is sum_leg_tss_v1; transition contributes time only.
Daily rows sum each session/leg once. Primary day mirror is not a second session.

Future rows are projected from assignments; past edit_current rows/assignments are
preserved. Weekly summaries are grouped by calendar date, not clipped list index.
Use math.fsum and one display rounding at each final field. Total is round(sum raw
daily), not sum(integer weeks). Per-sport week displays round independently;
response weeks round to their existing integer display. Preview before/after raw
whole totals and delta use the same lineage. Budgets/base/allocated_parts are not
asserted equal to effective delivered load.

Frozen forecast_input includes exact final planned load and separate forecast-only
race TSS plus initial metrics. Response forecast binds that input by fingerprint.
Assessor validates the sequence and finite points/final TSB without recalculating
Banister under writer lock. Race days are empty export assignments, race effort is
never included again in weekly training totals.

## State, failure and compatibility

Prepare rejects blocked before store_pending/cleanup, status 422 plan_not_ready,
no token/settings/profile/cycle/ledger writes. Confirmation replays valid applied
receipts first. Pending shape/expiry/current dependencies remain guarded; missing
old readiness asks for fresh preview, honest blocked yields 409, false-ready or
malformed/fingerprint/header mismatch yields 500 preview_corrupt. The existing
BEGIN IMMEDIATE owner runs bounded pure retained checks before first active write;
all later failures roll back. No second retention/reset owner, table or backfill.
Existing reset/restart/backup tests run against the new ready artifacts.

Future assignments must have unique parent/leg identities, known immutable
catalog definitions eligible for phase/role, materialized status, no failed_bounds,
nonempty steps and complete finite target unit/range/reference semantics. RPE
matches the known versioned catalog policy, not an arbitrary self-labelled map.
Zero exercise stays exercise and is validated. Only explicit empty rest/event days
are accepted with zero load. An unallocated activation remains blocked, not silently
renamed to rest. Weekly hours/declared available days apply to the new future
prescriptions; this request schema has no per-day minute ceiling to invent.

## Boundary / RED matrix

| Boundary | Test/evidence | Expected |
| --- | --- | --- |
| M1 new/replacement prepare/confirm | four original --runxfail RED, now actual GREEN without marks | ready or explicit blocked; replay safe |
| Light Recovery dose 46.6/115 | new pure RED -> cap inside catalog | concrete recovery, <= dose/time, requested recorded |
| Bike activation | new RED requested24 vs derived12 | retain request, effective follows power |
| Bad single/leg, unknown status/kind, zero exercise | M3 mutation matrix | addressed blocker, not hidden rest |
| Missing transition / duration / primary mirror | M3 composite and day tests | exact legs + transition, primary not doubled |
| NaN, unit, range, missing reference, forged RPE policy | M3 target/immutable-definition tests | explicit semantic rejection |
| Every aggregate / forecast / whole rounding | M3 matrix + valid 16-week event | no duplicate counting or per-child tolerance growth |
| Past legacy / last-day inclusion / old applied | M3 bounds and old HTTP receipt test | no retroactive prescription upgrade or GET write |
| Stale/current, both origins, corrupt/honest blocked | S1/S2 + M3 all-table cases | no bypass or partial write |
| Large step numeric string | bounded power test | reject without allocating an arbitrary profile |

## Evidence and review bundle

Six original M1/Recovery/activation behavioral RED reproduced. Current new M3
suite and storage/preparation contour: 117 passed; earlier protocol/Coach/HTTP
contour: 172 passed; S2+M3: 89 passed at that checkpoint. Latest full regression,
contracts and review results are appended to evidence, not inferred from counts.
Original v3/v4 golden files stay byte-identical; archived M2 reproduced 6/6 before
new oracle. New oracle pins SQL source timestamps (activities.created_at,
athlete_profile.synced_at, constraints.created_at and checkpoint row time) as well
as athlete/revision clocks. Two independently built fixture sets match 6/6.
This freezes test input; production dependency timestamps remain significant.

Demo now uses a declared manual eight-week synthetic example beginning with
Recovery and no invented A event; the ordinary guard remains active. First normal
training-goal demo request had an unsupported short long-bike assignment and was
correctly blocked. Manual demo was reproduced ready; no general planner or
personal training policy was changed to make a demo pass.

ASR-REL-1/2, ASR-MOD-2/3, ASR-PERF-4, ASR-DEP-2; ADR-0001 reused. Scientific
suitability remains not_assessed. Final verdict / finding dispositions / CI / native
rounds and publication identity live in the evidence report. Human merges only
following separate current-head acceptance.
