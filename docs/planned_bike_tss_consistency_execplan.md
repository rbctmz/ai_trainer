# Align planned bike TSS with the executable power prescription

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date while the work proceeds. It is maintained according to `.agent/PLANS.md` at the repository root.

## Purpose / Big Picture

The athlete should be able to ride a planned bike workout for its planned duration and power zones without the application reporting a large TSS failure caused by an incompatible planning estimate. After this change, a steady-state bike session with an FTP-based power prescription will show a planned TSS derived from that prescription, using the same power-based semantics as activity TSS. Running, swimming, interval templates, and composite bricks remain outside this first correction scope.

The existing active plan and all historical activity matches are immutable. The correction is first visible as a read-only, future-only preview. The preview lists each affected future bike session, its current and honest TSS, and the explicit volume change needed to preserve the existing weekly TSS budget. Nothing is written until a later confirmation action is explicitly invoked.

## Progress

- [x] (2026-08-20) Created the implementation goal for issue #477 and confirmed the active database was restored to checkpoint #121 content; no duration or historical binding changes are allowed during this work.
- [x] (2026-08-20) Audited issue #471, #475, #476, #444, #172, and the current planner/materializer/reconciliation flow.
- [x] (2026-08-20) Confirmed the root discrepancy with a sanitized steady-state example: a 40-minute FTP-based ride at 112 W NP and FTP 172 yields about 28.2 TSS, while the stored power-zone prescription implies about 28 TSS; the stored 36.5 TSS is a separate budget estimate.
- [x] (2026-08-20) Decided to keep existing session durations and zones as the prescription; sport-scoped density must not silently rewrite them.
- [x] (2026-08-20) Added the deterministic planned-bike-TSS calculator and RED→GREEN regressions for power-zone midpoint semantics, missing FTP, and duration preservation.
- [x] (2026-08-20) New steady-state bike materializations use the calculator as effective planned TSS, retain `requested_tss` audit evidence, and project effective load into new daily/weekly plans.
- [x] (2026-08-20) Added a read-only future-only preview and an approval-gated volume-first apply path with checkpoint fingerprint, stale guard, weekly conservation, and append-only identity lineage.
- [x] (2026-08-20) Exposed additive planning API endpoints and a planning-page card with explicit preview/confirm controls and fail-closed capacity-gap diagnostics.
- [x] (2026-08-20) Focused tests, contributor-safe tests, ruff, web lint/build, contract extraction, and read-only active-DB preview completed; active checkpoint remained unchanged.
- [x] (2026-08-20) Future correction now searches minute-resolution durations and uses a feasible catalog proxy only for structure materialization; persisted FTP power targets remain the intensity source of truth.
- [x] (2026-08-20) Preview now fails closed unless the saved weekly availability budget is present and every affected week remains within its total duration cap; the UI reports weekly minutes before/after/budget.
- [ ] Write the final outcome and remaining non-goals here; do not apply a preview to the user’s active database during this implementation.

## Surprises & Discoveries

- Observation: `models/workout_catalog.py::materialize_workout` distributes the caller’s `target_tss` across steps before it creates power targets, so step TSS and power zones are not reconciled.
  Evidence: the function calls `_exact_distribution(target_tss, duration_shares, 1)` and independently calls `_target_for_step(...)`.
- Observation: `models/training_planner.py::materialize_day_sessions` uses the original discipline budget when it finalizes a catalog result, so fixing only the catalog snapshot would leave daily and weekly plan totals inconsistent.
  Evidence: `_finalize(...)` receives `tss` from `parts` and writes it to `total_tss` even when the catalog has a different materialized prescription.
- Observation: the current #476 scoped density logic makes a valid generic duration seed change for bike steady-state sessions.
  Evidence: `tests/smoke/test_catalog_target_density.py` expects 60 TSS at 90 minutes for endurance despite an estimated 120-minute seed. This conflicts with the explicit requirement to preserve duration until a future-only preview proposes a change.
- Observation: the existing weekly rebalance is designed to reduce future load after actual overage; it is not a correction for a plan whose own executable prescription under-delivers its stored TSS.
  Evidence: `models/plan_actual_reconciliation.py::build_weekly_rebalance_preview` computes an overage and scales eligible easy sessions down.
- Observation: session identity is content-derived and append-only lineage is already supported.
  Evidence: `models/session_identity.py` includes duration, TSS, and the materialized prescription in the identity payload, and `ensure_session_identities` records `replaces_session_id` when content changes.
- Observation: the active checkpoint preview found five future bike sessions that can preserve their requested TSS by adding 80 minutes total, but two sessions cannot be reproduced inside the current catalog bounds/rounding tolerance.
  Evidence: read-only preview against checkpoint #125 returned `status=no_change`, `reason=capacity_gap`, `changes=5`, and `capacity_gaps=2`; the checkpoint id before and after remained 125.
- Observation: both reported capacity gaps were representational, not true capacity failures. Minute-resolution candidates of 104 minutes on 2026-08-22 and 58 minutes on 2026-09-01 produce 78.1 and 38.7 TSS respectively.
  Evidence: read-only preview after the correction returned `status=proposal`, no capacity gaps, and unchanged checkpoint #125.
- Observation: the active checkpoint stores a weekly availability contract (`available_hours=10.0`) but no per-day minute limits.
  Evidence: active preview after the time-budget gate reports 354/600 minutes for the week of 2026-08-17 and a maximum of 475/600 minutes in any affected future week; daily availability remains an explicit data gap.

## Decision Log

- Decision: use the midpoint of each persisted FTP power target band and the canonical power-TSS formula `hours × 100 × (midpoint_watts / FTP)^2`, summed over steps.
  Rationale: it is deterministic, explainable, matches the existing power TSS semantics, and is the same calculation validated by the #471 evidence spike. It avoids pretending that a range is an exact wattage.
  Date/Author: 2026-08-20 / Codex.
- Decision: apply the derived metric only to single, steady-state bike builders (`recovery`, `endurance`, and `progression`) with an explicit FTP provenance and power targets on every step.
  Rationale: this is the validated problem slice. Interval/NP semantics, race-pace templates, bricks, and fallback RPE prescriptions need separate evidence and must not be changed implicitly.
  Date/Author: 2026-08-20 / Codex.
- Decision: preserve the requested budget as `requested_tss` audit evidence, but make the effective planned TSS, session total, daily parts, and weekly summary use the executable derived value for newly built plans.
  Rationale: the product’s plan-vs-fact comparison must compare fact with what the athlete was actually prescribed. The original budget remains necessary for diagnosis and future rebalance.
  Date/Author: 2026-08-20 / Codex.
- Decision: a supplied estimated duration is preserved whenever it satisfies the catalog’s declared bounds; density is a fallback for infeasible selection, not an automatic duration mutation.
  Rationale: the athlete’s duration and power zones are the workout prescription. Future volume changes require an explicit preview and confirmation.
  Date/Author: 2026-08-20 / Codex.
- Decision: future budget preservation is volume-first. The preview may extend a future steady-state bike session within its catalog maximum, but it never silently raises power zones.
  Rationale: increasing intensity would change the workout stimulus and could make the user’s “done as prescribed” execution unsafe. A capacity gap must be shown rather than forced.
  Date/Author: 2026-08-20 / Codex.
- Decision: historical dates, existing session IDs, completed activity matches, and the current checkpoint are read-only during this task.
  Rationale: ASR-REL-1 and the user’s reported binding regression make data preservation a release gate, not an implementation detail.
  Date/Author: 2026-08-20 / Codex.

## Outcomes & Retrospective

2026-08-20: issue #477’s steady-state bike slice is implemented. New FTP-based recovery/endurance/progression prescriptions derive effective planned TSS from their persisted power bands, retain the requested scheduler budget for diagnosis, and project effective load into newly built daily/weekly plans. Valid duration seeds are preserved; #476’s silent duration rewrite is no longer used when the seed satisfies catalog bounds. A future-only preview/apply path is available through the planning API and UI, with volume-only changes, weekly conservation, append-only checkpoint lineage, and stale protection.

Validation completed: contributor-safe pytest returned 1946 passed, 3 skipped, and 26 deselected; focused catalog/planner/API/preview tests returned 79 passed; ruff, web lint, production build, contract extraction, and web API inventory passed. A read-only preview against active checkpoint #125 returned the same checkpoint id before and after and found five feasible changes plus two capacity gaps, so no active-plan mutation was confirmed. The browser showed the new preview card and the two explicit capacity diagnostics.

Remaining non-goals are deliberate: interval/NP templates, race-pace and composite brick semantics, fallback RPE/HR prescriptions, and per-athlete calibration are not silently changed. The active athlete plan remains unchanged until the user reviews a preview with no capacity gaps and explicitly confirms it.

## Context and Orientation

The product path is `models/` for planning and domain rules, `api/` for FastAPI contracts, and `web/` for the Next.js product surface. `models/workout_catalog.py` selects catalog definitions and materializes executable steps. A materialized step has a duration and a target range such as watts. `models/training_planner.py` turns daily sport budgets into session templates. A planning checkpoint in the database is an append-only version of the plan.

TSS means Training Stress Score, a load number. For power-based bike activities the existing canonical local formula is duration in hours multiplied by 100 and by normalized power divided by FTP, squared. For planning, a range has no single observed power, so this task uses the midpoint of each range as a transparent estimate. FTP is functional threshold power, the athlete’s stored power reference.

The active plan must not be rebuilt in place. A preview is a read-only object containing a base checkpoint id and a fingerprint. A confirmation may create a new checkpoint only if the base checkpoint is unchanged. Past and today are protected by date; future sessions retain their roles, zones, and calendar dates. A materially changed prescription receives a new content-derived session id linked to the old id with `replaces_session_id`.

The architectural quality attributes that constrain this work are ASR-REL-1 (no completed activity or executable session lost during replanning), ASR-MOD-2/3 (server-owned domain truth and additive API contracts), and ASR-PERF-4 (planning preview remains bounded and deterministic). The relevant repository references are `docs/architecture/asr_catalog.md`, `docs/architecture/architecture_analysis_add3.md`, and `docs/architecture/adr_0001_web_primary_ui.md`.

## Plan of Work

First add a pure calculator in `models/workout_catalog.py` or a narrowly scoped sibling module. It must return either a numeric derived TSS plus method/evidence or a fail-closed reason such as missing FTP, non-power targets, or unsupported builder. The calculator must not infer FTP from current settings for a historical session; it only uses the immutable provenance stored in the prescription.

Next change materialization for the supported steady-state bike slice. Keep the incoming budget as `requested_tss`; compute the effective planned TSS from the generated steps; distribute step TSS using the effective value; and store the method and evidence in `parameter_snapshot`. Keep the original target zones and duration unchanged. Update the training planner finalizer to use the effective catalog TSS for new plans and recompute daily/weekly sport totals from the materialized results. Non-bike or unsupported prescriptions retain existing behavior.

Before implementing the preview, add RED tests that prove the old behavior fails: a 40-minute endurance ride with a known FTP must not report the incompatible requested TSS as its effective planned TSS, and a valid estimated duration must not be rewritten merely because the scoped density table exists. Add tests for missing FTP and non-power targets to prove the calculator fails closed.

Then add a pure future-only preview/application pair. The preview reads the latest checkpoint, examines only dates after `as_of`, and selects supported future bike sessions whose effective TSS is lower than the stored weekly budget. For each, it estimates a longer duration using the same power zones, rounds to the catalog’s five-minute granularity, rematerializes the same definition, and checks the resulting effective TSS against the original session budget. It must report capacity gaps instead of applying partial hidden changes. The application path updates only future sessions, recomputes daily/weekly totals, records the preview fingerprint and provenance, and relies on `ensure_session_identities` for new ids and lineage.

Expose the preview and confirmation through additive planning API endpoints only after the model tests are green. Extend `web/lib/types.ts` from the generated contract workflow, add a compact planning-panel card showing “current honest TSS → after volume-only rebalance” and the duration delta, and require an explicit confirmation. Existing reconciliation and weekly-rebalance endpoints remain unchanged.

Finally run the focused catalog/planner/identity/API tests, the contributor-safe pytest command, ruff, and web lint/build when applicable. Exercise preview against a copied database or seeded temporary database and verify that a preview creates no checkpoint and confirmation changes no date at or before `as_of`. Do not confirm against the active athlete database in this task.

## Concrete Steps

Run all commands from `/Users/gregkisel/Developer/ai_trainer` and use `ai_trainer_env/bin/python` for Python commands.

    git status --short --branch
    ai_trainer_env/bin/python -m pytest tests/smoke/test_catalog_target_density.py tests/smoke/test_workout_catalog.py -q

Create or update tests before implementation and record the expected RED assertion in this plan. After each implementation slice run its focused tests, then run:

    ai_trainer_env/bin/python -m ruff check models/workout_catalog.py models/training_planner.py models/plan_actual_reconciliation.py tests/smoke/test_catalog_target_density.py tests/smoke/test_workout_catalog.py
    ai_trainer_env/bin/python -m pytest -m "not live and not debug and not e2e" tests/
    ai_trainer_env/bin/python -m pytest tests/smoke -q

If API or web types change, additionally run:

    npm --prefix web run contract:extract
    npm --prefix web run contract:extract -- --check
    npm --prefix web run lint
    npm --prefix web run build

For database verification, make a backup with `scripts/sqlite_backup_restore.py` before any explicit confirmation test. Use a temporary seeded database for the apply test; compare the serialized past templates, session ids, match ledger, and checkpoint count before and after preview.

## Validation and Acceptance

The pure calculator acceptance case is a supported steady-state bike prescription with explicit FTP and power targets. Its effective planned TSS must equal the sum of step-level midpoint power TSS within rounding tolerance, and the step TSS must sum to the same effective value. The requested budget must remain visible as audit data. A missing FTP or any non-power step must return a clear unsupported/data-gap result and must not fabricate a number.

The planner acceptance case is a new plan build with a valid estimated duration. The selected duration and every power target range remain unchanged from the materialized prescription, while session total TSS, daily sport parts, and weekly summary use the effective derived value for the supported bike slice. Existing run and swim assertions remain green.

The preview acceptance case uses `as_of` and a base checkpoint. It returns changes only for future steady-state bike sessions, never for past/today, races, interval/brick/unsupported sessions, or historical match rows. It includes before/after TSS, before/after duration, a volume-only reason, and any capacity gap. Repeating the preview without a database mutation returns the same fingerprint and creates no checkpoint. Confirmation rejects a stale base checkpoint and otherwise creates one append-only future-only version with lineage.

The human-visible acceptance case is the planning page: the user can request a bike-TSS consistency preview, see each proposed future duration/TSS change, and must click a separate confirmation action. The active plan is unchanged until that action. Existing “Скорректировать” reconciliation and activity binding controls continue to show the same historical matches.

## Idempotence and Recovery

All pure calculators and previews are read-only and deterministic. Preview fingerprints make repeated requests safe. A stale confirmation must fail closed with HTTP 409. Any local database apply test must use a temporary copy or a backup created by `scripts/sqlite_backup_restore.py`; never run the confirmation against the active athlete database for this task. If a test mutates a temporary checkpoint, restore the temporary database or delete only that explicitly created temporary file after verification.

If implementation reveals that the power prescription cannot be reconstructed from persisted provenance, leave that session unchanged and report a data gap. Do not substitute current athlete zones for historical data and do not regenerate a whole plan as a fallback.

## Artifacts and Notes

The primary artifact is this ExecPlan. Issue #477 tracks the product slice: https://github.com/rbctmz/ai_trainer/issues/477. The prior validated density evidence is in `spikes/issue-471-bike-tss-density-vs-zones/README.md`; it is evidence for the formula, not permission to mutate the active plan.

Expected focused proof after implementation:

    <focused catalog/planner/API tests>: passed
    <contributor-safe suite>: passed
    <web lint/build when applicable>: passed
    preview: no checkpoint written
    confirmation on temporary DB: past and match ledger unchanged; future-only checkpoint appended

## Interfaces and Dependencies

The calculator interface must be pure and callable without a database. Prefer a signature equivalent to:

    planned_bike_tss_from_steps(steps, target_provenance, *, supported_builders) -> dict

The result must contain `status`, `planned_tss`, `method`, `ftp`, `step_count`, and a stable reason/evidence field. The materializer’s `parameter_snapshot` must retain `requested_tss`, effective `target_tss`, `tss_per_hour`, and `planned_tss_method` for backward-compatible readers.

The future preview interface must be pure at the model layer and must accept a goal-plan mapping plus `as_of` and base checkpoint id. The API adapter must expose additive response fields, a preview fingerprint, and separate preview/confirm routes. The web client must use the existing `postJSON` pattern and preserve compatibility with a null/no-change preview.

No new third-party dependency is needed. Use existing Python standard-library math/copy/hash facilities, the current catalog materializer, checkpoint helpers, and the existing session identity/lineage mechanism.

## Revision Note

(2026-08-20) Initial plan created after the active-plan duration rollback. The key clarification is that #476’s density table is evidence for the TSS discrepancy but must not silently rewrite the athlete’s durations; explicit future-only volume changes belong behind a preview and confirmation boundary.
