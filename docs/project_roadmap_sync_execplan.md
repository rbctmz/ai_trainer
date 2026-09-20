# Project Roadmap Status Sync

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

This document must be maintained in accordance with `.agent/PLANS.md`.

> **Retired 2026-09-20.** The workflow this plan describes,
> `.github/workflows/project-roadmap-sync.yml`, has been removed. It shipped in
> PR `#28` on 2026-06-29 but never received the `ROADMAP_PROJECT_TOKEN` secret it
> required, and the repository integration token cannot write a user-owned
> Project v2. For three months every pull request therefore carried a failing
> `sync` check. Retirement was chosen over implementing the graceful-degradation
> item that had stayed open in `Progress` since the day the workflow shipped. The
> remainder of this document is retained as decision history and is no longer a
> description of current automation.

## Purpose / Big Picture

After this change, the Roadmap project at `users/rbctmz/projects/2` should stop drifting away from the repository’s issue automation state. A card like issue `#10` should not sit at `Todo` merely because no one manually edited the board; instead, the project `Status` field should follow the repository source of truth: open queued/blocked work stays `Todo`, active work becomes `In Progress`, and closed or merged work becomes `Done`.

## Progress

- [x] (2026-06-29 14:35Z) Confirmed the mismatch that motivated issue `#25`: roadmap cards were diverging from issue labels and PR state, including blocked work still showing `Todo`.
- [x] (2026-06-29 14:43Z) Implemented `.github/workflows/project-roadmap-sync.yml` to sync the project `Status` field from issue labels/state and PR open/merged state, with `workflow_dispatch` support for backfill.
- [x] (2026-06-29 14:47Z) Published the branch and opened PR `#28`.
- [x] (2026-06-29 14:53Z) Live validation on PR `#28` showed that repository `GITHUB_TOKEN` cannot resolve the private user-owned Project v2.
- [x] (2026-09-20) Resolved by **retirement instead of implementation**: the workflow was deleted rather than given `ROADMAP_PROJECT_TOKEN` and a warning on the write path. See `Outcomes & Retrospective`.

## Surprises & Discoveries

- Observation: the project board already stores useful planning metadata such as `Priority`, `Category`, and `Effort`, so the sync must be deliberately narrow and touch only the `Status` field.
  Evidence: `gh project field-list 2 --owner rbctmz --format json` showed separate single-select fields for `Status`, `Priority`, `Category`, and `Effort`.

- Observation: the roadmap contains both issue items and PR items from this repository.
  Evidence: `gh project item-list 2 --owner rbctmz --format json` returned issue cards like `#10` and PR cards like `#13`.

- Observation: the default repository `GITHUB_TOKEN` cannot access the private user-owned Roadmap project.
  Evidence: workflow run `28381056657` failed with `Could not resolve to a ProjectV2 with the number 2.`, while local owner-authenticated `gh project view 2 --owner rbctmz --format json` succeeds.

## Decision Log

- Decision: sync only the project `Status` field and leave all other board metadata manual.
  Rationale: `Priority`, `Category`, and `Effort` are planning inputs, not workflow outputs, so overwriting them from automation would make the board less useful.
  Date/Author: 2026-06-29 / Codex

- Decision: include `workflow_dispatch` in addition to event-driven sync.
  Rationale: event hooks keep future changes aligned, while manual dispatch gives a safe backfill and repair path when historical cards have already drifted.
  Date/Author: 2026-06-29 / Codex

- Decision: treat open linked PRs as `In Progress` even if the issue labels are stale.
  Rationale: the linked PR is the strongest signal that work is underway, and this matches the repository’s existing `codex-pr-link` logic.
  Date/Author: 2026-06-29 / Codex

- Decision: support repository secret `ROADMAP_PROJECT_TOKEN` and skip with a warning when that secret is absent or lacks access.
  Rationale: the automation belongs in the repo, but a private user-owned Project v2 cannot be mutated by the default repository token. Failing every PR would be worse than surfacing the missing secret explicitly.
  Date/Author: 2026-06-29 / Codex

- Decision: **retire the automation and delete the workflow**, superseding the
  decision above.
  Rationale: the secret was never configured, so every run fell through to
  `github.token`. That token can read the public project but not write it, so the
  workflow reached the unguarded `updateProjectV2ItemFieldValue` mutation and
  failed; for three months every pull request carried a failing `sync` check. The
  skip-with-warning promised by the decision above was never implemented for the
  write path, and the check never affected mergeability — the only required status
  check on `main` is `Contributor-safe pytest`. The label-driven projections are
  separate workflows that never depended on this token, so retirement costs no
  working automation.
  Date/Author: 2026-09-20 / Domain / API Implementer (DSH), PR #618

## Outcomes & Retrospective

The core state-mapping logic is implemented, and live PR validation immediately exposed the real operational boundary: private user-owned Project v2 access requires a stronger token than `GITHUB_TOKEN`. This follow-up patch keeps the workflow usable in contributor PRs while making the missing secret explicit.

**Retired 2026-09-20: the automation never worked, and removing it was cheaper than completing it.**

- **Observed**: `gh secret list --repo rbctmz/ai_trainer` returned exactly one
  secret, `CLAUDE_CODE_OAUTH_TOKEN`. `ROADMAP_PROJECT_TOKEN` was absent, so
  `${{ secrets.ROADMAP_PROJECT_TOKEN || github.token }}` always fell back to the
  integration token. Run logs showed `FORBIDDEN` /
  `Resource not accessible by integration` on `updateProjectV2ItemFieldValue` for
  project `PVT_kwHOBymzFc4BbL8C`. Source: repository secret listing and
  `gh run view --log` for runs 35500046058 and 35500231382.
- **Inferred**: the read path must have succeeded for the run to reach the write
  mutation at all, which means the workflow's own graceful-skip guard never fired.
  That guard catches only read failures (`Could not resolve to a ProjectV2`,
  `NOT_FOUND`); the write path is unguarded. Cheapest falsifying check: read the
  guard in the workflow file and confirm the mutation is outside it.
- **Verified by**: the guard covers `getProjectItems()` only, and the unguarded
  `setItemStatus` mutation is what raised. The 2026-06-29 note in `Progress`
  claimed `GITHUB_TOKEN` was unable to resolve the project; today the observed
  failure is on the write, so that note no longer describes the present behavior.
- **Decision**: retire the automation. The motivating issue `#25` and its PR `#28`
  were both closed in June, the board is still usable by hand, and the
  label-driven status projections (`status: queued`, `status: in progress`,
  `status: ready to merge`) are separate workflows that never depended on this
  token.

  **Preconditions for re-instating the automation.** Installing the secret alone
  is explicitly not sufficient: that is the state this plan spent three months in,
  and it restores the same unguarded write-failure path. Before the workflow comes
  back, all of the following must hold.

  1. A credential that can actually write the user-owned Project v2 exists
     (`ROADMAP_PROJECT_TOKEN`, currently absent from the repository secrets).
  2. The workflow degrades gracefully on **both** authorization failures — the
     read (`getProjectItems`) and the write (`setItemStatus`) — not only the read
     path, which is all the deleted version guarded.
  3. `workflow_dispatch` completes successfully against the live board with the
     credential in place, and the resulting item states are inspected, before the
     event-driven triggers are re-enabled.
  4. The reinstated workflow is re-subscribed in
     `.github/workflows/pr-ready-to-merge.yml` under `workflow_run.workflows`. That
     entry was removed during retirement, so without this step the readiness
     projection stops noticing sync completion.
  5. A board snapshot is taken before the first dispatch, because the dispatch path
     rewrites every item and is not a read-only probe.

## Context and Orientation

The repository now has a stronger issue automation state machine: `codex-assign.yml` queues work, `codex-pr-link.yml` moves linked issues to `in progress` and closes them on merge, `codex-watchdog.yml` blocks stalled work, and `codex-publish-verify.yml` handles publish failures. None of those workflows currently updates the GitHub Project v2 board. The board itself lives at project `2` under user `rbctmz` and uses single-select fields for `Status`, `Priority`, `Category`, and `Effort`.

The new workflow should not try to rebuild planning semantics. Its job is narrower: read the repository state and keep only the board’s `Status` field aligned. That requires handling both issue cards and PR cards, because the roadmap currently includes both.

## Plan of Work

Add `.github/workflows/project-roadmap-sync.yml`. The workflow should react to issue lifecycle events (`opened`, `reopened`, `closed`, `labeled`, `unlabeled`) and PR lifecycle events (`opened`, `reopened`, `edited`, `closed`). It should also expose `workflow_dispatch` so the board can be repaired on demand.

Inside the workflow, query the project items by GraphQL and match only content that belongs to `rbctmz/ai_trainer`. For issue items, fetch the live GitHub issue and compute the desired board status from repository truth:

- closed issue => `Done`
- open issue with `status: in progress` label => `In Progress`
- open issue with any open linked PR => `In Progress`
- all other open issue states, including queued/blocked/needs-triage => `Todo`

For PR items, compute:

- open PR => `In Progress`
- merged PR => `Done`
- closed-unmerged PR => `Todo`

Apply the computed option only to the project `Status` field. Do not modify `Priority`, `Category`, `Effort`, labels, assignees, or any repository issue state. Because the Roadmap project is private and user-owned, the workflow must prefer repository secret `ROADMAP_PROJECT_TOKEN` when available and otherwise skip with a warning rather than fail the job.

## Concrete Steps

Work from the repository root:

    cd /Users/gregkisel/Developer/ai_trainer
    git switch -c codex/project-roadmap-sync

Add `.github/workflows/project-roadmap-sync.yml` and this ExecPlan. Then validate the YAML and formatting:

    python3 -c "from pathlib import Path; import yaml; yaml.safe_load(Path('.github/workflows/project-roadmap-sync.yml').read_text())"
    git diff --check

Stage only:

    .github/workflows/project-roadmap-sync.yml
    docs/project_roadmap_sync_execplan.md

Publish the branch and open a PR with `Closes #25` in the PR body.

## Validation and Acceptance

The workflow should be readable as a direct mapping from repository workflow state to project `Status`. Before merge, YAML validation and diff hygiene are the local proof. After publication, a maintainer can trigger `workflow_dispatch` on the branch or after merge to backfill the board and verify at least:

- a blocked issue item such as `#10` resolves to `Todo`
- a merged PR item such as `#13` resolves to `Done`

The acceptance bar is that, once a project-capable token is configured, the project `Status` field becomes a mechanical reflection of repository workflow state while all other project metadata remains untouched. Before that token exists, the workflow should skip cleanly with an explicit warning instead of failing PR checks.

## Idempotence and Recovery

The workflow is idempotent because it always recomputes status from current repository truth. Re-running `workflow_dispatch` simply reapplies the same values. If the mapping ever proves too aggressive, disabling the workflow stops future updates without damaging repository issues or pull requests; only the project `Status` field will need manual adjustment.

## Artifacts and Notes

Project field constants used by the workflow:

    Project ID: PVT_kwHOBymzFc4BbL8C
    Status field ID: PVTSSF_lAHOBymzFc4BbL8CzhV-ROg
    Todo option: f75ad846
    In Progress option: 47fc9ee4
    Done option: 98236657

Current roadmap evidence before the sync:

    issue #10 is label-blocked in repository automation
    project item for #10 still shows Todo

## Interfaces and Dependencies

This workflow depends on GitHub GraphQL project mutations and the repository’s existing issue/PR linking logic. It uses `actions/github-script@v7`, reads `issues` and `pull-requests`, and writes only `repository-projects`. Because the target project is a private user-owned Project v2, repository secret `ROADMAP_PROJECT_TOKEN` is the intended credential for live automation.
