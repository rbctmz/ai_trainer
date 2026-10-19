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
- [x] (2026-10-18) M3b: S1 v2 start_new/edit_current, calendar/identity boundary and atomic replacement; applied-v1 replay retained, pending-v1 rejected. Independent round 1/2 READY at `5f5d2dd`, 473 focused GREEN; contributor-safe 3591 passed / 14 skipped / 68 deselected with only four known M4 assertions excluded beyond standard markers. Intermediate draft only.
- [x] (2026-10-19) M3c: every prescription writer uses selected-cycle/head CAS under the writer lock; explicit restore ownership. Independent round 1/2 READY at `cc8d900`, 642 focused GREEN; pinned contributor-safe 3645 passed / 14 skipped / 68 deselected with the same four M4 reader exclusions. Published/attached as intermediate draft #699, stacked on #698.
- [x] (2026-10-18–19) M3c on codex/issue-693-m3c-writer-guards, stacked on M3b #698: shared write guard, all mutation families/restore/Coach/legacy compatibility, synthetic fixture adaptation, 54 new writer cases and independent review completed. Class A; approved scope unchanged.
- [x] (2026-10-19) M4: shared current/history readers and explicit Domain→UI handoff completed. Draft #700; all five P2 CLOSED at 32ef3c3, new provenance proof CLOSED at aeff866. Final contributor-safe 3665 GREEN, 36 isolated browser GREEN; native/whole-S2/human gates remain M5.
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

Decision (2026-10-18, M3b Domain/API): public lifecycle action is spelled `action`.
All context fields are explicitly supplied; missing action gives
cycle_context_required, never an inferred new cycle/edit. Keep original resolved
parameters shape; reserve lifecycle UUID once outside publication and freeze it
in dependency_context_json, cycle_context_json and response.lifecycle. Recheck
reuses that same UUID. S1 canonical/payload/receipt algorithms for v1 remain
unchanged; v2 adds cycle_context_json to payload hashing. Pending v1 is readable
but not eligible for apply/bind; applied v1 validates/replays in its own schema.
The old raw build facade and pure v1 calculator stay temporary internal paths
until M3c, with no HTTP escape flag.

Decision (2026-10-18, M3b Domain/API): remove canonical day/template pairs before
actual start, regroup partial weeks by actual calendar dates, and derive affected
totals/audit/forecast from that result. The existing position-based weekly helper
is called on each calendar bucket; a shortened first week is never treated as
seven days. Forecast starts at captured athlete day with zero-load gap to a
scheduled start; it does not resimulate immutable past prescriptions. Edit
preserves cycle start and copies saved past prescriptions/IDs, limiting new
assignments to the remaining stored period. No post-A extension/recovery.

Decision (2026-10-18, M3b Domain/API): v2 material fingerprints include the
canonical UUID namespace; embedded IDs carry session_identity_namespace. A
different/missing stamp cannot donate IDs or replaces/parent lineage to a new
namespace. Day, nested session and composite-leg keys are separated; legacy v1
material tuples/IDs remain exact. Checkpoint snapshots retain identity_namespace
through restore. start_new has no checkpoint parent; source/closure IDs remain
only lifecycle audit/comparison context. Same-cycle edit retains donor identity.

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

### M3b — author checkpoint (2026-10-18)

Role Domain / API Implementer, Class A; branch codex/issue-693-m3b-cycle-build
stacks on M3a #697 (`aedba20`). Approved specification unchanged. Added
services/planning_cycle_build.py for coherent build form context, expected
selection/cycle CAS, known constraint ownership and actual calendar bounds.
Public build/confirm use v2 lifecycle with v1 successful replay retained;
planning_build_previews gains nullable cycle_context_json, leaving every v1
payload/receipt byte and digest definition intact. Under the S1 writer lock,
checkpoint/map, old closure/new cycle or same-cycle edit, selection, settings,
receipt and Coach approval commit together. No provider/live cache calls.

Observed / Verified by: original M1 identity contour was 11 failed / 4 passed;
after namespace/checkpoint support it became GREEN, including historical
feedback/match separation and local delivery external keys. Four existing M1
build/calendar/context RED are now GREEN. A new nested composite-leg control
also checks a stale foreign-cycle template cannot donate leg IDs.

S1 test adaptation is explicit: public preview fixtures supply full v2 context;
legacy first/existing calculation golden fixtures call the pure v1 capture /
calculator and low-level retained storage, without a public trusted flag. The
original complete M1 calculation JSON oracle is unchanged. Existing raw history
appends no longer represent a selected-state change: stale-writer fixtures now
advance the selection revision or confirm a real competing cycle. Future
constraint deactivation is tested in-range; an elapsed constraint is deliberately
not a new prescription dependency. Actor/fault/replay assertions remain intact.
Coach schemas and marker fixtures pass explicit lifecycle fields; the marker
parser understands literal true/false/null for those existing typed inputs.
An unbound tool call is refused, never silently assigned replacement consent.

Intermediate checks: 203 prior S1 tests GREEN (7 existing warnings); 94
Coach/v2/log/native tests GREEN before final additions; 37 Planning/onboarding/
mocked-Intervals/history tests GREEN. Current frozen M1 contour is **4 failed /
41 passed**: only overview current-phase/status and close test's final /status
reader assertion remain M4. No M1 assertion is weakened/skipped. All other
writer-family guards remain M3c; these are not whole-S2/CI/merge results.

Final author verification: 473 focused tests passed (7 warnings) in 67.86s;
contributor-safe contour passed 3591 / skipped 14 / deselected 68 in 306.98s.
The latter excludes only the four known M4 reader assertions above, in addition
to the standard live/debug/e2e marker exclusions. Full-repository Ruff,
git diff --check, web lint/build and generated contract freshness passed.
Independent review and publication follow below; this is not whole-S2 acceptance.

### M3b independent review and handoff (2026-10-18)

OpenCode 1.1.30 plan agent, fresh MODEL_OK from deepseek/deepseek-flash,
session `ses_eaf50776cffev2WRTi64jAlQH0`, reviewed exact
`aedba207c77b4d49cbdc025e95be3809988e50fd..5f5d2ddc8fe7d319266deb090ce4d0699bf5e627`.
It inspected every changed runtime/transport path, changed S1 and new lifecycle
tests, approved spec and relevant ASR/ExecPlan; generated TS artifact inspected
selectively for the new schemas. Verdict READY for M3b handoff, zero P1/blocking
P2. Independent allowed focused command returned 473 passed / 7 warnings in
66.34s; broad/web checks were author-only, not independently repeated. Suspected
legacy-edit undercount was falsified: checkpoint restoration normalizes nested
sessions before calendar regrouping. No blocking correction or second full
review requested. Before/after git status clean; no remaining reviewer process.
The reviewer performed no edits, issues/comments, approvals or merge.

All four suggestions are `follow-up #693`, not open-branch merge gates:
add edit_current build-context registry coverage (Observed: current registry
lists only start_new); add explicit legacy-edit weekly accounting assertions
(Observed: current edit test verifies exact past daily/template preservation);
preserve constraint_ids in Coach tool errors (Observed: HTTP preserves context,
AITools returns only code/error; M3c handoff); check displayed event dates and
weeks_to_race when an edit shortens its period (Inferred metadata risk, no
reproduced M3b invariant violation; diagnose before M4 display). These are
separate from the four known M1 RED reader assertions assigned to M4.

Reproducible final commands:

    ai_trainer_env/bin/python -m pytest -q tests/smoke/test_planning_cycle_build_v2.py tests/smoke/test_planning_cycle_identity.py tests/smoke/test_planning_cycle_commands.py tests/smoke/test_planning_cycle_storage.py tests/smoke/test_planning_cycle_characterization.py tests/smoke/test_planning_build_confirmation.py tests/smoke/test_planning_build_confirmation_storage.py tests/smoke/test_planning_build_preparation.py tests/smoke/test_planning_build_preview_store.py tests/smoke/test_planning_build_commit.py tests/smoke/test_planning_build_coach_confirmation.py tests/smoke/test_web_contract_drift.py tests/smoke/test_contract_extractor.py tests/smoke/test_api_call_inventory.py --tb=short
    ai_trainer_env/bin/python -m pytest -q -m 'not live and not debug and not e2e' tests/ --deselect=tests/smoke/test_planning_cycle_projection.py::test_behavior_phase_is_not_current_outside_period --deselect=tests/smoke/test_planning_cycle_projection.py::test_protocol_status_has_readable_but_not_actionable_ended_plan --deselect=tests/smoke/test_planning_cycle_build.py::test_protocol_close_retry_keeps_history_and_null_selection_after_restart --tb=short
    ai_trainer_env/bin/python -m ruff check .
    npm --prefix web run lint
    npm --prefix web run build
    npm --prefix web run contract:extract -- --check
    git diff --check

Next role remains Domain / API Implementer for M3c. Start from the immutable M1
caller/SQL inventory and guard shared persistence plus demand, adjustment,
recovery, constraint/repair, restore and Coach/legacy writers under the selected
cycle/head CAS; keep explicit historical exceptions and provider calls outside
the transaction. Do not make raw history or a cached plan select/reopen a cycle.
Then hand shared readers/transport semantics to M4 before any screen work.
This evidence-only documentation update does not change reviewed runtime.

Publication: [draft #698](https://github.com/rbctmz/ai_trainer/pull/698), stacked
on #697, attached to the task. Progress and all four non-blocking follow-ups are
recorded in [issue #693](https://github.com/rbctmz/ai_trainer/issues/693#issuecomment-6254877507).
GitHub CI was still running at publication; no native/final M5 readiness or
merge is claimed. The known M4 reader RED are deliberately retained.
Observed review-gate refusal at the published documentation head: no submitted
native review for the current head (run 39164275124). No acceptance label or
waiver is added; final native review remains M5.

### M3c — author checkpoint (2026-10-19)

Role Domain / API Implementer, Class A, branch codex/issue-693-m3c-writer-guards
stacked on M3b #698 (`5bd782e`). Approved spec/AC and the frozen M1 inventory are
unchanged. New data/planning_cycle_writes.py captures selected cycle/head,
selection and cycle revisions, athlete day and a constraint-row digest in one
read transaction; guard_write compares them under BEGIN IMMEDIATE. Child
checkpoint, immutable ownership mapping, cycle head/revision and demand settings
commit or roll back together. Namespace, version parent, restore source ownership
and actual bounds are checked before publication. Raw public save without
context and the unbound legacy build facade refuse without settings/plan writes.

All prescription-writer families now use that boundary: demand rebuild,
execution adjustment, weekly/bike rebalance, recovery downgrade/transfer/
rollback, materialization/day repair, history restore and Coach constraint
create/retract. Their calculation reads use the selected immutable checkpoint,
not MAX(history.id). Existing preview fingerprints include the captured cycle
token; pending recovery/constraint proposals retain it. Recovery publication
rechecks it under its own writer lock, and the report accepts an explicit
captured checkpoint so report generation cannot silently choose another cycle.
All provider/model computation remains outside the writer transaction.

Restore retains its existing confirm protocol and now requires explicit expected
cycle/selection revisions. Known same-cycle versions are permitted; unassigned
legacy history additionally requires restore_legacy_version in the selected open
legacy-import cycle, with no modern-cycle record. The old source stays
unassigned; the restored child is mapped. Donor/repair ancestry stops at a
missing or different immutable owner. Cycle-scoped constraints cannot be
applied/retracted as another cycle's prescription. Athlete-wide conditions may
be recorded without an actionable cycle, with no historical reactivation.

API/TS requests for adjust/constraint/repair/restore carry the expected selected
context; missing old-tab fields require refresh. These DTOs are the M4 handoff,
not screen wiring. Legacy cached saves fail with an explicit web-plan message.
The system demo seeds through retained v2. Empty synthetic evaluation/parity
databases use private one-time legacy initialization; production has no trusted
HTTP flag. The repair CLI uses a read-only adapter for diagnostics; a genuine
pre-migration file may be inspected as explicitly historical, without importing
or following unknown ancestry. Applying a repair always uses the selected guard.

Test adaptation is explicit: tests/planning_fixtures.py seeds deliberate
synthetic cycles/versions or unassigned history instead of weakening runtime
save guards. Pure v1 calculation goldens are unchanged, not regenerated.
Historical July/August mutation fixtures pin their athlete day; no production
clock/as_of escape is introduced. Existing actor/rollback/identity and full-JSON
assertions remain. The M3b Coach error-context suggestion is implemented by
preserving safe exception.context, including constraint_ids.

Observed / Verified by: the initial six writer regressions failed on the old
raw-save/closed-cycle paths and are GREEN with the shared guard. An additional
modern partial-week adjustment reproduced cycle_not_current because the old
rebuild expanded the date range to Monday. Reusing the S2 calendar boundary,
namespace/donor rules and forecast input fixes that case without new training
formulas. The expanded writer contour is 54 GREEN, including all twelve
families after close, calendar end and replacement; same-head outcome/scope
changes, real two-connection close-vs-child, mapping rollback, legacy/same-cycle/
cross-cycle restore, HTTP CAS and athlete-only ledger behavior. Intermediate
focused contour before the expanded switch/fault cases: 629 passed / 7 warnings
in 79.25s. Web lint/build, contract freshness, Ruff and diff check passed.
The original M1 projection/build/identity contour remains exactly four M4
reader RED / 41 GREEN. The contributor-safe run before those final thirteen
cases passed 3632 / skipped 14 / deselected 68 in 269.75s, with only the four
known M4 assertions excluded beyond standard markers. Final rerun on the pinned
review commit and independent review follow;
no whole-S2, native-review, merge or live-rollout readiness is claimed.

### M3c independent review and handoff (2026-10-19)

OpenCode 1.1.30 plan agent, verified fresh MODEL_OK from
deepseek/deepseek-flash, session `ses_eaf1dd21bffeQV8AHleQQgq5MJ`, reviewed exact
`5bd782e28501b023f6fd88d6961c6fb3f5d05ef6..cc8d900236cd1f52a06f6572b7864b04c0402a06`.
All 74 changed paths were in scope, including runtime/contract changes, private
synthetic initialization and test adaptations; generated TS artifact inspected
selectively. Verdict READY for M3c only, no P1/blocking P2. Its approved focused
command independently returned 642 passed / 7 warnings in 73.79s. Pinned author
contributor-safe run returned 3645 passed / 14 skipped / 68 deselected in 274.87s;
Ruff, web lint/build, contract freshness and diff check passed. Author broad/web
results were not independently repeated. Reviewer checkout clean before/after,
no repository edits or external publications, no remaining M3c review process.
One full round of the two-round budget used; no extra full review requested.

Suggestion 1 is `follow-up #693`, Domain/API owner in M4 contract polish:
Observed by static branch ordering, unknown restore checkpoint currently yields
409 cycle_not_current before the not-found branch, while the existing docstring
promises 422. No state change or AC7 violation was reproduced.

Suggestion 2 is `follow-up #693`, Domain/API owner in M4/M5 evidence: the shared
legacy evidence_bytes helper deliberately covers original checkpoints/facts/
settings, not lifecycle/constraint rows. Add a writer-specific complete state
snapshot, captured expected restore context and explicit Coach retract/commit
coverage. Do not globally change that helper's meaning: M3a uses it to prove
original history remains unchanged during legitimate lifecycle metadata writes.
Current tests separately check head/revision and constraints in specific cases;
the suggestion is a coverage gap, not a reproduced partial mutation.

Suggestion 3 is `follow-up #693`, Domain/API owner: low-level Coach commit can
accept athlete scope carrying a non-null cycle_id. Public preview normalizes
athlete scope to cycle_id=None, so no public bypass was found. Add the symmetric
internal validation as defense in depth.

Suggestion 4 is `fixed-in cb219d9`: removed duplicate pin_day setup from the
reconciliation identity test. The exact affected test passed (1 in 0.95s),
Ruff/diff check passed, and runtime remains byte-identical to the reviewed
cc8d900. This fixture-only correction does not require another full audit.

Reproducible independent focused command:

    ai_trainer_env/bin/python -m pytest -q tests/smoke/test_planning_cycle_writer_guards.py tests/smoke/test_planning_cycle_build_v2.py tests/smoke/test_planning_cycle_commands.py tests/smoke/test_planning_cycle_storage.py tests/smoke/test_planning_cycle_identity.py tests/smoke/test_coach_constraint_mutation_gate.py tests/smoke/test_constraint_retraction.py tests/smoke/test_coach_constraints.py tests/smoke/test_planning_history_restore.py tests/smoke/test_planning_demand_change.py tests/smoke/test_recovery_replan_loop.py tests/smoke/test_recovery_replan_materialization_p1.py tests/smoke/test_planning_build_confirmation.py tests/smoke/test_planning_build_preparation.py tests/smoke/test_planning_build_commit.py tests/smoke/test_planning_build_preview_store.py tests/smoke/test_planning_build_coach_confirmation.py tests/smoke/test_planning_cycle_characterization.py tests/smoke/test_web_contract_drift.py tests/smoke/test_api_call_inventory.py tests/smoke/test_contract_extractor.py --tb=short

The contributor-safe command is the M3b command above, with the same standard
markers and exactly four M4 assertions deselected. The unchanged M1 boundary
was independently exercised by the author: 4 failed / 41 passed. Full S2, native
review and merge remain M5, with no acceptance label/waiver or live rollout.

Handoff to Domain/API for M4: wire shared current/history semantics into status,
overview, Planning/Today/Coach and historical fact consumers; guard provider
delivery before provider I/O. Then hand CycleContext, allowed actions and the
new expected-context mutation DTOs to UI/Design for screen integration and
isolated browser acceptance. These are not implemented by this intermediate PR.

Publication: [draft #699](https://github.com/rbctmz/ai_trainer/pull/699), stacked
on #698 and attached to the task. Results and every review disposition are in
[issue #693](https://github.com/rbctmz/ai_trainer/issues/693#issuecomment-6255425137).
GitHub contributor-safe/E2E CI was still running at publication; contract and
secret checks passed. Review gate has no submitted native review for the
published head (run 39168408933); no acceptance label/waiver is added. Native
review, complete M4 acceptance and human merge remain M5. No merge performed.

## Context and Orientation

M3c implementation boundary: capture selected cycle ID, cycle revision,
selection revision and head in one read transaction before calculation. The
shared child commit rechecks all four under BEGIN IMMEDIATE, checks immutable
ownership/namespace/parent and appends mapping/head atomically. No raw public
save or legacy build may create/select a cycle. Existing proposal fingerprints
include captured cycle revisions; close/switch/outcome invalidates old proposals
even when raw latest ID is unchanged. New constraints explicitly retain athlete
or selected-cycle scope. Restore keeps its existing confirm protocol, extended
with expected cycle/selection revisions and explicit restore_legacy_version
acknowledgement; unassigned legacy source rows stay unassigned. Test fixtures
use explicit synthetic initialization rather than weakening production guards.
M4 reader/UI and provider-delivery adaptation remain a later clean handoff.

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

### M4 Domain → UI handoff (2026-10-19)

User explicitly authorized M4 shared readers, then UI. Domain/API owns the
first slice on `codex/issue-693-m4-readers-ui`, based on M3c `452ac71`.
`services/planning_cycles.py::current_plan_snapshot` now captures CycleContext
and its readable selected checkpoint in one read transaction. Status, overview,
edit, Today and Coach consume selection; explicit session/checkpoint history
keeps factual projections and corrections available after closure. Delivery
checks actionable selection before obtaining a provider. Raw MAX/history and
private v1 characterization paths remain raw, never selection fallbacks.

Observed: the four original M1 reader assertions now pass (projection/build
29 GREEN). New tests initially reproduced missing Coach cycle_context and loss
of explicit session projection after close; one new status assertion used the
wrong existing summary key (`id` instead of `checkpoint_id`) and was corrected
as a harness error. Provider tests added after its guard are characterization,
not claimed RED. Boundary rerun: 132 passed, including original M1, Coach,
Today and historical facts; expanded domain/broad checks are still running.
Historical July/October Today/provider fixtures explicitly pin the athlete
clock; no runtime `today=` override bypasses the lifecycle clock.

Clean role handoff: UI / Design Specialist consumes existing CycleContext,
CycleBuildContext, expected-context mutation DTOs and CycleCommandResponse
from `web/lib/types.ts` / `web/lib/planningCycles.ts`. History gains additive
server-owned cycle_id/can_restore/restore_action hints and cycle_context;
confirm still checks ownership/CAS. No API semantics/acceptance/CSS decision is
inferred in the browser. Implementation validation may hand a reproduced
contract defect back to Domain/API explicitly.

UI brief (Class A, same AC1–AC10, no new product scope): athlete sees actual
period/state first, can close without declaring an outcome, inspect history,
correct an explicit event declaration and start a fresh cycle. Expand existing
Planning panel, four-step builder and history using existing surface/ink/accent
tokens. Start-new uses canonical inputs, explicit goal/intent choice, actual
start date and explicit replacement acknowledgement; edit uses saved inputs.
Preview/cancel remains read-only. Retain original command/preview identity on
unknown outcome, lock reset/navigation until resolved. Today/Coach render the
same status without interpreting dates. Unknown constraint scope is explicit
and offers only athlete/known-cycle resolution.

Named acceptance journeys: expired_unknown_close; close_with_dns; historical
outcome_correction; start_new_clean/cancel/confirm; replacement_acknowledgement;
close_lost_response_same_command; build_lost_response_same_preview; empty and
indeterminate; scope_conflict. Use temporary SQLite/web stack only. Check
390/900/1280 widths, light/dark, keyboard focus and screenshots. No user
observation/UX acceptance or complete M4 result is claimed yet.

### M4 implementation checkpoint (2026-10-19, review pending)

Domain/API completed readers before the UI handoff above. UI/Design then wired
CyclePanel and canonical builder hydration; subsequent isolated checks handed
three concrete seams back to Domain/API: the Coach presenter still called an
ended period completed, the legacy cache could reconstruct an inactive plan,
and week reconciliation needed the exact captured checkpoint. Those corrections
consume the same approved semantics, with no new acceptance or domain rule.
The constraints-list response is now mirrored/registered for its existing GET;
edit-context stays supported/tested but leaves the frontend-call registry
because the builder now uses canonical build-context. Original S1 payload and
M1 caller/identity oracles were not regenerated.

Historical distinction: explicit matched historical sessions may refresh factual
recovery episodes without selecting their checkpoint (AC6); the previous test
that rejected every superseded ID now proves this access and unchanged selected
head. A retired, unexecuted session replaced within the selected cycle still
cannot receive fresh feedback by automatic matching. Its existing match-bound
facts remain available. No interventions or prescriptions are created by the
historical reader. Explicit date-based Coach structure inspection may read an
ended selected snapshot; upcoming-workout assignment remains disabled.

Observed / verified: the new lifecycle UI first passed 8/9, exposing a real
reset bug: Cancel cleared hydration state but unchanged SWR data did not rerun
hydration, leaving Next disabled. Corrected cancellation preserves its read-only
draft; an applied/stale reset reloads context explicitly. Repeated new builders
use distinct read identities so a cached old selection cannot hydrate a fresh
new-cycle form. Expanded M4 + S1 browser run: 29 passed in 59.12s, synthetic
SQLite/ports, provider credentials disabled. Includes 11 new lifecycle cases:
unknown/DNS closure, historical correction, clean new start, cancel/confirm,
replacement acknowledgement, unknown scope resolution, close/build lost
responses with same identity, 390/900/1280 × light/dark and keyboard controls.
Screenshots live under docs/design/evidence/issue-693; old issue-685 evidence
is preserved. Owner-observed UX acceptance is not claimed.

Read-side author checks: initial projection/build 29 GREEN; expanded domain
431 GREEN; after presenter/cache/contract additions 27 targeted GREEN; calendar,
week boundary and original story checks 69 GREEN. Intermediate broad diagnostics
were run while files changed: 79 failed then 5 failed, with fixture clocks,
removed test seams, one test-local missing variable and contract freshness
corrected explicitly. They are not final current-head evidence. A frozen full
contributor-safe run and exact-ref independent review follow; no known M4 RED
is excluded from the final command. Ruff and web lint/build have passed; final
web check reruns after the final UI change. No rollout, live writes or merge.

M3c nonblocking follow-ups remain assigned in #693: restore error-contract
polish, writer-specific complete state snapshots and low-level athlete-scope
validation are not silently folded into this reader/UI milestone.

M4 frozen runtime author evidence at `f0fa5ce`: the approved independent-review
boundary command is 376 passed / 1 existing warning in 21.87s. Browser rerun on
that runtime: 32 passed / 1 existing warning in 61.00s, after adding three
E2E-only empty/scheduled/indeterminate states; original 29 journeys remain.
The supplementary test/screenshot commit does not alter runtime or contracts.
The read-only checker began from CLEAN f0fa5ce. During its pinned-ref audit the
author added only those three browser cases and regenerated the named synthetic
screenshots; these are author changes, not checker edits. Review budget 1/2 is
in progress. Final contributor-safe command runs without the four old M4
reader exclusions; counts and independent verdict will be recorded below.

M4 author self-review found two additional concrete UI regressions while the
independent first round remained pinned to f0fa5ce. Two new isolated tests
reproduced RED (2 failed / 18 deselected in 26.71s): changing the goal type in
edit_current reset the acknowledgement even though only start_new renders its
checkbox; and after a lost edit confirmation, external close plus SWR refresh
unmounted the builder, losing its retry control and leaving the parent lock.
Narrow UI correction: edit_current keeps its explicit edit eligibility when the
goal changes; a builder owning an unresolved confirmation stays mounted across
null selection. The same two tests now pass (16.66s), including historical
same-preview replay without reselecting the closed cycle. No API/domain change.
This correction will receive only a scoped delta check after the first review.

Frozen contributor-safe run on runtime f0fa5ce is GREEN: 3661 passed / 14 skipped
/ 78 deselected / 7 existing warnings in 279.85s. Only standard not-live,
not-debug, not-e2e markers are used; all original four M4 readers run GREEN.
Additional excluded count is the three new optional E2E states, not a hidden
reader exclusion. The later two-line UI fix needs its own web/browser checks,
not another unchanged Python broad run.

### M4 independent round 1/2 and corrective handoff (2026-10-19)

OpenCode 1.1.30, plan/edit-denied, exact-model MODEL_OK; session
`ses_ead4b2182ffeqVGQf4IgCbwyHM`. Requested immutable `452ac71..f0fa5ce` review;
54 paths (author verified: 42 text, 12 PNG; reviewer split 44/10 was a metadata
count error). Reviewer used git-show for the pinned code, ran only the allowed
376-case command (23.50s), made no edits/posts/approvals, and returned no P1 but
five blocking P2 at f0fa5ce. Author-only movement during review is documented
above; no acceptance of unreviewed runtime is inferred.

Written dispositions, all independently reproduced or checked by the author:

1. Acknowledgements: edit goal dead-end and stale replacement acknowledgement.
   First is fixed-in `6def63c`; the second was reproduced after correcting an
   overly strict screenshot/status locator (harness error), then RED 1 failed
   / 14 deselected (13.75s). Fresh canonical hydration now resets both flags;
   exact case GREEN (10.01s). Correction commit is recorded below.
2. Ended actions/factual correction: static check confirmed DemandControl was
   unconditional and AdjustMode hidden. UI now hides prescription controls for
   non-actionable cycles and exposes factual correction separately, querying
   the saved end date and a bounded history window. One real browser test proves
   a manual historical match succeeds while checkpoint remains unchanged and
   demand/rebalance controls are absent. No provider/replanning action added.
3. Partial ended week: author RED reproduced a Thursday actual end with Friday
   athlete day still labelled current. Reader now forces ended/scheduled
   week/day projections to past/future respectively, with no remaining budget
   on the ended week. Uses shared server state; no browser date calculation.
4. Direct legacy getter: author RED reproduced stale `goal_plan` without first
   touching the combined resolver. Direct access now refreshes shared selection;
   combined accessor consumes that captured cache instead of rereading it.
5. Historical ambiguity: author RED reproduced two closed legacy owners for one
   ID resolving to the newer checkpoint. Helper now refuses multiple owners or
   multiple unassigned rows when neither selection nor a saved match supplies
   context. Explicit `checkpoint_id` is accepted by the existing session-
   projection GET/service; membership is checked, with no selection/write.
   Saved-feedback resolution no longer retries the rejected global candidate
   list. Tests prove missing context is a 404 gap and explicit context resolves
   the original checkpoint after both cycles closed. Modern namespaces/v1 IDs
   and receipt algorithms are unchanged.

The three read-side reproductions were RED together (3 failed, no collection
errors); after correction the focused read/week/comparable/projection contour
is 89 GREEN. Extended lifecycle/history/provider/API contour initially had only
one narrow route-mock signature failure (417 GREEN); the fake now explicitly
asserts forwarding the approved checkpoint query. Contract/inventory/readback
checks: 73 GREEN. A dynamic reconciliation URL gets its existing manual route
annotation, not an inventory exclusion.

Nonblocking suggestions have explicit dispositions: choice re-acknowledgement
when changing other visible fields is `follow-up #693` (UI/Design, S4 polish);
stale build-context recovery without page refresh is `follow-up #693`
(UI/Design + Domain, existing explicit refresh path remains); stale CyclePanel
history after build confirm is fixed in the corrective commit by refreshing
both cycle reads. No extra full-diff review is requested; only the consolidated
correction delta goes to scoped round 2/2. Final broad/web/E2E evidence and SHA
follow. Latest author browser run: 36 GREEN in 73.53s, including all originals
and factual correction, repeated-new acknowledgement, external-close retry.

Scoped round 2/2: same reviewer/session examined `f0fa5ce..32ef3c3`, independently
ran 418 tests GREEN (23.56s), CLOSED all R1–R5 and returned READY for M4 at
32ef3c3, with no new blockers. Author frozen full run on the same runtime:
3664 passed / 14 skipped / 82 deselected / 7 existing warnings in 282.20s.
Ruff, web lint/build and 36-browser run are GREEN. No native/UX/merge approval.

A subsequent author-only falsifying probe supplied fresh risk evidence within
R5: a closed legacy replacement session with a duplicate unassigned row and an
explicit checkpoint projected the correct matched fact, but its inherited
`match_revision_id` was None instead of stored revision #1. Cause verified by
tracing the second independent context lookup in the revision resolver. The
persisted facts/ledger were not changed. A named regression reproduced RED
(1 failed, 14 deselected, 1.02s); the resolver now uses the already-captured
reconciliation checkpoint for inherited revisions instead of resolving the
ambiguous session again. Projection/story contour: 86 GREEN in 4.62s; no UI,
contract, training formula or matching algorithm change. The helper docstring
also now describes its explicit/selected/match-bound ownership policy accurately.

This is fresh reproduced evidence after READY, not a new preference or reopened
full audit. Request only a proof-specific continuation of R5 on the three-line
context correction and its new regression; no additional full-diff round.
A final contributor-safe run is running on the correction; exact SHA/results
and the proof-only disposition are recorded below before M4 is marked complete.


### M4 final evidence and M5 handoff (2026-10-19)

R5 proof-only continuation on `32ef3c3..aeff866` returned CLOSED/READY, with
86 independently executed tests GREEN (4.37s), no remaining invariant violation.
No second full audit occurred: one full M4 round, one consolidated scoped
correction, then a proof-only check justified by fresh reproduced evidence.
Current source is `aeff866`; subsequent commits only record evidence/links.

Final author contributor-safe run on that runtime:

    ai_trainer_env/bin/python -m pytest -q -m 'not live and not debug and not e2e' tests/ --tb=short

Result: **3665 passed / 14 skipped / 82 deselected / 7 existing warnings in
277.57s**. The 82 exclusions are the standard live/debug/optional-E2E markers;
all original M4 reader assertions run. Skips are 10 explicit fixture-regeneration
cases, missing optional garth (2), restricted process inspection (1), and local
listening socket restriction (1). Warnings are existing Starlette/httpx and
pandas proxy-connection diagnostics. No known failure is hidden by an exclusion.

Other final evidence: author correction contour 418 GREEN (22.92s); independent
418 GREEN (23.56s); final projection/story proof contour 86 GREEN (author 4.62s,
independent 4.37s); 36 real synthetic M4/S1 browser tests GREEN (73.53s). Ruff,
web lint/build, API inventory and contract artifact freshness GREEN. The later
provenance-only change does not alter web/DTO/UI behavior; no redundant browser
or web rebuild is claimed after it. Browser runs use temporary SQLite and
ports, provider credentials disabled, six width/theme combinations and keyboard.
Synthetic screenshots are committed under docs/design/evidence/issue-693;
old issue-685 evidence is unchanged. Native review, user-observed UX acceptance,
CI completion on the final published head and merge are distinct, not inferred.

All first-round blocking findings have fixing commits: R1 `6def63c` plus
`32ef3c3`; R2–R5 `32ef3c3`; newly reproduced inherited-revision edge `aeff866`.
Nonblocking follow-ups remain explicitly owned in #693 as written above, along
with the earlier M3c suggestions. No unaddressed blocking M4 finding remains.
The tracked handoff is [draft #700](https://github.com/rbctmz/ai_trainer/pull/700),
stacked on #699 and attached to this chat. No merge or rollout was performed.

Next role: Supervisor / Integrator for M5, not another UI redesign. Assemble one
whole-S2 candidate/evidence bundle against fresh main; include AC1–AC10,
current-head CI and native review, then explicit human merge acceptance. Parent
#677 retains S3 aggregates and S4 step-4 presentation. Personal live-provider
acceptance/deployment is outside this completed M4 synthetic implementation.
