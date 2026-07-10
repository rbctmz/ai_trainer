# Close the Recovery Replan loop with an auditable decision log

This ExecPlan is a living document maintained according to `.agent/PLANS.md`. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must remain current while work proceeds.

## Purpose / Big Picture

AI Trainer already computes one canonical readiness signal and detects when that state conflicts with a planned session. The remaining trust gap is operational: the detector result is only attached to Coach chat metadata, so quiet days and data gaps are not measured, and a real conflict does not become a safe action the athlete can inspect. After this change, each unique gate evaluation becomes an auditable recovery decision. A conflict produces one deterministic, bounded proposal that can be confirmed, rejected, or rolled back. Silence and insufficient data remain first-class logged outcomes and never create plan mutations.

The behavior is visible on the web-first product surface. Running the loop during a Coach request adds its result to the SSE meta event. Opening `/decisions` shows recovery decisions with readiness/conflict evidence. A pending recovery proposal appears in the existing confirmation section. The active plan changes only after `Подтвердить`; rejection leaves it untouched, and rollback restores the previous checkpoint as a new version so history is never deleted.

## Progress

- [x] (2026-07-10 13:16Z) Created structured GitHub issue #154 from a clean `main` at `f9a329b`.
- [x] (2026-07-10 13:17Z) Recorded the contributor-safe baseline: `452 passed, 1 skipped`.
- [x] (2026-07-10 13:18Z) Created branch `codex/issue-154-recovery-replan-loop` and audited the gate, decision/proposal tables, planning service, near-term editor, checkpoint provenance, rollback behavior, API, and web Decisions page.
- [ ] Add failing behavior tests for logging, idempotency, proposal generation, approval safety, rejection, and rollback.
- [ ] Implement the recovery decision persistence contract and deterministic domain variant builder.
- [ ] Implement the headless RecoveryReplanLoop and connect it to Coach meta.
- [ ] Extend the existing proposal lifecycle and planning service for recovery apply/rollback.
- [ ] Expose recovery history through the additive Decisions API/web contract.
- [ ] Complete validation, self-review, publication, and draft PR closing #154.

## Surprises & Discoveries

- Observation: the repository already has two durable audit concepts, but neither is the gate decision log required by Issue F.
  Evidence: `coach_decisions` stores a coarse `Push/Moderate/Recovery/Monitor` classification of final LLM text; `coach_proposals` stores actionable planning mutation lifecycle. Gate outcomes and their readiness/conflict evidence belong in a separate recovery decision table, while recovery mutations should reuse `coach_proposals`.

- Observation: safe approval and rejection already exist under `/api/decisions/proposals/{id}`.
  Evidence: issue #71 and PR #77 created the durable proposal lifecycle, and issue #78 made pending proposals actionable from `/decisions`. Issue #154 only needs a new recovery action, stale-checkpoint validation, and rollback.

- Observation: the existing near-term plan editor is deterministic and preserves checkpoint history, but its horizon is anchored at Monday of the current week and capped at ten plan rows.
  Evidence: `api/planning_service.py::_start_week` returns Monday, while `models/planning_near_term.py` currently caps editable indices at ten. A gate session up to six days from Sunday can be plan index twelve, so the reusable editor must permit a fourteen-row backing window even though the recovery decision itself remains bounded to seven days from today.

- Observation: the Wizard-of-Oz protocol names a transfer option, but moving a key session requires a quality forecast and calendar trade-off that this issue does not yet have.
  Evidence: `docs/woz_recovery_replan_protocol.md` lists keep, downgrade, and transfer variants. Issue D is explicitly out of scope, so v1 will expose `keep` and one deterministic recovery downgrade instead of pretending it can choose a safe transfer date.

## Decision Log

- Decision: add `recovery_decisions` rather than widening `coach_decisions`.
  Rationale: a final chat classification and a salience-gate evaluation have different cardinality, evidence, and lifecycle. Keeping them separate preserves existing API clients and makes intervention-rate measurement honest.
  Date/Author: 2026-07-10 / Codex.

- Decision: reuse `coach_proposals` for the recovery mutation and add stable source provenance/idempotency there.
  Rationale: approve/reject controls, SQLite lifecycle, Coach SSE proposal frames, and the Decisions page already use this table. A second proposal table would create competing mutation paths.
  Date/Author: 2026-07-10 / Codex.

- Decision: one unique evaluation fingerprint is based on gate as-of date, active checkpoint id, readiness state, horizon, and normalized conflicts.
  Rationale: Coach chat can evaluate the same state repeatedly. Stable fingerprints let repeated requests return the same log row and proposal while a new readiness day, plan checkpoint, or conflict creates a new auditable decision.
  Date/Author: 2026-07-10 / Codex.

- Decision: v1 modifies only the highest-severity, nearest conflict and offers an explicit unchanged-plan alternative.
  Rationale: changing several days at once would obscure which intervention is being evaluated. Severity-first and date-second ordering is deterministic; the user can always reject or keep the original plan.
  Date/Author: 2026-07-10 / Codex.

- Decision: use named recovery mappings and `protect_recovery` follow-up strategy.
  Rationale: high conflicts downgrade quality/long work to recovery load; medium conflicts downgrade it to easy load; easy×low becomes recovery. Removed load is not automatically caught up because that would recreate the same recovery conflict later.
  Date/Author: 2026-07-10 / Codex.

- Decision: approval is optimistic-concurrency guarded by the proposal's base checkpoint id.
  Rationale: applying a preview to a different active plan is unsafe. A stale proposal must fail without mutation and ask for a fresh evaluation.
  Date/Author: 2026-07-10 / Codex.

- Decision: rollback is append-only.
  Rationale: restoring the previous checkpoint as a new `restore_version` preserves the complete audit trail. Rollback is allowed only while the recovery-applied checkpoint remains active, so it cannot erase a newer unrelated edit.
  Date/Author: 2026-07-10 / Codex.

## Outcomes & Retrospective

Work is in progress. Success means a user can inspect why the gate stayed silent or intervened, and every plan mutation remains explicit, reversible, and tied to the exact readiness evidence and plan version that produced it.

## Context and Orientation

The canonical readiness calculation lives in `models/readiness.py`. `api/readiness_conflicts.py::build_readiness_conflict_report` combines it with the active planning checkpoint and returns a deterministic report. A report has `silence`, `data_gap`, `reason`, `readiness`, `sessions_evaluated`, `conflicts`, and effective-horizon provenance. A salience-gate is a filter that emits a conflict only when the readiness status and session role meet the severity matrix; otherwise silence is the correct action.

`api/routers/coach.py` builds that report before streaming a Coach response and includes it in the first SSE `meta` event. The new loop will replace the direct report call there, returning the same report plus recovery decision/proposal metadata. Failures in audit persistence must not prevent a Coach answer, but domain errors must be observable in the loop result and tests.

SQLite persistence is centralized in `data/database.py`. Existing `coach_decisions` rows classify final LLM answers. Existing `coach_proposals` rows contain action, status, params, preview, result/error, chat/message identifiers, and timestamps. Approval/rejection routes live in `api/routers/decisions.py` and call shared functions in `api/planning_service.py`.

The active plan is the latest row in `planning_checkpoints`. `models/planning_checkpoints.py` restores full goal plans and records parent/restored-from provenance. `models/planning_near_term.py` builds and applies explicit daily draft rows while recalculating weekly totals and safety metadata. The recovery variant must use those helpers rather than duplicating planning math.

The product page `web/app/decisions/page.tsx` already shows pending `coach_proposals` through `ProposalCard`. The change will extend its TypeScript contract with recovery actions/history and add a rollback control for an approved recovery proposal. Streamlit files are not in scope.

## Behavioral Specification

Given a current readiness report with no conflict and sufficient data, when the loop evaluates the same as-of date and checkpoint more than once, then one `silence` decision exists, no proposal exists, and each call returns the same decision id.

Given readiness confidence is insufficient, when the gate returns `data_gap`, then one `data_gap` decision stores the reason and report evidence, creates no proposal, and does not change the active checkpoint.

Given low readiness and a quality session inside the bounded gate horizon, when the loop runs, then it logs `conflict`, selects that high-severity session, and creates exactly one pending `recovery_replan` proposal. Its preview contains the current session, recommended role/load, TSS delta, gate reason/evidence, and an explicit `keep` option.

Given the same conflict is evaluated concurrently or repeatedly, when source keys collide, then SQLite returns the existing recovery decision/proposal rather than inserting duplicates.

Given a pending recovery proposal, when the user rejects it, then proposal status becomes rejected and the active checkpoint id remains unchanged.

Given a pending recovery proposal whose base checkpoint is still active, when the user approves it, then the shared near-term editor applies the stored draft, a child checkpoint with source `recovery_replan` is saved, and the result identifies both new and rollback checkpoint ids.

Given a pending recovery proposal whose base checkpoint is no longer active, when approval is attempted, then the API returns a conflict response, marks the proposal failed with a stale-plan reason, and saves no checkpoint.

Given the latest active checkpoint came from an approved recovery proposal, when the user rolls it back, then the previous checkpoint is restored into a new checkpoint with source `restore_version`. Given another checkpoint became active after the recovery change, rollback returns a conflict and does not overwrite it.

## Milestones

The first milestone establishes contract-first failures. Add tests for the database row shape and idempotency, pure recovery variant selection, loop outcomes, proposal lifecycle, API response compatibility, and web type/rendering behavior. Run focused tests before adding implementation and record the exact failures.

The second milestone implements the headless backend. Add the recovery decision table and stable proposal source keys in `data/database.py`; add a pure variant builder under `models/`; add an orchestration service under `api/` that builds the report, fingerprints it, logs it, and creates or reuses a recovery proposal. At the end, silence/data-gap/conflict tests pass without LLM or live credentials.

The third milestone closes mutation safety. Extend `api/planning_service.py` to preview/apply the stored recovery draft and restore a rollback checkpoint. Extend proposal approval/rejection/rollback in `api/routers/decisions.py`, add `recovery_replan` checkpoint provenance, and prove stale-plan guards. At the end, tests demonstrate confirm, reject, and rollback against real temporary SQLite databases.

The fourth milestone exposes the result. Coach SSE meta includes loop metadata while retaining `readiness_conflicts`. `GET /api/decisions` adds recovery groups without changing existing fields. The web Decisions page renders recovery evidence, pending recovery proposals through the existing card, and rollback only when valid. At the end, the web production build and API smoke tests pass.

The final milestone performs full validation and publication. Run the contributor-safe suite, Python compilation, Ruff, web lint/build, and `git diff --check`; inspect the full diff for correctness, concurrency, security, compatibility, and unnecessary complexity; update this living plan with evidence; commit, push, and open a draft PR with `Closes #154`.

## Plan of Work

First add `tests/smoke/test_recovery_replan_loop.py` and extend the existing coach decision/API tests. Tests will describe the public dictionaries and endpoint outcomes, not private implementation details. A pure goal-plan fixture will put a quality session on a known date so date-to-plan-index behavior is deterministic.

Next extend `data/database.py` additively. `recovery_decisions` stores a unique fingerprint, outcome, gate/report JSON, plan checkpoint id, proposal id, reason, and timestamps. `coach_proposals` receives nullable `source` and `source_key`; a unique partial index on non-null source keys makes recovery proposal creation idempotent without changing existing chat proposals. New database helpers must JSON-round-trip and never interpolate user values into SQL.

Add `models/recovery_replan.py`. It selects the worst conflict by severity rank then `days_until`, finds the matching absolute date in the active goal plan, builds reusable near-term draft rows, and returns two variants: unchanged and recommended. It uses named load factors and never returns a proposal for silence/data gaps. The backing near-term editor window may grow from ten to fourteen plan rows so a seven-day-from-today session remains addressable from a Monday-anchored plan.

Add `api/recovery_replan_loop.py`. It calls the existing gate builder, reads the latest checkpoint, computes a canonical JSON fingerprint, persists/reuses the decision, and creates/reuses a source-keyed proposal when the pure builder returns a recommendation. The loop output includes the unchanged gate report plus decision/proposal ids and outcome.

Extend `api/planning_service.py` with apply and restore functions that operate only on stored proposal parameters. Apply checks the latest checkpoint id before calling `apply_near_term_day_edits`, attaches source `recovery_replan`, sets the rollback target, and saves a child checkpoint. Restore checks that the proposal-applied checkpoint remains latest, restores the base checkpoint, attaches `restore_version`, and saves another checkpoint.

Extend `api/routers/decisions.py`, `api/routers/coach.py`, `web/lib/types.ts`, `web/components/ui/ProposalCard.tsx`, and `web/app/decisions/page.tsx` additively. Existing actions and response fields remain valid. Recovery history is explanatory; mutation buttons continue to call server endpoints.

## Concrete Steps

Work from `/Users/gregkisel/Developer/ai_trainer`:

    ai_trainer_env/bin/python -m pytest tests/smoke/test_recovery_replan_loop.py tests/smoke/test_coach_decisions.py -q
    ai_trainer_env/bin/python -m pytest tests/smoke/test_readiness_conflicts.py tests/smoke/test_planning_near_term.py tests/smoke/test_planning_checkpoint_history.py tests/smoke/test_api_planning.py -q
    ai_trainer_env/bin/python -m pytest tests/smoke -q
    ai_trainer_env/bin/python -m compileall -q api models services data ui
    ruff check api models data tests/smoke
    npm run lint --prefix web
    npm run build --prefix web
    git diff --check

The first focused run after adding tests must fail because the recovery persistence, loop, action, and rollback contracts do not yet exist. After implementation all commands must pass without Garmin or LLM credentials.

## Validation and Acceptance

The full acceptance proof uses temporary SQLite databases and deterministic plan/readiness fixtures. It verifies exact row counts for repeated loop evaluation, proposal counts, active checkpoint ids before and after every lifecycle action, checkpoint source/parent/restored-from metadata, and unchanged existing decision/proposal response keys.

A manual web check may run `./run_web.sh`, open `/coach` to trigger the loop, then open `/decisions`. On a conflict fixture or real conflict day, the page shows one recovery decision and one pending proposal. Reject preserves Planning. Approve changes only the named session. Rollback creates a later history version whose active plan matches the original checkpoint. On a quiet day, the recovery history shows silence and no pending card.

Definition of done is the issue #154 acceptance criteria plus a pushed draft PR. CI and maintainer merge remain external final gates.

## Idempotence and Recovery

Database migrations are additive and safe to rerun through `Database.init_tables()`. Unique fingerprints and source keys make loop retries safe. Approval, rejection, and rollback endpoints reject invalid lifecycle transitions. No operation deletes planning checkpoints or recovery decisions. If an operation fails after a network response is lost, refetch `/api/decisions`: persisted status and active checkpoint determine the truth.

If the pure variant builder cannot find the conflict date in the active plan, the decision remains logged as `conflict` with no proposal and a structured `proposal_gap` reason. This is safer than mutating the wrong plan day.

## Artifacts and Notes

Baseline before implementation:

    main: f9a329b
    smoke: 452 passed, 1 skipped in 11.05s
    issue: https://github.com/rbctmz/ai_trainer/issues/154

Existing reusable contracts:

    api.readiness_conflicts.build_readiness_conflict_report(db) -> gate report
    Database.save_coach_proposal(...) -> durable pending mutation
    models.planning_near_term.build_near_term_edit_rows(...) -> editable rows
    models.planning_near_term.build_near_term_edit_draft_rows(...) -> preview/apply rows
    models.planning_near_term.apply_near_term_day_edits(...) -> updated goal plan
    models.planning_checkpoints.with_checkpoint_provenance(...) -> version lineage

## Interfaces and Dependencies

`models/recovery_replan.py` will expose a pure function equivalent to:

    build_recovery_replan_variant(goal_plan, gate_report, *, today) -> dict | None

The result contains selected conflict, current/recommended session summaries, draft rows, horizon, post-edit strategy, options, evidence, and a compact preview. It has no database or LLM dependency.

`api/recovery_replan_loop.py` will expose:

    run_recovery_replan_loop(db) -> dict

The returned contract contains `outcome`, `decision`, `proposal`, and the original `readiness_conflicts` report.

`Database` will expose recovery log helpers and additive proposal source fields. Public API shapes remain JSON dictionaries to match existing database helpers.

`api.planning_service` will expose:

    apply_recovery_replan(db, proposal_params, *, persist=True) -> dict
    rollback_recovery_replan(db, proposal_result, *, persist=True) -> dict

`POST /api/decisions/proposals/{proposal_id}/rollback` is valid only for an approved `recovery_replan` proposal. The existing approve and reject endpoints retain their paths.

Revision note (2026-07-10 / Codex): initial self-contained plan created after repository architecture review and before behavior tests or implementation.
