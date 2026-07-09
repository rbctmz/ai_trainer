# Persist prioritized race events

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds. It follows `.agent/PLANS.md`.

## Purpose / Big Picture

Athletes can have a primary race and intermediate races. After this change every plan records races as an extensible `events` list, and the system derives the existing `event_date` field from that list. A plan built in the web UI, legacy Streamlit UI, or by a coach proposal will therefore retain an A-priority race event through checkpoint save, restore, and execution replanning. The coach can inspect every stored event and see its priority.

The observable proof is a smoke test that creates an A/B/C event list, saves and restores it, and verifies that the primary event remains the A event. A legacy checkpoint with only `event_date` restores with a synthesized A event, so existing athletes keep working.

## Progress

- [x] (2026-07-09 19:30Z) Read issue #138, the post-#144 compatibility decision, and the planning/checkpoint/coaching data flow.
- [x] (2026-07-09 19:30Z) Created branch `codex/issue-138-race-events` from updated `main` and wrote this ExecPlan.
- [x] (2026-07-09 19:38Z) Added behavior tests first; the initial run failed at collection because `models.plan_events` did not yet exist.
- [x] (2026-07-09 19:43Z) Implemented shared event normalization and the primary-event alias rule.
- [x] (2026-07-09 19:43Z) Threaded events through API and Streamlit creation, checkpoint serialization/restore, current-plan resolution, execution replan, and the coach payload/formatter.
- [x] (2026-07-09 19:45Z) Updated the web response type; `web/npm run build` passed.
- [x] (2026-07-09 19:51Z) Added direct coach-proposal coverage and completed self-review; focused tests passed (83 passed) and the final smoke suite passed (440 passed, 1 skipped).
- [ ] Commit, push, and create a draft PR that closes #138.

## Surprises & Discoveries

- Observation: planning checkpoints store their full plan in the JSON `goal_plan_snapshot`; adding `events` there needs no SQLite schema migration.
  Evidence: `data/database.py` serializes the complete checkpoint dictionary with `json.dumps`, and `models/planning_checkpoints.py` controls the snapshot fields.
- Observation: execution replan rebuilds a goal-plan dictionary instead of mutating the original one.
  Evidence: `models/planning_execution.py:1230` explicitly copies `event_date`; it must copy the new `events` field too.
- Observation: the web build request still has one date input, so v1 can create exactly one A event without adding a new UI control.
  Evidence: `web/app/planning/page.tsx` posts only `event_date` to `/api/planning/build`.
- Observation: Streamlit may use the live `StateManager.goal_plan` without a checkpoint restore, via `resolve_goal_plan_context`.
  Evidence: `state/manager.py` calls that resolver. It now applies the same normalization so the source-of-truth rule holds in the live legacy path too.

## Decision Log

- Decision: `events` is the source of truth and `event_date` is always derived from `primary_event(events)`.
  Rationale: a duplicate, independently editable date would make the old and new representations disagree.
  Date/Author: 2026-07-09 / Codex, from the agreed issue #138 design.
- Decision: `primary_event` selects the highest priority (`A`, then `B`, then `C`); ties select the chronologically earliest valid date.
  Rationale: this makes a lone B or C event safe for future API/import users and gives a deterministic alias without relying on UI restrictions.
  Date/Author: 2026-07-09 / Codex, from the agreed post-#144 design.
- Decision: v1 keeps the existing one-date web and Streamlit forms and creates one A event with a derived goal label; multi-event editing and B/C selection are deferred.
  Rationale: the persistence contract is useful now, while a priority picker that does not yet change periodization would be misleading.
  Date/Author: 2026-07-09 / Codex, from the agreed post-#144 design.
- Decision: a restored legacy plan with a valid `event_date` and no usable events gets one synthesized A event; a plan with neither remains eventless.
  Rationale: it preserves old checkpoints without inventing a race date where none was stored.
  Date/Author: 2026-07-09 / Codex.

## Outcomes & Retrospective

The implementation is complete pending publication. It adds no database migration and leaves periodization based on the compatibility alias. Multi-event editing and B/C-specific periodization remain deliberately out of scope.

Self-review found that the legacy live `StateManager` path obtains an in-memory plan through `resolve_goal_plan_context`; that resolver now applies the same synchronization as checkpoint restore. Writers construct an A event before persisting, checkpoint serialization synchronizes again defensively, and execution replanning carries the list before recalculating the alias. Invalid date/priority input cannot become primary; no valid event plus no legacy date remains eventless, which preserves the behaviour of the oldest checkpoints. The only intentional scaling boundary is that current periodization still reacts to the derived primary alias, not B/C events.

## Context and Orientation

`api/planning_service.py` is the shared production plan builder used by the FastAPI endpoint and coach plan proposals. It currently accepts one `event_date`, builds a `goal_plan`, persists a checkpoint, and returns a `goal` API payload. `web/app/planning/page.tsx` is the primary UI and sends that date; `web/lib/types.ts` declares its response type. `ui/pages/planning.py` is the legacy Streamlit fallback; its `_build_initial_goal_plan_payload` builds the equivalent plan dictionary.

`models/planning_checkpoints.py` turns a `goal_plan` into a compact checkpoint dictionary and restores it. The nested `goal_plan_snapshot` is the durable representation. `models/planning_execution.py` rebuilds a plan after completed or missed work. `models/ai_tools.py` restores the active plan and exposes it to the coach. `ui/components/ai_coach_output.py` formats that tool result for people.

An event is a dictionary with exactly these public fields: `date` (a `YYYY-MM-DD` string), `priority` (`A`, `B`, or `C`), and `label` (a human-readable string). The primary event is the deterministic event chosen for compatibility aliases: first by priority A/B/C and then by earliest calendar date. `event_date` remains in all existing consumers, but is not separately authoritative.

## Behavior Scenarios

    Given events B on 2026-07-10, A on 2026-09-01, and A on 2026-08-20
    When the system selects the primary event
    Then it selects the A event on 2026-08-20
    And event_date is 2026-08-20

    Given a checkpoint created before this change with event_date 2026-08-10 and no events
    When the plan is restored
    Then its events list contains one A event dated 2026-08-10
    And event_date stays 2026-08-10

    Given a future importer provides one valid B event and no A event
    When the plan is normalized or restored
    Then the B event is primary
    And event_date is its date

    Given a user builds a plan through the web UI, Streamlit fallback, or coach proposal
    When the plan is produced
    Then it contains one A event whose date equals the submitted event_date
    And the saved checkpoint and active coach payload expose that event

    Given an execution replan is saved
    When it rebuilds the original goal plan
    Then it preserves the full events list and recomputes event_date from it

## Plan of Work

First add `models/plan_events.py`, a small shared domain module. It will normalize valid event dictionaries, create the default A event, select `primary_event(events)`, and return a copied goal plan whose `events` list and `event_date` alias agree. Invalid dates or priorities will not become primary events; if no valid events remain, a valid legacy `event_date` becomes a synthesized A event. The module will not calculate periodization or add an input API.

Next make every writer call the shared rule. `api/planning_service.py` will create an A event from the existing submitted date and include the list in the API `goal` result. `_build_initial_goal_plan_payload` in `ui/pages/planning.py` will use the same helper. `models/planning_execution.py` will preserve events as it rebuilds a plan and synchronize the alias. Coach proposals already use `api/planning_service.build_plan`, so they inherit the behavior.

Then update `models/planning_checkpoints.py`. Checkpoint creation will snapshot normalized `events` and the derived alias. Checkpoint-to-plan restoration will normalize the snapshot and synthesize an A event from legacy `event_date`. This keeps `resolve_goal_plan_context`, full restore, and all downstream callers compatible. No database migration is needed because the checkpoint is JSON.

Finally, `models/ai_tools.py` will return normalized events in `get_active_plan`, and `ui/components/ai_coach_output.py` will render each event as priority, label, and date. `web/lib/types.ts` will explicitly declare `RaceEvent` and expose the events list under `BuiltPlan.goal`; the web page still supplies one A event only.

Tests will be added before each corresponding implementation. They will assert public behavior rather than the internal helper layout: selection rule, checkpoint round trip and legacy synthesis, execution-replan preservation, initial builder output, plan-builder API output, coach payload, and rendered priority. The full smoke suite and the Next.js build will validate Python and web contracts.

## Concrete Steps

Run all commands from `/Users/gregkisel/Developer/ai_trainer`.

1. Add tests first in `tests/smoke/test_plan_events.py` and extend the focused existing smoke modules where they already own a behavior. Run the new tests before implementing and expect assertion/import failures.
2. Add `models/plan_events.py`, then run:

       ./ai_trainer_env/bin/python -m pytest tests/smoke/test_plan_events.py -q

   Expect all primary-selection and legacy-synthesis assertions to pass.
3. Thread the shared helpers through the API/service, legacy payload, checkpoints, execution replan, and coach output. Run:

       ./ai_trainer_env/bin/python -m pytest tests/smoke/test_plan_events.py tests/smoke/test_planning_checkpoint_history.py tests/smoke/test_api_planning.py tests/smoke/test_ai_tools_plan.py tests/smoke/test_ai_coach_output.py tests/smoke/test_planning_page_explainability.py -q

4. Verify all repository-safe tests and the response type contract:

       ./ai_trainer_env/bin/python -m pytest tests/smoke -q
       cd web && npm run build
       git diff --check

5. Review the diff for hidden event-date writers, update this plan's living sections, commit the scoped changes, push `codex/issue-138-race-events`, and open a draft PR with `Closes #138`.

## Validation and Acceptance

Acceptance is complete when a new plan returns `goal.events` with one `{date, priority: "A", label}` entry and an equal `goal.event_date`; the persisted checkpoint snapshot carries the same list; restoring it returns the same list; and an execution adjustment keeps it. A checkpoint without events but with `event_date` must restore a synthesized A event. A manually supplied singleton B event must become primary so future clients cannot produce an undefined alias. The active-plan coach result must include the list, and its formatted output must visibly show at least `A`/`B`/`C` priority alongside the event.

The Python smoke suite must pass. Because `BuiltPlan.goal` gains a typed `events` field, `web/npm run build` must pass as well. The expected smoke count will be recorded after the run; one local-listening-socket skip is acceptable in this execution environment.

## Idempotence and Recovery

The helper only copies dictionaries and normalizes values, so checkpoint restoration can run repeatedly without adding duplicate synthesized events: synthesis occurs only when there is no valid event and a legacy date exists. Existing SQLite checkpoint rows are not rewritten during reads. If a test run fails, correct the failing behavior and rerun the focused command. If the branch needs to be abandoned, no database migration needs rollback; delete the branch only after preserving any desired commits.

## Artifacts and Notes

The new public shape is:

    {
      "events": [
        {"date": "2026-08-20", "priority": "A", "label": "Триатлон Олимпийка"},
        {"date": "2026-07-10", "priority": "B", "label": "Контрольный старт"}
      ],
      "event_date": "2026-08-20"
    }

The second event is accepted by the shared model and payload even though v1 UI does not yet create it. Periodization still consumes `event_date`, which now identifies the deterministic primary event.

## Interfaces and Dependencies

Add `models.plan_events.primary_event(events: Any) -> dict[str, str] | None`. It returns a normalized copy of the highest-priority, earliest event, or `None` for no valid event. Add `build_primary_event(date_value: Any, label: str) -> dict[str, str] | None` for v1 writers. Add `synchronize_goal_plan_events(goal_plan: dict[str, Any]) -> dict[str, Any]`; it returns a copy with normalized `events` and `event_date` derived from the primary event, synthesizing an A event from a valid legacy alias when necessary.

`api.planning_service.build_plan` keeps its existing arguments. Its returned `goal` gains `events: list[dict[str, str]]`. `AITools.get_active_plan` gains a top-level `events: list[dict[str, str]]`. `web/lib/types.ts` exports `RaceEvent` and adds `events: RaceEvent[]` to `BuiltPlan.goal`. No new packages, database columns, or UI controls are required.

Plan revision 2026-07-09 19:30Z: created after repository and issue analysis; records the agreed v1 scope and compatibility rules before test-first implementation.

Plan revision 2026-07-09 19:45Z: recorded implemented paths, focused/full/build evidence, and the additional live-StateManager normalization discovered during self-review.

Plan revision 2026-07-09 19:51Z: recorded final acceptance evidence: 83 focused tests, 440 smoke tests with one environment-limited skip, and a successful Next.js production build.
