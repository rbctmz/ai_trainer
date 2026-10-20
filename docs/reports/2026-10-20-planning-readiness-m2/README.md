# S3 M2 evidence: Recovery, feasible selection, RPE

Parent #677; stacked on M1 #705 / 7550d2e. Class A. Human authorization:
2026-10-20, Domain/API M2 only. No personal DB, .env, runtime logs, live API,
provider writes or user plan mutations. All observations below are synthetic.

## Scope and contract

M1 AC1/AC4 generation slice: Recovery prescribed explicitly, requested vs effective
roles recorded, feasibility before novelty, easy bike excludes sprints. Failed
quality requests can be downgraded only in Base/Build/Maintenance, with explicit
quality_to_easy evidence and real role/description. No increase beyond requested
TSS or duration; also fit the shortest failed candidate duration to avoid a blind
projection becoming longer when power targets resolve. A request exceeding the
entire eligible quality catalog load ceiling remains refused. Taper/Race Week
sharpening, activation and absolute-target math remain unchanged.

New versions: workout_catalog_v4 / workout_selector_v2 / workout_materializer_v5;
all changed immutable definitions increment version. Relative targets retain the
existing rpe_1_10 DTO, now with catalog-rpe-v1 / template policy provenance.
Definitions freeze an explicit stage map. No new top-level API/TS model, table,
clinical restriction or independent readiness verdict is added. M3 still owns
publication guard and complete load lineage; M4 owns personal entry dose.

RPE stage ranges are conservative application coaching defaults, not individual
physiological calibration. Warmup/cooldown/recovery 1–2; recovery/technique main
2–3; endurance 3–4; progression/tempo 5–6; threshold 7–8; VO2 8–9;
neuromuscular 9–10; race pace/activation 6–7. No fraction*10 conversion.
[CDC relative-intensity guidance](https://www.cdc.gov/physical-activity-basics/measuring/)
provides broad moderate/vigorous anchors, not validation of the exact catalog.
[Protocol comparison, 2003](https://pubmed.ncbi.nlm.nih.gov/12831268/)
shows perceived exertion can differ for the same relative physiological intensity
under different exercise protocols; this is why no universal conversion is claimed.

## Observed / Inferred / Verified by

Observed: M1's pure Base→Recovery control lost all three sports' steps.
Inferred: missing phase eligibility rather than missing thresholds.
Verified by: new 18-case role/sport/zone matrix materializes light Recovery; it
retains original requested_role and projects actual recovery role to the day.

Observed: fresh-only filtering hid an executable used progression behind an
infeasible new sprint. Inferred: rotation was a premature exclusion.
Verified by: quality 35 TSS / 60-minute request with used progression now succeeds
without downgrade. Low-dose bike/run quality requests receive explicit light
replacements; impossible 500-TSS input is refused, no input mutation.

Observed: first implementation grew a blind-projected second week from 355 to
375 minutes against a 365-minute ceiling; zone-aware projection stayed at 365.
Inferred: power resolution can replace a short failed pair with a longer light
one. Verified by: existing test_second_week_respects_hours_despite_template_rotation_drift
failed before tighter cap; after bounding replacement by failed pair duration it
passes. No bound floor was relaxed, and no test ceiling was weakened.

Observed: M1 frozen synthetic plan contained 35 materialized, 6 infeasible and
17 fallback sessions. Verified by: after M2 the same probe contains 58 materialized
sessions and no fallback/infeasible; prepare/confirm/replay remain exact.
Original M1 report is historical evidence and was not rewritten.

## Checks to date

Targeted M2 RED: 45 failed / 3 passed. This includes preliminary missing field /
provenance failures and is not represented as 45 independent behavioral bugs.
After implementation: M2 + catalog/v2 + density + scheduler + day projection:
128 passed in 4.52s. Repository Ruff --no-cache and git diff --check GREEN.

A separate temporary SQLite public-HTTP probe used a future Monday start and
reported actual calendar length, not merely the requested horizon:

| Actual horizon | Available hours | Sessions | Materialized | Max week minutes | Prepare seconds |
| --- | ---: | ---: | ---: | ---: | ---: |
| 8 weeks | 4 | 58 | 58 | 240 | 0.301 |
| 8 weeks | 6 | 62 | 62 | 335 | 0.156 |
| 8 weeks | 10 | 62 | 62 | 335 | 0.159 |
| 16 weeks, explicit A event | 10 | 115 | 115 | 415 | 0.321 |

These are bounded fixture observations, not a guarantee all inputs are feasible
or an individual training recommendation. An initial probe supplied mismatched
start_week/start_date and correctly got invalid_start_date; fixing the fixture
removed that false alarm. training_goal caps to 8 weeks by existing contract;
the 16-week performance case therefore uses a real 16-week event calendar.

Broad contributor and independent review final results follow below. Four M1
readiness acceptance cases remain M3 obligations; native rounds 0.

## Broad regression / oracle investigation

First sandbox contributor run: 51 failed, 3,660 passed, 38 skipped, 82 deselected.
Breakdown: 27 default SQLite path permission failures; 12 exact v3 oracle hashes
intentionally changed; 4 M1 acceptance tests reached absent M3 readiness keys
once generation passed; 7 #554 fixtures depended on now-repaired assignments;
1 recovery-replan assertion expected easy bike to select sprints. A fresh
`DATABASE_PATH` / `DEMO_DATABASE_PATH` / `CHATS_DIR` under temporary storage
removes default-path failures without opening an athlete DB. Seven legacy tests
also hard-code relative test_*.db files; they need a writable test checkout.
Assertions are updated narrowly,
not marked skipped; four M3 tests retain strict AssertionError-only XFAIL, with
an explicit missing-assessment assertion before accessing future DTO fields.

Observed: archived source `7550d2e` reproduces all six frozen pre-extraction hash
cases exactly. Verified by: same pinned helpers, temporary SQLite and full
`characterization` comparison. The original v3 JSON stays byte-for-byte intact;
`planning_build_confirmation_catalog_v4_baseline.json` is a separate explicit
oracle for the new generation. Every component still compared; only events
remain identical. Synthetic total TSS before/after is event_goal 1244/1205,
training_goal 1108/1020, manual 1105/1037, equal in first/existing variants.
Science/forecast changes follow changed prescriptions; no normalization hides them.

The oracle intentionally includes incompatible pre-race requests/overlays:
event_goal still has one infeasible Peak bike; training_goal has one Recovery
activation fallback from an explicit event; manual has two infeasible and two
fallback sessions. M2 must not silently replace pre-race intent or pretend these
are publishable. They are retained as explicit M3 rejection fixtures, unlike
the event-free training-goal probe where all 58 sessions now materialize. Final
load consistency/publication readiness is still NOT implemented.

Independent round 1: READY for code at 5f15c87, zero confirmed P1/blocking P2.
Checker independently passed 128 tests and examined 2,268 quality requests across
phase/sport/dose/time/threshold combinations: 84 explicit fallbacks, no load/time
cap, allowed phase, light-family or role violations. P3 E401 in report probe fixed.
Scoped round 2 below and final broad verification complete the author gate.

## Final verification and handoff

Final contributor command from the isolated worktree, with fresh temporary
DATABASE_PATH / DEMO_DATABASE_PATH / CHATS_DIR and existing TypeScript dependencies
linked read-only for contract tooling:

    python -m pytest -m "not live and not debug and not e2e" tests/ -q -p no:cacheprovider -W error::pytest.PytestReturnNotNoneWarning --tb=short

Result: **1 failed, 3738 passed, 16 skipped, 82 deselected, 4 xfailed, 7 warnings in 328.34s (0:05:28)**. The runner was permitted to write its own legacy test_*.db
files in the isolated checkout. The preceding sandbox rerun had 3,707 passed,
41 skipped, 4 xfailed and seven relative-test-path permission failures; those
are resolved in the final run, not suppressed or relabelled as successful tests.
The one remaining full-run failure was run_web busy-port preflight: the child
script could not find `python` on PATH. With the venv bin directory on PATH,
all three unchanged preflight tests pass (3 passed in 0.16s). This is a focused
environment rerun, not a claim the previous full command exited zero; no runtime
source changed after the broad run.
No athlete database was read or changed.

Ruff repository and explicit report probe, whitespace, five local Markdown links,
`npm --prefix web run contract:extract -- --check` and contract call inventory
exit 0. No TS artifact changed. UI lint/build/browser acceptance are N/A: no web
source or top-level HTTP model changed. Broad-suite skips are reported rather
than treated as successful feature coverage; strict M3 XFAIL remain explicit.

Independent read-only scoped round 2 READY at
52b2f3fd398834ffef176b70d076874c0e3fc295: 139 passed, 4 expected strict XFAIL in
21.12s; changed-file Ruff and whitespace GREEN; status clean before/after. Runtime
diff from round-1 5f15c87 is empty. Original bounds, effective-load assertions and
v3 fixture preserved. No confirmed P1/blocking P2; P3 probe import fixed-in 52b2f3f.
Review budget 2/2 (round 2 scoped delta), native rounds 0. Later edits only finish
this evidence and publication record.

Final public-HTTP probe again returned 58/58, 62/62, 62/62, 115/115 materialized;
max week minutes 240/335/335/415, times 0.356/0.207/0.186/0.363s. These are fixture
measurements, not a universal feasibility/suitability claim.

Handoff: M3 consumes the M1 contract and the repaired immutable prescriptions,
normalizes final effective load lineage and blocks incomplete/invalid candidates
before pending creation and at confirm. Preserve deliberately refused pre-race
fixtures and applied-receipt semantics. M4 remains recent-history entry dose;
S4 consumes agreed DTOs. Human owns native review acceptance, merge and cleanup.

## Publication checkpoint

[draft PR #706](https://github.com/rbctmz/ai_trainer/pull/706) targets
`codex/issue-677-s3-m1` (#705), not main directly. Runtime/review heads above are
unchanged; final commits only record verification/publication.
[Parent issue evidence](https://github.com/rbctmz/ai_trainer/issues/677#issuecomment-6284423409)
posted and read back. CI started; no final CI, native review, human acceptance or
merge is implied. No test DB files remain in the isolated checkout. Primary
checkout remains unchanged on codex/issue-693-postmerge-record. Keep worktree and
branches for review; cleanup belongs to the merge owner.
