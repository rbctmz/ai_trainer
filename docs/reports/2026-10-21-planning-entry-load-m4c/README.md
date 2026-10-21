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
`web/app/planning/page.tsx`, its existing `web/components/planning/PlanBuilder.tsx`, and
`web/lib/types.ts`; no domain derivation belongs in the browser. Backend evidence,
positive fixtures and safe refusal contracts are the handoff input.

M4d final/browser/native acceptance cannot be completed before that consumer gap
is addressed. Draft #711 must not merge/deploy in this state. Native budget stays
0/2; the independent M4c delta review is distinct. Owner acceptance and merge
remain separate and are not authorized for #711.

## Stable-head verification and independent review

Candidate `149dbf5aee01e4c9180ca64c3562dd7b4802fd0b` is published. Its stable
contributor contour:3962 passed /1 failed /16 skipped /82 deselected /7 warnings,
252.57s. The one failed cycle assertion incorrectly sums rounded week displays:
raw effective1816.1 correctly rounds to1816; separately rounded weeks sum1817.
The canonical existing effective_build_totals/S3 invariant is unchanged. The
assertion now compares total to round(sum(raw effective daily loads)), preserving
all individual weekly checks. This is a test correction, not a changed threshold.

Independent M4c delta round1 on149dbf5:BLOCK, one reproduced P2 (AC6). The actual
legacy demand-preview/confirm writer retained supported entry_load/evidence while
removing M3 readiness; the helper-only invalidation test missed that route. The
checker ran231pass/1rounding-assertion failure/7warnings(44.92s), Ruff green,
tracked tree clean. No provider/athlete writes or native review.

The exact demand workflow now has an assertion RED on retained entry_load. The
correction explicitly keeps trusted nonpublication build_plan captures outside
the new numerical policy; public prepare/confirm still require bound M4 evidence.
Legacy persistence strips entry_load/evidence/adjustments and returns unassessed,
alongside existing M3 invalidation. The demand regression forbids calling the new
constraining generator, checks current overview and unchanged prior version;
a second regression proves an internal nonpublication snapshot cannot pass the
public guard. No new public bypass parameter is introduced. Scoped correction
review and final committed-head broad verification follow.

The same30 frozen experiment conditions replayed on149dbf5 in4.6554s. Status,
limits, executable first-week dose and horizon total-TSS outputs equal the first
run exactly (elapsed time excluded). No new conditions or threshold tuning.


### Final bounded backend acceptance

Runtime `3a28f99d22e45005e868546367a2cec6449dc54a`: **READY for M4c backend handoff**.
AC6 P2: **fixed-in3a28f99**. Independent scoped delta round2 ran176 tests,
all passed /1 existing warning in42.17s; changed-file Ruff passed. HEAD unchanged,
tracked tree clean before/after. Two M4c delta rounds used; no additional full-diff
round, native0/2 unchanged. This is not native acceptance or owner merge approval.

Author stable contributor-safe command (PATH uses the main checkout's venv;
DATABASE_PATH/DEMO_DATABASE_PATH/CHATS_DIR all point to private temporary synthetic
paths): `python -m pytest -m "not live and not debug and not e2e" tests/ -q -p no:cacheprovider --tb=short`.
Result on3a28f99: **3965 passed /16 skipped /82 deselected /7 warnings,265.45s**.
No XFAIL remains in the original M4a final-assignment tests. Whole-repo Ruff,
`git diff --check`, extraction freshness and relative Markdown links passed.
Web lint/build/inventory passed on the identical reviewed TypeScript/web tree;
the scoped correction changed no API/TS/public schema or components.

Remote run39597418839 on149dbf5 had3939pass/1rounding-test failure/39skip in
contributor-safe pytest and51pass/7fail E2E. The rounding assertion is corrected;
three Coach E2E failures were positive fixtures missing explicit starting limits.
Only those fixtures now declare their synthetic8hour ceilings and use a future
start to avoid inventing ownership for today's completed activities. The actual
Coach browser approval/success/lost-response/stale cases reran **3passed /17deselected,
10.10s**, using the real backend approval endpoint; their existing transport
simulations remain unchanged. No current Planning form request was intercepted
or supplied with fake athlete declarations. These setup changes occur after the
backend review; runtime3a28f99 and contributor-safe sources are unchanged.

The other four failures are existing new-cycle UI journeys using the missing-dose
form path (including the independently reproduced local case). Full E2E has not
been rerun or declared green after the fixture correction. This is the explicit
UI/Design input/refusal handoff and keeps whole M4/native/merge acceptance open.
Final documentation/Coach-fixture commit publishes the reviewed runtime without
claiming final-head functional CI or native acceptance. #710 and#677 remain open;
#711 remains draft/unaccepted. Primary checkout's unrelated research edits and
live athlete cache remain untouched.


### UI handoff resolved; M4d local acceptance

The missing-input failure above is preserved as historical evidence. UI/Design
implemented the agreed DTO consumer in46e17f4..f0650b5: explicit blank starting
limits/coverage, structured refusal with edit path, sourced preview and all
server adjustments. No backend guard, schema, AC or policy was weakened.
Independent UI delta round1 READY, zero blocking P1/P2;5 entry UI tests passed.
Author whole63 isolated E2E passed/1warning189.89s; contributor3965passed/
16skipped/87deselected/7warnings277.59s. Lint/build/Ruff/contracts passed.
[Consumer brief, commands, screenshots and limitations](../../design/evidence/issue-710/README.md).
Whole-delivery native and final-head remote CI remain separate; #711 is not
accepted or merged. No human usability/clinical/provider acceptance is implied.
