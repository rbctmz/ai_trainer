# S4 comparison C2: server-owned frozen projection

23October2026, #714 / draft#715. Domain/API handoff after independent C1 READY
at93a37ec; C1 local spec budget2/2 complete, P2 reset wording fixed-in93a37ec.
[Approved contract](../../planning_confirmation_s4_comparison_spec.md).
This evidence describes backend/contract implementation, not before/after UI or
complete M3/human acceptance. Native ledger remains1/2, historical9d41e2b.

models/planning_build_comparison.py projects only raw captured selected checkpoint
and final serialized candidate. It validates dated scope, saved parameters,
canonical whole-load sums and weekly coverage, projects executable sessions/
steps/legs, compares same-date public prescription content, and preserves
unknown/rest/outside distinctions. IDs and engine metadata alone do not change
assignments. Per-side366rows/templates/span bounds apply before expansion;
disjoint union is bounded by732dates. No restore, provider, DB call, new table,
numerical dose/ramp/model policy or activity reconciliation is added.

New API models in planning_build_contract.py and mirrored web/lib/types.ts add
optional comparison. New v2 prepare calculates it after final M4 prescriptions
and before final readiness binding. It is retained in the original response,
so confirm/replay/historical receipt keep the same facts and identity. Old
responses missing the optional field remain readable, without a new save gate.
TypeScript only gains types in C2; UI/layout unchanged. Contract artifact refreshed.

## RED / failures / checks

Initial real-response C1 RED: require-comparison exits1, field absent. C2 domain
suite first fails collection because the required shared module does not exist
(1error0.07s); first implementation10passed0.04s, then14passed0.04s.

The first integrated probe failed existing require_prepared_readiness: response
fingerprinting includes the new field, so adding comparison after assessment
invalidates the binding. This is an integration-order error, not a reason to
weaken the guard. Moved projection before final assessment, after prescriptions
and entry repairs; guard unchanged. Initial real-response RED then passes.

First compatibility contour:119passed/1failed18.36s. The added baseline-identity
check incorrectly refused explicit replacement of an indeterminate, unreadable
old checkpoint, a supported S2 path. Projection now emits partial before-facts
when selected history is unreadable; it does not pretend no prior cycle or
introduce a new publication gate. A supplied wrong checkpoint identity still
fails stale. Named regression and new pure test cover both cases.

Next focused domain/confirmation/storage/cycle/contract contour:
**150passed /1existing Starlette/httpx warning20.79s**. After final old-event/
nonfinite-number handling: **21comparison tests passed1.57s**, including real
v2 prepare/confirm/replay/historical receipts and optional legacy response.
Latest TypeScript source passed web lint/production build and contract freshness;
repository Ruff and diff checks pass. Whole contributor-safe suite is running at
this checkpoint, not claimed green. No new browser/UI or native pass claimed.

Commands from this worktree with primary venv on PATH, PYTHONPATH=.:

    python -m pytest tests/smoke/test_planning_build_comparison.py -q -p no:cacheprovider --tb=short
    python docs/reports/2026-10-23-planning-comparison-m1/probe.py --require-comparison
    python -m pytest tests/smoke/test_planning_build_comparison.py tests/smoke/test_planning_build_confirmation.py tests/smoke/test_planning_build_confirmation_storage.py tests/smoke/test_planning_cycle_build_v2.py tests/smoke/test_contract_extractor.py tests/smoke/test_api_call_inventory.py -q -p no:cacheprovider --tb=short
    npm --prefix web run lint
    npm --prefix web run build
    npm --prefix web run contract:extract -- --check
    python -m ruff check . --no-cache
    python -m pytest -m "not live and not debug and not e2e" tests/ -q -p no:cacheprovider --tb=short

Status: author backend checkpoint. Independent C2 review and broad-suite result
pending; C3 UI handoff not yet issued. Do not mark the user-facing comparison
complete from API output or a green test. New ownership/reset/rollback storage is
N/A; existing publication/storage/cycle regression retains reset/replay gates.
Synthetic only, no athlete cache/provider read/write or live confirmation.

## Independent C2 round1 and scoped correction

Independent checker on5e29792 ran21comparison tests (21passed1.62s) and found
one blocking P2: empty steps or[{}] were treated as known complete content.
Supervisor independently reproduced both (complete/changed), then added four
structural RED cases (4failed/22passed1.69s). The narrow correction requires
nonempty finite step duration and a present nonempty target, without scientific
dose/eligibility classification. Incomplete raw assignments now become unknown
and comparison partial. A reordered-template regression proves date join rather
than index pairing; it is not a new template-order rejection policy.

Whole contributor run at5e29792:3985passed/16skipped/101deselected/7warnings,
1failed273.77s. Failure was run_web preflight subprocess missing bare python
because the venv was not on PATH. Same failure reproduced in the narrow run
(28passed/1failed2.91s), without changing run_web.sh. Adding the primary venv
bin to PATH made all26comparison+3preflight tests pass (29passed1.67s). This
confirms an author-command environment error, not a product port regression or
a randomly green rerun. New full correct-environment suite is pending. Native
review remains1/2; C2 scoped delta verification pending.
