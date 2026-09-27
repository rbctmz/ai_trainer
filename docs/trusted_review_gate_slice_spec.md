# Trusted Review Gate — Slice Spec And Review

- Issue / PR: #512 / #514
- Author / checker / merge owner: Codex / Codex Review + CI / rbctmz
- Date: 2026-08-28
- Candidate head SHA: pending

## Change Class

- Class: A
- Rationale: changes GitHub token permissions and the trusted execution boundary of a write-capable workflow.
- Automatic escalation triggers checked: security boundary and permissions.
- Review budget used: 1 of 2 rounds for phase 2
- Review trigger mode: manual
- Review acceptance head SHA: pending
- Review budget exception: N/A

## Scope

- Behavior that changes: current-head authenticated review evidence is mandatory; write policy loads from `main`; clean comment-only reviews are durable; candidate-controlled direct review triggers become a permissionless two-hop signal.
- Follow-up 2026-09-26: a privileged `status: native review waived` label lets the merge owner pass the first check while Codex is unavailable, without letting acceptance substitute for review. See the follow-up section at the end.
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
- Policy helper contract: historical clean comments are carried to the current ledger commit without qualifying the replacement head.
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
| review signal PR identity | smoke requires exact SHA + source branch + source repository and unique selection | SHA-only lookup can return stacked/shared PRs | one exact candidate or safe skip |
| rebase-safe clean ledger | Node test presents an authenticated historical SHA absent from current commits | helper throws and blocks recomputation | ledger context is carried on current head; current-head count stays zero |

## Follow-up 2026-09-26: native review waiver

Motivation. Codex became unavailable, and the first gate check requires a native
review on the current head. With no native reviewer there is no way to reach a
green gate, so a red gate stopped meaning "this change was not reviewed" and
started meaning "the reviewer is down" — noise instead of signal. The gate also
stopped being merge-blocking in practice, because the hosted ruleset on `main`
requires only the `Contributor-safe pytest` status check.

Why the obvious shortcut was rejected. Relaxing `humanPostBudgetException` by
dropping its `nativeReviewRounds >= MAX_NATIVE_REVIEW_ROUNDS` term would have
turned `review-budget-exception` into a general "skip the review" switch and
would have removed an invariant the Node tests pin by name
(`acceptance cannot substitute for a missing native review`). Budget semantics
stay untouched.

Behavior that changes. A privileged actor may apply `status: native review
waived`. When the current head has no native review, the waiver satisfies the
first check. It does not satisfy the second: `accepted` is still required, and
every later guardrail (unresolved threads, active changes request, budget) still
applies. So neither the waiver nor acceptance can substitute for the other, and
the recorded reason names the waiver explicitly:
`native review waived by merge owner (Codex unavailable); N/2 native round(s); no unresolved threads`.

Head scoping. The waiver is cleared together with `status: review accepted` on
every push, review submission, or authenticated clean-result comment, so one
waiver never silently covers a later head.

RED matrix row.

| Acceptance criterion / invariant | RED test or probe | Expected failure | GREEN evidence |
| --- | --- | --- | --- |
| waiver is not a review substitute | Node tests `a native-review waiver never substitutes for explicit acceptance` and `a native waiver is not enough on its own` | with `hasNativeWaiver` ignored, a waived PR with `accepted: false` reads as ready | waiver passes only the first check; acceptance, thread, changes-requested and budget guardrails still fail closed |

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
- Focused and broad tests: initial contour: Node (18 passed), focused smoke (12 passed), Ruff green, contributor-safe pytest (2178 passed, 3 skipped, 26 deselected). Review delta: Node (19 passed), focused smoke (12 passed), Ruff green, contributor-safe pytest (2178 passed, 3 skipped, 26 deselected), two GitHub-script blocks and both workflow YAML files parsed, `git diff --check` green.
- CI checks/reruns/flakes: six of six hosted checks passed on reviewed head `e235328`. Delta CI first run exposed a pre-existing midnight flake: runner date `2026-08-28` UTC versus canonical athlete date `2026-08-29` Europe/Moscow. `TZ=UTC` reproduced it locally; the test now fixes observation time across that boundary. Delta rerun pending.
- Lifecycle/probe evidence: runs `33114270228` and `33113456986` proved empty `workflow_run.pull_requests`; GitHub associated-pulls lookup for `8a3d844` resolved its PR lineage, motivating the trusted `head_sha` fallback.
- Changed contracts: GitHub workflow event contract only
- Unresolved review-thread count: 2 before delta push/resolution
- Residual risks and follow-ups: hosted CODEOWNERS/ruleset #511

## Review Findings

| Severity | Evidence and falsifying check | Gate | Owner/status |
| --- | --- | --- | --- |
| P1 | surviving historical clean SHA threw after rebase; reproduced by `aaaaaaa` -> `bbbbbbb` test | blocking | fixed locally; `fixed-in` reply pending |
| P2 | SHA-only fallback selected every associated open PR | blocking until triaged | exact run identity + unique selection fixed locally; `fixed-in` reply pending |

## Native Review Rounds

| Round | Reviewed head SHA | Trigger | Findings disposition | Stop / exception decision |
| ---: | --- | --- | --- | --- |
| 1 | `e235328fec` | manual | P1 and P2 reproduced and fixed in one delta | continue with scoped verification |
| 2 | pending | verification | pending | stop |

## Final Verdict

- Verdict: BLOCK until both threads are resolved and delta CI/scoped verification are green
- Blocking findings remaining: two threads awaiting `fixed-in` replies and resolution
- Review rounds used: 1
- Accepted risk or follow-up issue: #511
- Merge owner final gate: rbctmz
- Post-merge sync/branch/worktree/progress cleanup: Codex
