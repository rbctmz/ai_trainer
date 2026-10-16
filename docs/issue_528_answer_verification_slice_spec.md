# #528 M5: bounded evidence-backed activity narrative check

- Date2026-10-15; issue:https://github.com/rbctmz/ai_trainer/issues/528; base:f1b03ce.
- User «Реализуй план» authorizes the follow-up design. Spec Owner → Domain Implementer after independent spec check; independent read-only checker; Greg owns merge.
- Class A: extend internal evidence/claim domain. Manual review, one spec and one implementation delta round, scoped repair verification if needed; no native GitHub review or paid run.

## Scope / Contracts / Non-goals

Add bounded activity evidence extraction, observed unsupported assurance/absence checks and deterministic factual fallback to existing shared narrative gate. Reuse one-shot correction; no new retry/cost budget. Small helper module models/coach_activity_structure_evidence.py is owned by shared Python, used by models/coach_narrative_evidence.py. Source empty message and general hypothesis instruction may change narrowly to observations/checks that may confirm OR refute. Tests cover real raw tool/presenter, saved live answers and shared API/legacy consumers.

Internal evidence adds activity_structures allowlist; evidence/rule versions become v3; new ACTIVITY_STRUCTURE_CLAIM_UNSUPPORTED reason is hard (unsafe claim cannot be delivered unchanged). API/TS metadata fields already open strings/list[str], shape unchanged; verify schema compatibility. No persistence migration/UI/extractor contract change. Existing domains unchanged except versioned fingerprint. Old traces/registry predicates remain immutable; scripted eval tests must account for production correction/fallback, not pretend bad output remains deliverable.

No generic fact checker, exhaustive paraphrase guarantee, new agent/integration, sync, planner/readiness redesign, live calls, push/PR/merge or historical score rewrite.

## Observable Acceptance / State Boundary Matrix

| Evidence/claim | Expected result / falsifier |
| --- | --- |
| Saved M4 empty answer: future card check confirms likely cause | hard replacement; never deliver original assurance |
| Saved pre-M3 missing-cache repeat/sync promise | hard replacement; unknown remains unknown |
| «может подтвердить или опровергнуть», explicit successful-cache condition | allowed, no blanket ban on future/conditional statements |
| Correct structured values / analyzed-empty observation | preserved unchanged |
| unavailable + actual absence; empty + unsupported actual effort/circumstance | recognized bounded forms rejected; missing not empty |
| Mixed activities/date/identity | explicit matching scope; no evidence borrowed across activities/dates; ambiguous assurance fails closed without invalidating unrelated supported facts |
| Malformed/failed raw tool, duplicate conflicting identity | cannot establish structured/empty proof; allowlisted deterministic evidence only |
| Correction still unsafe/empty/error/provider absent | return original safe factual replacement, zero activity/planning writes, no extra retry loop; normal chat persistence unchanged |
| No activity tool evidence, unrelated claims | existing gate behavior preserved; no broad future-tense filter |

Allowlist: actual activity_id/date/sport/status/reason/source/analyzed/count plus numeric aggregates and interval values. Exclude tool messages/activity names/unknown fields/secrets. Normalize/reject malformed identity/status; conflicting rows cannot grant proof. Evidence fingerprint must differ between unavailable/empty/structured and remain deterministic under tool-order permutations. No new state/cursors; existing DB/cache provenance authoritative.

## RED Matrix / Definition of Done

- [x] RED replay original saved answers reproduces current pass; add explicit rejection/positive/mixed/malformed tests before production code.16failed/9passed initially.
- [x] GREEN helper/gate integration, safe fallback retains source facts with activity/date, bounded correction succeeds or safely fails.286focused passed.
- [x] API SSE uses validated delivered text and retains open metadata shape; legacy/shared path characterization and existing domain tests pass.
- [x] Focused + isolated broad tests, lint/diff, independent checker, offline replay all saved answers, historical artifacts byte-identical.3012smoke passed/35skipped/1existing warning,183.36s; replay twice byte-identical.
- [x] Local commit2f9db64 and concise evidence/case update. No claim of live quality improvement without a new authorized live run.

## Failure / Reset / Rollback / ASR

No new persistent state; reset/rollback revert code, no data operation. Preserve supported activity numbers in safe replacement rather than inventing structure; scope dates explicitly. Correction is existing at-most-one call with no new budget, fallback requires no provider. Extraction and rule errors retain existing fail-closed boundary. ASR-REL-2 (unknown≠empty), REL-1/3 (read-only), SEC-1 (allowlist), ADR-0001 (shared runtime), ADR-0010 (A0).

## Evidence / Review / Verdict

Observed at base: saved M4 empty answer and pre-M3 source traces passed gate; evidence omitted activity structure. Inferred: supplying this domain and checking the named forms can block these observed unsupported claims. Cheapest falsifier: offline replay with real saved tool results and positive/mixed controls. Verified by: initial RED16failed/9passed; final focused286passed,smoke3012passed and [replay](reports/2026-10-15-coach-answer-verification/README.md). Independent spec check no blockers; implementation checker found3P2, all fixed with exact regressions; one repair regression fixed, scoped7cases pass, no remaining blockers. New module is a narrow claim-domain helper, not another product path. Local checkpoint2f9db64; merge remains human-owned. Live effect not measured.
