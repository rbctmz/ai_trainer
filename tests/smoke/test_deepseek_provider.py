"""Smoke coverage for DeepSeek provider wiring."""
from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path
from types import SimpleNamespace

import pytest

from models import ai_providers
from ui.pages import ai_coaching


pytestmark = pytest.mark.smoke

ROOT = Path(__file__).resolve().parents[2]


def test_deepseek_default_model_is_representable_in_every_picker():
    """Issue #559: the DeepSeek picker resolves the configured model with
    ``list.index()`` and silently falls back to index 0, so a default that the
    lists do not contain would swap the model behind the user's back.

    Runs in a clean interpreter on purpose: a developer checkout may set
    ``DEEPSEEK_MODEL`` to a legacy alias in ``.env``, while the invariant under
    test is about the default value.
    """
    script = textwrap.dedent(
        """
        import dotenv
        dotenv.load_dotenv = lambda *args, **kwargs: False  # ignore the local .env
        from config.settings import Settings
        from models.ai_providers import DeepSeekProvider, DeepSeekResponsesProvider
        from ui.components.ai_coach_provider import DEEPSEEK_MODEL_OPTIONS

        default = Settings.DEEPSEEK_MODEL
        assert default == "deepseek-flash", default

        option_lists = {
            "DeepSeekProvider": DeepSeekProvider(api_key=None).get_available_models(),
            "DeepSeekResponsesProvider": DeepSeekResponsesProvider(api_key=None).get_available_models(),
            "DeepSeek picker": list(DEEPSEEK_MODEL_OPTIONS),
        }
        for name, options in option_lists.items():
            assert options[0] == default, (name, options)
            assert "deepseek-v4-flash" not in options, (name, options)
        print("OK")
        """
    )
    env = {key: value for key, value in os.environ.items() if key != "DEEPSEEK_MODEL"}

    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        env=env,
        cwd=ROOT,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "OK"


def test_deepseek_is_listed_in_provider_options():
    provider_options = ai_coaching._build_provider_options(demo_mode=False)

    assert provider_options["DeepSeek"] == "deepseek"


def test_deepseek_provider_uses_configured_base_url(monkeypatch: pytest.MonkeyPatch):
    created = {}

    class _FakeOpenAIClient:
        def __init__(self, api_key: str, base_url: str):
            created["api_key"] = api_key
            created["base_url"] = base_url

    class _Settings:
        DEEPSEEK_API_KEY = "deepseek-test-key"
        DEEPSEEK_MODEL = "deepseek-v4-flash"
        DEEPSEEK_BASE_URL = "https://api.deepseek.com"

    openai_module = type("OpenAIModule", (), {"OpenAI": _FakeOpenAIClient})
    monkeypatch.setitem(sys.modules, "openai", openai_module)

    provider = ai_providers.DeepSeekProvider(settings=_Settings)

    assert provider.is_available() is True
    assert provider.get_model_name() == "DeepSeek deepseek-v4-flash"
    assert created["api_key"] == "deepseek-test-key"
    assert created["base_url"] == "https://api.deepseek.com"


def test_factory_creates_deepseek_provider():
    provider = ai_providers.AIProviderFactory.create_provider(
        "deepseek",
        api_key="test-key",
        model="deepseek-v4-pro",
        base_url="https://api.deepseek.com",
    )

    assert isinstance(provider, ai_providers.DeepSeekProvider)


# ---------------------------------------------------------------------------
# Thinking policy and answer budget (issue #558)
# ---------------------------------------------------------------------------


class _StubSettings:
    """Settings double: explicit values, independent of the developer's .env."""

    DEEPSEEK_API_KEY = "stub-key"
    DEEPSEEK_MODEL = "deepseek-flash"
    DEEPSEEK_BASE_URL = "https://api.deepseek.com"
    OPENAI_API_KEY = "stub-key"
    OPENAI_MODEL = "gpt-4o-mini"
    AI_RESPONSE_MAX_TOKENS = 1800
    AI_TOOLS_TEMPERATURE = 0.0

    def __init__(self, thinking: bool = False) -> None:
        self.AI_DEEPSEEK_THINKING = thinking


def _tool_call():
    return SimpleNamespace(
        id="call_1",
        function=SimpleNamespace(name="get_ftp", arguments="{}"),
    )


def _stub_chat_provider(*, thinking: bool = False, content=None, finish_reason=None, tool_calls=None):
    """DeepSeekProvider on a recording stub client — no network, no SDK."""
    recorded: list = []

    def _create(**kwargs):
        recorded.append(kwargs)
        message = SimpleNamespace(content=content, tool_calls=tool_calls or [])
        return SimpleNamespace(choices=[SimpleNamespace(message=message, finish_reason=finish_reason)])

    provider = ai_providers.DeepSeekProvider(settings=_StubSettings(thinking=thinking))
    provider.client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=_create))
    )
    return provider, recorded


def test_deepseek_chat_disables_thinking_by_default():
    """Issue #558: thinking is on by default in V4.1 Flash, is billed from the
    answer budget, and ignores `temperature` (issue #440), so coach calls switch
    it off unless AI_DEEPSEEK_THINKING is enabled."""
    provider, recorded = _stub_chat_provider(content="ok")

    provider.generate_response("Как моя форма?")
    provider.generate_with_tools([{"role": "user", "content": "q"}], [])

    assert recorded[0]["extra_body"] == {"thinking": {"type": "disabled"}}
    assert recorded[1]["extra_body"] == {"thinking": {"type": "disabled"}}


def test_deepseek_chat_keeps_thinking_when_explicitly_enabled():
    provider, recorded = _stub_chat_provider(content="ok", thinking=True)

    provider.generate_response("Как моя форма?")
    provider.generate_with_tools([{"role": "user", "content": "q"}], [])

    assert all("extra_body" not in kwargs for kwargs in recorded)


def test_openai_provider_sends_no_deepseek_extras():
    """The tool adapter is shared with OpenAI, whose API rejects unknown body
    fields — the thinking control must stay DeepSeek-only."""
    recorded: list = []

    def _create(**kwargs):
        recorded.append(kwargs)
        message = SimpleNamespace(content="ok", tool_calls=[])
        return SimpleNamespace(choices=[SimpleNamespace(message=message, finish_reason="stop")])

    provider = ai_providers.OpenAIProvider(settings=_StubSettings())
    provider.client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=_create))
    )

    provider.generate_with_tools([{"role": "user", "content": "q"}], [])

    assert "extra_body" not in recorded[0]


def test_deepseek_chat_reports_exhausted_budget_instead_of_empty_answer():
    """Issue #558: `finish_reason=length` with empty content used to reach the
    coach as an empty string, which reads as a silent no-op."""
    provider, _ = _stub_chat_provider(content="", finish_reason="length")

    answer = provider.generate_response("Собери план на 6 недель")

    assert answer.strip()
    assert "1800" in answer


def test_deepseek_chat_keeps_empty_text_on_a_tool_turn():
    """An empty text with tool calls is a normal tool-selection turn."""
    provider, _ = _stub_chat_provider(content="", finish_reason="tool_calls", tool_calls=[_tool_call()])

    result = provider.generate_with_tools([{"role": "user", "content": "q"}], [])

    assert result["text"] == ""
    assert result["tool_calls"] == [{"id": "call_1", "name": "get_ftp", "arguments": {}}]


def test_deepseek_chat_reports_empty_tool_turn_without_tool_calls():
    provider, _ = _stub_chat_provider(content=None, finish_reason="length")

    result = provider.generate_with_tools([{"role": "user", "content": "q"}], [])

    assert result["text"].strip()
    assert "1800" in result["text"]


# ---------------------------------------------------------------------------
# Connection probe policy (Codex review on PR #561)
# ---------------------------------------------------------------------------


def test_deepseek_connection_probe_uses_the_thinking_policy():
    provider, recorded = _stub_chat_provider(content="OK")

    probe = provider.test_connection()

    assert probe["success"] is True
    assert probe["response_length"] == 2
    assert recorded[0]["extra_body"] == {"thinking": {"type": "disabled"}}


def test_deepseek_connection_probe_survives_a_reasoning_only_answer():
    """A reasoning-only probe answer has `content=None`; `len(None)` used to
    report a working connection as broken."""
    provider, _ = _stub_chat_provider(content=None, finish_reason="length")

    probe = provider.test_connection()

    assert probe["success"] is True
    assert probe["response_length"] == 0
    assert "пустой текст" in probe["message"]

