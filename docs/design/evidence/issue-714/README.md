# S4 M2 — confirmation UI prototype and implementation

2026-10-22 Europe/Moscow, #714 / draft #715. UI/Design consumes the reviewed M1
spec7337fb5 and handoffa7732e5. [Acceptance/source map](../../../planning_confirmation_s4_spec.md)
is unchanged. No Python/domain/API/TS schema, forecast/dose policy or persistence
change. The real isolated web stack is the interactive prototype and acceptance
surface; this is not a separate static mock or a production/athlete rollout.

## Brief and composition

An athlete reviews a frozen candidate before saving: action/goal/intent, exact
inclusive cycle dates, applied events and selected availability ceiling. One
summary leads with those facts, then total/peak/target TSS with distinct scopes
and the consequence of saving/replacing. The M4 source/adjustment panel precedes
confirmation. Unneeded first-run suggestions are hidden on step4; editing still
uses the existing wizard. Existing semantic tokens, cards, disclosures, table
and focus patterns are reused; no global theme/layout system was added.

PlanDecisionSummary reads only the returned candidate. A missing old dated scope
uses the agreed no-comparison text; all bare deltas/rolling/technical rule labels
are removed from this confirmation path. Missing values stay unknown; numerical
zero stays zero. Hours/counts of assigned training are not derived from TSS or
ceilings. Applied/current=false and current=null do not claim active status.

PlanForecast uses returned dated points, a neutral model explanation, calendar
coordinates for drawing only, theme tokens and an accessible date/value table
that does not require hover. No model verdict, TSB thresholds or goal efficacy
is calculated in TypeScript. Weekly rows retain all sports/units (local table
scroll on narrow screens), preserve zero, separate the optional race forecast
and put raw notes under disclosure. Rule-audit data stay advisory. Existing
S1 identity-only save, uncertain lock/retry, stale handling and M4 publication
gates stay in their original owner; presentation introduces no extra gate.

## Evidence and test boundaries

Before product edits, the new real-backend S4 test failed on the absent summary
region: **1failed/1warning10.91s**. Its initial fixture attempt had read an empty
start date before hydration; corrected by waiting for the existing observable
date value. That setup error is not product RED. No UI source was changed before
the missing-summary RED.

First new contour:9passed/1event-fixture refusal19.34s. A later related contour:
51passed/3failed89.90s. The historical/unknown receipt text was already visible;
exact text locators included the existing status icon, so only the locator was
corrected to retain the actual status/no-active/no-confirm assertions. These
are presentation fixtures, not real successful publication of altered payloads.

Two actual event-goal configurations (Thursday start/weekday race,10h) were
rejected by existing M3 readiness: prescription_infeasible bike_vo2max_intervals
and/or prescription_missing near the race. No guard, template, severity or API
was changed. The explicit positive fixture uses a future Monday start and a
Saturday race110days later and passes the real backend. This is one executable
scenario, not universal event-generator acceptance; existing generator follow-up
#707 stays outside UI scope. Correction contour:4passed/1warning9.55s.

Related real UI contour then passed **54tests/1existing warning80.11s**. The final
readiness-error presentation scenario and summary screenshots were added after
that measurement; final contour/build/review results are appended below.

| Scenario | Evidence boundary / outcome to verify |
| --- | --- |
| new no-race plan;390/900/1280 × light/dark | real preview + identity-only confirm; source values/scopes, keyboard table toggle and no page overflow |
| edit8→4weeks | real preview; no undated delta, candidate total/dates and comparison gap; cancel preserves saved checkpoint |
| event/manual; replacement | real supported preview; applied events/phases and replace consequence; cancel preserves current checkpoint |
| missing/infeasible starting dose | existing real entry E2E; rejection remains without confirm |
| stale/uncertain retry | existing real endpoint scenarios, transport simulation only where documented; locks and identity preserved |
| historical/current unknown/missing facts | explicitly modified read-only display fixtures; never confirm or claim backend acceptance of altered payload |
| structured M3 refusal | explicit422 error-display fixture; real M3 rejection above also observed, no fake successful token |

Screen captures are synthetic only. File names identify viewport/theme;
confirmation-* is the full page, decision-* focuses on the summary. Automated
checks and visual inspection are distinct from an unaided owner usability test.
That owner test, actual assistive-technology acceptance, whole S4/M3 final native
review and merge are **NOT YET**. #712 announcement follow-up is not silently
implemented or closed by this work.

## Reproduction

Use the primary checkout's venv on PATH; E2E harness allocates isolated SQLite,
ports and demo sources with providers disabled. No .env/log/private DB is included.

    python -m pytest -m e2e tests/e2e/test_planning_confirmation_s4_ui.py tests/e2e/test_planning_entry_ui.py tests/e2e/test_planning_build_confirmation_ui.py tests/e2e/test_planning_cycle_lifecycle_ui.py -q -p no:cacheprovider --tb=short
    npm --prefix web run lint
    npm --prefix web run build
    npm --prefix web run contract:extract -- --check
    npm --prefix web run contract:inventory
    python -m ruff check tests/e2e/test_planning_confirmation_s4_ui.py tests/e2e/test_planning_build_confirmation_ui.py tests/e2e/test_planning_cycle_lifecycle_ui.py --no-cache
    git diff --check

## Final M2 verification

Related contour: **55 passed / 1 existing Starlette/httpx warning, 80.71s**
(new S4 plus entry, identity-only confirmation, lifecycle/stale/uncertain tests).
After the final label/curve contrast adjustment: **14 S4 UI tests passed /
1 same warning, 22.52s**; all eight captures regenerated. The 55-test contour
was not repeated after this presentation-only adjustment. Curves now differ by
line style as well as theme tokens; summary/legend text uses the existing ink
token. Final web lint and production build both passed. Contract extractor
freshness, call inventory, Ruff for the three changed E2E modules and diff-check
passed. API/domain/schema/contract artifacts have no changes. This is targeted
M2 evidence, not whole contributor/all-browser acceptance.

Visually inspected the final decision-390-dark and decision-1280-light captures:
period, availability ceiling, total/peak/orientir and save consequence are
readable; the narrow layout stacks facts. Automated viewport checks separately
assert no page overflow and keyboard access to the numerical forecast table.
Owner unaided usability and actual assistive-technology testing remain NOT YET.

## Independent UI review and handoff

M2 UI round1/2: **READY** at
46201b3c52b6b9818a5a1420fdcb7324c66c1b0b, exact a7732e5..46201b3 diff.
Independent Reviewer checked S4-01…11 source/acceptance mapping: frozen data and
assignment/target/availability scopes; unknown/zero; historical/current-null
receipts; no new comparison/efficacy/domain policy; retained identity-only,
stale and uncertain guards. No concrete P1 or blocking P2. Independent S4 E2E:
**14 passed / 1 existing warning,22.53s**; changed-test Ruff and contract freshness
passed. Narrow-dark/wide-light summaries visually checked. Only eight generated
S4 screenshots restored to reviewed source; HEAD unchanged and tracked tree clean.

UI/Design hands the implementation and this evidence to Supervisor/Integrator.
Required next input is M3 integrated acceptance plus unaided owner responses to
the unchanged M1 questions. This record changes no acceptance/API/domain policy.
Native0/2 remains reserved for stable full S4; no native request, owner acceptance
label, merge or live write occurred. M2 automation is not proof of human usability.

## CI compatibility correction

Final-head CI39823267154 ran the whole browser suite: **77 passed,274.79s**;
contract CI passed. Contributor-safe Python run: **2 failed,3940 passed,39 skipped,
101 deselected,6 warnings,432.88s**. Both failures were legacy UI source gates: one
looked for a scroll class in PlanBuilder after WeeksTable moved to PlanForecast;
one required the former “Недельная цель” label instead of the agreed orientir.
No browser/product failure was observed in that run.

Those two source tests now inspect the actual weekly table component and current
Russian orientir label. The S4 browser test additionally verifies that the390px
weekly table really overflows inside its own scroll area and retains the swimming
column, while the document itself does not overflow. Both themes exercise that
invariant. Nine affected smoke tests passed0.04s;14 S4 E2E passed/1existing
warning22.46s; changed-test Ruff and diff-check passed. Runtime UI, public DTO,
M1 AC and numerical policies remain exactly the reviewed46201b3 source.
Eight regenerated captures restored to their reviewed versions. The subsequent
CI run and scoped UI review verify this test-only correction; the failed first
CI result is preserved above rather than claimed green.
