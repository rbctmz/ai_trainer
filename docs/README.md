# AI Trainer Documentation Map

This directory contains current product and architecture contracts, completed
ExecPlans, and historical design material. This page is the navigation source
of truth; it does not turn historical plans into current instructions.

## Status Vocabulary

- **Current** — authoritative for present behavior or process.
- **Completed contract** — delivered behavior whose invariants must be
  preserved, even though implementation work is closed.
- **Historical** — evidence from a completed phase; facts and decisions are kept
  intact but may describe an older product state.
- **Superseded** — replaced by a named current contract. Read only for decision
  history.
- **Draft** — proposal, not an implemented contract.

## Current

- [`README.md`](../README.md): user/developer quick start and current provider
  positioning.
- [`AGENTS.md`](../AGENTS.md): repository instructions for coding agents.
- [`AI_Feature_Development_Workflow.md`](AI_Feature_Development_Workflow.md):
  canonical SpecDD/BDD/TDD/Contract First workflow.
- [`loop_engineering_instruction.md`](loop_engineering_instruction.md): current
  issue-first agent loop and GitHub automation model.
- [`architecture/asr_catalog.md`](architecture/asr_catalog.md): living source of
  truth for quality attributes and ADR registry.
- [`architecture/architecture_analysis_add3.md`](architecture/architecture_analysis_add3.md):
  dated ADD 3.0/ATAM analysis; use the ASR catalog and debt register for current
  statuses.
- [`technical_debt_register.md`](technical_debt_register.md): single
  prioritized register of confirmed open technical debt.
- [`architecture/adr_0001_web_primary_ui.md`](architecture/adr_0001_web_primary_ui.md):
  active web-first migration policy and Streamlit EOL criteria.
- [`architecture/adr_0008_intervals_activity_ingestion.md`](architecture/adr_0008_intervals_activity_ingestion.md):
  current multi-provider activity-ingestion contract.
- [`activity_tss_methodology.md`](activity_tss_methodology.md): current
  per-sport TSS cascade and provenance policy.
- [`intervals_primary_quickstart.md`](intervals_primary_quickstart.md):
  supported Intervals-primary bootstrap.
- [`sqlite_backup_restore.md`](sqlite_backup_restore.md): current stopped-service
  SQLite backup, restore, rollback, and Docker volume runbook.
- [`ai_coaching_guide.md`](ai_coaching_guide.md): current AI provider and AI
  Coaching behavior.

## Completed Product Contracts

These completed ExecPlans describe the current product behavior and the invariants that future work must preserve:

- [`intervals_primary_handoff_execplan.md`](intervals_primary_handoff_execplan.md):
  completed M0–M5 track from provider links through planning, wellness, and
  Garmin demotion.
- [`intervals_primary_m1_slice_spec.md`](intervals_primary_m1_slice_spec.md),
  [`intervals_primary_m2_slice_spec.md`](intervals_primary_m2_slice_spec.md),
  [`intervals_primary_m3_slice_spec.md`](intervals_primary_m3_slice_spec.md),
  [`intervals_primary_m4_wellness_spec.md`](intervals_primary_m4_wellness_spec.md),
  and [`intervals_primary_m5_garmin_demotion_spec.md`](intervals_primary_m5_garmin_demotion_spec.md):
  completed milestone evidence. Statements scoped to an intermediate milestone
  are historical after later milestones.
- `docs/planner_discipline_distribution_execplan.md`: executable `sessions[]` as the plan truth, deterministic discipline scheduler, multi-session days, grouped bricks, race-load projection, and delivery identity.
- `docs/workout_catalog_v2_execplan.md`: current structured bike/run workout DSL and materialization rules; activation and bookend follow-ups are recorded in the planner contract above.
- `docs/race_microcycle_execplan.md`: A/B/C race microcycles, protected race/recovery dates, and structured pre-race activation.
- `docs/recovery_transfer_execplan.md`: RecoveryReplan v2 keep/downgrade/transfer D+1…D+3 decision contract, safety guards, identity lineage, confirm, and rollback.
- `docs/reconciliation_service_execplan.md`: canonical read-only plan/actual reconciliation service and API compatibility boundary.
- `docs/recovery_episode_refresh_execplan.md`: bounded ordinary recovery refresh plus targeted old-session refresh after match/feedback changes.

## Historical and Superseded

The following documents are retained for decision history or old UI exploration.
Do not execute them as current instructions unless a new issue or ExecPlan
explicitly revives them.

- [`SPEC_WEB_MIGRATION.md`](SPEC_WEB_MIGRATION.md): historical migration
  baseline; current policy is ADR-0001 and current product state is the root
  README.
- [`hardening_planning_v2_execplan.md`](hardening_planning_v2_execplan.md):
  completed historical plan; its Garmin-primary decision was superseded by
  ADR-0008 and the Intervals-primary M0–M5 contract.
- `docs/stabilize_modularize_polish_execplan.md`
- `docs/dashboard_planning_v2_execplan.md`
- `docs/dashboard_planning_visual_v2_execplan.md`
- `docs/dashboard_planning_visual_v21_execplan.md`
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
- Historical findings must not be copied into the debt register without
  rechecking the current tree.
- Every open debt item has one stable ID in
  [`technical_debt_register.md`](technical_debt_register.md); ASR and ExecPlans
  link to that ID instead of maintaining competing lists.
- Keep quick-start commands aligned with `README.md`, `AGENTS.md`, and `CLAUDE.md`.
- Keep process guidance aligned between `AGENTS.md`, `docs/AI_Feature_Development_Workflow.md`, and `docs/architecture/adr_0001_web_primary_ui.md`.
- During the migration window, explicitly say whether a doc section targets `web`/`api` or legacy Streamlit fallback.
- Use `python -m pytest tests/smoke -q` as the default contributor-safe test command in docs.
- Avoid absolute machine paths in new docs.
- Do not document `.env` values in a way that exposes real secrets or encourages pre-filling secret UI fields.
