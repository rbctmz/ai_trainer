# Reassign an unplanned activity to the current planned session

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds. This document must be maintained in accordance with `.agent/PLANS.md`.

## Purpose / Big Picture

An athlete can see a completed activity under “Вне плана” even when it is the fact for an unmatched planned session on the same date. After this change, the athlete can select that current planned session in the web planning screen, choose the role that was actually performed, and explicitly confirm the pair. If an old inactive session identity still reserves the activity, the append-only match ledger records the current confirmation as its successor instead of rejecting the correction or rewriting history.

The production-shaped acceptance case is a 2026-08-31 bike activity with 51.8 TSS and a current bike quality session with 60.4 planned TSS. The old confirmation points to an inactive nested session from checkpoint 128, while checkpoint 132 contains a different current parent session. Tests use sanitized temporary SQLite databases; development does not write the athlete database.

## Progress

- [x] (2026-09-04 12:38 MSK) Created issue #531 with Class A acceptance criteria and non-goals.
- [x] (2026-09-04 12:39 MSK) Reproduced the backend rejection on a SQLite backup: explicit current-target confirmation raised `one or more activities are already matched to another planned session`.
- [x] (2026-09-04 12:43 MSK) Created this ExecPlan and the Class A slice spec.
- [x] (2026-09-04 12:47 MSK) Added backend and web contract RED tests on sanitized temporary fixtures; the intended pre-change run reported five failures and one active-owner boundary pass.
- [ ] Implement bounded inactive-target reassignment in the existing match endpoint.
- [ ] Implement the `/planning` “Сопоставить” control for unplanned activities.
- [ ] Run focused, contract, web, broad, and lint validation; complete self-review.
- [ ] Publish a PR and obtain one consolidated independent review without merging.

## Surprises & Discoveries

- **Observed**: the 2026-08-31 activity is returned by the live read-only reconciliation endpoint as unplanned, while the same response contains one unmatched current session with the same date and sport.
  **Inferred**: the web list alone cannot recover the match because the activity may still be reserved by an older target. The cheapest falsifier is to call the production writer against a SQLite backup.
  **Verified by**: `record_plan_actual_match` against `/tmp/ai_trainer_match_diag.db` raised `one or more activities are already matched to another planned session`; no live write was made.

- **Observed**: the old match target is the checkpoint-128 nested bike id `ats_f6987bb48aa48bb99bae7cd2`, while the current checkpoint-132 parent is `ats_9f00d3bdbda089e1a6159b30` and names only day-level predecessor `ats_ed3deb7cb9dcace65d7840d5`.
  **Inferred**: #530's bounded one-hop resolver correctly cannot infer this cross-grain historical chain. A current explicit user correction needs a separate stale-owner rule rather than broader automatic inheritance.
  **Verified by**: read-only SQLite JSON queries showed the distinct nested, day-level, and current ids; checkpoint 132 predates merge commit `5ed37bd`.

## Decision Log

- Decision: Keep automatic reconciliation fail-closed and add an explicit correction path.
  Rationale: the user is choosing exact evidence; silently broadening historical lineage could assign the wrong activity.
  Date/Author: 2026-09-04 / Codex.

- Decision: A stale owner is reassignable only when it is a latest matched `user_confirmed` or `admin_resolve` row, its target session is absent from the active plan, all activities selected by that stale row are included in the new confirmation, and there is at most one such stale owner.
  Rationale: this preserves grouped matches and the single-parent `supersedes_match_id` lineage. Active targets, partial group moves, and multiple stale owners fail closed.
  Date/Author: 2026-09-04 / Codex.

- Decision: Reuse `POST /api/planning/reconciliation/matches`; do not add a request field or new endpoint.
  Rationale: the request already names the current session, exact activity ids, actual role, action, and base checkpoint. Only the server-side conflict classification and web reachability are missing.
  Date/Author: 2026-09-04 / Codex.

## Outcomes & Retrospective

Implementation is not complete. The intended outcome is a current-target append-only confirmation reachable from the web UI, with no checkpoint rewrite, schema migration, automatic backfill, cross-date match, or Streamlit change.

## Context and Orientation

`models/plan_actual_reconciliation.py` builds the read-only plan-versus-actual response. Its `unplanned_activities` collection contains completed activities not claimed by an effective current reconciliation row. `api/planning_service.py::record_plan_actual_match` is the domain write boundary behind `POST /api/planning/reconciliation/matches`; it validates the active checkpoint, session, activity date, conflicts, role, and append-only predecessor link. `data/database.py::save_plan_actual_match` appends revisions, and `get_plan_actual_match_for_activity` resolves effective lineage leaves.

`web/app/planning/page.tsx::AdjustMode` renders the reconciliation table and the unplanned warning. Row-level candidate confirmation already calls the match endpoint, but the top-level unplanned list is display-only. `web/lib/types.ts::ReconResponse` already contains all fields needed for a same-date selector, so the public TypeScript and API DTO shapes can remain unchanged.

This work affects ASR-REL-1 because a completed activity must remain recoverable through plan identity changes, and ASR-REL-2 because uncertain or conflicting evidence must fail closed. ADR-0001 requires the product flow in API/shared Python plus web, not Streamlit. ADR-0006's append-only planning/evidence model forbids rewriting the historical match.

## Plan of Work

First add a focused smoke module. Build a current plan with one session and save a sanitized activity. Save an explicit old match under a session id absent from the current plan. The happy-path RED calls `record_plan_actual_match` for the current session and expects a new current row whose `supersedes_match_id` points at the stale row, reconciliation to report the current match, and the activity lookup to resolve the new row. Boundaries must keep an active other-session owner as a conflict, reject a partial move from a grouped stale match, reject activities spanning multiple stale owners, retain cross-date rejection, and preserve idempotent retry behavior.

Add a source-level web contract test that requires an unplanned activity control, a same-date target filter, exact activity-id submission, an actual-role selector, and explanatory no-target state. This test is intentionally behavioral at the product wiring boundary and must fail before the UI edit.

In `api/planning_service.py`, classify matched explicit owners of requested activities. Exclude the target's own current row and the valid one-hop predecessor already supported by #530. Any owner whose session id is present in the active plan remains a hard conflict. Exactly one inactive explicit owner may become the append-only predecessor only when the request contains its complete selected activity group and the current target has no existing row. Otherwise fail closed with a specific validation error. Use that stale owner as `previous_row`, so the existing fingerprint and database writer append one current-target revision linked to the historical evidence.

In `web/app/planning/page.tsx`, render a small control for each unplanned activity. Eligible targets are unmatched current rows on the same calendar date. The target dropdown identifies the exact planned session and its sport/role; the role dropdown is populated only after a target is chosen and is visibly editable. Confirmation sends exactly the one displayed activity id through the existing `resolveMatch` function. If no same-date unmatched target exists, show a short reason and do not offer a write action. Preserve the existing row candidate flow.

Finally run focused tests, router contracts, reconciliation regressions, contract extraction check, Next lint/build, contributor-safe pytest, Ruff, and `git diff --check`. Inspect the diff for broad historical inference, partial grouped-match retirement, current-owner stealing, stale checkpoint handling, accidental API shape changes, and unrelated files.

## Concrete Steps

Work from `/Users/gregkisel/Developer/ai_trainer` on branch `codex/issue-531-unplanned-match`.

Run the RED module before product code:

    ai_trainer_env/bin/python -m pytest -q tests/smoke/test_issue_531_unplanned_activity_reassignment.py

After implementation, run:

    ai_trainer_env/bin/python -m pytest -q tests/smoke/test_issue_531_unplanned_activity_reassignment.py tests/smoke/test_issue_529_match_handoff.py tests/smoke/test_api_planning.py tests/smoke/test_api_planning_router_contract.py tests/smoke/test_plan_actual_reconciliation.py
    npm --prefix web run contract:extract -- --check
    npm --prefix web run lint
    npm --prefix web run build
    ai_trainer_env/bin/python -m pytest -m "not live and not debug and not e2e" tests/
    ai_trainer_env/bin/python -m ruff check .
    git diff --check

## Validation and Acceptance

The happy-path temporary database begins with an activity claimed by one inactive historical target and a same-date current unmatched session. Before the change, the writer rejects it. After the change, confirmation returns a current `user_confirmed` match linked to the old row, reconciliation removes the activity from `unplanned_activities`, and activity lookup returns only the new effective leaf.

An active other-session owner remains unmodified and the writer returns a conflict. A stale grouped match cannot be partially moved. Activities owned by multiple stale rows cannot be collapsed into one single-parent lineage. An activity on another date is rejected before conflict classification. A stale checkpoint retains the existing 409 mapping at the router.

In `/planning`, each unplanned activity either offers a same-date current target selector plus actual-role confirmation or explains that no eligible planned session exists. The 2026-08-31 bike can target Threshold Intervals. The 2026-08-29 extra bike and 2026-09-02 run are not silently assigned.

## Idempotence and Recovery

Tests use temporary SQLite files and are repeatable. The implementation adds no schema or migration. `save_plan_actual_match` retains its fingerprint idempotency. Reverting the code restores the old conflict behavior; historical rows remain intact because reassignment appends rather than updates or deletes. The live `ai_trainer.db`, its WAL sidecars, and `backups/` are outside development writes.

## Artifacts and Notes

Initial live-read evidence:

    current session = ats_9f00d3bdbda089e1a6159b30
    stale target = session:ats_f6987bb48aa48bb99bae7cd2
    activity = 24182468727
    writer probe on backup = ValueError: one or more activities are already matched to another planned session

RED test transcript:

    5 failed, 1 passed in 0.90s

The happy path and retry failed on the existing generic conflict. The partial-group and multiple-owner tests reached the same generic conflict instead of their new bounded guards. The web test failed because `UnplannedMatchControl` did not exist. The active current-session conflict already passed and is a characterization boundary that must stay green.

## Interfaces and Dependencies

No dependency, schema, request field, response field, configuration, or provider call is added. `record_plan_actual_match` keeps its signature. The existing `MatchCorrectionRequest` and `ReconResponse` contracts remain compatible. The only persistent effect is one ordinary append-only `plan_actual_matches` row whose `supersedes_match_id` points to the reassignable stale owner.

Revision note (2026-09-04): Initial ExecPlan created after issue #531 and the temporary-database falsifier established that both backend conflict classification and web reachability are required.

Revision note (2026-09-04): Recorded the five-failure RED run and the already-green active-owner fail-closed boundary before product implementation.
