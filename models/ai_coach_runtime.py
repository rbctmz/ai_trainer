"""Runtime helpers for the AI coaching execution pipeline."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, Optional

from config.settings import Settings
from models.ai_data_context import AIDataContext
from models.coach_narrative_evidence import (
    CoachNarrativeEvidence,
    build_coach_narrative_evidence,
    fail_closed_coach_narrative,
    resolve_calendar_evidence,
    validate_coach_narrative,
)
from utils.product_semantics import format_date_label


def _today_context_line() -> str:
    """Explicit 'today' anchor for prompts.

    Tool results only ever carry historical per-day dates (and the freshest
    row can lag behind the real day if Garmin sync hasn't caught up), so
    without this the model has to guess "today" from data rows and drifts.
    """
    calendar = resolve_calendar_evidence(
        athlete_timezone=Settings.ATHLETE_TIMEZONE,
        observed_at_utc=datetime.now(timezone.utc),
    )
    if calendar.get("status") != "available":
        return "Сегодня: не определено (неверный ATHLETE_TIMEZONE)"
    today = datetime.fromisoformat(str(calendar["local_date"])).date()
    return (
        f"Сегодня: {today.isoformat()} ({format_date_label(today, 'weekday_short')}); "
        f"часовой пояс спортсмена: {calendar['athlete_timezone']}"
    )


def _build_phase_context(goal_plan: Optional[Dict]) -> str:
    """Return a short phase/race block for injection into the synthesis prompt."""
    if not goal_plan:
        return ""
    try:
        from models.training_planner import current_periodization_phase
        resolved = current_periodization_phase(goal_plan)
        if resolved is None:
            return ""
        goal_type = goal_plan.get("goal_type", "")
        distance = goal_plan.get("distance", "")
        return (
            f"\n\n=== ПЛАН И ФАЗА ===\n"
            f"• Цель: {goal_type} {distance}\n"
            f"• Дней до старта: {resolved['days_to_race']}\n"
            f"• Текущая фаза: {resolved['phase']}"
        )
    except Exception:
        return ""


_TOOL_PATTERN = re.compile(r"\[TOOL:\s*([^,\]]+)(?:,\s*([^\]]*))?\]")

_COGNITIVE_GUARDRAILS = """
КОГНИТИВНЫЕ GUARDRAILS — НЕ НАРУШАТЬ:
1. Inference without verification: не называй гипотезу установленной причиной. Помечай непроверенный вывод словами «вероятно» или «похоже» и называй, какая фактическая проверка его подтвердит.
2. Saving without commitment: не говори, что решение сохранено, запомнено или применено, если результат инструмента не подтвердил запись. Ясно отделяй предложение от выполненного действия.
3. Action without consideration: перед рекомендацией действия опирайся на релевантные фактические метрики — TSB/readiness/HRV, фактически полученные через доступные инструменты. Если нужные метрики не получены, скажи «данных недостаточно» и не выдумывай основание для изменения нагрузки.
4. Narrative fabrication: при нехватке данных говори «данных недостаточно», при конфликте — «сигналы смешанные». Не строй правдоподобную причинную историю, которая не следует из наблюдений.
5. Presenting inference as observation: явно отделяй «Наблюдение» (факт, число и источник) от «Вывода» (интерпретация). Не выдавай интерпретацию за измеренный факт.
""".strip()


def create_chat_system_prompt_with_tools(ai_tools: Any, data_context: Any = None) -> str:
    """Создает системный промпт с инструментами для доступа к данным."""
    base_prompt = f"""
Ты — персональный AI тренер по выносливости с глубокими знаниями спортивной науки.

{_today_context_line()} — это ЕДИНСТВЕННЫЙ источник текущей даты. Самая свежая строка в данных может быть за сегодня (день ещё не закончился, значения неполные) или отставать на день-два из-за синхронизации. НЕ вычисляй сегодняшнюю дату из данных инструментов. Если ранее в разговоре названа другая «сегодняшняя» дата и она противоречит строке «Сегодня» выше — она ошибочна, исправь её.

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
• Для вопросов про план, цель, дистанцию, старт, фазы или TSS-таргеты ОБЯЗАТЕЛЬНО сначала вызывай **get_active_plan**
• Для вопросов про ближайшие тренировки, расписание, «что завтра», «что на неделе» ОБЯЗАТЕЛЬНО сначала вызывай **get_upcoming_workouts**
• Если в своём ответе называешь или рекомендуешь тренировку на конкретный день (сегодня, завтра, конкретная дата) — например в «Следующем шаге» или брифинге — ОБЯЗАТЕЛЬНО сначала вызови **get_upcoming_workouts** и цитируй фактическую сессию из плана (название, спорт, TSS). Слова «вероятно», «скорее всего» рядом с плановой тренировкой недопустимы: план знает точно.
• Для вопросов о восстановлении, HRV, нервной системе, готовности ОБЯЗАТЕЛЬНО сначала вызывай **analyze_hrv_trends** (или **get_hrv_data**)
• Перед ЛЮБОЙ рекомендацией «на сегодня/завтра» (что делать, выполнять ли сессию, стоит ли отдохнуть) ОБЯЗАТЕЛЬНО вызови **get_readiness_today** (канонический снимок готовности — те же CTL/ATL/TSB и readiness, что видит пользователь в сайдбаре) И **get_pending_proposals**. Значения readiness/TSB бери из get_readiness_today, а не из общих оценок. В get_performance_metrics поле **computed_for** — это сегодня, **data_through** — дата последней активности; НЕ выдавай data_through за «сегодня».
• Если **get_pending_proposals** вернул активное предложение (recovery replan, правка плана) — НЕ противоречь ему: сошлись на него и не советуй выполнять день, который контур предлагает разгрузить.
• Если пользователь упоминает выполненную или только что сделанную тренировку («с утра на велосипеде поехал», «пробежал десятку»), ОБЯЗАТЕЛЬНО сначала вызывай **get_recent_activities** (при необходимости ещё **get_daily_health_stats**) и цитируй фактические длительность/дистанцию/TSS из результата, а не предположения «на глаз». Если активности в данных ещё нет — прямо скажи, что она ещё не синхронизировалась с Garmin, и НЕ оценивай её параметры приблизительно.
• При общем анализе состояния или демонстрации возможностей ОБЯЗАТЕЛЬНО вызывай минимум **get_performance_metrics**, **analyze_hrv_trends**, **analyze_training_status** и **get_upcoming_workouts**
• Если вопрос требует период/дату, вызывай инструмент с параметром days/start/end, а затем цитируй фактические значения из результата
• Метрики CTL/ATL/TSB и анализ нагрузки получай через соответствующие инструменты, вместо общих оценок
• Утверждать «данных HRV нет» или «readiness нет» можно ТОЛЬКО если инструмент был вызван и вернул пустой результат
• Для предложения собрать новый план ОБЯЗАТЕЛЬНО вызывай **propose_plan_build** с параметрами goal_type, distance, event_date, available_hours. Не описывай такой план только словами.
• Для предложения скорректировать активный план ОБЯЗАТЕЛЬНО вызывай **propose_plan_adjustment**. Не обещай корректировку без вызова инструмента.
• Если пользователь явно сообщает ограничение на день («я болею завтра», «не могу тренироваться 2026-07-10», «удали тренировку в пятницу»), ОБЯЗАТЕЛЬНО вызывай **create_plan_constraint** с конкретной датой и kind. Когда речь о ОТМЕНЕ одной дисциплины в многодисциплинарном дне («плавание сегодня отменяется», «без вело в субботу»), обязательно указывай параметр **sport** этой дисциплины — так сохраняются остальные ноги дня, а не гасится целый день. Дата — тот день, к которому относится факт (для прошедшего дня — его дата, а не today).
• Если пользователь ЖАЛЕЕТ об отмене («забудь про плавание», «я всё-таки поплаваю», «верни вело в план»), ОБЯЗАТЕЛЬНО вызови **retract_plan_constraint**: сначала по id ограничения (id из **get_coach_constraints**), либо date+sport. Ограничение деактивируется, удалённые ноги дня возвращаются из ближайшей версии плана; при per-sport ограничении вернутся ВСЕ ноги ДНЯ кроме отменённого спорта. Не просто говори «верну» без вызова инструмента.
• **repair_plan_day** — только разовый аварийный инструмент (день стерт ошибкой, а активного ограничения больше нет); вызывай лишь при явном запросе восстановить конкретную дату.
• НЕ вызывай **propose_plan_adjustment** для обычного анализа формы, статуса или готовности, если не предлагаешь реальное изменение активного плана.
• НИКОГДА не говори «я составлю план» или «план будет готов» без вызова **propose_plan_build** или **propose_plan_adjustment**
"""

    tools_description = ""
    if ai_tools is not None and hasattr(ai_tools, "format_tool_descriptions_for_ai"):
        tools_description = ai_tools.format_tool_descriptions_for_ai()

    return f"{base_prompt}\n\n{_COGNITIVE_GUARDRAILS}\n\n{tools_description}".rstrip()


def create_native_chat_system_prompt(ai_tools: Any = None) -> str:
    """Системный промпт нативного пути (Issue #190).

    Те же коучинговые правила и правила выбора инструментов, что и на
    маркерном пути, но БЕЗ блока `[TOOL: ...]`-синтаксиса: модель с нативным
    tools API получает схемы инструментов контрактно (описания параметров
    едут в самих схемах ``AITools.get_tool_schemas``), и учить её текстовым
    маркерам значит провоцировать отвечать маркерами вместо tool_calls.
    """
    del ai_tools  # схемы передаются провайдеру отдельно, в промпте не нужны
    return create_chat_system_prompt_with_tools(None)


def create_chat_synthesis_system_prompt(goal_plan: Optional[Dict] = None) -> str:
    """System prompt for the final user-facing answer after tool execution."""
    phase_ctx = _build_phase_context(goal_plan)
    return f"""
Ты — персональный AI тренер по выносливости.{phase_ctx}

{_today_context_line()} — это ЕДИНСТВЕННЫЙ источник текущей даты. Если называешь дату в ответе (например, в заголовке брифинга) — используй эту дату, а не последнюю дату из результатов инструментов. Если ранее в разговоре или в данных фигурирует другая «сегодняшняя» дата — она ошибочна, исправь её. Строка данных за сегодняшнюю дату может быть неполной (день не закончился): низкие шаги или активные минуты за сегодня НЕ считай спадом активности.

Ты уже получил результаты нужных инструментов и теперь должен дать
ЗАВЕРШЁННЫЙ финальный ответ пользователю.

{_COGNITIVE_GUARDRAILS}

ФОРМАТ ОТВЕТА:
• Начни с 3–5 ключевых тезисов (каждый — одна строка с конкретной цифрой или выводом)
• Весь ответ — не более ~300 слов; расширяй только если пользователь явно просит подробнее
• Структурируй кратко: тезисы → 1–2 практических вывода → следующий шаг

ОБЯЗАТЕЛЬНО:
• отвечай по-русски
• используй конкретные цифры и выводы из результатов инструментов
• если данные неполные, скажи прямо, но всё равно предложи лучший следующий шаг

НЕЛЬЗЯ:
• писать, что ты ещё соберёшь данные или вернёшься позже
• оставлять черновые формулировки вроде «сейчас проанализирую»
• упоминать служебный синтаксис [TOOL: ...]
• говорить «HRV отсутствует», «данных readiness нет», если инструмент не вызывался — просто не упоминай или скажи «не проверял в этом запросе»
• называть значения метрик (CTL, ATL, TSB, HRV, VO₂max, пульс, TSS, даты стартов, тренировки плана), которых НЕТ в результатах инструментов — не выдумывай числа и сессии; если значения нет в данных, так и скажи
• если вопрос пользователя не требует данных (благодарность, уточнение формулировки) — не перечисляй метрики, ответь кратко по сути
""".strip()


def create_chat_system_prompt(data_context: Any) -> str:
    """Создает системный промпт с полным контекстом данных пользователя."""
    base_prompt = f"""
Ты — персональный AI тренер по выносливости с глубокими знаниями спортивной науки.

{_today_context_line()} — это ЕДИНСТВЕННЫЙ источник текущей даты. Самая свежая запись в данных может быть за сегодня (день ещё не закончился, значения неполные) или отставать из-за синхронизации. НЕ вычисляй сегодняшнюю дату из данных; дата, названная ранее в разговоре и противоречащая строке «Сегодня», — ошибочна.

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
    base_prompt = f"{base_prompt}\n\n{_COGNITIVE_GUARDRAILS}"

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


def build_chat_synthesis_prompt(
    history_messages: Iterable[Dict[str, Any]],
    user_input: str,
    tool_results: Iterable[Dict[str, Any]],
    response_contract: Any = None,
) -> str:
    """Build the prompt for the second-pass final synthesis over tool data."""
    conversation_history = build_conversation_history(history_messages)
    rendered_tool_results = "\n\n".join(
        f"### {result['tool_name']}\n{result['formatted_result']}"
        for result in tool_results
    ).strip()

    return f"""
ИСТОРИЯ РАЗГОВОРА:{conversation_history}

ВОПРОС ПОЛЬЗОВАТЕЛЯ: {apply_response_contract_to_user_input(user_input, response_contract)}

РЕЗУЛЬТАТЫ ИНСТРУМЕНТОВ:
{rendered_tool_results}

Сформируй завершённый ответ пользователю на основе результатов выше.
Не пиши, что ты ещё будешь собирать или анализировать данные позже.
Сразу дай финальный вывод и практические рекомендации.
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


def _execute_tool_to_result(
    ai_tools: Any,
    tool_name: str,
    params: Dict[str, Any],
    tool_result_formatter: Callable[[str, Any], str],
) -> Dict[str, Any]:
    """Execute one tool call and normalize the outcome to a tool-result entry."""
    try:
        result = ai_tools.execute_tool(tool_name, **params)

        if result.get("success"):
            data = result["result"]
            return {
                "tool_name": tool_name,
                "params": params,
                "formatted_result": tool_result_formatter(tool_name, data),
                "raw_result": data,
                "success": True,
            }

        return {
            "tool_name": tool_name,
            "params": params,
            "formatted_result": f"❌ Ошибка инструмента: {result.get('error', 'Неизвестная ошибка')}",
            "success": False,
        }
    except Exception as exc:  # pragma: no cover - defensive path
        return {
            "tool_name": tool_name,
            "params": params,
            "formatted_result": f"❌ Ошибка выполнения {tool_name}: {str(exc)}",
            "success": False,
        }


# Baseline data toolset for the grounding fallback: the same minimum set the
# system prompt mandates for a general state/briefing answer, plus the active
# plan (race date and phase are the costliest things to get wrong).
GROUNDING_TOOL_CALLS: tuple[tuple[str, Dict[str, Any]], ...] = (
    ("get_performance_metrics", {}),
    ("analyze_hrv_trends", {}),
    ("analyze_training_status", {}),
    ("get_active_plan", {}),
    ("get_upcoming_workouts", {}),
)


def build_grounding_tool_results(
    ai_tools: Any,
    tool_result_formatter: Callable[[str, Any], str],
) -> list[Dict[str, Any]]:
    """Deterministically execute the baseline toolset when the model skipped tools.

    Tool calling here is marker-based: the model must emit [TOOL: ...] itself.
    When it doesn't, the raw first-pass answer used to go out ungrounded — with
    fabricated metrics, plan and race dates. This fallback feeds the synthesis
    pass real data instead. Per-tool failures become error entries so synthesis
    can honestly say what is missing.
    """
    if ai_tools is None or not hasattr(ai_tools, "execute_tool"):
        return []
    return [
        _execute_tool_to_result(ai_tools, tool_name, dict(params), tool_result_formatter)
        for tool_name, params in GROUNDING_TOOL_CALLS
    ]


def run_native_tool_loop(
    provider: Any,
    ai_tools: Any,
    user_input: str,
    history_messages: Iterable[Dict[str, Any]],
    tool_result_formatter: Callable[[str, Any], str],
    *,
    max_rounds: int = 2,
) -> tuple[str, list[Dict[str, Any]]]:
    """Нативный цикл инструментов (Issue #190).

    Схемы из ``AITools.get_tool_schemas`` уходят провайдеру, структурные
    tool_calls исполняются через общий ``_execute_tool_to_result``, результаты
    возвращаются модели tool-сообщениями — до ``max_rounds`` раундов, стоп на
    первом раунде без вызовов. Записи tool_results байт-в-байт той же формы,
    что и у маркерного ``collect_tool_results``: synthesis, SSE-события,
    proposals и grounding-fallback (#189) остаются общим кодом. Ноль вызовов —
    пустой список: grounding срабатывает на существующих call sites.
    """
    system_prompt = create_native_chat_system_prompt(ai_tools)
    schemas = (
        list(ai_tools.get_tool_schemas())
        if ai_tools is not None and hasattr(ai_tools, "get_tool_schemas")
        else []
    )

    messages: list[Dict[str, Any]] = []
    for message in history_messages:
        role = str(message.get("role") or "user")
        if role not in {"user", "assistant"}:
            role = "user"
        messages.append({"role": role, "content": str(message.get("content") or "")})
    messages.append({"role": "user", "content": user_input})

    final_text = ""
    tool_results: list[Dict[str, Any]] = []
    for _round in range(max(1, int(max_rounds))):
        outcome = provider.generate_with_tools(messages, schemas, system_prompt=system_prompt) or {}
        final_text = str(outcome.get("text") or "")
        calls = [call for call in list(outcome.get("tool_calls") or []) if call]
        if not calls:
            break
        messages.append(
            {
                "role": "assistant",
                "content": final_text,
                "tool_calls": [dict(call) for call in calls],
            }
        )
        for call in calls:
            tool_name = str(call.get("name") or "")
            params = dict(call.get("arguments") or {})
            entry = _execute_tool_to_result(ai_tools, tool_name, params, tool_result_formatter)
            tool_results.append(entry)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": str(call.get("id") or ""),
                    "name": tool_name,
                    "content": entry["formatted_result"],
                }
            )
    return final_text, tool_results


def resolve_turn_tool_results(
    *,
    provider: Any,
    ai_tools: Any,
    user_input: str,
    history_messages: Iterable[Dict[str, Any]],
    tool_result_formatter: Callable[[str, Any], str],
    response_contract: Any = None,
) -> Dict[str, Any]:
    """Единая точка выбора пути добычи tool_results для хода коуча.

    Нативный цикл — когда провайдер и умеет нативные инструменты
    (capability), и доступен; иначе прежний маркерный путь: первый проход +
    regex-исполнение ``[TOOL: ...]``. Возвращает
    ``{"native": bool, "tool_results": [...], "rendered_response": str}`` —
    дальше обе ветки обрабатываются одинаково (grounding при пустом списке,
    synthesis, SSE) на существующих call sites.
    """
    native_supported = False
    supports = getattr(provider, "supports_native_tools", None)
    if callable(supports) and supports():
        available = getattr(provider, "is_available", None)
        native_supported = available() if callable(available) else True

    if native_supported:
        final_text, tool_results = run_native_tool_loop(
            provider,
            ai_tools,
            apply_response_contract_to_user_input(user_input, response_contract),
            history_messages,
            tool_result_formatter,
        )
        return {
            "native": True,
            "tool_results": tool_results,
            "rendered_response": final_text,
        }

    raw = generate_ai_chat_response(
        provider=provider,
        ai_tools=ai_tools,
        user_input=user_input,
        history_messages=history_messages,
        response_contract=response_contract,
    )
    rendered_response, tool_results = collect_tool_results(
        raw, ai_tools, tool_result_formatter
    )
    return {
        "native": False,
        "tool_results": tool_results,
        "rendered_response": rendered_response,
    }


def collect_tool_results(
    ai_response: str,
    ai_tools: Any,
    tool_result_formatter: Callable[[str, Any], str],
) -> tuple[str, list[Dict[str, Any]]]:
    """Execute tool markers and return both the rendered text and tool payloads."""
    tool_results: list[Dict[str, Any]] = []

    def replace_tool_call(match):
        tool_name = match.group(1).strip()
        params_str = match.group(2).strip() if match.group(2) else ""
        params = _parse_tool_params(params_str)
        entry = _execute_tool_to_result(ai_tools, tool_name, params, tool_result_formatter)
        tool_results.append(entry)
        return entry["formatted_result"]

    rendered_response = _TOOL_PATTERN.sub(replace_tool_call, ai_response)
    return rendered_response, tool_results


def synthesize_ai_chat_response(
    provider: Any,
    history_messages: Iterable[Dict[str, Any]],
    user_input: str,
    tool_results: Iterable[Dict[str, Any]],
    response_contract: Any = None,
    goal_plan: Optional[Dict] = None,
) -> str:
    """Run the second pass that turns tool results into a final user answer."""
    synthesis_prompt = build_chat_synthesis_prompt(
        history_messages=history_messages,
        user_input=user_input,
        tool_results=tool_results,
        response_contract=response_contract,
    )
    return provider.generate_response(
        synthesis_prompt,
        create_chat_synthesis_system_prompt(goal_plan=goal_plan),
    )


def process_tool_calls(
    ai_response: str,
    ai_tools: Any,
    tool_result_formatter: Callable[[str, Any], str],
) -> str:
    """Обрабатывает вызовы инструментов в ответе AI."""
    rendered_response, _tool_results = collect_tool_results(
        ai_response,
        ai_tools,
        tool_result_formatter,
    )
    return rendered_response


def finalize_ai_chat_response(
    ai_response: str,
    ai_tools: Any,
    tool_result_formatter: Callable[[str, Any], str],
    response_post_processor: Optional[Callable[[str], str]] = None,
    response_contract: Any = None,
    provider: Any = None,
    user_input: Optional[str] = None,
    history_messages: Iterable[Dict[str, Any]] = (),
    narrative_evidence: CoachNarrativeEvidence | None = None,
) -> str:
    """Превращает сырой ответ AI в финальный пользовательский ответ."""
    rendered_response, tool_results = collect_tool_results(
        ai_response,
        ai_tools,
        tool_result_formatter,
    )

    if not tool_results and provider is not None and user_input is not None:
        # The model skipped tool markers entirely: without grounding its raw
        # answer goes out with fabricated metrics/plan. Feed the synthesis
        # pass the baseline real data instead.
        tool_results = build_grounding_tool_results(ai_tools, tool_result_formatter)

    if provider is not None and user_input is not None and tool_results:
        final_response = synthesize_ai_chat_response(
            provider=provider,
            history_messages=history_messages,
            user_input=user_input,
            tool_results=tool_results,
            response_contract=response_contract,
        ) or rendered_response
    else:
        final_response = rendered_response

    if response_post_processor is not None:
        final_response = response_post_processor(final_response)
    final_response = apply_response_contract_to_final_response(final_response, response_contract)
    try:
        evidence = narrative_evidence or _runtime_narrative_evidence(ai_tools, tool_results)
        return validate_coach_narrative(final_response, evidence).delivered_text
    except Exception:
        fingerprint = narrative_evidence.fingerprint if narrative_evidence is not None else "unavailable"
        return fail_closed_coach_narrative(fingerprint).delivered_text


def _runtime_narrative_evidence(
    ai_tools: Any,
    tool_results: Iterable[Dict[str, Any]],
) -> CoachNarrativeEvidence:
    """Best bounded evidence for non-API consumers of the shared finalizer."""
    observed_at_utc = datetime.now(timezone.utc)
    calendar = resolve_calendar_evidence(
        athlete_timezone=Settings.ATHLETE_TIMEZONE,
        observed_at_utc=observed_at_utc,
    )
    local_date = (
        datetime.fromisoformat(str(calendar["local_date"])).date()
        if calendar.get("status") == "available"
        else None
    )
    readiness_snapshot: Dict[str, Any] = {}
    db = getattr(ai_tools, "db", None)
    if db is not None and local_date is not None:
        try:
            from services.readiness_snapshot import build_readiness_snapshot

            readiness_snapshot = build_readiness_snapshot(
                db,
                as_of=local_date,
                observed_at_utc=observed_at_utc,
            )
        except Exception:
            readiness_snapshot = {}
    return build_coach_narrative_evidence(
        readiness_snapshot=readiness_snapshot,
        tool_results=tool_results,
        athlete_timezone=Settings.ATHLETE_TIMEZONE,
        observed_at_utc=observed_at_utc,
    )


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
