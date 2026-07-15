# Make executable sessions the single source of truth for discipline distribution

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds. This document is maintained in accordance with `.agent/PLANS.md` from the repository root. It implements Issue #205 and builds on the merged results of #202 (race microcycles, which introduced the `activation` role and race/overlay metadata) and #203 (Workout Catalog v2, real bike/run interval structures).

## Purpose / Big Picture

Today a twelve-week triathlon plan shows a balanced weekly table (for example bike 44%, run 36%, swim 20%) while the sessions an athlete would actually execute are almost entirely one sport (bike about 90%, run about 7%, swim about 3%). The weekly table and the executable calendar disagree, so the plan cannot be trusted or delivered.

The cause is a boundary defect between two layers. `models/training_planner.py::expand_weekly_to_daily_triathlon` produces, for each day, a blended three-discipline load such as run 10, bike 15, swim 5 (total 30). The weekly summary sums those blended parts, so it looks balanced. But `models/training_planner.py::build_daily_session_templates` then materializes exactly one session per day: it calls `_dominant_sport(parts)` (line 1891) to pick the single largest discipline and assigns the whole day total to it (`target_tss=float(total or 0.0)`, line 1911). The ten run and five swim become bike. Because bike is the largest bucket on most days, almost every day collapses to bike.

After this change, the discipline mix an athlete sees in the weekly table equals, to the decimal, the sum of the sessions the plan will actually export. A day may now carry more than one executable session (for example a swim plus a bike), each with its own structure and its own Intervals.icu event. Deep-fatigue no longer erases bricks across the whole macrocycle, race lead-up activations are real structured sessions rather than empty calendar rows, and a B race carries a forecast training load instead of zero.

This work is prospective and preview-only. It never writes to Intervals.icu without a separate explicit human acceptance, and it does not rewrite historical checkpoints.

## How to see it working

Before this change, run the anchor test and observe it fail because the executable calendar has collapsed to one sport:

    source ai_trainer_env/bin/activate
    python -m pytest tests/smoke/test_plan_discipline_truth.py -q

The failure prints the divergence directly (recorded under Surprises & Discoveries). After Milestone three the same command passes, and building a plan and printing its weekly summary next to a per-session export shows equal per-discipline totals.

## The core invariant this plan must not break

The entire planning pipeline assumes that `goal_plan["session_templates"]` is a list with exactly one entry per day, index-aligned with `goal_plan["daily_plan"]` (both length seven times the number of weeks). Concretely, near-term editing reads and writes by position, for example `session_templates[day_index]` and `session_templates[day_index] = next_template` in `models/planning_near_term.py` (around lines 384, 452, 995, 1105). Intervals delivery walks `daily_plan` by index and reads `templates[index]`, raising `ValueError` if `template["date"]` does not equal that day (`models/intervals_workout_delivery.py` around lines 157-166), and it expects exactly one `session_id` per day. Checkpoint restore pairs `daily_plan` and `session_templates` positionally (`models/planning_checkpoints.py` around line 362); reconciliation, session identity, readiness conflicts, the Today snapshot, the dashboard summary, coach tools, and the session-quality forecast all iterate `session_templates` as one-per-day.

Therefore multiple sessions per day are represented WITHIN the single day-indexed template, not as extra top-level list entries. A flat list with several templates sharing a date would break roughly fifteen consumers at once.

## Design: one day slot, several sessions

A day template keeps its single slot in `session_templates` and gains an ordered `sessions` list. Each element of `sessions` is a fully materialized session for one discipline on that day, in deterministic order, and it is the unit of truth. The following rules are mandatory and are what the milestones implement.

Each session owns a stable `session_id`. Position in the `sessions` array is never identity; editing, delivery, reconciliation, and fingerprinting address a session by its `session_id`. `models/session_identity.py` assigns and preserves these ids per session.

The day-level scalar fields (`sport`, `session_role`, `duration_minutes`, `materialized_steps`, `target_provenance`, `structure_status`, and so on) become a computed projection of `sessions[0]`, never a second mutable source of truth. Any code that needs to change a day changes a session inside `sessions` and then re-projects; nothing writes the day scalars independently. This keeps `sessions[0]` the primary that legacy, not-yet-taught consumers observe.

`day.total_tss` (the second element of each `daily_plan` tuple) and the weekly per-sport buckets (`weekly_summary[i]["bike"|"run"|"swim"]`) are computed only as the sum of the materialized sessions. They are never taken from the pre-collapse blended `parts`. This is what makes the weekly table equal the export by construction, and it is enforced by the anchor test.

Old checkpoints migrate on read. When `restore_goal_plan_from_checkpoint` loads a checkpoint whose day templates have no `sessions` key, each single legacy template is wrapped as `sessions=[legacy_session]` so that all downstream code sees the new shape uniformly. Stored historical prescriptions, ids, and fingerprints are preserved unchanged; only the in-memory shape is normalized.

Discipline distribution becomes truthful because each discipline bucket on a day that clears a minimum threshold becomes its own session carrying its own share of the day's TSS, not the whole day. Very small buckets are folded into the nearest larger session on that day by a deterministic, tested rule so we never emit a physiologically meaningless three-minute swim; the folded discipline's TSS still counts toward the session it merges into, so the daily total is conserved.

A brick is not two arbitrary same-day sessions. Brick legs are sessions that share an explicit `group_id`, carry a `leg_index`, and preserve discipline order (bike then run), keeping the parent and leg load, transition, and identity invariants established in #173. Delivery and rendering treat a `group_id` as one coupled workout expressed as ordered legs.

Warm-up and cool-down obey a single minimum bookend contract of five minutes each, shared by Workout Catalog v2 and this planner, with an explicit exception for very short `activation` sessions, whose bookends may be shorter because the session itself is only a brief sharpening effort. The contract is a constant with a named exception, not an unconditional five minutes and not the current ad hoc three to four and a half minute bookends.

Race load participates in the CTL and ATL forecast so the load model reflects the effort of racing, but the athlete's own race event is sacred: a protected race day is never turned into a deliverable AI Trainer workout and the athlete's existing provider race event is never overwritten. The forecast TSS feeds the load simulation and the weekly accounting; it does not create a delivered session.

## Context and Orientation

`models/training_planner.py` owns weekly-to-daily expansion (`expand_weekly_to_daily_triathlon`), the day and session builder (`build_daily_session_templates`), the race overlay (`apply_race_event_overlays`), and `_dominant_sport`. `models/workout_catalog.py` owns immutable workout definitions, per-sport materialization, brick construction (`materialize_brick_session`), and `prepare_weekly_brick_allocations`, which currently disables all bricks whenever the current `load_state` is `deep_fatigue`. `api/planning_service.py::build_plan` assembles the goal plan, applies overlays, materializes templates, builds the preview, and optionally appends a checkpoint. Delivery to Intervals.icu is `models/intervals_workout_delivery.py`; the Today surface is `api/today_snapshot.py`; near-term editing is `models/planning_near_term.py`; persistence and restore are `models/planning_checkpoints.py`; identity is `models/session_identity.py`; the web planning and Today pages are under `web/app`.

## Milestones

Milestone one establishes the guard rail before touching behavior, and it is complete. `tests/smoke/test_plan_discipline_truth.py` builds a real-shaped twelve-week triathlon plan and asserts that, per discipline, the weekly summary equals the sum of the TSS across every exported session for that discipline, within one decimal, and that no session has a non-positive duration. It expresses the exported load in a way that is identical before and after the fix by reading the `sessions` list when present, the composite brick `legs` otherwise, and the single collapsed session as a last resort. The test fails RED today (evidence under Surprises & Discoveries). Commit it alone so the TDD order is inspectable.

Milestone two introduces the nested `sessions` model end to end while keeping behavior identical, so no intermediate commit leaves the model half-understood by the system. Following the reviewer's instruction, the teaching of checkpoint, delivery, Today, and the near-term editor is done vertically here rather than deferred. In this milestone every day still has exactly one discipline, so `sessions` has length one and equals the current single session, but the whole stack now speaks `sessions`: `build_daily_session_templates` emits `sessions=[primary]` with a per-session `session_id`; the day scalars stay a projection of `sessions[0]`; `restore_goal_plan_from_checkpoint` wraps legacy single templates as `sessions=[legacy_session]`; delivery emits one event per session with `session_id` inside the `external_id`; the Today snapshot and dashboard list sessions; and near-term editing addresses a session by `session_id` while still locating the day by index. Contributor-safe smoke stays green because behavior is unchanged. The weekly per-sport buckets are deliberately NOT yet derived from sessions in this milestone (see the Decision Log): while days are still collapsed onto one dominant sport, deriving the table from sessions would make the table itself collapse and the anchor pass trivially on a bad plan.

Milestone three makes executable sessions the single truth for distribution (Issue item 1). `build_daily_session_templates` splits each day's blended `parts` into one session per discipline above the minimum-TSS and minimum-duration threshold, materializes each session through the Catalog v2 path, and stops attributing the entire day to one sport. A discipline bucket too small for its own session on a day must never be silently re-glued onto the dominant sport (turning `{bike:15, run:10, swim:5}` into `{bike:20, run:10}` invisibly is forbidden). The only permitted resolutions are: emit a short session of the same discipline; merge the fragment into another session of the same discipline within the week; or record an explicit allocation/rebalance entry with a reason that is surfaced in the preview. The default is same-discipline preservation, which keeps the per-discipline sport budget conserved exactly, so the three-way anchor holds without any recorded rebalance. Simultaneously the `daily_plan` totals and the `weekly_summary` per-sport buckets are recomputed as the sum of the materialized sessions (deferred here from milestone two so the weekly table cannot collapse before the split).

Milestone three is a single atomic vertical landing: the split, the recomputed weekly buckets, per-session content fingerprints for `session_id` (guardrail two), the near-term editor addressing a specific `session_id` instead of blind-replacing the whole day, and the web rendering of every session all arrive together. There must never be an intermediate committed state where `sessions` already holds several trainings on a day but the editor still silently replaces the day or a consumer counts only one session. The milestone is complete only when all six of the following hold at once: the discipline split is correct; the editor edits by `session_id`; every session is displayed in order (brick legs separately, rest/race not shown as training); `tests/smoke/test_plan_discipline_truth.py` is GREEN; the total plan TSS is still conserved at 4624.1 on both sides; and the delivery identities (`session_id` and `external_id`) of legacy one-session-per-day plans are unchanged, verified by a regression test that a pre-split plan's delivery events are byte-identical before and after this milestone. At the end `tests/smoke/test_plan_discipline_truth.py` passes with a genuinely balanced plan and the weekly table equals the export.

Milestone four gives race lead-up its real structures and removes invalid fallbacks (Issue items 2 and 3). It adds deterministic `activation` prescriptions for bike and run to `models/workout_catalog.py` so an `activation` role materializes short structured sharpening instead of an empty or dominant-sport block, audits the seven currently unstructured days (a long day, four activations, two over-heavy Recovery Spins) so each materializes a valid structure or fails closed to an explicitly simpler valid session, and applies the five-minute bookend contract with the short-activation exception.

Milestone five represents bricks correctly and bounds their suppression (Issue items 4 and the brick condition). Brick legs become grouped sessions with `group_id`, `leg_index`, and bike-then-run order inside the day's `sessions`. `prepare_weekly_brick_allocations` is changed so `deep_fatigue` removes bricks only within the seven-day readiness horizon already used by #202 (measured from the build's `as_of`), leaving September Peak-block bricks intact.

Milestone six gives races a forecast load without ever delivering or overwriting them (Issue items 5 and the race condition). Where `apply_race_event_overlays` sets the race day to zero, it instead records a bounded forecast training load for A and B races that flows into the CTL and ATL simulation and the weekly accounting, while the race day stays protected, is not materialized as a deliverable session, and never overwrites the athlete's provider race event.

Milestone seven proves the whole plan end to end and finishes the surfaces. It completes web rendering of multiple sessions per day, runs focused tests, contributor-safe smoke, broad non-live tests, Next lint and build, and the sixteen-week latency guard, and, only if the athlete explicitly authorizes a real write, runs a sanitized isolated provider probe verifying that a multi-session day produces the expected multiple parsed events and then deletes them with zero residue.

## Decision Log

- Decision: represent multiple sessions per day nested inside the single day-indexed template (`sessions` list), not as extra top-level `session_templates` entries. Rationale: near-term editing, Intervals delivery, and checkpoint pairing are strictly positional one-per-day; a flat multi-entry list would break roughly fifteen consumers at once. Date/Author: 2026-07-15 / Claude Code.

- Decision: each session carries a stable `session_id`; array position is not identity. Editing, delivery, reconciliation, and fingerprints address sessions by id. Rationale: reordering or inserting a session must not silently retarget another session's delivery or history. Date/Author: 2026-07-15 / Greg.

- Decision: day-level scalar fields are a computed projection of `sessions[0]`; `day.total_tss` and weekly per-sport buckets are computed only from the materialized sessions. Rationale: one source of truth removes the exact divergence this issue is about and makes the anchor invariant hold by construction. Date/Author: 2026-07-15 / Greg.

- Decision: old checkpoints migrate on read into `sessions=[legacy_session]`; stored prescriptions, ids, and fingerprints are unchanged. Rationale: downstream code sees one shape without rewriting history. Date/Author: 2026-07-15 / Greg.

- Decision: delivery creates one event per session with `session_id` inside the protected `external_id`, and bricks carry `group_id`, `leg_index`, and bike-then-run order. Rationale: multi-session days must deliver as distinct idempotent events, and a brick is one coupled workout, not two coincidental sessions. Date/Author: 2026-07-15 / Greg.

- Decision: race forecast load feeds CTL and ATL and weekly accounting but never becomes a deliverable session and never overwrites the athlete's provider race event. Rationale: the athlete's own race is authoritative; AI Trainer models its load without impersonating or mutating it. Date/Author: 2026-07-15 / Greg.

- Decision: the bookend contract is five minutes each for warm-up and cool-down with an explicit exception for very short `activation` sessions. Rationale: an unconditional five-minute floor would make legitimate brief activations infeasible; the #203 review also found the repeat builder guaranteed only ten minutes combined split 55/45. Date/Author: 2026-07-15 / Greg.

- Decision: teach checkpoint, delivery, Today, and the editor about `sessions` vertically in Milestone two rather than deferring to the end. Rationale: intermediate commits must never leave the new model half-understood by the system. Date/Author: 2026-07-15 / Greg.

- Decision: derive `daily_plan` totals and `weekly_summary` per-sport buckets from the materialized sessions only in Milestone three, together with the day split, not in Milestone two. Rationale: in Milestone two each day is still collapsed onto one dominant sport; deriving the weekly table from sessions while collapsed would make the table itself show the collapsed distribution and the anchor test would pass trivially on a ninety-percent-bike plan. Deferring the derivation to the same milestone as the split keeps the anchor honest — it turns green only when the plan is genuinely balanced. Date/Author: 2026-07-15 / Claude Code.

- Decision (guardrail): the discipline invariant and delivery both count executable leaf sessions, never one composite brick parent. A brick contributes its bike and run legs to the per-discipline sums and produces one provider event per leg, so "one event per session" is unambiguous: a leaf is either a single-discipline session or one brick leg. The anchor helper already descends into `legs`, and delivery already emits per-leg; teaching delivery to read `sessions` must preserve this. Date/Author: 2026-07-15 / Greg.

- Decision (guardrail): a session's `session_id` is derived from its material content (date, sport, role, focus, TSS, steps), not from its position in the `sessions` array. Two identical-discipline sessions on the same day are disambiguated by an occurrence ordinal assigned in a canonical content order, so reordering the array never changes the set of identities and never retargets a session's delivery or history. Milestone three implements per-session fingerprints with this rule when days actually split; in Milestone two the single session inherits the day identity. Date/Author: 2026-07-15 / Greg.

- Decision (guardrail): Milestone three is atomic. The day split and the near-term editor's switch to `session_id` addressing land in the same vertical commit, because a state where `sessions` holds several trainings while the editor still blind-replaces the whole day would silently corrupt a day. Today and dashboard display are taught the leaf-session read model earlier (Milestone 2.6, read-only and safe), but the visible web rendering and the editor change land with the split. Milestone three also carries a regression test proving legacy one-session-per-day plans keep identical `session_id` and `external_id` delivery identities. Date/Author: 2026-07-15 / Greg.

- Decision: race and rest days carry `sessions == []` and are never delivered as AI Trainer sessions. In Milestone six the race's forecast TSS feeds the CTL/ATL load model and weekly accounting only; it never becomes an executable or deliverable session and never overwrites the athlete's own provider race event. Date/Author: 2026-07-15 / Greg.

- Decision (guardrail): the discipline anchor is a three-way invariant, not a two-way one. Once `weekly_summary` is derived from `sessions` in M3, asserting only `weekly == sessions` would pass by construction even for a mis-allocated split. The anchor therefore also asserts equality with the per-discipline sport budget taken from `daily_plan` parts (the split's input, which the split cannot rewrite): `budget == materialized leaf sessions == weekly_summary` per discipline, plus a total of 4624.1. This landed before M3 so M3 cannot be made green by following bad sessions. Date/Author: 2026-07-15 / Greg.

- Decision (guardrail): the sub-threshold fold preserves discipline. A discipline fragment too small for its own daily session is resolved by a short same-discipline session, a merge into another same-discipline session that week, or an explicit recorded allocation/rebalance surfaced in the preview — never a silent move of load onto the dominant sport. Same-discipline preservation is the default, so the sport budget is conserved exactly and the three-way anchor needs no rebalance term. Date/Author: 2026-07-15 / Greg.

- Decision: build on top of merged #202 and #203 rather than folding into those drafts. Rationale: both are correct within scope and independently reviewed green; this defect is a separate, largely pre-existing week-day boundary problem and deserves its own reviewable slice. Date/Author: 2026-07-15 / Greg + Claude Code.

## Progress

- [x] (2026-07-15) Confirmed #202 and #203 are merged into `main`; cut worktree branch `claude/issue-205-discipline-distribution` from `origin/main`; opened Issue #205.
- [x] (2026-07-15) Milestone one: added `tests/smoke/test_plan_discipline_truth.py` and recorded the RED anchor failure (see Surprises & Discoveries).
- [x] (2026-07-15) Milestone two: nested `sessions` model end to end, behavior-preserving; 691 passed, only the intentional anchor RED (M2-checkpoint reached).
    - [x] (2026-07-15) M2.1 `build_daily_session_templates` emits `sessions[]` additively; 688 other smoke tests green.
    - [x] (2026-07-15) M2.2 per-session identity on `sessions[0]`, day id a projection, no churn; 689 green, new identity test.
    - [x] (2026-07-15) M2.3 `ensure_session_identities` migrates legacy templates on read to `sessions=[legacy_session]`; 690 green, migration test.
    - [x] (2026-07-15) M2.4 delivery emits one event per leaf session (single session or brick leg), `session_id` in `external_id`; delivery smoke green.
    - [x] (2026-07-15) M2.5 editor consistency: an edited day rewritten without `sessions` is re-wrapped by the M2.3 migration at the edit flow's re-identity (planning_near_term.py:1340). Explicit edit-by-`session_id` lands atomically with the split in M3.
    - [x] (2026-07-15) M2.6 `iter_leaf_sessions` read model; Today snapshot and dashboard expose ordered leaf sessions (brick legs separate, rest/race none); 691 green, synthetic two-session and brick test.
- [ ] Milestone three (atomic): discipline split + weekly buckets from sessions + per-session content ids + editor edit-by-`session_id` + web display; anchor GREEN, 4624.1 conserved, legacy delivery identities unchanged.
- [ ] Milestone four: activation structures, fallback cleanup, bookend contract with activation exception.
- [ ] Milestone five: bricks as grouped ordered sessions; deep-fatigue brick suppression bounded to seven days.
- [ ] Milestone six: A/B race forecast load into CTL/ATL, never delivered or overwritten.
- [ ] Milestone seven: web multi-session rendering; full validation; optional sanitized provider probe.

## Surprises & Discoveries

- Observation: the pipeline is strictly one-template-per-day and positional. Evidence: `models/planning_near_term.py` assigns `session_templates[day_index] = next_template`; `models/intervals_workout_delivery.py` reads `templates[index]` and raises `ValueError` when `template["date"]` differs from `daily_plan[index]`'s date. This forced the nested-`sessions` representation over a flat list.

- Observation: the divergence root cause is two lines. Evidence: `build_daily_session_templates` picks `_dominant_sport(parts)` (training_planner.py:1891) and materializes with `target_tss=float(total or 0.0)` (line 1911), attributing the entire blended day to one discipline.

- Observation: the anchor test reproduces the live finding at the smoke level. Evidence, from the RED run of `tests/smoke/test_plan_discipline_truth.py`:

        AssertionError: discipline bike: weekly table 2054.4 != exported sessions 3953.2
        (full table={'bike': 2054.4, 'run': 1685.3, 'swim': 884.4},
         full exported={'bike': 3953.2, 'run': 411.6, 'swim': 259.3})

  The weekly table is a balanced triathlon while the exported sessions are about eighty-five percent bike, matching the reported 90/7/3 split.

- Observation: total TSS is conserved on both sides of the divergence, which proves the defect is re-labelling load onto the dominant sport rather than losing data. Evidence: in the RED run above the weekly table and the exported sessions both sum to 4624.1 TSS. The anchor test now asserts this conservation explicitly, before the per-discipline comparison.

- Observation: deriving the weekly buckets from sessions too early would make the anchor pass on a bad plan. Evidence: during Milestone 2.2 it became clear that if the weekly table were computed from the still-collapsed one-session-per-day, both sides of the anchor would collapse to about ninety percent bike and the equality would hold trivially. The derivation was therefore moved to Milestone three, alongside the split (see Decision Log).

- Observation: even after that deferral, a two-way anchor (`weekly == sessions`) would still pass by construction once weekly is derived from sessions in M3, because a wrong split would corrupt both sides identically. Evidence: the strengthened three-way anchor now pins both to the parts budget: `budget={'bike':2054.4,'run':1685.3,'swim':884.4}` equals `table` today while `exported={'bike':3953.2,'run':411.6,'swim':259.3}` fails against the budget. Because the budget is read from `daily_plan` parts and never from sessions, M3 must produce a correct split to turn it green.

## Outcomes & Retrospective

Pending implementation. This section will summarize what was achieved, what remains, and lessons learned at completion.

## Validation and Acceptance

Acceptance is behavioral. After Milestone three, building a twelve-week triathlon plan and comparing the weekly summary to the per-session export shows equal per-discipline totals and `tests/smoke/test_plan_discipline_truth.py` passes. After Milestone seven, delivering a preview to a copied database (never the real provider unless explicitly authorized) yields one event per session, multi-discipline days produce multiple events, bricks deliver as ordered grouped legs, and races carry non-zero forecast load without a delivered race session. The full command set is `python -m pytest tests/smoke -q`, `python -m pytest -m "not live and not debug" tests/ -q`, and `cd web && npm run lint && npm run build`, all green, with the sixteen-week latency guard remaining under its four-second bound.
