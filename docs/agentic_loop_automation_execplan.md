# Agentic loop readiness and CI failure automation

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds. This document follows `.agent/PLANS.md`.

## Purpose / Big Picture

AI Trainer already has an issue-first, PR-gated agent loop. The remaining manual friction is that a human still has to inspect whether a PR is green and mergeable, and a failed CI run can sit in GitHub until someone opens the Actions page and asks the agent to continue. After this change, GitHub automation will make both states explicit. Clean green linked PRs get a `status: ready to merge` label and a short comment. Failed CI runs on PRs get a structured comment with the run URL, failed jobs, and an `@codex` ping when the PR belongs to the Codex issue loop.

This does not enable full auto-merge. The maintainer still makes the merge decision.

## Progress

- [x] (2026-07-04 14:08+03:00) Confirmed local `main` is clean and up to date at merge commit `079e347`.
- [x] (2026-07-04 14:11+03:00) Created GitHub issue #80 and branch `codex/issue-80-agentic-loop-automation`.
- [x] (2026-07-04 14:17+03:00) Audited existing workflows: CI, Codex Review, PR link, watchdog, publish verifier, and roadmap sync.
- [x] (2026-07-04 14:31+03:00) Added a PR readiness workflow that creates/removes `status: ready to merge`.
- [x] (2026-07-04 14:36+03:00) Added a CI failure workflow that comments once per failed workflow run and pings Codex on agent PRs.
- [x] (2026-07-04 14:39+03:00) Updated `docs/loop_engineering_instruction.md` to document the new loop states.
- [x] (2026-07-04 14:45+03:00) Validated workflow YAML, ran contributor-safe smoke, and checked whitespace.
- [ ] Publish a PR that closes issue #80.

## Surprises & Discoveries

- Observation: The repository has no existing `status: ready to merge` label.
  Evidence: `gh label list --limit 200` returned `status: queued`, `status: in progress`, `status: blocked`, and `status: needs triage`, but no ready-to-merge label.

- Observation: The current watchdog only catches queued issues without PRs.
  Evidence: `.github/workflows/codex-watchdog.yml` scans `status: queued,agent: codex` issues and checks whether a linked PR exists; it does not inspect failed PR checks.

- Observation: `actionlint` is not installed in the local development environment.
  Evidence: `command -v actionlint` returned exit code 1. Validation therefore uses PyYAML parsing locally and relies on GitHub Actions to validate workflow schema on the PR.

## Decision Log

- Decision: Add two new workflows instead of folding this logic into existing `codex-pr-link.yml` or `ci.yml`.
  Rationale: PR readiness is a state projection over PR metadata and checks, while CI failure comments are a failed-run response. Keeping them separate avoids making the existing queue/link/watchdog workflows harder to reason about.
  Date/Author: 2026-07-04 / Codex

- Decision: The readiness workflow labels only linked, non-draft, open PRs whose merge state is `clean` and whose current-head check runs are complete and successful.
  Rationale: The label should mean "human can decide merge now" rather than merely "some checks passed." Pending checks, draft PRs, unlinked PRs, dirty branches, and failing checks should not look merge-ready.
  Date/Author: 2026-07-04 / Codex

- Decision: The CI failure workflow comments once per workflow run using an HTML marker.
  Rationale: GitHub can re-deliver workflow events or rerun the same handler. A hidden marker such as `<!-- codex-ci-failure:RUN_ID -->` prevents duplicate comments without needing external storage.
  Date/Author: 2026-07-04 / Codex

## Outcomes & Retrospective

The implementation adds two independent workflow files. `.github/workflows/pr-ready-to-merge.yml` projects clean green linked PR state into `status: ready to merge` and removes the label when the gate no longer holds. `.github/workflows/codex-ci-failure.yml` turns failed CI workflow runs into deduplicated PR comments and pings Codex for agent-owned PRs. `docs/loop_engineering_instruction.md` now documents both loop steps and preserves the human merge boundary.

Validation completed:

    python3 - <<'PY'
    import pathlib, yaml
    for path in pathlib.Path(".github/workflows").glob("*.yml"):
        yaml.safe_load(path.read_text())
    print("workflow yaml ok")
    PY
    workflow yaml ok

    python3 -m pytest tests/smoke -q
    332 passed

    git diff --check
    no output

## Context and Orientation

The repo's current agent loop is described in `docs/loop_engineering_instruction.md`. Structured GitHub issues are queued by `.github/workflows/codex-assign.yml`, linked PRs move issues to in-progress via `.github/workflows/codex-pr-link.yml`, and `.github/workflows/codex-watchdog.yml` re-pings queued issues when no PR appears. `.github/workflows/ci.yml` runs contributor-safe pytest on PRs, and `.github/workflows/codex-review.yml` asks Codex for review on new ready PRs.

This plan adds two new files under `.github/workflows/`. A workflow is a GitHub Actions YAML file. It reacts to repository events and can call GitHub APIs through `actions/github-script`. The first workflow projects PR state into labels. The second workflow turns failed CI runs into actionable PR comments.

## Plan of Work

Create `.github/workflows/pr-ready-to-merge.yml`. It should run on relevant `pull_request` events and after the existing workflows finish. It will find the affected PR, verify it is open, not draft, linked to an issue by PR body/title/branch, mergeable with `mergeable_state == clean`, and has at least one relevant completed successful check run on the current head SHA. It will create the `status: ready to merge` label if needed, add the label when ready, remove it when not ready, and comment only once per head SHA when the PR becomes ready.

Create `.github/workflows/codex-ci-failure.yml`. It should run when the `CI` workflow completes. If the conclusion is failure-like, it will find related PRs, avoid duplicate comments for the same workflow run, fetch failed job names when available, and comment on the PR. If the PR head branch starts with `codex/` or a linked issue has `agent: codex`, the comment should include `@codex`.

Update `docs/loop_engineering_instruction.md` with two new automation loop subsections. Keep the document explicit that code still lands only after human merge decision.

## Concrete Steps

From repository root `/Users/gregkisel/Developer/ai_trainer`, validate YAML after editing:

    python3 - <<'PY'
    import pathlib, yaml
    for path in pathlib.Path(".github/workflows").glob("*.yml"):
        yaml.safe_load(path.read_text())
    print("workflow yaml ok")
    PY

Then run contributor-safe smoke:

    python3 -m pytest tests/smoke -q

## Validation and Acceptance

The workflow parse command must print `workflow yaml ok`. The smoke suite must pass. On the PR created for issue #80, the new workflow should be visible in GitHub checks. It may not label its own PR immediately until all workflows are complete, but the logic is accepted when the YAML is valid, the scripts are scoped to PRs, and the PR body links issue #80 with `Closes #80`.

After merge, a future clean green linked PR should get `status: ready to merge`. A future failed CI run on a Codex branch should receive a single PR comment containing the workflow name, run URL, failed job list when available, and an `@codex` ping.

## Idempotence and Recovery

Both workflows are idempotent. Adding an already-present label is skipped by checking current labels. Removing a missing label catches and ignores GitHub 404 errors. Comments use hidden markers to avoid duplicates. If GitHub APIs are temporarily unavailable, a later event or manual workflow dispatch can recompute readiness.

## Artifacts and Notes

No database, API, or web runtime behavior changes are planned. This is an infrastructure-only PR.

## Interfaces and Dependencies

The new workflows depend on:

    actions/github-script@v7
    github.rest.pulls.get
    github.rest.checks.listForRef
    github.rest.actions.listJobsForWorkflowRun
    github.rest.issues.createComment
    github.rest.issues.addLabels
    github.rest.issues.removeLabel

The readiness label is:

    status: ready to merge
