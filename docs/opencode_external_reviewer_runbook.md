# OpenCode External Reviewer Runbook

## Purpose

OpenCode takes the Independent Reviewer role from `AGENTS.md` and is an optional
local second-opinion reviewer. It may inspect a bounded
diff, run explicitly allowed checks, and propose findings. It does not approve
a change, merge a PR, create issues, or make the repository ready by itself.
The supervising agent or human must independently validate and disposition its
output.

An OpenCode full-diff audit counts against the review budget in
`docs/AI_Feature_Development_Workflow.md`.

## Safety contract

- Never use `--auto`.
- Default to `--agent plan` for read-only review only after `opencode agent
  list` confirms that the current configuration denies the edit tool. This is a
  policy guard, not OS-level write protection: the prompt must still prohibit
  writes through shell tools. If prevention rather than detection is required,
  use a filesystem-read-only checkout or container.
- Name the exact commit or diff range. Do not ask for an unbounded repository
  review.
- Name the only test command the reviewer may run. Tests must use temporary or
  synthetic data.
- Prohibit dependency installation, network calls, and access to `.env*`,
  `logs/`, `ai_trainer.db`, personal data, and `backups/`.
- Never expose credentials in prompts, logs, or reports.
- Code-writing delegation requires explicit user authorization and a separate
  worktree. Two agents must not edit the same checkout concurrently.

## 1. Preflight

Record the repository baseline:

```bash
git status --short --branch
git rev-parse --verify <audit-ref>
```

Preserve unrelated changes. Do not start a delegated write task from a dirty
shared checkout. A read-only audit may proceed only when its prompt excludes all
unrelated paths explicitly.

Inspect configured providers without copying credential values into the report:

```bash
opencode --version
opencode providers list
opencode models
opencode agent list
```

`opencode models` is a catalog, not proof of authorization, quota, billing, or
runtime availability.

## 2. Model smoke check

Before each real assignment, require a minimal response from the exact model:

```bash
opencode run \
  --agent plan \
  --dir /private/tmp \
  --model <provider/model> \
  --title model-smoke-<short-name> \
  "Reply with exactly MODEL_OK. Do not use tools."
```

Classify the result precisely:

- `MODEL_OK`: verified available for this run;
- authentication or missing-key error: configured incorrectly;
- quota or credits error: known model, unavailable to this account now;
- timeout with no provider error: availability unverified, stop the process;
- catalog-only entry: untested, never call it available.

Availability is time-sensitive. Re-run the smoke check after credential,
billing, quota, provider, or OpenCode-version changes.

## 3. Read-only audit

Use one bounded prompt. Replace all angle-bracket placeholders before running:

```bash
opencode run \
  --agent plan \
  --dir <absolute-repository-path> \
  --model <verified-provider/model> \
  --title <audit-title> \
  "Conduct a strictly read-only audit of <PR or exact diff>. Do not edit, create, delete, rename, or format repository files. Do not install dependencies or use the network. Do not access backups/, .env files, logs/, ai_trainer.db, or personal data. Read AGENTS.md and the relevant acceptance criteria, non-goals, ASRs, slice spec, and ExecPlan. Focus on <named invariants>. Apply Observed / Inferred / Verified by and perform one cheap falsifying check before naming a bug. You may run only: <one allowed test command>. Report P1/P2 findings with exact file and line, violated invariant, reproduction, impact, and minimal correction. List suggestions separately. If there are no blocking findings, say so explicitly. Do not change files."
```

Monitor the process at least once per minute. If it enters an API retry loop,
inspect the provider error, stop the process, and classify the model as
unavailable rather than waiting indefinitely.

## 4. Supervisory review

Do not copy the model's verdict directly into the project decision. The
supervising agent must:

1. Check each P1 or blocking P2 for a reproduction or a named violated
   invariant.
2. Run one cheap falsifying check for each claimed cause.
3. Mark each finding `fixed-in <sha>`, `follow-up #N`, or
   `disputed: <reason>`.
4. Treat contradictions, incorrect counts, stale line numbers, and hypothetical
   scenarios as reviewer-quality defects, not repository defects.
5. Avoid creating issues or changing code unless the user separately authorizes
   that action.

## 5. Postflight

Verify that the audit was actually read-only and did not leave a worker behind:

```bash
git status --short --branch
git diff --name-only
git diff --check
ps aux | rg "[o]pencode run"
opencode session list
```

The final report must state:

- model and OpenCode session id;
- exact diff and files inspected;
- commands run and observed results;
- blocking findings and dispositions;
- non-blocking suggestions separately;
- whether the worktree changed;
- whether any process remains;
- actions deliberately not taken (edits, issues, comments, merge).

## Pilot snapshot: 2026-09-05

This is historical evidence, not a permanent availability promise.

- `deepseek/deepseek-v4-pro`: minimal smoke returned `MODEL_OK`; completed the
  read-only post-merge audit of PR #532.
- `deepseek/deepseek-v4-flash`, `neuraldeep/gpt-oss-120b`,
  `neuraldeep/qwen3.6-35b-a3b`, `opencode/nemotron-3-ultra-free`, and
  `opencode/ling-3.0-flash-fin-free`: minimal smoke returned `MODEL_OK`.
- `openai/gpt-5.3-codex`: provider recognized the model but the account had no
  credits.
- `google/gemini-3.1-pro-preview`: the configured environment-variable name
  required temporary mapping, after which the provider reported zero quota.
- `ollama/qwen3.5`: no response was observed; the process was stopped and the
  model remained unverified.
- PR #532 audit session: `ses_f8eca4022ffeb6LcCZPxp0IcW3`; focused regression
  `tests/smoke/test_issue_531_unplanned_activity_reassignment.py` reported
  `9 passed`; no blocking findings were accepted; the repository remained
  unchanged.
