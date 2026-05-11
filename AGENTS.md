# Repository Guidelines

## Project Structure & Module Organization
The Streamlit entry point is `app.py`, which wires UI flows, state hooks, and AI interactions. Configuration constants and environment lookups sit in `config/settings.py`; keep defaults centralized there. Data ingestion and persistence live under `data/` (Garmin clients, SQLite helpers) and `services/` (sync orchestration). AI logic is grouped in `models/`, while reusable UI components, themes, and assets live in `ui/` and `utils/`. Long-running state helpers reside in `state/`, and `tests/` houses pytest suites plus utility scripts; ignore `debug/` and `examples/` unless you need manual experiments.

## Build, Test, and Development Commands
Create or activate the virtualenv via `source ai_trainer_env/bin/activate` (macOS/Linux) or the Windows `Scripts` path. Install dependencies with `pip install -r requirements.txt`. Launch the app with `./run.sh`, which also applies the protobuf workaround; `streamlit run app.py` is the manual alternative. For Gemini-specific fixes, run `./setup_env.sh` once. Use `python -m pytest tests/` for the full test pass and `python -m pytest tests/test_ai_coach.py` (swap the filename) for focused checks.

## Coding Style & Naming Conventions
Use 4-space indentation and follow PEP 8; type hints are expected for public functions, as seen across `models/`. Module and package names stay lowercase with underscores (`ai_coach_universal.py`). Keep docstrings concise and in the language already used within the file (many core modules are Russian-first). When touching Streamlit components, prefer existing helpers in `ui/modern_ui.py` instead of inline HTML.

## Testing Guidelines
Pytest is the standard runner, and tests rely on fixtures under `tests/`—many integration suites expect populated SQLite data, so favor targeted modules unless you have synced Garmin credentials. Name new tests `test_*.py` and co-locate helper scripts next to them. Update or generate sample data via scripts like `tests/add_test_data.py` when coverage requires fresh fixtures.

## Commit & Pull Request Guidelines
Recent history follows Conventional Commits (`feat:`, `refactor:`, `chore:`); use the same prefixes and keep subjects under 72 characters. Provide descriptive bodies when the change spans multiple modules or alters data flow. Pull requests should link the relevant issue, list the manual or automated tests you ran, and include UI screenshots or GIFs whenever you adjust Streamlit components.

## Environment & Security Tips
Store secrets only in `.env`, never in version control. The SQLite cache `ai_trainer.db` is local-only; wipe it with `tests/clean_database.py` before sharing datasets. Logs under `logs/` might contain personal metrics—purge or redact them before publishing branches.

# ExecPlans
When writing complex features or significant refactors, use an ExecPlan (as described in .agent/PLANS.md) from design to implementation.