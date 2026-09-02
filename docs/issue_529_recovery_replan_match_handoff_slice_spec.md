# Issue #529 Slice Spec and Review

- Issue / PR: #529 / pending
- Author / checker / merge owner: Codex / independent checker pending / repository maintainer
- Date: 2026-09-02
- Candidate head SHA: pending

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

- [ ] Acceptance criteria are observable.
- [ ] Required tests/checks are named.
- [ ] Merge and cleanup owner is assigned.

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
| unchanged survivor | constraint checkpoint after confirmation | current-id confirmed row present | exact current key | same id and matched; any remint falsifies writer fix |
| valid replacement | same date and sport | predecessor confirmed row present, current row absent | one-hop allowed | current row matched; unplanned activity falsifies reader fix |
| current id | current explicit decision | current and predecessor rows present | current wins | output follows current decision |
| ambiguous replacement | two current parents claim one predecessor | predecessor confirmed row present | fail closed | neither silently inherits the same activity |
| incompatible replacement | date or sport differs | predecessor confirmed row present | fail closed | predecessor activity is not inherited |
| missing activity | valid replacement | confirmed id no longer available | existing ambiguous behavior | no fabricated match |

## RED Matrix

| Acceptance criterion / invariant | RED test or probe | Expected failure | GREEN evidence |
| --- | --- | --- | --- |
| constraint persistence preserves survivor | temporary DB confirm bike -> create swim constraint -> restore | survivor id changes during checkpoint build | pending |
| confirmed activity remains matched | same vertical test followed by `reconciliation_at` | unmatched plus unplanned | pending |
| valid replacement inherits confirmed row | pure S1 -> S2 reconciliation test | S2 unmatched plus activity unplanned | pending |
| current explicit decision wins | current and predecessor ledger rows | any predecessor override | pending |
| ambiguous/incompatible lineage fails closed | duplicate claimant and mismatch parameterization | duplicate or wrong inherited match | pending |
| existing behavior remains green | focused legacy contour | regression | pending |

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

- Head SHA: pending
- Changed invariants: pending final diff
- Focused and broad tests: pending
- CI checks/reruns/flakes: pending
- Lifecycle/probe evidence: pre-change probes recorded in ExecPlan; final probes pending
- Changed contracts: none expected
- Unresolved review-thread count: pending
- Residual risks and follow-ups: multi-hop historical lineage intentionally excluded

## Review Findings

| Severity | Evidence and falsifying check | Gate | Owner/status |
| --- | --- | --- | --- |
| P1 | Observed confirmed activity lost after persisted sibling constraint; pure persistence probe reproduces identity-grain crossover | writer and reader regressions must pass | Codex / in progress |

## Native Review Rounds

| Round | Reviewed head SHA | Trigger | Findings disposition | Stop / exception decision |
| ---: | --- | --- | --- | --- |
| 1 | pending | manual | pending | pending |
| 2 | pending if needed | verification | pending | stop |

## Final Verdict

- Verdict: BLOCK until implementation and validation complete
- Blocking findings remaining: writer and reader REDs not yet green
- Review rounds used: 0
- Accepted risk or follow-up issue: none yet
- Merge owner final gate: repository maintainer
- Post-merge sync/branch/worktree/progress cleanup: merge owner or delegated author after explicit merge decision
