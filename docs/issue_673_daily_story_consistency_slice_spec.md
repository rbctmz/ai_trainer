# Slice spec and independent review: #673

- Issue / PR: https://github.com/rbctmz/ai_trainer/issues/673 / not created
- Author / checker / merge owner: Spec / Architecture Owner → Domain / API Implementer explicit handoff / independent read-only reviewer / human repository owner
- Date: 2026-10-01
- Candidate base: 6d97787f49ce89502bfafed35a6f9f18e1a5e306

## Change Class

Class A: identity/provenance and additive cross-module contract. No migration, new persistent state, live provider calls or layout work. Review trigger manual, 1/2 spec rounds, acceptance SHA pending, exception N/A.

## Scope

Fix multi-parent Today/Coach story and canonical readiness evidence freshness. Files: models/today_decision_story.py, api/today_snapshot.py, api/routers/coach.py, web/lib/types.ts, services/session_projection.py (revision-head read helper only), contract artifact, focused tests and final report. New UI styling/interaction semantics are not assigned to Domain/API.

## Non-goals

Scoring, matching, plan mutation, lifecycle side effects, provider calls, feedback persistence, database changes, #660 resolution, live LLM quality, external athlete pilot. Main checkout and live data untouched. No merge authorization.

## Definition of Done

- [x] Observable criteria: retained completed bike + unobserved run and no false gap; brick stays one parent; fresh measurements have consistent label; ambiguity/stale/injury stay review-only.
- [x] Named checks: test_daily_story_consistency, Today/Coach/projector regressions, contributor-safe pytest, Ruff, contract extraction/inventory, lint/build, six real API/browser scenarios 390/978/1280 light/dark, independent reviewer.
- [x] Merge owner human; integrator stops its temporary servers and preserves needed evidence/worktree.

## Public Contracts

Today and Coach changed compatibly: optional decision_story.fact.sessions contains canonical TodayDecisionSessionFact[] for multiple independent parents; existing single/brick/no-plan fields retained. Multi-parent top session_id null, summary unknown cause/deviation rather than guessed cause. Top actual IDs/load describe attributed independent evidence only; per-parent DTOs carry unknown amounts. TypeScript optional sessions and extractor artifact updated. SQLite, events, config, CLI unchanged. Existing UI needs no layout or calculation change.

## Failure, Reset, Rollback, Idempotency

Projection errors/mixed checkpoint produce review action but preserve successful parents. Ambiguous parents demand confirmation. Duplicate/malformed identity or overlapping attribution fails closed without duplicate load. No new persistent state: reset/age-out N/A. Restart re-reads sources; retry same input is deterministic. Revert source/contract changes to rollback, no migration or data rewrite. No-write probes cover read adapter; pre-existing Today lifecycle not claimed pure.

## State Boundaries and Identity

Saved plan checkpoint owns ordered parent IDs; iter_parent_sessions excludes day bucket and brick legs. One reconciliation snapshot owns all parents' plan/fact. Expected checkpoint mismatch stays data_gap, never guessed relinking. Readiness owns anchor/confirmed buckets/blocked reasons; composer never rescales or grants clearance.

## Evidence Boundary Matrix

| Identity | Time/provenance | Evidence state | Fallback | Expected result / falsifier |
| --- | --- | --- | --- | --- |
| single | same checkpoint/today | matched | existing | exact known fact retained |
| two independent | one snapshot/today | bike matched + run unobserved | ordered parents | no calendar lookup; both canonical DTOs retained |
| brick | one parent/today | bike only confirmed | partial | no invented run/transition |
| multiple | same snapshot | ambiguous or one projection failure | retain successful facts | confirmation/review, no duplicate totals |
| multiple | changed checkpoint | present | fail closed | no mixed-version summary |
| recovery | current anchor/primary measured | fresh | current | canonical summary recognized |
| recovery | old/unknown/future anchor or blocked | provisional/data_gap/stale | stale/unknown | never current from TSB alone |
| injury | current specific injury value | conflicting | review-only | no clearance/plan write |
| rest/no-plan | no parents | missing session | existing | no fabricated session |

## RED Matrix

| Criterion | RED test/probe | Expected failure | GREEN |
| --- | --- | --- | --- |
| two-parent facts | persisted checkpoint + real Today/Coach adapter | false data_gap / no sessions | 85 focused passed + seven real API variants |
| fresh readiness | actual build_readiness_snapshot DTO | unknown instead of current | 85 focused passed + seven real API variants |
| failed parent retains other | real adapter, one projection error | absent multi-parent representation | 85 focused passed + seven real API variants |
| ambiguity, brick, stale, no-write | fixture/API regressions | existing characterization plus new boundaries | 85 focused passed + seven real API variants |

## ASR / ADR Traceability

ASR-REL-1 canonical identity/revision; ASR-REL-2 incomplete/conflicting evidence preserves facts and fails closed; ASR-PERF-2 bounded local reads; ASR-MOD-2 Python owns meaning; ASR-MOD-3 additive TS/API compatibility. ADR-0001 web-primary, shared Python. Trade-off: summary for several parents is explicit and per-parent evidence preserved, rather than silently picking the first. No new architecture boundary beyond existing story adapter.

## Delivery Slices

1. Spec and real RED scenarios; independent read-back before implementation.
2. Shared multi-parent assembly/composition plus canonical freshness; focused GREEN and artifact extraction.
3. Full required checks and real six-scenario repeat; independent code review with explicit findings dispositions; final report and unmerged reviewable branch.

## Evidence Bundle

Base above; head pending. 85 focused and 2973 contributor-safe tests passed; required code/web/contract checks green; seven API variants and 67 browser states passed; independent scoped delta has no unresolved blockers. Current-commit evidence read-back and durable report pending. Residual: live LLM and athlete pilot deliberately excluded.

## Review Findings

| Severity | Evidence/falsifier | Gate | Disposition |
| --- | --- | --- | --- |
| Audit P2 F1 | actual two-session day fails; ID-only change resolves | acceptance #673 | fixed in current candidate; final commit SHA recorded in report |
| Audit P2 F2 | fresh canonical → unknown; state-only falsifier | acceptance #673 | fixed in current candidate; final commit SHA recorded in report |

## Native Review Rounds

0 native PR rounds; no automated review request. Independent spec/code review records follow below, at most two consolidated rounds; subsequent review is scoped delta.

## Final Verdict

SOURCE/RUNTIME ACCEPTANCE PASSED; independent scoped delta cleared G1/G2/S1. Final current-commit evidence record pending. No native approval or merge claim.

Domain/API handoff 2026-10-01: independent specification round 1 established no blockers. RED: 7 failed, 9 passed; real Today multi-parent action and canonical fresh readiness failed. Implementer now owns the approved Python/API/type slice; no CSS/layout or domain policy change. Scalar reducer: all complete→complete, all unobserved→not_observed, mixed observed/unobserved→incomplete; gap→review, ambiguity→confirmation. Summary projection state prioritizes gap/ambiguity then matched/unmatched/mixed partial. Attributed IDs are ordered union; any unknown load/overlap gives null total; legs/transition remain per-parent only. One session evidence row per parent, one recovery and one injury row.

Review dispositions 2026-10-01: G1 P2 reproduced same-checkpoint A→B confirmation after reconciliation. Bounded revision-head capture/fence added within existing source assembly; inherited match and feedback heads are captured by their service owner, supplied only in private in-process snapshot metadata, never API fields. Affected parent fails closed, unaffected facts remain. G2 P2 malformed/missing identities and mixed revisions now request review with unknown total. P3 malformed readiness bucket reproducibly threw TypeError; now unknown. No persistence or matching changes. Services/session_projection.py is included only for the revision-head read helper. Focused review delta and final acceptance pending.
