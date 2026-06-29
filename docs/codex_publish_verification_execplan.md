# Codex publish verification loop

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

This document must be maintained in accordance with `.agent/PLANS.md`.

## Purpose / Big Picture

After this change, the repository should stop treating a Codex summary comment as proof that a task is publish-complete. A queued issue such as `#10` should either advance because a real GitHub pull request exists, or automatically get a targeted `@codex` retry comment that asks the agent to finish the push-and-PR step. The user-visible proof is simple: when Codex leaves a summary comment without a linked PR, the repository posts a follow-up publish reminder immediately instead of waiting for a human to notice the gap.

## Progress

- [x] (2026-06-29 08:25Z) Confirmed the failure mode on issue `#10`: `chatgpt-codex-connector[bot]` posted a summary comment with commit `5dfbacb`, but no linked PR exists and the SHA is not visible on GitHub.
- [x] (2026-06-29 08:28Z) Added `.github/workflows/codex-publish-verify.yml` to watch Codex summary comments and post one publish-retry `@codex` comment per queue cycle when no linked PR exists.
- [x] (2026-06-29 08:28Z) Strengthened `.github/workflows/codex-assign.yml` so the canonical task prompt now requires a pushed branch, a PR against `main`, `Closes #<issue>` in the PR body, and a final comment that includes the real PR URL plus pushed commit SHA.
- [x] (2026-06-29 08:29Z) Validated both workflow files with Python YAML parsing and checked `git diff --check` for formatting regressions.
- [x] (2026-06-29 08:31Z) Staged only the workflow and ExecPlan files, committed them on `codex/automation-publish-guard`, pushed the branch, and opened PR `#19`.
- [x] (2026-06-29 08:47Z) Confirmed the first live post-merge probe on issue `#10` missed the retry because the new connector used a `### Summary` heading instead of `**Summary**`.
- [ ] Expand the publish-verifier matcher to accept both summary heading styles, publish the patch, and re-run issue `#10`.

## Surprises & Discoveries

- Observation: the issue loop already verifies queueing, PR linking, and timeout blocking, but it never inspects Codex completion comments for evidence that the publish step actually happened.
  Evidence: issue `#10` remained labeled `status: queued` / `agent: codex` after a summary comment that claimed `Committed changes on the current branch: 5dfbacb ...`, and `gh api repos/rbctmz/ai_trainer/commits/5dfbacb` returned `No commit found for SHA: 5dfbacb`.

- Observation: the first version of the publish verifier was too strict about summary formatting. It only matched `**Summary**`, but the newer connector emitted `### Summary`, so the workflow completed successfully while skipping the retry comment.
  Evidence: GitHub Actions run `28359707608` for workflow `Codex publish verifier` completed with `success` at `2026-06-29T08:44:19Z`, yet issue `#10` stayed at 6 comments and the newest bot comment began with `### Summary`.

## Decision Log

- Decision: add a dedicated issue-comment verifier instead of teaching the watchdog to wait less.
  Rationale: the missing publish step is detectable the moment Codex posts its summary comment, so the shortest feedback loop is an immediate verifier on `issue_comment.created`.
  Date/Author: 2026-06-29 / Codex

- Decision: keep the verifier additive and limited to one retry comment per queue cycle.
  Rationale: this avoids comment spam if Codex repeats the same summary without publishing, while still giving the automation one immediate chance to recover before the existing watchdog takes over.
  Date/Author: 2026-06-29 / Codex

## Outcomes & Retrospective

The repository now has a direct publish-gap recovery path in addition to the existing queue, PR-link, and watchdog loops, but the first live probe exposed one remaining format mismatch. The workflow logic is correct, yet its summary detector must accept both `**Summary**` and `### Summary` so that new connector output actually triggers the retry path. This follow-up patch is therefore a narrow compatibility correction, not a redesign.

## Context and Orientation

The repository already has three GitHub Actions workflows that govern Codex issue automation. `.github/workflows/codex-assign.yml` converts a structured issue plus trusted `@codex` mention into a queued task by posting a canonical implementation comment and labels such as `status: queued`. `.github/workflows/codex-pr-link.yml` watches real pull requests and moves linked issues to `status: in progress` or closes them on merge. `.github/workflows/codex-watchdog.yml` runs every 30 minutes and marks queued issues blocked when no linked PR appears.

The current gap appears after execution but before publish. On issue `#10`, the external agent completed code work and left a summary comment, yet neither the commit SHA nor a PR exists on GitHub. Because no workflow inspects that completion comment, the issue remains queued until the watchdog eventually times out. The new work must fill that exact hole without disturbing the existing queue, PR-link, or timeout behavior.

## Plan of Work

First, update `.github/workflows/codex-assign.yml` so the canonical `@codex` instruction is explicit about the required publish contract. The prompt should tell Codex to keep an `issue-<n>` marker in the branch name, push that branch to `origin`, open a PR against `main`, include `Closes #<n>` in the PR body, and report the real PR URL plus pushed commit SHA before claiming success. This change does not alter repository state directly; it improves the first-pass odds that the external executor publishes correctly.

Second, add a new workflow at `.github/workflows/codex-publish-verify.yml`. This workflow will listen to `issue_comment.created`, ignore pull request comments, and only react to comments authored by `chatgpt-codex-connector[bot]` on issues that are still open and labeled both `status: queued` and `agent: codex`. It should only consider comments that look like Codex completion summaries, meaning they include `**Summary**` plus either `Committed changes` or `Opened PR:`. The workflow must reuse the same linked-PR definition already used in `codex-pr-link.yml` and `codex-watchdog.yml`: a PR counts only when its body, title, or branch name clearly references the issue number.

If a linked PR already exists, the verifier should exit quietly. If not, it should check whether a publish-retry comment was already posted during the current queue cycle. A queue cycle begins at the latest GitHub Actions comment that either starts with `@codex Please implement this task:` or matches the watchdog retry comment. If no publish-retry exists after that point, the workflow should post a single GitHub Actions comment that tags `@codex`, states that publish verification failed, and instructs the agent to continue from the existing work by pushing the branch, opening the PR, including `Closes #<n>`, and replying with the real PR URL and pushed SHA. That comment should leave the issue queued so the existing watchdog can continue supervising.

## Concrete Steps

Work from the repository root:

    cd /Users/gregkisel/Developer/ai_trainer
    git switch main
    git pull --ff-only
    git switch -c codex/automation-publish-guard

Edit `.github/workflows/codex-assign.yml` and add `.github/workflows/codex-publish-verify.yml`. Keep the workflow logic inside `actions/github-script@v7` so it matches the existing automation style. Then validate both workflow files with Python YAML parsing:

    python -c "from pathlib import Path; import yaml; [yaml.safe_load(Path(p).read_text()) for p in ['.github/workflows/codex-assign.yml', '.github/workflows/codex-publish-verify.yml']]"

If parsing succeeds, stage the workflow files and this ExecPlan, commit them on the current branch, push, and open a PR that includes `Closes #17` or a separate automation issue if one exists for this publish-loop gap.

## Validation and Acceptance

Validation has two layers. First, the workflow files must parse successfully as YAML and remain readable by GitHub Actions. Second, the behavior must be explainable against the live `#10` failure mode: after merge, a new Codex summary comment without a linked PR should trigger an immediate GitHub Actions publish-retry comment instead of sitting silently in `status: queued` until the 30-minute watchdog fires.

Acceptance is met when a reviewer can read the new workflow and see that:

1. only Codex completion comments from `chatgpt-codex-connector[bot]` are eligible;
2. a real linked PR suppresses the retry;
3. exactly one retry comment is posted per queue cycle when no PR exists; and
4. the retry comment contains `@codex` plus explicit push/PR instructions.

## Idempotence and Recovery

The verifier is intentionally idempotent. If GitHub replays the same comment event or the job is re-run manually, it will find the already-posted publish-retry comment and exit without adding duplicates. If the workflow is too noisy in practice, it can be disabled safely by removing `.github/workflows/codex-publish-verify.yml`; the rest of the existing queue and watchdog state machine continues to work unchanged.

## Artifacts and Notes

Relevant live evidence before the fix:

    gh api repos/rbctmz/ai_trainer/issues/10 --jq '{labels: [.labels[].name], comments: .comments}'
    # => {"comments":3,"labels":["type: enhancement","area: core","area: infrastructure","status: queued","agent: codex"]}

    gh api repos/rbctmz/ai_trainer/commits/5dfbacb
    # => {"message":"No commit found for SHA: 5dfbacb", ...}

## Interfaces and Dependencies

The new workflow uses `actions/github-script@v7`, the same helper already used in the existing automation workflows, and only needs `issues: write` plus `pull-requests: read` permissions. It must reuse the repository's current linked-PR contract based on issue references in PR body, title, or branch name, so no new labels, services, or external dependencies are introduced.

Revision note (2026-06-29): created this ExecPlan to cover the publish-step gap discovered on issue `#10`, where Codex reported a local commit without publishing any GitHub branch or pull request.

Revision note (2026-06-29): updated the plan after implementation to record the new verifier workflow, the stronger assign prompt, and the YAML validation evidence.

Revision note (2026-06-29): updated the plan after publish to record commit/push/PR completion and the initial PR check state.

Revision note (2026-06-29): updated the plan after the first live post-merge probe on issue `#10` exposed a summary-heading format mismatch in the verifier.
