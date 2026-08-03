# CLAUDE.md

This file provides repository-specific guidance for Claude Code when working in AI Trainer.

## Project Overview

AI Trainer is an endurance training cockpit built around Garmin Connect data, local SQLite persistence, workload/HRV analytics, planning execution, and multi-provider AI coaching.

The repository is in an active migration from Streamlit to a web stack:

- `web/` is the primary product direction for new UI work
- `api/` is the contract layer for that UI
- Streamlit remains a supported fallback surface until migration parity is complete

Do not describe the project as "Streamlit-only" anymore.

## Current Architecture

```text
ai_trainer/
├── api/                     # FastAPI routes and schemas for web flows
├── web/                     # Next.js UI under active migration
├── app.py                   # Legacy Streamlit shell and fallback routing
├── config/settings.py       # Environment-backed settings and defaults
├── data/                    # Garmin clients, SQLite persistence, ETL processors
├── services/                # Sync, Garmin service boundary, demo and acceptance mode
├── state/                   # Streamlit-oriented state helpers
├── ui/pages/                # Legacy Streamlit pages
├── ui/components/           # Legacy Streamlit widgets and helpers
├── models/                  # AI providers, coach runtime, planning, metrics/explainability
├── utils/                   # Shared helpers, Plotly/theme helpers, compatibility utilities
├── tests/smoke/             # Contributor-safe smoke suite
├── tests/                   # Broader unit, diagnostic, live, and integration tests
├── docs/                    # Current docs, ExecPlans, ADRs, and historical plans
└── run_acceptance.sh        # Isolated Streamlit launch with temp DB/demo dataset
```

## Development Commands

```bash
# Create and activate environment
python -m venv ai_trainer_env
source ai_trainer_env/bin/activate

# Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt
pip install -r requirements-web.txt

# Web/API path during migration
./run_web.sh

# Legacy Streamlit fallback
./run.sh

# Safe test path for ordinary development
python -m pytest tests/smoke -q

# Broader local pass without live external systems or diagnostics
python -m pytest -m "not live and not debug" tests/

# Focused tests
python -m pytest tests/test_ai_coach.py
python -m pytest tests/smoke/test_planning_execution.py

# Isolated browser/acceptance runtime
ACCEPTANCE_PORT=8510 ./run_acceptance.sh
```

Do not treat plain `python -m pytest tests/` as the normal contributor command. The tree still contains live/diagnostic tests that may require Garmin credentials, network, local AI runtimes, or historical assumptions.

## Product Surface Rules

- New product-facing work should start from shared Python logic plus explicit API contracts in `api/`, then be wired into `web/`.
- Streamlit work is still valid for bug fixes, acceptance/admin tooling, fallback behavior, or extracting reusable logic out of legacy UI code.
- Do not add new product behavior only to `ui/pages/*` unless the task is explicitly legacy-only.
- Do not duplicate business logic between Streamlit and API/web flows.

## Integrations

### Garmin

Runtime authentication is through `garminconnect`. The `garth` integration remains as a legacy diagnostic/runtime-inspection path, not a fresh-login strategy. Current code intentionally disables fresh `garth` login because upstream auth changed.

Use service helpers in `services/garmin.py` and `services/sync.py` instead of reaching into UI code from data clients.

### AI Providers

Supported provider types are OpenAI, Anthropic, DeepSeek, Google Gemini, Ollama, and Mock AI for demo mode. Provider setup in the legacy surface lives in `ui/components/ai_coach_provider.py`, with provider implementations in `models/ai_providers.py`.

Environment-backed API keys are intentionally hidden in the UI. Leaving a provider key field empty should continue to use the `.env` value when present.

### Demo and Acceptance

Demo mode uses deterministic local data and Mock AI. Acceptance mode uses an isolated temporary SQLite database and can disable real Garmin login. Use it for UI/browser checks when real user data should not be touched.

## Environment Variables

Common variables:

- `OPENAI_API_KEY`, `OPENAI_MODEL`
- `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL`
- `DEEPSEEK_API_KEY`, `DEEPSEEK_MODEL`, `DEEPSEEK_BASE_URL`
- `GOOGLE_API_KEY`, `GOOGLE_MODEL`
- `OLLAMA_HOST`, `OLLAMA_MODEL`
- `DEFAULT_AI_PROVIDER`
- `GARMIN_EMAIL`, `GARMIN_PASSWORD`
- `DATABASE_PATH`
- `INTERVALS_ICU_API_KEY`, `INTERVALS_ICU_ATHLETE_ID`, `INTERVALS_ICU_BASE_URL`
- `ACCEPTANCE_MODE`, `ACCEPTANCE_AUTO_DEMO`, `ACCEPTANCE_DISABLE_GARMIN`
- `SHOW_DEVELOPMENT_TOOLS`
- `USER_FTP`, `USER_LTHR`, `USER_MAX_HR`

Secrets belong only in `.env` or the local runtime environment, never in tracked files.

`USER_FTP`/`USER_LTHR` are fallback defaults only. Every Garmin sync refreshes the
athlete's real FTP/weight/LTHR and the running/swimming threshold paces from
Intervals.icu (`services/intervals_icu.py::sync_athlete_profile`, stored in the
`athlete_profile` table) when `INTERVALS_ICU_API_KEY` is configured;
`data/data_processor.py::resolve_athlete_tss_profile` prefers that synced profile
and only falls back to the static env values for a field the profile does not
have, or when nothing has synced yet. The swim threshold pace (CSS) has
**no** env fallback: without a synced value the swim TSS cascade stays on the HR
path (`docs/activity_tss_methodology.md`). See `docs/athlete_profile_sync_execplan.md`.

## Coding Notes

- Prefer shared service/model logic over adding business rules to UI files.
- For new UI work, prefer `api/` + `web/`.
- For legacy Streamlit work, prefer existing `utils/modern_ui.py` and `ui/components/*` helpers.
- Keep data clients UI-agnostic; return structured status/errors and let the UI render them.
- Many docs and strings are Russian-first; keep the language style already used in the file.
- Large planning/dashboard/API changes should use an ExecPlan per `.agent/PLANS.md`.
- Keep smoke tests green after each coherent slice.

## Troubleshooting

```bash
# Runtime diagnostics
python scripts/doctor_env.py check --runtime
python scripts/doctor_env.py repair --runtime

# Dev/test diagnostics
python scripts/doctor_env.py check --dev
python scripts/doctor_env.py repair --dev

# Workspace/iCloud availability
python scripts/doctor_env.py check --workspace
```

If Streamlit or pytest behaves strangely under an iCloud-backed path, keep the repository fully downloaded or move it to a local-only directory.
