# M3 #763 — тренировки тренера в календаре

Class A. Parent #760. M2 merged in 1fd9d67. This contract covers the user's Plan
calendar and explicit revision decisions. Implementation follows the handoffs in
the [ExecPlan](swim_calendar_execplan.md).

## Observable behavior

From a confirmed library version the athlete chooses actual local dates for
individual workouts. The trainer's week label remains source metadata. A review
shows the selected cycle and calendar dates, exact workout and exercise versions,
pool length or open water, steps, distances and any uncertainty. Confirmation
places the exact reviewed selection. A later library version does not move or
update earlier assignments.

An assignment has a stable ID within its cycle. A move retains the ID and changes
only its date. A substitution points to an explicitly chosen saved workout version.
Removal and rollback show a before/after diff and require confirmation. Rollback
appends a new checkpoint and takes authored assignments only from a verified
checkpoint of the same cycle. A cycle switch starts with its own assignments
and keeps the previous cycle readable by its historical checkpoint.

## Domain boundaries

Keep authored assignments in an additive `swim_calendar` array in the existing
checkpoint snapshot. Each entry binds assignment ID, ISO local date, library
program ID/revision/fingerprint and exact workout ID. Confirmed library versions
are immutable and resolve through the shared program adapter. Current, historical
and preview readers resolve that same reference. A missing or corrupt source is
an explicit data gap. Legacy checkpoints without this array are empty.

Ordinary checkpoint adjustments and rebuilds carry the array forward. Under the
selected-cycle write lock, a generic writer that drops or changes assignments,
or shortens the cycle past any assignment, fails atomically. Starting a new
cycle cannot acquire another cycle's assignments. Generic history restore and
Recovery rollback carry the current authored array, subject to date bounds.
Authored rollback uses the dedicated reviewed proposal. Store checks are a
backstop even if a caller bypasses a preview helper.

The calendar projects authored rows alongside generated sessions, preserving
both origins. Numeric generated-plan prescriptions remain the planner's own
model. Authored rows report unknown duration and load where evidence is absent,
and known partial/exact distance from the shared swimming summary. The UI labels
aggregates as incomplete and identifies dates with conflicts. Date eligibility,
availability, race protection, existing constraints, collisions and load risk
use shared Python checks and return explicit refusal or uncertainty. An unresolved
load assessment must remain visible through confirmation. It grants no authority
to rescale a workout, move it, or replace a generated session.

Reuse the weekday/date semantics from #668 if its contract is available on the
branch. Review baseline found no implementation on main 1fd9d67. Bring in the
shared eligibility rule once and keep #668's scheduler/brick work in its own scope.
Date rules override weekday rules, followed by the existing availability and
race/constraint checks. A missing discipline rule does not create a ban.

## Preview, confirmation and reads

Retained preview binds exact before/after and the full existing cycle write token,
including constraint digest and athlete day. It records operation identity,
expiry, warnings and affected dates. Replays of applied confirmation return the
original receipt. Pending stale, ambiguous, out-of-period and cross-cycle requests
fail closed. Atomic confirm writes checkpoint, cycle revision and receipt together.
There is no generic client-supplied checkpoint/write bypass. Read by current
selection or explicit checkpoint, checking ownership for historical queries.

## Evidence

1. Compare exact authored references and resolved content after generic rebuild,
   demand, resize, Recovery/Replan and restored checkpoint. Changes to other
   sessions retain their normal behavior.
2. Add, move, substitute, remove and roll back with explicit preview/acceptance.
   Race a competing confirmation and verify one writer succeeds. Recheck expiry,
   lost response, cycle switch, history, restart, restore and reset.
3. Verify pool and OW, exact nested structure, pinned exercise revision, legacy
   reads and uncertainty for duration/load. Exercise missing/out-of-range dates,
   date/week labels, unavailable days, sports restrictions and protected events.
4. Complete an isolated browser journey from library to calendar, then show the
   old and new placement after move/rollback. API/TS and lifecycle checks prove
   backend authority. CI and bounded independent review precede human merge.

M4 owns export/provider writes. M5 owns matching and accounting. The user's
calendar and database are outside the synthetic acceptance environment.
