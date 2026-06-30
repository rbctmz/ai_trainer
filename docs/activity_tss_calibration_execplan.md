# Tighten Activity TSS Calibration Against IntervalCoach

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

This document must be maintained in accordance with `.agent/PLANS.md`.

## Purpose / Big Picture

After issue `#35` and merged PR `#36`, AI Trainer no longer shows Garmin `activityTrainingLoad` as if it were product TSS. That semantic bug is fixed. The remaining user-visible gap is narrower but still important: completed walk, swim, and run activities can still disagree too much with the IntervalCoach reference values the user is actively comparing against.

After this change, a user should be able to sync Garmin, open `http://localhost:3000/activities`, and see completed-activity TSS values that are materially closer to IntervalCoach on validated examples while still keeping Garmin load separate as diagnostic metadata. The simplest way to see success is to compare the known reference activities from June 2026: the June 30 swim should stay near `65 TSS`, the short June 26 swims should stop overshooting so hard, the easy walks should land in low single digits, and the June 27 run should stop overshooting the IntervalCoach reference.

## Progress

- [x] (2026-07-01 08:44Z) Confirmed that PR `#36` is already merged into `main` as `8dbde8f`, and created a dedicated working branch `codex/tighten-activity-tss-calibration-37`.
- [x] (2026-07-01 08:48Z) Read the live issue `#37`, the prior ExecPlan in `docs/activity_tss_semantics_execplan.md`, and the current resolver/tests in `data/data_processor.py`, `data/database.py`, and `tests/smoke/test_activity_tss_reconciliation.py`.
- [x] (2026-07-01 08:57Z) Rechecked the current local activity rows and reproduced the remaining deltas against the user-validated IntervalCoach examples for walk/swim/run.
- [x] (2026-07-01 09:10Z) Added failing contributor-safe calibration tests for validated walk/swim/run examples plus a database-open recalibration case for pre-existing zone-based rows.
- [x] (2026-07-01 09:15Z) Refined the walk, swim, and run formulas in `data/data_processor.py` and broadened the database repair pass so existing stored rows are recomputed to current resolver rules.
- [x] (2026-07-01 09:19Z) Ran targeted smoke tests green: `python3 -m pytest tests/smoke/test_activity_tss_reconciliation.py tests/smoke/test_api_phase1.py tests/smoke/test_garmin_sync_service.py -q`.
- [x] (2026-07-01 09:20Z) Ran the full contributor-safe smoke suite green: `python3 -m pytest tests/smoke -q` (`257 passed`).
- [x] (2026-07-01 09:21Z) Verified the recalibrated local `ai_trainer.db` rows through the activities API helper: June 30 swim `64.8`, June 30 walk `2.0`, June 27 run `51.0`, June 25 swim `8.2`, June 24 walk `9.9`.

## Surprises & Discoveries

- Observation: the remaining mismatch is not one bug; it is three different calibration behaviors by sport.
  Evidence: current local rows show June 30 swim at `62.7` versus IC `65`, June 26 swims at `6.4 / 7.6` versus IC `5 / 5`, June 27 run at `57.9` versus IC `51`, and the short walks in the `1.4-4.6` range versus IC `2-5`.

- Observation: Garmin summary-zone data appears sufficient for a first calibration pass on swim and run; a detail fetch is not yet required to materially improve the validated examples.
  Evidence: a simple least-squares fit over the existing swim zone summaries can reproduce the validated swim examples much better than the current generic swim weights, including the June 25/26 short swims that are currently too high.

- Observation: walk calibration behaves better as a duration heuristic with a short-session floor and a lower long-session rate than with either Garmin load or the previous single constant.
  Evidence: current moving-duration examples imply that a single `8.5 TSS/hour` walk constant underestimates the short `9-32 minute` walks but overestimates the long `85 minute` walk.

- Observation: broad recalculation on `Database(...)` open is necessary if we want the local activities table to reflect the new calibration without forcing the user to wait for a fresh sync window.
  Evidence: a persisted `hr_zone_tss_swim` row remained at `62.7` until the database repair pass was widened beyond the old `garmin_training_load`-only migration query.

## Decision Log

- Decision: keep this as a follow-up calibration pass on top of the `#35` contract instead of reopening the Garmin-load separation work.
  Rationale: PR `#36` fixed the semantic bug correctly. The next step is narrower and should stay narrowly scoped.
  Date/Author: 2026-07-01 / Codex

- Decision: start with summary-payload calibration rather than immediately adding Garmin detail-fetches into sync.
  Rationale: the available zone summaries already explain most of the remaining swim and run mismatch, so a summary-only pass is the minimal-complexity path for `#37`.
  Date/Author: 2026-07-01 / Codex

- Decision: calibrate swims with empirical summary-zone weights and calibrate runs with a conservative zone-weighted path before average-HR fallback.
  Rationale: the validated examples show that the generic swim weights were too high on easy swims, while average-HR-only running overshot the June 27 aerobic pickups. Garmin summary zone times were already sufficient to fix both behaviors.
  Date/Author: 2026-07-01 / Codex

- Decision: recompute all persisted activity TSS rows during the database repair pass instead of limiting the repair query to legacy `garmin_training_load` rows.
  Rationale: this keeps local historical rows consistent with the current resolver after formula changes and avoids a user-visible split between newly synced rows and older cached rows.
  Date/Author: 2026-07-01 / Codex

## Outcomes & Retrospective

This pass tightened the calibrated examples materially without changing the API contract from `#35`. The local verified values now land much closer to the IntervalCoach references: June 30 swim moved from `62.7` to `64.8`, June 30 walk from `1.4` to `2.0`, June 27 run from `57.9` to `51.0`, June 25 swim from `13.8` to `8.2`, and June 24 walk from `12.0` to `9.9`.

The remaining gap is that this is still a summary-payload model. It is now good enough for the validated examples, but future calibration work could still justify per-activity detail or FIT-derived signals if new evidence shows summary zones are insufficient for other sports or edge cases.

## Context and Orientation

This work sits on top of the merged TSS-semantics fix from `docs/activity_tss_semantics_execplan.md`. The main resolver lives in `data/data_processor.py`. `ActivityProcessor.process_activities(...)` extracts Garmin summary fields into normalized activity rows, and `ActivityProcessor.resolve_tss(...)` computes the product-facing `tss` plus the explanatory `tss_method`. `data/database.py` persists these rows and backfills older ones. `api/routers/activities.py` publishes the values to the web UI without doing extra calculations.

The user is comparing AI Trainer against IntervalCoach, which means the practical target is not “a mathematically pure TSS formula in the abstract,” but “a stable local estimate that agrees much better with the user-validated reference values for completed activities.” In this plan, “reference values” means the explicit numbers the user validated from IntervalCoach screenshots and exports for June 2026 walks, swims, and runs.

## Plan of Work

First, expand `tests/smoke/test_activity_tss_reconciliation.py` with real calibration fixtures. The test file already covers the semantic separation bug; it should now also encode the validated reference examples that are still off. The new tests should focus on behavior, not internals: a representative short walk should land in the `~2 TSS` band, the June 30 swim-like summary should stay near `65 TSS`, the June 25/26 easy-swim summaries should drop closer to the `5-8 TSS` band, and the June 27 run-like summary should no longer overshoot into the high-50s.

Second, refine `ActivityProcessor.resolve_tss(...)` in `data/data_processor.py`. Walks should keep using a heuristic path, but that path needs a short-session uplift and a lower long-session rate. Swims should keep preferring summary-zone data when it exists, but the swim zone weights need to be recalibrated to the validated IC examples instead of the previous generic progression. Runs should stop relying only on average-heart-rate TSS when Garmin already provides zone summaries; the summary-zone path should become the primary run method when zone data is present, with average-HR kept as fallback.

Third, keep the rest of the contract stable. `data/database.py` should continue storing `garmin_training_load` separately from `tss`, and `api/routers/activities.py` should continue exposing the same fields. If the resolver method names change, update only the parts needed so tests and the API stay coherent.

Finally, rerun contributor-safe smoke coverage and inspect the local activity API output. The acceptance bar is the user-visible data, not only green tests.

## Concrete Steps

Work from the repository root:

    cd /Users/gregkisel/Developer/ai_trainer

Confirm the current branch:

    git status --short --branch

Run the focused reconciliation tests before editing so the existing baseline is known:

    python3 -m pytest tests/smoke/test_activity_tss_reconciliation.py -q

After adding the calibration tests and code changes, run:

    python3 -m pytest tests/smoke/test_activity_tss_reconciliation.py tests/smoke/test_api_phase1.py tests/smoke/test_garmin_sync_service.py -q
    python3 -m pytest tests/smoke -q

After tests pass, inspect the local API response:

    curl -sS 'http://127.0.0.1:8000/api/activities?days=10'

The important outcomes to observe are:

- June 30 swim remains near `65 TSS` and still exposes Garmin load separately.
- June 26 easy swims move down toward the validated `5 TSS` values instead of `6.4 / 7.6`.
- June 27 run moves down from `57.9` toward the validated `51`.
- validated walks stay in low single digits and do not regress back toward Garmin load.

## Validation and Acceptance

Acceptance is based on known, user-validated examples.

For walks, representative short sessions must remain around `2-5 TSS`, and long easy walks must not inflate into the teens merely because of a single universal hourly constant.

For swims, the June 30 swim-like summary must stay in the mid-60 band while the easy June 25/26 swim-like summaries move materially closer to the validated `5-8` range than the current implementation.

For runs, the June 27 aerobic-pickups-like summary must no longer overshoot into the high-50s when the validated reference is `51 TSS`.

No regression is allowed to the `#35` contract: `garmin_training_load` must remain separate from product-facing `tss`.

## Idempotence and Recovery

This plan is additive and safe to rerun. Tests can be run repeatedly. The resolver changes will affect newly synced and backfilled rows, but they do not require destructive schema changes. If a formula experiment fails, revert only the resolver/test edits and keep the database contract intact.

The current worktree already contains unrelated local files (`web/package-lock.json` changes and several untracked docs/artifacts). They are not part of this task and must not be staged into the calibration commit.

## Artifacts and Notes

Current local evidence before this calibration pass:

    2026-06-30 swim  -> AI Trainer 62.7 vs IC 65
    2026-06-30 walk  -> AI Trainer 1.4  vs IC 2
    2026-06-29 walk  -> AI Trainer 2.9  vs IC 3
    2026-06-28 walk  -> AI Trainer 4.6  vs IC 5
    2026-06-27 run   -> AI Trainer 57.9 vs IC 51
    2026-06-26 swims -> AI Trainer 6.4 / 7.6 vs IC 5 / 5
    2026-06-25 swim  -> AI Trainer 13.8 vs IC 8

These are the examples the updated tests should encode.

## Interfaces and Dependencies

At the end of this work, `data.data_processor.ActivityProcessor.resolve_tss(activity_data, ftp=None, lthr=None)` must still return a dictionary with at least:

    {
        "tss": <float>,
        "source_tss": <float | None>,
        "garmin_training_load": <float | None>,
        "tss_method": <str>,
    }

`data.database.Database.sync_activities(...)` and `api.routers.activities.list_activities(...)` must remain contract-compatible with `#35`.

Revision note (2026-07-01): created as the explicit follow-up ExecPlan for issue `#37` after merged PR `#36` fixed the semantic bug but left sport-specific calibration gaps against IntervalCoach.

Revision note (2026-07-01, implementation update): completed the first calibration pass with summary-zone swim/run formulas, walk heuristic retuning, and database-open recalibration for persisted rows.
