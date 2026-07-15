# Build real running and cycling prescriptions in Workout Catalog v2

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept current while the work proceeds. Maintain this document in accordance with `.agent/PLANS.md` from the repository root.

## Purpose / Big Picture

AI Trainer already chooses an appropriate workout stimulus, stores a complete immutable prescription in each planning checkpoint, and delivers those stored steps to Intervals.icu. The v1 catalog, however, represents threshold, VO2, sprint, tempo, and race-specific work as one uninterrupted block followed by one recovery block. That is not an executable interval workout and is especially misleading for running, where a generic percentage can accidentally be interpreted as cycling power.

After this change, every newly built cycling or running checkpoint contains a deterministic ordered prescription that an athlete can execute: warm-up, explicit numbered work/recovery repeats where the stimulus calls for them, and cool-down. Endurance and progression sessions contain purposeful ordered stages rather than fake repeats. Cycling targets resolve to absolute watts from FTP. Running targets resolve to pace from threshold pace, otherwise absolute heart rate from LTHR, otherwise explicit RPE; the provenance and fallback remain stored with the checkpoint. Intervals.icu receives exactly those persisted steps through the existing delivery path.

This change is prospective. Existing checkpoints retain their v1 definition snapshots, step lists, fingerprints, and delivery behavior. No migration rewrites historical prescriptions, and no real active plan is exported during implementation or local acceptance.

## Progress

- [x] (2026-07-15) Read issue #197 and architecture analysis #201, including ASR-PERF-4, ASR-REL-1, and the API-contract risk register.
- [x] (2026-07-15) Audited Workout Catalog v1, checkpoint restore and session identity, brick materialization, proportional recovery rescaling, FIT/TCX fallback, Intervals.icu serialization, the reversible live probe, and the v1/delivery ExecPlans.
- [x] (2026-07-15) Confirmed publish preflight, created isolated worktree `/private/tmp/ai_trainer_issue197` on `codex/issue-197-workout-catalog-v2`, and removed the obsolete blocked label after #198 merged.
- [x] (2026-07-15) Added contract-first tests for repeated structures, target provenance, deterministic simplification, brick reuse, immutable old checkpoints, and ordered Intervals serialization. The clean RED run reported `14 failed, 17 passed` at the intended v2 boundaries.
- [x] (2026-07-15) Implemented the versioned v2 materializer, 20th `bike_race_pace` definition, sport-specific stages/repeat tiers, prospective definition versions, Peak race-pace brick legs, and Intervals `% LTHR` serialization without changing provider ownership, delivery orchestration, selector version, or historical restore.
- [x] (2026-07-15) Completed the final focused contour (`47 passed`), contributor-safe smoke (`687 passed, 1 skipped`), broad non-live (`730 passed, 6 skipped, 24 deselected`), Python compilation, and Next lint/build. The 16-week planner remained inside its four-second regression guard.
- [x] (2026-07-15) With explicit athlete authorization, ran two isolated provider probes on 2026-07-30. Repeated upserts converged on bike event `123028945` and run event `123028946`; Intervals parsed seven ordered power steps and seven ordered HR steps, foreign events stayed byte-equivalent, both probes were deleted, and a bounded read found zero residue.
- [x] (2026-07-15) Addressed the independent review follow-up: clamp repeat bookends so both warm-up and cool-down are literally at least five minutes, and extend the all-definition min/mid/max contract to enforce it. Confirmed separately that the brick allocator only creates bricks in Build or Peak, so no Taper/Race Week race-leg ambiguity is reachable.
- [x] (2026-07-15) Opened draft PR #203 with `Closes #197`; independent review found no blockers and one prose/code bookend nuance, which is fixed and regression-tested before the human merge gate.

## Surprises & Discoveries

- Observation: delivery is already structurally lossless for catalog sessions.
  Evidence: `models.intervals_workout_delivery.build_delivery_events` reads `materialized_steps` from the persisted checkpoint and `build_intervals_workout_description` emits them in list order. The legacy `build_steps_for_sport` path is used only when old checkpoints have no stored steps.

- Observation: run target semantics are already safer than the legacy adapter when a catalog prescription exists.
  Evidence: `_resolve_provenance` prefers `threshold_pace`, then `lthr`, then `relative_rpe`; `_target_for_step` stores absolute pace or bpm dictionaries plus relative bounds. The serializer prints pace as `/km` and LTHR-derived heart rate as `% LTHR`, so neither can be parsed as FTP or max-HR. The ambiguous `% HR` behavior belongs only to the legacy fallback.

- Observation: v1 step-builder keys are shared across sports, so replacing the global pattern table would silently change swim and walk prescriptions.
  Evidence: `swim_threshold_repeats` also uses `step_builder_key="threshold"`, while `walk_recovery` uses `recovery`. V2 must dispatch on both sport and builder and retain the v1 pattern for non-bike/run definitions.

- Observation: Peak bricks currently advertise race pace but materialize both legs from aerobic-endurance definitions.
  Evidence: `materialize_brick_session` always chooses `bike_aerobic_endurance` and `run_aerobic_endurance`, even when the parent is `brick_race_pace`. V2 must choose sport-specific race-pace leg definitions for a Peak brick while leaving the parent/leg persistence contract unchanged.

- Observation: provider ownership and idempotence are independent of step grammar.
  Evidence: Intervals delivery uses `external_id="ai_trainer:<session_id>"`; session identity fingerprints the persisted prescription. A v2 prescription naturally receives a new material identity, while provider UID, cleanup rules, and bounded upsert do not need modification.

- Observation: the explicit v1 checkpoint fixture is preserved even though restore legitimately adds deterministic session identity metadata.
  Evidence: the RED fixture's catalog/materializer versions, definition snapshot, exact old step, and fingerprint round-trip byte-for-byte; only `session_id`, identity rule version, and material fingerprint are appended by the existing restore contract.

- Observation: Intervals.icu accepts `% LTHR` but does not parse absolute `bpm` from workout-builder text as an executable HR target.
  Evidence: the first authorized v2 live probe parsed all seven run lines only as `{duration, text}` when the serializer emitted absolute `bpm`; the bike event parsed as power and both temporary events were removed with zero residue. The current Intervals Workout Builder guide documents `% LTHR`, HR zones, and `% HR`, but not absolute bpm as a supported target. The existing target snapshot already retains both absolute bpm and relative LTHR bounds, so delivery can use the supported relative representation without losing provenance.

- Observation: the corrected `% LTHR` representation is parsed end-to-end by the configured provider account.
  Evidence: the final authorized probe returned seven parsed steps for each sport; the recursive provider evidence contained `power` for the bike and `hr` for the run, a second upsert retained the same provider ids, cleanup deleted exactly two acceptance rows, and foreign rows were unchanged.

- Observation: an independent review found that a ten-minute combined repeat bookend split at 55/45 could leave a 4:30 cool-down despite the plan saying five minutes per side.
  Evidence: `_repeat_specs` originally gated only `remaining >= 10 minutes`. The final implementation clamps warm-up into `[5 minutes, remaining - 5 minutes]`, then assigns the exact remainder to cool-down. The all-definition boundary test now checks both bookends on every structured repeat at feasible min/mid/max durations.

## Decision Log

- Decision: bump the global catalog and materializer rules to `workout_catalog_v2` and `workout_materializer_v2`, but retain `workout_selector_v1`.
  Rationale: #197 changes prescription construction, not the feasibility/ranking algorithm. New checkpoints must advertise the new material grammar without pretending the selector changed. Changed bike/run and brick definitions receive definition version `2`; unchanged swim/walk definitions remain version `1`. A newly introduced bike race-pace definition begins at version `1` inside catalog v2.
  Date/Author: 2026-07-15 / Codex

- Decision: add `bike_race_pace` rather than overloading tempo or the composite parent.
  Rationale: race-specific cycling is a first-class acceptance criterion and is ranked explicitly by Peak/Taper/Race Week selection. Reusing `bike_tempo_sweet_spot` would make stored stimulus, target, and evidence disagree. The catalog therefore grows from 19 to 20 definitions; v1 checkpoint snapshots remain complete and unchanged.
  Date/Author: 2026-07-15 / Codex

- Decision: represent repeats as a flat ordered list of persisted steps with explicit names such as `Threshold 1/3` and `Recovery 1/2`.
  Rationale: this is the smallest structure already understood by checkpoint persistence, session fingerprints, FIT export, web rendering, and Intervals native text. A nested repeat DSL would require new API and exporter contracts without adding athlete value for this slice.
  Date/Author: 2026-07-15 / Codex

- Decision: choose repeat tiers only from total duration and definition, then choose the largest feasible tier in stable declaration order.
  Rationale: identical inputs must yield identical repeat counts and ordering. Tier selection never depends on wall clock, database state, or provider response. If a preferred tier cannot leave at least five minutes each for warm-up and cool-down, the materializer tries the next simpler tier. If no repeat tier is feasible, it emits the definition's explicitly declared simpler continuous prescription with `structure_status="simplified"` and a reason; it never emits zero-duration or meaningless repeats.
  Date/Author: 2026-07-15 / Codex

- Decision: use the following pre-registered repeat families.
  Rationale: the ranges are deliberately conservative, duration-scaled, and express the requested stimulus without inventing athlete-specific physiology that is not in the profile.

  | Prescription | Short | Medium | Long |
  | --- | --- | --- | --- |
  | Bike tempo / sweet spot | 2×8 min, 4 min easy | 3×10 min, 4 min easy | 3×15 min, 5 min easy |
  | Bike threshold | 3×5 min, 3 min easy | 3×8 min, 4 min easy | 4×8 min, 4 min easy |
  | Bike VO2 | 4×2 min, 2 min easy | 5×3 min, 3 min easy | 5×4 min, 4 min easy |
  | Bike neuromuscular | 6×20 sec, 100 sec easy | 8×30 sec, 150 sec easy | 10×30 sec, 150 sec easy |
  | Bike race pace | 2×8 min, 4 min easy | 3×10 min, 4 min easy | 3×15 min, 5 min easy |
  | Run threshold | 3×5 min, 2 min easy | 3×8 min, 3 min easy | 4×8 min, 3 min easy |
  | Run VO2 / economy | 6×30 sec, 90 sec easy | 5×2 min, 2 min easy | 5×3 min, 3 min easy |
  | Run race pace | 2×8 min, 3 min easy | 3×10 min, 4 min easy | 3×15 min, 5 min easy |

  A recovery step exists only between work steps, never after the final repeat. Remaining time is divided deterministically between warm-up and cool-down, with any rounding remainder assigned to cool-down. Exact tier thresholds and fallback evidence are constants covered by tests, not prose-only heuristics.
  Date/Author: 2026-07-15 / Codex

- Decision: endurance and progression use ordered sport-specific stages, not artificial repetitions.
  Rationale: the executable intent is steady durability or a controlled finish. Bike and run endurance use warm-up, aerobic endurance, steady finish, cool-down. Progression uses warm-up, aerobic, moderate, strong finish, cool-down. Recovery stays warm-up, easy recovery, cool-down. Each stage has an explicit target and positive duration.
  Date/Author: 2026-07-15 / Codex

- Decision: preserve the v1 exact-duration and exact-TSS allocator.
  Rationale: seconds are allocated exactly to the requested duration and per-step TSS is allocated to one decimal so the sum equals requested session TSS. This keeps planner load accounting stable. V2 improves execution structure, not the existing TSS model.
  Date/Author: 2026-07-15 / Codex

- Decision: store absolute bpm from LTHR in the immutable catalog target, but serialize its existing relative bounds as `% LTHR` for Intervals.icu; never emit `% HR`/max-HR.
  Rationale: the first live v2 probe disproved the pre-implementation assumption that Intervals parses absolute bpm. `% LTHR` is explicitly supported, preserves the intended threshold scale, and is portable if the athlete profile changes. If threshold pace is absent, provenance remains `athlete_profile.lthr` with absolute bpm plus relative bounds; if both are absent, targets are explicit RPE and `fallback=true` lists the missing inputs.
  Date/Author: 2026-07-15 / Codex

- Decision: Peak race bricks reuse `bike_race_pace` and `run_race_pace`; Build endurance bricks reuse both aerobic-endurance builders.
  Rationale: both legs must be ordinary sport definitions run through the same materializer, with the current ordered leg, transition, load-conservation, and identity contracts unchanged.
  Date/Author: 2026-07-15 / Codex

- Decision: live acceptance will use synthetic one-off definitions and the existing acceptance external-id namespace, never checkpoint 63 or the active plan.
  Rationale: parsing must be verified against the real provider, but implementation acceptance must not deliver or mutate the athlete's plan. Each probe is future-only, upserted twice, checked for ordered parsed steps and expected target type, and deleted in `finally`; a bounded read must prove no residue and foreign events unchanged.
  Date/Author: 2026-07-15 / Codex

## Outcomes & Retrospective

Workout Catalog v2 now produces real ordered cycling and running prescriptions prospectively. The selector remains `workout_selector_v1`; new material is labeled `workout_catalog_v2`, `workout_materializer_v2`, and `workout_structure_v2`. Changed bike/run/brick definitions are version 2, unchanged swim/walk definitions remain version 1, and the new bike race-pace definition begins at version 1. Existing v1 checkpoint fixtures round-trip unchanged apart from the already-established deterministic session-identity metadata.

The contract-first run began at `14 failed, 17 passed`; the final focused contour is `47 passed`. Contributor-safe smoke is `687 passed, 1 skipped`, broad non-live is `730 passed, 6 skipped, 24 deselected`, Python compilation passed, the 16-week planner stayed under its four-second regression guard, and Next lint/build passed. The explicitly authorized live probe corrected one false assumption before publication: Intervals does not parse absolute bpm from workout text, but does parse the same LTHR-relative target as `% LTHR`. Final evidence is seven ordered bike power steps and seven ordered run HR steps, stable provider ids, exact cleanup, and no foreign mutation. Garmin arrival remains outside this issue; Intervals parsing is the provider acceptance boundary.

## Context and Orientation

`models/workout_catalog.py` owns immutable definitions, selection, materialization, brick construction, and proportional rescaling. `models/planning_checkpoints.py` persists the complete returned template dictionaries. Restore reads those snapshots and does not look up current definitions. `models/session_identity.py` fingerprints the materialized prescription, so changed v2 steps produce new session ids only for new builds.

`models/intervals_workout_delivery.py` converts persisted steps to Intervals native text. It maps target dictionaries to watts, supported `% LTHR`, pace per kilometre or 100 metres, and RPE. `models/fit_export.py` contains a legacy generic fallback for checkpoints with no catalog steps; #197 must not rewrite or delete it.

The planning surface is FastAPI plus Next.js. No new endpoint or web component is required because the existing plan/Today responses expose persisted templates and the existing Export action consumes them. The Streamlit fallback is outside scope.

Architecture analysis #201 requires a 16-week plan in under four seconds after PR #202, append-only preservation, and contract safety. The new builder is pure and linear in the small number of emitted steps. Validation must include the existing performance regression and immutable-checkpoint tests.

## Plan of Work

First add a focused `tests/smoke/test_workout_catalog_v2.py` contract. It will assert catalog/materializer/definition versions, explicit numbered bike and run repeats, deterministic order, positive durations, exact duration/TSS sums, pace→LTHR→RPE provenance, short-tier simplification, ordered endurance/progression stages, race-pace selection, and Peak/Build brick leg reuse. Add an Intervals delivery contract that the serialized line order equals persisted step order and that bike lines contain watts while running lines contain `/km`, `% LTHR`, or `RPE` but no bare FTP or max-HR percentage.

Run those tests before production edits and record the expected failures here. Commit the tests separately so TDD order remains inspectable.

The pre-implementation command was:

    python -m pytest tests/smoke/test_workout_catalog_v2.py tests/smoke/test_workout_catalog.py -q

It produced `14 failed, 17 passed` in 0.78 seconds. Failures were the absent v2 versions and definition, absent repeat/stage metadata, absent provenance scale, Peak bricks still using endurance legs, and the two updated v2 assertions in the original catalog contract. The explicit v1 restore and all unrelated v1 behavior passed.

Then evolve `models/workout_catalog.py`. Allow explicit per-definition versions, add `bike_race_pace`, keep the selector algorithm, and introduce a small internal step-spec representation plus deterministic builders for flat stages and repeat tiers. Dispatch v2 only for bike/run definitions; retain `_STEP_PATTERNS` as the non-bike/run v1 compatibility path. Attach `structure_status`, selected tier, repeat evidence, and target-scale provenance to the materialization result and persisted template without adding a database migration.

Update Peak brick leg choice while retaining Build endurance legs. Keep rescaling proportional and snapshot-only so an approved recovery proposal never reselects a stimulus or rewrites history.

Finally update affected v1 assertions to the prospective v2 contract, run focused and full validation, inspect the diff for accidental API/UI/provider changes, and update this living document. Publish a draft PR only after local gates pass. Real provider probes remain a separate explicit authorization gate.

## Concrete Steps

Run commands from `/private/tmp/ai_trainer_issue197` with the project environment active:

    source /Users/gregkisel/Developer/ai_trainer/ai_trainer_env/bin/activate
    python -m pytest tests/smoke/test_workout_catalog_v2.py -q
    python -m pytest tests/smoke/test_workout_catalog.py tests/smoke/test_intervals_plan_delivery.py tests/smoke/test_fit_export_session_templates.py -q

After implementation:

    python -m compileall models api services data
    python -m pytest tests/smoke/test_workout_catalog_v2.py tests/smoke/test_workout_catalog.py tests/smoke/test_intervals_plan_delivery.py tests/smoke/test_fit_export_session_templates.py tests/smoke/test_race_microcycles.py tests/smoke/test_api_planning.py -q
    python -m pytest tests/smoke -q
    python -m pytest -m "not live and not debug" tests/ -q
    cd web && npm run lint && npm run build

If and only if the athlete explicitly authorizes real Intervals.icu writes, run the dedicated v2 acceptance with a future date outside the active delivery window. The command and confirmation phrase will be added test-first to the acceptance runner; it must create and delete exactly two synthetic events, one bike and one run, and print only sanitized evidence.

## Validation and Acceptance

Focused tests are green when every changed cycling/running stimulus has the pre-registered structure, repeated calls are byte-for-byte equal, every duration is positive, and sums are exact. A short feasible request either chooses a valid short repeat tier or explicitly reports a simpler continuous structure; an infeasible request still returns no steps and the existing failed bounds.

Persistence acceptance is green when a newly built template advertises catalog/materializer v2 and changed definition version 2, while restoring a fixture saved with v1 snapshots returns exactly those v1 dictionaries. A material change creates a different fingerprint/session identity; a plain restore does not.

Delivery acceptance is green when the native text line sequence matches the persisted step names. Cycling work steps use absolute watts. Running with threshold pace uses `/km`; without pace but with LTHR it uses `% LTHR`; without either it uses `RPE`. No new catalog running event contains a bare FTP or `% HR` max-heart-rate target.

Brick acceptance is green when Build legs use bike/run endurance definitions and Peak legs use bike/run race-pace definitions, ordered bike then run, while parent TSS, sport buckets, transition, leg ids, and fingerprint rules remain conserved.

Full smoke and broad non-live suites, compileall, Next lint/build, and the 16-week planning performance regression must remain green. Live acceptance, if authorized, additionally requires provider-parsed ordered steps, correct target type for both sports, repeated-upsert identity, unchanged foreign events, exact cleanup, and zero residual acceptance rows.

## Idempotence and Recovery

All catalog functions are pure and deterministic. Re-running a build with the same inputs yields the same definitions, steps, TSS, provenance, and fingerprint. Existing checkpoint rows are never updated. If implementation fails, discard only the issue worktree/branch; the main worktree and local `ai_trainer.db` are untouched.

The live probe is fail closed. It performs no provider write without the exact confirmation, refuses today/past or distant dates, refuses pre-existing acceptance rows, upserts only acceptance-prefixed external ids, and deletes only the exact returned ids in `finally`. If cleanup cannot prove zero residue, stop and report the provider ids instead of attempting broad deletion.

## Artifacts and Notes

Expected examples after implementation:

    - Warm-up 10m 87-103w
    - Threshold 1/3 8m 154-164w
    - Recovery 1/2 4m 67-92w
    - Threshold 2/3 8m 154-164w

and for a run with threshold pace:

    - Warm-up 8m 6:20-7:10/km
    - VO2 1/5 3m 4:40-4:55/km
    - Recovery 1/4 3m 6:30-7:20/km

Exact values depend on the frozen athlete zone snapshot. These examples are illustrative; tests assert formulas, types, ordering, and invariants rather than personal production values.

## Interfaces and Dependencies

No new third-party dependency and no database migration are planned.

`WorkoutTemplateDefinition` remains the public immutable definition type. `_definition` gains an internal `version` argument. Public functions keep their current signatures:

    catalog_definitions() -> tuple[WorkoutTemplateDefinition, ...]
    select_workout_template(context: Mapping[str, Any]) -> dict[str, Any]
    materialize_workout(definition, parameters, zone_snapshot) -> dict[str, Any]
    materialize_session_template(...) -> dict[str, Any]
    materialize_brick_session(...) -> dict[str, Any]
    rescale_materialized_session(template, *, target_tss, parts) -> dict[str, Any]

`materialize_workout` adds inspectable fields without removing existing ones:

    structure_status: "structured" | "simplified" | "legacy_pattern"
    structure_evidence: {
        rule_version: "workout_structure_v2",
        prescription_key: str,
        tier: str | None,
        repeat_count: int | None,
        simplification_reason: str | None,
    }

Each persisted step retains the current keys `index`, `name`, `intensity`, `duration_seconds`, `tss`, and `target`. Optional `segment_kind` and `repeat_index` metadata may be added because current API and exporters preserve or ignore unknown fields. Target dictionaries retain current serializer-compatible shapes.

Revision note (2026-07-15, Codex): initial pre-implementation contract after full source, architecture, v1 catalog, delivery, and live-probe audit. It freezes the prospective-only version boundary, flat repeat representation, sport-specific target scales, explicit simplification behavior, and safe live gate before TDD begins.
