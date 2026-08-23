# Slice Spec And Review Template

Keep this as a separate working spec linked from the task's ExecPlan; do not copy
its checklists or tables into the strict ExecPlan format defined by
`.agent/PLANS.md`. Delete prompts that are not applicable only after writing
`N/A` and the reason.

- Issue / PR: #441 (PR: TBD)
- Author / checker / merge owner: opencode / независимый checker на PR / opencode
- Date: 2026-08-23
- Candidate head SHA: c3d2b6d

## Change Class

- Class: **A**
- Rationale: live-provider write (платные вызовы DeepSeek Responses API), новый cross-module public contract (provider type + адаптер), риск корректности парсинга нового формата ответа.
- Automatic escalation triggers checked: live-provider write — да; data migration — нет; identity/provenance — нет; security — нет; irreversible — нет; новый public contract — да (реестр провайдеров + UI-опция).
- Review budget used: 0 / 2 rounds

## Scope

- Behavior that changes: появляется провайдер `deepseek_responses`, который ходит в Responses API (вместо chat.completions) с тем же контрактом `generate_with_tools → {text, tool_calls}` и той же интеграцией с нативным циклом инструментов коуча. Существующий `deepseek` (chat) не меняется.
- Files/modules in scope:
  - `models/ai_providers.py` (парсер, mixin, провайдер, реестр);
  - `ui/components/ai_coach_provider.py` (опция пикера, 3 строки);
  - `tests/smoke/test_deepseek_responses_provider.py` (новый);
  - `docs/deepseek_responses_execplan.md` + этот файл.

## Non-goals

- Behavior deliberately unchanged: `DeepSeekProvider` и весь chat.completions-путь; рантайм `models/ai_coach_runtime.py`; web/UI; api-контракты; `ts_contract.json`.
- Deferred work and owner: перенос `spikes/002-deepseek-responses-api/README.md` из локального прогона (chore, позже); возможная миграция дефолта на Responses — отдельное решение после полевой проверки.

## Definition of Done

- [x] Acceptance criteria are observable (см. RED Matrix).
- [ ] Required tests/checks are named: `tests/smoke/test_deepseek_responses_provider.py` (new), `tests/smoke/test_coach_native_tools.py` (regression), ruff на затронутых файлах, полный smoke.
- [ ] Merge and cleanup owner is assigned: opencode.

## Public Contracts

- `generate_with_tools(messages, tools, system_prompt) -> {text: str, tool_calls: [{id, name, arguments: dict}]}` — **unchanged** (новый провайдер реализует тот же контракт; закреплён #190).
- `AIProviderFactory.create_provider(provider_type)` — **changed compatibly**: принимает новое значение `'deepseek_responses'`; существующие значения ведут себя как раньше.
- `get_available_providers()` — **changed compatibly**: новый ключ `'DeepSeek (Responses API)'`; старые ключи на месте.
- Streamlit picker options — **changed compatibly**: новая опция; выбранное значение по умолчанию не меняется.
- Env-конфигурация — **unchanged** (переиспользуются `DEEPSEEK_API_KEY`/`DEEPSEEK_MODEL`/`DEEPSEEK_BASE_URL`).
- API/web contract (`web/lib/types.ts`, `ts_contract.json`) — **unchanged** (проверяется `contract:extract -- --check` без регенерации).

## Failure, Reset, Rollback, Idempotency

- Failure modes and safe result: SDK-исключение → `{"text": "Ошибка DeepSeekResponsesProvider: ...", "tool_calls": []}`; клиент не настроен → `{"text": "...: клиент не настроен", "tool_calls": []}`. Рантайм при пустых вызовах уходит в grounding-fallback (#189) — без падения (ASR-REL-2).
- Retry/idempotency key and duplicate behavior: адаптер stateless; повторный вызов просто новый запрос, состояние не меняется.
- Rollback procedure and proof: revert коммита убирает `'deepseek_responses'` из реестра; `test_coach_native_tools.py` + старые smoke подтверждают прежнее поведение `deepseek`.
- [x] Does this add **new persistent state**? No (N/A).
- [x] Does **full reset** remove every row/artifact/cursor introduced here? No rows/cursors создаются (N/A).
- [x] Restart and partial-failure recovery are covered. Да: ошибки локализованы в ответе провайдера.

## State Boundaries and Identity

- Source of truth and owner: формат ответа DeepSeek Responses API (внешний контракт); каноническая нормализация — парсер в `models/ai_providers.py`.
- Stable identity/provenance keys: `call_id` Responses → `id` в нормализованном `tool_calls` (используется рантаймом для `tool_call_id` в tool-сообщениях).
- Cursor/checkpoint lifecycle: N/A (адаптер без состояния).
- Concurrency and stale-write behavior: N/A (каждый вызов независим; общих mutable-состояний нет).

## RED Matrix

| Acceptance criterion / invariant | RED test or probe | Expected failure | GREEN evidence |
| --- | --- | --- | --- |
| Парсер: message-item → text | test_parser_message_item_yields_text | ImportError (функции нет) | text совпадает |
| Парсер: function_call-item → {id: call_id, name, arguments dict} | test_parser_function_call_normalizes | ImportError | id/name/arguments равны |
| Парсер: reasoning-item пропускается | test_parser_skips_reasoning | ImportError | вызовов нет, текст не задвоен |
| Парсер: output_text None на финальном шаге не роняет | test_parser_handles_missing_output_text | ImportError | text из content-частей |
| Трансляция: assistant с tool_calls → assistant-item + function_call-items | test_history_translation_tool_calls | ImportError | элементы с call_id/name/arguments |
| Трансляция: tool-сообщение → function_call_output | test_history_translation_tool_results | ImportError | call_id/type/output корректны |
| Адаптер: вызов идёт в responses.create с instructions/tools/input | test_adapter_calls_responses_create | AttributeError (метода нет) | зафиксированные kwargs |
| Адаптер: результат нормализован в {text, tool_calls} | test_adapter_returns_normalized_result | AttributeError | форма как в #190 |
| Адаптер: ошибка SDK → error-text + [] | test_adapter_error_path_returns_empty_calls | AttributeError | строка «Ошибка» и пустой список |
| Адаптер: клиент None → «не настроен» | test_adapter_client_none_message | AttributeError | сообщение без исключения |
| Реестр: create_provider('deepseek_responses') | test_factory_creates_responses_provider | ValueError (неизвестный провайдер) | инстанс нового класса |
| Capability: supports_native_tools True | test_responses_provider_capability | AssertionError | True |
| Регрессия: старый deepseek не тронут | test_coach_native_tools.py (существующий) | — | зелёный без правок |

## ASR / ADR Traceability

- ASRs affected from `docs/architecture/asr_catalog.md`: **ASR-MOD-1** (новый AI-провайдер без правки основного кода — расширение аддитивно через фабрику и capability-флаги); **ASR-REL-2** (нет данных/сбой провайдера → data gap, а не выдуманная история — ошибка возвращается строкой, вызовы пустые, grounding включается).
- ADRs reused or required: новых ADR не требуется; изменение согласуется с миграционной политикой adr_0001 (продуктовая логика — shared Python).
- Tactic and trade-off: additivity (новый тип вместо флага/подмены) — цена: две живые ветки клиента DeepSeek; выигрыш: нулевой риск для рабочего chat-пути и честный откат.
- New architecture boundary discovered during review: (заполняется после review).

## Delivery Slices

For every slice, keep one reviewable behavior boundary and a clean pushed
checkpoint where the agent workflow requires it.

1. Slice: M1 RED — контрактные тесты адаптера.
   - RED, or characterization baseline for a behavior-preserving refactor: `tests/smoke/test_deepseek_responses_provider.py` падает на отсутствии `DeepSeekResponsesProvider`/парсера.
   - GREEN: —
   - Refactor/contract refresh: —
   - Verification: `python -m pytest tests/smoke/test_deepseek_responses_provider.py -q` → fail по ImportError/AttributeError, остальное зелёное.

2. Slice: M2 GREEN — реализация адаптера.
   - RED: предыдущий срез.
   - GREEN: парсер + `DeepSeekResponsesToolsMixin` + `DeepSeekResponsesProvider` + реестр + пикер.
   - Refactor/contract refresh: `ruff check` затронутых файлов.
   - Verification: focused-сьют зелёный; `tests/smoke/test_coach_native_tools.py` без правок зелёный; полный smoke зелёный.

3. Slice: M3 — verification bundle + PR.
   - RED: N/A.
   - GREEN: N/A.
   - Refactor/contract refresh: `contract:extract -- --check` без изменений; `git diff --check`.
   - Verification: evidence bundle в PR-описании; независимый checker на PR; после merge — строка метрик Class A в `docs/engineering_process_metrics.md`.

## Evidence Bundle

- head SHA: c3d2b6d (ветка feat/issue-441-deepseek-responses).
- Изменённые инварианты: добавлен аддитивный provider type deepseek_responses; существующие инварианты (#190 capability-матрица, контракт {text, tool_calls}, реестр openai/anthropic/deepseek/google/ollama) не меняются.
- Focused: python -m pytest tests/smoke/test_deepseek_responses_provider.py -q — 15 passed.
- Broad: python -m pytest tests/smoke -q — 2003 passed; регрессия test_coach_native_tools.py без правок — зелёная.
- Lint: python -m ruff check (затронутые файлы) — All checks passed.
- CI: после открытия PR (Contributor-safe pytest, web-contract, Web E2E, Gitleaks, link, ready-to-merge).
- Lifecycle/probe: N/A — новый persistent state не добавляется (адаптер stateless); провайдер-слой не имеет курсоров/таблиц.
- Намеренно изменённые контракты: AIProviderFactory.create_provider принимает 'deepseek_responses'; get_available_providers + Streamlit-пикер получили опцию «DeepSeek (Responses API)». api/web контракт и ts_contract.json — без изменений (contract:extract -- --check зелёный).
- Unresolved review-thread count: 0 на момент открытия PR.

## Review Findings

- Покрытие RED-матрицы: все 13 строк — зелёное evidence (focused 15 passed + CI).
- Интеграционные поверхности проверены отдельно: REAL_PROVIDER_TYPES/state (строковый passthrough), отсутствие web-списка провайдеров, рантайм порождает только dict-arguments (ai_coach_runtime.py:418).
- P3 (robustness): _messages_to_responses_input молча заменяет не-dict arguments на {} — недостижимо в текущем рантайме; follow-up не обязателен.
- P3 (cosmetic): instructions=None явным null при пустом system_prompt — принимается API; можно опускать ключ.

## Final Verdict

READY TO MERGE — P0/P1/blocking-P2 не найдено. Оба P3 не блокируют; после merge — запись метрик Class A в docs/engineering_process_metrics.md.
