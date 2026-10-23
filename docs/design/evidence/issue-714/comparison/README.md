# S4 C3: current → proposed plan comparison

23October2026, #714 / draft#715. UI/Design handoff consumes the independently
READY C2 contract atc7b42f5, unchanged. [Approved comparison semantics](../../../../planning_confirmation_s4_comparison_spec.md).
No API/domain/TS-schema/AC edits in C3. C2 final contributor-safe pass on clean
c7b42f5:3991passed/16skipped/101deselected/7warnings257.11s with correct venv PATH.
This is backend evidence, not a whole-suite measurement of the new UI.

Brief: the user must see what changes from selected current plan to the proposed
version before save. First view pairs both inclusive periods, saved preparation/
intent/focus/mode, availability/days, demand, canonical scoped total/peak TSS and
events. A separate visible weekly orientation remains distinct from assignment.
No scalar cross-period delta or client comparability/lineage rule. Server day
states and before/after prescriptions are available in keyboard-native details;
counts are explicitly calendar days, not workout counts. Unknown is not zero,
rest or an erased activity. Applied/uncertain comparison labels do not name a
historical baseline current today. Old receipts missing comparison keep the
candidate facts and explicit unavailable explanation without a new save gate.

Implementation: PlanComparisonSummary.tsx is presentational. It consumes C2
fields, maps vocabulary and formats existing numbers/dates/targets. Existing
WorkoutStrip.formatTarget is exported without behavior change; PlanningDate is
extracted unchanged from PlanDecisionSummary and shared. The main summary
includes existing save controls and M4 notices. Candidate-only duplicate facts
move into details when paired baseline facts exist; new no-baseline decisions
retain the existing first view. No confirmation/stale/unknown-save handlers move.

Initial observed UI RED: new real edit test expects paired region and values;
1failed/1existing warning13.37s before UI source edit. First full S4 source pass:
19passed/1warning36.78s. Added legacy/partial/historical comparison coverage and
checked related lifecycle/entry/confirmation journeys:63passed/1warning96.52s.
Final presentation-only historical labels/caption:22S4passed/1warning37.11s.
33UI/contract source smoke passed1.55s. Final lint/build, contract freshness,
repository Ruff and whitespace pass. No repeated full contributor claim for C3.

Captures are direct actual DOM, synthetic only. edit-390/900/1280 in light/dark
show the paired summary; schedule table scrolls locally at390 and has no document
overflow. capture.py runs the actual temporary-data new/edit/replacement/cancel/
post-commit response-loss/replay journey, producing owner-a/b/c/d and a factual
oracle. Same-identity replay succeeds, no unhandled JS exceptions; intentionally
disabled provider discovery503 and response-loss ERR_FAILED are classified.
An extra320px capture/assertion passes. No athlete cache/provider writes.

Reproduction, primary venv on PATH, PYTHONPATH=.:

    python -m pytest -m e2e tests/e2e/test_planning_confirmation_s4_ui.py tests/e2e/test_planning_entry_ui.py tests/e2e/test_planning_build_confirmation_ui.py tests/e2e/test_planning_cycle_lifecycle_ui.py -q -p no:cacheprovider --tb=short
    python docs/design/evidence/issue-714/comparison/capture.py
    npm --prefix web run lint
    npm --prefix web run build
    npm --prefix web run contract:extract -- --check

The prototype-edit images have now been shown to the owner with one neutral
question about actual change. After that point preserve those images as fixed
feedback evidence; subsequent capture versions need a new directory. E2E outputs
use different edit/confirmation names. Original A–D and revision1 owner images
are unchanged, and incidental old710/693/readiness captures were restored after
tests. UI rendering/tests do not establish owner understanding. New owner answer
pending; C3 independent review pending; M3/S4 remain unaccepted and draft. Native
1/2 historical9d41e2b, final scoped2/2 not requested yet. No merge.

## Independent C3 round1: rest phase correction

At681c29e the reviewer found one blocking P2: rest(Base) to rest(Recovery) is a
server-classified change, but both cells rendered only rest/0TSS. Parent
read-only display fixture independently reproduced it:1failed/22deselected/
1existing warning11.57s. This violates CMP06's visible phase requirement.
DayValue now displays the saved phase on rest days as on scheduled days.
No comparison classification or API/domain contract changes. Regression never
confirms the modified response, and cancelling preserves the selected checkpoint.
Final full S4 UI contour:23passed/1existing warning37.61s; Ruff/diff pass.
This change does not alter the paired owner prototype, which remains frozen.
The nonblocking suggestion to expose additional focus/transition details remains
tracked in #714 for later UI polish; it does not revise the approved C2 content
comparison or create a new publication gate. Scoped C3 delta review pending.
Final post-correction web lint/production build and contract freshness also pass.


Final scoped C3 round2/2 READY atc324c9eb9cee9d585575e2a9ba60c16297e4a660.
Named P2 fixed-inc324c9e; independent regression1passed/22deselected/1existing
warning6.31s, HEAD/tree clean unchanged. UI→Supervisor/Integrator handoff is
recorded in#714. C3 implementation/review is complete; owner response and C4
remain pending. Historical native1/2 and separate merge approval unchanged.
