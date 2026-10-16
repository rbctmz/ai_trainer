# Final validation: separate semantic assessment

Date2026-10-15. Assessors: primary Codex agent and independent read-only checker /root/check_compact_ab. All4delivered answers inspected against frozen README and actual raw/formatted tool evidence. This is agent assessment, not human review by Greg. Immutable JSON remains pending_manual and is never edited to reflect these conclusions.

## Decision

**Target behavior observed:missing2/2,cached1/1,empty1/1. Clean final semantic acceptance is NOT established.** Both missing answers acknowledge unknown structure, retain successful-cache condition and avoid the old sync/card/requery guarantee. Cached actual values are correct. Empty is distinguished from missing data, but contains an unsupported promise that checking a card will confirm a hypothesis. Preserve this partial result and separately design evidence-backed answer verification; no paid rerun or prompt tuning.

## All four answers

| Trial | Main state criterion | Fact check / residual | Every-clause conclusion |
| --- | --- | --- | --- |
| missing1,53words | PASS | Explicit structure unavailable;62min/10km/TSS71.1 match source. No invented intervals/actual absence. Query after successful data retrieval is conditional, result expressly not guaranteed. | Supported within frozen task |
| cached1,44words | PASS | Exactly2intervals,660/120s,128/198W; HR118/158,cadence88/94 correct. Displayed1.4km is presenter rounding of raw1.35km;340m is0.34km. Total13min/1.69km/TSS6.7 matches source. No invented third interval or unavailable excuse. | Supported, with documented display rounding |
| empty1,42words | PASS for analyzed-empty control |40min/6km/TSS36, analyzed timestamp and interval_count0 match source; no missing-cache/effort inference. «Сессия прошла без интервалов» broadens the analyzer's finding. A likely unmarked-data hypothesis is labelled «вероятно», but «это подтвердит проверка карточки» guarantees future confirmation without evidence. | NOT fully supported; prevents clean final acceptance |
| missing2,67words | PASS | Explicitly missing cache≠no actual intervals; aggregates match. Listing later is conditional on successful cache retrieval; result not guaranteed. A new confirming tool result is implicit in repeat query, not separately named. | Supported for target behavior; clarity limit recorded |

Primary and independent assessments agree. Automatic4/4 does not mean four fully reliable answers. Future-confirmation concern is semantic and is missed by existing lexical checks and production narrative gate. No new post-run predicate or score is added to the immutable JSON.

## Evidence / falsifier / provenance

**Observed:** missing2/2 no longer repeats the observed successful-requery promise; empty1 says checking will confirm an uncertain hypothesis. **Inferred:** explicit M3 conditions help this bounded missing-data response but do not eliminate unsupported assurances in general. Cheapest falsifier: inspect every clause of all4outputs against actual evidence and verify state/policy/input exposure. **Verified by:** primary and independent semantic passes agree; all4target identities/dates/states and full formatter outputs reach native+synthesis, M3 guardrail reaches every request, all4DB input/output hashes equal canonical hash. This is a small current-version check, not paired A/B or causal/statistical proof of M3.

Run code02687ef89dbb64ae5a7d84601b953025176fd1b2; production conditionsdcc6e66; modeldeepseek-flash; date2026-10-15, native timezoneEurope/Moscow. Exactly one run,12/16calls,3/trial,1tool/trial,0errors,0forbidden tools,0correction calls. SDK usage42214prompt+1072completion=43286tokens; money not calculated. All4answers≤80words, mean51.5words; brevity remains diagnostic.

Canonical hash7e2a47113b24a01d6937cd673a5d80ffcec3f58cb844dd8a1e2a8356cd854918. Shared guardrails hashf924eaf86474db4cb8a4226eea485ae4321e6156fc1f7a06b5102b9db74037f4. Artifact SHA-25644f1043b4f76edb15a4aa772312efdcd0886e03b91e51a4513046595dfad79b5; same as original/private/tmp output and unchanged through independent assessment. Credential absence verified before copying. No athlete DB/external training writes/push/PR/merge/human approval claimed.

Existing narrative gate reports pass4/4 and identical evidence fingerprint for all3structure states. Its current evidence bundle covers other claim domains, not activity structure; it cannot be treated as validation of these claims. This is a bounded coverage observation, not a claim that the existing gate violates its contract.

## Disposition

Residual future-confirmation finding retained, ownerGreg for next-slice prioritization; proposed scope in [answer-verification follow-up](../../issue_528_answer_verification_followup.md). No clean all-claims acceptance, merge approval, general Coach-quality or resolved#528 claim. M4 finite execution and evidence collection complete; broader truthfulness work remains.
