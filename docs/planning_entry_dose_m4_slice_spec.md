# Planning M4: discipline-specific initial dose — specification and review record

Issue [#710](https://github.com/rbctmz/ai_trainer/issues/710), parent
[#677](https://github.com/rbctmz/ai_trainer/issues/677). Date:2026-10-21,
Europe/Moscow. Role: Spec / Architecture Owner. Human owns merge/live writes;
Domain/API owns implementation after the explicit handoff; UI/Design owns S4.
[ExecPlan](planning_entry_dose_m4_execplan.md),
[evidence](reports/2026-10-21-planning-entry-dose-m4/README.md).

Reviewed specification checkpoint: `fb06cb803a17891624f47254c0a6b2edef60a9ee`,
base `99a6a1f84f9e9f4d51a22796ab819238c516e3c2`; draft
[#711](https://github.com/rbctmz/ai_trainer/pull/711). Independent spec review:
READY; this following documentation-only record does not change AC1–AC7. Acceptance SHA: N/A, owner has not accepted this candidate.

## Change Class

Class A: frozen history/intent provenance, new API↔TS shape, preview-confirm
freshness and initial-dose behavior across planner/Coach. Automatic escalation
checks: provenance and cross-module contracts apply; no live write, paid call,
credential handling or destructive migration proposed. Manual review only.
Independent spec budget1/2; M4b delta checker1/2; native0/2; no exception or accepted label.
This M4a checkpoint specifies/characterizes behavior; it does not implement or
validate personalized prescriptions. S3 technical readiness is already in main.

## Scope

Prepare an explicit contract, science boundary and behavioral RED for the first
14 calendar days of a newly selected training cycle, anchored to its actual
start_date, not rounded Monday. Later Domain/API slices implement a pure sport
exposure profile, initial constraints, generation and bounded confirmation.
Inputs remain the frozen canonical activity frame, athlete-local as-of date,
existing profile/zones, cycle identity and explicit human starting information.

Planned modules: new models/planning_entry_load.py; frozen capture/calculation/
prepare-confirm integration in api/planning_service.py and
models/planning_build_confirmation.py; api/planning_build_contract.py,
api/planning_cycle_contract.py and web/lib/types.ts mirrors/contract fixtures;
existing planner/materializer hooks only as necessary to respect constraints.
Reuse models/activity_lineage.py and utils/product_semantics.py. No production
source or TS contract changes in M4a; spec fixtures/probes live under tests/docs.

## Non-goals

No medical clearance, injury-risk percentage, VO2max/detraining estimate, ACWR
safe zone or universal10% guarantee. No single total-CTL→sport capability
conversion, optimal eight-week periodization or claim of goal attainment.
No threshold calibration#703, daily sports#668, Recovery Mode#669, post-A#680,
open-water competence assessment, #707 catalog expansion, S4 CSS/layout,
provider calls, live athlete DB change or historical JSON backfill. A successful
sync or absence of rows is not proof of complete history.

## Definition of Done

- [x] Observable entry-dose acceptance and scientific limits named below.
- [x] Targeted RED, compatibility/state checks and future broad contour named.
- [x] Human merge/cleanup owner assigned; independent checker required.
- [x] Independent spec review on exact `fb06cb8`, READY with no blocking findings; author and checker results distinguished below.
- [x] Domain/API implementation and runtime contract extraction complete at reviewed3a28f99; whole M4 UI/M4d/native/owner gates remain separate.

## Public Contracts

M4b implements the additive typed shapes and normalized request/parameter
capture below. M4c now populates entry_load only after final prescription
validation, constrains generation and guards prepare/confirm. Typed optional
entry_adjustments records retiming, removals at the cap and retirement of completed
assignments. Historical receipts may omit both additions. M4b alone emitted no
supported/can_publish claim; M4c evidence and UI handoff are recorded in its report.
Behavior for a new preparation with unsupported initial dose changes deliberately
and is NOT advertised as behavior-compatible: it requires an explicit baseline.

Request addition history_coverage: status unknown | partial |
user_reported_complete; start_date and end_date_exclusive. It is a human claim
about recorded activity coverage, not provider/medical verification. Only a
claim covering the entire reference window supports interpreting empty days as
zero recorded exposure. Omission means unknown; no inferred complete default.
A declaration must cover the frozen as-of window and be retained in parameters.

Request addition initial_dose_limits: map of targeted sports. Each entry carries
source=athlete_declared, weekly_minutes>0, weekly_sessions positive integer,
max_session_minutes>0 <=weekly_minutes. Values must be finite, fit available
slots/time and be feasible for the catalog or yield an explicit refusal. These
are supplied starting limits, not measured history; no minimum dose is invented
when the map is absent. A targeted sport cannot silently disappear to satisfy
another discipline's cap. Unused sports have no invented baseline requirement.

Build/confirm and frozen goal_plan_snapshot addition entry_load:

    policy_version: entry-load-v1
    status: supported | needs_baseline | blocked | unassessed
    can_publish: bool
    scope: {start_date, end_date}  # cycle start through start+13 days
    profile:
      as_of, window_start, window_end_exclusive, context_start
      completeness: {status, source, claimed_interval}
      sports: {bike, run, swim: SportExposure}
      quality_limits: [{code, activity_id?, field?}]
    limits: {sport: {source, weekly_minutes, weekly_sessions,
                     max_session_minutes, source_window, scope}}
    blockers: [{code, sport?, date?, field, expected?, observed?}]
    warnings: [{code, sport?, field}]

SportExposure contains session_count, eligible_duration_session_count,
training_days, total_minutes, session_minutes list/summary, longest_minutes,
last_exposure_date/days_since_last, four ordered seven-day bins, and TSS totals
with method/coverage. Nullable summaries explicitly distinguish unknown from0.
TSS is labelled estimated/measured/mixed/unverified and is not converted between
sports or used alone to infer duration/intensity tolerance. Public summaries do
not need raw provider identifiers; internal source fingerprints retain identity.

New structured preparation errors:422 entry_dose_required (unresolved sport
baseline, entry_load context, no pending token), or422 entry_dose_infeasible
(no feasible final allocation inside constraints, same no-write boundary).
Existing409 stale/cycle conflicts and500 malformed/tampered frozen payload remain
unchanged. Successful pending creation requires both the M3 technical gate and
the entry-load gate; technical can_confirm alone does not grant publication.
A refused preparation exposes no pending token or confirm affordance.
BuildConfirmRequest stays exactly preview_id+confirm; no fresh
baseline fields or arbitrary payload are accepted by confirm. Changes to coverage
or limits require a new prepare. New build parameters are normalized and echoed,
not silently discarded. Reuse canonical API errors; a malformed input is422
validation, not a fabricated entry-load result.

API/TS additions require contract extractor/registry updates in Domain work.
Database tables unchanged: retain evidence in existing immutable preview/
checkpoint/receipt JSON. Runtime config gains only a versioned policy stamp;
no hidden environment-derived dose. CLI/provider/event transport unchanged.
Historical reads without evidence expose unassessed, without writing/backfill.
No new GET recomputes an old plan against today's history.

## State Boundaries and Identity

The profile uses **28 completed athlete-local days** [as_of−28,as_of), in four
consecutive7-day bins. The84-day context is [as_of−84,as_of); it describes older
exposure/gaps and cannot silently raise the recent reference. These are versioned
product windows, not physiological cutoffs. Same-day partial rows are excluded
from the reference and disclosed; future/invalid dates and missing/nonpositive/
nonfinite duration cannot supply positive duration evidence. Positive TSS without
duration remains known activity/unknown dose. Frequency distinguishes observed
sessions from those eligible for duration calculations.

Normalize sport aliases with the existing vocabulary. Canonical activity_id
owns deduplication: identical duplicate projections count once; conflicting
same-ID records are ambiguous. Dates/proximity cannot link sessions. For proven
complete multisport groups count stages once and exclude the envelope. For
partial groups report received stage exposure and unknown unallocated remainder;
never assign the envelope's entire load/duration to one sport, fabricate missing
legs or add envelope+stages. Preserve the existing authoritative aggregate-load
projection for CTL; it intentionally differs from a partial sport-exposure view.
Whether a valid zero-TSS stage exists does not determine whether its positive
physical duration was observed. Missing lineage remains a disclosed quality gap.

The exact source frame, lineage, date/timezone, coverage declaration, user limits,
cycle/selection revision and entry policy version belong to dependency_digest.
Capture any additionally needed reconciliation/ownership sources in the same
read transaction. No post-capture provider/SQLite/wall-clock lookup in calculation.
Entry scope retains cycle.start_date through edits; edit_current cannot restart
an entry allowance by using today's date as a new anchor. Explicit cap changes
create a new frozen intent/version, not an in-place rewrite of an old receipt.

## Initial-dose policy and acceptance criteria

**AC1 — factual profile.** Given the synthetic four recent runs, profile reports
run4/bike0/swim0 observed sessions with their valid duration and dated coverage;
changing only their sports to run1/bike2/swim1 changes that profile. With unknown
coverage those zeros mean no observed rows, not proven absence of training.

**AC2 — transparent reference, no transferred permission.** For a sport with
user-reported-complete28-day coverage, usable durations in every observed
session, and nonzero exposure in the most recent7-day bin, compute a proposed
observed reference: median of the four weekly duration sums (zero covered bins
included), floor(median weekly eligible session counts), and median eligible
session duration. Require positive reference values and a feasible assignment;
otherwise needs_baseline. Missing duration/unresolved multisport dose makes that
sport unresolved. This conservative repeat-exposure envelope is a **product
heuristic**, not a scientifically validated safe starting prescription. Older
context, global CTL, target distance, demand and spare hours cannot raise it.
Recent run exposure cannot supply bike/swim reference limits.

**AC3 — absent/partial/sparse inputs.** A sport without a usable observed
reference requires explicit athlete_declared starting limits. Keep those values
and their source distinct from measurements. Coverage remains partial/unknown
when a dose is declared; declaring20minutes never proves20minutes were trained.
Absent required limits produces entry_dose_required, listing unresolved sports
and the needed input, before retaining a token. Default catalog minima are
feasibility bounds and are not promoted to safe bootstrap doses. The user may
choose a starting dose with their coach; the application records that decision.

**AC4 — final prescription boundary.** During the entry scope, every rolling
seven-day window intersecting the scope respects each sport's weekly time and
session caps; every session/leg respects max_session_minutes. Count completed
physical exposure and remaining assignments once using trusted execution
identity; a same-day matched planned/completed session must not be counted twice.
If that partition is ambiguous, report blocked/data quality instead of silently
spending the full allowance again. The generator may reduce/retime only within
approved easy/recovery/catalog intent and must expose changed roles/limits.
Race-specific/manual intent cannot silently be replaced: a conflict is explicit.
No excess is redistributed to another sport to fill a weekly target or hours.
M3 still validates executable steps, effective TSS, time, forecast and identity.
If an executable assignment cannot fit, return entry_dose_infeasible, no token.

**AC5 — start/remaining horizon.** Initial caps bind the actual14-day cycle
entry scope including partial calendar weeks. Changing/editing/closing/opening
cycle selection cannot relabel prior facts as a new dose source. Future dates
beyond frozen as_of are not observations or assumed completed training. Later
weeks remain a projection using the existing explicitly labelled progression
heuristic, not evidence of adaptation. Do not jump back to a goal floor solely
because the entry scope ends; start and subsequent progression must remain
continuous under existing planner limits. M4 makes no suitability claim for the
whole horizon; repeated planning re-captures actual exposure.

**AC6 — atomic/fresh publication.** History/coverage/limits/policy changes stale
pending previews. Prepare applies technical M3 and entry checks before pending
creation. Confirm performs bounded pure validation of the frozen entry evidence
and final assignments before any active write, under existing CAS/ownership
rules; it does not rebuild the plan/Banister. Honest needs_baseline/blocked pending
cannot publish (409); dishonest/malformed ready evidence is500 preview_corrupt.
Applied old receipts replay before new gates; older unassessed pending requires
refresh. Existing reset/expiry/backup retention/transaction failure proofs stay.
Other mutation writers invalidate entry evidence along with stale M3 assessment
rather than carrying a supported badge after changing its source/assignments;
M4 does not silently extend a new numerical policy into every legacy writer.

**AC7 — scientific/product separation.** training_suitability stays not_assessed.
The profile is historical evidence; observed-reference and declared-dose limits
are explicit policy/intention; technical consistency never certifies health,
injury risk or training efficacy. Unsupported quality/intensity/skill claims are
not manufactured from duration/TSS. The source review in the report supports
individual/sport-specific monitoring and uncertainty, not the exact operational
28/84-day windows, medians or entry14-day duration. S4 consumes these server-owned
states and reasons; no domain mathematics moves into the browser.

## Failure, Reset, Rollback, Idempotency

No new persistent table/cursor. Evidence belongs to the same retained-preview
and append-only checkpoint lifecycle; existing full reset/backup/retention owns
it. Missing/malformed limits, nonfinite input, unknown lineage, impossible
allocation, stale sources and tampered evidence have explicit safe outcomes.
Retries return the original applied receipt without reassessment. GET/history
is read-only. New policy stamps invalidate old pending, not old applied receipts.
Rollback means discard the unconfirmed candidate/close its preview; no live
athlete data or historical recalculation. All rejection and injected-write-failure
tests compare every existing table, not only checkpoint count.

## Evidence Boundary Matrix

| Identity | Time/provenance | Evidence state | Fallback | Expected result / falsifier |
| --- | --- | --- | --- | --- |
| canonical single | before as_of, within28days | complete durations/coverage | observed reference | sport-specific counts/caps; relabel sports changes profile |
| canonical single | before context84 or after/equal as_of | present | disclose exclusion | cannot raise recent reference; partial today is not full-day evidence |
| canonical single | valid date | no rows + complete claim / unknown claim | declared dose / needs input | proven recorded zero differs from unknown capture |
| duplicate same ID | equal / conflicting fields | present / ambiguous | dedupe / unresolved | never silently sum duplicate dose |
| envelope + linked legs | explicit complete lineage | positive duration, zero/missing TSS possible | count observed legs | no envelope+leg double count; TSS0 does not erase duration |
| envelope + partial stages | explicit partial lineage | known stages/unknown remainder | disclose, require missing baseline | no invented per-sport split |
| selected current cycle | partial week/edit/current-day execution | completed + future/matched | trusted partition only | retain scope/caps; no reset/double allowance |
| historical receipt | old/missing profile/version | applied | replay/read old bytes | no reassessment/write; old pending refreshes |
| frozen preview | activity/declaration/limits/version changes | stale/tampered |409/500 | all active tables unchanged, no rebuild under lock |

## RED Matrix

| Acceptance criterion | RED test/probe | Expected failure now | GREEN evidence |
| --- | --- | --- | --- |
| AC1 | test_build_exposes_frozen_recent_exposure_per_discipline (two histories) | entry_load missing | NOT YET: Domain profile |
| AC3/AC6 | test_absent_bike_swim_exposure_does_not_create_publishable_token | prepare returns a pending instead of entry_dose_required | NOT YET: guard/all-table rollback |
| AC4 | test_final_entry_dose_respects_declared_limits_or_explicitly_blocks | first-week time/count exceeds supplied limits | NOT YET: constrained generation/final validator |
| purity compatibility | test_frozen_entry_characterization_never_changes_active_plan_or_settings | already GREEN control, not a new RED | focused control only, no full lifecycle claim |
| AC2/5/6/7 + multisport/time matrix | named future tests in ExecPlan | not executed as M4 RED | NOT YET; no fixture or source-review overclaim |

## ASR / ADR Traceability

ASR-REL-1: preserve actual exposure/history/receipt identity; REL-2: explicit data
gaps; MOD-2/3: one Python projection + additive typed contract/JSON compatibility;
PERF-4: bounded90-day profile outside writer lock,16-week preview target unchanged;
DEP-2: no new table/reset owner. ADR-0001/0002/0003/0006/0008/0009 reused.
New boundary: sport-specific partial lineage/coverage versus authoritative global
load and human-declared dose. Independent checker must audit that boundary;
no new ADR required unless implementation changes source ownership.

## Delivery Slices

1. M4a (current): evidence/science/spec/template/BDD RED; independent review.
2. M4b: pure profile, frozen coverage/limits/lineage/version; contract first and
   profile boundary RED→GREEN. Do not expose publishable supported state early.
3. M4c: entry-constrained generation + prepare/confirm guard, honest failure,
   reuse/drop semantics for other mutations, all-table replay/reset/backup probes.
4. M4d: full contributor/contract/browser acceptance and bounded native review;
   separate explicit UI/Design handoff for S4, human owns merge and rollout.

## M4b implementation checkpoint

Domain/API consumes the reviewed AC1–AC7 without changing their acceptance.
models/planning_entry_load.py provides pure build_entry_exposure_profile and
derive_entry_limits. The first returns factual sport exposure and explicit
quality limits; the second returns needs_baseline or unassessed with
can_publish=false until M4c checks final assignments. Valid observed limits may
be lowered by an explicit declared ceiling, retained separately as provenance;
declarations do not inflate the observed reference. Missing reference falls
back only to a supplied athlete_declared dose. Target sports are explicit.

api/planning_entry_contract.py owns typed input/profile/limit/assessment shapes;
CycleBuildRequest and BuildParametersResponse accept/echo new fields. Shared
capture validates them for HTTP and Coach/non-HTTP callers and binds their
normalized bytes and entry-load-v1 in dependency_digest. web/lib/types.ts and
registry/extractor mirror the shape; no component/UI behavior changes.
M4b publishes no entry assessment in build responses; AC3/4/6 final-builder RED
remains expected until M4c. Existing applied replay/read history are preserved.
[Executed results and remaining gates](reports/2026-10-21-planning-entry-load-m4b/README.md).

## Evidence Bundle

Runtime baseline main `9d679b3`; branch base `99a6a1f` additionally contains
#704/#692 documentation. First synthetic falsifier in the report is
characterized, not preregistered algorithm selection. Executed: spec 1 passed /
4 strict XFAIL; --runxfail 4 intended assertion failures / 1 passed; compatibility
134 passed / 4 XFAIL / 1 warning (24.44s). Probe and Ruff passed. See report. Full S3 baseline3836local/3813CI is historical,
not an executed M4 broad pass. Runtime/contract/CI M4 GREEN and all-table/reset
proofs: NOT YET. Residual risk: user-declared limits may be unsuitable and a
history envelope does not measure tolerance. No clinical safety verdict.

## Review Findings

M4b delta round 1: reviewed `58d838b..176b77e1bf48a39a6cf9d37d6f554a7472fc4c6f`; **READY for M4c handoff,
zero blocking P1/P2**. Independent tests: 83 passed in 3.63s; additional
storage/preparation/M3/multisport 145 passed in 26.91s (one existing warning),
changed-Python Ruff passed. HEAD unchanged and tracked tree clean before/after;
parent push changed tracking only. No findings need disposition. Author separately
ran final contributor-safe: 3921 passed / 16 skipped / 82 deselected / 4 expected
XFAIL / 7 warnings in 238.78s; lint/build/extractor/inventory green. Native remains
0/2 until stable M4d. Following documentation record changes no runtime/test/AC.


Round 1: independent read-only checker reviewed full `99a6a1f..fb06cb8` plus
relevant capture/readiness/lineage/confirm boundaries. **READY for M4a handoff;
zero blocking P1/P2**, no findings to dispose. Independently reproduced 1 passed /
4 strict XFAIL (1.28s), --runxfail 4 intended assertion failures / 1 passed
(1.10s), and Ruff. Status clean before/after; only parent push changed upstream
tracking. The 134-test compatibility contour was author-run, not checker-run.

Author self-review record: add proposed M4 ASR status in the living catalog and
pin this exact reviewed checkpoint. These documentation metadata corrections
change no policy, runtime or tests; no extra full-diff round is requested for
review bookkeeping. Future blocking changes require a scoped correction within
the remaining independent budget. Findings use severity → Observed → Inferred →
executed falsifier/NOT YET → AC/gate and fixed-in/follow-up/disputed disposition.

## Native Review Rounds

| Round | Reviewed head | Trigger | Findings disposition | Stop/exception |
| ---: | --- | --- | --- | --- |
| 1 | 7b98ff3045d135e825e3c54db06659af4e7d0001 | manual after stable candidate/CI | clean receipt6326085434; zero findings | accepted by owner, merged00de158 |
| 2 | unused | not needed | no request | budget1/2 used |

## Final Verdict

**MERGED:**#711 accepted head7b98ff3 merged as00de158 on2026-10-22
00:01:23 Europe/Moscow. Functional CI39670959095 and fresh Review gate green;
native round1 clean [receipt](https://github.com/rbctmz/ai_trainer/pull/711#issuecomment-6326085434)
confirmed current head, zero review threads. Owner explicitly accepted review,
label and merge; no budget exception, admin bypass or second native round.
Earlier checkpoint paragraphs below remain historical evidence. Nonblocking
announcement suggestion now#712; no AC, policy or suitability claim changes.

M4c implementation evidence (AC unchanged): [report](reports/2026-10-21-planning-entry-load-m4c/README.md). Stable-head independent review and final M4d/native/owner acceptance remain separate.

M4c delta round1 BLOCK on149dbf5 (real demand writer retained supported evidence),
**fixed-in3a28f99**. Scoped round2 READY on3a28f99:176passed/1warning42.17s,
Ruff green, tracked clean. Author stable contributor-safe3965passed/16skip/
82deselected/7warnings265.45s. Operational thresholds and AC1–AC7 unchanged.
Original M4a REDs are GREEN. The historical missing-input UI gap is resolved by
the explicit consumer handoff reviewed atf0650b5; native0/2 is reserved for the
stable whole-delivery candidate. No acceptance criterion above is changed.


UI delta round1:46e17f4..f0650b53d8e394a84db539387b699da17f35acdd,
**READY, zero blocking P1/P2**. Independent5entryE2E passed/1existing warning
(12.74s); changed-test Ruff passed. First sandbox attempt stopped at localhost
setup permission errors, so it is not counted as a UI result. Authorized rerun
used the isolated harness. Source head unchanged; same12 known regenerated PNG
paths before/after, no source edits. Nonblocking suggestion: live announcement
or heading focus for structured refusals; **follow-up #710**, no reproduced
screen-reader failure or acceptance claim.

Author M4d local onf0650b5:3965 passed/16 skipped/87 deselected/7warnings
(277.59s); all63 isolated E2E passed/1warning(189.89s); earlier focused41passed.
Ruff, web lint/build, extraction freshness/inventory and diff check green.
[UI evidence](design/evidence/issue-710/README.md). Final native receipt belongs
on #711, bound to its reviewed SHA; no documentation-only post-review push.


UI scoped round2/2 READY at6895cc0ef426b446b7009c5c8645fe7dcddad43e: no
new blocking P1/P2. Independent5E2E passed/1existing warning10.78s, Ruff green.
The reviewer confirmed stronger coverage, real keyboard activation and unchanged
refusal assertions, with no product-code changes; the earlier failure cause
remains inferred. HEAD unchanged, only three known synthetic PNG regenerations.
Those generated differences were restored, not included as unrelated evidence.
UI delta budget exhausted; native0/2 remains reserved for whole-delivery review.


Post-merge record only: merged tree equals accepted head; main CI39675328437
was running at the snapshot. See[metrics](engineering_process_metrics.md).
Post-merge documentation is a separate Class C delta, not a new native round or
source push on the accepted product candidate. Parent#677 remains open.


2026-10-24 status: main CI39675328437 verified SUCCESS; parent#677 closed via
#717. The preceding staged/pending statements are historical evidence, not
remaining implementation work. Post-merge records from#713 are included in#716;
the combined documentation candidate has its own review/owner merge decision.
