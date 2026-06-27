"""Provider setup helpers for the AI coaching page."""
from __future__ import annotations

from typing import Any, Dict, Optional

import streamlit as st

from config.settings import Settings
from services import demo_mode as demo_mode_service
from state import StateManager


REAL_PROVIDER_TYPES = ("openai", "anthropic", "deepseek", "google", "ollama")
PROVIDER_CLASS_NAMES = {
    "openai": "OpenAIProvider",
    "anthropic": "AnthropicProvider",
    "deepseek": "DeepSeekProvider",
    "google": "GoogleGeminiProvider",
    "ollama": "OllamaProvider",
    "mock": "MockAIProvider",
}


def _render_hidden_api_key_input(label: str, field_key: str, env_value: Optional[str]) -> str:
    """Render a secret input without pre-filling the underlying environment value."""
    typed_value = st.text_input(
        label,
        value="",
        type="password",
        key=field_key,
        placeholder="Введите ключ только если хотите переопределить значение из .env",
    )
    if env_value and not typed_value:
        st.caption("API key из `.env` скрыт в интерфейсе и будет использован автоматически, если поле оставить пустым.")
    return typed_value or env_value or ""


def _build_provider_options(demo_mode: bool) -> Dict[str, str]:
    provider_options = {
        "OpenAI (GPT)": "openai",
        "Anthropic (Claude)": "anthropic",
        "DeepSeek": "deepseek",
        "Google (Gemini)": "google",
        "Ollama (Локально)": "ollama",
        "Mock AI (Demo)": "mock",
    }
    if not demo_mode:
        return provider_options
    return {
        "Mock AI (Demo)": "mock",
        "OpenAI (GPT)": "openai",
        "Anthropic (Claude)": "anthropic",
        "DeepSeek": "deepseek",
        "Google (Gemini)": "google",
        "Ollama (Локально)": "ollama",
    }


def _resolve_selected_provider(
    selected_provider: Optional[str],
    demo_mode: bool,
    provider_options: Dict[str, str],
) -> str:
    valid_providers = set(provider_options.values())
    if selected_provider in valid_providers:
        return selected_provider
    if demo_mode:
        return demo_mode_service.DEMO_PROVIDER
    if Settings.DEFAULT_AI_PROVIDER in valid_providers:
        return Settings.DEFAULT_AI_PROVIDER
    return next(iter(provider_options.values()))


def _ensure_demo_ai_coach(
    state: StateManager,
    coach_class: Any,
    provider_factory: Any,
) -> bool:
    if not demo_mode_service.is_demo_mode(state):
        return False
    if state.selected_provider != demo_mode_service.DEMO_PROVIDER:
        return False

    current_provider = getattr(getattr(state, "ai_coach", None), "provider", None)
    if current_provider is not None and current_provider.__class__.__name__ == "MockAIProvider":
        return False

    provider = provider_factory.create_provider(
        demo_mode_service.DEMO_PROVIDER,
        model="MockGPT-Demo",
        delay=0.0,
    )
    state.ai_coach = coach_class(provider)
    return True


def _provider_matches_selection(state: StateManager, provider_type: str) -> bool:
    """Return whether the current ai_coach provider matches the selected provider type."""
    provider = getattr(getattr(state, "ai_coach", None), "provider", None)
    if provider is None:
        return False
    return provider.__class__.__name__ == PROVIDER_CLASS_NAMES.get(provider_type)


def _sync_provider_selection(state: StateManager, provider_type: str) -> bool:
    """Persist manual provider selection and clear stale providers when it changes."""
    selection_changed = getattr(state, "selected_provider", None) != provider_type
    state.selected_provider = provider_type

    if not selection_changed:
        return False

    if not _provider_matches_selection(state, provider_type):
        state.ai_coach = None

    return True


def _connect_provider(
    state: StateManager,
    coach_class: Any,
    provider_factory: Any,
    provider_type: str,
    provider_kwargs: Dict[str, Any],
) -> Optional[str]:
    """Create and store a provider-backed coach when the provider is available."""
    provider = provider_factory.create_provider(provider_type, **provider_kwargs)
    if not provider.is_available():
        return None

    state.ai_coach = coach_class(provider)
    state.selected_provider = provider_type
    return provider.get_model_name()


def _default_provider_kwargs(provider_type: str) -> Dict[str, Any]:
    if provider_type == "ollama":
        return {
            "host": Settings.OLLAMA_HOST,
            "model": Settings.OLLAMA_MODEL,
        }
    return {}


def _ensure_real_ai_coach(
    state: StateManager,
    coach_class: Any,
    provider_factory: Any,
) -> Optional[str]:
    preferred = state.selected_provider if state.selected_provider in REAL_PROVIDER_TYPES else None
    demo_mode = demo_mode_service.is_demo_mode(state)

    if demo_mode and preferred is None:
        return None

    current_provider = getattr(getattr(state, "ai_coach", None), "provider", None)
    if preferred and current_provider is not None and _provider_matches_selection(state, preferred):
        return None

    if demo_mode:
        ordered_types = [preferred]
    else:
        preferred = preferred or Settings.DEFAULT_AI_PROVIDER
        ordered_types = [preferred] + [provider_type for provider_type in REAL_PROVIDER_TYPES if provider_type != preferred]

    for provider_type in ordered_types:
        connected_model = _connect_provider(
            state,
            coach_class,
            provider_factory,
            provider_type,
            _default_provider_kwargs(provider_type),
        )
        if connected_model:
            return connected_model

    return None


@st.cache_data(ttl=300)
def _get_models_for_provider(provider_type: str, provider_kwargs_items: tuple[tuple[str, Any], ...]) -> list[str]:
    """Fetch the provider-specific model list with a short cache."""
    from models.ai_providers import AIProviderFactory

    try:
        temp_provider = AIProviderFactory.create_provider(
            provider_type,
            **dict(provider_kwargs_items),
        )
        return temp_provider.get_available_models()
    except Exception:
        return []


def render_ai_provider_setup(state: StateManager) -> Dict[str, Any]:
    """Render provider selection and connection controls in the sidebar."""
    from models.ai_coach_universal import UniversalAICoach
    from models.ai_providers import AIProviderFactory

    demo_mode = demo_mode_service.is_demo_mode(state)
    if not getattr(state, "ai_coach", None):
        state.ai_coach = None

    provider_options = _build_provider_options(demo_mode)
    state.selected_provider = _resolve_selected_provider(
        state.selected_provider,
        demo_mode,
        provider_options,
    )
    _ensure_demo_ai_coach(state, UniversalAICoach, AIProviderFactory)
    auto_connected_model = _ensure_real_ai_coach(state, UniversalAICoach, AIProviderFactory)
    selection_auto_connected_model: Optional[str] = None

    with st.sidebar.expander("⚙️ Настройки AI", expanded=True):
        st.subheader("Выбор AI провайдера")
        available = AIProviderFactory.get_available_providers()
        for name, is_available in available.items():
            if is_available:
                st.success(f"✅ {name}")
            else:
                st.error(f"❌ {name}")

        selected_name = st.selectbox(
            "Провайдер:",
            options=list(provider_options.keys()),
            index=list(provider_options.values()).index(state.selected_provider),
        )
        selected_provider = provider_options[selected_name]
        provider_selection_changed = _sync_provider_selection(state, selected_provider)

        provider_kwargs: Dict[str, Any] = {}

        if selected_provider == "openai":
            api_key = _render_hidden_api_key_input(
                "API Key:",
                "openai_api_key_override",
                Settings.OPENAI_API_KEY,
            )
            if api_key:
                with st.spinner("Загрузка списка моделей OpenAI..."):
                    available_models = _get_models_for_provider(
                        "openai",
                        (("api_key", api_key),),
                    )
            else:
                available_models = ["gpt-3.5-turbo", "gpt-4", "gpt-4-turbo-preview"]

            if available_models:
                current_model = Settings.OPENAI_MODEL
                try:
                    default_index = available_models.index(current_model)
                except ValueError:
                    default_index = 0
                model = st.selectbox(
                    f"Модель: ({len(available_models)} доступно)",
                    available_models,
                    index=default_index,
                    help=f"Выберите модель из {len(available_models)} доступных",
                )
            else:
                model = st.text_input("Модель:", value=Settings.OPENAI_MODEL)
                st.warning("⚠️ Не удалось загрузить список моделей. Введите название модели вручную.")
            provider_kwargs = {"api_key": api_key, "model": model}

        elif selected_provider == "anthropic":
            api_key = _render_hidden_api_key_input(
                "API Key:",
                "anthropic_api_key_override",
                Settings.ANTHROPIC_API_KEY,
            )
            available_models = [
                "claude-3-haiku-20240307",
                "claude-3-sonnet-20240229",
                "claude-3-opus-20240229",
                "claude-2.1",
                "claude-2.0",
            ]
            current_model = Settings.ANTHROPIC_MODEL
            try:
                default_index = available_models.index(current_model)
            except ValueError:
                default_index = 0
            model = st.selectbox(
                f"Модель: ({len(available_models)} доступно)",
                available_models,
                index=default_index,
                help="Выберите модель Claude",
            )
            provider_kwargs = {"api_key": api_key, "model": model}

        elif selected_provider == "deepseek":
            api_key = _render_hidden_api_key_input(
                "API Key:",
                "deepseek_api_key_override",
                Settings.DEEPSEEK_API_KEY,
            )
            base_url = st.text_input(
                "Base URL:",
                value=Settings.DEEPSEEK_BASE_URL,
                help="Оставьте стандартный DeepSeek endpoint, если не используете прокси.",
            )
            available_models = [
                "deepseek-v4-flash",
                "deepseek-v4-pro",
                "deepseek-chat",
                "deepseek-reasoner",
            ]
            current_model = Settings.DEEPSEEK_MODEL
            try:
                default_index = available_models.index(current_model)
            except ValueError:
                default_index = 0
            model = st.selectbox(
                f"Модель: ({len(available_models)} доступно)",
                available_models,
                index=default_index,
                help="Для новых подключений предпочтительнее deepseek-v4-flash или deepseek-v4-pro.",
            )
            st.caption("Модели `deepseek-chat` и `deepseek-reasoner` оставлены для совместимости со старыми конфигурациями.")
            provider_kwargs = {"api_key": api_key, "model": model, "base_url": base_url}

        elif selected_provider == "google":
            api_key = _render_hidden_api_key_input(
                "API Key:",
                "google_api_key_override",
                Settings.GOOGLE_API_KEY,
            )
            available_models = [
                "gemini-2.5-flash",
                "gemini-2.5-pro",
                "gemini-2.0-flash",
                "gemini-1.5-flash",
                "gemini-1.5-pro",
            ]
            current_model = Settings.GOOGLE_MODEL.removeprefix("models/")
            try:
                default_index = available_models.index(current_model)
            except ValueError:
                default_index = 0
            model = st.selectbox(
                f"Модель: ({len(available_models)} доступно)",
                available_models,
                index=default_index,
                help="Выберите модель Gemini",
            )
            provider_kwargs = {"api_key": api_key, "model": model}

        elif selected_provider == "ollama":
            host = st.text_input("Host:", value=Settings.OLLAMA_HOST)
            with st.spinner("Загрузка локальных моделей Ollama..."):
                available_models = _get_models_for_provider(
                    "ollama",
                    (("host", host), ("model", "dummy")),
                )
            if available_models:
                current_model = Settings.OLLAMA_MODEL
                try:
                    default_index = available_models.index(current_model)
                except ValueError:
                    default_index = 0
                model = st.selectbox(
                    f"Модель: ({len(available_models)} локальных)",
                    available_models,
                    index=default_index,
                    help=f"Выберите локальную модель из {len(available_models)} установленных",
                )
            else:
                model = st.text_input("Модель:", value=Settings.OLLAMA_MODEL)
                st.warning("⚠️ Не удалось загрузить список моделей Ollama. Убедитесь, что Ollama запущен.")
            provider_kwargs = {"host": host, "model": model}

        elif selected_provider == "mock":
            model = st.selectbox(
                "Режим demo AI:",
                ["MockGPT-Demo", "CoachSim-Recovery", "CoachSim-Planning"],
                index=0,
                help="Локальный demo-провайдер для знакомства с AI коучем без внешнего API ключа.",
            )
            st.caption("Demo AI не требует API ключа и использует встроенные sample-ответы для first-run сценария.")
            provider_kwargs = {"model": model, "delay": 0.0}

        if provider_selection_changed and selected_provider in REAL_PROVIDER_TYPES:
            selection_auto_connected_model = _connect_provider(
                state,
                UniversalAICoach,
                AIProviderFactory,
                selected_provider,
                provider_kwargs,
            )
            auto_connected_model = selection_auto_connected_model or auto_connected_model

        col1, col2 = st.columns(2)
        with col1:
            if st.button("🔍 Тест подключения", help="Проверить API ключ и подключение"):
                try:
                    provider = AIProviderFactory.create_provider(selected_provider, **provider_kwargs)
                    with st.spinner("Проверка подключения..."):
                        test_result = provider.test_connection()
                    if test_result.get("success"):
                        st.success(f"✅ {test_result.get('message')}")
                        with st.expander("📋 Детали подключения"):
                            for key, value in test_result.items():
                                if key not in ["success", "message"]:
                                    st.write(f"**{key}:** {value}")
                    else:
                        st.error(f"❌ {test_result.get('error')}")
                except Exception as exc:
                    st.error(f"❌ Ошибка тестирования: {exc}")
        with col2:
            if st.button("🔌 Подключить AI", help="Подключиться к выбранному провайдеру"):
                try:
                    connected_model = _connect_provider(
                        state,
                        UniversalAICoach,
                        AIProviderFactory,
                        selected_provider,
                        provider_kwargs,
                    )
                    if connected_model:
                        st.success(f"✅ Подключено к {connected_model}")
                        st.info(f"🎯 Выбранная модель: **{provider_kwargs.get('model')}**")
                    else:
                        st.error("❌ Не удалось подключиться к провайдеру")
                except Exception as exc:
                    st.error(f"❌ Ошибка: {exc}")

    return {
        "demo_mode": demo_mode,
        "auto_connected_model": auto_connected_model,
    }


def render_ai_provider_status(
    state: StateManager,
    *,
    demo_mode: bool,
    auto_connected_model: Optional[str],
) -> None:
    """Render a short status message after provider setup."""
    if demo_mode:
        if state.selected_provider == demo_mode_service.DEMO_PROVIDER and _provider_matches_selection(state, demo_mode_service.DEMO_PROVIDER):
            st.info("🎮 В demo-режиме AI коуч уже готов к работе на Mock AI. Вы можете сразу задавать вопросы или переключиться на реальный провайдер вручную.")
        elif auto_connected_model:
            st.success(f"🎮 Demo-данные подключены к реальному AI провайдеру: {auto_connected_model}")
        else:
            st.info("🎮 Вы работаете на demo-данных. После выбора реального провайдера AI будет отвечать по sample dataset через выбранный API.")
    elif auto_connected_model:
        st.success(f"✅ AI коуч подключен автоматически: {auto_connected_model}")


__all__ = [
    "PROVIDER_CLASS_NAMES",
    "REAL_PROVIDER_TYPES",
    "_build_provider_options",
    "_connect_provider",
    "_default_provider_kwargs",
    "_ensure_demo_ai_coach",
    "_ensure_real_ai_coach",
    "_provider_matches_selection",
    "_render_hidden_api_key_input",
    "_resolve_selected_provider",
    "_sync_provider_selection",
    "render_ai_provider_setup",
    "render_ai_provider_status",
]
