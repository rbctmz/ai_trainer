# Issue #517 Slice Spec And Review

- Issue / PR: #517 / pending
- Author / checker / merge owner: Luna maker / Codex checker / repository maintainer
- Date: 2026-08-29
- Candidate head SHA: pending

## Change Class

- Class: A
- Rationale: the change corrects deduplication identity and persisted forecast lifecycle semantics.
- Automatic escalation triggers checked: deduplication rules and persistence semantics apply; no schema migration, provider write, security, or destructive synchronization.
- Review budget used: 0 / 2 rounds
- Review trigger mode: manual
- Review acceptance head SHA: pending
- Review budget exception: N/A

## Scope

- Behavior that changes: timestamp-only forecast replays are idempotent; meaningful pre-start driver changes append; start or terminal feedback closes creation; Today is evaluation/feedback-aware.
- Files/modules in scope: `api/session_quality_forecast.py`, `api/today_snapshot.py`, narrowly required helpers in `api/session_feedback.py` or `data/database.py`, and focused smoke tests.

## Non-goals

- Behavior deliberately unchanged: probability formula, decision influence, checkpoint format, existing prediction/evaluation rows, and provider integration.
- Deferred work and owner: cleanup of existing dogfood duplicates requires a separate user-authorized maintenance task.

## Definition of Done

- [x] (2026-08-29) Acceptance criteria are observable through temporary SQLite lifecycle tests; GREEN evidence is recorded below.
- [x] (2026-08-29) Required focused, broad, lifecycle, lint, and contract checks are recorded.
- [ ] Merge and cleanup owner is the repository maintainer after explicit approval.

## Public Contracts

The HTTP and TypeScript response shapes should remain unchanged. The Today forecast semantics change compatibly: a completed target is no longer presented as active pending. The SQLite schema is unchanged; prediction and evaluation rows remain append-only.

## Failure, Reset, Rollback, Idempotency

- Failure modes and safe result: missing identity, match, activity start, or feedback evidence must fail closed without inventing completion; it may continue the prior pre-start behavior only when the session is not proven started.
- Retry/idempotency key and duplicate behavior: the semantic fingerprint excludes volatile observation timestamps and includes all current forecast drivers.
- Rollback procedure and proof: revert the task commit; no migration or cleanup is performed.
- [x] Does this add new persistent state? No.
- [ ] Does full reset remove every row/artifact/cursor introduced here? N/A; no new state owner is introduced.
- [x] Restart and partial-failure recovery are covered by repeated temporary-database probes.

## State Boundaries and Identity

- Source of truth and owner: immutable prediction/evaluation tables owned by `data/database.py`; formula owned by `models/session_quality_forecast.py`.
- Stable identity/provenance keys: checkpoint id, target date/index/session id, rule version, semantic forecast drivers.
- Cursor/checkpoint lifecycle: no cursor; only the active checkpoint's eligible pre-start target may receive a revision.
- Concurrency and stale-write behavior: existing unique fingerprint plus transaction remains the write gate; semantically identical concurrent calls must converge on one row.

## Evidence Boundary Matrix

| Identity | Time/provenance | Evidence state | Fallback | Expected result / falsifier |
| --- | --- | --- | --- | --- |
| current target | before start; timestamp-only change | plan/readiness present | reuse allowed | same id and one row |
| current target | before start; driver changed | plan/readiness present | append allowed | one new immutable revision |
| current target | at/after actual start | confirmed match + start present | fail closed | no insert |
| current target | feedback submitted | active terminal feedback present | fail closed | no insert and not active in Today |
| historical/evaluated | any | evaluation present over raw pending | projection required | Today does not resurrect pending |
| ambiguous/missing | unknown start or incomplete feedback | partial evidence | preserve safe pre-start behavior | no fabricated completion |

## RED Matrix

| Acceptance criterion / invariant | RED test or probe | Expected failure | GREEN evidence |
| --- | --- | --- | --- |
| Timestamp-only replay is idempotent | `test_shadow_recording_reuses_semantic_forecast_when_only_provenance_timestamps_change` | current code creates multiple prediction rows | GREEN: ten calls, one row, same id, provenance retained |
| Meaningful driver change appends | existing `test_shadow_recording_appends_changed_readiness_without_product_mutation` | baseline remains green with two revisions | GREEN: existing test passes in focused and broad contours |
| Started session closes creation | `test_shadow_recording_stops_after_confirmed_actual_start` | current code returns the pending row instead of a lifecycle stop | GREEN: `session_started`, row count unchanged |
| Terminal feedback closes creation | `test_shadow_recording_stops_after_active_terminal_feedback` | current code returns the pending row instead of a lifecycle stop | GREEN: `terminal_feedback_exists`, row count unchanged |
| Today is lifecycle-aware | `test_today_skips_evaluated_pending_history_and_selects_next_forecast` | current code selects evaluated raw-pending id `1` | GREEN: evaluated id `1` skipped, next id `2` selected |
| Concurrent semantic replay converges | `test_shadow_recording_concurrent_semantic_replays_converge` | duplicate revision or lock failure | GREEN: one create, one row, shared id |

## ASR / ADR Traceability

- ASRs affected from `docs/architecture/asr_catalog.md`: ASR-REL-2, ASR-REL-3, ASR-PERF-1, ASR-MOD-3.
- ADRs reused or required: ADR-0002 SQLite primary store, ADR-0003 canonical signals snapshot, ADR-0006 append-only planning versions; no new ADR expected.
- Tactic and trade-off: explicit semantic identity plus append-only revisions; bounded local reads trade a small amount of Today work for correct lifecycle projection.
- New architecture boundary discovered during review: none yet.

## Delivery Slices

1. [x] Semantic fingerprint RED→GREEN: timestamp-only replay reuses, meaningful driver change appends.
2. [x] Lifecycle RED→GREEN: actual start and terminal feedback stop creation.
3. [x] Today projection RED→GREEN: evaluated/completed targets do not resurface; next eligible target remains visible.
4. [x] Broad validation and self-review: contributor-safe suite, Ruff, contract check, diff review, evidence bundle.

## Evidence Bundle

- Head SHA: not created; no commit or staging per task instruction
- Changed invariants: semantic fingerprint, pre-start lifecycle gate, evaluation-aware Today selection
- Focused and broad tests: maker focused `81 passed in 1.67s`; final parent focused `82 passed in 2.28s`; related lifecycle `71 passed in 3.05s`; contributor-safe `2180 passed, 6 skipped, 26 deselected` in `59.76s`
- CI checks/reruns/flakes: Ruff `All checks passed!`; contract extraction check reports artifact current; no flaky reruns observed
- Lifecycle/probe evidence: ten timestamp-only calls converge to one row; concurrent calls converge to one row; start/feedback calls do not insert; evaluated Today row is skipped
- Changed contracts: expected compatible semantic correction only
- Unresolved review-thread count: 0 before PR
- Residual risks and follow-ups: existing duplicate cleanup remains out of scope; legacy rows without a recoverable session identity cannot receive the new local lifecycle gate, but evaluation projection still suppresses evaluated status

## Review Findings

| Severity | Evidence and falsifying check | Gate | Owner/status |
| --- | --- | --- | --- |
| P1 | Loop-result fallback bypassed evaluation/lifecycle projection and could resurrect an evaluated raw-pending row when the main pool was empty; falsified by the stale loop-result case in `test_today_skips_evaluated_pending_history_and_selects_next_forecast` | must fix before PR | fixed in working tree; final focused suite green |

## Native Review Rounds

| Round | Reviewed head SHA | Trigger | Findings disposition | Stop / exception decision |
| ---: | --- | --- | --- | --- |
| 1 | pending | manual | pending | continue / stop |
| 2 | pending | verification | pending | stop / exception rationale |

## Final Verdict

- Verdict: READY FOR PARENT REVIEW
- Blocking findings remaining: none
- Review rounds used: 0 (manual self-review only; no full-diff reviewer invoked)
- Accepted risk or follow-up issue: existing duplicate cleanup remains separate
- Merge owner final gate: repository maintainer
- Post-merge sync/branch/worktree/progress cleanup: Codex after explicit merge approval
