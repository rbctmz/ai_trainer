# #528 M3: explicit cached-structure conditions in model context

- Date:2026-10-15; base:9e4d717; issue:https://github.com/rbctmz/ai_trainer/issues/528.
- Roles: Spec Owner → Domain Implementer after bounded spec check; independent read-only checker; merge owner Greg.
- Class B: compatible model instruction correction in existing shared runtime, no new boundary, state, paid calls or schema. Manual review, one spec check/one implementation delta budget. User «Закрепляй условия» authorizes this slice.

## Scope / Non-goals

Add one shared cognitive instruction covering cached factual activity structure, consumed by marker/native selection, synthesis and the existing correction path. `models/ai_coach_runtime.py` and focused runtime/tool tests. No changes to source message, product validator/evidence versions, sync, UI/API/TS, provider settings, budgets, eval scorer or immutable reports. Prompts change intentionally in this NEW slice, not retroactively in the completed frozen source A/B.

This slice makes the conditions explicit in model instructions. Offline checks prove context delivery; they do not prove the model always obeys or introduce a deterministic output blocker. No new paid experiment is part of M3.

## Observable Acceptance / Public Contracts

1. When get_activity_structure returns unavailable, instruct the model to start «Структура недоступна», never turn missing data into «Отрезков нет»/«отрезков не было».
2. Existence at Intervals.icu, sync, card opening or simply repeating a query does not establish successful local-cache retrieval. Do not promise «повторите запрос — тогда назову отрезки». State the condition: only after successful retrieval into cache AND confirmation by a new tool result can the model name actual intervals.
3. Actual structured intervals remain usable, and analyzed-empty is allowed to mean no intervals found. Scope is factual get_activity_structure, not planned structure/rest or generic coaching promises.
4. These exact conditions reach marker/native context, first synthesis and existing correction synthesis, including when a compact response contract is present. Real AITools/presenter preserve unavailable/empty/structured semantics and cache-only behavior.

Prompt instruction is a compatible model-facing change; API/TS/DB/CLI contracts unchanged, no extractor or migration.

## RED Matrix / Checks

| Invariant | RED / characterization | Expected failure / GREEN |
| --- | --- | --- |
| Conditional cache retrieval, no repeated-query guarantee | captured actual native+synthesis requests over real synthetic missing-cache tool | new instruction absent before change; present after |
| All prompt paths share conditions | marker/native/synthesis contract checks | explicit condition absent before change |
| Correction preserves condition | actual synthesize/revalidate request capture | explicit condition absent before change |
| unavailable differs from empty/structured | existing actual tool/cache network-denial tests | existing green characterization remains green |

Focused: tests/smoke/test_ai_coach_runtime.py, test_coach_activity_structure_tool.py, test_activity_intervals.py, test_coach_runtime_eval.py, test_coach_compact_ab.py, test_coach_source_ab.py. Whole-tree ruff and isolated smoke. Bounded independent spec/checker before local checkpoint. No push/PR/merge.

## State / Failure / Reset / Rollback

No persistent state, cursors, provider fetches or retries added. Existing tool ID/date/cache are authoritative; unknown remains unknown, empty requires analyzed data. Existing validator/correction behavior unchanged; no promise of exhaustive output filtering. Revert the instruction/tests for rollback; no data cleanup needed. Temp test databases/clones are removed; immutable historical reports remain byte-identical.

## Evidence / Traceability / Verdict

Observed: saved source-ab after1 drops successful-cache condition; after2 opens with ambiguous absence then explains missing cache. Inferred: making this missing condition explicit in all model contexts may reduce such paraphrases. Cheapest falsifier: capture actual requests through real shared runtime and tool/presenter; live behavioral improvement remains NOT YET. Verified by: RED5tests fail on missing condition before implementation; GREEN117focused tests pass after shared instruction. Both native/marker real synthetic SQLite turns preserve DB, unavailable/not_fetched identity and deliver condition to selection/synthesis/correction, including compact suffix. Marker selection embeds system instructions in plain prompt; test captures this existing transport rather than changing it.

ASR-REL-2 (unknown evidence), ADR-0001 (shared Python), ADR-0010 (A0 tools). Independent spec check found no blockers and authorized handoff; whole-tree lint/diff green. Independent implementation checker:59passed, lint/diff passed, no blockers, status unchanged before/after. One spec and one implementation delta check, no native GitHub review.

Broad smoke on isolated temp DATABASE_PATH/CHATS_DIR:2964passed,35skipped,1existing Starlette/httpx deprecation warning,208.00s. Skips:22TypeScript-dependent checks (worktree lacks node_modules),10explicit fixture regeneration,2historical pilot/process checks,1socket environment check. No web/API contracts changed. All3historical live JSON files byte-identical to9e4d717. Final state: READY for local checkpoint, zero blockers, paid calls0; merge remains Greg's gate. No new architecture boundary or exhaustive factuality checker; model behavior after this prompt change remains unmeasured.
