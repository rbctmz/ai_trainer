# Planning S3 M2: concrete Recovery and explicit RPE prescriptions (#677)

This living ExecPlan follows `.agent/PLANS.md` and the M1 contract in
[planning_build_readiness_slice_spec.md](planning_build_readiness_slice_spec.md).
Human owner explicitly authorized M2 on 2026-10-20. Role: Domain/API Implementer;
Class A (versioned prescription/provenance and cross-module role projection).
Base is M1 `7550d2e8a4df594ee502a359004287b341436074`, draft #705. M2 is a separate
stacked branch; no merge, provider delivery or change to the athlete DB is authorized.

## Purpose / Big Picture

A Recovery week must prescribe genuinely light sessions in all three disciplines.
An already-used feasible template must beat a novel infeasible one. When a quality
request cannot be prescribed, an explicitly marked light replacement may reduce
its load without silently lengthening the session. RPE targets are direct catalog
instructions, never FTP/CSS fractions multiplied by ten. This repairs generation;
M3 still owns final load consistency and the publication guard, M4 entry dose.

## Progress

- [x] (2026-10-20) Verified M1 head / #677 / main and reused managed worktree, new branch codex/issue-677-s3-m2.
- [x] (2026-10-20) Refreshed M1 contract, ADD3/ASR, ADR-0001, role/workflow boundaries and prior template intent/duration constraints.
- [x] (2026-10-20) Added 48 targeted cases: baseline 45 failed, 3 passed. Includes preliminary missing policy-field/provenance RED, not 45 independent behavioral reproductions.
- [x] (2026-10-20) Implemented eligibility, feasible rotation/replacement, explicit RPE and complete day-level role projection; 128 focused GREEN.
- [ ] No-growth/impossible/phase and whole-plan probes GREEN; stale-pending and historical preservation evidence being completed.
- [ ] Focused/broad regression, Ruff, contracts as applicable, independent bounded review and draft publication.

## Surprises & Discoveries

Observed: changing Base to Recovery at the same sport/TSS/time/thresholds removes
all candidates. Inferred: `_ALL_TRAINING_PHASES` lacks Recovery, despite a phase
preference entry. Verified by: M1 pure controls and M2 RED at the public materializer.
Only recovery/technique/endurance families gain eligibility; no blanket addition
to intense templates or race activations.

Observed: `_single_candidates` drops all recently used templates if any fresh
candidate exists. Inferred: a fresh candidate failing derived power bounds can
hide the only executable prescription. Verified by: Base quality 35 TSS / 60 min,
recent bike_aerobic_progression RED, to be rerun after correction.

Observed: low Base quality requests have no executable quality pair at their
existing dose; easy bike could select neuromuscular work. Inferred: role eligibility
and refusal handling need honest replacement, not relaxed bounds or longer sprints.
Verified by: targeted low-dose/easy cases; no derived-bound floors are changed.

Observed: sessions now carry an effective replacement role while the initial
builder explicitly keeps the requested top-level day role. Inferred: description
and day projection could contradict the session. Verified by: dedicated M2 test
initially failed after session selection was repaired; project the actual primary.

## Decision Log

Decision: Recovery scheduled easy/quality/long requests select the recovery role
and persist it explicitly; activation/race requests are not repurposed. Only light
families are eligible, and existing fatigue guards remain. Long is not a reason
to add intensity to a Recovery week. Date/author: 2026-10-20 / Domain owner.

Decision: recent exposure sorts candidates rather than deleting alternatives.
After all requested quality candidates fail in Base/Build/Maintenance, admit only
recovery/endurance/technique replacements with selected duration <= original
estimate and effective TSS <= requested TSS; also cap replacement to the shortest failed
pair duration and lower its request within unchanged catalog bounds if needed.
Requests above all eligible quality load ceilings are still refused. Mark quality_to_easy in evidence and
persist the real role. Do not apply this fallback to Peak/Taper/Race Week, do not
retime ordinary retry candidates upward, and never weaken derived bounds.
Date/author: 2026-10-20 / Domain owner.

Decision: use catalog-rpe-v1, an application-scale 1–10 coaching policy, not an
individual physiological calibration or claim of exact Borg/FTP equivalence.
Warmup/cooldown/recovery steps use 1–2. Main recovery/technique steps use 2–3;
endurance 3–4; progression/tempo 5–6; threshold 7–8; VO2 8–9; neuromuscular 9–10;
race pace/activation 6–7. Non-work middle stages use 2–3 in recovery/technique and
3–4 elsewhere. Each immutable definition stores the complete stage map; composite
legs store their own definitions/policies. Missing/incomplete/invalid fallback
policy yields target_semantics_unverified and no guessed steps. Valid absolute
power/pace/HR target behavior is preserved. Date/author: 2026-10-20 / Domain owner.

These are versioned conservative catalog defaults, not validated personal doses.
CDC's relative-intensity guidance places moderate work around 5–6 and vigorous
work around 7–8; it supports keeping recovery below those labels, not the exact
sport-specific prescription. Controlled cycling research shows the same relative
physiological intensity can receive different RPE under different protocols;
a threshold fraction cannot define a universal perceived-effort number.
Sources: https://www.cdc.gov/physical-activity-basics/measuring/ and
https://pubmed.ncbi.nlm.nih.gov/12831268/ .

## Context and Orientation

`models/workout_catalog.py` owns frozen definitions, role/phase eligibility,
materialization and target provenance. `_candidate_duration` and `_retry_durations`
already enforce explicit duration and pre-race intent constraints. The weekly
scheduler estimates actual materialized minutes before enforcing availability.
`models/training_planner.py::_finalize` creates descriptions and primary-session
projections; both must consume effective roles. Existing snapshots are immutable
JSON restored without materialization. Bump catalog/selector/materializer and
definition versions so S1 dependency freshness rejects old pending artifacts.

## Plan of Work

Add explicit RPE stage fields to the immutable definition and use their persisted
mapping only when no valid absolute target is available. Add Recovery eligibility
only to light families. Preserve all candidates for feasibility retries, remove
easy from sprint eligibility, and implement audited light fallback within original
time/load. Keep impossible requests explicit. Update only intentional version
pins in old tests, not old snapshot content or unrelated expected behavior.

M2 does not implement build_readiness, new HTTP rejection, weekly target formulas,
threshold zones (#703), clinical restrictions, availability-by-sport (#668), UI
changes or delivery. Existing DTOs use open dicts for provenance/definitions;
no new top-level HTTP field or TS contract is introduced here.

## Concrete Steps

From worktree root use Python with requirements/dev/web dependencies:

    python -m pytest tests/smoke/test_planning_recovery_catalog_m2.py -q
    python -m pytest tests/smoke/test_workout_catalog.py tests/smoke/test_workout_catalog_v2.py tests/smoke/test_catalog_target_density.py tests/smoke/test_session_scheduler.py tests/smoke/test_session_day_projection.py -q
    python docs/reports/2026-10-20-planning-readiness-m1/probe.py
    python -m pytest -m "not live and not debug and not e2e" tests/
    python -m ruff check .
    git diff --check

M1's four strict XFAIL are retained until M3 guards/readiness DTO exist; their
continued failure is not a generation failure if the synthetic sessions now pass.
When probe observations change, record a new M2 report rather than rewriting M1
historical evidence. No browser UI change is made; do not claim browser acceptance.

## Validation and Acceptance

Recovery all scheduled roles/zones must be materialized with light stimulus,
exact durations and honest role projection. Low-dose quality replacements must
be explicit, no longer or harder by effective TSS than the original request.
Existing feasible requested-role prescriptions must win before downgrade. Easy
bike must not choose sprints. Taper/activation/brick restrictions, hours ceilings,
absolute-target math, read-only historical snapshots and stale-input guards remain.
Independent checker reviews exact candidate and approved tests with the normal
two-round cap. Zero open blocking P1/P2 plus all required verification completes
M2 as a draft checkpoint; native/human merge acceptance is separate.

## ASR / risk traceability

ASR-REL-1/2: keep historical assignments; infeasible remains explicit.
ASR-MOD-2/3: Python-owned policy, additive provenance/definition payloads; no schema
migration. ASR-PERF-4: bounded candidate retry and 16-week build must remain viable.
ADR-0001 reused. Risk: a greedy fresh-only selector hides feasible reused choices;
mitigate with ordered retries. Risk: role downgrades mislabel workload; project
actual role and description, keep requested_role evidence. Clinical suitability
and final atomic publication validation remain explicit M3/M4 boundaries.

## Idempotence and Recovery

All experiments use pure functions or temporary SQLite. No historical backfill,
GET mutation, process restart, provider call or new persistent table. Rebuilding
with identical frozen inputs is deterministic. Existing stored prescriptions and
applied receipts retain their original versions/content until an explicit new edit.

## Outcomes & Retrospective

In progress. Final evidence and reviewer verdict go in
`docs/reports/2026-10-20-planning-readiness-m2/README.md`. The next handoff is M3;
no final readiness or individualized training suitability is claimed by M2.

Revision 2026-10-20: explicit human handoff from M1 to Domain/API M2; no implicit
extension into M3 publication or S4 UI.
