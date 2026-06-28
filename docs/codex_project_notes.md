# Codex Project Notes – AI Trainer

## Overview

- **Purpose**: training cockpit for Garmin-backed endurance analytics, planning, and AI coaching.
- **Current state**: active migration from Streamlit to FastAPI + Next.js.
- **Working rule**: new product development is web-first, but Streamlit remains a supported fallback until parity is complete.

## Runtime Architecture

- `web/`: primary UI direction during migration. Dashboard, coach, planning, HRV, and activities are already exposed here.
- `api/`: FastAPI contract layer for the web frontend. New product-facing flows should cross this boundary instead of reaching into Streamlit state.
- `app.py`: legacy Streamlit shell. Still useful for fallback, acceptance, admin/diagnostic flows, and any behavior not fully migrated yet.
- `config/settings.py`: single source of environment-backed configuration.
- `services/`: UI-agnostic orchestration for Garmin auth/sync, demo mode, acceptance mode, data refresh, and external integrations.
- `data/`: Garmin API wrappers, ETL, and SQLite persistence helpers.
- `models/`: AI providers, coaching runtime, planning logic, Banister/HRV analytics, export helpers, and structured context builders.
- `state/`: Streamlit-oriented state helpers; do not treat `st.session_state` as the contract for new product flows.
- `ui/`: legacy Streamlit pages/components. Maintain, shrink, or extract from them; avoid growing them with new product-specific logic.
- `utils/`: shared metrics, visualizations, sleep analytics, and Streamlit/theme helpers.

## Data Flow

1. Garmin and provider credentials are loaded from `.env` via `config/settings.py`.
2. Shared Python logic in `services/`, `data/`, and `models/` loads and computes activity, HRV, planning, and AI context data.
3. `api/` exposes that behavior through explicit HTTP contracts for `web/`.
4. `web/` renders the main migrated product flows.
5. Streamlit still consumes the same backend/domain modules for fallback and acceptance scenarios.

## Product Surface Policy

- Prefer `api/` + `web/` for new product-facing work.
- Keep domain rules in Python, not in ad hoc frontend-only logic.
- Streamlit changes are acceptable for bug fixes, acceptance/admin tooling, compatibility bridges, or extraction of reusable logic.
- Do not ship new product behavior only in `ui/pages/*` unless the task is explicitly legacy-only.

## Testing & Tooling

- Default contributor-safe command: `python -m pytest tests/smoke -q`
- Broader local pass: `python -m pytest -m "not live and not debug" tests/`
- Web/API local runtime: `./run_web.sh`
- Legacy Streamlit runtime: `./run.sh`
- Acceptance runtime: `ACCEPTANCE_PORT=8510 ./run_acceptance.sh`

## Documentation Anchors

- `docs/architecture/adr_0001_web_primary_ui.md`: migration policy and ownership boundary
- `docs/AI_Feature_Development_Workflow.md`: SpecDD/BDD/TDD/Contract First workflow
- `docs/SPEC_WEB_MIGRATION.md`: migration scope, phases, and contracts

## Open Follow-up Areas

1. Finish parity for flows that still depend on Streamlit-only UI behavior.
2. Keep extracting reusable logic from legacy UI paths into shared headless modules.
3. Prevent drift between API contracts and web/frontend assumptions.
4. Keep live Garmin acceptance coverage honest about whether a result validates web, Streamlit fallback, or both.

## Quick Reference

- Preferred direction for new product work: `api/` + `web/`
- Legacy fallback: `streamlit run app.py` or `./run.sh`
- Shared backend/domain source of truth: `services/`, `models/`, `data/`
- Migration policy: `docs/architecture/adr_0001_web_primary_ui.md`
