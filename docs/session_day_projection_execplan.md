# Unify the day-template primary-session projection (fix #232 session-name/metadata drift)

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

This document must be maintained in accordance with `.agent/PLANS.md` (repository root).


## Purpose / Big Picture

An endurance plan in this app stores one "day template" per calendar day. Each day template has a list `sessions` (the executable workouts of that day) and a set of **top-level scalar fields** that describe the day at a glance: its name/`template_name`, its `session_focus`, its `fatigue_cost`, its `expected_recovery_hours`, its `materialized_steps`, and so on. By an existing contract (issues #205/#206, "one template per day"), those top-level scalars are a **projection of the day's primary session** — `sessions[0]`, the hardest-first lead session.

After this change, whenever a session is moved between days (a "transfer"/recovery-replan) or a day is edited in the near-term editor, the day template's top-level scalars stay a *complete, consistent* projection of the new primary session. A user opening the "Сегодня по плану" card (`/api/today`), the plan view (`/api/planning/plan`), the Recovery Replan decision journal (`/api/decisions`), the chat coach, or an Intervals.icu delivery will see **one** name, focus, fatigue and recovery for the same session — never a mix.

Today they do not. On 2026-07-20 a swim day shows, on the Today card, the title "Neuromuscular Sprints" with `fatigue_cost` 1/1/3 and ~30h recovery, while its steps (Easy warm-up / Technique drills / Aerobic swim / Easy cool-down) and its `session_focus` in the plan snapshot say "Technique + Aerobic Swim". The day template is a Frankenstein: `session_focus` + `materialized_steps` come from the current primary (a technique swim), but `template_name` + `fatigue_cost` + `expected_recovery_hours` are stale leftovers from a previous primary (a neuromuscular bike session). You can see it fixed by transferring a session in a test plan and asserting the moved day's `template_name` and `fatigue_cost` now equal the new primary's, not the old one's.


## Progress

- [x] (2026-07-21) Root-cause investigation complete: the primary→top-level projection contract is implemented in four places; only the initial builder is complete. See `Context and Orientation`.
- [x] (2026-07-21) M1 — `project_day_scalars(template)` + `_SESSION_META_MIRROR_KEYS` added to `models/training_planner.py`.
- [x] (2026-07-21) M2 — Projector wired into all three mutation sites: `models/session_transfer.py::_rebuild_day_projection` (and dead `_DAY_MIRROR_KEYS` removed), `models/planning_near_term.py` both sites. Regression + day-survival tests added in `tests/smoke/test_session_day_projection.py` (regression RED before, GREEN after).
- [x] (2026-07-21) M3 — Builder-parity test added; guards the allow-list against drift. All three tests pass; full `tests/smoke` green at 974 passed.
- [x] (2026-07-21) M4 — Full smoke green. No `asr_catalog.md` row warranted: that catalog tracks API-router contract tests, and this is an internal plan-construction invariant, documented by this ExecPlan and the new test. PR to follow.
- [ ] (Optional) M5 — DEFERRED. Refactor the initial builder to call the shared projector, retiring the last duplicated projection. Not done: the builder's `**projected` is a denylist that propagates *every* primary key, so switching it to the allow-list projector could silently stop propagating a future out-of-allow-list key. The M3 parity test already keeps the two in lock-step (it fails if the builder projects a catalog key the projector omits), so no drift hole remains. Promote only with explicit appetite for touching the load-bearing builder.


## Surprises & Discoveries

- Observation: `ensure_session_identities` (`models/session_identity.py`) does NOT repair the stale top-level metadata; it only stamps `session_id`/`session_material_fingerprint`. So a stale projection from a transfer survives identity stamping.
  Evidence: `models/session_identity.py:300-372` mutates only identity keys and, for a single-session day, mirrors `legs` — never `template_name`/`fatigue_cost`/`expected_recovery_hours`.

- Observation: the mismatch cannot arise from a fresh build — only from a post-build mutation — because the initial builder projects *all* primary keys via `**projected`.
  Evidence: `models/training_planner.py:2163-2216`.

- Observation: `brick_status`/`brick_status_reason`/`mutation_evidence`/`allocated_parts` are DAY-level (spread from `day_meta`), not carried on the primary session dict. They were dropped from the projector's allow-list so a brick day's `project_day_scalars` does not clobber builder-set day metadata. The parity test only iterates keys present on the primary, so it naturally does not demand them.
  Evidence: `models/training_planner.py:2211-2212` sets `allocated_parts`/`**day_meta` on the template, never on the session; `_finalize` (2027-2038) returns no such keys.

- Observation: the near-term "edit day from parts" path rebuilds sessions as manual scalar shells with no catalog metadata (`_sessions_from_parts`, `models/planning_near_term.py:347-382` — only sport/role/focus/duration/tss/template_key/export_name). Running the projector there therefore *clears* the previous catalog session's `template_name`/`fatigue_cost`/`materialized_steps` rather than copying them, which is the correct #232 outcome (consumers fall back to the manual `session_focus`/`export_name`). No existing near-term test asserted the stale-retaining behavior; all 13 still pass.

- Observation: the builder-parity test first failed on `session_id` — the built template's `session_id` comes from `ensure_session_identities`, not from the primary projection. Identity/lineage keys were added to the test's day-owned exclusion set; the projector correctly leaves identity to `ensure_session_identities`.
  Evidence: RED `AssertionError: ('2026-07-20', 'session_id') assert None == 'ats_…'` before the exclusion fix.


## Decision Log

- Decision: Fix the data (the projection), not the presentation. Do not merely make `api/today_snapshot.py` read `session_focus` instead of `template_name`.
  Rationale: multiple consumers read the stale top-level fields — `api/today_snapshot.py:648,672-673`, `api/planning_service.py:772-773` (`plan_days`), and `models/intervals_workout_delivery.py:194-234` (which uses `template_name`/`export_name` to form Intervals.icu external ids). A presentation-only fix would leave delivery and coach context wrong.
  Date/Author: 2026-07-21, Claude (issue #232).

- Decision: The canonical projector uses an **allowlist** of session-metadata keys (copy-or-pop), not a denylist of day-owned keys.
  Rationale: with an allowlist, a forgotten key leaves a metadata field stale — caught by the builder-parity test at CI time and never corrupting day-level data. With a denylist, a forgotten day-owned key would be silently dropped from the template (real data loss). The safer failure mode wins.
  Date/Author: 2026-07-21, Claude (issue #232).

- Decision: Do not refactor the initial builder in the first pass (M1–M4). Keep it as the reference and prove equivalence by test; treat the builder refactor as optional M5.
  Rationale: the builder is load-bearing (identity, external ids, invariants). Switching it from its `**projected` denylist to the allowlist projector could stop propagating an out-of-allowlist key — a behavior change. The bug is fully fixed at M2 without touching it.
  Date/Author: 2026-07-21, Claude (issue #232).

- Decision: The allow-list holds only keys that live on the primary *session* (23 catalog/presentation keys). `brick_status`/`brick_status_reason`/`mutation_evidence`/`allocated_parts` are day-level and were left out so the projector never removes builder-set day metadata.
  Rationale: the projector's job is "top level mirrors sessions[0]"; day-level metadata is not the primary's to carry. Including them would make a brick day's projection erase its own `brick_status`.
  Date/Author: 2026-07-21, Claude (issue #232).

- Decision: The projector runs in the near-term "edit from parts" path only inside the `if rebuilt:` branch (where sessions were actually rebuilt), never on the composite/off branches that leave `sessions` unset.
  Rationale: calling it with no sessions would reduce a composite day to an off day at the top level. Scoping the call to real rebuilds keeps composite/off behavior unchanged while fixing the manual-edit drift.
  Date/Author: 2026-07-21, Claude (issue #232).


## Outcomes & Retrospective

(2026-07-21, M1–M4 complete.) A single canonical `project_day_scalars` now backs every post-build day mutation. The transfer/recovery-replan path and both near-term editor paths project the primary session in full, so a moved-onto day mirrors its new primary and a day emptied by the move sheds its catalog identity. The regression test `test_transfer_reprojects_full_primary_metadata_without_drift` was RED before the change (an emptied bike-recovery day kept `template_name='Recovery Spin'`) and is GREEN after; the builder-parity test guards the allow-list against future drift. Full `tests/smoke` is green at 974 passed (up from 971). Against the Purpose: the Today card, plan view, Recovery Replan journal, coach context and Intervals delivery now read one consistent name/focus/fatigue/recovery for a transferred or edited session, because they all read a top level that is a complete projection of `sessions[0]`.

Remaining: M5 (fold the initial builder onto the shared projector) is deferred by decision — the parity test already prevents drift, so the two-implementation state is safe. The two cosmetic `/decisions` tails noted in issue #232 (journal timestamps showing "00:00"; a trirepeated `low_readiness_easy_session` conflict row) are out of scope for this projection fix and, if wanted, belong in a separate change.


## Context and Orientation

A "day template" is a Python `dict`. Its `sessions` key holds a list of "session" dicts (each an executable workout, possibly a composite "brick" with `legs`). Its top-level keys mirror the **primary** session `sessions[0]`. This mirroring is the "day-level scalars are a projection of sessions[0]" contract from issue #205/#206 — a rest/off day (`sessions == []`) carries only off scalars.

A "session" dict is produced by the workout catalog and finalized by the planner. The catalog output (`models/workout_catalog.py::materialize_session_template` at line 1000, and `::materialize_brick_session` at line 1092) carries these keys, all consistent with one chosen catalog definition:

    kind, catalog_version, selector_rule_version, materializer_rule_version,
    template_key, template_version, template_name, stimulus, fatigue_cost,
    expected_recovery_hours, duration_minutes, materialization_status,
    definition_snapshot, parameter_snapshot, materialized_steps,
    target_provenance, structure_status, structure_evidence,
    selection_evidence, prescription_fingerprint
    (composite also: sport, sport_label, transition_minutes, legs)

The planner's `_finalize` (`models/training_planner.py:2012-2038`) wraps that with `sport`, `sport_label`, `session_role`, `session_focus` (set equal to the catalog `template_name` or the day focus), `total_tss`, `export_name`, `description`.

The projection contract is implemented in FOUR places. Only the first is complete:

1. Initial build — `models/training_planner.py:2163-2216`. Computes `projected = {k: v for k, v in primary.items() if k not in {sport, sport_label, session_role, session_focus, duration_minutes, total_tss, template_key, export_name, description}}` and builds the template as day-level keys + explicit recomputed scalars + `**projected` + `sessions`. Because `**projected` carries EVERY other primary key, `template_name`, `fatigue_cost`, `expected_recovery_hours`, `stimulus`, `materialized_steps`, etc. all land on the top level, consistent with the primary. This is the reference behavior.

2. Transfer / recovery-replan — `models/session_transfer.py::_rebuild_day_projection` at line 57. Mirrors only `session_role`, `sport`, `sport_label`, `session_focus`, `duration_minutes` (lines 69-73) plus `_DAY_MIRROR_KEYS = ("kind", "legs", "transition_minutes", "materialized_steps")` (line 26). It never mirrors `template_name`, `fatigue_cost`, `expected_recovery_hours`, `stimulus`, `template_key`, `template_version`, the snapshots, provenance, etc. — so those stay stale from the previous primary. `apply_session_transfer` (same file, line 132) is the single transfer primitive; recovery replan reaches it via `models/recovery_transfer.py:224` and `api/planning_service.py:1286`.

3. Near-term day edit (parts) — `models/planning_near_term.py:407-415`. Pops `sessions`/`allocated_parts`/`brick_status`/`brick_status_reason`, rebuilds `sessions` from edited parts, and returns without reprojecting any top-level metadata.

4. Near-term targeted session edit — `models/planning_near_term.py:1209-1220`. Sets new `sessions` and updates only `session_role`, `session_focus`, `sport`, `sport_label`, `duration_minutes` — leaving `template_name`, `fatigue_cost`, `expected_recovery_hours` and even `materialized_steps` stale on the copied `dict(current_template)`.

Consumers that read the stale top-level fields: `api/today_snapshot.py` (`_project_session`, line 634; name at 648, fatigue/recovery at 672-673); `api/planning_service.py::plan_days` (fatigue/recovery at 772-773); `models/intervals_workout_delivery.py:194-234` (name/export_name for external ids); the coach context and decision journal via the same templates.

An authoritative list of "session-level keys that must be cleared when a day stops being a training day" already exists at `models/coach_constraints.py:67-86` (the constraint-off path). The projector's allowlist should agree with it.


## Plan of Work

Add ONE canonical projector and route the three drifted mutation sites through it; prove it matches the initial builder by test.

Define, near the top of `models/training_planner.py`, a module constant and a function:

    # Top-level day scalars that mirror the primary session sessions[0].
    # These are the primary session's own catalog/presentation keys; the five
    # identity scalars (session_role, sport, sport_label, session_focus,
    # duration_minutes) are projected explicitly with fallbacks. total_tss,
    # sessions, allocated_parts, brick_status and the day/lineage/identity keys
    # are day-owned (not carried on a session) and never mirrored here.
    _SESSION_META_MIRROR_KEYS = (
        "kind", "template_key", "template_version", "template_name",
        "export_name", "description", "stimulus", "fatigue_cost",
        "expected_recovery_hours", "catalog_version", "selector_rule_version",
        "materializer_rule_version", "materialization_status",
        "definition_snapshot", "parameter_snapshot", "materialized_steps",
        "target_provenance", "structure_status", "structure_evidence",
        "selection_evidence", "prescription_fingerprint", "legs",
        "transition_minutes",
    )

    def project_day_scalars(template: MutableMapping[str, Any]) -> None:
        """Refresh a day template's top-level scalars as a COMPLETE projection
        of its primary session sessions[0]. Mutates in place. Day-owned keys
        (date, phase, week/day index, allocated_parts, constraint, lineage,
        identity, sessions, total_tss) are never touched. A day with no sessions
        is reduced to off scalars and carries no catalog metadata."""
        sessions = list(template.get("sessions") or [])
        if sessions:
            primary = dict(sessions[0] or {})
            template["session_role"] = str(primary.get("session_role") or "easy")
            template["sport"] = str(primary.get("sport") or "off")
            template["sport_label"] = str(
                primary.get("sport_label") or SPORT_LABELS_RU.get(template["sport"], template["sport"])
            )
            template["session_focus"] = str(primary.get("session_focus") or "—")
            template["duration_minutes"] = int(primary.get("duration_minutes") or 0)
            for key in _SESSION_META_MIRROR_KEYS:
                if key in primary:
                    template[key] = deepcopy(primary[key])
                else:
                    template.pop(key, None)
        else:
            template["session_role"] = "off"
            template["sport"] = "off"
            template["sport_label"] = SPORT_LABELS_RU.get("off", "off")
            template["session_focus"] = "—"
            template["duration_minutes"] = 0
            for key in _SESSION_META_MIRROR_KEYS:
                template.pop(key, None)

Note the `duration_minutes` here uses `int(primary.get("duration_minutes") or 0)`; the transfer's existing helper `session_duration_minutes(primary)` returns exactly `int(round(float(primary.get("duration_minutes") or 0)))`, so the two agree for integer minutes. Keep the transfer call reading its day total/parts separately as it does now.

Then:

1. In `models/session_transfer.py::_rebuild_day_projection`, replace the hand-written scalar block (lines 68-86) with a call to `project_day_scalars(template)` (imported from `models.training_planner`), still returning the recomputed `(total, parts)` from `sessions[]` as it does now. Remove the now-unused `_DAY_MIRROR_KEYS` constant (or keep it only if still referenced elsewhere — it is not).

2. In `models/planning_near_term.py`, after each of the two sites that assign `next_template["sessions"] = …` (around lines 415 and 1210), call `project_day_scalars(next_template)` so the top-level scalars follow the rebuilt sessions. Delete the now-redundant partial `next_template.update({...})` block at 1212-1220 (the projector supersedes it).

3. Do NOT change `api/today_snapshot.py`; after the data fix its reads become correct.

Keep the initial builder (`models/training_planner.py:2163-2216`) unchanged in M1–M4; the M3 parity test proves the projector reproduces it. M5 (optional) may later refactor the builder to call `project_day_scalars`.


## Concrete Steps

Work in the repository root. Use the project virtualenv interpreter.

Run the focused planning suites before the change to capture the baseline:

    python -m pytest tests/smoke/test_api_planning.py tests/smoke/test_recovery_replan_loop.py tests/smoke/test_recovery_transfer_product_surface_web.py -q

Create `tests/smoke/test_session_day_projection.py` with:

- A regression test that builds a real plan (reuse `_seeded_db` + `planning_service.build_plan(..., persist=True)` as in `tests/smoke/test_api_planning.py::test_export_and_adjust_active_plan`), locates two training days with DIFFERENT `template_name`s, transfers the primary session of one onto the other via `models.session_transfer.apply_session_transfer`, and asserts the target day's top-level `template_name`, `fatigue_cost`, `expected_recovery_hours`, `session_focus` and `materialized_steps` ALL equal the moved session's (no field lags behind). This test fails before the change (stale `template_name`/`fatigue_cost`) and passes after.

- A day-field-survival test: after the same transfer, assert day-owned keys `date`, `phase`, and any `constraint` on the touched templates are unchanged.

- A builder-parity test (the anti-drift guard): construct a representative single session dict and a composite session dict (borrow shapes from `models/workout_catalog.py` materializers, or from a built plan's `session_templates`), build a template two ways — once through the initial builder's projection, once by calling `project_day_scalars` on a `{"sessions": [primary]}` template — and assert the projected catalog/metadata keys are equal. If a future catalog key is added to sessions but omitted from `_SESSION_META_MIRROR_KEYS`, this test fails.

Run the new file (expect the regression test RED before code changes, GREEN after):

    python -m pytest tests/smoke/test_session_day_projection.py -q

Apply the code changes in `Plan of Work`. Re-run the new file and the baseline suites, then the whole smoke suite:

    python -m pytest tests/smoke/test_session_day_projection.py -q
    python -m pytest tests/smoke/test_api_planning.py tests/smoke/test_recovery_replan_loop.py tests/smoke/test_recovery_transfer_product_surface_web.py -q
    python -m pytest tests/smoke -q

Expected: the new file passes; the planning/recovery suites keep their prior pass counts; the full smoke suite stays green.


## Validation and Acceptance

Acceptance is behavioral: after a transfer, a day template's top-level name/fatigue/recovery match its primary session.

- Before: in a Python session, build a plan, transfer a session onto a day whose previous primary had a different `template_name`, and observe `target_template["template_name"]` still equal to the OLD name while `target_template["session_focus"]` is the NEW focus.
- After: the same steps show `target_template["template_name"]`, `["fatigue_cost"]`, `["expected_recovery_hours"]`, `["session_focus"]` and `["materialized_steps"]` all describing the moved session.

Test acceptance: `python -m pytest tests/smoke/test_session_day_projection.py -q` — expect all passed; the regression test is RED before the `Plan of Work` edits and GREEN after. The full `python -m pytest tests/smoke -q` stays green.


## Idempotence and Recovery

All edits are additive or in-place refactors of pure functions; re-running the steps is safe. The projector is idempotent — calling it twice on the same template yields the same result. If a milestone half-lands, the plan can be resumed from `Progress`. No migrations, no destructive data operations.


## Artifacts and Notes

Key references (repository-relative):

    Complete reference projection:   models/training_planner.py:2163-2216
    Drifted site (transfer):         models/session_transfer.py:57-87, 26
    Drifted site (near-term parts):  models/planning_near_term.py:407-416
    Drifted site (near-term edit):   models/planning_near_term.py:1209-1220
    Canonical key list precedent:    models/coach_constraints.py:67-86
    Stale-field consumers:           api/today_snapshot.py:648,672-673
                                     api/planning_service.py:772-773
                                     models/intervals_workout_delivery.py:194-234


## Interfaces and Dependencies

New public symbol: `models.training_planner.project_day_scalars(template)` (and the private `_SESSION_META_MIRROR_KEYS`). Imported by `models/session_transfer.py` and `models/planning_near_term.py`, which already import other helpers from `models.training_planner` (`_build_week_structure_metadata`, `derive_weekly_sport_buckets_from_sessions`), so the import direction introduces no cycle. No external dependencies, no schema or API contract changes; the fix is internal to plan construction and observable through existing endpoints.
