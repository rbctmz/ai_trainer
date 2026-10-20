# S3 M3: final load consistency and atomic build readiness (#677)

This living ExecPlan follows `.agent/PLANS.md`, the approved M1 contract in
`docs/planning_build_readiness_slice_spec.md` and M2 implementation `5aa8f6e` /
draft #706. The human explicitly authorized Domain/API M3 on 2026-10-20.
Class A: prescription validation, additive API contracts and publication semantics.
Independent read-only checking is required by repository workflow; merge owner is
human. Work occurs on codex/issue-677-s3-m3 in the existing managed worktree.

## Purpose / Big Picture

A new plan may be previewed and saved only when its future assigned sessions
contain executable instructions and all delivered loads/times agree. A technically
ready plan does not prove personal training suitability. Invalid preparation
returns 422 plan_not_ready with reasons and creates no token; invalid pending
confirmation refuses before active writes. Historical receipts replay as before.

## Progress

- [x] (2026-10-20) Verified M1/M2 handoff, branch and parent issue; role Domain/API, Class A.
- [x] (2026-10-20) Read M1 AC1–AC7, ADD3/ASR/ADR, workflow and transaction ownership.
- [x] (2026-10-20) Synthetic final-candidate probe: typical leaf loads/steps already agree; final totals currently sum rounded weeks.
- [x] (2026-10-20) Add behavioral RED for final assessor, aggregate/time/target boundaries and both-origin atomic guards.
- [x] (2026-10-20) Implement pure normalization/assessment and frozen input binding; prepare/confirm and historical compatibility.
- [x] (2026-10-20) API/TS/contracts, targeted/rollback/replay/performance tests; 117 latest focused GREEN.
- [x] Full contributor3816, full browser58, final contracts/Ruff/web lint/build and independent READY.
- [x] Independent2/2 READY; stacked draft #708 attached, #677 evidence posted and read back.

## Surprises & Discoveries

Observed: M2 future event-free candidate has no leaf-vs-parameter/step TSS mismatch.
Inferred: the remaining load issue is aggregate lineage/rounding, not a reason to
rewrite prescriptions. Verified by: temporary SQLite pure _calculate_plan_build
probe at identical frozen inputs; zero mismatches over the generated leaves.

Observed: _calculate_plan_build sums int weekly displays, and checkpoint builder
also derives header totals from rounded weeks. Inferred: rounding can accumulate
into a different whole-plan total. Verified by: upcoming small two-week boundary
fixture compares round(sum(raw)) with sum(round(weeks)); execution RED recorded
before replacement. No scientific dose or periodicity formula changes are needed.

Observed: apply_preview owns BEGIN IMMEDIATE and replays applied receipts before
pending eligibility. Inferred: adding bounded retained validation before insertion
can preserve transaction and replay guarantees. Verified by: existing commit,
rollback and receipt tests plus the new malicious retained-artifact controls.

## Decision Log

Use original effective leaf TSS once. Normalize new future daily rows from
sessions/legs, weekly rows by calendar date, and whole-plan total from unrounded
daily values. Weekly display remains integer; discipline display rounds each
column independently. Preserve past daily/session JSON during edit_current.
Allocated/requested/base TSS are budgets, not asserted equal to delivered TSS.
Date/author: 2026-10-20 / Domain/API, implementing M1 AC2.

Persist forecast input rows (planned and race-effort TSS separate), initial load
metrics and an input fingerprint. Build forecast from that final daily sequence;
assessor checks inputs and frozen output binding without rerunning Banister under
the writer lock. Race effort is forecast-only, never an exportable exercise or
part of weekly training totals. Date/author: 2026-10-20 / Domain/API.

Assess serialized final checkpoint snapshot, public response and frozen context.
Fingerprint excludes assessment, assigned plan ID and receipt/parameters decoration;
includes full remaining plan/response and captured parameters/context. Add readiness
policy to dependency versions. Existing v1/v2 response models keep readiness optional
only for old applied receipts; every new prepare enforces assessment server-side.
Missing old pending assessment requests fresh preview. Honest blocked assessment
returns 409; malformed/false-ready/fingerprint mismatch is 500 preview_corrupt.
Date/author: 2026-10-20 / Domain/API, implementing M1 AC5/AC6.

Assessment and forecast evidence are attached only by this build path after normal
checkpoint serialization. Other writers do not inherit a stale ready assessment:
new non-build checkpoints remain unassessed. Historical reader projects stored
assessment or explicit unassessed without database writes. No new table/backfill.
Date/author: 2026-10-20 / Domain/API.

## Context and Orientation

api/planning_service.py captures dependencies, calculates outside transactions,
then data/planning_build_preview_store.py retains and atomically applies bytes.
models/planning_checkpoints.py serializes a whitelist, so assessment is attached to
the final serialized goal_plan_snapshot in the build path. New
models/planning_build_readiness.py owns pure validation and normalization.
api/planning_build_contract.py and web/lib/types.ts mirror additive DTOs; no CSS
or UI interaction work. tests/smoke/_planning_build_confirmation.py supplies pinned
synthetic fixtures. All database paths are temporary; no athlete DB/provider calls.

## Milestones

First, add direct and public-HTTP RED tests against M2. Keep M1 four strict XFAIL
until implementation; record --runxfail failures and remove marks only on GREEN.
Exercise malformed target/unit/finite/provenance, bad composite leg and transition,
last-day inclusivity, unchanged past legacy, explicit zero/rest, rounding and
aggregate mismatches. No missing-module error is represented as a behavioral bug.

Second, implement pure final projections and readiness. Every single/leg must have
materialized status, steps, valid finite ranges/units/provenance and consistent
load/time. Composite duration equals legs plus explicit transition. Validate final
future weekly hours and declared available days; this request schema has no daily
minute-limit field, so none is invented (#668 remains separate). Historical past
assignments are not newly assessed or counted as new availability commitments.
Budget/base arrays are intentionally not effective-load assertions.

Third, integrate prepare refusal before store_pending and pending validation inside
apply_preview before active writes, after old applied replay. Validate both origins,
frozen signatures, stale/CAS/closed/expiry guards and rollback. Add no provider or
Banister call to confirm. Mirror contracts and historical unassessed read projection.

Finally run focused, contract and broad contributor checks with venv in PATH and a
writable isolated checkout. Check actual 16-week candidate, total guard latency,
reset/restore/restart and every-table snapshots. Independent checker gets exact
ref/diff and approved read-only checks; at most two rounds, second scoped delta.
Publish a draft stacked on M2 and record evidence in #677; no native/merge implied.

## Concrete Steps

From worktree root, with source venv and temporary DATABASE_PATH / DEMO_DATABASE_PATH
and CHATS_DIR, run these commands, retaining logs outside the repo:

    python -m pytest tests/smoke/test_planning_build_readiness_spec.py --runxfail -q
    python -m pytest tests/smoke/test_planning_build_readiness_m3.py -q
    npm --prefix web run contract:extract
    npm --prefix web run lint
    npm --prefix web run build
    python -m pytest tests/smoke/test_planning_build_commit.py tests/smoke/test_planning_build_preparation.py tests/smoke/test_planning_build_coach_confirmation.py -q
    python -m pytest -m "not live and not debug and not e2e" tests/ -W error::pytest.PytestReturnNotNoneWarning
    python -m ruff check .
    git diff --check

Expected outcome: new valid plans return ready and identical retained/confirmed
assessment; blocked prepare returns no token and all-table state is unchanged.
M1 XFAIL are removed once four cases are actual passing assertions. CI and native
review are separate from local author/checker evidence.

## ASR / ADR and non-goals

ASR-REL-1/2 protects complete prescription and historical identity; ASR-MOD-2/3
keeps Python-owned policy and old receipt compatibility; ASR-PERF-4 bounds pure
validation under lock; ASR-DEP-2 reuses reset/backup ownership. ADR-0001 reused.
M4 sport-specific return-to-training dose, clinical suitability, #703 thresholds,
#668 sport availability and S4 design are outside scope. Public target norms and
scientific training formulas are unchanged. Runtime work is not a main rollout.

## Idempotence and Recovery

All experiments are temporary synthetic SQLite or pure functions. Pending refusal
has no active writes; confirm transaction rolls back. Existing applied receipt is
read before new eligibility and must not republish/reopen historical cycles.
Missing historical assessment is unassessed, never backfilled by a GET. Reverting
code leaves additive JSON readable; policy/version changes stale pending artifacts.

## Outcomes & Retrospective

Implementation and targeted controls complete; final results, failures and review dispositions will be recorded in
`docs/reports/2026-10-20-planning-readiness-m3/README.md`. Do not claim personalized
training suitability or all plan mutation paths protected by this build-only slice.

Revision 2026-10-20: explicit M2→M3 handoff; materialization already repaired,
publication and final load lineage now authorized. No scope extension into UI/M4.

Implementation decisions 2026-10-20: use math.fsum at rounding boundaries; explicit
load_provenance distinguishes estimates/derived/leg sums. Known immutable catalog
policy prevents a forged RPE map using a valid policy name. Added a capped light
Recovery dose and activation NP TSS after separate behavioral RED. Original SQL
fixture timestamps were not frozen; pin synthetic inputs rather than weaken the
candidate binding. Demo fixture uses declared manual phases so the guard stays
active. See slice review matrix and report for verified evidence and remaining
unallocated pre-race activation refusals.

## First independent review and regression triage

Round 1 exact diff 5aa8f6e..d8d516f: three blocking P2 reproduced by the
read-only checker and independently by author. Five behavioral RED assertions
showed ready despite sport mismatch (single/leg), unsupported CSS target method,
and missing/reversed required brick legs after all arithmetic was resynchronized.
Narrow fixes bind sport and target method to immutable definition and required
ordered legs to composite requirements. The five semantic controls are now GREEN.
No parent role was invented for leg DTOs. Checker independently ran197 core and59
conformance tests green at the reviewed head; that is not a final-delta verdict.

Broad first run:15 failed/3796 passed/16 skipped/82 deselected. Two old activation
assertions equated requested budget with effective power load; controls now assert
both separately. Legacy demand confirm unintentionally acquired the new build
publication guard: removed this scope expansion, and explicitly strip readiness /
forecast evidence on this non-build writer. Demand regression asserts no inherited
assessment. Other old successful Coach/CAS fixtures used incomplete Sunday/event
plans; move those protocol controls to the same pinned feasible Saturday candidate,
retaining genuine HTTP blocked cases. A new cycle with the same goal still changes
selection/version and must invalidate the older proposal.

Demo empty-history matrix:10h manual fixture blocked at75.6TSS/100min swim quality;
8h and6h ready for both empty and seeded activity histories. Choose8h synthetic demo;
do not bypass guard or expand catalog just for a fixture. Standard training-goal
E2E edit initially blocked at20.2TSS/50min long-bike; explicit12h/all-seven-days availability still blocks. Final success protocol control
uses the existing executable manual8h demo; guard is never weakened. Browser refusal response is now asserted
before waiting for success text. No browser CSS or product interactions changed.

Oracle regeneration inspected complete six-case plans: only build_readiness
blockers changed (known matching sport eligibility message); existing-plan binding
also changes because captured previous checkpoint contains that assessment. Two
independently recreated full-payload sets match6/6 exactly. Old v3/v4 oracles remain
unchanged. Current oracle remains full-payload, not TSS-only or field-stripped.

Second full run and targeted Planning E2E are pending at this commit. First broad
E2E was stopped after repeated timeouts; temporary process groups were identified
and stopped explicitly, primary8000/3000 untouched. It is not counted as a pass.

## Final runtime verification snapshot

Contributor run2:3816passed/16skipped/82deselected,246.11s, command with normal
not-live/not-debug/not-e2e selection and return-value warnings as errors. Ruff
--no-cache GREEN. Python runtime has not changed since60c2343. Review fixes5 GREEN.
Planning confirmation + Coach card + lifecycle browser scenarios:36passed52.90s.
Coach UI fixtures now use actual origin=coach prepare/confirm on declared manual
inputs; AITools adapter remains covered by the separate true tool tests. No mocked
successful readiness/artifact is inserted. Existing screenshot fixtures are restored;
M3 screenshots live in its own evidence folder. Complete E2E is still pending.

## Outcomes / retrospective

Full E2E:58passed/1warning in176.03s (real isolated API/Next/Chromium, no user DB
or provider writes). Planning/Coach/lifecycle subset36passed52.90s. Complete broad
run3816passed/16skipped/82deselected246.11s. TS contract --check, inventory (inside
broad), Ruff --no-cache and diffcheck GREEN. Web lint/build completed successfully
before d8d516f; web/types/contracts have no changes since then. Existing historical
S1 screenshots regenerated by full E2E are restored one named file at a time after
proving clean pre-run state and matching screenshot writers; M3 captures retained
separately. Temporary E2E process groups cleaned by harness; primary stack untouched.

Independent round2 scoped delta READY at3eafc7b,199passed32.81s; all3 P2 fixed-in
60c2343,zero remaining blockers. Stop after this second round; native rounds0.
No further runtime edits. #707 records low-dose Base-long and off-slot race
activation leftovers with pure paired probes, exact inputs and proposed bounded
acceptance. These remain explicit safe refusals, not completeness success.

M3 is implemented/verified, without personal suitability assessment. Remaining
publication step: stacked draft on codex/issue-677-s3-m2, attach it, record/read back
#677 evidence. No merge, approval label, working athlete DB change, personalized
entry dose or S4 UI work is authorized by this completion record.

## Publication / handoff

Draft [#708](https://github.com/rbctmz/ai_trainer/pull/708) targets
codex/issue-677-s3-m2 (M2 #706), attached to the current task. Initial publication
head56d1b8b0c18501226558440dcfa731aedfb206f4, runtime60c2343, independent reviewed
head3eafc7b. Later publication record is docs-only. Parent evidence:
[#677 comment](https://github.com/rbctmz/ai_trainer/issues/677#issuecomment-6286793899).
Generator follow-up #707 body read back. #677 stays open. No label acceptance,
merge, rollout or cleanup claimed.

Initial remote snapshot: Gitleaks/Web contract/link successful; contributor and
Playwright CI in progress. Review gate failure reason verified from run39393549722:
`no submitted native review for the current head`. This is a missing native-review
gate, not a functional-test verdict. Do not bypass it with an acceptance label.
Final local tests remain green; remote current-head status must be checked again
by the merge owner. Worktree retained; unrelated primary-checkout changes were
observed during final read-only status and left untouched.

## Native round1: preserved identity collision (2026-10-20)

Native review of73aaab8 found one blocking P2 at
https://github.com/rbctmz/ai_trainer/pull/708#discussion_r4323327788.
Observed: assessor skipped days outside future scope before adding their IDs to
seen_ids. Author reproduced4 behavioral RED: future parent/leg reuses preserved
parent/leg ID and is marked ready with empty blockers. A separate historical
legacy/duplicate control remains ready. Initial test setup date parsing/missing
past brick errors are fixture errors, not represented as behavioral RED.

Inferred: reservation must cover preserved IDs without widening prescription
assessment into history. Verified by: scope-correct serialized candidate, actual
forecast adapter (no unrelated forecast blocker),4 ready[] assertions RED, then
all5 controls GREEN after seeding seen_ids from preserved nested sessions and
legs. Real find_planned_session on duplicate parent ID selects the old day, a
cheap falsifying check of the downstream lookup concern. Pure validation leaves
past plan/response/context unchanged, including old malformed prescriptions and
history-only duplicate IDs. No consumer mutation or live write was executed.

Fix only reserves nonempty string parent/leg IDs outside assessment scope before
future validation; it neither rewrites IDs/history nor introduces historical
prescription blockers. Future collision reports its date/parent/leg field, and
parent blocker address now names the actual assigned parent. API/TS unchanged,
no new version/backfill/medical or generator policy. Existing applied replay stays
before pending assessment; no receipt reassessment is added.

Targeted207passed51.22s (readiness/spec/commit/Coach/cycle), compatibility69passed
11.01s (transfer/preparation/full-payload storage), exact5passed1.28s, Ruff,
contract freshness and diffcheck GREEN. Full contributor run is pending. An initial
run used a nonexistent temporary parent directory; an isolated dashboard control
reproduced sqlite3 unable-to-open-file, unrelated to readiness. Create the test
directory and rerun without product code changes; do not call that failed run GREEN.
Native budget1/2, second verification must be scoped since73aaab8 after final CI.
No new independent full review (previous2/2 used), no accepted labels/merge.


Native-fix verification update: initial full run20failed/3804passed/13skipped,
82deselected,239.72s; every failure is sqlite unable-to-open-file from the missing
temporary parent. Same dashboard control without directory1failed; with created
separate temp directory1passed, no product changes. Complete rerun uses pre-created
/private/tmp/ai-trainer-m3-native-rerun/chats and DB siblings. This rerun is still
pending at fix commit; exact result will be recorded in the native thread before
verification request, without an extra documentation push after native review.
Final small subset10passed after the optional parent blocker address remained
nullable-string even for malformed IDs. Ruff/contract freshness/diffcheck GREEN.


## Dependency native fixes and integration (2026-10-20)

Human asked to finish and continue the full stack. Supervisor/Integrator handoff:
M1 d13d013 has green CI and clean scoped native round2; M2 dbf9772 fixes three
native P2 findings,203 targeted GREEN and3754 contributor-safe passed,16 skipped,
82 deselected,4 expected strict M3 XFAIL in207.40s. M2 final native is pending
stable CI. Native budgets M1 2/2, M2 1/2, M3 2/2; no third M3 review is requested.
M3 accepted clean receipt names32ab8712ef, not the later integrated candidate.

Merged M1 documentation corrections and M2 native fixes locally without rewriting
history. Conflict resolution preserves M3 activation-derived TSS, bounded Recovery
replacement, explicit composite leg status and atomic readiness guards alongside
raw RPE validation, explicit legacy stage identities and downward fallback
quantization. New integrated materializer v8 distinguishes v6 M3 and v7 M2 inputs;
matching version assertions and oracle pins change, with no new training policy.
No UI/API contract/acceptance changes; role stays integration of bounded fixes.

Pure pinned experiment reproduced old readiness-v1 oracle6/6 using original M3
catalog source. Full payload diff inspected: legacy segment kinds, version and
resulting session/leg/fingerprint identities change; readiness candidate hashes
and blocker addresses follow those identities. Daily-plan/events/science/forecast
hashes are identical6/6. New separate readiness-v2 oracle keeps complete-field
comparisons; all older fixtures stay unchanged.

Run integrated generation/readiness/confirm/receipt/lifecycle regressions, full
contributor-safe contour and current-head CI before owner acceptance. Main/user
DB/providers are unchanged. Because imported blocking native fixes advance M3
past its exhausted two-round budget, docs/loop_engineering_instruction.md requires
explicit privileged-owner review-budget-exception plus review acceptance for the
final tested head; the old accepted label does not authorize that exception.
Prepare the concrete evidence first, then request that final owner decision.
