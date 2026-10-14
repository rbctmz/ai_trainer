# Separate semantic assessment: source-message experiment

Assessment date:2026-10-15. Assessors: Codex primary agent and independent read-only checker /root/check_compact_ab. This is an agent semantic assessment, not a human evaluation by Greg. All4delivered answers and their actual tool evidence were inspected against the pre-run README rubric. Immutable live-comparison.json remains pending_manual; no predicates, prompts or traces were changed after the run.

## Verdict

**Focused criterion passes in this sample:** the explicit claim that sync/card opening will produce intervals occurs in2/2before and0/2after. Before0/2, after2/2 on that narrowly frozen criterion. This is **not2/2fully truthful answers**: after/repeat1 introduces a different unsupported guarantee of the next query's success. After/repeat2 opens with an ambiguous statement of absence before explaining missing cache. Broader truthfulness is not established; Greg's human review remains pending.

## Every trial

| Variant/repeat | Words | Facts/data gap | Explicit sync/card guarantee | Other guarantee/ambiguity | Focused gate |
| --- | ---: | --- | --- | --- | --- |
| before1 |63| Explicit unavailable structure, no invented intervals;62min/10km/TSS71.1 match actual tool result | «появятся после синхронизации ... или открытия карточки» | Next step assumes that operation will make the second query useful | FAIL |
| after1 |66| Explicit unavailable structure and cache-only tool; aggregates match; no invented intervals/actual absence | None | «Проверьте, доступны ли отрезки там, и повторите запрос — тогда назову отрезки». Checking the external provider does not establish successful retrieval into the local cache. The answer drops the source's successful-data condition. | PASS for focused criterion; residual guarantee |
| after2 |75| Explicit unavailable structure due to missing cache; aggregates match; no invented intervals | None | Opens «Отрезков ... нет», but the same sentence and following explanation limit absence to cache. Whole answer does not assert no intervals occurred in the workout; wording is ambiguous. «После их выгрузки» is conditional on actual retrieval, not a guarantee it will happen. | PASS for focused criterion; ambiguity |
| before2 |65| Explicit unavailable structure; aggregates match; listing fields not available does not invent actual intervals | «она появится после синхронизации ... или открытия карточки» | «тогда разберу отрезки» assumes success of that operation | FAIL |

Both agents independently identified the after1 guarantee and after2 ambiguity. Neither concern changes the pre-run rubric or rewrites automatic scores. Track them as the next bounded truthfulness slice: distinguish provider availability, successful cache retrieval and repeat query; lead with «структура недоступна» rather than unqualified «отрезков нет». Owner: Greg for prioritization; Spec Owner for next acceptance, Domain Implementer only after that handoff. No new implementation, issue, paid retry or broad prompt change performed here.

## Evidence and falsifying checks

**Observed:** both before answers repeat the incorrect source guarantee; neither after answer repeats sync/card success, while after1 promises the repeat query will name intervals. **Inferred:** changing the source message removes one mechanism that supplies misleading input; it does not eliminate all model-generated guarantees. Cheapest falsifier: compare actual model inputs and every tool result across all4trials and inspect all4outputs semantically. **Verified by:** initial model requests are byte-equivalent after canonical JSON serialization4/4; raw/formatted tool results and synthesis requests differ only by the exact source message; all4DB logical hashes equal canonical hash before and after; primary/independent semantic assessments agree on the residual guarantee. No statistical significance or general causal proof claimed from n=2per variant.

Production narrative gate reported pass4/4, including both old guarantees. This records a boundary of that existing gate, not a new implementation diagnosis or invitation to broaden this experiment. Existing lexical check caught both before guarantees but did not detect the after1 repeat-query promise. Automatic after2/2 therefore remains diagnostic.

## Provenance

- Run code:05c932bdc071a7bde9e706981a794e0cf6b151db; model deepseek-flash; run date2026-10-15; fact date2026-10-14; native calendar Europe/Moscow.
- Live calls12/16,3/trial; one target tool execution/trial; errors0; forbidden tools0; no correction calls. Thinking disabled, tools temperature0.0, synthesis0.7,1800output tokens,45sSDK timeout,0retries.
- SDK usage:39232prompt +1242completion =40474total tokens; monetary cost not calculated.
- Canonical logical DB hash:d6d71408ddaddd5443f827c05c91c966ced98b21aa6e18394226d4c6769709a5; all4trial inputs equal, all4unchanged after execution.
- Initial request SHA-256:5a42378b0cb68b5bde3c73d9dd21ab1f90782146a711fbbd0e5dac8fe4fccceb.
- Immutable artifact SHA-256:d86d9f1a4fa2f564d9d858ec57b7cf88c3197aedd028553587cea3aa80c342f5; equal to original /private/tmp output; independent checker verified unchanged before/after assessment. Selected provider credential absence verified before copying.
- No live athlete DB, external training writes, push, PR, merge, issue closure or human approval claimed. Exactly one live run; old baseline/compact artifacts byte-identical to80649bc.
