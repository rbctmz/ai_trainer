# Enable trusted `@claude` mentions in GitHub

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept current. This document follows `.agent/PLANS.md` and implements GitHub Issue #211.

## Purpose / Big Picture

After this change, the maintainer can mention `@claude` in an issue comment, a pull-request conversation, an inline review comment, or a submitted review. The official Anthropic GitHub Action will receive that issue or PR context and respond as Claude. This removes the manual copy-and-paste handoff between checker comments and the local Claude Code session.

The visible proof is a comment on a merged-workflow issue or PR such as `@claude summarize the blocking findings above`. GitHub Actions should start the `Claude Code` workflow and Claude should create or update its own progress comment. The action must not run automatically on every pull request.

## Progress

- [x] (2026-07-17) Read the official Claude Code Action v1 usage, security, and FAQ documentation; inspected existing repository workflows and ADD 3.0 security requirements.
- [x] (2026-07-17) Confirmed the repository already contains the `CLAUDE_CODE_OAUTH_TOKEN` secret and found an unmerged installer branch containing the vendor-generated starter workflows.
- [x] (2026-07-17) Created Issue #211 and branch `codex/issue-211-claude-code-action` from current `main`.
- [x] (2026-07-17) Registered four contributor-safe workflow contract tests RED; all four fail because `.github/workflows/claude.yml` does not yet exist.
- [x] (2026-07-17) Added the minimal interactive tag-mode workflow and documented its trigger and security boundary in the canonical agent-loop guide.
- [x] (2026-07-17) Validated four focused tests, 742 smoke tests (one environment skip), 788 broad non-live tests (three environment/dependency skips), YAML structure, and `git diff --check`.
- [ ] Commit and push the GREEN implementation and publish a draft PR.
- [ ] After human merge, perform one harmless live mention probe on Issue #211 or the setup PR.

## Surprises & Discoveries

- Observation: Anthropic's installer had already created remote branch `add-claude-github-actions-1783002676500` and the OAuth repository secret, but no PR was ever opened, so neither generated workflow reached `main`.
  Evidence: `gh secret list` shows `CLAUDE_CODE_OAUTH_TOKEN`; `git log --all -- .github/workflows/*claude*` shows the two installer commits only on that remote branch.

- Observation: The generated branch includes an automatic review-on-every-PR workflow in addition to interactive tag mode.
  Evidence: `.github/workflows/claude-code-review.yml` on the installer branch triggers on `pull_request` opened/synchronize/ready/reopened. Issue #211 requires explicit mentions only, so that workflow is intentionally not adopted.

- Observation: A normal user OAuth token cannot query GitHub's App-installation endpoint, so installation presence cannot be proven read-only through the current `gh` session.
  Evidence: `gh api user/installations` returns HTTP 403 requiring a token authorized to a GitHub App. The existing OAuth secret and vendor installer branch are strong setup evidence; the harmless post-merge mention is the definitive end-to-end check.

## Decision Log

- Decision: Enable only interactive tag mode, not automatic review.
  Rationale: The repository already has maker-checker review and CI automation. Automatic Claude review would add cost and duplicate existing review without being requested.
  Date/Author: 2026-07-17 / Codex.

- Decision: Accept only comment/review events authored with GitHub association `OWNER`, `MEMBER`, or `COLLABORATOR`, and also rely on the official action's permission validation.
  Rationale: This is defense in depth against prompt injection and unauthorized API spend. External contributors must not be able to invoke a secret-backed agent.
  Date/Author: 2026-07-17 / Codex.

- Decision: Use `issue_comment`, `pull_request_review_comment`, and `pull_request_review`; do not use `pull_request_target` and do not check out an untrusted PR head with repository secrets.
  Rationale: `issue_comment` covers both issue and PR conversation comments. Avoiding `pull_request_target` prevents untrusted PR code from sharing a workspace with secrets, matching Anthropic's security guidance.
  Date/Author: 2026-07-17 / Codex.

- Decision: Explicitly check out `github.event.repository.default_branch` for every event before invoking the action.
  Rationale: Review events can otherwise resolve to a PR merge ref. Starting from the trusted default branch keeps PR-controlled files out of the secret-bearing workspace; the official action obtains entity context and manages PR branches through its GitHub App.
  Date/Author: 2026-07-17 / Codex.

- Decision: Pin `anthropics/claude-code-action` v1 to commit `700e7f8316990de46bed556429765647af760efc` and annotate the major version.
  Rationale: A full commit pin limits supply-chain drift while the comment records the intended upstream release line.
  Date/Author: 2026-07-17 / Codex.

## Outcomes & Retrospective

The static implementation is complete: explicit trusted mentions are the only
trigger, the workflow token is read-only, the official action is commit-pinned,
and contract/smoke/broad validation is green. The only remaining outcome is the
post-merge GitHub-hosted mention probe, because comment-triggered workflows are
loaded from the default branch and cannot be exercised from this feature branch.

## Context and Orientation

GitHub workflows live in `.github/workflows/`. Existing files automate CI, Codex issue assignment, PR linking, readiness, and roadmap state. `docs/loop_engineering_instruction.md` is the canonical description of the current agent loop and must explain the new trigger.

The OAuth token is already stored as the GitHub repository secret `CLAUDE_CODE_OAUTH_TOKEN`. The workflow may reference that secret by name but must never print or duplicate its value. The official `anthropics/claude-code-action` uses the OAuth token for model authentication and its installed GitHub App for a short-lived repository-scoped token. The workflow's own permissions remain read-only except for `id-token: write`, which the built-in GitHub App authentication requires. `actions: read` lets Claude inspect CI failures after a maintainer explicitly asks it to do so.

## Plan of Work

First add `tests/smoke/test_claude_code_action_workflow.py`. The test reads the workflow as a contract and requires all three comment/review event types, explicit mention and trusted-association gates, the OAuth secret reference, the pinned official action, CI read access, and the absence of `pull_request_target`, automatic PR triggers, custom GitHub tokens, or application secrets.

Then add `.github/workflows/claude.yml`. The job prefilters comments that contain `@claude` and come from a trusted GitHub association. The official action performs the final complete-word trigger and permission checks. The job receives only the Claude OAuth secret, has a bounded timeout, can read CI, and follows `AGENTS.md`. Add a short `Claude Code tag mode` section to `docs/loop_engineering_instruction.md` describing how to invoke it and its security boundary.

Finally run the focused workflow test, the repository smoke contour, a YAML parser, and `git diff --check`. Commit and push only the workflow, its test, this ExecPlan, and the operating-guide update, then open a draft PR with `Closes #211`.

## Concrete Steps

Run from `/Users/gregkisel/Developer/ai_trainer`:

    /Users/gregkisel/Developer/ai_trainer/ai_trainer_env/bin/python -m pytest tests/smoke/test_claude_code_action_workflow.py -q
    /Users/gregkisel/Developer/ai_trainer/ai_trainer_env/bin/python -m pytest tests/smoke -q
    /Users/gregkisel/Developer/ai_trainer/ai_trainer_env/bin/python -c "import yaml; yaml.load(open('.github/workflows/claude.yml'), Loader=yaml.BaseLoader)"
    git diff --check

The first command must fail before `.github/workflows/claude.yml` exists and pass after implementation. The smoke suite must remain green apart from documented environment-only skips.

## Validation and Acceptance

Static acceptance requires the new contract test and smoke suite to pass. The workflow must contain no `pull_request_target` and no automatic `pull_request` event. It must reference only `secrets.CLAUDE_CODE_OAUTH_TOKEN`, use the pinned official action, expose `actions: read`, and gate all supported events by trusted author association plus `@claude`.

Live acceptance occurs only after merge because GitHub reads `issue_comment` workflows from the default branch. A maintainer posts `@claude summarize Issue #211 and do not change files` on Issue #211. A successful run appears under GitHub Actions as `Claude Code`, and `claude[bot]` posts a progress/final comment without modifying code. If the app installation is missing despite the existing secret, the run will fail during built-in authentication; rerun Anthropic's `/install-github-app`, keep the existing workflow, and retry the same harmless comment.

## Idempotence and Recovery

Repeated comments create independent bounded workflow runs and do not mutate application data. The workflow has no Garmin, Intervals.icu, database, deployment, or application-provider credentials. To disable it safely, revert the workflow commit or remove `.github/workflows/claude.yml`; the repository secret can remain stored without being accessible to any workflow.

## Artifacts and Notes

The official installer branch remains untouched as historical evidence. This implementation intentionally adopts only its interactive workflow concept and strengthens the repository-side trust gate and action pinning.

## Interfaces and Dependencies

The external dependency is `anthropics/claude-code-action` pinned to commit `700e7f8316990de46bed556429765647af760efc` (upstream major tag v1 on 2026-07-17). The only authentication input is `claude_code_oauth_token: ${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}`. The trigger phrase is the action default, `@claude`. No Python or JavaScript runtime dependency is added to the product.

Revision note (2026-07-17): initial self-contained plan created after discovering the incomplete vendor-installer branch; scope narrowed to explicit trusted mentions only to avoid duplicate automatic reviews and unnecessary model spend. Updated after implementation to record the explicit default-branch checkout, validation evidence, and the GitHub App installation-verification limitation.
