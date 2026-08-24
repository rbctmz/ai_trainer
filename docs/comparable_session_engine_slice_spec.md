# Comparable Session Engine v1 — Class A Slice Spec

- Issue / PR: [#500](https://github.com/rbctmz/ai_trainer/issues/500); PR pending
- Author / checker / merge owner: Codex / native Codex Review / user
- Date: 2026-08-24
- Candidate head SHA: base `dbc8ccae321a9040878336fa8c4fab2c9d803953`; immutable candidate SHA is recorded after commit

## Change Class

- Class: **A**
- Rationale: a new cross-module evidence contract joins activity lineage, plan stimulus, interval structure, athlete feedback, API/web presentation, and AI-coach tools.
- Automatic escalation triggers checked: new public contract — yes; provenance/identity — yes; persistence/schema — no; provider write — no; destructive sync — no; paid call — no.
- Review budget used: 0 / 2 independent rounds; one root self-review completed

## Scope

- Behavior that changes: one completed, stably matched single-activity session can expose the best eligible prior session of the same canonical sport and exact stimulus family, with transparent similarity evidence and bounded metric deltas.
- Files/modules in scope: `models/comparable_sessions.py`, `services/comparable_sessions.py`, `api/session_feedback.py`, `api/today_snapshot.py`, `models/ai_tools.py`, `models/coach_tool_presenter.py`, `web/lib/types.ts`, `web/components/today/PostWorkoutFeedbackCard.tsx`, smoke tests, contract artifact, this spec and the ExecPlan.

## Non-goals

- Behavior deliberately unchanged: canonical TSS and its cascade; plan/fact matching; provider data; historical activity rows; readiness/recovery decisions; cross-sport comparison; causal or adaptation claims.
- Deferred work and owner: aggregating split/composite activities into one physiological comparator, embeddings/ML ranking, historical backfill, and longitudinal trend inference remain unowned follow-ups until v1 evidence shows need.

## Definition of Done

- [x] Acceptance criteria are observable.
- [ ] Focused, broad, Ruff, web, and contract checks are green; independent native review remains pending on the PR.
- [ ] User remains merge owner; Codex owns draft PR and post-merge sync.

## Public Contracts

- Comparable-session DTO: new versioned additive contract, `comparable_session_v1`.
- Session-feedback prompt: changed compatibly with nullable `comparison`.
- Session-feedback submit/correct result: changed compatibly with nullable `comparison`.
- AI tool registry: changed compatibly with read-only `get_comparable_session`.
- TypeScript: changed compatibly; extractor must be refreshed.
- SQLite, provider, config, CLI, plan mutation, and TSS contracts: unchanged.

## Failure, Reset, Rollback, Idempotency

- Failure modes and safe result: missing target, multiple actual activities, missing stimulus, no eligible history, materially incompatible intensity, or insufficient source fields returns a stable machine-readable `data_gap`; it never guesses or falls back across sports.
- Retry/idempotency key and duplicate behavior: projection is pure over current local facts; repeated calls return the same selected activity and ordering for identical inputs regardless of insertion order.
- Rollback procedure and proof: revert code and additive web/API fields disappear; no stored row or provider state needs migration.
- [x] Does this add **new persistent state**? No.
- [x] Does **full reset** remove every row/artifact/cursor introduced here? N/A; no runtime state is introduced.
- [x] Restart and partial-failure recovery are covered: every read is local and exceptions degrade to `data_gap` at API/coach boundaries.

## State Boundaries and Identity

- Source of truth and owner: canonical activities from `activities`; stimulus from the matched checkpoint session's `definition_snapshot.step_builder_key`; structure from local `activity_intervals`; subjective facts from the latest active session feedback.
- Stable identity/provenance keys: canonical `activity_id`, plan `session_id`, match revision/checkpoint id, comparison rule version.
- Cursor/checkpoint lifecycle: checkpoints are read-only; no cursor exists.
- Concurrency and stale-write behavior: the projection freezes one target evidence bundle per call and performs no writes, so a later sync appears only on the next call.

## RED Matrix

| Acceptance criterion / invariant | RED test or probe | Expected failure | GREEN evidence |
| --- | --- | --- | --- |
| Best match uses sport, exact stimulus, duration, structure, and intensity rather than recency. | `test_best_candidate_is_not_merely_the_newest` | No selector/DTO exists. | Older, closer candidate wins with dimension evidence. |
| Cycling prefers normalized power and uses average power only as explicit fallback. | `test_bike_metric_prefers_normalized_power_with_named_fallback` | No metric projection exists. | Metric sources are `normalized_power` and `average_power_fallback`. |
| Run/swim pace uses the activity's stored threshold, never cycling FTP. | `test_run_and_swim_pace_evidence_uses_pace_threshold_context` | No pace comparison exists. | Sport-specific units and `tss_pace_used` provenance are explicit. |
| Qualitative feedback without RPE remains labelled subjective evidence and is not scored. | `test_qualitative_feedback_survives_without_numeric_rpe` | No comparison feedback projection exists. | Verbatim bounded label is returned outside similarity score. |
| Incompatible or weak evidence is a stable data gap. | `test_incompatible_intensity_and_missing_stimulus_fail_closed` | No machine-readable result exists. | Stable reason code; no comparator or progress/decline claim. |
| Selection is independent of insertion order. | `test_selection_is_deterministic_for_any_candidate_order` | No stable ordering exists. | Same activity id, score, and explanation for all permutations. |
| Product vertical exposes one comparison to UI and coach. | API/tool/web contract tests | Prompt/tool lacks comparison. | Additive prompt DTO, read-only tool, and neutral UI evidence block. |

## ASR / ADR Traceability

- ASRs affected from `docs/architecture/asr_catalog.md`: ASR-REL-1 (activity/session identity), ASR-REL-2 (data gap instead of fabrication), ASR-MOD-2/3 (shared server-owned additive contract), ASR-PERF-2 (coach tool remains bounded/local).
- ADRs reused or required: ADR-0001 web-primary UI; existing activity-lineage and read-only coach boundaries. No new ADR because this is an additive domain service inside established layers.
- Tactic and trade-off: deterministic rule-based ranking is explainable and testable but less flexible than embeddings; exact stimulus and compatibility gates intentionally reduce recall.
- New architecture boundary discovered during review: NOT YET.

## Delivery Slices

1. Slice: pure evidence and selector.
   - RED: fixed candidate fixtures for sport/stimulus, metrics, structure, qualitative evidence, data gaps, and permutation invariance.
   - GREEN: one pure feature projection and deterministic selector.
   - Refactor/contract refresh: none.
   - Verification: focused pytest and Ruff.
2. Slice: local data service and product contracts.
   - RED: temporary-DB service/API/tool tests and static web contract.
   - GREEN: bounded local reads, prompt/submit/coach tool projection, neutral UI block.
   - Refactor/contract refresh: TypeScript extractor.
   - Verification: relevant smoke suites, web lint/build.
3. Slice: broad verification and publication.
   - RED: N/A after behavior GREEN; review probes target false matches and unsupported claims.
   - GREEN: review fixes and synchronized evidence.
   - Refactor/contract refresh: living docs and ASR catalog.
   - Verification: full smoke, contributor-safe suite, CI, native Codex Review.

## Evidence Bundle

- Head SHA: pending until commit.
- Changed invariants: only a prior same-sport/exact-stimulus compatible session can be selected; one comparison is evidence, not a trend or cause.
- Focused and broad tests: initial import RED; product-boundary RED 3 failed / 8 passed; final new matrix 12 passed; combined feedback/coach 145 passed; smoke 2075 passed / 1 skipped; contributor-safe 2121 passed / 3 skipped / 26 deselected.
- CI checks/reruns/flakes: repository Ruff clean; web lint/build green; contract artifact current and contract smoke 23 passed; GitHub CI pending.
- Lifecycle/probe evidence: temporary DB only; local athlete DB may be used read-only for a final falsifying probe without printing personal notes.
- Changed contracts: additive comparison DTO/tool/TypeScript fields.
- Unresolved review-thread count: N/A before PR/native review.
- Residual risks and follow-ups: split/composite target is deliberately a data gap; interval structure may be absent and is then labelled missing rather than fabricated.

## Review Findings

| Severity | Evidence and falsifying check | Gate | Owner/status |
| --- | --- | --- | --- |
| P2 | **Observed**: the first service draft accepted legacy `template.stimulus` when versioned `step_builder_key` was absent. **Inferred**: legacy text could create a false exact-stimulus match. **Verified by**: self-review trace and final code requiring only `definition_snapshot.step_builder_key`. | Remove name/text fallback; missing versioned stimulus is a data gap. | Codex / resolved. |
| P2 | **Observed**: the first selector counted duration and intensity incompatibility under one reason. **Inferred**: evidence would be less falsifiable. **Verified by**: separate counters/reasons and the final 12-test matrix. | Preserve dimension-specific rejection evidence. | Codex / resolved. |
| P2 | **Observed**: sport-specific provenance existed in the DTO but the initial UI/tool presenter showed only TSS/duration. **Inferred**: NP/pace acceptance would not be observable to users. **Verified by**: final coach/UI projection plus lint/build. | Render source-labelled power or pace without evaluative wording. | Codex / resolved. |

## Final Verdict

- Verdict: **READY** for draft PR and CI; independent native review remains a merge gate.
- Blocking findings remaining: none from root self-review; native review pending.
- Review rounds used: 0.
- Accepted risk or follow-up issue: none yet.
- Merge owner final gate: user.
- Post-merge sync/branch/worktree/progress cleanup: Codex.
