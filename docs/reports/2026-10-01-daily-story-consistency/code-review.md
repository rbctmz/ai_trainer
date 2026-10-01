# Independent code review #673: consolidated round 1

Date: 2026-10-01. Branch: `codex/daily-loop-consistency-20261001`; base/HEAD `6d97787f49ce89502bfafed35a6f9f18e1a5e306`, candidate changes uncommitted. Role: Independent Reviewer, read-only. Scope is the approved #673 identity/freshness correction, not scoring, matching, medical policy, #660, or UI redesign.

## Verdict

Normal F1/F2 paths are corrected, but **two P2 findings need disposition before acceptance**. Finding G1 reproduces incorrect revision provenance through production temp-DB matching and the new frozen-snapshot adapter. Finding G2 reproduces failures of explicitly specified malformed/mixed parent evidence guards at the new pure-composer entry point. No P1 established. This is the first consolidated full-diff code review; later verification of fixes should be scoped delta, with written dispositions.

## Findings

### G1 — P2: A frozen reconciliation fact is relabelled with a newer match revision on the same checkpoint

Affected new lines: `api/today_snapshot.py:373-388`; underlying existing helper `services/session_projection.py:80-88`, 98-105. Existing Today now supplies its earlier `_yesterday_reconciliation` snapshot to this path.

**Observed:** `_build_parent_story_from_sources` composes rows from the supplied snapshot, but `session_projection_from_reconciliation` rereads the latest effective match revision. Its final guard checks only the planning checkpoint. A new match on the same checkpoint therefore does not invalidate the old fact.

**Verified by:** guarded production temp SQLite probe `reviewer_adversarial.py`: seed two independent sessions, add bike A and bike B, call production `record_plan_actual_match` to confirm A (ledger id/revision 1), capture actual `reconciliation_at(...include_provider=False)`, then production-confirm B (ledger id/revision 2) without changing checkpoint 1. Call the new parent adapter with the captured snapshot. Its bike parent reports A (`issue-529-bike-actual`, 60 TSS), but `evidence_revision.match_revision_id=2`, `match_revision=2`, whose stored match refers to B (`alternate-bike`, 30 TSS). No adapter table changes occurred.

**Cheap falsifier:** omit only the frozen snapshot argument and let the adapter obtain a fresh snapshot from the exact same DB/checkpoint/context. It correctly reports B30TSS/revision2. Thus the error is snapshot/revision mixing, not missing plan, malformed fixture, or a matching-policy disagreement. No actual concurrent process is needed; the probe deterministically reproduces an allowed match update between the two reads.

**Named violated invariant:** #673 slice spec lines 28/36/63: preserve per-parent provenance; one reconciliation snapshot owns all parents' plan/fact; ASR-REL-1 canonical identity/revision. Existing #609 revision identifies the immutable evidence actually used, not merely the latest ledger entry. The underlying helper reread predates this change, but the new shared-snapshot read boundary must not make its declared snapshot coherence false. This does not request new matching behavior.

**Recommendation:** bind effective match provenance to the same captured reconciliation evidence, or detect incompatible later match evidence and return an explicit gap for the affected parent while preserving other successful parents. Do not fix by silently attaching the latest revision to the old actual IDs. Add a regression for production confirmation A→B within one unchanged planning checkpoint.

### G2 — P2: The new multi-parent reducer does not fail closed for missing/malformed parent identity or mixed checkpoint provenance

Affected new lines: `models/today_decision_story.py:229-233`, 264-279. Scope is the new `session_projections` input contract; production route normal inputs are correctly normalized.

**Observed:** the reducer treats only duplicate IDs as an identity problem. A missing parent ID passes, an unhashable ID crashes `set(identities)`, and different checkpoint IDs only make aggregate checkpoint null while retaining the permissive action and numeric total.

**Verified by:** start with two real canonical projections produced by `session_projection_at` on the approved synthetic two-parent fixture (complete bike, unobserved run). In isolated pure-composer variants:

- Change only the second parent `session_id` to `None`: summary still `partial/follow_plan` and includes a parent without identity.
- Change only that ID to `['bad']`: raises `TypeError: unhashable type: 'list'` rather than a stable review story.
- Keep both identities valid but change only the second `evidence_revision.planning_checkpoint_id` from 1 to 2: summary remains `partial/follow_plan` with aggregate checkpoint null; it does not require evidence review.

**Cheap falsifier:** unmodified captured projections produce the expected ordinary mixed complete/unobserved `follow_plan` result. The variants change only the named identity/provenance boundary field, with all observations, loads, action, and readiness unchanged.

**Named violated invariants:** #673 slice spec line 32 explicitly requires duplicate/malformed identity to fail closed; lines 32/46 require mixed checkpoint evidence to produce review/no mixed-version summary. New source currently handles duplicate IDs/overlapping attribution but not these adjacent stated boundaries. This is a reproduced boundary failure, not a claim of currently observed corrupted production database input or a demand to widen the API.

**Recommendation:** validate nonempty string identities and coherent checkpoint provenance before multi-parent reduction; malformed/incoherent evidence must require review with no aggregate known total and retain the valid source parent facts. Add named negative boundary tests. Keep the existing correct single-session path compatible.

## Nonblocking suggestion

**S1 — P3: malformed readiness bucket items can crash the freshness explanation.** With a real canonical readiness DTO, change only `freshness.confirmed_today` to `[{}]`; `primary.issubset(confirmed)` raises `TypeError: unhashable type: 'dict'` (`models/today_decision_story.py:382-389`). The same risk applies to hash-based intersection of malformed contradictory-bucket items. The canonical snapshot currently generates string items, so no real production source path or #673 normal-scenario failure was established. Treat as a robustness suggestion, not another merge gate; filter/validate bucket item types conservatively if adopting it. Preserve unknown rather than granting current freshness on malformed data.

## What passed / checked

- Approved guarded check: **54 passed in 2.23s** across `test_daily_story_consistency.py`, `test_today_decision_story.py`, and `test_coach_fresh_context.py`.
- Today and Coach now derive ordered executable parent IDs from the frozen plan through `iter_parent_sessions`, excluding aggregate calendar IDs and brick legs. Empty explicit IDs retain no-plan/rest behavior; single parent retains legacy shape.
- Unknown parent load produces top null; activity overlap produces review/top null while source details remain; all unobserved parents remain not-observed without manufacturing an incomplete day. Known parent facts survive another parent's failed read.
- Canonical real fresh DTO now yields current only with current anchor and all three primary confirmed recovery inputs, with stale/blocked/provisional/TSB-only negative tests. Current injury and missing/stale injury caveat rules are unchanged.
- Additive TypeScript `TodayDecisionSessionFact` matches the per-parent story fact shape; optional `sessions` does not redefine raw SessionProjection or invent full DTOs for failed reads. Generated extraction includes the new interface and optional reference.
- No second matcher, score recalculation, plan mutation, provider call, new persistence, or UI styling change was introduced. Story read adapter does not invoke the existing Today/recovery lifecycle; existing Coach route initialization still has its earlier lifecycle, as documented.

## Commands and exact artifacts

```text
/Users/gregkisel/Developer/ai_trainer/ai_trainer_env/bin/python /private/tmp/ai-trainer-daily-fix-20261001/run.py pytest -m 'not live and not debug and not e2e' tests/smoke/test_daily_story_consistency.py tests/smoke/test_today_decision_story.py tests/smoke/test_coach_fresh_context.py --basetemp=/private/tmp/ai-trainer-daily-fix-20261001/runtime/reviewer-code -q
/Users/gregkisel/Developer/ai_trainer/ai_trainer_env/bin/python /private/tmp/ai-trainer-daily-fix-20261001/run.py python /private/tmp/ai-trainer-daily-fix-20261001/reviewer_adversarial.py
```

Exact probe JSON: `/private/tmp/ai-trainer-daily-fix-20261001/evidence/reviewer-adversarial.json`. Probe code is external to source and creates only guarded temporary synthetic databases. The two product lifecycle confirmation writes occur before the read-adapter nonmutation check, explicitly and only in that temporary database.

## Limits / source status

Reviewed entire tracked candidate product/type/test/artifact diff plus the new spec/ExecPlan/RED tests. Broad contributor suite, web checks and final real browser acceptance are integrator work and will receive a separate scoped evidence read-back. No live LLM quality, pilot, medical or screen-reader acceptance was performed.

Initial tracked modifications: `api/routers/coach.py`, `api/today_snapshot.py`, `models/today_decision_story.py`, `tests/contracts/ts_contract.json`, `tests/smoke/test_today_decision_story.py`, `web/lib/types.ts`; untracked spec/ExecPlan and `test_daily_story_consistency.py`. Reviewer did not modify any source, docs, tests, Git refs, issues or PRs. Candidate remains uncommitted and base HEAD unchanged at review completion; subsequent integrator edits must be distinguished from this reviewed snapshot.
