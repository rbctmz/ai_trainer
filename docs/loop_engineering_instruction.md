# Agent Loop Operating Model

This document records the agent-development loop that is actually active in this
repository. It replaces the earlier generic Loop Engineering notes with the
project-specific operating model.

## Current Maturity

AI Trainer uses an issue-first, PR-gated, human-in-the-loop process.

The loop is intentionally not full auto-merge. Agents may implement, test, push,
and open PRs, but code still lands through GitHub checks and an explicit merge
decision.

## Source Of Truth

- `AGENTS.md`: repository rules for coding agents.
- `docs/AI_Feature_Development_Workflow.md`: SpecDD, BDD, TDD, Contract First,
  Self-Review, and Minimal Complexity.
- `.agent/PLANS.md`: ExecPlan format for complex features and refactors.
- GitHub issues: source of task scope, acceptance criteria, and agent state.
- Pull requests: source of review, CI, and merge status.
- GitHub Project `rbctmz/projects/2`: roadmap view synced from issue/PR state.

One-off handoff files should not become permanent docs. If a handoff still has
useful work, convert it into an issue, ExecPlan, or canonical doc update. If the
work is done, delete the handoff.

## Issue Contract

Automation expects non-trivial agent tasks to be GitHub issues with:

- `### ExecPlan`
- `### Acceptance criteria`
- `### Smoke baseline`

An issue with that shape can be queued automatically on open/reopen, or by a
trusted collaborator comment that mentions `@codex`.

Small docs-only fixes and tiny local cleanups may skip the full issue ceremony,
but should still keep the same discipline: clear scope, minimal diff, explicit
verification.

## Automation Loops

### Queue

Workflow: `.github/workflows/codex-assign.yml`

On a structured issue or trusted `@codex` comment, GitHub Actions posts a
canonical implementation prompt, adds `agent: codex` and `status: queued`, and
tells the executor to verify publish capability before doing long work.

The generated prompt requires:

- branch name containing the issue number
- valid `origin`
- pushed branch
- PR against `main`
- `Closes #<issue>` in the PR body
- real PR URL and pushed commit SHA before claiming success

### PR Link

Workflow: `.github/workflows/codex-pr-link.yml`

When a PR opens, the workflow finds linked issues through explicit
`Closes/Fixes/Resolves #<issue>` references in PR body/title or through an
issue marker in the branch name, then moves them to `status: in progress`.

When a linked PR is merged, it closes the issue and removes agent/status labels.

### Watchdog

Workflow: `.github/workflows/codex-watchdog.yml`

Every 30 minutes, queued Codex issues are checked for a linked PR. If no PR
appears after the timeout, the issue is moved to `status: blocked` and the agent
is re-pinged with a retry request.

### Publish Verifier

Workflow: `.github/workflows/codex-publish-verify.yml`

When the Codex connector posts a summary, the workflow verifies that GitHub can
find a real linked PR. If the agent only produced local commits or reports a
publish blocker, the workflow either asks for the missing publish step or marks
the issue blocked for environment recovery.

### Roadmap Sync

Workflow: `.github/workflows/project-roadmap-sync.yml`

Issue and PR state is projected into GitHub Project `rbctmz/projects/2`.
`Todo`, `In Progress`, and `Done` are workflow outputs. Priority, category, and
effort remain planning inputs and are not overwritten by automation.

### Review And CI

Workflows:

- `.github/workflows/ci.yml`
- `.github/workflows/codex-review.yml`

CI runs the contributor-safe test contour. The Codex review workflow requests
review on PRs. A PR is mergeable only after checks are green and the maintainer
accepts the result.

### Claude Code Tag Mode

Workflow: `.github/workflows/claude.yml`

A repository owner, member, or collaborator can invoke the official Claude Code
GitHub Action by writing the complete trigger `@claude` in an issue/PR
conversation comment, an inline PR review comment, or a submitted PR review.
The action receives the surrounding GitHub context, can read CI results, and
posts progress and its final response as `claude[bot]`. It does not run on every
new PR; each invocation must be explicit.

The workflow references only the repository secret
`CLAUDE_CODE_OAUTH_TOKEN`. Its GitHub Actions token is read-only apart from the
OIDC permission required by Anthropic's installed GitHub App, and the job is
blocked for authors whose GitHub association is not `OWNER`, `MEMBER`, or
`COLLABORATOR`. It never uses `pull_request_target` or checks out an untrusted PR
head with repository secrets. The system prompt also prohibits merge,
force-push, live athlete/provider access, and disclosure of application secrets.
Implementation runs have a bounded 60-turn budget. Claude may edit files, run
the contributor-safe pytest contour, and use only read-only git diagnostics
(`status`, `diff`, `log`, `show`, and `rev-parse`); unrestricted shell and git
mutation commands are not exposed. For long RED-to-GREEN tasks, the confirmed
RED gate is committed before implementation and the GREEN fix is committed
separately, so a later bounded-run interruption does not erase the test-first
checkpoint.

For checker handoff, post the detailed findings first and finish with a direct
instruction such as:

    @claude Address the blocking findings above with RED tests before fixes.

GitHub reads comment-triggered workflows from the default branch, so tag mode is
available only after the workflow PR has been merged into `main`.

### Ready-To-Merge Projection

Workflow: `.github/workflows/pr-ready-to-merge.yml`

When a linked PR is open, not draft, mergeable with a clean merge state, and all
current-head check runs are green, GitHub Actions adds `status: ready to merge`
and posts a short readiness comment. If the PR becomes draft, dirty, unlinked,
closed, or receives pending/failing checks, the workflow removes the label.

This is a signal, not an auto-merge. The maintainer still makes the merge
decision.

To smoke-test this projection without touching product code, open a small
structured docs-only issue and PR whose branch name contains the issue number.
After CI is green, the linked PR should receive `status: ready to merge`
automatically. If the label is absent, inspect the `PR ready to merge` workflow
run before merging; missing PR write permissions will show as a 403 while adding
labels or comments. A successful smoke test shows a post-CI `workflow_run` and
the label without using `workflow_dispatch` or manually editing labels.

### CI Failure Loop

Workflow: `.github/workflows/codex-ci-failure.yml`

When the `CI` workflow concludes `failure`, `timed_out`, or `action_required` on
an open PR, GitHub Actions posts one structured comment for that workflow run.
The comment includes the workflow run URL, failed job names when GitHub exposes
them, and an `@codex` ping when the PR is agent-owned. A PR is treated as
agent-owned when its branch starts with `codex/` or one of its linked issues has
`agent: codex`.

A `cancelled` conclusion is intentionally ignored: cancelled runs are usually
superseded by a newer push or stopped on purpose, not an actual test failure, so
treating them as actionable would post a misleading "CI failure" comment and an
unnecessary `@codex` ping.

This closes the "PR exists but CI is red" gap in the loop. The agent still needs
to inspect the failure and push a fix; the workflow only turns the failure into
an actionable prompt.

## Maker-Checker In This Repo

Current maker-checker is practical, not theatrical:

- Maker: Codex/Claude/local developer implements the issue.
- Checker: tests, CI, Codex Review, GitHub issue automation, and human review.
- Final authority: maintainer merge decision.

Do not ask the same agent to be the only reviewer of its own work for risky
changes. At minimum, run the contributor-safe tests and inspect the diff against
the acceptance criteria.

## Definition Of Done For Agent Work

An agent task is not complete until:

- implementation is on a branch
- relevant tests were run and reported
- branch is pushed to GitHub
- PR exists against `main`
- PR body links the issue with `Closes #<issue>`
- checks are green or blockers are explicit
- `status: ready to merge` is present when the PR satisfies the readiness gate
  (or the reason it is absent is understood)
- merge decision is made by a human

For local maintenance without an issue, the local equivalent is:

- diff is scoped
- docs/code are current
- verification is appropriate for the change
- no unrelated files are staged

## Current Boundaries

The automation can move issues through queue, in-progress, blocked, and done
states, but it does not guarantee product correctness. Product correctness still
comes from the repo workflow: SpecDD, BDD, TDD, contract-first API boundaries,
smoke tests, and review.

The automation also cannot fix missing credentials or unavailable GitHub access.
In that case it must block explicitly instead of looping forever.
