# Exact manual activity link: slice spec and review (#720)

Issue: https://github.com/rbctmz/ai_trainer/issues/720. Author/integrator: Codex; checker: independent identity_checker; merge owner: human owner. Date: 2026-10-24. Base: ae557d4. Candidate/acceptance SHA pending.

## Change Class

Class A: additive persisted identity override, deduplication and live-ingest reader semantics. Review trigger: manual. Design round 1 completed read-only; native PR review rounds 0. No review acceptance or exception claimed.

## Scope and Non-goals

Operator CLI confirms one original standalone Intervals id and one Garmin id, with original Intervals survivor. Default preview, explicit token-gated apply and unlink. No automatic matching, UI, HTTP/TS changes, provider writes, live repair, or authored-ledger migration. Implementation files: data/activity_manual_links.py, data/database.py, data/activity_store.py, services/activity_manual_links.py, scripts/link_activities.py, tests/smoke/test_manual_activity_links.py and linked docs.

## Definition of Done

- [ ] Observable acceptance and synthetic RED→GREEN recorded.
- [ ] Focused/broad tests, copied-data rehearsal and independent final review recorded.
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
| preview/apply/replay | new manual-link smoke suite | service absent | pending |
| restart/unlink/reset | same suite | service absent | pending |
| stale/refs/rollback | same suite | service absent | pending |
| ordinary behavior | existing ingest/schema suites | already green baseline | 47 passed |

## ASR / ADR Traceability

ASR-REL-3 atomic ingest and ASR-MOD-3 additive schema; ADR-0008 retains ordinary fail-closed matching and receives a narrow explicit-operator exception. Trade-off: no guessing or broad migration; unsupported references require separate work.

## Delivery Slices

One behavior slice: exact-pair state, ingest replay and operator rollback; tests and docs travel with it. No web verification needed because web and contracts are untouched.

## Evidence Bundle

Base ae557d4. Focused baseline 47 passed. New RED, GREEN, broad tests, rehearsal, candidate SHA, CI and final checker pending. No live data changes.

## Review Findings

Design checker identified deterministic same-provider selection, authored-reference guards, derived cache cleanup, raw read-only preview, ambiguity, current-fact unlink and reset. All accepted as constraints; implementation evidence pending. This is one consolidated design review, followed by a scoped verification round.

## Native Review Rounds

0. No native review triggered. Human merge owner retains the normal native gate and two-round cap.

## Final Verdict

BLOCK: implementation and validation pending. No merge or live apply approval requested yet.

Duration precision clarification (2026-10-24 review): the one-second allowance is represented as 0.017 minutes, matching the existing three-decimal minute normalization; a two-second source difference is refused.
