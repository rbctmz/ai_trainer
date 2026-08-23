"""RED contract for the DeepSeek Responses API adapter (Issue #441, Class A pilot).

Pins, before any implementation exists:
- a parser normalizes Responses output items by type discriminator
  (message -> text, function_call -> {id, name, arguments dict}, reasoning -> skipped)
  and never crashes when output_text is None;
- history translation projects the runtime's OpenAI-style tool history onto
  Responses input items (assistant tool_calls -> function_call, tool message ->
  function_call_output);
- the adapter calls client.responses.create with instructions/tools/input and
  returns the SAME normalized shape as every other native provider
  ({text, tool_calls}); SDK errors and unconfigured clients degrade to an error
  text plus an empty tool list (grounding fallback, #189/#190);
- the new provider is additive: registered under deepseek_responses,
  supports native tools, and the existing deepseek chat provider is untouched.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.smoke


def _message_item(text: str) -> SimpleNamespace:
    return SimpleNamespace(type="message", content=[SimpleNamespace(text=text)])


def _function_call_item(call_id: str, name: str, arguments: dict) -> SimpleNamespace:
    return SimpleNamespace(type="function_call", call_id=call_id, name=name, arguments=arguments)


class _StubResponsesClient:
    """Fake client: records responses.create kwargs and returns a canned output."""

    def __init__(self, output=None, error=None) -> None:
        self.output = output or []
        self.error = error
        self.last_kwargs = None
        self.calls = 0
        self.responses = self._Responses(self)

    class _Responses:
        def __init__(self, owner) -> None:
            self.owner = owner

        def create(self, **kwargs):
            self.owner.calls += 1
            self.owner.last_kwargs = kwargs
            if self.owner.error is not None:
                raise self.owner.error
            return SimpleNamespace(
                output=list(self.owner.output),
                output_text=None,
            )


# ---------------------------------------------------------------------------
# Parser contract
# ---------------------------------------------------------------------------


def test_parser_message_item_yields_text():
    from models.ai_providers import responses_output_to_result

    result = responses_output_to_result([_message_item("Привет, атлет")])
    assert result == {"text": "Привет, атлет", "tool_calls": []}


def test_parser_function_call_normalizes_identity():
    from models.ai_providers import responses_output_to_result

    result = responses_output_to_result(
        [_function_call_item("call_1", "get_weather", {"city": "Москва"})]
    )
    assert result["tool_calls"] == [
        {"id": "call_1", "name": "get_weather", "arguments": {"city": "Москва"}}
    ]


def test_parser_skips_reasoning_items():
    from models.ai_providers import responses_output_to_result

    result = responses_output_to_result(
        [
            SimpleNamespace(type="reasoning", summary=[SimpleNamespace(text="думаю")]),
            _message_item("Ответ"),
        ]
    )
    assert result["text"] == "Ответ"
    assert result["tool_calls"] == []


def test_parser_empty_output_with_none_output_text_is_safe():
    from models.ai_providers import responses_output_to_result

    result = responses_output_to_result([])
    assert result == {"text": "", "tool_calls": []}


def test_parser_accepts_dict_items():
    from models.ai_providers import responses_output_to_result

    result = responses_output_to_result(
        [{"type": "function_call", "call_id": "c9", "name": "ping", "arguments": {"n": 1}}]
    )
    assert result["tool_calls"] == [{"id": "c9", "name": "ping", "arguments": {"n": 1}}]


# ---------------------------------------------------------------------------
# History translation contract
# ---------------------------------------------------------------------------


def test_history_translation_tool_calls_become_function_call_items():
    from models.ai_providers import _messages_to_responses_input

    items = _messages_to_responses_input(
        [
            {"role": "user", "content": "какая погода?"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"id": "tc_1", "name": "get_weather", "arguments": {"city": "Питер"}}
                ],
            },
        ]
    )
    assert items[0] == {"role": "user", "content": "какая погода?"}
    assert items[1] == {"role": "assistant", "content": ""}
    assert items[2] == {
        "type": "function_call",
        "call_id": "tc_1",
        "name": "get_weather",
        "arguments": {"city": "Питер"},
    }


def test_history_translation_tool_results_become_function_call_output():
    from models.ai_providers import _messages_to_responses_input

    items = _messages_to_responses_input(
        [
            {
                "role": "tool",
                "tool_call_id": "tc_1",
                "name": "get_weather",
                "content": "12°C",
            },
        ]
    )
    assert items == [
        {"type": "function_call_output", "call_id": "tc_1", "output": "12°C"}
    ]


# ---------------------------------------------------------------------------
# Adapter contract
# ---------------------------------------------------------------------------


def test_adapter_calls_responses_create_with_instructions_tools_input():
    from models.ai_providers import DeepSeekResponsesProvider

    client = _StubResponsesClient(output=[_message_item("готово")])
    provider = DeepSeekResponsesProvider(api_key=None)
    provider.client = client

    result = provider.generate_with_tools(
        messages=[{"role": "user", "content": "привет"}],
        tools=[
            {
                "name": "ping",
                "description": "Проверка связи",
                "parameters": {"type": "object", "properties": {}, "required": []},
            }
        ],
        system_prompt="Ты коуч",
    )

    kwargs = client.last_kwargs
    assert kwargs["model"] == provider.model
    assert kwargs["instructions"] == "Ты коуч"
    assert kwargs["tools"] == [
        {
            "type": "function",
            "name": "ping",
            "description": "Проверка связи",
            "parameters": {"type": "object", "properties": {}, "required": []},
        }
    ]
    assert kwargs["input"] == [{"role": "user", "content": "привет"}]
    assert result == {"text": "готово", "tool_calls": []}


def test_adapter_returns_normalized_tool_calls():
    from models.ai_providers import DeepSeekResponsesProvider

    client = _StubResponsesClient(
        output=[_function_call_item("call_7", "get_recent_activities", {"limit": 5})]
    )
    provider = DeepSeekResponsesProvider(api_key=None)
    provider.client = client

    result = provider.generate_with_tools([{"role": "user", "content": "q"}], [])
    assert result == {
        "text": "",
        "tool_calls": [{"id": "call_7", "name": "get_recent_activities", "arguments": {"limit": 5}}],
    }


def test_adapter_sdk_error_returns_error_text_and_empty_calls():
    from models.ai_providers import DeepSeekResponsesProvider

    client = _StubResponsesClient(error=RuntimeError("429 quota"))
    provider = DeepSeekResponsesProvider(api_key=None)
    provider.client = client

    result = provider.generate_with_tools([{"role": "user", "content": "q"}], [])
    assert result["tool_calls"] == []
    assert "Ошибка" in result["text"] and "429 quota" in result["text"]


def test_adapter_client_none_returns_not_configured():
    from models.ai_providers import DeepSeekResponsesProvider

    # Контракт не зависит от наличия ключа в окружении: явно гасим клиент.
    provider = DeepSeekResponsesProvider(api_key=None)
    provider.client = None
    result = provider.generate_with_tools([{"role": "user", "content": "q"}], [])
    assert result == {"text": "DeepSeekResponsesProvider: клиент не настроен", "tool_calls": []}


# ---------------------------------------------------------------------------
# Registry and capability contract
# ---------------------------------------------------------------------------


def test_factory_creates_responses_provider():
    from models.ai_providers import AIProviderFactory, DeepSeekResponsesProvider

    provider = AIProviderFactory.create_provider("deepseek_responses", api_key=None)
    assert isinstance(provider, DeepSeekResponsesProvider)


def test_responses_provider_supports_native_tools():
    from models.ai_providers import DeepSeekResponsesProvider

    assert DeepSeekResponsesProvider(api_key=None).supports_native_tools() is True


def test_chat_provider_remains_registered():
    from models.ai_providers import AIProviderFactory, DeepSeekProvider

    chat = AIProviderFactory.create_provider("deepseek", api_key=None)
    assert isinstance(chat, DeepSeekProvider)


def test_picker_exposes_responses_option():
    from ui.components.ai_coach_provider import _build_provider_options

    options = _build_provider_options(demo_mode=False)
    assert options.get("DeepSeek (Responses API)") == "deepseek_responses"


# ---------------------------------------------------------------------------
# Codex review fixes (#496): SDK capability gate, connection diagnostics
# ---------------------------------------------------------------------------


def test_client_supports_responses_helper():
    from models.ai_providers import _client_supports_responses

    assert _client_supports_responses(None) is False
    assert _client_supports_responses(SimpleNamespace()) is False
    assert _client_supports_responses(SimpleNamespace(responses=True)) is True


def test_provider_degrades_honestly_when_sdk_has_no_responses_resource():
    """Gate-обход (старый SDK): вызов деградирует в error-text, а не падает."""
    from models.ai_providers import DeepSeekResponsesProvider

    provider = DeepSeekResponsesProvider(api_key=None)
    provider.client = SimpleNamespace()  # у клиента нет .responses
    result = provider.generate_with_tools([{"role": "user", "content": "q"}], [])
    assert result["tool_calls"] == []
    assert "Ошибка" in result["text"]


def test_connection_measures_text_from_output_items():
    from models.ai_providers import DeepSeekResponsesProvider

    client = _StubResponsesClient(output=[_message_item("12345")])
    provider = DeepSeekResponsesProvider(api_key=None)
    provider.client = client

    probe = provider.test_connection()
    assert probe["success"] is True
    assert probe["response_length"] == 5
