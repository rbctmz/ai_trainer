# Deliver a deterministic comparable-session engine (#500)

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

This document must be maintained in accordance with `.agent/PLANS.md`.

## Purpose / Big Picture

After this change, post-workout feedback can show one prior session that is genuinely comparable to the completed session rather than merely recent. The system will require the same canonical sport and exact planned stimulus, rank eligible candidates by duration, overall intensity, and recorded interval structure, and expose the evidence behind the choice. Cycling evidence prefers normalized power; running and swimming use source-backed pace with the threshold stored on each activity. When facts are weak or incompatible, the API and coach receive a stable data gap and cannot turn a single comparison into a trend or causal adaptation claim.

## Progress

- [x] (2026-08-24) Re-queried issue #500, confirmed no open PR or remote issue branch, removed the stale automation `blocked` label, and set `status: in progress`.
- [x] (2026-08-24) Confirmed publish access with `gh auth setup-git` and `git ls-remote --heads origin`; created `codex/issue-500-comparable-session-engine` from `dbc8cca`.
- [x] (2026-08-24) Read the workflow, PLANS, ASR/ADD documents, ADR-0001, slice template, and current activity/feedback/coach contracts.
- [x] (2026-08-24) Completed the cheap falsifying check: repository search and current evidence-gate tests show no comparable-session DTO or selector; session comparison claims remain a comparator data gap.
- [x] (2026-08-24) Fixed the Class A slice contract and RED matrix.
- [x] (2026-08-24) Captured initial import RED, then product-boundary RED of 3 failed / 8 passed.
- [x] (2026-08-24) Implemented the pure model and bounded local projection; final new matrix is 12 passed.
- [x] (2026-08-24) Integrated additive feedback, coach-tool, presenter, TypeScript, and neutral web contracts.
- [x] (2026-08-24) Completed root self-review and local CI: combined focused 145 passed; smoke 2075 passed / 1 skipped; contributor-safe 2121 passed / 3 skipped / 26 deselected; Ruff, web lint/build, contract check, and 23 contract smoke tests green.
- [x] (2026-08-24) Committed implementation as `aac0ff1`, pushed the issue branch, and opened draft PR #505 with `Closes #500`.
- [x] (2026-08-24) Posted the pushed SHA/evidence to #500; GitHub CI completed green and the PR moved to Ready for review.
- [x] (2026-08-24) Native Codex Review reported 8 findings (3 P1, 5 P2); captured an exact RED of 8 failed / 10 passed and fixed every finding with regression coverage.
- [x] (2026-08-24) Re-verified the review slice: 19 comparable-session tests, 76 focused tests, smoke 2083 passed / 1 skipped, contributor-safe 2129 passed / 3 skipped / 26 deselected, Ruff, web lint/build, contract freshness, and 23 contract tests green.
- [x] (2026-08-24) Pushed `fa97bdc`, replied to and resolved all 8 first-round threads, and confirmed GitHub CI green on that head.
- [x] (2026-08-24) Second native Codex Review reported 3 P2 findings; captured an exact RED of 4 failed / 18 passed and fixed all three with regression coverage (22 passed).
- [x] (2026-08-24) Completed second-round local verification: 22 comparable-session tests, 95 focused tests, smoke 2086 passed / 1 skipped, contributor-safe 2132 passed / 3 skipped / 26 deselected, targeted Ruff, web lint/build, contract freshness, and 23 contract tests green.
- [x] (2026-08-24) Pushed `11c4b78`, replied to and resolved all 3 second-round threads, and confirmed every GitHub CI check green.
- [x] (2026-08-24) A docs-only outcome push triggered an unplanned third native review with 5 fresh findings (1 P1, 4 P2); captured the exact RED of 5 failed / 22 passed and fixed all findings with a 27-test GREEN and 100 focused tests.
- [x] (2026-08-24) Completed third-round verification: 27 comparable-session tests, 100 focused tests, smoke 2091 passed / 1 skipped, contributor-safe 2137 passed / 3 skipped / 26 deselected, full Ruff, web lint/build, contract freshness, and 23 contract tests green.
- [x] (2026-08-24) Pushed `02edf32`, replied to and resolved all 5 third-round threads, and confirmed GitHub CI green on that head.
- [x] (2026-08-24) A delayed fourth native review added 4 fresh findings (1 P1, 3 P2); captured the exact RED of 4 failed / 27 passed and fixed every finding with a 31-test GREEN.
- [x] (2026-08-25) Completed fourth-round verification: 31 comparable-session tests, 104 focused tests, smoke 2095 passed / 1 skipped, contributor-safe 2141 passed / 3 skipped / 26 deselected, full Ruff, web lint/build, contract freshness, and 23 contract tests green.
- [x] (2026-08-25) Pushed `f20fa74`, replied to and resolved all 4 fourth-round threads, and confirmed GitHub CI green.
- [x] (2026-08-25) Explicitly requested a current-head review instead of trusting the transient CLEAN state; the fifth native review added 2 fresh findings (1 P1, 1 P2). Captured the exact targeted RED of 2 failed / 31 deselected and fixed both findings with a 34-test GREEN.
- [x] (2026-08-25) Completed fifth-round verification: 34 comparable-session tests, 100 focused integration tests, smoke 2098 passed / 1 skipped, contributor-safe 2144 passed / 3 skipped / 26 deselected, full Ruff, web lint/build, contract freshness, and 23 contract tests green.
- [x] (2026-08-25) Pushed `4b7ead8`, replied to and resolved both fifth-round threads, and confirmed GitHub CI green.
- [x] (2026-08-25) The sixth explicit current-head review added 3 P2 findings. Captured the exact targeted RED of 3 failed / 34 deselected and fixed all findings plus the real SQLite checkpoint lookup with 48 focused tests green.
- [x] (2026-08-25) Completed sixth-round verification: 104 canonical focused integration tests, smoke 2102 passed / 1 skipped, contributor-safe 2148 passed / 3 skipped / 26 deselected, full Ruff, web lint/build, contract freshness, and 23 contract tests green.
- [x] (2026-08-25) Pushed the sixth review-fix commit `fca0cfc`, resolved its 3 threads, and confirmed GitHub CI green on that head.
- [x] (2026-08-26) The seventh explicit current-head review added 2 fresh findings (1 P1, 1 P2): a current manual match must suppress legacy revisionless auto-match feedback recovery for its session, and `tss_per_hour` density must be computed from positive moving duration with the established elapsed fallback. Captured the exact targeted RED of 2 failed / 38 passed and fixed both findings with a 40-test GREEN.
- [x] (2026-08-26) Completed seventh-round verification: 40 comparable-session tests, smoke 2105 passed, contributor-safe 2151 passed / 4 skipped / 24 deselected, full Ruff, web lint/build, and contract freshness green.
- [x] (2026-08-26) Pushed the seventh review-fix commit `d20d00f`; GitHub CI is green on that head. Its 2 threads remain open for one combined reply/resolution pass with the next review fixes.
- [x] (2026-08-26) The eighth current-head review added 3 findings (1 P1, 2 P2): saved feedback must follow the current match leaf, historical checkpoint recovery must be batched, and a present template without stimulus must stop lineage fallback. Captured an exact targeted RED of 4 failed / 1 control passed and a 5-test GREEN.
- [x] (2026-08-26) Completed eighth-round verification: 44 comparable-session tests, 96 canonical focused tests, smoke 2108 passed / 1 skipped, contributor-safe 2154 passed / 3 skipped / 26 deselected, full Ruff, web lint/build, contract freshness, and 23 contract tests green.
- [x] (2026-08-26) Pushed eighth-round commit `75828ba`, replied to and resolved all 5 open threads, and confirmed every GitHub CI check green.
- [x] (2026-08-26) The ninth current-head review found one P1 across rebound identity: an old target-key ancestor could hide a newer unmatched descendant. Captured the exact 1-test RED and fixed it by selecting the deepest current row whose immutable ancestry contains the saved match.
- [x] (2026-08-26) Completed ninth-round verification: 45 comparable-session tests, 97 canonical focused tests, smoke 2109 passed / 1 skipped, contributor-safe 2155 passed / 3 skipped / 26 deselected, full Ruff, web lint/build, contract freshness, and 23 contract tests green. A concurrent duplicate full-suite run exhausted macOS socket buffers; the sequential rerun was green and the isolated socket probe skipped under the documented sandbox limitation.
- [x] (2026-08-26) Pushed ninth-round commit `0400fe7`, replied to and resolved its thread, and confirmed every GitHub CI check green.
- [x] (2026-08-26) The tenth current-head review added 3 findings (1 P1, 2 P2): rollover history without feedback was excluded, the coach presenter dropped TSS/hour intensity, and the narrative boundary did not enforce the comparison's causal guardrail. Captured an exact 4-test RED, then expanded the GREEN controls for ambiguity, zero delta, negation, and non-causal advice; 48 comparable-session tests and 114 directly affected tests are green.
- [x] (2026-08-26) Completed tenth-round broad verification: 48 comparable-session tests, 114 directly affected tests, smoke 2115 passed / 1 skipped, contributor-safe 2161 passed / 3 skipped / 26 deselected, full Ruff, web lint/build, contract freshness, and 23 contract tests green.
- [x] (2026-08-26) Pushed tenth-round commit `27f5b42`, replied to and resolved its 3 threads, and confirmed GitHub CI green.
- [x] (2026-08-26) The eleventh current-head review added 5 P2 findings: broader causal phrasing, moving-time provenance, an explicit historical target without feedback, unknown threshold timing, and partial interval coverage. Captured an exact 7-test RED and fixed all five with negation/full-coverage/latest-revision controls; 52 comparable-session tests and 133 directly affected tests are green.
- [x] (2026-08-26) Completed eleventh-round broad verification: 52 comparable-session tests, 133 directly affected tests, smoke 2122 passed / 1 skipped, contributor-safe 2168 passed / 3 skipped / 26 deselected, full Ruff, web lint/build, contract freshness, and 23 contract tests green.
- [x] (2026-08-26) Pushed eleventh-round commit `c2458e7`, replied to and resolved its 5 threads, and confirmed every GitHub CI check green.
- [x] (2026-08-26) The twelfth current-head review added 4 P2 findings. Captured an exact 6-failure RED: three unrelated causal phrases, one saved-feedback `datetime`, one missing activity-time cutoff handoff, and one unbounded post-activity checkpoint lookup. Self-review added the active no-feedback `datetime` control; all evidence-boundary defects now have 128 focused tests green.
- [x] (2026-08-26) Completed twelfth-round broad verification: 53 comparable-session tests, 128 directly affected tests, smoke 2129 passed / 1 skipped, contributor-safe 2175 passed / 3 skipped / 26 deselected, full Ruff, web lint/build, contract freshness, and 23 contract tests green.
- [x] (2026-08-26) Pushed the twelfth review-fix commit `f000bbe`, resolved its 4 threads, and confirmed GitHub CI green.
- [x] (2026-08-26) A thirteenth native review on the unchanged product scope added 4 P2 suggestions. The merge owner classified them as non-blocking post-merge follow-ups, resolved the threads without another fix/review cycle, and squash-merged PR #505 as `881107c`.
- [x] (2026-08-26) Recorded the review-loop incident in `docs/engineering_process_metrics.md`; issues #506 and #507 own the executable gate and agent-visible stop rule.

## Surprises & Discoveries

- **Observed**: `plan_actual_matches.planned_snapshot` preserves sport, role, phase, load, and intervals but not the workout catalog's `step_builder_key`. **Inferred**: stimulus identity must be recovered from the immutable referenced planning checkpoint, not guessed from activity names. The cheapest falsifying check is to resolve a known match through its checkpoint and compare the session `definition_snapshot`. **Verified by**: temporary-DB-style service fixture resolves `prior-session` through checkpoint #3 and selects the candidate only after reading `step_builder_key=threshold`.

- **Observed**: canonical activities store `normalized_power`, `avg_power`, `tss_ftp_used`, and `tss_pace_used`, while compact interval structure is local and provider-independent after sync. **Inferred**: v1 needs no provider call or schema change. The cheapest falsifying check is a temporary database containing only these persisted fields and interval rows. **Verified by**: pure fixtures and bounded fake-store service test pass without provider clients or new tables; contract/build suites remain green.

- **Observed**: one plan/fact target may intentionally reference multiple split activities. **Inferred**: silently aggregating normalized power or pace across those activities would create unsupported physiology and would undo split activity semantics. The cheapest falsifying check is a target with two actual ids. **Verified by**: `test_service_refuses_to_aggregate_split_target_activities` returns `TARGET_ACTIVITY_COUNT_UNSUPPORTED`.

- **Observed**: native review proved the same split risk also existed on the comparator side and that late feedback/rematches could detach subjective evidence from its immutable match revision. **Inferred**: comparison identity must bind both sides to exactly one canonical activity and restore historical targets from the saved match checkpoint. **Verified by**: the 8-case review RED and the final 19-test matrix, including split comparator, superseded feedback, immutable checkpoint, and workout-time ordering cases.

- **Observed**: run TSS rows deliberately do not persist `tss_pace_used`, while athlete-profile pace thresholds are already append-only and source-labelled. **Inferred**: run pace evidence should resolve the newest threshold snapshot known at each activity time without changing TSS or schema. **Verified by**: store timeline and service tests select distinct 300/285 s/km threshold contexts for historical/current runs.

- **Observed**: constraint-driven rematching preserves immutable match rows as a `supersedes_match_id` chain, and provider interval rows do not share a provider-independent segmentation contract. **Inferred**: comparator identity must collapse one connected rebind lineage, while structure is comparable only inside the same provider source. **Verified by**: second-review RED/GREEN tests follow a two-revision lineage and label Intervals-vs-Garmin structure as missing instead of incompatible.

- **Observed**: an immediate feedback prompt previously omitted the current match revision from comparison evidence. **Inferred**: versioned feedback could be attached without proving revision compatibility. **Verified by**: prompt projection now resolves revision 22 in the fixture, while versioned feedback with no compatible current revision is excluded.

- **Observed**: `tss_per_hour` in `models/comparable_sessions.py::project_activity_features` divided stored TSS by elapsed `duration_minutes`, while the canonical TSS resolver derives load from positive `moving_duration_minutes`. **Inferred**: a paused session could be projected to a lower density and dropped by the intensity gate even when its moving-time load is identical to the target, so the density should use moving time with the established elapsed fallback. The cheapest falsifying check is two 40-moving-minute runs with identical TSS where one has 75 elapsed minutes. **Verified by**: `test_tss_density_uses_moving_duration_with_elapsed_fallback` projected 56 vs 105 TSS/hour on elapsed time and returned `NO_COMPATIBLE_INTENSITY`; after the fix both project to 105 and the candidate is available.

- **Observed**: the service's legacy recovery branch, `_auto_reconciled_stimulus`, restores a stimulus from revisionless auto-match feedback for an activity absent from the activity-indexed ledger without checking whether that feedback's planned session now has a current manual match to another activity. **Inferred**: after an athlete corrects session S from auto-matched activity A to confirmed activity B, A can still be selected as an exact-stimulus comparator even though the correction explicitly removed that identity, so that branch must be suppressed whenever the current session ledger no longer owns the activity. The cheapest falsifying check is a current `user_confirmed` S→B row plus an active legacy S→A feedback. **Verified by**: `test_service_suppresses_legacy_auto_feedback_after_manual_rematch` returned `available` for the stale A before the fix and `data_gap`/`NO_ELIGIBLE_CANDIDATE` after.

- **Observed**: saved feedback reconstruction used its historical match revision without reading the session's current ledger leaf. **Inferred**: a later manual S→B correction could leave coach comparison anchored to A. **Verified by**: `test_saved_feedback_revalidates_against_current_match_leaf` returned A before the fix and current revision 2 / activity B after it.

- **Observed**: revisionless historical feedback issued one `json_tree` checkpoint scan per session, and lineage fallback continued after finding a present template with empty stimulus evidence. **Inferred**: long histories could create N+1 reads, while incomplete current templates could inherit an unrelated ancestor stimulus. **Verified by**: the 100-session batch test now performs one multi-session read and zero singular reads; paired lineage tests stop on a present empty template but still walk when the identity is absent.

- **Observed**: constraint repair can move a match lineage to a new `target_key`/`session_id`, while a date-bounded latest query still returns the old target's matched ancestor beside the new target's unmatched descendant. **Inferred**: current-leaf revalidation must follow immutable ancestry, not only string identity. **Verified by**: `test_saved_feedback_follows_rebound_descendant_to_unmatched_leaf` returned revision 41 / matched activity A before the fix and revision 43 / unmatched after it.

- **Observed**: after plan rollover, a compatible historical activity and checkpoint can remain while ledger and feedback are both empty; additionally, `overall_intensity_tss_per_hour_delta` and `causal_claim_allowed=false` existed in the tool payload but were not enforced at the final coach boundary. **Inferred**: pre-feature history could disappear, and a model could describe a duration-driven TSS increase as adaptation despite equal TSS/hour density. **Verified by**: the tenth-round 4-test RED reproduced all three gaps; date-bounded checkpoint recovery, source-labelled TSS/hour output, and `CAUSAL_CLAIM_UNSUPPORTED` now pass alongside ambiguity and negation controls.

- **Observed**: the first causal matcher covered one phrasing but not other asserted relations; density used moving time while the label said only duration; active-plan lookup, end-of-day threshold fallback, and any non-empty interval cache each treated uncertain evidence as current/complete. **Inferred**: the coach could still claim adaptation, show contradictory intensity provenance, lose an explicit historical target, look ahead to a same-day threshold, or reject a valid comparator from a truncated interval cache. **Verified by**: the eleventh-round 7-test RED reproduced each case; scoped causal relations, moving-time labelling, immutable match-checkpoint recovery, strict pre-day threshold precedence, and 80% structure coverage controls now pass.

- **Observed**: the broad causal matcher blocked unrelated coaching about pain/recovery, both saved and active explicit-target paths treated `datetime` as a plain `date`, and historical recovery selected the highest checkpoint id without bounding its creation time to the activity. **Inferred**: valid advice could be replaced, valid public input could raise, and a post-workout plan edit could rewrite historical stimulus evidence. **Verified by**: the twelfth-round RED reproduced all three classes; comparison-scoped causal matching, `datetime → date` normalization, and per-date activity-time SQL bounds now pass, including same-day and unknown-time controls.

- **Observed**: provider-exact matching needs both the activity's paired event id and the provider event's AI Trainer external id; the historical local cache does not persist that session-specific pair. **Inferred**: reconstructing it would require provider I/O, new persistence, or guessing from an ambiguous same-sport day. **Verified by**: current local reconstruction intentionally returns a data gap for two same-sport sessions instead of fabricating `ai_trainer_external_id`; durable provider-match persistence remains a follow-up outside this read-only slice.

## Decision Log

- Decision: v1 compares exactly one canonical actual activity to exactly one prior canonical activity. Rationale: normalized power and pace are not safely composable across split activities without a separate aggregation contract; returning a data gap preserves activity-card semantics. Date/Author: 2026-08-24 / Codex.

- Decision: require same normalized sport and exact `step_builder_key`; do not infer stimulus from the activity name, role, or TSS. Rationale: those are weaker and can select the wrong workout while sounding plausible. Date/Author: 2026-08-24 / Codex.

- Decision: rank on duration, TSS-per-hour intensity, and interval-segment structure. If structure is absent, label that dimension missing and renormalize the remaining score; if present and materially incompatible, exclude the candidate. Rationale: missing optional enrichment is not proof of incompatibility, while contradictory structure is evidence against comparison. Date/Author: 2026-08-24 / Codex.

- Decision: sport-specific metric deltas are descriptive evidence only. A single comparison sets `trend_claim_allowed=false` and `causal_claim_allowed=false`. Rationale: one paired observation cannot establish adaptation, cause, or longitudinal direction. Date/Author: 2026-08-24 / Codex.

- Decision: use no new persistence. Rationale: comparison is a deterministic read projection over existing source-of-truth rows and should update naturally after sync, rematch, or feedback correction. Date/Author: 2026-08-24 / Codex.

- Decision: compute `tss_per_hour` from positive `moving_duration_minutes` and fall back to elapsed `duration_minutes` only when moving time is absent or zero. Rationale: the canonical TSS resolver already derives load from moving time, so the intensity gate must not penalize paused sessions with an artificial density drop that removes valid comparators. Date/Author: 2026-08-26 / DeepSeek Harness.

- Decision: suppress legacy revisionless auto-match feedback recovery whenever the session's current manual ledger row (`admin_resolve`, `user_confirmed`, `user_rejected`, `user_unmatched`) does not own the feedback's activity as its sole matched actual. Rationale: a manual correction explicitly removes the auto-matched identity from the session; restoring it through stale feedback would let the athlete's own correction be contradicted by the comparator selection. Date/Author: 2026-08-26 / DeepSeek Harness.

- Decision: revalidate active saved feedback against the current match leaf and use the current status, activity ids, method, confidence, and revision whenever objective identity changed. Rationale: immutable feedback remains historical evidence, but it cannot override a later explicit match correction. Date/Author: 2026-08-26 / Codex.

- Decision: add one read-only multi-session checkpoint query and cache restored historical plans per checkpoint id. Rationale: a bounded comparison request must not perform one full checkpoint scan or restoration per legacy candidate; no schema or write path is needed. Date/Author: 2026-08-26 / Codex.

- Decision: stop stimulus lineage traversal as soon as the requested session identity is present, even if `step_builder_key` is missing. Rationale: missing evidence is a data gap; ancestor traversal is allowed only to recover an absent/restamped identity. Date/Author: 2026-08-26 / Codex.

- Decision: when revalidating saved feedback, select the unique deepest current row whose `supersedes_match_id` ancestry contains the saved revision, hydrating missing intermediates from immutable match storage. Rationale: session strings can change during constraint repair, but lineage identity remains authoritative; ambiguous descendants fail closed. Date/Author: 2026-08-26 / Codex.

- Decision: recover feedback-free rollover history through one read-only query that selects the newest checkpoint containing session templates for each bounded candidate date, then rebuild stable auto-matches locally. Rationale: date bounds preserve the 730-day scope without an arbitrary checkpoint-count limit; newest-per-date avoids reviving superseded plans, and same-date/sport ambiguity fails closed. Date/Author: 2026-08-26 / Codex.

- Decision: expose overall intensity as source-labelled `TSS/ч = TSS ÷ duration`, preserving a true zero delta. Rationale: total TSS and duration deltas alone can suggest a false intensity difference. Date/Author: 2026-08-26 / Codex.

- Decision: propagate `causal_claim_allowed=false` from `get_comparable_session` into the deterministic narrative evidence gate and reject asserted causal/adaptation conclusions while allowing explicit disclaimers and ordinary adaptation-plan advice. Rationale: presenter text is context, not enforcement; the final delivery boundary must apply the guardrail. Date/Author: 2026-08-26 / Codex.

- Decision: recognize asserted adaptation relations (`привела к`, `связан с`, `результат`) but keep negated claims and ordinary adaptation-plan advice outside the causal gate. Rationale: causal enforcement must cover common Russian constructions without becoming a keyword ban. Date/Author: 2026-08-26 / Codex.

- Decision: label TSS/hour as TSS divided by moving time with explicit elapsed-duration fallback. Rationale: the presenter must name the same denominator used by the feature projection. Date/Author: 2026-08-26 / Codex.

- Decision: when an explicit target is absent from the active checkpoint and has no feedback, restore its latest immutable match and referenced checkpoint, then reuse current-leaf revalidation. Rationale: subjective feedback is optional; objective match identity remains authoritative and unmatched descendants still fail closed. Date/Author: 2026-08-26 / Codex.

- Decision: without a trustworthy activity timestamp, profile thresholds must be known strictly before the activity's calendar day; same-day snapshots are look-ahead and excluded. Rationale: temporal provenance is more important than retaining an optional pace metric. Date/Author: 2026-08-26 / Codex.

- Decision: interval structure is comparable only when both same-provider caches cover at least 80% of session duration; otherwise the dimension is missing, not incompatible. Rationale: segment-count disagreement from truncated enrichment is not evidence against comparability. Date/Author: 2026-08-26 / Codex.

## Outcomes & Retrospective

The engine now selects one prior same-sport, exact-stimulus session by transparent duration, TSS-per-hour, and provider-compatible interval-structure evidence. NP is preferred for bike, average power is explicitly a fallback, and run/swim pace uses moving time with a versioned source-backed threshold. Feedback, coach, and web surfaces expose neutral facts; split targets/comparators, stale feedback identity, unmatched or ambiguous match lineage, unstarted sessions, and weak/incompatible evidence fail closed. Same-day ordering uses UTC start time, historical and rebound targets restore their immutable checkpoint lineage, and the default coach target follows workout time rather than late feedback time. Feedback-free pre-feature history also survives plan rollover through newest-per-date checkpoint recovery, while ambiguous same-day plans stay excluded. The coach sees source-labelled TSS/hour intensity and the final narrative gate enforces the comparison's no-causality contract. Detectable target gaps return before candidate-history reads. No schema, TSS, provider, plan, or history write behavior changed. Publication and merge remain the final steps.

## Context and Orientation

`data/database.py` owns canonical activity and match reads. `models/plan_actual_reconciliation.py` links one planned `session_id` to canonical actual activity ids and an immutable checkpoint. `models/planning_checkpoints.py` restores the goal plan so the matched session's versioned `definition_snapshot.step_builder_key` can identify stimulus. `data/activity_store.py` owns compact, locally persisted interval structure. `models/post_workout_feedback.py` and `api/session_feedback.py` expose athlete feedback after a stable match. `models/ai_tools.py` is the read-only coach tool registry; `models/coach_tool_presenter.py` renders tool evidence. `web/components/today/PostWorkoutFeedbackCard.tsx` is the web-primary post-workout surface.

A “comparable session” is one prior activity with the same sport and versioned planned stimulus whose duration, TSS per hour, and interval structure are compatible enough for a descriptive side-by-side comparison. It is not a baseline, trend, or causal estimate.

## Plan of Work

First, create `models/comparable_sessions.py` as a pure module. It will project activity features, preserve source labels, calculate bounded similarity dimensions, exclude incompatible candidates, and return either one versioned comparison or a stable data-gap reason. All sorting will have explicit deterministic tie-breakers.

Second, create `services/comparable_sessions.py`. It will read at most a two-year local window, map latest matches in one bounded query, resolve checkpoint stimulus with a per-call cache, read compact intervals only for otherwise eligible candidates, join latest active feedback, and call the pure selector. It will not contact Intervals.icu or Garmin.

Third, integrate the projection into `api/session_feedback.py` for prompt and submit/correct responses, and into `api/today_snapshot.py` as structured coach session evidence. Add a read-only `get_comparable_session` tool for an explicit session id or the latest feedback-backed completed session. Add neutral presenter text that reports facts and repeats that one comparison is not a trend.

Fourth, mirror the additive DTO in `web/lib/types.ts` and show a compact side-by-side evidence block in `PostWorkoutFeedbackCard.tsx`. The block will never use “better”, “worse”, “progress”, or causal language. Data gaps remain machine-readable but do not add noisy UI.

Fifth, refresh the TypeScript contract, update the ASR catalog, run focused and broad verification, perform self-review and native Codex Review, resolve blocking findings, and publish a draft PR with `Closes #500`.

## Concrete Steps

Run from `/Users/gregkisel/Developer/ai_trainer`:

    ai_trainer_env/bin/python -m pytest tests/smoke/test_comparable_sessions.py -q
    ai_trainer_env/bin/python -m pytest tests/smoke/test_comparable_sessions.py tests/smoke/test_post_workout_feedback.py tests/smoke/test_coach_native_tools.py tests/smoke/test_ai_coach_runtime.py -q
    ai_trainer_env/bin/python -m ruff check models/comparable_sessions.py services/comparable_sessions.py api/session_feedback.py api/today_snapshot.py models/ai_tools.py models/coach_tool_presenter.py tests/smoke/test_comparable_sessions.py
    npm --prefix web run contract:extract
    npm --prefix web run contract:extract -- --check
    npm --prefix web run lint
    npm --prefix web run build
    ai_trainer_env/bin/python -m pytest tests/smoke -q
    ai_trainer_env/bin/python -m pytest -m "not live and not debug and not e2e" tests/

The first focused run before implementation must fail because the new model/service contracts do not exist. After implementation, every focused test must pass. Exact final counts and concise transcripts are recorded here and in the slice spec as work proceeds.

## Validation and Acceptance

A fixed bike fixture must choose an older closer threshold session over a newer incompatible one and report normalized power when present. Removing normalized power must use an explicitly named average-power fallback. Fixed run and swim fixtures must express pace in seconds per kilometre or per 100 metres and carry the activity's stored pace threshold, never FTP. A candidate with a qualitative athlete note and no RPE must preserve the note as labelled subjective evidence without changing its similarity score. Candidate permutations must select the same id and explanation. Missing stimulus, multiple target activities, materially incompatible intensity, or no eligible history must return stable data gaps.

At the product boundary, one temporary-DB prompt and the read-only coach tool must expose the same comparison id/rule version. The React component must compile and render only neutral evidence labels. Existing TSS, matching, feedback persistence, and coach evidence suites must remain green.

## Idempotence and Recovery

Every comparison call is read-only and deterministic. It can be retried after a sync or rematch with no duplicate state. Checkpoint and match rows are never modified. Tests use temporary databases. Rollback is a normal code revert; there is no schema, cursor, provider write, backfill, or local database cleanup.

## Artifacts and Notes

The initial cheap falsifier was repository search plus the #499 gate fixture: no comparable-session model/tool/DTO existed and a session-comparison claim received `TREND_COMPARATOR_MISSING`. Initial pytest failed at missing module import. After the pure slice, the product-boundary run was 3 failed / 8 passed; the first published matrix was 12 passed. First native review produced an exact 8 failed / 10 passed RED and a 19-test GREEN. Second native review produced an exact 4 failed / 18 passed RED and a 22-test GREEN. The unplanned third review produced an exact 5 failed / 22 passed RED and a 27-test GREEN. The delayed fourth review produced an exact 4 failed / 27 passed RED and a 31-test GREEN. The explicit current-head fifth review produced a targeted 2-test RED and a 34-test GREEN. The sixth review produced a targeted 3-test RED and 38 comparable-session tests green. The seventh review produced a targeted 2-test RED and 40 comparable-session tests green. The eighth review produced a targeted 4-failure / 1-control RED and 44 comparable-session tests green. The ninth review produced a targeted 1-test RED and 45 comparable-session tests green. The tenth review produced an exact 4-test RED followed by 9 behavior/control tests and 48 comparable-session tests green. The eleventh review produced an exact 7-test RED followed by 133 directly affected tests and 52 comparable-session tests green. The twelfth review produced an exact 6-failure RED followed by 128 directly affected tests and 53 comparable-session tests green. Latest verification is smoke 2129 passed / 1 skipped, contributor-safe 2175 passed / 3 skipped / 26 deselected, full Ruff, web lint/build, contract freshness, and 23 contract tests green.

## Interfaces and Dependencies

`models/comparable_sessions.py` exports `COMPARABLE_SESSION_RULE_VERSION`, `project_activity_features(activity, stimulus_family, intervals=None, subjective_evidence=None)`, `prefilter_comparable_candidates(target, candidates)`, and `select_comparable_session(target, candidates)`. Inputs and outputs are JSON-shaped mappings; no external dependency is added.

`services/comparable_sessions.py` will export `project_comparable_session(database, evidence, feedback=None, lookback_days=730)`. It returns the same versioned `available` or `data_gap` DTO for API, web, and coach consumers.

`api/session_feedback.py` will export `comparable_session_for_session(database, session_id=None, as_of=None)` for the coach tool and use the service internally for prompt/submission projections. `AITools.get_comparable_session(session_id=None)` will be read-only and share this path.

Revision note (2026-08-24): initial Class A plan created after architecture and contract inspection. The key scope decision is to fail closed for split/composite actuals rather than inventing aggregate power or pace.

Revision note (2026-08-24): implementation and local verification completed. Self-review removed legacy stimulus inference, split duration/intensity rejection evidence, and made sport-specific provenance visible in coach/UI output.

Revision note (2026-08-24): publication state recorded after draft PR #505 was created; implementation behavior did not change.

Revision note (2026-08-26): seventh-round review fixes recorded. `tss_per_hour` now derives from positive moving duration with elapsed fallback, and the legacy auto-match feedback recovery is suppressed when a session's current manual ledger row does not own the feedback's activity. Both are additive behavior with regression coverage; no schema, TSS, provider, plan, or history behavior changed.

Revision note (2026-08-26): eighth-round review fixes recorded. Saved feedback now follows an objective current-leaf correction, legacy checkpoint history is read in one bounded batch with per-checkpoint plan caching, and present templates without stimulus fail closed instead of inheriting ancestor evidence. SQLite schema and all write contracts remain unchanged.

Revision note (2026-08-26): ninth-round rebound-lineage fix recorded. Current-leaf revalidation now follows immutable descendants across re-stamped target/session identity and chooses the unique deepest leaf; an unmatched descendant therefore invalidates the old feedback-backed activity.

Revision note (2026-08-26): tenth-round fixes recorded. Feedback-free rollover history is reconstructed from newest-per-date historical checkpoints, the presenter exposes source-labelled TSS/hour density, and the deterministic final narrative gate blocks unsupported causal/adaptation claims while preserving explicit disclaimers and non-causal advice.

Revision note (2026-08-26): eleventh-round fixes recorded. Common asserted adaptation relations are blocked, intensity provenance names moving-time density, explicit historical targets recover immutable match evidence without feedback, unknown activity times exclude same-day thresholds, and partial interval caches degrade structure to missing.

Revision note (2026-08-26): twelfth-round fixes recorded. Causal blocking is scoped to comparison/adaptation claims, public `datetime` bounds are normalized on both evidence paths, and rollover checkpoint recovery excludes plan state created after the activity. Provider-exact recovery remains fail-closed until session-specific provider identity is durably available locally.
