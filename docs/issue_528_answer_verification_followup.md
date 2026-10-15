# #528: bounded follow-up for evidence-backed answer verification

Design after M4,2026-10-15; accepted by Greg «Реализуй план». Implemented locally as M5 under [slice spec](issue_528_answer_verification_slice_spec.md), Class A, Spec Owner → Domain Implementer after independent spec check. [Offline evidence](reports/2026-10-15-coach-answer-verification/README.md); no new live run. Previous traces/scores preserved.

## Problem and evidence boundary

Observed: M4 empty answer says «это подтвердит проверка карточки» for a likely unmarked-data hypothesis. The tool provides analyzed-empty state and aggregate numbers, not the cause of empty detection or the result of a future card check. Both semantic assessors flag the promise; existing lexical diagnostics and narrative gate pass it.

Inferred: instructions alone leave this class of unsupported future assurances uncovered. Cheapest falsifier: replay the saved answer through current gate with each actual structure evidence state and inspect the allowlisted bundle. Verified by: M4 trace shows pass4/4 with identical evidence fingerprint across states; current build_coach_narrative_evidence does not include get_activity_structure. No claim that a generic future-tense regex would solve factuality.

## Proposed bounded implementation

1. Extend existing structured narrative evidence with an allowlist of actual activity identity,date,structure_status,reason,source,analyzed timestamp and recorded interval count/values. Associate claims with the relevant activity, especially for mixed multi-activity responses. Define versioned evidence/reason semantics and review API metadata compatibility before implementation.
2. Add a bounded rule for the observed unsupported assurances: a future sync/card/query/check cannot guarantee available data or confirmation of a hypothesis. Preserve conditional verification that may confirm **or refute** a hypothesis. Detect the saved forms explicitly; this remains a narrow classifier, not complete natural-language factuality.
3. Keep unavailable distinct from analyzed-empty. For empty report what analysis found, rather than assert actual effort was easy/uniform or strengthen it into unsupported circumstances. Source wording should state analyzer observation; examine the existing empty message before attributing the whole failure to synthesis.
4. Reuse existing bounded correction/fallback path. If correction still violates the rule, return an athlete-facing statement of known facts/unknowns and an optional check, without claiming what that check will find. Preserve supported aggregate/interval facts where practical.

No new agents/integrations/UI or mutations, no wholesale planner/readiness classifier changes. The general hypothesis instruction's wording «проверка ... подтвердит» should be examined as another possible misleading input, not silently changed during this finished experiment.

## Acceptance and falsifying tests before any implementation

- Saved empty answer: future confirmation guarantee rejected; replacement does not repeat the guarantee. «Проверка может подтвердить или опровергнуть» remains allowed.
- Saved pre-M3 repeat-query guarantee rejected when cache unavailable; explicit successful-cache condition allowed, actual structured intervals retained.
- Analyzed-empty states permit «анализ не нашёл», no invented cause/effort. Missing data never becomes actual absence.
- Mixed activities/dates: unavailable activity does not invalidate supported structured intervals for another; unknown identity does not borrow another activity's evidence.
- Marker/native/API/legacy consumers retain shared policy; correction exhausted/error paths preserve safe facts and perform zero writes. No new paid retry budget inside output delivery.
- Rule/evidence version, public metadata compatibility, focused/broad tests and independent checker are specified in a future slice spec. An exhaustive guarantee against all paraphrases is explicitly out of scope.

## Stop rule / status

M5 implements the bounded scope above; independent consolidated review and scoped repairs completed.286focused passed,30saved outputs replayed without a provider; all4initial counterexamples blocked,3supported M4answers unchanged. Internal evidence/rulesv3; public metadata shape unchanged. No new paid-run budget; M4 is not rerun or tuned. Main and athlete state remain untouched; live quality and human merge approval remain separate.
