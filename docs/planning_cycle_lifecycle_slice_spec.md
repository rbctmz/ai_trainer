# Planning S2 — selected cycle, explicit close and clean new start

Issue [#693](https://github.com/rbctmz/ai_trainer/issues/693), parent
[#677](https://github.com/rbctmz/ai_trainer/issues/677). Author: Codex, Spec /
Architecture Owner. Independent spec checker: `s2_spec_checker`. Human owner: merge and
live rollout. Baseline main: `93fa4f4d8d41c9e392093538900f471903b6c331`,
2026-10-17. [ExecPlan](planning_cycle_lifecycle_execplan.md).

## Change Class

Class A — Full. Persistent selection/identity, migration, transaction/retry,
cross-module readers and writer compatibility trigger escalation. Manual review
only: specification budget 2/2, implementation/native budgets separately recorded
on their final candidate. This document proposes contracts; nothing here claims
implemented behavior or authorizes merge/deployment.

## Scope and non-goals

Select at most one cycle, close it explicitly, record/correct explicit event
participation and start a new cycle without old calendar context. Preserve plan
versions, activities, matching, feedback, lineage and delivery history. Planning,
Today and Coach share Python-owned state and allowed actions. UI changes consume
that contract and reuse existing components; CSS/composition choices are not
owned by this specification.

Post-A continuation/recovery belongs to #680, clinical restrictions to #679,
Recovery Mode to #669, event discipline to #678 and multi-day support to #579.
No automatic participation/finish inference, queue of future cycles, parallel
cycles, reopening a closed cycle, provider delivery, new training formulas,
general step-4 redesign (S4) or broad aggregate cleanup (S3). Recomputing the
aggregates affected by excluding days before the new start is necessary S2
calendar correctness. Closed historical prescriptions are read-only.

## Definition of Done

- [x] Observable AC1–AC10 recorded in #693 and mapped below.
- [x] Storage, migration, readers/writers, failure/reset and test boundaries named.
- [x] Human merge/rollout owner; author owns synthetic surfaces and task cleanup.
- [x] (2026-10-17) Independent full spec round plus scoped correction: READY at `a2f3848`, zero remaining blockers, budget 2/2.
- [x] (2026-10-19) Runtime/contracts/browser evidence GREEN; final native scoped round clean on 4f612dc, budget 2/2. Exact delivery receipts are in #701/#693 and ExecPlan.
- [x] (2026-10-19) Explicit human acceptance and #701 merge as 5f3b738; live rollout remains separately authorized and unperformed.

## State boundaries and identity

Cycle is a durable preparation context, not an individual plan version or a race
result. New cycle UUID and initial checkpoint are assigned only through a retained
`start_new` proposal. Later checkpoints append versions to that same cycle.
Current means the persisted singleton selection, never SQL `MAX(checkpoint.id)`.
Period state uses the athlete's configured local day; participation is explicit
data independent of that state.

| State | Rule | Allowed lifecycle actions |
| --- | --- | --- |
| `no_current` | Selection is null, even when history exists | start_new, browse history |
| `scheduled` | Selected, not closed; today < start_date | edit_current, close, start_new |
| `in_progress` | Selected, not closed; start_date <= today <= end_date | edit_current, close, start_new |
| `period_ended` | Selected, not closed; today > end_date | close, start_new, inspect execution/history |
| `closed` | Explicit closed record, returned only in historical context | inspect, correct event outcome |
| `indeterminate` | Selected record/linked checkpoint has missing, malformed or contradictory bounds/content | close without inventing dates/outcome, start_new with explicit replacement, inspect gap |

Dates passing never write closure, selection or outcome during GET. Current phase
is null outside the actual period; the last week remains available as a labelled
historical/last week. `completed_weeks` measures calendar passage, not execution
or participation. Same-cycle extension after an ended period is deferred to the
explicit #680 continuation contract; do not silently reopen it through edit.

## Storage and ownership

### Session identity and continuity across cycles

Modern cycles own an immutable identity_namespace equal to the server-reserved
cycle UUID. Generate session material fingerprints/IDs with a versioned v2
tuple of that namespace and the existing canonical date/prescription/occurrence
material. Keep the ats_ hash-ID format; changed input domain, not readable UUID
concatenation, separates cycles. Nested/multisport sessions use the same namespace;
leg IDs derive from their namespaced parent under existing leg identity rules.
Freeze namespace and IDs once in the retained preview, so retry/confirmation
does not generate them again.

start_new never supplies the preceding cycle as previous_goal_plan, honors its
embedded session IDs or copies its replaces_session_id/leg continuity. Its first
checkpoint has no prior-cycle plan-version parent; the old cycle/checkpoint is
recorded separately in lifecycle source/closure context for audit and preview
comparison, not as a replacement/donor chain. Same-cycle edit/restore preserves
the namespace, unchanged IDs and existing material-change/survivor lineage rules.
Require stored cycle ownership before following a donor/parent/replacement edge;
an apparent ID/content match across different cycle UUIDs is not continuity.

Legacy imported/previously stored sessions and legs keep their existing v1 IDs,
fingerprints and ledgers byte-for-byte. Within an imported legacy cycle retain
existing identity behavior; do not mass-salt historical data. Every genuinely
new modern cycle gets v2 namespacing, including a new cycle with identical date
and prescription. New matches, feedback and delivery keys therefore cannot reuse
an earlier cycle's identity accidentally. Existing ambiguous legacy ownership is
an explicit data gap, not a newly inferred cross-cycle match.

Historical session projection accepts an explicit checkpoint_id when selection
cannot determine ownership (notably legacy IDs). Verify the session belongs to
that checkpoint; missing/ambiguous context yields a gap rather than falling back
to latest/global date. Existing feedback/match keys are not rewritten; modern
namespacing separates new facts while explicit historical context preserves old
access. Test provider delivery keys locally without contacting a provider.

Implement the single-purpose store in `data/planning_cycles.py`, pure projection
in `models/planning_cycle.py`, orchestration in `services/planning_cycles.py`.
Use connection-bound helpers and the repository SQLite policy; no provider/model
call or scheduler inside a writer transaction. Suggested exact tables:

| Table | Essential columns/invariant |
| --- | --- |
| `planning_cycles` | UUID id PK; current_checkpoint_id nullable FK; revision integer >=1; status open/closed; start_date/end_date nullable; created_at/closed_at; origin explicit/legacy_import; event_outcomes_json default {}. Closed row retains its checkpoint. |
| `planning_cycle_state` | singleton id=1; namespace UUID; current_cycle_id nullable; revision integer >=0; legacy_migration_complete boolean. Null selection after migration must never fall back to latest history. |
| `planning_cycle_versions` | checkpoint_id PK/FK; cycle_id FK; action initial/edit/restore/adjustment; immutable association. One checkpoint belongs to at most one cycle. |
| `planning_cycle_commands` | command_id UUID PK; kind close/set_event_outcome/resolve_constraint_scope; request_digest; cycle_id nullable; event_key nullable; request_json/result_json; created_at. Only successful commands retained, append-only; fixed kinds, not a general workflow engine. |

Event outcome is the cycle's current event_outcomes_json projection, updated
atomically with a successful set_event_outcome or close-with-outcomes command.
Its immutable command request/result holds event snapshot, checkpoint ID,
before/after explicit value and resulting cycle revision; earlier commands are
the correction audit. Values: unspecified,
did_not_participate, participated. Unspecified is absence of a declaration, not
an inferred result. An event key is server-derived from cycle UUID and canonical
stored source/id/date/priority/label. Ambiguous duplicates cannot be targeted.
Renaming/replacing the event does not move its old outcome automatically; old
snapshots remain readable. No-event cycles show no participation question.

Selection, cycles, version associations and successful command receipts are
retained with planning history, without TTL cleanup. Existing S1 unused preview
TTL/cleanup remains bounded; applied receipts are retained. Full reset removes
all four tables' rows, rebuilds an empty migration-complete singleton and removes
preview rows. Backup/restore preserves namespace, selection and receipts. New
configuration flags are N/A; use existing athlete timezone and SQLite settings.

### Conservative legacy migration

Run once during explicit database initialization, one transaction, before
serving cycle readers. Empty DB: migration-complete state with null selection.
Legacy DB: import only its latest checkpoint as one selected legacy cycle and
link only that checkpoint. Derive valid bounds from its actual persisted daily
dates, not created_at, event date alone or a guessed number of weeks. Preserve
all checkpoint JSON/IDs and every ledger row byte-for-byte. Earlier checkpoints
remain unassigned legacy history; do not infer that all old versions were one
cycle from goal labels, dates or the old parent chain. Unknown/corrupt latest
content becomes indeterminate without fabricating bounds or participation.

Repeated init/restart does not import again or resurrect a closed/null selection.
Migration rollback leaves no half-selected record or partial mapping. Explicit
restoration of unassigned legacy history is permitted only into the currently
selected open legacy-import cycle after a visible `restore_legacy_version`
confirmation; it appends a new mapped checkpoint, never rewrites/assigns the old
one. Once a modern cycle exists, unassigned legacy history is read-only and a
new-cycle preview is the route to reuse explicit inputs. Closed cycles cannot
be restored. Known same-cycle versions retain the ordinary explicit restore.

### Constraint ownership

Add nullable `cycle_scope` (athlete/cycle/unknown) and `cycle_id` to existing
coach_constraints. Existing sport/date/status protections remain unchanged.
Resolve an explicit checkpoint/session binding only if it names one known
cycle. Binding conflict or unresolvable plan/session reference => unknown.
Without bindings, sick/unavailable/forced_rest retain their current athlete/day
meaning; manual_delete/disabled_plan_day are unknown until explicitly scoped.
Never convert old deleted/disabled training into a global athlete restriction.

New constraints declare athlete scope or the selected cycle. During prepare,
apply athlete constraints in their existing date/sport window and only that
target cycle's constraints; old cycle constraints do not flow into start_new.
Unknown in-range scope produces `constraint_scope_required` before a usable
preview. Resolve through the explicit scope command below; it changes only new
scope metadata, not dates/sport/status or a training prescription. The server
returns conflict IDs and safe reasons, never guesses or silently drops safety.

## Public contracts

### Reads and meaning

Add `GET /api/planning/cycles/current`, `/cycles?limit=…` (bounded 50) and
`/cycles/{cycle_id}`. `CycleContext` contains state, cycle_id nullable,
is_selected, current_cycle_id nullable,
selection_revision, cycle_revision nullable, checkpoint_id nullable, actual
start_date/end_date, athlete_day/timezone, is_legacy, has_history, reason_code,
allowed_actions and stored event rows with event_key/outcome. Missing data is
an explicit reason, not a browser decision. History GET never selects a cycle.
Read state, target cycle and its checkpoint in one read transaction, capturing
athlete day once. A historical response identifies its queried cycle separately
from the current selection; it must not relabel the old cycle as selected.

Existing planning status/overview/edit context, Today and Coach gain the same
`cycle_context`. `has_plan` means selected readable checkpoint, including
period_ended; add `has_actionable_plan` for scheduled/in_progress. Null selection
=> has_plan=false even if history exists. Indeterminate may have a readable
checkpoint but has_actionable_plan=false. Keep raw latest-history accessors
unchanged; introduce `get_current_planning_checkpoint` and connection-bound
equivalent, and migrate current-plan callers explicitly. Never redefine the
old raw SQL helper to secretly hide history.

`GET /api/planning/build-context?action=start_new|edit_current` provides canonical
form inputs, their sources and current CAS context. For start_new, start_date
defaults to athlete day, calendar_week_start to its Monday; events=[], no old
event_date/manual phases/moves/deletes. Goal/intent need a new explicit choice.
Valid available hours/days and preferences may be labelled profile suggestions;
form defaults are not confirmations. Future discovered events stay unselected.
edit_current uses the selected cycle's saved inputs only when action is allowed.

### Build and atomic replacement — reuse S1

New `POST /api/planning/build` requires lifecycle action start_new/edit_current,
base_cycle_id (UUID or null), base_cycle_revision (integer or null),
base_selection_revision, replace_current_cycle boolean and actual start_date,
beside current build parameters/base_checkpoint_id. These are expected context,
not trusted ownership. Resolve/check them on the coherent read transaction.
Missing lifecycle action yields 409 `cycle_context_required`; old raw writes
remain 409 preview_required. No HTTP field can choose trusted legacy mode.

For start_new, current selection must match expected context; with an existing
selection replace_current_cycle=true is mandatory. With no current selection it
must be false. Reserve a new cycle UUID in the artifact; no cycle/closure/profile
is published during preview. Reject start_date < athlete day and conflicting
supplied start_week; its sole meaning is Monday(start_date). Events before the
actual new start require correction, never silent reuse. event_goal still needs
an explicit confirmed A anchor. No assignments before start_date, even when its
calendar week starts earlier. Clip the canonical generated daily prescriptions,
then derive affected week totals/forecast/audit from that exact prepared result;
do not merely hide old days in React. Preserve existing training formulas.

edit_current keeps cycle identity and period start. Existing immutable past
prescriptions/identities are copied, future assignments can change only inside
the explicitly previewed remaining period. Do not fill an elapsed gap or invoke
post-race recovery automatically. period_ended/closed/indeterminate edit returns
an explicit lifecycle conflict, not implicit start_new.

Extend retained build storage with `cycle_context_json` and schema_version=2;
new artifact/receipt digest includes that frozen context. Protocol v2 responses
retain BuiltPlan/parameters fields unchanged and add immutable `lifecycle`:
action start_new/edit_current; source_cycle_id UUID/null; target_cycle_id UUID;
base_cycle_revision integer/null; base_selection_revision integer;
base_checkpoint_id integer; start_date/end_date YYYY-MM-DD; closes_cycle_id
UUID/null. This object is identical in preview and applied result; confirmation
metadata and assigned plan_id retain S1's allowed differences, protocol_version
is 2. Capture fixtures in `api/planning_cycle_contract.py`, `web/lib/types.ts` and
the contract registry before runtime integration. After apply clients refresh
current context rather than reuse the old base revisions. Confirm stays identity-only
`{preview_id,confirm:true}`; no lifecycle overrides at confirm.

One BEGIN IMMEDIATE rechecks S1 dependencies plus selection/current cycle and
constraint ownership. First success inserts/maps checkpoint; for start_new closes
old cycle if selected, creates new cycle, updates selection; for edit appends and
advances the same cycle. Settings, receipt and Coach approved/result remain in
that commit. Any fault rolls it all back. A lifecycle/outcome/scope change in a
relevant dependency invalidates pending preview even if raw latest ID is equal.
Two replacements from one base have one winner. Retry replays the same result
and never closes/reselects a later cycle.

Pending S1 v1 artifacts lack cycle ownership and must return preview_required
after migration, including pending Coach builds. Applied v1 receipts remain
readable/replayable with their original response shape/digest; is_current is now
computed against selected cycle/head, false after closure or replacement. Use
version-tagged response validation for retained v1 and new v2; never retrofit
cycle context or rewrite old receipt JSON. API/web ship together; old tabs must
refresh. Successful replay is not a create/select operation.

### Explicit cycle commands

`POST /api/planning/cycles/{id}/close`: command_id UUID, confirm strict true,
expected_selection_revision, expected_cycle_revision, expected_checkpoint_id,
optional event_outcomes list of stored event_key/value. Close is allowed early
and without outcome. In one writer transaction validate ownership/CAS, set
closed, clear selection, optionally append outcome declarations and save the
command result. No checkpoint, profile, next cycle or recovery is created.

`POST /api/planning/cycles/{id}/event-outcome`: command_id, confirm strict true,
expected_cycle_revision, event_key, outcome. Accept a stored event snapshot in
that cycle's history; future participated declarations are invalid, while an
explicit future non-participation is allowed. Increment cycle revision, append
declaration/receipt; do not select/reopen or change activities/prescriptions.
Historical outcome correction does not bump an unrelated selection revision.

`POST /api/planning/cycles/constraint-scope`: command_id, confirm strict true,
constraint_id, expected_constraint_fingerprint, scope athlete/cycle and cycle_id
only for cycle scope. Require a known stored cycle for that ownership; update
only scope metadata and retain a command receipt. The unknown-scope UI offers
this explicit resolution or cancellation, not an automatic relaxation.

Every command response has command_id, kind, replayed, immutable `result`
(affected cycle ID, resulting revision and effect) and `current_context` freshly
read under the transaction. On replay result is original historical evidence;
only replayed/current_context are dynamic. Clients render selection from current
context, never from an old successful close's result. Same ID + same canonical
request returns the saved result;
same ID + changed request gives 409 idempotency_conflict. Read receipt before CAS
on retry; historical successful close never clears another selected cycle.
Command controls retain unresolved ID and lock conflicting actions after lost
response, just like S1. Do not call transport error a failed close.

### Safe errors and compatibility

Use safe `{detail,code,retryable}` for new routes/build v2. 409 cycle_stale,
cycle_context_required, replacement_confirmation_required, cycle_not_current,
cycle_closed, cycle_period_ended, cycle_indeterminate, constraint_scope_required,
idempotency_conflict; 404 cycle_not_found/event_not_found; 422 invalid_cycle_request,
invalid_start_date/invalid_event_outcome; 503 planning_busy retry same identity;
500 cycle_storage_error retry same identity or cycle_corrupt non-retryable.
Stale/validation/failure changes no active state. Unknown/corrupt receipt retains
unresolved attempt for diagnosis. Existing S1 stale/expiry/corruption meanings
stay intact. No generic error contains private plan/activity payloads.

## Reader and writer inventory

This is an obligation list, not permission to replace every historical read.
Before M1 freeze the full `rg` inventory against current main in tests/fixtures.

| Boundary | Current-context adaptation / historical exception |
| --- | --- |
| api/planning_service.py status/overview/edit/build, demand, adjustment, near-term edits, move/rollback, repair, restore | Shared selected context. Every saved child proves expected cycle/selection/head inside its write transaction. Closed/noncurrent mutation rejected. Same-cycle restore only; unassigned legacy exception uses explicit restore_legacy_version action. Extend history/restore request with expected cycle/selection revisions and explicit legacy-target acknowledgement; preserve its existing confirmation protocol rather than migrating it to build S1. |
| data/database.py save/_insert checkpoint, commit_coach_plan_mutation | Lifecycle-bound commit primitive checks association/current CAS; no raw insert may select a cycle implicitly after migration. Trusted synthetic legacy seeding is private, never an HTTP flag. Adapt fixtures explicitly, do not weaken runtime guards for tests. |
| data/planning_build_preview_store.py and models/ai_tools.py / decisions / coach router | Frozen v2 cycle context and bound Coach proposal; card clearly states replacement. Other actions retain their protocols but cannot write an old cycle after close/switch. |
| api/today_snapshot.py, recovery_replan_loop.py, session_quality_forecast.py | Shared selector/current CAS. No obsolete intervention/assignment in no_current/ended/closed; readiness/load facts can still be shown. |
| services/reconciliation.py, session_projection.py, api/session_feedback.py, comparable_sessions.py, recovery_analytics.py | Split current views from explicitly checkpoint/session-bound history. Historical corrections/facts remain reachable without selecting/reactivating old cycles. Never rewrite match/feedback ledgers to follow selection. |
| services/intervals_plan_delivery.py | Select/check current context before any provider call; no_current/ended => idle. S2 tests stub providers and prove no old-cycle delivery. No new provider sync/cancel/delete feature. |
| utils/app_state.py, state/manager.py, ui/pages/planning.py / dashboard.py | Compatibility bridge to shared selector/write guards only. Cached old goal_plan is not authority. Unsupported legacy lifecycle writes explain use of web; no independent cycle logic/new Streamlit-only feature. |
| system/demo, acceptance/evaluation fixture builders | Explicit internal initialization with same lifecycle primitives or deliberate pre-migration legacy fixture. No magic source flag accepted from the public API. |
| web Planning/Today/Coach and history widgets | Render shared state/allowed_actions; no date/cycle inference. History is explicit read-only context; unresolved close/build replacement owns its original ID. |

## Failure, reset, rollback and lifecycle probes

Inject faults after old closure, new cycle insert, checkpoint/map, selection,
settings, S1 receipt, Coach status, command/outcome/scope writes and before commit.
Every old state survives failure or the complete committed result replays. Use
two real connections for close-vs-build, two replacements, edit-vs-close and
outcome/scope-vs-preview races. A newer historical checkpoint insertion does not
become current just by having a larger ID. Legacy GET and all GET transitions
leave selection, checkpoints and ledgers unchanged.

Initialization/migration, restart, full reset, Backup API restore and applied-v1
receipt replay are mandatory. Downgrade to a pre-cycle binary can read raw MAX
and violate closure; stop writers and disable confirmation/delivery during any
downgrade, preserve new rows, then fix forward. No live migration/rollback here.

## Evidence boundary and RED matrix

| AC / evidence boundary | Planned test/probe | Expected result |
| --- | --- | --- |
| AC1 no/current/future/start/end/day-after/unknown | test_planning_cycle_projection.py; pinned athlete clock/timezone | Pure exact state, no fabricated current phase/outcome, no GET writes |
| AC2 close early/ended/no event; history present after null selection | test_planning_cycle_commands.py | One closure, null selection, preserved checkpoint/ledger bytes |
| AC3 inherited inputs and mid-week start | test_planning_cycle_build.py; isolated builder E2E | Clean defaults and zero new executable days before actual start |
| AC4 same/different retained proposals; close/switch ABA | test_planning_cycle_build.py real connections/fault stages | Exact frozen publication; one winner; selection revision defeats same-head ABA; safe replay |
| AC5 unknown/DNS/participated/correction; historical/new event identity | test_planning_cycle_commands.py | Explicit auditable declaration only, no reopen/recovery or activity rewrite |
| AC6 latest-known / malformed / unassigned old versions | test_planning_cycle_storage.py plus unchanged S1 payload/ledger fixtures | Conservative once-only import, history preserved, unknown gap |
| AC3/6 overlapping cycles with identical/changed sessions, multisport/legs | test_planning_cycle_identity.py | Distinct modern IDs/feedback/match/delivery keys across cycles; no inherited replacement edges; same-cycle identity stable; v1 untouched; preview/retry same frozen IDs |
| AC7 each writer; same-cycle vs cross-cycle/legacy restore | test_planning_cycle_writer_guards.py | Current CAS or explicit safe rejection, never implicit reactivation |
| AC8 athlete/cycle/unknown date/sport/binding constraint | test_planning_cycle_constraint_scope.py | Protection applied, old edits not global, unknown blocked and explicitly resolvable |
| AC9 complete expired→close/outcome→new/cancel/confirm/retry | test_planning_cycle_lifecycle_ui.py with temp web fixture | Athlete can state selected period/consequence; shared readers agree; mobile/keyboard |
| AC10 migration/fault/restart/reset/restore/protocol versions | all above + original S1 suite/contracts/lint/build | No skipped known failure or regenerated old oracles to hide drift |

These names are proposed, not GREEN evidence. Baseline and executed falsifying
probe are in the ExecPlan. Current green 89-case baseline is not lifecycle RED.

## UI responsibility brief

Athlete's primary task: decide what to do after a period ends. Planning owns the
selected cycle, outcome declarations and explicit new-cycle start; Today owns
today's available work/facts; Coach describes that same context and shows the
prepared build consequence. First-level information is state + actual period +
one next action, with history reachable. Ended period is not successful execution
or race participation. Replacement confirm explicitly says the previous cycle
will close; Cancel changes nothing. Unknown outcome remains unanswered, including
when closing. Unknown command result retains retry identity and locks destructive
reset. The UI specialist chooses accessible composition within existing tokens;
no CSS/layout is prescribed here.

## ASR / ADR traceability and review handoff

ASR-REL-1/2 (history and honest gap), MOD-2/3 (server-owned semantics and legacy),
DEP-2 (additive migration/restore); ADR-0001 API/web policy. Tactics are explicit
selection, immutable associations, conservative import, CAS inside transactions,
retained result replay and provider-free synthetic acceptance. Trade-off: larger
cross-module integration and deliberate rejection of unsafe old write paths.

Delivery: M0 spec/check; M1 RED/characterization; M2 storage/selector/migration;
M3 commands/build/calendar/writer guards; M4 current/historical readers and UI
through explicit Domain→UI handoff; M5 complete acceptance/native review/human
merge. Intermediate REDs are not merge candidates.

## Evidence Bundle

Baseline main `93fa4f4`; spec round 1 candidate `a4647fd`. Author baseline 89
passed in 7.66s; independent checker repeated 89 passed in 8.17s. Synthetic
expired/inherited/mid-week probes are reproducible in the ExecPlan. Pure author
probe also demonstrated identical current ats_ IDs for identical sessions with
two different cycle_id values; that is existing content identity, not a claimed
baseline bug. The missing future namespace rule was the spec blocker below.
No implementation tests/contracts/browser/CI are GREEN for S2; no native result
or merge acceptance is claimed. Current branch contains documentation only.

## Review Findings

| Severity | Observed / inferred / verified | Disposition |
| --- | --- | --- |
| Blocking P2, AC3/AC6 | Observed: baseline session_identity.py hashes material/date, reuses previous IDs and can create replaces edges; builder always passes the prior plan, while ledger reads key by session ID. Inferred: an underspecified start_new could accidentally expose old-cycle evidence or lineage. Verified by: reviewer static payload/reuse/ledger inspection; author pure two-cycle synthetic probe returned the same ats_095fdf5c5cc311c9b2a29044. | fixed-in a2f3848: modern namespace, isolated initial parent/continuity, legacy preservation, historical context and overlapping-cycle test matrix; independently verified closed in scoped round 2/2. |

## Review Rounds

Specification round 1/2: independent read-only checker reviewed complete
`93fa4f4..a4647fd`, returned BLOCK for the one P2 above, no other evidence-bound
P1/blocking P2. Branch status clean before/after; independent baseline 89 passed.
Round 2 reviewed `a4647fd..a2f3848`, restricted to that correction and the added
evidence/template record; READY for spec handoff with no remaining blockers.
Status before/after remained clean; no extra runtime tests or external writes.
Implementation/native rounds: none requested; they belong to later candidates,
not this static specification check. No budget exception or waiver.

## Final Verdict

Specification handoff READY at `a2f3848`, zero remaining blocking findings after
scoped verification. Runtime S2 is unimplemented. Spec review budget used 2/2; human retains
merge/live rollout and implementing author owns branch/test-surface cleanup.
The next role is Domain / API Implementer for M1, with exact tests
and invariant obligations in the ExecPlan. No CSS/layout role is assigned here.


## Delivered S2 status (2026-10-19)

The M0 proposal/review records above retain their original historical wording;
they do not describe the delivery status after implementation. The approved
contract was delivered through #701, final head 4f612dc, merged as 5f3b738 after
human acceptance, fresh GREEN Review gate/CLEAN and pinned-head merge. Native
round 1 found three P2, reproduced and fixed; scoped round 2 was clean, zero
unresolved threads. Full synthetic CI/API/TS/browser evidence is in the ExecPlan
and PR/#693 handoff. S3/S4 remain with #677; no live migration/provider writes or
athlete-observed UX acceptance is claimed. This update changes status only,
not an AC, invariant, public contract or non-goal.
