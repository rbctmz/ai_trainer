# Planning S2: close the old cycle and start a new one (#693)

This living ExecPlan follows `.agent/PLANS.md`. Issue
[#693](https://github.com/rbctmz/ai_trainer/issues/693) is S2 of
[#677](https://github.com/rbctmz/ai_trainer/issues/677), after merged S1
[#691](https://github.com/rbctmz/ai_trainer/pull/691). The
[slice specification](planning_cycle_lifecycle_slice_spec.md) defines exact
state, storage, API, compatibility and acceptance obligations. Baseline main is
`93fa4f4d8d41c9e392093538900f471903b6c331`. M0 Spec / Architecture Owner handed
the reviewed contract to Domain / API Implementer for M1 tests; the user then
authorized continuing to M2 storage/projection on 2026-10-18. No API/UI role
expansion is implied by this milestone.
Human user authorized beginning S2 on 2026-10-17; this is not merge/live approval.

## Purpose / Big Picture

After the date of an Olympic triathlon has passed, the athlete needs to see that
the preparation period ended, decide whether to close it and optionally record
that they did not participate. They should be able to start a new cycle without
silently reusing last summer's start date or old races. Closing is not proof of
execution, participation or finishing. A cycle is a saved preparation context;
a checkpoint is one saved plan version within it.

The decisive journey uses synthetic data only: an expired event cycle with
unknown participation shows its ended period; closing without an answer keeps
the outcome unknown and history readable; choosing did_not_participate records
only that declaration; starting a fresh cycle offers today's actual start, no
old events and no backdated executable sessions. Preview/cancel changes nothing.
Confirm replaces selection atomically; retry after a lost response reuses the
same result. Planning, Today and Coach report the same server-owned state.

## Progress

- [x] (2026-10-17) Fresh main/GitHub checked at `93fa4f4`; S1 is merged, post-merge documentation #692 remains a separate draft.
- [x] (2026-10-17) Read #677 model v1 and #680 boundary; no existing S2 issue found, created #693 with AC1–AC10 and non-goals.
- [x] (2026-10-17) Inventory current/latest checkpoint readers and writers, history/restore, constraint binding and provider delivery boundary.
- [x] (2026-10-17) Synthetic falsifying probe confirms expired Race Week, inherited old calendar/events and two backdated executable days even with clean current-week inputs; protected active state unchanged.
- [x] (2026-10-17) Existing planning/overview/S1 HTTP baseline: 89 passed, 1 warning in 7.66s; no new lifecycle GREEN claimed.
- [x] (2026-10-17) Draft Class A slice spec: selected-cycle storage, conservative migration, protocol compatibility, commands/replay, calendar floor and reader/writer obligations.
- [x] (2026-10-17) Independent spec round 1/2 reviewed `93fa4f4..a4647fd`; one blocking P2: missing new-cycle session namespace/lineage boundary. Independent baseline 89 passed in 8.17s.
- [x] (2026-10-17) Pure synthetic identity probe confirms same content/date ignores differing cycle_id today; specified modern v2 namespace, no cross-cycle ID/lineage reuse and unchanged legacy IDs, with explicit historical context tests.
- [x] (2026-10-17) M0: scoped round 2/2 reviewed `a4647fd..a2f3848`, verified the identity/lineage correction and returned READY for spec handoff, zero remaining blockers. Publish draft follows; no extra review round.
- [x] (2026-10-17) M1 author checkpoint: 14 behavioral RED, 26 preliminary protocol RED, 7 new GREEN characterization; 256 existing S1/planning/history regressions passed. Initial inventory: 87 calls and 19 SQL sites. No product/schema/UI changes.
- [x] (2026-10-18) Partial independent M1 check reproduced 40 failed/7 passed, 7 GREEN characterization and Ruff. Found omitted historical accessor/callback references; author fixed inventory to 91 references / 19 SQL sites. Checker stopped on account usage limit before final verdict; no READY inferred.
- [x] (2026-10-18) M1 complete: independent round 2/2 reviewed `f857f58..82a430f`, reproduced 40 RED/7 GREEN and verified 91 references/19 SQL sites; READY for intermediate checkpoint, zero P1/P2. Draft #695 published/attached, stacked on #694; not a merge candidate.
- [x] (2026-10-18) M2 author implementation: additive store/migration, selected read and pure projection; initial 56 new storage cases GREEN, 75 with existing characterization/backup tests. Raw history/S1 oracles unchanged.
- [x] (2026-10-18) M2 complete: independent round 1 found one P2 (association DELETE); reproduced and fixed-in `69a2623`, scoped round 2/2 CLOSED/READY. Final 58 storage / 77 focused GREEN; contributor-safe contour excluding intentional M1 RED: 3427 passed, 14 skipped, 64 deselected. Draft #696 stacked on #695; no standalone merge/live migration.
- [x] (2026-10-18) M2 RED checkpoint: 29 storage/projection cases failed before implementation (missing interfaces/tables), no collection errors. This preliminary RED is not migration/transaction proof.
- [x] (2026-10-18) M3a complete: read/command API/TS contracts, retained close/outcome/scope commands, CAS/replay/rollback/retention probes. Independent scoped review READY at `b5807ad`, 222 focused GREEN; contributor contour with explicit M1 RED exclusions: 3502 passed / 14 skipped / 64 deselected. Publication remains intermediate draft only.
- [ ] M3b: S1 v2 start_new/edit_current, calendar/identity boundary and atomic replacement; preserve applied-v1 replay and reject pending-v1.
- [ ] M3c: every planning/Coach/legacy writer guards selected cycle/head under the writer lock; explicit restore ownership.
- [ ] M4: explicit current-vs-history reader integration, then Domain→UI handoff for minimal actions/status and isolated web acceptance.
- [ ] M5: final whole-S2 evidence, current-head CI/native review and explicit human merge decision.

## Surprises & Discoveries

**Observed:** on current main, status.has_plan is true for a synthetic
2026-08-03…2026-10-04 plan on athlete day 2026-10-16. Overview progress is
completed, yet current_week is Race Week/9 and event outcome is absent. The
web overview calls that checkpoint active and that phase current.
**Inferred:** existence of a checkpoint is being used as current-cycle selection;
calendar passage, execution and outcome are conflated in presentation. A cheap
falsifier is to read overview/edit context from an expired temporary checkpoint.
**Verified by:** the probe below reproduces those exact states without writes
from GET. There is no persisted selected-cycle record in current storage.

**Observed:** preparing training_goal from that edit context retains
start_week=2026-08-03 and event=2026-10-04. All 48 executable days fall before the
pinned athlete day; zero are future. Cleaning start_week/events yields Monday
2026-10-12 and no events, but two executable days still precede Friday 2026-10-16.
**Inferred:** clearing the old form alone cannot guarantee a genuinely new start;
the Monday week label must be separated from the actual first allowed date.
**Verified by:** both real S1 preparations on the temporary DB, reading their
retained checkpoints. Counts are diagnostic synthetic measurements, not golden
assertions. The test must assert no newly executable date before start_date.

**Observed:** current writers/consumers include demand/adjustment/near-term edits,
repair/restore, Coach build, Today/recovery, reconciliation/session feedback and
legacy Streamlit persistence. Constraint rows have plan_id/session_id and sport,
but no cycle scope. Delivery can obtain a client before discovering no plan.
**Inferred:** changing only overview or changing the raw latest-history helper
would leave stale mutations or break historical facts. The cheapest falsifier
is a frozen caller inventory plus a close/switch test for each writer family.
**Verified by:** source inventory collected with rg, named in the slice spec.
Runtime close/switch safety is NOT YET; M1 must establish executable RED.

The first probe used a datetime subclass that defeated the overview's
isinstance check, raising a type comparison error. This was a harness defect:
the corrected probe keeps the real datetime type and pins athlete_local_date.
No product datetime defect is claimed from that failed attempt.

**Observed:** identical synthetic sessions with two different cycle_id values
produce the same current content-derived ats_ ID. The current builder also
supplies the previous plan to identity generation; feedback/matches key by ID.
**Inferred:** S2 needs an explicit new-cycle identity boundary so a fresh plan
cannot inherit old evidence or replaces lineage. A pure two-cycle identity call
is the cheap falsifier; this is not a defect in the existing v1 content contract.
**Verified by:** author pure probe returned ats_095fdf5c5cc311c9b2a29044 twice;
independent checker inspected both material/reuse branches and ledger readers,
reported one blocking P2 in the proposed spec. Correction defines immutable
modern cycle namespace, no prior-cycle donor/parent chain, within-cycle stable
IDs, untouched legacy IDs and an overlapping-cycle test matrix. Runtime GREEN
is NOT YET; scoped spec verification follows.

## Decision Log

Decision (2026-10-18, M3 Domain/API): keep M3a commands/contracts separate from
M3b retained build publication/identity and M3c writer guards. This is a
review/commit boundary, not permission to merge an incomplete lifecycle. The
typed web/lib/planningCycles.ts transport contains no screen, styling or client
state decisions; M4 remains the UI handoff. API inventory now scans lib/ as well
as app/components so typed transports remain covered by the same contract gate.

Decision (2026-10-18, M3a Domain/API): hash the canonical request (including kind,
target UUID and sorted close declarations) and retain an internal result/digest
envelope in result_json. Public result stays immutable; replay reads that receipt
before CAS and computes only replayed/current_context afresh. SQL triggers block
update, replacement and deletion of successful receipts; full reset temporarily
drops only the deletion guard inside its existing transaction. Constraint CAS
fingerprints cover all existing constraint fields plus ownership, returned by the
existing constraints listing using the athlete's local day. Scope resolution
updates only cycle_scope/cycle_id.

Decision (2026-10-18, M2 Domain/API): initialize all cycle DDL, constraint scope
columns, conservative import and migration flag in one BEGIN IMMEDIATE after
existing Database column migrations finish. Existing initialization helpers
commit internally, so they must not split the cycle transaction. Pure reads
require initialized state; missing/corrupt selection is never repaired in a GET.
No HTTP lifecycle route, command, writer migration or UI integration is added in
M2. Existing raw writers remain temporary compatibility paths until M3 guards;
their later history rows cannot alter the new explicit selector.

Decision (2026-10-18, M2 Domain/API): ambiguous session-only constraint bindings
include unassigned legacy history as an unknown owner. A verified explicit
checkpoint disambiguates its own stored session; an unresolved/conflicting
checkpoint cannot be overridden by a coinciding current session ID. Session
scanning is skipped when no migrated constraint needs session ownership.

Decision (2026-10-17, M1 Domain/API): keep runtime unchanged and separate tests
by `test_behavior_`, `test_protocol_`, and `test_characterization_`. Missing
routes/fields are preliminary RED. Exercise actual-start clipping at the existing
pure calculator seam using the specified frozen lifecycle object; do not invent
a public action-field spelling before the M3 request contract is frozen.
Unknown legacy constraint scope is tested through migration/storage projection;
prepare refusal and scope-command transaction/replay remain M3 obligations.

Decision (2026-10-17, Spec Owner): use a persisted singleton selection and
immutable checkpoint-to-cycle associations. Keep get_latest_planning_checkpoint
as raw history; add an explicit current selector and migrate its callers. This
prevents closing a cycle from being undone by a later historical insert or a
reader falling back to MAX(id).

Decision (2026-10-17, Spec Owner): conservatively import only the latest legacy
checkpoint into one selected legacy cycle. Older versions remain unassigned
history, with no claim about historical cycle boundaries. Valid daily dates
define period; unknown data is indeterminate. Explicit same-legacy-cycle restore
is a separate guarded action; never rewrite old JSON/associations in migration.

Decision (2026-10-17, Spec Owner): reuse S1 publication/receipt for new cycles,
with a frozen v2 lifecycle context and selection revision. Close/outcome/scope
commands use a small fixed-purpose receipt table. Pending old v1 artifacts fail
closed; successful old receipts remain replayable without reselecting anything.
No general workflow engine, task scheduler or event-sourcing framework.

Decision (2026-10-17, Spec Owner): actual start_date is authoritative and cannot
be in the past for start_new; week Monday is a label only. New form context is a
separate action from editing. New events/intent are explicitly chosen; valid
availability is only a labelled suggestion. Recompute affected projections from
the exact clipped canonical prescriptions, retaining existing training formulas.

Decision (2026-10-17, Spec Owner): retain athlete constraints and explicit cycle
ownership. Unknown bindings cannot silently become global or disappear. Expose
one explicit metadata-only scope resolution command. This is the required
cross-cycle ownership repair, not medical/recovery policy implementation.

Decision (2026-10-17, Spec Owner, spec P2 correction): modern session/leg identity
uses an immutable cycle UUID namespace, frozen in preview; start_new cannot use
the prior cycle's IDs or replacement/parent continuity. Legacy IDs/ledgers remain
unchanged; within-cycle edits/restores retain existing identity rules. Historical
projection accepts explicit checkpoint context instead of guessing an owner.
This closes the clean-start/history evidence gap without a historical rekeying.

Decision (2026-10-17, Spec Owner): period_ended offers close/new rather than
silently extending an old calendar. Explicit same-cycle post-A continuation is
#680; no recovery or participation is inferred. Closed-cycle reactivation is
outside S2. Minimal UI integration follows approved API semantics, not a redesign.

## Outcomes & Retrospective

M0 has a tracked, reproduced issue and proposed complete integration boundary.
No cycle table, API contract, reader behavior or UI implementation has changed.
The 89 passing tests characterize the existing system; new lifecycle behavior
remains unimplemented. Independent round 1 found a new-cycle identity omission;
the correction at `a2f3848` was verified in scoped round 2/2: READY for specification
handoff, no remaining blockers. The personal database
and providers were not used. Merge and live rollout require separate approval.

M1 author checkpoint now adds runnable regression obligations and a green
preservation boundary. The explicit selected-cycle API, storage migration,
commands, writer guards and UI still do not exist. Tests are intentionally RED
and must stay in an intermediate draft, stacked on M0 #694, until subsequent
milestones make them GREEN. Existing S1 oracle JSON and production code remain
unchanged. Independent M1 round 2/2 completed on `82a430f` with READY for this
intermediate checkpoint, zero P1/P2. M0's exhausted spec review budget was not
reused as a new full specification review. M1 remains intentionally RED, not
runtime acceptance.

### M1 author evidence (2026-10-17)

Observed: `tests/smoke/test_planning_cycle_projection.py`,
`test_planning_cycle_build.py`, `test_planning_cycle_identity.py` and
`test_planning_cycle_characterization.py` collect 47 cases. On unchanged runtime
they yield 40 failed / 7 passed / 1 warning in 1.73s, with no collection errors,
skips or xfails. Fourteen failures reach existing behavior: a past/future week
claimed current (2), canonical assignments before actual start (1), overlapping
cycle IDs/lineage/checkpoint namespace (6), old match/feedback lookup (2), and
colliding provider external keys for singles/multisport/brick legs (3).
Twenty-six failures identify missing lifecycle protocol/projection: selected
state/boundaries/timezone/indeterminate/empty cache, actionable status, explicit
constraint scope, clean form context, build-action guard, close/replay/strict
confirmation and outcome correction. HTTP command tests currently stop at the
first missing route, so their downstream assertions prove no transaction yet.

Inferred: these are the bounded M2/M3 implementation targets, not evidence that
the future commands or atomic replacement are already correct. Cheapest
falsifiers are real existing calculator/identity calls, positive same-cycle and
legacy controls, and re-running untouched S1/history tests.

Verified by: the 14 behavioral cases all reach their asserted defect without
missing imports/interfaces. The actual-start case supplies a valid no-current
frozen lifecycle (base checkpoint 0) at the pure calculator seam and still gets
October 12 prescriptions before October 16. This is a calculator test, not
end-to-end proof of HTTP start_new. The 7 GREEN controls compare complete raw
checkpoint JSON (including whitespace), activities, matches, feedback, delivery
and settings across reads, abandoned S1 preview, restart and SQLite Backup API
restore, and preserve legacy/same-cycle identities. Fixture activities are
resolved through the existing TSS resolver before measurement: an initial
unresolved 55-TSS fixture was legitimately normalized on reopen; that harness
failure is not claimed as an S2 defect. An initial misspelled store import was
also corrected before this final collection/run.

Reproduce from the repository root, using the existing venv:

    ai_trainer_env/bin/python -m pytest -q tests/smoke/test_planning_cycle_projection.py tests/smoke/test_planning_cycle_build.py tests/smoke/test_planning_cycle_identity.py tests/smoke/test_planning_cycle_characterization.py --tb=short
    # Expected M1: 40 failed, 7 passed; exit 1, not a merge gate pass.
    ai_trainer_env/bin/python -m pytest -q tests/smoke/test_planning_cycle_projection.py tests/smoke/test_planning_cycle_build.py tests/smoke/test_planning_cycle_identity.py tests/smoke/test_planning_cycle_characterization.py -k characterization
    # Expected: 7 passed, 40 deselected.
    ai_trainer_env/bin/python -m pytest -q -m "not live and not debug and not e2e" tests/smoke/test_api_planning.py tests/smoke/test_planning_active_plan_overview.py tests/smoke/test_planning_build_confirmation.py tests/smoke/test_planning_build_confirmation_storage.py tests/smoke/test_planning_build_coach_confirmation.py tests/smoke/test_planning_checkpoint_history.py tests/smoke/test_planning_build_commit.py tests/smoke/test_planning_build_preparation.py tests/smoke/test_planning_build_preview_store.py
    # Author: 256 passed, 7 warnings in 30.36s.
    ai_trainer_env/bin/python -m ruff check .
    # All checks passed.

The frozen inventory is `tests/fixtures/planning_cycle_callers.json`, referenced
to baseline `93fa4f4`: 91 direct/dynamic/callback accessor references and 19 direct SQL sites
across eight named responsibility families. It includes explicit history and
mixed current/history callers, raw storage, compatibility and synthetic/admin
paths; it does not instruct replacing every MAX/history reader. Tests/fixtures
are explicitly excluded from that runtime inventory and must be adapted as
synthetic initialization, never given an HTTP bypass. Source calls may move;
the recorded line numbers are baseline evidence, not golden line-number tests.

M1 review round 1 (partial, 2026-10-18): the fresh read-only checker independently
reproduced 40 failed/7 passed in 1.59s, 7 GREEN characterization and Ruff, and
verified all original 87 call entries/19 SQL sites. It identified omitted
`api/routers/activities.py:312 get_checkpoint_data` and the historical callback
`api/routers/decisions.py:151 db.get_planning_checkpoint`. Author falsification
with source search/AST confirmed both; expanding the scan also adds the two
private read-only adapter calls in `scripts/repair_planning_materialization.py`.
The updated 91-reference fixture labels call/dynamic/callback forms and keeps
historical exceptions explicit. The checker hit its account usage limit before
a final verdict; its partial result is not a completed independent acceptance.
Its baseline command was still running at the last message, so no independent
256-case result is claimed. The author baseline remains verified.

M1 review round 2/2 (completed, 2026-10-18): followed
`docs/opencode_external_reviewer_runbook.md` after the first checker stopped.
OpenCode 1.1.30 plan agent had edit denied; configured
`deepseek/deepseek-flash` returned MODEL_OK before assignment. Session
`ses_eb1863f31ffeuBGZApqpN1VwFl` reviewed exact `f857f58..82a430f`, only the seven
M1 files, with the approved spec as reference. Its sole allowed pytest command
was the four-module M1 command above: 40 failed, 7 passed, 1 warning in 1.51s.
It verified the 14/26/7 split, real behavior seams, complete six-table row
comparisons and 91 inventory references (84 calls, 6 dynamic lookups, 1 callback)
plus 19 SQL sites. Verdict READY for the intermediate RED checkpoint only;
P1 none, P2 none. Supervisor checked its source/count evidence against the
fixture and existing captured runs. No tracked/untracked file changes by the
reviewer; postflight clean, no remaining audit process. Author push updated
remote tracking during the run without changing reviewed file content. Ruff
and the 256-case baseline remain author/prior-checker evidence, not round-2 runs.

Non-blocking suggestions are explicitly triaged as follow-up #693 within the
already approved milestones: M2 adds explicit end_date and historical-week
assertions when the projection exists; M4 expands the cached-state consumer
checklist for dashboard_summary, legacy Planning/dashboard and ai_coach_entry
behind app_state. Dynamic inventory lines intentionally anchor the `getattr(`
call expression rather than the following string literal; the new
reference_kind makes that convention explicit. None is an M1 merge gate or an
authorization to implement UI now. The round-1 historical-reference omission is
fixed-in `82a430f`; no unresolved blocking finding remains.

Publication: draft [#695](https://github.com/rbctmz/ai_trainer/pull/695), stacked
on M0 [#694](https://github.com/rbctmz/ai_trainer/pull/694), contains author RED
`b72f556` and inventory correction `82a430f`. This final metadata revision only
records the completed review and handoff. No additional full review requested.
Next role remains Domain / API Implementer, scoped to M2 storage/migration and
selected-cycle projection; HTTP commands/atomic replacement stay M3, UI M4.

Remaining proofs are deliberately scheduled in M2/M3: actual migration/selection
and reset, malformed data handling, real-command failure/race injection,
unknown-scope prepare refusal, atomic replacement, old successful receipt replay
after another selection, reserved namespace stability through preview/confirm,
and every writer family after close/switch. M4 owns cross-surface/UI acceptance.

### M2 author evidence (2026-10-18)

Observed: `tests/smoke/test_planning_cycle_storage.py` initially produced 29
failed cases in 1.37s on M1, missing new interfaces/tables rather than proving
transaction failures. Implementation now lives in `data/planning_cycles.py`,
`models/planning_cycle.py`, `services/planning_cycles.py` and narrow Database
initialization/selector/reset/constraint-metadata adapters. Additional tests
expanded initial coverage to 56 cases, then 58 after the review correction.
Fault injection includes after initial cycle,
association, singleton and after the final migration flag; a forced later reset
delete failure preserves all cycle/old state and releases the connection.

Inferred: the persisted selected pointer, immutable version associations and
coherent read transaction prevent higher-ID history from becoming current and
prevent closed/null selection from being reimported at restart. Conservative
scope classification prevents a coinciding legacy session from donating
ownership. Cheapest falsifiers are a larger raw checkpoint insertion, real
two-connection read/write interleave, concurrent initialization, and a duplicated
legacy session ID without an explicit checkpoint.

Verified by: targeted suite includes all those falsifiers, inclusive start/end
and athlete timezone boundary, missing/corrupt content, no writes under a SQLite
authorizer, unselected-open corruption, historical selection identity, default
unknown participation, provider source IDs in event keys, exact old JSON/ledger
bytes, full reset/restart and Backup API retention of namespace/receipts.
The duplicate legacy-ID constraint initially misclassified as cycle, and
distinct source_id events initially collided: both were reproduced as 2 RED / 7
GREEN targeted probes, then fixed. A simulated closed/selected state and seeded
receipt test storage/projection only, NOT command/CAS/idempotency semantics.

Author commands from the repository root:

    ai_trainer_env/bin/python -m pytest -q tests/smoke/test_planning_cycle_storage.py tests/smoke/test_planning_cycle_characterization.py tests/smoke/test_sqlite_backup_restore.py --tb=short
    # Final author focused run: 77 passed in 3.03s; storage alone contributes 58.
    ai_trainer_env/bin/python -m pytest -q -m "not live and not debug and not e2e" tests/smoke/test_api_planning.py tests/smoke/test_planning_active_plan_overview.py tests/smoke/test_planning_build_confirmation.py tests/smoke/test_planning_build_confirmation_storage.py tests/smoke/test_planning_build_coach_confirmation.py tests/smoke/test_planning_checkpoint_history.py tests/smoke/test_planning_build_commit.py tests/smoke/test_planning_build_preparation.py tests/smoke/test_planning_build_preview_store.py --tb=short
    # 256 passed, 7 warnings in 33.81s; existing S1 oracle unchanged.
    ai_trainer_env/bin/python -m pytest -q -m "not live and not debug and not e2e" tests/ --ignore=tests/smoke/test_planning_cycle_projection.py --ignore=tests/smoke/test_planning_cycle_build.py --ignore=tests/smoke/test_planning_cycle_identity.py --tb=short
    # First broad run: 3422 passed, 14 skipped, 64 deselected, 7 warnings in 183.40s.
    # Final post-P2 run on 69a2623: 3427 passed, 14 skipped, 64 deselected,
    # 7 warnings in 254.92s. No S2 case skipped or xfailed.
    ai_trainer_env/bin/python -m pytest -q tests/smoke/test_planning_cycle_projection.py tests/smoke/test_planning_cycle_build.py tests/smoke/test_planning_cycle_identity.py tests/smoke/test_planning_cycle_characterization.py --tb=short
    # Expected remaining M1 contour: 35 failed / 12 passed. Five migrated scope
    # projections became GREEN; public commands/build/UI and v2 IDs remain future.
    ai_trainer_env/bin/python -m ruff check .
    git diff --check
    # GREEN.

The broad command explicitly excludes three intentionally RED M1 modules, so it
is NOT a whole-S2 CI pass. Existing skips include optional missing `garth` and
pre-existing fixture requirements; no new S2 test is skipped/xfail. All new work
and probes use temporary synthetic databases; no local athlete cache is opened
to run migration. New constraint metadata is nullable/additive; old field values
are retained. Legacy activity normalization still runs as before; preservation
fixtures seed already-resolved synthetic TSS, without changing its math.

Independent M2 review completed after the scoped correction below. Next boundary remains M3 contracts/commands and
guarded exact publication. M4 will route Planning/Today/Coach and legacy cached
consumers through this selector. Until those slices, existing HTTP/UI readers
still use the old raw history behavior. This intermediate branch is neither a
standalone merge candidate nor authorization to migrate a live cache.

### M2 independent review and correction (2026-10-18)

OpenCode 1.1.30 plan agent (edit denied), verified MODEL_OK
`deepseek/deepseek-flash`, reviewed exact `39e8f39..873d701` in session
`ses_eb1427a4fffeL4Z5dU72LfUQxe`. Its only test command was the focused three-file
command above: 75 passed in 2.02s. One consolidated round-1 P2, no P1: UPDATE and
replacement were guarded, but association DELETE was not, contrary to retained
immutable version ownership. The reviewer returned NOT READY for M2, while
confirming the other migration/selection/scope/preservation checks.

Observed: supervisor added exact direct/bulk DELETE cases; both failed to raise
on `873d701` (2 RED, 2 GREEN existing update/replace controls). Inferred: an
accidental deletion could destroy retained ownership and turn the selected cycle
into an indeterminate gap. Verified by: those executable temp-DB failures, then
`69a2623` adds a BEFORE DELETE guard and makes full reset the sole production
deletion path. Reset drops/recreates the guard inside its existing writer
transaction. Its fault test checks guard restoration BEFORE any Database
reinitialization, so startup repair cannot mask a partial reset. Deliberate
corruption/pre-migration fixtures explicitly bypass the guard, not public code.

Scoped round 2/2 reviewed ONLY `873d701..69a2623`, two files / 23 added lines, in
session `ses_eb039426affeaX9frd788uOXZ0`. Same verified model/plan agent; 77 focused
tests passed in 3.51s. It returned P2 CLOSED — fixed-in `69a2623`, READY for the M2
checkpoint, no delta defect in initialization/reset/transactional DDL. Supervisor
accepted that evidence after the regression/final broad run. Both reviews were
read-only: clean tracked/untracked state before/after, no remaining audit
processes. Remote-tracking status changed only because the author pushed the
pinned commits. Native review/whole-S2 acceptance is still M5; no additional full
review is requested. Append-only command-receipt write guards remain explicitly
M3 scope, as triaged in the first review.

Publication: draft [#696](https://github.com/rbctmz/ai_trainer/pull/696), stacked
on [#695](https://github.com/rbctmz/ai_trainer/pull/695). Code checkpoint
`873d701`, correction `69a2623`; this final docs-only revision records the results
without changing reviewed runtime. Handoff to Domain / API Implementer for M3:
freeze `api/planning_cycle_contract.py`, router/API/TS fixtures first, then
strict close/outcome/scope receipts and S1 v2 exact publication/writer guards.
M1 build/identity and new-command HTTP RED must become GREEN in M3;
cross-surface overview/status RED remains M4 reader integration. No UI
composition/styling decision is part of this Domain/API handoff.

### M3a — author command/contract checkpoint (2026-10-18)

Role: Domain / API Implementer, Class A. Added api/planning_cycle_contract.py,
api/routers/planning_cycles.py and services/planning_cycle_commands.py. Cycle
current/history reads expose the M2 selector in one read transaction. Strict
UUID command IDs, confirm=true and typed revision CAS protect close, event
declaration and scope resolution. Close works early or with an indeterminate
checkpoint and needs no participation declaration. It changes cycle/selection
and receipt only. Event declaration can target a stored version from the same
cycle, rejects ambiguous events/future participation, and never selects/reopens
a cycle. Scope resolution changes only ownership metadata. Response schema and
finite JSON validation precede commit. Busy/storage failures retain retry with
the same identity; corrupted receipts fail closed without private error text.

Observed: the first command probe returned two missing-current-route 404s; the
scope probe initially hit a wall-clock fixture mismatch before reaching the
missing fingerprint. The existing constraints route used machine date while the
new cycle service uses athlete day. Verified by the synthetic pinned-date test;
the adapter now uses athlete_local_date and exposes the metadata fingerprint.
This is not recorded as three independently reproduced command bugs.

Verified by: focused command/storage/characterization/backup and API↔TS conformance,
extractor/inventory contour: 217 passed, 1 warning in 13.20s. New probes cover
every command's state/receipt/pre-commit/serialization rollback, close selection
write failure, same-ID replay after backup/restore, changed-ID payload conflict,
historical events, unknown ownership, future outcomes and real two-connection
close races. All fact/prescription/settings rows remain unchanged by commands.
Ruff/diff check and web lint/build passed; final broad run/review are pending.

Observed remaining M1 contour: 19 failed / 25 passed. Twelve formerly missing
cycle-read HTTP assertions now pass; close/retry/restart itself passes, but the
old test's final /status assertion still fails because M4 has not switched its
reader. No M1 assertion was removed, skipped or weakened. Build context/calendar,
v2 namespace/donor boundary and new-cycle publication are M3b, writer guards M3c;
overview/status and other current-reader integration are M4. Intermediate S2
drafts are not merge candidates and this branch is not a live rollout.

M3a independent review round 1/2, OpenCode 1.1.30 plan agent,
deepseek/deepseek-flash session `ses_eb01ec771ffeCiwt9rUK16yRCW`, examined
`d09c7ed..b350bee` (16 paths; generated contract checked for relevant new
schemas). Fresh MODEL_OK verified availability before assignment. The only
allowed test command was the focused contour above: independent 217 passed /
1 warning in 12.00s. One P2: the reader advertised close on indeterminate
cycles but a null head failed request validation and corrupt ownership failed
the command. Initial reviewer evidence was static; author independently
reproduced three failing close cases and one refusal-code mismatch, with one
already-green missing-checkpoint control (4 failed / 1 passed). Correction
**fixed-in `b5807ad`**: required nullable checkpoint CAS, lifecycle-only close,
and cycle-owned event lookup retained for optional declarations. No checkpoint
or version association is repaired. Exact five probes then passed.

Scoped review round 2/2 inspected **only `b350bee..b5807ad`**, five paths,
55 additions / 5 deletions; fresh model smoke again MODEL_OK. Session
`ses_eb0176968ffeeC4zVBHkZRqrVq`: P2-1 CLOSED, READY for M3a only, zero open
P1/P2. Independent focused contour: **222 passed, 1 warning in 13.70s**;
author same contour: **222 passed, 1 warning in 14.21s**. Reviewer limitations:
no web build/Ruff/native review/M1 rerun, only the named synthetic test command.
Both reviews were read-only with clean git status before/after; postflight ps
matched no remaining M3a review process. No further full-diff review is needed.

Non-blocking dispositions from consolidated round 1, in writing:
suggestion 1 **disputed**: unknown save completion remains retryable with the
same ID under the approved safe-error contract; only proven corrupt data is
non-retryable. Suggestion 2 **disputed**: ASR-MOD-3 and TypeScript structural
typing permit extra stored-event fields; declared date/label/priority and core
keys are covered by conformance, future fields can be typed at M4 consumption.
Suggestion 3 **follow-up #693** for later metadata hardening, not a new blocker:
NaN constraint metadata already failed the old JSON response without any
fingerprint. Cheap author falsifying check constructing JSONResponse with the
old metadata-shaped payload raises the same ValueError. No corrupt metadata is
silently repaired/dropped in this slice. Round 2 accepted these as triaged.

Final M3a checks on `b5807ad`: Ruff, git diff --check, web lint/build and
contract:extract --check GREEN. Final contributor-safe contour:

    ai_trainer_env/bin/python -m pytest -q -m 'not live and not debug and not e2e' tests/ --ignore=tests/smoke/test_planning_cycle_projection.py --ignore=tests/smoke/test_planning_cycle_build.py --ignore=tests/smoke/test_planning_cycle_identity.py --tb=short
    # 3502 passed, 14 skipped, 64 deselected, 7 warnings in 294.97s.

The 14 skips are the same pre-existing fixture regeneration, optional garth and
restricted socket/process cases as M2. No S2 assertion was skipped/xfail. The
three incomplete M1 RED modules remain
explicitly excluded from that contributor contour and independently measured
as 19 failed / 25 passed; no whole-S2/CI/merge readiness is claimed.

Publication: draft [#697](https://github.com/rbctmz/ai_trainer/pull/697), stacked
on [#696](https://github.com/rbctmz/ai_trainer/pull/696), attached to this task.
Reviewed runtime commits: `b350bee`, P2 correction `b5807ad`; the final docs-only
commit records evidence without changing that reviewed runtime. Handoff remains
Domain / API Implementer for M3b: freeze lifecycle build fields/API↔TS fixtures,
retain v2 cycle_context_json in the S1 artifact, reject pending v1 but replay
applied v1 unchanged, reserve target UUID/namespace once, clip new prescriptions
at actual start, and atomically publish checkpoint/map/cycles/selection/settings/
receipt/Coach approval. Then M3c must cover every writer family before M4 UI
acceptance. No new full-diff review of M3a and no standalone merge are needed.

## Context and Orientation

Shared Python in models/services/data owns domain meaning; FastAPI api/ and
Next.js web/ are the primary product path under ADR-0001. Streamlit remains a
supported fallback; its cached state cannot become the new lifecycle contract.
The single-athlete SQLite cache contains append-only planning_checkpoints JSON,
activities, matching/feedback and delivery records. Existing S1 captures coherent
dependencies, retains exact prepared bytes and confirms them atomically through
data/planning_build_preview_store.py. It currently determines currentness from
the latest checkpoint, which S2 must replace with selected cycle/head semantics.

Current public readers are api/planning_service.py current_status,
active_plan_overview and planning_edit_context; web/components/planning/PlanBuilder.tsx
hydrates its edit inputs. api/today_snapshot.py and models/ai_tools.py also choose
latest directly. History operations, services/session_projection.py and
api/session_feedback.py require explicit historical ID access even after closing
a cycle. The spec's caller table assigns each path to current, historical or
guarded writer semantics; implementers must freeze an exact inventory in M1.

## Plan of Work

### M0 — specify and check the boundary

Publish this plan, the companion slice spec and the ASR catalog entry after a
read-only independent spec check. Checker inspects the complete proposal against
#693/#677, especially lifecycle-vs-participation, unknown legacy ownership,
history, writer bypasses, S1 compatibility and reset/replay. One consolidated
review and one scoped correction at most. Record every finding with observed,
inferred, verified and disposition; no hypothetical blocker without an invariant.

### M1 — reproduce before replacing selectors

Explicit M0→M1 task handoff: Spec / Architecture Owner has completed the reviewed
contract. Next role is Domain / API Implementer, beginning with
tests/smoke/test_planning_cycle_projection.py,
tests/smoke/test_planning_cycle_build.py and
tests/smoke/test_planning_cycle_identity.py plus an inventory fixture. The first
bounded checkpoint contains behavioral/preliminary protocol RED and unchanged
S1/history characterization, no schema/UI implementation. Required inputs are
this plan, the accepted slice spec at `a2f3848`, baseline `93fa4f4` and #693 ACs.
The completed independent review does not mean any lifecycle test is GREEN.

Add pure projection/command/build/store tests named in the slice matrix and a
fixture inventory of every current-plan read/write family. Record true behavioral
RED for ended/current selection, old calendar carry-over, close/replacement/retry
and unknown scope. Missing new interfaces are preliminary protocol RED, not
evidence of transaction correctness. Characterize unchanged checkpoint JSON,
activities, matches, feedback and delivery history; do not regenerate S1 oracles
to accommodate unrelated changes. Commit/push a bounded RED checkpoint.

Add test_planning_cycle_identity.py for overlapping identical/changed modern
cycles, legacy IDs, same-cycle edits/restores, multisport legs and historical
feedback/match/delivery keys. start_new must never reuse a prior cycle donor or
replacement chain; preview/retry must retain the same reserved namespace/IDs.

### M2 — own cycle state and import legacy safely

Create models/planning_cycle.py, data/planning_cycles.py and
services/planning_cycles.py with additive tables/constraint columns initialized
from data/database.py. Implement idempotent migration and the explicit selector
on connection-bound reads. Prove no GET writes, empty/closed-null does not
reimport, malformed latest does not fabricate dates, and backup/reset/restart
preserve/remove precisely the intended new state. Keep raw history access and
ledger bytes unchanged. This is storage/projection readiness, not final delivery.

### M3 — commands and exact confirmed new cycle

Implement three reviewable parts in order: M3a commands/contracts, M3b retained
build publication and identity, then M3c writer-family adaptation. These divide
implementation evidence without changing approved scope or allowing an
intermediate draft to merge. M4 still owns current-reader/UI integration.

Define api/planning_cycle_contract.py and the cycle router before runtime
adapters; add API/TS fixtures and regenerate contracts. Implement strict
close/outcome/constraint-scope commands with retained same-ID results. Extend
S1 with frozen v2 lifecycle ownership, start_date and explicit replacement.
Keep v1 successful replay; reject v1 pending. Generate outside locks; commit old
closure, new cycle/checkpoint/map/selection, settings, receipt and Coach status
together. Test all fault points and real writer races. Adapt every mutation
family to the selected-cycle CAS or explicit historical exception. No raw facade,
legacy cache or provider sync can choose/reopen a cycle implicitly.

### M4 — current/history integration and UI handoff

Domain/API owner wires shared current context into Planning/Today/Coach and
separates checkpoint/session-bound history consumers. Delivery exits without a
provider call when no actionable cycle; no delivery algorithm is added. Legacy
Streamlit changes are compatibility guards and clear read-only messages only.
Close/switch cannot erase old activity or session-feedback access.

Stop at an explicit Domain→UI handoff with schema, named fixtures and allowed
actions. UI / Design role then adds minimal close/outcome/new-start operations,
canonical build-context hydration and cycle-aware history controls. UI renders
server state/reasons/period, retaining S1 uncertainty ownership; it does not
calculate cycle status or migrate data. Use existing tokens/components and the
spec's responsibility brief. Verify complete journeys, keyboard and narrow/
intermediate/desktop widths in both themes using the temporary web fixture.

### M5 — accept one complete delivery

Run targeted lifecycle/S1/history/constraint tests, contributor-safe suite,
Ruff, API/TS extractor/inventory, web lint/build and isolated full browser checks.
All real data/providers remain disabled. Collect a complete AC1–AC10 bundle and
one final candidate against current main. Do not merge intermediate RED branches.
Independent implementation/native review observes its two-round stop rule;
explicit human acceptance, fresh current-head gates and CLEAN precede merge.
Record post-merge proof/metrics and clean only this task's safe artifacts. Parent
#677 retains S3/S4; deploying to the athlete's running instance is not implied.

## Concrete Steps

Run from `/Users/gregkisel/Developer/ai_trainer`. Start with git status and fetch
origin; do not mix uncommitted work. S1 post-merge docs #692 are independent and
must not be silently amended/merged as part of S2. Use codex/ branches.

Baseline already executed:

    ./ai_trainer_env/bin/python -m pytest tests/smoke/test_api_planning.py tests/smoke/test_planning_active_plan_overview.py tests/smoke/test_planning_build_confirmation.py -q --tb=short

Observed 89 passed, 1 existing Starlette/httpx warning in 7.66s.
To repeat the falsifying probe, use the existing synthetic helpers and real
planning functions; all persistence is under TemporaryDirectory:

    from datetime import date, datetime
    from pathlib import Path
    from tempfile import TemporaryDirectory
    import json
    from pytest import MonkeyPatch
    from api import planning_service as ps
    from data.planning_build_preview_store import get_preview
    from models.planning_build_confirmation import BuildParameters
    from models.planning_checkpoints import restore_goal_plan_from_checkpoint
    from tests.smoke._planning_build_confirmation import pin_clock, protected_state, seeded_db

    with TemporaryDirectory() as tmp, MonkeyPatch.context() as mp:
        pin_clock(mp)
        mp.setattr(ps, 'datetime', datetime)
        mp.setattr(ps, 'athlete_local_date', lambda: date(2026, 10, 16))
        db = seeded_db(Path(tmp))
        ps.build_plan(db, goal_type='triathlon', distance='olympic',
            event_date='2026-10-04', start_week=date(2026, 8, 3),
            planning_mode='event_goal', available_hours=10, persist=True)
        before = protected_state(db)
        print(ps.current_status(db)['has_plan'], ps.active_plan_overview(db)['current_week'])
        inherited = dict(ps.planning_edit_context(db)['inputs'],
            planning_mode='training_goal', event_date=None, manual_phases=None)
        for params in [inherited, dict(inherited, start_week=None, events=[])]:
            built = ps.prepare_plan_build(db,
                parameters=BuildParameters.from_mapping(params), origin='planning_ui')
            row = get_preview(db, built['confirmation']['preview_id'], origin='planning_ui')
            days = ps.plan_days(restore_goal_plan_from_checkpoint(json.loads(row['checkpoint_json'])))
            print(built['parameters']['start_week'], built['parameters']['events'],
                sum(day['date'] < '2026-10-16' and bool(day['sessions']) for day in days))
        assert protected_state(db) == before

Capture the final code inventory with:

    rg -n 'get_latest_planning_checkpoint|save_planning_checkpoint|_insert_planning_checkpoint|commit_coach_plan_mutation' api models services data utils state ui --glob '*.py'

Future final verification commands are the normal contributor-safe pytest mark
expression, not bare pytest; use `npm --prefix web run contract:extract`,
`npm --prefix web run contract:extract -- --check`, contract inventory and tests,
`npm --prefix web run lint` / `build`, and `python -m pytest -m e2e tests/e2e -q`.
Run only named new files after adding them; a planned command is not execution.

## Validation and Acceptance

AC1–AC10 are observable in the companion matrix. The main demo is expired unknown
participation → close without declaring a result → history preserved → new
start_date on Friday → no earlier executable assignments → preview Cancel
leaves selection unchanged → confirm once → dropped response and same-ID retry
return that cycle, with no duplicate/new closure. Also cover replacement without
separate close, early close, future start/gap, no-event rolling plan, explicit DNS
and correction, legacy unknown bounds, stale scope and preserved historical fact
links. Three surfaces must agree on cycle identity and allowed actions.

Migration twice, reset twice, reopen, Backup API restore, malformed records,
v1 pending/applied receipts and all mutation-family guards must have runtime
proof. Inject errors after each write and use two independent SQLite connections
for race ordering. No test passes by skipping a known S2 failure or mutating a
past payload just to satisfy the new selector. Report original S1 equivalence
separately from intentionally changed new-start calendar behavior.

## Idempotence and Recovery

No personal SQLite is read or written in these commands. Use isolated test DBs,
synthetic snapshots and disabled providers. Successful command receipts and S1
build receipts own retries; unknown network result retains the same identity.
Migration/init is transactional and once-only; reset removes all cycle/command/
preview rows and prevents a reopened reader from importing old state again.

Live operators must stop all writers and use scripts/sqlite_backup_restore.py
before additive migration/restore. A pre-cycle binary is unsafe for downgrade:
it may read raw MAX and write/deliver a closed plan. Disable writes/delivery and
fix forward or deploy an explicitly compatible rejection bridge; preserve new
rows/receipts. This is a handoff procedure, not a performed live operation.

## Artifacts and Notes

Synthetic baseline on 93fa4f4, athlete day 2026-10-16: expired progress 9/9,
current phase Race Week; inherited training preview Aug 3–Sep 27 with old Oct 4
event and 48 past/0 future executable days; clean preview Oct 12–Dec 6 with 2
past executable days. No checkpoint/settings change during reads/previews.
Issue #693 holds sanitized observed/inferred/verified evidence and the same
89-test baseline. Counts are fixture measurements and must not become goldens.

## Interfaces and Dependencies

Introduce pure `project_cycle_context(record, *, athlete_day, timezone)` in
models/planning_cycle.py; Database adds current/connection-bound selectors while
raw latest/history access stays unchanged. Store helpers accept caller-owned
connections for lifecycle-bound checkpoint commits. Services own build context,
strict commands and allowed actions; api adapters validate/translate safe codes.
No new provider/package is required.

S1 schema/protocol v2 additions and v1 receipt read compatibility must be
contract-first; client owns only received identities/CAS fields and explicit
action choice. Selection revision guards close→new and other same-checkpoint ABA
changes. Existing calendar/training calculation remains shared, with a canonical
actual-start floor and exact affected projections. Historical ledgers keep their
old identity keys and are not rebound to the new cycle by selection.
Modern session identity is the versioned hash of cycle UUID plus canonical
content/date/occurrence. Legacy import keeps v1 identities. New initial checkpoint
parent is null; lifecycle source context separately records the replaced cycle.
No continuity reader may traverse a parent/donor edge into another cycle.

## ASR / risk traceability

ASR-REL-1/2, MOD-2/3 and DEP-2 are affected; ADR-0001 reused. Update the ASR
catalog's planned S2 entry and retain this distinction from runtime GREEN.
Principal risks: unguarded writer bypass, fabricated legacy grouping, history
becoming current, missing athlete constraint ownership and new-start backdating.
The prescribed mitigation is shared selection, conservative migration, atomic
CAS/replay, explicit scope resolution and focused failure/boundary tests.

Revision note (2026-10-17): created a separately tracked S2 after merged S1,
verified the reported lifecycle/calendar gaps on temporary SQLite and recorded
the full Class A implementation/review sequence. No product code changed.

Revision note (2026-10-17, spec round 1 correction): one blocking P2 under AC3/6
required explicit cross-cycle session/leg identity and lineage rules. Reproduced
current content-ID behavior with a pure synthetic probe, preserved that legacy
contract and specified modern namespacing plus matching/history/retry tests.
Completed explicit evidence/findings/verdict sections. Scoped check next;
no runtime, provider or personal DB change and no extra full review requested.

Revision note (2026-10-17, spec accepted): scoped round 2/2 checked only the
`a4647fd..a2f3848` correction and returned READY, zero blockers, clean branch
before/after. Spec review budget exhausted normally; no further full review.
This final metadata update records that verdict and the exact Domain/API M1
handoff, not a new implementation change. Draft publication and #693/#677 status
links are recorded externally after push. Human merge/rollout remains separate.
