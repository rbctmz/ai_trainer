# Independent scoped delta review: G1 / G2 / S1

Date: 2026-10-01. Branch `codex/daily-loop-consistency-20261001`; base/HEAD `6d97787f49ce89502bfafed35a6f9f18e1a5e306`, candidate uncommitted. Read-only reviewer. This is a **scoped verification of the dispositions from code-review round 1**, not another full-diff review or a merge approval.

## Dispositions

| Finding | Disposition | Independent evidence |
| --- | --- | --- |
| G1 P2: old fact / new match revision | **fixed in current candidate delta** | Production confirmation A→B at one unchanged checkpoint now invalidates only the affected bike parent, returns review, and preserves unaffected run's canonical frozen fact/revision. A fresh snapshot gives current B/revision2 correctly. |
| G2 P2: malformed identity / incoherent parent checkpoint | **fixed in current candidate delta** | Six isolated boundary variants now return `inspect_evidence`, `data_gap`, null aggregate actual load, and retain the valid bike fact: absent ID, unhashable ID, mixed checkpoint, malformed checkpoint, malformed actual ID, old parent anchor. No exception in these cases. |
| S1 P3: malformed readiness bucket exception | **accepted and fixed in current candidate delta** | Each of the five buckets independently changed to `[{}]` yields unknown freshness without an exception or false current state. |

No unresolved blocker remains from G1/G2 in the reviewed delta. Commit SHA is pending; the integrator must record `fixed-in <sha>` after committing. Broad tests, final real API/browser evidence and current-commit acceptance remain separate.

## Scoped source assessment

**G1:** new `services.session_projection.session_projection_revision_heads` captures the same effective match lookup (including uniquely inherited replacement ledger provenance) plus current feedback revision. Today captures heads before its existing shared reconciliation read; Coach/read-adapter path captures heads before its own read. The parent adapter compares frozen/current heads before projection and final heads after projection, conservatively turning changed or unreadable parent evidence into an explicit gap. Existing checkpoint guard remains. A raw supplied reconciliation without the internal head fence is conservatively rejected, rather than attaching latest metadata to unverified old facts. This is consistent with the declared snapshot boundary; no matching or persistence semantics were changed by the helper.

**G2:** the reducer now rejects missing/non-string/blank parent IDs, removes malformed actual ID items conservatively, requires coherent positive integer planning checkpoint IDs and same-day evidence anchors, and reuses the existing review/null-total path for malformed/incoherent evidence. Correct parents remain in `fact.sessions`. Duplicate/overlapping attribution remains conservative.

**S1:** freshness bucket shape/item validation precedes set operations; canonical string buckets still participate in the existing primary-measurement logic. Malformed buckets produce unknown, while stale anchors remain stale. No scoring or medical-clearance policy change.

## Verification

Approved guarded focused command: **85 passed in 3.68s**.

```text
/Users/gregkisel/Developer/ai_trainer/ai_trainer_env/bin/python /private/tmp/ai-trainer-daily-fix-20261001/run.py pytest -m 'not live and not debug and not e2e' tests/smoke/test_daily_story_consistency.py tests/smoke/test_today_decision_story.py tests/smoke/test_coach_fresh_context.py tests/smoke/test_api_today.py --basetemp=/private/tmp/ai-trainer-daily-fix-20261001/runtime/reviewer-delta -q
```

Independent production/temp-DB and pure-boundary probe:

```text
/Users/gregkisel/Developer/ai_trainer/ai_trainer_env/bin/python /private/tmp/ai-trainer-daily-fix-20261001/run.py python /private/tmp/ai-trainer-daily-fix-20261001/reviewer_delta_probe.py
```

Exact saved output: `/private/tmp/ai-trainer-daily-fix-20261001/evidence/reviewer-delta.json`.

The probe records real production confirmation A→B between frozen snapshot capture and composition. The run may legitimately be `needs_confirmation` due to the unmatched other bike candidate; verification compares its retained completion/actual IDs/revision to the actual frozen canonical projection rather than imposing `not_observed`. This avoids confusing conservative matching behavior with the provenance defect. Fresh-snapshot falsifier, all six G2 negative cases, and all five S1 malformed-bucket cases passed. Tracked table snapshots before/after adapter calls match. Production confirmation writes occurred explicitly before the read-adapter check and only in the guarded temporary database.

## Boundaries and source state

Only G1/G2/S1 implementation/test deltas and necessary neighboring source were reread. No full-diff rescan, broad review, external requests, provider/model generation, personal data, source/doc/Git changes, issues/PR writes, native approval, or merge.

Initial tracked candidate modifications remained `api/routers/coach.py`, `api/today_snapshot.py`, `models/today_decision_story.py`, `services/session_projection.py`, contract artifact, readiness fixture test, and TypeScript mirror; untracked spec/ExecPlan/daily consistency tests. The reviewer did not alter them. Final HEAD remains the stated base because the integrator has not committed yet.

Limits: no claim of snapshot isolation transaction for arbitrary later concurrent writes; the verified contract is conservative detection around the captured evidence/read boundary. Final browser, contributor suite, performance and artifact checks are pending scoped evidence read-back. Live LLM, athlete pilot and spoken screen-reader acceptance remain excluded.
