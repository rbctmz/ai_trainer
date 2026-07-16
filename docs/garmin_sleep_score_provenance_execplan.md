# Preserve Garmin sleep metrics and their provenance

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept current while Issue #207 is implemented. This document follows `.agent/PLANS.md`.

## Purpose / Big Picture

AI Trainer currently shows a locally derived sleep score as if Garmin supplied it. Garmin Connect returns the authoritative score inside `dailySleepDTO.sleepScores`, while the processor only checks a top-level `sleepScores` object. After this work, the sleep page, dashboard, readiness evidence, and downstream analytics will distinguish Garmin values from derived estimates. A normal Garmin resync can repair cached sleep rows without rewriting append-only readiness snapshots or decision history.

The user-visible proof is the 2026-07-16 fixture: Garmin reports 6 hours 42 minutes, score 62, stages 45/326/32 minutes, and 30 awake minutes. `/api/sleep/summary` must report score 62 with source `garmin`, an efficiency derived from actual awake time near 93.1%, and explicit provenance labels. The existing readiness evidence must say `оценка Garmin` only for source values.

## Progress

- [x] (2026-07-16 08:00 MSK) Reconciled Garmin CSV, local SQLite, API response, live read-only Garmin response, and readiness snapshot.
- [x] (2026-07-16 08:20 MSK) Created Issue #207 with the root cause, impact, and acceptance criteria.
- [x] (2026-07-16 08:45 MSK) Read the repository workflow, `.agent/PLANS.md`, and `docs/architecture/architecture_analysis_add3.md`; selected an additive provenance migration.
- [x] (2026-07-16 10:48 MSK) Added contributor-safe RED tests for nested, top-level, and missing Garmin scores, persistence migration, API provenance, and readiness wording; all six original scenarios failed on the intended contracts.
- [x] (2026-07-16 10:55 MSK) Implemented source-preserving extraction and actual-awake-time efficiency; the 2026-07-16 fixture now resolves to 62 Garmin and 93.1% from 30 awake minutes.
- [x] (2026-07-16 11:00 MSK) Added backward-compatible persistence, API/web contracts, demo provenance, and honest readiness/signal wording.
- [x] (2026-07-16 11:08 MSK) Validated 694 contributor-safe smoke tests, 736 broad non-live tests, Next lint, and the production web build.
- [x] (2026-07-16 11:18 MSK) Finalized the plan, self-reviewed the diff, pushed the branch, and opened draft PR #208 with `Closes #207`.

## Surprises & Discoveries

- Observation: all 31 cached sleep scores exactly match the fallback formula rather than Garmin scores.
  Evidence: a SQLite profile returned `scores_exact_fallback=31` for 31 rows.

- Observation: all 31 cached efficiencies exactly match `sleep_minutes / (sleep_minutes + awakenings_count * 5)`.
  Evidence: the same profile returned `efficiency_exact_fallback=31`; the latest UI value is 97.6%, while the actual 30 awake minutes imply about 93.1%.

- Observation: the live Garmin response contains no top-level `sleepScores` but does contain `dailySleepDTO.sleepScores.overall.value=62`.
  Evidence: a read-only request for 2026-07-16 returned `has_sleepScores=false` and the nested value 62. No sync or SQLite write occurred.

- Observation: rounded stage minutes can sum one minute above total sleep.
  Evidence: Garmin CSV and SQLite both contain 45+326+32=403 stage minutes against 402 total minutes. This is acceptable independent rounding, not corruption.

- Observation: demo awake minutes and demo efficiency must be generated from the same equation once both are visible.
  Evidence: self-review found the initial additive fields would have shown 18 awake minutes beside 86% efficiency for 435 sleep minutes. The fixture now derives awake minutes from its chosen efficiency.

## Decision Log

- Decision: accept both top-level and `dailySleepDTO` sleep score shapes, preferring the top-level object only when it is present and non-empty.
  Rationale: older fixtures and provider versions use the top-level shape; the current live response uses the nested shape. Supporting both avoids a provider-version regression.
  Date/Author: 2026-07-16 / Codex

- Decision: persist `awake_sleep_minutes`, `sleep_score_source`, and `sleep_efficiency_source` as additive nullable-compatible columns on `sleep_data`.
  Rationale: downstream consumers cannot safely infer provenance from a number. An additive migration satisfies ASR-MOD-3 and lets old databases open without destructive migration tooling.
  Date/Author: 2026-07-16 / Codex

- Decision: use source values `garmin`, `derived`, `demo`, and `legacy_unknown` for sleep score; use `derived_awake_time`, `derived_sleep_window`, `unavailable`, `demo`, and `legacy_unknown` for efficiency.
  Rationale: these values are small, stable, human-readable, and sufficient for current UI and readiness decisions without introducing a new provenance table.
  Date/Author: 2026-07-16 / Codex

- Decision: calculate efficiency from actual `awakeSleepSeconds` first, then from the observed sleep window when valid, and otherwise leave it unavailable. Do not estimate five minutes per awakening.
  Rationale: awakening count is not awakening duration. The old heuristic is systematically overconfident and has no source evidence.
  Date/Author: 2026-07-16 / Codex

- Decision: keep the existing derived sleep-score fallback but label it `derived`; readiness may continue to use the value in this PR but must not call it Garmin evidence.
  Rationale: removing the fallback changes readiness behavior for data sources that genuinely lack Garmin score and is a separate model-policy decision. Provenance makes that future decision possible without hiding the current behavior.
  Date/Author: 2026-07-16 / Codex

- Decision: do not mutate the real `ai_trainer.db` during implementation or tests. A normal user-confirmed Garmin resync is the backfill mechanism after merge.
  Rationale: `sync_sleep_data` already upserts historical sleep rows and post-sync recovery capture creates a new append-only readiness revision. Existing readiness snapshots and decision journals remain immutable.
  Date/Author: 2026-07-16 / Codex

- Decision: no new ADR is required.
  Rationale: this repair applies existing tactics—source provenance, additive SQLite compatibility, API contract tests, and append-only decision history—without introducing a new architectural direction.
  Date/Author: 2026-07-16 / Codex

## Outcomes & Retrospective

The implementation now preserves the live Garmin score shape and exposes metric provenance through processing, SQLite, API, readiness, signals, and the web UI. The sanitized 2026-07-16 fixture returns 402 total minutes, Garmin score 62, 30 awake minutes, and 93.1% efficiency derived from awake time. A legacy SQLite fixture retained its original row byte-for-value while additive columns appeared with `legacy_unknown` sources.

Validation completed with 694 passed and one environment-only socket skip in contributor-safe smoke; 736 passed, six expected skips, and 24 live/debug deselections in the broad non-live suite; Next lint and production build both succeeded. The maintainer's real cache has not been changed. After merge, a user-confirmed 31-day Garmin sync remains the only operational step needed to replace legacy cached estimates; existing append-only readiness snapshots remain historical evidence and are not rewritten.

## Context and Orientation

`data/data_processor_phase1.py` converts Garmin wellness payloads into normalized sleep dictionaries. `services/sync.py` collects those dictionaries and passes them to `data/database.py`, whose `sleep_data` table is the local canonical cache. `api/routers/sleep.py` projects cached rows into the FastAPI contract used by `web/app/sleep/page.tsx` and `web/components/dashboard/SleepWidget.tsx`. `models/readiness.py` and `models/signals_engine.py` consume the same cached sleep score.

“Source score” means a numeric score supplied by Garmin. “Derived score” means the local fallback formula used only when Garmin supplies no score. “Provenance” means the small source label stored next to a metric so a consumer can tell these cases apart. A “backfill” is a normal resync of recent Garmin days that updates the mutable `sleep_data` cache; it does not edit the append-only `readiness_snapshots`, `recovery_decisions`, or decision journal.

The relevant ADD 3.0 scenarios are ASR-REL-2 because readiness must degrade honestly instead of consuming a mislabeled metric, ASR-MOD-3 because existing SQLite files need an additive schema upgrade, ASR-PERF-3 because incremental sync must not gain extra provider calls, and ASR-SEC-1 because raw Garmin payloads and credentials must not enter logs or git. The implementation uses source tagging, idempotent schema migration, contract tests, and the existing append-only recovery journal as its reliability tactics.

## Plan of Work

First add a focused smoke module that captures the live nested Garmin shape, the legacy top-level shape, and a payload with no source score. The nested fixture must fail on current main by producing 47.7 instead of 62. Persistence tests must create an old `sleep_data` schema manually, initialize `Database`, and prove that the new columns appear without losing its row. API tests must prove source fields and awake minutes survive the round trip. A readiness test must prove derived evidence is not described as Garmin.

Then update `Phase1DataProcessor.process_sleep_data`. Resolve `sleep_scores` from top-level or nested data, validate the source score, and attach `sleep_score_source`. Preserve direct stage seconds. Store `awake_sleep_minutes` when `awakeSleepSeconds` exists. Replace the awakening-count efficiency heuristic with actual awake-time or sleep-window calculation and attach `sleep_efficiency_source`.

Next extend the `sleep_data` table and its upsert statements. Add an idempotent `_ensure_sleep_columns` migration following existing `daily_health` and `training_status` patterns. Existing rows receive `legacy_unknown`; freshly processed rows carry explicit source values. Demo rows receive `demo` sources so the product never claims that synthetic values came from Garmin.

Finally extend the API and TypeScript contracts. The sleep page and dashboard must display `Garmin` for source score, `расчётная` for derived score, and a short source label for efficiency. Add awake minutes without replacing the distinct awakening count. Update readiness evidence and normalized sleep signals to carry provenance. Do not add Streamlit-only behavior.

## Concrete Steps

Work from `/private/tmp/ai_trainer_issue207` on branch `codex/issue-207-garmin-sleep-score`.

Create and run the RED contour:

    python -m pytest tests/smoke/test_sleep_metric_provenance.py -q

After implementation run:

    python -m pytest tests/smoke/test_sleep_metric_provenance.py tests/smoke/test_api_phase3.py tests/smoke/test_readiness_snapshot_contract.py -q
    python -m pytest tests/smoke -q
    python -m pytest -m "not live and not debug" tests/ -q
    cd web && npm run lint && npm run build

No validation command may point at the real `ai_trainer.db`. No live Garmin call is required because the sanitized structure observed during diagnosis is captured as a fixture.

## Validation and Acceptance

The nested fixture with 402 total minutes, 45/326/32 stage minutes, two awakenings, 30 awake minutes, and score 62 must produce score 62 with source `garmin`, efficiency 93.1 with source `derived_awake_time`, and preserve the stage values. A top-level score fixture must retain its score and source. A missing-score fixture must produce a derived score with source `derived` and must not claim Garmin in readiness evidence.

An old SQLite file without provenance columns must open through `Database` and retain its existing sleep row while adding the new columns. Upserting a processed row must round-trip all provenance. `/api/sleep/summary` must expose source values, awake minutes, and an average-source summary. The web build must type-check and render labels without introducing a second business-rule implementation.

A regular sync after merge is idempotent: it updates the mutable sleep cache for requested dates. Existing append-only readiness snapshots remain unchanged; the post-sync capture creates a new current revision. This PR will not execute that backfill against user data.

## Idempotence and Recovery

The schema migration uses `PRAGMA table_info` and only adds missing columns. It is safe to run at every `Database` initialization. If two processes initialize the same database concurrently, duplicate-column errors for these specific columns are treated as a completed migration while unrelated SQLite errors still surface.

If the implementation fails before commit, discard only the issue worktree. If a resync after merge fails halfway, rerun the same sync window; `sync_sleep_data` upserts by date. Never delete or rewrite readiness snapshots or recovery decisions to make historical reports match the corrected cache.

## Artifacts and Notes

Diagnosis evidence retained in Issue #207:

    Garmin score: 62
    cached score: 47.7
    cached readiness: 53.8 limited
    estimate with corrected score only: 57.2 limited
    affected cached scores: 31/31 exact fallback
    affected cached efficiencies: 31/31 exact fallback

The source CSV remains local and is not committed because it contains personal wellness data.

## Interfaces and Dependencies

No new package dependency is needed. `Phase1DataProcessor.process_sleep_data` continues returning a dictionary and adds `awake_sleep_minutes`, `sleep_score_source`, and `sleep_efficiency_source`. `Database.sync_sleep_data` persists those keys. `Database.get_sleep_data` returns them as DataFrame columns. `GET /api/sleep/summary` adds the corresponding source fields while preserving all existing keys. The TypeScript `SleepSummary` interface mirrors that additive contract.

Revision note: created 2026-07-16 to turn the data-quality diagnosis in Issue #207 into an executable, restartable repair plan. Completed in draft PR #208. The plan explicitly preserves append-only readiness history and forbids real-database mutation during development.
