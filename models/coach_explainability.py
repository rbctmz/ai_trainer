from __future__ import annotations

from typing import Any, Dict, List


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _collect_planning_signals(goal_plan: Dict[str, Any] | None) -> List[str]:
    if not isinstance(goal_plan, dict):
        return []

    constraint_summary = goal_plan.get("constraint_summary", {}) or {}
    if not isinstance(constraint_summary, dict):
        return []

    signals: List[str] = []
    load_state_label = constraint_summary.get("load_state_label")
    if load_state_label and load_state_label != "Нейтральный старт":
        signals.append(f"Последний план учитывает состояние: {load_state_label}.")

    interruption_label = constraint_summary.get("interruption_label", "Нет")
    interruption_weeks = int(constraint_summary.get("interruption_weeks", 0) or 0)
    if interruption_label != "Нет" and interruption_weeks > 0:
        signals.append(f"Последний план уже адаптирован под сценарий «{interruption_label}» на {interruption_weeks} нед.")

    notes = constraint_summary.get("notes", [])
    if isinstance(notes, list):
        for note in notes:
            if not note:
                continue
            text = str(note)
            if "Стартовое состояние:" in text:
                signals.append(text)
                break

    return signals[:3]


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
        "signals": signals,
    }
