# Activity TSS Reconciliation

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

This document must be maintained in accordance with `.agent/PLANS.md`.

## Purpose / Big Picture

After this change, completed activities in AI Trainer should use the most faithful available Garmin load value instead of inflating TSS through one naive cross-sport formula. The user-visible effect is straightforward: the Activities page, dashboard load metrics, and downstream coaching/planning logic no longer treat easy walks or short swims as if they were hard bike sessions just because the sync pipeline had only duration, heart rate, or average power and applied the wrong fallback. A contributor should be able to sync or seed a source-backed activity, inspect `/api/activities`, and see both the corrected `tss` and the provenance that explains where it came from.

## Progress

- [x] (2026-06-30) Audited the current project state before starting issue `#32`: `main` and `origin/main` match, contributor-safe smoke is green (`246 passed`), the broader non-live pytest pass is green (`294 passed, 24 deselected`), `web/` builds successfully, and issue `#26` is already closed so the old publish blocker is no longer valid for this work.
- [x] (2026-06-30) Confirmed the current root cause in code: `services/sync.py::_sync_activities()` always recomputes `tss` locally through `ActivityProcessor.calculate_tss(...)`, and `data/database.py` stores only one opaque `tss` number with no source/provenance fields.
- [x] (2026-06-30) Confirmed the likely Garmin source-of-truth field from the installed `garminconnect` package: activity payload examples include `activityTrainingLoad` and `movingDuration`, while the current processor ignores both.
- [x] (2026-06-30) Implemented source-backed TSS resolution in `data/data_processor.py`, persisted richer activity provenance in `data/database.py`, rewired `services/sync.py` to stop blindly overwriting Garmin load, and exposed provenance through `api/routers/activities.py`.
- [x] (2026-06-30) Added focused contributor-safe coverage in `tests/smoke/test_activity_tss_reconciliation.py` and extended existing sync/API smoke assertions for source-backed activities.
- [x] (2026-06-30) Validated the change with focused smoke (`13 passed`), full contributor-safe smoke (`248 passed`), and the broader non-live suite (`296 passed, 24 deselected`).
- [ ] Publish the branch and open a PR that closes issue `#32`.

## Surprises & Discoveries

- Observation: the local SQLite schema and the checked-in `Database.init_tables()` definition have already drifted.
  Evidence: `PRAGMA table_info(activities)` on `ai_trainer.db` shows `training_effect`, `anaerobic_effect`, `activity_name`, and `description`, but `data/database.py::init_tables()` currently creates an `activities` table without those columns. Existing sync writes also do not persist those fields.

- Observation: the current TSS inflation is not hypothetical; the existing local data shows exactly the pattern reported from IntervalCoach.
  Evidence: recent `walking` rows in `ai_trainer.db` store `tss` values such as `27.9` for `66.9` minutes and `38.6` for `90.6` minutes, which are much higher than the user-reported Garmin/IntervalCoach values for equivalent easy walking sessions.

- Observation: using `avg_power / USER_FTP` on running rows is already happening in practice.
  Evidence: the recent local activity `23394412513` is stored as `running` with `avg_power=279` and `tss=103.8`. The current code path in `ActivityProcessor.calculate_tss()` prefers power-based TSS whenever `avg_power` and `USER_FTP` exist, regardless of sport.

- Observation: `garminconnect` already exposes the two fields this fix needs most, so this does not require per-activity detail fetches as a first step.
  Evidence: the installed package includes activity examples with `activityTrainingLoad` and `movingDuration` directly in the activity list payload, and the library source for `get_activities_by_date(...)` returns that raw list payload unchanged.

- Observation: the existing `activities` table schema drifted far enough that this bugfix naturally turned into a small compatibility migration.
  Evidence: once source/provenance fields were added, the existing mismatch between historical columns in `ai_trainer.db` and the much narrower `init_tables()` definition had to be corrected or fresh test databases would still lose fields like `training_effect`, `activity_name`, and the new provenance columns.

## Decision Log

- Decision: treat Garmin `activityTrainingLoad` as the preferred source TSS/load field when it is present and positive.
  Rationale: the user complaint is specifically that AI Trainer diverges from Garmin/IntervalCoach for completed sessions. A source-backed load is closer to the product the user is already validating against than any local heuristic.
  Date/Author: 2026-06-30 / Codex

- Decision: persist provenance explicitly instead of overwriting `tss` with no explanation.
  Rationale: once source-backed and fallback-computed values can both exist, the product needs a machine-readable way to explain which method produced the stored `tss`.
  Date/Author: 2026-06-30 / Codex

- Decision: stop using bike FTP power-based TSS for all sports.
  Rationale: the issue scope explicitly calls this out as an obvious cross-sport error. Power-based TSS may remain valid for bike-like sports, but not for run/walk/swim sessions under a bike FTP assumption.
  Date/Author: 2026-06-30 / Codex

- Decision: keep the fallback conservative when source load is absent instead of inventing a more complex physiological model in the same slice.
  Rationale: the highest-value correction is “prefer Garmin load when present.” Sport-specific conservative heuristics plus moving-duration support are enough to stop the worst 2x-5x inflation without turning issue `#32` into a larger training-model rewrite.
  Date/Author: 2026-06-30 / Codex

## Outcomes & Retrospective

The repository now prefers Garmin `activityTrainingLoad` when it is available, stores `source_tss`, `moving_duration_minutes`, and `tss_method` in `activities`, and exposes that provenance through `/api/activities`. The contributor-safe and broader non-live test baselines remain green after the change. What remains is the normal publication step for issue `#32` and, after that, a follow-up backlog pass to update stale issue labels that still reflect the old pre-`#26` automation state.

## Context and Orientation

This repository is in a web-first migration, but completed activity load still flows through the older shared Python path. The relevant modules are:

- `services/sync.py`: the Garmin sync orchestrator. `_sync_activities(...)` takes raw activity payloads from Garmin, converts them through `ActivityProcessor`, computes `tss`, and passes records into the database.
- `data/data_processor.py`: the activity normalizer. It currently extracts basic fields like duration, distance, and heart rate, but ignores Garmin `activityTrainingLoad` and `movingDuration`. Its `calculate_tss(...)` method always chooses one local formula.
- `data/database.py`: the SQLite persistence layer. The `activities` table is the source for `/api/activities`, dashboard load calculations, and downstream coaching/planning analytics. Today it persists only one final `tss` number with no provenance.
- `api/routers/activities.py`: the product-facing activities API. If this change adds provenance fields, this endpoint is where they become visible to the web UI or diagnostics.
- `web/app/activities/page.tsx`: the current activities screen. It does not need a large redesign for this issue, but it is a useful place to consume any new provenance fields if they help product diagnostics.

The bug is therefore not “the dashboard math is wrong in isolation.” The wrong number enters much earlier, at sync time, and then every other surface trusts that stored `tss`.

## Plan of Work

The first implementation step is to upgrade `data/data_processor.py` from a one-number calculator into a source-aware resolver. The processor should extract `activityTrainingLoad` into a dedicated `source_tss` field, extract `movingDuration` into minutes, and expose a `resolve_tss(...)` helper that returns both the chosen `tss` value and a short `tss_method` string. `calculate_tss(...)` can remain as a compatibility wrapper if any existing callers still expect a bare float.

The second step is to bring `data/database.py` back into sync with reality and make the `activities` table forward-compatible. The schema should explicitly include the existing richer activity columns plus new provenance columns such as `source_tss`, `moving_duration_minutes`, and `tss_method`. The table initializer should create them for fresh databases, and a compatibility helper should add any missing columns for existing databases through `PRAGMA table_info(...)` plus `ALTER TABLE ... ADD COLUMN ...`. Both `save_activities(...)` and `sync_activities(...)` must read and write the same richer column set.

The third step is to update `services/sync.py::_sync_activities(...)` so it stops assigning `df["tss"]` from one local formula. Instead, it should ask the processor for the resolved TSS record per activity, persist `tss`, `source_tss`, `moving_duration_minutes`, and `tss_method`, and keep the sync payload additive and backward-compatible.

The fourth step is to expose provenance in `api/routers/activities.py`. The API should keep the existing `tss` field for compatibility, but it should also include the source/provenance fields in each item so diagnostics and future UI can tell whether the value came from Garmin source load or a local fallback.

The fifth step is testing. Add a focused smoke test file for source-backed vs fallback-computed TSS. Also extend the existing sync smoke to assert that source-backed Garmin activities preserve their source load and that the method string survives to storage and API. The contributor-safe suite is the acceptance baseline.

## Concrete Steps

Work from the repository root:

    cd /Users/gregkisel/Developer/ai_trainer
    git switch -c codex/issue-32-tss-reconciliation

Inspect the current schema and recent activity rows:

    sqlite3 ai_trainer.db "PRAGMA table_info(activities); SELECT activity_id,date,sport,duration_minutes,tss FROM activities ORDER BY date DESC LIMIT 12;"

Confirm the live root cause in code:

    rg -n "calculate_tss|activityTrainingLoad|movingDuration|sync_activities" data services

After edits, validate syntax and contributor-safe behavior with:

    python3 -m pytest tests/smoke/test_garmin_sync_service.py tests/smoke/test_api_phase1.py tests/smoke/test_activity_tss_reconciliation.py -q
    python3 -m pytest tests/smoke -q

If the broader non-live suite still fits the touched scope, also run:

    python3 -m pytest -m "not live and not debug" tests/ -W error::pytest.PytestReturnNotNoneWarning

## Validation and Acceptance

Acceptance is behavioral, not just structural.

First, a source-backed Garmin activity with `activityTrainingLoad` must keep that value as the stored `tss`. A test fixture should demonstrate that when sync receives such an activity, the database record and `/api/activities` both show the Garmin-backed number plus a provenance marker such as `garmin_training_load`.

Second, a fallback-computed activity must use a sport-aware method. A running or walking fixture must no longer use bike FTP power-based TSS simply because `avg_power` is present. A test should prove that `tss_method` identifies the fallback path and that the computed value is materially lower than the old naive path for the same non-bike session.

Third, the contributor-safe suite must remain green. The default command is:

    python3 -m pytest tests/smoke -q

The expected result after this change is a fully passing smoke suite and new passing source-vs-fallback coverage. The live validation transcripts for this implementation are:

    python3 -m pytest tests/smoke/test_garmin_sync_service.py tests/smoke/test_api_phase1.py tests/smoke/test_activity_tss_reconciliation.py -q
    13 passed in 2.23s

    python3 -m pytest tests/smoke -q
    248 passed in 3.26s

    python3 -m pytest -m "not live and not debug" tests/ -W error::pytest.PytestReturnNotNoneWarning
    296 passed, 24 deselected, 1 warning in 20.05s

## Idempotence and Recovery

The database migration for `activities` must be additive. The plan may run against a fresh temporary SQLite file or an existing local `ai_trainer.db`; in both cases the code should safely create missing columns without deleting rows. If a test fails midway, rerunning the same initialization should leave the schema in the same final shape. No destructive migration is needed for this slice.

## Artifacts and Notes

Current evidence that motivates the fix:

    services/sync.py::_sync_activities():
        ActivityProcessor.process_activities(...)
        ActivityProcessor.calculate_tss(...)
        df["tss"] = tss_values

    Local ai_trainer.db recent rows:
        2026-06-29 walking 28.0 min -> tss 11.9
        2026-06-28 walking 66.9 min -> tss 27.9
        2026-06-24 walking 90.6 min -> tss 38.6

These are the kinds of inflated values that distort the whole product surface.

Implementation evidence after the fix:

    source-backed walking fixture:
        activityTrainingLoad = 3.0
        movingDuration = 1200 sec
        stored row -> tss 3.0, source_tss 3.0, tss_method garmin_training_load

    run fallback fixture with avgPower but no source load:
        sport = running
        avgPower = 279
        movingDuration = 2400 sec
        stored row -> tss 33.3, tss_method heuristic_duration_run

The second case is the key “do not use bike FTP for running power” proof.

## Interfaces and Dependencies

At the end of this work, the following interfaces should exist or remain stable:

- `data.data_processor.ActivityProcessor.resolve_tss(activity_data, ftp=None, lthr=None) -> dict`
  This helper should return the chosen `tss`, the original `source_tss` if any, the chosen `tss_method`, and any duration field needed by the method.

- `data.database.Database.sync_activities(activities) -> dict`
  This method should continue returning `{"new": N, "updated": M, "skipped": K}` while persisting the richer activity payload.

- `api.routers.activities.list_activities(...) -> dict[str, Any]`
  This endpoint should keep the current envelope but may add per-item provenance fields such as `source_tss`, `tss_method`, and `moving_duration_minutes`.

Revision note (2026-06-30): created this ExecPlan from the live project audit and issue `#32` investigation because the TSS bug is now the top product priority after the publish-loop fix in `#26`.
