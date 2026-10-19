# Planning readiness M1 evidence — 2026-10-20

Parent #677. Baseline `5f3b738a8b890d1d69ce7793f684277fb00b40dd`.
Scope: specification and executable synthetic diagnosis only. No source in api/,
models/, data/, services/ or web/ changed; no athlete database, provider or live
API used. The existing application in the original checkout was not restarted.

## Reproduction

From repository root, use Python with requirements + dev + web dependencies:

    python docs/reports/2026-10-20-planning-readiness-m1/probe.py
    python -m pytest tests/smoke/test_planning_build_readiness_spec.py --runxfail -q -p no:cacheprovider

`probe.py` inserts repository root into sys.path, creates TemporaryDirectory
SQLite through existing test fixtures and pins the athlete clock to a synthetic
reference date. Every printed profile/threshold and calendar is a fixture, not
athlete evidence. Temporary databases are deleted on return.

## Observed / Inferred / Verified by

Observed: prepare HTTP 200, confirm HTTP 200, readiness field absent. The saved
candidate has 35 materialized, 6 infeasible and 17 legacy_role_fallback sessions.
Inferred: current completeness/eligibility contract covers serialization and
frozen publication, not prescription readiness. Falsifier: compare retained
session_templates with the actual committed checkpoint, then inspect statuses.
Verified by: probe equality assertion passed; applied prescriptions equal frozen
ones; replay HTTP 200, replayed=true. This is not preview/confirm drift.

Observed: Base easy bike/run/swim, 15 TSS and 30 minutes with synthetic thresholds
produce 3/3/4 steps; changing only phase to Recovery produces fallback/0 in all
three sports. Inferred: Recovery is excluded by catalog phase eligibility.
Verified by: pure controls plus `_ALL_TRAINING_PHASES` and `_single_candidates`.
Hypothesis that missing FTP or pace explains the difference is rejected.

Observed: Base bike quality requested 25 TSS, estimated 45 minutes selects
30-minute neuromuscular sprints, derived 16.3 TSS; status infeasible with
`tss_below_minimum` and `density_below_minimum`. Inferred: a failed selection can
remain in an otherwise publishable candidate. Verified by: pure selector result
and independent public HTTP reproduction above. Validator refusal itself is not
called erroneous, and no stretching/relaxation fix is prescribed.

Observed: synthetic easy recovery swim with no CSS produces 13 minutes of drills
RPE 5–6 and 6 minutes Aerobic swim RPE 6–8 on a 1–10 scale. Inferred: literal
threshold-fraction conversion is not a documented template-specific RPE policy.
Verified by: pure output and `_target_for_step` implementation. This proves the
mapping used, not injury or a scientifically established replacement range.

Observed: a valid synthetic brick has parent 120 minutes, legs 80+35 and explicit
transition 5. Inferred: omitting transition in a flat reader can look like a lost
five minutes. Verified by: parent = legs + transition assertion. Do not create a
false duration blocker or rewrite composite history for this legitimate shape.

## Checks and limits

Author baseline: existing confirmation, cycle-build-v2 and catalog/v2 suites:
**128 passed in 15.79s**. One existing httpx deprecation and one sandbox cache
permission warning; tests themselves passed. Follow-up commands disable caches.

New acceptance with `--runxfail`: **4 assertion failures in 3.22s**. Two first /
replacement preview cases each expose 23 invalid prescriptions; two confirm
cases return 200 rather than refusing publication. No setup/collection failures.
Strict XFAIL catches only AssertionError; unexpected exceptions remain failures.
Normal XFAIL and Ruff results are filled after final verification below.

Coverage is deliberately partial: tests exercise the existing public UI-origin
prepare/confirm boundary and first/replacement cycles, not a future assessor
that does not exist. They can become GREEN either through explicit rejection or
through fully repaired generation. Independent injected invalid-artifact tests,
Coach parity, old pending/applied, all aggregates, target policy, availability,
composite negative cases and full failure/reset matrix remain M2/M3 obligations.
No medical safety, physiological adequacy or correct restart dose is established.
No full contributor, browser, web build or contract extraction run is claimed:
there is no runtime or TS change in M1.

## Research boundary

[Bourdon et al., Monitoring Athlete Training Loads, 2017](https://pubmed.ncbi.nlm.nih.gov/28463642/)
frames monitoring as a combination of workload and athlete response. It does not
validate this product's plan or its numerical cutoffs. It supports keeping
technical readiness separate from individual training suitability.

[Borg, Psychophysical bases of perceived exertion, 1982](https://pubmed.ncbi.nlm.nih.gov/7154893/)
discusses perceptual measurement scales. It is not evidence for fraction*10 as a
sport-/template-specific threshold-to-RPE conversion. M1 chooses an explicit
semantic-policy obligation rather than inventing new exertion targets.

## Review and final verification

Independent spec round 1/2: pending. Native review: not requested, 0 rounds.
No independent READY, merge approval or runtime GREEN is claimed yet.
