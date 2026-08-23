# Repository Guidelines

## Project Structure & Module Organization
AI Trainer is in an active web migration. The main product development path is `api/` + `web/`: `api/` exposes FastAPI contracts over shared Python logic, `web/` is the Next.js UI. Legacy Streamlit entry point is `app.py` — a thin fallback shell (page dispatch, sync callbacks, theme) while migration continues; Streamlit stays supported until parity, so never describe the project as already migrated.

- Intervals.icu is the recommended PRIMARY data source (`PRIMARY_ACTIVITY_SOURCE=intervals`, `services/intervals_icu.py`); Garmin Connect is the compatible optional second source (`data/garmin_client.py`). Route new ingestion through the service boundary in `services/` (sync, demo, acceptance orchestration) plus `config/settings.py` for all defaults/env lookups.
- `models/` = AI providers, coach runtime, planning, readiness/Banister metrics. `utils/` = shared helpers (metrics, Plotly/theme).
- `ui/pages/`, `ui/components/`, `state/` are legacy Streamlit surfaces; `state/manager.py` is Streamlit-specific and must not become the contract for new product flows. Treat them as maintenance/fallback unless the task explicitly targets Streamlit.
- Ignore `archived/`, `backups/`, `spikes/`, `debug/`, `examples/`, `research/`, `output/` (ruff-excluded experiment areas). `ai_trainer.db` at root is the local SQLite cache.

## Development Commands
```bash
source ai_trainer_env/bin/activate          # venv (Windows: Scripts\activate)
pip install -r requirements.txt -r requirements-dev.txt   # base + tests
pip install -r requirements-web.txt         # only for API/web runtime work
./setup_env.sh                              # bootstrap fresh environment

./run_web.sh        # FastAPI :8000 + Next.js :3000; auto-installs missing deps; override API_PORT=/WEB_PORT= if busy
./run.sh            # legacy Streamlit (:8501)
ACCEPTANCE_PORT=8510 ./run_acceptance.sh    # isolated temp-DB/demo-mode surface for browser checks
python scripts/doctor_env.py check|repair --runtime|--dev    # dependency diagnostics
```

Python lint and tests (mirrors CI `.github/workflows/ci.yml` exactly):
```bash
python -m ruff check .                                              # must be green (CI job)
python -m pytest -m "not live and not debug and not e2e" tests/     # contributor-safe pass
python -m pytest tests/smoke -q                                     # smoke subset
python -m pytest tests/test_ai_coach.py                             # focused module (swap filename)
python -m pytest -m e2e tests/e2e -q                                # Playwright web E2E, needs chromium
```
Pytest markers (`pytest.ini`): `smoke`, `live` (needs credentials/network/AI runtimes), `debug`, `e2e`. Do not treat bare `python -m pytest tests/` as the normal command.

Web changes MUST be verified before pushing:
```bash
npm --prefix web run lint && npm --prefix web run build
```

api↔web contract: mirrored in `web/lib/types.ts`, scenarios in `tests/contracts/registry.json`, artifact `tests/contracts/ts_contract.json`. When either side changes, regenerate: `npm --prefix web run contract:extract` (CI gates freshness via `contract:extract -- --check` in job `web-contract`, then runs `tests/smoke/test_contract_extractor.py` + `tests/smoke/test_api_call_inventory.py`; inventory script: `npm --prefix web run contract:inventory`).

Self-hosted deployment: `Dockerfile.api` + `docker-compose.yml` + `deploy/Caddyfile` (Caddy auth+proxy, only Caddy exposed). Details in `docs/self_hosted_deployment_execplan.md`, `docs/sqlite_backup_restore.md`.

## Product Surface Policy
New product-facing behavior goes through shared Python logic + explicit API contracts in `api/`, consumed by `web/`. Streamlit changes are acceptable only for bug fixes, acceptance/admin tooling, compatibility bridges, or extracting reusable logic out of legacy UI code. Never ship a new product feature only in `ui/pages/*`, and never duplicate business logic between the Streamlit and api/web paths.

## Architecture Context (ADD 3.0)
Before significant architecture/planning work, read `docs/architecture/asr_catalog.md` (ASR catalog + ADR registry — the living single source of truth for quality attributes) and `docs/architecture/architecture_analysis_add3.md` (tactics, ATAM-style risk heatmap, ASR→Module→Tactic map). UI/backend migration policy lives in `docs/architecture/adr_0001_web_primary_ui.md`; keep plans and PR scope aligned with it.

## Coding Style
- Type hints expected on public functions (see `models/`); keep docstrings in the language the file already uses (many core modules are Russian-first — match the file, don't translate).
- For legacy Streamlit work prefer existing helpers in `utils/modern_ui.py` and `ui/components/*` over inline HTML; keep data clients UI-agnostic (return structured status/errors).

## Testing Quirks
Many integration suites expect populated SQLite data; favor targeted modules unless you have synced Intervals/Garmin credentials. Generate sample data via `tests/add_test_data.py`. Wipe the cache with `tests/clean_database.py`.

## Commits, PRs
Conventional Commits (`feat:`, `fix:`, `refactor:`, `chore:`), subjects <72 chars. PR body lists tests run; link the issue; include screenshots/GIFs when touching any UI surface.

## Environment & Security Gotchas
- Secrets only in `.env` (never tracked); keys come from env — empty provider fields in the UI mean "fall back to `.env`", keep that behavior.
- Back up/migrate `ai_trainer.db` with `scripts/sqlite_backup_restore.py` (`backup ... --confirm-stopped` / `restore ...`) — a plain copy misses committed pages in the `-wal` file.
- `logs/` may contain personal training metrics — redact before publishing branches.

## Web Dev Surfaces
`/decisions`, `/recovery`, and the shadow `/today` module are hidden behind build-time flag `NEXT_PUBLIC_SHOW_DEV_TOOLS=true` (inlined at build — restarting the dev server after the change is required).

## Development Workflow
Canonical workflow: assign a `Change Class` using `docs/AI_Feature_Development_Workflow.md` (Full / Standard / Fast track, then SpecDD → BDD → TDD → Contract First → Self-Review → Minimal Complexity). Class A work uses `docs/templates/slice_spec_review_template.md`; docs-only/one-line fixes normally use Class C unless an automatic escalation trigger applies. Issue-first agent loop and GitHub automation model: `docs/loop_engineering_instruction.md`. Record tracked post-merge outcomes in `docs/engineering_process_metrics.md`.

- **Evidence Discipline:** causal claims must use `Observed` / `Inferred` / `Verified by` and run one cheap falsifying check before naming a bug or cause; follow `.agent/PLANS.md` and `docs/AI_Feature_Development_Workflow.md`.

## ExecPlans
Complex features and significant refactors use an ExecPlan from design to implementation, per `.agent/PLANS.md`.

## Claude GitHub Action Norms
The `@claude` workflow (`.github/workflows/claude.yml`) runs in a bounded sandbox (turn budget, 30-min timeout, shared quota). Norms that keep restarts cheap:
- **One milestone per @claude mention.** Milestone-sized self-contained tasks (a RED→GREEN pair or one review round) finish in a single run; split larger tracks.
- **Commit and push every completed RED/GREEN slice immediately.** A restart then costs at most one slice. Near exhaustion, stop at a clean pushed boundary and update the progress checklist.
- **Verify web changes inside the run** (`lint` + `build`) before pushing; CI is the second line.
- Draft PRs open automatically for action branches (`claude/issue-N-YYYYMMDD-HHMM`) via `claude-auto-draft-pr.yml`; failures report back classified via `claude-failure-notify.yml`. If quota exhausts mid-track, another agent picks up from the last pushed slice.
