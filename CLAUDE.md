# CLAUDE.md

This file provides repository-specific guidance for Claude Code when working in AI Trainer.

## Project Overview

AI Trainer is a Streamlit-based endurance training cockpit. It ingests Garmin Connect data into a local SQLite cache, analyzes workload, HRV, sleep, planning execution, and exposes multi-provider AI coaching over that local context.

## Current Architecture

`app.py` is a thin Streamlit composition shell. It sets page config, applies compatibility/theme setup, renders navigation, and delegates the real product surfaces to page/component modules.

Key directories:

```text
ai_trainer/
├── app.py                  # Streamlit shell and top-level routing
├── config/settings.py      # Environment-backed settings and defaults
├── data/                   # Garmin clients, SQLite persistence, ETL processors
├── services/               # Sync, Garmin service boundary, demo and acceptance mode
├── state/                  # StateManager facade over st.session_state
├── ui/pages/               # Dashboard, planning, HRV, sleep, activities, admin, AI pages
├── ui/components/          # Sidebar, AI coach, provider setup, execution feedback widgets
├── models/                 # AI providers, coach runtime, planning, metrics/explainability
├── utils/                  # Modern UI, Plotly theme, visualization and compatibility helpers
├── tests/smoke/            # Contributor-safe smoke suite
├── tests/                  # Broader unit, diagnostic, live, and integration tests
├── docs/                   # Current docs, ExecPlans, and historical plans
└── run_acceptance.sh       # Isolated Streamlit launch with temp DB/demo dataset
```

## Development Commands

```bash
# Create and activate environment
python -m venv ai_trainer_env
source ai_trainer_env/bin/activate

# Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Run the app
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

## Integrations

### Garmin

Runtime authentication is through `garminconnect`. The `garth` integration remains as a legacy diagnostic/runtime-inspection path, not a fresh-login strategy. Current code intentionally disables fresh `garth` login because upstream auth changed.

Use service helpers in `services/garmin.py` and `services/sync.py` instead of reaching into UI code from data clients.

### AI Providers

Supported provider types are OpenAI, Anthropic, DeepSeek, Google Gemini, Ollama, and Mock AI for demo mode. Provider setup lives in `ui/components/ai_coach_provider.py`, with provider implementations in `models/ai_providers.py`.

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

## Coding Notes

- Prefer existing page/component/service boundaries over adding logic to `app.py`.
- Prefer `utils/modern_ui.py` and existing `ui/components/*` helpers for Streamlit UI.
- Keep data clients UI-agnostic; return structured status/errors and let UI render them.
- Many docs and strings are Russian-first; keep the language style already used in the file.
- Large planning/dashboard changes should use an ExecPlan per `.agent/PLANS.md`.
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
