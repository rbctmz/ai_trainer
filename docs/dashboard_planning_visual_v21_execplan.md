# Dashboard and Planning Visual V2.1 Polish

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

This document is maintained in accordance with `.agent/PLANS.md`.

## Purpose / Big Picture

The first Visual V2 pass made Dashboard and Planning look substantially less like default Streamlit, but the current browser screenshots still show remaining clutter. Dashboard repeats page context with an extra `AI Trainer / DASHBOARD` strip, the week summary is split into several cards that compete for attention, and Planning's plan-builder area drops back into long default Streamlit forms after the hero. After this change, Dashboard should feel more focused on one coaching decision, and Planning's builder should read as a guided setup surface rather than a raw form stack.

The user-visible behavior is visible by running the app at `http://localhost:8501/`. Dashboard should no longer show the redundant context strip below navigation. Planning in `Собрать план` mode should show a concise setup intro and preview cards that explain goal, availability, checkpoint, and target load before the build action.

## Progress

- [x] (2026-06-21 17:31+04:00) Created this V2.1 ExecPlan after reviewing the Firefox screenshots and inspecting `ui/pages/dashboard.py`, `ui/pages/planning.py`, and `utils/modern_ui.py`.
- [x] (2026-06-21 17:37+04:00) Removed the redundant Dashboard context strip and kept the page hero as the only Dashboard page identity.
- [x] (2026-06-21 17:41+04:00) Reused existing Visual V2 helpers rather than adding new helper APIs.
- [x] (2026-06-21 17:44+04:00) Tightened Dashboard copy: Russian hero title, readable week status, and Russian sport labels for plan days.
- [x] (2026-06-21 17:49+04:00) Wrapped Planning builder sections in clearer Visual V2 cards and replaced default preview metrics with custom cards.
- [x] (2026-06-21 17:55+04:00) Ran smoke tests and browser DOM acceptance for Dashboard and Planning.
- [x] (2026-06-21 19:28+04:00) Added a theme-stability follow-up after Firefox screenshots showed dark native Streamlit widgets mixed into the light V2 surface.
- [x] (2026-06-21 19:34+04:00) Hardened shared button/input/sidebar/metric selectors against Streamlit's current `data-testid` markup.
- [x] (2026-06-21 19:38+04:00) Replaced the remaining `План готов` workspace `st.metric` block with Visual V2 cards.
- [x] (2026-06-21 19:49+04:00) Added a follow-up fix for invisible sidebar content and white radio labels on light Planning surfaces.
- [x] (2026-06-22 11:29+04:00) Converted the sidebar from a fragile native-flow panel into a fixed 300px rail for desktop layouts.
- [x] (2026-06-22 11:58+04:00) Relaxed the fixed sidebar rail CSS so Streamlit's native collapse/expand behavior works again.
- [x] (2026-06-22 12:09+04:00) Restored the collapsed-sidebar expand button by no longer hiding the entire Streamlit toolbar.

## Surprises & Discoveries

- Observation: Dashboard still renders the older `ModernUI.show_horizontal_nav("Dashboard")` page context strip.
  Evidence: `ui/pages/dashboard.py::render_dashboard_page` calls `ModernUI.show_horizontal_nav("Dashboard")`; Firefox shows an extra `AI Trainer` and `DASHBOARD` strip between the primary navigation and the demo alert.

- Observation: Planning's top hero is V2, but the builder flow below it is still dominated by raw Streamlit controls and metrics.
  Evidence: `ui/pages/planning.py::render_planning_page` uses `st.subheader("🎯 План под цель...")`, `st.markdown("#### 🧭 Сценарий...")`, sliders, selectboxes, and a bordered `st.container` with five `st.metric` calls.

- Observation: shell-based localhost health checks can be blocked by sandbox escalation review even when the Streamlit server is running.
  Evidence: the escalated Python `urllib.request.urlopen("http://localhost:8510/_stcore/health")` command was rejected by auto-review infrastructure, while read-only browser DOM checks against `http://localhost:8510/` succeeded and returned zero console errors.

- Observation: Streamlit's current button markup can bypass the older `.stButton > button` styling path.
  Evidence: Firefox screenshots showed inactive nav buttons rendering with dark native backgrounds and low-contrast text while the V2 shell surface remained light.

- Observation: the non-export Planning summary still used native `st.metric` after the V2.1 polish.
  Evidence: `ui/pages/planning.py::_render_active_plan_workspace_summary` rendered `План готов` through a bordered container with four `st.metric` calls, and the screenshot showed those values nearly invisible on the V2 background.

- Observation: the Streamlit sidebar can reserve width while its inner content layer remains visually absent in Firefox.
  Evidence: user screenshots showed a blank left rail while DOM/a11y still contained sidebar content and the main `.block-container` started after the reserved sidebar width.

- Observation: Planning's `Режим страницы` radio labels can render white over the light V2 background.
  Evidence: screenshot showed `Собрать план`, `Скорректировать выполнение`, and `Экспорт и детали` as low-contrast white text under the Planning hero.

- Observation: forcing the sidebar to `position: fixed` with `transform: translateX(0)` restores a visible rail but disables Streamlit's native collapse state.
  Evidence: user reported the left panel no longer collapsed after the fixed rail follow-up.

- Observation: hiding `div[data-testid="stToolbar"]` also hides Streamlit's collapsed-sidebar expand button.
  Evidence: browser DOM showed `button[data-testid="stExpandSidebarButton"]` present after collapse, but it inherited zero visible size while the toolbar was hidden.

## Decision Log

- Decision: remove the Dashboard context strip instead of restyling it.
  Rationale: Dashboard already has the app header, primary navigation, demo callout, and page hero. The extra strip repeats page identity and increases vertical noise without adding decision value.
  Date/Author: 2026-06-21 / Codex

- Decision: keep Streamlit controls for Planning inputs but add Visual V2 framing and summaries around them.
  Rationale: Replacing sliders/selectboxes would be high risk and would not improve planning logic. The immediate quality gain comes from better section hierarchy, explanatory cards, and custom preview cards around the existing controls.
  Date/Author: 2026-06-21 / Codex

- Decision: avoid adding new Visual V2 helper APIs in this slice.
  Rationale: `render_text_card`, `render_stat_card`, `render_section_title`, and `render_page_hero` were enough for the V2.1 polish. Avoiding new helpers keeps the change smaller and reduces the chance of another Streamlit Markdown rendering edge case.
  Date/Author: 2026-06-21 / Codex

- Decision: fix theme consistency at the shared `ModernUI.apply_modern_styles` layer instead of adding page-local overrides.
  Rationale: Dashboard, Planning, sidebar controls, and other Streamlit widgets all share the same native components. Centralizing the selectors prevents each page from drifting into a different light/dark contract.
  Date/Author: 2026-06-21 / Codex

- Decision: force the visible sidebar contract on `stSidebarContent` and `stSidebarUserContent`, not only the outer `stSidebar` section.
  Rationale: the outer section can be present and still visually empty if Streamlit's inner layers retain native transparency/visibility behavior. Targeting the inner content wrappers makes the rail deterministic without moving navigation logic.
  Date/Author: 2026-06-21 / Codex

- Decision: use a fixed desktop sidebar rail instead of relying on Streamlit's flex placement.
  Rationale: Chrome still showed a blank reserved left column even when the accessibility tree contained sidebar content. Fixing the rail to `left: 0` with a high z-index makes the sidebar render independently of Streamlit's main content stacking.
  Date/Author: 2026-06-22 / Codex

- Decision: relax the sidebar fix back to native Streamlit layout control and limit our CSS to visual styling.
  Rationale: a sidebar must remain collapsible. Overriding Streamlit's width, transform, visibility, and main-content offset is too brittle; the safer contract is to style the open panel while allowing Streamlit to own expand/collapse placement.
  Date/Author: 2026-06-22 / Codex

- Decision: keep Streamlit toolbar available for the sidebar expand control, but hide nonessential toolbar buttons.
  Rationale: removing the entire toolbar cleans the header but breaks recovery from a collapsed sidebar. Selectively hiding Deploy/menu while preserving `stExpandSidebarButton` keeps the minimal shell and preserves navigation.
  Date/Author: 2026-06-22 / Codex

## Outcomes & Retrospective

Implemented the V2.1 polish slice starting from commit `d22e33f fix: render v2 text cards as html fragments`.

Dashboard now removes the redundant `AI Trainer / DASHBOARD` context strip, uses the Russian page hero title `Дашборд`, maps plan sports such as `bike` and `run` into reader-facing Russian labels, and renders a more explicit week status such as `Неделя под контролем` instead of the terse `по плану`.

Planning now uses the Russian page hero title `Планирование`, opens build mode with a `Сборка плана` guided setup card, replaces emoji Markdown headings with Visual V2 section titles for goal, constraints, and local replanning, renders the historical auto-tuning note as a V2 text card, and replaces the bordered five-metric preview with Visual V2 stat/text cards under `Сводка перед сборкой`.

Validation completed:

- `python3 -m py_compile app.py utils/modern_ui.py ui/pages/dashboard.py ui/pages/planning.py`
- `python3 -m pytest tests/smoke/test_dashboard_v2_shell.py tests/smoke/test_planning_page_explainability.py tests/smoke/test_planning_execution.py tests/smoke/test_ui_page_exports.py -q` -> `56 passed`
- `python3 -m pytest tests/smoke -q` -> `184 passed`
- `git diff --check -- ui/pages/dashboard.py ui/pages/planning.py docs/dashboard_planning_visual_v21_execplan.md`
- Browser DOM acceptance on `http://localhost:8510/` confirmed Dashboard has the Russian hero, no old Dashboard context strip, no raw HTML text, Planning has `Планирование`, `Сборка плана`, `Цель и дата старта`, `Сводка перед сборкой`, and zero console errors.

The remaining gap is that Planning still uses native Streamlit sliders/selectboxes for the actual input controls. That is intentional for this slice because the controls are functional and the current problem is surrounding hierarchy, not input mechanics.

Theme-stability follow-up: shared Visual V2 CSS now targets Streamlit's current button `data-testid` selectors, input/select wrappers, expanders, legacy metric containers, and sidebar text/buttons. The `План готов` summary no longer uses native `st.metric`; it renders through Visual V2 stat/text cards, so it stays readable under both theme states and no longer looks detached from the rest of Planning.

Sidebar/radio follow-up: the sidebar now has a visual styling contract across the outer `stSidebar` and inner `stSidebarContent`/`stSidebarUserContent` layers without overriding native layout state. Planning radio groups now explicitly inherit `--ic-ink`, preventing white labels on the light V2 background.

Chrome sidebar follow-up: the earlier fixed-rail approach made the left panel visible but prevented collapse. The sidebar CSS now avoids overriding Streamlit's width, position, transform, visibility, and main-content offset. Visual V2 still controls sidebar background, contrast, and button styling, but Streamlit owns the actual open/collapsed layout state.

Collapse-control follow-up: the app no longer hides the whole `stToolbar`, because Streamlit renders the collapsed-sidebar expand button there. Visual V2 now hides nonessential toolbar buttons while keeping `stExpandSidebarButton` visible and styled.

## Context and Orientation

This repository is a Streamlit application. The entry point is `app.py`, which applies the Visual V2 shell and dispatches to page renderers. Dashboard lives in `ui/pages/dashboard.py`; its public entry point is `render_dashboard_page(state, on_sync)` and its V2 renderer is `_render_dashboard_v2_shell(...)`. Planning lives in `ui/pages/planning.py`; its public entry point is `render_planning_page(state)`.

The shared Visual V2 helpers live in `utils/modern_ui.py` on the `ModernUI` class. Helpers such as `render_page_hero`, `render_section_title`, `render_stat_card`, `render_text_card`, and `render_day_chip` render custom HTML through Streamlit Markdown. These helpers must escape user-provided text and avoid multi-line nested HTML that Streamlit may render as literal text.

The goal is visual presentation only. Do not change Garmin sync, training plan math, planning checkpoint persistence, Banister calculations, or export logic.

## Plan of Work

First remove the Dashboard call to `ModernUI.show_horizontal_nav("Dashboard")`. Leave `show_horizontal_nav` in `utils/modern_ui.py` for older pages that may still use it, but Dashboard should use its own page hero only.

Second, improve `utils/modern_ui.py` with small helpers only if existing helpers cannot express the needed Planning builder summaries. Any helper must render a single clean HTML fragment and escape values.

Third, tune Dashboard's visible copy and grouping: keep Today, workout, week, next seven days, plan, and next step, but reduce redundant subtitles and make week status read as a compact decision card.

Fourth, update Planning's `Собрать план` branch. Add a short setup callout before the controls. Replace the bordered five-metric preview with Visual V2 stat/text cards. Use section titles without emoji-heavy Markdown headings for the main setup sections, while keeping the actual Streamlit controls intact.

## Concrete Steps

Work from `/Users/gregkisel/Developer/ai_trainer`.

Inspect:

    rg -n "show_horizontal_nav|План под цель|Сценарий и ограничения|Локальная перепланировка|st.metric|render_text_card" ui/pages/dashboard.py ui/pages/planning.py utils/modern_ui.py

After edits, run:

    python3 -m py_compile app.py utils/modern_ui.py ui/pages/dashboard.py ui/pages/planning.py
    python3 -m pytest tests/smoke/test_dashboard_v2_shell.py tests/smoke/test_planning_page_explainability.py tests/smoke/test_planning_execution.py tests/smoke/test_ui_page_exports.py -q
    python3 -m pytest tests/smoke -q

For browser acceptance, run:

    ACCEPTANCE_PORT=8510 ./run_acceptance.sh

Then verify `http://localhost:8510/_stcore/health` returns `200 ok` and browser DOM text on Dashboard does not include the redundant context strip before the hero.

## Validation and Acceptance

This V2.1 slice is accepted when Dashboard no longer shows the extra `AI Trainer / DASHBOARD` strip below primary navigation, Dashboard no longer renders raw HTML text in V2 cards, Planning build mode uses custom Visual V2 preview cards for current state and availability/checkpoint summary, and all smoke tests pass.

Browser smoke should confirm zero console errors and visible Dashboard text still includes `Dashboard`, `Сегодня`, `Следующие 7 дней`, and `План`, while not showing literal `<div class="ic-card-title">`.

## Idempotence and Recovery

The edits are presentation-only and can be reverted file by file. If a Visual V2 helper causes malformed HTML, prefer reverting that helper call to existing `render_text_card` or `render_stat_card` rather than changing planning logic. Do not stage unrelated local environment changes under `ai_trainer_env/*` or unrelated untracked files.

## Artifacts and Notes

The Firefox screenshots showed the improved baseline and the remaining issues: extra Dashboard context strip, split week cards, default Planning controls, and default metric preview cards. This plan treats those as V2.1 polish targets, not as a full product redesign.
