"""Reusable execution-feedback and local-replanning helpers."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, Mapping

from models.training_planner import (
    apply_planning_constraints,
    build_daily_session_templates,
    expand_weekly_to_daily_triathlon,
)


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


__all__ = ["rebuild_goal_plan_with_adjustment"]
