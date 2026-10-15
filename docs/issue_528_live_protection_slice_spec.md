# #528 M6: fresh live validation of activity protection

Date2026-10-15; basea3d0687; issuehttps://github.com/rbctmz/ai_trainer/issues/528. Greg authorized «Приступай к проверке защиты на новых ответах живой модели»: one four-turn run, global16provider calls including correction, no adaptive rerun. Class A paid experiment; Spec Owner → bounded experiment implementer after independent spec check. Independent checker read-only; Greg owns merge.

## Scope / non-goals / contracts

Reuse cache-validation runner and canonical synthetic missing1/cached1/empty1/missing2 schedule. Model deepseek-flash, tools temperature0.0/synthesis0.7,1800output tokens,thinking disabled,45sSDK timeout,0SDK retries;4calls/trial,12tools/trial. Current date/calendar must match. Allowed tools read-only; no athlete DB/sync/external activity writes. No product prompts/gate/source/API/UI/scorers/registry changes, no general-quality claim.

Only additive versioned answer_verification observation in experimental run_trial: initial text/gate metadata, correction attempted, actual correction trace indices/calls/provider time, total verification-stage elapsed time, deterministic fallback flag. Same actual evidence for initial/final gate. Raw correction responses/elapsed/usage already in provider_trace. Final narrative_gate/final_answer unchanged. Empty observation if failure before initial gate. Existing budgets include correction; no new call path. Record exact pre-run checkpoint.

## Frozen acceptance / stop

All4delivered answers semantically supported by tool data. Missing2/2: explicitly unavailable, no invented intervals/counts/actual absence; no guarantees of sync/card/requery. Future naming conditional on successful cache retrieval plus confirming tool result. Structured1/1:2intervals660/120s,128/198W retained, aggregates coherent, no invented interval. Empty1/1: analysis observation, no missing-data substitution/unsupported cause/effort/real-world absence. Check may confirm or refute a hypothesis, never guarantees confirmation.

Protocol4/4: correct selected tool/activity/date/status; formatted evidence exposed in native/synthesis; current full guardrails in all requests; same canonical input/output hashes, only allowed tools. All4planned rows retained. Errors/budget/calendar/exposure failure → INCONCLUSIVE, never hidden by fallback. Semantic assessment of every clause of initial/corrective/final output by primary and independent checker; agent assessment is not Greg human approval. Automated checks/word count diagnostic.

Report initial supportedness separately from final, actual correction calls/time and fallback count. If all initial answers supported, live rejection path is unexercised, not falsely claimed tested. Compare descriptively with M4 (3supported/4, unsupported empty guarantee), no causal/statistical claim. After one run stop regardless of outcome; no tuning/retry. Local report/career brief; push/PR/merge not authorized.

## Validation / evidence / ASR

Before edits add RED observation tests: clean pass, rejected→corrected, rejected twice→fallback, cap interruption, trace/time/redaction. Focused runtime/cache/eval/claim tests, isolated broad smoke, ruff/diff; independent spec check and bounded implementation delta, narrow repairs. Four historical live JSON byte-identical. Freeze scope/rubric/pre-run commit before paid call.

Only experimental JSON gains observation, no product contracts/state/dependencies. ASR-REL-2 unknown≠empty, REL-1/3 read-only, SEC-1 redaction, PERF-2 correction latency observation; ADR-0001 shared runtime/ADR-0010 A0. Temp clones removed on exit; output exclusive. Rollback observation code without migration, preserve evidence; no automatic live restart.

Observed: M5 offline blocks4counterexamples, preserves3supported M4answers; base runner keeps only final gate but raw response/time exists. Inferred: stage observations make first-answer quality/correction cost inspectable without changing behavior. Cheap falsifier: scripted pass/correction/fallback/cap fixtures. Verified by: RED5failed missing observation; GREEN124focused passed after repairs. Independent spec check no blockers, handoff completed. One consolidated implementation review found soft data_gap misreported as fallback and2incorrect test expectations of lexical pass; repaired with exact soft RED regression and preserving scorer. Scoped checker28passed, no remaining blockers. Whole-tree ruff/diff green. Final isolated smoke3018passed/35skipped/1existing Starlette warning,199.54s. Product/registry/CLI and4historical JSON unchanged. Pre-run checkpoint freezes this scope/rubric/code, no new live calls yet; READY for the authorized single run.
