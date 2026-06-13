"""AI coaching page renderers and chat helpers."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import pandas as pd
import streamlit as st

from models.ai_coach_progress import (
    build_progress_report as _build_progress_report_core,
    is_progress_request as _is_progress_request_core,
    maybe_append_progress_report as _maybe_append_progress_report_core,
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
            system_prompt = create_chat_system_prompt_with_tools(state.data_context)

            chat_messages = state.chat_manager.get_chat_messages(state.current_chat_id)
            conversation_history = ""
            for msg in chat_messages[:-1]:
                conversation_history += f"\n{msg['role'].upper()}: {msg['content']}"

            full_prompt = f"""
{system_prompt}

ИСТОРИЯ РАЗГОВОРА:{conversation_history}

НОВЫЙ ВОПРОС ПОЛЬЗОВАТЕЛЯ: {user_input}

Используй инструменты для получения точных данных. ОБЯЗАТЕЛЬНО завершай задачу полностью - если просят план, составляй конкретный план, а не только анализируй данные. Отвечай персонально, конкретно и полезно. Используй эмодзи.
"""

            response_placeholder.markdown("🤖 *Генерирую ответ...*")

            ai_response = state.ai_coach.provider.generate_response(full_prompt, "")

            response_placeholder.markdown("🔧 *Обрабатываю данные...*")

            final_response = process_tool_calls(ai_response)
            final_response = maybe_append_progress_report(state, user_input, final_response)

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
                system_prompt = create_chat_system_prompt_with_tools(state.data_context)

                conversation_history = ""
                for msg in state.chat_messages[:-1]:
                    conversation_history += f"\n{msg['role'].upper()}: {msg['content']}"

                full_prompt = f"""
{system_prompt}

ИСТОРИЯ РАЗГОВОРА:{conversation_history}

НОВЫЙ ВОПРОС ПОЛЬЗОВАТЕЛЯ: {user_input}

Используй инструменты для получения точных данных. ОБЯЗАТЕЛЬНО завершай задачу полностью - если просят план, составляй конкретный план, а не только анализируй данные. Отвечай персонально, конкретно и полезно. Используй эмодзи.
"""

                ai_response = state.ai_coach.provider.generate_response(full_prompt, "")

                final_response = process_tool_calls(ai_response)
                final_response = maybe_append_progress_report(state, user_input, final_response)

                st.markdown(final_response)
                state.chat_messages.append({"role": "assistant", "content": final_response})

            except Exception as e:
                st.error(f"❌ Ошибка AI: {e}")


def create_chat_system_prompt_with_tools(data_context):
    """Создает системный промпт с инструментами для доступа к данным."""
    state = get_state_manager()

    base_prompt = """
Ты — персональный AI тренер по выносливости с глубокими знаниями спортивной науки.

У тебя есть доступ к мощным инструментам для анализа данных пользователя. Используй их для получения точной, актуальной информации.

ТВОИ ПРИНЦИПЫ:
• ВСЕГДА используй инструменты для получения конкретных данных
• ВСЕГДА завершай задачу полностью - не останавливайся на анализе
• Давай персонализированные, научно обоснованные советы
• Объясняй сложные концепции простым языком
• Предупреждай о рисках перетренированности и травм
• Поощряй постепенное развитие и терпение

ТВОИ ЭКСПЕРТИЗЫ:
• Анализ тренировочной нагрузки (TSS, CTL, ATL, TSB)
• Интерпретация HRV и состояния восстановления
• Планирование тренировок и периодизация
• Физиология выносливости и адаптации
• Предотвращение перетренированности

СТИЛЬ ОБЩЕНИЯ:
• Дружелюбный и мотивирующий
• Используй эмодзи для лучшего восприятия
• Структурируй ответы с заголовками и списками
• Будь конкретным с цифрами и фактами

ДАННЫЕ И ИНСТРУМЕНТЫ:
• Для запросов о шагах, калориях или ЧСС покоя ОБЯЗАТЕЛЬНО сначала вызывай инструмент **get_daily_health_stats** (укажи days при необходимости)
• Для readiness, VO₂max и статусов Garmin ОБЯЗАТЕЛЬНО сначала применяй **get_training_status** (для конкретных дат) или **analyze_training_status**
• Если вопрос требует период/дату, вызывай инструмент с параметром days/start/end, а затем цитируй фактические значения из результата
• Метрики CTL/ATL/TSB и анализ нагрузки получай через соответствующие инструменты, вместо общих оценок
• Если данных нет, явно сообщай об этом пользователю
"""

    tools_description = state.ai_tools.format_tool_descriptions_for_ai()

    return f"{base_prompt}\n\n{tools_description}"


def create_chat_system_prompt(data_context):
    """Создает системный промпт с полным контекстом данных пользователя."""
    from models.ai_data_context import AIDataContext

    base_prompt = """
Ты — персональный AI тренер по выносливости с глубокими знаниями спортивной науки.

У тебя есть полный доступ к данным пользователя и ты должен давать персонализированные, научно обоснованные советы.

ТВОИ ПРИНЦИПЫ:
• Всегда основывайся на предоставленных данных пользователя
• Объясняй сложные концепции простым языком
• Давай конкретные, практические рекомендации
• Учитывай индивидуальные особенности и текущее состояние
• Предупреждай о рисках перетренированности и травм
• Поощряй постепенное развитие и терпение

ТВОИ ЭКСПЕРТИЗЫ:
• Анализ тренировочной нагрузки (TSS, CTL, ATL, TSB)
• Интерпретация HRV и состояния восстановления
• Планирование тренировок и периодизация
• Физиология выносливости и адаптации
• Предотвращение перетренированности
• Техника и тактика в видах спорта на выносливость

СТИЛЬ ОБЩЕНИЯ:
• Дружелюбный и мотивирующий
• Используй эмодзи для лучшего восприятия
• Структурируй ответы с заголовками и списками
• Будь конкретным, но не перегружай деталями
• Адаптируй сложность под уровень пользователя
"""

    if not data_context or not data_context["summary"]["has_data"]:
        return (
            base_prompt
            + "\n\nВНИМАНИЕ: У пользователя нет данных тренировок. Давай общие рекомендации и объясни, как начать отслеживание тренировок."
        )

    context_formatter = AIDataContext(None)
    formatted_context = context_formatter.format_context_for_ai(data_context)

    return f"{base_prompt}\n\n{formatted_context}"


def process_tool_calls(ai_response):
    """Обрабатывает вызовы инструментов в ответе AI."""
    import re

    state = get_state_manager()

    tool_pattern = r"\[TOOL:\s*([^,\]]+)(?:,\s*([^\]]*))?\]"

    def replace_tool_call(match):
        tool_name = match.group(1).strip()
        params_str = match.group(2).strip() if match.group(2) else ""

        params = {}
        if params_str:
            param_pairs = [p.strip() for p in params_str.split(",")]
            for pair in param_pairs:
                if "=" in pair:
                    key, value = pair.split("=", 1)
                    key = key.strip()
                    value = value.strip()

                    if value.isdigit():
                        params[key] = int(value)
                    elif value.replace(".", "").isdigit():
                        params[key] = float(value)
                    else:
                        params[key] = value.strip("\"'")

        try:
            result = state.ai_tools.execute_tool(tool_name, **params)

            if result.get("success"):
                data = result["result"]
                formatted_result = format_tool_result(tool_name, data)
                return formatted_result
            else:
                return f"❌ Ошибка инструмента: {result.get('error', 'Неизвестная ошибка')}"

        except Exception as e:
            return f"❌ Ошибка выполнения {tool_name}: {str(e)}"

    processed_response = re.sub(tool_pattern, replace_tool_call, ai_response)
    return processed_response


def speak_text(text: str, voice: str = "default"):
    """Озвучивает текст с помощью Web Speech API через JavaScript."""
    import json
    import re

    clean_text = text
    clean_text = re.sub(r"^#+\s+", "", clean_text, flags=re.MULTILINE)
    clean_text = re.sub(r"\*\*(.+?)\*\*", r"\1", clean_text)
    clean_text = re.sub(r"\*(.+?)\*", r"\1", clean_text)
    clean_text = re.sub(r"`(.+?)`", r"\1", clean_text)
    clean_text = re.sub(r"\[(.+?)\]\(.+?\)", r"\1", clean_text)

    if len(clean_text) > 500:
        clean_text = clean_text[:500] + "..."

    clean_text_escaped = json.dumps(clean_text, ensure_ascii=False)

    js_code = f"""
    <script>
    (function() {{
        if ('speechSynthesis' in window) {{
            window.speechSynthesis.cancel();

            function speak() {{
                const utterance = new SpeechSynthesisUtterance({clean_text_escaped});
                utterance.lang = 'ru-RU';
                utterance.rate = 1.0;
                utterance.pitch = 1.0;
                utterance.volume = 1.0;

                const voices = window.speechSynthesis.getVoices();
                if (voices.length > 0) {{
                    let selectedVoice = voices.find(v => v.lang.startsWith('ru'));
                    if (!selectedVoice) {{
                        selectedVoice = voices[0];
                    }}
                    utterance.voice = selectedVoice;
                }}

                window.speechSynthesis.speak(utterance);
            }}

            if (window.speechSynthesis.getVoices().length > 0) {{
                speak();
            }} else {{
                window.speechSynthesis.onvoiceschanged = speak;
            }}
        }} else {{
            console.warn('Speech synthesis not supported');
        }}
    }})();
    </script>
    """

    import streamlit.components.v1 as components

    components.html(js_code, height=0)


def simulate_streaming_response(placeholder, text):
    """Симулирует стриминг вывода текста для лучшего UX."""
    import re
    import time

    if len(text) <= 100:
        placeholder.markdown(text)
        return

    sentences = re.split(r"(?<=[.!?])\s+|(?<=\n)(?=\n)|(?<=:)\n", text)
    current_text = ""

    for i, sentence in enumerate(sentences):
        current_text += sentence

        if i < len(sentences) - 1:
            display_text = current_text + " ▋"
        else:
            display_text = current_text

        placeholder.markdown(display_text)

        if len(sentence) > 50:
            time.sleep(0.25)
        elif len(sentence) > 20:
            time.sleep(0.12)
        else:
            time.sleep(0.04)

    placeholder.markdown(current_text)


def format_tool_result(tool_name, data):
    """Форматирует результат инструмента для красивого отображения."""
    if tool_name == "get_performance_metrics":
        tsb_emoji = "🟢" if data["tsb"] > 5 else "🟡" if data["tsb"] > -10 else "🟠" if data["tsb"] > -25 else "🔴"

        return f"""
## 📊 Текущие метрики производительности

### 🎯 Модель Банистера:
• **CTL** (хроническая нагрузка): **{data['ctl']:.1f}** 📈
• **ATL** (острая нагрузка): **{data['atl']:.1f}** ⚡
• **TSB** (баланс стресса): **{data['tsb']:+.1f}** {tsb_emoji}

### 🏃‍♂️ Анализ формы:
• **Текущая форма:** {data['form_state']}
• **Тренд фитнеса:** {data['fitness_trend']}
"""

    elif tool_name == "get_recent_activities":
        if data["count"] == 0:
            return "📭 **Нет недавних активностей**"

        sport_emojis = {
            "cycling": "🚴",
            "running": "🏃",
            "swimming": "🏊",
            "open_water_swimming": "🏊‍♂️",
            "walking": "🚶",
        }

        activities_text = f"## 🏃‍♂️ Последние {min(5, data['count'])} тренировок:\n\n"
        for i, activity in enumerate(data["activities"][:5], 1):
            sport = activity.get("sport", "unknown")
            emoji = sport_emojis.get(sport, "⚡")
            description = activity.get("description", f"{sport} - {activity.get('duration_minutes', 0):.0f}мин")
            activities_text += f"{i}. **{activity['date']}** {emoji} {description}\n"

        return activities_text

    elif tool_name == "get_activities":
        count = data.get("count", 0)
        period = data.get("period_days")
        activities = data.get("activities") or []

        if count == 0 or not activities:
            period_text = f"за {period} дней" if period is not None else ""
            return f"📭 **Нет тренировок {period_text}**"

        total_tss = sum(float(a.get("tss", 0) or 0) for a in activities)
        total_duration = sum(float(a.get("duration_minutes", 0) or 0) for a in activities)

        header = f"## 🏃‍♂️ Тренировки за {period} дней\n\n"
        summary = (
            f"- Всего занятий: **{count}**\n"
            f"- Суммарный TSS: **{total_tss:.0f}**\n"
            f"- Общее время: **{total_duration/60:.1f} ч**\n\n"
        )

        sport_emojis = {
            "cycling": "🚴",
            "running": "🏃",
            "swimming": "🏊",
            "open_water_swimming": "🏊‍♂️",
            "walking": "🚶",
            "strength": "💪",
        }

        rows = []
        for activity in activities[:7]:
            date = activity.get("date", "N/A")
            sport = activity.get("sport", "unknown")
            emoji = sport_emojis.get(sport.lower(), "⚡") if isinstance(sport, str) else "⚡"
            duration = activity.get("duration_minutes", 0) or 0
            tss = activity.get("tss", 0) or 0
            description = activity.get("description")
            if not description:
                description = f"{sport} — {duration:.0f} мин, TSS {tss:.0f}"
            rows.append(f"| {date} | {emoji} {description} |")

        table_header = "| Дата | Сессия |\n| --- | --- |\n"
        table_body = "\n".join(rows)

        return header + summary + table_header + table_body

    elif tool_name == "analyze_hrv_trends":
        recovery_emoji = {"отличное": "🟢", "хорошее": "🟡", "удовлетворительное": "🟠", "плохое": "🔴"}
        trend_emoji = {"improving": "📈", "declining": "📉"}

        return f"""
**💓 Анализ HRV:**
• Текущий RMSSD: {data['current_rmssd']:.1f} мс
• Среднее за 7 дней: {data['recent_avg_7days']:.1f} мс
• Базовый уровень: {data['baseline_median']:.1f} мс
• Тренд: {trend_emoji.get(data['trend_direction'], '')} {data['trend_direction']}
• Восстановление: {recovery_emoji.get(data['recovery_state'], '')} {data['recovery_state']}
"""

    elif tool_name == "get_activity_stats":
        return f"""
**📈 Статистика тренировок за {data['period_days']} дней:**
• Всего тренировок: {data['total_activities']}
• Общее время: {data['total_duration_hours']:.1f} ч
• Общий TSS: {data['total_tss']:.0f}
• Частота: {data['activities_per_week']:.1f} раз в неделю
• Средний TSS: {data['avg_tss_per_session']:.1f}
"""

    elif tool_name == "compare_periods":
        message = data.get("message")
        period2 = data.get("period2_days")

        if message:
            fallback = data.get("fallback", {})
            summary_lines = [f"### {message}"]

            recent_stats = fallback.get("recent_activity_stats")
            if isinstance(recent_stats, dict):
                summary_lines.append(
                    f"- Последний период: {recent_stats.get('total_activities', 0)} тренировок, "
                    f"{recent_stats.get('total_duration_hours', 0):.1f} ч, TSS {recent_stats.get('total_tss', 0):.0f}"
                )

            load_summary = fallback.get("training_load")
            if isinstance(load_summary, dict):
                summary_lines.append(f"- Тренд нагрузки: {load_summary.get('load_trend', 'н/д')}")

            summary_lines.append("Попробуй обновить данные, чтобы сравнить периоды заново.")

            return "## 📈 Прогресс за период\n\n" + "\n".join(summary_lines)

        recent = data.get("recent_period", {}) or {}
        previous = data.get("previous_period", {}) or {}
        comparison = data.get("comparison", {}) or {}

        def fmt_hours(minutes: float) -> str:
            return f"{(minutes or 0) / 60:.1f} ч"

        def fmt_delta(value: Optional[float], unit: str = "", precision: int = 0) -> str:
            if value is None:
                return "0"
            sign = "+" if value > 0 else ""
            formatted = f"{sign}{value:.{precision}f}" if precision > 0 else f"{sign}{int(value)}"
            return f"{formatted}{unit}"

        def arrow(value: Optional[float]) -> str:
            if value is None:
                return "→"
            if value > 0:
                return "↑"
            if value < 0:
                return "↓"
            return "→"

        recent_duration = recent.get("total_duration", 0.0)
        previous.get("total_duration", 0.0)
        volume_change = comparison.get("volume_change")
        duration_change_hours = (volume_change or 0) / 60 if volume_change is not None else None

        summary_block = [
            "## 📈 Прогресс за период",
            "",
            "**Итоги текущего периода**",
            f"- Тренировок: **{recent.get('activity_count', 0)}**",
            f"- Общее время: **{fmt_hours(recent_duration)}**",
            f"- Суммарный TSS: **{recent.get('total_tss', 0):.0f}**",
            f"- Частота: **{recent.get('activities_per_week', 0):.1f} / нед**",
        ]

        if not previous.get("no_data"):
            summary_block.extend(
                [
                    "",
                    f"**Динамика vs предыдущие {period2 or 'предыдущие'} дней**",
                    f"- Тренировок: {comparison.get('activity_count_change', 0):+d} {arrow(comparison.get('activity_count_change'))}",
                    f"- Объём: {fmt_delta(duration_change_hours, ' ч', 1)} {arrow(duration_change_hours)}",
                    f"- TSS: {fmt_delta(comparison.get('tss_change'), '', 0)} {arrow(comparison.get('tss_change'))}",
                ]
            )
        else:
            summary_block.append("\nНет данных для сравнения с предыдущим периодом.")

        return "\n".join(summary_block)

    elif tool_name == "analyze_training_load":
        if data.get("message"):
            return f"ℹ️ **{data['message']}**"

        intensity = data.get("intensity_distribution", {})
        weekly = data.get("weekly_breakdown", []) or []

        intensity_lines = (
            [
                f"- Низкая: {intensity.get('low_intensity_percent', 0):.1f}%",
                f"- Умеренная: {intensity.get('moderate_intensity_percent', 0):.1f}%",
                f"- Высокая: {intensity.get('high_intensity_percent', 0):.1f}%",
            ]
            if intensity
            else ["- Нет данных по зонам интенсивности"]
        )

        if weekly:
            table_rows = [
                "| Неделя | Сессий | TSS | Часы |",
                "| --- | --- | --- | --- |",
            ]
            for week in weekly[:4]:
                hours = (week.get("total_duration", 0) or 0) / 60
                table_rows.append(
                    f"| {week.get('week', '—')} | {week.get('session_count', 0)} | "
                    f"{week.get('total_tss', 0):.0f} | {hours:.1f} |"
                )
            weekly_section = "\n".join(table_rows)
        else:
            weekly_section = "Нет разбивки по неделям."

        return f"""
## 📊 Анализ тренировочной нагрузки

### ⚙️ Распределение интенсивности:
{chr(10).join(intensity_lines)}

### 📅 Недельная разбивка:
{weekly_section}
"""

    elif tool_name == "analyze_recovery_state":
        factors = data.get("factors", [])
        hrv_data = data.get("hrv", {})
        training_load = data.get("training_load", {})

        hrv_section = ""
        if hrv_data:
            current_rmssd = hrv_data.get("current_rmssd", 0)
            baseline_rmssd = hrv_data.get("baseline_rmssd", 0)
            deviation = hrv_data.get("deviation_percent", 0)

            if deviation > 10:
                hrv_emoji = "🟢"
                hrv_status = "отличное"
            elif deviation > -5:
                hrv_emoji = "🟡"
                hrv_status = "хорошее"
            elif deviation > -15:
                hrv_emoji = "🟠"
                hrv_status = "удовлетворительное"
            else:
                hrv_emoji = "🔴"
                hrv_status = "требует внимания"

            hrv_section = f"""
### 💓 HRV Анализ:
• **Текущий RMSSD:** {current_rmssd:.1f} мс {hrv_emoji}
• **Базовый уровень:** {baseline_rmssd:.1f} мс
• **Отклонение:** {deviation:+.1f}% ({hrv_status})"""

        load_section = ""
        if training_load:
            week_tss = training_load.get("week_tss", 0)
            session_count = training_load.get("session_count", 0)
            avg_tss = training_load.get("avg_tss_per_session", 0)

            if week_tss > 400:
                load_emoji = "🔴"
                load_status = "высокая"
            elif week_tss > 250:
                load_emoji = "🟡"
                load_status = "умеренная"
            else:
                load_emoji = "🟢"
                load_status = "низкая"

            load_section = f"""
### ⚡ Недельная нагрузка:
• **TSS за неделю:** {week_tss:.0f} {load_emoji} ({load_status})
• **Тренировок:** {session_count}
• **Средний TSS:** {avg_tss:.1f}"""

        factors_section = ""
        if factors:
            factors_section = f"""
### 🎯 Анализ и рекомендации:
{chr(10).join([f"• {factor}" for factor in factors[:5]])}"""

        return f"""
## 🔋 Анализ состояния восстановления
{hrv_section}
{load_section}
{factors_section}"""

    elif tool_name == "get_training_status":
        if not isinstance(data, dict):
            return f"ℹ️ **{data}**"
        if data.get("message"):
            return f"ℹ️ **{data['message']}**"

        latest = data.get("latest", {})
        summary = data.get("summary", {})

        def fmt_number(value, fmt: str = ".1f", default: str = "н/д"):
            if value is None:
                return default
            try:
                if pd.isna(value):
                    return default
                return format(float(value), fmt)
            except (TypeError, ValueError):
                return default

        status_distribution = summary.get("status_distribution", {})
        distribution_lines = [f"• {status}: {count}" for status, count in list(status_distribution.items())[:5]] if status_distribution else ["• Нет статистики по статусам"]

        history = data.get("history", [])
        readiness_rows = []
        for entry in history:
            readiness = entry.get("training_readiness")
            date_value = entry.get("date")
            if isinstance(date_value, str):
                date_str = date_value
            elif hasattr(date_value, "strftime"):
                date_str = date_value.strftime("%Y-%m-%d")
            else:
                date_str = str(date_value)
            if readiness is not None and not (hasattr(pd, "isna") and pd.isna(readiness)):
                readiness_rows.append((date_str, readiness))
        readiness_rows = readiness_rows[:7]
        if readiness_rows:
            readiness_table = "\n".join([f"| {date} | {fmt_number(value, '.0f')} / 100 |" for date, value in readiness_rows])
            readiness_block = f"""
### 📅 Readiness по датам:
| Дата | Readiness |
| --- | --- |
{readiness_table}
"""
        else:
            readiness_block = "\n### 📅 Readiness по датам:\n• Нет данных по дням\n"

        return f"""
## 📈 Статус тренированности (последние {data.get('period_days', 30)} дней)

### 🔝 Последний статус:
• Статус Garmin: {latest.get('training_status', 'н/д')}
• Readiness: {fmt_number(latest.get('training_readiness'), '.0f')} / 100
• Нагрузка 7 дней: {fmt_number(latest.get('training_load_7d'), '.0f')}
• VO₂max: {fmt_number(latest.get('vo2_max'), '.1f')}

### 📊 Средние значения:
• Readiness: {fmt_number(summary.get('avg_training_readiness'), '.1f')} / 100
• Нагрузка (7д): {fmt_number(summary.get('avg_training_load_7d'), '.1f')}
• VO₂max: {fmt_number(summary.get('avg_vo2_max'), '.1f')}

### 🧭 Распределение статусов:
{chr(10).join(distribution_lines)}
{readiness_block}
"""

    elif tool_name == "analyze_training_status":
        if not isinstance(data, dict):
            return f"ℹ️ **{data}**"
        if data.get("message"):
            return f"ℹ️ **{data['message']}**"

        insights = data.get("insights", [])
        latest = data.get("latest", {})
        readiness = data.get("readiness_assessment", {})
        load = data.get("load_assessment", {})

        def fmt_section(section: Dict[str, Any], default: str) -> str:
            lines = [value for value in section.values() if isinstance(value, str)]
            return chr(10).join([f"• {line}" for line in lines]) if lines else default

        return f"""
## 🧠 Анализ статуса тренированности

### 🔝 Последний статус:
• {latest.get('summary', 'Нет данных')}

### 💡 Ключевые выводы:
{chr(10).join([f"• {item}" for item in insights]) if insights else "• Нет выводов — недостаточно данных"}

### 📈 Readiness:
{fmt_section(readiness, "• Недостаточно данных по readiness")}

### ⚙️ Нагрузка:
{fmt_section(load, "• Недостаточно данных по нагрузке")}
"""

    elif tool_name == "get_daily_health_stats":
        if not isinstance(data, dict):
            return f"ℹ️ **{data}**"
        if data.get("message"):
            return f"ℹ️ **{data['message']}**"

        stats = data.get("stats", {})
        trend = data.get("trend_steps", "н/д")
        recent = data.get("recent_entries", [])

        def fmt_number(value, fmt: str = ".1f", default: str = "н/д"):
            if value is None:
                return default
            try:
                if pd.isna(value):
                    return default
                return format(float(value), fmt)
            except (TypeError, ValueError):
                return default

        recent_lines = []
        for entry in recent[:5]:
            date = entry.get("date")
            steps = fmt_number(entry.get("steps"), ".0f")
            resting_hr = fmt_number(entry.get("resting_hr"), ".0f")
            active_minutes = fmt_number(entry.get("active_minutes"), ".0f")
            recent_lines.append(f"• {date}: шаги {steps}, ЧСС покоя {resting_hr}, активность {active_minutes} мин")

        return f"""
## 🏥 Ежедневные показатели здоровья ({data.get('period_days', 30)} дней)

### 📊 Средние значения:
• Шаги: {fmt_number(stats.get('avg_steps'), '.0f')} в день
• ЧСС покоя: {fmt_number(stats.get('avg_resting_hr'), '.1f')} уд/мин
• Активные минуты: {fmt_number(stats.get('avg_active_minutes'), '.1f')} мин/день
• Активные калории: {fmt_number(stats.get('avg_calories_active'), '.0f')} ккал/день

### 📈 Тренд шагов: {trend}

### 🗓️ Последние дни:
{chr(10).join(recent_lines) if recent_lines else "• Нет свежих записей"}
"""

    elif tool_name == "get_activities_by_date_range":
        if data["count"] == 0:
            return f"📭 **Нет тренировок в период {data['period']}**"

        stats = data["statistics"]

        sport_emojis = {
            "cycling": "🚴",
            "running": "🏃",
            "swimming": "🏊",
            "open_water_swimming": "🏊‍♂️",
            "walking": "🚶",
            "strength": "💪",
            "yoga": "🧘",
            "other": "⚡",
        }

        sports_text = []
        for sport, count in stats["sports_distribution"].items():
            emoji = sport_emojis.get(sport, "⚡")
            sports_text.append(f"{emoji} {sport}: {count}")

        activities_preview = ""
        if "activities" in data and data["activities"]:
            activities_preview = "\n\n**📋 Некоторые тренировки:**"
            for i, activity in enumerate(data["activities"][:5], 1):
                sport_emoji = sport_emojis.get(activity["sport"], "⚡")
                date_formatted = activity["date"]
                activities_preview += (
                    f"\n{i}. **{date_formatted}** {sport_emoji} {activity['sport']} - "
                    f"{activity['duration_minutes']:.0f}мин (TSS: {activity['tss']:.0f})"
                )

        return f"""
## 📊 Тренировки за период {data['period']}

### 📈 Основная статистика:
• **🏃‍♂️ Всего тренировок: {data['count']}**
• **⏱️ Общее время: {stats['total_duration_hours']:.1f} часов**
• **📈 Общий TSS: {stats['total_tss']:.0f}**
• **🎯 Средний TSS: {stats['avg_tss_per_session']:.1f}**
• **🏃 Дистанция: {stats['total_distance_km']:.1f} км**

### 🏆 Виды активности:
{chr(10).join([f"• {sport}" for sport in sports_text])}
{activities_preview}"""

    elif tool_name == "get_sleep_data":
        if not data.get("has_data", True):
            return f"😴 **{data.get('message', 'Нет данных сна')}**"

        recent_sleep = data.get("recent_sleep", [])
        if recent_sleep:
            total_hours = []
            sleep_scores = []
            for record in recent_sleep:
                if record.get("total_sleep_hours") is not None:
                    total_hours.append(record["total_sleep_hours"])
                if record.get("sleep_score") is not None:
                    sleep_scores.append(record["sleep_score"])

            avg_hours = sum(total_hours) / len(total_hours) if total_hours else 0
            avg_score = sum(sleep_scores) / len(sleep_scores) if sleep_scores else 0

            latest_sleep = recent_sleep[0] if recent_sleep else {}
            recent_summary = f"Продолжительность: {latest_sleep.get('total_sleep_hours', 'н/д')}ч, "
            recent_summary += f"Качество: {latest_sleep.get('sleep_score', 'н/д')}/100, "
            recent_summary += f"Эффективность: {latest_sleep.get('sleep_efficiency', 'н/д')}%"
        else:
            avg_hours = 0
            avg_score = 0
            recent_summary = "Данные недоступны"

        return f"""
## 😴 Данные сна за последние {data.get('period_days', 30)} дней

### 📊 Основная информация:
• **Всего записей:** {data.get('data_points', 0)}
• **Среднее время сна:** {avg_hours:.1f} часов
• **Средняя оценка сна:** {avg_score:.1f}/100

### 🌙 Последний сон:
{recent_summary}"""

    elif tool_name == "get_sleep_stats":
        if not data.get("has_data", True):
            return f"😴 **{data.get('message', 'Нет данных сна')}**"

        stats = data.get("statistics", {})
        quality = stats.get("current_sleep_quality", "не определено")

        quality_emoji = "🟢" if "отличное" in quality.lower() else "🟡" if "хорошее" in quality.lower() else "🟠" if "удовлетворительное" in quality.lower() else "🔴"

        avg_total = stats.get("avg_sleep_hours", 0) * 60
        deep_pct = (stats.get("avg_deep_sleep_minutes", 0) / avg_total * 100) if avg_total > 0 else 0
        rem_pct = (stats.get("avg_rem_sleep_minutes", 0) / avg_total * 100) if avg_total > 0 else 0
        light_pct = 100 - deep_pct - rem_pct if (deep_pct + rem_pct) <= 100 else 0

        return f"""
## 😴 Статистика сна за {stats.get('period_days', 30)} дней

### 🎯 Общая оценка: {quality_emoji} {quality}

### 📈 Средние показатели:
• **Продолжительность:** {stats.get('avg_sleep_hours', 0):.1f} часов
• **Качество сна:** {stats.get('avg_sleep_score', 0):.1f}/100
• **Эффективность:** {stats.get('avg_sleep_efficiency', 0):.1f}%
• **Пробуждения:** {stats.get('avg_awakenings', 0):.1f} раз за ночь

### 🌀 Фазы сна:
• **Глубокий сон:** {stats.get('avg_deep_sleep_minutes', 0):.0f} мин ({deep_pct:.1f}%)
• **Легкий сон:** Расчетное ({light_pct:.1f}%)
• **REM сон:** {stats.get('avg_rem_sleep_minutes', 0):.0f} мин ({rem_pct:.1f}%)"""

    elif tool_name == "analyze_sleep_patterns":
        if not data.get("has_data", True):
            return f"😴 **{data.get('message', 'Нет данных для анализа сна')}**"

        patterns = data.get("patterns", {})
        recommendations = patterns.get("recommendations", [])

        main_patterns = []
        if patterns.get("avg_sleep_duration"):
            main_patterns.append(f"• **Средняя продолжительность:** {patterns['avg_sleep_duration']}")
        if patterns.get("sleep_consistency"):
            main_patterns.append(f"• **Постоянство сна:** {patterns['sleep_consistency']}")
        if patterns.get("optimal_sleep_adherence"):
            main_patterns.append(f"• **Следование рекомендациям:** {patterns['optimal_sleep_adherence']}")

        quality_trends = []
        if patterns.get("avg_sleep_score"):
            quality_trends.append(f"• **Средняя оценка качества:** {patterns['avg_sleep_score']}")
        if patterns.get("sleep_trend"):
            quality_trends.append(f"• **Тренд:** {patterns['sleep_trend']}")

        phases_text = []
        if patterns.get("deep_sleep_percentage"):
            phases_text.append(f"• **Глубокий сон:** {patterns['deep_sleep_percentage']}")
        if patterns.get("rem_sleep_percentage"):
            phases_text.append(f"• **REM сон:** {patterns['rem_sleep_percentage']}")

        recommendations_text = ""
        if recommendations:
            recommendations_text = f"""
### 💡 Рекомендации:
{chr(10).join([f"• {rec}" for rec in recommendations[:5]])}"""

        return f"""
## 😴 Анализ паттернов сна за {data.get('period_days', 30)} дней

### 📊 Основные паттерны:
{chr(10).join(main_patterns) if main_patterns else "• Недостаточно данных для анализа"}

### 📈 Качество и тренды:
{chr(10).join(quality_trends) if quality_trends else "• Данные о качестве недоступны"}

### 🌀 Фазы сна:
{chr(10).join(phases_text) if phases_text else "• Данные о фазах недоступны"}
{recommendations_text}"""

    else:
        if isinstance(data, dict):
            if "message" in data:
                return f"ℹ️ **{data['message']}**"
            elif "error" in data:
                return f"❌ **Ошибка:** {data['error']}"

            result_text = f"## 📊 Результат: {tool_name.replace('_', ' ').title()}\n\n"

            important_keys = ["count", "total_tss", "period_days", "current_rmssd"]
            other_keys = [k for k in data.keys() if k not in important_keys and not k.startswith("_")]

            for key in important_keys:
                if key in data:
                    result_text += f"• **{key.replace('_', ' ').title()}:** {data[key]}\n"

            for key in other_keys[:10]:
                value = data[key]
                if isinstance(value, (dict, list)) and len(str(value)) > 100:
                    result_text += f"• **{key.replace('_', ' ').title()}:** [данные доступны]\n"
                else:
                    result_text += f"• **{key.replace('_', ' ').title()}:** {value}\n"

            return result_text
        else:
            return f"**📊 {tool_name.replace('_', ' ').title()}:** {str(data)}"


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
