# Coach: native function calling instead of text [TOOL: ...] markers

This ExecPlan is a living document maintained per `.agent/PLANS.md`. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must stay current. It implements Issue #190.

## Purpose / Big Picture

The AI coach currently asks for data through a fragile text protocol: the model must literally write `[TOOL: name, param=value]` inside its first-pass answer, and the runtime extracts those markers with a regular expression (`models/ai_coach_runtime.py::collect_tool_results`, `_parse_tool_params`). Models routinely forget, escape, or paraphrase the markers — Issue #188 was a fully fabricated briefing born exactly this way. PR #189 added a grounding fallback (a deterministic baseline toolset executed when zero markers appear), but that is a seatbelt, not steering: the model still cannot reliably CHOOSE which tools and parameters it needs.

After this change, providers that support native function calling (the OpenAI-compatible `tools` API used by OpenAI and DeepSeek, and Anthropic tool use) receive real JSON-schema tool definitions and return structured `tool_calls`; the runtime executes them through the existing `AITools.execute_tool` and feeds the results to the existing synthesis pass. The marker path remains fully intact as the fallback for every other provider (Mock, Gemini, Ollama in this version) and the grounding fallback from #189 remains the last line of defense on BOTH paths. A user on DeepSeek — the default production provider, where #188 happened — gets a coach whose tool selection is contractual instead of regex-parsed.

## How to see it working

Before: `python -m pytest tests/smoke/test_coach_native_tools.py -q` fails (schemas, provider contract, and native loop absent). After the core milestones the same command passes; `python -m pytest tests/smoke -q` stays green (marker path and grounding regressions pinned); and a scripted fake-provider run shows: schemas in → structured tool_calls out → executed results → synthesis input identical in shape to the marker path. A live probe against DeepSeek happens only with explicit authorization in M6.

## ASR / risk traceability

- ASR-REL (coach must not fabricate): native tool_calls remove the weakest link (marker emission); grounding fallback (#189) is preserved verbatim for the zero-calls case on both paths.
- ASR-MOD (provider abstraction): the new operation lives on the `AIProvider` base with a capability flag; providers that do not implement it keep working untouched — no call site may branch on provider class names.
- Risk "contract drift between paths": the native loop returns tool-result entries of EXACTLY the same shape as `collect_tool_results` (`tool_name`, `params`, `formatted_result`, `raw_result`, `success`), so synthesis, SSE events, proposal persistence, and decision logging need no changes and cannot diverge.
- Risk "prompt/schema duplication": tool parameter knowledge must live in ONE registry that feeds both the JSON schemas (native) and the human-readable descriptions (marker prompt); a drift test pins the equality.

## Context and Orientation

- `models/ai_tools.py` — `AITools` with ~24 tools: `self.tools` maps name → bound method; `execute_tool(name, **kwargs)` normalizes success/error; `get_available_tools()` returns name → Russian description string (parameters only described informally, e.g. "days=30"); `format_tool_descriptions_for_ai()` renders the marker-path prompt block including the `[TOOL: ...]` usage examples.
- `models/ai_providers.py` — `AIProvider` ABC (`generate_response(prompt, system_prompt)`, `is_available`, `get_model_name`, `test_connection`, `get_available_models`); implementations OpenAIProvider, AnthropicProvider, DeepSeekProvider (OpenAI-compatible client), GoogleGeminiProvider, OllamaProvider, MockAIProvider. All are plain-text in/out today.
- `models/ai_coach_runtime.py` — the turn pipeline: `create_chat_system_prompt_with_tools` (system prompt including marker instructions) → `generate_ai_chat_response` (first pass) → `collect_tool_results` (regex over the answer, executes tools) → zero results ⇒ `build_grounding_tool_results` (#189) → `synthesize_ai_chat_response` (second pass over tool results) → response contract post-processing.
- `api/routers/coach.py` — SSE endpoint: performs the first pass + `collect_tool_results` inline, emits `tool_call` events per result (with `auto: true` when grounding fired), persists proposals from `raw_result.is_proposal`, then streams the synthesis answer token-by-token when the provider supports streaming.
- Existing test surfaces to keep green: `tests/smoke/test_ai_coach_runtime.py`, `test_ai_coaching_real_flow.py`, `test_coach_decisions.py` (scripted providers subclass MockAIProvider), `tests/test_ai_coach.py`, `tests/test_provider_features.py`.

## Design

One tool registry. `models/ai_tools.py` gains `get_tool_schemas()` returning, for every executable tool, a provider-agnostic schema: `{"name": str, "description": str, "parameters": {"type": "object", "properties": {param: {"type": ..., "description": ..., "default"?: ...}}, "required": [...]}}`. This registry is the single source: `get_available_tools()` derives its description strings from the schemas (same text as today), and `format_tool_descriptions_for_ai()` keeps rendering the marker prompt from them. A bijection gate pins schemas ⇄ executable registry (`self.tools`) so a new tool cannot ship half-registered.

Provider contract. `AIProvider` gains `supports_native_tools() -> bool` (base: False) and `generate_with_tools(messages, tools, system_prompt="") -> dict` (base: raises NotImplementedError). The normalized return shape is `{"text": str, "tool_calls": [{"id": str, "name": str, "arguments": dict}]}` — arguments always a parsed dict, never a JSON string. `messages` is an OpenAI-style list of `{"role": "system"|"user"|"assistant"|"tool", ...}` dicts; each adapter translates internally. In this version the capability is True for OpenAIProvider, DeepSeekProvider (one shared OpenAI-compatible adapter: schema → `{"type": "function", "function": {...}}`, tool_calls parsed from `message.tool_calls` with `json.loads(arguments)`, tool results sent back as `{"role": "tool", "tool_call_id", "content"}`), and AnthropicProvider (schema → `input_schema`, tool_use content blocks parsed, results returned as `tool_result` user-content blocks). GoogleGeminiProvider, OllamaProvider, and MockAIProvider stay False and keep the marker path (see Decision Log).

Runtime loop. `models/ai_coach_runtime.py` gains `run_native_tool_loop(provider, ai_tools, user_input, history_messages, tool_result_formatter, *, max_rounds=2)`: build the native system prompt (`create_native_chat_system_prompt` — the same coaching rules as the marker prompt but WITHOUT the `[TOOL: ...]` usage block, because on the native path that syntax is noise that invites marker emission), send messages + schemas, execute every returned tool_call through the shared `_execute_tool_to_result`, append the results as tool messages, and repeat up to `max_rounds`; stop as soon as a round returns no tool_calls. It returns `(final_text, tool_results)` where tool_results entries are byte-shape-identical to the marker path's. A dispatch helper `resolve_turn_tool_results(provider, ...)` chooses the native loop when `provider.supports_native_tools()` and `is_available()`, else the marker first-pass + `collect_tool_results`; the zero-results grounding fallback and everything after (synthesis, SSE, proposals) is shared and untouched.

Router. `api/routers/coach.py` swaps its inline first-pass block for the dispatch helper and adds `"native": bool` to the SSE `tool_call` events; the streaming synthesis, proposal persistence, decision logging, and error handling do not change.

## Milestones

Milestone one pre-registers the contract RED in `tests/smoke/test_coach_native_tools.py` (plus a marker-regression guard file if needed): schema registry bijection and single-sourcing; typed parameters for representative tools; provider capability matrix; normalized `generate_with_tools` contract for the OpenAI-compatible and Anthropic adapters via stubbed SDK clients (no network); the native loop against a scripted fake provider (schemas in, typed execution, bounded rounds, error entries, zero-calls ⇒ empty list for grounding); the native system prompt contains no `[TOOL:` syntax; dispatch chooses native/marker correctly; marker path and grounding behavior pinned unchanged.

Milestone two implements the schema registry in `models/ai_tools.py` and rewires `get_available_tools`/`format_tool_descriptions_for_ai` to derive from it (marker prompt output stays byte-compatible where tests pin it).

Milestone three implements the provider contract: base methods, the shared OpenAI-compatible adapter (OpenAI + DeepSeek), and the Anthropic adapter, each unit-tested with stubbed clients.

Milestone four implements `run_native_tool_loop` + `resolve_turn_tool_results` and the native system prompt; grounding fallback proven on both paths.

Milestone five wires the router: dispatch helper, `native` flag on SSE `tool_call` events, streaming and proposal flows regression-pinned.

Milestone six is validation: full smoke, broad non-live, and — only with explicit authorization — a live DeepSeek probe transcript recorded here; Outcomes & Retrospective.

## Decision Log

- Decision: v1 native scope is OpenAI-compatible (OpenAI, DeepSeek) + Anthropic; Gemini and Ollama stay on the marker path with `supports_native_tools() == False`. Rationale: DeepSeek is the default production provider and the site of #188; the OpenAI-compatible adapter covers two providers at once; Anthropic tool use is stable and well-documented. Gemini's function-declaration SDK shapes and Ollama's per-model tool support are follow-up slices — the capability flag makes widening additive. Date/Author: 2026-07-19 / Claude Code (per issue's "providers that support it" framing; open to veto).
- Decision: the native loop returns tool-result entries in EXACTLY the marker path's shape and plugs in BEFORE synthesis, so synthesis prompts, SSE `tool_call` events, proposal persistence, and grounding fallback are shared code with zero divergence risk. Rationale: the #206/#209 lesson — one primitive, not two parallel models. Date/Author: 2026-07-19 / Claude Code.
- Decision: the native path uses its own system prompt variant WITHOUT the `[TOOL: ...]` instruction block (tool selection rules stay; the syntax examples go). Rationale: teaching marker syntax to a model that has native tools invites it to answer with markers instead of tool_calls. Date/Author: 2026-07-19 / Claude Code.
- Decision: `generate_with_tools` normalizes arguments to parsed dicts inside each adapter and never leaks SDK objects. Rationale: the runtime loop must be provider-agnostic and deterministic to test with fakes. Date/Author: 2026-07-19 / Claude Code.

## Progress

- [x] (2026-07-19) Read Issue #190, `models/ai_coach_runtime.py`, `models/ai_providers.py`, `models/ai_tools.py` registry/executor, `api/routers/coach.py` SSE flow; created worktree branch `claude/issue-190-native-function-calling` from `origin/main` (5f71d13).
- [x] (2026-07-19) Milestone one: RED contract in `tests/smoke/test_coach_native_tools.py` — 13/13 honestly RED (missing methods/functions), draft PR #225.
- [x] (2026-07-19) Milestone two: `get_tool_schemas()` single registry; `get_available_tools()` derives descriptions from it byte-identically.
- [x] (2026-07-19) Milestone three: base capability/contract + `OpenAICompatibleToolsMixin` (OpenAI, DeepSeek) + Anthropic adapter (tool_use / merged tool_result translation); provider suites unchanged.
- [x] (2026-07-19) Milestone four: `run_native_tool_loop` + `resolve_turn_tool_results` + `create_native_chat_system_prompt`; 13/13 GREEN.
- [x] (2026-07-19) Milestone five: `api/routers/coach.py` dispatches through `resolve_turn_tool_results`; SSE `tool_call` events carry `native` (true only for genuinely native calls, false when grounding fired); M5 router gate RED→GREEN. Smoke 872 passed; broad non-live 915 passed (the one failure is the pre-existing date-dependent scheduler histogram, issue #226).
- [ ] Milestone six: live DeepSeek probe (only with explicit authorization) + retrospective.

- Decision (M5): the legacy Streamlit surface (`ui/pages/ai_coaching.py` → `finalize_ai_chat_response`) intentionally stays on the marker path. It is the fallback surface during the web migration; per repo rules new product behavior does not land in `ui/pages/*`, and its grounding fallback keeps protecting it. The web/API surface is the only native consumer in this slice. Date/Author: 2026-07-19 / Claude Code.

## Surprises & Discoveries

- (2026-07-19) `tests/smoke/test_session_scheduler.py::test_reference_plan_histogram_replaces_three_session_days` fails on main independent of this work — the reference plan is built from "today" and week 3 (Base) dropped to 6 occasions on 2026-07-19; filed as issue #226 (same class as #163/#164).
- (2026-07-19) On the native path `provider.generate_response` is still exercised — by the synthesis pass. The M5 gate therefore cannot simply forbid `generate_response`; it pins instead that no prompt reaching it contains the `[TOOL:` block (the marker first pass never runs), which is the actual invariant.

## Outcomes & Retrospective

Pending implementation.

## Validation and Acceptance

`python -m pytest tests/smoke/test_coach_native_tools.py -q` (focused), `python -m pytest tests/smoke -q`, `python -m pytest -m "not live and not debug" tests/ -q`. No live provider calls in any test; the M6 live probe runs only with explicit user authorization and its transcript is recorded in this document.
