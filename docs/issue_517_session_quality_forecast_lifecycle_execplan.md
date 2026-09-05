# Make session-quality forecasts idempotent and lifecycle-aware

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds. Maintain it in accordance with `.agent/PLANS.md` from the repository root.

## Purpose / Big Picture

The shadow session-quality forecast must describe one pre-start belief about one planned key session, not create a new database revision every time the Today page refreshes. After this change, repeated reads with the same forecast-driving facts reuse one prediction, meaningful pre-start changes append an immutable revision, and a started or feedback-completed session no longer receives or exposes an active pending forecast. The behavior is visible through focused tests and through stable row counts in a temporary SQLite lifecycle probe.

## Progress

- [x] (2026-08-29) Confirmed the live failure shape and acceptance criteria for issue #517.
- [x] (2026-08-29) Classified the change as Class A because deduplication and persisted lifecycle semantics are automatic escalation triggers.
- [x] (2026-08-29) Added RED tests for timestamp-only replay, post-start, post-feedback, and evaluation-aware Today projection; the existing readiness-change test covers meaningful revisions.
- [x] (2026-08-29) Implemented the smallest semantic fingerprint, local lifecycle gates, evaluation-aware Today projection, and bounded lifecycle caching.
- [x] (2026-08-29) Ran focused, contributor-safe, lint, and contract checks; exact evidence is recorded below.
- [x] (2026-08-29) Self-reviewed the final diff; publishing a PR is owned by the parent task after explicit approval.

## Surprises & Discoveries

- **Observed**: one current target key accumulated 70 prediction revisions, while removing only volatile observation timestamps reduced the stored inputs to 14 semantic variants; six unevaluated pending predictions were created after feedback. The source is the bounded SQLite query recorded in issue #517.
- **Inferred**: the complete readiness/report dictionaries are being hashed, so `observed_at_utc` defeats idempotency, and raw immutable `status="pending"` is being read without the evaluation/feedback lifecycle projection. The cheapest falsifying check is a temporary-database test that changes only observation timestamps and then records terminal feedback.
- **Verified by**: the new temporary-database RED tests fail on the current tree: ten timestamp-only calls create multiple revisions, started/terminal-feedback calls return a reused prediction instead of a named lifecycle stop, and Today returns evaluated prediction id `1` instead of next eligible id `2`. The pre-existing focused forecast suite remains green at 24 passed tests.
- **Verified by**: the GREEN contour passes with one row for ten timestamp-only calls, one immutable row for concurrent semantic replays, stable lifecycle stop reasons, and Today selecting the next pending target; the contributor-safe contour passes without provider access.

## Decision Log

- Decision: treat #517 as Class A even though no schema migration is planned.
  Rationale: repository policy explicitly escalates deduplication and persistence-semantics changes; the risk is silent state growth and incorrect lifecycle projection.
  Date/Author: 2026-08-29 / Codex.
- Decision: keep full readiness provenance in the immutable saved input, but derive idempotency from an explicit, minimal set of forecast-driving values rather than recursively deleting timestamp-shaped keys.
  Rationale: an allow-list follows the actual `session_quality_v1` formula and avoids hiding a future meaningful field behind a generic sanitizer.
  Date/Author: 2026-08-29 / Codex.
- Decision: preserve existing rows and evaluations; suppress or project stale pending history instead of deleting it.
  Rationale: append-only evidence is an established invariant and live cleanup is outside the issue's authorization.
  Date/Author: 2026-08-29 / Codex.
- Decision: normalize numeric fingerprint inputs with at least nine decimal places and cache Today lifecycle reads by stable session id.
  Rationale: formula-driving changes must not be rounded away, while repeated candidate revisions for one session should use bounded local readers without changing the response contract.
  Date/Author: 2026-08-29 / Codex.

## Outcomes & Retrospective

The intended outcome is implemented: one semantic forecast revision per distinct pre-start driver state, zero new forecasts after start or terminal feedback, and no completed target resurfacing as pending in Today. Focused and contributor-safe tests are green; existing duplicate dogfood rows remain untouched.

## Context and Orientation

`api/session_quality_forecast.py` selects the nearest key session, builds `session_quality_v1`, fingerprints inputs, and writes `session_quality_predictions`. `models/session_quality_forecast.py` owns the pure probability formula and therefore defines which readiness and demand values can change the prediction. `api/session_feedback.py` projects immutable evaluations over raw predictions; raw prediction rows deliberately retain their original pending status. `api/today_snapshot.py` currently reads raw predictions to choose the shadow forecast shown in the canonical Today snapshot. `data/database.py` owns append-only prediction and evaluation persistence. Tests live primarily in `tests/smoke/test_session_quality_forecast.py`, `tests/smoke/test_post_workout_feedback.py`, `tests/smoke/test_api_today.py`, and `tests/smoke/test_api_session_quality_router_contract.py`.

A semantic fingerprint is the hash used to decide whether a call represents the same forecast-driving state. Volatile provenance timestamps may be stored for auditability, but they must not create new forecast identity. Terminal feedback means the latest feedback revision for the session is active and its completion status establishes that the athlete has supplied the post-workout fact. A started session means a confirmed matched actual activity has a start timestamp at or before the orchestration time.

## Plan of Work

First add behavior-level RED tests against a temporary `Database`. One test records the same plan and readiness values ten times while changing only `observed_at_utc` and nested provenance timestamps, and expects one prediction id. A companion test changes a real forecast driver such as readiness score before the session starts and expects a second revision. Additional tests seed a confirmed match with an actual start, then active terminal feedback, and prove recording stops. The Today test seeds raw pending rows plus immutable evaluations/feedback and proves the completed target is skipped rather than resurfaced.

Then make `record_shadow_session_quality_forecast` compute its fingerprint from an explicit dictionary containing the rule version, checkpoint/target identity, the planned session fields used by the formula, the resulting forecast values, and the readiness fields used by the formula (`score`, `confidence`, and `stale`). Continue storing the full existing input snapshot for provenance. Extend the selected target with the stable parent session identity needed for local lifecycle checks. Use existing database readers for the latest match, activities, and feedback; do not add schema or provider calls.

Before inserting, fail closed with a named reason when active terminal feedback exists or when confirmed actual evidence proves the session has started. Accept an optional orchestration timestamp only if needed for deterministic tests; default to current UTC and preserve existing callers. In `api/today_snapshot.py`, project evaluations and active feedback before choosing a pending candidate. Iterate candidates in existing sort order so a completed today's target can be skipped in favor of the next valid future target without extra provider I/O.

Finally run focused tests, the contributor-safe Python contour, Ruff, and any affected API/web contract checks. Inspect the diff for append-only compatibility, bounded reads, race behavior, and accidental state cleanup. Record exact results below and in the slice review.

## Concrete Steps

Work from `/private/tmp/ai-trainer-517` on branch `codex/issue-517-forecast-lifecycle`.

Run the RED slice first (the isolated worktree uses the shared repository virtualenv at `/Users/gregkisel/Developer/ai_trainer/ai_trainer_env/bin/python`):

    /Users/gregkisel/Developer/ai_trainer/ai_trainer_env/bin/python -m pytest -q tests/smoke/test_session_quality_forecast.py tests/smoke/test_post_workout_feedback.py tests/smoke/test_api_today.py tests/smoke/test_api_session_quality_router_contract.py

The new tests should fail specifically because timestamp-only calls append rows, post-start/post-feedback calls insert predictions, or Today chooses a completed raw pending row. After the implementation, rerun the same command and expect all tests to pass.

Run broad validation:

    /Users/gregkisel/Developer/ai_trainer/ai_trainer_env/bin/python -m ruff check .
    /Users/gregkisel/Developer/ai_trainer/ai_trainer_env/bin/python -m pytest -m "not live and not debug and not e2e" tests/
    npm --prefix web run contract:extract -- --check

If the public TypeScript contract changes unexpectedly, stop and either make the additive compatibility decision explicit or reduce the implementation to the existing contract. This issue is expected to correct semantics without a breaking schema change.

## Validation and Acceptance

The timestamp replay test shows ten calls, one stored prediction, and one reused id. The driver-change test shows a second immutable revision. Started-session and terminal-feedback tests show no insert and stable named reasons. The Today projection omits the completed target as active pending and selects the next eligible future forecast. Existing historical evaluations remain readable and attached to their prediction ids. The concurrent replay probe converges on one row, and repeated semantic calls keep row counts stable.

The final evidence must include focused test counts, contributor-safe test counts, Ruff, contract freshness, and a read-only temporary-database row-count transcript. No live athlete database cleanup or provider access is part of acceptance.

## Idempotence and Recovery

All tests use temporary SQLite databases and are safe to repeat. Forecast recording remains append-only for meaningful input changes and returns the existing row for semantic replays. If implementation fails midway, no migration exists to roll back; revert the code and tests on the task branch. Existing duplicate dogfood rows remain untouched. A later cleanup would require separate authorization, a stopped-service backup, and its own issue.

## Artifacts and Notes

Baseline evidence from the dogfood snapshot:

    target revisions: 70
    semantic variants after removing volatile observation timestamps: 14
    predictions created after feedback: 6
    unevaluated pending predictions after feedback: 6

This evidence diagnoses the current behavior but must not be copied into public test fixtures with athlete identifiers or raw health values.

## Interfaces and Dependencies

Keep `models/session_quality_forecast.build_session_quality_forecast` pure and unchanged unless a test proves the formula itself is involved. Add a small private helper in `api/session_quality_forecast.py` for the semantic fingerprint payload. If deterministic time is needed, add an optional keyword-only `now_utc: datetime | None = None` to `record_shadow_session_quality_forecast`; existing callers must remain valid. Use `Database.get_latest_plan_actual_match_for_session`, `Database.get_activities_by_ids`, and `Database.get_latest_session_feedback` rather than direct SQL in service code. Reuse the evaluation projection in `api/session_feedback.py` or extract a cycle-free pure helper if importing it would create a circular dependency. Do not add a dependency, table, column, provider call, or destructive maintenance path.

Plan revision note (2026-08-29): recorded the first RED slice and its exact failures before implementation; after GREEN, recorded the maker focused `81 passed in 1.67s`, related lifecycle `71 passed in 3.05s`, contributor-safe `2180 passed, 6 skipped, 26 deselected` in `59.76s`, Ruff success, and contract freshness success. Independent review found that the loop-result fallback could still resurrect an evaluated raw-pending row; the fallback now passes through the same evaluation and lifecycle projection. The final parent rerun is `82 passed in 2.28s`, Ruff green, contract artifact current.
