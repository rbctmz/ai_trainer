# Dashboard and Planning V2 UI Reset

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

This document must be maintained in accordance with `.agent/PLANS.md`.

## Purpose / Big Picture

The current Dashboard and Planning pages are functionally rich but visually exhausting. They show too many internal signals, diagnostic controls, and editor workflows at the same priority. The user should not have to scan a technical console to answer basic coaching questions.

After this V2 reset, Dashboard answers: "What is my state today, what is the workout, how is this week going, and what is the next action?" Planning answers: "What is the goal, am I on track, what does the current week look like against facts, and what correction is needed?" Existing planning math, Garmin sync, checkpoint persistence, and export behavior remain available, but advanced/debug details move behind deliberate drill-downs.

The visible proof is straightforward: opening Dashboard should show a compact above-the-fold command center with no full execution editor and no diagnostic history. Opening Planning with an active plan should show the goal/phase/current-week review first, not the builder form, export controls, or low-level checkpoint internals.

## Progress

- [x] (2026-06-21 11:25+04:00) Created the V2 UI reset ExecPlan after auditing the current Dashboard and Planning render flows. The plan defines page ownership, milestones, acceptance criteria, and a safe migration path that keeps existing planning logic while replacing the visible shell.
- [x] (2026-06-21 12:10+04:00) Milestone 1: introduced pure summary helpers for Dashboard V2 and Planning V2 with smoke coverage for the stable summary contracts.
- [x] (2026-06-21 12:25+04:00) Milestone 2: replaced Dashboard's default visible shell with the V2 command-center layout and moved legacy sections into collapsed diagnostics.
- [x] (2026-06-21 12:35+04:00) Milestone 3: replaced Planning's active-plan correction mode with a review-first V2 shell and made the execution editor opt-in unless a plan/fact day is focused.
- [x] (2026-06-21 12:50+04:00) Milestone 4: ran focused smoke, full smoke, acceptance health, and browser smoke across desktop and mobile Dashboard loading.

## Surprises & Discoveries

- Observation: the current issue is not primarily visual styling.
  Evidence: `ui/pages/dashboard.py` renders status circles, recommendations, coach briefing, planning checkpoint, execution feedback, sync handoff, next step, quick actions, weekly calendar, and analytics in one vertical flow. Even with better spacing, that remains a mixed-purpose page.

- Observation: Planning already has named workspace modes, but the active-plan review still lacks a strong command-center top section.
  Evidence: `ui/pages/planning.py` can route between `Собрать план`, `Скорректировать выполнение`, and `Экспорт и детали`, but the correction mode still presents several heavy components as peers instead of first answering "what needs attention now?"

- Observation: Streamlit expanders cannot be casually nested.
  Evidence: `_render_near_term_editor(...)` already owns an expander, so wrapping it in a second `st.expander(...)` for history/edit/rollback would create a runtime-risky nested expander. The final implementation leaves the near-term editor in its existing expander and wraps version history separately.

- Observation: the acceptance dataset can start without an active goal plan.
  Evidence: browser smoke for Planning opened the safe builder fallback (`План под цель`) rather than the active-plan V2 shell. The active-plan V2 contract is covered by pure smoke tests, while browser smoke verifies that the page still loads in the no-plan state.

## Decision Log

- Decision: implement V2 as a shell reset over existing logic, not a rewrite of planning models.
  Rationale: the planning/checkpoint system is already tested and useful. The problem is information architecture and visual priority, so replacing the page composition is safer than touching training math, Garmin sync, or persistence.
  Date/Author: 2026-06-21 / Codex

- Decision: Dashboard must not contain the execution-feedback editor by default.
  Rationale: Dashboard is an overview page. If it includes a full editor, it becomes a maintenance console and competes with Planning for ownership. Dashboard may link to Planning or expose a fallback diagnostic toggle, but the primary path must be read-only.
  Date/Author: 2026-06-21 / Codex

- Decision: Planning's default active-plan mode must be review-first, not builder-first or export-first.
  Rationale: once a plan exists, the main job is tracking and adjustment. Building a new plan, exporting workouts, and inspecting version history are secondary jobs and should not dominate the first screen.
  Date/Author: 2026-06-21 / Codex

## Outcomes & Retrospective

Implemented Dashboard/Planning V2 as a shell reset over existing logic.

Dashboard now renders a compact command center first: `Сегодня`, `Тренировка сегодня`, `Неделя`, `Следующие 7 дней`, `План`, and `Следующий шаг`. The old recommendation, briefing, quick action, calendar, and analytics blocks remain available through diagnostics rather than competing with the top-level decision surface.

Planning now keeps `Собрать план` and `Экспорт и детали` as explicit modes, while the active correction mode starts with `Цель`, `Путь к цели`, `Текущая неделя`, and `Коррекция`. The full execution editor no longer appears by default; it opens from the correction CTA or when a focused plan/fact day requires it.

Verification completed on 2026-06-21:

- `python3 -m py_compile ui/pages/planning.py ui/pages/dashboard.py` passed.
- `python3 -m pytest tests/smoke/test_dashboard_v2_shell.py tests/smoke/test_planning_page_explainability.py tests/smoke/test_planning_execution.py tests/smoke/test_ui_page_exports.py -q` passed with `56 passed`.
- `python3 -m pytest tests/smoke -q` passed with `184 passed`.
- Acceptance runtime health on `ACCEPTANCE_PORT=8510` returned `HTTP/1.1 200 OK` and `ok`.
- Browser smoke loaded Dashboard V2 headings on desktop and mobile viewport `390x844` with no console errors.
- Browser smoke loaded Planning's no-active-plan fallback in acceptance mode with no console errors.

## Context and Orientation

The repository is a Streamlit application. Streamlit pages are Python functions that call `st.*` APIs to render UI top-to-bottom.

The current Dashboard page lives in `ui/pages/dashboard.py`. Its entry point is `render_dashboard_page(state, on_sync)`. It currently computes current training status, renders several metric cards, then renders many separate sections in sequence: recommendation panel, coach briefing, planning checkpoint, execution feedback loop, sync handoff, primary next step, quick actions, weekly calendar, and compact analytics.

The current Planning page lives in `ui/pages/planning.py`. Its entry point is `render_planning_page(state)`. It computes current Banister load metrics from activities, shows a workspace mode radio, renders plan-building controls in `Собрать план`, renders plan/fact and execution feedback in `Скорректировать выполнение`, and renders explainability/export controls in `Экспорт и детали`.

The shared execution editor lives in `ui/components/execution_feedback.py` as `render_execution_feedback_editor(...)`. It is useful but too heavy for Dashboard. It should remain available in Planning.

The current UI support layer is `utils/modern_ui.py` and theme support is `ui/theme.py`. V2 should reuse existing helpers where they help, but it should not keep the old page composition just because those helpers exist.

The user supplied IntervalCoach screenshots as a reference. The relevant lesson is not to copy exact visuals. The lesson is page ownership: each page has a clear top hierarchy and a small number of visible decisions.

## V2 Product Contract

Dashboard V2 must answer four questions in order:

1. What is my state today?
2. What should I do today?
3. How is this week going versus target?
4. What is the next important action?

Planning V2 must answer four questions in order:

1. What goal and phase am I training for?
2. Am I on track?
3. What does this week look like versus actual Garmin facts?
4. What correction, if any, should I make?

Anything that does not answer those questions belongs in diagnostics, advanced settings, export, or a separate lower-priority section.

## Non-Negotiable UI Rules

Dashboard above the fold must have at most five visible sections:

- Page header and sync status.
- Today command center.
- Today's workout or rest recommendation.
- This week load summary.
- Next 7 days or plan status.

Planning above the fold with an active plan must have at most five visible sections:

- Goal header.
- Phase/progress strip.
- On-track/off-track summary.
- Current week plan/fact summary.
- Primary correction action.

No full editor appears on Dashboard by default.

No raw checkpoint history appears on Dashboard by default.

No builder controls appear in Planning unless the user is in `Собрать план` or explicitly opens build/edit goal.

No export controls appear in Planning unless the user is in `Экспорт и детали`.

No large table appears above the fold unless it is the user's explicit selected task.

Every top-level page should have one visually dominant primary CTA. Secondary actions must be links, small buttons, or collapsed sections.

Russian labels should be used consistently in user-facing flows. English terms such as `checkpoint`, `execution feedback`, and `microcycle` can exist in code and diagnostics, but primary UI copy should use plain coaching language.

## Target Dashboard V2 Structure

The new Dashboard shell should be rendered by a function such as `_render_dashboard_v2_shell(state, current_status, latest_training_status, activities_df, on_sync)`.

The top section should be `Сегодня` with a large readiness/status card. It should show the minimum useful numbers: readiness or form, TSB, CTL, HRV/RHR/sleep if available, and one plain-language state label.

The second section should be `Тренировка сегодня`. It should show today's planned workout or rest state. It should include one primary CTA, likely `Открыть тренировку` or `Открыть план`, and one short reason.

The third section should be `Неделя`. It should show done TSS, remaining planned TSS, target TSS, and forecast. If exact target is unavailable, show a conservative label such as `цель не задана` rather than filling with noisy metrics.

The fourth section should be `Следующие 7 дней`. It should show compact day chips/cards with date, sport, TSS, and one status color. It should not show full workout descriptions.

The fifth section should be `План`. It should show whether the plan is on track and provide one CTA to Planning. It must not show raw checkpoint history by default.

Everything else moves into `Диагностика Dashboard`:

- old circular TSB/CTL/readiness charts if not reused,
- full coach briefing,
- detailed sync handoff,
- quick actions grid,
- old weekly calendar,
- compact analytics.

## Target Planning V2 Structure

The new Planning active-plan shell should be rendered by a function such as `_render_planning_v2_active_plan(state, goal_plan, activities_df, current_metrics)`.

The top section should be a `Goal Header`. It should show goal type, distance, race date, days/weeks remaining, phase, and on-track status.

The second section should be `Путь к цели`. It should show current CTL, target CTL, projected CTL, and form/ramp risk in one compact row. Detailed charts move below.

The third section should be `Текущая неделя`. It should summarize planned TSS, actual TSS, delta, completed sessions, missed/mismatched sessions, and the single suggested next action.

The fourth section should be `План и факт`. It should reuse the existing `_render_plan_fact_calendar(...)` logic but default to a compact week summary. Detailed day cards should open only when there is a mismatch, a focused day, or the user explicitly asks.

The fifth section should be `Коррекция`. It should show a plain-language recommendation and then let the user open the shared execution editor only when needed.

Builder controls move into `Собрать план`. Export controls stay in `Экспорт и детали`. Version history and rollback stay in `История и откат`, either as an expander inside correction mode or as a sub-section below the main review.

## Plan of Work

Milestone 1 builds data summaries without changing the visible UI. Add pure helpers in `ui/pages/dashboard.py` that collect Dashboard V2 data into dictionaries. The helpers should not call Streamlit. They should summarize current status, latest training status, today's likely action, weekly load, next seven days, and plan status. Add pure helpers in `ui/pages/planning.py` that summarize the active goal plan, current week, plan/fact status, and next correction signal. The tests should live in `tests/smoke/test_dashboard_v2_shell.py` and extend `tests/smoke/test_planning_page_explainability.py` where existing planning helper tests already live.

Milestone 2 replaces Dashboard's visible composition. Keep `render_dashboard_page(...)` as the public entry point, but after data loading it should call a new V2 renderer instead of rendering the current long chain. The old sections should move into a collapsed diagnostics expander so no existing functionality disappears during the first pass. The acceptance proof is that Dashboard no longer renders the full execution editor or raw planning history by default, and the top page shows the V2 section labels.

Milestone 3 replaces Planning's active-plan composition. Keep the existing workspace radio initially for safety, but make the default active-plan experience review-first. In `Скорректировать выполнение`, render the V2 goal header, current-week summary, plan/fact summary, and correction CTA before any editor/history details. The shared execution editor should appear only after the user opens correction or when a focused day is selected from plan/fact. The acceptance proof is that opening Planning with an existing goal shows the active plan review first and not the builder/export controls.

Milestone 4 polishes the visual system. Add a small set of reusable local card helpers if existing `ModernUI` helpers are insufficient. This should define consistent card spacing, status colors, label hierarchy, and compact day chips. Do not introduce a full design-system migration in this milestone; the aim is a coherent V2 shell, not a component-library rewrite.

Milestone 5 removes duplicate or obsolete paths after smoke and acceptance pass. If diagnostics preserve old sections successfully, decide which old blocks should remain as advanced details and which should be deleted. This milestone should include final test coverage and an update to this ExecPlan's retrospective.

## Concrete Steps

Work from `/Users/gregkisel/Developer/ai_trainer`.

Before editing, inspect current branch state:

    git status --short

Create helper tests first where practical:

    python3 -m pytest tests/smoke/test_planning_page_explainability.py tests/smoke/test_ui_page_exports.py -q

For Milestone 1, edit:

- `ui/pages/dashboard.py`
- `ui/pages/planning.py`
- `tests/smoke/test_dashboard_v2_shell.py`
- `tests/smoke/test_planning_page_explainability.py`

For Milestone 2, edit:

- `ui/pages/dashboard.py`
- any small local helper module only if the page becomes harder to read

For Milestone 3, edit:

- `ui/pages/planning.py`
- `ui/components/execution_feedback.py` only if the editor needs an explicit compact trigger or focus handoff change

For each milestone, run focused tests:

    python3 -m pytest tests/smoke/test_dashboard_v2_shell.py tests/smoke/test_planning_page_explainability.py tests/smoke/test_planning_execution.py tests/smoke/test_ui_page_exports.py -q

After each visible UI milestone, run full smoke:

    python3 -m pytest tests/smoke -q

For acceptance runtime verification:

    ACCEPTANCE_PORT=8510 ./run_acceptance.sh

Then in another shell:

    curl -sS -i http://localhost:8510/_stcore/health

Expected health result includes:

    HTTP/1.1 200 OK
    ok

Stop the acceptance server with Ctrl-C after verification.

## Validation and Acceptance

Milestone 1 is accepted when pure helper tests pass and no page behavior changes.

Milestone 2 is accepted when:

- Dashboard top-level visible sections are the V2 sections: `Сегодня`, `Тренировка сегодня`, `Неделя`, `Следующие 7 дней`, and `План`.
- Dashboard does not render `Факт выполнения по дням` or the full execution editor unless a fallback diagnostic toggle is explicitly opened.
- Dashboard still offers a path to Planning correction.
- Focused tests and full smoke pass.

Milestone 3 is accepted when:

- Planning with an active goal opens on goal/current-week review rather than builder/export controls.
- `Собрать план` still supports plan creation.
- `Экспорт и детали` still supports export and Intervals.icu actions.
- Plan/fact can still focus a day into the execution editor.
- Focused tests and full smoke pass.

Milestone 4 is accepted when:

- Dashboard and Planning use consistent section titles, card density, and status colors.
- The above-the-fold page area contains only the primary decision surfaces.
- Diagnostics are available but visually secondary.

Final acceptance is:

- `python3 -m pytest tests/smoke -q` passes.
- Acceptance runtime health returns `HTTP 200 ok`.
- A manual browser pass confirms the pages no longer read like a stacked diagnostic console.

## Idempotence and Recovery

The implementation should be additive at first. Keep old sections reachable in diagnostics until the V2 shell is stable. This makes it safe to compare old and new behavior and prevents losing functionality during the reset.

Do not change planning math, checkpoint persistence, Garmin sync, or export payload formats unless a failing test proves the UI shell cannot be separated from those contracts.

If a V2 renderer causes a regression, temporarily route the entry point back to the previous section renderer and keep the pure summary helpers. The helper layer is useful even if the visual shell needs another pass.

The worktree may contain unrelated local environment changes under `ai_trainer_env/*`; do not revert or stage those unless the user explicitly asks.

## Artifacts and Notes

Current audit snapshot from 2026-06-21:

- Dashboard entry point: `ui/pages/dashboard.py::render_dashboard_page`.
- Dashboard currently renders too many top-level jobs in a single chain.
- Planning entry point: `ui/pages/planning.py::render_planning_page`.
- Planning already has modes, but the active-plan review does not yet have a strong V2 top hierarchy.
- Full smoke after the latest pre-plan cleanup passed at `181 passed`.
- Acceptance runtime health after the latest pre-plan cleanup returned `HTTP 200 ok`.

## Interfaces and Dependencies

No new external dependencies are expected.

Dashboard helper interface should be a pure function shaped like:

    def _build_dashboard_v2_summary(
        state: StateManager,
        current_status: dict[str, Any],
        latest_training_status: dict[str, Any],
        activities_df: pd.DataFrame,
    ) -> dict[str, Any]:
        ...

The returned dictionary should contain stable keys such as `today`, `workout`, `week`, `next_days`, `plan`, and `diagnostics`.

Planning helper interface should be a pure function shaped like:

    def _build_planning_v2_summary(
        goal_plan: Mapping[str, Any],
        activities_df: pd.DataFrame,
        current_metrics: Mapping[str, Any],
    ) -> dict[str, Any]:
        ...

The returned dictionary should contain stable keys such as `goal`, `progress`, `current_week`, `plan_fact`, `correction`, and `diagnostics`.

The V2 renderers should consume these dictionaries and call Streamlit. This separation keeps tests cheap and prevents another round of UI changes from being untestable.
