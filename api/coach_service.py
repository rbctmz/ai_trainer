"""Provider resolution for the coach endpoints.

Reuses the existing AIProviderFactory and env-backed keys. The web layer never
holds its own AI logic — it just picks a provider and calls the shared runtime.
"""
from __future__ import annotations

from typing import Iterator, Optional

from config.settings import Settings
from models.ai_providers import AIProvider, AIProviderFactory, DeepSeekProvider

# Providers exposing an OpenAI-compatible streaming client.
_STREAMABLE = {"DeepSeekProvider", "OpenAIProvider"}

# Friendly aliases the frontend may send (per SPEC_WEB_MIGRATION coach contract).
_ALIASES = {
    "claude": "anthropic",
    "gpt": "openai",
    "gemini": "google",
}

# TD-007 (ASR-PERF-2): deterministic budget for the local, network-free coach
# path (provider="mock"): time from stream start to the first token event.
# Live-provider latency is observed separately and is never gated by this value.
COACH_FIRST_TOKEN_BUDGET_MS = 5000


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


def supports_streaming(provider: AIProvider) -> bool:
    """Whether we can stream tokens live from this provider."""
    return (
        provider.__class__.__name__ in _STREAMABLE
        and getattr(provider, "client", None) is not None
    )


def stream_tokens(
    provider: AIProvider,
    prompt: str,
    system_prompt: str = "",
) -> Iterator[str]:
    """Yield text deltas from an OpenAI-compatible provider (stream=True).

    Mirrors the non-streaming call params in DeepSeekProvider.generate_response.
    """
    client = provider.client
    model = getattr(provider, "model", None)
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    request = {
        "model": model,
        "messages": messages,
        "max_tokens": Settings.AI_RESPONSE_MAX_TOKENS,
        "temperature": 0.7,
        "stream": True,
    }
    if isinstance(provider, DeepSeekProvider):
        # Final synthesis must reserve the output budget for athlete-facing
        # text. Hidden reasoning_content is neither displayed nor persisted.
        request["extra_body"] = {"thinking": {"type": "disabled"}}

    response = client.chat.completions.create(**request)
    for chunk in response:
        choices = getattr(chunk, "choices", None)
        if not choices:
            continue
        delta = getattr(choices[0], "delta", None)
        content = getattr(delta, "content", None) if delta else None
        if content:
            yield content
