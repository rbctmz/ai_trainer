# Coach Narrative Evidence Gate — Class A Slice Spec

- Issue / PR: [#499](https://github.com/rbctmz/ai_trainer/issues/499); PR TBD
- Author / checker / merge owner: Codex / independent checker / user
- Date: 2026-08-24
- Candidate head SHA: base `e23d344f075fc664f8f00cbb0c43701b27043c77`; immutable candidate SHA is recorded in the issue/PR after commit

## Change Class

- Class: **A**
- Rationale: athlete-facing AI safety behavior crosses synthesis, streaming delivery, canonical health evidence, persistence, and additive API/web contracts.
- Automatic escalation triggers checked: health evidence/provenance — yes; persistence semantics — yes; external writes — no; plan mutation — no; live provider — no; destructive migration — no.
- Review budget used: 2 / 2 independent audits; the boundary checker then performed five bounded fix/recheck passes

## Scope

- Behavior that changes: bounded material coach claims are validated before delivery; unsupported claims are replaced with deterministic evidence-bounded text and stable reason codes.
- Files/modules in scope: pure model gate, shared runtime/API boundary, read-only today plan/fact projection, additive decision audit metadata, smoke tests, TypeScript contract, ExecPlan/spec.

## Non-goals

- Behavior deliberately unchanged: provider selection, tool execution, plan mutation/approval, readiness formula, plan/fact matching, historical messages, unrelated factual claims, medical diagnosis.
- Deferred work and owner: incremental sentence-safe streaming is a possible future latency optimization; no owner until measured live latency proves it necessary.

## Definition of Done

- [x] Acceptance criteria are observable.
- [x] Focused, broad, lint, web, and contract checks are named and green.
- [ ] User is merge owner; root agent owns draft PR and post-merge cleanup.

## Public Contracts

- Evidence/gate DTO: new internal versioned contract.
- `/api/coach/chat` SSE `done`: changed compatibly with optional `evidence_gate` metadata.
- `/api/decisions`: changed compatibly with nullable gate audit fields.
- TypeScript: changed compatibly to mirror optional metadata; extractor refreshed.
- SQLite: changed compatibly with nullable migrate-on-start columns; no backfill.
- CLI/config/provider contracts: unchanged; existing `ATHLETE_TIMEZONE` is consumed.

## Failure, Reset, Rollback, Idempotency

- Failure modes and safe result: invalid timezone, missing/stale evidence, or validator exception fail closed to deterministic data-gap text; raw unsafe narrative is never delivered or saved.
- Retry/idempotency key and duplicate behavior: one result per coach `message_id`; evidence fingerprint is deterministic for the supplied bundle. Repeating a request creates a normal new decision/message, unchanged from current chat behavior.
- Rollback procedure and proof: revert code; nullable columns and legacy rows remain valid. Temporary fixtures prove old-schema migration and reset behavior.
- [x] Does this add **new persistent state**? Yes: nullable gate audit metadata owned by the coach decision row; it ages out with that row.
- [x] Does **full reset** remove every row/artifact/cursor introduced here? Yes: existing reset deletes all `coach_decisions`; no new table/cursor exists.
- [x] Restart and partial-failure recovery are covered by legacy-schema migration and route failure tests.

## State Boundaries and Identity

- Source of truth and owner: readiness from `services/readiness_snapshot.py`; plan/fact from the read-only today reconciliation projection; calendar from one UTC instant + `ATHLETE_TIMEZONE`; comparator evidence only from successful raw tool results.
- Stable identity/provenance keys: coach `message_id`, `decision_event_id`, evidence version/fingerprint, readiness/session rule versions.
- Cursor/checkpoint lifecycle: read-only active checkpoint reference; no cursor or checkpoint write.
- Concurrency and stale-write behavior: evidence is frozen for one turn before provider synthesis; each decision row links metadata to that turn's `message_id`.

## RED Matrix

| Acceptance criterion / invariant | RED test or probe | Expected failure | GREEN evidence |
| --- | --- | --- | --- |
| Green readiness cannot support poor recovery/suppressed HRV. | `test_green_readiness_blocks_poor_recovery_and_suppressed_hrv_claims` | Scaffold passes unsafe text unchanged. | Replaced with both stable contradiction codes. |
| Missing readiness becomes an explicit gap. | `test_missing_readiness_is_an_explicit_data_gap` | Scaffold returns `pass`. | Deterministic `data_gap`. |
| A trend needs a domain comparator. | `test_trend_claim_without_comparator_is_refused` | Scaffold returns `pass`. | Missing comparator is refused; direction mismatch is separate. |
| Supported narrative is byte-identical. | `test_supported_hrv_trend_and_neutral_advice_pass_byte_identical` | Characterization stays green. | Exact original bytes preserved. |
| Calendar arithmetic uses the athlete timezone. | `test_calendar_uses_athlete_timezone_at_utc_midnight_boundary` | Scaffold lacks canonical calendar evidence and passes wrong wording. | One UTC instant resolves Moscow today/yesterday/race distance. |
| Invalid timezone fails closed. | `test_invalid_timezone_fails_closed_for_relative_date_claim` | Scaffold returns `pass`. | Stable invalid-timezone data gap. |
| A missed session needs canonical plan/fact evidence. | `test_missed_session_without_canonical_plan_fact_evidence_is_refused` | Scaffold returns `pass`. | Refused unless durable `did_not_start` evidence is joined. |
| Negation/intent/quote are not claims. | `test_negation_intent_and_quoted_text_do_not_trigger_material_claims` | Characterization stays green. | Per-assertion guards preserve safe text. |
| Policy reason ordering is stable. | `test_reason_codes_have_stable_policy_order` | Scaffold returns no codes. | Stable policy order asserted. |
| Streaming never reveals raw unsafe text. | `test_streaming_route_never_emits_unsafe_provider_text_and_audits_gate` | Existing route yields raw provider delta. | No raw unsafe token; SSE, chat, and audit share gated result. |

## ASR / ADR Traceability

- ASRs affected: ASR-REL-2 (missing evidence is data gap), ASR-MOD-2/3 (shared pure semantics and additive compatibility), ASR-PERF-2 (full narrative buffering delays first token).
- ADRs reused or required: ADR-0003 canonical signals snapshot; ADR-0010 coach boundary remains unchanged. No new ADR: this is a bounded validation tactic within the established coach runtime.
- Tactic and trade-off: complete-response validation maximizes safety/testability; live first-token latency may increase. Meta/tool/proposal events remain streaming and the deterministic local latency gate remains mandatory.
- New architecture boundary discovered during review: provider text is untrusted input until the final narrative gate succeeds.

## Delivery Slices

1. Slice: policy RED → pure GREEN.
   - RED: fixed structured fixtures above.
   - GREEN: evidence builder, fingerprint, narrow claim policy, deterministic replacement.
   - Refactor/contract refresh: no UI/API yet.
   - Verification: focused test and Ruff.
2. Slice: product delivery and audit.
   - RED: scripted live stream leaks unsupported token; audit row has no gate metadata.
   - GREEN: buffer, validate, emit/save/classify one delivered text; additive audit/SSE metadata.
   - Refactor/contract refresh: TypeScript and extractor.
   - Verification: coach suites, web lint/build, migration test.
3. Slice: broad verification/review/publication.
   - RED: N/A after behavior GREEN; independent review targets false positives, fail-closed behavior, and ASR latency.
   - GREEN: resolved findings and synchronized evidence.
   - Refactor/contract refresh: ExecPlan/spec final state.
   - Verification: smoke, contributor-safe, Ruff, contract check, CI.

## Evidence Bundle

- Head SHA: recorded in the issue/PR after commit.
- Changed invariants: final athlete-facing narrative is untrusted until the versioned gate passes; one evidence bundle/date anchor is frozen per turn; delivered, persisted, and classified text are identical.
- Focused and broad tests: initial RED 7 failed / 2 passed; final focused 177 passed; smoke 2055 passed / 1 skipped; contributor-safe 2101 passed / 3 skipped / 26 deselected.
- CI checks/reruns/flakes: Ruff clean; web lint/build green; contract artifact current; contract smoke 23 passed; PR CI pending.
- Lifecycle/probe evidence: all tests use temporary DB/chat paths; no live data.
- Changed contracts: additive SSE/decision/TypeScript/SQLite gate metadata; contract extractor refreshed and checked.
- Unresolved review-thread count: N/A.
- Residual risks and follow-ups: measured live latency unknown; regex taxonomy intentionally narrow.

## Review Findings

| Severity | Evidence and falsifying check | Gate | Owner/status |
| --- | --- | --- | --- |
| P1 | **Observed**: raw streaming delta was rendered before final validation. **Inferred**: post-stream filtering could not meet acceptance. **Verified by**: scripted route test. | Buffer and gate complete narrative before first `token`. | Root / resolved. |
| P1 | **Observed**: initial policy missed Russian comparator directions and common recovery/trend forms; sentence-wide advice/conditional/negation guards hid valid assertions. **Inferred**: the narrow taxonomy needed per-assertion guards and normalized structured directions. **Verified by**: independent falsifying probes across five bounded rechecks. | Add explicit regression matrix and normalize only admitted comparator domains. | Root / resolved. |
| P2 | **Observed**: legacy runtime and recovery loop could derive server-local dates; builder exceptions and internal first-token telemetry did not cover the whole route boundary. **Inferred**: evidence could drift or fail open around setup. **Verified by**: captured date anchors, injected builder exception, and external timing test. | Freeze one athlete-local date, fail closed, and start timing at route entry. | Root / resolved. |

## Final Verdict

- Verdict: **READY** for draft PR and CI.
- Blocking findings remaining: none in the bounded taxonomy.
- Review rounds used: 2 independent audits plus five bounded checker passes; final checker verdict READY.
- Accepted risk or follow-up issue: complete-response safety buffering increases live first-narrative-token latency; incremental safe streaming is deferred until measured latency justifies it.
- Merge owner final gate: user.
- Post-merge sync/branch/worktree/progress cleanup: root agent.
