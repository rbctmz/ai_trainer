"""Runtime helpers for the AI coaching execution pipeline."""
from __future__ import annotations

import re
from typing import Any, Callable, Dict, Iterable, Optional

from models.ai_data_context import AIDataContext


def create_chat_system_prompt_with_tools(ai_tools: Any, data_context: Any = None) -> str:
    """Создает системный промпт с инструментами для доступа к данным."""
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

    tools_description = ""
    if ai_tools is not None and hasattr(ai_tools, "format_tool_descriptions_for_ai"):
        tools_description = ai_tools.format_tool_descriptions_for_ai()

    return f"{base_prompt}\n\n{tools_description}".rstrip()


def create_chat_system_prompt(data_context: Any) -> str:
    """Создает системный промпт с полным контекстом данных пользователя."""
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


def build_conversation_history(messages: Iterable[Dict[str, Any]]) -> str:
    """Собирает историю разговора в том формате, который ожидает AI-провайдер."""
    conversation_history = ""
    for message in messages:
        conversation_history += f"\n{message['role'].upper()}: {message['content']}"
    return conversation_history


def build_chat_turn_prompt(system_prompt: str, history_messages: Iterable[Dict[str, Any]], user_input: str) -> str:
    """Собирает полный промпт для одного хода AI-коучинга."""
    conversation_history = build_conversation_history(history_messages)

    return f"""
{system_prompt}

ИСТОРИЯ РАЗГОВОРА:{conversation_history}

НОВЫЙ ВОПРОС ПОЛЬЗОВАТЕЛЯ: {user_input}

Используй инструменты для получения точных данных. ОБЯЗАТЕЛЬНО завершай задачу полностью - если просят план, составляй конкретный план, а не только анализируй данные. Отвечай персонально, конкретно и полезно. Используй эмодзи.
"""


def normalize_response_contract(contract: Any) -> Dict[str, Any] | None:
    if not isinstance(contract, dict):
        return None

    mode = str(contract.get("mode") or "").strip()
    if not mode:
        return None

    return {
        "mode": mode,
        "preview_label": str(contract.get("preview_label") or "").strip(),
        "today_action": str(contract.get("today_action") or "").strip(),
        "next_window": str(contract.get("next_window") or "").strip(),
        "watchout": str(contract.get("watchout") or "").strip(),
        "reason": str(contract.get("reason") or "").strip(),
        "prompt_suffix": str(contract.get("prompt_suffix") or "").strip(),
    }


def apply_response_contract_to_user_input(
    user_input: str,
    response_contract: Any = None,
) -> str:
    normalized = normalize_response_contract(response_contract)
    if normalized is None or not normalized.get("prompt_suffix"):
        return user_input

    return f"{user_input}\n\n{normalized['prompt_suffix']}"


def generate_ai_chat_response(
    provider: Any,
    ai_tools: Any,
    user_input: str,
    history_messages: Iterable[Dict[str, Any]],
    response_contract: Any = None,
) -> str:
    """Генерирует сырой ответ AI для текущего хода диалога."""
    system_prompt = create_chat_system_prompt_with_tools(ai_tools)
    full_prompt = build_chat_turn_prompt(
        system_prompt,
        history_messages,
        apply_response_contract_to_user_input(user_input, response_contract),
    )
    return provider.generate_response(full_prompt, "")


def process_tool_calls(
    ai_response: str,
    ai_tools: Any,
    tool_result_formatter: Callable[[str, Any], str],
) -> str:
    """Обрабатывает вызовы инструментов в ответе AI."""
    tool_pattern = r"\[TOOL:\s*([^,\]]+)(?:,\s*([^\]]*))?\]"

    def replace_tool_call(match):
        tool_name = match.group(1).strip()
        params_str = match.group(2).strip() if match.group(2) else ""
        params = _parse_tool_params(params_str)

        try:
            result = ai_tools.execute_tool(tool_name, **params)

            if result.get("success"):
                data = result["result"]
                return tool_result_formatter(tool_name, data)
            return f"❌ Ошибка инструмента: {result.get('error', 'Неизвестная ошибка')}"

        except Exception as exc:  # pragma: no cover - defensive path
            return f"❌ Ошибка выполнения {tool_name}: {str(exc)}"

    return re.sub(tool_pattern, replace_tool_call, ai_response)


def finalize_ai_chat_response(
    ai_response: str,
    ai_tools: Any,
    tool_result_formatter: Callable[[str, Any], str],
    response_post_processor: Optional[Callable[[str], str]] = None,
    response_contract: Any = None,
) -> str:
    """Превращает сырой ответ AI в финальный пользовательский ответ."""
    final_response = process_tool_calls(ai_response, ai_tools, tool_result_formatter)
    if response_post_processor is not None:
        final_response = response_post_processor(final_response)
    return apply_response_contract_to_final_response(final_response, response_contract)


def apply_response_contract_to_final_response(
    final_response: str,
    response_contract: Any = None,
) -> str:
    normalized = normalize_response_contract(response_contract)
    if normalized is None or normalized.get("mode") != "operational_brief":
        return final_response
    if "## 🎯 Operational Brief" in final_response:
        return final_response

    sections = [
        "## 🎯 Operational Brief",
        "",
        "### Сегодня",
        normalized.get("today_action") or "Уточните ключевое действие на сегодня по текущим сигналам.",
        "",
        "### Ближайшие 2-3 дня",
        normalized.get("next_window") or "Сверьте ближайшее окно с текущей формой и реальным планом.",
        "",
        "### Не делать",
        normalized.get("watchout") or "Не возвращайте объём резко, пока не уверены в восстановлении.",
        "",
        "### Почему",
        normalized.get("reason") or "Это самый безопасный следующий шаг по текущим данным.",
    ]

    analysis = final_response.strip()
    if analysis:
        sections.extend(
            [
                "",
                "### Разбор AI",
                analysis,
            ]
        )

    return "\n".join(sections)


def _parse_tool_params(params_str: str) -> Dict[str, Any]:
    params: Dict[str, Any] = {}
    if not params_str:
        return params

    param_pairs = [part.strip() for part in params_str.split(",")]
    for pair in param_pairs:
        if "=" not in pair:
            continue

        key, value = pair.split("=", 1)
        key = key.strip()
        value = value.strip()

        if value.isdigit():
            params[key] = int(value)
        elif value.replace(".", "").isdigit():
            params[key] = float(value)
        else:
            params[key] = value.strip("\"'")

    return params
