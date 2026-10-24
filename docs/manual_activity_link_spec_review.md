# Exact manual activity link: slice spec and review (#720)

Issue: https://github.com/rbctmz/ai_trainer/issues/720. Author/integrator: Codex; checker: independent identity_checker; merge owner: human owner. Date: 2026-10-24. Base: ae557d4. Reviewed implementation SHA: 064d1689a9336699d08a9543361da26510cdc88d. PR: https://github.com/rbctmz/ai_trainer/pull/721. Native acceptance remains the human merge-owner gate.

## Change Class

Class A: additive persisted identity override, deduplication and live-ingest reader semantics. Review trigger: manual. Design round 1 completed read-only; native PR review rounds 0. No review acceptance or exception claimed.

## Scope and Non-goals

Operator CLI confirms one original standalone Intervals id and one Garmin id, with original Intervals survivor. Default preview, explicit token-gated apply and unlink. No automatic matching, UI, HTTP/TS changes, provider writes, live repair, or authored-ledger migration. Implementation files: data/activity_manual_links.py, data/database.py, data/activity_store.py, services/activity_manual_links.py, scripts/link_activities.py, tests/smoke/test_manual_activity_links.py and linked docs.

## Definition of Done

- [x] Observable acceptance and synthetic RED→GREEN recorded.
- [x] Focused tests, copied-data rehearsal and independent final review recorded.
- [x] Final corrected broad test result: 3992 passed, 39 skipped, 116 deselected; related focused suite 88 passed.
- [x] Human owner retains merge/live-apply authority; task owns isolated worktree cleanup.

## Public Contracts

CLI is new and dry-run by default; explicit write requires expected token, stopped-writer confirmation and a link reason. Database schema adds activity_manual_links with unique exact source ids. HTTP/TS/events/configuration contracts unchanged. Original canonical identity and source payloads remain stable.

## Failure, Reset, Rollback, Idempotency

Reject missing identities, unsupported groups, incompatible ride metadata, stale token, competing manual decisions and authored references on disappearing canonicals. Preserve target references; clear rebuildable disappearing caches atomically. BEGIN IMMEDIATE covers revalidation, association and projections. Token covers selected source payloads, identities, decision and blockers. Unique pair makes repeat apply safe. Unlink uses current provider facts, not old row snapshots. Override owner is the database; lifetime ends on unlink or full reset. Reset clears overrides transactionally. Offline backup/restore is the operational fallback.

## State Boundaries and Identity

Source facts remain in activity_provider_links. A manual decision asserts equivalence, never rewrites source/external ids. Original standalone Intervals id determines the survivor and preferred Intervals enrichment source. A single Garmin-returned Intervals claimant follows the same exact coordinate. Two or more claimants abort instead of broadening the manual confirmation. Provider ingest re-applies the exact decision before projection; sync cursor ownership is unchanged.

## Evidence Boundary Matrix

| Identity | Time/provenance | Evidence | Fallback | Expected result |
| --- | --- | --- | --- | --- |
| original + Garmin | exact UTC start, compatible cycling/duration | two preserved payloads | none | one selected canonical after confirmation |
| no manual decision | any | existing exact coordinate | existing | previous behavior unchanged |
| stale preview / changed identity | changed | token mismatch | refuse | no partial writes |
| extra claimant | exact Garmin coordinate | one / multiple | fail closed | selected original / abort multiple |
| disappearing authored refs | any | present | refuse | history preserved |
| disappearing derived caches | any | present | rebuildable | clear atomically, refetch later |

## RED Matrix

| Contract | Probe | Expected RED | GREEN |
| --- | --- | --- | --- |
| preview/apply/replay | new manual-link smoke suite | service absent | 24-test manual suite passed |
| restart/unlink/reset | same suite | service absent | 24-test manual suite passed |
| stale/refs/rollback | same suite | service absent | 24-test manual suite passed |
| ordinary behavior | existing ingest/schema suites | already green baseline | 47 passed |

## ASR / ADR Traceability

ASR-REL-3 atomic ingest and ASR-MOD-3 additive schema; ADR-0008 retains ordinary fail-closed matching and receives a narrow explicit-operator exception. Trade-off: no guessing or broad migration; unsupported references require separate work.

## Delivery Slices

One behavior slice: exact-pair state, ingest replay and operator rollback; tests and docs travel with it. No web verification needed because web and contracts are untouched.

## Evidence Bundle

Base ae557d4. Focused baseline 47 passed. New suite: initial RED missing service, GREEN 24 passed. One-second boundary RED 2 failed / 2 passed, fixed-in 064d168 and verified 4 passed; complete manual suite 24 passed. Final related focused suite: 88 passed, including all four duration boundary cases. Global ruff and diff whitespace check passed. Copy-only link/replay/unlink/relink, integrity and orphan probes passed. Final corrected broad run: 3992 passed, 39 skipped, 116 deselected in 239.19s. No live data changes. CI started on PR #721; native Review gate correctly refuses acceptance until the current-head native review is submitted by the merge owner.

## Review Findings

Design checker identified deterministic same-provider selection, authored-reference guards, derived cache cleanup, raw read-only preview, ambiguity, current-fact unlink and reset. All accepted and covered. Consolidated implementation review found one blocking P2: existing minute normalization rejected an exact one-second source difference. Parent reproduced it, added acceptance/refusal boundary tests and fixed-in 064d168. Scoped checker verification: 24 passed; zero remaining blockers. One full implementation review plus one scoped fix verification; no second full-diff round was requested.

## Native Review Rounds

0. No native review triggered. Human merge owner retains the normal native gate and two-round cap.

## Final Verdict

READY for human code review: final local broad and focused evidence passed. Published-head CI is tracked on PR #721. Zero open independent-checker blockers. Native review/acceptance, human merge and live apply are pending; no such approval was inferred.

Duration precision clarification (2026-10-24 review): the one-second allowance is represented as 0.017 minutes, matching the existing three-decimal minute normalization; a two-second source difference is refused.
