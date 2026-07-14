# Build prospective personal recovery-response curves with evidence gates

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must remain current while work proceeds. This document is maintained according to `.agent/PLANS.md`.

## Purpose / Big Picture

After this change, AI Trainer will begin collecting verifiable, prospective evidence about how this athlete recovers after comparable training stimuli. A post-sync readiness observation becomes an immutable, versioned daily fact. A completed planned session becomes an immutable recovery episode that freezes its plan, actual activity evidence, adherence, athlete feedback, readiness anchor, D+1 through D+3 outcomes, and confounders. A read-only analytical projection groups only eligible episodes into personal cohorts and exposes a recovery curve only after the pre-registered sample gates are met.

The feature is intentionally shadow analytics. It does not alter readiness, the recovery conflict gate, coach proposals, planning, provider data, or device delivery. With the current data, the web page must lead with “идёт сбор данных”, show coverage and machine-readable exclusion reasons, and refuse to draw an authoritative curve. Later, when one cohort has at least ten eligible episodes, the same page can show median readiness change and IQR for D+1, D+2, and D+3; at twenty episodes it adds a deterministic cluster-bootstrap interval; at thirty episodes across at least eight ISO weeks it may label the result a non-causal `shadow_pattern`.

The user-visible proof is a new web-first recovery analytics surface backed by explicit FastAPI contracts. Repeated GET requests create no rows. Repeated post-sync capture with the same run identity returns the same readiness revision. A later same-day sync appends a new revision. Missing pre-session time provenance, missing D+2 evidence, a major plan deviation, or an unresolved brick remains visible as missing or excluded and is never converted to zero or silently mixed into a curve.

## Progress

- [x] (2026-07-14 08:40Z) Read Issue #176, `.agent/PLANS.md`, the repository workflow and ADR, and the current readiness, sync, reconciliation, catalog, feedback, SQLite, API, web, and test contracts.
- [x] (2026-07-14 08:40Z) Audited the live local database read-only: 58 activities, 48 HRV days, 47 sleep days, 48 daily-health days, 18 training-status days, 11 forecast revisions, one athlete feedback row, and source UTC start time on only 5 of 58 activities.
- [x] (2026-07-14 08:40Z) Published the pre-ExecPlan audit in Issue #176, including the historical look-ahead defect, missing athlete timezone, prospective/backfill boundary, write-event materialization boundary, and proposed statistical rules.
- [x] (2026-07-14 08:42Z) Created isolated worktree `/private/tmp/ai_trainer_issue176` on `codex/issue-176-recovery-curves` from clean `main` at `38de146`.
- [x] (2026-07-14 08:43Z) Recorded the contributor-safe baseline: `587 passed, 1 skipped`.
- [x] (2026-07-14 09:05Z) Pre-registered the persistence, temporal anchoring, episode, cohort, uncertainty, API, web, and no-mutation contracts in this plan before product code.
- [x] (2026-07-14 09:30Z) Added 37 BDD/TDD scenarios for no-look-ahead readiness, snapshot eligibility/revisions/concurrency, temporal anchors, load/RPE buckets, missing outcomes, exact sample/week gates, deterministic bootstrap, prospective separation, independent RPE overlays, read-only API, and route registration; the red run failed at the expected missing domain/service/table/route boundaries.
- [x] (2026-07-14 11:10Z) Implemented the as-of-safe canonical readiness service, `ATHLETE_TIMEZONE`, v2 provenance, and append-only prospective snapshot journal with atomic same-run retry and same-day revisions.
- [x] (2026-07-14 11:30Z) Implemented the append-only recovery episode ledger and provider-free write-event materializer over current reconciliation, catalog, match, feedback, constraints, and D+1 through D+3 snapshot evidence.
- [x] (2026-07-14 11:35Z) Implemented deterministic cohort projections, exact sample/week gates, independently gated RPE overlays, and week-cluster bootstrap intervals.
- [x] (2026-07-14 11:40Z) Exposed read-only FastAPI summary/detail routes and the web-first `/recovery` collection/maturity surface; no Streamlit-only feature or decision mutation was added.
- [x] (2026-07-14 11:50Z) Completed focused, smoke, broad, web build, migration/concurrency, copy-of-real-database, and browser acceptance; self-review closed historical TSB anchoring, retry identity, terminal lifecycle ordering, exclusion normalization, and feedback-note privacy.
- [x] (2026-07-14 12:35Z) Addressed independent review with executable regressions: time-only `maturing` to `eligible` now appends revision 2, late manual matches refresh at the current date, backfilled anchor selection honors its requested mode, and direct API route registration no longer leaves a dead `APIRouter` contract.
- [ ] Push the review fix to draft PR #187 and obtain the reviewer’s final verification before merge.

## Surprises & Discoveries

- Observation: the canonical readiness calculation is only partly historically bounded.
  Evidence: `models/readiness.py::compute_readiness_today` filters activities before TSB calculation, but the HRV, sleep, daily-health, and training-status frames reach `_split_frame` without `date <= anchor`; `_split_frame` then chooses the latest row. Recomputing a past date can therefore consume a future physiological row.

- Observation: the current readiness API contract lacks a scientific identity.
  Evidence: `api/readiness_snapshot.py::build_readiness_snapshot` returns score, status, factors, confidence, `computed_at`, missing inputs, and TSB, but no rule version, observed time, athlete timezone, sync/run identity, capture mode, immutable input fingerprint, or revision lineage. The stress factor also has `as_of=None` even though it comes from the selected HRV evidence.

- Observation: there is no canonical athlete timezone, and using process local time would change behavior after self-hosted deployment.
  Evidence: `config/settings.py` has no timezone field; `user_settings` currently contains only `planning_demand_level`. Product code alternates between UTC and `datetime.now().date()`. A VPS commonly runs UTC while the athlete’s Garmin calendar dates are local.

- Observation: most existing activities cannot prove a pre-session boundary.
  Evidence: the live database contains `started_at_utc` on 5 of 58 activities. The field was added recently and the processor correctly refuses to guess UTC from a local timestamp. Historical rows may be useful as explicitly backfilled context but cannot enter the primary prospective cohort.

- Observation: the API sync job ID is not available inside the shared sync function.
  Evidence: `api/sync_jobs.py::SyncJobManager` allocates its process-local job ID around a zero-argument closure, while both the web API and legacy shell call `services/sync.py::SyncService.sync_garmin_data`. A scientific capture must therefore use its own stable `capture_run_id` inside the shared sync service rather than pretend the API job ID is universal.

- Observation: existing append-only journals provide the correct concurrency pattern.
  Evidence: `session_quality_predictions`, `plan_actual_matches`, and `session_feedback` use unique fingerprints, monotonic target revisions, `BEGIN IMMEDIATE`, and frozen JSON evidence. Recovery snapshots and episodes can reuse this pattern rather than introduce an ORM or mutable current flags.

- Observation: the structured catalog has no field literally named `stimulus_family`, but it has a stable versioned builder key.
  Evidence: each `definition_snapshot` contains `step_builder_key`, `stimulus`, load bounds, version, and catalog version. The prose `stimulus` is descriptive and can change; `step_builder_key` is the stable v1 cohort family such as `recovery`, `endurance`, `threshold`, `vo2`, `brick_endurance`, or `brick_race_pace`.

- Observation: one completed planned session can exist without athlete feedback, while feedback already freezes the best available match evidence when present.
  Evidence: reconciliation computes matched sessions read-only, and `session_feedback.match_snapshot_json` freezes its planned/actual evidence and optional match revision. Recovery episodes must allow nullable RPE and quality rather than exclude objective episodes merely because the athlete did not answer the prompt.

- Observation: explicit illness and travel evidence already has a durable source.
  Evidence: `coach_constraints` stores `sick` and `unavailable` constraints, with `travel` normalized to `unavailable`. Inferring illness from low HRV would be circular and is outside the issue.

- Observation: the contract-first red phase reaches every intended new boundary without touching product code.
  Evidence: `python -m pytest tests/smoke/test_recovery_response.py tests/smoke/test_api_recovery_analytics.py -q` reports 37 failures for missing `services.readiness_snapshot`, `models.recovery_response`, readiness journal methods, recovery router, and route registration. Both new test files pass `py_compile`.

- Observation: a historical `as_of` fix must bound the activity query itself, not only filter an already current-relative frame.
  Evidence: the first implementation called the existing `get_activities(90)`, whose cutoff is relative to process “now”. Self-review replaced it with `get_activities_between(as_of - 89 days, as_of)` before TSB calculation; the readiness/dashboard regression tests stayed green.

- Observation: Next.js build in an isolated worktree needs worktree-local dependencies even when the main checkout has a complete `node_modules`.
  Evidence: lint passed through a borrowed executable path, but build could not resolve `next/dist/lib/metadata` until `npm ci` populated the worktree. The clean rerun compiled `/recovery` and all thirteen static pages successfully.

- Observation: the current real database correctly remains collection-only rather than manufacturing a historical curve.
  Evidence: acceptance on `/private/tmp/ai_trainer_issue176_real_acceptance.db`, copied from the 58-activity local database, appended one eligible readiness snapshot, returned the same ID on same-run retry, created zero retrospective episodes, exposed zero cohorts, and left proposal/decision counts unchanged. The original database mtime and size were identical before and after.

- Observation: the in-app browser rendered the new route and loaded the expected collection contract from the alternate-port acceptance stack.
  Evidence: DOM acceptance at `http://localhost:3016/recovery` showed the navigation link, “Персональное восстановление”, visible `shadow`, one reliable snapshot, zero episodes, “Сбор данных”, and “Идёт сбор данных”; both local processes were stopped afterward.

- Observation: an episode lifecycle transition can be material even when every evidence row and outcome remains unchanged.
  Evidence: independent review reproduced a session with only pre and D+1 snapshots. Refresh at D+1 stored `maturing`; refresh after D+3 returned the same fingerprint and left revision 1 stuck. The regression test first failed with `created=0`, then passed after lifecycle `status` was added to the frozen fingerprint.

- Observation: explicit match corrections need the observation clock, not the planned-session clock.
  Evidence: `record_plan_actual_match` previously refreshed with `as_of=session_date`, so confirming an older session re-ran lifecycle rules as though no time had elapsed. The hook now supplies the current date, while the materializer itself still bounds candidate session dates and provider access remains disabled.

## Decision Log

- Decision: extract the canonical database-backed readiness builder into `services/readiness_snapshot.py`; keep `api/readiness_snapshot.py` as a compatibility import/projection boundary.
  Rationale: sync orchestration must not import the API layer. Both API reads and post-sync recording must call one headless implementation, while existing imports should keep working during migration.
  Date/Author: 2026-07-14 / Codex.

- Decision: introduce `ATHLETE_TIMEZONE` as a validated IANA timezone setting and freeze it in every snapshot and episode. The initial documented default is `Europe/Moscow`, matching the current single-athlete deployment; an invalid value produces an explicit data gap and prevents scientific capture.
  Rationale: silently using the host timezone would move local dates and noon/activity cutoffs after VPS deployment. A single configuration field is the minimum correct contract; a timezone settings UI is not part of this issue.
  Date/Author: 2026-07-14 / Codex.

- Decision: `READINESS_SNAPSHOT_RULE_VERSION` becomes `readiness_snapshot_v2`. Every input frame is filtered to `date <= as_of` before the readiness model selects a row, and every included factor must report an `as_of` no later than the snapshot local date.
  Rationale: this closes the demonstrated look-ahead path while preserving the existing current-day score semantics. TSB remains bounded by the same date.
  Date/Author: 2026-07-14 / Codex.

- Decision: persist every capture attempt that has a valid timezone and computed readiness, including scientifically ineligible observations, in `readiness_snapshots`; store frozen eligibility status and reasons alongside the complete snapshot.
  Rationale: exclusion must be auditable. Dropping weak snapshots would hide coverage and make the denominator unknowable.
  Date/Author: 2026-07-14 / Codex.

- Decision: readiness snapshot target identity is `readiness:<capture_mode>:<local_date>`. Its idempotency fingerprint is the immutable pair `capture_mode + capture_run_id`; the complete rule version, local date/timezone, observation time, inputs, eligibility, and canonical snapshot are frozen in the resulting row. A retry of one run returns that row even if the retry clock differs; a new UUID on a later same-day sync appends a revision even when values are unchanged.
  Rationale: run identity, not the caller’s retry timestamp, distinguishes a network retry from a separate observation. Monotonic daily revisions retain intraday history without a mutable current flag, and the unique capture-run index closes concurrent duplicates.
  Date/Author: 2026-07-14 / Codex.

- Decision: a primary eligible readiness snapshot has a score, confidence at least `0.60`, `stale=false`, no included primary factor marked stale, a valid timezone, an explicit `as_of_date`, and all included factor dates at or before that `as_of_date`. Primary factors are HRV, resting heart rate, sleep, and training readiness; TSB is required to obey `as_of` but is not physiological freshness evidence. Missing inputs are allowed only when the canonical confidence still reaches the gate.
  Rationale: this is the exact eligibility interpretation requested in Issue #176. It preserves the current confidence model while preventing stale evidence from masquerading as a strong partial snapshot.
  Date/Author: 2026-07-14 / Codex.

- Decision: only `capture_mode=prospective` enters primary curves. `backfilled` rows, if an explicit administrative backfill is added for acceptance or later research, use separate target keys and remain excluded from prospective denominators and aggregates.
  Rationale: reconstructed observations were not actually available before the session and cannot validate prospective behavior.
  Date/Author: 2026-07-14 / Codex.

- Decision: the daily anchor is the latest eligible prospective snapshot observed before the earlier of the first source-proved activity start and local 12:00. If the day has any relevant activity but its start time is missing, the pre-session anchor is unprovable and the episode receives `activity_start_missing`; the system never substitutes midnight, noon, or the database insertion time. D+1, D+2, and D+3 use the same day-specific rule.
  Rationale: a readiness observation after exercise would reverse cause and effect. Failing closed is more important than historical coverage.
  Date/Author: 2026-07-14 / Codex.

- Decision: post-sync scientific recording runs in the shared sync service after caches are cleared. A UUID `capture_run_id` is allocated once per sync invocation, returned in sync details, used for idempotent snapshot capture, and followed by episode materialization. Match and feedback write endpoints also invoke the same episode materializer after their own transaction commits.
  Rationale: web and legacy sync paths then behave consistently, while analytics GET remains read-only. Match/feedback corrections can create a new episode revision immediately rather than waiting for another sync.
  Date/Author: 2026-07-14 / Codex.

- Decision: recovery episode target identity is `session:<parent_session_id>`. A composite brick produces one episode with ordered leg evidence; it is excluded as `unresolved_brick` unless the frozen actual evidence proves all required leg sports. Episode revisions supersede by parent session, and the fingerprint includes the selected snapshot IDs, current match/feedback evidence IDs or fingerprints, rule versions, frozen session/actual payloads, and confounders.
  Rationale: one planned brick is one training stimulus and one athlete experience. Revisioning by stable session identity preserves corrections without double-counting legs.
  Date/Author: 2026-07-14 / Codex.

- Decision: episodes may exist without feedback. RPE, quality, and completion are frozen when present; a completed matched session with objective load remains observable with null feedback fields. Tombstoned feedback produces a new episode revision without those athlete-entered values.
  Rationale: response rate is a KPI, not an eligibility requirement for objective readiness recovery. Null must not be interpreted as neutral or zero.
  Date/Author: 2026-07-14 / Codex.

- Decision: episode lifecycle is `open`, `maturing`, `eligible`, or `excluded`. `open` lacks a proved completed match or pre-anchor; `maturing` has a valid pre-anchor but D+3 has not yet elapsed; `eligible` has passed the cohort rules and may have missing individual D outcomes; `excluded` has one or more terminal machine-readable reasons. Every material change appends a revision.
  Rationale: a missing D+2 observation should remain visible without blocking D+1 and D+3. Terminal methodological failures must be distinguishable from an episode that is merely young.
  Date/Author: 2026-07-14 / Codex.

- Decision: lifecycle `status` is part of the episode fingerprint, and a late explicit match refreshes recovery episodes with the current date rather than the session date.
  Rationale: elapsed D+3 time is itself a material state transition even when no new snapshot arrives. Using the current clock also lets an old match enter its correct mature lifecycle immediately without mutating prior revisions.
  Date/Author: 2026-07-14 / Codex.

- Decision: primary episode exclusions are `capture_mode_mismatch`, `missing_pre_anchor`, `activity_start_missing`, `ambiguous_match`, `unknown_adherence`, `major_deviation`, `unversioned_stimulus`, `missing_actual_load`, `did_not_start`, and `unresolved_brick`. Explicit `sick` or `unavailable` constraints are stored as confounders and exclude the primary cohort with `explicit_health_or_travel_constraint`. Multiple same-day sessions, intervening load, and an accepted proposal are visible confounders but do not silently exclude; the API reports them and may stratify them.
  Rationale: the list is conservative and machine-readable. It separates evidence failure from observational context without inventing medical facts.
  Date/Author: 2026-07-14 / Codex.

- Decision: the primary outcome is `readiness_delta_dN = score(D+N) - score(pre)`. `recovered_by_day` is the first D+1 through D+3 with delta at least `-5`. A missing daily snapshot produces null, never zero. Secondary frozen observations are HRV deviation, resting heart rate, sleep score/duration, and TSB when source-backed.
  Rationale: this is the issue’s pre-registered outcome and keeps the first version interpretable.
  Date/Author: 2026-07-14 / Codex.

- Decision: `stimulus_family` is `definition_snapshot.step_builder_key`; the human stimulus text is also frozen but is not an identity. Cohort identity is `stimulus_family + sport + actual_load_bucket + adherence`. Actual-load buckets are `low` below 40 TSS, `moderate` from 40 through 79.9, and `high` at least 80. RPE overlays are low 1–3, moderate 4–6, and high 7–10 and require their own independent sample gate.
  Rationale: stable builder semantics survive copy changes. Frozen absolute v1 load bands avoid re-bucketing old episodes when athlete thresholds or the plan change.
  Date/Author: 2026-07-14 / Codex.

- Decision: cohort gates are `collection_only` for n below 10; `early_signal` with median and IQR for n 10–19; `exploratory` with the same summaries plus intervals for n 20–29; and `shadow_pattern` only at n at least 30 across at least eight distinct ISO weeks. A cohort with n at least 30 but fewer than eight weeks remains `exploratory` with `week_concentration` evidence. No gate produces causal language.
  Rationale: these are the issue gates, with the week requirement applied as an explicit maturity guard rather than hidden caveat.
  Date/Author: 2026-07-14 / Codex.

- Decision: uncertainty uses 2,000 percentile cluster-bootstrap resamples of ISO weeks with replacement. Each sampled week contributes all its eligible episodes; the statistic is the median delta for the selected day. The PRNG seed is deterministically derived from the fixed base seed 176, cohort ID, and D+ day. The 2.5th and 97.5th percentiles form the interval.
  Rationale: resampling whole weeks is more honest than treating several same-week sessions as independent. The stable seed and sorted inputs make rebuilds byte-for-byte deterministic.
  Date/Author: 2026-07-14 / Codex.

- Decision: v1 persists only readiness and episode journals. Cohort aggregates are deterministic projections over the latest episode revision and are not stored.
  Rationale: a third mutable/published aggregate table would add invalidation and correction complexity without improving the small-n product. GET remains read-only and reproducible.
  Date/Author: 2026-07-14 / Codex.

- Decision: expose `GET /api/recovery-analytics` for coverage and cohort registry and `GET /api/recovery-analytics/cohorts/{cohort_id}` for points and episode evidence. Add `/recovery` to the Next.js shell as “Восстановление”. Before n=10, the page shows collection maturity and exclusions but no curve; at later gates it renders a dependency-free D+1–D+3 SVG/semantic table from API values.
  Rationale: this is the smallest web-first surface that makes data collection and scientific refusal visible without adding a BI framework or duplicating analysis in TypeScript.
  Date/Author: 2026-07-14 / Codex.

## Outcomes & Retrospective

The implementation now delivers the prospective scientific collection loop end to end. Successful shared Garmin sync appends a versioned readiness observation and refreshes episodes after cache invalidation; explicit plan/actual matches and feedback revisions refresh the same materializer after their source transaction commits. The materializer is provider-free, preserves composite sessions as one parent, allows objective episodes without feedback, and refuses missing time provenance, major deviations, unversioned stimuli, and explicit health/travel confounders. GET projections are read-only and deterministic.

The product surface is deliberately modest at current n. `/recovery` leads with evidence maturity and exclusion coverage, displays no curve below ten eligible comparable episodes, and only renders server-authorized D+1 through D+3 points at later gates. The detail endpoint strips free-text athlete notes. No recovery path mutates readiness decisions, coach proposals, planning checkpoints, or provider data.

Validation evidence is `635 passed, 1 skipped` in contributor-safe smoke after the independent-review regressions, `676 passed, 6 skipped, 24 deselected` in the final broad run, clean `compileall`, clean Next lint, and a successful Next production build with `/recovery` at 3.26 kB. Focused concurrency, migration, exact gates, missing-day, insertion-order, privacy, lifecycle-transition, and real materialization tests are green. Copy-of-real-database and browser acceptance produced the honest `collection_only` state and left the source database unchanged.

The remaining operational work is review and merge, not implementation. Statistical value still depends on future prospective syncs and proved plan/actual matches; this is an intentional evidence horizon rather than a missing backfill feature. The next roadmap issue should not consume recovery analytics as a decision input until the pre-registered gates have accumulated and been reviewed.

## Context and Orientation

`models/readiness.py::compute_readiness_today` is the pure readiness calculator. `api/readiness_snapshot.py::build_readiness_snapshot` currently loads all database frames and builds the current-day API contract. The implementation will move database orchestration into `services/readiness_snapshot.py`, add an explicit `as_of` boundary, and leave the API module as the compatibility boundary used by Today, Dashboard, coach, and the recovery gate.

`services/sync.py::SyncService.sync_garmin_data` is the common successful sync path. It writes activities, HRV, sleep, daily health, and training status, clears caches, and returns details. The prospective recorder belongs after cache invalidation so it sees committed data and serves both web and legacy entry points. `api/sync_jobs.py` remains process-local runtime orchestration and is not a scientific identity source.

`models/plan_actual_reconciliation.py` computes current plan-versus-actual evidence and applies explicit revisions from `plan_actual_matches`. `models/session_identity.py` gives every material planned session a stable `session_id`, and composite bricks use one parent ID plus ordered leg IDs. `models/workout_catalog.py` freezes template definitions and materialized steps. `session_feedback` adds athlete-entered completion, RPE, and quality with revision lineage. The episode materializer composes these existing facts; it does not implement another matcher, catalog, or feedback scale.

`data/database.py` initializes SQLite additively and contains the existing append-only transaction pattern. New tables and methods remain there because that is the project’s persistence boundary. Pure anchor, episode, and aggregation rules belong in a new `models/recovery_response.py`; orchestration that reads the database and appends revisions belongs in `services/recovery_analytics.py`; FastAPI projections belong in `api/recovery_analytics.py` and `api/routers/recovery_analytics.py`.

The Next.js product shell lives in `web/`. `web/components/Nav.tsx` declares the navigation and `web/lib/types.ts` contains API contracts. The new page is `web/app/recovery/page.tsx`. It consumes API output and owns presentation only; it must not compute cohort membership, sample gates, medians, intervals, or exclusions.

## Behavioral Specification

Given physiological rows through July 15, when readiness is built with `as_of=2026-07-14`, then no July 15 HRV, sleep, daily-health, or training-status row influences the score or factor provenance.

Given a successful sync run with a valid athlete timezone, when scientific capture runs twice with the same `capture_run_id` and frozen inputs, then both results identify the same snapshot and one row exists. Given a new run later that day, then revision 2 points to revision 1 even if the score is unchanged.

Given readiness confidence 0.59, stale primary evidence, a future factor date, or an invalid timezone, when capture is evaluated, then the row is visible but ineligible with explicit reasons. Given confidence 0.60, non-stale source evidence, valid provenance, and a score, then it is eligible.

Given a session starting at 08:00 local and eligible snapshots observed at 07:00 and 09:00, when the pre-anchor is selected, then the 07:00 row is used. Given no activity that day, snapshots after 12:00 are not daily anchors. Given an activity whose start is missing, no pre-anchor is guessed.

Given a completed matched single session with a pre-anchor but D+3 is in the future, when materialized, then one `maturing` episode exists. After D+3 passes, a new revision becomes `eligible` or `excluded`; previous evidence remains queryable.

Given a composite brick with proved bike and run activity evidence, when materialized, then one parent episode contains both legs. Given only one unproved leg, then the episode is excluded as `unresolved_brick` and neither leg becomes an independent episode.

Given feedback correction or a new explicit match revision, when the materializer runs, then it appends one episode revision that supersedes the prior row. Running again with unchanged evidence returns the existing revision.

Given an eligible episode with no D+2 snapshot, when outcomes are built, then D+1 and D+3 remain usable, D+2 is null, outcome completeness reports the missing day, and recovered-by-day considers only observed days without filling the gap.

Given cohorts at n 9, 10, 19, 20, 29, and 30, when analytics is projected, then gates change exactly at the pre-registered boundaries. A 30-episode cohort across seven weeks remains exploratory; across eight weeks it becomes `shadow_pattern`.

Given identical latest episode revisions in any SQLite insertion order, when cohort analytics is requested repeatedly, then cohort IDs, membership, medians, IQR, and bootstrap intervals are identical.

Given repeated recovery analytics GET requests, when row counts are checked before and after, then readiness and episode journal counts are unchanged. No GET calls Garmin or Intervals.icu.

Given current live-like data with fewer than ten eligible prospective episodes, when the web page loads, then it leads with collection maturity, coverage, distinct weeks, and exclusion reasons and does not render an authoritative curve or imply a recovery recommendation.

## Persistence Contract

Create `readiness_snapshots` with integer primary key; unique `fingerprint`; required `target_key`; monotonic `revision`; nullable `supersedes_snapshot_id`; `capture_mode`; `local_date`; `athlete_timezone`; `observed_at_utc`; `capture_run_id`; `rule_version`; score/status/confidence; `as_of_date`; provisional/source-completeness/stale fields; eligibility status and reasons JSON; factors, drivers, missing inputs, TSB, source provenance, and full canonical snapshot JSON; and `created_at`. Unique `(target_key, revision)` and date/mode indexes support latest and anchor queries.

Create `recovery_episodes` with integer primary key; unique `fingerprint`; required `target_key`; monotonic `revision`; nullable `supersedes_episode_id`; parent `session_id`; nullable plan checkpoint, match revision, and feedback IDs; session date; capture mode; lifecycle status; rule version; catalog/template/stimulus family/sport/role/phase identity; actual TSS and frozen load bucket; adherence and nullable RPE band; pre/D+1/D+2/D+3 snapshot IDs; exclusion reasons JSON; frozen planned, actual, feedback, outcome, and confounder JSON; and `created_at`. Unique `(target_key, revision)` plus status/cohort/date indexes support projections.

All inserts use `BEGIN IMMEDIATE`. A fingerprint retry returns the existing row. A new revision selects the latest target revision inside the same transaction and records its ID as superseded. No method updates a prior scientific row. Database statistics and clear helpers include both tables. Initialization remains safe for legacy databases and two concurrent initializers.

Latest means the highest revision for a target, not the row with a mutable flag. Analytics excludes superseded revisions by query and still exposes full history in evidence endpoints. Foreign-key enforcement is not introduced solely for this feature because the existing SQLite connection policy does not enable it consistently; identity is validated in service code and frozen JSON retains interpretability.

## Snapshot and Episode Rules

`services/readiness_snapshot.py::build_readiness_snapshot(db, as_of, observed_at_utc)` filters every source frame before calling the readiness model. It produces the existing API fields plus rule version and input provenance. The current-day callers remain behaviorally compatible.

`models/recovery_response.py` defines immutable constants and pure functions for timezone validation, snapshot eligibility, daily cutoff selection, load/RPE buckets, episode lifecycle, outcomes, cohort identity, gate selection, quantiles, and cluster bootstrap. Pure functions accept mappings/sequences and a supplied clock; they do not import FastAPI, provider clients, Database, or UI code.

`services/recovery_analytics.py::record_post_sync_recovery_state` saves the snapshot and refreshes episodes. `refresh_recovery_episodes` obtains the latest checkpoint, local reconciliation with `include_provider=False`, latest feedback/match revisions, activities, constraints, accepted proposals, and journal snapshots. It writes only when the frozen evidence fingerprint changes.

An episode is eligible for a primary cohort only when its latest revision is prospective, matched, exact or substituted adherence, has versioned stimulus identity, positive actual TSS, a valid pre-anchor, no explicit health/travel exclusion, no unresolved composite evidence, and D+3 has elapsed. Individual missing D outcomes remain outcome completeness gaps rather than terminal episode exclusions.

The materializer limits prospective candidates to session dates on or after the earliest prospective readiness snapshot. It does not create a misleading historical episode backlog on first deployment. Any future administrative backfill must be explicit, versioned, and marked `backfilled`; v1 does not expose a public backfill endpoint.

## Analytical Contract

`GET /api/recovery-analytics` returns rule versions, generated-at time, capture mode, snapshot and episode coverage, feedback response coverage, outcome completeness by day, exclusion counts, prospective cohort depth, distinct weeks, and a registry. Each registry item has stable cohort ID, cohort dimensions, n, distinct weeks, maturity state, guardrails, last observation, and whether points are publishable.

`GET /api/recovery-analytics/cohorts/{cohort_id}` returns the selected registry item; D+1/D+2/D+3 points with n-observed, missing count, median, Q1, Q3, and nullable interval; recovered-by-day distribution; confounder counts; rule/bootstrap versions; and included/excluded episode evidence. Athlete notes are not returned in the cohort endpoint; only categorical feedback values and scientific provenance are needed.

At `collection_only`, point statistics are null and `publishable=false`. At `early_signal`, median and IQR are present. At `exploratory` and `shadow_pattern`, intervals are present when the day itself has at least twenty observed outcomes; otherwise the point falls back to the lower applicable gate and explains why. RPE subgroups use the same complete independent gates and never borrow the parent cohort label.

The API must use “наблюдение”, “ранний сигнал”, “исследовательский паттерн”, and “теневой паттерн”; it must not use “эффект”, “причина”, “лечит”, “предотвращает”, or a personalized prescription. It returns guardrails that the web renders rather than reconstructing wording rules client-side.

## API and Web Contract

Register `api/routers/recovery_analytics.py` in `api/main.py`. Both endpoints depend on the existing database dependency and accept only `capture_mode=prospective` in the public v1 API. Unknown cohort IDs return 404. Invalid data is represented in coverage/exclusions, not a 500. Unexpected service failure returns the normal API error while other product surfaces remain unaffected.

Add `RecoveryAnalyticsSummary`, cohort, point, evidence, and coverage TypeScript interfaces. Add `getRecoveryAnalytics` only if the existing generic SWR fetcher needs a typed wrapper; do not introduce a second API client. The page polls only on focus through SWR defaults and has explicit loading, error, empty/no-snapshot, collection-only, early-signal, exploratory, and shadow-pattern states.

The new `/recovery` page starts with “Персональное восстановление” and a visible `shadow` label. The first card answers how much trustworthy evidence exists. The second lists cohort maturity and allows selecting one cohort. The third renders D+1 through D+3 only when API `publishable` permits it, with n and interval/coverage adjacent to every point. An evidence disclosure lists included sessions and excluded counts/reasons. The page contains no button that mutates or applies a plan.

Add “Восстановление” to `web/components/Nav.tsx`. Do not add Streamlit recovery charts. The legacy shell benefits only through shared post-sync recording and remains a fallback.

## Plan of Work

Milestone one establishes contract-first failures. Add focused smoke tests for as-of filtering across all readiness sources, stress provenance, timezone validation, snapshot schema migration, idempotent retry, same-day revisions, two-connection contention, and daily anchor selection before activity/noon. Add episode tests for parent identity, brick atomicity, lifecycle, correction lineage, exclusion reasons, missing D+2, and no historical prospective backlog. Add analytics tests at every sample boundary, week concentration, independent RPE gates, deterministic bootstrap, insertion-order stability, and missing-day behavior. Add API tests proving GET is read-only and web contract tests for all maturity states. Record the expected missing table/module failures in `Surprises & Discoveries`.

Milestone two implements as-of-safe readiness and the snapshot journal. Extract the shared builder, add the v2 rule/provenance fields without changing current-day consumers, add timezone configuration and documentation, add the readiness table/methods, and add the shared post-sync capture hook with one UUID per sync invocation. Keep capture failure fail-open for operational sync: source data sync succeeds, its result reports the scientific capture error, and no partial journal transaction remains.

Milestone three implements episodes. Add pure anchor/outcome/cohort primitives, the episode table/methods, and the write-event materializer. Integrate it after successful sync, explicit plan/actual match writes, and feedback submit/correct/tombstone/admin bridge. Hooks run after the source transaction commits; their failure is reported without rolling back the already-valid user fact. Do not call Intervals.icu during materialization.

Milestone four implements analytics and product delivery. Add deterministic latest-revision projections, cohort gates, cluster bootstrap, API projections/routes, TypeScript contracts, navigation, and the `/recovery` page. Keep all calculations server-side and all GET methods read-only.

Milestone five validates and publishes. Run focused/adjacent tests, contributor-safe smoke, broad non-live pytest, Python compile/lint where configured, Next lint/build, migration/concurrency probes, and browser acceptance on a copied real database plus a sanitized synthetic mature cohort for gated curve states. Confirm the real database is never written, provider APIs receive no writes, and plan/readiness decision tables do not change. Self-review time provenance, correction determinism, privacy, route failure behavior, and minimal complexity. Update this living plan, commit logical docs/test/implementation milestones, push, and open a draft PR with `Closes #176`.

## Concrete Steps

Work from `/private/tmp/ai_trainer_issue176` and activate the existing environment:

    source /Users/gregkisel/Developer/ai_trainer/ai_trainer_env/bin/activate

Create the focused tests first and run:

    python -m pytest tests/smoke/test_recovery_response.py -q
    python -m pytest tests/smoke/test_readiness_snapshot.py tests/smoke/test_recovery_response.py -q

After the persistence/materializer milestone, run adjacent contracts:

    python -m pytest tests/smoke/test_recovery_response.py tests/smoke/test_plan_actual_reconciliation.py tests/smoke/test_post_workout_feedback.py tests/smoke/test_api_sync.py -q

After API/web integration, run:

    python -m pytest tests/smoke/test_api_recovery_analytics.py tests/smoke/test_api_today.py tests/smoke/test_dashboard_api.py -q
    cd web && npm run lint && npm run build

Before publication run from the worktree root:

    python -m pytest tests/smoke -q
    python -m pytest -m "not live and not debug" tests/ -q
    python -m compileall api models services data
    git diff --check main...HEAD

Acceptance uses a database copy under `/private/tmp` and alternate API/web ports. First initialize/migrate the copy, invoke one prospective capture with a fixed run ID, invoke it again to prove idempotency, then invoke a second run ID to prove a same-day revision. Start the web stack against the copy and verify the collection-only state and evidence counts. Use a separate sanitized fixture with 9/10/20/30 episodes across controlled weeks to verify each rendered maturity state. Record before/after counts for `readiness_snapshots`, `recovery_episodes`, `planning_checkpoints`, `coach_proposals`, and provider-facing data.

## Validation and Acceptance

Readiness acceptance passes when past `as_of` calculations cannot see future HRV/sleep/health/status rows, current-day consumers retain their contract, stress provenance has a real source date, and invalid timezone or stale/future evidence fails closed with a specific reason.

Snapshot acceptance passes when legacy databases migrate safely; identical run retries produce one row; separate same-day runs append lineage; two SQLite connections cannot allocate duplicate revisions; latest-before-cutoff selection ignores after-session/after-noon observations; and backfilled rows never enter a prospective query.

Episode acceptance passes when one completed parent session produces one revisioned episode; bricks remain atomic; automatic and explicit matches freeze evidence; feedback is optional and corrections supersede; D+1/D+2/D+3 remain independently missing or observed; explicit illness/travel and evidence failures have stable reasons; and repeated materialization with unchanged facts is idempotent.

Analytics acceptance passes at n 9/10/19/20/29/30, at seven/eight weeks, and for underpowered RPE overlays. Medians, quantiles, intervals, recovered-day counts, cohort IDs, and inclusion/exclusion membership are deterministic across calls and database insertion order. No backfilled episode contributes to prospective n.

API acceptance passes when summary and detail schemas are complete, unknown cohorts return 404, no endpoint calls a provider, and repeated GET requests leave all database counts unchanged. A malformed or excluded row lowers coverage instead of crashing the whole response.

Product acceptance passes when `/recovery` has loading/error/empty/collection/early/exploratory/shadow states; the current real-like copy shows collection rather than a curve; every published point displays n and uncertainty/coverage; evidence and exclusion reasons are inspectable; language stays observational; and there is no plan mutation control.

Regression acceptance passes when the existing Today, readiness gate, dashboard, coach, reconciliation, feedback, planning, sync, and deployment smoke suites remain green. No file in `api/` imports `ui/`, and no recovery business rule is duplicated in Next.js or Streamlit.

## Idempotence and Recovery

Schema initialization uses `CREATE TABLE IF NOT EXISTS` plus additive indexes and is rerunnable. Snapshot and episode writes use caller/evidence fingerprints and immediate transactions. The same run or materialization retry returns the existing row; a changed source revision creates one new superseding row. Analytics rebuild is a read projection and requires no cleanup.

Sync remains operationally fail-open: Garmin facts may commit even if recovery capture fails, and the sync response records the error. A later sync retries with a new capture run. Match/feedback writes similarly remain valid if episode refresh fails; the next sync or source correction can repair the derived ledger without rewriting source facts.

No public backfill or rebuild command is added. Test backfills use isolated databases and `capture_mode=backfilled`. If acceptance fails, stop alternate servers and delete only temporary database/worktree artifacts. Never modify or publish `ai_trainer.db`, `.env`, logs, athlete notes, or `docs/woz_tracking.csv`.

## Artifacts and Notes

Issue: `https://github.com/rbctmz/ai_trainer/issues/176`.

Pre-ExecPlan audit: `https://github.com/rbctmz/ai_trainer/issues/176#issuecomment-4966004357`.

Baseline: `38de146`, merged PR #184. Contributor-safe baseline is `587 passed, 1 skipped` on 2026-07-14.

The current live database is read-only evidence for planning: 58 activities, 48 HRV rows/days, 47 sleep rows/days, 48 daily-health rows/days, 18 training-status rows/days, 11 forecast revisions, one feedback revision, one explicit match revision, and seven recovery decisions. These counts will continue changing and are not test assertions.

## Interfaces and Dependencies

`services/readiness_snapshot.py` must expose:

    READINESS_SNAPSHOT_RULE_VERSION: str
    def build_readiness_snapshot(
        db: Database,
        *,
        as_of: date | None = None,
        observed_at_utc: datetime | None = None,
    ) -> dict[str, Any]: ...

`models/recovery_response.py` must expose version constants and pure helpers equivalent to:

    def evaluate_snapshot_eligibility(snapshot: Mapping[str, Any]) -> dict[str, Any]: ...
    def select_daily_anchor(
        snapshots: Sequence[Mapping[str, Any]],
        activities: Sequence[Mapping[str, Any]],
        *,
        local_date: date,
        athlete_timezone: str,
    ) -> dict[str, Any]: ...
    def build_episode_projection(evidence: Mapping[str, Any], *, as_of: date) -> dict[str, Any]: ...
    def build_recovery_analytics(episodes: Sequence[Mapping[str, Any]]) -> dict[str, Any]: ...

`services/recovery_analytics.py` must expose orchestration equivalent to:

    def record_post_sync_recovery_state(
        db: Database,
        *,
        capture_run_id: str,
        observed_at_utc: datetime | None = None,
        capture_mode: str = "prospective",
    ) -> dict[str, Any]: ...
    def refresh_recovery_episodes(
        db: Database,
        *,
        as_of: date | None = None,
        capture_mode: str = "prospective",
    ) -> dict[str, Any]: ...
    def recovery_analytics_summary(db: Database) -> dict[str, Any]: ...
    def recovery_cohort_detail(db: Database, cohort_id: str) -> dict[str, Any]: ...

Database methods must support atomic snapshot/episode append, lookup by fingerprint, latest/history by target, anchor-range reads, latest episode projection, stats, and clear. They return deserialized dictionaries and never expose JSON strings to domain/API code.

FastAPI route functions depend on `Database` and call the headless service only. Next.js consumes the returned schema through `web/lib/types.ts` and the existing fetcher. No new third-party Python or npm dependency is required; standard-library `zoneinfo`, `hashlib`, `random`, and existing numerical helpers are sufficient.

## Revision Note

2026-07-14 / Codex: Initial pre-registered plan created after the repository and live-data audit. It incorporates the reviewer’s Issue #176 contract, the newly observed missing-timezone and historical-start limitations, and exact v1 decisions for identity, exclusions, load/RPE buckets, week-cluster bootstrap, API routes, web maturity states, and write-event boundaries. No product implementation existed when these decisions were recorded. Updated after the red phase to record the 37 executable BDD scenarios and their expected missing-boundary evidence. Final implementation update records all delivered milestones, the same-run identity refinement, self-review fixes, test/build transcripts, copy-of-real-database evidence, browser acceptance, and the remaining human review/merge gate. The independent-review update adds the lifecycle-clock regression and its append-only fix, current-date late-match refresh, mode-aware anchors, direct-route cleanup, and the `635 passed, 1 skipped` smoke transcript.
