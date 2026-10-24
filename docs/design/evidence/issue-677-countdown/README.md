# #677: neutral event caption when countdown is not applicable

24October2026, UI/Design local Class C repair on main3aed0ac. Existing first
acceptance criterion; no new spec/API/domain date or persistence semantics.
The caption retains the saved A-event label/date. A suffix is shown only when
existing server facts say the plan is actionable and remaining days is positive.
Zero is not classified as past versus today in the browser; both stay neutral.
Missing/disabled reader facts also stay neutral. Existing layout/tokens unchanged.

Synthetic isolated browser scenarios use real backend/temporary SQLite:
ended period (390px), race day, future event, past event inside an ongoing cycle
(all others1280px). Two presentation-only legacy/disabled controls replace the
received nullable countdown or actionability field; no modified response is
confirmed. Every case checks the label/date, intended caption, no page overflow
and byte-identical planning evidence before/after the page read. All images are
caption-only light-theme actual DOM screenshots, named by synthetic case.
No personal DB/provider access or live restart. Dark palette is unchanged;
no new screen-reader/usability certification is claimed.

Observable RED on unchanged renderer:5failed/1future control passed/1existing
warning36.51s; regression commit9dee5fc precedes the source correction. GREEN:
6passed/1existing warning11.05s. Existing overview/lifecycle-boundary/contract
checks51passed/1existing warning3.58s. Ruff/whitespace, web lint/production build
and contract freshness passed. No local broad-suite repetition for this tiny UI
slice; standard PR CI and native review remain separate. Previous launch attempt
was not executed due to approval-service usage exhaustion; it changed no source.

Reproduce from task worktree with primary venv bin on PATH and PYTHONPATH=.:

    python -m pytest -m e2e tests/e2e/test_planning_event_countdown_ui.py -q -p no:cacheprovider --tb=short
    python -m pytest tests/smoke/test_planning_active_plan_overview.py tests/smoke/test_planning_cycle_projection.py tests/smoke/test_contract_extractor.py tests/smoke/test_api_call_inventory.py -q -p no:cacheprovider --tb=short
    npm --prefix web run lint
    npm --prefix web run build
    npm --prefix web run contract:extract -- --check

This record is pre-merge evidence. #677's last checkbox is not closed until the
fix is reviewed and merged. #713/#716 documentation and #707/#712 remain separate.
