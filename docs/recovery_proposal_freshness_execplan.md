# Make Recovery Replan proposals evidence-current and truthful

This ExecPlan is a living document maintained under `.agent/PLANS.md`. It implements issue #552. A user must never be able to approve a recovery proposal after newer complete readiness evidence has invalidated it, while the historical proposal remains visible for audit. The same card must show duration, target-day wording, and audit time truthfully.

## Purpose / Big Picture

After this change, a pending Recovery Replan is actionable only while the recovery-decision fingerprint that produced it is the latest complete evaluation for its planning checkpoint. A newer `silence` decision supersedes the card without deleting history, and an approval racing that decision is resolved atomically. The proposal preview describes the materialized child sessions on affected dates, future targets are not called “today”, and decision times use the configured athlete timezone.

## Progress

- [x] (2026-09-06 07:50Z) Reproduced stale approval, duration contamination, fixed variant label, and raw-UTC display on the current main baseline.
- [x] (2026-09-06 08:05Z) Chose evidence-fingerprint ownership and SQLite compare-and-set lifecycle semantics.
- [x] (2026-09-06 08:12Z) Added lifecycle, real concurrency, duration, label, and timezone regression tests; the focused contour passes 100 tests.
- [x] (2026-09-06 08:14Z) Implemented conditional supersession and an evidence-current SQLite claim before any plan or provider mutation.
- [x] (2026-09-06 08:15Z) Implemented materialized composite duration totals, unchanged-row neutrality, target-date wording, and athlete-local audit clocks.
- [x] (2026-09-06 08:18Z) Completed Ruff, web lint/build, contract freshness, and contributor-safe pytest validation.
- [x] (2026-09-06 08:20Z) Published implementation commit `370af4b` and opened issue-linked PR #553; product CI passed and human review remains the merge gate.

## Surprises & Discoveries

- **Observed**: the existing Today characterization test requires a current-checkpoint pending proposal to remain actionable after later silence.
  **Inferred**: issue #174 intentionally preserved visibility but conflated visibility with actionability.
  **Verified by**: `tests/smoke/test_api_today.py::test_today_keeps_current_pending_proposal_visible_when_latest_loop_is_silent` asserts `conflict_actionable`.
- **Observed**: proposal approval compares the planning checkpoint but not the recovery decision that created the preview.
  **Inferred**: a stale readiness proposal can mutate the plan whenever its checkpoint is still active.
  **Verified by**: an isolated SQLite probe through `approve_proposal` appended a checkpoint after newer silence; the source database was not changed.
- **Observed**: unchanged draft rows receive newly estimated target durations and are included in the total delta.
  **Inferred**: the weekly duration delta can be dominated by unrelated plan-prefix rows.
  **Verified by**: a pure synthetic draft showed a non-zero duration contribution from unchanged rows.
- **Observed**: a newer recovery decision commits before the proposal payload refresh because the decision journal and proposal lifecycle intentionally use separate short transactions.
  **Inferred**: an approval in that narrow interval must reject the old preview, but the continuing conflict still needs a fresh card after the race.
  **Verified by**: the implementation retries proposal creation only when the competing evidence claim has already changed the reused active-key row to `superseded`; an `applying` row is never replaced.

## Decision Log

- Decision: Store the owning recovery decision fingerprint in proposal params and preview instead of adding a mandatory schema column.
  Rationale: params are already durable and backward-compatible; legacy rows remain readable, while legacy pending recovery proposals fail closed at approval because they cannot prove current evidence ownership.
  Date/Author: 2026-09-06 / Codex.
- Decision: Serialize approval ownership with `BEGIN IMMEDIATE`, reading the latest recovery decision and changing `pending` to `applying` in one transaction.
  Rationale: if newer evidence commits first, approval supersedes and refuses the proposal; if approval claims first, the later loop cannot supersede the applying proposal. This yields one terminal lifecycle without holding a transaction across provider delivery.
  Date/Author: 2026-09-06 / Codex.
- Decision: `data_gap` does not supersede a proposal; only a newer complete `conflict` or `silence` evaluation does.
  Rationale: missing evidence cannot prove that the original conflict ended.
  Date/Author: 2026-09-06 / Codex.

## Outcomes & Retrospective

The implementation now gives recovery proposals an explicit evidence owner, removes invalidated cards from the confirmation queue without deleting their audit rows, and places the evidence comparison and `pending` to `applying` claim under one SQLite write lock. A real two-writer test allows either valid ordering and proves the row finishes as exactly `approved` or `superseded`; a stale committed decision produces HTTP 409 before a checkpoint or provider call.

The card projection now sums the materialized child sessions on the affected composite day. Unchanged prefix rows retain their real duration and contribute zero, while the displayed protected-duration delta is the before/after difference for the selected affected day. The web label is derived from the proposal target date and `as_of`, and all decision clocks convert persisted UTC through `ATHLETE_TIMEZONE` with an explicit UTC fallback for invalid configuration.

Validation at the candidate tree: focused recovery/Today/decision/UI contour `100 passed`; contributor-safe suite `2332 passed, 3 skipped, 26 deselected`; Ruff passed; Next.js lint and production build passed; the TypeScript contract artifact is current. GitHub PR #553 independently passed contributor-safe pytest, Playwright, the web contract check, and secret scanning. The three local skips and three warnings are the known environment/deprecation items recorded by the baseline, not regressions from this change. No local athlete database or provider was accessed.

## Context and Orientation

`api/recovery_replan_loop.py` builds and stores immutable recovery decisions plus one durable human-confirmed proposal. `data/database.py` owns SQLite lifecycle transitions. `api/routers/decisions.py` approves proposals and invokes planning mutations. `api/today_snapshot.py` projects the active proposal. `models/recovery_replan.py` and `models/planning_near_term.py` build the preview. `web/components/ui/ProposalCard.tsx` renders variant labels. Recovery decisions are immutable; proposals may move through lifecycle states; planning checkpoints are append-only.

The affected architecture requirements are ASR-REL-1, because a stale action must not corrupt plan/reconciliation lineage; ASR-REL-2, because incomplete readiness remains a data gap rather than fabricated recovery; and ASR-MOD-3, because legacy SQLite rows and TypeScript/API consumers must remain readable after additive lifecycle metadata.

## Plan of Work

First add database primitives that refresh the params and preview of one still-pending active proposal, supersede pending recovery proposals after newer complete evidence, and atomically claim a proposal only when its evidence fingerprint equals the latest recovery decision for the same checkpoint. Extend the allowed terminal statuses with `superseded`, retaining result reason and resolution time.

Then make the loop attach the immutable recovery-decision fingerprint to proposal params/preview. A complete silence supersedes pending proposals for that checkpoint. A complete conflict refreshes the one same-target active proposal and supersedes other target proposals; a data gap leaves actionability unchanged.

Next make recovery day cards sum materialized child-session durations before and after the selected change, and make unchanged draft rows retain their current duration. Derive the Russian downgrade label from target date relative to `as_of`. Convert persisted UTC audit clocks through `Settings.ATHLETE_TIMEZONE`, with an explicit UTC fallback when configuration is invalid.

## Concrete Steps

Work from `/Users/gregkisel/Developer/ai_trainer` on `codex/issue-552-recovery-proposal-freshness`. Run focused tests while implementing:

    ai_trainer_env/bin/python -m pytest tests/smoke/test_recovery_replan_loop.py tests/smoke/test_api_today.py tests/smoke/test_coach_decisions.py tests/smoke/test_recovery_transfer_product_surface_web.py -q

Then run Ruff, web lint/build, contract freshness, and contributor-safe pytest exactly as listed in `AGENTS.md`.

## Validation and Acceptance

Tests must prove newer silence supersedes a pending proposal but preserves its row, data gap does not supersede, approval after a newer committed decision returns 409 with no checkpoint or provider write, and two racing operations yield one terminal result. A continuing same-target conflict keeps one active proposal whose fingerprint and preview match the newest decision. A composite-day fixture must show duration from the sums of materialized child sessions and zero contribution from unchanged rows. Source/UI tests must prove tomorrow/date wording, and API tests must prove UTC conversion into the athlete timezone plus honest invalid-timezone fallback.

## Idempotence and Recovery

Schema initialization remains additive and repeatable. Recovery decisions and planning checkpoints are never deleted or rewritten. Superseding is a conditional update from `pending` only. Re-running an identical loop reuses the same decision/proposal; retrying approval after a terminal transition returns 409. Provider delivery happens only after a successful evidence-current claim.

## Artifacts and Notes

Baseline at `d05b7e3`: focused recovery/Today/web contour 76 passed; contributor-safe suite 2323 passed, 3 skipped, 26 deselected.

## Interfaces and Dependencies

`data.database.Database` will expose conditional recovery lifecycle methods returning deserialized proposal rows and machine-readable reasons. `api.recovery_replan_loop._proposal_payload` will accept the owning decision fingerprint. `api.routers.decisions.approve_proposal` will use the recovery-specific atomic claim before any plan/provider mutation. No external dependency is added; timezone conversion uses Python `zoneinfo`.

Revision note: initial executable specification created for issue #552 after source inspection and isolated falsifying probes. Updated after implementation to record the concurrent refresh edge, completed milestones, local validation evidence, and publication as PR #553; external review and merge remain explicit human-gated workflow steps.
