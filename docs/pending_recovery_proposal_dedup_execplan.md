# Deduplicate active Recovery Replan proposals by target session

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds. This document is maintained in accordance with `.agent/PLANS.md`.

## Purpose / Big Picture

Recovery Replan evaluates readiness whenever Coach is invoked. A second health sync during the same day can change readiness evidence and therefore create a new immutable decision fingerprint even though the intervention still concerns the same planned session. Today that can create two pending cards asking the athlete to make the same decision. After this change, every gate evaluation remains in the audit log, while the user sees at most one active Recovery Replan proposal for one athlete-day, plan version, and target session. The behavior is observable in focused smoke tests that run the loop twice with different readiness snapshots: two decision rows remain, but both point to one proposal.

## Progress

- [x] (2026-07-11 12:14Z) Inspected Recovery Replan orchestration, SQLite proposal lifecycle, existing idempotency tests, and project workflow.
- [x] (2026-07-11 12:14Z) Created structured GitHub Issue #156 with Spec/BDD, acceptance criteria, baseline, and scope boundaries.
- [x] (2026-07-11 12:14Z) Created isolated worktree `/tmp/ai_trainer_issue156_pending_dedup` on `codex/issue-156-pending-dedup` from `origin/main` at `0154f6c`.
- [x] (2026-07-11 12:18Z) Added contract-first persistence and loop tests; red run produced `2 failed, 8 passed` before production changes.
- [x] (2026-07-11 12:24Z) Added nullable `active_key`, active-state partial uniqueness, atomic reuse lookup, stable loop keying, and a two-connection race test; focused result is `11 passed`.
- [x] (2026-07-11 12:25Z) Completed focused, adjacent, contributor-safe, compilation, Ruff, diff, migration, and concurrency validation plus full self-review.
- [x] (2026-07-11 12:25Z) Published four process-ordered commits and opened mergeable draft PR #157 with `Closes #156`; GitHub CI and issue-link automation passed on implementation head `8a74206`.
- [x] (2026-07-11 12:26Z) Finalized this living document with implementation, validation, publication, and residual-risk evidence.

## Surprises & Discoveries

- Observation: exact evaluation idempotency and active-session deduplication are different contracts.
  Evidence: `data/database.py` has a unique partial index on `coach_proposals.source_key`, while `api/recovery_replan_loop.py` passes the complete readiness fingerprint as that key. Exact repeats reuse a proposal, but readiness 35 to 36 creates a new source key.

- Observation: proposal mutation already has a transient `applying` state.
  Evidence: `Database.transition_coach_proposal_status` atomically claims `pending → applying`. The active uniqueness rule must include both `pending` and `applying`, otherwise a concurrent evaluation could insert another card while approval is in progress.

- Observation: the current SQLite database is single-athlete storage.
  Evidence: neither `recovery_decisions` nor `coach_proposals` has an athlete/account column. This change can encode the local athlete scope implicitly, but a future shared multi-user database must add explicit athlete scope before reusing the uniqueness contract.

- Observation: the intended failures isolate both missing layers of the contract.
  Evidence: the red focused run failed because `save_coach_proposal` rejected `active_key`, while the loop test stored two decision rows correctly but linked them to proposal ids 1 and 2. The pre-change transcript was `2 failed, 8 passed`.

- Observation: SQLite's partial unique index is sufficient for the real two-writer race in this local architecture.
  Evidence: two threads opened independent connections with different decision fingerprints and the same active key; both returned the same proposal id and the database contained one pending row. The focused contour passed as `11 passed`.

## Decision Log

- Decision: preserve `source_key` as the immutable evaluation fingerprint and add a nullable `active_key` to `coach_proposals`.
  Rationale: changing `source_key` would collapse distinct evidence or break exact-call idempotency. A separate key expresses the different lifecycle rule: many decisions may share one active proposal.
  Date/Author: 2026-07-11 / Codex.

- Decision: enforce uniqueness for statuses `pending` and `applying`, not for terminal statuses.
  Rationale: the athlete must never see or create a duplicate while confirmation is open or being applied. Once a proposal is approved, rejected, failed, or rolled back, a later evaluation may legitimately open a new proposal.
  Date/Author: 2026-07-11 / Codex.

- Decision: build the active key from the gate as-of day, base checkpoint id, and target plan row date/index.
  Rationale: readiness evidence may drift without changing the user decision, so readiness is excluded. The checkpoint is included because a proposal for an older plan is stale and must not suppress a valid proposal for a newer plan version. In the current single-athlete SQLite model, the database itself supplies athlete scope.
  Date/Author: 2026-07-11 / Codex.

- Decision: reuse the first active proposal without mutating its preview or parameters.
  Rationale: a pending proposal is a concrete mutation against an exact base checkpoint. Rewriting it in place would make its audit provenance ambiguous. New readiness evidence remains immutable in the new `recovery_decisions` row, which links to the existing proposal.
  Date/Author: 2026-07-11 / Codex.

## Outcomes & Retrospective

Issue #156 is implemented and published in mergeable draft PR #157. Two intraday gate snapshots now produce two immutable `recovery_decisions` rows linked to one active `coach_proposals` row. Persistence reuses the proposal in both `pending` and `applying`, releases the key after a terminal status, survives a real two-connection race, and migrates an older database additively. Existing exact fingerprint idempotency and approve/reject/rollback behavior remain green.

The change deliberately keeps the first pending proposal immutable rather than rewriting evidence in place. The latest readiness snapshot remains visible in its own recovery decision row, while the actionable mutation stays tied to the same base checkpoint and target plan row. A later plan checkpoint creates a different active key so a stale card cannot suppress a valid proposal for the new plan version.

The local contributor-safe contour finished at `464 passed, 1 skipped`, adding four behavior tests to the `460 passed, 1 skipped` baseline. The skip remains the environment-specific local-listening-socket restriction. GitHub CI passed on the published implementation head. Human review and the explicit maintainer merge decision remain outside this plan's implementation scope.

## Self-Review

Correctness: readiness values, severity, and evidence are absent from `active_key`, so the exact intraday drift that motivated the issue deduplicates. The as-of day, checkpoint, target date, and target row index prevent unrelated days or plan versions from colliding. Every new decision still calls `save_recovery_decision` and is linked to the reused proposal.

Race safety: SQLite enforces active uniqueness rather than relying on a read-before-write check. `INSERT OR IGNORE` and lookup happen on one connection; an independent two-thread test proves that concurrent writers return one row. `applying` remains inside the partial index, closing the confirmation-window race.

Migration and compatibility: old rows receive null `active_key`; null values do not collide. Existing callers omit the optional argument and retain source-key behavior. Proposal dictionaries gain one additive field. No API route, frontend contract, gate threshold, or plan mutation logic changed.

Weakest point: athlete scope is implicit because the current SQLite database is single-athlete. A future shared database must add an explicit athlete/account id to the active key and queries. Also, this change does not supersede stale pending proposals after a plan edit; instead the checkpoint component permits a new valid proposal and existing stale-checkpoint guards still prevent unsafe application. Automated stale-card cleanup is a separate lifecycle concern, not part of intraday readiness deduplication.

## Context and Orientation

`api/recovery_replan_loop.py::run_recovery_replan_loop` builds the readiness conflict report, computes a fingerprint over the report and active planning checkpoint, saves an immutable row through `Database.save_recovery_decision`, and creates a durable `coach_proposals` row for a conflict. `models/recovery_replan.py::build_recovery_replan_variant` maps the selected conflict to a specific row in the active plan and returns `selected_conflict`, the target draft row, and a deterministic downgrade.

`data/database.py` owns SQLite schema migration and proposal persistence. `coach_proposals.source_key` is globally unique when non-null and makes the exact same evaluation idempotent. Proposal status begins as `pending`; approval claims it as `applying`; terminal public statuses are `approved`, `rejected`, `failed`, and `rolled_back`. An active proposal in this plan means a proposal whose status is `pending` or `applying`.

`tests/smoke/test_recovery_replan_loop.py` contains pure variant tests, database idempotency coverage, loop behavior, and approve/reject/rollback safety. The new behavior belongs there because it crosses the same persistence and orchestration boundary. No web or Streamlit changes are needed: the Decisions API already renders whatever active proposals persistence returns.

The active key is not a prediction identifier and must not include readiness score, severity, evidence, or the recovery decision fingerprint. It identifies the user decision scope. For this repository's single-athlete database, its canonical payload consists of the as-of calendar day, base plan checkpoint id, target plan date, and target plan row index, hashed or serialized deterministically. Including plan version prevents a stale pending proposal from suppressing a new valid proposal after an unrelated plan edit.

## Behavioral Specification

Given one pending Recovery Replan proposal, when an intraday readiness refresh changes the gate fingerprint but keeps the same as-of day, checkpoint, and target plan row, then the loop stores a second recovery decision, returns the existing proposal id, links both decisions to that proposal, and persistence contains one active proposal.

Given an active proposal is in `applying`, when another evaluation tries to create the same active key, then persistence returns the existing applying proposal and does not insert another row.

Given an earlier proposal with the same active key is terminal, when a new distinct decision fingerprint is evaluated, then persistence inserts a new pending proposal.

Given existing build-plan or adjust-plan callers do not provide an active key, when they save proposals, then their behavior and returned dictionaries remain unchanged except for an additive `active_key: None` field.

Given an older SQLite database without the new column, when `Database` initializes it, then it adds the nullable column and partial unique index without rewriting existing rows.

## Milestones

The first milestone establishes the contract in tests. Extend `tests/smoke/test_recovery_replan_loop.py` with one persistence test proving active/applying uniqueness and terminal reuse, and one loop test proving different fingerprints produce two immutable decisions linked to one proposal. Run the focused file and record the failures caused by the missing `active_key` interface.

The second milestone implements the smallest safe persistence change. Add nullable `active_key` to the proposal schema and migration map in `data/database.py`, create a partial unique SQLite index over active rows, extend proposal serialization and save logic, and preserve all existing callers by defaulting the new argument to `None`. Then add a stable key builder in `api/recovery_replan_loop.py` and pass it only for Recovery Replan proposals.

The final milestone validates and publishes. Run focused recovery tests, adjacent coach decision tests, the full contributor-safe smoke suite, compilation, Ruff, and `git diff --check`. Inspect the diff for race conditions, migration safety, lifecycle correctness, backward compatibility, and unnecessary abstraction. Finalize this living plan with evidence, commit in docs-test-feature order, push the issue-numbered branch, and open a draft PR with `Closes #156`.

## Plan of Work

First edit `tests/smoke/test_recovery_replan_loop.py`. At the database level, save two proposals with different `source_key` values but the same `active_key`; assert that pending and applying states reuse the first id. Resolve that row, save another proposal, and assert a new id is allowed. At the orchestration level, monkeypatch two conflict reports that differ only in readiness evidence, run the loop against the same checkpoint and day, and assert two decision rows plus one proposal row.

Next edit `data/database.py`. Add `active_key TEXT` to `CREATE TABLE`, `_COACH_PROPOSAL_COLUMN_TYPES`, every proposal select/deserialize path, and `save_coach_proposal`. Add `idx_coach_proposals_active_key` as a unique partial index where `active_key IS NOT NULL AND status IN ('pending', 'applying')`. When either unique constraint ignores an insert, resolve the existing row first by exact `source_key`, then by active `active_key`. Perform insertion and lookup on one connection so SQLite serializes competing writers. Existing proposals have null active keys and cannot collide during migration.

Then edit `api/recovery_replan_loop.py`. Define a private deterministic active-key function that receives the gate report, selected variant, and base checkpoint id. Its canonical payload contains the as-of day, checkpoint id, selected conflict date, and the target draft-row index. Pass the resulting key to `Database.save_coach_proposal`; do not change `_fingerprint`, recovery decision persistence, proposal payloads, or UI contracts.

Finally update this ExecPlan after every milestone. No dependencies, API endpoints, frontend code, gate thresholds, or planning mutation rules should change.

## Concrete Steps

Run all commands from `/tmp/ai_trainer_issue156_pending_dedup`:

    /Users/gregkisel/Developer/ai_trainer/ai_trainer_env/bin/python -m pytest tests/smoke/test_recovery_replan_loop.py -q
    /Users/gregkisel/Developer/ai_trainer/ai_trainer_env/bin/python -m pytest tests/smoke/test_coach_decisions.py tests/smoke/test_readiness_conflicts.py -q
    /Users/gregkisel/Developer/ai_trainer/ai_trainer_env/bin/python -m pytest tests/smoke -q
    /Users/gregkisel/Developer/ai_trainer/ai_trainer_env/bin/python -m compileall -q api models data
    /Users/gregkisel/Developer/ai_trainer/ai_trainer_env/bin/ruff check api/recovery_replan_loop.py data/database.py tests/smoke/test_recovery_replan_loop.py
    git diff --check

The focused test added in the first milestone must fail before implementation because `Database.save_coach_proposal` does not accept `active_key`. After implementation it must pass and demonstrate two recovery decisions linked to one active proposal. The final smoke count should exceed the baseline of 460 passed, with the same environment-specific socket skip permitted.

## Validation and Acceptance

Acceptance requires behavior, not only schema shape. The focused loop test must produce two different decision ids and one proposal id for two intraday snapshots. The database test must prove the uniqueness index covers `pending` and `applying`, and that a terminal status releases the key. Existing exact `source_key` idempotency, rejection, approval, stale-checkpoint refusal, and append-only rollback tests must remain green.

The contributor-safe suite must pass without Garmin credentials or live AI providers. Compilation, Ruff, and `git diff --check` must be clean. Because no UI behavior or frontend contract changes, a web build is not required for this persistence-only hardening.

## Idempotence and Recovery

Schema migration is additive: initialization may run repeatedly, existing rows receive null `active_key`, and both indexes use `IF NOT EXISTS`. Test databases are temporary. If implementation fails after adding the column, old application code ignores it safely. If a branch must be abandoned, remove only the isolated worktree after preserving any desired commit; never reset or clean the main checkout.

## Artifacts and Notes

Issue: `https://github.com/rbctmz/ai_trainer/issues/156`.

Draft PR: `https://github.com/rbctmz/ai_trainer/pull/157`.

Published implementation head: `8a7420622c1bf731fda8be7dbc784313646e8fa9`.

GitHub CI: `https://github.com/rbctmz/ai_trainer/actions/runs/29152526120` — success.

Baseline:

    main 0154f6c
    460 passed, 1 skipped

TDD red phase:

    2 failed, 8 passed
    TypeError: Database.save_coach_proposal() got an unexpected keyword argument 'active_key'
    assert second["decision"]["proposal_id"] == first["proposal"]["id"]

Final local evidence:

    focused: 12 passed
    adjacent: 45 passed
    contributor-safe: 464 passed, 1 skipped
    compileall, Ruff, git diff --check: pass

## Interfaces and Dependencies

No new third-party dependencies are allowed.

In `data/database.py`, extend the existing method compatibly:

    Database.save_coach_proposal(..., source_key=None, active_key=None) -> dict

Every returned proposal dictionary includes:

    {
        "source_key": str | None,
        "active_key": str | None,
    }

In `api/recovery_replan_loop.py`, add a private helper equivalent to:

    _active_proposal_key(report: dict[str, Any], variant: dict[str, Any], checkpoint_id: int) -> str

It must be deterministic and must not contain readiness evidence. Public API shapes remain additive and backward compatible.

Revision note (2026-07-11): Initial ExecPlan created after inspecting Issue F persistence and lifecycle. It separates immutable evaluation identity from active user-decision identity so deduplication does not erase audit evidence.

Revision note (2026-07-11): Finalized after TDD implementation, two-connection race validation, legacy-schema migration coverage, full local smoke, draft PR publication, and green GitHub CI. The retrospective records the deliberate checkpoint scoping and future multi-athlete boundary.
