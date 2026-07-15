# AI Trainer Documentation Map

This directory contains current project docs, active/historical ExecPlans, and archived design material. Prefer the sections below when choosing what to read first.

## Current

- `README.md` at repository root: user/developer quick start.
- `AGENTS.md` at repository root: repository instructions for coding agents.
- `CLAUDE.md` at repository root: Claude Code orientation.
- `docs/AI_Feature_Development_Workflow.md`: canonical SpecDD/BDD/TDD/Contract First workflow for non-trivial feature work.
- `docs/loop_engineering_instruction.md`: current issue-first agent loop and GitHub automation operating model.
|- `docs/architecture/adr_0001_web_primary_ui.md`: active migration policy; web-first for new product work, Streamlit still supported as fallback during parity work.
|- `docs/architecture/architecture_analysis_add3.md`: **ADD 3.0 analysis** — full catalog of ASR (Quality Attribute Scenarios), architectural tactics inventory, risk/tradeoff heatmap (ATAM), missing ADRs, and actionable next steps. Read this before planning major architecture work.
- `docs/codex_project_notes.md` and `docs/codex_project_notes_ru.md`: compact architecture notes.
- `docs/ai_coaching_guide.md`: current AI provider and AI Coaching behavior.
- `docs/activity_tss_methodology.md`: current per-sport Activity TSS cascade, formulas, zone weights, and provenance/comparison notes against Garmin and Intervals.icu.
- `docs/ollama_setup.md`: local model setup.
- `docs/competitive_analysis_intervalcoach.md`: product/reference analysis for future planning work.
- `docs/code_review_recommendations.md`: living audit checklist; check dates and baseline before using line references.

## Current ExecPlans

- `docs/hardening_planning_v2_execplan.md`: latest hardening, Planning V2, Coach Explainability, Garmin acceptance history.
- `docs/stabilize_modularize_polish_execplan.md`: completed stabilization/modularization/core-flow plan.
- `docs/dashboard_planning_v2_execplan.md`
- `docs/dashboard_planning_visual_v2_execplan.md`
- `docs/dashboard_planning_visual_v21_execplan.md`

ExecPlans are living documents while active, but older sections remain as history. Check the latest progress/closeout section before treating a task as open.

## Historical Reference

The following documents are retained for decision history and old UI exploration. Do not execute them as current implementation instructions unless a new ExecPlan explicitly revives them.

- `docs/modernization_plan/`
- `docs/redesign_guide/`
- `docs/garth_integration_final_report.md`
- `docs/final_garmin_data_solution.md`
- `docs/garmin_data_issues.md`
- `docs/garmin_data_expansion_plan.md`
- `docs/phase1_implementation_proposal.md`
- `docs/dashboard_optimization_plan.md`

## Maintenance Rules

- If a doc describes an old architecture, add an archive/status note rather than silently leaving it active.
- Keep quick-start commands aligned with `README.md`, `AGENTS.md`, and `CLAUDE.md`.
- Keep process guidance aligned between `AGENTS.md`, `docs/AI_Feature_Development_Workflow.md`, and `docs/architecture/adr_0001_web_primary_ui.md`.
- During the migration window, explicitly say whether a doc section targets `web`/`api` or legacy Streamlit fallback.
- Use `python -m pytest tests/smoke -q` as the default contributor-safe test command in docs.
- Avoid absolute machine paths in new docs.
- Do not document `.env` values in a way that exposes real secrets or encourages pre-filling secret UI fields.
