"""Smoke coverage for DeepSeek provider wiring."""
from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

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
