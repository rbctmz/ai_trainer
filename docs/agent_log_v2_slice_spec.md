# Agent Log v2 Slice Spec and Review Record (#501 / PR #551)

- Issue / PR: #501 / #551
- Author / checker / merge owner: Codex implementer / OpenCode independent reviewer / human repository owner
- Date: 2026-09-05
- Candidate head SHA: working tree after `d62114ee`; replace after final commit

## Change Class

- Class: A
- Rationale: persistent-state semantics, event identity/provenance, concurrency and API/UI contract behavior change.
- Automatic escalation triggers checked: schema/persistence semantics; identity/deduplication; cross-module event contract.
- Review budget used: 1 round (consolidated blocking review before this correction); OpenCode will be the delta verification round.
- Review trigger mode: manual
- Review acceptance head SHA: pending final commit
- Review budget exception: N/A

## Scope

- Behavior that changes: every supported Agent Log producer writes a sourced trigger, bounded scope, terminal/current outcome and explicit revisit condition; replay of one event is atomic; distinct v2 events remain distinct in the API projection.
- Files/modules in scope: `models/coach_decisions.py`, `services/agent_log.py`, `data/database.py`, `api/routers/coach.py`, `api/recovery_replan_loop.py`, `api/sync_jobs.py`, `api/routers/settings.py`, `api/routers/decisions.py`, the existing web Agent Log contract/presentation, focused tests and contract artifact.

## Non-goals

- Behavior deliberately unchanged: no autonomous revisit scheduler; no automatic proposal approval/replay; no deletion or rewriting of legacy rows; no change to provider authority or plan-mutation confirmation gates.
- Deferred work and owner: additional settings surfaces may adopt the same writer when they become agent decisions; owner is the future feature implementer. Manual trigger remains a contract value without a new product entry point.

## Definition of Done

- [x] Acceptance criteria are observable through temporary-database producer and API tests.
- [x] Required focused, broad, web and contract checks are named in the ExecPlan.
- [x] Human repository owner retains merge and cleanup authority.

## Public Contracts

- SQLite `coach_decisions`: changed compatibly with nullable columns already introduced by PR #551; this correction changes transactional semantics, not schema.
- Agent event values: changed compatibly; existing trigger/scope/outcome enums are retained and real producers now populate them.
- API `/api/decisions`: changed compatibly; payload fields are unchanged, but semantically different rows are no longer collapsed.
- TypeScript `CoachDecision`: unchanged by this correction; contract extraction must remain fresh.
- UI: unchanged structurally; it receives truthful row boundaries and metadata.

## Failure, Reset, Rollback, Idempotency

- Failure modes and safe result: `BEGIN IMMEDIATE` waits under the repository SQLite busy-timeout policy; a concurrent replay returns the first row. Provider/approval audit failures never rewrite an already authoritative external outcome. A standalone scheduled audit failure is surfaced through the existing `/today` recovery-loop data-gap boundary.
- Retry/idempotency key and duplicate behavior: `decision_event_id`; a retry returns the existing row, including under concurrent writers.
- Rollback procedure and proof: revert the correction commit; no data migration or destructive reversal is required. Existing nullable columns and historical rows remain readable.
- [x] Does this add **new persistent state**? It adds new rows to the existing owned `coach_decisions` table; full reset already clears that table.
- [x] Does **full reset** remove every row/artifact/cursor introduced here? Yes, `Database.clear_all_data` deletes `coach_decisions`.
- [x] Restart and partial-failure recovery are covered by stable event ids, SQLite transactions and lifecycle tests.

## State Boundaries and Identity

- Source of truth and owner: `Database.save_coach_decision` owns event persistence; `services.agent_log.record_agent_decision` owns required product metadata.
- Stable identity/provenance keys: coach UUID + chat/message source; recovery report fingerprint; sync job id + provider; proposal id; settings request UUID + setting key.
- Cursor/checkpoint lifecycle: unchanged. Recovery proposal keeps the same event owner as its standalone scheduled check or outer coach turn.
- Concurrency and stale-write behavior: one SQLite `BEGIN IMMEDIATE` covers lookup and insert; later retries read the committed row.

## Evidence Boundary Matrix

| Identity | Time/provenance | Evidence state | Fallback | Expected result / falsifier |
| --- | --- | --- | --- | --- |
| Same event replay | concurrent | source present | wait for writer | one row and one returned id |
| Coach request | current chat/message | source present | delivery survives audit error | `coach_request`, proposal-aware revisit |
| Standalone recovery check | report fingerprint/as-of | complete or data-gap | existing recovery-loop boundary | `scheduled_check`, deterministic replay |
| Provider sync | job id/provider | succeeded or failed | sync result remains authoritative | terminal `provider_sync` event |
| Settings PUT | request/setting | changed or unchanged | none | applied or deliberate no-change |
| Proposal approval | proposal id | approved | approval remains authoritative | one `proposal_approved` event |
| Legacy row | historical/unknown | metadata missing | explicit unknown | visible, not fabricated |

## RED Matrix

| Acceptance criterion / invariant | RED test or probe | Expected failure | GREEN evidence |
| --- | --- | --- | --- |
| Concurrent replay is idempotent | `test_database_concurrent_replay_creates_one_logical_decision` | 16 ids instead of 1 | 1 id, 1 row |
| Trigger plus source is produced | scheduled/sync/settings/approval focused tests | no matching rows | all supported producers observed |
| Proposed decision has revisit condition | coach proposal test | `no_revisit_required` | `proposal_resolved` |
| Distinct provenance remains visible | API grouping test | one group with count 2 | two items with count 1 |
| Legacy compatibility | existing legacy migration/API tests | N/A, characterization remains green | explicit unknown/null retained |

## ASR / ADR Traceability

- ASRs affected from `docs/architecture/asr_catalog.md`: ASR-REL-1/2 directional decision provenance and the repository SQLite single-writer policy.
- ADRs reused or required: ADR-0010 coach autonomy boundary remains unchanged; explicit `decision_event_id` ownership from #468 is reused.
- Tactic and trade-off: serialize only event-keyed Agent Log writes with `BEGIN IMMEDIATE`; preserve legacy duplicates instead of adding a failing UNIQUE migration.
- New architecture boundary discovered during review: standalone scheduled recovery and coach-embedded recovery must not compete for one decision identity.

## Delivery Slices

1. Atomic replay and projection integrity.
   - RED: concurrency and distinct-group tests.
   - GREEN: transaction plus v2-aware grouping key.
   - Refactor/contract refresh: no public payload shape change.
   - Verification: focused Agent Log suite.
2. Real producer and revisit wiring.
   - RED: coach source/revisit, scheduled, sync, settings and approval tests.
   - GREEN: common writer and five product boundaries.
   - Refactor/contract refresh: central semantic writer; TS contract unchanged.
   - Verification: producer-adjacent suites and broad contributor-safe run.
3. Independent delta audit.
   - RED or baseline: exact correction diff from `d62114ee` to candidate head.
   - GREEN: disposition every P1/P2 finding.
   - Verification: OpenCode read-only run plus supervisor reproduction.

## Evidence Bundle

- Head SHA: pending final commit
- Changed invariants: atomic logical event identity; producer completeness; proposal revisit; provenance-preserving projection.
- Focused and broad tests: `15 passed` focused and `121 passed` adjacent so far; final contributor-safe/web/contract pending.
- CI checks/reruns/flakes: pending push/CI.
- Lifecycle/probe evidence: deterministic 16-writer RED then GREEN; success/failure sync and applied/no-change settings covered.
- Changed contracts: event semantics only; API/TS shape unchanged.
- Unresolved review-thread count: zero GitHub threads; four local blocking findings are fixed in the working tree pending verification.
- Residual risks and follow-ups: audit writes after externally visible approval/settings mutations are not one cross-table transaction; current boundaries preserve authoritative product outcomes and are covered for normal operation.

## Review Findings

| Severity | Evidence and falsifying check | Gate | Owner/status |
| --- | --- | --- | --- |
| P1 | Concurrent temp-DB probe produced 16 logical duplicates | must fix before merge | implementer / fixed, final verification pending |
| P1 | Production search found only `coach_request` producer | must fix before merge | implementer / five producers covered |
| P2 blocking | Proposed row said no revisit required | must fix before merge | implementer / `proposal_resolved` covered |
| P2 blocking | API collapsed distinct v2 metadata | must fix before merge | implementer / metadata-aware grouping covered |

## Native Review Rounds

| Round | Reviewed head SHA | Trigger | Findings disposition | Stop / exception decision |
| ---: | --- | --- | --- | --- |
| 1 | `d62114ee` | manual consolidated review | four blocking findings reproduced and fixed in working tree | continue to one delta verification |
| 2 | pending | OpenCode verification | pending | stop after dispositions |

## Final Verdict

- Verdict: BLOCK pending final validation and delta review
- Blocking findings remaining: none known in the implementation; verification gates remain.
- Review rounds used: 1 of 2.
- Accepted risk or follow-up issue: none yet.
- Merge owner final gate: human repository owner after final-head CI.
- Post-merge sync/branch/worktree/progress cleanup: human-controlled merge; implementer updates ExecPlan/issue evidence. `backups/` remains untouched.
