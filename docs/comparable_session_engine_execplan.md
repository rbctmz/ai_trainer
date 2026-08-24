# Deliver a deterministic comparable-session engine (#500)

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

This document must be maintained in accordance with `.agent/PLANS.md`.

## Purpose / Big Picture

After this change, post-workout feedback can show one prior session that is genuinely comparable to the completed session rather than merely recent. The system will require the same canonical sport and exact planned stimulus, rank eligible candidates by duration, overall intensity, and recorded interval structure, and expose the evidence behind the choice. Cycling evidence prefers normalized power; running and swimming use source-backed pace with the threshold stored on each activity. When facts are weak or incompatible, the API and coach receive a stable data gap and cannot turn a single comparison into a trend or causal adaptation claim.

## Progress

- [x] (2026-08-24) Re-queried issue #500, confirmed no open PR or remote issue branch, removed the stale automation `blocked` label, and set `status: in progress`.
- [x] (2026-08-24) Confirmed publish access with `gh auth setup-git` and `git ls-remote --heads origin`; created `codex/issue-500-comparable-session-engine` from `dbc8cca`.
- [x] (2026-08-24) Read the workflow, PLANS, ASR/ADD documents, ADR-0001, slice template, and current activity/feedback/coach contracts.
- [x] (2026-08-24) Completed the cheap falsifying check: repository search and current evidence-gate tests show no comparable-session DTO or selector; session comparison claims remain a comparator data gap.
- [x] (2026-08-24) Fixed the Class A slice contract and RED matrix.
- [x] (2026-08-24) Captured initial import RED, then product-boundary RED of 3 failed / 8 passed.
- [x] (2026-08-24) Implemented the pure model and bounded local projection; final new matrix is 12 passed.
- [x] (2026-08-24) Integrated additive feedback, coach-tool, presenter, TypeScript, and neutral web contracts.
- [x] (2026-08-24) Completed root self-review and local CI: combined focused 145 passed; smoke 2075 passed / 1 skipped; contributor-safe 2121 passed / 3 skipped / 26 deselected; Ruff, web lint/build, contract check, and 23 contract smoke tests green.
- [x] (2026-08-24) Committed implementation as `aac0ff1`, pushed the issue branch, and opened draft PR #505 with `Closes #500`.
- [ ] Post the final pushed SHA/evidence to the issue and complete native Codex Review before merge.

## Surprises & Discoveries

- **Observed**: `plan_actual_matches.planned_snapshot` preserves sport, role, phase, load, and intervals but not the workout catalog's `step_builder_key`. **Inferred**: stimulus identity must be recovered from the immutable referenced planning checkpoint, not guessed from activity names. The cheapest falsifying check is to resolve a known match through its checkpoint and compare the session `definition_snapshot`. **Verified by**: temporary-DB-style service fixture resolves `prior-session` through checkpoint #3 and selects the candidate only after reading `step_builder_key=threshold`.

- **Observed**: canonical activities store `normalized_power`, `avg_power`, `tss_ftp_used`, and `tss_pace_used`, while compact interval structure is local and provider-independent after sync. **Inferred**: v1 needs no provider call or schema change. The cheapest falsifying check is a temporary database containing only these persisted fields and interval rows. **Verified by**: pure fixtures and bounded fake-store service test pass without provider clients or new tables; contract/build suites remain green.

- **Observed**: one plan/fact target may intentionally reference multiple split activities. **Inferred**: silently aggregating normalized power or pace across those activities would create unsupported physiology and would undo split activity semantics. The cheapest falsifying check is a target with two actual ids. **Verified by**: `test_service_refuses_to_aggregate_split_target_activities` returns `TARGET_ACTIVITY_COUNT_UNSUPPORTED`.

## Decision Log

- Decision: v1 compares exactly one canonical actual activity to exactly one prior canonical activity. Rationale: normalized power and pace are not safely composable across split activities without a separate aggregation contract; returning a data gap preserves activity-card semantics. Date/Author: 2026-08-24 / Codex.

- Decision: require same normalized sport and exact `step_builder_key`; do not infer stimulus from the activity name, role, or TSS. Rationale: those are weaker and can select the wrong workout while sounding plausible. Date/Author: 2026-08-24 / Codex.

- Decision: rank on duration, TSS-per-hour intensity, and interval-segment structure. If structure is absent, label that dimension missing and renormalize the remaining score; if present and materially incompatible, exclude the candidate. Rationale: missing optional enrichment is not proof of incompatibility, while contradictory structure is evidence against comparison. Date/Author: 2026-08-24 / Codex.

- Decision: sport-specific metric deltas are descriptive evidence only. A single comparison sets `trend_claim_allowed=false` and `causal_claim_allowed=false`. Rationale: one paired observation cannot establish adaptation, cause, or longitudinal direction. Date/Author: 2026-08-24 / Codex.

- Decision: use no new persistence. Rationale: comparison is a deterministic read projection over existing source-of-truth rows and should update naturally after sync, rematch, or feedback correction. Date/Author: 2026-08-24 / Codex.

## Outcomes & Retrospective

The engine now selects one prior same-sport, exact-stimulus session by transparent duration, TSS-per-hour, and interval-structure evidence. NP is preferred for bike, average power is explicitly a fallback, and run/swim pace carries each activity's stored pace threshold. Feedback, coach, and web surfaces expose neutral facts; split targets and weak/incompatible evidence fail closed. No schema, TSS, provider, plan, or history behavior changed. The implementation is published in draft PR #505; native Codex Review and GitHub CI remain before merge.

## Context and Orientation

`data/database.py` owns canonical activity and match reads. `models/plan_actual_reconciliation.py` links one planned `session_id` to canonical actual activity ids and an immutable checkpoint. `models/planning_checkpoints.py` restores the goal plan so the matched session's versioned `definition_snapshot.step_builder_key` can identify stimulus. `data/activity_store.py` owns compact, locally persisted interval structure. `models/post_workout_feedback.py` and `api/session_feedback.py` expose athlete feedback after a stable match. `models/ai_tools.py` is the read-only coach tool registry; `models/coach_tool_presenter.py` renders tool evidence. `web/components/today/PostWorkoutFeedbackCard.tsx` is the web-primary post-workout surface.

A “comparable session” is one prior activity with the same sport and versioned planned stimulus whose duration, TSS per hour, and interval structure are compatible enough for a descriptive side-by-side comparison. It is not a baseline, trend, or causal estimate.

## Plan of Work

First, create `models/comparable_sessions.py` as a pure module. It will project activity features, preserve source labels, calculate bounded similarity dimensions, exclude incompatible candidates, and return either one versioned comparison or a stable data-gap reason. All sorting will have explicit deterministic tie-breakers.

Second, create `services/comparable_sessions.py`. It will read at most a two-year local window, map latest matches in one bounded query, resolve checkpoint stimulus with a per-call cache, read compact intervals only for otherwise eligible candidates, join latest active feedback, and call the pure selector. It will not contact Intervals.icu or Garmin.

Third, integrate the projection into `api/session_feedback.py` for prompt and submit/correct responses, and into `api/today_snapshot.py` as structured coach session evidence. Add a read-only `get_comparable_session` tool for an explicit session id or the latest feedback-backed completed session. Add neutral presenter text that reports facts and repeats that one comparison is not a trend.

Fourth, mirror the additive DTO in `web/lib/types.ts` and show a compact side-by-side evidence block in `PostWorkoutFeedbackCard.tsx`. The block will never use “better”, “worse”, “progress”, or causal language. Data gaps remain machine-readable but do not add noisy UI.

Fifth, refresh the TypeScript contract, update the ASR catalog, run focused and broad verification, perform self-review and native Codex Review, resolve blocking findings, and publish a draft PR with `Closes #500`.

## Concrete Steps

Run from `/Users/gregkisel/Developer/ai_trainer`:

    ai_trainer_env/bin/python -m pytest tests/smoke/test_comparable_sessions.py -q
    ai_trainer_env/bin/python -m pytest tests/smoke/test_comparable_sessions.py tests/smoke/test_post_workout_feedback.py tests/smoke/test_coach_native_tools.py tests/smoke/test_ai_coach_runtime.py -q
    ai_trainer_env/bin/python -m ruff check models/comparable_sessions.py services/comparable_sessions.py api/session_feedback.py api/today_snapshot.py models/ai_tools.py models/coach_tool_presenter.py tests/smoke/test_comparable_sessions.py
    npm --prefix web run contract:extract
    npm --prefix web run contract:extract -- --check
    npm --prefix web run lint
    npm --prefix web run build
    ai_trainer_env/bin/python -m pytest tests/smoke -q
    ai_trainer_env/bin/python -m pytest -m "not live and not debug and not e2e" tests/

The first focused run before implementation must fail because the new model/service contracts do not exist. After implementation, every focused test must pass. Exact final counts and concise transcripts are recorded here and in the slice spec as work proceeds.

## Validation and Acceptance

A fixed bike fixture must choose an older closer threshold session over a newer incompatible one and report normalized power when present. Removing normalized power must use an explicitly named average-power fallback. Fixed run and swim fixtures must express pace in seconds per kilometre or per 100 metres and carry the activity's stored pace threshold, never FTP. A candidate with a qualitative athlete note and no RPE must preserve the note as labelled subjective evidence without changing its similarity score. Candidate permutations must select the same id and explanation. Missing stimulus, multiple target activities, materially incompatible intensity, or no eligible history must return stable data gaps.

At the product boundary, one temporary-DB prompt and the read-only coach tool must expose the same comparison id/rule version. The React component must compile and render only neutral evidence labels. Existing TSS, matching, feedback persistence, and coach evidence suites must remain green.

## Idempotence and Recovery

Every comparison call is read-only and deterministic. It can be retried after a sync or rematch with no duplicate state. Checkpoint and match rows are never modified. Tests use temporary databases. Rollback is a normal code revert; there is no schema, cursor, provider write, backfill, or local database cleanup.

## Artifacts and Notes

The initial cheap falsifier was repository search plus the #499 gate fixture: no comparable-session model/tool/DTO existed and a session-comparison claim received `TREND_COMPARATOR_MISSING`. Initial pytest failed at missing module import. After the pure slice, the product-boundary run was 3 failed / 8 passed; final new matrix is 12 passed. Local verification is focused 145 passed, smoke 2075 passed / 1 skipped, contributor-safe 2121 passed / 3 skipped / 26 deselected, repository Ruff clean, web lint/build green, contract artifact current, and contract smoke 23 passed.

## Interfaces and Dependencies

`models/comparable_sessions.py` will export `COMPARABLE_SESSION_RULE_VERSION`, `project_activity_features(activity, stimulus_family, intervals=None, subjective_evidence=None)`, and `select_comparable_session(target, candidates)`. Inputs and outputs are JSON-shaped mappings; no external dependency is added.

`services/comparable_sessions.py` will export `project_comparable_session(database, evidence, feedback=None, lookback_days=730)`. It returns the same versioned `available` or `data_gap` DTO for API, web, and coach consumers.

`api/session_feedback.py` will export `comparable_session_for_session(database, session_id=None, as_of=None)` for the coach tool and use the service internally for prompt/submission projections. `AITools.get_comparable_session(session_id=None)` will be read-only and share this path.

Revision note (2026-08-24): initial Class A plan created after architecture and contract inspection. The key scope decision is to fail closed for split/composite actuals rather than inventing aggregate power or pace.

Revision note (2026-08-24): implementation and local verification completed. Self-review removed legacy stimulus inference, split duration/intensity rejection evidence, and made sport-specific provenance visible in coach/UI output.

Revision note (2026-08-24): publication state recorded after draft PR #505 was created; implementation behavior did not change.
