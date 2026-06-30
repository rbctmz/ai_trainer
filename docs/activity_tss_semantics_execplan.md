# Separate Garmin Load From Activity TSS

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

This document must be maintained in accordance with `.agent/PLANS.md`.

## Purpose / Big Picture

After this change, the Activities screen and any downstream load math will stop treating Garmin `activityTrainingLoad` as if it were already Training Stress Score (TSS). A user will be able to sync Garmin, open `http://localhost:3000/activities`, and see a `TSS` column that comes from a reproducible sport-specific estimate while still keeping Garmin load available as a separate diagnostic metric. The practical outcome is that short open-water swims no longer show absurd values like `99.8 TSS` for `18.6 min`, and long swims no longer inflate weekly totals simply because Garmin load was written into the `tss` column.

## Progress

- [x] (2026-07-01 00:37Z) Confirmed the regression after issue `#32`: historical rows now refresh correctly, but `tss` is still semantically wrong because `activityTrainingLoad` is stored directly in the TSS field.
- [x] (2026-07-01 00:40Z) Verified against live Garmin and IntervalCoach that the June 30 open-water swim (`activity_id=23432905393`) has `activityTrainingLoad=155.7` in Garmin summary payload while IntervalCoach shows `65 TSS`, proving the metrics are not equivalent.
- [x] (2026-07-01 00:43Z) Confirmed the Garmin list payload already contains enough summary fields to compute a better estimate without extra per-activity detail calls: `movingDuration`, `moderateIntensityMinutes`, `vigorousIntensityMinutes`, and `hrTimeInZone_1..5`.
- [x] (2026-07-01 00:52Z) Implemented schema and sync changes so Garmin load is stored separately from computed TSS. `activities` rows now persist `garmin_training_load` plus optional zone/intensity summary fields, and `resolve_tss(...)` no longer aliases Garmin load into `tss`.
- [x] (2026-07-01 00:54Z) Added contributor-safe tests for walk separation, swim zone-based estimation, legacy row backfill, API envelope semantics, and sync-pipeline semantics.
- [x] (2026-07-01 00:58Z) Ran `python3 -m pytest tests/smoke -q` green and verified the local API after a real `/api/sync?days=7` call. The June 30 swim now lands at `62.7 TSS` with `garmin_training_load=155.7`, which is materially aligned with the user-validated `65 TSS`.

## Surprises & Discoveries

- Observation: the current bug is not a stale-UI problem anymore; it is a metric-semantics problem.
  Evidence: after manual sync, `http://127.0.0.1:3000/api/activities?days=3` updated immediately, but the June 30 swim still showed `tss=155.7`, matching Garmin load rather than IntervalCoach `65 TSS`.

- Observation: Garmin list payloads already include heart-rate zone times and intensity minutes, so a better TSS estimate does not require an expensive detail request for every activity.
  Evidence: the live list item for `23432905393` includes `hrTimeInZone_1..5`, `moderateIntensityMinutes=4`, `vigorousIntensityMinutes=59`, `movingDuration=3473`, and `activityTrainingLoad=155.7`.

- Observation: a simple zone-weighted swim score is much closer to IntervalCoach than Garmin load.
  Evidence: using weights `[0.25, 0.5, 0.75, 1.0, 1.25]` over Garmin zone minutes yields about `62.6` for the June 30 swim (IC shows `65`), `12.6` for the June 23 `12.2 min` swim (IC shows `12`), and `19.4` for the June 23 `18.6 min` swim (IC shows `19`).

- Observation: the live Garmin resync on the patched code only populates zone summaries for some swims, so the resolver must remain dual-path.
  Evidence: after a real `/api/sync?days=7`, the June 30 and June 26 swims switched to `hr_zone_tss_swim`, while several June 23 swims still lacked zone summary fields and correctly stayed on `hr_tss_swim` fallback instead of reverting to Garmin load.

- Observation: walk sessions align better with moving-duration heuristics than with Garmin load or intensity minutes.
  Evidence: the user-verified walks are near `2 / 3 / 5 TSS` in IntervalCoach, while `movingDuration * 8.5 / 60` gives roughly `1.4 / 2.9 / 4.6`, and raw Garmin load gives `3.3 / 3.9 / 6.8`.

## Decision Log

- Decision: treat `activityTrainingLoad` as Garmin load, not as TSS.
  Rationale: live evidence from the June 30 swim proves the values are materially different (`155.7` vs `65`), so preserving the old mapping would keep the product mathematically wrong.
  Date/Author: 2026-07-01 / Codex

- Decision: keep the fix summary-payload-only for now instead of implementing an interval-aware IC clone.
  Rationale: Garmin list payload already contains enough data for a strong correction. Exact parity with IntervalCoach interval modeling is a deeper follow-up and should not block the immediate semantics repair.
  Date/Author: 2026-07-01 / Codex

- Decision: use sport-specific TSS estimation paths.
  Rationale: the evidence shows one universal formula is the source of repeated errors. Walk, swim, run, and bike need different fallback logic even when they all come from the same Garmin sync.
  Date/Author: 2026-07-01 / Codex

- Decision: keep `source_tss` as a compatibility alias for Garmin load during this transition, but stop using it as the product-facing `tss`.
  Rationale: the current API/web path already knows about `source_tss`, so preserving it avoids a broader contract break while still fixing the displayed metric semantics.
  Date/Author: 2026-07-01 / Codex

## Outcomes & Retrospective

This plan started from a completed-but-wrong `#32`: historical rows refreshed, but they refreshed into the wrong metric. The implemented result is now concrete and verifiable: after sync, `tss` means “best local TSS estimate,” `garmin_training_load` means “Garmin load,” and the Activities totals no longer explode on swims. Exact IC parity is still a follow-up problem for sports/activities where Garmin does not expose zone summary fields on the list payload, but that is now an explicit estimation gap rather than a mislabeled metric.

## Context and Orientation

The relevant code lives in four places.

`data/data_processor.py` normalizes Garmin list payloads and currently extracts `activityTrainingLoad` into `source_tss`, then short-circuits `resolve_tss(...)` to store that value directly as `tss`. That is the semantic bug.

`services/sync.py` calls `ActivityProcessor.process_activities(...)`, then `resolve_tss(...)`, then hands the enriched records to `Database.sync_activities(...)`.

`data/database.py` defines the `activities` schema and the write/update paths. This file needs to store Garmin load separately from computed TSS and must also repair existing rows where `tss_method == "garmin_training_load"`.

`api/routers/activities.py` exposes the recent activity envelope consumed by `web/app/activities/page.tsx`. This endpoint must keep `tss` as the displayed metric while also exposing Garmin load as diagnostic metadata.

For this plan, “Garmin load” means the value Garmin reports as `activityTrainingLoad`. “TSS” means the product-facing stress score shown in the Activities table and rolled into activity totals. They are no longer allowed to be aliases of the same number.

## Plan of Work

First, update `data/data_processor.py` so processing extracts `garmin_training_load`, `moderate_intensity_minutes`, `vigorous_intensity_minutes`, and `hr_time_in_zone_1..5` from Garmin list items. Keep `source_tss` only as a backward-compatible alias for the Garmin load field while the rest of the codebase catches up. Then replace the `resolve_tss(...)` short-circuit. Instead of “if Garmin load exists, return it as TSS,” the method should compute TSS by sport:

- walking: use a moving-duration heuristic, because that best matches the observed easy-walk sessions.
- swimming: prefer a zone-weighted score built from `hr_time_in_zone_1..5`, using weights tuned from the real June 23 and June 30 swims. If zone data is missing, fall back to HR-based TSS using available duration/heart-rate fields.
- running: compute both HR-based TSS and a zone-weighted run score, then keep the larger one so interval runs are not undercounted by average heart rate alone.
- cycling: keep the existing power-first behavior, but use moving duration and normalize the power-field extraction.
- other sports: use the conservative duration heuristics already present.

Second, extend `data/database.py` so the `activities` table stores the new summary fields, especially `garmin_training_load`, `moderate_intensity_minutes`, `vigorous_intensity_minutes`, and `hr_time_in_zone_1..5`. Add a one-time additive backfill in the database initializer: any row whose `tss_method` is still `garmin_training_load` should copy its legacy load into `garmin_training_load` and then recompute `tss` with the new resolver from whatever summary fields are available locally.

Third, update `api/routers/activities.py` so `tss_source` reflects how `tss` was actually computed, not the mere presence of Garmin load. Expose `garmin_training_load` separately in each item, and keep `source_tss` only as a compatibility alias if removing it would break current callers.

Fourth, adapt the smoke tests. The old acceptance that “source TSS is preferred and persisted” is now wrong and must be replaced with “Garmin load is persisted separately while TSS stays computed.” Add one swim test that proves a Garmin load of `155.7` does not become `tss=155.7`, one walk test that proves moving-duration heuristics remain conservative, and one run test that proves interval runs are no longer limited to plain average-HR undercounting.

## Concrete Steps

Work from the repository root:

    cd /Users/gregkisel/Developer/ai_trainer

Capture the live evidence already observed:

    curl -sS 'http://127.0.0.1:3000/api/activities?days=3'

Garmin summary evidence for the June 30 swim:

    activityTrainingLoad = 155.725830078125
    duration = 3717.056 sec
    movingDuration = 3473 sec
    averageHR = 142
    hrTimeInZone_1..5 = 63 / 318 / 516 / 1312 / 1509 sec

IntervalCoach evidence for the same swim:

    2.2 km · 1:00:17 · 65 TSS
    intervals: 12m@Z1, 13m@Z2, 15m@Z3, 16m@Z2, 5m@Z4

After edits, run:

    python3 -m pytest tests/smoke/test_activity_tss_reconciliation.py tests/smoke/test_api_phase1.py tests/smoke/test_garmin_sync_service.py -q
    python3 -m pytest tests/smoke -q

Then verify the local API output:

    curl -sS 'http://127.0.0.1:8000/api/activities?days=10'

The expected qualitative result is that swim rows stop carrying Garmin load in the `tss` field and instead expose a lower `tss` plus a separate `garmin_training_load`.

## Validation and Acceptance

Acceptance is behavioral.

For a Garmin swim activity with `activityTrainingLoad=155.7`, after sync or backfill the stored `tss` must no longer equal `155.7`. The row must retain the Garmin load separately, and the product-facing TSS must land in the same rough band as the user’s validated reference (`65 TSS` in IntervalCoach for the June 30 swim).

For walks, the result must remain conservative. A short walk like the June 30 `11 min` activity should stay in the low single digits, not jump into double digits because the score was derived from the wrong metric.

For interval runs, the estimate must not be limited to plain average-HR undercounting. The June 27 run should no longer collapse to the mid-30s just because its average HR was lower than its interval peaks.

The contributor-safe smoke suite must remain green.

## Idempotence and Recovery

The schema change is additive. Re-running table initialization must be safe because `_ensure_activity_columns(...)` only adds missing columns. The backfill must be written to be re-runnable: rows already migrated away from `tss_method == "garmin_training_load"` should be skipped. If the backfill is interrupted, restarting the application or re-running the tests should converge the rows to the same final state.

## Artifacts and Notes

Key evidence from live Garmin list payload for `23432905393`:

    activityTrainingLoad = 155.725830078125
    moderateIntensityMinutes = 4
    vigorousIntensityMinutes = 59
    hrTimeInZone_1..5 = 63.027 / 317.548 / 515.680 / 1311.768 / 1508.927

Zone-weighted swim estimate using weights `[0.25, 0.5, 0.75, 1.0, 1.25]`:

    1.05*0.25 + 5.29*0.5 + 8.59*0.75 + 21.86*1.0 + 25.15*1.25 = 62.6

That is close enough to the user-validated `65 TSS` to justify the summary-payload fix.

## Interfaces and Dependencies

At the end of this work, `ActivityProcessor.process_activities(...)` must emit `garmin_training_load`, `moderate_intensity_minutes`, `vigorous_intensity_minutes`, and `hr_time_in_zone_1..5` when the Garmin payload contains them.

`ActivityProcessor.resolve_tss(activity_data, ftp=None, lthr=None)` must continue returning a dictionary, but its returned `tss` must represent computed product TSS, not Garmin load. The dictionary should still include the Garmin load for persistence, either through `garmin_training_load` directly or a documented compatibility alias.

`Database.sync_activities(...)` must continue returning `{"new": N, "updated": M, "skipped": K}` while writing the richer activity schema.

`api.routers.activities.list_activities(...)` must continue returning the existing envelope shape while adding a distinct Garmin-load field and ensuring `tss_source` describes the actual TSS derivation path.

Revision note (2026-07-01): created this follow-up ExecPlan after the merged `#32` fix revealed the deeper semantic bug that Garmin load and TSS are not interchangeable. Formal tracking issue: `#35`.
