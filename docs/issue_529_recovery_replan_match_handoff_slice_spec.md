# Issue #529 Slice Spec and Review

- Issue / PR: #529 / #530
- Author / checker / merge owner: Codex / independent checker pending / repository maintainer
- Date: 2026-09-02
- Candidate implementation SHA: `10e62fe`

## Change Class

- Class: A
- Rationale: parent-session identity, checkpoint provenance, and append-only reconciliation semantics change.
- Automatic escalation triggers checked: identity/provenance and persistence semantics.
- Review budget used: 0 rounds
- Review trigger mode: manual
- Review acceptance head SHA: pending
- Review budget exception: N/A

## Scope

- Behavior that changes: a parent session unchanged by removal of a sibling keeps its id through coach-constraint persistence; reconciliation can inherit an explicit confirmed match through one valid parent-session replacement.
- Files/modules in scope: `api/planning_service.py`, `models/plan_actual_reconciliation.py`, focused smoke tests, this spec, and the ExecPlan.

## Non-goals

- Behavior deliberately unchanged: match heuristics and thresholds; `user_rejected` and `user_unmatched` semantics; recovery-replan selection and load math; automatic historical backfill; database schema; provider delivery; brick leg matching; issues #516 and #517.
- Deferred work and owner: multi-hop lineage across checkpoints is excluded unless the RED evidence proves one-hop current-plan lineage insufficient; any such expansion needs a separately reviewed boundary.

## Definition of Done

- [x] Acceptance criteria are observable.
- [x] Required tests/checks are named.
- [x] Merge and cleanup owner is assigned.

## Public Contracts

- API and TypeScript: unchanged.
- Database schema: unchanged; `plan_actual_matches` remains append-only.
- Checkpoint JSON: compatible correction of existing `session_id`/`replaces_session_id` values, no new field.
- Reconciliation DTO: unchanged shape; current session identity remains authoritative.
- CLI/configuration/user-visible strings: unchanged.

## Failure, Reset, Rollback, Idempotency

- Failure modes and safe result: ambiguous lineage, incompatible date/sport, or missing predecessor activity fails closed without inherited assignment.
- Retry/idempotency key and duplicate behavior: no new write or key; existing constraint mutation and match fingerprints remain authoritative.
- Rollback procedure and proof: revert the scoped commit; no migration or data cleanup required.
- [x] Does this add new persistent state? No.
- [x] Does full reset remove every row/artifact/cursor introduced here? N/A; no state introduced.
- [x] Restart and partial-failure recovery are covered by existing atomic coach-mutation persistence plus temporary-DB vertical regression.

## State Boundaries and Identity

- Source of truth and owner: `sessions[].session_id` owns executable parent identity; `template.session_id` is a day projection on multi-session days and cannot own a match.
- Stable identity/provenance keys: current `session:<session_id>` target; one-hop parent from the current session's `replaces_session_id`.
- Cursor/checkpoint lifecycle: immutable checkpoints; unchanged survivor identity across `2 -> 1`; no match-row mutation.
- Concurrency and stale-write behavior: existing `base_checkpoint_id` and mutation preview fingerprint remain unchanged.

## Evidence Boundary Matrix

| Identity | Time/provenance | Evidence state | Fallback | Expected result / falsifier |
| --- | --- | --- | --- | --- |
| unchanged survivor | constraint checkpoint after confirmation | current-id confirmed row present | exact current key | GREEN: same id and matched |
| valid replacement | same date and sport | predecessor confirmed row present, current row absent | one-hop allowed | GREEN: current row matched and activity claimed |
| current id | current explicit decision | current and predecessor rows present | current wins | GREEN: current `user_unmatched` wins |
| ambiguous replacement | two current parents claim one predecessor | predecessor confirmed row present | fail closed | GREEN: neither inherits and activity stays unplanned |
| incompatible replacement | date or sport differs | predecessor confirmed row present | fail closed | GREEN: predecessor activity is not inherited |
| missing activity | valid replacement | confirmed id no longer available | existing ambiguous behavior | Existing confirmed-ledger ambiguity behavior unchanged |

## RED Matrix

| Acceptance criterion / invariant | RED test or probe | Expected failure | GREEN evidence |
| --- | --- | --- | --- |
| constraint persistence preserves survivor | temporary DB confirm bike -> create swim constraint -> restore | RED: survivor id changed | GREEN in `test_sport_scoped_constraint_persistence_keeps_confirmed_survivor_matched` |
| confirmed activity remains matched | same vertical test followed by `reconciliation_at` | RED: identity assertion failed before reconciliation could match | GREEN: `matched`, activity returned, not unplanned |
| valid replacement inherits confirmed row | pure S1 -> S2 reconciliation test | RED: S2 unmatched plus activity unplanned | GREEN for `user_confirmed` and `admin_resolve` |
| current explicit decision wins | current and predecessor ledger rows | any predecessor override | GREEN: current `user_unmatched` wins |
| ambiguous/incompatible lineage fails closed | duplicate claimant and date/sport mismatch parameterization | duplicate or wrong inherited match | GREEN: no inheritance |
| existing behavior remains green | focused legacy contour | regression | GREEN: 132 passed |

## ASR / ADR Traceability

- ASRs affected from `docs/architecture/asr_catalog.md`: ASR-REL-1.
- ADRs reused or required: existing append-only planning/checkpoint decisions; no new ADR because no new architecture boundary is introduced.
- Tactic and trade-off: preserve stable identity at the writer and add bounded read-time state resynchronization; deliberate fail-closed behavior leaves unresolved evidence visible rather than guessing.
- New architecture boundary discovered during review: checkpoint serialization can restamp identities without previous-plan context; the mutation caller must canonicalize lineage before this boundary.

## Delivery Slices

1. Writer survivor identity:
   - RED: production-shaped coach-constraint persistence test.
   - GREEN: canonicalize updated constraint plan with `previous_goal_plan` before checkpoint construction.
   - Refactor/contract refresh: none expected.
   - Verification: focused vertical plus coach-constraint and identity suites.

2. Reconciliation handoff:
   - RED: valid one-hop confirmed predecessor test plus fail-closed boundaries.
   - GREEN: internal planned lineage and bounded ledger resolution before reservation filtering.
   - Refactor/contract refresh: no public shape change.
   - Verification: reconciliation, transfer, recovery-replan, Today, broad contributor contour.

## Evidence Bundle

- Implementation SHA: `10e62fe`
- Changed invariants: unchanged survivor keeps parent id through sport-scoped constraint persistence; valid one-hop confirmed predecessor can supply evidence only under unambiguous same-date/sport guards; current-id ledger always wins.
- Focused and broad tests: new module 7 passed; focused contour 132 passed; contributor-safe contour 2,241 passed, 3 skipped, 26 deselected.
- CI checks/reruns/flakes: local Ruff and diff check green; GitHub CI pending on PR #530.
- Lifecycle/probe evidence: temporary DB proposal -> atomic confirmation -> checkpoint restore -> reconciliation passes; no state migration.
- Changed contracts: no API, TypeScript, schema, configuration, or provider contract change.
- Unresolved review-thread count: N/A before PR.
- Residual risks and follow-ups: historical malformed checkpoint #129 is not rewritten and cannot satisfy the new valid-lineage reader guard; explicit re-confirmation or separately authorized repair is required.

## Review Findings

| Severity | Evidence and falsifying check | Gate | Owner/status |
| --- | --- | --- | --- |
| P1 | Observed confirmed activity lost after persisted sibling constraint; pure persistence probe reproduced identity-grain crossover | writer and reader regressions must pass | fixed-in `10e62fe`; local focused and broad evidence green |

## Native Review Rounds

| Round | Reviewed head SHA | Trigger | Findings disposition | Stop / exception decision |
| ---: | --- | --- | --- | --- |
| 1 | pending | manual | pending | pending |
| 2 | pending if needed | verification | pending | stop |

## Final Verdict

- Verdict: READY FOR INDEPENDENT REVIEW; merge remains human-gated
- Blocking findings remaining: none in self-review; GitHub CI and independent review pending
- Review rounds used: 0
- Accepted risk or follow-up issue: no automatic repair of historical malformed checkpoint #129; documented non-goal
- Merge owner final gate: repository maintainer
- Post-merge sync/branch/worktree/progress cleanup: merge owner or delegated author after explicit merge decision
