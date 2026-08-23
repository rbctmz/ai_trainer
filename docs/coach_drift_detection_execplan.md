# Directional Drift Detection for Coach Decisions

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

This document follows `.agent/PLANS.md` and the repository workflow in `docs/AI_Feature_Development_Workflow.md`.

## Purpose / Big Picture

After this change, the hidden `/decisions` audit surface can answer a narrow, factual question: when a completed coach turn both declared a direction (`Push`, `Moderate`, `Recovery`, or `Monitor`) and explicitly produced a `coach_tool` proposal that the athlete later approved, did the persisted plan move in an obviously contradictory TSS direction?

The report is deliberately not a causal model. It never joins rows by nearby timestamps, never treats a pending proposal as applied, and never invents a result for old rows that lack explicit lineage. A contributor can prove the behavior with a temporary SQLite database and no provider credentials.

## Progress

- [x] (2026-08-23) Synchronized local `main` with `origin/main` and created `codex/issue-468-directional-drift`.
- [x] (2026-08-23) Read the architecture catalog, ADD analysis, web-primary ADR, proposal/autonomy/checkpoint ADRs, repository feature workflow, and issue loop instructions.
- [x] (2026-08-23) Ran three independent read-only audits for lineage, API/web contract shape, and false-positive risk.
- [x] (2026-08-23) Re-checked the live issue body and acceptance criteria for #468.
- [x] (2026-08-23) Added RED smoke and contract tests for explicit turn lineage, verified checkpoint comparison, data gaps, and conservative mismatch semantics; initial collection failed on the absent service as expected.
- [x] (2026-08-23) Added additive SQLite lineage columns and passed one `decision_event_id` through the complete coach turn, including the recovery loop.
- [x] (2026-08-23) Implemented the read-only drift service and additive `/api/decisions` response.
- [x] (2026-08-23) Rendered a compact report on the existing dev-only `/decisions` page with a rolling-deploy fallback for an older API.
- [x] (2026-08-23) Completed focused, contract, ruff, full contributor-safe pytest, web lint/build, and diff checks.
- [ ] Publish the reviewed implementation as a draft PR linked with `Closes #468`.

## Surprises & Discoveries

- Observation: ordinary `coach_decisions` and `coach_proposals` have no durable relation. Their optional `chat_id` and `message_id` values are correlation metadata, not a unique foreign key.
  Evidence: `data/database.py` defines the two tables independently, and the live database snapshot contains only one proposal with both chat and message identifiers.

- Observation: the recovery loop runs before the chat stream creates its `message_id`; its proposals therefore have no chat/message identifiers. Recovery has a separate verified edge from `recovery_decisions.proposal_id`.
  Evidence: `api/routers/coach.py` calls `run_recovery_replan_loop` before entering `stream()`, while `api/recovery_replan_loop.py` explicitly links its recovery decision and proposal.

- Observation: `Push`, `Moderate`, `Recovery`, and `Monitor` classify the final recommendation. They are not mutation commands and do not require a proposal.
  Evidence: `models/coach_decisions.py` deterministically derives the label from metrics and response text; proposal creation is a separate tool-result path.

- Observation: proposal approval proves a local mutation lifecycle transition, but not successful Intervals delivery. Delivery has its own nested result state.
  Evidence: `api/routers/decisions.py` marks a proposal approved after local application and records provider delivery separately for recovery variants.

- Observation: historical result JSON is not a stable lineage ledger. Older recovery rows can contain `plan_id` without current `applied_checkpoint_id` and `rollback_checkpoint_id` fields, and rollback replaces `result_json`.
  Evidence: the live SQLite snapshot and `update_coach_proposal_status` behavior.

- Observation: `execution_adjustment` checkpoints created by the legacy adjustment path do not always include a parent checkpoint even though newer mutation paths do.
  Evidence: `api/planning_service.py::apply_adjustment` adds provenance without a parent id. These rows must be `data_gap`, not inferred.

- Observation: event-scoped linkage alone still over-attributed the automatic recovery gate to the final LLM recommendation.
  Evidence: independent self-review showed both events share the turn UUID. The implementation now requires `source="coach_tool"`; recovery-loop proposals are `unattributed_proposal`.

- Observation: a newer web bundle can briefly talk to an older API during rolling deployment.
  Evidence: independent contract review found that a required `drift_report` would dereference `undefined`. The TypeScript field and card are now backward-compatible optional additions.

## Decision Log

- Decision: create a UUID `decision_event_id` before the recovery loop and persist it on every new coach decision and proposal created during that turn; also persist proposal origin in the existing `source` field and compare only `source="coach_tool"`.
  Rationale: event scope removes time-based matching, while origin prevents the automatic recovery gate from being misattributed to the final recommendation. Multiple explicit tool proposals in one turn remain independent facts.
  Date/Author: 2026-08-23 / Codex.

- Decision: add immutable proposal lineage columns for `base_checkpoint_id`, `applied_checkpoint_id`, and `rollback_checkpoint_id`, populated from the proposal preview/params and the first successful apply result.
  Rationale: `result_json` is lifecycle output and can be replaced on rollback. Dedicated additive columns preserve the verified `before → after` edge needed for a later read-only report.
  Date/Author: 2026-08-23 / Codex.

- Decision: old rows without `decision_event_id`, a comparable base checkpoint, an applied checkpoint, or a verified parent edge are `data_gap`/`unlinked`; they are never repaired by timestamp proximity.
  Rationale: ASR-REL-2 requires explicit missing-evidence states instead of fabricated results.
  Date/Author: 2026-08-23 / Codex.

- Decision: absence of a proposal or mutation is not directional drift. The first version only reports an obvious contradiction after a linked approved mutation: `Push + decrease`, `Moderate + increase`, `Recovery + increase`, or `Monitor + non-neutral change`.
  Rationale: the decision label is a recommendation classification, not an imperative to mutate the plan. This matrix detects contradictions without claiming that the coach failed merely by keeping the plan unchanged.
  Date/Author: 2026-08-23 / Codex.

- Decision: `pending`, `rejected`, `failed`, and `rolled_back` proposals remain lifecycle facts but do not enter the active directional comparison. Approved no-op recovery `keep` increments a separate `no_change_count`, not `compared_count`.
  Rationale: only a successfully persisted local plan mutation can establish an actual plan direction, and a rolled-back mutation is no longer the active result of that proposal.
  Date/Author: 2026-08-23 / Codex.

- Decision: extend the existing `GET /api/decisions` response with `drift_report` and render it on the already dev-only `/decisions` page rather than creating a second audit route.
  Rationale: the page already owns coach decisions, proposals, and recovery history. An additive server-owned DTO keeps the diagnostic beside its evidence and avoids another request.
  Date/Author: 2026-08-23 / Codex.

## Outcomes & Retrospective

The complete web-first vertical is implemented. New coach turns carry explicit event lineage; explicit tool proposals also carry origin and immutable base/applied/rollback checkpoint ids. The report fails closed on legacy/unattributed/orphan rows, inactive lifecycle states, result/base/parent disagreement, missing checkpoints, malformed TSS, and incompatible horizons. It reports only the conservative contradiction matrix and keeps approved no-op actions separate.

Validation completed on 2026-08-23:

    147 focused/contract tests passed
    2024 contributor-safe tests passed, 3 skipped, 26 deselected
    python -m ruff check . passed
    contract:extract -- --check passed
    web lint passed
    web production build passed (15 static pages)
    git diff --check passed

The three skips are expected environment gaps: one local-socket preflight and two optional `garth` imports. No live provider or athlete-data mutation was run.

## Context and Orientation

`api/routers/coach.py::coach_chat` owns one successful coach turn. It currently calls the recovery loop before streaming, saves tool-created proposals during the stream, and writes one `coach_decisions` row after the final answer. This is where one event identifier must be generated and passed to all three persistence sites.

`data/database.py` owns SQLite schema initialization and migrate-on-start column additions. The implementation must add columns through the existing `_COACH_DECISION_COLUMN_TYPES` and `_COACH_PROPOSAL_COLUMN_TYPES` patterns so existing local databases remain usable. Proposal serialization and every SELECT projection must expose the new columns without breaking old callers.

`planning_checkpoints` is append-only. Its JSON payload exposes `weekly_tss_plan` and checkpoint provenance such as `checkpoint_parent_id`. The drift service must load both persisted checkpoints, verify that the applied checkpoint names the recorded base as parent, require equal-length weekly horizons, sum the two weekly TSS lists, and derive `increase`, `decrease`, or `neutral`. Missing, malformed, or horizon-incompatible evidence returns a structured gap.

`api/routers/decisions.py::list_decisions` already groups the audit history. It will call a pure read-only service using the same bounded decision/proposal rows and the database checkpoint reader, then attach one additive `drift_report` object.

`web/app/decisions/page.tsx` is behind `NEXT_PUBLIC_SHOW_DEV_TOOLS=true`. `web/lib/types.ts` is the mirrored client contract. The UI will show counts and exact tuples (decision id/type, proposal id/action, checkpoint ids, before/after/delta TSS); it must not generate new domain conclusions.

The relevant quality requirements are ASR-REL-1 (append-only lineage), ASR-REL-2 (honest data gaps), ASR-REL-3 (consistent lifecycle facts), ASR-MOD-2 (server-owned domain semantics), and ASR-MOD-3 (additive compatibility). ADR-0004 keeps mutations behind proposal/confirm, ADR-0006 keeps checkpoints append-only, and ADR-0010 forbids autonomous application.

## Plan of Work

First, add smoke tests on temporary SQLite databases. The RED suite will prove migrate-on-start compatibility, one event id across a coach decision and every proposal from that turn, no timestamp join for legacy rows, multiple proposals per event, explicit lifecycle exclusions, verified checkpoint-parent comparison, and each boundary of the conservative mismatch matrix. A falsifying test will construct two temporally adjacent but unlinked rows and require `data_gap`.

Second, add the schema and persistence fields. Generate `decision_event_id` before `run_recovery_replan_loop`, pass it into recovery proposal creation, tool proposal creation, and final decision persistence, and mark explicit LLM tool proposals with `source="coach_tool"`. Capture base lineage on proposal creation and applied/rollback checkpoint ids on successful approval without erasing them during rollback.

Third, add `services/coach_drift.py`. It will accept row dictionaries and a checkpoint lookup callable, group only exact non-empty event ids, preserve all proposals for a turn, validate proposal status and checkpoint ancestry, calculate TSS facts, and return a deterministic DTO containing `state`, counts, `mismatches`, and `data_gaps`. It will not read provider APIs or mutate storage.

Fourth, attach the report to `GET /api/decisions`. Add the mirrored TypeScript interfaces and a compact audit card to `/decisions`. The API remains the sole owner of mapping and mismatch rules.

Fifth, regenerate the TypeScript contract artifact, run focused and full contributor-safe checks, and perform a diff review for causal wording, migration safety, query compatibility, untracked personal-data artifacts, and unrelated changes.

## Concrete Steps

From `/Users/gregkisel/Developer/ai_trainer`:

    ai_trainer_env/bin/python -m pytest tests/smoke/test_coach_drift.py tests/smoke/test_coach_decisions.py -q
    ai_trainer_env/bin/python -m ruff check .
    ai_trainer_env/bin/python -m pytest -m "not live and not debug and not e2e" tests/
    npm --prefix web run contract:extract
    npm --prefix web run lint
    npm --prefix web run build
    git diff --check

Expected RED before implementation: new drift tests fail because the schema fields, report service, and response field do not exist. Expected GREEN: every command exits zero, with live/debug/e2e tests excluded from the broad Python pass.

## Validation and Acceptance

BDD scenarios:

1. Given an old decision and proposal close in time but without a shared event id, when the report runs, then it emits an `unlinked` data gap and no mismatch.
2. Given a linked `Recovery` decision and an approved proposal whose verified child checkpoint has higher total TSS than its base, when the report runs, then one mismatch lists only the stored ids and TSS facts.
3. Given the same data with lower total TSS, then the pair is compared but no mismatch is emitted.
4. Given `Push + decrease`, `Moderate + increase`, or `Monitor + non-neutral`, then each exact pair is a mismatch.
5. Given pending, rejected, failed, or rolled-back proposals, then no active mutation direction is claimed.
6. Given approved recovery `keep`, then the report increments `no_change_count`, keeps `compared_count == 0`, and emits no mismatch.
7. Given missing checkpoints, malformed weekly TSS, or a child whose parent differs from the recorded base, then the report emits `data_gap` and no direction.
8. Given one event with two proposals, then both remain independently visible and neither is selected by heuristics.
9. Given an empty database, then `drift_report.state == "data_gap"`, counts are zero, and no synthetic conclusion is returned.
10. Given at least one verified comparable pair with no contradiction, then the report says `ready`, `mismatch_count == 0`, and the UI says that no contradictions were found among the verified pairs.

Acceptance also requires the pre-existing decision/proposal/recovery tests and the full smoke baseline to remain green, the web contract artifact to be fresh, and web lint/build to pass.

## Idempotence and Recovery

SQLite column migrations use `ALTER TABLE ... ADD COLUMN` only when `PRAGMA table_info` shows a missing column, so creating `Database(path)` repeatedly is safe. Report generation is read-only and repeatable. Proposal lineage columns are first-write evidence: rollback may change lifecycle status/result JSON but must not erase the original base/applied ids.

If a test run is interrupted, rerun the focused commands. Temporary pytest databases are disposable. Do not delete or stage root `ai_trainer.db`, `ai_trainer.db-wal`, `ai_trainer.db-shm`, logs, or credentials; they may belong to a running local app and contain personal data.

## Artifacts and Notes

The report DTO is additive and shaped approximately as:

    {
      "state": "ready" | "data_gap",
      "decision_count": 3,
      "linked_proposal_count": 2,
      "compared_count": 1,
      "no_change_count": 0,
      "mismatch_count": 1,
      "mismatches": [
        {
          "decision_id": 12,
          "decision_type": "Recovery",
          "proposal_id": 34,
          "action": "adjust_plan",
          "base_checkpoint_id": 7,
          "applied_checkpoint_id": 8,
          "total_tss_before": 410,
          "total_tss_after": 455,
          "total_tss_delta": 45,
          "actual_direction": "increase"
        }
      ],
      "data_gaps": [{"decision_id": 9, "reason": "unlinked"}]
    }

Exact field names may be refined by the RED contract tests, but the server owns all verdict semantics and every mismatch must carry its verifiable raw facts.

## Interfaces and Dependencies

`services/coach_drift.py` will expose one typed public function similar to:

    def build_coach_drift_report(
        decisions: list[dict[str, Any]],
        proposals: list[dict[str, Any]],
        get_checkpoint: Callable[[int], dict[str, Any] | None],
    ) -> dict[str, Any]:
        ...

`Database.save_coach_decision`, `Database.save_coach_proposal`, and `run_recovery_replan_loop` gain optional `decision_event_id` parameters for backward compatibility. No new runtime dependency is required.

Revision note (2026-08-23): initial plan created after architecture review and independent lineage/risk audits. It rejects temporal inference, separates local mutation from provider delivery, and limits drift to verified contradictory directions. Updated after two independent diff reviews to distinguish `coach_tool` from recovery-gate origin, expose orphan proposals, separate no-op counts, triple-check result/base/parent lineage, and preserve rolling-deploy compatibility.
