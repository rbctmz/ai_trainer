"""Demo-mode smoke tests for the AI coaching first-run flow."""
from __future__ import annotations

import pytest

from ui.pages import ai_coaching


pytestmark = pytest.mark.smoke


class _DummyCoach:
    def __init__(self, provider):
        self.provider = provider


class _DummyState:
    def __init__(self):
        self.demo_mode = True
        self.selected_provider = "mock"
        self.ai_coach = None


def test_build_provider_options_prioritizes_mock_in_demo_mode():
    provider_options = ai_coaching._build_provider_options(demo_mode=True)

    assert list(provider_options.values())[0] == "mock"
    assert provider_options["Mock AI (Demo)"] == "mock"


def test_resolve_selected_provider_prefers_mock_for_demo_mode():
    provider_options = ai_coaching._build_provider_options(demo_mode=True)

    resolved = ai_coaching._resolve_selected_provider(None, True, provider_options)

    assert resolved == "mock"


def test_ensure_demo_ai_coach_autoconnects_mock(monkeypatch: pytest.MonkeyPatch):
    state = _DummyState()
    created = {}

    class _ProviderFactory:
        @staticmethod
        def create_provider(provider_type, **kwargs):
            created["provider_type"] = provider_type
            created["kwargs"] = kwargs

            class _Provider:
                __name__ = "MockAIProvider"

            provider = _Provider()
            provider.__class__.__name__ = "MockAIProvider"
            return provider

    monkeypatch.setattr(ai_coaching.demo_mode_service, "is_demo_mode", lambda _state: True)

    connected = ai_coaching._ensure_demo_ai_coach(state, _DummyCoach, _ProviderFactory)

    assert connected is True
    assert created["provider_type"] == "mock"
    assert created["kwargs"]["delay"] == 0.0
    assert state.ai_coach is not None
    assert state.ai_coach.provider.__class__.__name__ == "MockAIProvider"


def test_sync_provider_selection_clears_stale_demo_coach():
    state = _DummyState()

    class _Provider:
        __name__ = "MockAIProvider"

    provider = _Provider()
    provider.__class__.__name__ = "MockAIProvider"
    state.ai_coach = _DummyCoach(provider)

    changed = ai_coaching._sync_provider_selection(state, "deepseek")

    assert changed is True
    assert state.selected_provider == "deepseek"
    assert state.ai_coach is None


def test_real_provider_can_autoconnect_on_demo_data(monkeypatch: pytest.MonkeyPatch):
    state = _DummyState()
    state.selected_provider = "deepseek"
    calls = []

    class _ProviderFactory:
        @staticmethod
        def create_provider(provider_type, **kwargs):
            calls.append((provider_type, kwargs))

            class _Provider:
                def is_available(self) -> bool:
                    return True

                def get_model_name(self) -> str:
                    return "DeepSeek deepseek-v4-flash"

            provider = _Provider()
            provider.__class__.__name__ = "DeepSeekProvider"
            return provider

    monkeypatch.setattr(ai_coaching.demo_mode_service, "is_demo_mode", lambda _state: True)

    model_name = ai_coaching._ensure_real_ai_coach(state, _DummyCoach, _ProviderFactory)

    assert model_name == "DeepSeek deepseek-v4-flash"
    assert calls == [("deepseek", {})]
    assert state.ai_coach is not None
    assert state.ai_coach.provider.__class__.__name__ == "DeepSeekProvider"
