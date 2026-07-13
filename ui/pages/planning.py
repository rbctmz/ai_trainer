"""Training planning page renderer."""
from __future__ import annotations

import html
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, Any, Dict, List, Mapping

import pandas as pd
import streamlit as st

from models.banister import tsb_zone
from models.plan_events import build_primary_event, synchronize_goal_plan_events
from models.planning_near_term import (
    EDITABLE_NEAR_TERM_HORIZON_MAX,
    EDITABLE_NEAR_TERM_HORIZON_MIN,
    EDITABLE_SESSION_ROLES,
    EDITABLE_SPORTS,
    apply_near_term_day_edits,
    build_near_term_edit_draft_rows,
    build_near_term_edit_seed_from_goal_plans,
    build_near_term_edit_rows,
    build_safer_near_term_draft,
    summarize_near_term_draft_rows,
)
from models.planning_execution import rebuild_goal_plan_with_adjustment
from models.planning_execution import summarize_execution_corrective_microcycle
from ui.plotly_theme import apply_plotly_theme
from models.planning_summary import (
    NEAR_TERM_EDIT_POST_STRATEGIES,
    NEAR_TERM_EDIT_POST_STRATEGY_LABELS_RU,
    summarize_execution_adaptation_pressure,
    summarize_near_term_edit,
)

if TYPE_CHECKING:
    from state import StateManager


PLANNING_WORKSPACE_MODES = (
    "Собрать план",
    "Скорректировать выполнение",
    "Экспорт и детали",
)
# Near-duplicate of api/planning_service.py::_TSB_TONE_TO_FORECAST_MESSAGE
# (same canonical tones, this page's own wording) -- see issue #63.
_TSB_TONE_TO_FORECAST_MESSAGE = {
    "success": "🟢 Отличный прогноз! Вы будете в пиковой форме.",
    "neutral": "🟡 Хорошая нагрузка для поддержания формы.",
    "warning": "🟠 Внимание: возможно накопление усталости.",
    "danger": "🔴 Предупреждение: высокий риск переутомления!",
}
SPORT_LABELS_RU = {
    "run": "бег",
    "bike": "вело",
    "swim": "плавание",
    "strength": "силовая",
    "gym": "зал",
    "walk": "ходьба",
}
WEEKDAY_SHORT_LABELS_RU = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
PLAN_FACT_STATUS_META = {
    "matched": {
        "label": "Совпадает",
        "badge_bg": "#dcfce7",
        "badge_fg": "#166534",
        "badge_bg_dark": "#0d3b22",
        "badge_fg_dark": "#7ef0b0",
        "card_border": "#22c55e",
        "action_label": "Подтвердить Garmin",
        "action_hint": "У дня уже найден совпавший факт: подтвердите автоподстановку или поправьте его перед checkpoint.",
    },
    "other_sport": {
        "label": "Другой спорт",
        "badge_bg": "#fef3c7",
        "badge_fg": "#92400e",
        "badge_bg_dark": "#3d2f08",
        "badge_fg_dark": "#f5c969",
        "card_border": "#f59e0b",
        "action_label": "Проверить mismatch",
        "action_hint": "План и факт расходятся по виду спорта: решите, считать ли день выполненным иначе.",
    },
    "planned_only": {
        "label": "Нет факта",
        "badge_bg": "#fee2e2",
        "badge_fg": "#991b1b",
        "badge_bg_dark": "#3d1212",
        "badge_fg_dark": "#f08a8a",
        "card_border": "#ef4444",
        "action_label": "Зафиксировать факт",
        "action_hint": "У дня нет подтвержденного факта: отметьте пропуск или введите реальный TSS вручную.",
    },
    "upcoming": {
        "label": "Впереди",
        "badge_bg": "#dbeafe",
        "badge_fg": "#1d4ed8",
        "badge_bg_dark": "#10243f",
        "badge_fg_dark": "#8ab4f8",
        "card_border": "#3b82f6",
        "action_label": "Открыть день",
        "action_hint": "День еще впереди: можно заранее проверить план и при необходимости скорректировать ближайшее окно.",
    },
    "off_day": {
        "label": "Отдых",
        "badge_bg": "#e5e7eb",
        "badge_fg": "#374151",
        "badge_bg_dark": "#2a2a2a",
        "badge_fg_dark": "#b5b5b5",
        "card_border": "#9ca3af",
        "action_label": "Проверить отдых",
        "action_hint": "Это день отдыха: убедитесь, что лишний факт не нужно учитывать в локальном replanning.",
    },
    "unplanned_actual": {
        "label": "Вне плана",
        "badge_bg": "#ede9fe",
        "badge_fg": "#6d28d9",
        "badge_bg_dark": "#2a1d44",
        "badge_fg_dark": "#c4a3f5",
        "card_border": "#8b5cf6",
        "action_label": "Проверить вне плана",
        "action_hint": "В этот день найден факт вне плана: решите, как он должен повлиять на ближайший микросикл.",
    },
}


def _strategy_label(strategy: str) -> str:
    return "Наверстать аккуратно" if strategy == "catch_up" else "Беречь восстановление"


def _infer_sport_for_export(parts: Dict[str, Any], session_template: Dict[str, Any] | None = None) -> str:
    sport = str((session_template or {}).get("sport") or "").strip().lower()
    if sport and sport != "off":
        return sport
    bike = float(parts.get("bike", 0.0) or 0.0)
    run = float(parts.get("run", 0.0) or 0.0)
    swim = float(parts.get("swim", 0.0) or 0.0)
    if bike >= max(run, swim):
        return "bike"
    if swim >= max(run, bike):
        return "swim"
    return "run"


def _resolve_target_weekly_tss_control(
    auto_suggested: int | float | None,
    t_min: int,
    t_max: int,
    availability_cap_tss: int,
) -> Dict[str, Any]:
    """Resolve a safe UI state for the target weekly TSS control."""
    distance_floor = max(100, int(t_min))
    distance_ceiling = max(distance_floor, int(t_max))
    effective_cap = max(100, int(availability_cap_tss))
    default_target = int(auto_suggested or int((distance_floor + distance_ceiling) / 2))
    resolved_value = max(100, min(default_target, effective_cap, distance_ceiling))
    slider_max = min(max(300, distance_ceiling), effective_cap)

    if slider_max <= distance_floor:
        return {
            "is_fixed": True,
            "value": resolved_value,
            "slider_min": distance_floor,
            "slider_max": slider_max,
            "reason": "availability_cap" if resolved_value < distance_floor else "single_value",
        }

    return {
        "is_fixed": False,
        "value": max(distance_floor, min(slider_max, resolved_value)),
        "slider_min": distance_floor,
        "slider_max": slider_max,
        "reason": "range",
    }


def _resolve_target_weekly_tss_step(slider_min: int, slider_max: int) -> int:
    """Choose a slider step that remains valid for narrow achievable ranges."""
    span = max(0, int(slider_max) - int(slider_min))
    if span <= 10:
        return 1
    if span <= 25:
        return 5
    return 25


def _align_slider_value(value: int | float, *, min_value: int, max_value: int, step: int) -> int:
    """Clamp an integer slider value so it matches the slider's accessible step values."""
    safe_min = int(min_value)
    safe_max = max(safe_min, int(max_value))
    safe_step = max(1, int(step))
    clamped = max(safe_min, min(int(round(float(value or 0))), safe_max))
    offset = clamped - safe_min
    aligned = safe_min + int(round(offset / safe_step)) * safe_step
    return max(safe_min, min(aligned, safe_max))


def _resolve_near_term_tss_widget_max(
    current_total_tss: int | float,
    draft_total_tss: int | float,
    widget_value: int | float,
) -> int:
    """Keep the near-term TSS input range compatible with draft and session-state values."""
    current_value = int(round(float(current_total_tss or 0.0)))
    draft_value = int(round(float(draft_total_tss or 0.0)))
    session_value = int(round(float(widget_value or 0.0)))
    return max(180, current_value + 80, draft_value, session_value)


def _normalize_planning_workspace_mode(value: Any, *, has_goal_plan: bool) -> str:
    """Resolve a stable planning workspace mode for the current page state."""
    mode = str(value or "").strip()
    if mode not in PLANNING_WORKSPACE_MODES:
        return PLANNING_WORKSPACE_MODES[0]
    if not has_goal_plan and mode != PLANNING_WORKSPACE_MODES[0]:
        return PLANNING_WORKSPACE_MODES[0]
    return mode


def _resolve_planning_start_week(base_date: date | None = None) -> date:
    """Choose the weekly plan anchor date, avoiding a near-finished current week."""
    today = base_date or datetime.now().date()
    current_week_start = today - timedelta(days=today.weekday())
    remaining_days_in_week = 7 - today.weekday()
    if remaining_days_in_week <= 3:
        return current_week_start + timedelta(days=7)
    return current_week_start


def _build_initial_goal_plan_payload(
    *,
    event_date: date,
    **plan_fields: Any,
) -> Dict[str, Any]:
    """Attach the selected A event to a newly built legacy plan payload."""
    label = " ".join(
        str(plan_fields.get(key) or "").strip()
        for key in ("goal_type", "distance")
        if str(plan_fields.get(key) or "").strip()
    )
    initial_event = build_primary_event(event_date, label)
    return synchronize_goal_plan_events({
        **plan_fields,
        "event_date": event_date.isoformat(),
        "events": [initial_event] if initial_event is not None else [],
    })


def _build_plan_explainability(goal_plan: Dict[str, Any]) -> Dict[str, Any]:
    """Build a concise, UI-friendly explanation for the generated plan."""
    adjusted = [int(round(value)) for value in goal_plan.get("weekly_tss_plan", [])]
    base = [int(round(value)) for value in goal_plan.get("base_weekly_tss_plan", adjusted)]
    phases = goal_plan.get("phases", [])
    weekly_summary = goal_plan.get("weekly_summary", [])
    constraint_summary = goal_plan.get("constraint_summary", {}) or {}
    plan_adjustment = constraint_summary.get("plan_adjustment", {}) or {}

    comparison_rows: List[Dict[str, Any]] = []
    changed_weeks = 0
    for idx, adjusted_value in enumerate(adjusted):
        base_value = base[idx] if idx < len(base) else adjusted_value
        delta = adjusted_value - base_value
        if delta != 0:
            changed_weeks += 1
        phase = phases[idx] if idx < len(phases) else "Base"
        week_start = ""
        if idx < len(weekly_summary):
            week_start_value = weekly_summary[idx].get("week_start")
            if week_start_value is not None:
                week_start = week_start_value.strftime("%d.%m")
        note = "—"
        if idx < len(weekly_summary):
            note = weekly_summary[idx].get("adjustment_note", "—")
        comparison_rows.append(
            {
                "Неделя": f"{idx + 1} • {week_start}" if week_start else str(idx + 1),
                "Фаза": phase,
                "Базовый TSS": base_value,
                "Адаптивный TSS": adjusted_value,
                "Δ TSS": f"{delta:+d}",
                "Почему": note,
            }
        )

    peak_before = max(base) if base else 0
    peak_after = max(adjusted) if adjusted else 0
    total_before = sum(base)
    total_after = sum(adjusted)
    capacity_tss = int(constraint_summary.get("weekly_capacity_tss", peak_after or 0))
    availability_days = ", ".join(constraint_summary.get("available_day_labels", [])) or "Все дни"
    interruption_label = constraint_summary.get("interruption_label", "Нет")
    catch_up_strategy = constraint_summary.get("catch_up_strategy", "protect_recovery")
    recovered_tss = int(constraint_summary.get("recovered_tss", 0))
    capacity_loss = int(constraint_summary.get("capacity_loss_tss", 0))
    interruption_loss = int(constraint_summary.get("interruption_loss_tss", 0))
    interruption_weeks = int(constraint_summary.get("interruption_weeks", 0))
    available_day_count = int(constraint_summary.get("available_day_count", 0))
    recommended_days = int(constraint_summary.get("recommended_days", 0))
    plan_adjustment_label = str(plan_adjustment.get("label", "Нет") or "Нет")
    plan_adjustment_weeks = int(plan_adjustment.get("weeks", 0) or 0)
    plan_adjustment_loss = int(constraint_summary.get("plan_adjustment_loss_tss", 0))
    plan_adjustment_recovered = int(constraint_summary.get("plan_adjustment_recovered_tss", 0))
    near_term_edit = summarize_near_term_edit(constraint_summary)
    execution_corrective_microcycle = summarize_execution_corrective_microcycle(
        plan_adjustment.get("execution_corrective_microcycle")
    )
    execution_adaptation_pressure = summarize_execution_adaptation_pressure(
        plan_adjustment.get("execution_adaptation_pressure")
    )
    summary_notes = list(constraint_summary.get("notes", []))
    first_week_structure = ""
    if weekly_summary:
        first_week_structure = str(weekly_summary[0].get("structure_summary", "") or "")
        if first_week_structure:
            summary_notes = [f"Структура первой недели: {first_week_structure}"] + summary_notes

    if plan_adjustment_loss > 0 and plan_adjustment_recovered > 0:
        headline = "План локально пересчитывает ближайшие недели после сбоя: сначала снимает объём, затем возвращает только безопасную часть в коротком окне."
    elif plan_adjustment_loss > 0:
        headline = "План локально упрощает ближайшие недели после сбоя и не размазывает пропущенный объём по всему циклу."
    elif interruption_loss > 0 and catch_up_strategy == "catch_up":
        headline = "План сначала снижает нагрузку из-за ограничения, затем возвращает только безопасную часть объёма."
    elif interruption_loss > 0:
        headline = "План защищает восстановление: первые недели упрощены, а пропущенный объём не догоняется автоматически."
    elif capacity_loss > 0:
        headline = "План подрезает пик под ваш реальный календарь, чтобы нагрузка оставалась выполнимой."
    else:
        headline = "Текущая доступность позволяет почти не менять базовый план — ограничения скорее подтверждают цель, чем режут её."

    return {
        "headline": headline,
        "peak_before": peak_before,
        "peak_after": peak_after,
        "peak_delta": peak_after - peak_before,
        "total_before": total_before,
        "total_after": total_after,
        "total_delta": total_after - total_before,
        "changed_weeks": changed_weeks,
        "capacity_tss": capacity_tss,
        "availability_days": availability_days,
        "available_hours": constraint_summary.get("available_hours", 0.0),
        "available_day_count": available_day_count,
        "recommended_days": recommended_days,
        "interruption_label": interruption_label,
        "interruption_weeks": interruption_weeks,
        "catch_up_label": _strategy_label(catch_up_strategy),
        "recovered_tss": recovered_tss,
        "plan_adjustment_label": plan_adjustment_label,
        "plan_adjustment_weeks": plan_adjustment_weeks,
        "plan_adjustment_loss_tss": plan_adjustment_loss,
        "plan_adjustment_recovered_tss": plan_adjustment_recovered,
        "execution_corrective_microcycle": execution_corrective_microcycle,
        "execution_adaptation_pressure": execution_adaptation_pressure,
        "near_term_edit": near_term_edit,
        "summary_notes": summary_notes,
        "comparison_rows": comparison_rows,
    }


def _render_active_plan_workspace_summary(
    goal_plan: Dict[str, Any],
    *,
    title: str,
    caption: str,
) -> Dict[str, Any]:
    """Render a compact summary of the active plan for non-export workflows."""
    from utils.modern_ui import ModernUI

    explain = _build_plan_explainability(goal_plan)
    ModernUI.render_section_title(title, caption)
    metric_cols = st.columns(4)
    with metric_cols[0]:
        ModernUI.render_stat_card("Пик TSS", explain["peak_after"], "нагрузка", "success")
    with metric_cols[1]:
        ModernUI.render_stat_card("Сумма TSS", explain["total_after"], "весь план", "neutral")
    with metric_cols[2]:
        ModernUI.render_stat_card("Стратегия", explain["catch_up_label"], "после сбоя", "info")
    with metric_cols[3]:
        checkpoint_tone = "warning" if explain["plan_adjustment_label"] != "Нет" else "neutral"
        ModernUI.render_stat_card("Checkpoint", explain["plan_adjustment_label"], "реальность недели", checkpoint_tone)

    follow_up = None
    if explain["execution_adaptation_pressure"] is not None:
        follow_up = (
            "После окна: "
            f"{explain['execution_adaptation_pressure']['follow_up_label']} · "
            f"{explain['execution_adaptation_pressure']['follow_up_window_description']}"
        )
    elif explain["near_term_edit"] is not None:
        follow_up = (
            "Активный override: "
            f"{explain['near_term_edit']['compact_label']} · "
            f"{explain['near_term_edit']['follow_up_description']}"
        )
    summary_body = explain["headline"] if follow_up is None else f"{explain['headline']} {follow_up}"
    ModernUI.render_text_card(
        "Что изменится в плане",
        summary_body,
        eyebrow="Plan ready",
        tone=checkpoint_tone,
    )
    return explain


def _build_planning_v2_summary(
    goal_plan: Mapping[str, Any],
    activities_df: pd.DataFrame | None,
    current_metrics: Mapping[str, Any],
    *,
    reference_date: date | None = None,
) -> Dict[str, Any]:
    """Build a testable active-plan command center summary for Planning V2."""
    daily_plan = list(goal_plan.get("daily_plan", []) or [])
    weekly_summary = list(goal_plan.get("weekly_summary", []) or [])
    explain = _build_plan_explainability(dict(goal_plan))
    today = reference_date or datetime.now().date()

    plan_dates = [_coerce_calendar_date(entry[0]) for entry in daily_plan if isinstance(entry, (list, tuple)) and entry]
    plan_dates = [item for item in plan_dates if item is not None]
    first_plan_date = min(plan_dates) if plan_dates else None
    last_plan_date = max(plan_dates) if plan_dates else None
    days_to_goal = (last_plan_date - today).days if last_plan_date is not None else None

    default_week_index = _resolve_plan_fact_calendar_default_week(dict(goal_plan), reference_date=today)
    timeline_rows = _build_plan_fact_timeline_rows(dict(goal_plan), activities_df)
    selected_timeline = None
    if timeline_rows:
        selected_timeline = next(
            (row for row in timeline_rows if int(row["week_index"]) == int(default_week_index)),
            timeline_rows[0],
        )
    selected_week_label = (
        str(selected_timeline["week_label"])
        if selected_timeline is not None
        else f"Неделя {default_week_index + 1}"
    )
    review_brief = _build_plan_fact_review_brief(timeline_rows, selected_week_label) if timeline_rows else None

    rows = _build_plan_fact_calendar_rows(
        dict(goal_plan),
        activities_df,
        week_index=default_week_index,
    )
    week_summary = _build_plan_fact_week_summary(rows) if rows else {
        "matched": 0,
        "mismatch": 0,
        "prefill_ready": 0,
        "unplanned_actual": 0,
        "upcoming": 0,
    }

    current_ctl = float(current_metrics.get("ctl") or 0.0)
    current_tsb = float(current_metrics.get("tsb") or 0.0)
    current_atl = float(current_metrics.get("atl") or 0.0)
    if review_brief is not None:
        correction_headline = str(review_brief["headline"])
        correction_body = str(review_brief["body"])
        correction_action = str(review_brief["next_action"])
        correction_tone = str(review_brief["tone"])
    elif selected_timeline is not None and int(selected_timeline.get("planned_total_tss", 0) or 0) > 0:
        correction_headline = "Неделя идёт без явного сигнала"
        correction_body = "Пока достаточно следить за план-факт и не открывать редактор без причины."
        correction_action = "Открывайте корректировку только при пропуске, wrong sport или заметном снижении нагрузки."
        correction_tone = "neutral"
    else:
        correction_headline = "План требует первой сверки"
        correction_body = "Для выбранной недели пока мало данных."
        correction_action = "Проверьте план-факт после следующей синхронизации Garmin."
        correction_tone = "neutral"

    phase = "—"
    if default_week_index < len(weekly_summary):
        phase = str(weekly_summary[default_week_index].get("phase") or "—")

    return {
        "goal": {
            "title": f"{goal_plan.get('goal_type', 'Цель')} · {goal_plan.get('distance', 'дистанция')}",
            "goal_type": str(goal_plan.get("goal_type") or "—"),
            "distance": str(goal_plan.get("distance") or "—"),
            "start_date": first_plan_date.isoformat() if first_plan_date else "—",
            "race_date": last_plan_date.isoformat() if last_plan_date else "—",
            "days_to_goal": days_to_goal,
            "phase": phase,
        },
        "progress": {
            "headline": explain["headline"],
            "current_ctl": round(current_ctl, 1),
            "current_atl": round(current_atl, 1),
            "current_tsb": round(current_tsb, 1),
            "peak_tss": int(explain["peak_after"]),
            "total_tss": int(explain["total_after"]),
            "strategy": str(explain["catch_up_label"]),
            "checkpoint": str(explain["plan_adjustment_label"]),
        },
        "current_week": {
            "week_index": default_week_index,
            "label": selected_week_label,
            "planned_tss": int(selected_timeline.get("planned_total_tss", 0) if selected_timeline else 0),
            "actual_tss": int(selected_timeline.get("actual_total_tss", 0) if selected_timeline else 0),
            "delta_tss": int(selected_timeline.get("delta_tss", 0) if selected_timeline else 0),
            "status": str(selected_timeline.get("status_label", "—") if selected_timeline else "—"),
            "matched": int(week_summary["matched"]),
            "mismatch": int(week_summary["mismatch"]),
            "prefill_ready": int(week_summary["prefill_ready"]),
            "unplanned_actual": int(week_summary["unplanned_actual"]),
            "upcoming": int(week_summary["upcoming"]),
        },
        "correction": {
            "headline": correction_headline,
            "body": correction_body,
            "next_action": correction_action,
            "tone": correction_tone,
            "button": "Открыть корректировку факта",
        },
        "diagnostics": {
            "explain": explain,
            "timeline_rows": timeline_rows,
        },
    }


def _render_planning_v2_active_plan(
    state: "StateManager",
    goal_plan: Dict[str, Any],
    activities_df: pd.DataFrame | None,
    current_metrics: Mapping[str, Any],
) -> Dict[str, Any]:
    """Render the review-first active plan shell for Planning V2."""
    from utils.modern_ui import ModernUI

    summary = _build_planning_v2_summary(goal_plan, activities_df, current_metrics)

    ModernUI.render_section_title("Цель", "Что тренируем и сколько времени осталось.")
    title_cols = st.columns([1.35, 0.8, 0.8, 0.8])
    with title_cols[0]:
        days_to_goal = summary["goal"]["days_to_goal"]
        ModernUI.render_text_card(
            summary["goal"]["title"],
            f"До финального дня плана: {days_to_goal} дн." if days_to_goal is not None else "Дата цели не определена.",
            eyebrow=summary["goal"]["goal_type"],
            tone="success",
            footer=f"Дистанция: {summary['goal']['distance']}",
        )
    with title_cols[1]:
        ModernUI.render_stat_card("Фаза", summary["goal"]["phase"], "текущий блок", "neutral")
    with title_cols[2]:
        ModernUI.render_stat_card("Старт", summary["goal"]["start_date"], "первый день", "info")
    with title_cols[3]:
        ModernUI.render_stat_card("Финиш", summary["goal"]["race_date"], "день цели", "warning")

    ModernUI.render_section_title("Путь к цели", summary["progress"]["headline"])
    progress_cols = st.columns(5)
    with progress_cols[0]:
        ModernUI.render_stat_card("CTL", summary["progress"]["current_ctl"], "fitness", "neutral")
    with progress_cols[1]:
        ModernUI.render_stat_card("ATL", summary["progress"]["current_atl"], "fatigue", "warning")
    with progress_cols[2]:
        tsb_tone = tsb_zone(float(summary["progress"]["current_tsb"]))["tone"]
        ModernUI.render_stat_card("TSB", summary["progress"]["current_tsb"], "form", tsb_tone)
    with progress_cols[3]:
        ModernUI.render_stat_card("Пик", f"{summary['progress']['peak_tss']} TSS", "нагрузка", "success")
    with progress_cols[4]:
        ModernUI.render_stat_card("Стратегия", summary["progress"]["strategy"], summary["progress"]["checkpoint"], "info")

    ModernUI.render_section_title("Текущая неделя", "Plan/fact без таблицы на первом экране.")
    week_cols = st.columns([1.25, 0.9, 0.9, 0.9, 0.9])
    week_tone = "warning" if summary["current_week"]["delta_tss"] < 0 else "success"
    with week_cols[0]:
        ModernUI.render_text_card(
            summary["current_week"]["label"],
            summary["current_week"]["status"],
            eyebrow="Selected week",
            tone=week_tone,
        )
    with week_cols[1]:
        ModernUI.render_stat_card("План", f"{summary['current_week']['planned_tss']} TSS", "target", "neutral")
    with week_cols[2]:
        ModernUI.render_stat_card("Факт", f"{summary['current_week']['actual_tss']} TSS", "Garmin", week_tone)
    with week_cols[3]:
        ModernUI.render_stat_card("Δ", f"{summary['current_week']['delta_tss']:+d} TSS", "gap", week_tone)
    with week_cols[4]:
        ModernUI.render_stat_card("Проверки", summary["current_week"]["mismatch"], "mismatch", "warning")
    ModernUI.render_text_card(
        "Сводка сверки",
        (
            f"Совпало: {summary['current_week']['matched']} · "
            f"Garmin-ready: {summary['current_week']['prefill_ready']} · "
            f"Вне плана: {summary['current_week']['unplanned_actual']} · "
            f"Впереди: {summary['current_week']['upcoming']}."
        ),
        tone=week_tone,
    )

    ModernUI.render_section_title("Коррекция", "Открывайте редактор только когда есть реальная задача.")
    ModernUI.render_text_card(
        summary["correction"]["headline"],
        summary["correction"]["body"],
        eyebrow="Next decision",
        tone=summary["correction"]["tone"],
        footer=summary["correction"]["next_action"],
    )
    if st.button(
        summary["correction"]["button"],
        key="planning_v2_open_execution_editor",
        type="primary",
        width="stretch",
    ):
        st.session_state["planning_v2_execution_editor_visible"] = True
        st.rerun()

    return summary


def _build_daily_session_rows(goal_plan: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Build a daily session breakdown with recovery-aware roles and focuses."""
    daily_plan = goal_plan.get("daily_plan", [])
    weekly_summary = goal_plan.get("weekly_summary", [])
    session_templates = goal_plan.get("session_templates", [])
    rows: List[Dict[str, Any]] = []

    for idx, (dt, total, parts) in enumerate(daily_plan):
        week_idx = idx // 7
        day_idx = idx % 7
        week_meta = weekly_summary[week_idx] if week_idx < len(weekly_summary) else {}
        day_roles = week_meta.get("day_roles") or ["—"] * 7
        day_focuses = week_meta.get("day_focuses") or ["—"] * 7
        session_template = session_templates[idx] if idx < len(session_templates) else {}

        rows.append(
            {
                "date": dt.strftime("%Y-%m-%d"),
                "phase": session_template.get("phase", week_meta.get("phase", "—")),
                "sport": session_template.get("sport", "—"),
                "session_role": session_template.get("session_role", day_roles[day_idx] if day_idx < len(day_roles) else "—"),
                "session_focus": session_template.get("session_focus", day_focuses[day_idx] if day_idx < len(day_focuses) else "—"),
                "session_name": session_template.get("export_name", "—"),
                "duration_minutes": session_template.get("duration_minutes", 0),
                "total_tss": total,
                "run_tss": parts.get("run", 0.0),
                "bike_tss": parts.get("bike", 0.0),
                "swim_tss": parts.get("swim", 0.0),
            }
        )

    return rows


def _normalize_plan_fact_sport(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if not normalized or normalized in {"—", "off", "rest"}:
        return ""
    if any(token in normalized for token in ("swim", "swimming", "плав")):
        return "swim"
    if any(token in normalized for token in ("bike", "cycling", "cycle", "ride", "вело", "велосип")):
        return "bike"
    if any(token in normalized for token in ("run", "running", "бег")):
        return "run"
    if any(token in normalized for token in ("strength", "gym", "сил", "зал")):
        return "gym"
    if any(token in normalized for token in ("walk", "ход")):
        return "walk"
    return normalized


def _coerce_calendar_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if hasattr(value, "to_pydatetime"):
        try:
            return value.to_pydatetime().date()
        except Exception:
            return None
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        pass
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _format_duration_label(value: Any) -> str:
    minutes = max(0, int(round(float(value or 0.0))))
    if minutes <= 0:
        return "0 мин"
    hours, remainder = divmod(minutes, 60)
    if hours <= 0:
        return f"{remainder} мин"
    return f"{hours} ч {remainder:02d} м" if remainder else f"{hours} ч"


def _format_calendar_day_label(day_date: date) -> str:
    weekday_label = WEEKDAY_SHORT_LABELS_RU[day_date.weekday()]
    return f"{weekday_label} {day_date.strftime('%d.%m')}"


def _build_plan_fact_focus_action(status: Any) -> Dict[str, str]:
    normalized_status = str(status or "").strip().lower()
    status_meta = PLAN_FACT_STATUS_META.get(normalized_status, PLAN_FACT_STATUS_META["planned_only"])
    action_label = str(status_meta.get("action_label") or "Открыть день").strip() or "Открыть день"
    action_hint = str(status_meta.get("action_hint") or "").strip()
    return {
        "label": action_label,
        "hint": action_hint,
    }


def _build_plan_fact_activity_index(activities_df: pd.DataFrame | None) -> Dict[str, Dict[str, Any]]:
    if activities_df is None or activities_df.empty or "date" not in activities_df.columns:
        return {}

    normalized_df = activities_df.copy()
    normalized_df["date"] = pd.to_datetime(normalized_df["date"], errors="coerce").dt.normalize()
    normalized_df = normalized_df[normalized_df["date"].notna()]
    if normalized_df.empty:
        return {}

    sport_series = (
        normalized_df["sport"]
        if "sport" in normalized_df.columns
        else pd.Series([""] * len(normalized_df), index=normalized_df.index)
    )
    duration_series = (
        normalized_df["duration_minutes"]
        if "duration_minutes" in normalized_df.columns
        else pd.Series([0.0] * len(normalized_df), index=normalized_df.index)
    )
    tss_series = (
        normalized_df["tss"]
        if "tss" in normalized_df.columns
        else pd.Series([0.0] * len(normalized_df), index=normalized_df.index)
    )
    normalized_df["normalized_sport"] = sport_series.apply(_normalize_plan_fact_sport)
    normalized_df["duration_minutes"] = pd.to_numeric(duration_series, errors="coerce").fillna(0.0)
    normalized_df["tss"] = pd.to_numeric(tss_series, errors="coerce").fillna(0.0)

    by_date: Dict[str, Dict[str, Any]] = {}
    for day_value, day_df in normalized_df.groupby(normalized_df["date"].dt.date):
        if day_df.empty:
            continue
        main_row = day_df.sort_values(["duration_minutes", "tss"], ascending=False).iloc[0]
        sport_breakdown: Dict[str, Dict[str, Any]] = {}
        for sport_key, sport_df in day_df.groupby("normalized_sport"):
            if not sport_key:
                continue
            sport_breakdown[str(sport_key)] = {
                "count": int(len(sport_df)),
                "total_tss": round(float(sport_df["tss"].sum()), 1),
                "total_duration_minutes": round(float(sport_df["duration_minutes"].sum()), 1),
            }
        by_date[day_value.isoformat()] = {
            "date": day_value.isoformat(),
            "activity_count": int(len(day_df)),
            "actual_total_tss": round(float(day_df["tss"].sum()), 1),
            "actual_total_duration_minutes": round(float(day_df["duration_minutes"].sum()), 1),
            "main_sport": str(main_row.get("normalized_sport") or ""),
            "main_sport_label": SPORT_LABELS_RU.get(
                str(main_row.get("normalized_sport") or ""),
                str(main_row.get("sport") or "другая активность"),
            ),
            "sport_breakdown": sport_breakdown,
        }
    return by_date


def _resolve_plan_fact_calendar_default_week(
    goal_plan: Dict[str, Any],
    *,
    reference_date: date | None = None,
) -> int:
    daily_plan = list(goal_plan.get("daily_plan", []) or [])
    if not daily_plan:
        return 0

    reference = reference_date or datetime.now().date()
    first_day = _coerce_calendar_date(daily_plan[0][0] if daily_plan and isinstance(daily_plan[0], (list, tuple)) else None)
    if first_day is None:
        return 0
    if reference <= first_day:
        return 0

    total_weeks = max(1, (len(daily_plan) + 6) // 7)
    week_index = (reference - first_day).days // 7
    return max(0, min(total_weeks - 1, int(week_index)))


def _build_plan_fact_calendar_rows(
    goal_plan: Dict[str, Any],
    activities_df: pd.DataFrame | None,
    *,
    week_index: int,
    reference_date: date | None = None,
    activity_index: Dict[str, Dict[str, Any]] | None = None,
    dark_mode: bool | None = None,
) -> List[Dict[str, Any]]:
    if dark_mode is None:
        dark_mode = bool(st.session_state.get("dark_mode", False))
    daily_plan = list(goal_plan.get("daily_plan", []) or [])
    session_templates = list(goal_plan.get("session_templates", []) or [])
    if not daily_plan:
        return []

    start = max(0, int(week_index or 0) * 7)
    end = min(len(daily_plan), start + 7)
    resolved_activity_index = activity_index if isinstance(activity_index, dict) else _build_plan_fact_activity_index(activities_df)
    today = reference_date or datetime.now().date()
    rows: List[Dict[str, Any]] = []

    for offset, daily_item in enumerate(daily_plan[start:end]):
        if not isinstance(daily_item, (list, tuple)) or len(daily_item) < 3:
            continue
        dt, total_tss, _parts = daily_item
        day_date = _coerce_calendar_date(dt)
        if day_date is None:
            continue
        absolute_index = start + offset
        session_template = session_templates[absolute_index] if absolute_index < len(session_templates) else {}
        planned_total_tss = round(float(total_tss or 0.0), 1)
        planned_sport = _normalize_plan_fact_sport(session_template.get("sport"))
        planned_duration_minutes = int(session_template.get("duration_minutes", 0) or 0)
        actual_summary = resolved_activity_index.get(day_date.isoformat(), {})
        actual_count = int(actual_summary.get("activity_count", 0) or 0)
        actual_main_sport = str(actual_summary.get("main_sport") or "")

        if planned_total_tss <= 0 and actual_count > 0:
            status = "unplanned_actual"
        elif planned_total_tss <= 0:
            status = "off_day"
        elif actual_count <= 0 and day_date > today:
            status = "upcoming"
        elif actual_count <= 0:
            status = "planned_only"
        elif planned_sport and planned_sport == actual_main_sport:
            status = "matched"
        else:
            status = "other_sport"

        status_meta = PLAN_FACT_STATUS_META[status]
        action_meta = _build_plan_fact_focus_action(status)
        rows.append(
            {
                "absolute_index": absolute_index,
                "date": day_date.isoformat(),
                "date_label": _format_calendar_day_label(day_date),
                "status": status,
                "status_label": status_meta["label"],
                "badge_bg": status_meta["badge_bg_dark" if dark_mode else "badge_bg"],
                "badge_fg": status_meta["badge_fg_dark" if dark_mode else "badge_fg"],
                "card_border": status_meta["card_border"],
                "focus_action_label": action_meta["label"],
                "focus_action_hint": action_meta["hint"],
                "planned_session_name": str(session_template.get("export_name") or "Сессия").strip(),
                "planned_sport": planned_sport,
                "planned_sport_label": SPORT_LABELS_RU.get(planned_sport, planned_sport or "—"),
                "planned_total_tss": planned_total_tss,
                "planned_duration_label": _format_duration_label(planned_duration_minutes),
                "actual_activity_count": actual_count,
                "actual_total_tss": round(float(actual_summary.get("actual_total_tss", 0.0) or 0.0), 1),
                "actual_duration_label": _format_duration_label(actual_summary.get("actual_total_duration_minutes", 0.0)),
                "actual_sport_label": str(actual_summary.get("main_sport_label") or "—").strip() or "—",
            }
        )

    return rows


def _build_plan_fact_week_summary(rows: List[Dict[str, Any]]) -> Dict[str, int]:
    summary = {
        "matched": 0,
        "mismatch": 0,
        "prefill_ready": 0,
        "unplanned_actual": 0,
        "upcoming": 0,
    }
    for row in rows:
        status = str(row.get("status") or "").strip()
        if status == "matched":
            summary["matched"] += 1
            summary["prefill_ready"] += 1
        elif status in {"other_sport", "planned_only"}:
            summary["mismatch"] += 1
        elif status == "unplanned_actual":
            summary["unplanned_actual"] += 1
        elif status == "upcoming":
            summary["upcoming"] += 1
    return summary


def _build_plan_fact_timeline_rows(
    goal_plan: Dict[str, Any],
    activities_df: pd.DataFrame | None,
    *,
    reference_date: date | None = None,
) -> List[Dict[str, Any]]:
    daily_plan = list(goal_plan.get("daily_plan", []) or [])
    weekly_summary = list(goal_plan.get("weekly_summary", []) or [])
    if not daily_plan:
        return []

    total_weeks = max(1, (len(daily_plan) + 6) // 7)
    activity_index = _build_plan_fact_activity_index(activities_df)
    timeline_rows: List[Dict[str, Any]] = []

    for week_index in range(total_weeks):
        week_rows = _build_plan_fact_calendar_rows(
            goal_plan,
            activities_df,
            week_index=week_index,
            reference_date=reference_date,
            activity_index=activity_index,
        )
        if not week_rows:
            continue
        week_summary = _build_plan_fact_week_summary(week_rows)
        planned_total_tss = int(round(sum(float(row.get("planned_total_tss", 0.0) or 0.0) for row in week_rows)))
        actual_total_tss = int(round(sum(float(row.get("actual_total_tss", 0.0) or 0.0) for row in week_rows)))
        actual_day_count = sum(1 for row in week_rows if int(row.get("actual_activity_count", 0) or 0) > 0)
        attention_rows = [
            row
            for row in week_rows
            if str(row.get("status") or "").strip() in {"other_sport", "planned_only", "unplanned_actual"}
        ]
        first_attention_date = str(attention_rows[0]["date"]) if attention_rows else ""
        if week_summary["mismatch"] > 0 or week_summary["unplanned_actual"] > 0:
            status_label = "Нужна проверка"
            action_label = "Проверить drift"
            signal_label = (
                f"Проверки {week_summary['mismatch'] + week_summary['unplanned_actual']} дн."
            )
        elif actual_day_count > 0 and week_summary["upcoming"] > 0:
            status_label = "Идёт по плану"
            action_label = "Открыть неделю"
            signal_label = f"Garmin {week_summary['prefill_ready']} дн. · впереди {week_summary['upcoming']} дн."
        elif week_summary["prefill_ready"] > 0:
            status_label = "Garmin готов"
            action_label = "Открыть неделю"
            signal_label = f"Garmin {week_summary['prefill_ready']} дн."
        elif week_summary["upcoming"] > 0:
            status_label = "Впереди"
            action_label = "Открыть неделю"
            signal_label = f"Впереди {week_summary['upcoming']} дн."
        else:
            status_label = "Ждёт факта"
            action_label = "Открыть неделю"
            signal_label = "Факт не найден"

        week_label = f"Неделя {week_index + 1}"
        if week_index < len(weekly_summary) and weekly_summary[week_index].get("week_start") is not None:
            week_start = weekly_summary[week_index]["week_start"]
            week_label = f"Неделя {week_index + 1} · {week_start.strftime('%d.%m')}"

        timeline_rows.append(
            {
                "week_index": week_index,
                "week_label": week_label,
                "planned_total_tss": planned_total_tss,
                "actual_total_tss": actual_total_tss,
                "delta_tss": actual_total_tss - planned_total_tss,
                "status_label": status_label,
                "action_label": action_label,
                "signal_label": signal_label,
                "prefill_ready": week_summary["prefill_ready"],
                "mismatch": week_summary["mismatch"],
                "unplanned_actual": week_summary["unplanned_actual"],
                "upcoming": week_summary["upcoming"],
                "attention_day_count": len(attention_rows),
                "first_attention_date": first_attention_date,
            }
        )

    return timeline_rows


def _build_plan_fact_replan_signal(
    timeline_rows: List[Dict[str, Any]],
) -> Dict[str, Any] | None:
    drift_rows = [
        row for row in timeline_rows
        if int(row.get("mismatch", 0) or 0) > 0 or int(row.get("unplanned_actual", 0) or 0) > 0
    ]
    if not drift_rows:
        return None

    target_row = drift_rows[0]
    drift_week_count = len(drift_rows)
    attention_day_count = sum(int(row.get("attention_day_count", 0) or 0) for row in drift_rows)
    negative_delta = sum(
        min(0, int(row.get("delta_tss", 0) or 0))
        for row in drift_rows
    )
    horizon_weeks = 2 if drift_week_count >= 2 else 1
    if drift_week_count >= 2 or attention_day_count >= 3 or negative_delta <= -60:
        severity = "high"
        headline = "Накопился multi-week drift"
        action_label = "Предложить мягкий replan"
    else:
        severity = "medium"
        headline = "Недельный drift уже требует проверки"
        action_label = "Открыть проблемную неделю"

    week_word = "нед." if drift_week_count > 1 else "неделе"
    reason = (
        f"Проблемных недель: {drift_week_count} · "
        f"сигнальных дней: {attention_day_count} · "
        f"суммарный Δ TSS: {negative_delta:+d}. "
        f"Начните с {target_row['week_label']}."
    )

    return {
        "severity": severity,
        "headline": headline,
        "action_label": action_label,
        "reason": reason,
        "drift_week_count": drift_week_count,
        "attention_day_count": attention_day_count,
        "delta_tss": negative_delta,
        "target_week_index": int(target_row["week_index"]),
        "target_week_label": str(target_row["week_label"]),
        "target_date": str(target_row.get("first_attention_date") or "").strip(),
        "weeks_horizon": horizon_weeks,
        "follow_up_hint": (
            f"Откроем {drift_week_count} {week_word} для локальной проверки execution drift."
        ),
    }


def _build_plan_fact_review_brief(
    timeline_rows: List[Dict[str, Any]],
    selected_week_label: str,
) -> Dict[str, str] | None:
    if not timeline_rows:
        return None

    selected_row = next(
        (row for row in timeline_rows if str(row.get("week_label")) == str(selected_week_label)),
        timeline_rows[0],
    )
    week_label = str(selected_row.get("week_label") or "Выбранная неделя")
    status_label = str(selected_row.get("status_label") or "Статус неясен")
    signal_label = str(selected_row.get("signal_label") or "нет сигнала")
    planned_tss = int(selected_row.get("planned_total_tss", 0) or 0)
    actual_tss = int(selected_row.get("actual_total_tss", 0) or 0)
    delta_tss = int(selected_row.get("delta_tss", 0) or 0)
    mismatch = int(selected_row.get("mismatch", 0) or 0)
    unplanned = int(selected_row.get("unplanned_actual", 0) or 0)
    prefill_ready = int(selected_row.get("prefill_ready", 0) or 0)
    upcoming = int(selected_row.get("upcoming", 0) or 0)

    if mismatch > 0 or unplanned > 0:
        tone = "warning"
        headline = f"{week_label}: нужна проверка факта"
        next_action = "Откройте детали выбранной недели и проверьте только сигнальные дни."
    elif prefill_ready > 0 and upcoming == 0:
        tone = "success"
        headline = f"{week_label}: Garmin готов к подтверждению"
        next_action = "Если всё совпадает, можно подтверждать окно без ручного разбора каждого дня."
    elif upcoming > 0:
        tone = "info"
        headline = f"{week_label}: план впереди"
        next_action = "Детали можно держать закрытыми до появления факта из Garmin sync."
    else:
        tone = "info"
        headline = f"{week_label}: факт ещё не найден"
        next_action = "После синка Garmin вернитесь к этой неделе для сверки."

    return {
        "tone": tone,
        "headline": headline,
        "body": (
            f"{status_label} · {signal_label} · "
            f"план {planned_tss} TSS / факт {actual_tss} TSS ({delta_tss:+d})."
        ),
        "next_action": next_action,
    }


def _build_plan_fact_calendar_markup(rows: List[Dict[str, Any]]) -> str:
    cards: List[str] = []
    for row in rows:
        if int(row["actual_activity_count"] or 0) > 0:
            actual_block = (
                "<div class='pfv-actual-title'>Факт</div>"
                f"<div class='pfv-actual-main'>{html.escape(str(row['actual_sport_label']))}</div>"
                f"<div class='pfv-actual-meta'>{int(round(float(row['actual_total_tss'] or 0.0)))} TSS · "
                f"{html.escape(str(row['actual_duration_label']))}</div>"
                f"<div class='pfv-actual-meta'>{int(row['actual_activity_count'])} акт.</div>"
            )
        else:
            actual_block = "<div class='pfv-actual-empty'>Факт пока не найден</div>"

        cards.append(
            (
                f"<div class='pfv-card' style='border-top: 4px solid {row['card_border']};'>"
                "<div class='pfv-top'>"
                f"<div class='pfv-day'>{html.escape(str(row['date_label']))}</div>"
                f"<span class='pfv-badge' style='background:{row['badge_bg']}; color:{row['badge_fg']};'>"
                f"{html.escape(str(row['status_label']))}"
                "</span>"
                "</div>"
                "<div class='pfv-plan-title'>План</div>"
                f"<div class='pfv-plan-main'>{html.escape(str(row['planned_session_name']))}</div>"
                f"<div class='pfv-plan-meta'>{html.escape(str(row['planned_sport_label']))} · "
                f"{int(round(float(row['planned_total_tss'] or 0.0)))} TSS</div>"
                f"<div class='pfv-plan-meta'>{html.escape(str(row['planned_duration_label']))}</div>"
                "<div class='pfv-divider'></div>"
                f"{actual_block}"
                "</div>"
            )
        )

    return "<div class='pfv-grid'>" + "".join(cards) + "</div>"


def _render_plan_fact_calendar(
    goal_plan: Dict[str, Any],
    activities_df: pd.DataFrame | None,
    *,
    key_prefix: str,
    title: str,
    focus_state_key: str | None = None,
    show_replan_signal: bool = False,
) -> None:
    daily_plan = list(goal_plan.get("daily_plan", []) or [])
    if not daily_plan:
        return

    total_weeks = max(1, (len(daily_plan) + 6) // 7)
    weekly_summary = list(goal_plan.get("weekly_summary", []) or [])
    default_week_index = _resolve_plan_fact_calendar_default_week(goal_plan)
    week_options = list(range(total_weeks))
    option_labels = []
    for idx in week_options:
        if idx < len(weekly_summary) and weekly_summary[idx].get("week_start") is not None:
            week_start = weekly_summary[idx]["week_start"]
            option_labels.append(f"Неделя {idx + 1} · {week_start.strftime('%d.%m')}")
        else:
            option_labels.append(f"Неделя {idx + 1}")

    st.markdown(title)
    st.caption("Короткая сверка выбранной недели. Подробности раскрываются только когда они нужны.")
    timeline_rows = _build_plan_fact_timeline_rows(goal_plan, activities_df)
    week_key = f"{key_prefix}_week_index"
    default_week_label = option_labels[max(0, min(default_week_index, len(option_labels) - 1))]
    if str(st.session_state.get(week_key) or "").strip() not in option_labels:
        st.session_state[week_key] = default_week_label

    replan_signal = _build_plan_fact_replan_signal(timeline_rows) if show_replan_signal else None
    if replan_signal is not None:
        with st.container(border=True):
            st.markdown(f"**{replan_signal['headline']}**")
            st.caption(replan_signal["reason"])
            if st.button(
                replan_signal["action_label"],
                key=f"{key_prefix}_open_replan_signal",
                type="primary",
                width="stretch",
            ):
                st.session_state[week_key] = replan_signal["target_week_label"]
                if focus_state_key:
                    if replan_signal["target_date"]:
                        st.session_state[focus_state_key] = replan_signal["target_date"]
                    st.session_state[f"{focus_state_key}_action_label"] = replan_signal["action_label"]
                    st.session_state[f"{focus_state_key}_action_hint"] = replan_signal["follow_up_hint"]
                    st.session_state[f"{focus_state_key}_weeks_pending"] = int(replan_signal["weeks_horizon"])
                st.rerun()

    selected_label = st.selectbox(
        "Неделя плана",
        options=option_labels,
        key=week_key,
    )
    if timeline_rows and replan_signal is None:
        review_brief = _build_plan_fact_review_brief(timeline_rows, selected_label)
        if review_brief is not None:
            brief_text = (
                f"**{review_brief['headline']}**\n\n"
                f"{review_brief['body']}\n\n"
                f"{review_brief['next_action']}"
            )
            if review_brief["tone"] == "warning":
                st.warning(brief_text)
            elif review_brief["tone"] == "success":
                st.success(brief_text)
            else:
                st.info(brief_text)

    if timeline_rows:
        with st.expander("Диагностика: таймлайн по неделям", expanded=False):
            st.caption("Для разбора drift. В обычном сценарии достаточно статуса выбранной недели выше.")
            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            "Неделя": row["week_label"],
                            "План TSS": row["planned_total_tss"],
                            "Факт TSS": row["actual_total_tss"],
                            "Δ TSS": f"{int(row['delta_tss']):+d}",
                            "Статус": row["status_label"],
                            "Сигнал": row["signal_label"],
                        }
                        for row in timeline_rows
                    ]
                ),
                width="stretch",
                hide_index=True,
            )
            for chunk_start in range(0, len(timeline_rows), 3):
                chunk = timeline_rows[chunk_start:chunk_start + 3]
                cols = st.columns(len(chunk))
                for col, row in zip(cols, chunk):
                    with col:
                        is_selected = str(selected_label) == str(row["week_label"])
                        if st.button(
                            f"{row['action_label']} · {row['week_label']}",
                            key=f"{key_prefix}_select_week_{row['week_index']}",
                            type="primary" if is_selected else "secondary",
                            width="stretch",
                        ):
                            st.session_state[week_key] = str(row["week_label"])
                            st.rerun()
    selected_week_index = option_labels.index(selected_label)
    rows = _build_plan_fact_calendar_rows(
        goal_plan,
        activities_df,
        week_index=selected_week_index,
    )
    if not rows:
        st.info("Для выбранной недели пока нет данных плана.")
        return

    week_summary = _build_plan_fact_week_summary(rows)
    current_focus = str(st.session_state.get(focus_state_key) or "").strip() if focus_state_key else ""
    focus_inside_week = any(current_focus == str(row.get("date")) for row in rows)
    has_review_signal = week_summary["mismatch"] > 0 or week_summary["unplanned_actual"] > 0
    details_expanded = has_review_signal or focus_inside_week
    details_label = (
        "Проверить выбранную неделю"
        if has_review_signal
        else "Открыть детали выбранной недели"
    )

    with st.expander(details_label, expanded=details_expanded):
        metric_cols = st.columns(5)
        with metric_cols[0]:
            st.metric("Совпало", week_summary["matched"])
        with metric_cols[1]:
            st.metric("Нужны проверки", week_summary["mismatch"])
        with metric_cols[2]:
            st.metric("Garmin-prefill", week_summary["prefill_ready"])
        with metric_cols[3]:
            st.metric("Вне плана", week_summary["unplanned_actual"])
        with metric_cols[4]:
            st.metric("Впереди", week_summary["upcoming"])

        st.markdown(
            """
            <style>
            .pfv-grid {
              display: grid;
              grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
              gap: 0.75rem;
              margin: 0.5rem 0 1rem 0;
            }
            .pfv-card {
              border-radius: 16px;
              padding: 0.9rem;
              background: rgba(255, 255, 255, 0.04);
              box-shadow: 0 1px 3px rgba(15, 23, 42, 0.08);
            }
            .pfv-top {
              display: flex;
              justify-content: space-between;
              align-items: flex-start;
              gap: 0.5rem;
              margin-bottom: 0.75rem;
            }
            .pfv-day {
              font-size: 0.95rem;
              font-weight: 700;
            }
            .pfv-badge {
              border-radius: 999px;
              font-size: 0.72rem;
              font-weight: 700;
              padding: 0.2rem 0.55rem;
              white-space: nowrap;
            }
            .pfv-plan-title, .pfv-actual-title {
              font-size: 0.72rem;
              text-transform: uppercase;
              letter-spacing: 0.04em;
              opacity: 0.72;
              margin-bottom: 0.25rem;
            }
            .pfv-plan-main, .pfv-actual-main {
              font-size: 0.88rem;
              font-weight: 600;
              line-height: 1.35;
              margin-bottom: 0.2rem;
            }
            .pfv-plan-meta, .pfv-actual-meta, .pfv-actual-empty {
              font-size: 0.8rem;
              opacity: 0.86;
              line-height: 1.35;
            }
            .pfv-actual-empty {
              padding: 0.3rem 0 0.1rem 0;
            }
            .pfv-divider {
              height: 1px;
              background: rgba(148, 163, 184, 0.22);
              margin: 0.7rem 0;
            }
            </style>
            """,
            unsafe_allow_html=True,
        )
        st.markdown(_build_plan_fact_calendar_markup(rows), unsafe_allow_html=True)
        if focus_state_key:
            st.caption("Кнопки ниже передают выбранный день в редактор факта.")
            focus_action_label_key = f"{focus_state_key}_action_label"
            focus_action_hint_key = f"{focus_state_key}_action_hint"
            for chunk_start in range(0, len(rows), 4):
                chunk = rows[chunk_start:chunk_start + 4]
                cols = st.columns(len(chunk))
                for col, row in zip(cols, chunk):
                    with col:
                        is_selected = current_focus == str(row["date"])
                        if st.button(
                            str(row["focus_action_label"]),
                            key=f"{key_prefix}_focus_day_{row['date']}",
                            type="primary" if is_selected else "secondary",
                            width="stretch",
                        ):
                            st.session_state[focus_state_key] = str(row["date"])
                            st.session_state[focus_action_label_key] = str(row["focus_action_label"])
                            st.session_state[focus_action_hint_key] = str(row["focus_action_hint"])
                            st.session_state[f"{focus_state_key}_weeks_pending"] = (
                                2 if int(row.get("absolute_index", 0) or 0) >= 7 else 1
                            )
                            st.rerun()


def _build_near_term_draft_preview(
    current_goal_plan: Dict[str, Any],
    draft_goal_plan: Dict[str, Any],
) -> Dict[str, Any]:
    """Summarize week-level impact and the persisted label for the current draft."""
    return _build_goal_plan_transition_preview(current_goal_plan, draft_goal_plan)


def _build_goal_plan_transition_preview(
    current_goal_plan: Dict[str, Any],
    target_goal_plan: Dict[str, Any],
) -> Dict[str, Any]:
    """Summarize week-level impact between two concrete goal plan versions."""
    current_weekly_summary = list(current_goal_plan.get("weekly_summary", []) or [])
    target_weekly_summary = list(target_goal_plan.get("weekly_summary", []) or [])
    weekly_rows: List[Dict[str, Any]] = []

    for idx, target_row in enumerate(target_weekly_summary):
        current_row = current_weekly_summary[idx] if idx < len(current_weekly_summary) else {}
        current_tss = int(current_row.get("weekly_tss", 0) or 0)
        target_tss = int(target_row.get("weekly_tss", current_tss) or 0)
        current_note = str(current_row.get("adjustment_note", "—") or "—")
        target_note = str(target_row.get("adjustment_note", current_note) or "—")

        if current_tss == target_tss and current_note == target_note:
            continue

        week_start_value = target_row.get("week_start") or current_row.get("week_start")
        week_label = str(idx + 1)
        if week_start_value is not None:
            week_label = f"{idx + 1} • {week_start_value.strftime('%d.%m')}"

        weekly_rows.append(
            {
                "Неделя": week_label,
                "Было TSS": current_tss,
                "Станет TSS": target_tss,
                "Δ TSS": f"{target_tss - current_tss:+d}",
                "Почему": target_note,
            }
        )

    return {
        "near_term_edit": summarize_near_term_edit(target_goal_plan.get("constraint_summary", {})),
        "changed_week_count": len(weekly_rows),
        "weekly_rows": weekly_rows,
    }


def _render_near_term_risk_callout(near_term_edit: Dict[str, Any], *, prefix: str) -> None:
    risk_level = str(near_term_edit.get("risk_level") or "low").lower()
    risk_badge = str(near_term_edit.get("risk_badge") or "Риск низкий")
    risk_guardrail = str(near_term_edit.get("risk_guardrail") or "").strip()
    risk_reasons = [
        str(reason).strip()
        for reason in near_term_edit.get("risk_reasons", [])
        if str(reason).strip()
    ]
    body = f"**{prefix}: {risk_badge}.**"
    if risk_guardrail:
        body += f" {risk_guardrail}"

    if risk_level == "high":
        st.error(body)
    elif risk_level == "medium":
        st.warning(body)
    else:
        st.info(body)

    for reason in risk_reasons[:3]:
        st.write(f"• {reason}")


def _render_near_term_editor(
    goal_plan: Dict[str, Any],
    rollback_goal_plan: Dict[str, Any] | None = None,
    rollback_checkpoint_id: int | None = None,
    draft_seed: Dict[str, Any] | None = None,
) -> Dict[str, Any] | None:
    """Render an in-place editor for the next 7-10 days of the current plan."""
    daily_plan = list(goal_plan.get("daily_plan", []) or [])
    if len(daily_plan) < EDITABLE_NEAR_TERM_HORIZON_MIN:
        return None

    max_horizon = min(EDITABLE_NEAR_TERM_HORIZON_MAX, len(daily_plan))
    plan_revision = str(goal_plan.get("plan_revision") or goal_plan.get("start_week") or "current-plan")
    edit_version = int(goal_plan.get("near_term_edit_version", 0) or 0)
    key_prefix = f"{plan_revision}:{edit_version}"

    role_labels = {
        "off": "Отдых",
        "recovery": "Восстановление",
        "easy": "Лёгкая",
        "quality": "Качество",
        "long": "Длительная",
    }
    sport_labels = {
        "run": "бег",
        "bike": "вело",
        "swim": "плавание",
        "off": "отдых",
    }
    role_labels_reverse = {label: code for code, label in role_labels.items()}
    sport_labels_reverse = {label: code for code, label in sport_labels.items()}
    strategy_labels = {
        code: NEAR_TERM_EDIT_POST_STRATEGY_LABELS_RU[code]
        for code in NEAR_TERM_EDIT_POST_STRATEGIES
    }
    strategy_labels_reverse = {label: code for code, label in strategy_labels.items()}

    seed_source_label = ""
    seed_hint = ""
    if isinstance(draft_seed, dict):
        seed_source_label = str(draft_seed.get("source_label") or "").strip()
        seed_hint = str(draft_seed.get("hint") or "").strip()
        seeded_horizon = max(
            EDITABLE_NEAR_TERM_HORIZON_MIN,
            min(max_horizon, int(draft_seed.get("horizon_days") or EDITABLE_NEAR_TERM_HORIZON_MIN)),
        )
        st.session_state[f"near_term_horizon_{key_prefix}"] = seeded_horizon
        seeded_strategy = str(draft_seed.get("post_edit_strategy") or "keep")
        st.session_state[f"near_term_strategy_{key_prefix}"] = strategy_labels.get(
            seeded_strategy,
            strategy_labels["keep"],
        )

    st.markdown("### ✍️ Редактировать ближайшие 7-10 дней")
    with st.expander("Открыть редактор ближайших дней", expanded=bool(draft_seed)):
        st.caption(
            "Этот редактор меняет только ближайшие дни текущего плана. Остальной цикл не перестраивается, "
            "а checkpoint, explainability и экспорты обновятся только после явного применения черновика."
        )
        saved_summary = summarize_near_term_edit(goal_plan.get("constraint_summary", {}))
        if saved_summary is not None:
            st.info(
                "Сейчас в сохранённом checkpoint уже есть ручная правка: "
                f"{saved_summary['compact_label']}."
            )
        default_strategy = "keep"
        if saved_summary is not None:
            default_strategy = str(saved_summary.get("post_edit_strategy") or "keep")
        st.session_state.setdefault(
            f"near_term_strategy_{key_prefix}",
            strategy_labels.get(default_strategy, strategy_labels["keep"]),
        )
        horizon_days = st.slider(
            "Сколько дней открыть для правки:",
            min_value=EDITABLE_NEAR_TERM_HORIZON_MIN,
            max_value=max_horizon,
            value=min(EDITABLE_NEAR_TERM_HORIZON_MIN, max_horizon),
            step=1,
            key=f"near_term_horizon_{key_prefix}",
        )
        editable_rows = build_near_term_edit_rows(goal_plan, horizon_days=horizon_days)
        if isinstance(draft_seed, dict):
            seeded_overrides = {
                int(index): dict(value or {})
                for index, value in (draft_seed.get("overrides_by_index") or {}).items()
                if isinstance(value, dict)
            }
            for row in editable_rows:
                override = seeded_overrides.get(int(row["index"]))
                if not override:
                    continue
                st.session_state[f"near_term_role_{key_prefix}_{row['index']}"] = role_labels[override["session_role"]]
                st.session_state[f"near_term_sport_{key_prefix}_{row['index']}"] = sport_labels[override["sport"]]
                st.session_state[f"near_term_tss_{key_prefix}_{row['index']}"] = int(
                    round(float(override["total_tss"] or 0.0))
                )
        for row in editable_rows:
            st.session_state.setdefault(
                f"near_term_role_{key_prefix}_{row['index']}",
                role_labels[row["current_role"]],
            )
            st.session_state.setdefault(
                f"near_term_sport_{key_prefix}_{row['index']}",
                sport_labels[row["current_sport"]],
            )
            st.session_state.setdefault(
                f"near_term_tss_{key_prefix}_{row['index']}",
                int(round(row["current_total_tss"])),
            )
        if seed_source_label:
            st.info(
                "Черновик открыт из execution microcycle: "
                f"{seed_source_label}. "
                "Если примените эти правки здесь, они сохранятся как ручной override ближнего горизонта, "
                "а не как прямое подтверждение execution checkpoint."
            )
            if seed_hint:
                st.caption(seed_hint)

        overrides_by_index = {
            int(row["index"]): {
                "session_role": role_labels_reverse[
                    st.session_state[f"near_term_role_{key_prefix}_{row['index']}"]
                ],
                "sport": sport_labels_reverse[
                    st.session_state[f"near_term_sport_{key_prefix}_{row['index']}"]
                ],
                "total_tss": st.session_state[f"near_term_tss_{key_prefix}_{row['index']}"],
            }
            for row in editable_rows
        }
        draft_rows = build_near_term_edit_draft_rows(
            editable_rows,
            goal_type=str(goal_plan.get("goal_type") or ""),
            distance=str(goal_plan.get("distance") or ""),
            overrides_by_index=overrides_by_index,
        )
        draft_rows_by_index = {
            int(row["index"]): row
            for row in draft_rows
        }
        draft_summary = summarize_near_term_draft_rows(draft_rows)
        selected_strategy_label = st.selectbox(
            "Что делать с этой дельтой в следующих 1-2 нед.:",
            options=[strategy_labels[code] for code in NEAR_TERM_EDIT_POST_STRATEGIES],
            key=f"near_term_strategy_{key_prefix}",
            disabled=not draft_summary["has_changes"],
        )
        selected_post_edit_strategy = strategy_labels_reverse[selected_strategy_label]
        draft_preview = None
        if draft_summary["has_changes"]:
            draft_preview = _build_near_term_draft_preview(
                goal_plan,
                apply_near_term_day_edits(
                    goal_plan,
                    draft_rows,
                    horizon_days=horizon_days,
                    post_edit_strategy=selected_post_edit_strategy,
                ),
            )
        safer_draft = None
        soften_clicked = False
        rollback_clicked = False
        rollback_preview = None
        if rollback_goal_plan is not None:
            rollback_preview = _build_goal_plan_transition_preview(goal_plan, rollback_goal_plan)

        st.markdown("#### Черновик правок")
        if draft_summary["has_changes"]:
            metric_cols = st.columns(4)
            with metric_cols[0]:
                st.metric("Правок дней", draft_summary["changed_day_count"])
            with metric_cols[1]:
                st.metric(
                    "TSS окна",
                    draft_summary["target_total_tss"],
                    delta=f"{draft_summary['total_delta_tss']:+d}",
                )
            with metric_cols[2]:
                st.metric("Дней отдыха", draft_summary["off_day_count"])
            with metric_cols[3]:
                st.metric("Качественных дней", draft_summary["quality_day_count"])
            st.caption(
                "Это пока только черновик. Сохранённый checkpoint, explainability и экспорты "
                "обновятся после нажатия «Применить правки ближнего горизонта»."
            )
            st.dataframe(
                pd.DataFrame(draft_summary["changed_rows"]),
                width="stretch",
                hide_index=True,
            )
            if draft_preview and draft_preview["near_term_edit"] is not None:
                st.caption(
                    "После применения сохранённый checkpoint покажет: "
                    f"{draft_preview['near_term_edit']['compact_label']}."
                )
                st.caption(draft_preview["near_term_edit"]["follow_up_description"])
                _render_near_term_risk_callout(
                    draft_preview["near_term_edit"],
                    prefix="Оценка правки",
                )
                safer_draft = build_safer_near_term_draft(
                    goal_plan,
                    draft_rows,
                    horizon_days=horizon_days,
                    post_edit_strategy=selected_post_edit_strategy,
                )
                if safer_draft is not None:
                    st.caption(
                        "Можно смягчить черновик одним кликом: "
                        f"{safer_draft['description']}."
                    )
                    st.caption(
                        "Более безопасный вариант даст: "
                        f"{safer_draft['near_term_edit']['compact_label']}."
                    )
                    _render_near_term_risk_callout(
                        safer_draft["near_term_edit"],
                        prefix="Если смягчить",
                    )
                    soften_clicked = st.button(
                        "🛟 Смягчить черновик",
                        key=f"near_term_soften_{key_prefix}",
                        width="stretch",
                    )
            if draft_preview and draft_preview["weekly_rows"]:
                st.markdown("##### Как изменятся недели")
                st.dataframe(
                    pd.DataFrame(draft_preview["weekly_rows"]),
                    width="stretch",
                    hide_index=True,
                )
        else:
            st.info(
                "Черновик совпадает с текущим ближним горизонтом: "
                f"{draft_summary['horizon_days']} дн. · {draft_summary['current_total_tss']} TSS."
            )

        if rollback_goal_plan is not None:
            st.markdown("#### ↩️ Откат последней сохранённой правки")
            current_saved_edit = summarize_near_term_edit(goal_plan.get("constraint_summary", {}))
            if current_saved_edit is not None:
                st.caption(
                    "Текущий checkpoint хранит ручную правку: "
                    f"{current_saved_edit['compact_label']}."
                )
            if rollback_preview and rollback_preview["near_term_edit"] is not None:
                st.caption(
                    "После отката активной станет версия: "
                    f"{rollback_preview['near_term_edit']['compact_label']}."
                )
            else:
                st.caption("После отката ручная правка ближнего горизонта исчезнет из сохранённого checkpoint.")
            if rollback_preview and rollback_preview["weekly_rows"]:
                st.dataframe(
                    pd.DataFrame(rollback_preview["weekly_rows"]),
                    width="stretch",
                    hide_index=True,
                )
            rollback_clicked = st.button(
                "↩️ Откатить последнюю ручную правку",
                key=f"near_term_rollback_{key_prefix}",
                width="stretch",
            )

        for row in editable_rows:
            draft_row = draft_rows_by_index[int(row["index"])]
            role_key = f"near_term_role_{key_prefix}_{row['index']}"
            sport_key = f"near_term_sport_{key_prefix}_{row['index']}"
            tss_key = f"near_term_tss_{key_prefix}_{row['index']}"
            tss_widget_max = _resolve_near_term_tss_widget_max(
                row["current_total_tss"],
                draft_row["total_tss"],
                st.session_state[tss_key],
            )
            with st.container(border=True):
                st.markdown(f"**{row['date_label']} • {row['phase']}**")
                st.caption(
                    f"Сейчас: {draft_row['current_summary']} · ~{row['current_duration_minutes']} мин"
                )
                if draft_row["changed"]:
                    st.caption(
                        f"Черновик: {draft_row['target_summary']} · "
                        f"~{draft_row['target_duration_minutes']} мин · "
                        f"Δ {int(round(float(draft_row['delta_tss'] or 0.0))):+d} TSS"
                    )
                else:
                    st.caption("Черновик пока совпадает с сохранённым днём.")
                col1, col2, col3 = st.columns([1.2, 1, 1])
                with col1:
                    st.selectbox(
                        "Роль дня",
                        options=[role_labels[role] for role in EDITABLE_SESSION_ROLES],
                        key=role_key,
                    )
                with col2:
                    editable_sports = (
                        EDITABLE_SPORTS
                        if row.get("current_kind") == "composite"
                        else [sport for sport in EDITABLE_SPORTS if sport != "brick"]
                    )
                    st.selectbox(
                        "Основной спорт",
                        options=[sport_labels[sport] for sport in editable_sports],
                        key=sport_key,
                    )
                with col3:
                    st.number_input(
                        "TSS",
                        min_value=0,
                        max_value=tss_widget_max,
                        step=5,
                        key=tss_key,
                    )

        action_cols = st.columns([1, 1.4])
        with action_cols[0]:
            reset_clicked = st.button(
                "↺ Сбросить черновик",
                key=f"near_term_reset_{key_prefix}",
                disabled=not draft_summary["has_changes"],
                width="stretch",
            )
        with action_cols[1]:
            apply_clicked = st.button(
                "💾 Применить правки ближнего горизонта",
                key=f"near_term_apply_{key_prefix}",
                type="primary",
                disabled=not draft_summary["has_changes"],
                width="stretch",
            )

        if reset_clicked:
            for row in editable_rows:
                st.session_state[f"near_term_role_{key_prefix}_{row['index']}"] = role_labels[row["current_role"]]
                st.session_state[f"near_term_sport_{key_prefix}_{row['index']}"] = sport_labels[row["current_sport"]]
                st.session_state[f"near_term_tss_{key_prefix}_{row['index']}"] = int(round(row["current_total_tss"]))
            st.rerun()

        if rollback_clicked and rollback_goal_plan is not None:
            restored_goal_plan = dict(rollback_goal_plan)
            restored_goal_plan["plan_revision"] = datetime.now().isoformat()
            restored_goal_plan["_transient_planning_action"] = "rollback_near_term_edit"
            restored_goal_plan["_transient_restore_checkpoint_id"] = rollback_checkpoint_id
            return restored_goal_plan

        if soften_clicked and safer_draft is not None:
            st.session_state[f"near_term_strategy_{key_prefix}"] = strategy_labels[safer_draft["post_edit_strategy"]]
            for row in safer_draft["draft_rows"]:
                row_index = int(row["index"])
                st.session_state[f"near_term_role_{key_prefix}_{row_index}"] = role_labels[row["session_role"]]
                st.session_state[f"near_term_sport_{key_prefix}_{row_index}"] = sport_labels[row["sport"]]
                st.session_state[f"near_term_tss_{key_prefix}_{row_index}"] = int(round(float(row["total_tss"] or 0.0)))
            st.rerun()

        if apply_clicked:
            updated_goal_plan = apply_near_term_day_edits(
                goal_plan,
                draft_rows,
                horizon_days=horizon_days,
                post_edit_strategy=selected_post_edit_strategy,
            )
            if seed_source_label:
                updated_goal_plan["_transient_planning_action"] = "override_execution_microcycle"
                updated_goal_plan["_transient_near_term_edit_origin"] = {
                    "origin_kind": str(draft_seed.get("origin_kind") or "execution_microcycle_override"),
                    "origin_checkpoint_id": draft_seed.get("origin_checkpoint_id"),
                    "origin_checkpoint_source": draft_seed.get("origin_checkpoint_source"),
                    "origin_plan_adjustment_label": draft_seed.get("origin_plan_adjustment_label"),
                    "origin_weekly_review_headline": draft_seed.get("origin_weekly_review_headline"),
                    "origin_microcycle_headline": draft_seed.get("origin_microcycle_headline") or seed_source_label,
                }
            return updated_goal_plan

    return None


def _render_planning_version_history(
    goal_plan: Dict[str, Any],
    latest_checkpoint: Dict[str, Any] | None,
    checkpoint_history: List[Dict[str, Any]] | None,
) -> Dict[str, Any] | None:
    """Render recent saved plan versions with compare + restore actions."""
    from models.planning_checkpoints import (
        restore_goal_plan_from_checkpoint,
        summarize_planning_checkpoint,
    )

    current_summary = summarize_planning_checkpoint(latest_checkpoint)
    if current_summary is None:
        return None

    latest_checkpoint_id = current_summary.get("checkpoint_id")
    history_records = [
        record
        for record in (checkpoint_history or [])
        if isinstance(record, dict) and record.get("id") != latest_checkpoint_id
    ][:4]
    if not history_records:
        return None

    st.markdown("### 🗂️ История версий плана")
    st.caption("Сравните текущую версию с недавними checkpoint и при необходимости восстановите любую из них.")

    current_provenance = current_summary.get("provenance") or {}
    with st.container(border=True):
        st.markdown(
            f"**Сейчас активна:** checkpoint #{current_summary['checkpoint_id']} · "
            f"{current_provenance.get('label', 'Текущая версия')}"
        )
        if current_summary["created_at_label"]:
            st.caption(f"Сохранён: {current_summary['created_at_label']}")
        if current_provenance.get("detail"):
            st.caption(current_provenance["detail"])
        st.write(
            f"**Checkpoint:** {current_summary['plan_adjustment_label']} · "
            f"Пик {current_summary['peak_tss']} TSS · Сумма {current_summary['total_tss']} TSS"
        )
        if current_summary.get("execution_reconciliation"):
            execution_reconciliation = current_summary["execution_reconciliation"]
            st.caption(
                f"Факт окна: {execution_reconciliation['actual_total_tss']} из "
                f"{execution_reconciliation['planned_total_tss']} TSS · "
                f"{execution_reconciliation['changed_day_count']} дн. изменено"
            )
        if current_summary.get("execution_weekly_review"):
            execution_weekly_review = current_summary["execution_weekly_review"]
            st.caption(
                f"Weekly review: {execution_weekly_review['review_badge']} · "
                f"{execution_weekly_review['headline']} · "
                f"{execution_weekly_review['selected_response_label']}"
            )
        if current_summary.get("execution_corrective_microcycle"):
            corrective_microcycle = current_summary["execution_corrective_microcycle"]
            st.caption(f"Microcycle: {corrective_microcycle['headline']}")
            st.caption(corrective_microcycle["today_action"])
        if current_summary.get("execution_adaptation_pressure"):
            adaptation_pressure = current_summary["execution_adaptation_pressure"]
            st.caption(
                f"Execution drift pressure: {adaptation_pressure['compact_label']}"
            )
            st.caption(adaptation_pressure["follow_up_window_description"])
        if current_summary.get("near_term_edit") and current_summary["near_term_edit"].get("origin_description"):
            st.caption(current_summary["near_term_edit"]["origin_description"])

    for record in history_records:
        summary = summarize_planning_checkpoint(record)
        restored_goal_plan = restore_goal_plan_from_checkpoint(record)
        if summary is None or not isinstance(restored_goal_plan, dict) or not restored_goal_plan.get("daily_plan"):
            continue

        preview = _build_goal_plan_transition_preview(goal_plan, restored_goal_plan)
        provenance = summary.get("provenance") or {}
        with st.container(border=True):
            st.markdown(
                f"**Checkpoint #{summary['checkpoint_id']} · {provenance.get('label', 'Сохранённая версия')}**"
            )
            if summary["created_at_label"]:
                st.caption(f"Сохранён: {summary['created_at_label']}")
            if provenance.get("detail"):
                st.caption(provenance["detail"])
            st.write(
                f"**Checkpoint:** {summary['plan_adjustment_label']} · "
                f"Пик {summary['peak_tss']} TSS · Сумма {summary['total_tss']} TSS"
            )
            if summary.get("execution_reconciliation"):
                execution_reconciliation = summary["execution_reconciliation"]
                st.caption(
                    f"Факт окна: {execution_reconciliation['actual_total_tss']} из "
                    f"{execution_reconciliation['planned_total_tss']} TSS · "
                    f"{execution_reconciliation['changed_day_count']} дн. изменено"
                )
            if summary.get("execution_weekly_review"):
                execution_weekly_review = summary["execution_weekly_review"]
                st.caption(
                    f"Weekly review: {execution_weekly_review['review_badge']} · "
                    f"{execution_weekly_review['headline']} · "
                    f"{execution_weekly_review['selected_response_label']}"
                )
            if summary.get("execution_corrective_microcycle"):
                corrective_microcycle = summary["execution_corrective_microcycle"]
                st.caption(f"Microcycle: {corrective_microcycle['headline']}")
                st.caption(corrective_microcycle["today_action"])
            if summary.get("execution_adaptation_pressure"):
                adaptation_pressure = summary["execution_adaptation_pressure"]
                st.caption(
                    f"Execution drift pressure: {adaptation_pressure['compact_label']}"
                )
                st.caption(adaptation_pressure["follow_up_window_description"])
            if summary.get("near_term_edit"):
                st.caption(f"Ручная правка: {summary['near_term_edit']['compact_label']}")
                if summary["near_term_edit"].get("origin_description"):
                    st.caption(summary["near_term_edit"]["origin_description"])
            if preview["weekly_rows"]:
                st.dataframe(
                    pd.DataFrame(preview["weekly_rows"]),
                    width="stretch",
                    hide_index=True,
                )
            else:
                st.caption("По недельной структуре эта версия совпадает с текущей.")
            if st.button(
                "↩️ Восстановить эту версию",
                key=f"restore_planning_checkpoint_{summary['checkpoint_id']}",
                width="stretch",
            ):
                restored_goal_plan = dict(restored_goal_plan)
                restored_goal_plan["plan_revision"] = datetime.now().isoformat()
                restored_goal_plan["_transient_planning_action"] = "restore_checkpoint_version"
                restored_goal_plan["_transient_restore_checkpoint_id"] = summary["checkpoint_id"]
                return restored_goal_plan

    return None


def _render_plan_explainability(goal_plan: Dict[str, Any]) -> pd.DataFrame:
    explain = _build_plan_explainability(goal_plan)

    st.markdown("### 🧠 Почему план такой")
    with st.container(border=True):
        st.markdown(f"**{explain['headline']}**")
        for note in explain["summary_notes"]:
            st.write(f"• {note}")

    metric_cols = st.columns(4)
    with metric_cols[0]:
        st.metric("Пик TSS", explain["peak_after"], delta=f"{explain['peak_delta']:+d} к базе")
    with metric_cols[1]:
        st.metric("Сумма TSS", explain["total_after"], delta=f"{explain['total_delta']:+d} к базе")
    with metric_cols[2]:
        st.metric("Недель с коррекцией", explain["changed_weeks"])
    with metric_cols[3]:
        st.metric("Стратегия", explain["catch_up_label"])

    scenario_col, planner_col = st.columns(2)
    with scenario_col:
        with st.container(border=True):
            st.markdown("#### Сценарий")
            st.write(f"• Доступно часов: {explain['available_hours']:.1f}")
            st.write(
                f"• Дни: {explain['availability_days']} "
                f"({explain['available_day_count']} из {explain['recommended_days']})"
            )
            if explain["interruption_weeks"] > 0 and explain["interruption_label"] != "Нет":
                st.write(
                    f"• Ограничение: {explain['interruption_label']} "
                    f"на {explain['interruption_weeks']} нед."
                )
            else:
                st.write("• Ограничение: нет")
            if explain["plan_adjustment_label"] != "Нет":
                weeks_suffix = (
                    f" на {explain['plan_adjustment_weeks']} нед."
                    if explain["plan_adjustment_weeks"] > 0
                    else ""
                )
                st.write(f"• Checkpoint: {explain['plan_adjustment_label']}{weeks_suffix}")
            else:
                st.write("• Checkpoint: без локальной перепланировки")
    with planner_col:
        with st.container(border=True):
            st.markdown("#### Решение Планировщика")
            st.write(f"• Мягкий потолок: {explain['capacity_tss']} TSS/нед")
            if explain["recovered_tss"] > 0:
                st.write(f"• Возвращено нагрузки: {explain['recovered_tss']} TSS")
            else:
                st.write("• Возврат нагрузки: не применялся")
            if explain["plan_adjustment_recovered_tss"] > 0:
                st.write(f"• Локально возвращено: {explain['plan_adjustment_recovered_tss']} TSS")
            elif explain["plan_adjustment_loss_tss"] > 0:
                st.write("• Локальный возврат: не применялся")
            if explain["execution_corrective_microcycle"] is not None:
                st.write(f"• Corrective microcycle: {explain['execution_corrective_microcycle']['headline']}")
                st.write(f"• Сегодня: {explain['execution_corrective_microcycle']['today_action']}")
                st.write(f"• Guardrail: {explain['execution_corrective_microcycle']['guardrail']}")
            if explain["execution_adaptation_pressure"] is not None:
                st.write(
                    f"• Execution drift pressure: {explain['execution_adaptation_pressure']['compact_label']}"
                )
                st.write(
                    f"• После окна: {explain['execution_adaptation_pressure']['follow_up_window_description']}"
                )
            if explain["near_term_edit"] is not None:
                st.write(f"• Ручная правка: {explain['near_term_edit']['compact_label']}")
                if explain["near_term_edit"].get("origin_description"):
                    st.write(f"• Источник override: {explain['near_term_edit']['origin_description']}")
                st.write(f"• После окна: {explain['near_term_edit']['follow_up_description']}")
                st.write(f"• Оценка правки: {explain['near_term_edit']['risk_badge']}")
                st.write(f"• Guardrail: {explain['near_term_edit']['risk_guardrail']}")
            st.write(f"• Пик базового плана: {explain['peak_before']} → {explain['peak_after']}")

    comparison_df = pd.DataFrame(explain["comparison_rows"])
    st.markdown("### ↔️ До / После По Неделям")
    st.dataframe(comparison_df, width="stretch", hide_index=True)
    return comparison_df


def render_planning_page(state: "StateManager") -> None:
    """Render the training planning page."""
    from models.banister import BanisterModel
    from services import intervals_icu
    from services.data_cache import load_activities
    from utils.modern_ui import ModernUI
    from utils.visualizations import Visualizations

    activities_df = load_activities(90)

    if activities_df.empty:
        st.warning("📭 Нет данных для анализа. Синхронизируйте данные с Garmin Connect.")
        return

    banister = BanisterModel()

    tss_data = []
    dates = []

    for _, row in activities_df.iterrows():
        tss_val = row["tss"] if "tss" in row and pd.notna(row["tss"]) else 0
        if pd.isna(tss_val) or tss_val is None:
            tss_val = 0
        tss_data.append(float(tss_val))
        dates.append(row["date"])

    current_metrics = banister.get_current_metrics(tss_data, dates)
    recommendation = banister.get_training_recommendation(current_metrics)
    form_color = {
        "Отличная форма": "🟢",
        "Хорошая форма": "🟡",
        "Усталость": "🟠",
        "Переутомление": "🔴",
        "Недостаточно данных": "⚫",
    }
    form_status = current_metrics["form"] if "form" in current_metrics else "Недостаточно данных"
    ModernUI.render_page_hero(
        "Планирование",
        "Соберите план, сверяйте неделю с фактом Garmin и открывайте коррекцию только когда план реально разошёлся с выполнением.",
        eyebrow="Planning cockpit",
        meta=f"CTL {current_metrics['ctl']} · ATL {current_metrics['atl']} · TSB {current_metrics['tsb']} · {form_status}",
    )
    has_goal_plan = bool((getattr(state, "goal_plan", None) or {}).get("daily_plan"))
    workspace_mode_key = "planning_workspace_mode"
    normalized_workspace_mode = _normalize_planning_workspace_mode(
        st.session_state.get(workspace_mode_key),
        has_goal_plan=has_goal_plan,
    )
    if st.session_state.get(workspace_mode_key) != normalized_workspace_mode:
        st.session_state[workspace_mode_key] = normalized_workspace_mode
    workspace_mode = st.radio(
        "Режим страницы",
        options=list(PLANNING_WORKSPACE_MODES),
        key=workspace_mode_key,
        horizontal=True,
    )
    workspace_mode = _normalize_planning_workspace_mode(
        workspace_mode,
        has_goal_plan=has_goal_plan,
    )

    if workspace_mode == "Собрать план":
        ModernUI.render_text_card(
            "Сборка плана",
            "Сначала задайте цель, затем реальные ограничения недели и только после этого собирайте план. Корректировка выполнения и экспорт остаются в отдельных режимах.",
            eyebrow="Guided setup",
            tone="info",
        )
        ModernUI.render_section_title("Текущее состояние", "Стартовая нагрузка для расчёта ближайшего плана.")
        col1, col2 = st.columns(2)
        col3, col4 = st.columns(2)

        with col1:
            ModernUI.render_stat_card("CTL", current_metrics["ctl"], "фитнес", "neutral")
        with col2:
            ModernUI.render_stat_card("ATL", current_metrics["atl"], "усталость", "warning")
        with col3:
            tsb_tone = tsb_zone(float(current_metrics["tsb"]))["tone"]
            ModernUI.render_stat_card("TSB", current_metrics["tsb"], "форма", tsb_tone)
        with col4:
            ModernUI.render_stat_card("Состояние", form_status, "Banister", tsb_tone)

        with st.expander("📊 Контекст нагрузки, рекомендации и быстрый прогноз", expanded=False):
            dates_full, ctl_values, atl_values, tsb_values = banister.calculate_ctl_atl_tsb(tss_data, dates)
            if dates_full and ctl_values:
                fig_banister = Visualizations.create_banister_chart(dates_full, ctl_values, atl_values, tsb_values)
                apply_plotly_theme(fig_banister, dark_mode=state.dark_mode)
                st.plotly_chart(fig_banister, width="stretch")

            intensity_colors = {
                "Высокая": "🔴",
                "Умеренная": "🟡",
                "Низкая": "🟢",
                "Очень низкая/Отдых": "🔵",
            }

            col1, col2 = st.columns([2, 1])

            with col1:
                st.markdown(
                    f"""
                **{recommendation['recommendation']}**

                {recommendation['description']}

                **Рекомендуемый диапазон TSS:** {recommendation['suggested_tss']}
                """
                )

            with col2:
                st.markdown(
                    f"""
                **Интенсивность:** {intensity_colors.get(recommendation['intensity'], '⚫')} {recommendation['intensity']}
                """
                )

            st.markdown("#### 🎲 Симулятор планирования")

            col1, col2 = st.columns(2)
            simulator_default_tss = _align_slider_value(
                int((current_metrics["ctl"] if "ctl" in current_metrics else 50) * 7),
                min_value=0,
                max_value=1000,
                step=50,
            )

            with col1:
                planned_weekly_tss = st.slider(
                    "Планируемый недельный TSS:",
                    min_value=0,
                    max_value=1000,
                    value=simulator_default_tss,
                    step=50,
                    help="Планируемая тренировочная нагрузка на неделю",
                )

            with col2:
                simulation_weeks = st.slider(
                    "Период симуляции (недели):",
                    min_value=1,
                    max_value=12,
                    value=4,
                    step=1,
                )

            if st.button("🚀 Показать прогноз"):
                future_dates, future_ctl, future_atl, future_tsb = banister.simulate_training_load(
                    current_metrics, planned_weekly_tss, simulation_weeks
                )

                if future_dates:
                    fig_future = Visualizations.create_banister_chart(
                        future_dates, future_ctl, future_atl, future_tsb
                    )
                    fig_future.update_layout(title="Прогноз при планируемой нагрузке")
                    apply_plotly_theme(fig_future, dark_mode=state.dark_mode)
                    st.plotly_chart(fig_future, width="stretch")

                    final_tsb = future_tsb[-1]
                    forecast_message = _TSB_TONE_TO_FORECAST_MESSAGE[tsb_zone(final_tsb)["tone"]]

                    st.info(f"**Прогноз через {simulation_weeks} недель:** TSB = {final_tsb:.1f} - {forecast_message}")
    elif not has_goal_plan:
        st.info("Сначала соберите план в режиме «Собрать план». После этого откроются режимы корректировки и экспорта.")

    if workspace_mode == "Собрать план":
        ModernUI.render_section_title(
            "Цель и дата старта",
            "Выберите тип события и дату. План стартует со следующей полноценной недели, если текущая уже почти закрыта.",
        )

        from models.training_planner import (
            WEEKDAY_LABELS_RU,
            apply_planning_constraints,
            compute_phase_schedule,
            create_weekly_tss_plan,
            estimated_tss_per_hour,
            expand_weekly_to_daily_triathlon,
            flatten_daily_total,
            goal_target_weekly_tss,
            summarize_availability,
            suggest_target_weekly_tss,
            weeks_until,
        )

        planning_reference_date = datetime.now().date()
        planning_start_week = _resolve_planning_start_week(planning_reference_date)

        colg1, colg2, colg3 = st.columns(3)
        with colg1:
            goal_type = st.selectbox(
                "Тип цели:",
                ["Триатлон", "Бег", "Вело"],
                index=0,
            )
            if goal_type == "Триатлон":
                distance_options = ["Спринт", "Олимпийка", "Half (70.3)", "Ironman"]
                default_index = 1
            elif goal_type == "Бег":
                distance_options = ["5 км", "10 км", "Полумарафон", "Марафон", "Ультра"]
                default_index = 2
            else:
                distance_options = ["40 км TT", "100 км", "100 миль", "200 км (бревет)", "Этапная гонка"]
                default_index = 1
            distance = st.selectbox("Дистанция:", distance_options, index=default_index)
        with colg2:
            goal_date = st.date_input(
                "Дата старта:",
                value=planning_reference_date + timedelta(weeks=8),
            )
            weeks_to_race = weeks_until(goal_date, from_date=planning_start_week)
            start_caption = f"Старт плана: {planning_start_week.strftime('%d.%m.%Y')} · до старта: ~{weeks_to_race} нед."
            if planning_start_week > planning_reference_date:
                start_caption += " Текущая неделя почти завершена, поэтому план начинается со следующего понедельника."
            st.caption(start_caption)
        with colg3:
            start_weekly_tss_guess = int(current_metrics.get("ctl", 50) * 7)
            auto = suggest_target_weekly_tss(goal_type, distance, activities_df)
            ModernUI.render_text_card(
                "Автонастройка нагрузки",
                f"Последняя неделя {auto['last_week']} TSS · среднее 4н {auto['avg_4']} · лучшая 8н {auto['best_8']}.",
                eyebrow="History-based",
                tone="neutral",
            )

        t_min, t_max = goal_target_weekly_tss(goal_type, distance)
        default_hours = max(
            3.0,
            min(
                20.0,
                round((float(auto["suggested"] or int((t_min + t_max) / 2)) / estimated_tss_per_hour(goal_type)) * 2) / 2,
            ),
        )

        ModernUI.render_section_title(
            "Сценарий и ограничения",
            "Доступность задаёт потолок нагрузки. Это не цель заполнить все часы, а ограничитель для безопасной сборки.",
        )
        cola1, cola2, cola3 = st.columns([1, 1.3, 1])
        with cola1:
            available_hours = st.slider(
                "Доступно часов в неделю:",
                min_value=3.0,
                max_value=20.0,
                value=float(default_hours),
                step=0.5,
                help="Используется как мягкий потолок weekly TSS под ваш реальный календарь.",
            )
        with cola2:
            available_day_labels = st.multiselect(
                "Доступные дни для тренировок:",
                options=WEEKDAY_LABELS_RU,
                default=WEEKDAY_LABELS_RU,
                help="Нагрузка будет перераспределена только на выбранные дни.",
            )
        with cola3:
            interruption_label = st.selectbox(
                "Ближайшее ограничение:",
                ["Нет", "Ограниченная доступность", "Отпуск", "Болезнь", "Травма"],
                index=0,
            )

        interruption_key_map = {
            "Нет": "none",
            "Ограниченная доступность": "limited",
            "Отпуск": "holiday",
            "Болезнь": "illness",
            "Травма": "injury",
        }
        plan_adjustment_key_map = {
            "Нет": "none",
            "Выполнено по плану": "completed",
            "Пропущены сессии": "skipped",
            "Нагрузка урезана": "reduced",
            "Неделя ограничена": "unavailable",
        }
        selected_day_indices = [
            WEEKDAY_LABELS_RU.index(label)
            for label in available_day_labels
            if label in WEEKDAY_LABELS_RU
        ] or list(range(7))

        colb1, colb2 = st.columns([1, 1.5])
        with colb1:
            interruption_weeks = st.slider(
                "Сколько недель продлится:",
                min_value=0,
                max_value=min(4, weeks_to_race),
                value=1 if interruption_label != "Нет" and weeks_to_race > 0 else 0,
                step=1,
                disabled=interruption_label == "Нет",
            )
        with colb2:
            catch_up_label = st.radio(
                "После пропуска:",
                ["Беречь восстановление", "Наверстать аккуратно"],
                horizontal=True,
                help="«Беречь восстановление» не пытается автоматически вернуть весь пропущенный объём. «Наверстать аккуратно» возвращает только часть нагрузки и с ограничением по усталости.",
            )

        catch_up_strategy = "catch_up" if catch_up_label == "Наверстать аккуратно" else "protect_recovery"
        availability_preview = summarize_availability(goal_type, available_hours, selected_day_indices)
        availability_cap_tss = int(availability_preview["weekly_capacity_tss"])

        ModernUI.render_section_title(
            "Локальная перепланировка",
            "Если реальное выполнение уже пошло не по плану, отметьте это локально, без полной перестройки цикла.",
        )
        adjustment_col1, adjustment_col2, adjustment_col3 = st.columns([1.3, 1, 1])
        with adjustment_col1:
            plan_adjustment_label = st.selectbox(
                "Что произошло в реальном выполнении:",
                ["Нет", "Выполнено по плану", "Пропущены сессии", "Нагрузка урезана", "Неделя ограничена"],
                index=0,
                help="Этот checkpoint меняет только ближайший горизонт, а не перестраивает весь цикл вслепую.",
            )

        plan_adjustment_status = plan_adjustment_key_map.get(plan_adjustment_label, "none")
        max_adjustment_weeks = min(2, max(1, weeks_to_race))
        with adjustment_col2:
            plan_adjustment_weeks = st.slider(
                "Горизонт пересчёта:",
                min_value=1,
                max_value=max_adjustment_weeks,
                value=1,
                step=1,
                disabled=plan_adjustment_status in {"none", "completed"},
                help="План меняет только ближайшие 7-14 дней и короткое окно safe catch-up после них.",
            )

        plan_adjustment_missed_sessions = 0
        plan_adjustment_reduced_share = 0.70
        with adjustment_col3:
            if plan_adjustment_status == "skipped":
                max_missed_sessions = max(1, min(4, int(availability_preview["available_day_count"])))
                plan_adjustment_missed_sessions = st.slider(
                    "Сколько сессий выпало:",
                    min_value=1,
                    max_value=max_missed_sessions,
                    value=min(2, max_missed_sessions),
                    step=1,
                )
            elif plan_adjustment_status == "reduced":
                reduced_percent = st.slider(
                    "Сколько % нагрузки реально осталось:",
                    min_value=35,
                    max_value=95,
                    value=70,
                    step=5,
                )
                plan_adjustment_reduced_share = reduced_percent / 100.0
            elif plan_adjustment_status == "unavailable":
                st.caption("План временно упростит 1-2 недели и вернёт нагрузку только в коротком безопасном окне.")
            elif plan_adjustment_status == "completed":
                st.caption("Checkpoint фиксирует, что неделя закрыта по плану. Дополнительная коррекция не нужна.")
            else:
                st.caption("Если реальная неделя пошла не по плану, отметьте это здесь — локально, без полной перестройки цикла.")

        plan_adjustment_payload = {
            "status": plan_adjustment_status,
            "weeks": 0 if plan_adjustment_status == "none" else plan_adjustment_weeks,
            "missed_sessions": plan_adjustment_missed_sessions,
            "reduced_load_share": plan_adjustment_reduced_share,
        }

        target_control = _resolve_target_weekly_tss_control(
            auto_suggested=auto["suggested"],
            t_min=t_min,
            t_max=t_max,
            availability_cap_tss=availability_cap_tss,
        )

        ModernUI.render_section_title("Сводка перед сборкой", "Проверьте ограничения до генерации плана.")
        preview_cols = st.columns(5)
        with preview_cols[0]:
            ModernUI.render_stat_card("Часы / нед", availability_preview["available_hours"], "доступно", "neutral")
        with preview_cols[1]:
            ModernUI.render_stat_card("Дней", availability_preview["available_day_count"], "в календаре", "success")
        with preview_cols[2]:
            interruption_tone = "warning" if interruption_label != "Нет" else "success"
            ModernUI.render_stat_card("Ограничение", interruption_label, "ближайшее", interruption_tone)
        with preview_cols[3]:
            checkpoint_tone = "warning" if plan_adjustment_status not in {"none", "completed"} else "neutral"
            ModernUI.render_stat_card("Checkpoint", plan_adjustment_label, "реальность недели", checkpoint_tone)
        with preview_cols[4]:
            ModernUI.render_stat_card("Реакция", _strategy_label(catch_up_strategy), "после сбоя", "info")
        availability_body = (
            f"Доступность сейчас около {availability_preview['available_hours']} ч/нед, "
            f"{availability_preview['available_day_count']} дн. из рекомендованных {availability_preview['recommended_days']}. "
            f"Мягкий потолок: примерно {availability_cap_tss} TSS/нед."
        )
        if plan_adjustment_status in {"skipped", "reduced", "unavailable"}:
            availability_body += (
                f" Локальная перепланировка активна: {plan_adjustment_label.lower()} на "
                f"{plan_adjustment_weeks} нед.; изменится только ближайший горизонт и короткое окно возврата нагрузки."
            )
        ModernUI.render_text_card(
            "Что это значит для плана",
            availability_body,
            eyebrow="Planning guardrail",
            tone=checkpoint_tone if plan_adjustment_status not in {"none", "completed"} else "success",
        )
        if availability_cap_tss < int(auto["suggested"] or 0):
            st.warning(
                f"Текущая доступность ограничивает план примерно до {availability_cap_tss} TSS/нед. "
                "Пик выше этого значения будет автоматически урезан."
            )

        if target_control["is_fixed"]:
            target_weekly_tss = int(target_control["value"])
            ModernUI.render_stat_card("Целевой недельный TSS к пику", target_weekly_tss, "зафиксировано", "warning")
            if target_control["reason"] == "availability_cap":
                st.caption(
                    "Под текущую доступность реалистичный пик уже зафиксирован. "
                    "Он ниже типового диапазона для этой цели, поэтому план будет строиться от достижимого потолка."
                )
            else:
                st.caption("Для этой цели и текущей доступности доступен один реалистичный пик нагрузки.")
        else:
            target_slider_step = _resolve_target_weekly_tss_step(
                int(target_control["slider_min"]),
                int(target_control["slider_max"]),
            )
            target_weekly_tss = st.slider(
                "Целевой недельный TSS к пику:",
                min_value=int(target_control["slider_min"]),
                max_value=int(target_control["slider_max"]),
                value=int(target_control["value"]),
                step=target_slider_step,
                help="Ориентир под дистанцию и доступность; фактический план дальше дополнительно учитывает ограничения и стратегию возврата нагрузки.",
            )

        with st.expander("⚙️ Продвинутые настройки распределения", expanded=False):
            st.caption("Обычно этот блок не нужен. Используйте его, только если хотите вручную управлять миксом дисциплин и днями внутри недели.")
            phases_all = ["Base", "Build", "Peak", "Taper"]
            if "planner_mix" not in state:
                state.planner_mix = {}
            if "planner_weights" not in state:
                state.planner_weights = {}

            prev_goal = state.planner_goal_type
            if prev_goal != goal_type:
                state.planner_goal_type = goal_type
                state.planner_mix = {}
                state.planner_weights = {}
                for phase in phases_all:
                    for key in (f"mix_bike_{phase}", f"mix_run_{phase}", f"mix_swim_{phase}"):
                        state.pop(key, None)
                    for i in range(7):
                        for key in (f"w_run_{phase}_{i}", f"w_bike_{phase}_{i}", f"w_swim_{phase}_{i}"):
                            state.pop(key, None)

            tabs = st.tabs(phases_all)
            from models.training_planner import daily_weights_for_phase, triathlon_weekly_mix

            for phase, tab in zip(phases_all, tabs):
                with tab:
                    st.caption("Проценты TSS по видам спорта (нормализуются автоматически)")
                    if goal_type == "Бег":
                        default_mix = {"run": 1.0, "bike": 0.0, "swim": 0.0}
                    elif goal_type == "Вело":
                        default_mix = {"run": 0.0, "bike": 1.0, "swim": 0.0}
                    else:
                        default_mix = triathlon_weekly_mix(distance, phase)
                    stored_mix = state.planner_mix.get(phase, default_mix)
                    bike = st.slider(
                        f"{phase} • Bike %",
                        0,
                        100,
                        int(round(stored_mix.get("bike", default_mix["bike"]) * 100)),
                        key=f"mix_bike_{phase}",
                    )
                    run = st.slider(
                        f"{phase} • Run %",
                        0,
                        100,
                        int(round(stored_mix.get("run", default_mix["run"]) * 100)),
                        key=f"mix_run_{phase}",
                    )
                    swim = st.slider(
                        f"{phase} • Swim %",
                        0,
                        100,
                        int(round(stored_mix.get("swim", default_mix["swim"]) * 100)),
                        key=f"mix_swim_{phase}",
                    )
                    total = bike + run + swim
                    if total == 0:
                        mix_norm = default_mix
                    else:
                        mix_norm = {"bike": bike / total, "run": run / total, "swim": swim / total}
                    state.planner_mix[phase] = mix_norm
                    st.caption(f"Сумма: {bike + run + swim}% → будет нормализовано до 100%")

                    st.divider()
                    st.caption("Дневные веса (Пн..Вс) для каждого вида спорта. Значения нормализуются к 100% на неделю.")
                    default_w = daily_weights_for_phase(phase)
                    stored_w = state.planner_weights.get(phase, default_w)
                    days = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
                    cols_run = st.columns(7)
                    run_vals = []
                    for i, col in enumerate(cols_run):
                        with col:
                            val = col.number_input(
                                f"Run {days[i]}",
                                min_value=0.0,
                                max_value=1.0,
                                step=0.05,
                                value=float(stored_w.get("run", default_w["run"])[i]),
                                key=f"w_run_{phase}_{i}",
                            )
                            run_vals.append(val)
                    cols_bike = st.columns(7)
                    bike_vals = []
                    for i, col in enumerate(cols_bike):
                        with col:
                            val = col.number_input(
                                f"Bike {days[i]}",
                                min_value=0.0,
                                max_value=1.0,
                                step=0.05,
                                value=float(stored_w.get("bike", default_w["bike"])[i]),
                                key=f"w_bike_{phase}_{i}",
                            )
                            bike_vals.append(val)
                    cols_swim = st.columns(7)
                    swim_vals = []
                    for i, col in enumerate(cols_swim):
                        with col:
                            val = col.number_input(
                                f"Swim {days[i]}",
                                min_value=0.0,
                                max_value=1.0,
                                step=0.05,
                                value=float(stored_w.get("swim", default_w["swim"])[i]),
                                key=f"w_swim_{phase}_{i}",
                            )
                            swim_vals.append(val)
                    state.planner_weights[phase] = {"run": run_vals, "bike": bike_vals, "swim": swim_vals}

        if st.button("🧭 Построить план до старта"):
            from models.planning_checkpoints import build_planning_checkpoint, with_checkpoint_provenance
            from models.training_planner import build_daily_session_templates

            base_weekly_tss_plan = create_weekly_tss_plan(
                start_weekly_tss=start_weekly_tss_guess,
                weeks_total=weeks_to_race,
                target_weekly_tss=target_weekly_tss,
                deload_every=4,
                taper_weeks=2,
                max_ramp=0.10,
            )

            start_week = planning_start_week
            phases = compute_phase_schedule(weeks_to_race)
            mix_overrides = state.planner_mix or None
            if not mix_overrides:
                if goal_type == "Бег":
                    mix_overrides = {phase: {"run": 1.0, "bike": 0.0, "swim": 0.0} for phase in phases}
                elif goal_type == "Вело":
                    mix_overrides = {phase: {"run": 0.0, "bike": 1.0, "swim": 0.0} for phase in phases}
            weekly_tss_plan, constraint_details, constraint_summary = apply_planning_constraints(
                base_weekly_tss_plan,
                phases,
                goal_type,
                available_hours=available_hours,
                available_day_indices=selected_day_indices,
                interruption_type=interruption_key_map.get(interruption_label, "none"),
                interruption_weeks=interruption_weeks if interruption_label != "Нет" else 0,
                catch_up_strategy=catch_up_strategy,
                current_tsb=float(current_metrics.get("tsb", 0.0)) if current_metrics.get("tsb") is not None else None,
                current_ctl=float(current_metrics.get("ctl", 0.0)) if current_metrics.get("ctl") is not None else None,
                current_atl=float(current_metrics.get("atl", 0.0)) if current_metrics.get("atl") is not None else None,
                plan_adjustment=plan_adjustment_payload,
            )
            weights_overrides = state.planner_weights or None
            daily_plan, weekly_summary = expand_weekly_to_daily_triathlon(
                weekly_tss_plan,
                phases,
                distance,
                start_week,
                mix_overrides=mix_overrides,
                weights_overrides=weights_overrides,
                available_day_indices=selected_day_indices,
                goal_type=goal_type,
                load_state=str(constraint_summary.get("load_state", "balanced")),
            )
            daily_seq = flatten_daily_total(daily_plan)
            for week_row, detail in zip(weekly_summary, constraint_details):
                week_row["capacity_tss"] = detail.get("capacity_tss")
                week_row["adjustment_note"] = detail.get("adjustment_note", "—")
            session_templates = build_daily_session_templates(
                daily_plan,
                weekly_summary,
                goal_type=goal_type,
                distance=distance,
            )

            goal_plan_payload = with_checkpoint_provenance(
                _build_initial_goal_plan_payload(
                    event_date=goal_date,
                    goal_type=goal_type,
                    distance=distance,
                    weeks_to_race=weeks_to_race,
                    start_week=start_week,
                    weekly_tss_plan=weekly_tss_plan,
                    base_weekly_tss_plan=base_weekly_tss_plan,
                    phases=phases,
                    daily_plan=daily_plan,
                    session_templates=session_templates,
                    weekly_summary=weekly_summary,
                    constraint_summary=constraint_summary,
                    planner_mix=mix_overrides,
                    planner_weights=weights_overrides,
                    plan_revision=datetime.now().isoformat(),
                    near_term_edit_version=0,
                    near_term_edit_rollback_target_checkpoint_id=None,
                ),
                source="initial_plan",
            )
            state.goal_plan = goal_plan_payload
            state.last_execution_feedback_result = None
            saved_checkpoint = state.database.save_planning_checkpoint(
                build_planning_checkpoint(goal_plan_payload)
            )
            state.latest_planning_checkpoint = saved_checkpoint
            state.planning_checkpoint_history = state.database.get_recent_planning_checkpoints(limit=6)
            st.rerun()

    if state.goal_plan:
        goal_plan = state.goal_plan
        if workspace_mode == "Собрать план":
            _render_active_plan_workspace_summary(
                goal_plan,
                title="План готов",
                caption="Детальная корректировка выполнения и экспорты вынесены в отдельные режимы страницы.",
            )
            st.info(
                "Переключитесь в «Скорректировать выполнение», если неделя пошла не по плану, "
                "или в «Экспорт и детали», если хотите посмотреть explainability, таблицы и sync."
            )
            return

        if workspace_mode != "Экспорт и детали":
            from models.planning_checkpoints import (
                build_planning_checkpoint,
                get_near_term_edit_rollback_target_checkpoint_id,
                restore_goal_plan_from_checkpoint,
                summarize_execution_feedback_transition,
                with_checkpoint_provenance,
            )
            from ui.components.execution_feedback import render_execution_feedback_editor

            flash_message = st.session_state.pop("planning_near_term_flash", None)
            if flash_message:
                st.success(flash_message)
            _render_planning_v2_active_plan(
                state,
                goal_plan,
                activities_df,
                current_metrics,
            )
            _render_plan_fact_calendar(
                goal_plan,
                activities_df,
                key_prefix="planning_plan_fact_review",
                title="### План и факт",
                focus_state_key="planning_execution_feedback_focus_day",
                show_replan_signal=True,
            )

            editor_visible_key = "planning_v2_execution_editor_visible"
            if str(st.session_state.get("planning_execution_feedback_focus_day") or "").strip():
                st.session_state[editor_visible_key] = True

            execution_feedback_result = None
            if st.session_state.get(editor_visible_key):
                execution_feedback_result = render_execution_feedback_editor(
                    goal_plan,
                    key_prefix="planning_execution_feedback",
                    title="### Факт выполнения по дням",
                    allow_open_as_draft=True,
                    focus_state_key="planning_execution_feedback_focus_day",
                )
            else:
                st.info(
                    "Редактор факта скрыт, пока нет явной задачи. "
                    "Откройте его через блок «Коррекция» или выберите день в plan/fact."
                )
            if execution_feedback_result is not None:
                latest_checkpoint = getattr(state, "latest_planning_checkpoint", None)
                if execution_feedback_result.get("mode") == "open_near_term_draft":
                    projected_goal_plan = execution_feedback_result.get("projected_goal_plan")
                    corrective_microcycle = execution_feedback_result.get("execution_corrective_microcycle") or {}
                    draft_seed = None
                    if isinstance(projected_goal_plan, dict):
                        draft_seed = build_near_term_edit_seed_from_goal_plans(
                            goal_plan,
                            projected_goal_plan,
                            horizon_days=7,
                            post_edit_strategy=str(corrective_microcycle.get("selected_response_strategy") or "keep"),
                            source_label=str(corrective_microcycle.get("headline") or "Execution microcycle"),
                        )
                    if draft_seed is not None:
                        draft_seed["hint"] = (
                            "Это override-path для ближайших 7 дней: сначала проверьте diff, risk и follow-up strategy, "
                            "а уже потом сохраняйте manual override."
                        )
                        draft_seed["origin_kind"] = "execution_microcycle_override"
                        draft_seed["origin_checkpoint_id"] = (
                            (latest_checkpoint or {}).get("id") if isinstance(latest_checkpoint, dict) else None
                        )
                        draft_seed["origin_checkpoint_source"] = (
                            (latest_checkpoint or {}).get("checkpoint_source")
                            if isinstance(latest_checkpoint, dict)
                            else None
                        )
                        draft_seed["origin_plan_adjustment_label"] = str(
                            execution_feedback_result["plan_adjustment"].get("label") or ""
                        )
                        draft_seed["origin_weekly_review_headline"] = str(
                            (
                                execution_feedback_result["plan_adjustment"].get("execution_weekly_review") or {}
                            ).get("headline")
                            or ""
                        )
                        draft_seed["origin_microcycle_headline"] = str(
                            corrective_microcycle.get("headline") or ""
                        )
                        st.session_state["planning_near_term_prefill"] = draft_seed
                        st.session_state["planning_near_term_flash"] = (
                            "Execution microcycle открыт как черновик ручной правки. "
                            "Проверьте diff и risk перед сохранением override."
                        )
                        st.rerun()
                    st.warning("Не удалось открыть microcycle как черновик: в ближнем горизонте нет видимого diff.")
                    return
                updated_goal_plan = rebuild_goal_plan_with_adjustment(
                    goal_plan,
                    execution_feedback_result["plan_adjustment"],
                )
                updated_goal_plan = with_checkpoint_provenance(
                    updated_goal_plan,
                    source="execution_feedback",
                    parent_checkpoint_id=(latest_checkpoint or {}).get("id") if isinstance(latest_checkpoint, dict) else None,
                )
                state.goal_plan = updated_goal_plan
                saved_checkpoint = state.database.save_planning_checkpoint(
                    build_planning_checkpoint(updated_goal_plan)
                )
                state.latest_planning_checkpoint = saved_checkpoint
                state.planning_checkpoint_history = state.database.get_recent_planning_checkpoints(limit=6)
                state.last_execution_feedback_result = summarize_execution_feedback_transition(
                    latest_checkpoint,
                    saved_checkpoint,
                )
                execution_reconciliation = execution_feedback_result["plan_adjustment"].get("execution_reconciliation")
                execution_weekly_review = execution_feedback_result["plan_adjustment"].get("execution_weekly_review")
                execution_adaptation_pressure = execution_feedback_result.get("execution_adaptation_pressure")
                execution_corrective_microcycle = (
                    (
                        (
                            (updated_goal_plan.get("constraint_summary", {}) or {}).get("plan_adjustment", {})
                            or {}
                        ).get("execution_corrective_microcycle")
                    )
                )
                if (
                    isinstance(execution_reconciliation, dict)
                    and execution_reconciliation.get("changed_day_count", 0) > 0
                    and isinstance(execution_weekly_review, dict)
                    and isinstance(execution_corrective_microcycle, dict)
                ):
                    st.session_state["planning_near_term_flash"] = (
                        "Execution checkpoint сохранён: "
                        f"{execution_reconciliation['compact_label']} · "
                        f"{execution_weekly_review['headline']} · "
                        f"{execution_weekly_review['selected_response_label']} · "
                        f"{execution_corrective_microcycle['headline']}."
                    )
                    if isinstance(execution_adaptation_pressure, dict):
                        st.session_state["planning_near_term_flash"] += (
                            f" После окна: {execution_adaptation_pressure['follow_up_label']}."
                        )
                elif (
                    isinstance(execution_reconciliation, dict)
                    and execution_reconciliation.get("changed_day_count", 0) > 0
                    and isinstance(execution_weekly_review, dict)
                ):
                    st.session_state["planning_near_term_flash"] = (
                        "Execution checkpoint сохранён: "
                        f"{execution_reconciliation['compact_label']} · "
                        f"{execution_weekly_review['headline']} · "
                        f"{execution_weekly_review['selected_response_label']}."
                    )
                    if isinstance(execution_adaptation_pressure, dict):
                        st.session_state["planning_near_term_flash"] += (
                            f" После окна: {execution_adaptation_pressure['follow_up_label']}."
                        )
                elif isinstance(execution_reconciliation, dict) and execution_reconciliation.get("changed_day_count", 0) > 0:
                    st.session_state["planning_near_term_flash"] = (
                        "Execution checkpoint сохранён: "
                        f"{execution_reconciliation['compact_label']}."
                    )
                    if isinstance(execution_adaptation_pressure, dict):
                        st.session_state["planning_near_term_flash"] += (
                            f" После окна: {execution_adaptation_pressure['follow_up_label']}."
                        )
                elif execution_feedback_result.get("mode") == "confirm_garmin_window":
                    st.session_state["planning_near_term_flash"] = (
                        "Garmin-подтверждение сохранено: execution checkpoint зафиксировал окно как выполненное."
                    )
                else:
                    st.session_state["planning_near_term_flash"] = "Execution checkpoint сохранён."
                st.rerun()

            rollback_goal_plan = None
            latest_checkpoint = getattr(state, "latest_planning_checkpoint", None)
            rollback_target_checkpoint_id = get_near_term_edit_rollback_target_checkpoint_id(latest_checkpoint)
            if rollback_target_checkpoint_id is not None:
                rollback_checkpoint = state.database.get_planning_checkpoint(rollback_target_checkpoint_id)
                rollback_goal_plan = restore_goal_plan_from_checkpoint(rollback_checkpoint)
                if not isinstance(rollback_goal_plan, dict) or not rollback_goal_plan.get("daily_plan"):
                    rollback_goal_plan = None

            draft_seed = st.session_state.pop("planning_near_term_prefill", None)
            updated_goal_plan = _render_near_term_editor(
                goal_plan,
                rollback_goal_plan=rollback_goal_plan,
                rollback_checkpoint_id=rollback_target_checkpoint_id,
                draft_seed=draft_seed,
            )
            if updated_goal_plan is None:
                with st.expander("История и откат версий", expanded=False):
                    updated_goal_plan = _render_planning_version_history(
                        goal_plan,
                        latest_checkpoint,
                        getattr(state, "planning_checkpoint_history", []),
                    )
            if updated_goal_plan is not None:
                planning_action = str(updated_goal_plan.pop("_transient_planning_action", "") or "")
                restored_from_checkpoint_id = updated_goal_plan.pop("_transient_restore_checkpoint_id", None)
                near_term_edit_origin = updated_goal_plan.pop("_transient_near_term_edit_origin", None)
                if (
                    planning_action == "override_execution_microcycle"
                    and isinstance(updated_goal_plan.get("constraint_summary"), dict)
                    and isinstance((updated_goal_plan.get("constraint_summary") or {}).get("near_term_edit"), dict)
                    and isinstance(near_term_edit_origin, dict)
                ):
                    updated_goal_plan["constraint_summary"]["near_term_edit"].update(
                        {key: value for key, value in near_term_edit_origin.items() if value not in (None, "")}
                    )
                near_term_summary = summarize_near_term_edit(updated_goal_plan.get("constraint_summary", {}))
                latest_checkpoint_id = (latest_checkpoint or {}).get("id") if isinstance(latest_checkpoint, dict) else None
                if planning_action in {"rollback_near_term_edit", "restore_checkpoint_version"}:
                    updated_goal_plan = with_checkpoint_provenance(
                        updated_goal_plan,
                        source="restore_version",
                        parent_checkpoint_id=latest_checkpoint_id,
                        restored_from_checkpoint_id=restored_from_checkpoint_id,
                    )
                else:
                    updated_goal_plan = with_checkpoint_provenance(
                        updated_goal_plan,
                        source="manual_edit",
                        parent_checkpoint_id=latest_checkpoint_id,
                    )
                    if near_term_summary is not None and latest_checkpoint_id is not None:
                        updated_goal_plan["near_term_edit_rollback_target_checkpoint_id"] = latest_checkpoint_id
                    elif near_term_summary is None:
                        updated_goal_plan.pop("near_term_edit_rollback_target_checkpoint_id", None)

                state.goal_plan = updated_goal_plan
                state.last_execution_feedback_result = None
                saved_checkpoint = state.database.save_planning_checkpoint(
                    build_planning_checkpoint(updated_goal_plan)
                )
                state.latest_planning_checkpoint = saved_checkpoint
                state.planning_checkpoint_history = state.database.get_recent_planning_checkpoints(limit=6)
                if planning_action == "rollback_near_term_edit":
                    if near_term_summary is not None:
                        st.session_state["planning_near_term_flash"] = (
                            "Откат выполнен. Активная версия: "
                            f"{near_term_summary['compact_label']}."
                        )
                    else:
                        st.session_state["planning_near_term_flash"] = "Последняя ручная правка ближнего горизонта откатана."
                elif planning_action == "restore_checkpoint_version":
                    if restored_from_checkpoint_id is not None:
                        st.session_state["planning_near_term_flash"] = (
                            f"Версия checkpoint #{int(restored_from_checkpoint_id)} восстановлена."
                        )
                    else:
                        st.session_state["planning_near_term_flash"] = "Сохранённая версия плана восстановлена."
                elif planning_action == "override_execution_microcycle":
                    if near_term_summary is not None:
                        st.session_state["planning_near_term_flash"] = (
                            "Execution microcycle переопределён вручную: "
                            f"{near_term_summary['compact_label']}."
                        )
                        if near_term_summary.get("origin_microcycle_headline"):
                            st.session_state["planning_near_term_flash"] += (
                                f" База override: {near_term_summary['origin_microcycle_headline']}."
                            )
                        if near_term_summary["risk_level"] != "low":
                            st.session_state["planning_near_term_flash"] += (
                                f" Оценка: {near_term_summary['risk_badge']}."
                            )
                    else:
                        st.session_state["planning_near_term_flash"] = "Execution microcycle переопределён вручную."
                else:
                    if near_term_summary is not None:
                        st.session_state["planning_near_term_flash"] = (
                            "Ближний горизонт обновлён: "
                            f"{near_term_summary['compact_label']}."
                        )
                        if near_term_summary["risk_level"] != "low":
                            st.session_state["planning_near_term_flash"] += (
                                f" Оценка: {near_term_summary['risk_badge']}."
                            )
                    else:
                        st.session_state["planning_near_term_flash"] = "Ближний горизонт обновлён."
                st.rerun()
                return

            return

        flash_message = st.session_state.pop("planning_near_term_flash", None)
        if flash_message:
            st.success(flash_message)
        _render_active_plan_workspace_summary(
            goal_plan,
            title="Активный план для экспорта и деталей",
            caption="Здесь собраны explainability, недельные таблицы, внешние sync и файловые экспорты.",
        )
        daily_plan = goal_plan["daily_plan"]
        weekly_summary = goal_plan["weekly_summary"]
        start_week = goal_plan["start_week"]
        goal_type_cached = goal_plan.get("goal_type", "Триатлон")
        distance_cached = goal_plan.get("distance", "Олимпийка")
        session_templates = goal_plan.get("session_templates", [])

        from models.training_planner import flatten_daily_total

        future_dates, future_ctl, future_atl, future_tsb = banister.simulate_variable_load(
            current_metrics, flatten_daily_total(daily_plan), start_date=datetime.combine(start_week, datetime.min.time())
        )
        fig_future = Visualizations.create_banister_chart(
            future_dates, future_ctl, future_atl, future_tsb
        )
        fig_future.update_layout(title=f"Прогноз до старта ({goal_type_cached} • {distance_cached})")
        apply_plotly_theme(fig_future, dark_mode=state.dark_mode)
        st.plotly_chart(fig_future, width="stretch")

        comparison_df = _render_plan_explainability(goal_plan)
        daily_session_rows = _build_daily_session_rows(goal_plan)
        df_plan = pd.DataFrame(weekly_summary)
        df_plan["Неделя от"] = df_plan["week_start"].apply(lambda d: d.strftime("%d.%m"))
        plan_columns = ["Неделя от", "phase", "weekly_tss", "bike", "run", "swim"]
        if "capacity_tss" in df_plan.columns:
            plan_columns.append("capacity_tss")
        if "adjustment_note" in df_plan.columns:
            plan_columns.append("adjustment_note")
        if "structure_summary" in df_plan.columns:
            plan_columns.append("structure_summary")
        if "key_sessions" in df_plan.columns:
            plan_columns.append("key_sessions")
        if "recovery_days" in df_plan.columns:
            plan_columns.append("recovery_days")
        df_plan = df_plan[plan_columns]
        df_plan.rename(
            columns={
                "phase": "Фаза",
                "weekly_tss": "Weekly TSS",
                "bike": "Bike",
                "run": "Run",
                "swim": "Swim",
                "capacity_tss": "Потолок TSS",
                "adjustment_note": "Коррекция",
                "structure_summary": "Структура недели",
                "key_sessions": "Ключевые сессии",
                "recovery_days": "Восстановление",
            },
            inplace=True,
        )
        with st.expander("📋 Подробная Разбивка По Неделям И Дисциплинам", expanded=False):
            st.dataframe(df_plan, width="stretch", hide_index=True)

        df_daily = pd.DataFrame(daily_session_rows)
        with st.expander("🗓️ Структура Дней И Восстановления", expanded=False):
            st.dataframe(df_daily, width="stretch", hide_index=True)

        with st.expander("🗓️ План и факт по неделе", expanded=False):
            _render_plan_fact_calendar(
                goal_plan,
                activities_df,
                key_prefix="planning_plan_fact_export",
                title="#### Недельный overlay плана и факта",
                focus_state_key="planning_execution_feedback_focus_day",
            )

        near_term_export_summary = summarize_near_term_edit(goal_plan.get("constraint_summary", {}))
        if near_term_export_summary is not None:
            st.caption(
                "Экспорты и sync уже используют вручную обновлённый ближний горизонт: "
                f"{near_term_export_summary['compact_label']}."
            )

        export_cols = st.columns(3)
        with export_cols[0]:
            csv_weekly = comparison_df.to_csv(index=False).encode("utf-8")
            st.download_button(
                label="💾 Сравнение до/после (CSV)",
                data=csv_weekly,
                file_name="weekly_plan_comparison.csv",
                mime="text/csv",
            )
        with export_cols[1]:
            weekly_detail_csv = df_plan.to_csv(index=False).encode("utf-8")
            st.download_button(
                label="💾 Детали по неделям (CSV)",
                data=weekly_detail_csv,
                file_name="weekly_plan.csv",
                mime="text/csv",
            )

        with export_cols[2]:
            csv_daily = df_daily.to_csv(index=False).encode("utf-8")
            st.download_button(
                label="💾 Дневной план (CSV)",
                data=csv_daily,
                file_name="daily_plan.csv",
                mime="text/csv",
            )

        from models.training_planner import create_ics_from_daily

        ics_content = create_ics_from_daily(
            daily_plan,
            title_prefix=f"{goal_type_cached} {distance_cached}",
            session_templates=session_templates,
        )
        st.download_button(
            label="📅 Экспорт в календарь (ICS)",
            data=ics_content,
            file_name="training_plan.ics",
            mime="text/calendar",
        )

        total_days = len(daily_plan)
        total_weeks = max(1, (total_days + 6) // 7)

        st.markdown("### 📤 Intervals.icu")
        intervals_info = intervals_icu.connection_info()
        if intervals_info.get("configured"):
            st.caption(
                "Personal API key найден: "
                f"athlete_id={intervals_info.get('athlete_id', '0')} · {intervals_info.get('base_url', 'https://intervals.icu')}"
            )

            col_int_1, col_int_2, col_int_3 = st.columns([1.2, 1, 1])
            with col_int_1:
                if st.button("🔎 Проверить подключение", key="intervals_test_connection"):
                    try:
                        result = intervals_icu.test_connection()
                        calendar_count = result.get("calendar_count")
                        if calendar_count is None:
                            st.success("Intervals.icu ответил корректно.")
                        else:
                            st.success(f"Intervals.icu подключён. Найдено календарей: {calendar_count}.")
                    except intervals_icu.IntervalsICUError as exc:
                        st.error(str(exc))

            with col_int_2:
                intervals_day_number = st.number_input(
                    "День плана",
                    min_value=1,
                    max_value=total_days,
                    value=1,
                    key="intervals_day_number",
                )

            with col_int_3:
                intervals_week_number = st.number_input(
                    "Неделя плана",
                    min_value=1,
                    max_value=total_weeks,
                    value=1,
                    key="intervals_week_number",
                )

            col_int_4, col_int_5 = st.columns(2)

            with col_int_4:
                if st.button("📤 Отправить день в Intervals.icu", key="intervals_push_day"):
                    day_index = int(intervals_day_number) - 1
                    selected_day = [daily_plan[day_index]]
                    selected_templates = session_templates[day_index:day_index + 1]
                    events = intervals_icu.build_planned_events(
                        selected_day,
                        goal_type_cached,
                        distance_cached,
                        session_templates=selected_templates,
                    )
                    if not events:
                        st.warning("Выбранный день не содержит достаточной тренировочной нагрузки для отправки.")
                    else:
                        try:
                            created = intervals_icu.push_planned_events(events)
                            event_name = events[0].get("name", "planned workout")
                            created_count = len(created)
                            st.success(f"Отправлено {created_count} событие: {event_name}.")
                        except intervals_icu.IntervalsICUError as exc:
                            st.error(str(exc))

            with col_int_5:
                if st.button("📤 Отправить неделю в Intervals.icu", key="intervals_push_week"):
                    start_idx = (int(intervals_week_number) - 1) * 7
                    end_idx = min(start_idx + 7, total_days)
                    selected_days = daily_plan[start_idx:end_idx]
                    selected_templates = session_templates[start_idx:end_idx]
                    events = intervals_icu.build_planned_events(
                        selected_days,
                        goal_type_cached,
                        distance_cached,
                        session_templates=selected_templates,
                    )
                    if not events:
                        st.warning("В выбранной неделе нет дней с достаточной нагрузкой для отправки.")
                    else:
                        try:
                            created = intervals_icu.push_planned_events(events)
                            st.success(
                                f"Отправлено {len(created)} planned workouts в Intervals.icu "
                                f"за неделю {int(intervals_week_number)}."
                            )
                        except intervals_icu.IntervalsICUError as exc:
                            st.error(str(exc))
        else:
            st.info(
                "Чтобы отправлять planned workouts в Intervals.icu, укажите "
                "`INTERVALS_ICU_API_KEY` в `.env`. `INTERVALS_ICU_ATHLETE_ID=0` подходит для персонального аккаунта."
            )

        st.markdown("### 🧩 Экспорт тренировки (FIT-CSV / FIT / TCX)")
        day_idx = st.number_input("День недели (1=Пн … 7=Вс)", min_value=1, max_value=7, value=1, key="fit_day")
        if st.button("⬇️ Экспортировать выбранный день в FIT-CSV / FIT", key="export_fit_day"):
            from config.settings import Settings
            from models.fit_export import build_steps_for_sport, generate_fit_csv, try_convert_fit_verbose
            from models.tcx_activity_export import generate_tcx_activity
            from models.tcx_export import generate_tcx_workout

            day_index = day_idx - 1
            day = daily_plan[day_index]
            dt, total, parts = day
            session_template = session_templates[day_index] if day_index < len(session_templates) else {}
            sport = _infer_sport_for_export(parts, session_template)
            steps = build_steps_for_sport(
                total,
                sport,
                session_role=str(session_template.get("session_role", "easy")),
                phase=session_template.get("phase"),
            )
            workout_name = str(
                session_template.get("export_name")
                or f"{goal_type_cached} {distance_cached} — {dt.strftime('%Y-%m-%d')}"
            )
            csv_text = generate_fit_csv(workout_name, sport, steps, created=dt)
            csv_bytes = csv_text.encode("utf-8")

            colf1, colf2, colf3, colf4 = st.columns(4)
            with colf1:
                st.download_button(
                    label="💾 Скачать FIT-CSV",
                    data=csv_bytes,
                    file_name=f"workout_{dt.strftime('%Y%m%d')}.csv",
                    mime="text/csv",
                )
            with colf2:
                jar = Settings.FIT_SDK_JAR
                fit_bytes, out_s, err_s, rc = try_convert_fit_verbose(csv_bytes, "java", jar) if jar else (None, "", "FIT_SDK_JAR не задан", 127)
                if fit_bytes and rc == 0:
                    st.download_button(
                        label="💾 Скачать FIT",
                        data=fit_bytes,
                        file_name=f"workout_{dt.strftime('%Y%m%d')}.fit",
                        mime="application/octet-stream",
                    )
                else:
                    if rc != 0:
                        st.warning("FIT не собран. Логи FitCSVTool:")
                        if out_s:
                            st.code(out_s)
                        if err_s:
                            st.code(err_s)
                    else:
                        st.info("Чтобы собрать .FIT внутри приложения, укажите путь к FitCSVTool.jar в переменной окружения FIT_SDK_JAR.")
            with colf3:
                tcx_text = generate_tcx_workout(workout_name, sport, steps, created=dt)
                st.download_button(
                    label="💾 Скачать TCX",
                    data=tcx_text.encode("utf-8"),
                    file_name=f"workout_{dt.strftime('%Y%m%d')}.tcx",
                    mime="application/vnd.garmin.tcx+xml",
                )
            with colf4:
                tcx_act = generate_tcx_activity(workout_name, sport, steps, start_time=datetime.combine(dt.date(), datetime.min.time()))
                st.download_button(
                    label="💾 TCX Activity (импорт)",
                    data=tcx_act.encode("utf-8"),
                    file_name=f"activity_{dt.strftime('%Y%m%d')}.tcx",
                    mime="application/vnd.garmin.tcx+xml",
                    help="Используйте этот файл на странице Импорт данных в Garmin Connect",
                )

        with st.expander("📦 Экспорт всей недели (ZIP)", expanded=False):
            week_idx = st.number_input("Номер недели (1=первая)", min_value=1, max_value=total_weeks, value=1, key="fit_week_idx")
            if st.button("⬇️ Собрать ZIP с FIT-CSV/FIT/TCX", key="export_fit_week_zip"):
                import io
                import zipfile

                from config.settings import Settings
                from models.fit_export import build_steps_for_sport, generate_fit_csv, try_convert_fit_verbose
                from models.tcx_export import generate_tcx_workout

                jar = Settings.FIT_SDK_JAR

                start = (week_idx - 1) * 7
                end = min(start + 7, total_days)
                week_days = daily_plan[start:end]
                week_templates = session_templates[start:end]

                csv_zip = io.BytesIO()
                tcx_zip = io.BytesIO()
                with zipfile.ZipFile(csv_zip, "w", zipfile.ZIP_DEFLATED) as csv_archive, zipfile.ZipFile(
                    tcx_zip, "w", zipfile.ZIP_DEFLATED
                ) as tcx_archive:
                    for day_offset, (dt, total, parts) in enumerate(week_days):
                        session_template = week_templates[day_offset] if day_offset < len(week_templates) else {}
                        sport = _infer_sport_for_export(parts, session_template)
                        steps = build_steps_for_sport(
                            total,
                            sport,
                            session_role=str(session_template.get("session_role", "easy")),
                            phase=session_template.get("phase"),
                        )
                        workout_name = str(
                            session_template.get("export_name")
                            or f"{goal_type_cached} {distance_cached} — {dt.strftime('%Y-%m-%d')}"
                        )
                        csv_text = generate_fit_csv(workout_name, sport, steps, created=dt)
                        csv_archive.writestr(f"workout_{dt.strftime('%Y%m%d')}.csv", csv_text)
                        tcx_text = generate_tcx_workout(workout_name, sport, steps, created=dt)
                        tcx_archive.writestr(f"workout_{dt.strftime('%Y%m%d')}.tcx", tcx_text)
                st.download_button(
                    label="💾 Скачать все FIT-CSV (ZIP)",
                    data=csv_zip.getvalue(),
                    file_name=f"week_{week_idx:02d}_fitcsv.zip",
                    mime="application/zip",
                    key="dl_fitcsv_week_zip",
                )
                st.download_button(
                    label="💾 Скачать все TCX (ZIP)",
                    data=tcx_zip.getvalue(),
                    file_name=f"week_{week_idx:02d}_tcx.zip",
                    mime="application/zip",
                    key="dl_tcx_week_zip",
                )

                if jar:
                    fit_zip = io.BytesIO()
                    failed_days = 0
                    with zipfile.ZipFile(fit_zip, "w", zipfile.ZIP_DEFLATED) as fit_archive:
                        for day_offset, (dt, total, parts) in enumerate(week_days):
                            session_template = week_templates[day_offset] if day_offset < len(week_templates) else {}
                            sport = _infer_sport_for_export(parts, session_template)
                            steps = build_steps_for_sport(
                                total,
                                sport,
                                session_role=str(session_template.get("session_role", "easy")),
                                phase=session_template.get("phase"),
                            )
                            workout_name = str(
                                session_template.get("export_name")
                                or f"{goal_type_cached} {distance_cached} — {dt.strftime('%Y-%m-%d')}"
                            )
                            csv_text = generate_fit_csv(workout_name, sport, steps, created=dt)
                            fit_bytes, _, _, rc = try_convert_fit_verbose(csv_text.encode("utf-8"), "java", jar)
                            if fit_bytes and rc == 0:
                                fit_archive.writestr(f"workout_{dt.strftime('%Y%m%d')}.fit", fit_bytes)
                            else:
                                failed_days += 1
                    if fit_zip.getbuffer().nbytes > 0:
                        st.download_button(
                            label="💾 Скачать все FIT (ZIP)",
                            data=fit_zip.getvalue(),
                            file_name=f"week_{week_idx:02d}_fit.zip",
                            mime="application/zip",
                            key="dl_fit_week_zip",
                        )
                    if failed_days:
                        st.info(f"Не удалось собрать FIT для {failed_days} дн. Проверьте FIT_SDK_JAR/Java или структуру CSV.")

        if st.button("♻️ Сбросить план"):
            state.reset_planner_overrides()
            st.success("План сброшен")
            st.rerun()

    if workspace_mode == "Собрать план":
        with st.expander("📈 Дополнительная статистика", expanded=False):
            col1, col2 = st.columns(2)

            with col1:
                if not activities_df.empty and "tss" in activities_df.columns:
                    fig_tss_dist = Visualizations.create_tss_distribution_chart(activities_df)
                    apply_plotly_theme(fig_tss_dist, dark_mode=state.dark_mode)
                    st.plotly_chart(fig_tss_dist, width="stretch")

            with col2:
                if not activities_df.empty:
                    fig_weekly = Visualizations.create_weekly_tss_chart(activities_df)
                    apply_plotly_theme(fig_weekly, dark_mode=state.dark_mode)
                    st.plotly_chart(fig_weekly, width="stretch")
