# Import daily Intervals self-reports

This living ExecPlan follows .agent/PLANS.md. Issue #555 is Class A — Full. The owner implements specification, then domain/API, then explicitly hands off to the UI role; OpenCode is a read-only checker. The human owns merge.

## Purpose / Big Picture

An athlete who already records feelings in Intervals sees those observations in AI Trainer without a second questionnaire. Coach receives the same dated observations. No observation changes computed readiness, load, or plans.

## Progress

- [x] (2026-09-09) Isolated worktree /private/tmp/ai-trainer-555 from origin/main aff1a06; existing #554 checkout untouched.
- [x] (2026-09-09) Official OpenAPI downloaded without credentials; eight integer fields and updated timestamp confirmed. Provider author documents 1–4, lower is better. Labels cross-checked against owner screenshot.
- [x] (2026-09-09) Mapping/storage RED (missing module) → GREEN; clear, invalid, retry, restart/reset and transaction rollback verified.
- [x] (2026-09-09) Eight new tests pass, including real TestClient API and AITools agreement from temporary SQLite.
- [x] (2026-09-09) UI handoff, component, contract extraction, lint/build and desktop/mobile browser checks complete. Screenshots visually inspected; no horizontal overflow.
- [ ] Broad tests, OpenCode review, disposition, commit and draft PR.

## Surprises & Discoveries

Observed: WELLNESS_FIELDS only requests sleepQuality among the eight ratings. normalize_intervals_wellness ignores it. Verified by source inspection; targeted new tests will falsify the missing-path hypothesis.

Observed: official schema declares integers but does not enumerate labels. The provider author's API guide explicitly states 1–4 with 1 good, 4 bad. The screenshot agrees for all eight scales. A third-party reference says 1–5; rejected in favor of the primary source. API field updated is a day-record timestamp, not the time a person answered a particular question. No morning claim or manual-entry attribution is justified.

## Decision Log

Store provider-owned daily snapshots separately from measured metrics. The identity is provider plus local date. Explicit null and absent requested fields become missing in the latest returned day snapshot; never carry forward an older answer into a new day. Unknown numeric/string values become invalid with no diagnostic interpretation, while other fields remain usable. Missing whole days are not inferred to be deletions. No raw free-text or unrelated health data is retained.

Serialize storage with BEGIN IMMEDIATE inside the existing chunk transaction. Compare fetch-start timestamps to reject out-of-order responses; reject an older provider updated timestamp too when both are known. Use received_at for transport provenance only, not observation freshness. Incremental overlap remains one day; older edits require an explicit bounded backfill through the existing sync option. No new cursor.

## Outcomes & Retrospective

Initial broad run: 2340 passed, 6 skipped, 26 deselected (before three additional route/date tests). Focused suite: 47 passed before those additions; new suite now 8 passed. Web lint/build and contract extraction passed; 67 contract checks and final 50 focused tests passed. No live athlete data read or changed. Screenshots: docs/assets/issue_555_dashboard.png and docs/assets/issue_555_today.png. Browser fixture initially returned malformed empty objects to unrelated endpoints; corrected to explicit 503 responses. The feature rendered on both routes from real synthetic API data.

## Context and Orientation

services/intervals_icu.py selects GET fields; services/wellness_ingest.py maps provider rows and calls Database.sync_wellness_batch. data/database.py owns SQLite initialization, atomic chunk persistence and full reset. Add data/subjective_wellness_store.py for the provider-owned table, models/subjective_wellness.py for bounded scales, and services/subjective_wellness.py for dated read projection. services/readiness_snapshot.py exposes a separate subjective_wellness block even when measured readiness is unknown. api/today_snapshot.py forwards the block. models/ai_coach_runtime.py instructs Coach how to read it; get_readiness_today has a separate measured calculation; attach the same subjective read projection there without changing its measured calculation. UI reads backend labels without implementing scales.

## Plan of Work

Write mapping/lifecycle tests before implementation. Add one table without modifying existing tables or metrics. Include it in full reset. Preserve source timestamp, fetch timestamp, mapping version, per-field present/missing/invalid state and bounded value. Add an optional TS/API block containing status, date, source, age_days, timestamps, and labeled items. Status describes observations only: current, stale, missing, unavailable. Today and dashboard show the same reusable read-only component; it remains visible without a training plan. Coach must not re-ask present current fields, but may ask about context or missing fields. No automatic action derives from the block.

## Concrete Steps

Work in /private/tmp/ai-trainer-555. Use ./ai_trainer_env/bin/python -m pytest tests/smoke/test_issue_555_subjective_wellness.py -q for the new route and lifecycle. Run existing test_m4_intervals_wellness.py and test_readiness_snapshot_contract.py as compatibility baseline. Run ruff and contributor-safe tests. For web run lint, build, contract:extract and contract freshness; browser checks must use a synthetic API response, never personal records. Record exact results below when run.

## Validation and Acceptance

Eight answers survive the full provider → sync → temporary SQLite → shared snapshot → API/Coach route. Repeated reads do not duplicate rows, corrections and clears supersede, out-of-order responses do not restore old values, midnight preserves provider-local date, stale data remains stale after a current activity. Unknown enums and absent data do not become good health. Full reset removes the table rows and wellness cursor. Transaction failure leaves both data and cursor unchanged. Existing measured metrics, readiness score and plan/load tables are identical before and after subjective-only imports. API and browser display labels, source and age without a duplicate form.

## Idempotence and Recovery

One row per provider/day is an additive cache projection. Restart reconstructs from SQLite; repeated sync updates transport timestamps without duplicating observations. Rollback to prior code leaves an unused additive table; no existing schema changes need reversal. Full reset removes observations. Do not touch the real ai_trainer.db or backups. No provider writes.

## Artifacts and Notes

Sources checked 2026-09-09: https://intervals.icu/api/v1/docs (Wellness properties), https://forum.intervals.icu/t/api-access-to-intervals-icu/609/34 (daily GET and scale semantics), owner screenshot (eight labels). Synthetic fixtures only. Missing GET fields are conservatively unavailable, never proof of a healthy state. Scale contract: sleepQuality excellent/good/average/poor; soreness, fatigue, stress low/average/high/extreme; mood excellent/good/OK/grumpy; motivation extreme/high/average/low; injury none/niggle/poor/injured; hydration excellent/OK/poor/bad. All are 1–4. PUT unset sentinel -1 is not treated as a valid GET rating.

## Interfaces and Dependencies

No new dependency. Store ownership remains Intervals regardless of PRIMARY_WELLNESS_SOURCE, because these are separate observations. Mapping preserves provider field keys and emits Russian labels from shared Python. Settings.ATHLETE_TIMEZONE determines the read date unless explicitly supplied. ASR-REL-2 (missing evidence), ASR-REL-3 (atomic cursor), ASR-MOD-2 (web projection), ASR-MOD-3 (additive schema), ADR-0001 (web primary) apply. The slice spec is docs/issue_555_slice_spec.md.

Revision 2026-09-09: updated completed checks and corrected the Coach tool handoff after tracing its independent measured-readiness path.

Revision 2026-09-09: corrected ASR IDs against the catalog, recorded UI evidence. External reviewer export awaits explicit permission after automatic approval rejection.
