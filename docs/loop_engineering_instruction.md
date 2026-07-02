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

When a PR opens, the workflow finds linked issues through PR body, PR title, or
branch name and moves them to `status: in progress`.

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
