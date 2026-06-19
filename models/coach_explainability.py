from __future__ import annotations

from typing import Any, Dict, List

from models.planning_execution import (
    summarize_execution_corrective_microcycle,
    summarize_execution_reconciliation,
    summarize_execution_weekly_review,
)
from models.planning_checkpoints import NON_ACTIONABLE_PLAN_ADJUSTMENTS
from models.planning_summary import (
    summarize_execution_adaptation_pressure,
    summarize_near_term_edit,
)

OPERATIONAL_RESPONSE_PREVIEW = "Первый ответ вернётся в формате: Сегодня / Ближайшие 2-3 дня / Не делать / Почему."


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


def _summarize_execution_weekly_review_line(
    execution_weekly_review: Dict[str, Any] | None,
) -> str | None:
    review = summarize_execution_weekly_review(execution_weekly_review)
    if not isinstance(review, dict):
        return None

    fragments: List[str] = []
    headline = str(review.get("headline") or "").strip()
    if headline:
        fragments.append(headline)

    deviation_fragments: List[str] = []
    for item in review.get("deviations", [])[:2]:
        label = str(item.get("label") or "").strip()
        detail = str(item.get("detail") or "").strip()
        if label and detail:
            deviation_fragments.append(f"{label}: {detail}")
        elif label:
            deviation_fragments.append(label)
    if deviation_fragments:
        fragments.append("; ".join(deviation_fragments))

    response_label = str(
        review.get("selected_response_label")
        or review.get("recommended_response_label")
        or ""
    ).strip()
    if response_label:
        fragments.append(f"Ответ: {response_label}")

    return " · ".join(fragments) if fragments else None


def _summarize_execution_corrective_microcycle_line(
    execution_corrective_microcycle: Dict[str, Any] | None,
) -> str | None:
    microcycle = summarize_execution_corrective_microcycle(execution_corrective_microcycle)
    if not isinstance(microcycle, dict):
        return None

    fragments: List[str] = []
    headline = str(microcycle.get("headline") or "").strip()
    if headline:
        fragments.append(headline)
    sessions = microcycle.get("sessions", [])
    if sessions:
        first_session = sessions[0]
        action_label = str(first_session.get("action_label") or "").strip()
        session_name = str(first_session.get("session_name") or "").strip()
        if action_label and session_name:
            fragments.append(f"{action_label}: {session_name}")
    guardrail = str(microcycle.get("guardrail") or "").strip()
    if guardrail:
        fragments.append(guardrail)

    return " · ".join(fragments) if fragments else None


def _summarize_execution_adaptation_pressure_line(
    execution_adaptation_pressure: Dict[str, Any] | None,
) -> str | None:
    pressure = summarize_execution_adaptation_pressure(execution_adaptation_pressure)
    if not isinstance(pressure, dict):
        return None

    fragments = [pressure["compact_label"]]
    if pressure.get("follow_up_window_description"):
        fragments.append(str(pressure["follow_up_window_description"]))
    if pressure.get("reason"):
        fragments.append(str(pressure["reason"]))
    return " · ".join(part for part in fragments if part)


def _checkpoint_source_label(source: str | None) -> str:
    mapping = {
        "initial_plan": "базовая версия",
        "manual_edit": "ручная правка",
        "execution_feedback": "execution replan",
        "restore_version": "восстановленная версия",
    }
    return mapping.get(str(source or "").strip(), "")


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
    plan_adjustment = constraint_summary.get("plan_adjustment", {}) or {}
    near_term_edit = summarize_near_term_edit(constraint_summary)
    execution_reconciliation = summarize_execution_reconciliation(
        plan_adjustment.get("execution_reconciliation")
    )
    execution_weekly_review = summarize_execution_weekly_review(
        plan_adjustment.get("execution_weekly_review")
    )
    execution_corrective_microcycle = summarize_execution_corrective_microcycle(
        plan_adjustment.get("execution_corrective_microcycle")
    )
    execution_adaptation_pressure = summarize_execution_adaptation_pressure(
        plan_adjustment.get("execution_adaptation_pressure")
    )

    return {
        "checkpoint_source": str(goal_plan.get("checkpoint_source") or "").strip(),
        "checkpoint_source_label": _checkpoint_source_label(goal_plan.get("checkpoint_source")),
        "checkpoint_restored_from_checkpoint_id": _int_or_zero(goal_plan.get("checkpoint_restored_from_checkpoint_id")),
        "load_state_label": constraint_summary.get("load_state_label"),
        "interruption_label": constraint_summary.get("interruption_label", "Нет"),
        "interruption_weeks": _int_or_zero(constraint_summary.get("interruption_weeks")),
        "available_hours": _float_or_none(constraint_summary.get("available_hours")),
        "available_day_labels": available_day_labels,
        "available_day_count": _int_or_zero(constraint_summary.get("available_day_count")),
        "recommended_days": _int_or_zero(constraint_summary.get("recommended_days")),
        "catch_up_strategy": str(constraint_summary.get("catch_up_strategy", "protect_recovery")),
        "catch_up_label": _strategy_label(constraint_summary.get("catch_up_strategy")),
        "plan_adjustment_label": str(plan_adjustment.get("label", "Нет")),
        "plan_adjustment_weeks": _int_or_zero(plan_adjustment.get("weeks")),
        "plan_adjustment_recovered_tss": _int_or_zero(constraint_summary.get("plan_adjustment_recovered_tss")),
        "execution_reconciliation": execution_reconciliation,
        "execution_weekly_review": execution_weekly_review,
        "execution_corrective_microcycle": execution_corrective_microcycle,
        "execution_adaptation_pressure": execution_adaptation_pressure,
        "near_term_edit": near_term_edit,
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
    checkpoint_source = planning_context.get("checkpoint_source")
    restored_from_checkpoint_id = _int_or_zero(planning_context.get("checkpoint_restored_from_checkpoint_id"))
    if checkpoint_source == "restore_version":
        if restored_from_checkpoint_id > 0:
            signals.append(f"Активная версия плана восстановлена из checkpoint #{restored_from_checkpoint_id}.")
        else:
            signals.append("Активная версия плана восстановлена из прошлой сохранённой версии.")

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

    plan_adjustment_label = planning_context.get("plan_adjustment_label", "Нет")
    plan_adjustment_weeks = _int_or_zero(planning_context.get("plan_adjustment_weeks"))
    if plan_adjustment_label != "Нет" and plan_adjustment_weeks > 0:
        signal = (
            "Последний checkpoint уже учтён в плане: "
            f"«{plan_adjustment_label}» на {plan_adjustment_weeks} нед."
        )
        recovered_tss = _int_or_zero(planning_context.get("plan_adjustment_recovered_tss"))
        if recovered_tss > 0:
            signal += f" Локально возвращено {recovered_tss} TSS."
        signals.append(signal)
    execution_reconciliation = planning_context.get("execution_reconciliation")
    if isinstance(execution_reconciliation, dict) and execution_reconciliation.get("changed_day_count", 0) > 0:
        signals.append(
            "Факт ближнего окна уже учтён: "
            f"{execution_reconciliation['actual_total_tss']} из {execution_reconciliation['planned_total_tss']} TSS, "
            f"изменено {execution_reconciliation['changed_day_count']} дн."
        )
    weekly_review_line = _summarize_execution_weekly_review_line(
        planning_context.get("execution_weekly_review")
    )
    if weekly_review_line:
        signals.append(f"Weekly review: {weekly_review_line}.")
    adaptation_pressure_line = _summarize_execution_adaptation_pressure_line(
        planning_context.get("execution_adaptation_pressure")
    )
    if adaptation_pressure_line:
        signals.append(f"Execution drift pressure: {adaptation_pressure_line}.")
    corrective_microcycle_line = _summarize_execution_corrective_microcycle_line(
        planning_context.get("execution_corrective_microcycle")
    )
    if corrective_microcycle_line:
        signals.append(f"Execution microcycle: {corrective_microcycle_line}.")

    near_term_edit = planning_context.get("near_term_edit")
    if isinstance(near_term_edit, dict):
        signals.append(
            "Ближайший горизонт уже правился вручную: "
            f"{near_term_edit['description']}."
        )
        if near_term_edit.get("origin_description"):
            signals.append(
                "Эта ручная правка выросла из execution-развилки: "
                f"{near_term_edit['origin_description']}."
            )
        if near_term_edit.get("risk_level") != "low":
            signals.append(
                "Риск ручной правки: "
                f"{near_term_edit['risk_badge']}. {near_term_edit['risk_guardrail']}"
            )

    for note in planning_context.get("notes", []):
        if "Стартовое состояние:" in note:
            signals.append(note)
            break

    return signals[:5]


def _build_plan_context_line(goal_plan: Dict[str, Any] | None) -> str | None:
    planning_context = _extract_planning_context(goal_plan)
    if not planning_context:
        return None

    fragments: List[str] = []
    available_hours = planning_context.get("available_hours")
    available_day_labels = planning_context.get("available_day_labels", [])
    checkpoint_source = planning_context.get("checkpoint_source")
    restored_from_checkpoint_id = _int_or_zero(planning_context.get("checkpoint_restored_from_checkpoint_id"))

    if checkpoint_source == "restore_version":
        if restored_from_checkpoint_id > 0:
            fragments.append(f"восстановленную версию checkpoint #{restored_from_checkpoint_id}")
        else:
            fragments.append("восстановленную версию плана")

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

    plan_adjustment_label = planning_context.get("plan_adjustment_label", "Нет")
    plan_adjustment_weeks = _int_or_zero(planning_context.get("plan_adjustment_weeks"))
    if plan_adjustment_label != "Нет" and plan_adjustment_weeks > 0:
        checkpoint_text = f"checkpoint «{plan_adjustment_label}» на {plan_adjustment_weeks} нед."
        recovered_tss = _int_or_zero(planning_context.get("plan_adjustment_recovered_tss"))
        if recovered_tss > 0:
            checkpoint_text += f", локально возвращено {recovered_tss} TSS"
        fragments.append(checkpoint_text)
    execution_reconciliation = planning_context.get("execution_reconciliation")
    if isinstance(execution_reconciliation, dict) and execution_reconciliation.get("changed_day_count", 0) > 0:
        fragments.append(
            "факт ближнего окна: "
            f"{execution_reconciliation['actual_total_tss']}/{execution_reconciliation['planned_total_tss']} TSS, "
            f"изменено {execution_reconciliation['changed_day_count']} дн."
        )
    weekly_review_line = _summarize_execution_weekly_review_line(
        planning_context.get("execution_weekly_review")
    )
    if weekly_review_line:
        fragments.append(f"weekly review: {weekly_review_line}")
    corrective_microcycle_line = _summarize_execution_corrective_microcycle_line(
        planning_context.get("execution_corrective_microcycle")
    )
    if corrective_microcycle_line:
        fragments.append(f"execution microcycle: {corrective_microcycle_line}")
    adaptation_pressure_line = _summarize_execution_adaptation_pressure_line(
        planning_context.get("execution_adaptation_pressure")
    )
    if adaptation_pressure_line:
        fragments.append(f"execution drift pressure: {adaptation_pressure_line}")

    near_term_edit = planning_context.get("near_term_edit")
    if isinstance(near_term_edit, dict):
        fragments.append(f"ручную правку ближнего горизонта: {near_term_edit['description']}")
        if near_term_edit.get("origin_description"):
            fragments.append(f"источник этой правки: {near_term_edit['origin_description']}")
        if near_term_edit.get("risk_level") != "low":
            fragments.append(
                f"guardrail этой правки: {near_term_edit['risk_badge']}, {near_term_edit['risk_guardrail']}"
            )

    load_state_label = planning_context.get("load_state_label")
    if not fragments and load_state_label and load_state_label != "Нейтральный старт":
        fragments.append(f"стартовое состояние «{load_state_label}»")

    if not fragments:
        return None

    return "Текущий план уже учитывает " + "; ".join(fragments) + "."


def _append_plan_context_to_prompt(
    prompt: str,
    goal_plan: Dict[str, Any] | None,
    execution_feedback: Dict[str, Any] | None = None,
) -> str:
    context_fragments: List[str] = []

    plan_context = _build_plan_context_line(goal_plan)
    if plan_context:
        context_fragments.append(plan_context)

    execution_context = _build_execution_feedback_context_line(execution_feedback)
    if execution_context:
        context_fragments.append(execution_context)

    if not context_fragments:
        return prompt

    return (
        f"{prompt}\n\n"
        f"Учти контекст текущего плана: {' '.join(context_fragments)} "
        "Если текущее состояние конфликтует с планом, выбери более безопасный вариант и явно объясни компромисс."
    )


def _normalize_execution_feedback(execution_feedback: Dict[str, Any] | None) -> Dict[str, Any]:
    if not isinstance(execution_feedback, dict):
        return {}

    plan_adjustment_label = str(execution_feedback.get("plan_adjustment_label") or "Нет").strip()
    execution_reconciliation = summarize_execution_reconciliation(
        execution_feedback.get("execution_reconciliation")
    )
    execution_weekly_review = summarize_execution_weekly_review(
        execution_feedback.get("execution_weekly_review")
    )
    execution_corrective_microcycle = summarize_execution_corrective_microcycle(
        execution_feedback.get("execution_corrective_microcycle")
    )
    execution_adaptation_pressure = summarize_execution_adaptation_pressure(
        execution_feedback.get("execution_adaptation_pressure")
    )
    return {
        "title": str(execution_feedback.get("title") or "").strip(),
        "created_at_label": str(execution_feedback.get("created_at_label") or "").strip(),
        "plan_adjustment_label": plan_adjustment_label,
        "plan_adjustment_weeks": _int_or_zero(execution_feedback.get("plan_adjustment_weeks")),
        "peak_tss": _int_or_zero(execution_feedback.get("peak_tss")),
        "peak_delta": _int_or_zero(execution_feedback.get("peak_delta")),
        "total_tss": _int_or_zero(execution_feedback.get("total_tss")),
        "total_delta": _int_or_zero(execution_feedback.get("total_delta")),
        "execution_reconciliation": execution_reconciliation,
        "execution_weekly_review": execution_weekly_review,
        "execution_corrective_microcycle": execution_corrective_microcycle,
        "execution_adaptation_pressure": execution_adaptation_pressure,
        "is_actionable": plan_adjustment_label not in NON_ACTIONABLE_PLAN_ADJUSTMENTS,
    }


def _build_execution_feedback_context_line(
    execution_feedback: Dict[str, Any] | None,
) -> str | None:
    feedback = _normalize_execution_feedback(execution_feedback)
    if not feedback.get("is_actionable"):
        return None

    fragments = [
        f"Последний execution checkpoint: «{feedback['plan_adjustment_label']}»",
    ]
    if feedback["plan_adjustment_weeks"] > 0:
        fragments[-1] += f" на {feedback['plan_adjustment_weeks']} нед."
    execution_reconciliation = feedback.get("execution_reconciliation")
    if isinstance(execution_reconciliation, dict) and execution_reconciliation.get("changed_day_count", 0) > 0:
        fragments.append(
            "Факт окна: "
            f"{execution_reconciliation['actual_total_tss']} из {execution_reconciliation['planned_total_tss']} TSS, "
            f"изменено {execution_reconciliation['changed_day_count']} дн."
        )
    weekly_review_line = _summarize_execution_weekly_review_line(
        feedback.get("execution_weekly_review")
    )
    if weekly_review_line:
        fragments.append("Weekly review: " + weekly_review_line + ".")
    corrective_microcycle_line = _summarize_execution_corrective_microcycle_line(
        feedback.get("execution_corrective_microcycle")
    )
    if corrective_microcycle_line:
        fragments.append("Execution microcycle: " + corrective_microcycle_line + ".")
    adaptation_pressure_line = _summarize_execution_adaptation_pressure_line(
        feedback.get("execution_adaptation_pressure")
    )
    if adaptation_pressure_line:
        fragments.append("Execution drift pressure: " + adaptation_pressure_line + ".")
    delta_parts: List[str] = []
    if feedback["total_delta"] != 0:
        delta_parts.append(f"сумма {feedback['total_delta']:+d} TSS")
    if feedback["peak_delta"] != 0:
        delta_parts.append(f"пик {feedback['peak_delta']:+d} TSS")
    if delta_parts:
        fragments.append("Изменение: " + ", ".join(delta_parts) + ".")
    return " ".join(fragments)


def _collect_execution_feedback_signals(
    execution_feedback: Dict[str, Any] | None,
) -> List[str]:
    feedback = _normalize_execution_feedback(execution_feedback)
    if not feedback.get("is_actionable"):
        return []

    signals = [
        f"Execution checkpoint: {feedback['plan_adjustment_label']}.",
    ]
    execution_reconciliation = feedback.get("execution_reconciliation")
    if isinstance(execution_reconciliation, dict) and execution_reconciliation.get("changed_day_count", 0) > 0:
        signals.append(
            "Факт ближнего окна: "
            f"{execution_reconciliation['actual_total_tss']}/{execution_reconciliation['planned_total_tss']} TSS, "
            f"{execution_reconciliation['changed_day_count']} дн. изменено."
        )
    weekly_review_line = _summarize_execution_weekly_review_line(
        feedback.get("execution_weekly_review")
    )
    if weekly_review_line:
        signals.append("Weekly review: " + weekly_review_line + ".")
    corrective_microcycle_line = _summarize_execution_corrective_microcycle_line(
        feedback.get("execution_corrective_microcycle")
    )
    if corrective_microcycle_line:
        signals.append("Execution microcycle: " + corrective_microcycle_line + ".")
    adaptation_pressure_line = _summarize_execution_adaptation_pressure_line(
        feedback.get("execution_adaptation_pressure")
    )
    if adaptation_pressure_line:
        signals.append("Execution drift pressure: " + adaptation_pressure_line + ".")
    delta_parts: List[str] = []
    if feedback["total_delta"] != 0:
        delta_parts.append(f"сумма {feedback['total_delta']:+d} TSS")
    if feedback["peak_delta"] != 0:
        delta_parts.append(f"пик {feedback['peak_delta']:+d} TSS")
    if delta_parts:
        signals.append("Локальный replan изменил " + " и ".join(delta_parts) + ".")
    return signals


def _build_execution_feedback_guardrail(
    execution_feedback: Dict[str, Any] | None,
) -> Dict[str, str]:
    feedback = _normalize_execution_feedback(execution_feedback)
    if not feedback.get("is_actionable"):
        return {}

    label = feedback["plan_adjustment_label"]
    total_delta = feedback["total_delta"]
    delta_text = (
        f" Локальный replan уже изменил объём на {total_delta:+d} TSS."
        if total_delta
        else ""
    )

    if label == "Пропущены сессии":
        return {
            "today": "Считайте пропущенные сессии уже учтёнными в новом потолке недели, а не долгом на завтра.",
            "next_window": "После пропущенных сессий не втискивайте объём обратно в ближайшие 1-2 дня." + delta_text,
            "watchout": "Не пытайтесь закрыть выпавший объём одним перегруженным блоком.",
        }
    if label == "Нагрузка урезана":
        return {
            "today": "Считайте облегчённую неделю новой верхней границей до следующей оценки формы.",
            "next_window": "После урезанной недели возвращайте нагрузку только ступенчато, а не одним скачком." + delta_text,
            "watchout": "Не компенсируйте урезанный объём резким ростом интенсивности.",
        }
    return {
        "today": "Сначала примите ограниченное окно недели как факт и стройте решение от него.",
        "next_window": "Не расширяйте ближайшие 2-3 дня сверх фактически доступного окна." + delta_text,
        "watchout": "Не уплотняйте неделю только потому, что календарно хочется вернуться в исходный план.",
    }


def build_coach_explainability_summary(
    *,
    tsb: Any = None,
    ctl: Any = None,
    atl: Any = None,
    readiness: Any = None,
    recovery_state: str | None = None,
    sleep_quality: str | None = None,
    goal_plan: Dict[str, Any] | None = None,
    execution_feedback: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Build a shared reasoning summary for dashboard and AI coaching surfaces."""
    tsb_val = _float_or_none(tsb)
    ctl_val = _float_or_none(ctl)
    atl_val = _float_or_none(atl)
    readiness_val = _float_or_none(readiness)
    planning_context = _extract_planning_context(goal_plan)
    feedback_context = _normalize_execution_feedback(execution_feedback)
    execution_microcycle = (
        feedback_context.get("execution_corrective_microcycle")
        or planning_context.get("execution_corrective_microcycle")
    )
    execution_adaptation_pressure = (
        feedback_context.get("execution_adaptation_pressure")
        or planning_context.get("execution_adaptation_pressure")
    )
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
    elif feedback_context.get("is_actionable"):
        label = feedback_context["plan_adjustment_label"]
        weekly_review = feedback_context.get("execution_weekly_review")
        focus = "execution_review"
        icon = "♻️"
        title = "Разберите execution checkpoint и ближайший план"
        short_title = "Checkpoint требует разбора"
        description = (
            "Последняя неделя уже изменила план через execution checkpoint. "
            "Сейчас полезнее сверить этот локальный replan с текущей формой, чем сразу возвращаться к обычной интерпретации readiness."
        )
        reason = (
            "После пропуска, урезания или ограничения недели главный риск — "
            "не неверная метрика, а попытка слишком быстро вернуть объём в ближайшие 1-2 дня."
        )
        button = "Разобрать checkpoint"
        dashboard_button = "Открыть разбор checkpoint"
        action = "ai_chat"
        prompt = (
            "Проанализируй мой последний execution checkpoint, текущие метрики формы и ближайший план. "
            "Объясни, что делать сегодня, что менять в ближайшие 2-3 дня и какой объём точно не нужно пытаться вернуть сразу."
        )
        if label == "Пропущены сессии":
            today_action = "Не втискивайте выпавшие сессии в ближайшие 1-2 дня; сначала решите, какую часть нагрузки стоит вернуть, а какую отпустить."
            watchout = "Не превращайте пропущенный объём в долг, который нужно закрыть одним перегруженным блоком."
        elif label == "Нагрузка урезана":
            today_action = "Примите облегчённую неделю как новый baseline и проверьте, что ближайшая ключевая сессия всё ещё уместна."
            watchout = "Не компенсируйте урезанную нагрузку резким скачком уже на следующий день."
        else:
            today_action = "Сначала перестройте ближайшие дни под реальное окно доступности, а уже потом решайте, что из объёма безопасно вернуть."
            watchout = "Не уплотняйте неделю сверх фактически доступных дней, даже если хочется быстро вернуться к исходному плану."

        checkpoint_horizon = feedback_context.get("plan_adjustment_weeks", 0)
        total_delta = feedback_context.get("total_delta", 0)
        total_delta_text = (
            f" Локальный replan уже изменил краткосрочный объём на {total_delta:+d} TSS."
            if total_delta
            else ""
        )
        if checkpoint_horizon > 0 and available_days_text:
            next_window = (
                f"Пересоберите ближайшие {checkpoint_horizon} нед. вокруг реального окна {available_days_text} "
                "и проверьте, что safe catch-up не спорит с восстановлением."
                f"{total_delta_text}"
            )
        elif checkpoint_horizon > 0:
            next_window = (
                f"Пересоберите ближайшие {checkpoint_horizon} нед. вокруг фактической готовности и не возвращайте объём автоматически."
                f"{total_delta_text}"
            )
        else:
            next_window = (
                "Сверьте ближайшие 2-3 дня с фактическим объёмом недели и уберите автоматическое желание 'добить план'."
                f"{total_delta_text}"
            )
        weekly_review_line = _summarize_execution_weekly_review_line(weekly_review)
        if weekly_review_line:
            next_window = f"{next_window} Weekly review: {weekly_review_line}."
        recommended_reason = ""
        if isinstance(weekly_review, dict):
            recommended_reason = str(weekly_review.get("recommended_response_reason") or "").strip()
        if recommended_reason:
            watchout = f"{watchout} {recommended_reason}"
        if isinstance(execution_microcycle, dict):
            if execution_microcycle.get("today_action"):
                today_action = str(execution_microcycle["today_action"])
            if execution_microcycle.get("next_window"):
                next_window = str(execution_microcycle["next_window"])
            if execution_microcycle.get("guardrail"):
                watchout = str(execution_microcycle["guardrail"])
        if isinstance(execution_adaptation_pressure, dict):
            if execution_adaptation_pressure.get("follow_up_window_description"):
                next_window = (
                    f"{next_window} {execution_adaptation_pressure['follow_up_window_description']}"
                )
            if execution_adaptation_pressure.get("reason"):
                watchout = f"{watchout} {execution_adaptation_pressure['reason']}"
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

    if feedback_context.get("is_actionable") and focus != "execution_review":
        guardrail = _build_execution_feedback_guardrail(feedback_context)
        if guardrail.get("today"):
            today_action = f"{today_action} {guardrail['today']}"
        if guardrail.get("next_window"):
            next_window = f"{next_window} {guardrail['next_window']}"
        if guardrail.get("watchout"):
            watchout = f"{watchout} {guardrail['watchout']}"
        if isinstance(execution_microcycle, dict):
            if execution_microcycle.get("today_action"):
                today_action = f"{today_action} {execution_microcycle['today_action']}"
            if execution_microcycle.get("next_window"):
                next_window = f"{next_window} {execution_microcycle['next_window']}"
            if execution_microcycle.get("guardrail"):
                watchout = f"{watchout} {execution_microcycle['guardrail']}"
        if isinstance(execution_adaptation_pressure, dict):
            if execution_adaptation_pressure.get("follow_up_window_description"):
                next_window = (
                    f"{next_window} {execution_adaptation_pressure['follow_up_window_description']}"
                )
            if execution_adaptation_pressure.get("reason"):
                watchout = f"{watchout} {execution_adaptation_pressure['reason']}"

    prompt = _append_plan_context_to_prompt(prompt, goal_plan, feedback_context)

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

    signals.extend(_collect_execution_feedback_signals(feedback_context))
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


def build_operational_response_contract(summary: Dict[str, Any] | None) -> Dict[str, Any] | None:
    """Build a deterministic first-response contract for dashboard/entry coaching flows."""
    if not isinstance(summary, dict):
        return None

    today_action = str(summary.get("today_action") or "").strip()
    next_window = str(summary.get("next_window") or "").strip()
    watchout = str(summary.get("watchout") or "").strip()
    reason = str(summary.get("reason") or "").strip()
    if not any([today_action, next_window, watchout, reason]):
        return None

    return {
        "mode": "operational_brief",
        "preview_label": OPERATIONAL_RESPONSE_PREVIEW,
        "today_action": today_action,
        "next_window": next_window,
        "watchout": watchout,
        "reason": reason,
        "prompt_suffix": (
            "Верни первый ответ в строгом operational формате:\n"
            "1. Сегодня — одно короткое действие на сегодня.\n"
            "2. Ближайшие 2-3 дня — как вести себя в ближайшем окне.\n"
            "3. Не делать — один главный запрет или риск.\n"
            "4. Почему — коротко объясни логику через текущие сигналы и план.\n"
            "После этих 4 пунктов можешь добавить короткий раздел «Разбор AI», если он реально нужен."
        ),
    }
