# Async Garmin Sync Job Contract

This ExecPlan is a living document. It follows `.agent/PLANS.md` and must keep
`Progress`, `Surprises & Discoveries`, `Decision Log`, and
`Outcomes & Retrospective` current while work proceeds.

## Purpose / Big Picture

Garmin sync can take minutes when Garmin is slow or rate-limiting. Before this
change, the web dashboard kept a single `POST /api/sync` request open until the
whole sync finished, so local Next.js proxy timeouts could make the UI report an
error while the backend kept syncing in the background. After this change,
`POST /api/sync` starts or reuses a background sync job and returns quickly with
a `job_id`, lifecycle state, and progress. The dashboard then polls
`GET /api/sync` until the job is done, so the browser is no longer responsible
for holding a long blocking request open.

## Progress

- [x] (2026-07-02 12:04Z) Confirmed issue #50 is open and moved it from
  `status: queued` to `status: in progress`.
- [x] (2026-07-02 12:04Z) Created branch `codex/async-garmin-sync-job-50`.
- [x] (2026-07-02 12:09Z) Inspected current sync API, sync service progress
  callback, dashboard caller, and frontend types.
- [x] (2026-07-02 12:18Z) Added contract-first smoke tests for idle, running, duplicate start,
  success, partial, and failure states.
- [x] (2026-07-02 12:29Z) Implemented an in-process sync job manager and wired it into
  `api/routers/system.py`.
- [x] (2026-07-02 12:44Z) Updated the Next.js dashboard sync button to start a job and poll status.
- [x] (2026-07-02 12:54Z) Ran smoke tests and web build locally. Commit, push, PR,
  and GitHub checks remain.

## Surprises & Discoveries

- Observation: #10 already added a lightweight `GET /api/sync` idle contract and
  `sync_state` in completed sync payloads.
  Evidence: `api/routers/system.py::sync_status` returns `sync_state: "idle"`,
  and `services/sync.py::build_sync_status_payload` returns `succeeded` or
  `partial`.
- Observation: The only current web caller is dashboard `SyncButton`, which
  awaits `postJSON<SyncResult>("/api/sync", {})`.
  Evidence: `rg -n "/api/sync|SyncResult" web` only finds
  `web/app/dashboard/page.tsx` and shared type declarations.
- Observation: Calling the public snapshot helper while already holding the
  manager lock deadlocked the first sync-job test.
  Evidence: The first `tests/smoke/test_sync_job_api.py` run hung until
  interrupted; the fix split the helper into locked and public variants.

## Decision Log

- Decision: Implement an in-process job manager with `threading.Thread` and a
  process-local lock instead of adding Redis, Celery, or a database queue.
  Rationale: This project is currently a local single-athlete FastAPI/Next.js
  app. The immediate product failure is a long HTTP request and duplicate
  clicks in one process. A process-local job manager solves that without new
  dependencies. Multi-worker durable jobs can be a later deployment issue if
  the app moves to a horizontally scaled server.
  Date/Author: 2026-07-02 / Codex.
- Decision: Keep `POST /api/sync` backward-compatible at the endpoint path but
  change its behavior to start/reuse a job and return quickly.
  Rationale: The web caller can migrate without changing URL structure, and
  API clients can read `sync_state` to distinguish `running` from completed
  payloads.
  Date/Author: 2026-07-02 / Codex.
- Decision: Poll `GET /api/sync` from the dashboard instead of adding SSE in
  this slice.
  Rationale: Polling is simpler, testable, and sufficient for one sync button.
  `SyncProgressUpdate` still surfaces progress through the job snapshot, so SSE
  can be added later without changing the job state model.
  Date/Author: 2026-07-02 / Codex.

## Outcomes & Retrospective

Implemented outcome: dashboard sync no longer depends on a minutes-long `POST`.
`POST /api/sync` now starts or reuses a background job and returns a `job_id`
plus `sync_state`. Duplicate starts return the running job with `reused: true`.
`GET /api/sync` exposes idle/running/succeeded/partial/failed states, progress,
timestamps, final result, error payloads, and the existing operational-state
envelope. The dashboard polls the status endpoint until terminal state and
does not refresh SWR data after a failed job.

Validation completed locally:

    python3 -m pytest tests/smoke/test_sync_job_api.py tests/smoke/test_api_operational_states.py tests/smoke/test_api_phase3.py tests/smoke/test_garmin_sync_service.py tests/smoke/test_sync_incremental.py -q
    # 24 passed
    python3 -m pytest tests/smoke -q
    # 286 passed
    cd web && npm run build
    # Next.js production build passed
    git diff --check
    # passed

## Context and Orientation

The FastAPI system router lives in `api/routers/system.py`. It currently
authenticates Garmin and runs `services.sync.sync_garmin_data(...)` directly
inside `POST /api/sync`. The sync service already accepts an `on_progress`
callback that receives `SyncProgressUpdate` objects with `percent`, `message`,
`step_text`, and optional stats. Completed sync summaries are produced by
`services.sync.build_sync_status_payload(...)`.

The frontend dashboard lives in `web/app/dashboard/page.tsx`. Its `SyncButton`
currently calls `postJSON("/api/sync", {})` and waits for the completed result.
Shared frontend response types live in `web/lib/types.ts`, and the fetch helper
is in `web/lib/api.ts`.

An "async sync job" in this plan means a Python thread created by the FastAPI
process. The job manager stores a snapshot of the current or latest sync in
memory. That snapshot is enough for the local app and contributor-safe tests.

## Plan of Work

First, create tests under `tests/smoke/test_sync_job_api.py`. The tests should
not use real Garmin. They should monkeypatch authentication and sync execution,
start a job, assert `POST /api/sync` returns quickly with `sync_state:
"running"`, assert a second POST reuses the same `job_id`, and assert
`GET /api/sync` exposes running and final states.

Second, add `api/sync_jobs.py`. It should define a small dataclass snapshot and
manager methods: `start_or_get`, `status`, and `reset_for_tests`. The manager
must hold a lock when reading/writing shared job state. It must store the latest
progress event and the final sync payload or error payload.

Third, replace blocking logic in `api/routers/system.py::sync` with a call into
the job manager. The worker thread should do the same Garmin auth and
`sync_garmin_data` call that the router currently does, but off the request
thread. It should pass `on_progress` so the job status updates while running.
`GET /api/sync` should return the current snapshot instead of always returning
idle.

Fourth, update `web/app/dashboard/page.tsx` and `web/lib/types.ts` so the sync
button posts once, then polls `GET /api/sync` every couple of seconds until the
job is `succeeded`, `partial`, or `failed`. During `running`, the button should
show progress text and remain disabled.

## Concrete Steps

Work from repository root:

    cd /Users/gregkisel/Developer/ai_trainer
    python3 -m pytest tests/smoke/test_sync_job_api.py -q
    python3 -m pytest tests/smoke/test_api_operational_states.py tests/smoke/test_api_phase3.py tests/smoke/test_garmin_sync_service.py -q
    python3 -m pytest tests/smoke -q
    cd web && npm run build
    git diff --check

The new sync-job tests should fail before implementation because `POST
/api/sync` is still blocking and no job manager exists. After implementation,
all commands should pass.

## Validation and Acceptance

Acceptance is met when:

1. `POST /api/sync` returns quickly with a `job_id` and `sync_state:
   "running"` or returns the currently running job.
2. A second `POST /api/sync` while a job is running returns the same `job_id`
   and does not invoke Garmin sync again.
3. `GET /api/sync` reports `idle`, `running`, `succeeded`, `partial`, or
   `failed` with progress and timestamps.
4. `SyncProgressUpdate` data is visible in the API status payload while running.
5. Dashboard sync UI no longer waits on a long blocking POST and polls status
   until completion.
6. Contributor-safe smoke tests and web build pass.

## Idempotence and Recovery

The job manager is in-process memory only. Restarting FastAPI resets job state
to idle, which is acceptable for the local app. Tests must call the reset helper
between scenarios to avoid leaking state. No database migration or destructive
operation is required.

## Artifacts and Notes

Current issue body for #50 states that duplicate concurrent sync runs must be
prevented and progress should be exposed through the API. The immediate prior
mitigation for #45 was `experimental.proxyTimeout`; this feature should remove
the product dependency on that long request.

## Interfaces and Dependencies

In `api/sync_jobs.py`, expose:

    sync_job_manager
    class SyncJobManager:
        def start_or_get(self, *, days: int | None, run_sync: Callable) -> dict
        def status(self, db=None, demo: bool = False) -> dict
        def reset_for_tests(self) -> None

The public payload should include:

    job_id: str | None
    sync_state: "idle" | "running" | "succeeded" | "partial" | "failed"
    started_at: str | None
    finished_at: str | None
    progress: dict | None
    result: dict | None
    error: dict | None
    operational_state: dict

Revision note (2026-07-02 / Codex): initial ExecPlan created after issue #50
triage and before tests.
