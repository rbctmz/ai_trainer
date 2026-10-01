# Independent specification review: #673, consolidated round 1

Date: 2026-10-01. Role: Independent Reviewer (read-only). Candidate base: `6d97787f49ce89502bfafed35a6f9f18e1a5e306`. Branch: `codex/daily-loop-consistency-20261001`.

Reviewed `docs/issue_673_daily_story_consistency_slice_spec.md` and `docs/issue_673_daily_story_consistency_execplan.md`, plus necessary existing identity/projection/composer/type/UI sources. No runtime tests were run in this specification review. No product code or specification was edited; no external requests, issue/PR writes, review approval, or merge. Initial source status contained only the two untracked spec/ExecPlan files; product diff was empty.

## Verdict

**No specification blocker established. Proceed to RED and bounded Domain/API implementation.** This is a specification read-back, not implementation acceptance or merge authority. Count as first consolidated specification round (1/2); later rechecks of adopted clarifications may be scoped delta.

The documents authorize a proportionate correction of both audit findings, establish the explicit role handoff, and preserve existing safety/domain boundaries. Canonical parent enumeration, single reconciliation snapshot, optional `fact.sessions`, null multi-parent scalar ID, conservative ambiguity/error action, unknown amounts, and same-day primary measured freshness are sufficiently specified for the planned fix. Ordinary, completed, two-parent, partial-brick, ambiguous, stale/conflicting and no-plan outcomes have observable acceptance. Existing Today/Coach lifecycle writes are correctly distinguished from pure/read-adapter behavior.

## Evidence-bound assessment

- **Identity:** verified source `models/plan_actual_reconciliation.py:112-137` enumerates ordered independent executable parents and excludes aggregate calendar ID/brick legs. This directly resolves audit F1 without a second matcher or guessed first parent. Optional full `SessionProjection[]` preserves parent plan/fact/revisions; scalar `session_id=null` avoids pretending a day is a session.
- **Checkpoint consistency:** spec lines 32/36/46 and ExecPlan lines 36/69 require one reconciliation snapshot and reject mismatched expected checkpoint. Do not implement this by calling `session_projection_at` once per parent: existing `services/session_projection.py:65-72` starts a fresh reconciliation for every call. Using `session_projection_from_reconciliation` is appropriate for common plan/fact, while its separate revision reads require attention below.
- **Load/unknown facts:** spec line 28 and ExecPlan line 36 explicitly exclude candidate/repeated day-total summation and require unknown amounts to remain explicit; overlaps/duplicate IDs fail closed. That preserves the established #609 disjoint-parent and missing-fact invariant.
- **Readiness:** canonical source defines `fresh` only with all primary recovery inputs confirmed (`services/readiness_snapshot.py:175-180`, 201-221; `models/readiness.py:63`). The proposal recognizes that aggregate contract with valid current anchor, measured primary recovery, and no blocked/provisional/data-gap promotion. This fixes audit F2 without changing scoring or treating TSB as primary recovery measurement.
- **Presentation/scope:** no CSS/layout/interaction work is implied. Existing parent projection cards already distinguish bike/run; existing evidence row renders source-supplied status and freshness. Any needed change in UI interaction semantics remains an explicit UI-specialist handoff.

## Suggestions (nonblocking)

These tighten the recording of already stated behavior; they do not establish additional blockers or widen the product scope.

1. **Document the required scalar summary fields alongside `fact.sessions`.** `TodayDecisionStory.fact` still requires `projection_status`, `completion_status`, `plan`, `evidence_revision`, and top `actual` (`web/lib/types.ts:2021-2043`). The UI can display scalar `complete/incomplete` text (`web/components/today/TodayDecisionStory.tsx:111-123`) and uses evidence `status` labels. Record the intended reducer for all unobserved / mixed complete+unobserved / all complete / ambiguous / unavailable parents, and whether disclosure has one aggregate evidence entry or one entry per parent. This avoids future implementations assigning incompatible scalar meanings while retaining the array. Existing acceptance already requires no false gap/false completion; this suggestion makes it easier to audit.

2. **Pin snapshot provenance in a targeted test.** `session_projection_from_reconciliation` reuses supplied rows but reads latest match revision and latest feedback separately (`services/session_projection.py:80-88`), with replacement lookup also rereading latest checkpoint (`:103-106`). Merely counting one reconciliation call does not prove that revision metadata belongs to its rows. Prefer an assertion that a deliberately changed expected checkpoint yields a gap with no mixed summary, and that each successful parent carries the snapshot-compatible match identity/revision. This is a verification caution about satisfying the existing spec, not a newly proven production race or new requirement to add a transaction mechanism.

3. **Assert unknown-load and freshness boundaries explicitly in RED.** Include an attributed parent's `fact.load_tss=None` alongside a known parent and assert top total remains explicitly unknown rather than silently becoming the known subtotal; unobserved/no-attribution parents must remain zero/not-observed without creating a warning. For freshness include real canonical `fresh` DTO, provisional/blocked/malformed confirmed buckets, old/future anchor, and TSB-only evidence. This operationalizes the spec's stated conditions instead of relying on synthetic factor-state values.

## Required implementation verification, already in scope

RED must reproduce the actual two-parent adapter failure and real canonical `fresh` summary failure. GREEN must preserve single/brick/no-plan compatibility, retained successful-parent facts after another parent error, ambiguity confirmation, disjoint unknown amounts, expected-checkpoint gap, existing injury override/caveat, and adapter nonmutation. API/contract/web/browser checks remain pending. No live LLM, pilot, spoken screen reader or #660 acceptance follows from this review.

## Scoped contract clarification read-back (same round)

The owner clarified and revised the additive array to `TodayDecisionSessionFact[]` rather than raw `SessionProjection[]` (slice spec line 28; ExecPlan lines 36/38/69). Each element is the existing per-parent story `fact` shape, produced from the canonical SessionProjection by the existing pure composer. This accommodates a failed-read data-gap element without pretending it is a complete #609 projection or inventing zero amounts. Successful parent ID, plan, actual, status, deviation/cause, and revision remain preserved; independent parent ordering and null top scalar ID remain unchanged.

Owner also explicitly clarified: top total is null if the entire summable fact is not known; overlapping attribution retains source parent details but yields review/no aggregate total. This matches the recorded unknown/disjoint evidence invariant and is not a narrowing of the user objective. No new specification blocker resulted from the delta. RED implementation started concurrently (new untracked `tests/smoke/test_daily_story_consistency.py`); it was not reviewed or run in this spec-only read-back. Product diff remains unchanged.
