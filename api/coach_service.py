"""Provider resolution for the coach endpoints.

Reuses the existing AIProviderFactory and env-backed keys. The web layer never
holds its own AI logic — it just picks a provider and calls the shared runtime.
"""
from __future__ import annotations

from typing import Optional

from config.settings import Settings
from models.ai_providers import AIProvider, AIProviderFactory

# Friendly aliases the frontend may send (per SPEC_WEB_MIGRATION coach contract).
_ALIASES = {
    "claude": "anthropic",
    "gpt": "openai",
    "gemini": "google",
}


def resolve_provider(provider_type: Optional[str] = None) -> Optional[AIProvider]:
    """Return an available provider.

    Priority: explicit request → DEFAULT_AI_PROVIDER → first available
    (incl. Mock as last resort, same as the Streamlit app).
    """
    candidates: list[str] = []
    if provider_type:
        candidates.append(_ALIASES.get(provider_type.lower(), provider_type.lower()))
    if Settings.DEFAULT_AI_PROVIDER:
        candidates.append(Settings.DEFAULT_AI_PROVIDER)

    seen: set[str] = set()
    for ptype in candidates:
        if ptype in seen:
            continue
        seen.add(ptype)
        try:
            provider = AIProviderFactory.create_provider(ptype)
        except Exception:
            continue
        if provider is not None and provider.is_available():
            return provider

    return AIProviderFactory.get_first_available()
