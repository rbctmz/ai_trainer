# Planning S2: close the old cycle and start a new one (#693)

This living ExecPlan follows `.agent/PLANS.md`. Issue
[#693](https://github.com/rbctmz/ai_trainer/issues/693) is S2 of
[#677](https://github.com/rbctmz/ai_trainer/issues/677), after merged S1
[#691](https://github.com/rbctmz/ai_trainer/pull/691). The
[slice specification](planning_cycle_lifecycle_slice_spec.md) defines exact
state, storage, API, compatibility and acceptance obligations. Baseline main is
`93fa4f4d8d41c9e392093538900f471903b6c331`. M0 Spec / Architecture Owner handed
the reviewed contract to Domain / API Implementer for M1 tests only.
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
- [ ] M2: additive cycle migration/store, explicit selection and pure state projection; reset/restart/restore probes.
- [ ] M3: close/outcome/scope commands, S1 v2 start_new/edit_current and atomic replacement; every writer guards current cycle.
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
