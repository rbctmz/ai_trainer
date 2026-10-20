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

Broad contributor contour: running; no GREEN claimed yet. Independent review:
pending, native rounds 0. Final failures/triage/verification are appended before
publishing. Four M1 readiness acceptance cases remain M3 obligations.
