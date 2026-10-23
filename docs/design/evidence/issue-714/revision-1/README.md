# S4 UI revision1 — owner comprehension correction

UI/Design consumes unchanged M1/S4 AC and frozen-response contracts. #714 / draft
#715. The owner answered “Вообще не понятно.” and clarified “Сам экран плана”.
The first M3 exercise therefore did not demonstrate comprehension. Clarification
identifies the product surface; it does not prove a specific cause or establish
a per-field correctness score. Feedback and handoff are recorded in #714.

## Bounded prototype

Hypothesis: a first view listing implementation-oriented labels and similarly
weighted numbers needs a clearer current decision. That causal hypothesis still
needs owner feedback; a DOM test is not evidence of human comprehension.

The prototype uses the real PlanDecisionSummary/PlanBuilder components and the
existing temporary web-stack harness. It covers one new-plan decision. Its direct
DOM captures are in prototype-1280-light.png, prototype-390-dark.png and
prototype-320-light.png. No bitmap mock/edit or separate business-logic demo.
The original failed A/B/C/D captures remain unchanged at reviewed9d41e2b.

The header names the action and preparation; save consequence is immediately
below it. Candidate dates have Russian display text and exact ISO datetime
attributes, formatted in UTC solely to avoid display timezone shifts. The time
ceiling says “Ваш лимит времени” and is explicitly a maximum. Total, maximum
week and weekly orientation remain visible with separate scopes/units. TSS is
explained as load points, not assigned hours. Unknown parameters remain unknown;
no physical duration/count is derived from TSS or availability.

Extra load explanation, other constraints, successful starting-volume checks and
target calculation are disclosures. The main card includes the existing save
controls. Only EntryLoadSummary supported/can_publish-success presentation can
collapse; refusals/unverified status remain visible before confirmation. The
shared component's default presentation is unchanged for its other callers.
All original M4 provenance and per-assignment adjustments remain available.
The retained-starting-limits notice stays visible before the disclosure and save
controls; it is not hidden inside successful details. Status/identity/CAS/expiry/uncertain handlers
and API calls are untouched. Historical/current-null receipts keep their meaning.

No API, TS schema, numerical policy, M1 specification or acceptance rewrite.
UI/Design does not turn these disclosures into a new publication policy. No
new palette/global layout system or fabricated goal-efficacy interpretation.

## Checks and observed failures

Observed owner feedback is the human failure. Separately, a new observable UI
check failed before source edits: semantic date elements absent,1failed/1existing
warning11.44s. That RED proves the presentation change is new; it does not prove
that ISO dates caused the owner's confusion.

First related contour:53passed/2failed89.83s. Existing M4 tests had expected a
successful heading immediately visible; they now open the real successful-check
disclosure by keyboard before checking the same limits/sources and save/invalidate
behavior. The next run was54passed/1failed91.55s: keyboard focus was set before
the wizard's existing asynchronous title-focus transition completed. Waiting for
the actual step-heading focus (rather than retrying Enter or changing product
focus behavior) fixed the probe. Final related contour: **55passed /1existing
Starlette/httpx warning,80.90s**.

An additional320px capture exposed document overflow (324px). Wrapping the
confirmation buttons alone did not eliminate it: that was an insufficient
hypothesis, not a successful fix. Inspection also showed the long existing form
value in Stat. Adding word wrapping to that value, without changing it, made the
same capture pass at320/390/1280. Controls wrap on narrow widths as well. These
are CSS-only corrections after the55-test run. On the final source: **14S4 E2E
passed /1same warning22.79s**; the three-viewport prototype capture exited0 with
no page overflow and no confirmation. **33UI/contract smoke tests passed1.39s**
(before the two wrapping classes); repository Ruff passed. Final web lint and
production build passed; contract extraction freshness passed. This is targeted
revision evidence, not a repeated final whole contributor suite.

The M3 capture helper now selects the innermost action section because the
controls share the main summary card. Its compatibility capture is redirected
to temporary output; the original owner-case files are not regenerated. That
helper's compatibility probe passed on the final source (temporary PNG only).
The probe initially called Playwright Python's `last` property as a function;
correcting that diagnostic-helper typo made it pass, with original files intact. New probes/captures use synthetic data and
no personal/provider write. Preparation retains only the existing temporary
preview; capture does not confirm it.

## Reproduction

From this worktree with the primary venv on PATH and PYTHONPATH=.:

    python docs/design/evidence/issue-714/revision-1/capture.py
    python -m pytest -m e2e tests/e2e/test_planning_confirmation_s4_ui.py tests/e2e/test_planning_entry_ui.py tests/e2e/test_planning_build_confirmation_ui.py tests/e2e/test_planning_cycle_lifecycle_ui.py -q -p no:cacheprovider --tb=short
    npm --prefix web run lint
    npm --prefix web run build
    npm --prefix web run contract:extract -- --check
    python -m ruff check . --no-cache
    git diff --check

The single prototype was shown without explaining its answer, with one open
question about the save effect. Revision1 owner outcome is **PARTIAL**, not passed by automation. On23October
2026 the owner answered the save-effect question: “План создаться”. This correctly
identifies creation of a plan; it does not independently demonstrate exact period,
load, ceiling, edit/replacement or uncertain-save understanding. The answer was
received before the assistant confirmed the interpretation. The next answer about “До10ч в неделю” was: “Это сколько я готов выделить и
план будет не больше”. It correctly identifies availability as a ceiling, not
assigned time. This second question contrasted the two interpretations, so this
is a prompted check, not a second unaided result. The assistant confirmed the
interpretation only after the answer. A neutral actual-total question is pending;
the old grouped A–D exercise is not repeated. It is an unassisted task within prior product discussion, not a
blind first-use study. One correct save-effect answer alone will not silently
satisfy all remaining M1 owner criteria for period/load/edit/replacement/unknown.
M3 remains incomplete and #715 remains draft. Native1/2 is historical at9d41e2b;
reserve the scoped second native review for a stable revision after owner feedback.
Do not request another full-diff/native review for a prototype status update.

Final-source refinement check: **6passed /1existing warning17.34s**, covering
the5Entry UI cases and real edit-horizon case. The latter asserts the server
retained-limit warning is visible while successful details stay collapsed. Latest
web lint/build and contract freshness passed after this refinement. No full55-case
rerun is claimed after this small presentation change.
