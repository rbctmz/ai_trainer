# S4 comparison C1: specification and source characterization

23October2026, #714 / parent#677 / draft#715. Runtime baseline3f75915, main00de158.
Role: Spec / Architecture Owner after explicit owner scope approval and issue
handoff. [Specification](../../planning_confirmation_s4_comparison_spec.md) and
[ExecPlan](../../planning_confirmation_s4_execplan.md). This is a Class A contract
extension; no new runtime/API/TS/UI behavior is claimed by this C1 evidence.

Fixed question: can the existing frozen response explain current→proposed dates,
parameters and schedule changes, or must a new server-owned comparison exist?
Bound: one pinned synthetic eight-week plan, explicit temporary fixture confirm,
then four-week edit. No tuning, model, provider or athlete cache. User feedback is
recorded separately in the task without publishing personal responses here.

[Probe](probe.py) and [characterization](characterization.json) show the old raw
checkpoint contains56dated days/executable template lists and saved10h/all-day
availability; proposed plan has28days. Before26October–20December, after26October–
22November. Canonical totals999/433TSS. Existing public preview has8/4undated
weekly arrays and no before-period/comparability projection. Pure capture and
calculation leave every table unchanged; network0. One temporary confirm is
fixture setup, not part of pure calculation or a live write.

The field-presence contract probe is a real initial RED, not a failed synthetic
identity comparison: `probe.py --require-comparison` exits1 with:

    AssertionError: frozen before/after comparison missing from new edit response

Normal characterization exits0. It is not a GREEN implementation of CMP01…14;
all detailed comparison BDD still require tests in C2. Dates, totals and ceilings
are generous synthetic fixtures, not advice or efficacy/safety evidence.

Commands, repository root with primary Python venv and PYTHONPATH=.:

    python docs/reports/2026-10-23-planning-comparison-m1/probe.py
    python docs/reports/2026-10-23-planning-comparison-m1/probe.py --require-comparison
    python -m pytest tests/smoke/test_planning_build_confirmation.py tests/smoke/test_planning_build_confirmation_storage.py tests/smoke/test_planning_cycle_build_v2.py -q -p no:cacheprovider --tb=short
    python -m ruff check . --no-cache
    git diff --check

Existing compatibility106passed /1existing Starlette/httpx warning16.93s. Ruff
and diff checks pass. Production api/models/services/data/web/contracts are
unchanged in C1. Web lint/build not rerun for a spec/report-only delta; latest
runtime3f75915 already passed them and CI39991604878. No local whole-suite rerun
claimed for documentation. New changes get standard current-head CI on push.

Spec decisions: raw selected checkpoint rather than rebuilding old assignments;
final candidate rather than pre-M4 proposal; paired scoped totals without scalar
cross-period percentages; date/content comparison without moved-session lineage;
partial/missing evidence not rest/zero; existing frozen receipt/reset ownership.
Full schedule larger than the explicit366per-side bound is unavailable, not silently
truncated. Source inspection, typed-contract validation, chronology/identity-only
and metadata-only versus actual-prescription mutation cases are required in C2.

Independent C1 round1/2 atdee2422: BLOCK, one P2 in CMP12 incorrectly requiring
checkpoint history retention after full reset. Supervisor independently read
data/database.py5751: explicit full reset deletes planning_checkpoints. Existing
106-case contour includes the reset regression; no live reset was run. Corrected
spec preserves that deletion and separates it from read-only/normal publication
history retention. Accepted suggestions clarify rest↔outside and bound elapsed
calendar span before expansion (366per side, at most732union dates). These are
spec corrections only, not changed runtime. Scoped delta check pending. Author result is not READY implementation or
completed owner acceptance. Original candidate-only M1 spec and UI captures
remain historical; the original fallback is superseded only for this approved
new comparison. Native1/2 at9d41e2b stays historical; do not request round2 for
this spec checkpoint. No merge/review acceptance/provider writes.
