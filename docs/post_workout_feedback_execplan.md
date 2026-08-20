# Record athlete-entered post-workout feedback and score forecasts from it

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must remain current while work proceeds. This document is maintained according to `.agent/PLANS.md`.

## Purpose / Big Picture

After this change, the athlete can open the web-first “Today” screen after a planned session, record what actually happened, rate whole-session effort from 1 through 10, and separately rate whether the intended training quality succeeded from 1 through 5. The saved observation is an athlete-entered fact with visible provenance, correction history, and a frozen plan-versus-actual match. Session-quality forecasts consume that fact through an append-only evaluation journal; feedback is useful even when no forecast exists and never changes readiness or the plan by itself.

The user-visible proof is a compact post-session card under the existing “Yesterday · plan vs fact” block. A matched completed session produces one prompt, an explicit submission returns revision 1, a correction returns revision 2 without deleting revision 1, and a repeated request with the same client fingerprint returns the same revision. The existing admin resolve endpoint remains compatible, but it must create the same match, feedback, and evaluation records rather than maintain a second scoring path.

## Progress

- [x] (2026-07-13 19:05Z) Read Issue #175, the reviewer’s pre-ExecPlan audit, `.agent/PLANS.md`, the repository workflow/ADR, and the current Today, reconciliation, forecast, SQLite, API, web, and test contracts.
- [x] (2026-07-13 19:05Z) Created isolated worktree `/private/tmp/ai_trainer_issue175` on `codex/issue-175-post-workout-feedback` from `origin/main` at `c105de9`.
- [x] (2026-07-13 19:05Z) Pre-registered the append-only schemas, prompt lifecycle, time provenance, quality semantics, compatibility bridge, and no-duplicate-reconciliation boundary in this plan before product implementation.
- [x] (2026-07-13 19:22Z) Added the first BDD/TDD contract for time provenance, prompt states, bricks, non-start timing, independent RPE/quality, append-only/idempotent feedback, correction evaluations, stats/clear, and API routes; the red run stopped at the expected missing domain module.
- [x] (2026-07-13 19:48Z) Implemented transaction-safe feedback, prompt-event, and forecast-evaluation persistence; idempotency, concurrent retry, correction lineage, stats, and clear tests pass.
- [x] (2026-07-13 19:48Z) Implemented pure prompt/time/evaluation rules plus headless submission, correction, tombstone, dismissal, history, summary, projection, and `admin_resolve` compatibility orchestration.
- [x] (2026-07-13 19:56Z) Added FastAPI lifecycle contracts and fail-open Today composition; a focused test proves one provider-disabled reconciliation call and no journal writes on repeated reads.
- [x] (2026-07-13 19:56Z) Added the web feedback card with anchored completion/RPE/quality controls, evidence summary, athlete-entered provenance, retry-safe submit, explicit correction/history, dismiss, and ambiguous-match guidance.
- [x] (2026-07-13 21:04Z) Completed focused, smoke, broad, Python/web lint, production-build, migration/concurrency, and copy-of-real-database browser acceptance; self-review removed the legacy scoring path and hardened revision/dismissal migration behavior.
- [x] (2026-07-13 22:50Z) Addressed the pre-merge retry review: the web retains one fingerprint until success, the service returns an existing identical request before reconciliation, rejects a second active submit, and SQLite atomically enforces the expected latest revision.
- [x] (2026-07-13 22:36Z) Pushed `codex/issue-175-post-workout-feedback` and opened draft PR #184 with `Closes #175`; merge remains at the human gate.

## Surprises & Discoveries

- Observation: the current forecast “resolution” mutates columns on `session_quality_predictions` even though forecast inputs themselves are immutable.
  Evidence: `data/database.py::resolve_session_quality_prediction_group` updates status, adherence, quality, actual snapshot, unscored reason, Brier score, and resolved time in place. User-correctable feedback therefore requires a separate append-only evaluation table rather than another update method.

- Observation: Today v2 already computes yesterday’s reconciliation without provider traffic.
  Evidence: `api/today_snapshot.py::_yesterday_reconciliation` calls `reconciliation_at(..., include_provider=False)` and returns full planned rows, match state, activities, adherence, rule version, and checkpoint. The prompt composer can consume that block directly; calling the provider again would add latency and Intervals.icu rate-limit pressure without adding evidence.

- Observation: automatic reconciliation rows are computed views, while explicit corrections live in `plan_actual_matches`.
  Evidence: `models/plan_actual_reconciliation.py::build_reconciliation` exposes actual activity IDs and frozen-shape evidence, and `data/database.py::save_plan_actual_match` appends only explicit user revisions. A feedback POST must revalidate the selected session against a local-only reconciliation rather than trust evidence JSON sent by the browser.

- Observation: activity end time is derivable from source-backed fields but is not stored.
  Evidence: local activities contain `started_at_utc` and `duration_minutes`. The canonical end is the latest `started_at_utc + duration_minutes` across matched activities. A missing start remains unknown; local time must never be guessed as UTC.

- Observation: the same quality mapping is already a scientific contract in three places.
  Evidence: Issue D and `docs/session_quality_forecast_execplan.md`, `models/session_quality_forecast.py::brier_score`, and `docs/woz_tracking_schema.md` all define 1–2 as failure, 3 as ambiguous/unscored, and 4–5 as success.

- Observation: the contract-first red phase fails at the intended first missing boundary.
  Evidence: `python -m pytest tests/smoke/test_post_workout_feedback.py -q` stops during collection with `ModuleNotFoundError: No module named 'models.post_workout_feedback'`; no product implementation exists yet.

- Observation: an automatic match has no required ledger revision by design, but an admin compatibility resolve can create one without changing the automatic GET contract.
  Evidence: user submissions freeze the computed match with nullable `match_revision_id`; the admin bridge appends `match_method=admin_resolve`, then the same feedback/evaluation service runs. The focused bridge test shows the raw forecast remains `pending` while the projected result is `scored`.

- Observation: the first headless milestone is green before Today/web integration.
  Evidence: `python -m pytest tests/smoke/test_post_workout_feedback.py -q` reports `19 passed`, including a two-connection SQLite retry and the admin bridge.

- Observation: Today can add feedback without increasing reconciliation/provider work.
  Evidence: the composition regression test records exactly one call with `include_provider=False`, obtains a ready prompt from the supplied `yesterday` row, and verifies `session_feedback` remains empty after the GET.

- Observation: the web contract compiles without a frontend copy of matching or scoring rules.
  Evidence: `npm run lint` reports no warnings/errors and `npm run build` compiles `/today`; the component only renders API-provided prompt state and posts athlete values.

- Observation: the first self-review found that leaving the legacy resolver body in place would preserve a second, mutable scoring implementation even if the router no longer called it.
  Evidence: the compatibility function now delegates directly to `resolve_prediction_via_feedback`; regression tests prove raw prediction rows remain pending/immutable while projected evaluations stay frozen after activity TSS changes.

- Observation: prompt dismissal identity must describe the material evidence, not merely the athlete-day.
  Evidence: dismissal events now store `prompt_fingerprint`; an unchanged prompt remains dismissed while changed match/activity evidence can prompt again without deleting history.

- Observation: additive SQLite migrations can race when two test/API processes initialize the same file.
  Evidence: the parallel validation exposed simultaneous `ALTER TABLE ... ADD COLUMN prompt_fingerprint`; initialization now treats only the competing `duplicate column name` result as success and still raises unrelated operational errors.

- Observation: live product data contains a safe eligible prompt and exercises the correction path without fixture invention.
  Evidence: a temporary copy of `ai_trainer.db` produced one ready matched cycling prompt. The browser saved athlete-entered RPE 8 and quality 4 as revision 1, corrected quality to 3 as revision 2, and displayed both immutable history rows. The real database was never opened for writes.

- Observation: a client-generated idempotency key is ineffective when regenerated on every click, and a service-only latest check still leaves a two-writer race.
  Evidence: the pre-merge review reproduced revision 2 with no `supersedes_feedback_id` after a simulated lost response. The final contract keeps a `useRef` fingerprint through failures, returns the identical request before revalidation, maps a distinct second submit to 409, and checks `expected_latest_feedback_id` inside the same `BEGIN IMMEDIATE` transaction that allocates the revision. Regression coverage includes two different fingerprints racing across separate SQLite connections.

## Decision Log

- Decision: persist athlete observations in `session_feedback`, prompt dismissals in `session_feedback_prompt_events`, and forecast outcomes in `session_quality_evaluations`.
  Rationale: an observation, a UI prompt lifecycle, and a model evaluation have different lifetimes. Keeping them separate prevents a dismissed prompt from masquerading as feedback and prevents a corrected observation from rewriting a historical forecast.
  Date/Author: 2026-07-13 / Codex.

- Decision (M0 follow-up): keep `session_feedback` as the canonical event journal and append a separate `athlete_feedback_facts` row for each new feedback revision.
  Rationale: the future athlete-file/Preferences layer needs a durable provenance boundary, but raw feedback must not be copied into `athlete_profile` or mutable `user_settings`. The fact ledger is storage-only and is not read by TSS, planning, readiness, or provider delivery.
  Date/Author: 2026-08-20 / Codex. See `docs/durable_rpe_feedback_fact_execplan.md`.

- Decision: derive “current” state by the highest revision per target instead of updating a `current` flag.
  Rationale: a mutable current marker would weaken the append-only guarantee and create a two-row race. Transactional monotonic revisions plus `supersedes_*_id` retain lineage and make current state a query result.
  Date/Author: 2026-07-13 / Codex.

- Decision: feedback target identity is `session:<session_id>`; a composite workout uses the parent session ID and stores the optional parent ID plus every matched leg activity ID in one observation.
  Rationale: one planned brick is one athlete experience and must prompt once. Activity evidence remains one-to-many, so bike and run legs are not lost.
  Date/Author: 2026-07-13 / Codex.

- Decision: `session_rpe_1_10` and `quality_rating_1_5` are nullable observations; completion is required. The web form asks for both ratings for completed/partial/stopped sessions, while `did_not_start` and tombstones may omit them.
  Rationale: Issue #175 explicitly allows `did_not_start` without quality and forbids treating absence as failure. Null must remain an explicit unknown rather than a fabricated neutral value.
  Date/Author: 2026-07-13 / Codex.

- Decision: quality uses the existing pre-registered mapping unchanged: 1–2 failure, 3 ambiguous/unscored, 4–5 success. RPE and quality are never inferred from each other or from TSS, duration, heart rate, Training Effect, completion, adherence, or proposal reaction.
  Rationale: this is the shared contract in Issue D, `brier_score`, and the WoZ schema. Changing it during data collection would invalidate calibration.
  Date/Author: 2026-07-13 / Codex.

- Decision: every user submission freezes the planned row, actual activities, match status/method/confidence, adherence, rule version, and explicit match revision ID when one exists. Automatic matches may have no persisted match revision; the feedback row stores null `match_revision_id` plus the complete frozen computed match snapshot. Admin resolve first appends an explicit `admin_resolve` match revision, so its feedback and evaluation always have a match revision.
  Rationale: #172 deliberately keeps GET computation read-only. Requiring a ledger write for every page render would violate that contract, but feedback still needs immutable provenance. Admin compatibility inputs are otherwise outside #172 and need an auditable bridge.
  Date/Author: 2026-07-13 / Codex.

- Decision: the Today snapshot builds prompt state from its already-computed `yesterday` block. The standalone prompt endpoint may call local-only reconciliation, and submission/correction may revalidate with `include_provider=False`; the Today web page never calls both `/today` and a second prompt endpoint.
  Rationale: this preserves one provider-free reconciliation computation per Today render and answers the reviewer’s rate-limit concern. A state-changing POST is allowed one local revalidation to avoid trusting the browser.
  Date/Author: 2026-07-13 / Codex.

- Decision: a ready auto-prompt requires a past or completed planned session and either a matched row with confidence at least 0.75 or an explicit user/admin-confirmed match. Ambiguous rows remain `pending_match`. An unmatched past row may expose a `did_not_start` entry only after its calendar day has elapsed, but it cannot claim adherence.
  Rationale: the threshold matches the existing unique date/sport heuristic. The exception is necessary to record a real non-start without inventing an activity match.
  Date/Author: 2026-07-13 / Codex.

- Decision: derive session end as the maximum source-backed `started_at_utc + duration_minutes` among matched activities. If start or duration is missing, end remains unknown and the prompt is not due on the same date. A no-activity `did_not_start` prompt becomes eligible only when the application’s calendar date is later than the planned date; no synthetic UTC timestamp is stored.
  Rationale: this follows the source-time rule from #165 and the reviewer audit without adding a redundant database column or pretending a local calendar date is UTC.
  Date/Author: 2026-07-13 / Codex.

- Decision: add `session_quality_evaluations` with one immutable evaluation revision per forecast prediction and feedback revision. New feedback never updates `session_quality_predictions`; API projections overlay the latest evaluation for backward-compatible status/summary fields.
  Rationale: corrections must supersede evaluations without rewriting forecast evidence. Projection preserves the existing list/resolve response shape while establishing the new source of truth.
  Date/Author: 2026-07-13 / Codex.

- Decision: the compatibility `POST /api/session-quality-predictions/{id}/resolve` appends an `admin_resolve` match revision, synthesizes an `admin_resolve` feedback revision, evaluates through the shared service, and returns projected predictions. It does not call the legacy in-place resolver.
  Rationale: quality has one source and scoring has one implementation from migration day one.
  Date/Author: 2026-07-13 / Codex.

- Decision: historical `docs/woz_tracking.csv` rows are not imported.
  Rationale: they have no stable session ID, match revision, activity evidence, or submission provenance. Importing them would turn manual notes into falsely precise canonical facts.
  Date/Author: 2026-07-13 / Codex.

- Decision: display `athlete-entered` beside user feedback in the web UI and return `provenance_label` in API projections. `admin_resolve` remains visibly administrative.
  Rationale: unlike IntervalCoach’s automatic N/10 activity score, this product treats quality as an explicit athlete observation. The provenance is part of the evidence, not internal metadata.
  Date/Author: 2026-07-13 / Codex.

- Decision: retain the client submission fingerprint across failed retries and clear it only after a successful response; atomically require the latest feedback ID expected by each append.
  Rationale: stable client identity handles a lost response, while the SQLite optimistic check prevents two distinct first-submit requests from creating unlinked revisions. A deliberate later change must use the correction endpoint and name its superseded revision.
  Date/Author: 2026-07-13 / Codex.

## Outcomes & Retrospective

The implementation and local acceptance milestones are complete. The project now has separate append-only observation, prompt-event, and evaluation journals; pure prompt/time/quality semantics; and one compatibility path that turns the old admin resolve request into an explicit match plus feedback plus evaluation. Raw forecast rows are not changed by new resolutions, while API projections preserve familiar status fields. Today embeds one provider-free prompt block and the web exposes athlete-entered submit/correct/history UX.

Final validation is green after the pre-merge retry fix: focused contract coverage reports `72 passed`, contributor-safe smoke reports `587 passed, 1 skipped`, the broader non-live suite reports `630 passed, 6 skipped, 24 deselected`, Ruff and `compileall` pass, Next lint has no warnings, and the production build includes `/today`. Browser acceptance on a temporary copy of the real database demonstrated revision 1, correction revision 2, and both rows in append-only history with visible athlete-entered provenance. No provider write, historical WoZ import, plan mutation, Streamlit feature, or write to the real database was introduced.

Self-review and pre-merge review caught and closed five boundary risks before merge: the old mutable resolver implementation was removed instead of merely bypassed; tombstones append an unscored evaluation so an old score cannot remain current; repeated admin corrections create proper feedback/evaluation lineage; material prompt fingerprints make dismissals expire only when evidence changes; and lost-response retries can no longer create an unlinked duplicate revision. The only remaining operational follow-up is longitudinal product observation: #176 can consume these athlete-entered samples once enough revisions accumulate.

## Context and Orientation

`api/today_snapshot.py::build_today_decision_snapshot` is the headless source for the web “Today” screen. It runs the recovery loop, composes readiness, current session, proposal, shadow forecast, and a provider-free `yesterday` reconciliation. `web/app/today/page.tsx` renders that contract. Feedback must be added to this API/web path; Streamlit is not a product target for this issue.

`models/plan_actual_reconciliation.py::build_reconciliation` compares stable planned `session_id` values with local activities. It returns `matched`, `ambiguous`, or `unmatched`, actual activity IDs/snapshots, confidence, match method, and adherence. `plan_actual_matches` stores explicit corrections as immutable revisions. “Frozen match snapshot” in this plan means copying all evidence needed to understand the observation later even if FTP, TSS, plan checkpoint, or matching rules change.

`session_quality_predictions` stores immutable pre-session forecast inputs but currently also contains legacy mutable resolution columns. `api/session_quality_forecast.py::resolve_session_quality_prediction` implements existing scoring. The new evaluation service will own those rules, write `session_quality_evaluations`, and project latest evaluation fields onto forecast API responses. Legacy resolved rows remain readable; new rows are not mutated.

The “prompt” is a derived instruction that feedback is appropriate, not the feedback itself. Prompt state is computed from plan/fact evidence, latest feedback, and the latest dismissal event. States are `not_eligible`, `pending_match`, `ready`, `submitted`, `superseded`, and `dismissed`. Only dismissals need their own persisted event; ready/submitted/superseded are derived.

## Behavioral Specification

Given a matched completed quality session, when Today is loaded repeatedly, then it exposes one ready prompt for the parent session and creates no database row merely because the page was read.

Given RPE 9 and quality 5, when feedback is submitted, then both values persist unchanged and the latest eligible forecast evaluates to success. Given RPE 3 and quality 1, then the values remain independent and the forecast evaluates to failure.

Given quality 3, when feedback is submitted, then the observation is valid and the forecast evaluation is `unscored` with reason `ambiguous_quality`.

Given an ambiguous reconciliation row, when prompts are composed, then its state is `pending_match`; a feedback request cannot turn it into exact or substituted adherence. A later explicit match revision can make it eligible.

Given a composite brick with bike and run evidence, when feedback is submitted for the parent session, then one feedback target contains both activity IDs and Today does not offer a prompt per leg.

Given the same client fingerprint twice, when both requests reach SQLite concurrently, then both responses identify the same feedback row and exactly one revision exists.

Given a correction, when the user confirms it, then a new feedback revision points to the previous row, new evaluation revisions supersede previous evaluations, calibration reads only latest evaluations, and full history remains queryable.

Given a session without a forecast, when feedback is submitted, then history contains the observation and no synthetic forecast or evaluation is created.

Given a session that has not started or whose latest derived activity end is in the future, when prompt state is computed, then it is not due. Given a no-activity planned session on the current date, then `did_not_start` is not due until the following calendar date.

Given the legacy admin resolve endpoint, when it receives valid activities, role, and quality, then it appends one explicit match revision, one `source=admin_resolve` feedback revision, and shared evaluation revisions; it never mutates forecast input or legacy resolution columns.

## Persistence Contract

Create `session_feedback` with integer primary key; unique non-empty client fingerprint; `target_key`; monotonic revision; nullable `supersedes_feedback_id`; required `session_id`; nullable `parent_session_id` and `match_revision_id`; required frozen `match_snapshot_json`; required `actual_activity_ids_json`; required completion status; nullable completion percentage plus `completion_pct_source`; nullable RPE and quality; nullable note; source; nullable derived session end UTC and its provenance; status `active` or `tombstone`; rule/schema version; and submitted/created timestamps. Unique `(target_key, revision)` and fingerprint indexes protect identity.

Create `session_feedback_prompt_events` with unique fingerprint, session ID/target key, event `dismissed`, optional reason, source, rule version, and created time. The latest dismissal is ignored after a newer active feedback revision or a materially changed prompt fingerprint.

Create `session_quality_evaluations` with unique fingerprint; `target_key=prediction:<prediction_id>`; monotonic revision; nullable `supersedes_evaluation_id`; prediction ID/target key; feedback ID; nullable match revision ID; evaluation status `scored` or `unscored`; adherence; copied quality rating and outcome; unscored reason; nullable Brier score; frozen evidence JSON; rule version; and created time. Evaluation insertion and revision allocation use `BEGIN IMMEDIATE`.

Schema initialization is additive with `CREATE TABLE IF NOT EXISTS` and indexes. Existing SQLite files migrate on normal `Database` initialization. Clearing/statistics helpers include the new tables. No personal observation is added to fixtures outside temporary or sanitized test databases.

## API Contract

Add a router under `/api/session-feedback` and register it in `api/main.py`.

`GET /api/session-feedback/prompts` returns prompt objects from a local-only reconciliation. The Today web page does not call it; `/api/today` embeds the same prompt projection under `feedback` from its existing `yesterday` block.

`POST /api/session-feedback` accepts `session_id`, `client_submission_fingerprint`, `completion_status`, nullable completion percentage, nullable RPE, nullable quality, and note. It revalidates the current local match and appends revision 1. Invalid ranges, a current/in-progress session, or an ambiguous unconfirmed match return 422/409 without writes.

`POST /api/session-feedback/{feedback_id}/correct` accepts a new client fingerprint and replacement values, requires the supplied row to be the latest current revision, and appends a revision. A stale correction returns 409.

`POST /api/session-feedback/{feedback_id}/tombstone` appends a tombstone revision. `POST /api/session-feedback/prompts/{session_id}/dismiss` appends an idempotent dismissal event. `GET /api/session-feedback/{session_id}/history` returns every revision and current evaluation projections. `GET /api/session-feedback/summary` returns counts, response/correction rates, RPE/quality/completion distributions, submission lag, and forecast scored/unscored reasons; sample sizes accompany any grouping.

The existing forecast list and resolve routes keep their response shape. They add feedback/evaluation identifiers and provenance fields. Legacy already-resolved rows remain visible as legacy resolution provenance; all new admin resolves use the feedback service.

## Plan of Work

Milestone one adds contract-first failures. Create focused smoke tests for schema migration, fingerprint idempotency under two SQLite connections, correction/tombstone history, prompt states, source-backed end derivation, same-day in-progress guards, unmatched non-start timing, brick one-to-many evidence, RPE/quality independence, quality 3, no-forecast storage, latest-pre-start evaluation, and the admin bridge. Add API route/validation tests and Today composition tests that monkeypatch reconciliation to prove it is called once with provider disabled. Record the expected missing-module/table failures.

Milestone two establishes persistence and the pure domain. Add the three tables and transaction-safe database methods. Add `models/post_workout_feedback.py` for validation, canonical fingerprints, prompt-state composition, activity-end derivation, and evaluation classification. This pure module must not import FastAPI, web, provider clients, readiness, or plan mutation services.

Milestone three establishes orchestration. Add `api/session_feedback.py` to restore the relevant checkpoint/session, perform local-only reconciliation for writes, freeze match evidence, append/correct/tombstone feedback, create evaluations, overlay latest evaluation onto forecast rows, build summaries, and implement the admin bridge. The bridge appends an explicit `plan_actual_matches` revision with `match_method=admin_resolve`; reconciliation must treat that method as authoritative exactly like `user_confirmed`.

Milestone four exposes API and Today. Add request models/routes, register the router, and extend `api/today_snapshot.py` so feedback composition receives `yesterday`, goal plan, forecast, and a supplied UTC clock. It must not call `reconciliation_at` itself. Preserve Today’s fail-open property: a feedback-journal error produces an unavailable feedback block while readiness, plan, gate, and proposal remain usable.

Milestone five wires the web. Extend `web/lib/types.ts` and `web/app/today/page.tsx` with a compact client form. Show completion choices, anchored RPE and quality controls, optional note, frozen match evidence, and the provenance label “athlete-entered.” Submission uses a random client fingerprint retained for retries, shows the saved revision, and refreshes `/today`. Correction is an explicit action; history is expandable. Do not add a Streamlit form.

Milestone six validates and publishes. Run focused and adjacent tests, contributor-safe smoke, broader non-live pytest, TypeScript/lint/production build, migration/concurrency checks, and a browser acceptance against a temporary copy of the real database with alternate ports. Confirm no provider writes and no writes to the real database. Self-review correctness, race behavior, backward compatibility, privacy, and complexity; update this plan, commit logical milestones, push, and open a draft PR with `Closes #175`.

## Concrete Steps

Work from `/private/tmp/ai_trainer_issue175` and activate the existing environment:

    source /Users/gregkisel/Developer/ai_trainer/ai_trainer_env/bin/activate

Create the focused tests first and run:

    python -m pytest tests/smoke/test_post_workout_feedback.py -q

After the domain/persistence milestone, run the focused file plus forecast, reconciliation, and Today suites:

    python -m pytest tests/smoke/test_post_workout_feedback.py tests/smoke/test_session_quality_forecast.py tests/smoke/test_plan_actual_reconciliation.py tests/smoke/test_api_today.py -q

Before publication run:

    python -m pytest tests/smoke -q
    python -m pytest -m "not live and not debug" tests/ -q
    cd web && npm run lint && npm run build
    git diff --check origin/main...HEAD

Acceptance uses a copied database in `/private/tmp`, alternate API/web ports, and the local browser. It must demonstrate one eligible historical prompt, idempotent submission, visible athlete-entered provenance, correction history, and a forecast evaluation when eligible. If the real copied data has no safe eligible row, use a sanitized temporary fixture for the UI while still running migration/read-only inspection against the copy.

## Validation and Acceptance

Persistence acceptance passes when an existing database initializes safely; two concurrent identical submissions produce one row; distinct corrections get monotonic revisions; tombstones retain history; and no method updates a prior feedback/evaluation row.

Prompt acceptance passes when matched completed sessions prompt once, ambiguous sessions request match resolution, bricks prompt once with all activities, same-day in-progress sessions do not prompt, no-activity non-starts wait until the next day, dismissals are idempotent, and repeated Today reads create no journal rows.

Scoring acceptance passes when RPE and quality persist independently; only quality 1–2/4–5 produces failure/success; quality 3 remains unscored; major deviation, unknown adherence, missing start, and post-start forecasts remain explicitly unscored; only the latest pre-start forecast revision scores; corrections create new evaluation revisions; and feedback without forecasts remains valid.

Compatibility acceptance passes when admin resolve returns the familiar forecast group and summary while the database shows an `admin_resolve` match, feedback, and evaluation and unchanged raw forecast rows. Legacy resolved predictions still appear in list summaries.

Product acceptance passes when the Today page retains all five #174 states and structured #173 sessions, renders the feedback card from the same snapshot, labels user values athlete-entered, saves explicit revisions, recovers from retry/stale errors, and remains usable when the feedback service fails.

## Idempotence and Recovery

All schema creation is rerunnable. Every write uses a caller fingerprint and a SQLite immediate transaction, so a network retry returns the existing row. Corrections require the latest feedback ID; stale concurrent edits cannot fork silently. Forecast evaluation can be rerun because its fingerprint includes prediction ID, feedback ID, match revision, and rule version.

No migration deletes or rewrites legacy forecast resolutions. If the new service fails, the transaction rolls back and Today degrades only its feedback block. If local acceptance fails, stop the alternate servers and delete only the temporary database/worktree artifacts. Never modify or publish `ai_trainer.db`, `docs/woz_tracking.csv`, `.env`, or logs.

## Artifacts and Notes

Issue: `https://github.com/rbctmz/ai_trainer/issues/175`.

Reviewer audit: `https://github.com/rbctmz/ai_trainer/issues/175#issuecomment-4961305288`.

Baseline: `c105de9`, merged PR #183. Contributor-safe baseline reported by the previous milestone is `563 passed, 1 skipped`; final counts must be recorded from this branch.

No historical WoZ row is imported. `docs/woz_tracking_schema.md` remains explanatory prior art only.

## Interfaces and Dependencies

In `models/post_workout_feedback.py`, provide version constants and pure functions resembling:

    FEEDBACK_RULE_VERSION = "session_feedback_v1"
    EVALUATION_RULE_VERSION = "session_quality_evaluation_v1"
    def derive_session_end_utc(activities, *, now_utc) -> tuple[str | None, str]
    def build_feedback_prompts(rows, *, templates, latest_feedback, prompt_events, forecasts, now_utc, as_of) -> dict[str, Any]
    def evaluate_prediction(prediction, feedback, match_snapshot, *, latest_eligible_id) -> dict[str, Any]

In `data/database.py`, provide transaction-safe append/read methods for feedback, prompt events, and evaluations. Each save method returns the persisted row plus whether it was created.

In `api/session_feedback.py`, provide orchestration resembling:

    def feedback_from_today_evidence(db, *, yesterday, goal_plan, forecast, now_utc) -> dict[str, Any]
    def submit_session_feedback(db, payload, *, now_utc=None, source="user_web") -> dict[str, Any]
    def correct_session_feedback(db, feedback_id, payload, *, now_utc=None) -> dict[str, Any]
    def resolve_prediction_via_feedback(db, prediction_id, *, activity_ids, actual_role, quality_rating_1_5, note=None) -> dict[str, Any]

Request/response schemas live in `api/routers/session_feedback.py`. TypeScript interfaces mirror the API; frontend code contains presentation and request state only, never matching, prompt eligibility, or scoring rules.

Revision note (2026-07-13 / Codex): created the initial self-contained ExecPlan after the issue/reviewer/source audit and pre-registered all data, timing, provenance, compatibility, and composition decisions before tests or product implementation. Updated after the red BDD/TDD run, the green headless milestone, the Today/web milestone, self-review hardening, full validation, browser acceptance on a copied real database, and the pre-merge retry fix to preserve evidence and actual progress.
