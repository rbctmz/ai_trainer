# Repository Guidelines

## Project Structure & Module Organization
The Streamlit entry point is `app.py`, which is now a thin composition shell for page configuration, navigation dispatch, Garmin sync callbacks, and theme bootstrap. Configuration constants and environment lookups sit in `config/settings.py`; keep defaults centralized there. Data ingestion and persistence live under `data/` (Garmin clients, SQLite helpers) and `services/` (sync, demo, acceptance, and integration orchestration). AI logic is grouped in `models/`, while reusable UI pages/components, themes, and assets live in `ui/` and `utils/`. Long-running state helpers reside in `state/`, and `tests/` houses pytest suites plus utility scripts; ignore `debug/` and `examples/` unless you need manual experiments.

## Build, Test, and Development Commands
Create or activate the virtualenv via `source ai_trainer_env/bin/activate` (macOS/Linux) or the Windows `Scripts` path. Install dependencies with `pip install -r requirements.txt` and `pip install -r requirements-dev.txt` for tests. Launch the app with `./run.sh`, which also applies the protobuf workaround; `streamlit run app.py` is the manual alternative. For Gemini-specific fixes, run `./setup_env.sh` once. Use `python -m pytest tests/smoke -q` for the contributor-safe pass, and `python -m pytest -m "not live and not debug" tests/` for a broader local pass. Use `python -m pytest tests/test_ai_coach.py` (swap the filename) for focused checks.

## Coding Style & Naming Conventions
Use 4-space indentation and follow PEP 8; type hints are expected for public functions, as seen across `models/`. Module and package names stay lowercase with underscores (`ai_coach_universal.py`). Keep docstrings concise and in the language already used within the file (many core modules are Russian-first). When touching Streamlit components, prefer existing helpers in `utils/modern_ui.py` and page/component helpers under `ui/` instead of inline HTML.

## Testing Guidelines
Pytest is the standard runner, and tests rely on fixtures under `tests/`—many integration suites expect populated SQLite data, so favor targeted modules unless you have synced Garmin credentials. Name new tests `test_*.py` and co-locate helper scripts next to them. Update or generate sample data via scripts like `tests/add_test_data.py` when coverage requires fresh fixtures.

## Commit & Pull Request Guidelines
Recent history follows Conventional Commits (`feat:`, `refactor:`, `chore:`); use the same prefixes and keep subjects under 72 characters. Provide descriptive bodies when the change spans multiple modules or alters data flow. Pull requests should link the relevant issue, list the manual or automated tests you ran, and include UI screenshots or GIFs whenever you adjust Streamlit components.

## Environment & Security Tips
Store secrets only in `.env`, never in version control. The SQLite cache `ai_trainer.db` is local-only; wipe it with `tests/clean_database.py` before sharing datasets. Logs under `logs/` might contain personal metrics—purge or redact them before publishing branches.

## Development Workflow
Use `docs/AI_Feature_Development_Workflow.md` as the canonical workflow for non-trivial feature and architecture work: SpecDD, BDD, TDD, Contract First, Self-Review, and Minimal Complexity. Keep the process lightweight for small docs-only or one-line fixes, but start significant work from a spec, acceptance criteria, and the repo's existing contracts.

# ExecPlans
When writing complex features or significant refactors, use an ExecPlan (as described in .agent/PLANS.md) from design to implementation.
