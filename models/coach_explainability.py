from __future__ import annotations

from typing import Any, Dict, List


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_or_zero(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _strategy_label(strategy: str | None) -> str:
    return "Наверстать аккуратно" if (strategy or "").lower() == "catch_up" else "Беречь восстановление"


def _extract_planning_context(goal_plan: Dict[str, Any] | None) -> Dict[str, Any]:
    if not isinstance(goal_plan, dict):
        return {}

    constraint_summary = goal_plan.get("constraint_summary", {}) or {}
    if not isinstance(constraint_summary, dict):
        return {}

    available_day_labels = [
        str(label)
        for label in constraint_summary.get("available_day_labels", [])
        if label
    ]

    return {
        "load_state_label": constraint_summary.get("load_state_label"),
        "interruption_label": constraint_summary.get("interruption_label", "Нет"),
        "interruption_weeks": _int_or_zero(constraint_summary.get("interruption_weeks")),
        "available_hours": _float_or_none(constraint_summary.get("available_hours")),
        "available_day_labels": available_day_labels,
        "available_day_count": _int_or_zero(constraint_summary.get("available_day_count")),
        "recommended_days": _int_or_zero(constraint_summary.get("recommended_days")),
        "catch_up_strategy": str(constraint_summary.get("catch_up_strategy", "protect_recovery")),
        "catch_up_label": _strategy_label(constraint_summary.get("catch_up_strategy")),
        "notes": [
            str(note)
            for note in constraint_summary.get("notes", [])
            if note
        ],
    }


def _collect_planning_signals(goal_plan: Dict[str, Any] | None) -> List[str]:
    planning_context = _extract_planning_context(goal_plan)
    if not planning_context:
        return []

    signals: List[str] = []
    load_state_label = planning_context.get("load_state_label")
    if load_state_label and load_state_label != "Нейтральный старт":
        signals.append(f"Последний план учитывает состояние: {load_state_label}.")

    available_hours = planning_context.get("available_hours")
    available_day_labels = planning_context.get("available_day_labels", [])
    if available_hours and available_day_labels:
        signals.append(
            f"Плановое окно: {available_hours:.1f} ч/нед и дни {', '.join(available_day_labels)}."
        )
    elif available_hours:
        signals.append(f"Плановое окно: {available_hours:.1f} ч/нед.")
    elif available_day_labels:
        signals.append(f"Плановое окно по дням: {', '.join(available_day_labels)}.")

    interruption_label = planning_context.get("interruption_label", "Нет")
    interruption_weeks = _int_or_zero(planning_context.get("interruption_weeks"))
    if interruption_label != "Нет" and interruption_weeks > 0:
        signals.append(
            "Последний план уже адаптирован под сценарий "
            f"«{interruption_label}» на {interruption_weeks} нед."
        )

    for note in planning_context.get("notes", []):
        if "Стартовое состояние:" in note:
            signals.append(note)
            break

    return signals[:4]


def _build_plan_context_line(goal_plan: Dict[str, Any] | None) -> str | None:
    planning_context = _extract_planning_context(goal_plan)
    if not planning_context:
        return None

    fragments: List[str] = []
    available_hours = planning_context.get("available_hours")
    available_day_labels = planning_context.get("available_day_labels", [])

    if available_hours and available_day_labels:
        fragments.append(
            f"{available_hours:.1f} ч/нед и дни {', '.join(available_day_labels)}"
        )
    elif available_hours:
        fragments.append(f"{available_hours:.1f} ч/нед")
    elif available_day_labels:
        fragments.append(f"дни {', '.join(available_day_labels)}")

    interruption_label = planning_context.get("interruption_label", "Нет")
    interruption_weeks = _int_or_zero(planning_context.get("interruption_weeks"))
    if interruption_label != "Нет" and interruption_weeks > 0:
        interruption_text = f"ограничение «{interruption_label}» на {interruption_weeks} нед."
        interruption_text += f", стратегия «{planning_context['catch_up_label']}»"
        fragments.append(interruption_text)

    load_state_label = planning_context.get("load_state_label")
    if not fragments and load_state_label and load_state_label != "Нейтральный старт":
        fragments.append(f"стартовое состояние «{load_state_label}»")

    if not fragments:
        return None

    return "Текущий план уже учитывает " + "; ".join(fragments) + "."


def _append_plan_context_to_prompt(
    prompt: str,
    goal_plan: Dict[str, Any] | None,
) -> str:
    plan_context = _build_plan_context_line(goal_plan)
    if not plan_context:
        return prompt

    return (
        f"{prompt}\n\n"
        f"Учти контекст текущего плана: {plan_context} "
        "Если текущее состояние конфликтует с планом, выбери более безопасный вариант и явно объясни компромисс."
    )


def build_coach_explainability_summary(
    *,
    tsb: Any = None,
    ctl: Any = None,
    atl: Any = None,
    readiness: Any = None,
    recovery_state: str | None = None,
    sleep_quality: str | None = None,
    goal_plan: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Build a shared reasoning summary for dashboard and AI coaching surfaces."""
    tsb_val = _float_or_none(tsb)
    ctl_val = _float_or_none(ctl)
    atl_val = _float_or_none(atl)
    readiness_val = _float_or_none(readiness)
    planning_context = _extract_planning_context(goal_plan)
    available_day_labels = planning_context.get("available_day_labels", [])
    available_days_text = ", ".join(available_day_labels)
    atl_ratio = None
    if ctl_val is not None and ctl_val > 0 and atl_val is not None:
        atl_ratio = atl_val / ctl_val

    focus = "form_today"
    icon = "🤖"
    title = "Начните с оценки текущей формы"
    short_title = "Оценка формы"
    description = "Метрики не сигналят о критическом риске, поэтому сейчас полезнее всего коротко интерпретировать форму и ближайшую нагрузку."
    reason = "Так вы быстрее всего превратите сырые показатели в понятное решение на сегодня."
    button = "Спросить про форму сегодня"
    dashboard_button = "Спросить AI коуча"
    action = "ai_chat"
    prompt = "Проанализируй мою текущую форму: TSB, CTL, ATL, HRV, readiness и недавнюю нагрузку. Дай краткую оценку состояния и самый важный следующий шаг."
    today_action = "Коротко оцените, тянет ли состояние на обычную тренировку или день стоит сделать легче."
    next_window = (
        f"Сверьте ближайшие 2-3 дня с реальным окном {available_days_text}."
        if available_days_text
        else "Сверьте ближайшие 2-3 дня с текущим тренировочным блоком, а не только с ощущениями за одно утро."
    )
    watchout = "Не повышайте интенсивность по одному сигналу; TSB, readiness и восстановление лучше читать вместе."

    if (
        (tsb_val is not None and tsb_val < -20)
        or (readiness_val is not None and readiness_val < 40)
        or recovery_state == "poor"
        or sleep_quality == "poor"
        or (atl_ratio is not None and atl_ratio >= 1.35)
    ):
        focus = "recovery"
        icon = "😴"
        title = "Сначала разберите восстановление"
        short_title = "Фокус на восстановлении"
        description = "Сигналы усталости уже заметны. Сейчас важнее скорректировать восстановление, чем пытаться добавить нагрузку."
        reason = "Это снижает риск перегруза и помогает не принять высокий ATL или низкий TSB за нормальное рабочее состояние."
        button = "Спросить про восстановление"
        dashboard_button = "Открыть план восстановления"
        action = "recovery_plan"
        prompt = "Проанализируй мое состояние восстановления: TSB, HRV, качество сна и недавнюю нагрузку. Дай конкретную рекомендацию, что делать сегодня и в ближайшие 2-3 дня."
        today_action = "Снизьте день до отдыха или очень лёгкой Zone 1, а фокус сместите на сон, питание и снятие накопленной усталости."
        next_window = (
            f"Ближайшие 2-3 дня держите нагрузку мягкой и возвращайтесь к плану по дням {available_days_text} только после стабилизации сигналов."
            if available_days_text
            else "Ближайшие 2-3 дня возвращайте нагрузку только после стабилизации HRV и readiness, а не по календарю любой ценой."
        )
        if planning_context.get("catch_up_strategy") == "catch_up":
            watchout = "Даже если план допускает аккуратный catch-up, не догоняйте объём, пока сигналы усталости ещё красные."
        else:
            watchout = "Не пытайтесь наверстать пропущенный объём, пока сигналы усталости ещё красные."
    elif (
        readiness_val is not None
        and readiness_val >= 75
        and (tsb_val is None or tsb_val > -10)
        and recovery_state != "poor"
        and sleep_quality != "poor"
    ):
        focus = "plan_week"
        icon = "📈"
        title = "Составьте план на ближайшие 7 дней"
        short_title = "Окно для прогрессии"
        description = "Readiness и нагрузка выглядят достаточно устойчиво. Самый полезный следующий шаг — превратить это окно готовности в конкретный недельный план."
        reason = "Когда состояние хорошее, общая интерпретация уже менее ценна, чем решение, как именно использовать это окно."
        button = "Спросить про план недели"
        dashboard_button = "Открыть план недели"
        action = "ai_chat"
        prompt = "На основе моего текущего readiness, TSB, HRV и недавних тренировок составь конкретный план тренировок на ближайшие 7 дней с распределением по дням и интенсивности."
        today_action = "Зафиксируйте одну ключевую тренировку в ближайшем окне высокой готовности, пока состояние это позволяет."
        next_window = (
            f"Разложите 7-дневный объём по доступным дням {available_days_text} и оставьте зазор между тяжёлыми сессиями."
            if available_days_text
            else "Разложите 7-дневный объём так, чтобы тяжёлые сессии не стояли подряд и были привязаны к реальному окну готовности."
        )
        interruption_label = planning_context.get("interruption_label", "Нет")
        interruption_weeks = _int_or_zero(planning_context.get("interruption_weeks"))
        if interruption_label != "Нет" and interruption_weeks > 0:
            watchout = (
                f"Даже при хорошем readiness учитывайте ограничение «{interruption_label}» "
                "и не уплотняйте неделю сверх доступного окна."
            )
        else:
            watchout = "Даже при хорошем readiness не ставьте тяжёлые дни подряд и контролируйте, чтобы ATL не рос быстрее формы."

    prompt = _append_plan_context_to_prompt(prompt, goal_plan)

    signals: List[str] = []
    if tsb_val is not None:
        signals.append(f"TSB: {tsb_val:+.1f}")
    if ctl_val is not None:
        signals.append(f"CTL: {ctl_val:.1f}")
    if atl_val is not None:
        signals.append(f"ATL: {atl_val:.1f}")
    if atl_ratio is not None:
        signals.append(f"ATL/CTL: {atl_ratio:.2f}")
    if readiness_val is not None:
        signals.append(f"Readiness: {readiness_val:.0f}/100")
    if recovery_state:
        signals.append(f"HRV recovery: {recovery_state}")
    if sleep_quality:
        signals.append(f"Сон: {sleep_quality}")

    signals.extend(_collect_planning_signals(goal_plan))

    return {
        "focus": focus,
        "icon": icon,
        "title": title,
        "short_title": short_title,
        "description": description,
        "reason": reason,
        "button": button,
        "dashboard_button": dashboard_button,
        "action": action,
        "prompt": prompt,
        "today_action": today_action,
        "next_window": next_window,
        "watchout": watchout,
        "plan_context": _build_plan_context_line(goal_plan),
        "signals": signals,
    }
