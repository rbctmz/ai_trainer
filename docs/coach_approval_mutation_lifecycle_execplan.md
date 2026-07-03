# Coach proposal approval lifecycle for planning mutations

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds. This document follows `.agent/PLANS.md`.

## Purpose / Big Picture

The coach can already produce a structured planning proposal during chat, but before this change that proposal only lived in the browser. Confirming it called planning endpoints directly, so the decision log had no durable record of what the coach proposed, whether the athlete approved it, and which plan checkpoint was produced. After this change, a coach proposal becomes a stored pending action with a stable id. The user can approve or reject it, approved proposals apply the same planning service used by the Planning page, and `/decisions` exposes both ordinary coach decisions and proposal lifecycle state.

The behavior is visible by running `./run_web.sh`, opening `http://localhost:3000/coach`, asking the coach to build or adjust a plan, and observing a proposal card. The card has a server-backed id. Pressing `Подтвердить` posts to `/api/decisions/proposals/{id}/approve`, persists a planning checkpoint, and marks the proposal approved. Pressing `Отменить` posts to `/api/decisions/proposals/{id}/reject` and leaves the active plan unchanged.

## Progress

- [x] (2026-07-03 15:20+03:00) Created GitHub issue #71 and branch `codex/issue-71-coach-planning-approvals`.
- [x] (2026-07-03 15:34+03:00) Audited existing proposal tools, coach SSE route, decisions route, planning service, database persistence, and web proposal card.
- [x] (2026-07-03 15:43+03:00) Added failing smoke coverage for durable proposals, approve/reject endpoints, build/adjust application, and coach SSE `proposal_id`.
- [x] (2026-07-03 15:55+03:00) Added `coach_proposals` database table and persistence helpers.
- [x] (2026-07-03 16:05+03:00) Added `/api/decisions/proposals/{proposal_id}/approve` and `/reject`, plus proposal metadata in `GET /api/decisions`.
- [x] (2026-07-03 16:12+03:00) Updated coach SSE to persist proposal events and emit `proposal_id` plus pending status.
- [x] (2026-07-03 16:18+03:00) Updated the web proposal card to approve/reject through the decisions API instead of posting directly to planning endpoints.
- [x] (2026-07-03 16:25+03:00) Ran focused backend contour: `23 passed`.
- [x] (2026-07-03 16:28+03:00) Ran full smoke suite: `332 passed`.
- [x] (2026-07-03 16:31+03:00) Ran `npm run build --prefix web`: green, 11 static pages.
- [ ] Publish PR with `Closes #71`.

## Surprises & Discoveries

- Observation: `docs/coach_approval_mutations_execplan.md` already completed the first slice: proposal tools, transient SSE `proposal` events, and a web card. The missing part is persistence and lifecycle, not proposal generation.
  Evidence: `api/routers/coach.py` already emitted `{"type": "proposal", "action": ..., "params": ..., "preview": ...}` before this issue.

- Observation: The existing web card bypassed the decision log by posting directly to `/api/planning/build` and `/api/planning/adjust`.
  Evidence: `web/components/ui/ProposalCard.tsx` called `postJSON("/api/planning/build", ...)` and `postJSON("/api/planning/adjust", ...)` before this issue.

## Decision Log

- Decision: Store proposal lifecycle in a new `coach_proposals` table instead of adding many nullable columns to `coach_decisions`.
  Rationale: A coach decision is the final synthesized recommendation classification (`Push`, `Moderate`, `Recovery`, `Monitor`). A proposal is an actionable pending mutation with params, preview, result, status, and optional error. Separating the tables preserves the existing decision log shape and keeps proposal-specific JSON isolated.
  Date/Author: 2026-07-03 / Codex

- Decision: Approval endpoints live under `/api/decisions/proposals/...`.
  Rationale: The action is part of the coach audit trail, not a second planning API. The implementation still calls `api/planning_service.py`, so planning math remains single-source.
  Date/Author: 2026-07-03 / Codex

- Decision: `message_id` is generated before the tool phase in the coach stream.
  Rationale: Proposals are emitted before the final `done` event, but they should still be linked to the assistant message that produced them. Generating the id early lets `coach_proposals.message_id`, `coach_decisions.message_id`, and the final SSE `done.message_id` match.
  Date/Author: 2026-07-03 / Codex

## Outcomes & Retrospective

The implementation now turns coach planning proposals into durable pending actions. Proposal events in the chat stream carry a stored `proposal_id`; approving that id applies the same planning service paths as the Planning page and records the proposal as approved; rejecting it records a rejected proposal and leaves the active plan unchanged. `/api/decisions` continues to return the existing decision `days` shape and adds proposal groups for audit visibility. The web coach card now calls the approval API rather than bypassing the decision log.

Verification completed:

    python3 -m pytest tests/smoke/test_coach_decisions.py tests/smoke/test_ai_tools_proposal.py tests/smoke/test_api_planning.py -q
    23 passed

    python3 -m pytest tests/smoke -q
    332 passed

    npm run build --prefix web
    Compiled successfully; generated 11 static pages

## Context and Orientation

AI Trainer's active product path is FastAPI under `api/` plus Next.js under `web/`. The coach chat endpoint is `api/routers/coach.py`. It does a hidden first LLM pass that can request tools from `models/ai_tools.py`, executes those tools, emits tool and proposal events over Server-Sent Events, then streams or returns a final synthesized answer.

The existing planning engine lives in `api/planning_service.py`. It exposes `build_plan(db, ..., persist=True)` for creating a new planning checkpoint and `apply_adjustment(db, rows, weeks, persist=True)` for rebuilding an active plan from execution reconciliation. These are the only functions that should mutate planning checkpoints for this feature.

The decision log endpoint is `api/routers/decisions.py`. Before this issue it only exposed rows from `coach_decisions`, a small audit table populated after each coach response. This issue adds proposal lifecycle state while keeping the old `days` shape intact.

The web coach page is `web/app/coach/page.tsx`, and the proposal card is `web/components/ui/ProposalCard.tsx`. Before this issue the card confirmed proposals by calling planning endpoints directly. After this issue it must use the server-backed proposal id.

## Plan of Work

Add a `coach_proposals` table in `data/database.py` with action, status, params, preview, result, error, chat id, message id, timestamps, and helper methods to save, fetch, list, and update proposal status. Keep JSON fields serialized inside SQLite because this repo already uses compact JSON for planning checkpoints and because proposal params/previews are structured but small.

Update `api/routers/coach.py` so a proposal tool result is saved before the SSE `proposal` event is emitted. The event must include `proposal_id` and `status`. Generate the final assistant `message_id` before tool execution so saved proposals and the final decision row refer to the same message id.

Update `api/routers/decisions.py` so `GET /api/decisions` returns existing `days` unchanged and adds `proposal_count` plus `proposal_days`. Add `POST /api/decisions/proposals/{proposal_id}/approve` and `/reject`. Approve must only accept pending proposals. For `build_plan`, call `planning_service.build_plan(..., persist=True)` using stored params. For `adjust_plan`, call `planning_service.apply_adjustment(..., persist=True)` using stored rows and weeks. Reject must mark status rejected and not call planning.

Update the web types and proposal card. `CoachProposalEvent` gets `proposal_id` and `status`. `ProposalCard` receives the id and confirms through `/api/decisions/proposals/{id}/approve`; rejection goes through `/reject`. The card should still render the same preview, but the mutation path must now be audited.

## Concrete Steps

From repository root `/Users/gregkisel/Developer/ai_trainer`:

    python3 -m pytest tests/smoke/test_coach_decisions.py -q

Expected after implementation:

    10 passed

Then run the relevant smoke contour:

    python3 -m pytest tests/smoke/test_coach_decisions.py tests/smoke/test_ai_tools_proposal.py tests/smoke/test_api_planning.py -q

Then run the full contributor-safe smoke suite:

    python3 -m pytest tests/smoke -q

Then run the web build:

    npm run build --prefix web

## Validation and Acceptance

The new tests prove the main behavior. `test_database_persists_coach_proposals` proves proposal params and preview round-trip through SQLite. `test_approve_build_plan_proposal_persists_checkpoint` proves approving a build proposal creates a planning checkpoint. `test_approve_adjust_plan_proposal_persists_adjusted_checkpoint` proves approving an adjustment proposal creates a new adjusted checkpoint. `test_reject_plan_proposal_does_not_mutate_active_plan` proves rejection leaves planning unchanged. `test_coach_stream_persists_proposal_and_emits_id` proves the chat SSE contract now includes a persisted proposal id linked to the assistant message.

The web build proves the updated TypeScript contract is coherent. Manual verification, if needed, is to run `./run_web.sh`, ask the coach to build a plan, confirm the card, and then open `/planning` and `/decisions`. `/planning` should show the saved active plan, and `/decisions` should show the proposal as approved.

## Idempotence and Recovery

The database migration is additive. Existing SQLite files get the new `coach_proposals` table on `Database.init_tables()` without changing existing rows. If approval fails because params are invalid or an active plan is missing, the proposal is marked failed and the API returns an error; retry by asking the coach for a fresh proposal. Rejecting a proposal is non-destructive and does not touch planning checkpoints.

## Artifacts and Notes

Focused smoke after implementation:

    python3 -m pytest tests/smoke/test_coach_decisions.py -q
    10 passed

## Interfaces and Dependencies

`data.database.Database` exposes:

    save_coach_proposal(action, params, preview, chat_id=None, message_id=None, date=None) -> dict
    get_coach_proposal(proposal_id) -> dict | None
    get_coach_proposals(days=30, status=None, limit=100) -> list[dict]
    update_coach_proposal_status(proposal_id, status, result=None, error=None) -> dict | None

`api/routers/decisions.py` exposes:

    GET /api/decisions
    POST /api/decisions/proposals/{proposal_id}/approve
    POST /api/decisions/proposals/{proposal_id}/reject

`api/routers/coach.py` emits proposal SSE frames:

    {"type": "proposal", "proposal_id": 1, "action": "build_plan", "status": "pending", "params": {...}, "preview": {...}}
