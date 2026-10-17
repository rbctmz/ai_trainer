# Planning S1 — final acceptance bundle

Issue [#685](https://github.com/rbctmz/ai_trainer/issues/685), parent
[#677](https://github.com/rbctmz/ai_trainer/issues/677). Prepared 2026-10-17 by
Codex as Supervisor / Integrator. The [specification](planning_preview_confirm_slice_spec.md)
owns AC1–AC8 and the [ExecPlan](planning_preview_confirm_execplan.md) records
the implementation and independent checks of M1–M4.

## Candidate and scope

The final candidate branch is `codex/issue-685-s1-acceptance`, based on M4
`3b88d331039ee45e2954af524015b7d682d9ac39`. Its M5 changes are acceptance
documentation only. The product tree was last changed at `f681b82`; test-fixture
correction `495d589` is included. Main was freshly fetched and is an ancestor:
`f0f80d335e7f3973a80241a5127d88ba7eca52dc`. The final PR must target `main` and
contain the complete S1 diff; its GitHub head and check URLs are recorded in the
PR/issue after publication to avoid a self-referential commit hash here.

This candidate retains one frozen result, rejects changed inputs, publishes
plan/settings/receipt atomically, and replays successful Planning and Coach
build confirmations without duplication or reactivation. It does not change
training mathematics, expired-cycle behavior, inherited dates/events or the
step-4 information design. Those remain #677 S2–S4.

## Delivery decision

**Observed:** #687 and #688 have failed contributor-safe checks, as expected
for intermediate M1/M2 RED states. #689 and #690 pass contributor-safe,
contract, complete browser and secret checks. None has a native review result;
#690's Review gate annotation explicitly says `no submitted native review for
the current head`.

**Inferred:** sequentially merging all five draft PRs would expose the
deliberately incomplete regression stages on main. The cheap falsifier is to
inspect current PR checks and compare the final branch to freshly fetched main.

**Verified by:** GitHub reads for #686–#690 on 2026-10-17 and
`git merge-base --is-ancestor origin/main HEAD` succeeded. Publish one final PR
to main, retaining #686–#690 as milestone evidence. Do not merge intermediate
RED branches, close the parent issue, or delete branches with dependent work.
After the final PR is merged, the human owner may close the superseded draft
PRs without merging them; there is no remaining chain to merge.

## Acceptance mapping

All paths below are repository-relative. Test names are the executed names,
not the original proposed names in the specification's historical RED matrix.

| Criterion | Executed evidence and observable result | Status before native/human gate |
| --- | --- | --- |
| AC1 exact result | `tests/smoke/test_planning_build_commit.py::test_commit_is_complete_frozen_payload_without_calculation`, all three modes with first/existing plan; complete M1 checkpoint/response oracles in `test_planning_build_confirmation_storage.py` and `test_planning_build_preparation.py`. Confirm inserts retained checkpoint JSON; planner/forecast/materializer recomputation is forbidden by guards. | GREEN |
| AC2 freshness | HTTP `test_activity_added_after_preview_is_stale`; preparation coherent-read/race/dependency matrix; commit `test_stale_invalidates_only_preview`, `test_full_dependency_contract_at_confirmation`, `test_writer_committed_before_confirm_lock_is_visible`. Named activity/profile/constraint/settings/base/clock/rule changes reject, while named unrelated/no-op changes succeed. Protected plan/settings remain unchanged on stale. | GREEN |
| AC3 atomicity | Commit `test_two_real_confirm_connections_serialize`, `test_dependency_writer_blocked_until_after_confirm_is_later_event`, `test_each_write_failure_rolls_back`, `test_precommit_response_validation_failure_rolls_back`; Coach transaction failure/binding failure and approve/reject race tests. Real independent SQLite connections and injected faults prove one winner and rollback of checkpoint/settings/receipt/proposal. | GREEN |
| AC4 retry | Commit `test_lost_post_commit_result_retries_same_receipt`, `test_busy_keeps_identity_pending_and_retry_succeeds`, `test_replay_survives_restart_expiry_rules_and_later_plan`, receipt corruption/unknown/origin cases; both browser lost-response scenarios and historical replay. Same ID returns one saved result; later plan remains current. | GREEN |
| AC5 UI | `tests/e2e/test_planning_build_confirmation_ui.py`: identity-only submit/no profile PUT, distance/late response, explicit stale return, locked uncertainty, authoritative terminal response, same-ID retry, Cancel without active writes, keyboard and viewport cases. Input handlers invalidate generations before confirm; unresolved attempts retain identity. | GREEN |
| AC6 compatibility | HTTP raw-save/strict-request tests for first/existing plans; complete unchanged calculation/internal-build oracles; Coach bound approval/replay/dedup/legacy rejection; existing planning/Today visibility and other Coach-action suites remain in broad regression. Old raw public writes receive safe 409 instead of bypassing confirmation. | GREEN |
| AC7 introduced storage | `test_planning_build_preview_store.py`: twice-run initialization/reopen, ownership, TTL boundary, bounded cleanup/applied retention, full reset, synthetic Backup API restore; commit `test_expired_successful_receipt_replays_after_restart_and_backup`. No personal database migration or binary downgrade was executed. Rollout/downgrade procedure is below. | GREEN synthetic lifecycle; live rollout separate |
| AC8 evidence/review | Original M1 RED, full checkpoint comparisons, 203 final focused cases, broad M4/local and pinned CI, complete browser checks, contracts, screenshots and bounded independent M1–M4 reviews are recorded. Final native review, current-head CI and explicit human acceptance must be read from the final PR before merge. | Native/current-head/human gates pending at publication |

## Verification ledger

M5 focused command on unchanged M4 product/test tree:

    ./ai_trainer_env/bin/python -m pytest tests/smoke/test_planning_build_confirmation.py tests/smoke/test_planning_build_confirmation_storage.py tests/smoke/test_planning_build_preparation.py tests/smoke/test_planning_build_preview_store.py tests/smoke/test_planning_build_commit.py tests/smoke/test_planning_build_coach_confirmation.py -q --tb=short

Result: **203 passed, 7 warnings in 58.33s**. No skip/xfail or file exclusions.
Warnings are the existing Starlette/httpx deprecation and six synthetic
pandas connection-proxy warnings. M5 contract suite: **70 passed, 1 warning in
8.26s**. Repository Ruff and contract extraction freshness/inventory pass.
Existing M4 web lint/build passed on the same UI tree;
M5 documentation does not alter web code or schemas.

The accepted M4 broad local run at `495d589` was **3366 passed, 14 skipped,
64 deselected in 170.80s**, with no file exclusions. Skips: unavailable local
process/socket capabilities (2), explicit fixture regeneration (10), optional
garth (2). This is previous-stage evidence on the identical product/test tree,
not a second M5 broad local run.

Pinned M4 GitHub CI at `3b88d331039ee45e2954af524015b7d682d9ac39`:

- [Contributor-safe pytest](https://github.com/rbctmz/ai_trainer/actions/runs/39034800826/job/117402354197): **3342 passed, 38 skipped, 64 deselected, 6 warnings in 233.47s**.
- [Complete browser suite](https://github.com/rbctmz/ai_trainer/actions/runs/39034800826/job/117402354387): **40 passed in 226.24s**.
- [Contract job](https://github.com/rbctmz/ai_trainer/actions/runs/39034800826/job/117402354389) and [secret scan](https://github.com/rbctmz/ai_trainer/actions/runs/39034800847/job/117402354175): success.

CI and local counts intentionally differ. The Python CI job does not install
Node dependencies and skips extractor-dependent tests; those run with Node
installed in the separate contract job. CI also lacks local saved pilot/HRV
fixtures; its documented regeneration/optional-dependency skips remain. These
counts do not mean S1 regressions were excluded. Final-PR CI must independently
pass at the published candidate SHA; historical green checks cannot qualify it.

The M4 targeted browser result was **18 passed in 21.91s**. Its six inspected
[synthetic screenshots](design/evidence/issue-685/README.md) cover desktop/mobile,
light/dark, keyboard and unknown-result states. M5's fresh full existing browser
suite completed with **40 passed in 224.41s**, using
`./ai_trainer_env/bin/python -m pytest -m e2e tests/e2e -q --tb=short`.
The rerun's generated screenshots were discarded in favor of the already
inspected M4 captures on the identical UI code. Test
servers use temporary synthetic databases with providers disabled; Coach SSE
is synthetic, while approval uses the real API/store. No model call or real
athlete database is part of this acceptance.

## Review and handoff gates

Independent specification and M1–M4 reviews are recorded in the ExecPlan. Their
closed findings do not substitute for the final native review of the complete
main-to-candidate diff. The final PR starts with zero native rounds; request one
manual `@codex review` only after its code/docs/evidence and CI are stable.
Round 1 covers the complete final diff against AC1–AC8. Any findings must receive
`fixed-in <sha>`, `follow-up #N` or `disputed: <reason>` with reproduction or named
invariant. Only a scoped correction review follows; native budget is two rounds.
Do not request an additional review merely to record later process outcomes.

The authenticated native result must name the current head. Record review and
unresolved-thread counts in the issue/PR; zero local blocking findings or passing
CI is not native acceptance. Do not self-apply human acceptance or exception
labels. The human merge owner accepts review and decides merge after all
current-head checks pass, all blocking threads are closed/triaged, and the
repository merge gate is satisfied. M5 may hand off with only that explicit
human gate remaining; it may not claim merged or deployed.

## Rollout and rollback boundary

Ship API and web from the same accepted revision. Before any live migration,
the human/operator stops all writers and takes a verified SQLite Backup API
snapshot following [the backup/restore runbook](sqlite_backup_restore.md).
Table/index creation is additive and idempotent; no personal-data backfill is
needed. Old tabs/unbound Coach proposals receive `preview_required` and must
refresh/rebuild. Pending previews expire; successful receipts are retained.

Do not roll back to an old API with confirmation writes enabled: it restores
the raw-save bypass. On failure stop confirmation writers, retain preview and
receipt rows, then fix forward or use an explicitly compatible rejection
patch. Restore only under the stopped-writer runbook with its rollback snapshot;
discarded pending previews require rebuilding, not applying unverified JSON.
No old-binary downgrade rehearsal or live deployment is claimed here. Synthetic
reset/restart/backup/restore and legacy-request rejection are the tested boundary.

## Proposed verdict

Functionality and synthetic acceptance evidence satisfy AC1–AC7 within the
listed test boundaries. AC8's final current-head CI/native result and human gate
remain explicit at publication. #677 stays open for S2–S4. Final PR comments
and issue #685 hold subsequent review disposition and the exact gate snapshot;
the evidence document is not a merge authorization.
