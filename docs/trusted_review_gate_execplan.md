# Activate the trusted current-head review gate

This ExecPlan is a living document and must be maintained in accordance with `.agent/PLANS.md`. It completes issue #512 after bootstrap PR #513 placed the required policy helpers on `main`.

## Purpose / Big Picture

After this change, the write-capable PR readiness automation evaluates only a review result tied to the current pull-request head and loads every policy helper from the trusted default branch. A contributor cannot make a candidate branch execute modified review policy with a token that can write labels or commit statuses. A maintainer can observe the behavior by pushing a new head, seeing acceptance removed, completing at most two Codex review rounds, and applying `status: review accepted` only after the current head has an authenticated result.

## Progress

- [x] (2026-08-28 18:45Z) Merged bootstrap PR #513 and fast-forwarded local `main` to `6ddc0d3`.
- [x] (2026-08-28 18:50Z) Classified phase 2 as Class A because it changes a security boundary and write permissions.
- [x] (2026-08-28 19:00Z) Added RED smoke contracts for trusted triggers, default-branch checkout, current-head counting, and clean-result persistence; focused smoke failed with `1 failed, 4 passed` because `main` lacked `pull_request_target`.
- [x] (2026-08-28 19:18Z) Implemented the trusted workflow, permissionless review signal, current-head gate, durable clean-result ledger, and associated-commit fallback.
- [x] (2026-08-28 19:22Z) Ran Node policy tests, focused smoke tests, YAML/inline-JS parsing, Ruff, the contributor-safe suite, and `git diff --check` locally.
- [x] (2026-08-28 21:58Z) Published draft PR #514; all six hosted checks passed on `e235328`.
- [x] (2026-08-29 10:05Z) Reproduced review round 1 findings: historical clean comments raised after rebase, and one signal commit could select multiple associated PRs.
- [x] (2026-08-29 10:12Z) Added RED tests and fixed both findings locally; focused Node and smoke contours are green.
- [ ] Push the delta, resolve both threads with `fixed-in <sha>`, and collect one scoped verification review.

## Surprises & Discoveries

- **Observed**: run `33114270228` executed the candidate workflow body but checked out the old helper module from `main`, then failed with `TypeError: persistCleanReviewStatuses is not a function`.
  **Inferred**: a single PR cannot both introduce a helper on `main` and require that helper from the trusted ref during its own checks. The cheapest falsifying check was to split the helper into a bootstrap PR and verify it existed on `main` before activating the workflow.
  **Verified by**: PR #513 merged as `6ddc0d3`; `main:.github/scripts/review-gate.cjs` now exports `persistCleanReviewStatuses` and `countNativeReviewRoundsForHead`.

- **Observed**: direct `pull_request_review` and `pull_request_review_comment` runs used the candidate workflow definition while the job token had write permissions.
  **Inferred**: retaining those triggers would leave candidate-controlled YAML on the privileged path even if the helper checkout used `main`. The cheapest falsifying check is a static workflow contract that rejects both direct triggers in the write-capable workflow and requires a separate permissionless signal workflow.
  **Verified by**: the RED contract failed on `main`; GREEN must prove that only the signal workflow receives direct review events and that it has `permissions: {}`, no checkout, and no secrets.

- **Observed**: historical `pull_request_review` runs `33114270228` and `33113456986` expose an empty `workflow_run.pull_requests` array even though `workflow_run.head_sha` is the reviewed PR commit.
  **Inferred**: consuming only `workflow_run.pull_requests` would silently defer review invalidation to the 15-minute repair schedule. The cheapest falsifying check queried the associated-pulls endpoint for run head `8a3d844`, which resolved the PR lineage.
  **Verified by**: the trusted consumer falls back to `listPullRequestsAssociatedWithCommit(run.head_sha)` and accepts only open PRs returned by GitHub.

- **Observed**: `persistCleanReviewStatuses` threw when a surviving authenticated clean comment named a commit removed by rebase.
  **Inferred**: the historical round could block every later recomputation instead of merely consuming budget. The falsifying test supplied reviewed SHA `aaaaaaa` with only replacement head `bbbbbbb` in the PR.
  **Verified by**: the RED test raised the exact production exception; GREEN carries the immutable `aaaaaaa` ledger context on the current head while current-head round counting remains zero.

- **Observed**: the associated-commit fallback accepted every open PR returned for a signal SHA.
  **Inferred**: stacked/shared commits could invalidate acceptance on a PR that did not receive the review event.
  **Verified by**: the trusted consumer now accepts exactly one candidate matching run SHA, source branch, and source repository; zero or multiple exact candidates are skipped with a warning.

## Decision Log

- Decision: deliver issue #512 in two PRs: bootstrap helpers first, privileged workflow second.
  Rationale: the trusted default branch must contain the helper contract before a candidate workflow can load it without a bootstrap bypass.
  Date/Author: 2026-08-28 / Codex.

- Decision: direct review events run a separate permissionless `PR review signal` workflow; its completed `workflow_run` wakes the write-capable readiness workflow loaded from the default branch.
  Rationale: candidate-controlled workflow YAML must never receive a write token, checkout, or secrets, while a two-hop signal preserves prompt invalidation instead of waiting for the scheduled repair path.
  Date/Author: 2026-08-28 / Codex.

- Decision: preserve the two-round budget and do not add an automatic review trigger.
  Rationale: issue #512 explicitly excludes budget changes and repository policy requires manual review ownership.
  Date/Author: 2026-08-28 / Codex.

- Decision: disambiguate review signals from trusted GitHub run identity rather than accepting every associated PR.
  Rationale: SHA alone is not a stable PR identity; SHA + source branch + source repository must resolve uniquely or the write path fails safe and leaves scheduled reconciliation as recovery.
  Date/Author: 2026-08-29 / Codex.

## Outcomes & Retrospective

The activation branch passed the full local and hosted contours. Independent review round 1 found two reproducible boundary cases; both now have RED/GREEN coverage. A scoped verification review, maintainer acceptance, and merge remain.

## Context and Orientation

`.github/workflows/pr-ready-to-merge.yml` owns two label-writing jobs. `.github/scripts/review-gate.cjs` contains deterministic policy helpers and is now present on `main` after PR #513. `.github/scripts/review-gate.test.cjs` covers review counting, clean-result authentication, durable status-ledger behavior, and gate decisions. `tests/smoke/test_native_codex_review_integration.py` is the repository-level workflow contract. `docs/loop_engineering_instruction.md` explains the human review loop.

An authenticated clean review may arrive as a connector-authored issue comment rather than a submitted review. The workflow persists such a round as a uniquely keyed successful commit status before counting it. Historical rounds continue to consume the budget, but only a submitted review or clean-result marker matching the current head can satisfy acceptance.

## Plan of Work

First extend `tests/smoke/test_native_codex_review_integration.py` so the current workflow fails the trusted-trigger and current-head contracts. Then add `.github/workflows/pr-review-signal.yml` as a permissionless, checkout-free listener for direct review events. Update `.github/workflows/pr-ready-to-merge.yml`: replace `pull_request` with `pull_request_target`, consume completion of the signal workflow, resolve an empty `workflow_run.pull_requests` list from the run's GitHub-associated head commit, add the connector-only `issue_comment` trigger, set least-privilege job permissions including `statuses: write`, explicitly check out `github.event.repository.default_branch`, fetch comments and durable statuses, and pass both total and current-head round counts to the policy helper. The ready projection must use the same evidence and refetch the latest head and privileged labels before publishing.

Finally update `docs/loop_engineering_instruction.md` to explain the permissionless signal and trusted default-branch recomputation. Keep CODEOWNERS and hosted ruleset changes in #511.

## Concrete Steps

Work from `/Users/gregkisel/Developer/ai_trainer` on branch `codex/issue-512-trusted-review-workflow`.

Run the focused RED contract:

    ai_trainer_env/bin/python -m pytest tests/smoke/test_native_codex_review_integration.py -q

After implementation run:

    node --test .github/scripts/review-gate.test.cjs
    ai_trainer_env/bin/python -m pytest tests/smoke/test_native_codex_review_integration.py tests/smoke/test_dev_workflow_v2_docs.py -q
    ai_trainer_env/bin/python -m ruff check .
    ai_trainer_env/bin/python -m pytest -m "not live and not debug and not e2e" tests/
    git diff --check

Also parse every `actions/github-script` block with Node's `vm.Script` so invalid inline JavaScript cannot reach hosted Actions.

## Validation and Acceptance

The RED smoke must prove that current `main` still exposes candidate-controlled direct review triggers. GREEN requires no `pull_request` or direct review trigger in the privileged workflow, a permissionless signal workflow for direct review events, an explicit default-branch checkout, `pull_request_target` synchronization invalidation, connector-authenticated clean comments, durable clean-round statuses, exact current-head counting, and unchanged two-round budget behavior.

Hosted acceptance is a small PR whose current head has an authenticated Codex result and an owner-applied acceptance label. A historical review alone must keep `Review gate` red after a push. The workflow must never auto-request another Codex review and must never merge automatically.

## Idempotence and Recovery

Every recomputation is safe to retry. Clean-result commit statuses are keyed by connector comment ID and reviewed SHA; an existing context is reused rather than duplicated. Label operations tolerate absent labels. Stale evaluation is abandoned after refetching the head and privileged labels.

Rollback is a normal revert of the activation PR. Durable clean-review statuses remain immutable audit evidence but the old workflow ignores them. No athlete database, provider data, or repository secret is changed.

## Artifacts and Notes

Issue: #512. Bootstrap: PR #513 / merge `6ddc0d3`. Follow-up CODEOWNERS and hosted ruleset configuration remain #511.

## Interfaces and Dependencies

The helper contract loaded from `.github/scripts/review-gate.cjs` must export `countNativeReviewRounds`, `countNativeReviewRoundsForHead`, `persistCleanReviewStatuses`, `evaluateReviewGate`, `shouldInvalidateAcceptance`, `latestLabelActor`, `isPrivilegedRepositoryPermission`, `cleanNativeReviewHead`, `selectReadinessStatusComments`, `MAX_NATIVE_REVIEW_ROUNDS`, and `READY_MARKER`. No new dependency is introduced. The only persistent repository-side artifact is an authenticated successful commit status with context `review-gate/codex-clean/<comment-id>:<reviewed-sha-prefix>`.
