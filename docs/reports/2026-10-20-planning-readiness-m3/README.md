# S3 M3 evidence: final consistency and publication readiness

Parent #677; M2 base 5aa8f6e / #706. Class A, Domain/API; human authorization
2026-10-20. All probes use synthetic temporary SQLite/TestClient, no athlete DB,
.env, private runtime logs, live API/provider calls or live writes.

## Observed / Inferred / Verified by

Observed: original four M1 assertions fail on M2 because readiness is absent.
Verified by: --runxfail -> four AssertionError RED. They now pass unmarked.

Observed: Recovery bike long 46.6 TSS /115 minutes/deep_fatigue returns fallback,
even with no events. Inferred: dose exceeds the recovery template's own envelope;
not a reason to relax catalog bounds or rename pre-race activation. Verified by:
new pure RED, then explicit smaller light replacement GREEN. Existing Recovery
role, impossible-request and hours tests remain required.

Observed: activation bike20min/request24 gives power-derived12 TSS, but stored
parameter target24. Verified by: dedicated RED, then existing named NP/TSS method
also applied to activation. Targets and derived-bound thresholds unchanged.

Observed: a week with run sum115.5 could be compared as115 using naïve float sum,
while display was116 after its one-decimal projection. Inferred: float accumulation
near .5, not a legitimate load difference. Verified by: 16-week event control and
stable math.fsum projections. Whole total uses raw daily sums once; preview delta
uses the same before/after total rather than summed rounded weeks.

Observed: full-payload hashes changed between identical-looking test runs, while
only readiness/response/checkpoint hashes drifted. Verified by: two snapshots
showed different activities.created_at/profile.synced_at/constraint.created_at
SQL timestamps. Pin those synthetic source timestamps; do not strip context from
production fingerprints. After pinning, two complete six-case sets match exactly.
Archived M2 reproduced all six original catalog-v4 oracle cases before this change;
original v3/v4 fixture files remain unchanged. Separate readiness-v1 oracle keeps
all fields, including false/blocked assessment for legacy characterization inputs.

Observed: demo's former event/short-long assignment is not executable under the
new guard. Verified by: offline demo seed probe. Demo fixture now declares manual
phases (Recovery/Base/Build/Recovery/Base/Base/Build/Recovery), no fictional race,
and still goes through shared prepare/confirm validation. Conformance passed at
124-test checkpoint; final suite follows below.

Discarded: a new historical GET test initially hit date-vs-datetime under the test
PinnedDateTime subclass. Restoring the native parser class just for that GET while
keeping athlete-day helpers pinned resolves it. No production clock defect or
unrelated clock-code fix is claimed.

## Boundaries / measurements so far

Final-build scope and transaction behavior follow M1. Every future parent and leg
is checked; old past assignments and applied receipts are not rematerialized.
RPE/definition integrity uses immutable catalog constants. Power load is derived;
run/swim/relative targets explicitly retain an estimate. Candidate/forecast bindings
cover the final serialized artifact, not an intermediate draft. Current build guard
covers UI and Coach; other mutation checkpoints deliberately become unassessed.

Latest focused M3+storage+preparation: 117 passed in23.87s. Previous protocol,
Coach, HTTP:172 passed; original S2+M3 contour89 passed; conformance/inventory with
manual demo124 passed at its checkpoint. Four M1 XFAIL removed after actual GREEN.
Valid 16-week Saturday A control prepares/confirms within10s per operation; same
calendar with Sunday A exposes unallocated activation and is blocked with reasons.
This remaining unsupported event arrangement is retained as rejection evidence,
not hidden by altering rest/activation intent or weakening the guard.

Full contributor, final contract/lint/build and independent review are in progress;
no full GREEN, native review or merge claimed. Final disposition appended below.


## Independent round 1 / author reproduction

Full diff5aa8f6e..d8d516f:3 reproduced blocking P2, author RED5 failed (sport single
and leg, unsupported CSS bike targets, missing/reversed brick legs), then GREEN5.
Assessment now checks matching known definition sport, allowed target_preference,
and exact ordered requirements. No claim of an external HTTP digest exploit.
Independent checker197 core +59 conformance GREEN, clean unchanged head/status.
Dispositions: all three fixed in the subsequent fix commit; final scoped verdict
is pending. Native rounds0, independent full rounds1/2.

Broad first run15failed/3796passed/16skipped/82deselected in233.59s. Narrow triage:
legacy demand guard was unintended outside AC5; removed, explicit unassessed
checkpoint regression added. Bike activation old budget-equality assertions now
check retained request and independently recomputed effective power TSS. Other
Coach/CAS/characterization success controls use feasible pinned candidates; real
incomplete-Sunday controls stay blocked. Demo manual8h passes both empty/seeded
history matrix (10h empty failed swim quality75.6TSS/100min). These are synthetic
fixture choices, not personalized dose prescriptions.

Planning E2E initially timed out on a blocked20.2TSS/50min long-bike. Add explicit
build HTTP assertion and feasible availability in protocol success controls. First
broad E2E was interrupted, not passed; temporary servers were stopped without
touching the user's primary stack. Remaining unsupported low-dose Base-long/event
activation arrangements must be tracked for a generation follow-up, not waived.


## Post-fix checks

Contributor-safe suite:3816passed,16skipped,82deselected,7warnings in246.11s.
Command: venv PATH + temporary DATABASE_PATH/DEMO_DATABASE_PATH/CHATS_DIR;
`python -m pytest -m "not live and not debug and not e2e" tests/ -q
-p no:cacheprovider -W error::pytest.PytestReturnNotNoneWarning --tb=short`.
Existing FastAPI/httpx deprecation and six wrapped-SQLite/pandas warnings remain;
no returned-non-None test warnings suppressed. Ruff --no-cache and diffcheck GREEN.

Browser Planning+Coach+lifecycle:36passed in52.90s on isolated temporary servers.
Unsupported ordinary training-goal remained blocked even with12h/all-seven-days;
success protocol controls explicitly choose executable manual8h inputs. Coach card
control uses real origin=coach prepare and real bound approval/replay, while true
AITools generation is separately exercised by tool tests. No UI/CSS implementation
or browser-local business rule was introduced. Full browser suite still pending.


## Final verification and dispositions

Full browser suite58passed,1existing FastAPI/httpx deprecation warning in176.03s;
all isolated API/Next/Chromium servers shut down. Planning/Coach/lifecycle36passed
subset is part of that58, not additional coverage to sum. Contributor3816passed
is a separate no-live/no-debug/no-e2e contour. Final TS contract extractor --check,
Ruff --no-cache, inventory and whitespace GREEN. Web lint/build successful; no
web/type/registry/artifact change after the verified build snapshot. No personal
runtime DB, credentials, user API8000/3000 or provider was modified.

Independent scoped delta round2 READY at3eafc7bf6070904c3c97b2265b6ca6bbd8223e41;
runtime60c234371bb2666369946ec7375077d4af05909e.199passed32.81s. All3 reproduced P2
fixed-in60c2343. Round1 sport definition, target_preference and ordered composite
requirements are now enforced;5 exact semantic RED→GREEN cases. Reviewer wrote no
files and HEAD remained unchanged. Post-review changes only record evidence.
Review budget2/2 (one full + one scoped),native0; stop, no merge acceptance.

Generator gaps and paired falsifying checks tracked/read back in [#707](https://github.com/rbctmz/ai_trainer/issues/707).
[Planning retry screenshot](browser/planning-uncertain-390.png) and
[Coach retry screenshot](browser/coach-uncertain.png) are synthetic M3 evidence.
Worktree is retained for review. Human owns merge and cleanup. CI/native acceptance
will be reported separately; local GREEN is not a remote CI or deployment claim.


## Publication

[Draft PR #708](https://github.com/rbctmz/ai_trainer/pull/708), stacked on M2#706;
attached. Initial head56d1b8b0c18501226558440dcfa731aedfb206f4; subsequent publication
record only changes docs. [Parent evidence](https://github.com/rbctmz/ai_trainer/issues/677#issuecomment-6286793899)
posted/read back; #677 remains open. #707 read back. No accepted labels or merge.
Initial remote checks: Gitleaks and Web contract SUCCESS, contributor/E2E running;
Review gate FAIL with verified reason `no submitted native review for the current
head` (run39393549722). Current-head CI/native acceptance remains a separate
merge gate; local58 browser and3816 contributor results do not replace it.
