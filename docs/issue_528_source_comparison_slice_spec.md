# #528 M2: frozen source-message comparison

- Issue: https://github.com/rbctmz/ai_trainer/issues/528
- Author: Codex, Spec Owner; implementation handoff follows independent spec check.
- Checker: independent read-only agent; merge owner: Greg.
- Date:2026-10-14; base head:80649bc.

## Change Class

Class A: one explicitly authorized paid experiment. Manual review; budget0/2 before execution. No native GitHub review, push, PR or merge. User's «Делай» authorizes the presented4trials/16calls experiment.

## Scope / Non-goals

Add `source-ab` CLI mode and one bounded runner using existing run_trial, recording provider, read-only tools, SQLite backup clones and canonical fixture. New versioned registry/report metadata. Experiment-only old-message substitution, no production change. Files: services/coach_runtime_eval.py, scripts/run_coach_runtime_eval.py, tests/evals/coach/runtime_registry.py, tests/smoke/test_coach_source_ab.py, this spec/ExecPlan and new report directory.

No changes to product prompts/runtime, M1 message, sync, persistence, UI/API/TS, old predicates, baseline/compact reports or budgets. No adaptive tuning/retries after results.

## Frozen Protocol / Definition of Done

- One scenario: missing-actual-structure regression, completed run today−1, linked activity without interval cache. Canonical fixture: coach_coherent_fixture_v2, normalized once, identical logical hash for all clones.
- Exactly2repeats, order before/after then after/before =4trials. Experiment wrapper changes ONLY get_activity_structure.activities[*].message for unavailable/not_fetched. `before` is the exact string preserved in old compact trace; `after` is the actual production result. No global monkeypatch.
- Both variants use identical COMPACT_CONTRACT compact_answer_v1, existing native/synthesis prompts/settings, DeepSeek/deepseek-flash. Execution date2026-10-15, updated with relative fixture anchors after midnight BEFORE any live calls; original spec date2026-10-14. Same restricted tool schemas, no mutation calls.
- Global cap16provider calls,4/trial,12tool executions/trial,1800output tokens/call,45sSDK timeout,0retries. Native calendar guard freezes current timezone/day and stops if it changes. CLI preflight failures retain all4planned trials. Existing baseline24/compact64caps unchanged.
- [x] RED→GREEN offline checks prove message-only delta, delivery in native+synthesis, exposure, AB/BA, same-input/read-only boundaries, denominator/caps/preflight and output no-overwrite.
- [x] Focused/broad tests, lint, independent checker before paid run.
- [ ] Immutable JSON with source-message texts/hashes, fixture hash, model/settings/head/calendar, calls/token totals, raw/formatted traces and every trial including errors.
- [ ] Separate semantic assessment of ALL4answers; local verified checkpoint. Greg owns merge; worktree retained.

## Acceptance and Public Contracts

CLI adds compatible `--experiment source-ab`; fixed2repeats, explicit --live required for real provider. JSON has its own source registry/report version. API/TS/database/config/public production tool contract unchanged; no extractor/migration.

Protocol requires same canonical input, unchanged DB, allowed tools, correct selected target tool and actual variant message in both native tool context and synthesis input. Missing exposure prevents treating source effect as measured. Errors/calendar changes → INCONCLUSIVE, all4rows retained. Word count/≤80words are diagnostics, never truthfulness blockers.

Final source criterion:2/2after answers explicitly acknowledge unavailable structure, invent no intervals and guarantee neither sync nor card opening will yield them. Existing lexical checks are diagnostic; automated pass cannot replace semantic review (known misses such as «материализуются»). Immutable JSON verdict remains pending_manual if execution is valid; human assessment and combined verdict are recorded separately. No significance/causal proof claim from n=2per variant.

## Failure, Reset, Rollback, Idempotency

No persistent product state. Temp canonical DB/trial clones cleaned on exit; output JSON created exclusively, never overwritten. Credentials loaded only for selected AI provider, sanitized from traces; no athlete DB/config/clients. Read-only tool wrapper denies unknown/mutation tools before callable. Exceptions retain type only. Revert runner/CLI changes to remove experiment; production M1 remains. Failed live run is not restarted automatically.

## State Boundaries / Evidence Matrix

| Identity/provenance | Evidence | Expected result / falsifier |
| --- | --- | --- |
| canonical linked run, same day/hash | missing cache | both unavailable/not_fetched; only message differs |
| unrelated/structured/empty/corrupt/no-link | other tool result | never substitute text |
| actual target tool not selected | no message exposure | protocol invalid, no source-effect conclusion |
| provider/preflight/calendar failure | incomplete request/output |4rows retained, finite calls, INCONCLUSIVE |
| model promises future success | lexical or semantic finding | candidate fails truthfulness even if brief |
| >80words, honest answer | complete limitation | length diagnostic, truthfulness may pass |

## RED Matrix / Delivery Slice

| Invariant | RED test | Expected failure | GREEN |
| --- | --- | --- | --- |
| Exactly message-only paired runtime | capturing provider canonical pair | RED missing source runner/interface | GREEN source tests |
| Budget and full denominator | provider failures / reduced cap / CLI preflight | RED missing source interface | GREEN source tests |
| Diagnostic length and semantic boundary | long honest answer / hidden guarantee | RED missing source interface | GREEN pending_manual despite lexical pass |
| No old-output overwrite | CLI exclusive output + existing reports byte comparison | existing invariant characterization | GREEN |

One reviewable implementation slice, independent delta check, commit before finite live run; one subsequent report checkpoint. No push authorized.

## ASR / ADR Traceability

ASR-REL-2: missing evidence remains unknown. ASR-SEC-1: synthetic-only/sanitized traces. ASR-REL-1/3: no mutations. ADR-0001: shared Python runtime; ADR-0010: A0 tools. Trade-off: restricted scenario proves only this bounded behavior, not full Coach quality.

## Evidence Bundle / Review Findings / Final Verdict

Independent spec check: no blockers; handoff to Domain Implementer. RED: new test module could not collect because run_source_comparison interface did not exist. GREEN:112focused tests passed including all8source tests; whole-tree ruff and diff checks passed. Broad smoke:2957passed/35skipped/1existing Starlette warning,190.53s on separate temp DB/chats. Broad collection preceded the final2source boundary tests; both were subsequently covered by112focused checks and checker32tests. Skips are TypeScript dependency, fixture-regeneration, historical pilot/process and socket environment checks; no web/API contract changed.

Independent implementation delta check against80649bc:32passed, lint/diff checks passed; no blockers, no edits, unchanged git status. One spec check and one implementation delta review, no native GitHub review. Old baseline/compact JSON files byte-identical to80649bc; no scoring/report rewrite. Pending immutable live run and semantic assessment. A negative result is retained as evidence rather than tuned away. No human semantic review by Greg claimed; agent semantic assessment will be clearly attributed. READY for the already-authorized finite execution, not a model-quality verdict or merge approval.
