# #528 compact A/B — bounded slice

Issue #528; base 5674fd5. Author Spec Owner → explicit handoff to Domain Implementer for experiment-only Python/CLI/tests. Checker independent/read-only; merge owner Greg. Class A (paid call). New milestone review: manual, spec1/2, implementation1/2 (delta accepted at5d4b42a), no native review/merge acceptance.

## Scope and Non-goals

Extend local runner with compact contract, frozen consistent fixture and paired comparison; existing baseline behavior stays compatible. Files: services/coach_runtime_eval.py, tests/evals/coach/runtime_registry.py, scripts/run_coach_runtime_eval.py, new tests/smoke/test_coach_compact_ab.py, plan/spec/report. No product prompt changes, API/TS/schema, UI, provider defaults, truncation, automatic fix, #528 closure or rollout. Earlier baseline/result not rewritten.

## Public Contracts

CLI adds --experiment baseline|compact-ab (default baseline). v2 A/B registry and report separate from v1 baseline; candidate suffix fingerprint recorded. A/B preflight returns all planned trials with 0 calls and provenance. Exit0 candidate properties pass; exit1 completed negative comparison; exit2 runtime error. Existing baseline cap24 and signatures default unchanged. New paired runner budget64, up to16 trials. Same model/settings/date and canonical DB snapshot for all trials; order AB/BA alternates by repeat, control cases after candidate freeze.

## Definition of Done

- [x] Contract propagated to model selection, synthesis and correction; no answer post-truncation.
- [x] Coherent fixture, identical A/B input snapshots, DB unchanged (offline16-trial proof).
- [x] Frozen criteria evaluated without post-result tuning: candidate failed (4/8 automatic passes,5/8 brevity), facts/tools checked and rest correct; missing-cache guarantees persist per manual rubric.
- [x] 16 trials completed;49/64calls, max4/trial,12tools/trial,1800tokens/call,45sSDKtimeout,0retries.
- [x] RED/GREEN,72focused,broad2949passed/35skipped,independent checker,live trace and manual assessment recorded.
- [x] Greg owns follow-up/merge,local worktree retained; no rollout/merge requested.

## Failure, Reset, Rollback, Idempotency

Temp canonical fixture and per-trial clones deleted at run end. Hash confirms no mutation. Unknown tools denied before callable. Output exclusive; no overwrite/network calls if file exists. Preflight errors retain planned denominator16, missing/error trials don't pass. Global budget consumed once per provider call, callbacks no network. SDK retries disabled. No new product persistence; reset deletes only report. Interrupted output may be partial, must use new filename; no implicit rerun.

## State and Evidence Boundary Matrix

| Evidence | Expected check |
| --- | --- |
| planned materialized steps | three phases, ten work repetitions, work/rest duration intact |
| cached actuals | powers128/198 and durations11:00/2:00 intact; summary coherent |
| uncached actual (known regression) | explicit gap, no invented structure or promised fetch success |
| rest day (new control) | explicit planned rest, no workout steps or false missing-data claim |
| error/empty/budget | INCONCLUSIVE with denominator preserved |
| provider selection skips tool | fails grounding even if answer matches expected words |

## RED Matrix

Contract all stages, same snapshot, coherent summary/cache, rest scenario, guarantee fail, budgets, CLI preflight16: new tests first fail then GREEN. Older15 runtime tests plus behavioral/synthetic/runtime tests characterize unchanged defaults. Named command: pytest tests/smoke/test_coach_compact_ab.py tests/smoke/test_coach_runtime_eval.py -q.

## ASR / ADR Traceability

Reuse ASR-SEC-1, REL-1/3, PERF-2 and ADR-0001/0010 from preceding local CLI boundary. No new product architecture. Critical evaluation invariant: change exactly one candidate contract; canonical fixture shared, old baseline cannot substitute new A control.

## Review Findings / Evidence Bundle

Spec accepted without blockers. Consolidated implementation delta5674fd5..5d4b42a accepted;24permittedtests and ruffpassed. Non-blocking reproduced limitation: «По плану отдых. Структура недоступна: нет данных о тренировке» can pass automatic rest predicates; manual rubric explicitly rejects false missing-data claim (not observed in actualcontrol). No production fix/automatic scorer tuning required by this limitation. 72focusedchecks,broad2949passed/35skipped. Bundle docs/reports/2026-10-13-coach-compact-ab/ containsimmutableJSON,fullpairtable,manualrubric and negativecandidateverdict. Live49calls/16trials/0errors,allinputsidenticalandDBunchanged. CI/protection/native review/merge unclaimed.

## Final Verdict

READY: bounded experiment implemented and evaluated. Candidate outcome FAIL, not recommended for production transfer. Checker blockers0. Greg owns nextscope/merge; no productacceptance/#528closure claim.
