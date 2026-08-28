# Trusted Review Gate — Slice Spec And Review

- Issue / PR: #512 / pending
- Author / checker / merge owner: Codex / Codex Review + CI / rbctmz
- Date: 2026-08-28
- Candidate head SHA: pending

## Change Class

- Class: A
- Rationale: changes GitHub token permissions and the trusted execution boundary of a write-capable workflow.
- Automatic escalation triggers checked: security boundary and permissions.
- Review budget used: 0 rounds for phase 2
- Review trigger mode: manual
- Review acceptance head SHA: pending
- Review budget exception: N/A

## Scope

- Behavior that changes: current-head authenticated review evidence is mandatory; write policy loads from `main`; clean comment-only reviews are durable; candidate-controlled direct review triggers become a permissionless two-hop signal.
- Files/modules in scope: `.github/workflows/pr-ready-to-merge.yml`, `.github/workflows/pr-review-signal.yml`, `tests/smoke/test_native_codex_review_integration.py`, `docs/loop_engineering_instruction.md`, this spec, and `docs/trusted_review_gate_execplan.md`.

## Non-goals

- Behavior deliberately unchanged: two-round review budget, human merge ownership, no auto-review, no auto-merge.
- Deferred work and owner: CODEOWNERS and hosted ruleset settings remain #511 / rbctmz.

## Definition of Done

- [x] Acceptance criteria are observable locally; hosted signal behavior remains the PR acceptance probe.
- [x] Required local tests/checks are named and green.
- [ ] Merge and cleanup owner is rbctmz; Codex owns branch/PR evidence and post-merge local sync.

## Public Contracts

- GitHub event contract: changed compatibly; direct review events only complete a permissionless signal workflow, whose `workflow_run` wakes trusted default-branch recomputation.
- Policy helper contract: unchanged from merged PR #513.
- API, TypeScript, database, CLI, and product UI: unchanged.

## Failure, Reset, Rollback, Idempotency

- Failure modes and safe result: missing current-head evidence, missing trusted label actor, unresolved thread, active changes request, exceeded budget, or stale head all fail closed.
- Retry/idempotency key and duplicate behavior: clean result uses `<comment-id>:<reviewed-sha-prefix>` commit-status context; repeats do not duplicate.
- Rollback procedure and proof: revert activation PR; old workflow ignores durable statuses.
- [x] Does this add new persistent state? Successful commit statuses are durable audit entries owned by the review workflow and intentionally do not age out.
- [x] Does full reset remove every row/artifact/cursor introduced here? N/A: no destructive reset is provided for immutable review audit evidence.
- [x] Restart and partial-failure recovery are covered by idempotent recomputation, immutable status keys, associated-commit lookup, and scheduled repair.

## State Boundaries and Identity

- Source of truth and owner: submitted GitHub reviews, authenticated connector clean-result comments/statuses, and privileged label timeline; GitHub owns storage.
- Stable identity/provenance keys: review ID/commit ID; clean connector comment ID/reviewed SHA; PR head SHA.
- Cursor/checkpoint lifecycle: no cursor; every event recomputes from GitHub state.
- Concurrency and stale-write behavior: refetch head and privileged labels immediately before publishing; abandon stale evaluation.

## Evidence Boundary Matrix

| Identity | Time/provenance | Evidence state | Fallback | Expected result / falsifier |
| --- | --- | --- | --- | --- |
| current-head native review | exact commit ID | present | none | eligible after privileged acceptance |
| historical native review | older commit ID | present | counts budget only | cannot satisfy current head |
| clean connector comment | reviewed SHA in PR | present or later deleted | durable Actions status | counts once |
| maintainer-authored lookalike | any SHA | spoofed | none | rejected |
| candidate workflow | PR head | modified | permissionless signal only | never receives checkout, secrets, or write-capable token |

## RED Matrix

| Acceptance criterion / invariant | RED test or probe | Expected failure | GREEN evidence |
| --- | --- | --- | --- |
| no candidate-controlled write trigger | static workflow smoke rejects direct review events in the privileged workflow and constrains the signal workflow | current main contains direct events with writes | direct events exist only with `permissions: {}`, no checkout, and no secrets |
| trusted helper ref | static workflow smoke requires default-branch checkout | current main uses candidate checkout | explicit ref present |
| current-head evidence | smoke requires `countNativeReviewRoundsForHead` wired into both jobs | symbol absent from workflow | symbol and decision arg present |
| clean result durability | smoke requires `issue_comment`, `statuses: write`, and persistence helper | all absent | all present and Node tests green |
| synchronization invalidation | smoke requires `pull_request_target` plus invalidation call | target trigger absent | push clears acceptance/readiness |
| review signal PR identity | smoke requires associated-pulls fallback keyed by `workflow_run.head_sha` | historical review runs expose empty `pull_requests` | trusted GitHub lookup supplies only associated open PRs |

## ASR / ADR Traceability

- ASRs affected from `docs/architecture/asr_catalog.md`: ASR-SEC-1 and merge-control reliability.
- ADRs reused or required: no new product ADR; reuse least privilege and trusted-default-ref tactics.
- Tactic and trade-off: permissionless direct-event signal plus trusted `workflow_run` recomputation preserves prompt invalidation without exposing write authority; the schedule remains a repair path.
- New architecture boundary discovered during review: candidate workflow definition itself is executable policy, not only the checked-out helper.

## Delivery Slices

1. Slice: trusted activation workflow.
   - RED: workflow contract fails on direct review triggers and candidate checkout.
   - GREEN: trusted triggers/ref, current-head evidence, durable clean-round ledger.
   - Refactor/contract refresh: update engineering-loop documentation and inline JS syntax checks.
   - Verification: focused smoke, Node policy tests, Ruff, contributor-safe suite, hosted PR checks.

## Evidence Bundle

- Head SHA: pending
- Changed invariants: trusted workflow ref; current-head review; immutable clean-round budget.
- Focused and broad tests: `node --test .github/scripts/review-gate.test.cjs` (18 passed); focused smoke (12 passed); Ruff green; contributor-safe pytest (2178 passed, 3 skipped, 26 deselected); two GitHub-script blocks parsed with `vm.Script`; both workflow YAML files parsed with PyYAML; `git diff --check` green.
- CI checks/reruns/flakes: pending
- Lifecycle/probe evidence: runs `33114270228` and `33113456986` proved empty `workflow_run.pull_requests`; GitHub associated-pulls lookup for `8a3d844` resolved its PR lineage, motivating the trusted `head_sha` fallback.
- Changed contracts: GitHub workflow event contract only
- Unresolved review-thread count: pending
- Residual risks and follow-ups: hosted CODEOWNERS/ruleset #511

## Review Findings

| Severity | Evidence and falsifying check | Gate | Owner/status |
| --- | --- | --- | --- |
| pending | pending | pending | pending |

## Native Review Rounds

| Round | Reviewed head SHA | Trigger | Findings disposition | Stop / exception decision |
| ---: | --- | --- | --- | --- |
| 1 | pending | manual | pending | continue / stop |
| 2 | pending | verification | pending | stop |

## Final Verdict

- Verdict: BLOCK only until hosted CI and independent current-head review complete
- Blocking findings remaining: hosted evidence and independent checker not yet available
- Review rounds used: 0
- Accepted risk or follow-up issue: #511
- Merge owner final gate: rbctmz
- Post-merge sync/branch/worktree/progress cleanup: Codex
