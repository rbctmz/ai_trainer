# #528: runtime baseline — Slice Spec and Review

- Issue: https://github.com/rbctmz/ai_trainer/issues/528; bounded experiment, not issue closure.
- Author: Codex as Spec Owner, then explicit handoff below to Domain Implementer. Independent checker: separate read-only agent. Merge owner: Greg.
- Date: 2026-10-13. Candidate base: `23fd7d6ce19a93c6d07b885daf8cf298d0afa909`.
- Class A: paid AI call and new local CLI boundary. Manual review: spec 1/2, implementation 2/2 (full + scoped delta); code checker acceptance head 839febe. No exception requested.

## Scope and handoff

Spec Owner hands this bounded implementation to Domain Implementer: add an offline-tested CLI around shared Coach runtime with three synthetic scenarios, trace and limits, then a six-trial live baseline. Scope: `services/coach_runtime_eval.py`, `tests/evals/coach/runtime_registry.py`, `scripts/run_coach_runtime_eval.py`, `tests/smoke/test_coach_runtime_eval.py`, this spec, accompanying ExecPlan and report. Existing synthetic fixtures, AITools, runtime and presenter are inputs, not new business logic.

## Non-goals

Production prompts, scoring, planner, API/TS/database schema, UI, CI secrets, automatic fixes, whole #528 closure and complete coaching-safety evaluation are unchanged. SSE and API orchestration/persistence are not exercised. No new agent framework. Future expansion requires separate scope; Greg owns follow-up prioritization.

## Definition of Done

- [x] A runnable CLI records model selection, tool execution, synthesis and narrative validation on three fixtures, with development/holdout labels.
- [x] Every trial reports checks, error category, final answer and duration; aggregate denominator includes failures.
- [x] Fresh temp DB per trial; unknown/mutation tool denied before invocation; logical snapshot unchanged.
- [x] Three scenarios × two repeats; 18/24 calls, max 4 provider calls per trial, 1800 output tokens/call, 45-second SDK timeout, zero SDK retries.
- [x] Offline RED/GREEN tests (30 passed), broad smoke (2940 passed, 35 skipped), lint (green) and independent checker (gate passed) evidence recorded.
- [x] Live baseline: quality fail 2/6, zero runtime errors; immutable JSON and separate manual answer assessment recorded.
- [x] Merge/cleanup owner Greg; active local worktree retained for result; no merge requested.

## Public Contracts

API, TS, DB, SSE and production settings: unchanged. CLI added compatibly: explicit `--provider`, `--today`, `--repeats`, `--output`; live requires `--live` and selected credentials via env/`--env-file`. No implicit provider fallback. Report version and registry version pin experiment provenance, with base SHA, configured model, synthetic fixture/date, repeats, budgets, per-property metrics and results. Offline provider labelled scripted; it never counts as live quality evidence. Exit 0 all checks pass, 1 completed quality failure, 2 runtime/provider error.

## Failure, Reset, Rollback, Idempotency

Every trial starts with a new temp fixture. Output creation is exclusive: existing file aborts before model calls. Error outputs use categories, not raw exceptions. All trials remain in denominator. Provider method strings indicating errors or empty output are runtime errors, not useful answers. No SDK retry and global hard call cap. Read-only tools have max 12 executions/trial, denied calls count. Reset removes output; temp directories self-clean even on failure. No new product persistent state/cursor. CLI report ownership and removal are explicit.

## State Boundaries and Identity

Source: synthetic fixture builder on temporary SQLite, no supplied live DB path. Scenario IDs and registry version; trial identity = scenario ID + repeat number. Provider is explicit and model recorded. Date anchors are explicit; fixture plan = today - 4d, cached fact = today - 2d, uncached fact = today - 1d. No concurrent writes. Whole SQLite logical dump hash before/after proves no durable fixture change.

## Evidence Boundary Matrix

| Evidence | Route | Expected observation |
| --- | --- | --- |
| plan with steps | real get_workout_structure | required tool succeeds; short grounded plan answer |
| cached completed intervals | real get_activity_structure | required tool succeeds; 128/198 W referenced |
| activity without interval cache (holdout) | real get_activity_structure | explicit data gap, no invented interval table |
| provider missing/error/empty | no fallback | error, INCONCLUSIVE, denominator preserved |
| mutation/unknown tool | denied before execution | fail and fixture unchanged |
| correct text without required tool | no fabricated pass | tool-grounding fails |
| scripted provider | shared real tool/runtime | runner validation only, not live model quality |

## RED Matrix

| Invariant | Test/probe | RED | GREEN |
| --- | --- | --- | --- |
| complete turn with trace | offline scripted trial | new runner import absent | pending |
| wrong numeric answer fails | supplied incorrect synthesis | new runner absent | pending |
| missing data honest | absent-cache fixture | new runner absent | pending |
| denied tool has no writes | trap mutation callable | new runner absent | pending |
| provider failure cannot pass | error/empty scripted output | new runner absent | pending |
| call budget enforced | over-budget scripted provider | new runner absent | pending |
| repeat isolation/reset | independent fixtures/output exclusive | new runner absent | pending |

## ASR / ADR Traceability

ASR-SEC-1 secret handling; ASR-REL-1/3 isolation and unchanged persistence; ASR-PERF-2 duration observation only. ADR-0001 shared Python runtime; ADR-0010 A0-only tool boundary. Trade-off: four-tool restricted surface gives narrow evidence, not production-all-tools coverage. New local CLI report contract; no product contract migration.

## Delivery Slices

First slice: tests then minimal runner and registry, passing shared runtime/tool isolation probes. Second slice: CLI/limits/exclusive artifact creation tests then implementation. Final: one consolidated implementation check, scoped fixes, broad verification and bounded live baseline. No deployment or external issue/comment write required.

## Evidence Bundle

RED: new test module failed import before runner existed; subsequent wrong-response/denial/CLI tests covered actual invariants. GREEN: 30 focused eval tests, 2940 broad smoke tests passed/35 skipped, whole-tree ruff --no-cache green. Independent implementation check accepted code839febe. Live command and sanitized JSON in `docs/reports/2026-10-13-coach-runtime-eval`. Quality fail 2/6, all failures brevity; arithmetic and future-cache certainty are manual findings outside frozen predicates. CI not run remotely; acceptance/protection/merge unclaimed. Residual risk: small synthetic corpus with inconsistency, restricted tools and limited lexical/numeric predicates; human interpretation and new unseen cases required for broad quality claims.

## Review Findings

Independent spec check: blocking P2 неверные 260 Вт как факт — fixed before implementation: 128/198 Вт подтверждены BIKE_INTERVALS. Один consolidated spec round. Cheap falsifying checks for output arithmetic and unconditional cache-fetch guarantee recorded in report; no speculative production root cause asserted.

Implementation consolidated round at 51e7785: blocking P2 preflight теряет denominator/provenance — fixed-in 839febe. Scoped delta round confirmed 15 runtime tests + independent probe + ruff, no remaining blockers. Reviewer stayed read-only and made no model calls.

## Native Review Rounds

None dispatched. Independent checker: spec round 1; implementation full round 1 at 51e7785; scoped delta round 2 at 839febe. This experiment does not request native GitHub review or merge acceptance.

## Final Verdict

READY for bounded local experiment; baseline PARTIAL / automated quality fail 2/6. No remaining checker blockers. Live/API full-product acceptance and #528 completion unclaimed. Merge owner Greg; no merge requested.
