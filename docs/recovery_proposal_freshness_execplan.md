# Make Recovery Replan proposals evidence-current and truthful

This ExecPlan is a living document maintained under `.agent/PLANS.md`. It implements issue #552. A user must never be able to approve a recovery proposal after newer complete readiness evidence has invalidated it, while the historical proposal remains visible for audit. The same card must show duration, target-day wording, and audit time truthfully.

## Purpose / Big Picture

After this change, a pending Recovery Replan is actionable only while the recovery-evidence revision and fingerprint that produced it are the latest complete evaluation for its planning checkpoint. A newer `silence` decision supersedes the card without deleting history, and publication or approval racing that decision is resolved atomically. The proposal preview describes the materialized child sessions on affected dates, future targets are not called “today”, and decision times use the configured athlete timezone.

## Progress

- [x] (2026-09-06 07:50Z) Reproduced stale approval, duration contamination, fixed variant label, and raw-UTC display on the current main baseline.
- [x] (2026-09-06 08:05Z) Chose evidence-fingerprint ownership and SQLite compare-and-set lifecycle semantics.
- [x] (2026-09-06 08:12Z) Added lifecycle, real concurrency, duration, label, and timezone regression tests; the focused contour passes 100 tests.
- [x] (2026-09-06 08:14Z) Implemented conditional supersession and an evidence-current SQLite claim before any plan or provider mutation.
- [x] (2026-09-06 08:15Z) Implemented materialized composite duration totals, unchanged-row neutrality, target-date wording, and athlete-local audit clocks.
- [x] (2026-09-06 08:18Z) Completed Ruff, web lint/build, contract freshness, and contributor-safe pytest validation.
- [x] (2026-09-06 08:20Z) Published implementation commit `370af4b` and opened issue-linked PR #553; product CI passed and human review remains the merge gate.
- [x] (2026-09-06 09:30Z) Reproduced all four review findings: identical A → silence → A recurrence, superseded audit outcome, stale publication interleavings, and UTC-day grouping.
- [x] (2026-09-06 09:55Z) Added a monotonic per-checkpoint evidence head, atomic publication ownership, explicit superseded outcome mapping, and athlete-local grouping-day tests.
- [x] (2026-09-06 14:25Z) Reproduced the scoped delta-review findings for displaced event audit, real-midnight row semantics, applying collisions, and recurring revision linkage.
- [x] (2026-09-06 14:40Z) Replaced cross-revision proposal reassignment with one durable proposal per evidence revision, added honest in-flight publication state/retry, refreshed the current recovery-decision pointer, and made business-date detection semantic.

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
- **Observed**: immutable `recovery_decisions` deduplicate identical content by fingerprint, so row order cannot represent A → silence → identical A evaluation recency.
  **Inferred**: freshness ownership needs a monotonic evaluation revision separate from immutable content identity.
  **Verified by**: the review regression replays the sequence and requires a new pending proposal owned by a higher revision while reusing the immutable A decision row.
- **Observed**: saving evidence and publishing its proposal in separate transactions allowed C → silence or C1 → C2 to leave the older finisher advertising stale payload.
  **Inferred**: the publish/refresh operation itself must compare-and-set against the current complete evidence head under one write lock.
  **Verified by**: direct database tests reject stale publication and prove C2 gets the single active proposal while C1 remains terminally associated with its original decision event.
- **Observed**: localized clocks around UTC midnight were grouped under the raw UTC date.
  **Inferred**: the grouping day and display clock must derive from the same timestamp and athlete timezone, except for explicit business-date midnight rows.
  **Verified by**: the API groups `2026-07-02T22:30:00Z` under `2026-07-03` in `Europe/Moscow` while retaining recovery business date `2026-07-02`.
- **Observed**: treating every `00:00` value as a business date misgrouped real midnight coach decisions and ordinary proposals.
  **Inferred**: the recovery date exception must be selected from row type/source, not clock value alone.
  **Verified by**: the API places a `build_plan` proposal and coach decision at `2026-07-03T00:00:00Z` under July 2 at 17:00 in `America/Los_Angeles`, while a recovery decision retains July 3.
- **Observed**: moving a pending proposal's event/source ownership from C1 to C2 orphaned C1's audit outcome, and an `applying` C1 could be returned as though C2 had published.
  **Inferred**: proposal identity must be evidence-revision scoped; only a pending predecessor may be superseded, while an applying predecessor blocks publication until a later retry.
  **Verified by**: same-target tests show C1 → `superseded`/`no_change`, one new pending C2 with its own event linkage, and successful C2 publication after an applying C1 terminates as failed.

## Decision Log

- Decision: Store the owning evidence revision and fingerprint in proposal params and preview, backed by an additive mutable `recovery_evidence_heads` row per checkpoint.
  Rationale: immutable decisions remain content-deduplicated for audit, while the monotonic head preserves evaluation recency. Legacy rows remain readable, and legacy pending recovery proposals fail closed because they cannot prove revision ownership.
  Date/Author: 2026-09-06 / Codex.
- Decision: Serialize proposal publication and approval ownership with `BEGIN IMMEDIATE`, reading the evidence head before either publishing/refreshing `pending` or changing it to `applying`.
  Rationale: an older evaluation cannot publish or overwrite a card after newer complete evidence commits. A newer revision supersedes a pending predecessor and inserts its own proposal without moving audit ownership. If approval claims first, the later loop reports `in_flight` and can publish on retry after an unsuccessful application. This yields one terminal lifecycle per evidence revision without holding a transaction across provider delivery.
  Date/Author: 2026-09-06 / Codex.
- Decision: `data_gap` does not supersede a proposal; only a newer complete `conflict` or `silence` evaluation does.
  Rationale: missing evidence cannot prove that the original conflict ended.
  Date/Author: 2026-09-06 / Codex.

## Outcomes & Retrospective

The implementation now gives each recovery evidence revision its own durable proposal identity, removes invalidated cards from the confirmation queue without deleting or reassigning their audit rows, and places both publication ownership and the `pending` to `applying` claim under SQLite write locks. A real two-writer test allows either valid ordering and proves the row finishes as exactly `approved` or `superseded`; a stale committed decision produces HTTP 409 before a checkpoint or provider call. Identical evidence can recur after an intervening complete evaluation without losing freshness history, and the content-deduplicated recovery row points to the current revision's proposal.

The card projection now sums the materialized child sessions on the affected composite day. Unchanged prefix rows retain their real duration and contribute zero, while the displayed protected-duration delta is the before/after difference for the selected affected day. The web label is derived from the proposal target date and `as_of`. Real audit timestamps convert both clock and grouping day through `ATHLETE_TIMEZONE`, while recovery rows explicitly marked by type/source retain their business date; invalid timezone configuration has an explicit UTC fallback.

Validation at the latest local candidate tree: focused recovery/Today/decision/UI contour `122 passed`; contributor-safe suite `2338 passed, 3 skipped, 26 deselected`; Ruff passed; Next.js lint and production build passed; the TypeScript contract artifact is current. The first review-fix head `8bb8a57` also passed contributor-safe pytest, Playwright, the web contract check, and secret scanning before the scoped delta review. The three local skips and warnings are the known environment/deprecation baseline items. No local athlete database or provider was accessed.

## Context and Orientation

`api/recovery_replan_loop.py` builds and stores immutable recovery decisions plus one durable human-confirmed proposal. `data/database.py` owns SQLite lifecycle transitions. `api/routers/decisions.py` approves proposals and invokes planning mutations. `api/today_snapshot.py` projects the active proposal. `models/recovery_replan.py` and `models/planning_near_term.py` build the preview. `web/components/ui/ProposalCard.tsx` renders variant labels. Recovery decisions are immutable; proposals may move through lifecycle states; planning checkpoints are append-only.

The affected architecture requirements are ASR-REL-1, because a stale action must not corrupt plan/reconciliation lineage; ASR-REL-2, because incomplete readiness remains a data gap rather than fabricated recovery; and ASR-MOD-3, because legacy SQLite rows and TypeScript/API consumers must remain readable after additive lifecycle metadata.

## Plan of Work

First add database primitives that maintain one monotonic complete-evidence head per checkpoint, atomically reuse a proposal only for the same revision or supersede-and-replace a pending predecessor for a newer head, report an applying predecessor as in-flight, supersede pending recovery proposals after newer complete evidence, and atomically claim a proposal only when its evidence revision and fingerprint equal the head. Extend the allowed terminal statuses with `superseded`, retaining result reason and resolution time.

Then make the loop attach the complete-evidence revision and immutable recovery-decision fingerprint to proposal params/preview. A complete silence supersedes pending proposals for that checkpoint. A complete conflict refreshes the one same-target active proposal and supersedes other target proposals; a data gap leaves actionability unchanged.

Next make recovery day cards sum materialized child-session durations before and after the selected change, and make unchanged draft rows retain their current duration. Derive the Russian downgrade label from target date relative to `as_of`. Convert persisted UTC audit clocks through `Settings.ATHLETE_TIMEZONE`, with an explicit UTC fallback when configuration is invalid.

## Concrete Steps

Work from `/Users/gregkisel/Developer/ai_trainer` on `codex/issue-552-recovery-proposal-freshness`. Run focused tests while implementing:

    ai_trainer_env/bin/python -m pytest tests/smoke/test_recovery_replan_loop.py tests/smoke/test_api_today.py tests/smoke/test_coach_decisions.py tests/smoke/test_recovery_transfer_product_surface_web.py -q

Then run Ruff, web lint/build, contract freshness, and contributor-safe pytest exactly as listed in `AGENTS.md`.

## Validation and Acceptance

Tests must prove newer silence supersedes a pending proposal but preserves its row, data gap does not supersede, approval after a newer committed decision returns 409 with no checkpoint or provider write, and two racing operations yield one terminal result. A continuing same-target conflict keeps one active proposal whose revision, fingerprint, source key, event linkage, and preview match the newest evidence; the displaced event derives `no_change`. An applying predecessor is never reported as a successful publication, and the current revision can publish after that application fails. A → silence → identical A creates a fresh actionable revision and current recovery-row linkage. A composite-day fixture must show duration from the sums of materialized child sessions and zero contribution from unchanged rows. Source/UI tests must prove tomorrow/date wording, and API tests must prove UTC conversion and semantic local-day grouping in the athlete timezone plus honest invalid-timezone fallback.

## Idempotence and Recovery

Schema initialization remains additive and repeatable. Recovery decision content and planning checkpoints are never deleted or rewritten; only the separate per-checkpoint evidence head and the recovery row's current proposal pointer advance. Superseding is a conditional update from `pending` only. Re-running an identical current evaluation reuses the same decision/proposal, while recurrence after intervening complete evidence receives a new revision and proposal; retrying approval after a terminal transition returns 409. An in-flight collision creates no misleading card and becomes publishable on a later identical retry after failure. Provider delivery happens only after a successful evidence-current claim.

## Artifacts and Notes

Baseline at `d05b7e3`: focused recovery/Today/web contour 76 passed; contributor-safe suite 2323 passed, 3 skipped, 26 deselected.

## Interfaces and Dependencies

`data.database.Database` exposes revision-head and conditional recovery lifecycle methods returning deserialized proposal rows and machine-readable reasons. `api.recovery_replan_loop._proposal_payload` accepts the owning evidence fingerprint and revision. `api.routers.decisions.approve_proposal` uses the recovery-specific atomic claim before any plan/provider mutation. No external dependency is added; timezone conversion uses Python `zoneinfo`.

Revision note: initial executable specification created for issue #552 after source inspection and isolated falsifying probes. Updated after implementation to record the concurrent refresh edge, completed milestones, local validation evidence, and publication as PR #553. Updated after the first consolidated review to record all reproduced findings and the revisioned publication CAS, then after the scoped delta review to preserve proposal/event audit identity and semantic midnight handling. Merge remains an explicit human-gated workflow step.
