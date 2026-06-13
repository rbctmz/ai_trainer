"""AI coaching page renderers and chat helpers."""
from __future__ import annotations

from typing import Optional

import streamlit as st

from models.ai_coach_progress import (
    build_progress_report as _build_progress_report_core,
    is_progress_request as _is_progress_request_core,
    maybe_append_progress_report as _maybe_append_progress_report_core,
)
from models.ai_coach_runtime import (
    create_chat_system_prompt as _create_chat_system_prompt_core,
    create_chat_system_prompt_with_tools as _create_chat_system_prompt_with_tools_core,
    finalize_ai_chat_response as _finalize_ai_chat_response_core,
    generate_ai_chat_response as _generate_ai_chat_response_core,
    process_tool_calls as _process_tool_calls_core,
)
from services import demo_mode as demo_mode_service
from state import StateManager, get_state_manager
from ui.components.ai_coach_chat import (
    apply_ai_chat_styles,
    ensure_ai_chat_context_loaded,
    ensure_ai_chat_session_state,
    render_ai_chat_conversation,
    render_ai_chat_input_bar,
    render_ai_chat_sidebar,
)
from ui.components.ai_coach_entry import (
    _build_ai_coach_explainability_summary,
    _choose_recommended_first_prompt,
    _normalize_ai_coach_handoff,
    _resolve_ai_coach_entry_prompt,
    render_dashboard_handoff,
    render_empty_ai_chat_guidance,
)
from ui.components.ai_coach_output import (
    format_tool_result as _format_tool_result_core,
    simulate_streaming_response as _simulate_streaming_response_core,
    speak_text as _speak_text_core,
)
from ui.components.ai_coach_provider import (
    _build_provider_options,
    _connect_provider,
    _default_provider_kwargs,
    _ensure_demo_ai_coach,
    _ensure_real_ai_coach,
    _provider_matches_selection,
    _render_hidden_api_key_input,
    _resolve_selected_provider,
    _sync_provider_selection,
    render_ai_provider_setup,
    render_ai_provider_status,
)


def render_ai_coaching_page(state: StateManager) -> None:
    """Render the AI coaching page with provider selection and chat."""
    st.header("🤖 AI Коучинг")

    provider_setup = render_ai_provider_setup(state)
    render_ai_provider_status(
        state,
        demo_mode=bool(provider_setup.get("demo_mode", False)),
        auto_connected_model=provider_setup.get("auto_connected_model"),
    )

    if state.ai_coach is None:
        st.warning("👆 Настройте AI провайдера в боковой панели")
        return

    if state.switch_to_chat_tab:
        state.switch_to_chat_tab = False

    render_ai_chat_page(state)


def render_ai_chat_page(state: StateManager) -> None:
    """Render the modern AI chat interface with history and tools."""
    database = state.database
    if state.ai_coach is None:
        st.warning("👆 Настройте AI провайдера для использования чата")
        return

    ensure_ai_chat_session_state(state, database)
    apply_ai_chat_styles()
    context_days = render_ai_chat_sidebar(
        state,
        database,
        create_chat_system_prompt_with_tools,
    )

    st.title("🤖 AI Тренер")
    ensure_ai_chat_context_loaded(state, database, context_days)
    render_ai_chat_conversation(state, process_modern_chat_message)
    render_ai_chat_input_bar(process_modern_chat_message)


def handle_chat_command(command: str, state) -> None:
    """Обрабатывает команды чата (начинающиеся с /)."""
    parts = command.strip().split(maxsplit=1)
    cmd = parts[0].lower()
    args = parts[1] if len(parts) > 1 else ""

    if not state.current_chat_id:
        state.current_chat_id = state.chat_manager.create_new_chat()

    state.chat_manager.add_message(state.current_chat_id, "user", command)

    with st.chat_message("user"):
        st.write(command)

    with st.chat_message("assistant"):
        response = ""

        if cmd == "/speechcore":
            response = handle_speechcore_command(args, state)
        else:
            response = (
                f"❓ Неизвестная команда: `{cmd}`\n\n"
                "Доступные команды:\n- `/speechcore` - Управление речевыми функциями"
            )

        st.markdown(response)
        state.chat_manager.add_message(state.current_chat_id, "assistant", response)

    st.rerun()


def handle_speechcore_command(args: str, state) -> str:
    """Обрабатывает команду /speechcore."""
    args = args.strip().lower()

    if "speechcore_enabled" not in state._session:
        state._session["speechcore_enabled"] = False
    if "speechcore_voice" not in state._session:
        state._session["speechcore_voice"] = "default"

    if args == "" or args == "help" or args == "?":
        enabled_status = "✅ Включен" if state._session.get("speechcore_enabled", False) else "❌ Выключен"
        voice_name = state._session.get("speechcore_voice", "default")
        return f"""🎤 **SpeechCore - Речевые функции AI тренера**

**Доступные команды:**
- `/speechcore` или `/speechcore help` - Показать эту справку
- `/speechcore on` - Включить речевой синтез (озвучивание ответов)
- `/speechcore off` - Выключить речевой синтез
- `/speechcore status` - Показать текущий статус
- `/speechcore voice <имя>` - Выбрать голос (например: `default`, `female`, `male`)

**Текущий статус:**
- Речевой синтез: {enabled_status}
- Голос: `{voice_name}`

**Примечание:** Речевой синтез будет озвучивать ответы AI тренера в чате."""

    elif args == "on" or args == "enable":
        state._session["speechcore_enabled"] = True
        return f"""✅ **Речевой синтез включен**

Ответы AI тренера теперь будут озвучиваться. Голос: `{state._session.get('speechcore_voice', 'default')}`

Используйте `/speechcore off` для отключения."""

    elif args == "off" or args == "disable":
        state._session["speechcore_enabled"] = False
        return """❌ **Речевой синтез выключен**

Ответы AI тренера больше не будут озвучиваться.

Используйте `/speechcore on` для включения."""

    elif args == "status":
        enabled = state._session.get("speechcore_enabled", False)
        voice = state._session.get("speechcore_voice", "default")
        return f"""📊 **Статус SpeechCore**

- Речевой синтез: {'✅ Включен' if enabled else '❌ Выключен'}
- Голос: `{voice}`

Используйте `/speechcore help` для списка команд."""

    elif args.startswith("voice "):
        voice_name = args.replace("voice ", "").strip()
        if voice_name:
            state._session["speechcore_voice"] = voice_name
            return f"""🎙️ **Голос изменен**

Новый голос: `{voice_name}`

Доступные варианты: `default`, `female`, `male`

Используйте `/speechcore on` для включения речевого синтеза."""
        else:
            return """❌ **Ошибка**

Укажите имя голоса. Например: `/speechcore voice female`"""

    else:
        return f"""❓ **Неизвестная подкоманда: `{args}`**

Используйте `/speechcore help` для списка доступных команд."""


def process_modern_chat_message(user_input):
    """Обрабатывает сообщение в современном чате с сохранением."""
    state = get_state_manager()

    if user_input.startswith("/"):
        handle_chat_command(user_input, state)
        return

    if not state.current_chat_id:
        state.current_chat_id = state.chat_manager.create_new_chat()

    if not state.chat_manager.add_message(state.current_chat_id, "user", user_input):
        st.error(f"❌ Не удалось сохранить сообщение пользователя (чат {state.current_chat_id}).")
        return

    with st.chat_message("user"):
        st.write(user_input)

    with st.chat_message("assistant"):
        response_placeholder = st.empty()

        try:
            chat_messages = state.chat_manager.get_chat_messages(state.current_chat_id)
            response_placeholder.markdown("🤖 *Генерирую ответ...*")

            ai_response = _generate_ai_chat_response_core(
                provider=state.ai_coach.provider,
                ai_tools=state.ai_tools,
                user_input=user_input,
                history_messages=chat_messages[:-1],
            )

            response_placeholder.markdown("🔧 *Обрабатываю данные...*")

            final_response = _finalize_ai_chat_response_core(
                ai_response,
                state.ai_tools,
                format_tool_result,
                response_post_processor=lambda response: maybe_append_progress_report(state, user_input, response),
            )

            simulate_streaming_response(response_placeholder, final_response)

            if not state.chat_manager.add_message(state.current_chat_id, "assistant", final_response):
                st.error(f"❌ Не удалось сохранить ответ AI в чат (чат {state.current_chat_id}).")

            if state._session.get("speechcore_enabled", False):
                speak_text(final_response, state._session.get("speechcore_voice", "default"))

            state.selected_page = "🤖 AI Коучинг"
            state.switch_to_chat_tab = True

            st.rerun()

        except Exception as e:
            error_msg = f"❌ Ошибка AI: {e}"
            response_placeholder.markdown(error_msg)
            state.chat_manager.add_message(state.current_chat_id, "assistant", error_msg)


def process_chat_message(user_input):
    """Обрабатывает сообщение пользователя в чате с поддержкой инструментов."""
    state = get_state_manager()
    state.chat_messages.append({"role": "user", "content": user_input})

    with st.chat_message("user"):
        st.write(user_input)

    with st.chat_message("assistant"):
        with st.spinner("AI тренер анализирует данные..."):
            try:
                ai_response = _generate_ai_chat_response_core(
                    provider=state.ai_coach.provider,
                    ai_tools=state.ai_tools,
                    user_input=user_input,
                    history_messages=state.chat_messages[:-1],
                )

                final_response = _finalize_ai_chat_response_core(
                    ai_response,
                    state.ai_tools,
                    format_tool_result,
                    response_post_processor=lambda response: maybe_append_progress_report(state, user_input, response),
                )

                st.markdown(final_response)
                state.chat_messages.append({"role": "assistant", "content": final_response})

            except Exception as e:
                st.error(f"❌ Ошибка AI: {e}")


def create_chat_system_prompt_with_tools(data_context):
    """Создает системный промпт с инструментами для доступа к данным."""
    state = get_state_manager()
    return _create_chat_system_prompt_with_tools_core(state.ai_tools, data_context)


def create_chat_system_prompt(data_context):
    """Создает системный промпт с полным контекстом данных пользователя."""
    return _create_chat_system_prompt_core(data_context)


def process_tool_calls(ai_response):
    """Обрабатывает вызовы инструментов в ответе AI."""
    state = get_state_manager()
    return _process_tool_calls_core(ai_response, state.ai_tools, format_tool_result)


def speak_text(text: str, voice: str = "default"):
    """Озвучивает текст с помощью Web Speech API через JavaScript."""
    _speak_text_core(text, voice=voice)


def simulate_streaming_response(placeholder, text):
    """Симулирует стриминг вывода текста для лучшего UX."""
    _simulate_streaming_response_core(placeholder, text)


def format_tool_result(tool_name, data):
    """Форматирует результат инструмента для красивого отображения."""
    return _format_tool_result_core(tool_name, data)


def is_progress_request(text: Optional[str]) -> bool:
    """Определяет, просит ли пользователь отчёт по прогрессу за месяц."""
    return _is_progress_request_core(text)


def maybe_append_progress_report(state, user_input: Optional[str], final_response: str) -> str:
    """Добавляет отчёт о прогрессе, если пользователь его запрашивал."""
    return _maybe_append_progress_report_core(
        state,
        user_input,
        final_response,
        format_tool_result,
    )


def build_progress_report(state, period_days: int = 30, previous_days: Optional[int] = None) -> Optional[str]:
    """Собирает структурированный отчёт о прогрессе, восстановлении и сне."""
    return _build_progress_report_core(
        state,
        format_tool_result,
        period_days=period_days,
        previous_days=previous_days,
    )


show_ai_coaching = render_ai_coaching_page
show_ai_chat = render_ai_chat_page
