# Prefer Running Pace Targets When Intervals.icu Provides Threshold Pace

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`,
`Decision Log`, and `Outcomes & Retrospective` must stay current while the work proceeds.
This document is maintained in accordance with `.agent/PLANS.md`.

## Purpose / Big Picture

AI Trainer already knows how to prescribe running workouts by pace, heart rate, or
perceived effort, in that order. In production, however, every running workout currently
uses heart rate because the athlete profile sync discards Intervals.icu's running
threshold pace and the planning service never receives it.

After this change, a valid Intervals.icu running threshold pace is stored locally as
seconds per kilometre, with its own source and observation time. A newly and explicitly
built plan uses that pace to materialize running steps and the export screen explains the
basis before delivery, for example `по пороговому темпу 6:15/км`. If pace is missing or
invalid, the existing safe chain remains unchanged: LTHR, the lactate-threshold heart
rate, then relative RPE, the athlete's perceived effort. Sync does not rebuild or mutate
an existing plan, so workouts already delivered to Intervals.icu or Garmin do not change.

## Progress

- [x] (2026-07-29 11:10Z) Read issue #308, the current profile sync, database schema,
  planning materialization, Intervals delivery, and web export surfaces.
- [x] (2026-07-29 11:15Z) Fixed the data contract and failure semantics in this plan
  before editing production code.
- [x] (2026-07-29 11:24Z) Added RED provider/schema/planning/delivery/UI gates; initial
  focused run reported 25 failed and 38 passed for the expected missing behavior.
- [x] (2026-07-29 11:31Z) Implemented additive profile migration, strict Run mapping,
  canonical conversion, field provenance, and carry-forward.
- [x] (2026-07-29 11:35Z) Wired explicit plan builds to the existing
  pace/LTHR/RPE chain and added Intervals `/km` round-trip coverage.
- [x] (2026-07-29 11:38Z) Added profile and pre-delivery web explanations; Next lint
  and production build pass.
- [x] (2026-07-29 11:42Z) Focused vertical 63/63, regression 93/93, contributor-safe
  smoke 1330 passed/1 skipped, broad 1376 passed/3 skipped/24 deselected.
- [x] (2026-07-29 11:43Z) Completed diff/self-review and updated ASR traceability.
- [x] (2026-07-29 11:50Z) Published ready PR #309 with `Closes #308`; implementation
  SHA `ffb5c96` passed every required check and thread-aware review inspection found
  zero unresolved threads. This final ExecPlan evidence update is docs-only.

## Surprises & Discoveries

- Observation: The realistic Intervals.icu fixture already contains a Run
  `threshold_pace` of `2.6666667`, but `normalize_athlete_profile` selects only the
  cycling settings entry and returns FTP, weight, and LTHR.
  Evidence: `tests/smoke/test_athlete_profile.py::_REAL_SHAPE_PROFILE` and
  `services/intervals_icu.py::normalize_athlete_profile`.

- Observation: The workout catalog and Intervals delivery are already pace-capable.
  The unreachable branch is caused by missing profile data, not missing workout logic.
  Evidence: `models/workout_catalog.py` resolves running targets in the order
  `threshold_pace`, `lthr`, `relative_rpe`; existing catalog tests already prove that a
  seconds-per-kilometre value produces pace targets and `/km` delivery text.

- Observation: The active plan is an append-only planning checkpoint. Athlete-profile
  sync writes a separate table and does not call a plan builder.
  Evidence: `api/planning_service.py::build_plan` is the place where profile values are
  copied into `zone_snapshot`; `services/intervals_icu.py::sync_athlete_profile` only
  writes `athlete_profile`.

- Observation: Reciprocal floating-point arithmetic can move an inclusive pace boundary
  just below its mathematical value.
  Evidence: `1000 / (1000 / 120)` produced a value slightly below 120 on the active
  Python runtime, so the first GREEN run had one failure. Rounding the converted
  canonical value to six decimals before validating fixed the numerical boundary without
  weakening the input contract.

- Observation: A complete generated horizon can include a positive-TSS session that is
  intentionally repair-gated for reasons unrelated to pace.
  Evidence: The first delivery vertical raised `planned session ... is not executable`
  on such a day. The final test selects one actual run day where every leaf passes
  `require_executable_planned_session`, then verifies the pace serialization. It does not
  bypass the production fail-closed guard.

- Observation: Repository-wide Ruff currently reports two pre-existing unused imports in
  `api/planning_service.py`; neither line is touched by this change.
  Evidence: `ruff check` reports F401 at lines 44 and 93, while the zero-context diff for
  that file contains only the new `zone_snapshot` field. Ruff with F401 excluded passes
  for every changed Python file.

## Decision Log

- Decision: Store the canonical value as
  `threshold_pace_seconds_per_km`, never as an unqualified `threshold_pace` database or
  API field.
  Rationale: Intervals.icu sends metres per second while the workout catalog consumes
  seconds per kilometre. An explicit storage name prevents a future caller from silently
  mixing reciprocal units. The planning boundary deliberately maps the explicit field to
  the catalog's existing `zone_snapshot["threshold_pace"]`.
  Date/Author: 2026-07-29, Codex.

- Decision: Identify the running settings entry by exact membership of `Run` in its
  `types` list, independent of array order. Reject ambiguous multiple Run entries.
  Rationale: Array position and cycling capabilities are not a running identity
  contract. Choosing one of several candidates would allow the cursor/profile snapshot
  to claim a value whose origin is ambiguous.
  Date/Author: 2026-07-29, Codex.

- Decision: Accept converted threshold paces from 120 through 900 seconds per kilometre
  inclusive, equivalent to 2:00/km through 15:00/km. Reject booleans, strings,
  non-finite numbers, zero/negative values, and values outside that range.
  Rationale: This bounded interval comfortably covers human running thresholds while
  failing closed on unit mistakes and implausible provider data. Numeric strings are
  rejected here because the provider contract is numeric and coercion would hide a
  malformed response.
  Date/Author: 2026-07-29, Codex.

- Decision: Give threshold pace field-level provenance:
  `threshold_pace_source` and `threshold_pace_synced_at`.
  Rationale: A partial later profile response may refresh FTP or weight while carrying
  forward the last valid pace. Reusing the row-level `synced_at` would falsely claim that
  the provider observed the carried value during the latest request.
  Date/Author: 2026-07-29, Codex.

- Decision: On a successful but partial or malformed profile response, carry forward
  only the last valid threshold pace and its field-level provenance. Keep existing
  FTP/weight/LTHR behavior out of scope.
  Rationale: Issue #308 explicitly requires that a partial response not erase the last
  valid pace. Broadly changing merge semantics for all existing fields would enlarge the
  behavioral surface and risk unrelated TSS logic.
  Date/Author: 2026-07-29, Codex.

- Decision: Do not rebuild, repair, or redeliver an existing plan during profile sync.
  Rationale: A profile observation and a plan mutation are separate user actions.
  Preserving the checkpoint proves already-sent workouts remain byte-for-byte unchanged
  until the user explicitly builds a new plan.
  Date/Author: 2026-07-29, Codex.

## Outcomes & Retrospective

The implementation now delivers the full local vertical. The checked-in realistic
Intervals payload maps `2.6666667 m/s` to approximately `375 seconds/km`, stores it in an
explicit additive schema with field-level source/time, and carries it forward without
restamping when a later response is partial. A newly and explicitly built plan uses pace
for every materialized run prescription; removing pace selects LTHR, and removing both
selects RPE. The Intervals delivery description contains `/km` and excludes `% LTHR` and
`bpm` on the pace path.

The profile card shows threshold pace with its own provider/date. The export view shows
the target basis and pace ranges on singles, multi-session leaves, and brick legs before
the user presses delivery. Sync/checkpoint isolation is covered directly, so this change
does not rebuild or redeliver the user's existing plan.

Verification finished with 63 focused tests and 93 adjacent regressions passing;
contributor-safe smoke reported 1330 passed and 1 environment skip; the broad non-live
suite reported 1376 passed, 3 skipped, and 24 deselected. Next lint and production build
pass. A live Garmin round-trip was deliberately not executed: this repository owns the
structured Intervals payload boundary, while the Intervals-to-Garmin forwarding step is
external and the user has already validated that route with the prior heart-rate plan.
PR #309 is published ready-for-review and awaits the human merge decision. GitHub
reported the implementation SHA mergeable/clean with all checks green and no unresolved
review threads.

## Context and Orientation

`services/intervals_icu.py` owns the standard-library HTTP client and the pure mapping
from an Intervals.icu athlete response into the local profile. Intervals.icu's Run
`threshold_pace` is a numeric speed in metres per second. The local workout catalog in
`models/workout_catalog.py` already treats its `threshold_pace` input as seconds per
kilometre. Conversion is therefore `1000 / metres_per_second`; for the realistic fixture
value `2.6666667`, the result is approximately `375`, or `6:15/km`.

`data/database.py` creates SQLite tables at application start and applies additive
`PRAGMA table_info` plus `ALTER TABLE` migrations to older databases. `athlete_profile`
is append-only: each successful sync inserts a snapshot and
`Database.get_athlete_profile` reads the newest row. The new columns must be nullable so
legacy rows remain valid.

`api/planning_service.py::build_plan` is the explicit plan-construction boundary. It
reads the latest profile and passes a `zone_snapshot` to
`build_daily_session_templates`. The catalog records a `target_provenance` object on each
materialized session or brick leg. No background sync path may call `build_plan`.

`models/intervals_workout_delivery.py` turns stored structured steps into an
Intervals.icu description. Pace steps already render as `/km`; LTHR fallback renders as
`% LTHR`. `api/planning_service.py::plan_days` exposes structured targets and provenance
to `web/app/planning/page.tsx`, whose export tab is the user's final inspection surface
before delivery.

The architecture qualities affected are ASR-MOD-3, because an existing SQLite database
must migrate additively; ASR-REL-1, because an existing checkpoint and delivered workout
must not mutate during sync; and ASR-REL-2, because missing pace must degrade to LTHR or
RPE instead of breaking planning.

## Plan of Work

Milestone 1 establishes the data boundary with tests first. Extend
`tests/smoke/test_athlete_profile.py` with an order-independent Run-selection matrix,
metres-per-second to seconds-per-kilometre conversion, validation boundaries, ambiguous
Run entries, database round-trip, legacy-schema migration, partial-response
carry-forward, and a checkpoint immutability check. Extend the API profile contract test
to expose the explicit value and field-level provenance. Run these tests before
production edits and retain the failing transcript as RED evidence.

Then update `data/database.py`. Add nullable
`threshold_pace_seconds_per_km REAL`, `threshold_pace_source TEXT`, and
`threshold_pace_synced_at TIMESTAMP` columns to new table creation and to an idempotent
athlete-profile migration helper called from `init_tables`. Extend
`save_athlete_profile` and `get_athlete_profile` without changing the meaning of existing
fields. The save method accepts an explicit field timestamp so a carried value preserves
the timestamp of the request that actually observed it.

Update `services/intervals_icu.py` with a pure Run-settings selector and strict numeric
converter. `normalize_athlete_profile` returns the explicit canonical field. During a
successful sync, use the latest database value only when the new normalized pace is
absent; preserve its source and timestamp, otherwise stamp the newly observed value as
`intervals_icu` at insertion time. Provider request failure continues to write nothing.

Milestone 2 proves the vertical plan and delivery behavior. Add an integration test in
`tests/smoke/test_api_planning.py` that explicitly builds a plan from a profile containing
threshold pace and finds materialized running sessions whose provenance kind is
`threshold_pace` and whose step target type is `pace`. Add paired tests showing LTHR and
RPE fallback when pace or both signals are missing. The existing bike and swim assertions
remain unchanged.

Pass `athlete_profile["threshold_pace_seconds_per_km"]` as
`zone_snapshot["threshold_pace"]` in `api/planning_service.py::build_plan`. Expose the
explicit profile fields through `api/routers/athlete_profile.py` and `web/lib/types.ts`.
Add a fourth item to `AthleteProfileCard` that formats the canonical value as `m:ss/км`
and shows the threshold-specific source/date.

Add a small pure formatter in `web/app/planning/page.tsx` for target provenance and render
it on single sessions, multi-session cards, and brick legs. It must show the actual
threshold pace, LTHR, or RPE basis without exposing internal field names. Add pace
formatting to `formatTarget` so the export preview shows the same pace range that will be
delivered.

Finally add an Intervals delivery integration gate in
`tests/smoke/test_intervals_plan_delivery.py` using an actually materialized pace-based
run. Assert `/km` is present and `% LTHR` and `bpm` are absent. Re-run existing bike,
swim, Garmin success-path, and activity-ingest contours.

Update `docs/architecture/asr_catalog.md` with the new source-to-plan unit/provenance
contract and its tests. Keep this ExecPlan current with RED/GREEN transcripts and final
test counts.

## Concrete Steps

Work from the repository root:

    cd /Users/gregkisel/Developer/ai_trainer

Run the initial focused RED set after adding tests but before production code:

    ai_trainer_env/bin/python -m pytest \
      tests/smoke/test_athlete_profile.py \
      tests/smoke/test_api_athlete_profile_contract.py \
      tests/smoke/test_api_planning.py \
      tests/smoke/test_intervals_plan_delivery.py -q

Observed RED: 25 failed and 38 passed. Failures named missing threshold-pace fields,
missing database columns, heart-rate provenance where pace was expected, and absent UI
labels.

After the implementation, the focused command reports 63 passed. Then run:

    ai_trainer_env/bin/python -m pytest \
      tests/smoke/test_workout_catalog.py \
      tests/smoke/test_workout_catalog_v2.py \
      tests/smoke/test_activity_ingest.py \
      tests/smoke/test_garmin_sync_service.py -q

Run the contributor-safe and broad Python contours:

    ai_trainer_env/bin/python -m pytest tests/smoke -q
    ai_trainer_env/bin/python -m pytest -m "not live and not debug" tests/

Run the web checks:

    npm --prefix web run lint
    npm --prefix web run build

Observed results:

    focused vertical: 63 passed
    adjacent catalog/ingest/Garmin/TSS regression: 93 passed
    contributor-safe smoke: 1330 passed, 1 skipped
    broad non-live/non-debug: 1376 passed, 3 skipped, 24 deselected
    Next lint: no warnings or errors
    Next production build: compiled successfully, types valid, 14 static pages generated

## Validation and Acceptance

A realistic Intervals profile with Run `threshold_pace=2.6666667` must result in the
latest database profile containing approximately:

    threshold_pace_seconds_per_km = 375.0
    threshold_pace_source = "intervals_icu"
    threshold_pace_synced_at = <non-empty timestamp>

Reordering `sportSettings` must not change the result. Two exact Run entries, a string,
NaN, infinity, zero, negative speed, or a converted pace outside 120–900 seconds per
kilometre must not replace the previous valid pace.

After an explicit new plan build with this profile, at least one materialized running
session must have:

    target_provenance.kind = "threshold_pace"
    target_provenance.value = 375.0
    materialized_steps[*].target.type = "pace"

The plan API and export page must display the basis as `по пороговому темпу 6:15/км`.
The Intervals description for the same session must contain `/km` and must not contain
`% LTHR` or `bpm`. Removing pace but keeping LTHR must produce LTHR provenance and
Intervals `% LTHR`; removing both must produce relative RPE.

Saving an existing planning checkpoint, running profile sync, and reading the latest
checkpoint again must return the same checkpoint identifier and payload. This is the
automated proof that sync alone does not alter already-built or already-delivered plans.

## Idempotence and Recovery

The schema migration only adds nullable columns that are absent, so repeated
`Database()` initialization is safe. Profile snapshots remain append-only. Repeating a
successful sync may add a newer snapshot but does not duplicate or mutate planning
checkpoints. A partial response carries the last valid pace and its original provenance;
a provider exception writes no row at all.

All verification uses temporary SQLite databases and fake provider responses. Do not run
a live plan build or delivery as part of this change. If implementation fails midway,
re-run the focused tests after editing; no data cleanup is required. The untracked
`.zcode/` directory belongs to the local environment and remains untouched.

## Artifacts and Notes

Issue contract: GitHub issue `#308`, titled “sync running threshold pace and prefer pace
targets over LTHR.”

Initial evidence from the checked-in realistic fixture:

    Intervals Run threshold_pace: 2.6666667 m/s
    Canonical conversion: 1000 / 2.6666667 = approximately 375 seconds/km
    Human display: 6:15/km

The current production gap before this implementation is:

    athlete profile -> ftp, weight_kg, lthr
    planning zone_snapshot -> ftp, lthr
    running catalog -> threshold_pace missing -> LTHR fallback

The intended path is:

    Intervals Run speed -> validated seconds/km + provenance
    -> explicit plan build zone_snapshot -> existing pace materializer
    -> API/web inspection -> existing Intervals structured delivery

## Interfaces and Dependencies

`services/intervals_icu.py` continues to expose:

    def normalize_athlete_profile(raw: Mapping[str, Any]) -> Dict[str, Any]:
        # Adds "threshold_pace_seconds_per_km": float | None.

    def sync_athlete_profile(database: Any) -> Dict[str, Any]:
        # Carries forward only the last valid threshold pace on a partial response.

`data/database.py::Database` continues to expose:

    def save_athlete_profile(self, profile: dict) -> None: ...
    def get_athlete_profile(self) -> dict | None: ...

Their dictionaries additionally contain:

    threshold_pace_seconds_per_km: float | None
    threshold_pace_source: str | None
    threshold_pace_synced_at: str | None

No new third-party dependency is introduced. Python uses `math.isfinite`; web formatting
uses existing TypeScript and React. The workout catalog, plan checkpoint format, and
Intervals HTTP client signatures remain backward compatible.

Revision note (2026-07-29, planning): Created the self-contained implementation plan
after inspecting issue #308 and the current profile, planning, delivery, and UI paths.
The plan fixes canonical units, exact Run selection, field-level provenance, validation
bounds, and the non-mutation guarantee before TDD begins.

Revision note (2026-07-29, implementation): Recorded RED evidence, implemented the
profile-to-delivery vertical, added ASR traceability, documented the floating-point and
repair-gate discoveries, and replaced predicted validation with exact local results.

Revision note (2026-07-29, publication): Recorded ready PR #309, green implementation
CI, and the zero-unresolved-thread audit so this plan no longer depends on conversation
history for its final state.
