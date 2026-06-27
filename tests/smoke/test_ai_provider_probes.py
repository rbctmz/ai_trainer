"""Smoke tests for quiet AI provider availability probes."""
from __future__ import annotations

import sys
import types

import pytest

from models import ai_providers


pytestmark = pytest.mark.smoke


def test_get_available_providers_uses_quiet_google_probe(monkeypatch: pytest.MonkeyPatch):
    calls: list[bool] = []

    class _FakeGoogleProvider:
        def __init__(self, emit_warnings: bool = True):
            calls.append(emit_warnings)

        def is_available(self) -> bool:
            return False

    monkeypatch.setattr(ai_providers, "GoogleGeminiProvider", _FakeGoogleProvider)

    providers = ai_providers.AIProviderFactory.get_available_providers()

    assert calls == [False]
    assert "Google Gemini" in providers


def test_get_first_available_uses_quiet_google_probe(monkeypatch: pytest.MonkeyPatch):
    calls: list[bool] = []

    class _UnavailableProvider:
        def is_available(self) -> bool:
            return False

    class _FakeGoogleProvider:
        def __init__(self, emit_warnings: bool = True):
            calls.append(emit_warnings)

        def is_available(self) -> bool:
            return False

    monkeypatch.setattr(ai_providers, "OpenAIProvider", lambda *args, **kwargs: _UnavailableProvider())
    monkeypatch.setattr(ai_providers, "AnthropicProvider", lambda *args, **kwargs: _UnavailableProvider())
    monkeypatch.setattr(ai_providers, "GoogleGeminiProvider", _FakeGoogleProvider)
    monkeypatch.setattr(ai_providers, "OllamaProvider", lambda *args, **kwargs: _UnavailableProvider())

    ai_providers.AIProviderFactory.get_first_available()

    assert calls == [False]


def test_google_provider_uses_google_genai_client(monkeypatch: pytest.MonkeyPatch):
    created: dict[str, str] = {}
    calls: list[dict[str, object]] = []

    class _FakeResponse:
        text = "gemini response"

    class _FakeModels:
        def generate_content(self, **kwargs):
            calls.append(kwargs)
            return _FakeResponse()

    class _FakeClient:
        def __init__(self, api_key: str):
            created["api_key"] = api_key
            self.models = _FakeModels()

    fake_genai = types.ModuleType("google.genai")
    fake_genai.Client = _FakeClient
    fake_google = types.ModuleType("google")
    fake_google.genai = fake_genai
    monkeypatch.setitem(sys.modules, "google", fake_google)
    monkeypatch.setitem(sys.modules, "google.genai", fake_genai)

    provider = ai_providers.GoogleGeminiProvider(
        api_key="google-test-key",
        model="models/gemini-2.5-flash",
    )

    assert provider.is_available() is True
    assert created["api_key"] == "google-test-key"

    response = provider.generate_response("user prompt", "system prompt")

    assert response == "gemini response"
    assert calls[0]["model"] == "gemini-2.5-flash"
    assert calls[0]["contents"] == "user prompt"
    assert calls[0]["config"] == {
        "temperature": 0.7,
        "max_output_tokens": 1000,
        "system_instruction": "system prompt",
    }

    connection_result = provider.test_connection()

    assert connection_result == {
        "success": True,
        "message": "Подключение успешно",
        "model": "models/gemini-2.5-flash",
        "response_length": len("gemini response"),
    }
    assert calls[1]["model"] == "gemini-2.5-flash"
    assert calls[1]["contents"] == "Test"
    assert calls[1]["config"] == {"max_output_tokens": 5}


def test_google_provider_without_api_key_stays_unconfigured():
    class _Settings:
        GOOGLE_API_KEY = None
        GOOGLE_MODEL = "gemini-2.5-flash"

    provider = ai_providers.GoogleGeminiProvider(settings=_Settings)

    assert provider.is_available() is False
    assert provider.generate_response("prompt") == "Google Gemini провайдер не настроен"
