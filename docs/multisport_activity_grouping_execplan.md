# Group multisport activities without double-counting totals

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds. This document follows `.agent/PLANS.md` and implements GitHub issue #433.

## Purpose / Big Picture

An athlete who completes one triathlon must see one workout on `/activities`, not a flat list containing both the whole Garmin multisport recording and every Intervals.icu stage. The one workout can be expanded to inspect swim, transition, bike, transition, and run stages. Counts, elapsed time, distance, and TSS must describe the event once.

The behavior is observable with the local 2026-07-26 data. Before this change the activity list treats six rows as six workouts and totals 412.4 minutes, 99.41 km, and 360.2 TSS. After the change it shows one top-level triathlon with five stages and totals 206.2 minutes, 49.70 km, and 291.5 TSS.

## Progress

- [x] (2026-08-13 05:45Z) Profiled the real multisport rows and provider lineage in local SQLite.
- [x] (2026-08-13 05:45Z) Created structured GitHub issue #433 and branch `codex/issue-433-multisport-activity-groups`.
- [x] (2026-08-13 05:47Z) Added and confirmed RED API/web tests for complete, partial, standalone, and unrelated activity shapes: 5 failed, 19 passed before implementation.
- [x] (2026-08-13 06:17Z) Implemented shared `models/activity_lineage.py`, reused it for CTL/ATL selection, and added the additive grouped API fields.
- [x] (2026-08-13 06:17Z) Rendered an accessible expandable stage list in the Next.js activity table with Russian transition labels.
- [x] (2026-08-13 06:20Z) Completed focused/full tests, lint, build, desktop/mobile browser acceptance, and self-review: 1693 passed, 1 skipped; no document overflow at 1280/390 px.
- [x] (2026-08-13 06:24Z) Committed GREEN, pushed the branch, opened draft PR #434 closing #433, and observed clean merge state with all current-head checks green.

## Surprises & Discoveries

- Observation: The local event is represented at two grains: one Garmin envelope plus five Intervals.icu child stages. The child links all carry `external_provider='garmin'` and `external_id='23738670433'`.
  Evidence: raw totals are 6 rows, 412.4 minutes, 99.41 km, and 360.2 TSS; the linked stages alone are 5 rows, 206.2 minutes, 49.70 km, and 291.5 TSS.
- Observation: CTL/ATL already use `models.signals_engine._without_multisport_envelopes`, so training load is not double-counted there. The defect is the flat activity-list projection and its aggregate totals.
  Evidence: `training_load_metrics` filters a complete positive swim/bike/run set before invoking the Banister model, while `api.routers.activities.list_activities` sums the unfiltered DataFrame.
- Observation: The RED gate isolates presentation aggregation from the existing training-load behavior.
  Evidence: the three new API grouping cases and two web contracts fail, while all 19 existing `test_multisport_training_load.py` cases pass.

## Decision Log

- Decision: Keep provider ingestion and SQLite rows unchanged; group only in a shared read projection.
  Rationale: Both source records are valuable evidence. Destructive merging would lose provider detail and violate the accepted multi-provider ADR.
  Date/Author: 2026-08-13 / Codex.
- Decision: A complete positive swim/bike/run set makes child stages authoritative for TSS, including linked transition TSS. The envelope remains authoritative when the stage set is incomplete.
  Rationale: This is the established training-load rule and prevents both double-counting and partial-sync data loss.
  Date/Author: 2026-08-13 / Codex.
- Decision: Duration and distance of a grouped workout come from the envelope, while the stages remain visible as details.
  Rationale: The envelope expresses the event grain and already equals the sum of the complete local stages. It also remains safe if stages arrive only partially.
  Date/Author: 2026-08-13 / Codex.
- Decision: Extend the existing activity DTO additively with `group_kind`, `group_label`, and `segments`; do not version or replace the endpoint.
  Rationale: Existing single-sport consumers keep the same fields and behavior. The web UI can opt into grouping without a breaking API migration.
  Date/Author: 2026-08-13 / Codex.
- Decision: The disclosure control owns expansion separately from the existing row click action, and its accessible name changes between show and hide.
  Rationale: Opening stages must not accidentally open the activity modal; keyboard and screen-reader users need the same state transition as pointer users.
  Date/Author: 2026-08-13 / Codex.

## Outcomes & Retrospective

The local implementation meets the user-visible purpose: the real 26.07.2026 event is one top-level triathlon with five ordered stages, 206.2 minutes, 49.7 km, and 291.5 TSS. Partial linked stages remain nested under the envelope without replacing envelope TSS, and unrelated same-day activity remains separate. The shared lineage model keeps the pre-existing CTL/ATL behavior unchanged while removing duplicate totals from the activity list.

Verification is clean: 24 focused activity/lineage/UI tests pass; the contributor-safe suite reports 1693 passed and 1 environment skip; Next lint and production build pass. Browser acceptance confirms disclosure without modal side effects, ordinary-row modal behavior, Russian stage labels, and no document-level overflow at 1280 or 390 px. No SQLite rows, provider links, or sync cursors were mutated by the implementation.

The implementation is published in draft PR #434. CI, secret scan, issue linkage,
roadmap sync, and the ready-to-merge projection are green; GitHub reports a
clean merge state and no review threads. Human merge authority remains the only
step outside this ExecPlan.

## Context and Orientation

`activities` is the canonical SQLite table. `activity_provider_links` stores the relationship from a canonical activity to Garmin or Intervals.icu evidence. `data.database.Database.get_activities` exposes `provider_external_id` for an Intervals row whose external Garmin identifier points at the Garmin multisport envelope.

`models/signals_engine.py` currently contains the load-only lineage rule. It removes the envelope when a linked positive swim/bike/run set is complete and removes partial child rows when the set is incomplete. `api/routers/activities.py` currently bypasses that rule: it maps every SQLite row to an item and sums the raw DataFrame. `web/app/activities/page.tsx` renders those items as flat table rows. `web/lib/types.ts` defines the TypeScript contract.

An envelope is the single Garmin row with sport `multi_sport` or `multisport` that covers the whole event. A stage is a non-envelope row whose `provider_external_id` equals the envelope `activity_id`. A complete triathlon stage set contains positive-TSS swim, bike, and run stages; transition stages may also be present.

The affected architectural requirements are ASR-REL-1 because completed activity evidence must not be lost, ASR-REL-2 because partial lineage must degrade safely, and ASR-MOD-2 because the web component must consume a server-owned contract. No schema change or new ADR is required: ADR-0008 already requires preserving provider evidence and using read projections.

## Plan of Work

First, add a small shared lineage module under `models/` that identifies envelope-to-stage groups without mutating the input DataFrame. Move the existing training-load selection onto that module so load calculation and activity-list presentation use the same definition of complete lineage.

Second, add API tests in the existing activity router smoke suite. Construct a temporary database with the real six-row shape and explicit provider links. The test must fail while the endpoint returns six top-level items. It must require one top-level group, five chronologically ordered `segments`, envelope duration and distance, stage-derived TSS, and unchanged standalone behavior. Add a static web contract test that requires an accessible disclosure button and segment labels.

Third, update `api/routers/activities.py` to build base items once, group linked stages under their envelope, and calculate totals from the resulting top-level items. The grouped envelope receives `group_kind='multisport'`, `group_label='Триатлон'`, and a `segments` array. With a complete positive swim/bike/run set, its displayed TSS is the sum of all linked stage TSS and its provenance is `stages`; otherwise it keeps the envelope TSS. Single activities do not receive group fields.

Fourth, extend `web/lib/types.ts` additively and update `web/app/activities/page.tsx`. The table displays one triathlon row. A separate button with `aria-expanded` toggles a nested stage row so opening details does not accidentally open the existing activity modal. Each stage shows sport, minutes, distance, and TSS. Add `stages` to the TSS provenance labels.

Finally, verify the real database through the API and browser. Run the focused and full smoke suites, Next lint and build, and inspect `/activities` at the default viewport and 390 px. Confirm that expanding the triathlon causes no document-level horizontal overflow and that single-sport row click behavior remains intact.

## Concrete Steps

Run all commands from `/Users/gregkisel/Developer/ai_trainer`.

Add tests first and run their focused files. The new tests must fail because grouping and disclosure do not exist yet:

    ./ai_trainer_env/bin/python -m pytest tests/smoke/test_api_phase1.py tests/smoke/test_multisport_training_load.py tests/smoke/test_activities_multisport_ui_contract.py -q

Commit the confirmed RED gate. Implement the shared model, API projection, DTO, and UI. Re-run the focused command and expect all tests to pass.

Then run:

    ./ai_trainer_env/bin/python -m pytest tests/smoke -q
    npm --prefix web run lint
    npm --prefix web run build
    git diff --check

Start the local stack with `./run_web.sh`, open `http://localhost:3000/activities`, expand the 26.07.2026 triathlon, and verify desktop and 390 px behavior.

## Validation and Acceptance

The complete linked fixture must produce exactly one top-level item whose `activity_id` is the Garmin envelope identifier and whose five segments are in chronological order. Its duration must be 206.2 minutes, distance 49.70 km, and TSS 291.5. The API totals and top-level `count` must use the same values.

A standalone multisport envelope must remain one ordinary visible activity. A linked but incomplete stage set must remain one visible envelope group, expose the received stages, and keep the envelope TSS rather than substituting an incomplete stage sum. An unrelated same-day run without explicit lineage must remain a separate top-level activity.

In the browser, the table must initially show one triathlon row for the event. Its disclosure button must announce collapsed/expanded state, reveal all stages without fetching a provider, and avoid opening the activity modal. Existing ordinary rows must still open their modal. Neither desktop nor 390 px must introduce document-level horizontal overflow.

## Idempotence and Recovery

The work changes only read projection code, tests, types, and documentation. It does not rewrite SQLite or provider links and is safe to rerun. If grouping cannot prove an envelope relationship, rows remain visible rather than being deleted. If the branch must be abandoned, switching back to `main` restores the previous projection without a data rollback.

## Artifacts and Notes

The real local evidence that motivated the issue is:

    envelope: multi_sport, 206.2 min, 49.71 km, 68.7 heuristic TSS
    stages: swimming 34.7, transition 1.6, cycling 133.1,
            transition 1.2, running 120.9 TSS
    stage total: 206.2 min, 49.70 km, 291.5 TSS

The raw list currently sums the envelope and stages together. The implementation must never expose provider payload JSON or credentials in the API.

## Interfaces and Dependencies

The shared lineage module must expose a small immutable group description and a function that accepts a pandas DataFrame and identifies multisport groups. `models.signals_engine.training_load_metrics` must continue accepting the same arguments and producing the same public result.

`GET /api/activities` remains backward compatible. Each existing field remains available. A grouped item adds:

    group_kind: "multisport"
    group_label: "Триатлон"
    segments: Activity[]

For stage-derived group TSS, `tss_source` adds the value `stages`; `tss_method` is `multisport_stages_sum`. No new package dependency is permitted.

Revision note (2026-08-13 06:24Z): Recorded draft PR #434, green current-head checks, clean merge state, and the final human merge boundary.
