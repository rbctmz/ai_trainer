"""Smoke coverage for coach response token budgeting."""
from __future__ import annotations

from config.settings import Settings
from api.coach_service import stream_tokens
from models.ai_providers import DeepSeekProvider


class _DummyStreamDelta:
    def __init__(self, content: str | None):
        self.content = content


class _DummyStreamChoice:
    def __init__(self, content: str | None):
        self.delta = _DummyStreamDelta(content)


class _DummyStreamChunk:
    def __init__(self, content: str | None):
        self.choices = [_DummyStreamChoice(content)]


class _DummyStreamingCompletions:
    def __init__(self):
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        return iter([_DummyStreamChunk("Привет "), _DummyStreamChunk("мир")])


class _DummyStreamingClient:
    def __init__(self):
        self.completions = _DummyStreamingCompletions()
        self.chat = type("Chat", (), {"completions": self.completions})()


class _DummyMessage:
    def __init__(self, content: str):
        self.content = content


class _DummyChoice:
    def __init__(self, content: str):
        self.message = _DummyMessage(content)


class _DummyResponse:
    def __init__(self, content: str):
        self.choices = [_DummyChoice(content)]


class _DummyNonStreamingCompletions:
    def __init__(self):
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        return _DummyResponse("ok")


class _DummyNonStreamingClient:
    def __init__(self):
        self.completions = _DummyNonStreamingCompletions()
        self.chat = type("Chat", (), {"completions": self.completions})()


def test_stream_tokens_uses_configured_response_cap(monkeypatch):
    monkeypatch.setattr(Settings, "AI_RESPONSE_MAX_TOKENS", 1800, raising=False)
    provider = type(
        "Provider",
        (),
        {"client": _DummyStreamingClient(), "model": "deepseek-v4-flash"},
    )()

    chunks = list(stream_tokens(provider, "Что ты умеешь?"))

    assert "".join(chunks) == "Привет мир"
    assert provider.client.completions.kwargs["max_tokens"] == 1800
    assert "extra_body" not in provider.client.completions.kwargs


def test_stream_tokens_disables_thinking_for_deepseek(monkeypatch):
    monkeypatch.setattr(Settings, "AI_RESPONSE_MAX_TOKENS", 1800, raising=False)
    # Explicit policy: a developer who enables thinking globally must not turn
    # this assertion into an environment-dependent test (issue #558).
    monkeypatch.setattr(Settings, "AI_DEEPSEEK_THINKING", False, raising=False)
    provider = DeepSeekProvider(api_key=None, settings=Settings)
    provider.client = _DummyStreamingClient()
    provider.api_key = "test"
    provider.model = "deepseek-v4-flash"

    chunks = list(stream_tokens(provider, "Сформируй итоговый ответ"))

    assert "".join(chunks) == "Привет мир"
    assert provider.client.completions.kwargs["extra_body"] == {
        "thinking": {"type": "disabled"}
    }


def test_deepseek_provider_uses_configured_response_cap(monkeypatch):
    monkeypatch.setattr(Settings, "AI_RESPONSE_MAX_TOKENS", 1800, raising=False)

    provider = DeepSeekProvider(api_key=None, settings=Settings)
    provider.client = _DummyNonStreamingClient()
    provider.api_key = "test"
    provider.model = "deepseek-v4-flash"

    result = provider.generate_response("Расскажи про мою форму")

    assert result == "ok"
    assert provider.client.completions.kwargs["max_tokens"] == 1800


class _ReasoningOnlyDelta:
    def __init__(self, reasoning: str):
        self.content = None
        self.reasoning_content = reasoning


class _ReasoningOnlyChoice:
    def __init__(self, reasoning: str, finish_reason=None):
        self.delta = _ReasoningOnlyDelta(reasoning)
        self.finish_reason = finish_reason


class _ReasoningOnlyChunk:
    def __init__(self, reasoning: str, finish_reason=None):
        self.choices = [_ReasoningOnlyChoice(reasoning, finish_reason)]


class _ReasoningOnlyCompletions:
    def create(self, **kwargs):
        # Thinking-mode shape: every delta carries hidden reasoning, the visible
        # answer never arrives, and the stream stops on the output limit.
        return iter(
            [
                _ReasoningOnlyChunk("Сначала оценю объём..."),
                _ReasoningOnlyChunk("Проверяю ограничения..."),
                _ReasoningOnlyChunk("", finish_reason="length"),
            ]
        )


class _ReasoningOnlyClient:
    def __init__(self):
        self.completions = _ReasoningOnlyCompletions()
        self.chat = type("Chat", (), {"completions": self.completions})()


def test_stream_tokens_reports_exhausted_budget_instead_of_empty_stream(monkeypatch):
    """Codex review on PR #561: a stream that spent the whole budget on hidden
    reasoning used to yield nothing at all, so the tool-backed coach flow fell
    through to its generic error instead of the budget notice."""
    monkeypatch.setattr(Settings, "AI_RESPONSE_MAX_TOKENS", 1800, raising=False)
    provider = DeepSeekProvider(api_key=None, settings=Settings)
    provider.client = _ReasoningOnlyClient()
    provider.api_key = "test"
    provider.model = "deepseek-flash"

    chunks = list(stream_tokens(provider, "Сформируй итоговый ответ"))

    answer = "".join(chunks)
    assert answer.strip()
    assert "1800" in answer
    assert "ответ не получен" in answer
