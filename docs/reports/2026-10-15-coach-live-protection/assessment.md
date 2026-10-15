# M6: semantic assessment and protection precision

2026-10-15. Primary agent and independent read-only checker /root/check_compact_ab separately inspected frozen README and all actual raw/formatted evidence, initial/corrective/delivered outputs. Both assessments agree on partial result and two residuals; Greg human approval not claimed. Immutable JSON remains pending_manual. One run on bad70d5,13/16calls,4turns,0runtimeerrors; no paid rerun or policy tuning.

## Primary verdict

Target three-state behavior is present in all4delivered answers, with no observed sync/card/requery guarantee or invented intervals. **Protection is not cleanly accepted:** missing1 initial is already semantically safe but the gate rejects its explicit denial of a guarantee. Correction adds one unnecessary call/2033.52ms. This run exercises a live correction after a false positive, not demonstrated rejection of an actually unsafe model answer. Deterministic fallback is not exercised live.

An empty answer also presents the synthetic activity name as a structure-status label; its actual raw structure_status is empty. Main state explanation is correct, but this wording is not an exact status-field fact. Do not declare all clauses fully supported based on automated4/4. It also exposes fixture terminology; no new product behavior or cause is inferred from this small sample.

## Every answer

| Turn | Initial / gate | Corrective / delivered | Source check and limit |
| --- | --- | --- | --- |
| missing1 | Explicit unavailable;62min/10km/TSS71.1; cannot name unknown intervals, future retrieval not guaranteed. Gate replaced: false positive on «Гарантировать, что после этого отрезки появятся, не могу». | One correction, final pass; facts retained, actual absence explicitly distinguished from missing cache; check may confirm or refute, result unknown. | Supported initial and final for task. Correction unnecessary; final99words vs81initial, implementation terms get_activity_structure/structure_status exposed. No new promise in final. |
| cached1 | Gate pass;2intervals11:00/2:00,128/198W. | No correction, unchanged. | Raw660/120s and128/198W match. Display1.4km rounds raw1.35km in actual presenter;340m=0.34km. No invented interval or unavailable claim. |
| empty1 | Gate pass; analysis did not find intervals,40min/6km/TSS36. Explicitly says this does not establish absence in actual workout. | No correction, unchanged. | Correct analyzed-empty observation and conditional check without guaranteed outcome. Quoted «синтетика, анализ без отрезков» comes from activity name, not status field; raw status=empty. Preserve this clarity/factual-label limit. |
| missing2 | Gate pass; unavailable,62min/10km/TSS71.1, cannot name intervals. | No correction, unchanged. | Successful retrieval condition and explicit uncertainty, no invented intervals/actual absence. No independent current provider fetch claimed; cached-only tool limitation retained. |

Initial model outputs do not contain the original M4 unsupported future confirmation. The only live rejection is unjustified. Initial gate3pass/1replaced and final gate4pass are runtime metadata, not independently labelled model-quality rates. Corrective output is semantically supported for the task; deterministic fallback0. Small sample cannot estimate general false-positive/false-negative rates.

Both assessors: main missing2/2,structured1/1,empty1/1 criteria observed, but strictly fully supported initial3/4 and delivered3/4 because of the empty status/name attribution. Full frozen acceptance is **not met**, not overridden by automated4/4. Initial pass count and semantic supportedness happen to both be3/4, but different rows fail: gate rejects supported missing1 and passes misattributed empty1.

## Reproduction of observed false positive

Use missing1 saved actual raw tool data and date2026-10-15, UTC evidence calendar, no provider. Both the full initial answer and isolated «Гарантировать, что после этого отрезки появятся, не могу.» return replaced/ACTIVITY_STRUCTURE_CLAIM_UNSUPPORTED. Replace only that sentence in the full answer with «Результат заранее неизвестен.» → pass. Control «Нельзя гарантировать, что после этого отрезки появятся.» → pass; genuine «После этого отрезки появятся.» → replaced. Prefix wording «Не могу гарантировать, что после этого отрезки появятся.» is also incorrectly replaced. This is a bounded negation-scope defect, not evidence that all future-claim detection is wrong.

Observed: actual initial rejection and extra call in immutable trace. Inferred: recognized qualifier forms/position fail to represent this explicit negation. Cheapest falsifier: minimal phrase and neutral replacement on same saved evidence. Verified by: local offline probes after run reproduce outcomes above; no changes to classifier/scorer/prompts or retry. Exact source boundary models/coach_activity_structure_evidence.py::_qualified and future-assertion branch.

## Calls, timing and comparison

| Turn | Calls | Correction calls | Correction provider ms | Verification stage ms | Full turn ms |
| --- | ---: | ---: | ---: | ---: | ---: |
| missing1 | 4 | 1 | 2033.52 | 2040.67 | 6476.57 |
| cached1 | 3 | 0 | 0 | 1.10 | 3961.92 |
| empty1 | 3 | 0 | 0 | 2.22 | 4520.92 |
| missing2 | 3 | 0 | 0 | 1.12 | 4176.06 |

Total13calls,1correction,0fallback; verification stage2045.11ms, of which2033.52ms provider and11.59ms other gate/correction overhead. Full turns19135.47ms total. These batch timings are observations, not API/SSE first-token measurements or SLA. Usage44374prompt+1368completion=45742tokens; correction alone1950+214=2164tokens. Monetary cost unknown, not zero.

M4 had12calls/0corrections, full turns16108.22ms,3supported/4 with unsupported empty future confirmation. M6 has no such confirmation guarantee, but adds a false-positive correction and the status/name wording limit. Same4prompts and dates; raw activity fields identical except intentionally changed empty message. Canonical DB hashes differ (M4 7e2a47113b24a01d6937cd673a5d80ffcec3f58cb844dd8a1e2a8356cd854918; M6 88b0ea5eae5831fc6434ba12640b51c52a222106791177f25b7f8f1ecbc5cd3d). No cross-run DB identity or causal performance/quality comparison is claimed. Within M6 all4input/output hashes equal canonical.

## Disposition

Execution/evidence collection complete, semantic result partial. Keep M5 protection and negative evidence; isolate negation false positive as next bounded repair, requiring original guarantee counterexamples to remain blocked and supported negated forms to pass without correction. Keep status/name attribution as separate coverage finding, not a pretext for a general fact checker. No repair/new live attempt inside M6. [Independent notes and next-scope boundaries](review_notes.md). Push/PR/merge and resolved#528 not claimed.
