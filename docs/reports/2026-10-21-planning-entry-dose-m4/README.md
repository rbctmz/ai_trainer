# M4a entry-dose evidence and scientific boundary

Date2026-10-21 (Europe/Moscow). Issue#710, parent#677. Runtime source main `9d679b3`; branch base `99a6a1f` includes the
subsequently merged #704/#692 documentation with no runtime change. Spec/Architecture work only; no personal
activity rows, cache, provider calls or runtime changes. Example dates below are
pinned synthetic dates, not today's training advice.

## Question and cheap falsifier

Observed: current capture includes a90-day activity frame, aggregate CTL and
weekly target/mix; technical readiness deliberately reports personal suitability
not_assessed. Inferred: replacing only recent activity sport labels at equal
aggregate date/time/TSS may leave starting sport dose unchanged. Falsifier:
change recent exposure run4→run1/bike2/swim1 while holding older history, athlete
profile, goal, availability, dates and TSS/duration fixed. Any dose/profile change
would weaken that narrow hypothesis. This first check was a cheap evidence-
discipline falsifier, not a preregistered dose-model-selection experiment.

Verified by: paired pure _calculate_plan_build using synthetic temporary SQLite,
as-of2026-10-16, requested start2026-10-26,8weeks,10available hours, no events.
There are28 older mixed-sport rows, then four recent45-minute/55-TSS sessions at
as-of−21/14/7/2days. Both results have identical daily plan and first-week dose:

| Sport | Week1 minutes | Sessions | Effective TSS |
| --- | ---: | ---: | ---: |
| bike |120|3|60.2|
| run |90|3|47.9|
| swim |35|1|24.7|

Both technical readiness statuses are ready; training_suitability=not_assessed.
No M4 entry assessment exists. Normal prepare currently retains a pending token;
active plan/settings remain unchanged. Token preparation is not counted as an
active write and is not a claim that future M4 no-pending refusal already works.
Raw templates differ because their cycle namespaces differ; this report compares
semantic dose/daily allocation and does not assert byte-identical identities.
Fixture numbers, including declared20/20/45-minute test limits, are test inputs
and not recommendations for the athlete. No injury, safety or efficacy endpoint
was measured.

Reproduce from repository root with an activated environment:

    PYTHONPATH=. python docs/reports/2026-10-21-planning-entry-dose-m4/probe.py
    python -m pytest tests/smoke/test_planning_entry_load_spec.py -q
    python -m pytest tests/smoke/test_planning_entry_load_spec.py --runxfail -q

Executed on 2026-10-21 using the repository venv, synthetic temporary DBs and
`-p no:cacheprovider`:

- Spec tests: **1 passed, 4 strict XFAIL in 1.37s**.
- The same tests with `--runxfail`: **4 failed, 1 passed in 1.19s**. Failures
  were the two missing `entry_load` assertions, absent-sport preparation returning
  a token instead of `entry_dose_required`, and assignments exceeding declared
  limits. All were intended assertions; no import/setup/runtime error was hidden.
- Compatibility command with `test_planning_entry_load_spec.py`,
  `test_planning_build_readiness_m3.py`, `test_planning_build_preparation.py`,
  `test_multisport_training_load.py` under `tests/smoke/`:
  **134 passed, 4 XFAIL, 1 warning in 24.44s**. The warning is not a new M4
  runtime failure; no M4 production code is present.
- The installed probe reproduced the aggregate table above; the pure calculations
  and normal prepare left the protected active plan/settings unchanged. Prepare
  still retained one pending preview in each independent synthetic database.
- Ruff on the helper/test/probe: passed. All-table rollback, full contributor
  tests, HTTP/TS extraction and browser checks are **NOT YET** for M4.

Strict XFAIL is a characterization of a missing feature, not evidence of a
working entry-dose policy. Removing XFAIL requires the later Domain RED→GREEN
slice; the already-green purity control is not relabelled a new RED.

## Scientific sources: findings versus application decisions

1. [Bourdon et al., Monitoring Athlete Training Loads,2017](https://pubmed.ncbi.nlm.nih.gov/28463642/),
   DOI10.1123/IJSPP.2017-0208. Consensus on interpreting external/internal load
   through multidisciplinary monitoring. It supports retaining duration, frequency,
   intensity/provenance and individual response. It does not validate a universal
   starting weekly TSS or the exact M4 windows/medians. Application inference:
   a single aggregate score is insufficient evidence for all discipline doses.
2. [Tanaka, cross-training review,1994](https://pubmed.ncbi.nlm.nih.gov/7871294/),
   DOI10.2165/00007256-199418050-00005. Some aerobic transfer exists, while
   sport-specific adaptation remains important; literature was limited. This is
   a historical review, not validation of an individual transfer multiplier.
   Application inference: preserve cross-training context without converting run
   TSS into measured cycling/swimming exposure or proving technique/tissue tolerance.
3. [Chen et al., detraining study](https://pubmed.ncbi.nlm.nih.gov/33517866/),
   DOI10.1080/17461391.2021.1880647 (online2021, journal2022). Fifteen young trained
   men were measured before/after two weeks of detraining; some cardiopulmonary
   and knee-extensor measures decreased, others did not. Limited population and
   endpoints do not supply safe restart minutes or a universal gap threshold.
   M4 reports dated gaps rather than estimating a personal fitness loss percentage.
4. [Buist et al., randomized novice-running trial,2008](https://pubmed.ncbi.nlm.nih.gov/17940147/),
   DOI10.1177/0363546507307505. The532-person comparison found no injury reduction
   for the graded13-week program based on the10% rule versus an8-week program.
   It is not a trial of triathlon restart doses. M4 must not label10% as a
   generally validated injury-prevention guarantee; this also does not prove
   that every alternative progression is unsafe or ineffective.
5. [Impellizzeri et al., ACWR methodological critique,2020](https://pubmed.ncbi.nlm.nih.gov/32502973/),
   DOI10.1123/ijspp.2019-0864. The paper identifies causal/methodological problems
   with using ACWR to prescribe injury reduction. It does not identify a better
   validated personal dose formula. M4 avoids an ACWR safe zone or injury-risk
   probability and explicitly labels its operational policy assumptions.

The policy proposal uses28 completed days,84-day context, median duration/counts
and a14-day entry scope. These are inspectable application decisions, not values
derived or validated by those papers. The observed envelope describes recorded
exposure; athlete_declared limits describe intent. Neither is medical clearance.
No runtime network dependency on papers, Blocks or an LLM is proposed.

## Frozen next experiment protocol — not executed yet

Question: can the proposed observed-reference envelope plus explicit declarations
meet data-quality/constraint/feasibility requirements without a false supported
state or cross-sport transfer? This is a technical experiment, not a test of
physiological safety. Baselines: current global-CTL/mix allocation (observed above),
active-weeks-only summary, and proposed complete28-day-bin reference. No policy
is promoted merely for fitting more templates; report refusal rates separately.

Fixed cases: twelve histories, each on Monday and Wednesday anchors with relative
activity dates (24 cases): run-only, matched-aggregate mixed, steady three-sport,
empty+complete, empty+unknown, sparse+complete, missing duration, partial capture,
complete multisport, partial multisport, identical duplicates, conflicting IDs.
Six additional cases: future row, same-day partial row, zero-TSS/positive-duration
stage, nonfinite duration, nonfinite declared limit, edit retaining original entry
anchor. Total30. No private data, providers or paid calls. Budget30cases/15minutes
wall time, deterministic Python only. Freeze fixture values before running.

Absolute acceptance: no false supported state from incomplete evidence; no
cross-sport permission transfer; no envelope/leg double count; every supported
allocation respects actual time/frequency/session caps; scope/freshness/purity
hold. Require a supported feasible steady-history and run-only+declared-other-
sports control, not an always-blocked implementation. Relative reports include
usable/proposed/refused counts, changes in initial dose and template feasibility;
relative improvement is separate from passing the absolute criteria.

Exit: any invariant violation rejects the candidate; inconclusive/unsupported
inputs remain explicit and trigger a narrower proposal. Passing only establishes
technical adequacy within these fixtures, never an injury-prevention or training-
efficacy claim. This protocol must be mirrored in spikes/issue-710-entry-dose/
README.md before the next numerical operator experiment; no such operator has
been run in M4a. Current cheap characterization is retained separately.

## Boundaries still NOT YET

No runtime M4 profile/limit/guard, new HTTP/TS implementation, all-table rollback,
compatibility/reset proof, browser acceptance or personalized training suitability
is claimed. The four strict XFAIL cover only the named missing behavior; other
matrix rows are planned. Existing S3 full test counts are a baseline. Independent
spec review and Domain/API handoff precede implementation.
