# Agent Loop Operating Model

This document records the agent-development loop that is actually active in this
repository. It replaces the earlier generic Loop Engineering notes with the
project-specific operating model.

## Current Maturity

AI Trainer uses an issue-first, PR-gated, human-in-the-loop process.

The loop is intentionally not full auto-merge. Agents may implement, test, push,
and open PRs, but code still lands through GitHub checks and an explicit merge
decision.

## Tried And Rejected

AI Trainer does not use a background "consciousness worker" that continuously
creates review work, or an autonomous self-improvement loop in which an agent
rewrites its own identity, skills, or notes. These mechanisms were tried and
rejected: roughly 40 edits across more than 20 sessions produced no measurable
improvement, while the review queue accumulated stale state.

This rejection does not apply to the active engineering loop. The validated
path remains issue-first and PR-gated: an issue defines scope, an agent may
implement and verify it, GitHub checks review the result, and a human makes the
merge decision. Future automation must strengthen that evidence chain rather
than recreate unattended self-evolution.

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

Automation expects tracked agent tasks to be GitHub issues with:

- `### Change Class`
- `### ExecPlan`
- `### Non-goals`
- `### Acceptance criteria`
- `### Smoke baseline`

Class A must provide the ExecPlan path or state that it will be created. Class B
and Class C keep the heading for a stable automation contract but may write
`N/A` plus a short rationale. Class A must list explicit non-goals; Class B/C
may use `N/A` with a reason. Only the three recognized Change Class values are
queued. An issue with that shape can be queued
automatically on open/reopen, or by a trusted collaborator comment that mentions
`@codex`.

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

When a PR is merged, the workflow closes only issues named by an explicit
`Closes/Fixes/Resolves #<issue>` reference in the PR body/title and removes
their agent/status labels. A branch marker links milestone work for progress
tracking but cannot close a larger epic by itself.

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

CI runs the contributor-safe test contour through `.github/workflows/ci.yml`.
Codex review uses the native GitHub integration configured at
`https://chatgpt.com/codex/settings/code-review`. Keep **Code review** enabled and
**Automatic reviews** disabled for this repository: the merge owner requests one
review from the connected GitHub account of the maintainer only after the candidate head,
documentation, evidence bundle, and CI are stable. Do not mix automatic and
manual triggers, and do not create an Actions workflow that posts
`@codex review`: its author is `github-actions[bot]`, not the connected
maintainer account. The exact maintainer command is `@codex review`; every
submitted native review counts against the two-round budget even when it is clean
or repeats a head SHA. Dismissing a submitted review does not refund its round.

After the first review, every finding receives `fixed-in <sha>`, `follow-up #N`,
or `disputed: <reason>`. One verification review is allowed. After the second
native pass, fix remaining P0/P1 and blocking P2 findings with targeted evidence,
resolve or own every thread, and stop requesting full native reviews unless the
merge owner records a new architecture boundary and applies the documented
budget exception. A later docs-only outcome push does not justify another
review; record final process metrics after merge instead.

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

The workflow has two independent gates. `Review gate` passes only when the merge
owner applies `status: review accepted`, all review threads are resolved, and no
more than two native Codex reviews were submitted. A third pass adds
`status: review budget exceeded`; it needs a documented merge-owner decision and
the `review-budget-exception` label. Every new push removes review acceptance and
readiness, so acceptance is always bound to the current head.

When a linked PR is open, not draft, has no merge conflict, passes the accepted
review gate, and all other current-head check runs are green, GitHub Actions adds
`status: ready to merge`. One bot comment is updated in place instead of posting
one comment per head SHA. Review submission and review-comment events recompute
the projection; after resolving the final thread, the merge owner applies review
acceptance to trigger the final recomputation. If the PR becomes draft,
conflicted, unlinked, closed, loses acceptance, gains an unresolved thread, or
receives pending/failing checks, the workflow removes readiness.

GitHub Actions has no direct trigger for reopening an existing review thread.
The repository ruleset therefore remains the immediate merge guard through
`required_review_thread_resolution`, while a 15-minute scheduled reconciliation
removes stale readiness labels and neutralizes legacy per-head Ready comments.

This is a signal, not an auto-merge. The maintainer still makes the merge
decision.

To smoke-test this projection without touching product code, open a small
structured docs-only issue and PR whose branch name contains the issue number.
Green CI without `status: review accepted` must not produce readiness. Apply
acceptance only after review threads are resolved; the linked PR should then
receive `status: ready to merge`. Push one harmless follow-up commit and verify
that both acceptance and readiness disappear. A third native review must keep
the gate red until a documented exception is applied. If the projection is
wrong, inspect the `PR ready to merge` workflow; missing PR write permissions
show as a 403 while adding labels or updating its single status comment.

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

## Review Evidence Bundle

The author publishes **one bundle** for the current head instead of scattering
proof across status comments. It contains:

- PR number, branch, and exact **head SHA**;
- change class, scope, non-goals, and **changed invariants**;
- commands and outcomes for **focused and broad tests**, or for Class C the
  targeted verification with broad tests marked `N/A` and a reason;
- CI checks for the same head SHA, including reruns or flakes;
- lifecycle/probe evidence for new state, cursor, reset, rollback, or idempotency;
- changed public contracts and compatibility decision;
- findings by P0/P1/P2/P3 and the **unresolved review-thread count**;
- residual risks, owned follow-ups, and the proposed verdict.

The bundle is class-aware: Class C does not invent broad suites or persistence
probes that its change does not warrant, while Class A cannot omit them when its
risk requires them. A checker validates the bundle against the diff and
acceptance criteria, not merely against the author's summary. If the head SHA
changes materially, refresh the affected evidence and state what was not rerun.

## Merge And Cleanup Ownership

- The author owns implementation, evidence, responses, and resolution of review
  threads after each finding has been addressed or explicitly deferred.
- The checker owns a severity-labelled verdict and confirms that blocking
  findings are closed on the current head.
- The **merge owner** performs the last gate: linked issue,
  `mergeStateStatus=CLEAN` from `gh pr view`,
  required checks green on the current SHA, zero unresolved blocking threads,
  and an explicit human merge decision.
- Never use `--admin` to bypass checks, reviews, or branch protection.
- After merge, the merge owner or delegated author must sync local `main`, delete
  only the known task branch/worktree after confirming it has no dependent work,
  and update the issue/ExecPlan progress record.

Cleanup is part of the task, not permission to remove unrelated branches,
worktrees, local changes, or persisted athlete data.

## Process Metrics

Definitions and the append-only retrospective table live in
`docs/engineering_process_metrics.md`. Record the metrics after tracked Class A
and Class B work plus representative Class C work. Revisit thresholds and the
review budget after 5–10 PRs; do not claim faster delivery from timestamps that
mix active work with human or quota wait.

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
