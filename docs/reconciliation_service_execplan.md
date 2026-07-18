Move `reconciliation_at` out of `api/planning_service.py` into `services/reconciliation.py`

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

This document must be maintained according to `.agent/PLANS.md`, which is checked into this repository at that path and defines the required format and living-document discipline for ExecPlans in AI Trainer.

## Purpose / Big Picture

Today, `api/planning_service.py` — a module that exists to be the FastAPI contract layer between the web/Streamlit UI and the rest of the system — owns a piece of pure orchestration logic called `reconciliation_at`. `reconciliation_at` compares a saved training plan against the athlete's actual recorded activities (from the local SQLite database and, optionally, from the Intervals.icu provider) and returns a dictionary describing which planned sessions were matched to which actual activities, which activities are unplanned, and whether there is a "data gap" (for example because the Intervals.icu provider was unreachable). This dictionary is called the reconciliation payload throughout this plan.

Because `reconciliation_at` lives in the API layer, the analytics module `services/recovery_analytics.py` — which is not part of the API layer, and by architectural convention (see `AGENTS.md` and `docs/architecture/architecture_analysis_add3.md`) is only allowed to depend on `data/`, `models/`, and other `services/` modules, never on `api/` — has to reach "upward" into `api.planning_service` with a local (function-body) import to call `reconciliation_at`. This is a layering violation: dependencies are supposed to flow `api → services/models/data`, never `services → api`. It was flagged in review on PR #187 and tracked as Issue #194.

After this change, `reconciliation_at` (and the two small private helpers it depends on, `_parse_as_of` and `_provider_reconciliation_evidence`) live in a new file, `services/reconciliation.py`. `services/recovery_analytics.py` imports `reconciliation_at` directly from `services.reconciliation` — no more reaching into `api`. `api/planning_service.py` keeps a compatibility re-export (`from services.reconciliation import reconciliation_at, ...`) so every existing caller of `api.planning_service.reconciliation_at` (the planning router, `api/session_feedback.py`, `api/today_snapshot.py`, `models/ai_tools.py`, and the smoke test suite) keeps working with zero behavior change — same function object, same return value, byte-for-byte.

You can see this working two ways. First, `python -c "from services.reconciliation import reconciliation_at; from api.planning_service import reconciliation_at as ps_reconciliation_at; assert reconciliation_at is ps_reconciliation_at"` succeeds — proving the compatibility re-export is the exact same function, not a copy. Second, a new regression test, `tests/smoke/test_api_architecture.py::test_services_modules_do_not_depend_on_api`, statically scans every `.py` file under `services/` for any `import api` or `from api...` statement (including ones nested inside a function body, which is how the original violation hid) and fails if it finds one. Before this change, that test fails because of the local import inside `services/recovery_analytics.py::refresh_recovery_episodes`. After this change, it passes.

## Progress

- [x] (2026-07-18) Read `AGENTS.md`, `docs/architecture/architecture_analysis_add3.md`, `.agent/PLANS.md`, `docs/AI_Feature_Development_Workflow.md`.
- [x] (2026-07-18) Surveyed `api/planning_service.py` (the `reconciliation_at`/`_parse_as_of`/`_provider_reconciliation_evidence` trio, plus `reconciliation`, `preview_weekly_rebalance`, `confirm_weekly_rebalance` which call into it) and every consumer of `reconciliation_at` repo-wide (`services/recovery_analytics.py`, `api/session_feedback.py`, `api/today_snapshot.py`, `api/routers/planning.py`, `models/ai_tools.py`, and the smoke tests).
- [x] (2026-07-18) Created this ExecPlan.
- [x] (2026-07-18) Wrote the RED contract: `tests/smoke/test_reconciliation_service_migration.py` (byte-equivalent old-path/new-path payloads across five scenarios, mutation-freedom, provider gating) and a new `test_services_modules_do_not_depend_on_api` regression guard added to `tests/smoke/test_api_architecture.py`. Committed separately before any production code changed.
- [x] (2026-07-18) Implemented GREEN: created `services/reconciliation.py` (moved `reconciliation_at`, `_parse_as_of`, `_provider_reconciliation_evidence` verbatim), turned the three definitions in `api/planning_service.py` into a compatibility import, switched `services/recovery_analytics.py`'s local import to `services.reconciliation`, and updated the one white-box smoke test that monkeypatched `api.planning_service._provider_reconciliation_evidence` (`tests/smoke/test_api_planning.py::test_provider_failure_blocks_rebalance_without_hiding_local_evidence`) to patch the new home instead.
- [x] (2026-07-18) Ran the focused reconciliation/recovery/session-feedback/Today/weekly-rebalance/RecoveryReplan tests, then the full smoke suite, then the broader non-live suite. Recorded exact pass counts below in Outcomes & Retrospective.
- [ ] Push the branch and open a draft PR with `Closes #194`.

## Surprises & Discoveries

- Observation: `api/session_feedback.py` and `api/today_snapshot.py` both import `reconciliation_at` directly from `api.planning_service` at module scope. That is not a layering violation (api depending on api), so per the issue's explicit instruction ("inspect ... rather than creating a second orchestration path") these two files are left untouched, still importing the compatibility re-export from `api.planning_service`. Only `services/recovery_analytics.py`'s import is a genuine `services → api` inversion.
  Evidence: `grep -n "reconciliation_at\|planning_service" api/session_feedback.py api/today_snapshot.py` shows `from api.planning_service import reconciliation_at` at module scope in both files, called locally by name thereafter — untouched by moving the underlying implementation.
- Observation: one existing smoke test performs white-box monkeypatching of `api.planning_service._provider_reconciliation_evidence` (`tests/smoke/test_api_planning.py::test_provider_failure_blocks_rebalance_without_hiding_local_evidence`). Because `preview_weekly_rebalance` stays in `api/planning_service.py` but the real `reconciliation_at`/`_provider_reconciliation_evidence` now live in `services/reconciliation.py`, `reconciliation_at`'s internal call to `_provider_reconciliation_evidence` resolves against `services.reconciliation`'s own module globals, not `api.planning_service`'s — so the old monkeypatch target silently stops having any effect. This one test had to be updated, as a direct, minimal consequence of the migration, not scope creep.
  Evidence: `tests/smoke/test_api_planning.py:588-591` — `monkeypatch.setattr(ps, "_provider_reconciliation_evidence", ...)`.

## Decision Log

- Decision: Move only `reconciliation_at` and its two private helpers (`_parse_as_of`, `_provider_reconciliation_evidence`) into `services/reconciliation.py` — not `preview_weekly_rebalance`, `confirm_weekly_rebalance`, or `reconciliation`.
  Rationale: Issue #194's stated scope is `reconciliation_at` and "minimally necessary dependencies." `services/recovery_analytics.py` only calls `reconciliation_at`. The three preview/confirm/rebalance functions are planning-checkpoint mutation orchestration that belongs with the rest of `api/planning_service.py`'s checkpoint-authoring functions (`build_plan`, `apply_adjustment`, etc.) and isn't needed outside the API layer today; moving them would widen the diff without fixing any layering violation. They keep calling `reconciliation_at` by its (now imported) name, unchanged.
  Date/Author: 2026-07-18, Claude.
- Decision: `api/planning_service.py` re-exports via `from services.reconciliation import reconciliation_at, _parse_as_of, _provider_reconciliation_evidence` (a real import, i.e. the same function objects), not a wrapper function that calls through.
  Rationale: A wrapper would create two call sites and risk the "subtly different copies" the issue explicitly warns against; a direct re-export guarantees byte-identical behavior by construction (it's literally the same function).
  Date/Author: 2026-07-18, Claude.
- Decision: Update `tests/smoke/test_api_planning.py`'s one monkeypatch of `_provider_reconciliation_evidence` to target `services.reconciliation` instead of `api.planning_service`, as part of the GREEN commit.
  Rationale: This is required for the "contributor-safe smoke suite stays green" acceptance gate; the alternative (leaving a second, dead copy of `_provider_reconciliation_evidence` behind in `api/planning_service.py` just so the old monkeypatch target still exists) would recreate exactly the "subtly different copies" problem Issue #194 asks to avoid.
  Date/Author: 2026-07-18, Claude.
- Decision: Add the "services must not import api" regression guard as a new test function in the existing `tests/smoke/test_api_architecture.py` (which already hosts the analogous "api must not import ui" guards), rather than a new file.
  Rationale: Keeps all static import-direction contracts in one place; matches the existing `_import_roots` AST-walk helper exactly (it already recurses into function bodies, so it catches local imports like the one this issue is about).
  Date/Author: 2026-07-18, Claude.

## Outcomes & Retrospective

GREEN landed as planned, with no scope surprises beyond the two documented in Surprises & Discoveries. `services/reconciliation.py` now owns `reconciliation_at`, `_parse_as_of`, and `_provider_reconciliation_evidence`, moved verbatim (no logic changes — confirmed by the RED byte-equivalence tests passing unchanged after the move). `api/planning_service.py::reconciliation_at` is a real re-export (`is` identity, not a wrapper), so `reconciliation`, `preview_weekly_rebalance`, and `confirm_weekly_rebalance` needed zero code changes. `services/recovery_analytics.py::refresh_recovery_episodes` now imports `reconciliation_at` from `services.reconciliation`, closing the only genuine `services → api` inversion in the codebase. `api/session_feedback.py`, `api/today_snapshot.py`, and the planning router were inspected and intentionally left unchanged — they already imported from `api.planning_service`, which is a same-layer (api → api) dependency, not an inversion, so touching them would only have widened the diff without fixing anything.

Validation results (all commands run from repo root):

    python -m pytest tests/smoke/test_reconciliation_service_migration.py tests/smoke/test_api_architecture.py -q
    -> 12 passed

    python -m pytest tests/smoke/test_recovery_transfer_identity_handoff.py tests/smoke/test_recovery_replan_loop.py tests/smoke/test_api_planning.py tests/smoke/test_api_today.py tests/smoke/test_plan_discipline_truth.py tests/smoke/test_post_workout_feedback.py tests/smoke/test_feedback_planning_handoff.py tests/smoke/test_recovery_response.py tests/smoke/test_recovery_episode_materializer.py -q
    -> 154 passed

    python -m pytest tests/smoke -q
    -> 844 passed (baseline was 834 passed, 1 skipped; the 9 new tests from this issue's RED contract account for the delta, plus one previously-skipped case now passing, unrelated to this change)

    python -m pytest -m "not live and not debug" tests/ -q
    -> 887 passed, 5 skipped, 24 deselected (the 5 skips are pre-existing environment-gated cases — missing local HRV fixture data and the `garth` package not being installed — unrelated to this change)

No web/API contract types or `web/` files changed, so Next lint/build was not run, per the task's own validation instructions.

Gaps/lessons: the migration surfaced one piece of hidden coupling — a smoke test white-box-monkeypatching a private helper by module attribute (`tests/smoke/test_api_planning.py`) — that a purely black-box test suite would not have caught until it silently stopped exercising its intended failure path. Worth remembering for future service-layer extractions: grep test files for `monkeypatch.setattr(<module>, "_private_name"` on anything being moved, not just public functions.

## Context and Orientation

The reconciliation payload is a Python dictionary produced by `reconciliation_at(db, *, weeks=1, as_of=None, include_provider=True)`, defined (before this change) in `api/planning_service.py`. `db` is a `data.database.Database` instance, a thin wrapper around a local SQLite file. `weeks` bounds how far back to look (clamped to 1..12). `as_of` is the "as of" date to reconcile up to — a `datetime.date`, an ISO string like `"2026-07-18"`, or `None` (meaning "today"). `include_provider` controls whether the function also asks the Intervals.icu integration (`services/intervals_icu.py`) for corroborating provider evidence; when `False`, no network/provider call happens at all.

`reconciliation_at` does the following, in order: it loads the most recent planning checkpoint (a saved version of the athlete's training plan) via `db.get_latest_planning_checkpoint()`; if there is no plan, it returns `{"has_plan": False, "rows": [], "unplanned_activities": []}` immediately. Otherwise it restores the plan dictionary (`models/planning_checkpoints.py::restore_goal_plan_from_checkpoint`), stamps every planned session with a stable content-derived identity (`models/session_identity.py::ensure_session_identities`), resolves the `as_of` date and week window, asks `_provider_reconciliation_evidence` for provider activities/events (or a `{"status": "disabled"}` placeholder if `include_provider=False`), reads locally recorded activities and any existing user-confirmed plan/actual "ledger" rows from the database, and hands all of that to `models/plan_actual_reconciliation.py::build_reconciliation`, which does the actual matching. If the provider evidence came back `"unavailable"` (a `services.intervals_icu.IntervalsICUError`, e.g. an HTTP failure), `reconciliation_at` marks `data_quality.status = "data_gap"` and appends `"provider_unavailable"` to `data_quality.reasons` so callers can tell local-only evidence apart from an outage. It never writes to the database — this function is read-only.

Three other functions in `api/planning_service.py` call `reconciliation_at`: the thin two-line `reconciliation(db, weeks=1)` wrapper, `preview_weekly_rebalance` (builds a proposed plan change from the reconciliation payload), and indirectly `confirm_weekly_rebalance` (calls `preview_weekly_rebalance` to re-derive and validate a fingerprint before committing a change). None of those three move in this plan — only `reconciliation_at` and its two private helpers do.

`services/recovery_analytics.py::refresh_recovery_episodes` is the one production caller outside `api/` that needs `reconciliation_at`. It calls it with `include_provider=False` (recovery analytics is explicitly local-only/shadow-mode; see the "guardrails" block in `services/recovery_analytics.py::recovery_analytics_summary`) inside a function-body import, with the comment "Local import avoids making the pure analytics module part of planning's import graph and guarantees provider access is disabled" — that comment is about avoiding *api's* wider planning import graph specifically (`api/planning_service.py` imports the whole training planner, FIT/TCX export, workout catalog, etc.), which is exactly the layering problem this issue fixes; `services/reconciliation.py` has none of that baggage, so after the move a module-level import would be just as safe, but this plan keeps the import local anyway to keep the diff minimal and avoid asserting a new claim (top-level import safety) that isn't this issue's concern.

`tests/smoke/test_api_architecture.py` already contains the pattern to copy for the new import-direction guard: `_import_roots(path)` parses a file with `ast.parse` and walks every `ast.Import`/`ast.ImportFrom` node (via `ast.walk`, which recurses into function bodies — this is what makes it able to catch the local import inside `refresh_recovery_episodes`), returning the set of top-level module names imported. `test_api_modules_do_not_depend_on_legacy_ui` uses this to assert no file under `api/` imports `ui`. The new guard does the mirror check for `services/` against `api`.

## Plan of Work

1. Create `services/reconciliation.py`. Move `_parse_as_of`, `_provider_reconciliation_evidence`, and `reconciliation_at` out of `api/planning_service.py` into this new file, verbatim (no logic changes). The new file needs its own imports: `from __future__ import annotations`; `date`, `datetime`, `timedelta` from `datetime`; `Any`, `Dict` from `typing`; `data.database.Database`; `models.plan_actual_reconciliation.build_reconciliation`; `models.planning_checkpoints.restore_goal_plan_from_checkpoint`; `models.session_identity.ensure_session_identities`. The `from services.intervals_icu import IntervalsICUError, get_client` import inside `_provider_reconciliation_evidence` stays local exactly as it was (this was already a `services → services` import, not a layering issue).

2. In `api/planning_service.py`: delete the bodies of `_parse_as_of`, `_provider_reconciliation_evidence`, and `reconciliation_at`; replace them with `from services.reconciliation import _parse_as_of, _provider_reconciliation_evidence, reconciliation_at` placed with the other top-of-file imports. Remove `build_reconciliation` from the `models.plan_actual_reconciliation` import list at the top of the file (it becomes unused there — its only call site moved). Leave `MATCH_RULE_VERSION`, `apply_weekly_rebalance_preview`, `build_weekly_rebalance_preview`, `find_planned_session` (still used elsewhere in the file) untouched. The `reconciliation(db, weeks=1)` wrapper, `preview_weekly_rebalance`, and `confirm_weekly_rebalance` need no code changes — they already call `reconciliation_at` by bare name, which now resolves through the import.

3. In `services/recovery_analytics.py::refresh_recovery_episodes`: change `from api.planning_service import reconciliation_at` to `from services.reconciliation import reconciliation_at`, and adjust the explanatory comment above it (it currently says the local import "avoids making the pure analytics module part of planning's import graph" — reword to note it no longer needs to reach into `api` at all, and that the import stays local purely to minimize this module's always-loaded surface, not to dodge a layering violation).

4. Update `tests/smoke/test_api_planning.py::test_provider_failure_blocks_rebalance_without_hiding_local_evidence`: change `from api import planning_service as ps` / `monkeypatch.setattr(ps, "_provider_reconciliation_evidence", ...)` to import `from services import reconciliation as reconciliation_service` and patch `reconciliation_service._provider_reconciliation_evidence` instead. This is the only test in the repository that monkeypatches this private helper by module attribute.

5. Add `test_services_modules_do_not_depend_on_api` to `tests/smoke/test_api_architecture.py`, following the existing `test_api_modules_do_not_depend_on_legacy_ui` pattern: walk every `.py` file under `services/`, collect `_import_roots`, and assert none of them contains `"api"`.

## Concrete Steps

All commands run from the repository root, `/home/runner/work/ai_trainer/ai_trainer`, inside the project's virtualenv (`source ai_trainer_env/bin/activate`, or whatever Python environment already has `requirements.txt` + `requirements-dev.txt` installed).

RED (test-only) commit — before any production file changes:

    python -m pytest tests/smoke/test_reconciliation_service_migration.py tests/smoke/test_api_architecture.py -q

Expected RED output: `test_reconciliation_service_migration.py` fails to even collect (`ModuleNotFoundError: No module named 'services.reconciliation'`), and `test_services_modules_do_not_depend_on_api` fails with an assertion listing `services/recovery_analytics.py` as an offender.

    git add tests/smoke/test_reconciliation_service_migration.py tests/smoke/test_api_architecture.py docs/reconciliation_service_execplan.md
    git commit -m "test: RED contract for services/reconciliation extraction (#194)"

GREEN commit — after applying the Plan of Work above:

    python -m pytest tests/smoke/test_reconciliation_service_migration.py tests/smoke/test_api_architecture.py -q
    python -m pytest tests/smoke/test_recovery_transfer_identity_handoff.py tests/smoke/test_recovery_replan_loop.py tests/smoke/test_api_planning.py tests/smoke/test_api_today.py tests/smoke/test_plan_discipline_truth.py -q
    python -m pytest tests/smoke -q
    python -m pytest -m "not live and not debug" tests/ -q

Expected GREEN output: all of the above pass; the full smoke suite is expected to match or exceed the pre-change baseline of `834 passed, 1 skipped`.

    git add api/planning_service.py services/reconciliation.py services/recovery_analytics.py tests/smoke/test_api_planning.py docs/reconciliation_service_execplan.md
    git commit -m "refactor: move reconciliation_at ownership to services/reconciliation (#194)"

## Validation and Acceptance

Behavior is unchanged and observable the same way it always was: calling `api.planning_service.reconciliation_at(db, weeks=1, as_of="2026-07-18", include_provider=False)` against a plan checkpoint returns the exact same dictionary shape and values as before this change (proved by the RED/GREEN byte-equivalence tests, which build the same inputs and compare `json.dumps(result, sort_keys=True, default=str)` for the old and new import paths across five scenarios: no plan; local-only with provider disabled; provider available; provider unavailable/data-gap; and a ledger-confirmed nested multi-session identity case reusing the fixtures from `tests/smoke/test_recovery_transfer_identity_handoff.py`).

The architectural acceptance is the new `test_services_modules_do_not_depend_on_api` test: run `python -m pytest tests/smoke/test_api_architecture.py -q` and see `5 passed` (the 3 existing tests plus the new one, plus any others added meanwhile) with no `services/*` file reported as importing `api`.

The full required validation command set (see Concrete Steps) must all pass, with the smoke suite pass count at or above the documented baseline (`834 passed, 1 skipped`).

## Idempotence and Recovery

Every step is a plain file edit or an additive new file — nothing destructive, nothing that touches the database or any external service. If a step is interrupted partway, `git status` shows exactly which files were touched; re-running the same edits is safe because they are simple replacements, not accumulating patches. If the GREEN implementation turns out to break something unexpected, `git revert` of the GREEN commit alone restores the pre-refactor behavior while keeping the RED tests in history as documentation of the target contract.

## Artifacts and Notes

(Test output and diff excerpts will be added here once RED and GREEN are both verified.)

## Interfaces and Dependencies

In `services/reconciliation.py`, this plan defines:

    def reconciliation_at(
        db: Database,
        *,
        weeks: int = 1,
        as_of: date | str | None = None,
        include_provider: bool = True,
    ) -> Dict[str, Any]: ...

`api.planning_service.reconciliation_at` becomes an alias for this exact function object (verified by `is` identity in the RED/GREEN tests), not a separate function with matching behavior. `services/recovery_analytics.py` depends on `services.reconciliation.reconciliation_at` directly. No new third-party dependencies are introduced; this plan only moves existing code and its existing internal dependencies (`data.database.Database`, `models.plan_actual_reconciliation.build_reconciliation`, `models.planning_checkpoints.restore_goal_plan_from_checkpoint`, `models.session_identity.ensure_session_identities`, `services.intervals_icu`).
