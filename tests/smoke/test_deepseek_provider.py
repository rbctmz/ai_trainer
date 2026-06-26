"""Smoke coverage for DeepSeek provider wiring."""
from __future__ import annotations

import sys

import pytest

from models import ai_providers
from ui.pages import ai_coaching


pytestmark = pytest.mark.smoke


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
