# Planning S3 M1: Class A slice and review record

- Issue / PR: [#677](https://github.com/rbctmz/ai_trainer/issues/677) / [#705](https://github.com/rbctmz/ai_trainer/pull/705).
- Author: Spec / Architecture Owner; checker: independent read-only M1 spec checker plus native Codex; merge/cleanup owner: human.
- Date: 2026-10-20.
- Candidate head SHA: `7550d2e8a4df594ee502a359004287b341436074` (native round1 baseline). Fixing documentation commit and next reviewed SHA are pinned in the PR thread; no self-referential commit hash is asserted here.
- [ExecPlan](planning_build_readiness_execplan.md), [AC1–AC7](planning_build_readiness_slice_spec.md), [evidence](reports/2026-10-20-planning-readiness-m1/README.md).

## Change Class

- Class: A, specification for future persistent publication eligibility; the present fix is documentation-only inside this Class A slice.
- Rationale: M2/M3 will change identity/provenance, a shared API boundary and pending-confirmation eligibility; M1 defines acceptance without implementing it.
- Automatic escalation triggers checked: future cross-module contract, persistent publication semantics and identity/provenance apply. M1 adds no data migration, provider write, security boundary or destructive action.
- Review budget used: independent spec1/2 READY at `b279178`; native1/2 on `7550d2e`, three P2, documentation fixes awaiting scoped round2.
- Review trigger mode: manual.
- Review acceptance head SHA: N/A — owner has not accepted a native result for this M1 PR. Earlier independent READY is only a spec-checker result, not native/merge acceptance.
- Review budget exception: N/A; do not request a third full native round.

## Scope

M1 adds the future readiness contract, synthetic probes and four strict XFAIL acceptance assertions. Native fixes add this instantiated record, portable commands and accurate wording of executed evidence. No runtime behavior changes.

Files: `docs/planning_build_readiness_slice_spec.md`, `docs/planning_build_readiness_execplan.md`, this record, M1 report/probe, ASR planned entry and `tests/smoke/test_planning_build_readiness_spec.py`. The native fix changes docs only.

## Non-goals

No runtime guard, catalog repair, RPE policy implementation, load normalization, new HTTP/TS schema, personal dose/medical suitability, UI change, provider operation or live database write in M1. Domain/API owns M2 catalog semantics and M3 consistency/guard; Spec owns M4 entry-dose rationale; UI/Design owns S4 after the shared DTO.

## Definition of Done

- [x] Observable future AC1–AC7 and M1 spec-only boundary are explicit.
- [x] Four current AssertionError RED and existing focused characterization/check commands are named; they are not implementation GREEN.
- [x] Human merge/cleanup owner assigned; native verification/acceptance remain separate gates.

## Public Contracts

| Surface | M1 classification | Future handoff / check |
| --- | --- | --- |
| HTTP API and error envelope | unchanged | M3 proposes additive readiness/error fields; API/TS tests and extractor together |
| TypeScript | unchanged | M3 mirrors schemas; no browser policy |
| Database / persistent events | unchanged | proposed snapshot field reuses existing retention/transaction; no new table/backfill |
| Configuration / CLI | unchanged | PYTHON in portable experiment commands is a caller interpreter override, not product config |
| User-visible UI / provider | unchanged | safe error detail via existing envelope; detailed UI belongs to S4 |
| Scientific / personal suitability | unchanged | not assessed; M4 separately defines entry-dose acceptance |

The proposed M3 contract is compatible/additive, with old applied receipts preserved. It is a proposal in M1, not an implemented public-schema claim.

## Failure, Reset, Rollback, Idempotency

Failure of a probe/assertion does not modify product state. Each experiment uses TemporaryDirectory/pytest tmp_path and local monkeypatch clocks. No usable product mutation is introduced by this docs/test slice. Existing public API is invoked only on synthetic temporary SQLite.

Retry creates a new temporary fixture; there is no new runtime idempotency key. Removing M1 files reverts the slice; no working DB restore is required. Future M3 preserves the existing preview token/receipt transaction owner and applied replay.

- [x] New persistent state: no in M1; future assessment reuses snapshot ownership, no second ledger.
- [x] Full reset: N/A for new product rows because none are introduced; TemporaryDirectory owns experiment cleanup.
- [x] Restart/partial failure: M1 experiments terminate without live writes; runtime reset/replay/rollback verification is explicitly deferred to M3, not claimed as executed here.

## State Boundaries and Identity

M1 source of truth is the spec plus recorded synthetic evidence. Proposed runtime owner is shared Python over final serialized candidate; UI/Coach consume it. Candidate fingerprint/policy version must bind final assignments and aggregates; new keys are not implemented by this slice. Past assignments/applied receipts remain historical. Future eligibility must preserve existing scope/CAS/freshness guards. No cursor/checkpoint mutation is added in M1.

## Evidence Boundary Matrix

| Identity / origin | Time | Evidence | Fallback | M1 execution / future expectation |
| --- | --- | --- | --- | --- |
| new / replacing cycle | future | incomplete instructions present | current API accepts | two prepare AssertionError RED; future prepare rejects or returns fully executable assignments |
| retained pending | future | 23 invalid prescriptions | current API publishes | two confirm AssertionError RED at the invalid-publication assertion; valid branch is not reached |
| genuine executable control | future | complete | no hidden fallback | deferred M2/M3; M1 does not claim ready/replay acceptance coverage |
| historical assignment / old applied receipt | past / old policy | missing assessment | unassessed / preserved replay | proposed compatibility only; future M3 tests required |
| bike / run / swim | Base vs Recovery | equal thresholds and dose | Recovery produces no steps | pure paired probe; catalog semantics handed to M2 |
| composite parent / legs | same date | explicit transition5min | allowed | pure control70+30+5=105; no false duration blocker |

## RED Matrix

| Acceptance / invariant | RED / characterization | Expected failure | GREEN status |
| --- | --- | --- | --- |
| new/replacement assignments | two public prepare assertions | returned success contains invalid instructions | NOT YET in M1; strict XFAIL |
| server publication refusal | two public confirm assertions | HTTP200 with23 invalid prescriptions instead of409 | NOT YET in M1; strict XFAIL; no valid-plan/replay branch reached |
| ready path / retry | planned acceptance branch only | not executed by these invalid fixtures | deferred M2/M3; existing S1/S2 replay tests are separate characterization |
| target/load/time semantics | bounded pure probes | Recovery/sprint/RPE observations, legal composite control | observations recorded; no runtime repair claimed |
| compatibility / all-table reset | proposed AC6 and coverage handoff | not executed as new behavior in M1 | deferred M3, not an M1 pass |

Normal M1 acceptance module yields4 XFAIL; `--runxfail` yields4 AssertionError failures. Existing focused128 passes are regression baseline, not GREEN for the new invariants. The separate baseline probe can replay an **invalid** published candidate; that observation does not prove the proposed ready-plan path.

## ASR / ADR Traceability

ASR-REL-1/2, ASR-MOD-2/3, ASR-PERF-4 and ASR-DEP-2; ADR-0001 reused. Tactic: one shared Python assessment over a frozen final artifact, bounded pending validation before existing writes. Trade-off: rollout needs executable valid candidates as well as refusal. No new architecture boundary was introduced by these native documentation fixes.

## Delivery Slices

M1 is spec/evidence only: current observable RED, strict XFAIL and existing characterization. M2 implements catalog/target semantics; M3 implements final consistency/guard and complementary valid/invalid/compatibility tests. M4 and S4 remain deferred owners. Each future runtime slice needs its own current-head validation; this record cannot certify it.

## Evidence Bundle

- Head SHA: native baseline `7550d2e8a4df594ee502a359004287b341436074`; source/evidence independent spec head `b279178` recorded in M1 report.
- Changed invariants: none in M1 runtime; AC1–AC7 are proposed implementation acceptance.
- Focused tests: original128 passed plus4 strict XFAIL; native-fix rerun recorded in report/PR thread.
- Broad CI: original candidate contributor, web-contract and E2E checks SUCCESS on GitHub; Review gate awaits accepted native result. Do not substitute this for future runtime GREEN.
- Lifecycle probe: synthetic invalid publication17 fallback+6 infeasible and invalid receipt replay; no live DB/provider data.
- Contracts: unchanged in M1, additive proposal only.
- Unresolved review threads: three native P2 at baseline; author fixes posted with SHA and each resolved only after verification. Scoped native round2 pending at this record.
- Residual risks: valid plan/replay, bad leg/transition, rounding, future-boundary, all-table/reset and performance acceptance remain M2/M3 work; personal suitability remains unassessed.

## Review Findings

| Severity | Observed / Inferred / Verified by | Gate / disposition |
| --- | --- | --- |
| P2 | Required Class A fields absent as one instantiated template. Search for candidate head/acceptance/contract/reset fields found scattered prose only. | Blocking documentation defect; this record fills every template section and links from spec/ExecPlan. |
| P2 | Concrete Steps pinned `/Users/...` interpreter, absent on other checkouts. The shell assignment itself selects a nonexistent author path. | Blocking portability defect; activated interpreter or caller PYTHON override is used, default python is checked. |
| P2 | Invalid confirm fixtures fail before ready/replay branch; source branch plus `--runxfail` demonstrate23 invalid prescriptions. | Blocking evidence overclaim; matrix now says invalid-publication only; valid control/replay explicitly deferred. |

No domain acceptance or test expectation was rewritten to dispose these findings.

## Native Review Rounds

| Round | Reviewed head SHA | Trigger | Findings | Stop decision |
| --- | --- | --- | --- | --- |
| 1 | `7550d2e8a4df594ee502a359004287b341436074` | manual, [request](https://github.com/rbctmz/ai_trainer/pull/705#issuecomment-6291368773) |3 documentation P2; fixes/evidence in current PR delta | one scoped verification allowed |
| 2 | pending; exact fixing SHA/result recorded in PR thread | scoped delta only | pending | stop after round2; owner gate remains |

## Final Verdict

Current native verdict: BLOCK at original candidate, fixes awaiting verification. Independent spec READY atb279178 is historical checker evidence, not a clean native result. Three original P2 have concrete documentation fixes; their `fixed-in` SHA/check results and subsequent native verdict belong to the PR thread. No human acceptance or merge is asserted. Human owns final review acceptance, CI/threads, merge, post-merge metric record and worktree cleanup; no force push or automatic history rewrite is authorized by this record.
