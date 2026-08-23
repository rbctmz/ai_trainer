# Slice Spec And Review Template

Keep this as a separate working spec linked from the task's ExecPlan; do not copy
its checklists or tables into the strict ExecPlan format defined by
`.agent/PLANS.md`. Delete prompts that are not applicable only after writing
`N/A` and the reason.

- Issue / PR:
- Author / checker / merge owner:
- Date:
- Candidate head SHA:

## Change Class

- Class: A / B / C
- Rationale:
- Automatic escalation triggers checked:
- Review budget used: 0 / 1 / 2 rounds

## Scope

- Behavior that changes:
- Files/modules in scope:

## Non-goals

- Behavior deliberately unchanged:
- Deferred work and owner:

## Definition of Done

- [ ] Acceptance criteria are observable.
- [ ] Required tests/checks are named.
- [ ] Merge and cleanup owner is assigned.

## Public Contracts

List API, TypeScript, database, event, configuration, CLI, and user-visible
contracts. For each, state `unchanged`, `changed compatibly`, or `breaking` with
the corresponding extractor/test/migration.

## Failure, Reset, Rollback, Idempotency

- Failure modes and safe result:
- Retry/idempotency key and duplicate behavior:
- Rollback procedure and proof:
- [ ] Does this add **new persistent state**? If yes, define ownership and age-out.
- [ ] Does **full reset** remove every row/artifact/cursor introduced here?
- [ ] Restart and partial-failure recovery are covered.

## State Boundaries and Identity

- Source of truth and owner:
- Stable identity/provenance keys:
- Cursor/checkpoint lifecycle:
- Concurrency and stale-write behavior:

## RED Matrix

| Acceptance criterion / invariant | RED test or probe | Expected failure | GREEN evidence |
| --- | --- | --- | --- |
| | | | |

Include happy path, boundary, failure, retry, compatibility, and reset rows when
they are relevant. For an intentional behavior change, a test that was already
green is not evidence of a new RED. For a pure behavior-preserving refactor, use
already-green characterization/equivalence evidence as the baseline and prove
the observable behavior remains unchanged; do not invent a failing behavior or
an implementation-coupled test.

## ASR / ADR Traceability

- ASRs affected from `docs/architecture/asr_catalog.md`:
- ADRs reused or required:
- Tactic and trade-off:
- New architecture boundary discovered during review:

## Delivery Slices

For every slice, keep one reviewable behavior boundary and a clean pushed
checkpoint where the agent workflow requires it.

1. Slice:
   - RED, or characterization baseline for a behavior-preserving refactor:
   - GREEN:
   - Refactor/contract refresh:
   - Verification:

## Evidence Bundle

- Head SHA:
- Changed invariants:
- Focused and broad tests:
- CI checks/reruns/flakes:
- Lifecycle/probe evidence:
- Changed contracts:
- Unresolved review-thread count:
- Residual risks and follow-ups:

## Review Findings

Use `P0/P1/P2/P3 → Observed → Inferred → Verified by → gate`.

| Severity | Evidence and falsifying check | Gate | Owner/status |
| --- | --- | --- | --- |
| | | | |

## Final Verdict

- Verdict: BLOCK / READY / READY WITH OWNED FOLLOW-UP
- Blocking findings remaining:
- Review rounds used:
- Accepted risk or follow-up issue:
- Merge owner final gate:
- Post-merge sync/branch/worktree/progress cleanup:
