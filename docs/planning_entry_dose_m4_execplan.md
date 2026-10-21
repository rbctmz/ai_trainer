# Planning M4: initial dose from sport-specific recorded exposure

This living ExecPlan follows `.agent/PLANS.md` and implements the bounded
[issue#710](https://github.com/rbctmz/ai_trainer/issues/710), parent#677.
Date2026-10-21, Europe/Moscow. Current role: Supervisor / Integrator after the
explicit reviewed Domain/API and UI/Design handoffs. Class A. No acceptance
criteria, domain policy or API contract is changed by this integration record.
[Instantiated spec/review record](planning_entry_dose_m4_slice_spec.md),
[scientific/evidence report](reports/2026-10-21-planning-entry-dose-m4/README.md).
Runtime baseline main `9d679b3410cc7b34c9a3a554b050edaebf8ccd23` includes S3 M1–M3.
The M4a branch is based on `99a6a1f84f9e9f4d51a22796ab819238c516e3c2`,
which also contains the merged S1–S3 post-merge records (#704/#692).

## Purpose / Big Picture

A run-only recent history should not silently authorize the same initial bike
and swim dose as recent practice in all three sports. Users should see which
starting limits follow recorded exposure and which they supplied explicitly.
The new build must fit those limits or say which starting information/feasible
assignment is missing. Executable steps and coherent TSS are necessary; they do
not prove a personally safe or effective dose. M4a makes that boundary reviewable;
M4b/c implement it and M4d hands the typed result to S4.

## Progress

- [x] (2026-10-21) Read architecture/workflow, S3 handoff and frozen-capture boundaries; create#710 before M4 tracked edits.
- [x] (2026-10-21) Cheap synthetic paired falsifier: run4 versus run1/bike2/swim1 at equal dates/time/TSS gives the same daily allocation and initial sport dose; both technical ready. No athlete DB/provider write.
- [x] (2026-10-21) Review primary scientific sources; freeze factual/proposed/unknown distinctions and reference rules in the separate spec.
- [x] (2026-10-21) Strict spec contour: 1 passed / 4 XFAIL; --runxfail: 4 intended assertion failures / 1 passed. Compatibility contour: 134 passed / 4 XFAIL / 1 warning in 24.44s. Probe and Ruff passed; no runtime change.
- [x] (2026-10-21) Candidate `fb06cb803a17891624f47254c0a6b2edef60a9ee` committed/pushed in draft #711; independent full spec review READY, no blocking findings. Reviewer reproduced 1 passed / 4 strict XFAIL and 4 intended RED failures / 1 passed, Ruff green. Documentation-only record follows; no acceptance of runtime or merge.
- [x] (2026-10-21) M4b implementation: pure per-sport exposure/reference profile, validated coverage/declared limits, frozen parameters + policy digest, additive API/TS models and registry/extractor. 83 focused M4b tests pass after two reproduced lineage/date corrections; exact implementation `176b77e` independently reviewed READY. Final contributor-safe 3921 passed / 16 skipped / 82 deselected / 4 expected XFAIL / 7 warnings (238.78s).
- [x] (2026-10-21) M4b independent delta review 1/2 READY on `176b77e`, no blocking P1/P2; checker 83 new + 145 compatibility passed, Ruff green. Author final broad/lint/build/contracts green; current documentation-only record preserves the runtime checkpoint. M4c handoff below; native 0/2 remains M4d.
- [x] (2026-10-21) Domain/API M4c complete at reviewed runtime3a28f99:3965 contributor-safe passed, independent scoped round2 READY/176passed; AC6 demand-writer P2 fixed-in3a28f99. Three explicit Coach browser approval fixtures pass. UI form gap is reproduced/tracked; whole M4/M4d/native/merge remain open.
- [x] (2026-10-21) UI consumer handoff complete at f0650b5: explicit coverage/limits, typed refusal/provenance/adjustments, token-only confirmation. Independent UI round1 READY,5 real E2E passed; author41 focused then63 whole E2E passed. No browser dose derivation or API/AC change.
- [x] (2026-10-21) M4d local acceptance on f0650b5:3965 passed/16 skipped/87 deselected/7 warnings in277.59s; Ruff, web lint/build, contract freshness/inventory green. Six isolated UI screenshots retained.
- [x] (2026-10-21) Remote CI39669348958 SUCCESS on4e9efe9:3942 contributor passed/39skip/87deselected,63E2E and24contract passed. Prior CI one keyboard-test failure investigated; test-only6895cc0 synchronizes expected step focus and asserts checkbox activation, author5passed. Cause remains inferred; full account in UI evidence.
- [ ] M4d final test-correction CI and native review (0/2 before request); owner acceptance and merge are separate. Exact native receipt/CI result will be recorded on #711 without a documentation push after review.

## Surprises & Discoveries

Historical observation at M4c (resolved by the UI handoff below): the real new-cycle browser journey returns422 entry_dose_required
because the form does not transmit coverage/dose. Verified by the existing
isolated lifecycle E2E (1 failed,7.71s), without API mocking. This is an explicit
UI/Design consumer handoff, not a reason to bypass the backend guard. That consumer work was explicitly handed to UI/Design and is now reviewed at
f0650b5; native/owner acceptance remains separate. No UI scope was transferred
to Domain/API. Details and typed inputs are in the M4c report.


Observed: adding the entry policy stamp changed six existing full-payload golden
checks. Inferred: the only observable delta may be the M3 readiness binding,
which intentionally includes the frozen context. Verified by: six executed
paired complete-payload calculations with/without only that stamp; after removing
candidate_fingerprint both checkpoint/response objects are equal. All five
prescription/daily/event/forecast/science component hashes remain unchanged in
six historical cases; the three first-plan old-context whole hashes reproduce
the historical oracle. The old fixture is retained; entry-capture-v1 is separate.

Observed: the first physical-lineage projection treated future/today stages as
proof of a complete past multisport event. Inferred: date eligibility must also
bind group completeness, not only the final row sum. Verified by: two new
assertion REDs (today and future linked swim stage), then GREEN when completeness
requires completed context-day legs. Known actual legs remain visible; no global
CTL authority logic was changed.


Observed: current capture freezes90days and uses aggregate CTL plus a weekly
TSS target/mix; source sport labels affect evidence identity but not the initial
sport dose in the paired fixture. Inferred: a separate sport exposure/entry
constraint boundary is missing; technical readiness is intentionally not a
suitability assessment. Verified by: pure _calculate_plan_build paired probe,
same daily plan and first-week dose, four-run history still technically ready.
Raw template equality is false because cycle namespaces differ; it is not proof
of a dose difference or a regression in identity. No causal injury claim is made.

Observed: the global authoritative multisport view drops stages for partial
groups and keeps the envelope. Inferred: blindly reusing that view would hide
known per-sport exposure; blindly summing every row would double count. Verified
by: models/activity_lineage.py source, current deterministic group boundary;
full M4 partial/zero-TSS/ambiguous lineage tests are NOT YET executed.

Observed: recent_weekly_tss_summary groups observed weeks and target math can
retain a goal floor. Inferred: neither is an adequate initial sport-duration
reference. Verified by: source and paired output with target420 while last4
weekly observations are55TSS; a new reference must use explicit covered bins,
without changing the historical summary's meaning in place.

## Decision Log

M4b implementation note (2026-10-21, Domain/API): resolved reference limits stay
unassessed/can_publish=false until final assignment validation in M4c. Build
responses reserve the optional typed entry_load shape but do not populate it;
new declarations are accepted, validated, retained and echoed without claiming
that generation already enforces them. No XFAIL is removed from M4a's final-build
RED. This stages the agreed contract without a premature supported badge.

M4b implementation note: a supplied ceiling binds even with a usable recorded
reference; take the smaller value per unit and retain declared_ceiling provenance.
For absent/unusable history, use explicit declared limits with source_window=null.
This consumes AC2/AC3 (observed envelope and supplied limits remain distinct),
not a new capability conversion or an efficacy/safety guarantee. Catalog/time
feasibility and rolling-window assignment checks remain M4c.


Decision: keep training_suitability=not_assessed; expose a separate entry_load
historical/intention check. Rationale: the reviewed sources do not establish
safe individual minutes/TSS or a universal injury-preventing ramp. Date/author:
2026-10-21 / Spec Owner.

Decision:28 complete local days plus84-day context, four7-day bins,14-day entry
scope; same-sport observed median reference with explicit coverage, positive
recent-bin evidence and valid durations, else declared limits. Rationale:
transparent conservative product heuristic with empty/unknown distinction;
these numbers are not physiological thresholds. See exact AC2–AC5 and residual
risks in the spec. No catalog minimum becomes a clinical bootstrap dose.
Date/author:2026-10-21 / Spec Owner, proposed for independent review.

Decision: add typed request/response/profile evidence via existing immutable
preview/checkpoint JSON, no new persistent table. Confirm remains token-only,
applied old replay stays first. Rationale: preserve S1/S2/S3 ownership and
transaction semantics. Date/author:2026-10-21 / Spec Owner.

## Context and Orientation

api/planning_service.py::_capture_plan_build_inputs owns the coherent read
transaction and current90-day activity frame/provider_external_id. The pure
_calculate_plan_build currently derives start load from global CTL, calls
models/planning_targets.py and the shared training planner, then M3 final
readiness. prepare_plan_build checks before store_pending; confirm_plan_build
validates the frozen artifact and CAS under the write transaction. Existing
BuildInputSnapshot dependency components include all captured source fields;
new parameters/lineage and the entry policy version must join that same digest.

models/activity_lineage.py identifies explicit provider-linked envelopes/stages;
utils/product_semantics.py owns sport aliases. Partial per-sport exposure and
authoritative global load deliberately serve different questions. data/database.py
::_get_activities reads no completeness assertion, so sync success cannot be
relabelled complete coverage. api/planning_build_contract.py and
api/planning_cycle_contract.py own typed build contracts; web/lib/types.ts is
the mirror. No UI calculation or legacy Streamlit-only feature is permitted.

## Plan of Work

M4a records sources, explicit proposal and behavioral RED in docs/test fixtures.
The tests use only temporary synthetic DBs and no runtime patches. A strict
AssertionError-only XFAIL is a recorded missing feature, not a passing safety
check; --runxfail must show the intended assertion, not an import/setup error.
Do not relabel the already-green purity control as a new RED.

Explicit role handoff after independent review of `fb06cb8`: Spec / Architecture
Owner hands the AC1–AC7 contract and source evidence to Domain / API Implementer.
The implementer may add the pure profile, typed contracts and subsequent guards
within #710, but must not redefine the numerical policy, add UI, or claim safety.
The same integrator may take that role under this recorded task handoff; human
merge/live-write authority remains unchanged.

At M4b, Domain/API implements a small pure profile in models/planning_entry_load.py
from frozen rows and explicit date/coverage, then typed normalization/versioned
serialization. Work the matrix: empty/unknown/covered zero; valid/invalid duration,
TSS-method gaps; aliases; complete/partial/zero-TSS multisport; duplicates;
window/today/future/timezone boundaries. Add contracts/extractor fixtures before
public integration. Do not let the browser derive missing semantics.

M4b to M4c clean handoff: Domain/API continues from implementation
`176b77e1bf48a39a6cf9d37d6f554a7472fc4c6f` and the reviewed AC1–AC7. Required
inputs now exist in models/planning_entry_load.py (pure profile/limits),
api/planning_entry_contract.py (DTO), frozen normalized parameters/context in
api/planning_service.py and the TS mirror/contract artifact. All-table malformed
input and applied replay checks are green; final-builder M4a RED remains explicit.
M4c must consume the captured frame/as-of/timezone and original cycle entry
anchor; capture any additionally needed execution/reconciliation ownership facts
in the same transaction; integrate generation and the final guard together before
emitting supported/can_publish. No UI/math scope or clinical claim is transferred.

At M4c, derive or retain scoped starting limits, allocate within each discipline's
time/frequency/session limits, and run final effective prescription validation.
Missing inputs or impossible catalog/phase intent gives structured refusal,
not arbitrary short workouts or transfer of unused allowance. Freeze entry
scope through edits; include execution partition/lineage dependencies when
counting completed plus future exposure. Tampering, changed history/limits,
old pending, applied replay, restart/reset/backup and injected write failures
must preserve all existing table state on rejection. Existing mutation writers
drop stale entry evidence rather than inheriting a supported badge.

At M4d, execute whole contributor/contract/isolated browser contours with the
new honest success/refusal fixtures, then native review within the normal cap.
UI/Design receives only agreed DTO/states and an explicit S4 handoff. Owner
accepts final head and merge separately; no live athlete write is required.

## Concrete Steps

From repository root activate its environment with dependencies, or supply
PYTHON pointing to an installed interpreter with requirements/dev/web packages:

    PYTHON="${PYTHON:-python}"
    "$PYTHON" --version
    "$PYTHON" -m pytest tests/smoke/test_planning_entry_load_spec.py -q
    "$PYTHON" -m pytest tests/smoke/test_planning_entry_load_spec.py --runxfail -q
    PYTHONPATH=. "$PYTHON" docs/reports/2026-10-21-planning-entry-dose-m4/probe.py
    "$PYTHON" -m ruff check tests/smoke/_planning_entry_dose.py tests/smoke/test_planning_entry_load_spec.py docs/reports/2026-10-21-planning-entry-dose-m4/probe.py
    git diff --check

Use fresh existing temporary parent directories for DATABASE_PATH,
DEMO_DATABASE_PATH and CHATS_DIR if checking broader modules. Never instantiate
a default Database against the athlete cache. A future Domain broad command is
python -m pytest -m "not live and not debug and not e2e" tests/; prepend the venv
to PATH for subprocess tests. New API/TS changes require contract:extract,
contract --check/inventory, web lint/build and relevant isolated E2E.

## Validation and Acceptance

Current M4a expected normal contour: one purity control passes, four strict
XFAIL. --runxfail: four assertion failures, no setup/import errors. Probe records
same first-week sport allocation for different recent sports, no entry profile,
pending prepare and unchanged active state. Executed measurements are recorded in the report: 1 passed / 4 XFAIL,
then 4 intended assertion failures / 1 passed under --runxfail; compatibility
134 passed / 4 XFAIL. These are not M4 runtime GREEN or a broad test claim.

Future gate is AC1–AC7 in the separate spec, including true usable-history and
declared-limit successes, absent/partial/refused cases, all-table no-write,
namespace/clock/lineage compatibility and profile/forecast final-load agreement.
No hidden thresholds/cross-sport conversion, no injury-risk/medical claim and
no historical rewrite. Parameter sensitivity/template feasibility experiments
can falsify technical adequacy; they cannot validate a medically safe dose.

## Idempotence and Recovery

All M4a experiments use temporary SQLite and deterministic pinned dates. Discard
unconfirmed candidates; reset owns existing retained previews/evidence. No new
persistent owner/table/cursor or retrospective recomputation. Repeating the same
frozen input yields the same profile/limits, apart from existing cycle identities;
publication replay uses the existing immutable receipt. On malformed inputs
fail explicitly, without reading/writing live providers or rebuilding under lock.

## Artifacts and Notes

The report contains only synthetic aggregate observations and scientific source
links, no private athlete rows or logs. Raw template equality is not used as a
dose oracle because different cycles carry different IDs. Old S3 test counts
are labelled baselines, not new M4 results. Independent checker receives the
exact committed ref, complete diff and only approved check commands.

## Interfaces and Dependencies

Future pure interface: build_entry_exposure_profile(rows, *, as_of, timezone,
coverage) -> EntryExposureProfile; derive_entry_limits(profile, declared_limits,
*, cycle_scope) -> EntryLoadAssessment; assess_entry_assignments(plan, assessment,
execution_partition) -> EntryLoadAssessment. Use plain typed records/Pydantic
only at the API boundary; do not create a parallel planner/cache/service stack.
Serialize finite canonical JSON, preserve provenance/units and existing selected
cycle/revision CAS. Exact shapes and error compatibility are in the spec; no
production signature is introduced by this M4a document.

## Outcomes & Retrospective

M4a specification/source review is complete. M4b pure evidence, input capture
and typed shapes are implemented; final independent/broad evidence is recorded
in the [M4b report](reports/2026-10-21-planning-entry-load-m4b/README.md).
M4b is complete for its bounded handoff: independent 83 + 145 compatibility
checks and author final 3921-test contributor contour are green; four final-build
RED are now GREEN in M4c. Runtime3a28f99 generation/publication is independently
READY for bounded backend handoff with3965 local contributor passes. The UI
consumer is now independently READY on f0650b5, and all63 isolated E2E pass.
Whole M4d local contributor verification is3965 passed/16 skipped/87 deselected;
the five new UI cases explain the deselection increase from82. Remote final-head
CI/native/owner acceptance remains open; no human usability or merge is claimed. Clinical validation is not
claimed. The first paired falsifier was an evidence-discipline check, not a
preregistered model-selection experiment. Further numerical experimentation must
freeze cases/baselines/budget/exit rules before execution, as described in the
report. A usable template fit does not promote a dose to scientifically safe.

M4c implementation/evidence and UI handoff: [report](reports/2026-10-21-planning-entry-load-m4c/README.md). No acceptance criteria or numerical thresholds changed.


UI/Design → Supervisor/Integrator handoff (2026-10-21): source
46e17f4..f0650b5 independently READY, zero blocking P1/P2. Scope is the existing
DTO consumer, input/response presentation and isolated browser fixtures only.
The integrator now records whole-delivery evidence and requests native review
on the stable final head. One nonblocking accessibility announcement suggestion
is retained as follow-up #710; no screen-reader failure was demonstrated.
[UI acceptance/evidence](design/evidence/issue-710/README.md).
