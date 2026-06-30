# Codex Executor Publish Recovery

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

This document must be maintained in accordance with `.agent/PLANS.md`.

## Purpose / Big Picture

After this change, a queued Codex task should attempt a real publish preflight before it can end in local-only commits and retry noise. When the executor checkout starts without `origin`, the queue contract should tell Codex exactly how to bootstrap `origin`, verify GitHub auth, and confirm a working publish path. If that bootstrap succeeds, the task can finish with a real pushed branch and PR. If it fails, the executor must stop early and report a machine-readable `Publish preflight blocker:` line so repository automation can block the issue immediately instead of looping. This still cannot manufacture credentials that do not exist, but it can turn the missing-`origin` case from a silent executor assumption into an explicit self-healing path with a precise blocker fallback.

## Progress

- [x] (2026-06-29 14:38Z) Confirmed that issue `#10` reaches the publish-verifier path and fails because the external executor checkout has no usable `origin`.
- [x] (2026-06-29 14:40Z) Merged the first mitigation in PR `#27`: missing-`origin` summaries now block the issue immediately instead of re-queueing forever.
- [x] (2026-06-30) Chosen the full repo-owned follow-up for issue `#26`: teach the queued Codex task to bootstrap `origin` from repository context, verify GitHub auth up front, and emit a machine-readable `Publish preflight blocker:` line if bootstrap still fails.
- [x] (2026-06-30) Updated the queue and verifier workflows to align on that preflight contract.
- [x] (2026-06-30) Validated the workflow YAML and whitespace locally.
- [ ] Publish the branch and open a PR that closes issue `#26`.

## Surprises & Discoveries

- Observation: the repository can control the task contract and the verifier, but not the executor image itself.
  Evidence: issue `#26` explicitly scopes `external Codex executor checkout/bootstrap` as the root cause, while the only repository-owned levers are the queue prompt, the verifier, and documentation.

- Observation: the existing verifier ignores an early publish failure if the executor stops before it produces commit metadata.
  Evidence: `.github/workflows/codex-publish-verify.yml` currently returns unless the summary contains `Committed changes` or `Opened PR:`. A true preflight blocker would not naturally contain either marker.

## Decision Log

- Decision: keep PR `#27` behavior, but add an earlier publish preflight contract to the queue prompt.
  Rationale: blocking after a failed local run is better than retry loops, but it still wastes executor work. The queue prompt can tell Codex how to self-heal `origin` before final delivery and how to stop before claiming success if bootstrap fails.
  Date/Author: 2026-06-30 / Codex

- Decision: standardize on a machine-readable blocker phrase, `Publish preflight blocker:`.
  Rationale: the verifier should not have to infer every possible failure wording from free-form prose. A stable phrase lets the queue contract and verifier share one explicit protocol for "I could not establish a real GitHub publish path".
  Date/Author: 2026-06-30 / Codex

## Outcomes & Retrospective

The queue and verifier contracts are now updated and locally validated. Publication and a live queue retry after merge are still pending.

## Context and Orientation

`.github/workflows/codex-assign.yml` is the only repository-owned place that consistently tells the external executor how to finish a queued task. Right now it requires "push to origin" but does not tell the executor how to repair a missing or wrong `origin`, how to verify GitHub auth before delivery, or how to report a structured blocker if publish remains impossible.

`.github/workflows/codex-publish-verify.yml` already knows how to classify missing-`origin` summaries as fatal blockers, but today it assumes a publish-related summary will include commit or PR markers. That assumption is too narrow once we want fail-fast behavior before local-only commits are produced.

The live example remains issue `#10`. The repository automation correctly queued the work and the executor correctly reported `fatal: 'origin' does not appear to be a git repository`. PR `#27` stopped the retry loop, but the next step is to let the queued task repair `origin` automatically when possible.

## Plan of Work

Update `.github/workflows/codex-assign.yml` and `.github/workflows/codex-publish-verify.yml` together.

In the queue prompt, add a publish preflight section that tells Codex to:

1. ensure the branch name contains `issue-<n>`,
2. inspect `git remote get-url origin`,
3. set `origin` to `https://github.com/<owner>/<repo>.git` when it is missing or wrong,
4. run `gh auth status` and `gh auth setup-git` when `gh` is available,
5. verify a real publish path via `git ls-remote --heads origin` or an equivalent GitHub-native branch/PR path,
6. stop immediately with a `Publish preflight blocker:` line if bootstrap still fails.

In the verifier, accept those early blocker summaries even when they do not mention `Committed changes` or `Opened PR:`. Treat `Publish preflight blocker:` as a first-class fatal blocker signal, alongside the older missing-`origin` phrases, and keep the existing idempotence guard so duplicate cycle comments do not spam the issue.

Do not redesign the PR matcher or watchdog. This slice is about making the executor publish contract self-healing when `origin` is repairable and explicitly blocked when it is not.

## Concrete Steps

Work from the repository root:

    cd /Users/gregkisel/Developer/ai_trainer
    git switch -c codex/issue-26-publish-bootstrap

Edit `.github/workflows/codex-assign.yml`, `.github/workflows/codex-publish-verify.yml`, and update this ExecPlan. Then validate the workflows as YAML and check for whitespace regressions:

    python3 -c "from pathlib import Path; import yaml; [yaml.safe_load(Path(path).read_text()) for path in ['.github/workflows/codex-assign.yml', '.github/workflows/codex-publish-verify.yml']]"
    git diff --check

Stage only:

    .github/workflows/codex-assign.yml
    .github/workflows/codex-publish-verify.yml
    docs/codex_executor_publish_execplan.md

Publish the branch and open a PR that closes issue `#26`.

## Validation and Acceptance

Validation is primarily contract-level and behavioral. Confirm all of the following by inspection:

1. the queue comment now tells Codex exactly how to bootstrap `origin` and verify GitHub auth,
2. the verifier accepts `Publish preflight blocker:` summaries even if they contain no commit metadata,
3. missing-`origin` and auth/bootstrap failures still take the fatal-blocker path before the generic retry path.

The resulting issue transition for a real preflight blocker must be:

1. `status: blocked` added,
2. `status: queued` removed,
3. one GitHub Actions comment explaining how to restore a usable publish path.

This satisfies the repository-owned portion of issue `#26`: a missing `origin` is no longer an implicit executor assumption. It becomes either an automatic bootstrap path or an explicit early blocker. The only remaining unsolved case would be an executor that has neither GitHub git credentials nor any GitHub-native branch/PR path available.

## Idempotence and Recovery

The blocker comment remains guarded per queue cycle. If GitHub replays the same comment event or the connector posts duplicate summaries in the same cycle, the workflow should not add duplicate `Publish environment blocked` comments. If the executor environment is later improved further, a trusted human can still re-queue the issue with a fresh `@codex` comment; the normal queue path remains intact.

## Artifacts and Notes

Live evidence that motivated this slice:

    issue #10 connector summary:
    * Commit SHA: c7226fd2fa1425bdbe640d1ea10a4160c1891277
    * push failed because `origin` does not appear to be a git repository

    issue #10 follow-up:
    * GitHub Actions posted `Publish verification failed`
    * watchdog later posted `@codex please retry`
    * PR #27 changed that outcome to an immediate block instead of a loop

## Interfaces and Dependencies

This slice stays inside GitHub Actions and uses the existing `actions/github-script@v7` runtime with `issues: write` and `pull-requests: read`. It depends on the current queue-cycle heuristics already present in `.github/workflows/codex-publish-verify.yml` and does not add new labels or external services. The actual publish bootstrap still executes inside the external Codex executor, but the repository now defines that contract explicitly instead of assuming `origin` already exists.
