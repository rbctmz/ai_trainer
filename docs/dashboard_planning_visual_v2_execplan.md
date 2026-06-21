# Dashboard and Planning Visual V2 Shell

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

This document is maintained in accordance with `.agent/PLANS.md`.

## Purpose / Big Picture

Dashboard and Planning already have a better information architecture after `docs/dashboard_planning_v2_execplan.md`, but the current visible UI still looks like default Streamlit: large generic title, emoji tab buttons, a purple banner, bordered default metric boxes, and weak hierarchy. After this change, a user opening Dashboard or Planning should see an intentional coaching-app cockpit: a compact product header, warm non-purple visual direction, custom summary cards, clear section titles, and no duplicate hero/title stack.

The measurable behavior is visible at `http://localhost:8501/`: Dashboard should no longer show the old purple `AI Trainer` banner from `ModernUI.show_horizontal_nav`, and the first screen should use custom V2 cards rather than plain Streamlit metric boxes. Planning with an active plan should use the same visual language for goal, progress, current week, and correction.

## Progress

- [x] (2026-06-21 16:06+04:00) Created this visual V2 ExecPlan after inspecting the live Safari screenshot, `app.py`, `utils/modern_ui.py`, `ui/navigation.py`, `ui/pages/dashboard.py`, and `ui/pages/planning.py`.
- [x] (2026-06-21 16:15+04:00) Added shared Visual V2 CSS variables and render helpers in `utils/modern_ui.py`.
- [x] (2026-06-21 16:20+04:00) Replaced the global app title and old horizontal page banner with a compact product shell.
- [x] (2026-06-21 16:28+04:00) Converted Dashboard V2 top sections from default Streamlit metrics into custom visual cards.
- [x] (2026-06-21 16:36+04:00) Converted Planning V2 review sections into the same custom visual card system where summary data is available.
- [x] (2026-06-21 16:50+04:00) Ran py_compile, smoke tests, acceptance health, and browser DOM smoke for Dashboard and Planning.

## Surprises & Discoveries

- Observation: the Dashboard V2 logic is correct but the visual shell is still default Streamlit.
  Evidence: the live screenshot shows `🏃‍♂️ Персональный AI Тренер`, emoji nav buttons, a purple `AI Trainer` banner, then another `Dashboard` title before the actual V2 sections.

- Observation: the purple banner is not in Dashboard logic itself.
  Evidence: `ui/pages/dashboard.py` calls `ModernUI.show_horizontal_nav("Dashboard")`, and `utils/modern_ui.py::show_horizontal_nav` renders the gradient `AI Trainer` card.

- Observation: Planning's active-plan V2 shell uses `st.metric` and bordered containers.
  Evidence: `_render_planning_v2_active_plan(...)` in `ui/pages/planning.py` renders `st.markdown("### ...")`, `st.container(border=True)`, and `st.metric(...)`, which preserves the default Streamlit visual feel.

- Observation: Streamlit renders duplicate nav button labels in the DOM even when only one visual button is present.
  Evidence: browser DOM smoke found two text instances for several navigation labels, but exactly one visible `План` button rect. Visual validation should check visible rects or the rendered page, not raw text counts.

- Observation: browser screenshot capture in the in-app browser timed out once after DOM validation.
  Evidence: `tab.screenshot({ fullPage: false })` timed out at `Page.captureScreenshot`, while the same tab successfully returned V2 DOM checks and zero console errors. Acceptance health and smoke tests stayed green.

## Decision Log

- Decision: implement a shared Streamlit-compatible visual layer rather than replacing Streamlit.
  Rationale: the application is already a Streamlit app with many tested pages and state flows. The immediate problem is page presentation on Dashboard and Planning, so custom CSS plus small HTML helpers is lower risk than a frontend framework migration.
  Date/Author: 2026-06-21 / Codex

- Decision: move away from the purple gradient direction.
  Rationale: the user explicitly reacted to the current look as generic and messy, and the prior purple hero is one of the strongest visual offenders. The new direction should use a warmer coaching cockpit palette: ink, cream, green, teal, and amber.
  Date/Author: 2026-06-21 / Codex

- Decision: load the Visual V2 CSS contract as the baseline app shell, not only behind the older custom-theme toggle.
  Rationale: Dashboard and Planning now render `ic-*` helper classes. If those styles depend on an optional toggle, disabling the toggle would degrade the V2 pages back into unstyled Streamlit markup.
  Date/Author: 2026-06-21 / Codex

## Outcomes & Retrospective

Implemented the visual polish slice after the information-architecture V2 slice.

The app now renders a compact `AI Trainer` cockpit header after theme CSS is applied, removes the old huge `st.title("🏃‍♂️ Персональный AI Тренер")`, replaces the purple `AI Trainer` page banner with a slim page context strip, and shortens the primary navigation labels to reduce wrapping.

Dashboard now presents the first-screen state through Visual V2 helpers: page hero, readiness/form/fitness cards, today's workout card, weekly load card, next-seven-days chips, plan status, and next action. Planning now uses the same visual language for the page hero and planning summary metrics, and active-plan review cards use the shared helpers for goal, progress, current week, and correction.

Validation completed:

- `python3 -m py_compile app.py utils/modern_ui.py ui/navigation.py ui/pages/dashboard.py ui/pages/planning.py`
- `python3 -m pytest tests/smoke -q` -> `184 passed`
- `git diff --check -- app.py utils/modern_ui.py ui/navigation.py ui/pages/dashboard.py ui/pages/planning.py docs/dashboard_planning_visual_v2_execplan.md`
- `curl -sS -i http://localhost:8510/_stcore/health` -> `HTTP/1.1 200 OK` and `ok`
- Browser DOM smoke on `http://localhost:8510/` confirmed `.ic-app-header`, `.ic-page-hero`, Dashboard stat cards, seven Dashboard day chips, Planning hero/stat cards, and zero console errors.

The remaining limitation is that this is still Streamlit. Some framework chrome and sidebar controls remain, but the Dashboard/Planning first-screen experience no longer depends on the old generic title, purple banner, or default metric-stack presentation.

## Context and Orientation

This repository is a Streamlit application. The entry point is `app.py`, which initializes the page, applies theme CSS, renders a top title, renders primary navigation through `ui/navigation.py`, and dispatches to page renderers.

The shared UI helper class lives in `utils/modern_ui.py`. Its `ModernUI.apply_modern_styles(...)` method injects global CSS, and its `ModernUI.show_horizontal_nav(...)` method currently renders the purple page banner visible in the screenshot.

Dashboard lives in `ui/pages/dashboard.py`. Its public entry point is `render_dashboard_page(state, on_sync)`. The current V2 renderer is `_render_dashboard_v2_shell(...)`.

Planning lives in `ui/pages/planning.py`. Its public entry point is `render_planning_page(state)`. The current active-plan V2 renderer is `_render_planning_v2_active_plan(...)`.

The goal is not to change Garmin sync, planning math, checkpoint storage, exports, or AI coaching. The goal is to change how the existing Dashboard and Planning V2 summaries are presented.

## Plan of Work

First, extend `utils/modern_ui.py` with Visual V2 CSS variables and small helpers for page headers, section titles, stat cards, narrative cards, and day chips. These helpers should produce HTML strings or call `st.markdown(..., unsafe_allow_html=True)` and should escape user-provided text.

Second, update `app.py` so the global title is no longer a huge `st.title(...)`. Render a compact product header after CSS is applied. Keep existing navigation behavior but let CSS make the buttons feel like a deliberate segmented nav.

Third, replace `ModernUI.show_horizontal_nav(...)` with a slim page context strip instead of the old purple gradient banner. This preserves the call sites while removing the visual offender.

Fourth, update Dashboard's `_render_dashboard_v2_shell(...)` to render the V2 summary through the new visual helpers. The top screen should be a card-based cockpit with custom HTML cards and fewer default Streamlit metric widgets.

Fifth, update Planning's `_render_planning_v2_active_plan(...)` in the same way. The active plan top section should show goal, progress, current week, and correction as coherent cards.

## Concrete Steps

Work from `/Users/gregkisel/Developer/ai_trainer`.

Inspect the relevant files:

    rg -n "show_horizontal_nav|apply_modern_styles|st.title|st.metric" utils ui app.py

After edits, run:

    python3 -m py_compile app.py utils/modern_ui.py ui/pages/dashboard.py ui/pages/planning.py
    python3 -m pytest tests/smoke/test_dashboard_v2_shell.py tests/smoke/test_planning_page_explainability.py tests/smoke/test_planning_execution.py tests/smoke/test_ui_page_exports.py -q
    python3 -m pytest tests/smoke -q

For runtime acceptance, run:

    ACCEPTANCE_PORT=8510 ./run_acceptance.sh

Then verify:

    curl -sS -i http://localhost:8510/_stcore/health

Expected health result includes `HTTP/1.1 200 OK` and `ok`.

## Validation and Acceptance

The visual V2 slice is accepted when:

Dashboard no longer shows the old purple `AI Trainer` gradient banner.

Dashboard's first screen uses custom V2 card classes such as `ic-hero`, `ic-stat-card`, or `ic-day-chip` instead of only default metric containers.

Planning active-plan review uses the same visual system for `Цель`, `Путь к цели`, `Текущая неделя`, and `Коррекция`.

The app still passes focused smoke, full smoke, and Streamlit acceptance health.

Browser smoke on Dashboard returns no console errors and the visible headings still include Dashboard V2 labels.

## Idempotence and Recovery

The changes are additive in spirit: they replace rendering helpers and CSS but do not alter planning data structures or persistence. If a visual helper breaks rendering, revert the helper call to the previous `st.metric` block while keeping the pure summary helpers from the prior V2 implementation.

Do not stage unrelated local environment changes under `ai_trainer_env/*` or unrelated untracked files.

## Artifacts and Notes

The current live screenshot shows the exact anti-pattern this plan fixes: duplicate product title, emoji nav buttons, purple banner, duplicate Dashboard title, and default metric cards. That is the before-state for this visual slice.
