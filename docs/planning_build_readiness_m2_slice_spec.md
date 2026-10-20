# S3 M2 prescription generation and RPE: slice and review record

Issue [#677](https://github.com/rbctmz/ai_trainer/issues/677); stacked on M1
[#705](https://github.com/rbctmz/ai_trainer/pull/705), base `7550d2e`.
Date: 2026-10-20. Author: Domain/API Implementer. Checker: independent read-only
`s3_m2_checker`; merge/cleanup owner: human, merge requires separate acceptance.
[ExecPlan](planning_build_readiness_m2_execplan.md),
[M1 acceptance contract](planning_build_readiness_slice_spec.md),
[evidence](reports/2026-10-20-planning-readiness-m2/README.md).

## Change Class

Class A: versioned prescription/provenance and cross-module role projection.
Automatic escalation: identity/provenance. Manual review; round 1/2 examined
`7550d2e..5f15c87`, code READY, overall pending broad verification. Round 2 is a
scoped test/fixture/evidence delta, not another runtime full-diff review.
Native round 1 on 5aa8f6e found three P2 defects, now reproduced and corrected
(raw RPE shape/duplicates, legacy stage identity, fallback quantization). Round 2
will verify only this delta after stable CI. No exception or human merge
acceptance is implied.

## Scope and non-goals

Generation portion of M1 AC1/AC4: light Recovery prescriptions, feasible reused
candidates, explicit bounded quality-to-easy fallback in Base/Build/Maintenance,
no easy-to-sprints assignment, direct versioned per-stage RPE. Files:
`models/workout_catalog.py`, role projections in `models/training_planner.py`,
focused/regression tests and versioned synthetic oracle. M3 owns aggregate load
consistency and final publication guards; M4 owns personal entry dose. UI/S4,
threshold-source changes #703, sport availability #668 and provider delivery are
out of scope. No claim that all generated event/manual plans are publishable.

## Definition of Done

- [x] Recovery, fallback dose/time, role and RPE criteria observable below.
- [x] Targeted RED and GREEN, pure/public temp-SQLite probes, Ruff and broad suite named in ExecPlan.
- [x] Human merge/cleanup owner assigned; independent delta verdict and final evidence required before publication.

## Public contracts

API/TS/schema/config/CLI unchanged. Existing open dictionary definition/target
provenance payloads change compatibly with catalog/selector/materializer version
bumps v4/v2/v5 and incremented definition versions. New assignments carry actual
role plus requested/effective role evidence; RPE scale/type/unit unchanged,
`catalog-rpe-v1` and stage map explicitly persisted. No migration or TS extractor
regeneration is needed. Runtime provider syntax remains covered by existing tests.

## Failure, reset, rollback and identity

No candidate, impossible dose or missing/invalid RPE policy remains explicit
fallback/infeasible, never guessed success. Catalog bounds are unchanged.
No persistent tables/state/reset ownership introduced (N/A). Existing checkpoint,
preview store and receipt lifecycle owns retention/reset. Pending artifacts from
old versions fail existing freshness; applied receipts replay unchanged without
recapture/republication. Historical snapshots restore without rematerialization.
Undo code does not rewrite saved assignments; a new plan still needs explicit
prepare/confirm. Session identities/fingerprints continue through existing helpers.

## Evidence boundary matrix

| Identity / time | Evidence | Fallback | Expected / falsifier |
| --- | --- | --- | --- |
| New Recovery, all 3 sports, easy/quality/long | thresholds present / missing | light only | concrete steps and actual recovery role, no intense definition |
| New Base/Build/Maintenance quality | fresh infeasible, used feasible | requested role first | reused executable wins before downgrade |
| New low-dose quality | no executable requested pair | explicit light | time <= estimate and shortest failed pair; effective TSS <= requested |
| Peak/Taper/Race Week or impossible load | no valid requested prescription | fail closed | no quality-to-easy intent replacement |
| New relative targets | valid / missing / incomplete / invalid stage policy | explicit RPE / fail closed | all stages defined on application 1–10 scale; no fraction conversion |
| New absolute targets | valid FTP/pace/HR provenance | existing target behavior | catalog/density/provider syntax regression unchanged |
| Historical assignment / receipt | prior catalog context | no upgrade | stored JSON/receipt unchanged |
| Pending preview | prior version context | refuse stale | no active checkpoint/profile mutation |

## RED / GREEN and delivery

48 initial targeted cases: 45 failed / 3 passed; some RED assert absent fields,
not 45 independent defects. 128 focused GREEN after code repair; 10 later boundary
cases cover shortest-pair cap, three changed version contexts x pending/receipt,
and invalid RPE maps. Existing hour-limit and taper intent checks retained.
Historical #554 fail-closed fixtures use Peak (where light fallback is forbidden);
historical rebalance constructs the old easy-labelled sprint assignment explicitly
so all original effective-load assertions remain. Easy replan now expects a real
endurance session. No bound/ceiling assertion is relaxed.

Before replacing any oracle, archived M1 source reproduced all six old hash cases
exactly. Original JSON remains unchanged. A separate catalog-v4 oracle compares
all fields, not TSS-only; load, forecast and science outputs change with the
prescriptions, events do not. Detailed totals and remaining invalid event-overlay
cases are in evidence. Runtime implementation is commit `5f15c87`; regression,
compatibility and evidence delta is the second delivery checkpoint.

## ASR / ADR

ASR-REL-1/2: immutable history and explicit refusal; ASR-MOD-2/3: shared Python,
versioned provenance, open DTOs; ASR-PERF-4: bounded retries / 16-week probe.
Reuse ADR-0001; no new architecture boundary. Trade-off: conservative light
replacement can lower delivered load and requires honest subsequent aggregates
(M3); readiness is not personalized training suitability (M4).

## Findings, verdict and evidence

Round 1 on `5f15c87`: zero confirmed P1/blocking P2, 128 focused passed, 2,268
quality requests independently examined, 84 bounded explicit fallbacks, no cap,
phase, role or family violations. P3 report-probe E401 fixed in regression delta.
Broad verification and scoped round-2 result are recorded in the evidence report;
this paragraph does not substitute for them. Native review, human acceptance,
merge, deployed/browser acceptance and live plan migration are not claimed.
