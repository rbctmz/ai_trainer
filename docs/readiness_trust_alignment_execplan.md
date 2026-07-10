# Align readiness metrics and look ahead to the next quality session

This ExecPlan is a living document maintained according to `.agent/PLANS.md`. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must remain current while work proceeds.

## Purpose / Big Picture

An athlete should never see one readiness value in the Coach sidebar and a different value in the Coach briefing or conflict gate for the same moment. The live morning check on 2026-07-10 exposed exactly that trust gap: Dashboard/Coach sidebar showed Readiness 54, TSB -22.6, and CTL 14.8, while the canonical fused readiness used by the gate and briefing showed Readiness 61.1, TSB -19.2, and CTL 18.4. The same check also showed that a key quality ride four days away was outside the gate's fixed three-day horizon.

After this change, Dashboard summary and widgets project their readiness/load values from the same canonical readiness snapshot already exposed to Coach and Planning. The salience-gate continues to inspect its base three-day window but extends through the nearest quality session when that session is within seven days. A developer can verify both outcomes with deterministic smoke tests and a live report that names the effective horizon and policy.

## Progress

- [x] (2026-07-10 11:22Z) Reproduced the live trust gap through the web Coach flow and direct readiness conflict report.
- [x] (2026-07-10 11:23Z) Created issue #152 and branch `codex/issue-152-readiness-trust-alignment`.
- [x] (2026-07-10 11:24Z) Recorded the isolated branch baseline: `445 passed, 1 skipped` on `main` commit `2b73d3e`.
- [x] (2026-07-10 11:34Z) Added behavior tests and recorded the red phase: collection failed because `project_readiness_snapshot` and `MAX_QUALITY_LOOKAHEAD_DAYS` did not yet exist.
- [x] (2026-07-10 11:42Z) Implemented a non-mutating canonical readiness projection for Dashboard summary/widgets and removed the Garmin-only readiness override.
- [x] (2026-07-10 11:47Z) Implemented bounded nearest-quality lookahead with additive report provenance and no changes to severity/confidence rules.
- [x] (2026-07-10 11:55Z) Passed targeted and adjacent-contour validation: `38 passed`, then `60 passed`; Ruff also exposed and led to removal of one unused import.
- [x] (2026-07-10 12:00Z) Re-ran the real local-data report: Dashboard, widgets, and snapshot now agree at readiness 61.1, TSB -19.2, CTL 18.4; the gate uses horizon five and correctly remains silent for readiness `ready`.
- [x] (2026-07-10 12:12Z) Completed full validation and self-review: `452 passed, 1 skipped`, Python compile, Ruff, diff-check, web lint, and production build all passed.
- [ ] Publish the reviewed change and open a draft PR closing #152.

## Surprises & Discoveries

- Observation: Coach/gate readiness uses `models.readiness.LOAD_METRICS_WINDOW_DAYS`, currently 90 days, while Dashboard summary status is assembled from only 30 days of activities.
  Evidence: `api/readiness_snapshot.py` and `api/readiness_conflicts.py` fetch 90-day load input; `api/routers/dashboard.py::dashboard_summary` passes `db.get_activities(30)` into `calculate_current_status`.
- Observation: The live quality session on 2026-07-14 is four days after the 2026-07-10 briefing.
  Evidence: the default three-day report evaluated July 10-12 only; a manual five-day report included `Качество • вело`, days_until 4, TSS 41.
- Observation: Low sleep alone did not make the fused score limited.
  Evidence: sleep was 43.5/100 and TSB factor 55, but HRV and resting-HR factors were 70, producing readiness 61.1 (`ready`) with confidence 0.8. The gate correctly remained silent under its existing matrix.
- Observation: An existing smoke test encoded Garmin training readiness as a higher-priority Dashboard value than the fused application readiness.
  Evidence: after making the snapshot canonical, the test expected 82 while the fused fixture value was 70. The expectation was changed intentionally because the product contract now has one source of truth.
- Observation: Keeping nested Dashboard signals unchanged would preserve a subtler contradiction even after replacing the top-level metrics.
  Evidence: the new projection test initially exposed old values inside `signals.readiness`, `signals.load`, and `signals.state`; the helper now projects those nested fields too while proving that the input dictionaries are not mutated.

## Decision Log

- Decision: Keep `models.readiness.compute_readiness_today` and the readiness snapshot as the canonical metric source rather than changing Banister formulas or factor thresholds.
  Rationale: The live issue was inconsistent consumers, not evidence that the canonical 90-day fusion math is wrong.
  Date/Author: 2026-07-10 / Codex.
- Decision: Preserve all existing Dashboard response fields and project canonical values into `summary.today` and widgets.
  Rationale: The web UI already consumes these fields; additive provenance is safe, but a response redesign would widen scope.
  Date/Author: 2026-07-10 / Codex.
- Decision: Use policy `base_plus_nearest_quality`, with a default base of three days and a cap of seven days.
  Rationale: A permanent wide horizon would increase alert noise from ordinary sessions. Extending only through the nearest quality session makes the next key workout visible without turning the gate into a weekly warning list.
  Date/Author: 2026-07-10 / Codex.
- Decision: Do not change the conflict severity matrix or readiness confidence threshold.
  Rationale: The live run showed correct silence for readiness `ready`; this task fixes visibility and consistency, not intervention sensitivity.
  Date/Author: 2026-07-10 / Codex.

## Outcomes & Retrospective

Implementation and local validation are complete. The same canonical score and load metrics are now observable in Dashboard summary, Dashboard widgets, Coach meta, and the gate. On the real local dataset they agree at readiness 61.1, TSB -19.2, CTL 18.4, and HRV 32. The gate reports base horizon three, effective horizon five, and the quality session that caused extension. It remains silent because readiness is `ready`, confirming that visibility changed without broadening the intervention matrix. The full contributor-safe contour passed with `452 passed, 1 skipped`; Python compilation, Ruff, diff-check, web lint, and the Next.js production build also passed. Only Git publication remains.

## Context and Orientation

`models/readiness.py::compute_readiness_today` is the single fused readiness calculation. It combines personal HRV and resting-HR baselines, sleep, Garmin readiness when present, and CTL/ATL/TSB calculated from a stable 90-day activity window. `api/readiness_snapshot.py::build_readiness_snapshot` turns that result into a JSON-safe API contract used by Dashboard, Planning, and Coach meta. `api/readiness_conflicts.py::build_readiness_conflict_report` independently loads the same inputs with a stricter freshness policy and passes the fused result to `models/readiness_conflicts.py`.

The trust gap exists because `api/routers/dashboard.py` also calls `models/dashboard_summary.calculate_current_status` using a 30-day activity dataframe. Its `summary.today` values feed `web/app/coach/page.tsx::ContextSidebar`, even though the same response already carries the canonical `readiness_snapshot`. Dashboard widgets repeat the 30-day calculation.

The conflict gate currently uses `DEFAULT_HORIZON_DAYS = 3`. A horizon is a half-open day interval beginning today: three days means days_until 0, 1, and 2. A quality session four days away is therefore invisible. The new effective horizon will start at three and extend to `days_until + 1` for the nearest quality session, but never beyond seven days total.

## Plan of Work

First add behavior tests. Seed a database where 30-day and 90-day Banister values differ, then assert Dashboard `summary.today` and widgets equal the response's canonical readiness snapshot values. Add pure lookahead tests where quality sessions at days four and six extend the effective horizon, a session at day seven does not, and absence of a near quality session leaves the horizon at three. Run these tests before implementation and record their failures.

Next add a pure projection helper in the headless Dashboard domain layer. It will copy a valid snapshot score, CTL, ATL, TSB, and HRV factor into the current Dashboard status, using the existing readiness label/tone semantics. `api/routers/dashboard.py` will build the snapshot once per request and use the projected status for summary and widget calculations. The Streamlit fallback may pass the same snapshot from its database, but no UI module may import from `api/`.

Then add a pure effective-horizon resolver in `models/readiness_conflicts.py`. It will inspect the active plan for the nearest quality session inside a seven-day cap. `api/readiness_conflicts.py` will resolve the horizon before collecting sessions and pass the effective value to conflict detection. The report will add `base_horizon_days`, `lookahead_policy`, and `horizon_extended_for_quality`; existing keys remain unchanged.

Finally run targeted readiness/dashboard tests, all smoke tests, Python compilation, Ruff, web lint, and the production build. Self-review will check time-boundary semantics, stale/unknown snapshots, no-plan behavior, response compatibility, and alert-noise risk.

## Milestones

The first milestone establishes the failing behavioral contract. It is complete when tests reproduce the two observed gaps: Dashboard values differ from the canonical snapshot, and a quality session four days away does not affect a three-day report. The recorded red phase failed at collection because the planned projection helper and lookahead constant did not yet exist, which proves the tests preceded implementation.

The second milestone aligns every Dashboard readiness consumer. It is complete when summary and widgets derive readiness, CTL, ATL, TSB, and HRV from one snapshot, nested signals agree with the top-level values, and the original dictionaries remain unchanged. Focused tests and the real-data report demonstrate this outcome.

The third milestone makes the conflict horizon salience-aware without changing intervention sensitivity. It is complete when quality sessions on days four and six extend the effective horizon to five and seven days respectively, day seven remains outside the cap, non-quality sessions do not extend it, and a `ready` athlete still produces silence.

The final milestone validates and publishes the change. Local validation is complete with the full smoke suite, static checks, and a production web build. Publication is complete only after the conventional commit is pushed and a draft pull request links and closes issue #152.

## Concrete Steps

Work from `/Users/gregkisel/Developer/ai_trainer`:

    ai_trainer_env/bin/python -m pytest tests/smoke/test_readiness_conflicts.py tests/smoke/test_readiness_snapshot_contract.py tests/smoke/test_api_dashboard.py -q
    ai_trainer_env/bin/python -m pytest tests/smoke -q
    ai_trainer_env/bin/python -m compileall -q api models services data ui
    ruff check <changed Python files>
    cd web && npm run lint && npm run build
    git diff --check

Before implementation, new tests must fail because Dashboard `summary.today` still uses the 30-day status and the gate still fixes its horizon at three. After implementation, all commands must pass without live credentials.

## Validation and Acceptance

Given a database whose 30-day and 90-day Banister metrics differ, when `GET /api/dashboard/summary` and `GET /api/dashboard/widgets` are built, then their readiness, CTL, and TSB values equal the canonical readiness snapshot included in the response.

Given the same database and as-of date, when Coach meta and Dashboard summary are built, then both expose the same readiness score and canonical TSB values.

Given the base horizon is three days and the nearest quality session is four days away, when the conflict report is built, then its effective horizon is five days and the quality session appears in `sessions_evaluated`.

Given the nearest quality session is six days away, the effective horizon is seven days. Given it is seven or more days away, the effective horizon stays three days. Recovery/easy/long sessions alone never extend the horizon.

Given readiness is `ready`, when a quality session is visible through the extended horizon, then the report remains silent because the severity matrix has no `quality × ready` conflict.

## Idempotence and Recovery

The change is calculation and contract plumbing only. It does not migrate or delete data. Tests and live reports are safe to rerun. If canonical projection breaks a consumer, revert the router projection while keeping the new tests and pure helpers to isolate the contract mismatch. If extended lookahead creates unexpected noise, the cap and policy are named constants and can be reverted independently without touching readiness math.

## Artifacts and Notes

Live evidence before implementation:

    Coach sidebar: readiness 54, TSB -22.6, CTL 14.8
    Canonical snapshot/gate: readiness 61.1, TSB -19.2, CTL 18.4
    Base horizon: sessions on days 0, 1, 2; silence true
    Manual five-day horizon: includes quality ride on day 4; silence still true because readiness ready

TDD and live evidence after implementation:

    Red phase: test collection failed on missing project_readiness_snapshot and MAX_QUALITY_LOOKAHEAD_DAYS
    Focused tests: 38 passed
    Adjacent readiness/dashboard contour: 60 passed
    Dashboard summary: readiness 61, TSB -19.2, CTL 18.4, HRV 32
    Canonical snapshot: readiness 61.1, TSB -19.2, CTL 18.4, ATL 37.7, HRV 32
    Dashboard widgets: CTL 18 and TSB -19.2 from the same snapshot
    Gate: base horizon 3, effective horizon 5, extended for quality day 4, silence true
    Full smoke: 452 passed, 1 skipped in 11.24s
    Python compile, Ruff, git diff --check: passed
    Web lint: no warnings or errors
    Web production build: compiled and generated 11 static pages

## Interfaces and Dependencies

In `models/dashboard_summary.py`, define a pure helper with an interface equivalent to:

    project_readiness_snapshot(current_status, readiness_snapshot) -> dict[str, Any]

It must not mutate its arguments. It must retain unrelated status fields and use snapshot values only when present and non-null.

In `models/readiness_conflicts.py`, define:

    BASE_HORIZON_DAYS = 3
    MAX_QUALITY_LOOKAHEAD_DAYS = 7
    resolve_effective_horizon(goal_plan, *, today, base_horizon_days=3, max_horizon_days=7) -> dict[str, Any]

The returned dictionary must contain the effective horizon and whether/which quality session caused extension. `api/readiness_conflicts.py` will expose additive policy metadata in the final report.

Revision note (2026-07-10 / Codex): initial plan created from the live web/Coach verification before tests or implementation.

Revision note (2026-07-10 / Codex): updated after the red/green TDD cycle, adjacent-contour tests, and the post-implementation real-data verification.

Revision note (2026-07-10 / Codex): updated after full validation and self-review; added explicit milestones required by `.agent/PLANS.md` and normalized the public policy name to the implemented `base_plus_nearest_quality` value.
