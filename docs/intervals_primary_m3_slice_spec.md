# M3: source-agnostic sync UI and Intervals-first Docker handoff

This ExecPlan is a living document. The sections `Progress`, `Surprises &
Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to
date as work proceeds. This document is maintained in accordance with
`.agent/PLANS.md`.

## Purpose / Big Picture

After M3, a technical athlete who does not have Garmin credentials can clone AI
Trainer, configure an Intervals.icu API key, start the Docker stack, select
Intervals.icu in the product UI, synchronize activities, complete planning
onboarding, and see a first plan. The dashboard must no longer silently start
Garmin when Intervals.icu is the only configured activity source.

The observable acceptance path is:

    fresh SQLite → only Intervals.icu configured → source-aware sync →
    planning onboarding → preview/confirm → plan visible in Planning and Today

M3 does not import Intervals.icu wellness data. Sleep and HRV remain Garmin-only
until M4, so their empty-state copy must not promise Intervals support.

## Progress

- [x] (2026-07-26 21:42Z) Read issue #272, the parent ExecPlan, ADD/ASR
  constraints, the M1 sync API, the M2 onboarding vertical, and current Docker
  topology.
- [x] (2026-07-26 21:47Z) Added RED contract tests for provider discovery,
  source-aware dashboard copy, the Docker quickstart, and the complete hermetic
  handoff path. Evidence: 14 failed for the expected missing contracts.
- [x] (2026-07-27 13:10Z) Added the safe provider-status and explicit Intervals
  connection-test API contract through `services/sync_providers.py`; responses
  contain configuration flags and bounded summaries, never credentials.
- [x] (2026-07-27 13:25Z) Replaced the Garmin-hardcoded dashboard sync control
  with a reusable source-aware control and honest first-run guidance. The web
  caller now always sends the selected source; the API's absent-source Garmin
  compatibility remains unchanged.
- [x] (2026-07-27 13:40Z) Added and Compose-validated the Intervals-first Docker
  quickstart; `.env.example` no longer makes placeholder credentials look
  configured.
- [x] (2026-07-27 14:20Z) Ran focused M3 (14 passed), relevant regression
  (115 passed), smoke (1236 passed, 1 skipped), broad offline (1279 passed,
  6 skipped, 24 deselected), Ruff, web lint/build, Compose validation, and
  isolated browser acceptance.
- [x] (2026-07-27 14:35Z) Updated parent ExecPlan and ASR traceability and
  completed this retrospective.

## Surprises & Discoveries

- Observation: `POST /api/sync` is already source-aware, but the dashboard still
  posts an empty body. The API therefore uses its backward-compatible Garmin
  default even when only Intervals.icu is configured.
  Evidence: `web/app/dashboard/page.tsx::SyncButton` posts `{}`;
  `api/routers/system.py::SyncRequest.source` defaults to `garmin`.

- Observation: Intervals.icu already has safe `connection_info()` and
  `test_connection()` service functions, but no product API exposes them.
  Evidence: `services/intervals_icu.py`.

- Observation: copying the current `.env.example` creates non-empty placeholder
  Garmin credentials. A first-run UI cannot distinguish those placeholders from
  real credentials.
  Evidence: `.env.example` currently contains
  `GARMIN_EMAIL=your_garmin_email@example.com`.

- Observation: the default database path cannot be created inside a sandboxed
  Git worktree because it resolves below `.codex`; this is an execution-
  environment restriction rather than a product failure.
  Evidence: the first smoke run failed only while opening SQLite; the same suite
  passed with explicit temporary `DATABASE_PATH` and `DEMO_DATABASE_PATH`.

- Observation: a hermetic browser test can exercise the complete product path
  without live credentials by replacing only the Intervals HTTP server.
  Evidence: the isolated stack showed Intervals as configured and recommended,
  passed the explicit connection probe, synchronized activities, previewed and
  confirmed the first plan, then rendered that plan on `/today`.

## Decision Log

- Decision: Add `GET /api/sync/providers` as the safe, read-only provider
  discovery contract. It returns labels, configured flags, safe Intervals
  connection metadata, and a recommended source. It never returns credentials
  or API keys.
  Rationale: the frontend must not infer server-side secrets, and page rendering
  must not perform a live provider call.
  Date/Author: 2026-07-26 / Codex.

- Decision: The recommended source is the configured primary source; if that
  source is not configured, it falls back to the other configured source. If
  neither is configured, the configured primary remains selected but sync is
  disabled with setup guidance.
  Rationale: this preserves backward compatibility while making an
  Intervals-only first run work even if the operator forgot the optional
  `PRIMARY_ACTIVITY_SOURCE=intervals` setting.
  Date/Author: 2026-07-26 / Codex.

- Decision: Add `POST /api/sync/providers/intervals/test`, returning only
  `ok`, `source`, and `calendar_count`. Provider response bodies and calendar
  details are not exposed.
  Rationale: it uses the existing Intervals service boundary while respecting
  ASR-SEC-1.
  Date/Author: 2026-07-26 / Codex.

- Decision: Keep Garmin as the API default when `source` is omitted; change only
  the web caller to send the selected source explicitly.
  Rationale: M1 deliberately pinned the absent-field behavior for backward
  compatibility.
  Date/Author: 2026-07-26 / Codex.

- Decision: Do not generalize Sleep/HRV empty states in M3.
  Rationale: Intervals wellness mapping is M4; source-agnostic copy there would
  overpromise product capability.
  Date/Author: 2026-07-26 / Codex.

## Outcomes & Retrospective

M3 achieved the intended handoff: the browser no longer assumes Garmin, provider
configuration is obtained through a secret-safe backend contract, and an
Intervals-only athlete can travel from an empty database to a visible plan. The
existing sync API compatibility was preserved: callers that omit `source` still
get Garmin, while the new web control always submits an explicit choice.

The most useful design choice was keeping provider discovery and connection
testing in `services/sync_providers.py`. That kept the HTTP router thin, gave the
UI one stable contract, and made credential non-disclosure straightforward to
test. The browser acceptance caught the real product seam—the selected provider
must survive discovery, probe, sync, onboarding, confirm, and Today—not merely
the existence of individual endpoints.

M3 intentionally leaves Sleep and HRV Garmin-specific. Making their labels
source-neutral before Intervals wellness mapping would be misleading; M4 owns
that contract. The remaining deployment debt is operational backup/restore for
the named SQLite volume (ASR-DEP-2 remains yellow), not first-run startup.

## Context and Orientation

`api/routers/system.py` owns `GET/POST /api/sync` and delegates to the source-aware
job manager. `services/intervals_sync.py` fetches Intervals activities through
the common ingest path. `web/app/dashboard/page.tsx` owns the dashboard sync
control and first-run empty state. M2 added the planning onboarding API and
`/planning` card. `docker-compose.yml` already provides the authenticated
single-command stack and persistent SQLite volume.

“Configured” means the process has the credentials required to start that
provider. It does not claim the credentials are valid. “Connection test” means
an explicit user action that makes a bounded provider request.

## Plan of Work

First, add behavior tests. Backend contract tests will pin safe provider
discovery, recommendation rules, secret non-disclosure, and connection-test
failure mapping. A web contract test will pin explicit `{source}` submission and
remove Garmin-hardcoded dashboard/activities empty copy. A deployment test will
pin the quickstart’s required environment and commands. A hermetic vertical test
will replace only the Intervals HTTP transport, then call the real sync API,
onboarding API, planning build/confirm API, and public Planning/Today reads
against one temporary SQLite database.

Second, add `services/sync_providers.py` as the shared provider-discovery and
connection-probe boundary, then extend `api/routers/system.py` with two additive
endpoints that delegate to it. The service uses `Settings` plus
`services.intervals_icu.connection_info()` and `test_connection()`. The router
returns minimal dictionaries and maps provider/config errors to explicit HTTP
responses.

Third, extract a reusable source-aware sync control under
`web/components/sync/`. It will load provider discovery via SWR, select the
recommended source, post `{"source": selectedSource}`, and format progress using
the job’s actual source. The dashboard header uses a compact variant; the empty
dashboard uses a detailed variant with provider status and setup guidance.

Fourth, replace placeholder secrets in `.env.example` with empty values, add
`PRIMARY_ACTIVITY_SOURCE`, and write
`docs/intervals_primary_quickstart.md`. The quickstart will contain the exact
Docker commands and the UI path from sync through first plan.

Finally, update `docs/intervals_primary_handoff_execplan.md` and ASR traceability,
then run all verification contours.

## Concrete Steps

All commands run from the M3 worktree.

    python -m pytest tests/smoke/test_m3_intervals_handoff.py \
      tests/smoke/test_m3_sync_provider_api.py \
      tests/smoke/test_m3_sync_ui_contract.py \
      tests/smoke/test_m3_quickstart.py -q

    python -m pytest tests/smoke -q
    python -m pytest -m "not live and not debug" tests/
    npm --prefix web run lint
    npm --prefix web run build
    docker compose config --quiet

For browser acceptance, start an isolated API/web pair with a temporary
`DATABASE_PATH`, use a fake Intervals transport, open `/dashboard`, synchronize
Intervals, complete `/planning`, and verify `/today`. Stop both processes and
remove the temporary database afterward.

## Validation and Acceptance

The provider discovery endpoint must recommend `intervals` when Intervals is the
only configured source and must not contain the configured API key anywhere in
its serialized response. A failed explicit connection test must be visible and
must not alter sync state.

The dashboard must send the selected source in every sync request. Its idle,
running, partial, success, and failure messages must name the actual job source.
With no configured provider, sync is disabled and the UI names the exact
environment variables needed.

The hermetic handoff test must begin with an empty database and no Garmin
credentials, ingest Intervals activities via `POST /api/sync`, complete planning
onboarding, confirm a plan, and observe non-empty `/api/planning/plan` and a
non-`no_plan` `/api/today`.

The Docker quickstart must produce a valid Compose configuration and tell the
tester how to preserve the named SQLite volume. It must not instruct the user to
commit or paste secrets into the UI.

## Idempotence and Recovery

Provider discovery is read-only. The connection probe is read-only and
user-triggered. Activity sync remains idempotent through M0/M1 common ingest and
the persistent cursor. Planning preview remains non-persistent until confirm.
Repeated `docker compose up -d --build` reuses the named database volume;
`docker compose down -v` is documented as destructive.

If a handoff sync fails, the UI keeps the selected source and displays the job
error. The user can fix `.env`, restart the stack, and retry. No cursor advances
past a dirty Intervals chunk.

## Artifacts and Notes

ASR traceability:

- ASR-SEC-1: provider discovery and connection test expose no credentials.
- ASR-DEP-1: a tested Docker quickstart demonstrates one-command startup.
- ASR-DEP-2: the quickstart preserves the named SQLite volume and warns against
  destructive volume removal.
- ASR-MOD-2: the web control consumes an explicit API contract rather than
  reading provider assumptions from unrelated dashboard data.

## Interfaces and Dependencies

The additive backend interfaces are:

    GET /api/sync/providers
    {
      "recommended_source": "garmin" | "intervals",
      "providers": [
        {
          "source": "garmin" | "intervals",
          "label": str,
          "configured": bool,
          "connection": object | null
        }
      ]
    }

    POST /api/sync/providers/intervals/test
    {
      "ok": true,
      "source": "intervals",
      "calendar_count": int | null
    }

`SyncJobResponse` gains `source: "garmin" | "intervals" | null`. The dashboard
sync control always calls:

    POST /api/sync {"source": selectedSource}

No new third-party dependency is introduced.
