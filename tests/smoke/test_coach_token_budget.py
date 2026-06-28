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


def test_deepseek_provider_uses_configured_response_cap(monkeypatch):
    monkeypatch.setattr(Settings, "AI_RESPONSE_MAX_TOKENS", 1800, raising=False)

    provider = DeepSeekProvider(api_key=None, settings=Settings)
    provider.client = _DummyNonStreamingClient()
    provider.api_key = "test"
    provider.model = "deepseek-v4-flash"

    result = provider.generate_response("Расскажи про мою форму")

    assert result == "ok"
    assert provider.client.completions.kwargs["max_tokens"] == 1800
