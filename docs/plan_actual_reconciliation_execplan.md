# Reconcile planned sessions with actual activities and rebalance only the future

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept current as implementation proceeds. Maintain this file according to `.agent/PLANS.md`.

## Purpose / Big Picture

After this change, an athlete can open Planning and see which completed activities are matched to each planned session, why the match was made, what remains ambiguous or unplanned, and the full actual load without clamping. When the evidence is sufficient and completed load materially exceeds plan, the athlete can preview a conservative reduction to future easy sessions and explicitly confirm it. Past dates, today, races, rest days, coach constraints and manual edits remain unchanged. A stale preview cannot be applied.

This replaces the optimistic legacy behavior that labels missing or cross-sport evidence “as planned,” limits the view to the first days of the plan, clamps actual TSS to planned TSS, and rebuilds the entire plan after one click.

## Progress

- [x] (2026-07-13 10:19Z) Synced `main` after merged PR #171 and created isolated branch `codex/issue-172-plan-actual-reconciliation` in `/private/tmp/ai_trainer_issue172`.
- [x] (2026-07-13 10:27Z) Audited the active checkpoint, legacy execution matcher, Issue D adherence rules, Intervals client, SQLite patterns and web Adjust surface.
- [x] (2026-07-13 10:27Z) Pre-registered stable identity, evidence coverage and load-response formulas in this plan before tests or implementation.
- [ ] Add failing BDD/contract tests for session identity, matching, ledger revisions, provider evidence and future-only preview/confirm.
- [ ] Implement stable session identity and persist it through checkpoints/API exports.
- [ ] Implement bounded Intervals GET adapters and the append-only match ledger.
- [ ] Replace legacy reconciliation with evidence rows relative to explicit `as_of`.
- [ ] Implement deterministic future-only rebalance preview and stale-safe confirm.
- [ ] Replace the web optimistic outcome selector with evidence and preview/confirm UI.
- [ ] Run focused, smoke, broader non-live and Next.js build checks; perform synthetic 07–12 July acceptance.
- [ ] Self-review the full diff, finalize this living plan, push the branch and open a draft PR with `Closes #172`.

## Surprises & Discoveries

- Observation: the old matcher aggregates by `(date, sport)` and intentionally clamps a completed day to the planned load once either TSS or duration reaches 75 percent.
  Evidence: `models/planning_execution.py::_build_activity_prefill` returns `suggested_actual_total_tss = planned_tss` on that branch.

- Observation: the old window is `daily_plan[:weeks*7]`; it is unrelated to the review date.
  Evidence: `models/planning_execution.py::build_execution_reconciliation_rows` slices from index zero and has no `as_of` argument.

- Observation: the active activity table has Garmin `activity_id` and `started_at_utc`, but no persisted Intervals identifiers. Provider evidence therefore belongs in immutable match snapshots rather than in local activity identity.
  Evidence: `data/database.py::_ACTIVITY_COLUMN_ORDER` contains no Intervals columns.

- Observation: manual near-term edits store a count and horizon but not exact edited dates.
  Evidence: `models/planning_near_term.py::apply_near_term_day_edits` writes `edited_day_count` and `horizon_days`. This milestone must add `edited_dates` for future protection while conservatively treating the active legacy edit horizon as protected.

- Observation: local data on 2026-07-13 already proves that full actual load matters: multiple activities may share a sport and additional same-day sports must remain visible.
  Evidence: issue #172 records 08.07 as two rides totaling 64.2 TSS against 21.5 planned and 12.07 as a ride plus three swims.

## Decision Log

- Decision: use a deterministic opaque `ats_<hash>` session ID derived from a versioned material session signature, while explicitly preserving the prior ID when the material signature is unchanged.
  Rationale: preview and confirmation of the same normalized plan must agree without storing preview state. Date or array index alone is insufficient; random IDs would differ between preview and confirm. A changed signature produces a replacement ID and keeps `replaces_session_id`.
  Date/Author: 2026-07-13 / Codex.

- Decision: non-rest sessions receive IDs; rest days remain protected dates but are not sessions.
  Rationale: a session identity should name an intended workout. Treating rest as a workout would pollute match coverage and future composite support.
  Date/Author: 2026-07-13 / Codex.

- Decision: the match ledger table is `plan_actual_matches` and uses a required `target_key`, immutable JSON snapshots, fingerprint idempotency and append-only revisions.
  Rationale: `session_id` is nullable for unplanned activity groups, while `target_key` supports both `session:<id>` and `unplanned:<date>:<activity fingerprint>`. This follows the existing prediction/decision journal patterns without overwriting corrections.
  Date/Author: 2026-07-13 / Codex.

- Decision: automatic matching precedence is AI Trainer external ID, then user-confirmed ledger evidence, then a unique date-and-sport heuristic. A provider pair to an event without `ai_trainer:<session_id>` is supporting evidence only.
  Rationale: Intervals-created or manual events are not AI Trainer identity. The matcher must not silently claim that another product's workout fulfilled this plan.
  Date/Author: 2026-07-13 / Codex.

- Decision: heuristic matching may attach all same-date, same-sport activities to the single eligible planned session; other same-day activities remain unplanned. If more than one planned session or conflicting candidate can claim an activity, the result is ambiguous.
  Rationale: this represents split rides such as 08.07 without discarding load and remains composite-safe. Choosing one of multiple candidates would manufacture certainty.
  Date/Author: 2026-07-13 / Codex.

- Decision: never infer actual role by copying planned role. When a stable match exists but role is unknown, adherence is `unknown`, except that actual/planned load outside 0.60–1.40 is necessarily `major_deviation`. Exact/substituted classification otherwise reuses `models/session_quality_forecast.py::classify_plan_adherence`.
  Rationale: a same-sport activity is not proof that the intended stimulus was executed. A load ratio outside the outer boundary cannot be exact or substituted under any role.
  Date/Author: 2026-07-13 / Codex.

- Decision: a rebalance is evidence-eligible only with at least three completed planned sessions, matched coverage at least 0.70, zero ambiguous planned rows and no provider/data error that invalidates the evidence. Coverage is matched planned sessions divided by completed non-rest planned sessions in the requested lookback.
  Rationale: one or two matches are too fragile for a plan mutation. A visible ambiguity should be resolved before the system acts.
  Date/Author: 2026-07-13 / Codex.

- Decision: under-completion produces `no_change_under_plan`; it never adds future load. Over-completion below 10 TSS produces `no_change_below_threshold`.
  Rationale: this issue removes automatic catch-up and avoids noisy tiny edits.
  Date/Author: 2026-07-13 / Codex.

- Decision: for over-completion, the maximum reduction budget is `round_to_5(min(0.50 * overage_tss, 0.15 * next_7_day_future_tss, 40))`. The system reduces only future `easy` sessions inside the next seven days, proportionally, by at most 25 percent per session and never below 5 TSS. It does not alter quality, long, recovery or off sessions.
  Rationale: the formula responds to real excess without overcorrecting, preserves the key structure of the microcycle, and has explicit global and per-session ceilings. If eligible easy sessions cannot absorb the budget, the unused remainder is reported rather than moved elsewhere.
  Date/Author: 2026-07-13 / Codex.

- Decision: all dates `<= as_of`, event `protected_dates`, active coach-constraint dates, explicit `near_term_edit.edited_dates`, and the entire active legacy manual-edit horizon when exact dates are unavailable are byte-equivalent between base and preview.
  Rationale: these dates represent facts or explicit user intent. Conservative over-protection is safer than silently overwriting a legacy edit.
  Date/Author: 2026-07-13 / Codex.

- Decision: `GET /api/planning/reconciliation` is read-only and returns computed evidence plus the latest applicable user ledger revision. Automatic computation is frozen in the confirmed checkpoint snapshot; only explicit user confirm/reject endpoints append match-ledger corrections.
  Rationale: GET must remain retry-safe and should not create database history merely because a page refreshes. User corrections need durable append-only provenance.
  Date/Author: 2026-07-13 / Codex.

- Decision: replace `POST /api/planning/adjust` behavior with preview/confirm semantics while retaining a compatibility-shaped route during migration. Confirmation requires `base_checkpoint_id` and the exact preview fingerprint and returns HTTP 409 on a newer checkpoint.
  Rationale: the web surface already calls `/adjust`; evolving the contract avoids duplicate plan mutation paths while preserving a controlled migration.
  Date/Author: 2026-07-13 / Codex.

## Outcomes & Retrospective

Implementation is in progress. The current outcome is a frozen design contract and isolated branch. Update this section after each milestone with observed behavior, remaining gaps and test evidence.

## Context and Orientation

`api/planning_service.py` restores the latest plan checkpoint and owns Planning API orchestration. `models/planning_checkpoints.py` serializes the complete goal plan into `planning_checkpoints`; every confirmed plan change appends a row through `data/database.py::save_planning_checkpoint`. A checkpoint is the immutable version of the plan that stale guards compare.

`models/training_planner.py::build_daily_session_templates` creates one template aligned to each daily-plan entry. Templates currently contain date, role, sport, phase, duration and export text but no stable identity. `models/planning_execution.py` contains the old day-level execution matcher and full-horizon rebuilding logic. The new matching and rebalance rules should live in a focused headless module so API and web consume one contract; legacy summary helpers may remain for checkpoint explainability until their consumers migrate.

`data/database.py` stores local Garmin activities. `services/intervals_icu.py` is a small HTTP client that already performs bounded event discovery. It must gain bounded GET methods for completed activities and WORKOUT events, but this issue must not call provider POST/PUT/DELETE methods.

`models/session_quality_forecast.py` is the canonical source for adherence load bounds: exact is 0.80–1.20 with same sport and role; substituted is 0.60–1.40 with the same role; everything outside those bounds is major deviation. Unknown evidence is not a failure and does not enter adherence denominators.

`web/app/planning/page.tsx::AdjustMode` currently renders a select whose default is “as planned” and immediately POSTs rows to rebuild the plan. It must instead display evidence states, full activity load, match provenance, data quality, and a separate future diff that requires confirmation.

The term “match ledger” means an append-only table of immutable planned/actual evidence revisions. “Coverage” means matched completed non-rest planned sessions divided by all completed non-rest planned sessions in the requested lookback. “Unplanned load” means activity TSS that is visible in the window but is not assigned to a planned session. “Future-only rebalance” means a proposal that can reduce eligible easy sessions after `as_of`; it never modifies completed dates or today.

## Plan of Work

Milestone 1 establishes identity. Add `models/session_identity.py` with a versioned material-signature builder and `ensure_session_identities(goal_plan, previous_goal_plan=None)`. Call it after plan generation, event overlays, manual/recovery edits and execution rebalance, and before checkpoint serialization/restoration/API projection. Extend `plan_days` and TypeScript contracts. Add `edited_dates` to new manual near-term metadata. Tests first prove deterministic preview/confirm IDs, persistence, unchanged-ID preservation and replacement lineage.

Milestone 2 establishes evidence and history. Add `plan_actual_matches` schema/migration and Database save/read helpers with transactional revision allocation, fingerprint idempotency and immutable deserialization. Extend `IntervalsICUClient` with date-bounded read adapters and pure normalization helpers. Add `models/plan_actual_reconciliation.py` with activity normalization, provider-evidence joins, match precedence, unplanned rows, adherence classification and aggregate metrics. The main response includes base checkpoint, explicit as-of/lookback, rule versions, coverage, data-gap reasons and full load totals.

Milestone 3 establishes suggestion-only rebalance. In the same domain module add a pure preview builder that applies the pre-registered formula to a deep copy of the active plan and returns before/after rows, changed count, future TSS delta, unused reduction and a fingerprint. Recompute affected weekly totals, refresh changed template descriptions, preserve protected dates and run `ensure_session_identities` against the base plan. In `api/planning_service.py`, preview from the latest checkpoint and confirm only against the same checkpoint/fingerprint. Confirmation appends source `weekly_rebalance` with the entire reconciliation and diff in the snapshot. It never writes Intervals.

Milestone 4 migrates the product surface. Extend `api/routers/planning.py` request/response behavior and error mapping. Replace the optimistic selector in `web/app/planning/page.tsx` with evidence badges, matched-activity details, unplanned rows, data-quality guidance, preview and explicit confirm. On HTTP 409, discard the local preview and refetch. Update `web/lib/types.ts` contract-first.

Milestone 5 validates and publishes. Run focused tests, all contributor-safe smoke tests, broader non-live tests and a production Next build. Run a synthetic acceptance fixture reproducing 07–12 July without external writes. Inspect the final diff for data loss, hidden load, lookahead, race/manual overwrite, concurrent revision allocation, stale apply and backward compatibility. Finalize this plan, commit in logical order, push and open a draft PR linking issue #172.

## Concrete Steps

Work from `/private/tmp/ai_trainer_issue172`.

First create tests and prove they fail for the missing contracts:

    source /Users/gregkisel/Developer/ai_trainer/ai_trainer_env/bin/activate
    python -m pytest tests/smoke/test_plan_actual_reconciliation.py -q

Implement each milestone and rerun that focused file plus affected existing suites:

    python -m pytest tests/smoke/test_plan_actual_reconciliation.py tests/smoke/test_planning_execution.py tests/smoke/test_api_planning.py tests/smoke/test_intervals_icu_service.py -q

Before publication run:

    python -m pytest tests/smoke -q
    python -m pytest -m "not live and not debug" tests/ -q
    cd web && npm run build

The synthetic acceptance must show an old plan reviewed at `as_of=2026-07-13` returning only the relative completed window; 64.2 actual TSS remaining 64.2 against 21.5 planned; cross-sport facts not defaulting to exact; extra swims remaining visible; ambiguity blocking preview; and a confirmed preview creating exactly one new checkpoint after a successful stale check.

## Validation and Acceptance

Identity acceptance passes when the same normalized plan preview and confirmation expose identical non-rest session IDs, a checkpoint round-trip preserves them, unchanged sessions retain IDs after rebalance and changed sessions have a new ID with lineage.

Reconciliation acceptance passes when every activity in the window appears exactly once either as matched evidence or unplanned evidence; actual TSS is never capped; future plan dates are not treated as completed facts; ambiguous evidence is visible; and the aggregate denominator excludes unknown/ambiguous/unplanned rows.

Rebalance acceptance passes when insufficient coverage or ambiguity returns `data_gap`; under-plan and small-overage windows return an explicit no-change reason; an eligible overage changes only allowed future easy dates within the formula bounds; protected bytes are identical; stale confirm returns 409 without writes; and successful confirm appends one restorable `weekly_rebalance` checkpoint containing evidence and diff.

Product acceptance passes when the web page no longer preselects “По плану,” displays plan and full actual load with activity IDs/provenance, shows unplanned activities, requires preview before confirm and recovers from stale state by refetching.

## Idempotence and Recovery

Schema creation uses `CREATE TABLE IF NOT EXISTS` and indexes that can be rerun. Match submissions use a deterministic fingerprint and transactional revision allocation; an identical retry returns the existing revision. Preview is pure and can be repeated. Confirm is append-only and guarded by the latest checkpoint. If confirmation fails, no partial checkpoint or provider write exists. A confirmed plan remains restorable through the existing checkpoint history.

Do not delete or rewrite old execution checkpoints. Legacy checkpoints without IDs are upgraded in memory with deterministic IDs and persist them only when a new checkpoint is explicitly confirmed.

## Artifacts and Notes

Issue: `https://github.com/rbctmz/ai_trainer/issues/172`.

Baseline commit: `3c94b70` (merged PR #171). The prior main baseline was 501 passed and one skipped; update exact final counts after validation.

The live Intervals observations in the issue are read-only design evidence. Tests must use sanitized fixtures and must not store API credentials or raw personal payloads.

## Interfaces and Dependencies

In `models/session_identity.py` provide:

    SESSION_ID_RULE_VERSION = "session_identity_v1"
    def ensure_session_identities(goal_plan: Mapping[str, Any], previous_goal_plan: Mapping[str, Any] | None = None) -> dict[str, Any]

In `models/plan_actual_reconciliation.py` provide pure entry points resembling:

    MATCH_RULE_VERSION = "plan_actual_match_v1"
    REBALANCE_RULE_VERSION = "weekly_rebalance_v1"
    def build_reconciliation(goal_plan, activities, *, as_of, weeks, base_checkpoint_id, provider_activities=None, provider_events=None, ledger_rows=None) -> dict[str, Any]
    def build_weekly_rebalance_preview(goal_plan, reconciliation, *, as_of, protected_dates=()) -> dict[str, Any]
    def apply_weekly_rebalance_preview(goal_plan, preview) -> dict[str, Any]

In `data/database.py` add transaction-safe methods:

    def save_plan_actual_match(self, payload: Mapping[str, Any]) -> dict[str, Any]
    def get_latest_plan_actual_matches(self, *, start_date: str, end_date: str) -> list[dict[str, Any]]

In `services/intervals_icu.py` add bounded GET methods that reject reversed or excessive windows and normalize only fields needed by the matcher. Do not add a dependency or a provider write.

In `api/planning_service.py`, reconciliation accepts explicit `as_of`; preview and confirm return the same versioned contract. `StalePlanningCheckpointError` maps to HTTP 409. Request DTOs in `api/routers/planning.py` include base checkpoint and preview fingerprint. TypeScript interfaces in `web/lib/types.ts` mirror the API without reimplementing matching or load rules.

Revision note (2026-07-13 / Codex): created the initial self-contained ExecPlan after source audit and pre-registered all identity, evidence-threshold and load-response decisions before writing tests.
