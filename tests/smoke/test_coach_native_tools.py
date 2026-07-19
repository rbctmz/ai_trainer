"""M1 RED contract for native function calling in the coach (Issue #190).

Pins, before any implementation exists:
- one tool registry: JSON schemas cover exactly the executable tools and are
  the single source for the marker-path description strings;
- the provider contract: `supports_native_tools` capability matrix and the
  normalized `generate_with_tools` return shape (parsed-dict arguments, never
  SDK objects or JSON strings);
- adapter translation for the OpenAI-compatible client (OpenAI/DeepSeek) and
  Anthropic tool use, via stubbed SDK clients — no network;
- the native runtime loop: schemas in → structured tool_calls executed through
  the shared executor → tool-result entries BYTE-SHAPE-IDENTICAL to the marker
  path → bounded rounds → zero calls yields an empty list so the #189
  grounding fallback engages at the existing call sites;
- the native system prompt carries no `[TOOL:` marker syntax;
- dispatch: native loop when supported+available, marker path otherwise —
  and the marker path itself stays regression-pinned.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from data.database import Database
from models.ai_providers import (
    AnthropicProvider,
    DeepSeekProvider,
    GoogleGeminiProvider,
    OllamaProvider,
    OpenAIProvider,
)
from models.ai_tools import AITools
from models.mock_ai_provider import MockAIProvider


pytestmark = pytest.mark.smoke


@pytest.fixture()
def ai_tools(tmp_path):
    return AITools(Database(str(tmp_path / "native.db")))


def _formatter(tool_name: str, data: object) -> str:
    return f"{tool_name}: formatted"


# ---------------------------------------------------------------------------
# One tool registry: schemas ⇄ executable tools ⇄ marker descriptions
# ---------------------------------------------------------------------------


def test_tool_schemas_cover_exactly_the_executable_registry(ai_tools):
    schemas = {schema["name"]: schema for schema in ai_tools.get_tool_schemas()}
    assert set(schemas) == set(ai_tools.tools.keys())
    for schema in schemas.values():
        assert isinstance(schema["description"], str) and schema["description"].strip()
        parameters = schema["parameters"]
        assert parameters["type"] == "object"
        assert isinstance(parameters["properties"], dict)
        assert isinstance(parameters.get("required", []), list)


def test_marker_descriptions_are_single_sourced_from_schemas(ai_tools):
    schemas = {schema["name"]: schema for schema in ai_tools.get_tool_schemas()}
    available = ai_tools.get_available_tools()
    assert set(available) == set(schemas)
    for name, description in available.items():
        assert description == schemas[name]["description"], name


def test_representative_parameter_schemas_are_typed(ai_tools):
    schemas = {schema["name"]: schema for schema in ai_tools.get_tool_schemas()}

    limit = schemas["get_recent_activities"]["parameters"]["properties"]["limit"]
    assert limit["type"] == "integer"
    assert limit.get("default") == 10

    days = schemas["get_performance_metrics"]["parameters"]["properties"]["days"]
    assert days["type"] == "integer"

    date_range = schemas["get_activities_by_date_range"]["parameters"]
    assert date_range["properties"]["start_date"]["type"] == "string"
    assert date_range["properties"]["end_date"]["type"] == "string"
    assert set(date_range["required"]) == {"start_date", "end_date"}

    build = schemas["propose_plan_build"]["parameters"]
    assert {"goal_type", "distance", "event_date", "available_hours"} <= set(
        build["required"]
    )

    compare = schemas["compare_periods"]["parameters"]["properties"]
    assert compare["period1_days"]["type"] == "integer"
    assert compare["period2_days"]["type"] == "integer"


# ---------------------------------------------------------------------------
# Provider contract: capability matrix + normalized generate_with_tools
# ---------------------------------------------------------------------------


def test_provider_native_capability_matrix():
    assert OpenAIProvider(api_key=None).supports_native_tools() is True
    assert DeepSeekProvider(api_key=None).supports_native_tools() is True
    assert AnthropicProvider(api_key=None).supports_native_tools() is True
    # v1 scope: Gemini and Ollama stay on the marker path (ExecPlan decision).
    assert GoogleGeminiProvider(api_key=None).supports_native_tools() is False
    assert OllamaProvider().supports_native_tools() is False
    assert MockAIProvider().supports_native_tools() is False


def test_base_generate_with_tools_is_not_implemented():
    with pytest.raises(NotImplementedError):
        MockAIProvider().generate_with_tools(
            messages=[{"role": "user", "content": "q"}], tools=[]
        )


def _openai_style_response(content, tool_calls):
    message = SimpleNamespace(content=content, tool_calls=tool_calls)
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def test_openai_compatible_adapter_normalizes_tools_and_tool_calls():
    provider = DeepSeekProvider(api_key="test-key")
    recorded: dict = {}

    def _create(**kwargs):
        recorded.update(kwargs)
        return _openai_style_response(
            "секунду, соберу данные",
            [
                SimpleNamespace(
                    id="call_1",
                    function=SimpleNamespace(
                        name="get_recent_activities",
                        arguments=json.dumps({"limit": 3}),
                    ),
                )
            ],
        )

    provider.client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=_create))
    )

    schema = {
        "name": "get_recent_activities",
        "description": "Последние активности",
        "parameters": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "default": 10}},
            "required": [],
        },
    }
    out = provider.generate_with_tools(
        messages=[{"role": "user", "content": "как дела?"}],
        tools=[schema],
        system_prompt="системный",
    )

    sent_tool = recorded["tools"][0]
    assert sent_tool["type"] == "function"
    assert sent_tool["function"]["name"] == "get_recent_activities"
    assert sent_tool["function"]["parameters"]["properties"]["limit"]["type"] == "integer"
    assert recorded["messages"][0] == {"role": "system", "content": "системный"}
    assert recorded["messages"][-1] == {"role": "user", "content": "как дела?"}

    assert out["text"] == "секунду, соберу данные"
    assert out["tool_calls"] == [
        {"id": "call_1", "name": "get_recent_activities", "arguments": {"limit": 3}}
    ]


def test_openai_compatible_adapter_tolerates_missing_and_broken_arguments():
    provider = DeepSeekProvider(api_key="test-key")

    def _create(**kwargs):
        return _openai_style_response(
            None,
            [
                SimpleNamespace(
                    id="call_1",
                    function=SimpleNamespace(name="analyze_recovery_state", arguments=""),
                ),
                SimpleNamespace(
                    id="call_2",
                    function=SimpleNamespace(name="get_hrv_data", arguments="{broken"),
                ),
            ],
        )

    provider.client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=_create))
    )

    out = provider.generate_with_tools(
        messages=[{"role": "user", "content": "q"}], tools=[]
    )
    assert out["text"] == ""
    assert out["tool_calls"] == [
        {"id": "call_1", "name": "analyze_recovery_state", "arguments": {}},
        {"id": "call_2", "name": "get_hrv_data", "arguments": {}},
    ]


def test_anthropic_adapter_normalizes_tool_use_blocks():
    provider = AnthropicProvider(api_key="test-key")
    recorded: dict = {}

    def _create(**kwargs):
        recorded.update(kwargs)
        return SimpleNamespace(
            content=[
                SimpleNamespace(type="text", text="смотрю данные"),
                SimpleNamespace(
                    type="tool_use",
                    id="tu_1",
                    name="get_performance_metrics",
                    input={"days": 30},
                ),
            ],
            stop_reason="tool_use",
        )

    provider.client = SimpleNamespace(messages=SimpleNamespace(create=_create))

    schema = {
        "name": "get_performance_metrics",
        "description": "CTL/ATL/TSB",
        "parameters": {
            "type": "object",
            "properties": {"days": {"type": "integer"}},
            "required": [],
        },
    }
    out = provider.generate_with_tools(
        messages=[{"role": "user", "content": "форма?"}],
        tools=[schema],
        system_prompt="системный",
    )

    sent_tool = recorded["tools"][0]
    assert sent_tool["name"] == "get_performance_metrics"
    assert sent_tool["input_schema"]["type"] == "object"
    assert sent_tool["input_schema"]["properties"]["days"]["type"] == "integer"
    assert recorded["system"] == "системный"

    assert out["text"] == "смотрю данные"
    assert out["tool_calls"] == [
        {"id": "tu_1", "name": "get_performance_metrics", "arguments": {"days": 30}}
    ]


# ---------------------------------------------------------------------------
# Native runtime loop
# ---------------------------------------------------------------------------


class _FakeTools:
    """Minimal AITools stand-in: registry + executor + schemas."""

    def __init__(self):
        self.executed: list[tuple[str, dict]] = []
        self.tools = {
            "get_performance_metrics": lambda **kw: {"ctl": 18.4},
            "get_recent_activities": lambda **kw: {"activities": []},
        }

    def get_tool_schemas(self):
        return [
            {
                "name": name,
                "description": name,
                "parameters": {"type": "object", "properties": {}, "required": []},
            }
            for name in self.tools
        ]

    def execute_tool(self, tool_name: str, **kwargs):
        self.executed.append((tool_name, dict(kwargs)))
        if tool_name not in self.tools:
            return {"error": f"Инструмент '{tool_name}' не найден"}
        return {
            "success": True,
            "tool": tool_name,
            "parameters": kwargs,
            "result": self.tools[tool_name](**kwargs),
        }


class _ScriptedNativeProvider:
    """Duck-typed provider driving the loop with pre-scripted rounds."""

    def __init__(self, rounds):
        self.rounds = list(rounds)
        self.calls: list[dict] = []

    def supports_native_tools(self) -> bool:
        return True

    def is_available(self) -> bool:
        return True

    def generate_with_tools(self, messages, tools, system_prompt=""):
        self.calls.append(
            {"messages": list(messages), "tools": list(tools), "system": system_prompt}
        )
        if self.rounds:
            return self.rounds.pop(0)
        return {"text": "готово", "tool_calls": []}

    def generate_response(self, prompt: str, system_prompt: str = "") -> str:
        raise AssertionError("marker path must not be used by the native loop")


def test_native_loop_executes_calls_and_matches_marker_result_shape():
    from models.ai_coach_runtime import run_native_tool_loop

    provider = _ScriptedNativeProvider(
        [
            {
                "text": "",
                "tool_calls": [
                    {"id": "c1", "name": "get_performance_metrics", "arguments": {}},
                    {
                        "id": "c2",
                        "name": "get_recent_activities",
                        "arguments": {"limit": 3},
                    },
                ],
            },
            {"text": "готово", "tool_calls": []},
        ]
    )
    tools = _FakeTools()

    final_text, tool_results = run_native_tool_loop(
        provider,
        tools,
        "как моя форма?",
        [],
        _formatter,
    )

    assert final_text == "готово"
    assert tools.executed == [
        ("get_performance_metrics", {}),
        ("get_recent_activities", {"limit": 3}),
    ]
    # entries are byte-shape-identical to collect_tool_results' marker entries
    assert [sorted(entry.keys()) for entry in tool_results] == [
        ["formatted_result", "params", "raw_result", "success", "tool_name"],
        ["formatted_result", "params", "raw_result", "success", "tool_name"],
    ]
    assert tool_results[0]["tool_name"] == "get_performance_metrics"
    assert tool_results[0]["success"] is True
    assert tool_results[0]["formatted_result"] == "get_performance_metrics: formatted"
    assert tool_results[1]["params"] == {"limit": 3}

    # round 1: schemas went to the provider; round 2: tool results came back
    assert provider.calls[0]["tools"] == tools.get_tool_schemas()
    round_two_roles = [m.get("role") for m in provider.calls[1]["messages"]]
    assert "tool" in round_two_roles


def test_native_loop_is_bounded_and_zero_calls_stay_empty_for_grounding():
    from models.ai_coach_runtime import run_native_tool_loop

    greedy = _ScriptedNativeProvider(
        [
            {
                "text": "",
                "tool_calls": [
                    {"id": f"c{i}", "name": "get_performance_metrics", "arguments": {}}
                ],
            }
            for i in range(10)
        ]
    )
    tools = _FakeTools()
    _text, results = run_native_tool_loop(
        greedy, tools, "q", [], _formatter, max_rounds=2
    )
    assert len(greedy.calls) == 2  # bounded: no third round
    assert len(results) == 2

    silent = _ScriptedNativeProvider([{"text": "без данных", "tool_calls": []}])
    final_text, results = run_native_tool_loop(silent, _FakeTools(), "q", [], _formatter)
    assert results == []  # grounding fallback (#189) engages at the call site
    assert final_text == "без данных"


def test_native_loop_turns_unknown_tool_into_error_entry_and_continues():
    from models.ai_coach_runtime import run_native_tool_loop

    provider = _ScriptedNativeProvider(
        [
            {
                "text": "",
                "tool_calls": [
                    {"id": "c1", "name": "no_such_tool", "arguments": {}},
                    {"id": "c2", "name": "get_performance_metrics", "arguments": {}},
                ],
            },
            {"text": "готово", "tool_calls": []},
        ]
    )
    _text, results = run_native_tool_loop(provider, _FakeTools(), "q", [], _formatter)
    assert [entry["success"] for entry in results] == [False, True]
    assert results[0]["formatted_result"].startswith("❌")


# ---------------------------------------------------------------------------
# Prompts and dispatch
# ---------------------------------------------------------------------------


def test_native_system_prompt_has_no_marker_syntax(ai_tools):
    from models.ai_coach_runtime import (
        create_chat_system_prompt_with_tools,
        create_native_chat_system_prompt,
    )

    native_prompt = create_native_chat_system_prompt(ai_tools)
    assert "[TOOL:" not in native_prompt
    assert "Сегодня:" in native_prompt  # the date anchor (#125) survives

    # regression: the marker path keeps teaching the marker syntax
    marker_prompt = create_chat_system_prompt_with_tools(ai_tools)
    assert "[TOOL:" in marker_prompt


def test_coach_stream_uses_native_loop_and_flags_tool_events(tmp_path, monkeypatch):
    """M5: the SSE endpoint dispatches through resolve_turn_tool_results — a
    native-capable provider never sees the marker first pass, tool_call events
    carry native: true, and the synthesis/stream flow is unchanged."""
    import asyncio

    from config.settings import Settings

    monkeypatch.setattr(Settings, "CHATS_DIR", str(tmp_path / "chats"), raising=False)

    from api.routers import coach as coach_mod

    class NativeProvider(MockAIProvider):
        def __init__(self):
            super().__init__(delay=0)
            self.native_calls = 0
            self.plain_prompts: list[str] = []

        def supports_native_tools(self) -> bool:
            return True

        def generate_with_tools(self, messages, tools, system_prompt=""):
            self.native_calls += 1
            assert any(t["name"] == "get_performance_metrics" for t in tools)
            if self.native_calls == 1:
                return {
                    "text": "",
                    "tool_calls": [
                        {
                            "id": "c1",
                            "name": "get_performance_metrics",
                            "arguments": {"days": 30},
                        }
                    ],
                }
            return {"text": "готово", "tool_calls": []}

        def generate_response(self, prompt: str, context: str = "") -> str:
            self.plain_prompts.append(prompt)
            return "Синтез по данным."

    provider = NativeProvider()
    monkeypatch.setattr(
        coach_mod, "resolve_provider", lambda provider_type=None: provider
    )
    monkeypatch.setattr(coach_mod, "supports_streaming", lambda _provider: False)

    db = Database(str(tmp_path / "coach_native_stream.db"))
    req = coach_mod.ChatRequest(message="Как моя форма?", provider="mock")
    response = coach_mod.coach_chat(req, db)

    async def _collect() -> list[dict]:
        out = []
        async for raw in response.body_iterator:
            text = raw if isinstance(raw, str) else raw.decode()
            if text.startswith("data:"):
                out.append(json.loads(text[5:].strip()))
        return out

    events = asyncio.run(_collect())

    tool_events = [event for event in events if event["type"] == "tool_call"]
    assert [event["tool_name"] for event in tool_events] == ["get_performance_metrics"]
    assert all(event["native"] is True for event in tool_events)
    assert events[-1]["type"] == "done"
    assert provider.native_calls == 2
    # generate_response is only the synthesis pass — the marker first pass
    # (whose prompt teaches the [TOOL: ...] syntax) must never run natively
    assert provider.plain_prompts, "synthesis still uses generate_response"
    assert all("[TOOL:" not in prompt for prompt in provider.plain_prompts)


def test_dispatch_prefers_native_and_keeps_marker_fallback():
    from models.ai_coach_runtime import resolve_turn_tool_results

    native = _ScriptedNativeProvider(
        [
            {
                "text": "",
                "tool_calls": [
                    {"id": "c1", "name": "get_performance_metrics", "arguments": {}}
                ],
            },
            {"text": "готово", "tool_calls": []},
        ]
    )
    out = resolve_turn_tool_results(
        provider=native,
        ai_tools=_FakeTools(),
        user_input="как форма?",
        history_messages=[],
        tool_result_formatter=_formatter,
    )
    assert out["native"] is True
    assert [entry["tool_name"] for entry in out["tool_results"]] == [
        "get_performance_metrics"
    ]
    assert isinstance(out["rendered_response"], str)

    class _MarkerProvider:
        def supports_native_tools(self) -> bool:
            return False

        def is_available(self) -> bool:
            return True

        def generate_response(self, prompt: str, system_prompt: str = "") -> str:
            return "Смотрю. [TOOL: get_performance_metrics]"

    out = resolve_turn_tool_results(
        provider=_MarkerProvider(),
        ai_tools=_FakeTools(),
        user_input="как форма?",
        history_messages=[],
        tool_result_formatter=_formatter,
    )
    assert out["native"] is False
    assert [entry["tool_name"] for entry in out["tool_results"]] == [
        "get_performance_metrics"
    ]
    # marker rendering behavior is unchanged: the marker is replaced inline
    assert "get_performance_metrics: formatted" in out["rendered_response"]
    assert "[TOOL:" not in out["rendered_response"]
