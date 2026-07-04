# Surface pending coach proposals on the decisions page

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds. This document follows `.agent/PLANS.md`.

## Purpose / Big Picture

The coach can now create durable planning proposals, but the `/decisions` page currently shows them only as passive history entries. A pending proposal can therefore be missed after the chat session is gone. After this change, `/decisions` has a clear top section for proposals that still need the athlete's approval. The user can open `/decisions`, see every pending coach proposal first, approve or reject it from the same page, and then continue reading the ordinary decision journal below.

This is a small continuation of issue #71. It does not change planning math and does not introduce a new mutation path. It reuses the existing proposal approval endpoints under `/api/decisions/proposals/{proposal_id}/approve` and `/reject`.

## Progress

- [x] (2026-07-04 14:20+03:00) Created GitHub issue #78 and branch `codex/issue-78-decisions-pending-proposals`.
- [x] (2026-07-04 14:27+03:00) Audited the current decisions API, proposal card, web types, and smoke tests.
- [x] (2026-07-04 14:35+03:00) Added a failing smoke assertion for explicit pending proposal metadata in `GET /api/decisions`; it failed with `KeyError: 'pending_proposal_count'`.
- [x] (2026-07-04 14:39+03:00) Added `pending_proposal_count` and `pending_proposal_days` to the decisions API without breaking `proposal_days`.
- [x] (2026-07-04 14:43+03:00) Updated `/decisions` to render pending proposals first with approve/reject controls and refresh after action.
- [x] (2026-07-04 14:49+03:00) Ran focused smoke, full smoke, web build, `git diff --check`, and self-review.
- [ ] Publish a PR that closes issue #78.

## Surprises & Discoveries

- Observation: `web/components/ui/ProposalCard.tsx` already contains the correct server-backed approve/reject behavior from issue #71.
  Evidence: The card posts to `/api/decisions/proposals/${proposalId}/approve` and `/reject`, so `/decisions` can reuse it instead of creating a second UI mutation flow.

- Observation: `GET /api/decisions` already returns `proposal_days`, but it groups all proposal statuses together.
  Evidence: `api/routers/decisions.py:list_decisions` builds `proposal_grouped` from every `db.get_coach_proposals(days=days)` row and does not expose a pending-only view.

- Observation: The TDD pass produced the expected contract failure before implementation.
  Evidence: `python3 -m pytest tests/smoke/test_coach_decisions.py -q` failed with `KeyError: 'pending_proposal_count'` after adding the test and before changing `api/routers/decisions.py`.

## Decision Log

- Decision: Add pending-only metadata to the existing `/api/decisions` response instead of creating a new endpoint.
  Rationale: `/decisions` already needs the full decision journal and proposal history. Returning `pending_proposal_count` and `pending_proposal_days` keeps the page to one request and preserves backward compatibility for existing fields.
  Date/Author: 2026-07-04 / Codex

- Decision: Keep non-pending proposal history visible below the pending section.
  Rationale: Pending proposals are actions, while approved, rejected, and failed proposals are audit history. Splitting them visually makes the next action obvious without hiding the lifecycle record.
  Date/Author: 2026-07-04 / Codex

## Outcomes & Retrospective

The implementation exposes pending proposal metadata from `GET /api/decisions` while preserving the existing proposal history contract. The `/decisions` page now renders pending proposals in a top `Ожидают подтверждения` section using the existing server-backed `ProposalCard`. Approving or rejecting a proposal refreshes the page state through SWR, so the resolved proposal leaves the pending section and remains available in history.

Verification completed:

    python3 -m pytest tests/smoke/test_coach_decisions.py -q
    10 passed

    python3 -m pytest tests/smoke -q
    332 passed

    npm run build --prefix web
    Compiled successfully; generated 11 static pages

    git diff --check
    no output

## Context and Orientation

AI Trainer's active product surface is FastAPI under `api/` and Next.js under `web/`. Coach planning proposals are durable rows in the SQLite `coach_proposals` table, managed by `data/database.py`. A proposal is a structured pending action suggested by the coach, such as building a new plan or adjusting the current plan. It has an `action`, `status`, `params`, `preview`, and optional `result` or `error`.

The API route `api/routers/decisions.py` exposes `GET /api/decisions`. Today it returns ordinary coach decisions in `days` and all proposal history in `proposal_days`. The web page `web/app/decisions/page.tsx` reads this response and renders proposal history with a local `ProposalEntry`, which does not allow approving or rejecting pending proposals. The reusable component `web/components/ui/ProposalCard.tsx` already knows how to approve or reject a proposal through the decisions API and display a useful preview.

## Plan of Work

First, update `tests/smoke/test_coach_decisions.py` so the existing decisions API proposal test seeds both a pending and a non-pending proposal. The test should assert that `proposal_days` still contains both proposals and that the new pending-only fields contain only the pending row. This is the contract-first and TDD step.

Next, update `api/routers/decisions.py:list_decisions`. Build a second grouped list from only proposal rows where `status == "pending"`. Return it as `pending_proposal_days` and return its row count as `pending_proposal_count`. Keep `proposal_count`, `proposal_days`, `days`, and `count` unchanged.

Then update `web/lib/types.ts` to mirror the new response fields. In `web/app/decisions/page.tsx`, render a top card titled `Ожидают подтверждения` whenever `pending_proposal_days` is non-empty. Each pending proposal should use `ProposalCard`. On approve or reject, show a short notice and call SWR `mutate()` so the page refreshes. The proposal history below should filter out pending proposals so pending actions are not duplicated.

## Concrete Steps

From repository root `/Users/gregkisel/Developer/ai_trainer`, run the focused smoke test after adding the failing assertion:

    python3 -m pytest tests/smoke/test_coach_decisions.py -q

Before implementation, the new assertion should fail because `pending_proposal_count` does not exist. After implementation, it should pass.

After the API and UI edits, run:

    python3 -m pytest tests/smoke/test_coach_decisions.py -q
    python3 -m pytest tests/smoke -q
    npm run build --prefix web
    git diff --check

## Validation and Acceptance

The change is accepted when `GET /api/decisions` returns both the existing proposal history and pending-only proposal metadata, and the web build proves the TypeScript UI consumes the contract. A user can verify behavior manually by running `./run_web.sh`, opening `http://localhost:3000/decisions`, and checking that pending proposals appear in the top `Ожидают подтверждения` section with `Подтвердить` and `Отменить` controls. After clicking either action, the proposal should leave the pending section and remain visible in history with its resolved status.

The empty state must still render when the response has no decisions and no proposals. Existing decision entries must still render exactly through `DecisionEntry`.

## Idempotence and Recovery

The API change is additive and backward compatible. Existing clients that only read `days` or `proposal_days` continue to work. Approve and reject buttons reuse existing server endpoints that already reject non-pending proposals with HTTP 409, so a stale browser tab cannot apply the same proposal twice. If a web refresh fails after an action, reloading `/decisions` will fetch the durable proposal status from SQLite.

## Artifacts and Notes

This plan is intentionally smaller than the issue #71 lifecycle plan. It does not alter `data/database.py`, `api/planning_service.py`, or coach stream behavior.

## Interfaces and Dependencies

`GET /api/decisions` must include these additional fields:

    pending_proposal_count: number
    pending_proposal_days: Array<{ date: string, proposals: CoachProposal[] }>

`web/lib/types.ts` must mirror those fields on `CoachDecisionsResponse`.

`web/app/decisions/page.tsx` must use:

    ProposalCard
    SWR mutate()

to apply approvals and refresh the decisions page state.
