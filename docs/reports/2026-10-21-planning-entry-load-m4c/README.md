# M4c: constrain initial assignments and guard publication

2026-10-21. Issue #710 / draft #711, parent #677. Domain / API Implementer;
base `a1fa7d2`. The approved [AC1–AC7](../../planning_entry_dose_m4_slice_spec.md)
and [ExecPlan](../../planning_entry_dose_m4_execplan.md) remain unchanged.
No UI components, real athlete cache, provider calls or live training plans changed.

## Result and boundary

New lifecycle builds use the M4b sport-specific observed reference or explicit
athlete-declared limits. The actual cycle's first14days bind duration, session
count and maximum session/leg duration in every overlapping7day window, including
six adjacent days. Later assignments remain anchored to those limits with the
existing10percent projection heuristic; frequency is held fixed. This is a
constraint envelope, not an adaptation or injury-risk prediction.

Generation reduces or retimes existing catalog assignments, records adjustments,
and never transfers unused allowance to another sport. Manual and Peak/Taper/
Race Week intent cannot change template/role to make a cap fit. An incompatible
assignment remains explicitly infeasible. All-rest output cannot satisfy the
required targeted disciplines. M3 validates the final effective assignments,
TSS, identities, availability and forecast after M4 adjustments.

Prepare returns422 entry_dose_required for missing reference/declarations or422
entry_dose_infeasible for incompatible assignments/physical partition, before
retaining any token. Both include typed entry_load. Planning and Coach share this
boundary; Coach preserves nested explicit dose objects on its legacy marker path.
No catalog minimum, global CTL, spare hours, sync success or old events invent a
starting dose. Synthetic demo setup explicitly supplies its own synthetic limits;
ordinary builds do not inherit them.

Confirm revalidates frozen minimal physical evidence and final assignments before
writes, without a provider call, Banister rebuild or new plan calculation. Honest
blocked pending returns409; malformed/dishonest evidence returns500 preview_corrupt.
Source recapture/CAS still invalidates stale pending. Applied receipts replay
before new eligibility checks; old unassessed pending requires refresh. No new
tables or backfill. Other checkpoint builders drop the now-stale entry evidence;
historical reads project unassessed with null source/scope instead of rewriting.
`training_suitability` remains `not_assessed`.

## Physical evidence and ownership

Capture occurs on the same SQLite connection as the existing source snapshot.
A bounded extra read retains malformed/undated rows and original entry-window
actuals that can age beyond ordinary90day history. ISO timestamps get a one-date
buffer at each end before local-day filtering. Capture truncation blocks rather
than silently declaring complete evidence. Stored source context keeps component
hashes; minimal canonical evidence lives only in the frozen internal checkpoint,
not the public response. Foreign provider identifiers are not copied unless they
resolve to a captured canonical envelope.

Completed physical leaves count once independently of whether TSS is zero.
Only explicit trusted matches owned by this cycle/version retire assignments;
heuristic, conflicting or same-day unpartitioned records refuse publication.
Editing retains original14day scope and sourced limits unless the athlete supplies
a new explicit frozen intent. Recaptured recent history remains separately dated;
it does not relabel retained limits as newly observed facts.

## TDD and compatibility evidence

The original four M4a assertion REDs are GREEN (five tests including the existing
purity control). Additional regressions cover Monday/Wednesday starts, usable
positive prescriptions, missing baseline in both origins, impossible catalog
minimums, seven-day boundary overlaps, composite legs, completed maximum duration,
trusted/heuristic/duplicate/foreign-cycle matches, same-day ambiguity, source
freshness, tampering, pure confirmation, original anchor on edit, old pending,
applied replay and historical unassessed mutation output.

Two local AC4 probes prompted corrections: completed duration was not checked
against maximum-session caps; protected phase retiming needed the same role/key
check as manual intent. A separate assertion RED showed an ISO timestamp on the
entry read's last day was lost by a plain date-string upper bound. Those paths now
have regression tests. The first phase probe initially used serialized daily rows
where generation expects runtime tuples; that setup error was corrected and is
not counted as a behavior RED.

Existing protocol/CAS positive fixtures now explicitly declare test-only generous
ceilings and use completed/rested history. Absence and same-day ambiguity are
separate negative tests; production defaults/guards were not relaxed. Historical
v1 golden fixtures strip the new public intent fields only at the trusted test
seeding boundary. S2 start clipping now uses the real public capture seam rather
than injecting a lifecycle into an unbound v1 snapshot.

Author focused M4 + HTTP/TS conformance:186 passed /1 warning,13.58s. Existing
transaction/cycle contour:135 passed /7 warnings,38.63s. Broader compatibility
contour earlier:115 passed /1 warning,23.28s. Ruff and diff whitespace checks pass.
The first broad verification ran while the TypeScript artifact changed; its
3958 passes /1 artifact-freshness failure is diagnostic only, not final-head
acceptance. A stable committed-head broad run and independent delta checker are
required below. Web contract extraction, inventory, lint and production build
passed; final head-bound records follow without replacing these boundaries.

## Frozen numerical experiment

[Protocol](protocol.md) was frozen locally in spikes/issue-710-entry-dose before
the first operator run. [Runner](experiment.py) creates only temporary synthetic
SQLite. [First result](experiment-first.json):30 fixed conditions,4.2692s,
12 supported /16 needs_baseline /2 invalid input, zero tested invariant violations.
The same-sport covered28day envelope and active-nonempty-week/global-CTL baselines
were fixed in M4a; no median, duration, scope or progression threshold was tuned.

The unchanged old four-run baseline allocated bike120/run90/swim35minutes in
week1 despite absent bike/swim observations. In the new run-only positive control,
run40 is the observed reference, bike60/swim20 are explicit declarations; executable
first-week dose is bike40/run30/swim20 on both anchors. Steady three-sport reference
60/40/20 gives executable30/30/20 (Monday) or50/30/20 (Wednesday). Refusals are
reported separately; they are not zero-load successful plans or evidence that
there is no possible training program for that athlete.

Identical duplicate fault injection retains four physical sessions per sport and
does not enlarge entry limits. Its whole-horizon TSS can still differ because the
legacy aggregate generator sees the injected noncanonical duplicate frame. The
experiment does not claim whole-plan duplicate invariance; normal SQLite canonical
identities are unique. Future/today rows cannot enlarge the observed reference;
today's global-load signal may still affect assignment choices inside the caps.
No clinical/efficacy/skill/intensity claim follows from any supported case.

## Reproduced UI handoff: M4 is not merge ready

Observed: the existing real browser test
`tests/e2e/test_planning_cycle_lifecycle_ui.py::test_expired_close_unknown_new_cancel_confirm_and_history`
fails at new_preview: actual POST /api/planning/build returns422 entry_dose_required,
where old UI expects200. Run:1 failed /1 warning,7.71s on an isolated stack with
providers disabled. This is a reproduced contract-consumer gap, not a green E2E.

Verified by: the response lists missing bike/run/swim dose with unknown coverage;
source inspection finds no history_coverage/initial_dose_limits input in the
Planning form. No API interception, fake user declaration or guard bypass was
added to make this journey pass. UI/Design Specialist must provide explicit
coverage/discipline-dose input and display supported/needs_baseline/blocked plus
EntryDoseAdjustment under the agreed API/TS contract. Exact entry points are
`web/app/planning/page.tsx`, its existing PlanningForm components, and
`web/lib/types.ts`; no domain derivation belongs in the browser. Backend evidence,
positive fixtures and safe refusal contracts are the handoff input.

M4d final/browser/native acceptance cannot be completed before that consumer gap
is addressed. Draft #711 must not merge/deploy in this state. Native budget stays
0/2; the independent M4c delta review is distinct. Owner acceptance and merge
remain separate and are not authorized for #711.

## Stable-head verification and independent review

Pending candidate commit. Record the exact implementation head, final commands,
all results, checker round/findings/dispositions, current CI and clean status here.
