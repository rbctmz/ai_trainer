# Formalize Web API Operational State Contracts

This ExecPlan is a living document. It follows `.agent/PLANS.md` and must keep
`Progress`, `Surprises & Discoveries`, `Decision Log`, and
`Outcomes & Retrospective` current while work proceeds.

## Purpose / Big Picture

The Next.js frontend currently infers whether an API response represents demo
data, empty data, stale data, sync success, partial sync, or an error by looking
at missing fields and endpoint-specific strings. After this change, the web API
will expose an explicit `operational_state` object on the affected endpoints so
the frontend can render state directly and consistently. A developer can verify
the behavior by calling API router functions in smoke tests and seeing stable
machine-readable state fields alongside the existing payload fields.

## Progress

- [x] (2026-07-02 11:36Z) Closed issue #45 as completed and created follow-up
  issue #50 for the larger async sync-job contract.
- [x] (2026-07-02 11:38Z) Marked issue #10 as `status: in progress` and created
  branch `codex/operational-state-contracts-10`.
- [x] (2026-07-02 11:42Z) Inspected existing API surfaces in `api/routers/*`,
  `api/deps.py`, and `services/sync.py`.
- [x] (2026-07-02 11:39Z) Added contract-first smoke tests for empty, demo,
  stale, sync, and coach operational states; confirmed they failed before
  implementation with missing `operational_state` and missing `GET /api/sync`.
- [x] (2026-07-02 11:45Z) Implemented `api/operational_state.py` and wired
  additive `operational_state` fields into dashboard, activities, HRV, sleep,
  coach, and sync endpoints.
- [x] (2026-07-02 11:48Z) Added sync lifecycle `sync_state` to
  `services/sync.py` and `GET /api/sync` idle status in `api/routers/system.py`.
- [x] (2026-07-02 11:50Z) Ran targeted API/sync smoke tests: 32 passed.
- [x] (2026-07-02 11:51Z) Ran full contributor-safe smoke suite:
  `284 passed`.
- [ ] Commit, push, and open a PR that closes #10.

## Surprises & Discoveries

- Observation: The previous agent summary for #10 did not land in `main`.
  Evidence: `rg -n "operational_state|build_operational_state"` returned no
  implementation hits in API code on `main`, while issue #10 was still open.
- Observation: The sync timeout bug #45 was already mitigated in code.
  Evidence: `web/next.config.mjs` has `experimental.proxyTimeout: 300_000` and
  a comment referencing issue #45.
- Observation: FastAPI `Query(False)` defaults are awkward for direct router
  tests because the function receives a `Query` object outside FastAPI.
  Evidence: early implementation treated direct calls as demo mode because the
  default query object was truthy. The fix was to use plain `demo: bool = False`;
  FastAPI still parses the query parameter, and direct smoke tests receive a
  real boolean.
- Observation: A local variable named `message` inside the streaming error
  handler shadowed the outer user message in Python's generator scope.
  Evidence: old coach tests produced an SSE error:
  `local variable 'message' referenced before assignment`. Renaming it to
  `error_message` restored token streaming.

## Decision Log

- Decision: Add `operational_state` as a new top-level field while preserving
  every existing response field.
  Rationale: This is backward-compatible for the current web UI and still gives
  new clients the explicit contract requested in #10.
  Date/Author: 2026-07-02 / Codex.
- Decision: Use a small shared helper in `api/operational_state.py` instead of
  pushing state logic into each router.
  Rationale: Demo/live mode, empty, stale, latest timestamp, sync state, and
  error shape must remain consistent across endpoints.
  Date/Author: 2026-07-02 / Codex.
- Decision: Keep this PR synchronous and defer durable async sync jobs to #50.
  Rationale: #10 is about explicit contracts on current endpoints. Changing sync
  execution semantics would widen the blast radius and duplicate #50.
  Date/Author: 2026-07-02 / Codex.

## Outcomes & Retrospective

Implementation result: the API now returns additive `operational_state` fields
on dashboard, activities, HRV, sleep, coach meta/history, and sync status
surfaces. Existing response fields remain in place. `services/sync.py` now
emits `sync_state` as `succeeded` or `partial` for completed sync summaries, and
`api/routers/system.py` exposes `GET /api/sync` for idle/status reads plus
machine-readable sync error details. Validation passed with:

    python3 -m pytest tests/smoke/test_api_operational_states.py tests/smoke/test_api_dashboard.py tests/smoke/test_api_phase1.py tests/smoke/test_api_phase3.py tests/smoke/test_garmin_sync_service.py tests/smoke/test_sync_incremental.py -q
    32 passed

    python3 -m pytest tests/smoke -q
    284 passed

    git diff --check
    no output

## Context and Orientation

The product is migrating from Streamlit to `api/` plus `web/`. The FastAPI
application is defined in `api/main.py` and includes routers for dashboard,
activities, HRV, sleep, coach, planning, and system endpoints. The shared
database wrapper is `data/database.py`; it can read recent activities, HRV, and
sleep data and stores `user_settings`, including `dataset_origin` written by
`services/demo_mode.py`.

An "operational state" is the API's explicit machine-readable description of
whether a response is usable and why. In this repository it should include:
`status` (`ready`, `empty`, `stale`, or `error`), `mode` (`live` or `demo`),
boolean `demo`, boolean `empty`, boolean `stale`, `latest_data_at`, `sync_state`,
and optional `error` metadata.

Existing clients already consume fields such as `has_data`, `summary`, `items`,
`latest`, and `trend`. Those fields must stay in place. The new contract is
additive.

## Plan of Work

First, add smoke tests that describe the new contract. The tests should use
temporary SQLite databases and direct router calls, not real Garmin or real AI
providers. Add or update tests under `tests/smoke/`.

Second, create `api/operational_state.py`. It should provide helpers for turning
dataframes and database state into the shared `operational_state` dictionary.
It should avoid importing Streamlit and should not write to the database.

Third, wire the helper into `api/routers/dashboard.py`,
`api/routers/activities.py`, `api/routers/hrv.py`, `api/routers/sleep.py`,
`api/routers/coach.py`, and `api/routers/system.py`. Keep the current response
shape and add the new field. For sync, add `GET /api/sync` returning an idle
contract, and add `sync_state` to the existing `POST /api/sync` result.

Fourth, validate with targeted smoke tests and the broader smoke suite. Commit
and open a PR with `Closes #10`.

## Concrete Steps

Work from repository root:

    cd /Users/gregkisel/Developer/ai_trainer
    python3 -m pytest tests/smoke/test_api_operational_states.py -q
    python3 -m pytest tests/smoke/test_api_dashboard.py tests/smoke/test_api_phase1.py tests/smoke/test_api_phase3.py tests/smoke/test_garmin_sync_service.py -q
    python3 -m pytest tests/smoke -q
    git diff --check

The first test command should fail before implementation because
`operational_state` does not exist. After implementation, all listed commands
should pass.

## Validation and Acceptance

Acceptance for #10 is met when:

1. Empty dashboard, activities, HRV, and sleep payloads include
   `operational_state.status == "empty"` and keep their old empty fields.
2. Demo data payloads include `operational_state.mode == "demo"` and
   `operational_state.demo is True`.
3. Old data payloads include `operational_state.stale is True` and
   `status == "stale"`.
4. Coach stream `meta` events and coach history responses include
   `operational_state`.
5. Sync status responses include explicit `sync_state`; successful sync payloads
   are `succeeded` or `partial`, and failure details are machine-readable.
6. Contributor-safe smoke tests pass without real Garmin credentials.

## Idempotence and Recovery

The change is additive and safe to rerun. It does not migrate or delete data. If
an endpoint accidentally breaks an existing shape, revert only the route edits
and keep the tests as the source of the desired contract.

## Artifacts and Notes

Current evidence before implementation:

    gh issue list --state open
    #10 Formalize demo, sync, stale and error state contracts for web API
    #21 feat(coach): agent decision log ...
    #23 feat(planning): weekly target math ...
    #45 fix(web): dev-proxy timeout ...

Issue #45 has since been closed and follow-up #50 now tracks async sync jobs.

## Interfaces and Dependencies

In `api/operational_state.py`, define these public helpers:

    latest_iso_from_frame(frame, column="date") -> str | None
    latest_iso_from_database(db) -> str | None
    build_operational_state(
        db,
        *,
        demo: bool = False,
        has_data: bool,
        latest_data_at: str | None = None,
        sync_state: str = "idle",
        error: dict | None = None,
        stale_after_days: int = 2,
    ) -> dict

The returned dictionary must be JSON-serializable and must not contain pandas or
datetime objects.

Revision note (2026-07-02 / Codex): initial ExecPlan created after issue triage
and before contract tests.

Revision note (2026-07-02 / Codex): updated after implementation and validation
to record the direct-router `demo` default decision, the coach generator
shadowing fix, and the green test evidence.
