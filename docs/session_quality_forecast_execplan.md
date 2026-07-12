# Record and score session-quality forecasts in shadow mode

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must remain current while work proceeds. This document is maintained according to `.agent/PLANS.md`.

## Purpose / Big Picture

AI Trainer already knows today's recovery state, detects when that state conflicts with the plan, records the decision, and can propose a reversible downgrade. It cannot yet make a falsifiable statement before a key session and later show whether that statement was eligible to be judged. After this change, every fresh sync can write an immutable, versioned probability for the nearest planned `quality` or `long` session. A Wizard-of-Oz operator can later attach the actual session and the athlete's post-session quality rating. The system then either scores exactly one pre-start revision or records an explicit reason why the forecast is unscored.

The feature is deliberately shadow-only. It must not affect the readiness score, salience-gate, RecoveryReplanLoop outcome, planning checkpoints, proposals, `/today`, or Streamlit. Its observable output is a headless forecast journal and calibration summary, not a recommendation.

## Progress

- [x] (2026-07-12 09:22Z) Read Issue #161, `.agent/PLANS.md`, the canonical readiness/gate adapters, Recovery Replan, Today composition, Garmin activity ingestion, sync orchestration, and SQLite persistence.
- [x] (2026-07-12 09:22Z) Verified publish path and created isolated worktree `/tmp/ai_trainer_issue161_session_quality` on `codex/issue-161-session-quality-shadow` from current `origin/main` at `c824bd2`.
- [x] (2026-07-12 09:22Z) Pre-registered the exact `session_quality_v1` formula, timing rule, adherence boundaries, rating mapping, and calibration metrics in this plan before production data can be written.
- [x] (2026-07-12 09:34Z) Added BDD/TDD contracts for formula, adherence, timing, revisions, scoring, immutable facts, shadow isolation, API, and sync fail-open; red run stopped at the expected missing domain module.
- [ ] Implement source-backed activity start timestamps and additive forecast persistence.
- [ ] Implement the pure predictor, shadow orchestration, resolution, API, and post-sync integration.
- [ ] Update the WoZ schema without rewriting historical rows.
- [ ] Complete focused, adjacent, full, lint, compile, migration, concurrency, and self-review validation.
- [ ] Publish a draft PR with `Closes #161`, verify current-head CI, and finalize this plan.

## Surprises & Discoveries

- Observation: the source start timestamp already exists but is discarded.
  Evidence: `data/data_processor.py::ActivityProcessor.process_activities` reads `startTimeLocal` or `startTimeGMT` only to derive a calendar date. `activities` stores no source-backed start instant, so a rule that requires `forecast.created_at < session.started_at` is currently unverifiable.

- Observation: adherence and quality are independent observations.
  Evidence: the WoZ log has both a 3.5× overlong session and a skipped key session. Treating TSS deviation as "quality" would either score a different workout or remove genuine failures from the denominator. The post-session athlete rating therefore supplies quality ground truth; adherence only decides comparability.

- Observation: the existing `реакция_1_5` WoZ column cannot be reused.
  Evidence: it measures response to a recommendation, not perceived execution quality. Issue D needs a separate `качество_сессии_1_5` column.

- Observation: `/api/today` intentionally writes Recovery Replan state on read, while Issue D needs forecasts even when Coach/Today is not opened.
  Evidence: `api/routers/today.py` calls `run_recovery_replan_loop`, but the daily data-producing action is Garmin sync. The shadow recorder therefore belongs after successful sync, with an additional idempotent link when Recovery Replan later has a decision id.

- Observation: `docs/woz_tracking.csv` is intentionally local-only and absent from clean worktrees.
  Evidence: `.gitignore` ignores `*.csv`; `git ls-files docs/woz_tracking.csv` is empty. The PR must document the schema and provide a safe migration helper or instruction, while the user's local file is migrated separately without pretending it is a committed artifact.

- Observation: the red phase fails at the intended first missing boundary before any production code exists.
  Evidence: focused pytest reports `ModuleNotFoundError: No module named 'models.session_quality_forecast'` during collection. This proves tests depend on the new contract rather than accidentally exercising an existing helper.

## Decision Log

- Decision: target only the nearest planned `quality` or `long` session inside seven calendar days.
  Rationale: those are the repository's explicit key-stimulus roles. Predicting easy/recovery days would inflate sample size with low-stakes outcomes and dilute the WoZ hypothesis.
  Date/Author: 2026-07-12 / Codex.

- Decision: use a transparent deterministic rule named `session_quality_v1`, not an LLM or learned model.
  Rationale: the first purpose is a falsifiable logging/scoring contract. A learned model at n=1 would hide assumptions and invite leakage from the same outcomes used for evaluation.
  Date/Author: 2026-07-12 / Codex.

- Decision: preserve every changed readiness snapshot as an immutable revision, but score at most the latest revision created before actual session start.
  Rationale: overwriting loses evidence; scoring every revision creates correlated pseudo-samples. The latest pre-start rule is pre-registered and cannot be selected after seeing the outcome.
  Date/Author: 2026-07-12 / Codex.

- Decision: store Garmin `startTimeGMT` only as `activities.started_at_utc`; do not infer UTC from a timezone-less local timestamp.
  Rationale: a guessed timezone could incorrectly convert a post-start forecast into an eligible pre-start forecast. Missing GMT must produce `unscored: missing_session_start`.
  Date/Author: 2026-07-12 / Codex.

- Decision: use athlete rating 1–5 as v1 ground truth: 1–2 failure, 4–5 success, 3 ambiguous/unscored.
  Rationale: Garmin TSS and Training Effect are useful evidence but do not directly answer whether the intended stimulus felt qualitatively executable. A separate rating keeps the target explicit.
  Date/Author: 2026-07-12 / Codex.

- Decision: freeze the actual activity snapshot at resolution.
  Rationale: this repository can recalculate activity TSS after FTP/LTHR changes. A scored historical row must not change retroactively.
  Date/Author: 2026-07-12 / Codex.

- Decision: keep the ignored WoZ data local and commit only a canonical schema/migration contract.
  Rationale: force-adding personal CSV rows risks publishing sensitive metrics and contradicts the repository's data-security rule. The implementation will add a small safe migration utility or documented command and apply it only to the local ignored file.
  Date/Author: 2026-07-12 / Codex.

## Pre-registered `session_quality_v1` formula

The predictor accepts only a canonical readiness snapshot and an immutable planned-session snapshot. It must not read `activities`, prediction outcomes, `recovery_decisions` outcomes, or `docs/woz_tracking.csv`.

Required readiness inputs are `score` and `confidence`. If `score` is missing or confidence is below `0.60`, the predictor returns a data gap and no forecast row. Confidence is clamped to `[0, 1]`. The confidence-adjusted base probability shrinks uncertain readiness toward a coin flip:

    base = 50 + (readiness_score - 50) * confidence

The role-specific demand adjustment is deliberately small and capped to `[-10, +10]` points. For a `quality` session with positive planned duration, compute planned TSS density:

    density_tss_per_hour = planned_tss / (planned_duration_minutes / 60)
    demand_adjustment = clamp((50 - density_tss_per_hour) / 5, -10, +10)

For a `long` session with positive planned duration:

    demand_adjustment = clamp((90 - planned_duration_minutes) / 15, -10, +10)

If duration is missing or non-positive, demand adjustment is `0` and evidence explicitly says the demand adjustment was neutral because duration was unavailable. The final probability is:

    prediction_pct = round(clamp(base + demand_adjustment, 5, 95))

Bands are fixed: `low` below 60, `uncertain` from 60 through 74, and `high` from 75. Named constants must encode every number above. Examples, fixed before implementation:

1. readiness 75 at confidence 0.80, quality 60 TSS for 60 minutes: base 70, density 60, adjustment -2, forecast 68 (`uncertain`).
2. readiness 35 at confidence 0.80, the same quality session: base 38, adjustment -2, forecast 36 (`low`).
3. readiness 80 at confidence 1.00, long 20 TSS for 50 minutes: base 80, adjustment about +2.67, forecast 83 (`high`).

Changing any formula constant requires a new `rule_version`; historical rows are never recalculated.

## Adherence and scoring contract

The actual session role is supplied explicitly by the WoZ operator because Garmin activities do not carry the plan's role vocabulary. Actual sport, total TSS, duration, start UTC, and activity ids are copied from selected persisted activities.

`exact` means the actual role and sport equal the planned role and sport, and actual TSS is inclusively 80–120% of planned TSS. `substituted` means the role is equal and actual TSS is inclusively 60–140%, but `exact` is not satisfied; sport may differ. `major_deviation` means role differs or TSS lies outside 60–140%. Missing role/load evidence yields null adherence and `unscored: missing_adherence_evidence`.

At resolution, revisions are ordered by `created_at`. Revisions created at or after the earliest selected activity `started_at_utc` become `unscored: post_start_prediction`. Of the remaining pre-start revisions, only the latest is eligible; earlier ones become `unscored: superseded`. The eligible revision is still unscored when start time is missing, adherence is `major_deviation`, rating is 3/missing, or evidence is incomplete.

For rating 4–5, `quality_outcome = success` and numeric target `y = 1`. For rating 1–2, outcome is `failure` and `y = 0`. The scored row receives:

    brier_score = round((prediction_pct / 100 - y) ** 2, 4)

Calibration summaries count only `status = scored`. They report total/scored/unscored counts, unscored reasons, mean Brier score, and low-forecast hit rate: failures divided by scored forecasts below 60. At 10 scored rows, only process/data quality is reviewed. At 20–30 scored rows, the first descriptive calibration review is allowed, grouped by `rule_version`. No automatic threshold tuning exists.

## Outcomes & Retrospective

Implementation has not started. Success means the project can accumulate honest forecasts immediately while being explicit about non-attempts, substitutions, ambiguous ratings, and post-start leakage.

## Context and Orientation

Canonical recovery state comes from `api/readiness_snapshot.py::build_readiness_snapshot`, which calls the shared readiness model over stable windows. Planned sessions and gate reports are assembled by `api/readiness_conflicts.py`; the active plan is the latest row in `planning_checkpoints`. `api/recovery_replan_loop.py` persists gate outcomes and optional recovery proposals. None of these decision consumers may read Issue D output.

Activity ingestion starts in `data/data_processor.py::ActivityProcessor.process_activities`, flows through `services/sync.py::_sync_activities`, and is persisted by `data/database.py::Database.sync_activities`. The source payload contains `startTimeGMT`; the schema must preserve it additively as nullable UTC text.

FastAPI sync orchestration is `api/routers/system.py::sync`. Its background `run_sync` closure owns the database after ingestion succeeds, so it can call a fail-open shadow recorder. List/resolve routes should live in a new `api/routers/session_quality.py` and be registered in `api/main.py`. No web files are in scope.

## Behavioral Specification

Given the same canonical readiness, plan checkpoint, target session, and rule version, when recording runs repeatedly or concurrently, then one forecast fingerprint/revision exists.

Given readiness changes before the target session, when recording runs again, then a new immutable revision is appended while the old inputs/evidence remain unchanged.

Given two pre-start revisions and one post-start revision, when the target is resolved, then the latest pre-start revision alone may be scored; the older row is superseded and the post-start row is marked post-start.

Given exact or substituted adherence and an unambiguous rating, when resolution completes, then the eligible row contains frozen actual evidence, success/failure, and Brier score.

Given major deviation, missing start UTC, missing adherence evidence, or rating 3, when resolution completes, then no Brier score is written and the row has an explicit unscored reason.

Given a successful Garmin sync, when shadow recording fails, then sync still succeeds and exposes a non-fatal shadow error; no planning or recovery state changes.

## Milestones

Milestone one creates contract-first failures. Add pure predictor/adherence tests, activity timestamp processing/migration tests, persistence idempotency/concurrency tests, revision-resolution tests, API list/resolve tests, and post-sync fail-open tests. Record the exact red failures before production changes.

Milestone two establishes data integrity. Add `started_at_utc` to activity schema/order and normalize only `startTimeGMT`. Add `session_quality_predictions` plus migration-safe create/list/link/resolve methods. At the end, persistence and migration tests pass without API orchestration.

Milestone three implements the shadow domain. Add the pure predictor and adherence/scoring helpers under `models/session_quality_forecast.py`, then add orchestration under `api/session_quality_forecast.py`. Prove deterministic evidence, immutable revisions, latest-pre-start scoring, and frozen actual snapshots.

Milestone four exposes and invokes the journal. Add the headless router, register it, invoke recording after successful sync and idempotently from Recovery Replan when a decision exists, and extend the WoZ CSV header with a separate quality-rating column. Prove all existing decision/planning rows remain unchanged.

The final milestone runs full validation, performs self-review, updates this document, publishes a draft PR with `Closes #161`, and waits for CI on the final docs head.

## Plan of Work

Start with tests in a new `tests/smoke/test_session_quality_forecast.py` and focused additions to activity/sync tests. Tests should use temporary SQLite files and pure fixtures; they must not use live Garmin credentials or the real athlete database.

Extend `data/database.py` additively. Preserve existing activity column behavior while adding `started_at_utc`. Create the prediction table and indexes with `IF NOT EXISTS`. Revision allocation must use a SQLite write transaction so concurrent identical calls return one fingerprint and distinct snapshots receive monotonic revisions. Forecast input/evidence columns are immutable; resolution columns may transition once from pending.

Implement pure functions in `models/session_quality_forecast.py` for forecasting, adherence, and Brier calculation. Implement selection/recording/resolution in `api/session_quality_forecast.py`. The orchestrator reads the latest checkpoint and canonical report, selects the nearest quality/long plan row, hashes canonical inputs, and persists. Resolution validates activity ids from the database, freezes their fields, applies timing/adherence/rating rules atomically, and returns the target group.

Add `api/routers/session_quality.py` with `GET /api/session-quality-predictions` and `POST /api/session-quality-predictions/{prediction_id}/resolve`. The resolve payload carries activity ids, actual role, quality rating, and optional note. Invalid ratings/ids return HTTP 422/404 without partial updates.

Update `api/routers/system.py` so successful real sync calls the recorder in a try/except and adds a small shadow result/error field to the sync payload. Update Recovery Replan in a fail-open block only to idempotently link an existing/equivalent revision to its decision id. Never feed the result back into gate or proposal logic.

Finally add a committed canonical WoZ schema/migration note and migrate the user's ignored local CSV separately by adding `качество_сессии_1_5`. Append an empty field to existing rows mechanically so column alignment remains valid; do not reinterpret `реакция_1_5` and do not force-add personal CSV data.

## Concrete Steps

Run from `/tmp/ai_trainer_issue161_session_quality` using the main repository virtual environment:

    /Users/gregkisel/Developer/ai_trainer/ai_trainer_env/bin/python -m pytest tests/smoke/test_session_quality_forecast.py -q
    /Users/gregkisel/Developer/ai_trainer/ai_trainer_env/bin/python -m pytest tests/smoke/test_garmin_sync_service.py tests/smoke/test_sync_job_api.py tests/smoke/test_recovery_replan_loop.py tests/smoke/test_api_today.py -q
    /Users/gregkisel/Developer/ai_trainer/ai_trainer_env/bin/python -m pytest tests/smoke -q
    /Users/gregkisel/Developer/ai_trainer/ai_trainer_env/bin/python -m compileall -q api models services data
    ruff check api models services data tests/smoke
    git diff --check

The first focused run must fail because the new model/orchestration/persistence interfaces do not exist. The final smoke count must exceed the current-main baseline; the environment-specific local socket skip is acceptable.

## Validation and Acceptance

Acceptance requires direct evidence for the three scientific safety properties: no post-start scoring, no scoring of a materially different session, and no retroactive score change after activity TSS is updated. It also requires behavioral proof that shadow recording changes no planning checkpoint, gate outcome, recovery proposal, or `/decisions` payload.

The API OpenAPI schema must contain the list/resolve endpoints. Focused and full smoke must pass. Python compilation, Ruff, and diff check must be clean. No web build is required because no web files change.

## Idempotence and Recovery

All schema work is additive and repeatable. Existing activities receive null start UTC. Existing product behavior ignores the new table. A forecast recording failure is fail-open and cannot fail Garmin sync or Recovery Replan. Resolution is one-way; retrying returns the already resolved group rather than rewriting evidence. Test databases are disposable. Work only in the isolated worktree and remove it after the branch is safely pushed.

## Artifacts and Notes

Issue: `https://github.com/rbctmz/ai_trainer/issues/161`.

Starting base:

    c824bd2 Merge pull request #162

TDD red evidence:

    1 error during collection
    ModuleNotFoundError: No module named 'models.session_quality_forecast'

## Interfaces and Dependencies

No third-party dependency is added.

`models/session_quality_forecast.py` must expose pure equivalents of:

    build_session_quality_forecast(readiness: Mapping[str, Any], session: Mapping[str, Any]) -> dict[str, Any] | None
    classify_plan_adherence(planned: Mapping[str, Any], actual: Mapping[str, Any]) -> str | None
    brier_score(prediction_pct: float, quality_rating_1_5: int) -> float | None

`api/session_quality_forecast.py` must expose:

    record_shadow_session_quality_forecast(db: Database, *, report=None, checkpoint=None, recovery_decision_id=None) -> dict[str, Any]
    resolve_session_quality_prediction(db: Database, prediction_id: int, *, activity_ids: list[str], actual_role: str | None, quality_rating_1_5: int | None, note: str | None = None) -> dict[str, Any]
    summarize_session_quality_predictions(rows: list[Mapping[str, Any]]) -> dict[str, Any]

`Database` must provide additive create/get/list/link/resolve operations for prediction rows and an activity-id lookup that returns `started_at_utc`.

Revision note (2026-07-12): Initial plan created and formula pre-registered before tests or production implementation. It separates readiness probability, planned demand, adherence eligibility, and observed quality so the shadow track record remains falsifiable.
