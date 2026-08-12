# Harden plan-to-actual evidence, delivery history, and workout visuals

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds. Maintain this document in accordance with `.agent/PLANS.md` from the repository root.

## Purpose / Big Picture

The recent Intervals.icu, plan-vs-fact, recovery delivery, and workout-strip series is functional but an independent review found several boundary defects that can misstate evidence or hide device-sync risk. After this work, canceling a match also retires feedback derived from any superseded revision, plan-vs-fact comparisons preserve chronological order and target precision, every successful plan delivery has durable history, athlete-local dates drive sync hints, role and RPE contracts agree, and the 60-minute power peak uses a provider endpoint that can actually return it. The user can observe the result through focused regression tests and the existing Activities, Today, and Planning web surfaces.

## Progress

- [x] (2026-08-11 19:30Z) Reviewed commits `37da528..HEAD`, reproduced feedback-lineage, out-of-order matching, invalid-role, and timezone failures, and recorded eight findings.
- [x] (2026-08-11 19:35Z) Created this ExecPlan with BDD scenarios, ASR traceability, ownership boundaries, and validation commands.
- [x] (2026-08-11 19:42Z) Milestone 1: added the older-match-revision RED regression and made unmatch retire the latest active feedback for the session idempotently.
- [x] (2026-08-11 19:41Z) Milestone 2: made matching monotonic and preserved two-decimal relative targets; the focused suite passed 39 tests.
- [x] (2026-08-11 19:44Z) Milestone 3: unified the closed role vocabulary, corrected RPE to 1–10, and filled 60-minute power through one bounded best-effort call with cache-safe failure behavior.
- [x] (2026-08-11 19:48Z) Milestone 4: added the append-only delivery ledger with legacy reads, athlete-local timestamp handling, and a twice-run hermetic distance-backfill test.
- [x] (2026-08-11 19:54Z) Milestone 5: integrated and self-reviewed all slices, updated ASR traceability, and completed backend, web build, and desktop/mobile browser acceptance.

## Surprises & Discoveries

- Observation: all existing smoke and broad non-live tests passed while a real feedback revision remained active after unmatch.
  Evidence: the reproduced sequence confirm-without-role, submit-feedback, reconfirm-with-role, unmatch ended with `[(feedback_id=1, match_revision_id=1, status='active')]` because cleanup queried only match revision 2.
- Observation: the matcher described as ordered can match backwards.
  Evidence: plan `[60, 300]` and actual `[300, 60]` returned `matched=2` because removing the 60-second item left the earlier 300-second item available.
- Observation: the live power-curve contract ends at 2700 seconds while the card requests 3600 seconds.
  Evidence: `IntervalsICUClient.get_activity_power_curve` documents the verified 1..2700-second response; the existing test fabricates a 3600-second point.
- Observation: manual plan delivery has no durable record.
  Evidence: `api.planning_service.deliver_intervals_plan` returns `safe_deliver_active_plan` directly, while `Database.get_approved_recovery_replan_deliveries` can only reconstruct automatic recovery proposal deliveries.
- Observation: the real Planning correction data had no currently confirmable candidate, so browser acceptance could not render the role selector without mutating user data.
  Evidence: the Adjust page showed only matched, rejected, or no-candidate rows. The exact seven-value selector contract is therefore pinned hermetically by `test_actual_role_contract.py`; browser acceptance still covered the surrounding Adjust surface read-only.
- Observation: independent integration review found four boundary issues after the first green integration: plan-vs-fact rounded the already-correct projected 0.95 back to 0.9; ledger persistence failure was untyped in the UI; provider IDs were fingerprinted in unstable response order; and the first history warning falsely implied provider success during a double failure.
  Evidence: each finding received a focused RED regression before correction. The updated precision/delivery suite passed 61 tests, and the reviewer reported no remaining actionable findings on the final diff.

## Decision Log

- Decision: use one additive append-only `intervals_plan_deliveries` table as the source of delivery history for manual delivery, recovery approve, and recovery rollback.
  Rationale: reconstructing history from mutable proposal `result_json` loses manual sends and may overwrite the original approved delivery during rollback. A small event ledger makes history complete, retryable, and independently queryable without changing checkpoint storage.
  Date/Author: 2026-08-11 / Codex.
- Decision: record only completed delivery attempts, including failures, but let warning readers select successful events.
  Rationale: failures are useful retry/audit evidence, while device-sync warnings must never claim that a failed provider write reached Intervals.icu.
  Date/Author: 2026-08-11 / Codex.
- Decision: preserve backward compatibility by reading legacy proposal delivery evidence in addition to the new ledger until all relevant histories naturally age out.
  Rationale: current databases already contain recovery delivery results. Additive read compatibility avoids a destructive migration or a one-off historical rewrite.
  Date/Author: 2026-08-11 / Codex.
- Decision: enforce chronological matching by advancing past the selected actual interval rather than retaining earlier unmatched intervals.
  Rationale: the product promise is plan-vs-fact by repetitions in execution order; a monotonic greedy matcher is the smallest correction and preserves the existing tolerance rules.
  Date/Author: 2026-08-11 / Codex.
- Decision: define one backend actual-role set that includes planner roles used by completed sessions and project the equivalent list in the web selector.
  Rationale: arbitrary strings corrupt adherence categories, while divergent hard-coded sets make valid activation or race evidence impossible on some surfaces.
  Date/Author: 2026-08-11 / Codex.
- Decision: reuse the existing SQLite and append-only planning ADRs instead of creating a new ADR for the delivery ledger.
  Rationale: the table is an additive evidence journal inside ADR-0002's single-athlete SQLite boundary and follows ADR-0006's established immutable-version tactic; it does not introduce a new datastore, ownership boundary, or cross-service protocol.
  Date/Author: 2026-08-11 / Codex.

## Outcomes & Retrospective

All eight reproduced defects are closed. Unmatch now tombstones feedback across a corrected match lineage; ordered repetition matching cannot move backward; relative targets preserve 95%/88.2%-class precision; execution roles are closed and shared across backend and web; RPE uses a 1–10 denominator; the 60-minute power headline comes from the verified best-efforts endpoint; successful manual deliveries are durable warning evidence; and SQLite UTC timestamps are evaluated in the athlete timezone. The distance backfill now executes twice against a temporary database and fake provider without changing Garmin-authoritative distance.

Validation finished with 1635 passed/1 skipped in smoke and 1681 passed/3 skipped/24 deselected in the broad non-live contour. Next lint and production build, Python compileall, and `git diff --check` passed. Browser acceptance covered Activities plus an activity detail, Today, Planning Overview/Execution/Adjust at 1280 px, and Activities/detail/Today/Planning at 390 px; every API request returned 200, there were no console errors, and no page-level horizontal overflow. The only residual limitations are that the live database had no confirmable candidate row, so the role dropdown itself was validated by its hermetic source contract rather than browser interaction, and the 3600-second best-effort call was verified with the recorded provider contract plus fake client rather than a live Intervals.icu request. Provider delivery and the local SQLite ledger cannot be one transaction; a ledger failure is now typed, visible, and safely retryable. No live provider writes were made.

## Context and Orientation

Plan-to-actual reconciliation lives in `models/plan_actual_reconciliation.py`; explicit user corrections are orchestrated by `api/planning_service.py` and persisted append-only in `data/database.py`. Session feedback is a separate append-only ledger managed by `api/session_feedback.py`. A match revision can supersede an older match revision, so canceling the current association must retire current feedback derived from any revision in that association's lineage, not only feedback whose `match_revision_id` equals the immediately previous row.

Activity-card repetition comparison lives in `models/plan_intervals.py` and `models/plan_vs_fact.py`, is exposed by `api/routers/activities.py`, and is rendered by `web/app/activities/page.tsx`. The planned `relative_low` and `relative_high` values are fractions such as `0.95`; they must retain two decimal places because the UI multiplies them by 100 for athlete-visible percentages.

Intervals plan delivery is performed by `services/intervals_plan_delivery.py`. Manual delivery enters through `POST /api/planning/delivery/intervals`; automatic delivery enters through recovery proposal approve and rollback handlers in `api/routers/decisions.py`. Planning checkpoints use SQLite `CURRENT_TIMESTAMP`, which is UTC. Athlete-facing day boundaries must use `ATHLETE_TIMEZONE`, already used by `services.intervals_plan_delivery.athlete_local_date`.

Power curves and best efforts are read through `services/intervals_icu.py`. The compact activity curve is built in `models/power_curve.py` and fetched by `services/best_efforts.py`. The verified power-curve list stops at 2700 seconds, but `get_activity_best_efforts` accepts an explicit 3600-second duration. The web workout strip is `web/components/WorkoutStrip.tsx`; backend workout targets label RPE as `rpe_1_10`.

The new distance backfill is `scripts/backfill_intervals_distance.py`. It must be tested without live credentials by injecting a fake client, pointing `Settings.DATABASE_PATH` at a temporary SQLite database, and proving both Intervals-authoritative and Garmin-authoritative behavior plus idempotence.

## BDD Scenarios

Given feedback was submitted against an earlier confirmed match revision and the same session was later reconfirmed with an explicit role, when the athlete cancels the current match, then the latest active feedback for that session becomes a tombstone and no active feedback remains attributed to the canceled association.

Given planned work steps are 60 seconds then 300 seconds and actual detected intervals are 300 seconds then 60 seconds, when plan-vs-fact matching runs, then it must not report both steps as matched because chronological order cannot move backwards.

Given a planned target has `relative_high=0.95`, when it is projected into activity-card intervals, then the API and web tooltip retain 95%, not 90%.

Given a caller submits an unknown actual role, when an explicit match is recorded, then the API returns a validation error and no match revision is written. Given a valid planner role such as activation or race, the agreed contract determines consistently whether it is accepted across reconciliation and feedback paths.

Given an RPE target uses the `rpe_1_10` scale, when the workout strip computes height, then RPE 5 maps to 50% and RPE 10 maps to 100% before the existing visual minimum clamp.

Given an activity has at least 60 minutes of power data but the provider power-curve array ends at 2700 seconds, when its card is enriched, then the 60-minute peak is filled from `best-efforts?stream=watts&duration=3600&count=1`; a normal no-stream 422 remains a no-data result, and provider failure preserves the cached curve.

Given the active plan was delivered manually and a later recovery checkpoint changes the same date, when the activity card checks delivery history, then it finds the successful manual delivery and shows the replanned-after-delivery warning.

Given a recovery checkpoint is created after local midnight but its SQLite UTC date is still the previous calendar day, when Today is built in the configured athlete timezone, then the device-sync hint is shown for the athlete's current day.

Given a temporary database contains Intervals-only and Garmin-paired links, when the distance backfill runs twice with a fake provider response, then the first run updates only authoritative canonical distances and full provider payloads, the second run changes nothing, and no live network or repository database is touched.

## ASR / Risk Traceability

This work affects ASR-REL-1 because match and feedback evidence must not survive an explicit cancellation incorrectly. It affects ASR-REL-2 because malformed roles, provider no-data, and legacy delivery rows must fail closed or degrade to data gaps instead of fabricating evidence. It affects ASR-REL-3 because delivery history and backfill writes must be transactional and retry-safe. It affects ASR-MOD-3 because the delivery table is an additive schema change with legacy-read compatibility. It affects ASR-PERF-3 only minimally: delivery ledger writes are one local SQLite insert after an already completed provider operation, with no extra provider calls except the deliberate single 3600-second best-effort request while enriching an activity card.

## Plan of Work

Milestone 1 adds a failing regression to `tests/smoke/test_api_planning.py` for feedback attached to an older match revision. The implementation will identify the active feedback for the session/target across the superseded match chain and append one tombstone through the existing feedback service. The smallest safe design is preferred; if cross-ledger atomicity cannot be achieved without duplicating persistence logic, match save remains append-only first and cleanup must be idempotent so a retried unmatch completes it.

Milestone 2 adds reversed-order and target-precision regressions to `tests/smoke/test_plan_vs_fact.py` and `tests/smoke/test_plan_intervals.py`. `models/plan_vs_fact.py` will advance the actual cursor after a match. `models/plan_intervals.py` will use field-appropriate precision: duration and absolute targets retain their current compaction, relative fractions retain two decimals.

Milestone 3 adds backend tests for invalid and valid actual roles, a web contract check for the role options and RPE denominator, and service tests for the 3600-second fallback. It will keep provider errors fail-open to the existing cached curve. No new dependency is allowed.

Milestone 4 adds the delivery ledger DDL and database facade, then changes all three delivery entry points to append sanitized result evidence. Readers merge ledger events with legacy proposal-derived success evidence and deduplicate by stable event content. Athlete-local freshness is determined through a shared timezone-aware helper rather than timestamp string slicing. The backfill script gains optional dependency injection at its `main` boundary so a hermetic temporary-database test can execute the real code path.

Milestone 5 merges the parallel slices, inspects the combined diff for overlapping enums and duplicated helpers, updates this ExecPlan and `docs/architecture/asr_catalog.md`, and runs the full validation contour. No commit, push, or PR is created unless separately requested by the user.

## Concrete Steps

Work from `/Users/gregkisel/Developer/ai_trainer`.

Run focused RED and GREEN tests as each milestone lands:

    ai_trainer_env/bin/python -m pytest tests/smoke/test_api_planning.py -q
    ai_trainer_env/bin/python -m pytest tests/smoke/test_plan_vs_fact.py tests/smoke/test_plan_intervals.py -q
    ai_trainer_env/bin/python -m pytest tests/smoke/test_best_efforts.py tests/smoke/test_api_today.py -q
    ai_trainer_env/bin/python -m pytest tests/smoke/test_intervals_plan_delivery.py tests/smoke/test_recovery_replan_loop.py -q
    ai_trainer_env/bin/python -m pytest tests/smoke/test_backfill_intervals_distance.py -q

Then run the contributor-safe and broad contours:

    ai_trainer_env/bin/python -m pytest tests/smoke -q
    ai_trainer_env/bin/python -m pytest -m "not live and not debug" tests/ -q
    npm --prefix web run lint
    npm --prefix web run build
    ai_trainer_env/bin/python -m compileall -q api data models services scripts
    git diff --check

Finally start the isolated web stack on free ports and inspect Activities, Today, and Planning at desktop and 390-pixel widths. Expect no console errors, no page-level horizontal overflow, correct workout strips, and successful API responses.

## Validation and Acceptance

All new RED tests must fail for the reproduced reason before their implementation and pass afterward. Existing tests must remain green. The unmatch regression must assert that no active feedback remains after a role-correction revision. The matching regression must assert that a reversed sequence cannot score full completion. The delivery regression must exercise the actual manual endpoint/service path and prove the later warning sees its ledger entry. The timezone regression must use a UTC timestamp whose athlete-local date is the following day. The power regression must prove one bounded 3600-second best-effort request and cache preservation on failure. The backfill regression must compare database bytes or selected rows after a second run to prove idempotence.

The web build and lint must pass. Browser acceptance must show `/activities`, an activity card, `/today`, and `/planning` without console errors at desktop and 390 pixels. No live provider writes are permitted during tests or browser acceptance.

## Idempotence and Recovery

All schema changes are `CREATE TABLE IF NOT EXISTS`. Delivery event inserts use a stable fingerprint or unique constraint so retrying an already completed API response does not duplicate history. Feedback tombstoning reuses client fingerprints and the existing optimistic revision checks. Backfill tests use a temporary database and fake client; the real repository database is never opened by the test. If any parallel slice overlaps another file, stop that slice before integration and apply the smaller patch manually rather than overwriting another agent's work.

## Artifacts and Notes

Baseline before implementation:

    1663 passed, 3 skipped, 24 deselected
    Next lint: clean
    Next production build: clean
    Browser: Activities/Today/Planning clean at desktop and 390 px

Known reproduced counterexamples:

    feedback after unmatch: [(1, 1, "active")]
    reversed repetitions: summary.matched == 2
    relative target: 0.95 -> 0.9
    invalid role: "not-a-real-role" -> major_deviation

## Interfaces and Dependencies

In `data/database.py`, add a durable delivery event API whose public shape is equivalent to:

    save_intervals_plan_delivery(payload: Mapping[str, Any]) -> dict[str, Any]
    get_intervals_plan_deliveries(*, successful_only: bool = False) -> list[dict[str, Any]]

The event contains a stable fingerprint, source, checkpoint id, selected dates, status, provider event ids/counts, retryability, sanitized error if any, and a UTC creation timestamp. Existing `get_approved_recovery_replan_deliveries` remains as a compatibility facade or is replaced only after all callers use a merged history reader.

In `api/planning_service.py`, actual-role validation must use one named canonical set rather than accepting arbitrary strings. In `models/plan_vs_fact.py`, the public `match_plan_vs_fact` shape remains backward compatible. In `models/plan_intervals.py`, the output keys remain unchanged; only precision is corrected. In `services/best_efforts.py`, the public activity-card curve shape remains unchanged while the 3600-second value may be enriched through the existing Intervals client.

Revision note (2026-08-11): Initial plan created after independent review. It resolves all eight findings as one integration track because delivery history, match evidence, and the shared web presentation must be validated together, while implementation remains split into non-overlapping RED-to-GREEN milestones for safe parallel work.
