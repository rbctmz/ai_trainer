# Comparable Session Engine v1 — Class A Slice Spec

- Issue / PR: [#500](https://github.com/rbctmz/ai_trainer/issues/500); [draft PR #505](https://github.com/rbctmz/ai_trainer/pull/505)
- Author / checker / merge owner: Codex / native Codex Review / user
- Date: 2026-08-24
- Candidate head SHA: base `dbc8ccae321a9040878336fa8c4fab2c9d803953`; immutable candidate SHA is recorded after commit

## Change Class

- Class: **A**
- Rationale: a new cross-module evidence contract joins activity lineage, plan stimulus, interval structure, athlete feedback, API/web presentation, and AI-coach tools.
- Automatic escalation triggers checked: new public contract — yes; provenance/identity — yes; persistence/schema — no; provider write — no; destructive sync — no; paid call — no.
- Review budget used: 4 native Codex Review rounds (third and fourth were delayed connector reviews); one root self-review completed

## Scope

- Behavior that changes: one completed, stably matched single-activity session can expose the best eligible prior session of the same canonical sport and exact stimulus family, with transparent similarity evidence and bounded metric deltas.
- Files/modules in scope: `models/comparable_sessions.py`, `services/comparable_sessions.py`, `api/session_feedback.py`, `api/today_snapshot.py`, `models/ai_tools.py`, `models/coach_tool_presenter.py`, `web/lib/types.ts`, `web/components/today/PostWorkoutFeedbackCard.tsx`, smoke tests, contract artifact, this spec and the ExecPlan.

## Non-goals

- Behavior deliberately unchanged: canonical TSS and its cascade; plan/fact matching; provider data; historical activity rows; readiness/recovery decisions; cross-sport comparison; causal or adaptation claims.
- Deferred work and owner: aggregating split/composite activities into one physiological comparator, embeddings/ML ranking, historical backfill, and longitudinal trend inference remain unowned follow-ups until v1 evidence shows need.

## Definition of Done

- [x] Acceptance criteria are observable.
- [x] Focused, broad, Ruff, web, and contract checks are green; native review completed with an exact RED and all findings have regression fixes.
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
- Focused and broad tests: initial import RED; product-boundary RED 3 failed / 8 passed; first matrix 12 passed; review RED/GREEN rounds: 8/10→19, 4/18→22, 5/22→27, 4/27→31, targeted 2-test RED→34, targeted 3-test RED→38, targeted 2-test RED→40; smoke 2105 passed; contributor-safe 2151 passed / 4 skipped / 24 deselected.
- CI checks/reruns/flakes: full Ruff, web lint/build, contract artifact and 23 contract tests green; `fca0cfc` (sixth-review head) GitHub CI green; seventh-review head pending push.
- Lifecycle/probe evidence: temporary DB only; local athlete DB may be used read-only for a final falsifying probe without printing personal notes.
- Changed contracts: additive comparison DTO/tool/TypeScript fields.
- Unresolved review-thread count: 0 from rounds one through six; 2 from round seven pending pushed replies/resolution.
- Residual risks and follow-ups: split/composite target is deliberately a data gap; interval structure may be absent and is then labelled missing rather than fabricated.

## Review Findings

| Severity | Evidence and falsifying check | Gate | Owner/status |
| --- | --- | --- | --- |
| P2 | **Observed**: the first service draft accepted legacy `template.stimulus` when versioned `step_builder_key` was absent. **Inferred**: legacy text could create a false exact-stimulus match. **Verified by**: self-review trace and final code requiring only `definition_snapshot.step_builder_key`. | Remove name/text fallback; missing versioned stimulus is a data gap. | Codex / resolved. |
| P2 | **Observed**: the first selector counted duration and intensity incompatibility under one reason. **Inferred**: evidence would be less falsifiable. **Verified by**: separate counters/reasons and the final 12-test matrix. | Preserve dimension-specific rejection evidence. | Codex / resolved. |
| P2 | **Observed**: sport-specific provenance existed in the DTO but the initial UI/tool presenter showed only TSS/duration. **Inferred**: NP/pace acceptance would not be observable to users. **Verified by**: final coach/UI projection plus lint/build. | Render source-labelled power or pace without evaluative wording. | Codex / resolved. |
| P1 | **Observed**: split comparator matches mapped each activity independently. **Inferred**: a commute/continuation could inherit whole-session stimulus and feedback. **Verified by**: dedicated split-comparator RED. | Require exactly one actual id on comparator matches. | Codex / resolved. |
| P1 | **Observed**: historical coach targets re-read the latest checkpoint. **Inferred**: a plan rollover could erase valid immutable stimulus evidence. **Verified by**: historical-checkpoint RED. | Restore the feedback's saved match revision and referenced checkpoint. | Codex / resolved. |
| P1 | **Observed**: supplied feedback was not bound to current actual ids/revision. **Inferred**: rematched activity B could receive activity A's RPE/note. **Verified by**: superseded-feedback RED. | Require exact singleton ids and compatible match revision before attaching subjective evidence. | Codex / resolved. |
| P2 | **Observed**: run TSS does not persist `tss_pace_used`. **Inferred**: fixture-only pace evidence would not work on real runs. **Verified by**: profile-timeline and service RED/GREEN tests. | Resolve the append-only source-backed threshold snapshot known at each activity time. | Codex / resolved. |
| P2 | **Observed**: default target used feedback submission time. **Inferred**: a late note could make an old workout look latest. **Verified by**: late-feedback ordering RED. | Sort by session end/activity time, using submission/id only as tie-breakers. | Codex / resolved. |
| P2 | **Observed**: same-day candidates were rejected by date alone. **Inferred**: an earlier compatible two-a-day session was invisible. **Verified by**: 08:00 vs 18:00 RED. | Compare UTC starts on the same date and fail closed when timestamps are missing. | Codex / resolved. |
| P2 | **Observed**: web pace output omitted units and comparator threshold provenance. **Inferred**: run/swim values were ambiguous. **Verified by**: static UI contract plus build. | Render sport-specific units and both threshold sources. | Codex / resolved. |
| P2 | **Observed**: coach presenter dropped projected RPE/notes. **Inferred**: preserved subjective evidence never reached the model. **Verified by**: presenter RED. | Add bounded provenance-labelled subjective lines outside the similarity score. | Codex / resolved. |
| P2 | **Observed**: immediate prompt comparison omitted its current match revision. **Inferred**: versioned feedback could pass without proving revision compatibility. **Verified by**: second-round prompt and fail-closed feedback RED/GREEN tests. | Resolve the current immutable match revision and reject versioned feedback when compatible revision evidence is absent. | Codex / resolved locally. |
| P2 | **Observed**: constraint rebinds create multiple connected immutable match rows for one activity. **Inferred**: treating every duplicate row as ambiguity hides valid historical comparators. **Verified by**: two-revision lineage RED/GREEN test. | Collapse exactly one connected lineage, use the leaf identity, and recover stimulus through its ancestors; reject disconnected rows. | Codex / resolved locally. |
| P2 | **Observed**: Intervals and Garmin can segment the same workout differently. **Inferred**: raw cross-provider segment-count comparison can falsely reject a valid comparator. **Verified by**: cross-provider structure RED/GREEN test. | Compare structure only for equal provider sources; otherwise label the dimension missing and preserve both sources. | Codex / resolved locally. |
| P1 | **Observed**: an unmatched rebind leaf has no activity ids and was filtered before lineage resolution. **Inferred**: its matched ancestor could still be selected after explicit removal. **Verified by**: unmatched-leaf RED/GREEN service test. | Resolve effective lineage leaves before status/activity indexing; an unmatched leaf invalidates the ancestor. | Codex / resolved locally. |
| P2 | **Observed**: pace used elapsed duration although canonical moving duration exists. **Inferred**: pauses distort pace and threshold-relative intensity. **Verified by**: 60 elapsed / 40 moving / 10 km RED/GREEN fixture. | Prefer positive moving duration with elapsed fallback for run/swim pace only. | Codex / resolved locally. |
| P2 | **Observed**: a rebound feedback session id is absent from its preserved old checkpoint. **Inferred**: later coach comparison loses valid immutable stimulus. **Verified by**: rebound feedback RED/GREEN fixture. | Follow saved match ancestry and resolve the first checkpoint/session identity that contains the template. | Codex / resolved locally. |
| P2 | **Observed**: default coach selection admitted did-not-start and unknown feedback rows. **Inferred**: an unstarted item can replace the latest completed workout. **Verified by**: completion-filter RED/GREEN fixture. | Default only to completed, partial, or stopped-early feedback; explicit session lookup remains available. | Codex / resolved locally. |
| P2 | **Observed**: known target gaps still triggered candidate-history reads. **Inferred**: latency and unrelated read failures could hide the stable target reason. **Verified by**: history methods that raise after missing-stimulus evidence. | Preflight target-only evidence before feedback, intervals, matches, or candidate reads. | Codex / resolved locally. |
| P1 | **Observed**: latest feedback rows are newest-first, but the activity index overwrote each earlier assignment. **Inferred**: an obsolete RPE/note could replace a newer rebound feedback. **Verified by**: id 20 then id 10 RED/GREEN fixture. | Select by submitted timestamp, append-only id, and revision instead of iteration overwrite. | Codex / resolved locally. |
| P2 | **Observed**: latest-per-target match reads can omit an intermediate rebound revision. **Inferred**: visible endpoints look disconnected and a valid comparator becomes ambiguous. **Verified by**: ids 1 and 3 with hydrated missing id 2 RED/GREEN fixture. | Hydrate absent immutable ancestors through `get_plan_actual_match` before resolving effective leaves. | Codex / resolved locally. |
| P2 | **Observed**: local dates and UTC starts may disagree after timezone travel. **Inferred**: a later UTC activity could be accepted as historical. **Verified by**: date-line crossing RED/GREEN fixture. | Whenever both UTC starts exist, require strict UTC precedence; use local dates only as fallback. | Codex / resolved locally. |
| P2 | **Observed**: default historical lookup selected max before applying `as_of`. **Inferred**: a future workout could hide the latest eligible historical one. **Verified by**: August 1 / August 24 with August 10 bound RED/GREEN fixture. | Filter completed feedback candidates by resolved session day before max selection. | Codex / resolved locally. |
| P1 | **Observed**: ordinary provider-id and unique date/sport reconciliation does not persist ledger rows. **Inferred**: stable automatically matched sessions could disappear from comparator history. **Verified by**: a compatible prior activity with an empty ledger now resolves through one local checkpoint reconciliation. | Rebuild stable auto-match identity in memory without provider I/O or writes; explicit ledger corrections retain priority. | Codex / resolved locally. |
| P2 | **Observed**: every same-stimulus activity was enriched before duration/intensity rejection. **Inferred**: a long history caused avoidable per-activity SQLite interval reads and repeated threshold-history loads. **Verified by**: 100 duration-incompatible candidates now read intervals only for the target; run threshold history is read once per request. | Apply pure cheap gates before enrichment and cache interval/threshold reads within the request. | Codex / resolved locally. |
| P2 | **Observed**: saved auto-match feedback without a ledger revision depended on the latest active checkpoint. **Inferred**: a plan rollover could erase stimulus evidence inside the 730-day lookback. **Verified by**: a replacement latest plan plus a historical checkpoint containing the saved session now restores the threshold stimulus. | Query checkpoint history by exact immutable session id; never infer stimulus from activity names. | Codex / resolved locally. |
| P2 | **Observed**: an unmatched old lineage overrode a separate effective matched lineage for the same activity. **Inferred**: legitimate rematching could leave the activity permanently unavailable. **Verified by**: matched(A) → unmatched plus separate matched(A) now resolves to the new owner. | Apply unmatched suppression only when no effective matched lineage currently owns the activity. | Codex / resolved locally. |
| P2 | **Observed**: explicit lookup restored a tombstoned feedback's stale match revision. **Inferred**: an unmatch could still appear as a stable target comparison. **Verified by**: tombstone evidence is rejected and the endpoint revalidates current reconciliation with no subjective feedback attachment. | Treat tombstones as prompt/history state only; rebuild objective target evidence from current facts. | Codex / resolved locally. |
| P2 | **Observed**: `tss_per_hour` divided stored TSS by elapsed duration, while the canonical TSS resolver derives load from positive moving time. **Inferred**: pauses could make equivalent workouts look intensity-incompatible and remove valid comparators. **Verified by**: `test_tss_density_uses_moving_duration_with_elapsed_fallback` — two 40-moving-minute / 70-TSS runs with 40 vs 75 elapsed minutes. | Compute density from positive moving duration with the established elapsed fallback. | DeepSeek Harness / resolved locally. |
| P1 | **Observed**: the legacy auto-recovery branch restored a stimulus from revisionless auto-match feedback without checking the session's current manual ledger row. **Inferred**: after a manual S→B correction, the auto-matched A could still be selected as an exact-stimulus comparator. **Verified by**: `test_service_suppresses_legacy_auto_feedback_after_manual_rematch` — current `user_confirmed` S→B plus legacy S→A feedback. | Suppress legacy recovery whenever the current session ledger does not own the feedback's activity as its sole matched actual. | DeepSeek Harness / resolved locally. |

## Final Verdict

- Verdict: **READY after seventh-round push, thread resolution, CI, and final current-head connector review**.
- Blocking findings remaining: none in local code; publication gates remain.
- Review rounds used: 7 (five delayed/current-head connector reviews; 27 findings total).
- Accepted risk or follow-up issue: none yet.
- Merge owner final gate: user.
- Post-merge sync/branch/worktree/progress cleanup: Codex.
