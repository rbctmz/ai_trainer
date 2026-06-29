# Project Roadmap Status Sync

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

This document must be maintained in accordance with `.agent/PLANS.md`.

## Purpose / Big Picture

After this change, the Roadmap project at `users/rbctmz/projects/2` should stop drifting away from the repository’s issue automation state. A card like issue `#10` should not sit at `Todo` merely because no one manually edited the board; instead, the project `Status` field should follow the repository source of truth: open queued/blocked work stays `Todo`, active work becomes `In Progress`, and closed or merged work becomes `Done`.

## Progress

- [x] (2026-06-29 14:35Z) Confirmed the mismatch that motivated issue `#25`: roadmap cards were diverging from issue labels and PR state, including blocked work still showing `Todo`.
- [x] (2026-06-29 14:43Z) Implemented `.github/workflows/project-roadmap-sync.yml` to sync the project `Status` field from issue labels/state and PR open/merged state, with `workflow_dispatch` support for backfill.
- [ ] Validate the workflow YAML, publish the branch, and open a PR that closes issue `#25`.

## Surprises & Discoveries

- Observation: the project board already stores useful planning metadata such as `Priority`, `Category`, and `Effort`, so the sync must be deliberately narrow and touch only the `Status` field.
  Evidence: `gh project field-list 2 --owner rbctmz --format json` showed separate single-select fields for `Status`, `Priority`, `Category`, and `Effort`.

- Observation: the roadmap contains both issue items and PR items from this repository.
  Evidence: `gh project item-list 2 --owner rbctmz --format json` returned issue cards like `#10` and PR cards like `#13`.

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

## Outcomes & Retrospective

Pending validation and publication.

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

Apply the computed option only to the project `Status` field. Do not modify `Priority`, `Category`, `Effort`, labels, assignees, or any repository issue state.

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

The acceptance bar is that the project `Status` field becomes a mechanical reflection of repository workflow state, while all other project metadata remains untouched.

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

This workflow depends on GitHub GraphQL project mutations and the repository’s existing issue/PR linking logic. It uses `actions/github-script@v7`, reads `issues` and `pull-requests`, and writes only `repository-projects`. No Python application code or frontend files are involved.
