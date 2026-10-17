# Planning S1: publish exactly the confirmed preview (#685)


This is a living ExecPlan maintained under `.agent/PLANS.md`. Issue
[#685](https://github.com/rbctmz/ai_trainer/issues/685) is the first bounded slice
of [#677](https://github.com/rbctmz/ai_trainer/issues/677). The companion
[slice specification](planning_preview_confirm_slice_spec.md) contains the exact
API, storage and acceptance matrix. Status: implementation started. On 2026-10-17
the human owner handed implementation to Domain / API Implementer after the
independent specification check. No active product behavior has changed at M1.

## Purpose / Big Picture


An athlete who reviews a plan and presses «Подтвердить и сохранить» must save
that plan. Today the server calculates it again, so a background activity sync
can change the result without the athlete seeing it. After S1, the server stores
the prepared result, checks that its inputs are still current, and publishes
that result once. Changed inputs require another preview. A repeated click or a
retry after a lost response returns the original result without another plan.

The observable demonstration uses a temporary synthetic database: preview a
plan, add an activity, confirm the old preview, and see a conflict with zero plan
or profile writes. Preview again and confirm twice; both successful responses
identify the same single saved checkpoint. A checkpoint is the existing
append-only saved plan version. S1 does not fix expired-cycle labels, inherited
dates/events, training mathematics, or the whole confirmation-screen design.

## Progress


- [x] (2026-10-16) Verify issue #685, baseline main `f0f80d335e7f3973a80241a5127d88ba7eca52dc`, public build callers and repository workflow.
- [x] (2026-10-16) Reproduce drift on temporary SQLite and probe SQLite writer exclusion; no athlete database access.
- [x] (2026-10-16) Draft ExecPlan, precise slice contract and acceptance matrix on `codex/issue-685-preview-confirm-spec`.
- [x] (2026-10-17) Independent spec round 1 completed; one blocking P2 identified in uncertain-state token ownership.
- [x] (2026-10-17) Scoped spec round 2 verified the correction; READY for specification handoff, 2/2 rounds used.
- [x] (2026-10-17) M1: 20 expected HTTP RED cases (4 reach unsafe writes; 16 preliminary protocol cases); 12 unchanged-build checks plus existing 66 tests pass, 78 total. Ruff passes.
- [x] (2026-10-17) Independent M1 checker reviewed e0cd700..097cf99: no blocking P1/P2, 12 characterization cases independently pass. M1 draft handoff only; acceptance RED remains.
- [x] (2026-10-17) M2 implementation: coherent connection-bound read snapshot, immutable serialized inputs/result, prepare-time freshness recheck and additive preview store. After review fixes, 75 M2/characterization tests pass; initial existing focused pass: 108 tests.
- [x] (2026-10-17) M2 verification: 3236 contributor-safe tests passed (14 skipped, 46 deselected; only the known M1 HTTP RED file excluded). Independent scoped round 2 accepted `6516989`, zero open blocking findings. Ready for bounded draft handoff only.
- [x] (2026-10-17) M3 implementation: frozen publication, same-connection freshness/receipt/settings transaction, replay, strict HTTP protocol and typed API/TS responses. Original 20 HTTP RED cases are GREEN.
- [x] (2026-10-17) M3 independent review: full round at `0fc01c4` and test-only delta at `77b51b2`, no blocking P1/P2; independent runs 177 passed and 62 passed.
- [x] (2026-10-17) M3 final verification: 3346 passed, 14 skipped, 46 deselected in 227.62s; no file exclusions. Ruff, whitespace, web lint/build, contract freshness/conformance/inventory and ExecPlan structure/links pass. Draft publication follows; M4 callers remain unchanged.
- [ ] M4: minimal Planning UI and Coach build-proposal adapters; contract refresh.
- [ ] M5: isolated browser acceptance, required checks, implementation review and human merge gate.

## Surprises & Discoveries


**Observed:** the M3 pre-change run reproduced all 20 M1 HTTP failures in 4.70s,
including unsafe raw writes. A separate 35-case transaction/replay suite failed
on the absent `confirm_plan_build` interface. **Inferred:** preparation storage
alone cannot satisfy confirmation; the cheapest falsifying check is the same
HTTP and transaction matrix after wiring the retained artifact.
**Verified by:** initial M3 run passed 118 tests in 28.45s, including every original
M1 HTTP case, all six full-checkpoint mode/base comparisons, write rollback,
real-connection duplicate/competing confirmation and SQLite writer exclusion.
Final broader evidence and independent review are pending below.

**Observed:** the contract inventory previously treated every registered endpoint
as a GET, while M3 adds two POST response contracts. **Inferred:** listing the new
POSTs without method semantics falsely reports dead GETs. **Verified by:** the
registry now declares POST explicitly; conformance exercises real prepare/confirm
on separate temporary fixtures, and the unchanged GET coverage obligation filters
only GET entries. 50 inventory/conformance checks passed in 5.29s. No UI adapter
or visual change is included; old Planning raw-save receives the reviewed 409
until M4 switches it to identity confirmation.


**Observed:** M2 review found a hidden live-day read through the unused readiness
branch of `assemble_signals`, and capture conflated a missing setting row with
an existing SQL NULL row. **Inferred:** these violate the named pure-calculation
and exact raw-setting dependency invariants; no plan-output drift was inferred
from either observation. **Verified by:** three exact regression cases first
failed (one transitive clock guard, both absent/NULL directions). The core now
uses the existing canonical `training_load_metrics` helper directly with the
captured day, and source settings preserve row presence. All 75 focused M2 and
unchanged-calculation checks pass (15.71s), with no oracle regeneration. Scoped
independent round 2 accepted both fixes at `6516989` and independently passed
75 tests in 29.07s. The final broad rerun passed 3236 tests (14 skipped,
46 deselected) in 232.04s, excluding only the known M1 HTTP RED file.

**Observed:** extracting the builder into `_calculate_plan_build(snapshot)` and
serializing its complete result preserves all six M1 full-checkpoint/response
oracles, including nested prescriptions and forecast. **Inferred:** the M2
refactor can share one calculation core without changing training mathematics.
**Verified by:** 73 M2/storage/characterization tests passed in 17.50s; 108
focused existing planning/calendar/metrics/Coach/backup tests passed in 11.78s.
Final broader compatibility and independent M2 review are recorded above. Public HTTP build
confirmation is deliberately unchanged until M3: its 20 known M1 RED cases still
fail (5.07s), so M2 is not an S1 fix or a deployable checkpoint.

**Observed:** a real second SQLite connection commits an activity/profile update
while the capture transaction is open. The captured activity count and FTP both
remain old; a new capture sees both new values. **Inferred:** the explicit read
transaction prevents mixed inputs across helpers. **Verified by:**
`test_read_snapshot_cannot_mix_a_concurrent_sync`, plus trace checks proving one
read connection and one `BEGIN IMMEDIATE` recheck/store connection for prepare.
Race tests reject activity/base/day/rule changes before retaining any token.

**Observed:** M1's pinned HTTP regression reaches the existing handler and returns
200 after a synthetic activity is added: preview 1531 TSS, saved 1759 TSS, one
unexpected checkpoint for both first/existing-plan cases. An unbound raw retry
returns 200 twice and appends two checkpoints. **Inferred:** base-only checking
does not establish input freshness, and omitting the optional base permits
duplicate raw application. **Verified by:**
`test_planning_build_confirmation.py`, 2026-10-17: four behavior REDs; four more
cases fail for missing preview identity and twelve for the missing confirm route.
Those sixteen are preliminary protocol RED, not stale/replay implementation proof.
No xfail/skip or production fallback is introduced. Fixture values differ from
the earlier probe because inputs are now pinned and include events/zones/rest
constraints; they are not training-model golden totals.

**Observed:** `PlanBuilder.confirmPlan` repeats the build parameters, and
`api/routers/planning.py::planning_build` calls `build_plan` again. The latter
reads activities and profile before writing the checkpoint. **Inferred:** a new
activity can change the saved prescription while the base checkpoint remains
unchanged. The cheapest falsifier is to insert only one synthetic activity
between the calls. **Verified by:** the issue's temporary-database router probe
was rerun on the baseline: preview 1914 TSS, confirmation 2205 TSS,
`same_weeks=False`. These are fixture values, not golden expected loads or
athlete data. The actual new HTTP protocol remains **NOT YET** implemented.

**Observed:** `models/ai_tools.py::propose_plan_build` prepares a plan; approval
in `api/routers/decisions.py::_apply_proposal` invokes `build_plan(persist=True)`.
The generic approval path claims a proposal before applying it. **Inferred:**
fixing only the Planning route would leave the same build-confirmation gap in
Coach. **Verified by:** caller inspection and the 66-test baseline below;
end-to-end Coach drift/replay verification is **NOT YET**. Scope includes only
the existing Coach `build_plan` action, not a general proposal-engine migration.

**Observed:** `data/database.py` helpers open separate SQLite connections;
`commit_coach_plan_mutation` already uses `BEGIN IMMEDIATE` to check and write on
one connection. **Inferred:** the same SQLite transaction boundary can exclude
concurrent writers while S1 checks input freshness and publishes. **Verified
by:** two connections to temporary SQLite, the first holding `BEGIN IMMEDIATE`,
the second attempting a setting insert with a 1 ms test timeout, returned
`database is locked`. The full new confirmation transaction is **NOT YET**
implemented; the probe establishes writer exclusion only.

**Observed:** demand can be written before checkpoint construction completes;
forecast is calculated after checkpoint persistence. The UI separately saves
`planning_profile` from current form state after confirmation. **Inferred:**
these writes/computations cannot form the required all-or-nothing result.
**Verified by:** inspection of `build_plan`, `PlanBuilder.confirmPlan`, and
`services/planning_profile.py`; injected failure tests are **NOT YET**.

## Decision Log


Decision (2026-10-16, Spec Owner): use one server-owned, persistent prepared
artifact, addressed by a random UUID. It contains the full serialized checkpoint
and response, not merely weekly totals. Confirmation never runs the planner,
materializer, forecast or science audit again. This is simpler to prove than
rebuilding and comparing a changing collection of fields.

Decision (2026-10-16, Spec Owner): capture inputs with one read transaction,
calculate outside the writer lock, then recheck inputs in a short write
transaction before storing the preview. Confirmation checks and publishes in
another single write transaction. This avoids holding the SQLite writer lock
through the scheduler while preventing a check/write race. Input fingerprints
are deterministic hashes of the named dependencies, not timestamps alone.

Decision (2026-10-16, Spec Owner): include whole relevant activity/profile rows
and the exact active-constraint read result in the fingerprint. This deliberately
permits conservative invalidation when an included row's descriptive field
changes. Unrelated settings, HRV and sleep do not invalidate this builder. No
database-wide revision counter, triggers, event sourcing or general workflow
engine is introduced.

Decision (2026-10-16, Spec Owner): persist Planning UI profile and demand with
the checkpoint and receipt in the same transaction. Coach build confirmation
does not update the Planning onboarding profile, preserving its current scope.
The existing standalone onboarding save endpoint remains available.

Decision (2026-10-16, Spec Owner): reject legacy raw public build confirmations
with `409 preview_required`. Migrate both current public build-confirmation
callers, Planning UI and Coach build proposals, together. Trusted demo seeding,
demand changes and other action types retain their separate existing contracts.
No request parameter grants the trusted internal role.

Decision (2026-10-16, Spec Owner): pending previews expire after 30 minutes or
become stale on a relevant day/timezone/rules change. Successful receipts survive
expiry and restart for the lifetime of their checkpoint. Replaying an old receipt
does not make that historical checkpoint current. This trades a small local
storage cost for reliable retry after a lost response.

## Outcomes & Retrospective


M3 publishes the retained checkpoint bytes with the prepared demand/profile
writes and a receipt in one SQLite transaction. It rejects stale/expired/unknown
artifacts and the former raw HTTP save. Applied retries validate the receipt and
checkpoint, then return the frozen response without recapture or reactivation.
Same-preview concurrency yields first apply plus replay; competing previews share
one winner. Synthetic trigger faults cover checkpoint, demand, profile, receipt
and pre-commit failures for both initial INSERTs and later UPDATEs. A simulated
lost commit response resolves through the durable receipt, including Backup API
restore. None of these checks uses the athlete database or a provider.

The initial full contributor-safe run at `0fc01c4` passed 3338 cases and exposed
two old integration requests still using raw-save. Those tests were adapted to
preview identity at `77b51b2`, preserving all original Planning/Today visibility
assertions; their two-case rerun passed in 2.01s. Six additional first-insert
rollback cases passed with the full transaction file (60 passed in 12.11s).
Independent M3 round 1 accepted `0fc01c4` (177 passed in 28.05s); scoped round 2
accepted the test-only delta `77b51b2` (62 passed in 12.39s), no open blocking
findings. Final contributor-safe evidence will be recorded below. M4 UI and Coach
binding remain unimplemented; current browser raw-save receives the deliberate
409. This is backend draft readiness, not deployment or whole-S1 acceptance.

The baseline defect and transaction primitive have been checked. M1 now supplies
executable failing HTTP acceptance plus a pinned full-payload calculation oracle.
The 78 passing tests are 12 characterization checks plus 66 existing tests, not
GREEN evidence for S1. The complete checkpoint JSON and public response are hashed
with component digests for diagnosis, using six synthetic first/existing scenarios
over three modes; only assigned response plan ID and external row metadata are
excluded. Fixture hashes were generated from unchanged production code at the
recorded baseline and are not regenerated automatically.
Independent spec review completed on 2026-10-17: one P2 corrected and verified,
READY for specification handoff. M2 now provides internal `prepare_plan_build`,
not a new HTTP endpoint: it captures all dependencies, calculates outside the
writer lock, rechecks the same inputs under `BEGIN IMMEDIATE`, and retains only
the frozen checkpoint/response/settings intention and dependency hashes. Existing
trusted `build_plan` shares the pure core. Pending expiry/cleanup, reset, reopen,
integrity failure and Backup API restore are tested; applied receipt fixtures
exercise retention shape only, not future M3 replay. UI work starts only with
the tested public API contract in later milestones. M2 is ready for draft handoff
at `6516989`, after two review rounds and no unresolved blocking findings. The
final broad run explicitly excludes the 20 separately confirmed M1 HTTP REDs;
the branch remains unsuitable for deployment/merge as a completed S1 fix.

## Context and Orientation


The product uses FastAPI in `api/` and Next.js in `web/`, with shared Python
planning logic. Streamlit remains a supported fallback, not the target of this
slice. `api/planning_service.py::build_plan` resolves parameters, reads activities
and athlete zones, calculates weeks and daily sessions, applies event overlays
and Coach constraints, creates session identities, and optionally saves through
`data/database.py`. `models/planning_checkpoints.py::build_planning_checkpoint`
serializes the full plan, including prescriptions and provenance. Provenance
means the source version/rules and parent checkpoint that explain the result.

`web/components/planning/PlanBuilder.tsx` currently posts the same raw request
twice to `/api/planning/build`, first for preview then for saving. Its separate
profile PUT can use form values different from the preview. `web/lib/types.ts`
defines `BuiltPlan`; `web/lib/api.ts` turns error `detail` into an `ApiError`.
The TypeScript contract extractor and `tests/contracts/registry.json` keep API
examples and frontend types in agreement.

The other public path is `models/ai_tools.py::propose_plan_build`, persisted by
`api/routers/coach.py`, then approved by
`api/routers/decisions.py::approve_proposal`. Only its `build_plan` branch moves
to the new protocol. `api/routers/system.py::_seed_demo_plan` is a trusted fixture
builder; demand, repair, recovery and rebalance have separate confirmation rules.
Inventory these callers again before editing, and keep their characterization
tests green. S1 does not claim to retrofit every legacy Streamlit mutation.

Read `.agent/PLANS.md`, `AGENTS.md`, `docs/AI_Feature_Development_Workflow.md`,
`docs/architecture/asr_catalog.md`,
`docs/architecture/architecture_analysis_add3.md`, and
`docs/architecture/adr_0001_web_primary_ui.md`. The essential role rule is that
the Domain implementer consumes this contract; a UI specialist consumes the
resulting API without moving freshness or training calculations into React.

## Plan of Work


### M1 — prove the boundary before changing it


Domain / API Implementer creates
`tests/smoke/test_planning_build_confirmation.py` and
`tests/smoke/test_planning_build_confirmation_storage.py`. Reuse the synthetic
seed helper in `tests/smoke/test_api_planning.py`; freeze athlete time and isolate
SQLite in `tmp_path`. Record the old route's activity-between-preview-and-confirm
failure, then write the expected new-protocol tests: missing identity cannot
write, stale preview cannot write, and two confirmations create one checkpoint.
Use HTTP `TestClient` for request validation/status and service/storage tests for
exact payload and transaction behavior. Missing routes are preliminary RED only;
the eventual GREEN must prove the behavioral assertions, not just route presence.

Characterize unchanged build mathematics for event_goal, training_goal and
manual modes, including events, active constraints, zones, nested/composite
sessions and first/existing checkpoint. Freeze revision time. Compare complete
prepared checkpoint and public response, excluding only persisted database ID
and database creation time. These already-green equivalence checks protect the
refactor; they are not described as new failing behavior. Run the focused command
in Concrete Steps and record each actual RED and baseline result.

### M2 — calculate once and retain the result


Extract a narrowly typed immutable input snapshot and prepared result from
`api/planning_service.py::build_plan`. Put their data types and canonical
dependency hashing in new `models/planning_build_confirmation.py`. Keep existing
domain algorithms in their current modules. Add
`data/planning_build_preview_store.py` for connection-bound storage/read helpers,
registered by `Database` initialization and reset. Do not duplicate SQL semantics:
extract private connection-taking versions of existing activity, profile,
checkpoint and constraint reads as needed; existing public methods delegate and
retain their connection lifecycle. Never store a request connection on the
shared/cached Database instance or monkeypatch `_connect`.

Within one explicit read transaction resolve defaults and collect dependencies
listed in the slice spec. The effective constraint bounds are the same generated
plan date bounds as today, derived by shared calendar-resolution code, not a
second approximation. Capture clocks once. Use the current 90-day activities
query semantics, including its host-date cutoff, for equivalence; include that
cutoff in freshness alongside athlete-local date/timezone. Do not silently fix
the older host/athlete time distinction in this slice.

Compute the full checkpoint, full response, profile projection and integrity
digest with that snapshot and explicit revision time, outside a write
transaction. After all computations/serialization succeed, acquire
`BEGIN IMMEDIATE`, re-read the same dependencies, verify clocks/rules/base, and
insert a pending preview only if unchanged. A race during computation returns
409 and requires another explicit preview. No active plan/settings writes occur
at preparation. The retained artifact is real SQLite state; the UI must say
«План ещё не сохранён», not «SQLite не изменён».

The milestone ends with preview storage, expiration/reset tests and unchanged
build equivalence green. The confirm endpoint can remain unavailable until M3;
do not ship an intermediate deployment where old confirmation bypasses S1.

### M3 — publish and replay atomically


Add `prepare_plan_build` and `confirm_plan_build` in `api/planning_service.py`
with the interfaces below. The confirmation store receives the selected database,
opens one connection and executes `BEGIN IMMEDIATE`. On that same connection it
validates preview ownership/origin, checks a successful receipt first, then for
pending state verifies expiry, integrity, base checkpoint and all dependencies.
It inserts the frozen checkpoint, applies captured demand/profile writes, and
records the applied checkpoint/result before committing. A stale preview can
be marked invalidated; it cannot change the active plan or settings. On exception,
roll back the entire transaction. Separate helper commits are forbidden here.

Return the stored response with the assigned `plan_id` and confirmation metadata.
Only metadata may differ from the preview. An already-applied preview returns its
original result even after new activities, expiry or a later plan; report whether
it is still current without activating it. If its checkpoint is missing, fail
closed instead of regenerating it. Failures after commit are recovered by retry.
SQLite busy is retryable 503 and leaves pending state usable. No planner,
forecast, science audit, network call or provider write runs inside confirmation.

Add the new HTTP route and explicit rejection of the old raw persist request in
`api/routers/planning.py`. Use typed request/response models. Demonstrate two real
connections coordinated by barriers, not sleeps: competing previews, same-preview
duplicates, dependency writer before and during confirmation, and forced failures
after each planned write. Check counts plus complete plan/profile/provenance and
receipt consistency. The checkpoint insertion and all linked state must roll back
together. Run the new storage/service/HTTP matrix before proceeding.

### M4 — connect the existing public callers


Domain implementer adapts the existing Coach build action only.
`propose_plan_build` creates an origin=coach prepared artifact and derives the
card summary from its frozen response. Saving a build proposal binds that
preview to exactly one proposal in the same transaction as proposal persistence.
Approval dispatches this action before the generic pending-only gate and uses
the S1 transaction, which updates proposal status/result atomically too. Repeated
approval of the same successful proposal replays; rejected or mismatched proposals
cannot apply. Legacy build proposals without identity require a new preview.
Other action types retain their original path. The existing supplemental decision
audit can remain best effort after first success; its failure cannot turn a
committed plan into a reported failed application or cause another plan write.

At the explicit UI handoff, the UI specialist changes
`web/components/planning/PlanBuilder.tsx`, `web/lib/api.ts`, `web/lib/types.ts` and,
only as needed for this build result, `web/components/ui/ProposalCard.tsx`.
POST preview receives the prepared
identity; confirm sends only that identity and `confirm:true`. Every build field
change invalidates it, including distance. A request generation counter discards
late preview responses after any input change/cancel/newer request. Disable edits
and duplicate submit while confirmation is in flight. Preserve an unresolved
identity after a transport failure so Retry resends it, not another build. For
stale/expired state show the specified message and explicit return to preview.
While the confirmation outcome is uncertain, continue to disable editing,
Cancel and new-preview actions; retain the unresolved ID outside the ordinary
pre-confirm invalidation/reset path. Retry the same ID until a successful result
or an authoritative rejection resolves the attempt. A corrupt/unreadable receipt
does not prove that no plan was committed: preserve the unresolved identity and
show a non-retryable error for manual diagnosis rather than clearing it or
offering another save. Show an accessible status explaining why editing is locked.

Remove the follow-up onboarding PUT; the server already saved the captured
Planning profile atomically. Refresh status, overview, history and onboarding
queries after success/replay. A historical replay must not be rendered as the
active plan. This is contract wiring and accessible status/error behavior, not
a visual redesign. Update fixtures, registry and generated TS contract; verify
lint/build before any push touching web. This milestone ends with all public
build-confirmation paths covered and old bypasses rejected.

### M5 — accept the slice with evidence


Run focused tests, failure/restart/reset/concurrency probes, contract extraction
and the contributor-safe suite. Use existing isolated web E2E fixtures, with a
temporary synthetic DB and providers disabled, to exercise successful confirm,
stale rejection, distance invalidation, late response, cancel, lost-response retry
and historical replay. Add `tests/e2e/test_planning_build_confirmation.py` using
the repository's web fixture rather than launching against the athlete's live
localhost instance. Verify desktop and mobile controls with keyboard use; no
CSS redesign is required. Record screenshot evidence from synthetic scenarios.

The independent implementation reviewer checks the final diff against AC1–AC8,
not speculative unrelated improvements. Review budget is two rounds: one full
review, then scoped corrections. Human owner decides merge. Update this document,
the slice evidence bundle and issue with actual checks, failures and limits.
Do not close parent #677; S2 lifecycle, S3 calculation consistency and S4 screen
explanation remain independent work.

## Concrete Steps


Run from the repository root `/Users/gregkisel/Developer/ai_trainer`, using the
existing environment. Before implementation inspect `git status --short --branch`
and avoid mixing another task's changes. Current work is docs-only on
`codex/issue-685-preview-confirm-spec`. Publish the reviewed documents as a
docs-only draft PR linked with Refs #685; publication does not start M1 or close
the implementation issue.

Baseline already executed on 2026-10-16:

    ./ai_trainer_env/bin/python -m pytest tests/smoke/test_api_planning.py tests/smoke/test_planning_active_plan_overview.py tests/smoke/test_planning_m4c_plan_editor.py tests/smoke/test_coach_decisions.py -q
    66 passed in 11.69s

During M1–M4, once the new files exist:

    ./ai_trainer_env/bin/python -m pytest tests/smoke/test_planning_build_confirmation.py tests/smoke/test_planning_build_confirmation_storage.py tests/smoke/test_api_planning.py tests/smoke/test_planning_m4c_plan_editor.py tests/smoke/test_coach_decisions.py -q

Expected final result: all tests pass, with the activity-change case rejecting
before any checkpoint/demand/profile write and the replay case proving one insert.
Record actual test count rather than predicting it. Expand caller regressions to
existing demand, recovery, demo and API HTTP suites identified by the inventory.

Before the implementation PR is ready:

    ./ai_trainer_env/bin/python -m ruff check .
    ./ai_trainer_env/bin/python -m pytest -m "not live and not debug and not e2e" tests/
    npm --prefix web run contract:extract
    npm --prefix web run contract:extract -- --check
    npm --prefix web run contract:inventory
    ./ai_trainer_env/bin/python -m pytest tests/smoke/test_contract_extractor.py tests/smoke/test_api_call_inventory.py -q
    npm --prefix web run lint
    npm --prefix web run build
    ./ai_trainer_env/bin/python -m pytest -m e2e tests/e2e/test_planning_build_confirmation.py -q
    git diff --check

Install browser/runtime dependencies only if needed and per repository guidance;
if a check is unavailable, record the exact limitation instead of calling it green.
For docs authoring now, check links/structure and `git diff --check`; broad code
tests above are future implementation gates, not work required to validate prose.

## Validation and Acceptance


The slice spec maps AC1–AC8 to named tests, boundaries and expected outcomes.
Accuracy means identical full saved prescription: dates, sports, durations,
targets, steps, nested sessions, identities, events, constraints, rules and
provenance. Weekly TSS equality alone is insufficient. Assert equality against
the frozen checkpoint, as well as equality of public weeks/forecast/audit.

Freshness covers inserts, updates, deletions and linked-provider changes within
the effective activity view; athlete zones; relevant constraints; latest checkpoint;
planning settings; rule version; athlete day/timezone and activity cutoff. A changed
unrelated theme setting must still allow confirm. Identical dependency values
rewritten without a semantic change must not invalidate solely because a write
occurred (included row timestamps are themselves values under the conservative
policy). At expiry equality (`now >= expires_at`) confirmation fails. Successful
replay is checked before these pending-only rules.

The UI demonstrates one coherent confirmed profile, an explicit stale error and
a usable Retry after uncertain transport. API tests establish what the browser
alone cannot: atomic rollback, real writer exclusion and durable replay after
reopening the database. Performance verification keeps calculation outside the
writer transaction and provider I/O at zero; record 16-week reference-preview
latency against ASR-PERF-4 (<10 seconds on the reference environment), without
claiming a deployment SLA from a unit test.

## Idempotence and Recovery


Preview ID is the idempotency key: repeated successful confirmation returns the
same stored plan and never inserts or activates again. Pending expiry is stored
in UTC; applied receipts are not TTL-deleted. The selected database owns all rows,
so a real/demo switch cannot import a preview from the other database. Full reset
deletes new previews with checkpoints and proposals. Restart reads the persistent
receipt; it does not need process memory.

Schema addition is idempotent and does not rewrite existing checkpoints. Before
any authorized deployment backup use `scripts/sqlite_backup_restore.py` as
documented in `docs/sqlite_backup_restore.md`, with services stopped; do not copy
the SQLite file directly and miss its WAL. This spec task does not back up, alter
or reset the live database. Test migrations/reset/backup restore on temporary DBs.

Rollback of a failed transaction is automatic. Application downgrade is different:
an old binary re-enables unsafe raw confirmation. Do not claim it safe merely
because it ignores the additive table. Revert with confirmation writes disabled
at the deployment boundary, or deploy a compatibility patch preserving the
rejection; regenerate previews after re-upgrade. Keep applied checkpoints and
receipts. Verify this compatibility behavior in the implementation evidence.

## Artifacts and Notes


Evidence is synthetic and can be published without personal workout values.
Observed baseline transcript:

    drift 1914 2205 same_weeks False
    writer_lock_probe database is locked

The proposed wire example is not an executed response:

    POST /api/planning/build                 -> 200, plan_id=null, confirmation.status=pending
    POST /api/planning/build/confirm
    {"preview_id":"<server UUID>","confirm":true}
                                            -> 200, plan_id="<new checkpoint ID>", replayed=false
    repeat same request                     -> 200, same plan_id, replayed=true
    confirm stale pending preview           -> 409, code=preview_stale, no plan/settings writes

The [slice spec](planning_preview_confirm_slice_spec.md) holds the review record
and exact response/error/retention definitions. No tokens, personal databases,
raw dependency snapshots or logs should be attached to the public issue.

## Interfaces and Dependencies


Use existing Python/FastAPI/Pydantic/SQLite and TypeScript tooling. No new service
or third-party dependency is required. In `models/planning_build_confirmation.py`
define immutable `BuildParameters`, `BuildInputSnapshot`, `PreparedPlanBuild` and
the versioned canonical JSON/digest functions. A frozen dataclass alone does not
make nested dictionaries immutable: serialize retained payloads or defensively
copy at ownership boundaries. Prepared data includes checkpoint JSON, response
JSON, normalized parameters, dependency digest and intended settings writes.

In `api/planning_service.py` expose the narrow public orchestration functions:

    prepare_plan_build(db: Database, *, parameters: BuildParameters,
                       origin: Literal["planning_ui", "coach"]) -> dict[str, Any]
    confirm_plan_build(db: Database, *, preview_id: str,
                       origin: Literal["planning_ui", "coach"],
                       proposal_id: int | None = None) -> dict[str, Any]

Only trusted adapters select origin; HTTP clients cannot supply it. Pure build
calculation consumes `BuildInputSnapshot`, with explicit effective day and revision
time, and returns `PreparedPlanBuild`; it must not read SQLite or wall time. The
existing `build_plan` facade can delegate to this core for internal callers while
retaining their behavior. Public raw persist routes must not call that facade.

The store in `data/planning_build_preview_store.py` owns connection-bound capture,
pending insertion, proposal binding and atomic confirm. Refactor shared read/insert
primitives in `data/database.py` rather than nesting public helpers that commit.
`models/planning_checkpoints.py::build_planning_checkpoint` runs during prepare;
confirm inserts its frozen output. `services/planning_profile.py::normalize_profile`
supplies validation; profile storage inside confirm uses the transaction's connection.

`config/settings.py` owns `PLANNING_BUILD_PREVIEW_TTL_SECONDS` (default 1800,
positive integer) and `PLANNING_BUILD_PREVIEW_RETENTION_DAYS` (default 7, positive
integer). Store per-row expiry at preparation; later config changes do not rewrite
it. Constants for protocol/storage/build-rule version live with the new model;
pending confirmations require the current versions. Canonical response models and
the TS additions are specified in the companion contract.

## ASR / risk traceability


ASR-REL-1: retain exact prescription identity and append-only history.
ASR-REL-2: explicit stale/missing/corrupt outcomes without partial application.
ASR-MOD-2: server-owned meaning, thin UI. ASR-MOD-3: additive storage/read
compatibility and explicitly breaking unsafe write protocol. ASR-PERF-4:
no scheduler/provider work under the writer lock. ADR-0001's web-first/shared
Python boundary is reused; no new architecture platform is introduced. Planned
status and verification are recorded in `docs/architecture/asr_catalog.md`.

Revision note (2026-10-16): initial executable specification prepared from #685,
current source inspection, synthetic drift reproduction and writer-lock probe.
All implementation milestones and acceptance GREEN remain pending.

Revision note (2026-10-17): independent spec round 1 identified a conflicting
edit/cancel reset rule after a lost confirmation response. The uncertain state
now owns the unresolved ID, keeps those controls locked, and requires resolution
through same-ID retry or diagnosis of an unreadable receipt. The companion test
matrix covers lost response followed by attempted edit/cancel/new preview.
Scoped round 2 verified this correction and returned READY for spec handoff.

Revision note (2026-10-17, M1): owner authorized implementation. Added isolated
HTTP RED and full-payload characterization fixtures. Focused baseline plus
characterization: 78 passed in 14.86s. HTTP acceptance: 20 failed in 5.07s as
expected before the new protocol; no unrelated failures are hidden as expected.
Repository Ruff and whitespace checks passed. M2–M5 remain pending.
Independent M1 review of `097cf99` found no blocking P1/P2 and independently ran
the 12 characterization cases (4.33s). A synthetic mutation probe changed one
nested materialized-step duration by one second while leaving total TSS unchanged:
checkpoint/session hashes changed and response hash did not. This checks that the
calculation oracle protects prescriptions beyond totals. M1 is a non-merge-ready
RED checkpoint; the next bounded implementation step is M2 preparation/storage.

Revision note (2026-10-17, M2): implementation added on
`codex/issue-685-m2-prepared-preview`, based on M1 `93d3bb0`. The first six new
preparation tests were preliminary RED for the missing model/service, then GREEN
against the unchanged M1 full-payload oracle. No M1 hash fixture was regenerated.
The 73-case M2 suite covers immutable ownership, pure calculation, coherent
concurrent reads, dependency boundaries, prepare-time races, corruption, TTL,
bounded cleanup, reset/reopen and backup/restore. A local synthetic 16-week
prepare took 0.308s (<10s reference target), with active state unchanged; this is
an observation, not a deployment SLA. Full S1 confirmation and UI acceptance
remain M3–M5; broad checks and independent M2 review are recorded when finished.

M2 review round 1 on `24b0448` identified two blocking P2 invariants: a transitive
readiness clock and absent/NULL setting conflation. Both were reproduced by the
three-case RED above, then fixed without changing readiness behavior elsewhere.
An initial broad run on the pre-correction tree passed 3234 tests (14 skipped,
46 deselected), excluding only the separately rerun 20 known M1 HTTP RED cases.
The post-correction broad run passed 3236 tests, 14 skipped and 46 deselected in
232.04s. Independent scoped round 2 verified both fixes (`fixed-in 6516989`),
passed 75 focused tests and returned READY for M2 draft handoff. Review budget
2/2 is complete. Fourteen broad skips comprise unavailable process/socket
capabilities (2), explicit fixture regeneration (10), and optional garth (2).
Known M1 HTTP RED was tested separately (20 expected failures); no new failure
was excluded as expected. A final corrected-tree 16-week prepare took 0.339s
with active state unchanged. M3 remains the next explicit milestone.

Revision note (2026-10-17, M3 in progress): public preparation now retains an
artifact; confirmation applies its exact JSON without scheduler calls. The store
owns checkpoint/settings/receipt publication and replays without reactivation.
Coach origin remains fail-closed pending the M4 proposal-binding adapter. M3
initial RED/GREEN and contract harness evidence recorded; final checks/review pending.

Revision note (2026-10-17, M3 review): independent review accepted product code
`0fc01c4` and the protocol-test adaptation at `77b51b2`. Documented original RED,
transaction/replay GREEN, unchanged calculation oracle and the two legacy caller
test adaptations. Public UI and Coach are the next explicit M4 role handoff.

Final M3 verification (2026-10-17, `77b51b2`, metadata-only follow-up):

    ./ai_trainer_env/bin/python -m pytest -m "not live and not debug and not e2e" tests/ -q --tb=short
    3346 passed, 14 skipped, 46 deselected, 7 warnings in 227.62s

No file exclusions or new skip/xfail. The 14 skips are the environment's unavailable
process/socket capabilities (2), explicit fixture regeneration (10) and optional
garth dependency (2). Warnings are the pre-existing Starlette/httpx deprecation
and six synthetic connection-proxy pandas warnings in fault/race probes. Web
lint/build, full repository Ruff, whitespace, contract extraction/freshness,
conformance/inventory and ExecPlan sections/links pass. Full local checks do not
replace M4 browser/Coach integration or the M5 native/human merge gates.

Next bounded milestone: M4 Domain/API adapter for Coach proposal binding and
atomic approval/replay, then explicit UI/Design handoff for identity-only Planning
confirmation, unresolved-response ownership and safe stale/retry UX. Use the
accepted contracts; do not redesign step 4 or change training mathematics.

M4 Domain/API to UI handoff (2026-10-17): Coach tool now prepares origin=coach,
proposal persistence binds the saved/deduplicated card in the same transaction,
approval dispatches build before the generic claim, and the shared store publishes
proposal approved/result with checkpoint/settings/receipt. Initial new Coach
matrix: 16 failed, 2 passed; implementation: 18 passed. Coach/related regression
subset after intentional protocol adaptations: 52 passed in 6.54s. Other actions
retain the generic claim; their tests now use adjust_plan rather than the removed
legacy build writer. Independent final M4 review remains pending.

Explicit role handoff: Domain/API slice stops here; UI/Design Specialist continues
with existing BuildPreviewResponse/BuildConfirmResponse and ApiError code/retryable.
Files: web/components/planning/PlanBuilder.tsx, web/components/ui/ProposalCard.tsx,
and minimal parent lock wiring in web/app/planning/page.tsx to prevent destroying
an unresolved editor by switching tabs. UI brief: athlete previews a draft, explicitly
confirms it, sees applied/current status or a safe conflict, and can retry an unknown
outcome using only its original identity. Reuse current layout/tokens; no new math,
information hierarchy or visual redesign. All edits invalidate before confirmation;
confirming/uncertain lock edits, Cancel and another preview. Accessible status/error
and explicit stale return action are required. Test on isolated synthetic stack,
including keyboard, late responses and 390/1280px light/dark; no live localhost.
