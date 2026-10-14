# #528 M1: truthful missing-cache tool message

- Issue: https://github.com/rbctmz/ai_trainer/issues/528
- Author: Codex, Spec Owner → Domain Implementer after bounded spec check.
- Checker: independent read-only checker; merge owner: Greg.
- Date: 2026-10-14; base head: d53d529.

## Change Class

Class B for M1: compatible correction of one existing message and offline regression tests. No paid calls, new boundary, persistence, schema, security or UI changes. Overall ExecPlan retains Class A for deferred M2. Manual review; one spec check and one implementation delta review, no native GitHub review.

## Scope and Non-goals

Change only `_ACTIVITY_STRUCTURE_MESSAGES['not_fetched']` in `models/ai_tools.py` and regressions in `tests/smoke/test_coach_activity_structure_tool.py`. Message says the structure is unavailable and another query is conditional on successfully obtaining data. It must not promise that sync or opening a card will supply intervals.

Preserve unavailable/not_fetched identity, raw result shape, cached-only behavior, existing presenter and runtime. Cached structured, analyzed empty, no-provider-link and corrupt-cache results remain unchanged. No prompts, provider settings, sync, UI, metrics or eval scorer changes. M2 live source comparison is deferred to the separate ExecPlan milestone.

## Definition of Done and Public Contracts

- [x] Actual tool output has truthful conditional guidance.
- [x] Real presenter delivers that limitation to native tool context and synthesis prompt in offline regressions.
- [x] Existing structure and fetch failure checks pass; source lint passes.
- [x] Independent checker disposes findings; this spec is included in the verified local checkpoint.

User-visible message changes compatibly. API/TypeScript/database/configuration/CLI shape unchanged; no extractor or migration required.

## Failure, Reset, Rollback, Idempotency and State Boundaries

Tool reads the existing cache; lack of evidence stays unknown, never analyzed-empty. No new persistent state, checkpoint, retries or writes. Existing activity ID/date and cache provenance remain authoritative. Concurrency/stale-write handling unchanged. Rollback is reverting the text and its regression; no data reset is needed. Existing offline fetch tests cover provider failure with and without cached data.

## Evidence Boundary Matrix

| Activity/cache | Provenance | Expected result / falsifier |
| --- | --- | --- |
| linked/missing | intervals link, no payload | unavailable/not_fetched; conditional guidance, no future guarantee |
| unlinked/missing | no provider link | unavailable/no_provider_link; existing message |
| linked/corrupt | unreadable payload | unavailable/corrupt_cache; existing message |
| linked/analyzed empty | valid empty payload | empty; may state no intervals found |
| linked/structured | valid cached intervals | structured; existing numbers preserved |

## RED Matrix and Delivery Slice

| Invariant | RED or characterization | Expected failure | GREEN evidence |
| --- | --- | --- | --- |
| Missing cache is uncertainty | real tool regression | failed on old unconditional message | passes corrected source |
| Delivery to model | actual formatter/native loop/synthesis prompt | failed on old guarantee in native context | passes; identical message delivered to native and synthesis |
| Compatibility/network boundary | existing structure/fetch failure tests | characterization already green | 104 focused tests pass |

One M1 slice: add failing source/delivery regressions, correct only message, run focused suites and lint, independent read-only delta review, local commit. No push/PR/merge in current authorization.

## ASR / ADR Traceability

ASR-REL-2: missing data remains uncertainty. ADR-0001: shared Python source; ADR-0010: read-only Coach tools. No new architecture boundary.

## Evidence Bundle and Review Findings

Base/reviewed delta: d53d529 plus models/ai_tools.py and tests/smoke/test_coach_activity_structure_tool.py; local checkpoint follows final checks. RED: two new regressions failed on original message,19 deselected. GREEN:104passed across structure tool, activity intervals, runtime eval, compact A/B and shared runtime modules. `ruff check . --no-cache`:passed; `git diff --check`:passed.

Real synthetic SQLite native+synthesis probe (activity syn-run-uncached, fixed date2026-10-14): unavailable/not_fetched preserved, identical logical hash before/after, zero external calls. Existing offline fetch failure and cache-only boundary tests passed. Broad smoke on separate temporary DATABASE_PATH/CHATS_DIR:2951passed,35skipped,1existing Starlette/httpx deprecation warning,173.88s. Skips:22TypeScript-dependent checks (worktree lacks node_modules),10explicit fixture regeneration checks,2pilot/session/process environment checks,1socket check. No web/API contract changes require installing dependencies for this message correction.

Independent checker: bounded spec check found no invariant gaps; implementation delta review found no blockers,21module tests passed, status unchanged before/after. No findings require dispositions. No CI/push/PR/merge performed. No live model quality claim follows from offline delivery checks. M2 must evaluate actual generated answers separately.

## Final Verdict

READY for local M1 checkpoint: zero blocking findings, checks complete. This is not a live Coach-quality verdict or merge approval. Greg owns merge and any future live execution; worktree remains attached for M2.
