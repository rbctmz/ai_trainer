# Repository Guidelines

## Project Structure & Module Organization
AI Trainer is in an active web migration. The main product development path is `api/` + `web/`: `api/` exposes FastAPI contracts over the existing Python logic, and `web/` contains the Next.js UI. The legacy Streamlit entry point is `app.py`, which remains a thin fallback shell for page configuration, navigation dispatch, Garmin sync callbacks, and theme bootstrap while migration is still in progress. Configuration constants and environment lookups sit in `config/settings.py`; keep defaults centralized there. Data ingestion and persistence live under `data/` (Garmin clients, SQLite helpers) and `services/` (sync, demo, acceptance, and integration orchestration). AI logic is grouped in `models/`. Reusable Streamlit pages/components, themes, and assets live in `ui/` and `utils/`; treat them as maintenance/fallback surfaces unless a task explicitly targets Streamlit. Long-running state helpers reside in `state/`, but `state/manager.py` is Streamlit-specific and should not become the contract for new product flows. `tests/` houses pytest suites plus utility scripts; ignore `debug/` and `examples/` unless you need manual experiments.

## Build, Test, and Development Commands
Create or activate the virtualenv via `source ai_trainer_env/bin/activate` (macOS/Linux) or the Windows `Scripts` path. Install base dependencies with `pip install -r requirements.txt` and `pip install -r requirements-dev.txt` for tests. When working on API/web runtime, also install `pip install -r requirements-web.txt`. Launch the web stack with `./run_web.sh` when working on FastAPI/Next.js flows; the script starts FastAPI on `:8000`, Next.js on `:3000`, and reconciles missing web dependencies. Use `./run.sh` or `streamlit run app.py` for legacy Streamlit flows that have not been fully migrated yet. For runtime dependency issues, prefer `python scripts/doctor_env.py check --runtime` and `python scripts/doctor_env.py repair --runtime`. Use `python -m pytest tests/smoke -q` for the contributor-safe pass, and `python -m pytest -m "not live and not debug" tests/` for a broader local pass. Use `python -m pytest tests/test_ai_coach.py` (swap the filename) for focused checks.

|## Product Surface Policy
New product-facing behavior should go through shared Python logic plus explicit API contracts in `api/`, then be consumed from `web/`. Streamlit changes are acceptable for bug fixes, acceptance/admin tooling, compatibility bridges, or extracting reusable logic out of legacy UI code. Do not ship new product features only in `ui/pages/*` unless the task is explicitly legacy-only, and do not duplicate business logic between Streamlit and API/web paths.

## Architecture Context (ADD 3.0)
Before starting significant architecture or planning work, read `docs/architecture/architecture_analysis_add3.md`. It documents:
- Explicit Quality Attribute Scenarios (ASR) for performance, reliability, modifiability, security, deployability
- Architectural tactics already used and gaps to fill
- Risk/tradeoff heatmap (ATAM-style) — know what you might break
- Missing ADRs that should be written alongside new decisions
- Map of `ASR → Module → Tactic` for traceability

## Coding Style & Naming Conventions
Use 4-space indentation and follow PEP 8; type hints are expected for public functions, as seen across `models/`. Module and package names stay lowercase with underscores (`ai_coach_universal.py`). Keep docstrings concise and in the language already used within the file (many core modules are Russian-first). For new product UX/backend flows, prefer shared Python services/models plus API contracts over adding logic to Streamlit pages. When touching Streamlit components, prefer existing helpers in `utils/modern_ui.py` and page/component helpers under `ui/` instead of inline HTML.

## Testing Guidelines
Pytest is the standard runner, and tests rely on fixtures under `tests/`—many integration suites expect populated SQLite data, so favor targeted modules unless you have synced Garmin credentials. Name new tests `test_*.py` and co-locate helper scripts next to them. Update or generate sample data via scripts like `tests/add_test_data.py` when coverage requires fresh fixtures.

## Commit & Pull Request Guidelines
Recent history follows Conventional Commits (`feat:`, `refactor:`, `chore:`); use the same prefixes and keep subjects under 72 characters. Provide descriptive bodies when the change spans multiple modules or alters data flow. Pull requests should link the relevant issue, list the manual or automated tests you ran, and include UI screenshots or GIFs whenever you adjust web or Streamlit surfaces.

## Environment & Security Tips
Store secrets only in `.env`, never in version control. The SQLite cache `ai_trainer.db` is local-only; wipe it with `tests/clean_database.py` before sharing datasets. Logs under `logs/` might contain personal metrics—purge or redact them before publishing branches.

## Development Workflow
Use `docs/AI_Feature_Development_Workflow.md` as the canonical workflow for non-trivial feature and architecture work: SpecDD, BDD, TDD, Contract First, Self-Review, and Minimal Complexity. Use `docs/loop_engineering_instruction.md` for the current issue-first agent loop and GitHub automation model. Repo-level UI/backend migration policy lives in `docs/architecture/adr_0001_web_primary_ui.md`; keep plans, specs, and PR scope aligned with that document. Keep the process lightweight for small docs-only or one-line fixes, but start significant work from a spec, acceptance criteria, and the repo's existing contracts.

# ExecPlans
When writing complex features or significant refactors, use an ExecPlan (as described in `.agent/PLANS.md`) from design to implementation.
