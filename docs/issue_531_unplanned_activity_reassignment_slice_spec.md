# Issue #531 Slice Spec and Review

- Issue / PR: #531 / pending
- Author / checker / merge owner: Codex / independent reviewer pending / repository maintainer
- Date: 2026-09-04
- Candidate head SHA: pending

## Change Class

- Class: A
- Rationale: append-only match identity/provenance semantics and a user-triggered persistent correction change.
- Automatic escalation triggers checked: identity/provenance and persistence semantics.
- Review budget used: 0 / 2 rounds
- Review trigger mode: manual
- Review acceptance head SHA: pending
- Review budget exception: N/A

## Scope

- Behavior that changes: an unplanned activity reserved only by one inactive historical match can be explicitly reassigned to a current same-date session, and `/planning` exposes that explicit correction.
- Files/modules in scope: `api/planning_service.py`, `web/app/planning/page.tsx`, focused smoke/UI contract tests, this spec, and the ExecPlan.

## Non-goals

- Behavior deliberately unchanged: automatic reconciliation heuristics, cross-date rejection, current active match conflicts, actual-role inference, load math, checkpoint contents, provider ingestion, Streamlit.
- Deferred work and owner: automatic multi-hop historical reconstruction or backfill requires a separate issue; grouped stale matches must be reassigned together rather than partially split.

## Definition of Done

- [x] Acceptance criteria are observable.
- [x] Required tests/checks are named.
- [x] Merge and cleanup owner is assigned.

## Public Contracts

- API request/response DTO: unchanged; existing `POST /api/planning/reconciliation/matches` is reused.
- TypeScript DTO: unchanged; existing `ReconResponse` fields are sufficient.
- Database schema: unchanged; one append-only ordinary match revision is added per successful correction.
- User-visible web contract: changed compatibly by adding “Сопоставить” to eligible unplanned activities and a no-target explanation otherwise.
- Configuration, CLI, provider, Streamlit: unchanged.

## Failure, Reset, Rollback, Idempotency

- Failure modes and safe result: active owner, partial grouped move, multiple inactive owners, cross-date activity, missing activity, missing current session, or stale checkpoint fails closed without a row.
- Retry/idempotency key and duplicate behavior: existing payload fingerprint and target revision behavior; identical retry resolves to the existing row.
- Rollback procedure and proof: revert scoped commits; no migration or data rewrite is required.
- [x] Does this add **new persistent state**? No new state kind; it appends an existing match row only after explicit confirmation.
- [x] Does **full reset** remove every row/artifact/cursor introduced here? Existing full database reset already removes match rows; no new artifact.
- [ ] Restart and partial-failure recovery are covered by the temporary-DB retry and failure probes.

## State Boundaries and Identity

- Source of truth and owner: the active checkpoint owns current parent-session ids; the match ledger owns immutable user evidence.
- Stable identity/provenance keys: current `session:<session_id>`, stale row primary id, and `supersedes_match_id`.
- Cursor/checkpoint lifecycle: request must name the latest checkpoint; history is never rewritten.
- Concurrency and stale-write behavior: existing checkpoint mismatch remains 409; match conflicts are re-evaluated immediately before append under the current service contract.

## Evidence Boundary Matrix

| Identity | Time/provenance | Evidence state | Fallback | Expected result / falsifier |
| --- | --- | --- | --- | --- |
| inactive historical target | same date, current checkpoint | one explicit matched owner, complete group selected | explicit reassignment allowed | current row supersedes stale row |
| active other target | same date | explicit matched owner | fail closed | existing conflict preserved |
| inactive grouped target | same date | only subset selected | fail closed | no orphaned remainder |
| multiple inactive targets | same date | requested ids span owners | fail closed | no multi-parent lineage invented |
| current target | same date | current row already exists plus stale owner | fail closed | no broken dual history |
| no owner | same date | ordinary unplanned activity | normal confirmation | current row appended |
| any target | different date | activity present | fail closed | existing cross-date error |
| stale checkpoint | any | request base is old | refresh | router returns 409 |

## RED Matrix

| Acceptance criterion / invariant | RED test or probe | Expected failure | GREEN evidence |
| --- | --- | --- | --- |
| inactive reservation can move | production writer on temporary DB | RED: existing `already matched` ValueError | pending |
| effective leaf becomes current | activity lookup after reassignment | RED: blocked before row exists | pending |
| active owner cannot be stolen | active target fixture | already green characterization | must remain green |
| grouped match moves atomically | select subset of two ids | RED: generic conflict instead of bounded group guard | pending guard |
| multiple owners fail closed | two stale rows selected together | RED: generic conflict instead of multi-owner guard | pending guard |
| web exposes exact correction | source-level UI contract | RED: `UnplannedMatchControl` absent | pending |
| no same-date target is explained | source-level UI contract | RED: list is display-only | pending |

## ASR / ADR Traceability

- ASRs affected from `docs/architecture/asr_catalog.md`: ASR-REL-1 and ASR-REL-2.
- ADRs reused or required: ADR-0001 web-first boundary and ADR-0006 append-only planning versions; no new ADR.
- Tactic and trade-off: explicit state resynchronization with bounded stale-owner classification; fail closed rather than infer multi-hop identity.
- New architecture boundary discovered during review: pending.

## Delivery Slices

1. Backend stale-owner reassignment:
   - RED: inactive historical owner rejects explicit current confirmation.
   - GREEN: bounded single-owner complete-group supersession.
   - Refactor/contract refresh: no DTO/schema change.
   - Verification: issue module plus #529, API planning, reconciliation, and database lineage regressions.

2. Web correction flow:
   - RED: no action exists for top-level unplanned activities.
   - GREEN: same-date target and role selector submits the exact activity id.
   - Refactor/contract refresh: contract extractor must remain byte-current.
   - Verification: UI contract test, Next lint/build, and browser acceptance.

## Evidence Bundle

- Head SHA: pending
- Changed invariants: pending
- Focused and broad tests: pending
- CI checks/reruns/flakes: pending
- Lifecycle/probe evidence: initial backup probe and sanitized RED fixture reproduced existing conflict; RED `5 failed, 1 passed`; final temporary fixture pending.
- Changed contracts: user-visible web action only; DTO/schema unchanged.
- Unresolved review-thread count: N/A before PR.
- Residual risks and follow-ups: historical multi-hop identity remains intentionally non-automatic.

## Review Findings

| Severity | Evidence and falsifying check | Gate | Owner/status |
| --- | --- | --- | --- |
| P1 | Explicit same-date correction is blocked by an inactive historical reservation; reproduced on a SQLite backup | backend RED→GREEN plus active-conflict boundary | open / Codex |
| P2 | Top-level unplanned activities have no correction action; verified in `web/app/planning/page.tsx` | web contract and build | open / Codex |

## Native Review Rounds

| Round | Reviewed head SHA | Trigger | Findings disposition | Stop / exception decision |
| ---: | --- | --- | --- | --- |
| 1 | pending | manual | pending | continue / stop |
| 2 | pending | verification | pending | stop / exception rationale |

## Final Verdict

- Verdict: BLOCK until implementation, validation, and review complete
- Blocking findings remaining: backend historical reservation and missing web action
- Review rounds used: 0
- Accepted risk or follow-up issue: none yet
- Merge owner final gate: repository maintainer
- Post-merge sync/branch/worktree/progress cleanup: only after explicit merge decision
