# S4 M1: current-response characterization

2026-10-22 Europe/Moscow, #714 / parent#677. Baseline main00de158.
[Spec](../../planning_confirmation_s4_spec.md), [ExecPlan](../../planning_confirmation_s4_execplan.md).
Synthetic only; pinned athlete day2026-10-16, start2026-10-26. Explicit generous
8hour per-sport test ceilings are fixtures, never a suggested athlete baseline.
Question fixed before execution: which decision facts are available and does a
delta between different horizons describe a comparable weekly reduction? Budget:
two supported builds, new8weeks then genuine current edit4weeks, no model tuning.

Run from repository root with its venv; create the parent temp paths first:

    mkdir -p /private/tmp/ai-trainer-s4-m1/chats
    DATABASE_PATH=/private/tmp/ai-trainer-s4-m1/default.db DEMO_DATABASE_PATH=/private/tmp/ai-trainer-s4-m1/demo.db CHATS_DIR=/private/tmp/ai-trainer-s4-m1/chats PYTHONPATH=. python docs/reports/2026-10-22-planning-confirmation-s4-m1/probe.py

[Probe](probe.py) and [recorded result](result.json). No runtime/API/UI source edit.
Both actual public v2 responses pass schema validation/readiness/entry support.
Pure capture/calculation leave every SQLite table unchanged; each prepare changes
only planning_build_previews. The only confirm is deliberate temporary fixture
setup before edit. socket connect/create_connection deny network; observed calls0.
No athlete cache, provider or private screenshot is read/written.

New8weeks2026-10-26..12-20:total999TSS,peak174,target420. Edit4weeks..11-22:
total433,peak125,target420; before/after arrays8/4, delta−566. Preview has no dated
old period/comparability field. Both intent=develop forecasts return the same
legacy maintenance message; finalTSB1.2, points have dates. Those are technical
synthetic observations, not workload advice, an injury/efficacy claim or an
unaided UX test. No dated before/after comparison can be silently manufactured.

Initial diagnostic attempt failed an overbroad whole-payload equality assertion:
separate start_new captures allocate different cycle IDs/readiness fingerprints.
This was a **probe-oracle error**, not product RED. Corrected comparison covers
semantic totals, lifecycle dates and forecast.points; it does not claim byte
identity. Corrected run exit0; future UI BDD/RED/owner acceptance NOT YET.
Focused compatibility, independent verdict and final check results follow below.

Author checks: focused existing entry-integration + frozen-confirmation compatibility
**56 passed /1 existing Starlette/httpx warning in8.51s**. Probe exit0, Ruff and
whitespace checks pass. This is a targeted compatibility baseline, not execution
of new S4 BDD, a full-suite measurement, native acceptance or human usability.
Independent committed-candidate spec review follows; no UI lint/build required
for this specification-only delta.
