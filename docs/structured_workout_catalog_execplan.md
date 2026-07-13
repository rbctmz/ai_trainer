# Replace generic workout roles with a versioned stimulus catalog and composite bricks

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept current as implementation proceeds. Maintain this document according to `.agent/PLANS.md` from the repository root.

## Purpose / Big Picture

After this change, a plan no longer says only “quality bike” or “long run” and then exports the same generic three or four steps for every phase. Each planned workout names a deterministic training stimulus such as aerobic progression, threshold intervals, neuromuscular sprints, technique swim, or race pace; shows why it was selected; stores an immutable versioned prescription with exact step durations and relative targets; and exports those same steps. A triathlon Build or Peak week can contain one real bike-to-run brick represented as one parent session with two ordered legs. Planning and Today show the stimulus, fatigue cost and step preview, while old checkpoints keep rendering the prescription that was originally stored.

The observable acceptance is a synthetic Olympic-triathlon plan containing different Base and Build bike-quality prescriptions, a Build endurance brick with two exportable legs, and checkpoint restore returning byte-equivalent prescription snapshots. Running the web stack and opening Planning’s Export tab must show the template names and step summaries rather than only generic sport labels.

## Progress

- [x] (2026-07-13 11:10Z) Merged prerequisite PR #177, closed issue #172 and synchronized `main` at `38a58bf`.
- [x] (2026-07-13 11:16Z) Created isolated branch `codex/issue-173-structured-catalog` in `/private/tmp/ai_trainer_issue173` from the merged `main`.
- [x] (2026-07-13 11:21Z) Audited the role-only template builder, FIT/TCX exporters, checkpoint serializer, session identity, manual/recovery edits, readiness gate, Today API and Planning web surface.
- [x] (2026-07-13 11:21Z) Pre-registered the catalog bounds, phase matrix, selector precedence, target fallback rules, brick allocation and exporter contract in this plan before tests or implementation.
- [x] (2026-07-13 14:58Z) Added red-first BDD/contract coverage for the catalog, selector, materializer, SQLite checkpoint history, brick/recovery atomics, exporters, Planning API and Today projection.
- [x] (2026-07-13 11:41Z) Implemented the immutable 19-definition catalog, deterministic selector/materializer and conservative weekly brick allocator as a headless Python domain; 8 new BDD tests and 10 existing planner tests pass.
- [x] (2026-07-13 12:03Z) Integrated catalog snapshots, prescription-aware identity, athlete FTP/LTHR provenance and one conservative brick per eligible balanced triathlon week into initial plan generation and checkpoint persistence.
- [x] (2026-07-13 12:34Z) Refresh/rescale immutable prescriptions through manual/recovery edits and weekly rebalances, including exact composite-leg scaling, replacement identity and execution-plan rebuilds.
- [x] (2026-07-13 12:17Z) Migrated FIT-CSV, workout TCX and activity TCX to persisted seconds and honest targets; composite export requires an explicit leg and never reconstructs parent steps.
- [x] (2026-07-13 15:12Z) Exposed compact prescriptions in Planning and Today, including stimulus/fatigue/step evidence, one composite card and separate leg exports; Next.js production build passes.
- [x] (2026-07-13 15:23Z) Completed focused and synthetic UI acceptance, `555 passed, 1 skipped` smoke, `598 passed, 6 skipped, 24 deselected` broader non-live, and a clean 12-route Next.js production build.
- [x] (2026-07-13 15:23Z) Self-reviewed the complete diff, closed the Taper-long and Today-data-gap edges found in acceptance, and finalized this living plan.
- [ ] Publish a draft PR with `Closes #173` and leave merge to the human gate.

## Surprises & Discoveries

- Observation: the current daily sport parts are allocation buckets, not session boundaries; every sample day in Base, Build, Peak, Taper, Recovery and Maintenance contains non-zero bike, run and swim values.
  Evidence: `expand_weekly_to_daily_triathlon([180], [phase], ...)` produced seven three-sport rows for every tested phase, while `build_daily_session_templates` chose only `_dominant_sport(parts)`. A brick therefore cannot be inferred merely from “bike and run are non-zero.”

- Observation: the exporter accepts `phase` but deliberately discards it, and all quality sessions use the same `Warmup / Main Intervals / Reset / Cooldown` blueprint.
  Evidence: `models/fit_export.py::build_steps_for_sport` begins with `del phase` and delegates only to `_build_role_blueprint(session_role)`.

- Observation: both existing exporters reconstruct duration from `step.tss * 60`; FIT-CSV always writes heart-rate target type and TCX always writes heart-rate zone 2, even for bike power and swim pace targets.
  Evidence: `generate_fit_csv` hard-codes `target_type,1`; `generate_tcx_workout` emits `<Target xsi:type="HeartRateZone_t"><ZoneNumber>2</ZoneNumber>` for every step.

- Observation: complete `session_templates` are already inside each checkpoint’s `goal_plan_snapshot`, so immutable prescription history needs no new database table.
  Evidence: `models/planning_checkpoints.py::build_planning_checkpoint` serializes the entire list and restore returns it without rebuilding when daily details exist.

- Observation: RecoveryReplan applies through the general near-term editor. Composite atomics therefore belong in the shared materialization/edit path rather than a special API-only branch.
  Evidence: `api/planning_service.py::apply_recovery_replan` calls `apply_near_term_day_edits` with a deterministic draft.

- Observation: the persisted athlete profile currently contains FTP and LTHR but no threshold run pace or critical swim speed.
  Evidence: the `athlete_profile` schema and `Database.get_athlete_profile` expose only `ftp`, `weight_kg`, `lthr`, source and timestamp. Run and swim prescriptions need explicit relative/RPE fallback provenance until those zones exist.

- Observation: a phase preference cannot rank on the human-readable `stimulus` explanation because it is deliberately descriptive rather than an enum.
  Evidence: the first selector test chose neuromuscular work instead of aerobic progression when the rank map compared `progression` to `progressive aerobic durability`. Selection now ranks the stable `step_builder_key` while preserving the richer stimulus text as product evidence.

- Observation: the shared API planning fixture represents a genuinely deep-fatigued athlete, so expecting bricks from it would violate the pre-registered fatigue guard.
  Evidence: its active plan reported `load_state=deep_fatigue` and `brick_allocation.reason=deep_fatigue`; the same deterministic build on a clean balanced profile allocated exactly one brick in each Build week and preserved all sport totals.

- Observation: the legacy FIT/TCX duration heuristic can accidentally equal a materialized duration for one step, so duration-only assertions do not prove that persisted prescriptions are used.
  Evidence: the red exporter test's first duration matched while FIT still emitted `target_type=heart_rate`; target semantics and explicit composite-leg selection are required companion assertions.

- Observation: persisted target provenance is sufficient to rebuild prescriptions without a live database profile.
  Evidence: execution feedback rebuilds operate as pure plan transforms with no `Database`; `extract_zone_snapshot` recovers only non-fallback FTP/LTHR/pace/CSS values from immutable prior templates and never invents missing zones.

- Observation: a durable coach constraint can turn a materialized brick into a rest day after catalog generation.
  Evidence: the constraint layer runs after initial templates; it now removes definition/steps/legs/fingerprint and marks `constraint_off`, so a hidden prescription cannot survive behind zero TSS.

- Observation: the legacy phase scheduler can retain the role `long` in Taper, leaving no eligible short catalog candidate even though the phase contract requires sharpening.
  Evidence: adversarial acceptance with a 120-minute Taper bike request initially returned infeasible. The selector now records `role_override=long_to_sharpening`, admits only eligible quality/easy definitions, and caps the materialized duration at 60 minutes.

- Observation: the readiness gate deliberately evaluates no sessions when recovery confidence is below threshold, so Today cannot rely on `sessions_evaluated` as its only plan projection.
  Evidence: synthetic browser acceptance showed `state=data_gap` and “Плановой сессии нет” despite an active checkpoint session on 2026-07-13. Today now falls back to the immutable checkpoint template for the same `as_of` date while retaining the data-gap verdict and no proposal.

## Decision Log

- Decision: add `models/workout_catalog.py` with frozen dataclasses for definitions and pure functions that return JSON-serializable dictionaries. Use `workout_catalog_v1`, `workout_selector_v1` and `workout_materializer_v1` as independent rule versions.
  Rationale: immutable code definitions prevent runtime mutation, separate version fields show which rule changed, and plain serialized snapshots fit existing checkpoints and APIs without a new dependency or table.
  Date/Author: 2026-07-13 / Codex.

- Decision: the catalog contains exactly the 19 keys named by issue #173 and no aliases. Each definition stores display name, kind, sport, role set, stimulus, phase eligibility, goal eligibility, duration/TSS/density bounds, fatigue vector, recovery hours, target preference, requirements, contraindications and a pure step-builder key.
  Rationale: a bounded first library is inspectable and testable. Aliases and a marketplace would hide whether the required taxonomy really exists.
  Date/Author: 2026-07-13 / Codex.

- Decision: use the following pre-registered bounds. Duration is minutes; load density is TSS per hour. A request must satisfy duration, absolute TSS and density bounds or return `materialization_status=infeasible` with every failed bound; no target is stretched silently.
  Rationale: duration is primary in a workout prescription, while both absolute load and density catch nonsensical combinations. The ranges are deliberately broad enough for current amateur plans but still rule out impossible prescriptions.
  Date/Author: 2026-07-13 / Codex.

  - `bike_recovery_spin`: 20–75 min, 5–45 TSS, 15–45 TSS/h, fatigue `(1,0,0)`, recovery 8 h.
  - `bike_aerobic_endurance`: 40–240 min, 20–180 TSS, 35–75 TSS/h, fatigue `(1,1,0)`, recovery 18 h.
  - `bike_aerobic_progression`: 45–180 min, 25–160 TSS, 45–85 TSS/h, fatigue `(2,1,0)`, recovery 24 h.
  - `bike_tempo_sweet_spot`: 45–150 min, 35–180 TSS, 60–95 TSS/h, fatigue `(2,1,1)`, recovery 30 h.
  - `bike_threshold_intervals`: 40–120 min, 35–160 TSS, 70–110 TSS/h, fatigue `(3,1,1)`, recovery 36 h.
  - `bike_vo2max_intervals`: 35–90 min, 30–125 TSS, 75–120 TSS/h, fatigue `(3,1,2)`, recovery 42 h.
  - `bike_neuromuscular_sprints`: 30–75 min, 20–85 TSS, 40–90 TSS/h, fatigue `(1,1,3)`, recovery 30 h.
  - `run_recovery`: 20–60 min, 8–55 TSS, 20–65 TSS/h, fatigue `(1,1,0)`, recovery 12 h.
  - `run_aerobic_endurance`: 30–150 min, 20–150 TSS, 35–80 TSS/h, fatigue `(1,2,0)`, recovery 24 h.
  - `run_progression`: 35–120 min, 25–130 TSS, 45–90 TSS/h, fatigue `(2,2,0)`, recovery 30 h.
  - `run_tempo_threshold`: 35–100 min, 30–125 TSS, 55–105 TSS/h, fatigue `(3,2,1)`, recovery 42 h.
  - `run_vo2_neuromuscular`: 30–75 min, 25–95 TSS, 60–115 TSS/h, fatigue `(3,2,3)`, recovery 48 h.
  - `run_race_pace`: 30–100 min, 30–120 TSS, 55–105 TSS/h, fatigue `(2,2,1)`, recovery 36 h.
  - `swim_technique_aerobic`: 25–75 min, 10–65 TSS, 20–60 TSS/h, fatigue `(1,0,1)`, recovery 12 h.
  - `swim_endurance`: 35–120 min, 20–110 TSS, 30–75 TSS/h, fatigue `(1,1,0)`, recovery 18 h.
  - `swim_threshold_repeats`: 35–90 min, 25–100 TSS, 45–95 TSS/h, fatigue `(2,1,1)`, recovery 30 h.
  - `walk_recovery`: 20–120 min, 3–40 TSS, 8–30 TSS/h, fatigue `(0,1,0)`, recovery 6 h.
  - `brick_endurance`: 60–240 min, 40–220 TSS, 35–85 TSS/h, fatigue `(2,2,1)`, recovery 36 h.
  - `brick_race_pace`: 50–150 min, 45–180 TSS, 50–110 TSS/h, fatigue `(3,2,2)`, recovery 48 h.

- Decision: fatigue vectors are ordered `(metabolic, musculoskeletal, neuromuscular)` on the issue’s 0–3 scale. They are evidence and guardrail inputs, not a new readiness score. The selector excludes any definition with a cost of 3 when `load_state=deep_fatigue` and excludes threshold, VO2max, race-pace and both bricks in Recovery phase.
  Rationale: reusing the existing load state avoids inventing a second recovery model. A vector remains explainable and can later feed Issue D or recovery curves.
  Date/Author: 2026-07-13 / Codex.

- Decision: phase eligibility is data on each definition. Recovery allows recovery, technique, walk and easy aerobic only. Base and Maintenance allow recovery, aerobic endurance, progression, technique and small neuromuscular doses. Build adds tempo, threshold, bounded VO2max, swim repeats and `brick_endurance`. Peak prefers threshold/race pace and permits `brick_race_pace`. Taper and Race Week allow recovery/aerobic plus a `sharpening` parameter variant of neuromuscular, VO2, threshold, swim repeats or run race pace capped at 60 minutes and 60 TSS. Race event templates remain authoritative and are never replaced by the catalog.
  Rationale: this encodes the issue’s precedence without UI conditionals and prevents the original “Peak simply means more load” error from reappearing at workout level.
  Date/Author: 2026-07-13 / Codex.

- Decision: Stage A receives only normalized goal, distance, planning intent/focus, phase, role, sport allocation, duration/TSS, load state, protection flags, athlete capabilities and recent stimulus keys. It filters hard constraints, then selects from a versioned phase/role preference list. Equal-ranked candidates rotate by stable session date ordinal; a high-intensity stimulus present in the preceding seven days is skipped when an eligible alternative exists. Selection evidence records filtered reasons and whether the recent-exposure guard fired.
  Rationale: deterministic rotation supplies variety without randomness or an LLM, while a bounded exposure guard avoids repeatedly selecting VO2/threshold on adjacent quality days.
  Date/Author: 2026-07-13 / Codex.

- Decision: recent exposure comes first from catalog snapshots selected earlier in the same new plan and then from the active checkpoint’s catalog sessions dated before the new plan start. Unknown legacy sessions and raw activities do not receive invented stimuli.
  Rationale: the system can use honest persisted evidence immediately and later enrich it through #172 matches and #175 feedback. Copying a planned role onto an activity would repeat the adherence error fixed in #172.
  Date/Author: 2026-07-13 / Codex.

- Decision: Stage B materializes exact integer seconds whose sum equals the requested duration within zero seconds, not merely the issue tolerance of 60 seconds. It distributes requested TSS across steps and corrects the final step so estimated TSS equals the feasible target within 0.1. Each step stores ordinal, semantic name, duration, intensity kind, relative lower/upper target and unit, flags, optional cadence, estimated TSS, target provenance and all rule versions.
  Rationale: exact conservation is simpler to reason about than accumulating rounding error, and one canonical step list can feed all exporters.
  Date/Author: 2026-07-13 / Codex.

- Decision: target preference is bike `%FTP`, run `%threshold pace` then `%LTHR`, swim `%CSS pace`, and walk/RPE. With a matching zone snapshot, materialization stores absolute lower/upper values and `target_source` such as `ftp:intervals_icu`. Without it, relative bounds remain valid, absolute values are null, and `target_source=relative_only_fallback` or `rpe_fallback`; it never invents watts, pace or HR.
  Rationale: the current athlete profile can support honest bike power and run HR today, while explicit fallback preserves usability without false precision.
  Date/Author: 2026-07-13 / Codex.

- Decision: persist `catalog_definition_snapshot`, `template_key`, `template_version`, `stimulus`, `fatigue_cost`, `expected_recovery_hours`, `selection_evidence`, `parameter_snapshot`, `materialized_steps`, `prescription_fingerprint` and rule versions inside each session template. Extend session identity’s material signature with `prescription_fingerprint`.
  Rationale: old checkpoints already persist templates. A full snapshot prevents later catalog code from retroactively changing history, and prescription changes become material session replacements with #172 lineage.
  Date/Author: 2026-07-13 / Codex.

- Decision: a Build or Peak triathlon week may contain at most one automatic brick, on its unprotected `long` day, only when the request is feasible. Build chooses `brick_endurance`; Peak chooses `brick_race_pace`; Recovery/Taper/Race Week and deep fatigue choose none. This rule does not infer bricks from the legacy fact that all sport buckets are non-zero.
  Rationale: one deliberate weekly slot is comprehensible and avoids turning every mixed allocation bucket into a composite workout.
  Date/Author: 2026-07-13 / Codex.

- Decision: before catalog selection, the brick allocator converts the chosen parent day to bike+run only while preserving every day’s total, the week’s total and the week’s bike/run/swim totals. It moves the parent’s swim allocation to unprotected easy/recovery donor days by replacing proportional bike/run amounts there. If donors cannot conserve all three sport totals within 0.1 TSS, no brick is created and evidence says `brick_allocation_infeasible`.
  Rationale: the compatibility `daily_plan` must truthfully equal the two brick legs, but silently dropping swim or changing weekly sport mix would corrupt the plan.
  Date/Author: 2026-07-13 / Codex.

- Decision: a brick parent stores `kind=composite`, `sport=brick`, a 5-minute transition, and two ordered leg snapshots. Bike receives its exact parent bike TSS and 70 percent of non-transition duration; run receives exact run TSS and the remaining duration. After parent `session_id` generation, stable leg IDs are `<parent>:1` and `<parent>:2`. Parent TSS is exactly the sum of leg TSS; transition adds time but no TSS.
  Rationale: parent and leg identities match the #173 contract and future #168 external IDs without counting load twice.
  Date/Author: 2026-07-13 / Codex.

- Decision: the existing export endpoint gains optional `leg` ordinal. Single sessions ignore an absent leg. Composite sessions require `leg=1` or `leg=2` and otherwise return a clear 422; Planning renders separate TCX/FIT-CSV links for both legs. ICS remains one parent calendar event describing both legs.
  Rationale: this is backward compatible for single sessions and avoids inventing an archive format just to return two artifacts through one HTTP response.
  Date/Author: 2026-07-13 / Codex.

- Decision: FIT-CSV and TCX consume persisted `duration_seconds` and target metadata. FIT uses power target type and absolute watts when FTP exists, HR target when LTHR is the resolved run source, and open/RPE when no supported absolute target exists. TCX emits supported HR targets directly; for power or pace it emits an open target plus explicit target evidence in the step name/extension rather than lying with HR zone 2. Both formats preserve exact step duration.
  Rationale: TCX workout target support is narrower than the domain model. An explicit open target with provenance is safer than producing schema-looking but false power data.
  Date/Author: 2026-07-13 / Codex.

- Decision: all plan mutation paths call one catalog refresh/rescale helper. A changed manual single session is reselected and its preview reports old/new template. A composite reduction preserves both ordered legs and scales them proportionally; it never removes, reorders or changes only one leg. Protected parents make all legs immutable.
  Rationale: RecoveryReplan, manual edits and weekly rebalance already share headless plan mutation paths. Central refresh avoids stale steps and meets atomic brick behavior without UI-specific logic.
  Date/Author: 2026-07-13 / Codex.

- Decision: when the recovery report contains no evaluated sessions, Today projects the session dated `as_of` from the restored active checkpoint; an `off` template still projects as rest. Gate state, readiness confidence and proposal behavior remain unchanged.
  Rationale: data availability governs whether the agent may intervene, not whether the user may see an already persisted plan. This keeps one immutable prescription visible without manufacturing a gate evaluation.
  Date/Author: 2026-07-13 / Codex.

## Outcomes & Retrospective

Issue #173 is implemented end to end. The bounded catalog contains exactly 19 immutable definitions, produces deterministic phase-aware prescriptions, persists complete snapshots, conserves composite brick load, survives every supported replan path, and serializes persisted seconds and honest targets through FIT/TCX. Planning and Today consume the same compact API truth; React performs no selection or zone math.

Synthetic acceptance built a balanced eight-week Olympic-triathlon plan with two Build bricks. Planning displayed each as one `Endurance Brick · вело → бег` parent with bike then run legs and distinct `leg=1` / `leg=2` TCX/FIT links. Today displayed `Aerobic Endurance Ride`, its stimulus, fatigue/recovery evidence and Warm-up/Aerobic/Cool-down steps even under `data_gap`. Browser console errors were empty. Sanitized captures are stored outside the repository at `/private/tmp/ai_trainer_issue173_planning_catalog.png` and `/private/tmp/ai_trainer_issue173_today_catalog.png`.

Final validation: 25 focused catalog/Today tests passed; contributor-safe smoke produced `555 passed, 1 skipped`; broader non-live produced `598 passed, 6 skipped, 24 deselected`; Next.js 14.2.35 compiled, type-checked and generated all 12 routes. The sole smoke skip is the environment-dependent local listening-socket preflight. No real athlete database, provider mutation or new third-party dependency entered the branch.

## Context and Orientation

`models/training_planner.py` creates weekly phase/load structure, expands it into `daily_plan`, and builds one aligned dictionary in `session_templates` per day. `daily_plan` is a list of `(datetime, total_tss, parts)` tuples, where `parts` has bike/run/swim TSS. Today, `build_daily_session_templates` chooses only the dominant part and writes a generic `phase:role:sport` key.

`api/planning_service.py::build_plan` orchestrates plan creation, event overlays, coach constraints, session identity and checkpoint persistence. It has access to `Database`, the current athlete profile and the previous checkpoint, so it is the correct composition boundary for zone snapshots and recent catalog history. New business rules remain in `models/`; API code only supplies inputs and projects output.

`models/session_identity.py` assigns deterministic `ats_<hash>` IDs from a material signature and preserves replacement lineage. The prescription fingerprint must join that signature so different steps cannot share an old identity.

`models/planning_checkpoints.py` serializes the whole goal plan, including session templates, into SQLite JSON. A “catalog definition snapshot” means the complete immutable definition and materialized prescription stored in that template. Restore must use this stored object, not look up the current catalog by key.

`models/fit_export.py` creates generic step dictionaries and FIT-CSV. `models/tcx_export.py` creates TCX workouts. “Materialized steps” are the exact versioned steps already stored in a session template; exporters become serializers of those steps rather than planners.

`models/planning_near_term.py` is the shared headless editor used by manual edits and RecoveryReplan. `models/plan_actual_reconciliation.py` applies future-only weekly reductions. Both must refresh a single prescription or atomically rescale a brick after load changes.

`models/readiness_conflicts.py::upcoming_plan_sessions` projects session templates into the readiness gate. `api/routers/today.py` then projects today’s evaluated session. Adding catalog fields to this existing path exposes the same persisted truth without a second lookup.

`web/app/planning/page.tsx` renders plan build/adjust/export surfaces. `web/app/today/page.tsx` renders the daily session. TypeScript contracts in `web/lib/types.ts` must mirror the backend; no selector or target math belongs in React.

## Plan of Work

Milestone 1 creates the domain and proves it independently. Add `models/workout_catalog.py` containing the frozen definitions, catalog validator, selector, materializer, brick allocator, prescription rescaler and helpers to attach parent/leg identity. Add `tests/smoke/test_workout_catalog.py` first. Tests enumerate exactly 19 unique definitions, prove all bounds/matrices are valid, show Base and Build bike quality select different stimuli, exclude hard work in Recovery/deep fatigue, prove deterministic byte-equivalent steps, verify explicit infeasible/fallback results and conserve load during brick allocation.

Milestone 2 integrates immutable prescriptions. Extend `build_daily_session_templates` to accept a versioned catalog context, prepared brick dates, athlete zone snapshot and recent stimuli. In `api/planning_service.py`, build the zone snapshot from the latest athlete profile, collect only honest prior catalog stimuli, run brick allocation after event overlays, then select/materialize chronologically. Persist the zone snapshot and catalog versions at plan root. Extend `models/session_identity.py` with prescription fingerprint and attach leg IDs after parent IDs exist. Extend `_build_plan_preview` and public plan rows with template changes and catalog summaries. Checkpoint round-trip tests must prove byte identity even if the active catalog object is monkeypatched after save.

Milestone 3 makes edits safe. Add a shared catalog refresh function to manual near-term and weekly-rebalance mutations. Extend editable sport normalization to preserve `brick` for an existing composite parent. Manual changes to sport/role reselect a single template and report old/new keys; TSS-only brick changes rescale both legs, duration and step TSS proportionally. RecoveryReplan remains suggestion-only but its confirmed downgrade is atomic. Event/coach protected parents never reach the rescaler. Tests cover replacement lineage, both-leg scaling and append-only checkpoint restore.

Milestone 4 migrates export and product contracts. Deprecate planning-time use of `build_steps_for_sport` but keep it as a legacy adapter for old checkpoints. Make FIT/TCX/activity exporters prefer persisted durations and target provenance. Add optional `leg` query to the existing export route and render two leg links for composites. Add template display name, stimulus, fatigue vector, selection evidence and compact steps to Planning export rows and Today’s session card. Tests assert bike FTP power encoding, honest run/swim fallback, duration/TSS tolerances, composite 422 without a leg and distinct stable leg files.

Milestone 5 validates observable behavior. Create a sanitized synthetic plan spanning Base, Build, Peak, Taper and Recovery, plus a high-load Build week that generates one brick. Restore it through SQLite, export both legs and compare totals/IDs/steps. Run focused suites, all contributor-safe smoke tests, broader non-live tests, TypeScript/Next build and `git diff --check`. Start the web stack if environment ports permit and capture Planning and Today screenshots for the PR. Finalize this plan with exact evidence, self-review all acceptance criteria, push and open a PR with `Closes #173`.

## Concrete Steps

Work only in `/private/tmp/ai_trainer_issue173` on branch `codex/issue-173-structured-catalog`.

Create the ExecPlan commit before implementation, then add failing BDD tests:

    source /Users/gregkisel/Developer/ai_trainer/ai_trainer_env/bin/activate
    python -m pytest tests/smoke/test_workout_catalog.py -q

Expected red evidence is an import failure for `models.workout_catalog` or missing public functions. Implement the pure domain until that suite passes, then integrate incrementally with:

    python -m pytest tests/smoke/test_workout_catalog.py tests/smoke/test_fit_export_session_templates.py tests/smoke/test_planning_checkpoint_history.py tests/smoke/test_api_planning.py tests/smoke/test_recovery_replan_loop.py -q

Before publication run:

    python -m pytest tests/smoke -q
    python -m pytest -m "not live and not debug" tests/ -q
    cd web && npm run build
    git diff --check

The production build may reuse the main worktree’s installed `web/node_modules` through a temporary symlink, which must be removed afterward. Never copy `.env`, the real SQLite database or personal workout payloads into the branch.

## Validation and Acceptance

Catalog acceptance passes when code exposes exactly 19 unique versioned definitions with every required schema field, all phase references are known, all bounds are ordered, and all fatigue components are integers 0–3. A test comparing Base and Build bike quality at equal duration/TSS must produce different template/stimulus/steps.

Safety acceptance passes when Recovery phase and deep fatigue never select threshold, VO2max, race pace or a quality brick; protected race/coach dates remain byte-equivalent; recent hard-stimulus exposure selects an eligible lower-cost alternative and records the guard activation; infeasible duration/load returns explicit reasons and no steps.

Materialization acceptance passes when repeated normalized inputs produce byte-equivalent JSON, exact step seconds sum to requested seconds, estimated step TSS sums within 0.1, and target source is honest. An FTP-backed threshold bike must expose relative percent FTP plus absolute watts. Missing FTP, threshold pace, LTHR or CSS must have null absolute targets and an explicit relative/RPE fallback.

Brick acceptance passes when one Build long day becomes `brick_endurance`, parent compatibility parts contain only bike and run, parent and weekly totals are counted once, original weekly bike/run/swim totals are preserved within 0.1, leg order is bike then run, leg IDs derive from parent ID, and both leg exports use their own steps. A RecoveryReplan reduction must change both legs proportionally and preserve order; a protected brick must not change.

History acceptance passes when a checkpoint round-trip returns the complete catalog definition snapshot and materialized prescription byte-for-byte. Replacing the in-process catalog definition after saving must not affect restored output. A material prescription change must generate a new parent session ID with `replaces_session_id` pointing to the previous one.

Product acceptance passes when `/api/planning/plan` exposes catalog fields and leg summaries, `/api/today` exposes the same template name/stimulus/fatigue/steps for today, Planning renders one brick card with bike → transition → run and separate leg export links, and no frontend code selects a stimulus or calculates zones.

Exporter acceptance passes when all exporters use persisted seconds. FIT-CSV represents FTP-backed bike work as power rather than heart-rate zone. TCX never silently converts unsupported power/pace targets to HR zone 2; its explicit open target and evidence are visible. Existing legacy checkpoints without materialized steps still export through the old adapter and are labelled `legacy_role_fallback`.

## Idempotence and Recovery

Catalog definitions are constants and selection/materialization are pure, so repeated runs cannot mutate state. Preview remains read-only. A confirmed plan or edit appends one checkpoint through existing persistence; no migration rewrites old checkpoints. If a plan build fails materialization, it returns validation evidence and does not save a partial checkpoint.

Brick allocation works on deep copies and commits only if all row totals and weekly sport totals reconcile within 0.1. Otherwise it returns the original plan and a reason. Export is read-only. No Intervals POST/PUT/DELETE is added; provider delivery remains #168.

If publication fails, the branch and commits remain in the isolated worktree. Retry only push/PR creation after verifying `git status`, remote tracking and actual GitHub state. Never commit from the main worktree.

## Artifacts and Notes

Issue: `https://github.com/rbctmz/ai_trainer/issues/173`.

Prerequisite merge: PR #177 at `38a58bf22a7e9e1386708ec5c0f00010a4054e77`.

The independent IntervalCoach evidence in #173 is design input only. No copied workout text, personal payload or external mutation belongs in this implementation.

The first source-audit transcript showed why the compatibility bridge is necessary:

    Build 180 TSS, long day 2026-07-18:
      total=35.5, parts={run: 14.4, bike: 15.0, swim: 6.1}
      current template sport=bike (dominant only)

The new brick allocator must either conserve that 6.1 swim TSS elsewhere in the same week or refuse the brick; it may not hide it.

## Interfaces and Dependencies

In `models/workout_catalog.py`, expose immutable domain interfaces resembling:

    CATALOG_VERSION = "workout_catalog_v1"
    SELECTOR_RULE_VERSION = "workout_selector_v1"
    MATERIALIZER_RULE_VERSION = "workout_materializer_v1"

    @dataclass(frozen=True)
    class WorkoutTemplateDefinition:
        template_key: str
        version: int
        display_name: str
        kind: str
        sport: str
        roles: tuple[str, ...]
        stimulus: str
        phase_eligibility: tuple[str, ...]
        goal_eligibility: tuple[str, ...]
        min_duration_minutes: int
        max_duration_minutes: int
        min_tss: float
        max_tss: float
        min_tss_per_hour: float
        max_tss_per_hour: float
        fatigue_cost: tuple[int, int, int]
        expected_recovery_hours: int
        target_preference: tuple[str, ...]
        requirements: tuple[str, ...]
        contraindications: tuple[str, ...]
        step_builder_key: str

    def catalog_definitions() -> tuple[WorkoutTemplateDefinition, ...]: ...
    def select_workout_template(context: Mapping[str, Any]) -> dict[str, Any]: ...
    def materialize_workout(definition, parameters, zone_snapshot) -> dict[str, Any]: ...
    def prepare_weekly_brick_allocations(daily_plan, weekly_summary, *, goal_type, protected_dates, load_state) -> dict[str, Any]: ...
    def materialize_session_template(...): ...
    def refresh_materialized_session(...): ...
    def attach_composite_leg_ids(goal_plan): ...

The serialized single-session template must contain `kind=single` and `materialized_steps`. A composite template must contain `kind=composite`, `transition_minutes`, `legs`, aggregate `parameter_snapshot`, and no duplicate parent steps. Every leg contains its own definition snapshot, steps and prescription fingerprint.

`api/planning_service.py::export_workout` gains `leg: int | None = None`. `api/routers/planning.py` accepts `leg` as an optional constrained query. `plan_days` exposes `kind`, `template_key`, `template_version`, `template_name`, `stimulus`, `fatigue_cost`, `selection_evidence`, compact steps and leg summaries.

No new third-party dependency is required. Use standard-library dataclasses, hashing, JSON and existing SQLite/checkpoint, FastAPI, pytest and React/TypeScript infrastructure.

Revision note (2026-07-13 / Codex): finalized after implementation and synthetic browser acceptance; recorded the Taper-long sharpening override, Today checkpoint fallback under `data_gap`, exact validation counts and observable product evidence.
