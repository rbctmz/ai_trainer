"""Reusable execution-feedback and local-replanning helpers."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Mapping

from models.training_planner import (
    apply_planning_constraints,
    build_daily_session_templates,
    expand_weekly_to_daily_triathlon,
)

EXECUTION_DAY_OUTCOME_LABELS = {
    "as_planned": "По плану",
    "reduced": "Сделано легче",
    "missed": "Пропущено",
    "unavailable": "Недоступно",
}


def _coerce_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value if value is not None else default)
    except (TypeError, ValueError):
        return float(default)


def _coerce_int(value: Any, default: int = 0) -> int:
    try:
        return int(value if value is not None else default)
    except (TypeError, ValueError):
        return int(default)


def _round_int(value: float) -> int:
    return int(round(float(value or 0.0)))


def _plan_adjustment_label(status: str) -> str:
    mapping = {
        "completed": "Выполнено по плану",
        "skipped": "Пропущены сессии",
        "reduced": "Нагрузка урезана",
        "unavailable": "Неделя ограничена",
        "none": "Нет",
    }
    return mapping.get((status or "none").lower(), "Нет")


def build_execution_reconciliation_rows(
    goal_plan: Mapping[str, Any],
    *,
    weeks: int = 1,
) -> List[Dict[str, Any]]:
    """Build editable day-level execution rows for the near-term horizon."""
    daily_plan = list(goal_plan.get("daily_plan", []) or [])
    session_templates = list(goal_plan.get("session_templates", []) or [])
    horizon_days = min(len(daily_plan), max(1, int(weeks or 1)) * 7)
    rows: List[Dict[str, Any]] = []

    for index, daily_item in enumerate(daily_plan[:horizon_days]):
        if not isinstance(daily_item, (list, tuple)) or len(daily_item) < 3:
            continue
        dt, total_tss, parts = daily_item
        session_template = session_templates[index] if index < len(session_templates) else {}
        date_value = dt.date() if isinstance(dt, datetime) else dt
        sport = str((session_template or {}).get("sport") or "").strip() or "—"
        session_role = str((session_template or {}).get("session_role") or "").strip() or "—"
        session_name = str((session_template or {}).get("export_name") or "").strip() or "Сессия"
        rows.append(
            {
                "index": index,
                "week_index": index // 7,
                "date": date_value.isoformat() if hasattr(date_value, "isoformat") else str(date_value),
                "date_label": date_value.strftime("%a %d.%m") if hasattr(date_value, "strftime") else str(date_value),
                "phase": str((session_template or {}).get("phase") or "—"),
                "sport": sport,
                "session_role": session_role,
                "session_name": session_name,
                "planned_total_tss": _round_int(_coerce_float(total_tss)),
                "planned_parts": dict(parts or {}),
                "planned_duration_minutes": _coerce_int((session_template or {}).get("duration_minutes"), 0),
                "outcome": "as_planned",
                "actual_total_tss": _round_int(_coerce_float(total_tss)),
            }
        )
    return rows


def summarize_execution_reconciliation(
    execution_reconciliation: Mapping[str, Any] | None,
) -> Dict[str, Any] | None:
    """Normalize a persisted day-level execution reconciliation summary."""
    if not isinstance(execution_reconciliation, Mapping):
        return None

    planned_total_tss = _round_int(_coerce_float(execution_reconciliation.get("planned_total_tss")))
    actual_total_tss = _round_int(_coerce_float(execution_reconciliation.get("actual_total_tss")))
    delta_tss = _round_int(_coerce_float(execution_reconciliation.get("delta_tss"), actual_total_tss - planned_total_tss))
    changed_day_count = _coerce_int(execution_reconciliation.get("changed_day_count"))
    missed_day_count = _coerce_int(execution_reconciliation.get("missed_day_count"))
    reduced_day_count = _coerce_int(execution_reconciliation.get("reduced_day_count"))
    unavailable_day_count = _coerce_int(execution_reconciliation.get("unavailable_day_count"))
    completion_share = execution_reconciliation.get("completion_share")
    if completion_share is None:
        completion_share = (actual_total_tss / planned_total_tss) if planned_total_tss > 0 else 1.0
    completion_share = max(0.0, min(1.0, _coerce_float(completion_share, 1.0)))
    changed_rows = [
        dict(row)
        for row in execution_reconciliation.get("changed_rows", [])
        if isinstance(row, dict)
    ][:10]

    status = str(execution_reconciliation.get("status") or "").strip().lower()
    if not status:
        if changed_day_count <= 0:
            status = "completed"
        elif unavailable_day_count > 0 and unavailable_day_count >= max(1, (changed_day_count + 1) // 2):
            status = "unavailable"
        elif missed_day_count > 0 and reduced_day_count == 0:
            status = "skipped"
        else:
            status = "reduced"

    compact_label = str(execution_reconciliation.get("compact_label") or "").strip()
    if not compact_label:
        compact_label = (
            f"{actual_total_tss}/{planned_total_tss} TSS · {changed_day_count} дн. изменено"
            if changed_day_count > 0
            else f"{actual_total_tss}/{planned_total_tss} TSS"
        )

    description = str(execution_reconciliation.get("description") or "").strip()
    if not description:
        if changed_day_count <= 0:
            description = "Ближнее окно выполнено по плану без отклонений."
        else:
            description = (
                f"По факту выполнено {actual_total_tss} из {planned_total_tss} TSS; "
                f"изменено {changed_day_count} дн."
            )

    return {
        "status": status,
        "status_label": _plan_adjustment_label(status),
        "planned_total_tss": planned_total_tss,
        "actual_total_tss": actual_total_tss,
        "delta_tss": delta_tss,
        "changed_day_count": changed_day_count,
        "missed_day_count": missed_day_count,
        "reduced_day_count": reduced_day_count,
        "unavailable_day_count": unavailable_day_count,
        "completion_share": completion_share,
        "compact_label": compact_label,
        "description": description,
        "changed_rows": changed_rows,
    }


def summarize_execution_reconciliation_rows(
    rows: List[Mapping[str, Any]] | None,
) -> Dict[str, Any]:
    """Summarize day-level execution facts into a compact local-replan input."""
    planned_total_tss = 0
    actual_total_tss = 0
    changed_day_count = 0
    missed_day_count = 0
    reduced_day_count = 0
    unavailable_day_count = 0
    changed_rows: List[Dict[str, Any]] = []

    for row in rows or []:
        planned_tss = max(0, _round_int(_coerce_float(row.get("planned_total_tss"))))
        outcome = str(row.get("outcome") or "as_planned").strip().lower()
        planned_total_tss += planned_tss
        actual_tss = planned_tss
        if outcome == "reduced":
            actual_tss = min(planned_tss, max(0, _round_int(_coerce_float(row.get("actual_total_tss"), planned_tss))))
        elif outcome in {"missed", "unavailable"}:
            actual_tss = 0

        actual_total_tss += actual_tss
        changed = outcome != "as_planned" or actual_tss != planned_tss
        if not changed:
            continue

        changed_day_count += 1
        if outcome == "missed":
            missed_day_count += 1
        elif outcome == "reduced":
            reduced_day_count += 1
        elif outcome == "unavailable":
            unavailable_day_count += 1

        changed_rows.append(
            {
                "Дата": str(row.get("date_label") or row.get("date") or ""),
                "Сессия": str(row.get("session_name") or "Сессия"),
                "План TSS": planned_tss,
                "Факт TSS": actual_tss,
                "Δ TSS": f"{actual_tss - planned_tss:+d}",
                "Статус": EXECUTION_DAY_OUTCOME_LABELS.get(outcome, EXECUTION_DAY_OUTCOME_LABELS["as_planned"]),
            }
        )

    completion_share = (actual_total_tss / planned_total_tss) if planned_total_tss > 0 else 1.0
    if changed_day_count <= 0:
        status = "completed"
    elif unavailable_day_count > 0 and unavailable_day_count >= max(1, (changed_day_count + 1) // 2):
        status = "unavailable"
    elif missed_day_count > 0 and reduced_day_count == 0:
        status = "skipped"
    else:
        status = "reduced"

    summary = summarize_execution_reconciliation(
        {
            "status": status,
            "planned_total_tss": planned_total_tss,
            "actual_total_tss": actual_total_tss,
            "delta_tss": actual_total_tss - planned_total_tss,
            "changed_day_count": changed_day_count,
            "missed_day_count": missed_day_count,
            "reduced_day_count": reduced_day_count,
            "unavailable_day_count": unavailable_day_count,
            "completion_share": completion_share,
            "changed_rows": changed_rows,
        }
    )
    assert summary is not None
    return summary


def build_execution_plan_adjustment(
    goal_plan: Mapping[str, Any],
    rows: List[Mapping[str, Any]] | None,
    *,
    weeks: int = 1,
) -> Dict[str, Any]:
    """Convert day-level execution facts into a plan-adjustment payload."""
    summary = summarize_execution_reconciliation_rows(rows)
    status = str(summary["status"] or "completed")
    available_day_count = _coerce_int((goal_plan.get("constraint_summary", {}) or {}).get("available_day_count"), 0)
    missed_sessions = summary["missed_day_count"] + summary["unavailable_day_count"]

    return {
        "status": status,
        "label": _plan_adjustment_label(status),
        "weeks": max(1, int(weeks or 1)) if status != "none" else 0,
        "missed_sessions": missed_sessions,
        "reduced_load_share": max(0.35, min(0.95, float(summary["completion_share"]))),
        "completion_share": float(summary["completion_share"]),
        "available_day_count": max(1, available_day_count),
        "execution_reconciliation": summary,
    }


def _coerce_start_week(goal_plan: Mapping[str, Any]) -> date:
    raw_start_week = goal_plan.get("start_week")
    if isinstance(raw_start_week, datetime):
        return raw_start_week.date()
    if isinstance(raw_start_week, date):
        return raw_start_week

    weekly_summary = list(goal_plan.get("weekly_summary", []) or [])
    if weekly_summary:
        week_start = weekly_summary[0].get("week_start")
        if isinstance(week_start, datetime):
            return week_start.date()
        if isinstance(week_start, date):
            return week_start

    return datetime.now().date()


def rebuild_goal_plan_with_adjustment(
    goal_plan: Mapping[str, Any],
    plan_adjustment: Mapping[str, Any] | None,
) -> Dict[str, Any]:
    """Rebuild a goal plan from its persisted context plus a new execution checkpoint."""
    constraint_summary = dict(goal_plan.get("constraint_summary", {}) or {})
    base_weekly_tss_plan = [
        int(round(value))
        for value in (goal_plan.get("base_weekly_tss_plan") or goal_plan.get("weekly_tss_plan") or [])
    ]
    phases = list(goal_plan.get("phases", []) or [])
    goal_type = str(goal_plan.get("goal_type") or "Триатлон")
    distance = str(goal_plan.get("distance") or "")
    start_week = _coerce_start_week(goal_plan)
    planner_mix = goal_plan.get("planner_mix") or None
    planner_weights = goal_plan.get("planner_weights") or None

    weekly_tss_plan, constraint_details, rebuilt_constraint_summary = apply_planning_constraints(
        base_weekly_tss_plan,
        phases,
        goal_type,
        available_hours=float(constraint_summary.get("available_hours", 0.0) or 0.0),
        available_day_indices=list(constraint_summary.get("available_day_indices", []) or []),
        interruption_type=str(constraint_summary.get("interruption_type", "none") or "none"),
        interruption_weeks=int(constraint_summary.get("interruption_weeks", 0) or 0),
        catch_up_strategy=str(constraint_summary.get("catch_up_strategy", "protect_recovery") or "protect_recovery"),
        current_tsb=float(constraint_summary.get("current_tsb", 0.0)) if constraint_summary.get("current_tsb") is not None else None,
        current_ctl=float(constraint_summary.get("current_ctl", 0.0)) if constraint_summary.get("current_ctl") is not None else None,
        current_atl=float(constraint_summary.get("current_atl", 0.0)) if constraint_summary.get("current_atl") is not None else None,
        plan_adjustment=plan_adjustment,
    )

    daily_plan, weekly_summary = expand_weekly_to_daily_triathlon(
        weekly_tss_plan,
        phases,
        distance,
        start_week,
        mix_overrides=planner_mix,
        weights_overrides=planner_weights,
        available_day_indices=list(rebuilt_constraint_summary.get("available_day_indices", []) or []),
        goal_type=goal_type,
        load_state=str(rebuilt_constraint_summary.get("load_state", "balanced")),
    )

    for week_row, detail in zip(weekly_summary, constraint_details):
        week_row["capacity_tss"] = detail.get("capacity_tss")
        week_row["adjustment_note"] = detail.get("adjustment_note", "—")

    session_templates = build_daily_session_templates(
        daily_plan,
        weekly_summary,
        goal_type=goal_type,
        distance=distance,
    )

    return {
        "goal_type": goal_type,
        "distance": distance,
        "weeks_to_race": int(goal_plan.get("weeks_to_race", len(weekly_tss_plan)) or len(weekly_tss_plan)),
        "start_week": start_week,
        "weekly_tss_plan": weekly_tss_plan,
        "base_weekly_tss_plan": base_weekly_tss_plan,
        "phases": phases,
        "daily_plan": daily_plan,
        "session_templates": session_templates,
        "weekly_summary": weekly_summary,
        "constraint_summary": rebuilt_constraint_summary,
        "planner_mix": planner_mix,
        "planner_weights": planner_weights,
    }


__all__ = [
    "EXECUTION_DAY_OUTCOME_LABELS",
    "build_execution_plan_adjustment",
    "build_execution_reconciliation_rows",
    "rebuild_goal_plan_with_adjustment",
    "summarize_execution_reconciliation",
    "summarize_execution_reconciliation_rows",
]
