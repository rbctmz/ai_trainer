# Codex Executor Publish Fail-Fast

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

This document must be maintained in accordance with `.agent/PLANS.md`.

## Purpose / Big Picture

After this change, the repository should stop treating a missing executor publish remote as a normal retry condition. When Codex finishes local implementation work but reports that `origin` is missing, the issue should move to `status: blocked` immediately with a precise infrastructure diagnosis, instead of bouncing between retry comments and watchdog re-queues. This does not solve the external executor environment by itself; it makes the failure honest, fast, and operationally cheap.

## Progress

- [x] (2026-06-29 14:38Z) Confirmed that issue `#10` now reaches the new publish-verifier path and emits a publish-retry comment, but still loops because the external executor repeatedly reports `origin` is missing.
- [x] (2026-06-29 14:40Z) Implemented a fatal publish-blocker branch in `.github/workflows/codex-publish-verify.yml` that recognizes missing-`origin` summaries, moves the issue to `status: blocked`, and posts a dedicated infrastructure-blocker comment.
- [ ] Validate the workflow YAML, publish the branch, and open a PR that clearly scopes this as the repo-owned mitigation slice of issue `#26`.

## Surprises & Discoveries

- Observation: the repository-side verifier now works end-to-end, but its generic retry path is too optimistic for one specific class of failures: the executor explicitly says it cannot push because `origin` does not exist.
  Evidence: issue `#10` received both `**Publish verification failed**` and later repeated connector summaries saying `fatal: 'origin' does not appear to be a git repository`, followed by a watchdog block.

## Decision Log

- Decision: treat missing-`origin` executor summaries as a fatal infrastructure blocker, not as a normal publish retry.
  Rationale: a retry cannot succeed without a publish target, so keeping the issue queued only wastes executor cycles and produces duplicate local-only commits.
  Date/Author: 2026-06-29 / Codex

- Decision: keep this slice repository-owned and explicitly partial relative to issue `#26`.
  Rationale: the true fix for automatic publish capability may live in the external executor platform, which this repository cannot reconfigure directly. The repo can still improve truthfulness and stop futile retries.
  Date/Author: 2026-06-29 / Codex

## Outcomes & Retrospective

Pending validation and publication.

## Context and Orientation

`.github/workflows/codex-publish-verify.yml` runs on `issue_comment.created` and inspects `chatgpt-codex-connector[bot]` summary comments on queued Codex issues. Its job is to decide whether a real linked PR exists; if not, it currently posts a generic retry comment. That behavior is useful for transient publish misses, but it is wrong when the executor explicitly says it has no `origin` remote. In that case the system already knows the publish step cannot succeed by retrying the same environment.

The live example is issue `#10`. The repository automation now correctly queues the work, recognizes the missing PR, and posts a publish-retry comment. The external executor then replies that it committed locally on branch `codex/issue-10-operational-states` but cannot run `git push -u origin ...` because `origin` does not exist in that checkout. The repository needs to classify that as a platform blocker immediately.

## Plan of Work

Update `.github/workflows/codex-publish-verify.yml` in one narrow place. After summary heading detection and before the generic retry path, detect known fatal publish-blocker phrases such as `no configured origin remote`, `origin does not appear to be a git repository`, or text saying the branch could not be pushed to GitHub. If any of those patterns appear and no linked PR exists, the workflow should add `status: blocked`, remove `status: queued`, and post one dedicated GitHub Actions comment explaining that the executor environment cannot publish. Keep the existing idempotence guard so repeated runs do not spam duplicate blocker comments inside the same queue cycle.

Do not change the linked-PR matcher or the generic retry behavior for other cases. This slice is intentionally about early classification of a known infrastructure blocker, not about redesigning the publish state machine.

## Concrete Steps

Work from the repository root:

    cd /Users/gregkisel/Developer/ai_trainer
    git switch -c codex/publish-fail-fast-blocker

Edit `.github/workflows/codex-publish-verify.yml` and add this ExecPlan. Then validate the workflow as YAML and check for whitespace regressions:

    python3 -c "from pathlib import Path; import yaml; yaml.safe_load(Path('.github/workflows/codex-publish-verify.yml').read_text())"
    git diff --check

Stage only:

    .github/workflows/codex-publish-verify.yml
    docs/codex_executor_publish_execplan.md

Publish the branch and open a PR that references issue `#26` as a partial infrastructure mitigation rather than a full close.

## Validation and Acceptance

Validation is primarily behavioral. Read the workflow and confirm that a summary comment containing the known missing-`origin` phrases now takes the blocker path before the generic retry path. The resulting issue transition must be:

1. `status: blocked` added,
2. `status: queued` removed,
3. one GitHub Actions comment explaining that the executor lacks a publish target.

This does not satisfy the full external-environment acceptance of issue `#26`, but it does satisfy the repository-owned fail-fast requirement: known impossible publish attempts stop looping immediately.

## Idempotence and Recovery

The blocker comment is guarded per queue cycle. If GitHub replays the same comment event or the connector posts duplicate summaries in the same cycle, the workflow should not add duplicate `Publish environment blocked` comments. If the external executor environment is later fixed, a trusted human can still re-queue the issue with a fresh `@codex` comment; the normal queue path remains intact.

## Artifacts and Notes

Live evidence that motivated this slice:

    issue #10 connector summary:
    * Commit SHA: c7226fd2fa1425bdbe640d1ea10a4160c1891277
    * push failed because `origin` does not appear to be a git repository

    issue #10 follow-up:
    * GitHub Actions posted `Publish verification failed`
    * watchdog later posted `@codex please retry`

## Interfaces and Dependencies

This slice stays inside GitHub Actions and uses the existing `actions/github-script@v7` runtime with `issues: write` and `pull-requests: read`. It depends on the current queue-cycle heuristics already present in `.github/workflows/codex-publish-verify.yml` and does not add new labels or external services.
