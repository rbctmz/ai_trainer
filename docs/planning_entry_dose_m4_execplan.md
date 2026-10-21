# Planning M4: initial dose from sport-specific recorded exposure

This living ExecPlan follows `.agent/PLANS.md` and implements the bounded
[issue#710](https://github.com/rbctmz/ai_trainer/issues/710), parent#677.
Date2026-10-21, Europe/Moscow. Current role: Spec / Architecture Owner for M4a;
Domain/API and UI/Design handoffs are explicit below. Class A.
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
- [ ] Domain/API M4b: frozen profile/limits/lineage, typed contracts and profile boundary matrix.
- [ ] Domain/API M4c: constrained generation and shared atomic publication/replay compatibility.
- [ ] M4d: whole-delivery verification/native/owner gate; UI/Design S4 handoff.

## Surprises & Discoveries

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

M4a proposal/source review and first cheap paired falsifier are prepared; runtime
implementation, numerical-policy clinical validation and final acceptance are
NOT YET. The first paired falsifier was an evidence-discipline check, not a
preregistered model-selection experiment. Further numerical experimentation must
freeze cases/baselines/budget/exit rules before execution, as described in the
report. A usable template fit does not promote a dose to scientifically safe.
