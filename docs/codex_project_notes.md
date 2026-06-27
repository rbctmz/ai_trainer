# Codex Project Notes – AI Trainer

## Overview
- **Purpose**: Streamlit app that ingests Garmin Connect training data, analyzes workload (TSS/CTL/ATL/TSB), HRV, and produces coaching insights via multi-provider LLM integration. 
- **Core pillars**: data ingestion (Garmin API + local SQLite cache), analytics (Banister, HRV, workload modeling, sleep regularity), AI coaching layer, and modernized UI with light/dark themes.

## Runtime Architecture
- `app.py`: thin Streamlit composition shell. It sets page config, applies Streamlit compatibility/theme setup, renders navigation/sidebar wiring, and delegates page work to `ui/pages/*`.
- `config/settings.py`: single source of environment-driven configuration (API keys, FTP/LTHR defaults, DB path, etc.).
- `state/manager.py`: typed facade over `st.session_state` with lazy dependencies for database, Garmin client, AI tools, and chat state.
- `services/`: UI-agnostic orchestration for Garmin auth/sync, demo mode, acceptance mode, data cache invalidation, and Intervals.icu.
- `ui/`: page renderers and reusable Streamlit components. Dashboard, planning, activities, HRV, sleep, admin, welcome, and AI coaching live under `ui/pages`; provider setup, chat, Garmin sidebar, and execution feedback live under `ui/components`.
- `data/`: Garmin API wrappers and data ETL.
  - `garmin_client.py`: uses `garminconnect` for runtime auth/data retrieval and keeps `garth` as legacy diagnostics/runtime inspection only; fresh `garth` login is intentionally disabled.
  - `data_processor.py`: normalizes activity payloads into pandas DataFrame, computes fallback TSS + sports translation.
  - `database.py`: SQLite schema + CRUD for activities, HRV, sleep, daily health, training status. Uses pandas I/O and date coercion fixes.
- `models/`:
  - `ai_providers.py`: polymorphic layer for OpenAI, Anthropic, DeepSeek, Gemini, Ollama, plus mock provider. Handles availability detection, test connections, model enumeration.
  - `ai_coach_universal.py`: orchestrates prompts for analyses, planning, workout review, metrics explanations, structured weekly plans.
  - `banister.py`: CTL/ATL/TSB modeling, Banister performance simulation, recommendations, scenario simulation.
  - `hrv_analyzer.py`: aggregates HRV metrics (RMSSD, DFA α1), smoothing, readiness scoring, detection of trends/anomalies.
  - `training_planner.py`: rule-based helper to derive weekly TSS targets and phased plans (deload/taper), used to seed AI planning prompts.
  - `fit_export.py`, `tcx_export.py`, `tcx_activity_export.py`: convert structured workouts into Garmin-compatible FIT/TCX, plus CSV intermediate generation. Wrap optional Garmin FIT SDK support.
  - `ai_data_context.py`: builds structured context packages (history summaries, workload snapshots) consumed by AI prompts.
- `utils/`:
  - `metrics.py`: additional metric computations (Intensity Factor, normalized power, load summaries).
  - `sleep_metrics.py`: sleep schedule regularity, weekday aggregation, ModernUI-ready recommendations.
  - `visualizations.py`: Plotly dashboards + chart factories; now aligned with theme helpers.
  - `modern_ui.py`: shared HTML/CSS snippets, responsive card rendering, cockpit theme colors.
  - `logger.py` (in package) and others support structured logging.

## Persistence & Data Flow
1. User configures API keys in `.env` (template available in `.env.example`).
2. Streamlit session authenticates with Garmin through `GarminClient`/`garminconnect`; `garth` is diagnostics-only.
3. Activities & wellness data saved to SQLite via `Database` helpers; pandas ensures typing normalization.
4. `ActivityProcessor` + `metrics.py` compute TSS, CTL/ATL, HRV readiness; results memoized in session state for UI + AI.
5. AI interactions: `AIProviderFactory` selects available provider; `UniversalAICoach` crafts prompts using `ai_data_context` to provide historial context; responses displayed alongside charts.
6. Workout planning/export: UI collects structured plan → `training_planner` builds weekly TSS targets → planning checkpoints persist versions/execution feedback → FIT/TCX/Intervals.icu export surfaces serialize planned workouts.

## UI & Theming
- Modern design built around Material-like palette with consistent CSS variables for light/dark modes.
- `ModernUI` centralizes card components, responsive grids, mini-chart styling, icon stacks.
- Extensive custom HTML injected via `st.markdown` to overcome Streamlit styling limits.

## Testing & Tooling
- `tests/` contains API provider unit tests, HRV trend checks, sleep regularity coverage, etc. (`pytest` runner documented in README).
- Debug scripts in `debug/` (Ollama connectivity, data inspection).
- `examples/` hosts demo flows for AI features.
- `run.sh` applies conservative Google/gRPC runtime defaults and launches Streamlit; use `scripts/doctor_env.py` for dependency diagnostics/repair.

## Documentation Assets
- `docs/modernization_plan/` and `docs/redesign_guide/`: historical UI modernization material. Treat as archive/reference unless a current ExecPlan says otherwise.
- `docs/dashboard_optimization_plan.md`: targeted UI/dashboard improvements checklist.

## Open Questions / Follow-up Areas
1. **State management**: Streamlit page now split across `state/`, `ui/`, `services/`, and `StateManager` wraps session state for readability/testability.
2. **Caching strategy**: review usage of `st.cache_data`/`st.cache_resource` (present in app) for data fetches; ensure cache invalidation on sync.
3. **Database growth**: evaluate retention/archival for large historical datasets; maybe add pruning or incremental updates instead of full replace in `save_activities`.
4. **Fitness modeling**: integrate HRV readiness and Banister outputs into combined readiness metric; align interpretation thresholds.
5. **Testing**: expand unit coverage for new planners/exporters and theme utilities; add integration smoke test for Garmin sync using mocked data.
6. **Internationalization**: app currently mixes RU/EN labels—decide on localization strategy or add translation layer.

## Quick Reference
- Entry point: `streamlit run app.py` or `./run.sh` (runtime checks/defaults).
- Core configs: `config/settings.py`, `.env`.
- Database file (default): `ai_trainer.db` in repo root.
- AI provider selection + validation handled in `ui/components/ai_coach_provider.py` through `AIProviderFactory`.
- Export artifacts saved to temp directories and offered via Streamlit download buttons.
