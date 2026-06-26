"""Real-provider smoke tests for the AI coaching first-run flow."""
from __future__ import annotations

import pytest

from ui.pages import ai_coaching


pytestmark = pytest.mark.smoke


class _DummyCoach:
    def __init__(self, provider):
        self.provider = provider


class _DummyProvider:
    def __init__(self, available: bool, model_name: str):
        self._available = available
        self._model_name = model_name

    def is_available(self) -> bool:
        return self._available

    def get_model_name(self) -> str:
        return self._model_name


class _DummyState:
    def __init__(self, selected_provider=None, ai_coach=None):
        self.demo_mode = False
        self.selected_provider = selected_provider
        self.ai_coach = ai_coach


def test_real_ai_autoconnects_preferred_provider(monkeypatch: pytest.MonkeyPatch):
    state = _DummyState(selected_provider="openai")
    calls = []

    class _ProviderFactory:
        @staticmethod
        def create_provider(provider_type, **kwargs):
            calls.append((provider_type, kwargs))
            return _DummyProvider(provider_type == "openai", f"{provider_type}-model")

    monkeypatch.setattr(ai_coaching.demo_mode_service, "is_demo_mode", lambda _state: False)

    model_name = ai_coaching._ensure_real_ai_coach(state, _DummyCoach, _ProviderFactory)

    assert model_name == "openai-model"
    assert state.selected_provider == "openai"
    assert state.ai_coach is not None
    assert calls[0][0] == "openai"


def test_real_ai_falls_back_to_first_available_real_provider(monkeypatch: pytest.MonkeyPatch):
    state = _DummyState(selected_provider="openai")
    calls = []

    class _ProviderFactory:
        @staticmethod
        def create_provider(provider_type, **kwargs):
            calls.append(provider_type)
            return _DummyProvider(provider_type == "anthropic", f"{provider_type}-model")

    monkeypatch.setattr(ai_coaching.demo_mode_service, "is_demo_mode", lambda _state: False)

    model_name = ai_coaching._ensure_real_ai_coach(state, _DummyCoach, _ProviderFactory)

    assert model_name == "anthropic-model"
    assert state.selected_provider == "anthropic"
    assert state.ai_coach is not None
    assert calls[:2] == ["openai", "anthropic"]


def test_real_ai_does_not_autoconnect_mock_outside_demo(monkeypatch: pytest.MonkeyPatch):
    state = _DummyState(selected_provider="openai")
    calls = []

    class _ProviderFactory:
        @staticmethod
        def create_provider(provider_type, **kwargs):
            calls.append(provider_type)
            return _DummyProvider(False, f"{provider_type}-model")

    monkeypatch.setattr(ai_coaching.demo_mode_service, "is_demo_mode", lambda _state: False)

    model_name = ai_coaching._ensure_real_ai_coach(state, _DummyCoach, _ProviderFactory)

    assert model_name is None
    assert state.ai_coach is None
    assert "mock" not in calls
