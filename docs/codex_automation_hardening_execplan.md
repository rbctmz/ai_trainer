# Codex Automation Hardening

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

This document must be maintained in accordance with `.agent/PLANS.md`.

## Purpose / Big Picture

After this change, a structured agent task issue in this repository will move through a more reliable GitHub-side state machine: when a trusted human writes `@codex` on an issue, the repository should re-queue the task; when a PR clearly references the issue, the issue should move to `in progress`; when no PR appears after a queue window, a watchdog should mark the issue blocked and retry; and when the linked PR merges, the issue should close cleanly. The user-visible proof is issue `#17`: today it stayed open with `status: needs triage` even though Codex claimed it had opened a PR. After this hardening, the repository workflows should make that failure mode much less likely.

## Progress

- [x] (2026-06-28 19:54Z) Read `.agent/PLANS.md`, inspected the tracked GitHub automation files in `.github/workflows/`, and confirmed the current state on live issue `#17`.
- [x] (2026-06-28 19:57Z) Created the hardening edits for `codex-assign.yml`, `codex-watchdog.yml`, and `codex-pr-link.yml`.
- [x] (2026-06-28 19:57Z) Parsed all three workflow YAML files locally with `python3 + yaml.safe_load`.
- [x] (2026-06-28 19:59Z) Staged and committed the automation changes on `codex/automation-hardening`, pushed the branch, and opened PR `#18`.

## Surprises & Discoveries

- Observation: the repository already contains more automation than expected: `codex-pr-link.yml` and `codex-watchdog.yml` are already tracked in `main`.
  Evidence: `git ls-files .github/workflows .github/ISSUE_TEMPLATE` shows both files in the tracked tree.

- Observation: live issue `#17` is still `open` with `status: needs triage`, even though comments show multiple `@codex` pings and a Codex summary claiming a PR was opened.
  Evidence: `gh api repos/rbctmz/ai_trainer/issues/17` returned `state: open` and labels `status: needs triage`; `gh api repos/rbctmz/ai_trainer/issues/17/comments` shows the Codex summary comment but no successful state transition.

- Observation: the local shell does not provide `python`; workflow validation had to use `python3`.
  Evidence: `python - <<'PY' ...` failed with `zsh:1: command not found: python`, while the same parser check succeeded with `python3`.

## Decision Log

- Decision: keep the fix entirely on the repository side, inside GitHub Actions and issue/PR conventions, rather than trying to build a new external orchestrator.
  Rationale: the failure mode is already visible inside GitHub (`issue -> comments -> missing PR -> wrong labels`). Tightening the repository workflows gives immediate leverage without introducing a second automation system.
  Date/Author: 2026-06-28 / Codex

- Decision: accept only trusted human `issue_comment` pings (`OWNER`, `MEMBER`, `COLLABORATOR`) as re-queue triggers.
  Rationale: this prevents comment loops when `github-actions[bot]` or `chatgpt-codex-connector[bot]` themselves write `@codex` comments.
  Date/Author: 2026-06-28 / Codex

- Decision: treat a PR as linked to an issue only when the PR body, PR title, or PR branch contains an issue-specific marker.
  Rationale: the previous `ref.startsWith('codex/')` heuristic was too broad and could mark unrelated queued issues as `in progress` merely because some Codex branch existed in the repository.
  Date/Author: 2026-06-28 / Codex

## Outcomes & Retrospective

The hardening slice is now implemented and published for review in PR `#18`. The repository-side state machine is materially stronger than before: trusted human `@codex` comments can re-queue an already-open issue, the watchdog no longer treats any `codex/*` branch as proof of linkage, and PR open/merge events use richer issue extraction than “body contains Closes #N” alone. The remaining work is merge-and-observe on a live issue such as `#17`.

## Context and Orientation

The repository already has a small GitHub Actions layer for agent-driven work.

`/.github/ISSUE_TEMPLATE/agent_task.yml` is the structured issue form for Codex tasks. It guarantees the issue body contains sections like `### ExecPlan`, `### Acceptance criteria`, and `### Smoke baseline`.

`/.github/workflows/codex-assign.yml` currently listens only to `issues.opened` and `issues.reopened`. It posts a canonical `@codex Please implement this task...` comment and tries to move the issue to `status: queued`.

`/.github/workflows/codex-watchdog.yml` runs every 30 minutes and looks for open issues labeled `status: queued` and `agent: codex`. Its job is to detect a stalled queue and mark the issue blocked. Today it contains a weak PR matcher: any PR whose branch starts with `codex/` can be treated as “linked”, even if that PR has nothing to do with the issue being inspected.

`/.github/workflows/codex-pr-link.yml` reacts to PR open/close events and tries to move issues to `status: in progress` or close them on merge. Today it only looks at `closes/fixes/resolves #N` tokens in the PR body.

Issue `#17` is the concrete motivating example. It demonstrates two gaps at once: there is no reliable `issue_comment -> requeue` path for an already-open issue, and there is no strong proof that a claimed Codex PR actually exists and is linked to the issue.

## Plan of Work

The first edit is `/.github/workflows/codex-assign.yml`. Expand its triggers to include `issue_comment.created`. Replace the split logic with one canonical `github-script` step that first determines whether the event is actionable. For `issues.opened` and `issues.reopened`, actionable means the issue body contains the `### ExecPlan` section and the issue is not a PR. For `issue_comment.created`, actionable means the issue body contains `### ExecPlan`, the comment is on a real issue rather than a PR, the comment author is a trusted human association, and the comment body contains `@codex`. When actionable, the workflow should post the canonical implementation comment and move the issue to `status: queued` plus `agent: codex`, while removing `status: needs triage`, `status: blocked`, and `status: in progress`.

The second edit is `/.github/workflows/codex-watchdog.yml`. Define a stricter “linked PR” rule. A PR should count as linked to issue `N` only if at least one of these holds: its body contains `closes/fixes/resolves #N`; its title contains `#N`; or its branch name contains a stable issue marker such as `issue-17`, `issue_17`, `-17-`, or `/17-`. Remove the current broad `ref.startsWith('codex/')` shortcut, because that can incorrectly move unrelated issues to `in progress`.

The third edit is `/.github/workflows/codex-pr-link.yml`. Use the same issue-extraction logic as the watchdog so that “PR opened” and “PR merged” apply to the same issue set. On PR open, add `status: in progress` and remove `status: queued`, `status: blocked`, and `status: needs triage`. On PR merge, remove `status: in progress`, `status: queued`, `status: blocked`, and `agent: codex`, then close the issue with `state_reason: completed`. Keep the logic additive and idempotent so reruns are harmless.

The final pass is validation. Parse the YAML locally so syntax errors are caught before commit. Then inspect issue `#17` again and explain what the new behavior would be: a trusted `@codex` comment would re-queue it, the watchdog would stop treating unrelated `codex/*` branches as linked, and the issue would move to `in progress` only when a PR is truly linked.

## Concrete Steps

Work from the repository root:

    cd /Users/gregkisel/Developer/ai_trainer

Create or update:

    .github/workflows/codex-assign.yml
    .github/workflows/codex-watchdog.yml
    .github/workflows/codex-pr-link.yml
    docs/codex_automation_hardening_execplan.md

Validate syntax with a local YAML parser after editing. The simplest acceptable check is:

    python - <<'PY'
    import pathlib, yaml
    for path in [
        ".github/workflows/codex-assign.yml",
        ".github/workflows/codex-watchdog.yml",
        ".github/workflows/codex-pr-link.yml",
    ]:
        with open(path, "r", encoding="utf-8") as fh:
            yaml.safe_load(fh)
        print("OK", path)
    PY

Expected output is three `OK ...` lines, one per workflow file.

## Validation and Acceptance

Acceptance is behavioral.

First, the workflow files must parse locally and the repository must remain on a clean feature branch except for the intended edits.

Second, the logic must cover the live issue `#17` case:

- Given an already-open agent task issue with `### ExecPlan`, when the owner writes `@codex` in a new issue comment, then `codex-assign.yml` should be eligible to re-queue it and restore `status: queued` plus `agent: codex`.
- Given a queued issue, when no actually linked PR appears within the watchdog window, then `codex-watchdog.yml` should mark it `status: blocked` and write a retry comment.
- Given a PR whose body or branch clearly references the issue number, when the PR opens, then `codex-pr-link.yml` should move the issue to `status: in progress`.
- Given that same PR merges, when the close event arrives, then the issue should close automatically and shed the queue/progress labels.

Local structural validation is already complete:

    OK .github/workflows/codex-assign.yml
    OK .github/workflows/codex-watchdog.yml
    OK .github/workflows/codex-pr-link.yml

## Idempotence and Recovery

These workflow edits are safe to apply repeatedly because they only change repository metadata rules. If a script block is wrong, rerun the YAML parser, edit the file, and re-parse; there is no data migration. GitHub-side label updates use additive calls plus defensive `try/catch` removals, so rerunning the workflows should not break issue state.

## Artifacts and Notes

The live evidence that motivates this work:

    gh api repos/rbctmz/ai_trainer/issues/17
    -> state: open
    -> labels: type: enhancement, status: needs triage, area: ai-coaching

    gh api repos/rbctmz/ai_trainer/issues/17/comments
    -> contains owner @codex pings
    -> contains Codex summary claiming “Opened PR”
    -> no actual linked PR was found

Delivery artifact:

    Branch: codex/automation-hardening
    PR: https://github.com/rbctmz/ai_trainer/pull/18

## Interfaces and Dependencies

Use GitHub Actions `actions/github-script@v7` in all three workflow files. Keep the implementation in JavaScript embedded in the workflow because that matches the existing repository style and avoids creating a second scripting entrypoint.

The workflows depend on these repository labels already existing, which they do today:

- `status: needs triage`
- `status: queued`
- `status: in progress`
- `status: blocked`
- `agent: codex`

The issue parsing logic depends on the structured issue template in `/.github/ISSUE_TEMPLATE/agent_task.yml`, especially the presence of `### ExecPlan`, `### Acceptance criteria`, and `### Smoke baseline`.

Change note: Created this ExecPlan to guide a multi-workflow repository automation hardening change after observing that issue `#17` did not move through the intended queue → PR → merge lifecycle.
