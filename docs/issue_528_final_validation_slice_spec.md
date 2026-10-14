# #528 M4: final live validation of cache conditions

- Date:2026-10-15; base:dcc6e66; issue:https://github.com/rbctmz/ai_trainer/issues/528.
- Roles: Spec Owner → Domain Implementer after bounded spec check; independent read-only checker; Greg owns merge.
- Class A (explicit paid experiment), manual review; one spec check/one implementation delta before run. User «Отлично! Делай» accepts4trials/max16calls and completion/reporting. No push/PR/merge authorized.

## Scope / Non-goals

Add `cache-validation` mode to the existing CLI/runner with its own versioned registry/fixture/report and offline boundary tests. Exactly4turns using production prompts including M3: missing-cache twice, actual cached intervals once, analyzed-empty once. One canonical synthetic DB, cloned via SQLite backup for every trial.

No product prompt/source/gate/schema/UI/sync changes. No score changes to old registries or reinterpretation of immutable traces. No new integrations, broad agent infrastructure, adaptive tuning or rerun until green. Prepare a local review brief and bounded engineering case if the frozen criteria pass; no external publishing.

## Frozen Acceptance / Definition of Done

- Fixed schedule:missing1,cached1,empty1,missing2. Missing run=today−1; cached bike=today−2; analyzed-empty run=today−3. Canonical contains all3states so every input DB hash is identical.
- Missing2/2: explicitly unavailable structure, never actual absence of intervals; no invented intervals; no promise of sync/card/requery success; any naming of future intervals is conditional on successful cache retrieval confirmed by a new tool result.
- Cached1/1: actual128/198W and11/2min intervals preserved, no substituted plan/generic structure, no fabricated third interval or claims of unavailable structure.
- Empty1/1: acknowledge analyzed-empty, not unavailable/missing-cache; no invented interval structure or inference that the workout was necessarily easy/uniform.
- Protocol4/4: actual model selected get_activity_structure for expected activity/date; actual raw state/identity matches; matching formatted evidence reaches native and synthesis contexts; M3 policy reaches every model request; all DB inputs identical/unchanged and allowed read-only tools only.
- Errors, budget/calendar changes, missing exposure → INCONCLUSIVE; all4planned rows retained. Semantic review of every answer required; lexical checks diagnostic only. Word count≤80 is diagnostic, not truthfulness blocker. Immutable JSON pending_manual; primary and independent agent assessment attributed separately, Greg human review not claimed.
- DeepSeek/deepseek-flash, compact_answer_v1 identical across trials, tools temperature0.0, synthesis0.7,thinking disabled. Global16calls,4/trial,12tool executions/trial,1800output tokens,45sSDK timeout,0retries. Existing baseline24/compact64/source16budgets unchanged.
- [x] RED→GREEN for schedule, real tool state/exposure, normalization, caps/denominator/preflight/exclusive output and diagnostic length.
- [x] Focused/isolated broad tests, lint, self-review and independent checker; code/rubric included in pre-run checkpoint.
- [ ] Immutable trace and all4semantic assessments; checkpoint/decision. Pass → local review brief/career case; fail → retain negative result, separately scope evidence-based answer validation. No silent prompt tuning.

## Contracts / State / Failure / Reset

CLI compatible new experiment enum; own report namespace coach_cache_conditions_validation_v1. API/TS/DB/config contracts unchanged, no extractor/migration. Fixture adds only synthetic analyzed-empty row/cache in temp DB, normalized before clones; no product persistent state. Stable activity IDs/date/state captured in rows. Logical hash before/after verified, unknown/mutation tools denied before callable.

Output open-exclusive; no overwrite, SDK retries0, errors retain exception type only. Selected AI credentials loaded/sanitized only, no athlete DB/clients. Temp DB/clones cleaned on exit. Rollback experiment code without undoing M3; report evidence stays. Partial failure retains all4denominator, never automatic live restart.

## Evidence Boundary Matrix / RED Matrix

| Identity/provenance | Evidence | Expected result / falsifier |
| --- | --- | --- |
| linked run, past date | missing cache | unavailable/not_fetched; unknown is not empty |
| cached bike, past date |2actual intervals| structured128/198W,660/120s; actual summary totals coherent |
| cached run, past date | analyzed timestamp + empty intervals | empty; no missing-data substitute |
| wrong tool/activity/date or missing delivery | insufficient exposure | protocol invalid, no claim of rule compliance |
| provider/preflight/calendar/budget failure | incomplete attempt |4rows retained; finite calls; INCONCLUSIVE |

| Invariant | RED / characterization | GREEN evidence |
| --- | --- | --- |
| Exactly4fixed trials with actual3states | new runner/CLI regression, RED missing interface | GREEN |
| Missing-vs-empty recognition / cached facts | actual tools + scripted response diagnostics | GREEN |
| Cap16/full denominator/exclusive output/preflight | budget/failure/CLI regression | GREEN |
| Policy and actual tool state in both contexts | captured real runtime requests | GREEN |
| Existing modes/reports unchanged | old focused suites/byte comparison | GREEN |

## ASR / ADR / Evidence Bundle / Verdict

ASR-REL-2 (unknown≠empty), ASR-REL-1/3 (read-only), ASR-SEC-1 (synthetic/redaction), ADR-0001 (shared Python) and ADR-0010 (A0). Same runtime, not API/SSE/live athlete acceptance; small regression/control sample, not general Coach quality or causal proof. Original compact_candidate was rejected as product feature; compact format here remains an experimental constant.

Independent spec check: no blockers; handoff Spec Owner → Domain Implementer. RED: new test module fails to collect because run_cache_validation interface absent. GREEN:124focused tests passed across new/old eval, shared runtime and real tool/fetch suites, whole-tree lint/diff green. Independent implementation delta againstdcc6e66:39passed, lint/diff passed, no blockers, status unchanged before/after. One spec and one delta review, no native GitHub review. All3historical live traces byte-identical todcc6e66. Broad on separate temp DB/chats:2971passed/35skipped/1existing Starlette deprecation warning,198.01s. Skips:22TypeScript dependency,10explicit fixture regeneration,2historical pilot/process,1socket environment checks. No web/API changes. READY for the already-authorized finite run; no paid calls yet, no model-quality or merge verdict.
