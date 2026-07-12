# Package AI Trainer as a self-hosted, password-protected web service (Docker + Caddy)

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must remain current while work proceeds. This document is maintained according to `.agent/PLANS.md`. It implements Issue #166 (service readiness, step 1).

## Purpose / Big Picture

Today AI Trainer runs only on a developer machine: `./run_web.sh` starts a FastAPI backend on `:8000` and a Next.js dev server on `:3000`, both bound to localhost, with no authentication of any kind. There is no way to run the product on a VPS or home server and reach it safely from a phone or another computer.

After this change, a person with a Linux host and Docker can clone the repository, fill in `.env`, run `docker compose up -d --build`, and get the full AI Trainer web UI served through a single edge proxy (Caddy) that requires a username and password and — when a `DOMAIN` is configured — terminates HTTPS with an automatic Let's Encrypt certificate. The SQLite database lives in a named Docker volume and survives container rebuilds. The FastAPI backend is never published to the host network; only Caddy is reachable from outside.

This is deliberately a **single-user** deployment. Multi-tenancy (per-user rows in the database, real login accounts, official Garmin OAuth, billing) is out of scope and belongs to later service-readiness steps. The security model of this step is: network isolation inside the Compose network, plus one shared basic-auth credential at the edge, plus HTTPS.

## Progress

- [x] (2026-07-12 12:05Z) Researched the current runtime: `api/main.py` (CORS, `/api/health`), `api/deps.py` (database resolution), `api/sync_jobs.py` (process-local jobs), `web/next.config.mjs` (rewrites, proxy timeout), `run_web.sh` (health polling), `.gitignore` (secrets/db exclusions). Findings recorded below.
- [x] (2026-07-12 12:10Z) Authored this plan; created Issue #166 and branch `claude/issue-166-self-hosted-deploy`.
- [x] (2026-07-12 13:05Z) Added the deployment behavior/security contract as smoke tests before implementation. On a checkout without `docker-compose.yml` the module intentionally skips; once Milestone 1 introduces Compose, the incomplete topology must fail until Milestones 2–3 are present.
- [ ] Milestone 1: backend image (`Dockerfile.api`), `.dockerignore`, Compose skeleton, compiler fallback, and data volume created. Pip successfully built `spectrum` and installed the complete dependency graph; final image export and runtime health acceptance are blocked by the host disk having only 560 MB free.
- [x] (2026-07-12 13:55Z) Milestone 2: web image (`web/Dockerfile`, `web/.dockerignore`) and Compose `web` service implemented. The container production build completed, including Next compilation, lint, TypeScript checks, and all 12 static routes.
- [ ] Milestone 3: Caddy edge (`deploy/Caddyfile`), basic auth + HTTPS, and private API/web ports implemented; 401/200 runtime acceptance pending the API image build.
- [x] (2026-07-12 14:00Z) Milestone 4: deployment smoke test, `.env.example` additions, and README self-hosting/migration guide implemented.
- [ ] Validation: Compose config, deployment guardrails, smoke suite, and Next production image build are green. Full container runtime acceptance remains blocked until host disk space is recovered without deleting Docker volumes.

## Surprises & Discoveries

- Observation: the repository already has the health endpoint this plan needs.
  Evidence: `api/main.py` defines `GET /api/health` returning `{"status": "ok"}`, and `run_web.sh` already polls it with a 0.5 s timeout before starting Next.js. The container health check reuses the same contract.

- Observation: background Garmin sync is process-local, which constrains how uvicorn may run.
  Evidence: `api/sync_jobs.py` documents that `SyncJobManager` "intentionally avoids external queues because the current product runs as a local single-user FastAPI process" and coordinates a `threading.Thread` behind a `Lock`. Additionally `api/deps.py` caches `Database` handles in an `lru_cache`. Running uvicorn with `--workers N>1` would give each worker its own job manager and cache, so sync status queries could hit a worker that knows nothing about a running job. The backend container therefore MUST run a single uvicorn process.

- Observation: `API_BASE_URL` is read at Next.js **server start**, not only at build time.
  Evidence: `web/next.config.mjs` computes `API_BASE` from `process.env.API_BASE_URL` at module evaluation, and `next start` re-evaluates `next.config.mjs` when the production server boots. This only holds if the runtime image ships `next.config.mjs` and does NOT use Next's `standalone` output mode (which inlines the config at build). The web Dockerfile below keeps the non-standalone layout on purpose so one built image works with any backend URL.

- Observation: a full Garmin sync can take minutes, so no proxy layer may impose a short upstream timeout.
  Evidence: `web/next.config.mjs` sets `experimental.proxyTimeout: 300_000` with a comment referencing issue #45 (default ~30 s dev proxy killed `POST /api/sync` with ECONNRESET under Garmin's 429 rate limiting). Caddy's `reverse_proxy` has no default upstream read timeout, so the edge adds no new limit; do not "harden" Caddy with a `response_header_timeout` shorter than ~5 minutes.

- Observation: no Garmin token cache needs persisting.
  Evidence: `data/garmin_client.py` authenticates through `garminconnect` with `GARMIN_EMAIL`/`GARMIN_PASSWORD` from the environment on each login call; fresh `garth` login is intentionally disabled. So the only state that must live in a volume is the SQLite files.

- Observation: CORS becomes irrelevant in this topology, no code change needed.
  Evidence: the browser only ever talks to the Caddy origin; Next.js proxies `/api/*` server-side to `http://api:8000` (same-origin from the browser's point of view). The existing `WEB_ORIGINS` default in `api/main.py` stays untouched.

- Observation: the original Dockerfile example and the planned guardrail disagreed about the literal `--workers` text.
  Evidence: the example comment said "Do not add --workers", while `test_deployment_config.py` is required to reject any Dockerfile containing that token. The implementation keeps the strict test and phrases the comment as "do not add multiple workers" so comments cannot mask an accidental flag.

- Observation: the first full image build reached PyPI but a slow download exhausted pip's default read timeout.
  Evidence: the build downloaded the 10.3 MB Streamlit wheel, then failed partway through the 12.1 MB pandas wheel with `ReadTimeoutError` from `files.pythonhosted.org`; no compiler or package-resolution error occurred. The API image now sets `PIP_DEFAULT_TIMEOUT=300` and `PIP_RETRIES=10`, making clean VPS builds tolerant of slow package mirrors while preserving the same dependency set.

- Observation: a second build proved the full Next.js image but Docker Desktop then returned an I/O error while pip was downloading an OpenCV wheel.
  Evidence: `npm ci` completed, `next build` compiled and type-checked all 12 routes, and the web image was exported. The API build progressed through the full dependency graph before `OSError: [Errno 5] Input/output error`; immediately afterwards `docker info` returned `EOF`, identifying the local Docker VM rather than the Dockerfile as the failed component.

- Observation: the clean arm64 API build needs a compiler for one transitive legacy analytics package.
  Evidence: after Docker recovery, pip resolved and downloaded the dependency graph successfully, then `spectrum` (pulled by `pyhrv`) failed while building `spectrum.mydpss` because `gcc` was absent. The documented Milestone 1 fallback was applied: install `build-essential` before pip and remove the apt package-list cache afterwards.

- Observation: the acceptance host ran out of physical disk space and Docker's content store became unreadable.
  Evidence: after `spectrum` built successfully and every Python package installed, BuildKit failed while committing `metadata_v2.db` with `input/output error`. Host `df` showed only 560 MB free on `/System/Volumes/Data`; Docker occupied 54 GB and reported about 33 GB of unused images. `docker system prune -af` (without volumes) could not complete because the already-starved content store returned the same blob I/O errors. Resetting Docker data would destroy unrelated volumes and was not attempted.

## Decision Log

- Decision: authenticate at the edge with Caddy `basic_auth`, not inside the application.
  Rationale: this step serves exactly one user. One bcrypt-hashed credential at the proxy protects both the UI and the API with zero product-code changes and zero new business logic to test. Real account-based auth is a multi-tenant concern and is explicitly deferred (see Issue #166 "Вне объёма").
  Date/Author: 2026-07-12 / Claude.

- Decision: keep the FastAPI container unpublished; only Caddy binds host ports.
  Rationale: defense by topology. Even with no application auth, the API is unreachable except through the authenticated proxy. The temporary `127.0.0.1` port bindings used in Milestones 1–2 for verification are removed in Milestone 3, and the smoke test pins that final state.
  Date/Author: 2026-07-12 / Claude.

- Decision: single uvicorn process, no `--workers`.
  Rationale: `SyncJobManager` state and `lru_cache`d `Database` handles are per-process (see Surprises). SQLite also prefers a single writer. Load is one athlete; throughput is not a concern.
  Date/Author: 2026-07-12 / Claude.

- Decision: base images `python:3.10-slim` and `node:20-alpine`.
  Rationale: match the runtimes the repository is developed and CI-tested against (local Python 3.10.11, Node 20, `web/package.json` targets Next 14). No gratuitous version jumps inside a packaging-only change.
  Date/Author: 2026-07-12 / Claude.

- Decision: keep the existing Next.js rewrite proxy; defer an API bearer token.
  Rationale: Next rewrites cannot attach an `Authorization` header, so an app-level API token would force replacing the rewrite with a catch-all route-handler proxy — a behavioral change to the request path (timeouts, streaming) far beyond packaging. Since the API has no published port, the token adds little in this topology. Milestone 4 of the service roadmap (multi-tenant auth) will revisit this properly.
  Date/Author: 2026-07-12 / Claude.

- Decision: do not trim `requirements.txt` for the image (Streamlit and friends get installed even though the container only runs FastAPI).
  Rationale: splitting requirements is a repo-wide refactor with its own risks; image size is not a goal of this step. Recorded as possible follow-up.
  Date/Author: 2026-07-12 / Claude.

- Decision: write the final-topology guardrails before the packaging files, even though the milestone list introduces the services incrementally.
  Rationale: this preserves the repository's TDD discipline. The test module remains bisect-safe by skipping when Compose is absent, then becomes red as soon as the first incomplete Compose skeleton exists and turns green only when the protected final topology is complete.
  Date/Author: 2026-07-12 / Codex.

- Decision: configure pip retries and a five-minute network timeout in the image build.
  Rationale: container builds are deployment infrastructure and must tolerate a slow but progressing package download. This changes only download recovery; dependency versions and the resulting runtime stay unchanged.
  Date/Author: 2026-07-12 / Codex.

- Decision: document database migration through a created-but-stopped API container rather than copying over a running SQLite process.
  Rationale: `docker compose create api` mounts the named volume without opening the database. Copying into that stopped container avoids replacing a file while SQLite connections may be live; a backup remains mandatory because a repeated copy intentionally overwrites the volume copy.
  Date/Author: 2026-07-12 / Codex.

- Decision: install `build-essential` in the API image.
  Rationale: `spectrum` has no usable prebuilt arm64 wheel in the resolved dependency set and compiles a small C extension. Keeping the existing requirements is an explicit scope constraint; splitting builder/runtime stages or trimming legacy analytics dependencies belongs to the recorded image-size follow-up.
  Date/Author: 2026-07-12 / Codex.

## Outcomes & Retrospective

The configuration, security guardrails, operator documentation, and production web image are implemented. The exercise found and fixed two real clean-build issues before publication: slow PyPI links now have explicit retry/timeout policy, and arm64 builds install the compiler required by `spectrum`. Compose validation and the contributor-safe smoke suite are green.

The only incomplete outcome is the end-to-end container runtime transcript. The local host exhausted its physical disk while BuildKit committed the API dependency layer, so the API image could not be exported even though dependency installation itself completed. Runtime checks (Caddy 401/200, demo seed, volume persistence, unpublished 8000/3000) must be resumed after the operator frees several gigabytes or moves Docker's disk image. Docker volumes were deliberately preserved.

## Context and Orientation

The repository contains one product with two UI surfaces and one shared Python core:

- `api/main.py` is the FastAPI entry point. All routes live under `/api/*` (routers in `api/routers/`). `GET /api/health` returns `{"status": "ok"}`. There is **no authentication anywhere** in this layer. On import it calls `load_dotenv()`, so a `.env` file in the working directory supplies secrets (`GARMIN_EMAIL`, AI provider keys, etc.).
- `web/` is a Next.js 14 app. The browser calls `/api/*` on the web origin; `web/next.config.mjs` rewrites those to `${API_BASE_URL}/api/*` server-side (default `http://127.0.0.1:8000`). Production mode is `npm run build` then `npm run start` (port 3000).
- Persistence is SQLite. `config/settings.py` reads `DATABASE_PATH` (default `ai_trainer.db` in the working directory). `api/deps.py` derives an isolated demo database path from it (`ai_trainer_demo.db`) unless `DEMO_DATABASE_PATH` overrides it. Both files must live on a persistent volume in Docker.
- `app.py` is the legacy Streamlit surface. It is NOT part of this deployment; `./run.sh` remains the local fallback.
- "Edge proxy" here means one Caddy container that is the only thing listening on host ports. Caddy checks a username/password (HTTP Basic Auth, bcrypt hash) and forwards everything to the Next.js container, which in turn proxies `/api/*` to FastAPI. Caddy obtains and renews TLS certificates automatically when given a real domain name.

New files created by this plan (all repository-relative):

- `Dockerfile.api` — backend image (repo root, because the API imports `services/`, `models/`, `data/`, `config/` from the repo root).
- `.dockerignore` — keeps secrets, local databases, venvs, and junk out of the build context.
- `web/Dockerfile`, `web/.dockerignore` — frontend image.
- `docker-compose.yml` — services `api`, `web`, `caddy`; named volumes `ai_trainer_data`, `caddy_data`, `caddy_config`.
- `deploy/Caddyfile` — edge configuration (basic auth + HTTPS-or-plain-HTTP).
- `tests/smoke/test_deployment_config.py` — guards the security-relevant invariants of the above.

## Plan of Work

### Milestone 1 — backend image and Compose skeleton

Create `.dockerignore` at the repo root. It must exclude at minimum: `.git`, `.env`, `*.db`, `ai_trainer_env/`, `web/node_modules/`, `web/.next/`, `__pycache__/`, `archived/`, `chats/`, `logs/`, `debug/`, `docs/`, `tests/`. Excluding `.env` and `*.db` is a security requirement (secrets and personal training data must never enter an image), the rest is build-context hygiene.

Create `Dockerfile.api` at the repo root:

    FROM python:3.10-slim

    ENV PYTHONUNBUFFERED=1 \
        PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=python \
        PIP_NO_CACHE_DIR=1

    WORKDIR /app

    COPY requirements.txt requirements-web.txt ./
    RUN pip install -r requirements.txt -r requirements-web.txt

    COPY . .

    EXPOSE 8000

    # Single process on purpose: SyncJobManager and the Database lru_cache are
    # process-local (api/sync_jobs.py, api/deps.py). Do not add --workers.
    CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]

`PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=python` mirrors `run.sh`/`run_web.sh` (Gemini/gRPC runtime compatibility). If `pip install` fails on a package needing compilation, add `RUN apt-get update && apt-get install -y --no-install-recommends build-essential && rm -rf /var/lib/apt/lists/*` before the pip step and record it in the Decision Log; on x86_64/arm64 all pinned packages are expected to have wheels for CPython 3.10.

Create `docker-compose.yml` with the `api` service only (the `web` and `caddy` services arrive in later milestones):

    services:
      api:
        build:
          context: .
          dockerfile: Dockerfile.api
        env_file: .env
        environment:
          DATABASE_PATH: /data/ai_trainer.db
        volumes:
          - ai_trainer_data:/data
        # TEMPORARY (Milestone 1-2 verification only, removed in Milestone 3):
        ports:
          - "127.0.0.1:8000:8000"
        healthcheck:
          test: ["CMD", "python", "-c", "import urllib.request,sys; sys.exit(0 if b'ok' in urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3).read() else 1)"]
          interval: 30s
          timeout: 5s
          retries: 5
          start_period: 30s
        restart: unless-stopped

    volumes:
      ai_trainer_data:

Notes a novice needs: `env_file: .env` injects the user's secrets at run time (never at build time); `DATABASE_PATH=/data/ai_trainer.db` overrides the repo-root default so SQLite lands on the named volume; `api/deps.py` will automatically derive the demo database as `/data/ai_trainer_demo.db`. The health check uses Python's stdlib because the slim image has no `curl`.

Acceptance: from the repo root, `docker compose up -d --build api`, then within ~30 s `docker compose ps` shows `api` as `healthy` and `curl -s http://127.0.0.1:8000/api/health` prints `{"status":"ok"}`. `curl -s -X POST http://127.0.0.1:8000/api/demo/seed` then `curl -s "http://127.0.0.1:8000/api/dashboard?demo=1"` proves the volume-backed database works end to end without touching real data.

### Milestone 2 — web image

Create `web/.dockerignore` containing `node_modules`, `.next`, `.env.local`.

Create `web/Dockerfile` (multi-stage; the final stage keeps `next.config.mjs` so `API_BASE_URL` stays a **runtime** setting — see Surprises):

    FROM node:20-alpine AS deps
    WORKDIR /app
    COPY package.json package-lock.json ./
    RUN npm ci --no-audit --no-fund

    FROM node:20-alpine AS build
    WORKDIR /app
    COPY --from=deps /app/node_modules ./node_modules
    COPY . .
    ENV NEXT_TELEMETRY_DISABLED=1
    RUN npm run build

    FROM node:20-alpine AS run
    WORKDIR /app
    ENV NODE_ENV=production \
        NEXT_TELEMETRY_DISABLED=1
    COPY --from=build /app/node_modules ./node_modules
    COPY --from=build /app/.next ./.next
    COPY --from=build /app/package.json ./package.json
    COPY --from=build /app/next.config.mjs ./next.config.mjs
    EXPOSE 3000
    CMD ["npm", "run", "start"]

There is no `web/public/` directory in this repository today; if one appears later, add `COPY --from=build /app/public ./public` to the run stage.

Add the `web` service to `docker-compose.yml`:

      web:
        build:
          context: web
        environment:
          API_BASE_URL: http://api:8000
        depends_on:
          api:
            condition: service_healthy
        # TEMPORARY (Milestone 2 verification only, removed in Milestone 3):
        ports:
          - "127.0.0.1:3000:3000"
        restart: unless-stopped

`http://api:8000` resolves via Compose's internal DNS; the browser never sees this address because the Next server proxies `/api/*` itself.

Acceptance: `docker compose up -d --build`, open `http://127.0.0.1:3000` — the dashboard page renders; `http://127.0.0.1:3000/api/health` returns `{"status":"ok"}` through the Next rewrite, proving web→api connectivity inside the Compose network.

### Milestone 3 — Caddy edge: basic auth and HTTPS

Create `deploy/Caddyfile`:

    {$DOMAIN::8080} {
        basic_auth {
            {$BASIC_AUTH_USER} {$BASIC_AUTH_HASH}
        }
        reverse_proxy web:3000
    }

How this reads: `{$DOMAIN::8080}` is a Caddy environment placeholder with a default — if `DOMAIN` is set (e.g. `trainer.example.com`), Caddy serves that site with automatic HTTPS (Let's Encrypt, ports 80+443); if `DOMAIN` is empty, Caddy serves plain HTTP on `:8080`, which is the local/LAN test mode. `basic_auth` rejects every request without the correct username/password with HTTP 401 before anything reaches the app. Do not add upstream timeouts to `reverse_proxy` (long Garmin syncs, see Surprises).

Add the `caddy` service to `docker-compose.yml`, and **delete the two temporary `ports:` blocks** from `api` and `web`:

      caddy:
        image: caddy:2
        ports:
          - "80:80"
          - "443:443"
          - "8080:8080"
        environment:
          DOMAIN: ${DOMAIN:-}
          BASIC_AUTH_USER: ${BASIC_AUTH_USER:?set BASIC_AUTH_USER in .env}
          BASIC_AUTH_HASH: ${BASIC_AUTH_HASH:?set BASIC_AUTH_HASH in .env}
        volumes:
          - ./deploy/Caddyfile:/etc/caddy/Caddyfile:ro
          - caddy_data:/data
          - caddy_config:/config
        depends_on:
          - web
        restart: unless-stopped

    volumes:
      ai_trainer_data:
      caddy_data:
      caddy_config:

`caddy_data` persists issued TLS certificates across restarts (avoids Let's Encrypt rate limits). The `:?` syntax makes Compose fail fast with a clear message when the auth variables are missing, so an unauthenticated deployment cannot be brought up by accident.

The user generates the bcrypt hash once:

    docker run --rm caddy:2 caddy hash-password --plaintext 'chosen-password'

and puts the output in `.env` as `BASIC_AUTH_HASH` (single-quote it in `.env`: bcrypt hashes contain `$`).

Acceptance (local mode, `DOMAIN` unset): `curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8080/api/health` prints `401`; the same with `-u user:chosen-password` prints `200`; the browser prompts for credentials at `http://127.0.0.1:8080` and then shows the dashboard; `curl` against `:8000`/`:3000` now fails to connect (ports no longer published). Domain mode is verified on a real VPS: with DNS A-record pointing at the host and `DOMAIN` set, `https://$DOMAIN` serves with a valid certificate — this check is deferred to first real deployment and recorded in `Outcomes & Retrospective` when done.

### Milestone 4 — guardrails and documentation

Create `tests/smoke/test_deployment_config.py`. Plain-text assertions, no new dependencies (do not import yaml). It must assert, by reading the files as strings: `.dockerignore` contains lines `.env` and `*.db`; `Dockerfile.api` does not contain `COPY .env` and does not contain `--workers`; `docker-compose.yml` does not publish `8000` or `3000` in any `ports:` mapping (only Caddy's 80/443/8080 are allowed) and sets `DATABASE_PATH: /data/ai_trainer.db`; `deploy/Caddyfile` contains `basic_auth`. Each assertion carries a message explaining the security invariant it protects. Skip the whole module with `pytest.skip(..., allow_module_level=True)` if `docker-compose.yml` does not exist, so the suite stays green on checkouts predating this plan (e.g. bisects).

Append to `.env.example` (with a comment block explaining each): `DOMAIN=`, `BASIC_AUTH_USER=trainer`, `BASIC_AUTH_HASH=` and a reminder that the hash comes from `caddy hash-password` and must be single-quoted.

Add a "Self-hosted deployment (Docker)" section to `README.md`: prerequisites (Docker + Compose plugin), the four commands (hash-password, edit `.env`, `docker compose up -d --build`, open the URL), the existing-data migration recipe (below), and a pointer to this ExecPlan. Keep the section's language consistent with the surrounding README style.

Existing-data migration (documented in README, not automated): a user who already has a local `ai_trainer.db` copies it into the volume once, before first start:

    cp ai_trainer.db ai_trainer.db.backup
    docker compose create api
    docker compose cp ai_trainer.db api:/data/ai_trainer.db
    docker compose up -d

Creating rather than starting the API ensures no SQLite process has the destination file open during the copy. `docker compose cp` is idempotent (it overwrites the target file); warn the user it replaces whatever the volume already holds and require the backup shown above.

## Concrete Steps

All commands run from the repository root on the branch `claude/issue-166-self-hosted-deploy`.

1. Implement Milestone 1 files; run `docker compose up -d --build api`; verify health per the milestone's acceptance; commit (`feat: containerize FastAPI backend with persistent SQLite volume`).
2. Implement Milestone 2 files; run `docker compose up -d --build`; verify per acceptance; commit (`feat: containerize Next.js web frontend`).
3. Implement Milestone 3; `docker compose up -d --build`; verify 401/200 behavior and the absence of published app ports; commit (`feat: add Caddy edge with basic auth and automatic HTTPS`).
4. Implement Milestone 4; run the smoke suite; commit (`test+docs: deployment config guardrails and self-hosted guide`).
5. After each commit: `python -m pytest tests/smoke -q` must stay green.
6. Push and open a PR that references Issue #166; paste the acceptance transcript into the PR description.

Expected smoke run tail (count will differ as the suite grows):

    python -m pytest tests/smoke -q
    ...
    NNN passed in XX.XXs

## Validation and Acceptance

The change is accepted when, on a clean checkout with Docker installed and a filled `.env` (Garmin + AI keys + `BASIC_AUTH_USER`/`BASIC_AUTH_HASH`):

1. `docker compose up -d --build` completes; `docker compose ps` shows `api` healthy and all three services `Up`.
2. `curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8080/` → `401`.
3. `curl -s -u trainer:chosen-password http://127.0.0.1:8080/api/health` → `{"status":"ok"}`.
4. In a browser at `http://127.0.0.1:8080` (after the auth prompt): the dashboard renders; `POST /api/demo/seed` via the demo controls (or `curl -su trainer:pass -X POST http://127.0.0.1:8080/api/demo/seed`) populates demo data and pages render with `?demo=1`.
5. `docker compose down` followed by `docker compose up -d` preserves all data (named volume), demonstrated by re-opening a page that shows previously synced or seeded data.
6. `curl http://127.0.0.1:8000/api/health` and `curl http://127.0.0.1:3000` both fail to connect from the host.
7. `python -m pytest tests/smoke -q` passes, including the new `test_deployment_config.py`.

## Idempotence and Recovery

Every step is re-runnable: `docker compose up -d --build` converges to the declared state; `npm ci` and `pip install` in image builds are hermetic; the smoke test only reads files. To reset completely, `docker compose down` (add `-v` ONLY if the operator explicitly wants to destroy training data — say so out loud in any instructions). If a Let's Encrypt issuance fails (DNS not propagated), Caddy retries automatically; certificates live in the `caddy_data` volume so restarts do not re-issue. If the backend image build fails at pip, see the `build-essential` fallback in Milestone 1. Nothing in this plan modifies existing application code paths, so reverting is `git revert` of the packaging commits plus `docker compose down`.

## Artifacts and Notes

Captured locally on 2026-07-12:

    docker compose config --quiet
    # exit 0; services: api, web, caddy

    python -m pytest tests/smoke -q
    501 passed, 1 skipped in 11.26s

    docker compose build web
    Compiled successfully
    Linting and checking validity of types ...
    Generating static pages (12/12)
    image ai_trainer_issue166_selfhosted-web exported

    docker compose build api
    Successfully built spectrum
    Successfully installed ... streamlit-1.59.1 ... uvicorn-0.51.0 ...
    error committing ... metadata_v2.db: input/output error

Pending after host disk recovery: `docker compose ps`, the Caddy 401/200 curl transcript, demo seed, named-volume restart persistence, and proof that host ports 8000/3000 are closed.

## Interfaces and Dependencies

No Python or TypeScript source files change. The deliverable is configuration only:

- `Dockerfile.api`, `.dockerignore` (repo root)
- `web/Dockerfile`, `web/.dockerignore`
- `docker-compose.yml` (repo root; services `api`, `web`, `caddy`; volumes `ai_trainer_data`, `caddy_data`, `caddy_config`)
- `deploy/Caddyfile`
- `tests/smoke/test_deployment_config.py`
- `.env.example` additions: `DOMAIN`, `BASIC_AUTH_USER`, `BASIC_AUTH_HASH`
- `README.md` section "Self-hosted deployment (Docker)"

External images: `python:3.10-slim`, `node:20-alpine`, `caddy:2` — all official library images. No new Python/npm dependencies.

Follow-ups explicitly out of scope (candidates for the next service-readiness ExecPlans): account-based authentication and multi-tenant schema (Postgres, `user_id`), official Garmin OAuth instead of `garminconnect` credentials, an app-level API token (requires replacing the Next rewrite proxy with a route handler that can attach headers), request rate limiting, structured production logging, and trimming `requirements.txt` into runtime vs. legacy-Streamlit sets to shrink the backend image.
