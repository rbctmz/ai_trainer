# Readiness Snapshot Contract for Adaptive Coaching

This ExecPlan is a living document. It follows `.agent/PLANS.md` and must keep `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` current as the work proceeds.

## Purpose / Big Picture

AI Trainer already shows readiness-like numbers, but those numbers are not exposed as one stable API contract. A frontend or coach runtime can see a score, but it cannot reliably know whether the score is fresh, which recovery inputs contributed to it, which inputs are missing, or whether the result should be treated as provisional. After this change, dashboard, coach, and planning clients can read one additive `readiness_snapshot` object and make conservative UI or coaching decisions without guessing.

The user-visible proof is simple: API responses from `/api/dashboard/summary`, `/api/planning/status`, and the first `meta` event from `/api/coach/chat` contain a machine-readable `readiness_snapshot` with `score`, `status`, `computed_at`, `is_provisional`, `source_completeness`, `factors`, `missing_inputs`, `stale`, and `reason`. Existing fields remain unchanged.

## Progress

- [x] (2026-07-08 15:43+03:00) Created GitHub issue #112 and branch `codex/issue-112-readiness-snapshot`.
- [x] (2026-07-08 15:52+03:00) Audited current dashboard, coach, planning, database, and signals-engine readiness paths.
- [x] (2026-07-08 21:33+03:00) Added failing contributor-safe smoke tests for empty, partial, stale, full-data, dashboard, coach meta, and planning status contracts. The first run failed with `ModuleNotFoundError: No module named 'api.readiness_snapshot'` and missing `readiness_snapshot` keys.
- [x] (2026-07-08 21:38+03:00) Implemented `api/readiness_snapshot.py` as an additive contract wrapper over existing Phase 1 readiness math.
- [x] (2026-07-08 21:40+03:00) Wired the builder into dashboard summary, coach stream meta, and planning status.
- [x] (2026-07-08 21:44+03:00) Added TypeScript contract types in `web/lib/types.ts`.
- [x] (2026-07-08 21:47+03:00) Validation passed: new smoke test `7 passed`, focused API smoke `22 passed`, full smoke `372 passed, 1 skipped`, and `web` `npm run build` passed.
- [ ] Publish PR that closes #112.

## Surprises & Discoveries

- Observation: `models/signals_engine.py` already describes itself as a unified recovery/load signal assembly layer, but it is optimized for broad UI signal semantics rather than a specific API snapshot contract.
  Evidence: `assemble_signals()` feeds planning metrics and dashboard signals, while API routers still emit no explicit readiness provenance object.

- Observation: The socket preflight smoke test is skipped in this execution environment.
  Evidence: `python3 -m pytest tests/smoke -q` reported `SKIPPED [1] tests/smoke/test_run_web_preflight.py:52: environment does not allow opening a local listening socket`, with all other smoke tests passing.

## Decision Log

- Decision: Add a small API-layer readiness snapshot builder instead of changing the existing readiness math.
  Rationale: The issue is contract and provenance, not a mathematical redesign. Reusing `Phase1DataProcessor.calculate_comprehensive_readiness()` keeps existing scoring semantics intact while making freshness, missing inputs, and provisional state explicit.
  Date/Author: 2026-07-08 / Codex.

- Decision: Treat the snapshot as additive top-level API metadata.
  Rationale: Existing web consumers already rely on current payload shapes. Adding `readiness_snapshot` without removing or renaming fields keeps backward compatibility and lets UI adopt the contract incrementally.
  Date/Author: 2026-07-08 / Codex.

- Decision: Mark a snapshot provisional when Garmin `training_readiness` is absent even if the app can compute a fallback score from sleep/HRV/health.
  Rationale: This preserves a conservative distinction between an anchored Garmin readiness signal and a locally computed partial estimate. It lets coach/UI clients decide how much confidence to place in the score.
  Date/Author: 2026-07-08 / Codex.

## Outcomes & Retrospective

Implemented. The API now exposes a shared readiness snapshot from dashboard summary, planning status, and the coach stream meta event. The change is additive and keeps existing payload fields intact. It does not redesign readiness math; it wraps the existing Phase 1 calculator with provenance, completeness, missing-input, stale, and provisional metadata.

## Context and Orientation

The active product path is FastAPI in `api/` and Next.js in `web/`. The legacy Streamlit UI remains a fallback and is not the target for this issue.

Readiness data comes from several persisted tables in `data/database.py`: `sleep_data` stores sleep score and duration, `hrv_data` stores RMSSD and stress, `daily_health` stores resting heart rate and wellness signals, and `training_status` stores Garmin training readiness when Garmin provides it. Existing scoring logic lives in `data/data_processor_phase1.py` as `Phase1DataProcessor.calculate_comprehensive_readiness()`.

The API surfaces for this issue are `api/routers/dashboard.py`, `api/routers/coach.py`, and `api/planning_service.py` through `api/routers/planning.py`. The new contract should live in a small reusable module under `api/` so all three surfaces use the same rules.

## Plan of Work

First, add smoke tests under `tests/smoke/` that construct temporary SQLite databases with no Garmin credentials and call router functions directly. The tests should assert that empty data produces an unknown provisional snapshot, full data produces a non-provisional complete snapshot, partial data lists missing inputs, stale data marks the snapshot stale, and the dashboard, coach meta event, and planning status all include the same top-level field.

Next, add `api/readiness_snapshot.py`. It should read the latest rows from `Database.get_sleep_data()`, `get_hrv_data()`, `get_daily_health()`, and `get_training_status_history()`. It should call `Phase1DataProcessor.calculate_comprehensive_readiness()` using those latest rows, normalize the result into a JSON-safe dict, compute a latest `computed_at` date from contributing sources, calculate `source_completeness` across the primary inputs `sleep`, `hrv`, `resting_hr`, and `training_readiness`, and set `is_provisional` when data is missing, stale, or no Garmin readiness exists.

Then wire this builder into the three API surfaces. `dashboard_summary()` should return `readiness_snapshot` beside `summary` and `operational_state`. The coach stream first `meta` event should include it. `planning_service.current_status()` should include it so `/api/planning/status` exposes the same contract.

## Concrete Steps

Run focused tests from the repository root:

    python3 -m pytest tests/smoke/test_readiness_snapshot_contract.py -q

Run the existing nearby smoke tests:

    python3 -m pytest tests/smoke/test_api_dashboard.py tests/smoke/test_api_planning.py tests/smoke/test_api_operational_states.py -q

If TypeScript API types are changed, run:

    cd web && npm run build

## Validation and Acceptance

The change is accepted when the new smoke test proves all required snapshot states and the existing dashboard, planning, and operational-state smoke tests still pass. A manual API check after `./run_web.sh` should show `readiness_snapshot` in JSON responses from `/api/dashboard/summary` and `/api/planning/status`, and the first SSE event from `/api/coach/chat` should include the same field.

## Idempotence and Recovery

The implementation is additive. If a seeded test database has no data, the builder must return an unknown provisional snapshot instead of raising. If a database call fails, the router should still be able to return a conservative unknown snapshot. Re-running tests is safe because all tests use temporary SQLite files.

## Artifacts and Notes

The GitHub issue for this work is #112: `Backend: readiness snapshot contract for adaptive coaching`.

## Interfaces and Dependencies

In `api/readiness_snapshot.py`, define:

    def build_readiness_snapshot(db: Database, *, stale_after_days: int = 2) -> dict[str, Any]:

The returned dict must contain:

    score: float | None
    status: str
    computed_at: str | None
    is_provisional: bool
    source_completeness: float
    factors: list[dict[str, Any]]
    missing_inputs: list[str]
    stale: bool
    reason: str

Revision note (2026-07-08): initial plan created for issue #112 after comparing AI Trainer's current API state with IntervalCoach's recent readiness/adaptive-coaching changelog direction.
