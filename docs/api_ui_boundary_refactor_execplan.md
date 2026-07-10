# Remove FastAPI dependencies on the legacy Streamlit UI

This ExecPlan is a living document. It follows `.agent/PLANS.md`; the sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must remain current while work proceeds.

## Purpose / Big Picture

The FastAPI backend currently imports formatting and dashboard helpers from the legacy Streamlit UI. That reverses the repository's intended dependency direction: the product API can fail to import when Streamlit-only dependencies change, and domain behavior cannot evolve independently of the fallback UI. After this refactor, shared coach presentation and dashboard summary logic will live in headless Python modules. FastAPI and Streamlit will consume the same functions, while existing API responses and rendered Russian text remain unchanged.

## Progress

- [x] (2026-07-10 00:00Z) Read the repository workflow, issue-loop model, web-first ADR, and ExecPlan requirements.
- [x] (2026-07-10 00:00Z) Identified direct `api/` imports from `ui/` in coach and dashboard routers.
- [x] (2026-07-10 00:00Z) Added the coach architecture contract and observed the expected pre-implementation failure: `assert "ui" not in imports`.
- [x] (2026-07-10 00:00Z) Moved coach tool-result formatting to `models/coach_tool_presenter.py`; FastAPI imports it directly and the Streamlit component re-exports it.
- [x] (2026-07-10 00:00Z) Completed self-review and validation on the isolated #147 branch: 43 targeted tests and 441 smoke tests pass, one socket-dependent test is skipped, Python compilation is clean, and Next.js lint/build are green.
- [x] (2026-07-10 00:00Z) Published commit `d08464c` on `codex/issue-147-api-ui-boundary` and opened draft PR #149 closing issue #147.
- [x] (2026-07-10 10:58Z) Created issue #150 and branch `codex/issue-150-dashboard-api-boundary` for the isolated dashboard milestone.
- [x] (2026-07-10 10:59Z) Analyzed the six imported dashboard helpers and their local dependency closure; the closure contains eleven pure or headless-capable helpers.
- [x] (2026-07-10 11:00Z) Recorded the isolated pre-change baseline: `442 passed, 1 skipped` on `main` commit `58808f4`.
- [x] (2026-07-10 11:01Z) Added the repository-wide API architecture contract and observed the expected failure with `api/routers/dashboard.py` as the only offender.
- [x] (2026-07-10 11:06Z) Extracted the dashboard helper closure into `models/dashboard_summary.py`, switched FastAPI to public headless functions, and retained Streamlit aliases plus its cached-data wrapper.
- [x] (2026-07-10 11:12Z) Completed validation and self-review: 28 expanded dashboard tests passed, full smoke passed with `445 passed, 1 skipped`, Python compilation and Ruff were clean, and Next.js lint/build succeeded.
- [ ] Commit, push, and open a draft PR closing #150.

## Surprises & Discoveries

- Observation: `api/routers/coach.py` imports only one UI symbol, `format_tool_result`, while `api/routers/dashboard.py` imports six private UI helpers.
  Evidence: `rg -n "from ui\\." api --glob '*.py'` returns exactly those two import sites.
- Observation: coach formatting already depends on `utils.product_semantics`, which is a headless shared module.
  Evidence: `ui/components/ai_coach_output.py` imports sport, date, trend, and partial-day labels from that utility.
- Observation: The formatter accepts non-dictionary payloads in fallback branches despite most tool results being mappings.
  Evidence: existing branches explicitly return text for non-dictionary training-status and generic payloads, so the extracted function retains `data: Any` rather than narrowing the runtime contract.
- Observation: The six helpers imported by `api/routers/dashboard.py` depend on five additional local helpers, for an eleven-function extraction closure.
  Evidence: AST call analysis found `_build_dashboard_v2_summary` also reaches date/TSS/sport formatting and next-step explainability helpers.
- Observation: `_calculate_current_status` is the only function in the closure with a Streamlit-specific fallback.
  Evidence: when its dataframe arguments are omitted, it calls `services.data_cache`; FastAPI already supplies every dataframe explicitly.
- Observation: The first compatibility-file reconstruction accidentally read only the first 1,100 lines of the 1,253-line Streamlit module.
  Evidence: full smoke failed in `test_dashboard_sync_handoff_copy_uses_next_step_button` because the omitted tail contained `_format_date`. Reconstructing from the complete `git show main:ui/pages/dashboard.py` source restored all 17 non-moved functions; an AST comparison then reported `missing [] changed []`.

## Decision Log

- Decision: Extract the coach formatter before the dashboard helpers.
  Rationale: It is a single dependency with existing behavioral smoke coverage, so it provides a small independently verifiable milestone and reduces risk before the larger dashboard move.
  Date/Author: 2026-07-10 / Codex.
- Decision: Preserve the existing function signature and output text byte-for-byte.
  Rationale: The change is architectural, not product-facing; changing the SSE/API presentation contract would unnecessarily widen scope.
  Date/Author: 2026-07-10 / Codex.
- Decision: Expose public headless dashboard functions to FastAPI and retain underscore-prefixed aliases/wrappers only in the Streamlit page.
  Rationale: API should not depend on private UI symbols, while existing fallback rendering and tests need a low-risk compatibility path.
  Date/Author: 2026-07-10 / Codex.
- Decision: Require dataframes in the headless current-status function and keep cached loading in a UI-only wrapper.
  Rationale: This removes the transitive Streamlit dependency without changing either caller's behavior.
  Date/Author: 2026-07-10 / Codex.

## Outcomes & Retrospective

Both implementation milestones are now complete locally. The coach and dashboard API routers import no Streamlit UI module. Dashboard summary, plan lookup, status calculation, latest training status, and next-step selection have one headless source of truth in `models/dashboard_summary.py`; the Streamlit page retains only compatibility aliases and the cached-data loading wrapper needed by the fallback UI.

Self-review found no API response, database, concurrency, or security change. AST comparison proved that all 17 non-moved Streamlit functions were preserved unchanged. The main remaining weakness is module size: the coach presenter and dashboard builder are still substantial, because these milestones deliberately moved behavior without redesigning it. Splitting their internal branches should be a later behavior-driven task, not part of this dependency-direction refactor.

## Context and Orientation

`api/routers/coach.py` implements FastAPI chat endpoints and passes a formatter callback into functions from `models/ai_coach_runtime.py`. The callback currently comes from `ui/components/ai_coach_output.py`, a Streamlit component module. `ui/pages/ai_coaching.py` and `app.py` also expose this formatter for the legacy application. A headless module is ordinary Python code that imports no Streamlit or UI modules and can therefore be used safely by both HTTP and Streamlit entry points.

The web API contract must remain backward-compatible. In this milestone that means the same tool payload produces the same Markdown string and the coach SSE event shapes do not change. No database schema, endpoint path, request model, or web TypeScript type changes are required.

For dashboard Milestone 2, `api/routers/dashboard.py` currently imports `_build_activity_day_tss`, `_build_dashboard_v2_summary`, `_build_plan_day_lookup`, `_calculate_current_status`, `_get_dashboard_goal_plan`, and `_get_latest_training_status` from `ui/pages/dashboard.py`. Those functions build `GET /api/dashboard/summary` and parts of `GET /api/dashboard/widgets`. Their local dependency closure also includes date coercion, compact formatting, next-step selection, and explainability-summary construction. The extraction must preserve both endpoint payloads and the legacy Streamlit dashboard.

## Plan of Work

First add an architecture test under `tests/smoke/` that parses `api/routers/coach.py` and asserts it has no import rooted at `ui`. Add or adapt behavior tests so representative performance, activity, health, and proposal payloads still produce the existing strings. Run the new architecture test before implementation and record that it fails on the current UI import.

Next create a small headless formatter module under `models/` or `utils/`, choosing the location that best matches its existing dependencies. Move the formatter implementation without changing its public signature. Update `api/routers/coach.py` and the Streamlit component to import the shared implementation. Keep a compatibility re-export from `ui/components/ai_coach_output.py` because existing legacy imports and tests use that path.

Finally run targeted coach tests, all smoke tests, Python compilation, web lint, and the production web build. Inspect the diff for accidental product changes, circular imports, dead code, and formatting drift. Only after the coach milestone is green should the dashboard dependency graph be extracted in the same test-first manner.

For dashboard Milestone 2, first extend `tests/smoke/test_api_architecture.py` so every Python module under `api/` is forbidden from importing `ui`. Run that test before implementation and record its failure on `api/routers/dashboard.py`.

Next create `models/dashboard_summary.py` as the headless source of truth. Give FastAPI public function names and explicit dataframe inputs. Update `api/routers/dashboard.py` to import those public functions. In `ui/pages/dashboard.py`, import the shared functions and preserve the existing underscore-prefixed names; keep only the cached-data fallback wrapper in the UI module. Do not change JSON fields, labels, thresholds, date semantics, or Streamlit rendering behavior.

Finally run dashboard summary/API/widget tests, the architecture test, the full smoke suite, Python compilation, web lint, and the production web build. Review import direction, function identity/compatibility, accidental time-dependent changes, and the final diff before publication.

## Concrete Steps

Work from `/Users/gregkisel/Developer/ai_trainer`:

    ai_trainer_env/bin/python -m pytest tests/smoke/test_api_architecture.py -q
    ai_trainer_env/bin/python -m pytest tests/smoke/test_ai_coach_output.py tests/smoke/test_ai_coach_runtime.py -q
    ai_trainer_env/bin/python -m pytest tests/smoke -q
    ai_trainer_env/bin/python -m compileall -q api models services data ui
    cd web && npm run lint && npm run build
    git diff --check

For dashboard Milestone 2, also run:

    ai_trainer_env/bin/python -m pytest tests/smoke/test_api_architecture.py -q
    ai_trainer_env/bin/python -m pytest tests/smoke/test_dashboard_v2_shell.py tests/smoke/test_api_dashboard.py -q

Before implementation, the architecture test must fail because `api/routers/coach.py` imports `ui.components.ai_coach_output`. After implementation, it must pass, existing formatter tests must remain green, and the complete smoke suite must pass without live credentials.

## Validation and Acceptance

Given a Python process imports `api.routers.coach`, when its imports are inspected, then no dependency rooted at `ui` is present in that router.

Given an existing tool result such as performance metrics or recent activities, when both the shared formatter and the compatibility import from `ui.components.ai_coach_output` format it, then they return identical Markdown.

Given the coach endpoint processes a tool call, when it emits SSE events, then event names and payload fields remain unchanged and existing runtime smoke tests pass.

Given no external AI or Garmin credentials, when the contributor-safe smoke command runs, then it completes successfully apart from explicitly documented infrastructure skips.

Given any Python module under `api/`, when its imports are inspected, then no import root is `ui`.

Given identical state, activities, HRV, sleep, training status, and reference date, when the extracted dashboard builder runs, then summary and widget payloads match the existing behavior.

Given the Streamlit dashboard renders without explicit dataframes, when it calculates current status, then its UI wrapper still loads cached activities, HRV, and sleep before delegating to the headless function.

## Idempotence and Recovery

The refactor changes imports and pure formatting code only; it performs no data migration or external write. Tests and build commands are safe to repeat. If a compatibility regression appears, restore the re-export at the legacy UI path while keeping the new shared implementation and use the behavioral tests to isolate the mismatched branch.

## Artifacts and Notes

Baseline before the boundary refactor:

    ai_trainer_env/bin/python -m pytest tests/smoke -q
    441 passed, 1 skipped

    npm run lint
    No ESLint warnings or errors

    npm run build
    Compiled successfully

Dashboard Milestone 2 evidence on issue #150 branch:

    ai_trainer_env/bin/python -m pytest tests/smoke/test_api_architecture.py tests/smoke/test_dashboard_v2_shell.py tests/smoke/test_api_dashboard.py tests/smoke/test_dashboard_next_step.py tests/smoke/test_dashboard_tsb_zones.py tests/smoke/test_signals_engine.py tests/smoke/test_readiness_snapshot_contract.py -q
    28 passed

    ai_trainer_env/bin/python -m pytest tests/smoke -q
    445 passed, 1 skipped

    npm run lint && npm run build
    No ESLint warnings or errors; compiled successfully

## Interfaces and Dependencies

The shared module must expose:

    format_tool_result(tool_name: str, data: dict[str, object]) -> str

It may depend on `utils.product_semantics`. It must not import `streamlit`, `ui`, `api`, or web code. `api/routers/coach.py` and `ui/components/ai_coach_output.py` will import this function. The UI module must continue exposing `format_tool_result` so legacy callers remain compatible.

For dashboard Milestone 2, `models/dashboard_summary.py` must expose public equivalents of the six helpers currently imported by FastAPI:

    get_dashboard_goal_plan(state) -> dict[str, Any]
    build_plan_day_lookup(goal_plan) -> dict[date, dict[str, Any]]
    build_activity_day_tss(activities_df) -> dict[date, float]
    build_dashboard_summary(state, current_status, latest_training_status, activities_df, *, reference_date=None) -> dict[str, Any]
    calculate_current_status(activities_df, hrv_df, sleep_df, training_status=None) -> dict[str, Any]
    get_latest_training_status(database) -> dict[str, Any]

The module may depend on pandas and shared `models`/`utils` modules. It must not import `streamlit`, `ui`, `services.data_cache`, or `api`.

Revision note (2026-07-10 / Codex): initial plan created after repository-wide audit and before adding the architecture contract.

Revision note (2026-07-10 / Codex): updated after the red TDD run and coach formatter extraction to record compatibility behavior and targeted test evidence.

Revision note (2026-07-10 / Codex): updated after self-review and complete validation to close the coach milestone and leave dashboard extraction as the next independently testable milestone.

Revision note (2026-07-10 / Codex): recorded issue #147, published commit `d08464c`, and draft PR #149 so the living plan matches GitHub state.

Revision note (2026-07-10 / Codex): opened Milestone 2 as issue #150, recorded the eleven-function dashboard dependency closure, isolated baseline, BDD scenarios, and the public headless interface before tests or implementation.

Revision note (2026-07-10 / Codex): updated after implementation and self-review with red/green test evidence, the full-source reconstruction discovery, AST preservation proof, and final validation results.
