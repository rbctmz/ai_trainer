# Добавить версионный справочник упражнений плавания

Living ExecPlan per .agent/PLANS.md. Issue #767, M2 #762, epic #760. Contract:
docs/swim_exercise_library_slice_spec.md. Owner approved work17.11.2026.

## Purpose / Big Picture


A private exercise is reusable technique rather than a prescribed workout. This
slice lets API consumers create/find/revise a definition, open an old revision
and resolve it into an explicit metre-based M1 step. A saved workout retains
copied content when the catalog changes. Browser/Coach selection remains the
next M2 handoff, so this backend slice is not a completed user-facing constructor.

## Progress


- [x]17.11.2026: owner approved exercise→series→workout direction and requested Intervals/Garmin feasibility check.
- [x] Existing main5042102 inspected; issue767 created without queuing another executor.
- [x] ClassA contract written; Spec Owner→Domain/API handoff recorded.
- [ ] Behavioral RED suites, implementation and contract refresh.
- [ ] Focused/lifecycle/contributor-safe tests, Ruff, web lint/build and self-review.
- [ ] Push PR, stable CI and independent bounded review; human merge separately.

## Context and Orientation


models/swim_program.py and data/swim_program_store.py own immutable complete
programs. api/routers/swim_programs.py is their HTTP surface. data/database.py
initializes additive tables and _clear_all_data deletes owned state. Shared
services/snapshot_runtime.py performs post-commit snapshots. Definitions will
live in models/swim_exercise.py/data/swim_exercise_store.py, service boundary in
services/swim_exercises.py and explicit API in api/swim_exercise_contract.py plus
api/routers/swim_exercises.py. web/lib/types.ts mirrors data, not business rules.
No personal DB is used in development. Private corpus remains ignored and is
never read by tests or automatically imported. The worktree must not be removed
until that dependent private material has been relocated safely.

## Plan of Work


First add strict domain/API/store behavioral tests on synthetic data. Confirm
RED before adding modules. Implement document validation, canonical fingerprint,
append-only store with request replay and compare-and-swap (reject changed head),
then read-only resolution of exact revision to copied M1 step. Wire initialize,
full reset, snapshot service and routes. Mirror TypeScript and registry fixtures.

Run focused tests including a real temporary SQLite Backup API→restore lifecycle
and M1 readback after catalog changes. Run full contributor-safe suite, lint,
web build and extracted-contract checks. Record failures/reproductions, not only
success. Push a reviewable candidate before native review; never merge without
owner decision. Finish at a clean Domain/API→UI handoff naming exact envelopes,
example fixtures, checked behaviors and remaining Coach/composition persistence.

## Surprises & Discoveries


Observed: existing Intervals serializer accepts legacy duration-based steps;
a synthetic authored50m drill rendered as5m RPE3 and omitted gear/instructions.
Inferred: piping M1 documents into it is not an authored-swim delivery path.
Verified by: pure build_intervals_workout_description probe on5042102. This is
an unsupported input boundary, not a reproduced regression in existing callers.
Delivery feasibility is recorded separately and remains M4, not a catalog flag.

## Decision Log


Decision: one definition id per independently meaningful variant, aliases only
search aids. Rationale: trainer names are ambiguous; no semantic auto-merge.
Date/author:17.11.2026, local Spec Owner.

Decision: pure preview plus explicit full-payload confirm/request replay for
small catalog entries; no ephemeral draft table. Rationale: no AI mutation tool
in this slice; reviewed fingerprint detects changed content and CAS detects
changed base. M1 retains its existing server-preview contract.
Date/author:17.11.2026, local Spec Owner.

Decision: resolve returns full pinned definition plus copied M1 step; do not
change M1 schema1/hash to add a nullable reference. Rationale: compatibility of
already accepted source versions. Rich composition lineage is next M2 contract.
Date/author:17.11.2026, local Spec Owner.

## Concrete Steps


Workdir is repository checkout, branch codex/issue-767-swim-exercise-library.
Python is /Users/gregkisel/Developer/ai_trainer/ai_trainer_env/bin/python. Run:

    python scripts/run_isolated_tests.py tests/smoke/test_swim_exercise.py tests/smoke/test_swim_exercise_store.py tests/smoke/test_api_swim_exercises.py -q
    python -m ruff check .
    python scripts/run_isolated_tests.py -m "not live and not debug and not e2e" tests/
    npm --prefix web run contract:extract
    npm --prefix web run lint
    npm --prefix web run build

Use Node22 PATH on this Mac. No running user application is started. Test DBs
are tmp_path owned by isolated launcher; never override source DATABASE_PATH.

## Validation and Acceptance


Synthetic API scenario: preview definition with alias and video cue; GET list
empty; explicit confirm; alias search finds it; resolve revision1 into50m step;
save step through existing M1 program preview/confirm. Change definition to
revision2, then read exercise revision1 and saved program: both retain exact
old instructions. Retry first request after revision2: first receipt returned.
Backup into new owned SQLite target, reopen and repeat readback; reset original,
expect empty catalog while restored copy remains. No network/provider involved.

## Idempotence and Recovery


Additive table creation is repeatable. Atomic append contains receipt metadata;
same request id cannot create extra revision. Rollback copies a reviewed old
definition into a new revision. Version history persists until full reset;
snapshots retain it. A backup failure reports degradation after business commit.
No media files/provider state are owned by this feature.

## Interfaces and Dependencies


SwimExerciseDocument owns validated definition; exercise_fingerprint hashes
canonical model output. Store preview is pure; confirm(db,document,base_revision,
request_id,fingerprint) appends/replays. get_version(db,id,revision=None) reads
validated historical/current version; list_exercises(db,query='') searches;
service resolve uses exact pinned revision and explicit assignment. No new
packages. API contracts mirror all returned snapshots and M1 SwimStep.

## Artifacts and Notes


Review/evidence bundle lives with issue/PR and final sections of slice spec.
Use anonymous fixtures only. Delivery research must distinguish documentation,
local serializer probes, provider readback and actual FR255 acceptance.

## Outcomes & Retrospective


Contract prepared. Implementation, tests, CI and native review not yet run.
M2 Coach/browser and M4 delivery are still open; no runtime rollout performed.

Revision17.11.2026: initial plan and explicit boundaries after owner approval.
