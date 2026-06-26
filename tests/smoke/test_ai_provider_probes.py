"""Smoke tests for quiet AI provider availability probes."""
from __future__ import annotations

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
