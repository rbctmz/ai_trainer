# Prescribe deterministic race microcycles around A/B/C events

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must remain current while implementation proceeds.

This document is maintained in accordance with `.agent/PLANS.md` at the repository root.

## Purpose / Big Picture

After this change, a plan does more than reduce TSS around a race. A confirmed A race still anchors the macrocycle, but the final seven days become an explicit triathlon microcycle with swim, bike, run, rest, and short activation intent. An earlier B race receives a shorter four-day freshening overlay. A C race remains train-through. The athlete sees every event-driven role, sport, phase, and load change in the read-only Planning preview before choosing whether to append a replacement checkpoint.

The active local checkpoint is deliberately not modified by this work (it was #63 when planning began and #65 at final acceptance). The real acceptance fixture is a B race on 2026-07-26 and a confirmed A race on 2026-10-04. Acceptance builds only a read-only preview against a copy of `ai_trainer.db`; it never persists a plan and never exports to Intervals.icu.

## Progress

- [x] (2026-07-14 13:05Z) Read Issue #198, its live-status comment, `AGENTS.md`, `.agent/PLANS.md`, the predecessor race-priority ExecPlan, and the current planner/catalog/checkpoint/rebuild/web contracts.
- [x] (2026-07-14 13:05Z) Completed publish preflight, created `codex/issue-198-race-microcycles` in `/private/tmp/ai_trainer_issue198`, and verified that `origin` points to `rbctmz/ai_trainer` with authenticated GitHub publication available.
- [x] (2026-07-14 13:05Z) Pre-registered `race-microcycle-v2`, its exact A/B/C prescriptions, overlap precedence, deep-fatigue behavior, persistence boundary, and preview contract in this ExecPlan.
- [x] (2026-07-14 13:18Z) Added contract-first A/B/C, overlap, no-increase, and deep-fatigue tests. The pre-implementation run failed 5/5 on the intentionally absent `goal_type` keyword contract.
- [x] (2026-07-15) Implemented the pure `race-microcycle-v2` overlay and threaded it through initial builds and execution-feedback rebuilds.
- [x] (2026-07-15) Persisted the same microcycle explainability metadata and exposed before/after changes in the Planning preview and web UI.
- [x] (2026-07-15) Audited Issue #201 and `docs/architecture/architecture_analysis_add3.md`; added an ASR-PERF-4 regression for a 16-week read-only preview and retained the existing append-only/evidence contracts required by ASR-REL-1.
- [x] (2026-07-15) Validated a read-only preview on a copy of the real database with B 2026-07-26 and A 2026-10-04: 0.110 s, checkpoint #65 unchanged, `plan_id=null`, and no provider method invoked.
- [x] (2026-07-15) Completed verification: 66 focused, 667 smoke (+1 environment skip), 710 broad non-live (+6 environment skips, 24 deselected), clean `git diff --check`, and a successful Next.js 14 production build.
- [x] (2026-07-15) Rebased onto `origin/main` containing the #201 architecture analysis, reopened #198, pushed implementation commit `53fae50`, and opened replacement draft PR #202 with `Closes #198`.
- [x] (2026-07-15) Addressed independent review findings: enforced same-sport race-eve degradation, removed readiness `as_of=None` and protected-date footguns, tightened ASR-PERF-4 to 4 seconds, and reverified 67 focused, 668 smoke, and 711 broad non-live tests.

## Surprises & Discoveries

- Observation: `race-overlay-v1` changes TSS and protected dates but leaves every pre-race role, focus, and sport untouched.
  Evidence: `models/training_planner.py::apply_race_event_overlays` only calls `set_cap` without role/focus for negative offsets. The live-shaped preview therefore retained `long` on 2026-07-25 at 6.8 TSS.

- Observation: a modern A Race Week can collapse into repeated bike Recovery Spin sessions even though the weekly phase is correct.
  Evidence: daily sport remains whatever the generic weekly distribution produced; `build_daily_session_templates` chooses the dominant sport and has no race-microcycle intent input.

- Observation: the persisted checkpoint already stores the complete daily parts and session templates, while weekly rows retain only explicit whitelisted fields.
  Evidence: `build_planning_checkpoint` serializes `daily_plan` and `session_templates` wholesale but reconstructs each `weekly_summary` row with `day_roles` and `day_focuses`. New canonical sport truth can therefore live in daily parts, while any new explainability metadata must be added explicitly.

- Observation: execution-feedback replanning rebuilds daily load from weekly totals and reapplies `apply_race_event_overlays` before materializing templates.
  Evidence: `models/planning_execution.py::rebuild_goal_plan_with_adjustment` is a second required call site; changing only `api/planning_service.py` would make later checkpoints regress to cap-only behavior.

- Observation: the 19-item Workout Catalog v1 cannot guarantee a very low-TSS pre-race activation without weakening its registered feasibility bounds.
  Evidence: existing bike neuromuscular and run race-pace definitions require at least 20 and 30 TSS respectively, while the v1 overlay may leave less. Issue #197 owns richer run/bike structure. This issue therefore persists an explicit `activation` role and sport/focus truth without changing catalog definitions or claiming final workout structure.

- Observation: the Intervals.icu provider-category blocker is resolved.
  Evidence: the Issue #198 owner update records 2026-10-04 as `RACE_A`; 2026-07-26 remains `RACE_B`. No plan has been rebuilt or persisted.

- Observation: the initial BDD run is red for the intended missing public contract, not fixture or environment failures.
  Evidence: all five tests in `tests/smoke/test_race_microcycles.py` fail at `apply_race_event_overlays(..., goal_type="Триатлон")` with `unexpected keyword argument 'goal_type'`.

- Observation: current readiness must not rewrite a distant race microcycle.
  Evidence: applying `deep_fatigue` from 2026-07-15 to the 2026-10-04 A race initially removed October activation sessions. Readiness suppression is now bounded to the next seven days and is covered by a regression test.

- Observation: PR #200 merged only this ExecPlan and closed #198 before the implementation was published.
  Evidence: merge commit `7948d4f` contains the documentation commit only. The implementation therefore requires a replacement PR and reopening #198; no feature code is attributed to #200.

- Observation: the corrected real-data preview retains both distant A-race activations while still replacing the B-race eve long ride.
  Evidence: B D-1 changed `long bike 27.4` to `activation run 6.8`; A D-3 and D-1 changed to bike/run activations; the final phases are Peak, Taper, Race Week. The preview completed in 0.110 seconds and checkpoint #65 remained #65.

## Decision Log

- Decision: Version the new rule as `race-microcycle-v2` and keep the v1 load caps unchanged.
  Rationale: this change adds intent prescription and explainability without silently changing the already reviewed load-reduction budget. Daily and weekly TSS can only remain equal or decrease.
  Date/Author: 2026-07-14 / Codex.

- Decision: For a triathlon A race, prescribe the following offsets after the existing cap is applied: D-7 recovery swim, D-6 easy bike, D-5 easy run, D-4 recovery swim, D-3 bike activation, D-2 off, D-1 run activation, D0 race, D+1/D+2 off.
  Rationale: the sequence is deterministic, represents all three disciplines, includes recovery and full rest, and preserves two brief race-specific activation touches without retaining threshold, VO2, long, or generic quality roles.
  Date/Author: 2026-07-14 / Codex.

- Decision: For a triathlon B race, prescribe D-4 easy swim, D-3 bike activation, D-2 off, D-1 run activation, D0 race, D+1/D+2 off. C remains cap-only at D-1, race on D0, and recovery-capped on D+1.
  Rationale: B gets a shorter local freshening window and resumes the A macrocycle afterward. C makes the smallest safe intervention and does not manufacture a taper.
  Date/Author: 2026-07-14 / Codex.

- Decision: Add `activation` as a persisted session role and human-readable focus, but do not add or relax Workout Catalog definitions in this PR.
  Rationale: role/sport/focus is the stable planning contract needed by checkpoint, Today, reconciliation, and delivery. Exact repeat structures and target scales belong to #197; changing feasibility bounds here would hide rather than solve that work.
  Date/Author: 2026-07-14 / Codex.

- Decision: In `deep_fatigue`, prescribed activations within the next seven days become off days with zero TSS; more distant activations remain in the prospective plan. Recovery/easy prescriptions remain, while catalog selection still receives `deep_fatigue` and can only choose allowed low-cost material.
  Rationale: readiness is allowed to remove imminent stimulation but is not a valid forecast for a race weeks or months away. Seven days matches the bounded planning horizon and prevents today's fatigue from corrupting the October A-race microcycle. Suppression requires an explicit `as_of`; readiness-created rest is zero-load but is not added to immutable event `protected_dates`.
  Date/Author: 2026-07-14 / Codex.

- Decision: Prescription conflicts resolve by safety first (`race`, `off`, `recovery`, `activation`, `easy`), then event priority A before B before C, then nearest offset and event date. Caps always combine by minimum.
  Rationale: input order must not change the plan. A neighboring event cannot overwrite an immutable race day or post-race rest with a training prescription, and overlapping windows choose the safer result.
  Date/Author: 2026-07-14 / Codex.

- Decision: Sport reassignment is permitted only for a triathlon goal and only redistributes that already-capped day's total TSS to the prescribed sport. A zero-load or unavailable day stays zero.
  Rationale: multisport activation requires changing the dominant sport, but overlays must never create training load or bypass availability.
  Date/Author: 2026-07-14 / Codex.

- Decision: Non-triathlon goals retain their sport and normal pre-race structure under the existing A/B/C caps, except that a hard `long`/`quality` role on D-1 of A or B degrades to same-sport `easy`.
  Rationale: the registered swim/bike/run sequence is a triathlon prescription, but the issue-level safety invariant that race eve cannot remain hard applies to every sport. The minimal degradation satisfies it without inventing a multisport pattern.
  Date/Author: 2026-07-15 / Codex.

- Decision: `activation` is not a quality-forecast target and does not trigger post-workout quality scoring.
  Rationale: activation is a short, low-fatigue primer rather than a key quality outcome. Readiness conflict detection still recognizes it and may remove it under imminent deep fatigue.
  Date/Author: 2026-07-15 / Codex.

- Decision: Persist root-level `microcycle_changes` alongside `event_overlays`, and expose the same list in preview. Each row contains event/offset, phase, before/after role, sport, focus, and TSS.
  Rationale: the daily parts and session templates remain executable truth; versioned change rows provide durable explainability for preview, checkpoint history, and later audits without recomputing against a moving baseline.
  Date/Author: 2026-07-14 / Codex.

## Outcomes & Retrospective

Implementation, real-data acceptance, verification, and publication are complete in draft PR #202. A single versioned race-microcycle truth is created before catalog materialization, survives checkpoint round-trip and execution rebuild, and appears in the Planning preview. On the copied production fixture the A race remains the macrocycle anchor, the phase tail is Peak/Taper/Race Week, and B/A microcycles are explicit without persisting a checkpoint. The implementation deliberately preserves Workout Catalog v1 structures and provider transport; #197 owns richer running and cycling workouts. Issue #201 added a measurable 16-week preview latency guard and caused the readiness interaction to be audited prospectively rather than only on the July fixture. Self-review also prevented triathlon-specific swim/bike/run focus labels from leaking into single-sport goals. The earlier PR #200 remains a docs-only historical merge; #202 is the implementation review gate.

## Context and Orientation

`models/training_planner.py::apply_race_event_overlays` is the pure shared boundary. It receives daily tuples `(datetime, total_tss, parts)` and weekly rows containing phase, day roles, and focuses. It applies exact A/B/C caps, replaces race/post-race roles, recalculates weekly totals, and returns metadata. The implementation extends this function with keyword-only `goal_type`, `load_state`, and `as_of` inputs while keeping defaults backward compatible for direct callers.

`api/planning_service.py::build_plan` is the product build path. It computes constraints, expands weekly load, applies event overlays, allocates bricks, materializes session templates, builds a read-only preview, and optionally appends a checkpoint. It must pass goal/load state into the overlay, persist returned `microcycle_changes`, and show them in `_build_plan_preview` before confirmation.

`models/planning_execution.py::rebuild_goal_plan_with_adjustment` repeats the expansion/overlay/materialization pipeline after execution feedback. It must pass the same inputs and replace overlay metadata with the rebuilt truth. `models/planning_checkpoints.py` must explicitly preserve `microcycle_changes`; daily parts and session templates already round-trip completely.

`web/lib/types.ts` defines the API contract and `web/app/planning/page.tsx` renders the preview. The new UI is a compact list under the existing preview summary. It shows date, event priority/offset, phase, before role/sport/TSS, and after role/sport/TSS. It performs no planning logic.

`models/workout_catalog.py` remains unchanged. An `activation` role may legitimately receive `legacy_role_fallback` until #197 supplies exact low-volume activation structures. The persisted role, focus, sport, TSS, and provenance still reach delivery through the canonical session template.

## BDD Scenarios

Given a B triathlon on Sunday and a base plan whose Saturday is `long`, when v2 is applied, then Saturday becomes run activation, not long/quality/threshold/VO2, and its TSS is no greater than the v1 cap.

Given a confirmed A triathlon on Sunday, when Race Week is built, then D-7 through D-1 have the registered swim/bike/run pattern, D-2 is off, D-3 and D-1 are activation, D0 is an immutable race event, and no pre-race day retains `long` or `quality`.

Given a C race, when the overlay is applied, then D-1 keeps its original role and sport under the 70% cap, D0 is race, D+1 is recovery-capped, and macrocycle phases do not change.

Given a run- or bike-only A/B goal whose D-1 role is `long` or `quality`, when the overlay is applied, then D-1 becomes same-sport `easy` under the cap without receiving triathlon-specific labels.

Given overlapping A and B windows in either input order, when overlays are applied, then daily caps, prescriptions, protected dates, and `microcycle_changes` are identical; race/off/recovery safety wins before event priority.

Given `load_state=deep_fatigue`, when A or B activations fall within seven days of `as_of`, then those dates are off at zero TSS and no quality/long role appears.

Given `load_state=deep_fatigue` in July and an A race in October, when the prospective plan is built, then the October activation sessions remain prescribed because current readiness is not projected beyond seven days.

Given `load_state=deep_fatigue` without an explicit `as_of`, when the pure overlay is called, then no readiness-based activation is removed; and when an imminent activation is removed with `as_of`, its rest day is not marked as an immutable protected event date.

Given `planning_mode=event_goal` without a confirmed A event, when a build is requested, then the existing no-A validation still rejects it and creates no checkpoint.

Given a preview request with the real B/A fixture on a database copy, when it completes, then checkpoint count and Intervals.icu event count remain unchanged while the preview shows B and A microcycle changes.

Given a confirmed v2 checkpoint, when it is restored or rebuilt from execution feedback, then the same overlay rule, protected dates, role/sport daily truth, and microcycle change schema remain available to Today, reconciliation, RecoveryReplan, and delivery.

## Plan of Work

First add failing domain tests in `tests/smoke/test_race_microcycles.py`. Pin exact A/B/C rows, no-increase invariants, order-independent overlap handling, and deep-fatigue removal. Extend API tests for preview change rows and the existing no-A rejection. Extend checkpoint and execution tests for round-trip/rebuild metadata.

Then replace the cap-only internals of `apply_race_event_overlays` with a small prescription registry and deterministic resolver. Capture each affected day's pre-overlay role, sport, focus, TSS, and phase; apply minimum caps; redistribute the capped total only when triathlon sport intent wins; update weekly roles/focuses/totals; and return final before/after change rows. Preserve immutable event and post-race dates.

Thread `goal_type`, `load_state`, and returned metadata through `api/planning_service.py`, `models/planning_execution.py`, and `models/planning_checkpoints.py`. Add the `activation` role label. Do not alter provider clients, export mutation code, or the active database.

Finally extend the web response type and preview card. Run focused and full verification, then copy the real database to a temporary path and call `build_plan(..., persist=False)` with B 2026-07-26 and A 2026-10-04. Record evidence that checkpoint #63 was not replaced and no delivery endpoint was invoked.

## Concrete Steps

Work from `/private/tmp/ai_trainer_issue198` on `codex/issue-198-race-microcycles`. Use the virtualenv Python from the main workspace because ignored environments are not copied into worktrees:

    /Users/gregkisel/Developer/ai_trainer/ai_trainer_env/bin/python -m pytest tests/smoke/test_race_microcycles.py tests/smoke/test_race_priority_periodization.py tests/smoke/test_api_planning.py tests/smoke/test_planning_checkpoint_history.py tests/smoke/test_planning_execution.py -q

After implementation run:

    /Users/gregkisel/Developer/ai_trainer/ai_trainer_env/bin/python -m pytest tests/smoke -q
    /Users/gregkisel/Developer/ai_trainer/ai_trainer_env/bin/python -m pytest -m "not live and not debug" tests/ -q
    cd web && npm run build

For real-data acceptance, copy `/Users/gregkisel/Developer/ai_trainer/ai_trainer.db` to `/private/tmp/ai_trainer_issue198_acceptance.db`, point a temporary `Database` instance at that copy, and invoke only the read-only planner preview. Compare checkpoint counts before/after. Do not call delivery or Intervals.icu mutation methods.

## Validation and Acceptance

The new focused tests must fail on cap-only v1 before implementation and pass on v2. Full smoke must not regress below the Issue #198 baseline of 657 passed and one environment-dependent skip. The broader non-live suite and Next.js production build must pass.

Domain acceptance checks exact roles/sports for A and B, C train-through, input-order-independent overlaps, deep-fatigue removal, immutable protected dates, and `after_tss <= before_tss` for every day plus `after_weekly_tss <= before_weekly_tss` for every week.

API acceptance checks a preview response includes event, phase, offset, and before/after role/sport/TSS; cancel/persist-false changes neither checkpoint count nor settings; and confirmation remains bound to `base_checkpoint_id`. Checkpoint acceptance restores the same daily parts/templates and versioned change metadata. Execution acceptance proves a rebuild still applies v2 rather than regressing to cap-only v1.

The real-data preview must show 2026-07-26 as B and 2026-10-04 as A, preserve A as `macrocycle_event_date`, remove the long role from B D-1, and show a multisport A Race Week. It must also prove the active checkpoint remains #63 (or whatever ID was current in the copied fixture) and no external write occurred.

## Idempotence and Recovery

The overlay is pure and safe to repeat from the same base expansion. Preview is read-only. Tests use temporary databases. The acceptance database is a disposable copy. If the branch is abandoned, no local production data or provider data needs rollback. A persisted replacement plan and any delivery remain separate explicit human actions after merge.

## Artifacts and Notes

Issue #197 owns Workout Catalog v2: repeat grammar, run target scale, and richer bike/run structure. This PR makes race intent explicit enough for that catalog to consume, but does not claim that an `activation` template has final repeat structure. Issue #168/#192 owns delivery mechanics and is touched only through compatibility tests proving it consumes persisted templates.

The live probe from PR #199 established that Intervals.icu parses generic running `% HR` targets as `%hr` and that `external_id` upsert is idempotent. No provider probe is necessary for #198 because this task changes plan truth, not transport syntax.

## Interfaces and Dependencies

`models.training_planner` retains the public function and adds backward-compatible keyword inputs:

    def apply_race_event_overlays(
        daily_plan,
        weekly_summary,
        events,
        *,
        goal_type: str = "",
        load_state: str = "balanced",
        as_of: date | None = None,
    ) -> tuple[list, list, dict]: ...

The returned metadata has:

    {
        "rule_version": "race-microcycle-v2",
        "protected_dates": [...],
        "overlays": [...],
        "microcycle_changes": [
            {
                "date": "YYYY-MM-DD",
                "event_date": "YYYY-MM-DD",
                "priority": "A|B|C",
                "offset": -3,
                "phase": "Race Week",
                "before": {"role": "long", "sport": "bike", "focus": "...", "tss": 40.0},
                "after": {"role": "activation", "sport": "bike", "focus": "...", "tss": 16.0},
            }
        ],
    }

`POST /api/planning/build` adds `preview.microcycle_changes` and `event_overlay.microcycle_changes`. This is additive. The web consumes these fields without computing prescriptions. Checkpoint snapshots add root-level `microcycle_changes`; old checkpoints without the field restore as an empty list.

Plan revision note: 2026-07-14, initial self-contained design after source and issue audit; exact A/B/C sequences, deep-fatigue removal, overlap precedence, persistence, preview, and real-data no-write acceptance were resolved before tests or implementation. Revised 2026-07-15 after Issue #201 audit and real-shaped execution exposed the need to bound readiness suppression to seven days; also recorded the premature docs-only merge of PR #200.
