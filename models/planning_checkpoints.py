"""Helpers for compact persisted planning checkpoints."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Optional

from models.planning_summary import summarize_near_term_edit

NON_ACTIONABLE_PLAN_ADJUSTMENTS = {"", "Нет", "Выполнено по плану"}


def _isoformat_date(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _parse_date(value: Any) -> Any:
    if not value:
        return value
    try:
        return datetime.fromisoformat(str(value)).date()
    except ValueError:
        return value


def build_planning_checkpoint(goal_plan: Dict[str, Any]) -> Dict[str, Any]:
    """Build a compact persisted snapshot from the current goal plan."""
    weekly_summary_rows: List[Dict[str, Any]] = []
    for row in goal_plan.get("weekly_summary", []) or []:
        weekly_summary_rows.append(
            {
                "week_start": _isoformat_date(row.get("week_start")),
                "phase": row.get("phase"),
                "weekly_tss": row.get("weekly_tss"),
                "capacity_tss": row.get("capacity_tss"),
                "adjustment_note": row.get("adjustment_note", "—"),
                "structure_summary": row.get("structure_summary", ""),
            }
        )

    constraint_summary = dict(goal_plan.get("constraint_summary", {}) or {})
    constraint_summary["notes"] = [
        str(note)
        for note in constraint_summary.get("notes", [])
        if note
    ]

    near_term_edit = summarize_near_term_edit(constraint_summary)

    goal_plan_snapshot = {
        "goal_type": goal_plan.get("goal_type"),
        "distance": goal_plan.get("distance"),
        "weeks_to_race": goal_plan.get("weeks_to_race"),
        "start_week": _isoformat_date(goal_plan.get("start_week")),
        "weekly_tss_plan": list(goal_plan.get("weekly_tss_plan", []) or []),
        "base_weekly_tss_plan": list(goal_plan.get("base_weekly_tss_plan", []) or []),
        "phases": list(goal_plan.get("phases", []) or []),
        "planner_mix": goal_plan.get("planner_mix"),
        "planner_weights": goal_plan.get("planner_weights"),
        "weekly_summary": weekly_summary_rows,
        "constraint_summary": constraint_summary,
    }

    plan_adjustment = constraint_summary.get("plan_adjustment", {}) or {}
    adjusted = [int(round(value)) for value in goal_plan_snapshot["weekly_tss_plan"]]
    base = [int(round(value)) for value in goal_plan_snapshot["base_weekly_tss_plan"]]

    return {
        "goal_type": goal_plan.get("goal_type"),
        "distance": goal_plan.get("distance"),
        "weeks_to_race": goal_plan.get("weeks_to_race"),
        "headline": constraint_summary.get("notes", [""])[0] if constraint_summary.get("notes") else "",
        "peak_tss": max(adjusted) if adjusted else 0,
        "base_peak_tss": max(base) if base else 0,
        "total_tss": sum(adjusted),
        "base_total_tss": sum(base),
        "plan_adjustment_label": plan_adjustment.get("label", "Нет"),
        "plan_adjustment_weeks": int(plan_adjustment.get("weeks", 0) or 0),
        "near_term_edit_label": near_term_edit.get("label", "") if near_term_edit else "",
        "near_term_edit_edited_day_count": near_term_edit.get("edited_day_count", 0) if near_term_edit else 0,
        "near_term_edit_horizon_days": near_term_edit.get("horizon_days", 0) if near_term_edit else 0,
        "near_term_edit_total_delta_tss": near_term_edit.get("total_delta_tss", 0) if near_term_edit else 0,
        "interruption_label": constraint_summary.get("interruption_label", "Нет"),
        "load_state_label": constraint_summary.get("load_state_label"),
        "goal_plan_snapshot": goal_plan_snapshot,
    }


def checkpoint_to_goal_plan_context(checkpoint: Dict[str, Any] | None) -> Dict[str, Any] | None:
    """Convert a persisted checkpoint back to a goal-plan-like context for explainability."""
    if not isinstance(checkpoint, dict):
        return None

    snapshot = checkpoint.get("goal_plan_snapshot")
    if not isinstance(snapshot, dict):
        return None

    goal_plan_snapshot = dict(snapshot)
    goal_plan_snapshot["start_week"] = _parse_date(goal_plan_snapshot.get("start_week"))
    weekly_summary: List[Dict[str, Any]] = []
    for row in goal_plan_snapshot.get("weekly_summary", []) or []:
        normalized_row = dict(row)
        normalized_row["week_start"] = _parse_date(normalized_row.get("week_start"))
        weekly_summary.append(normalized_row)
    goal_plan_snapshot["weekly_summary"] = weekly_summary
    return goal_plan_snapshot


def resolve_goal_plan_context(
    current_goal_plan: Dict[str, Any] | None,
    latest_checkpoint: Dict[str, Any] | None,
) -> Dict[str, Any] | None:
    """Prefer the current full plan; otherwise fall back to the last persisted snapshot."""
    if isinstance(current_goal_plan, dict) and current_goal_plan:
        return current_goal_plan
    return checkpoint_to_goal_plan_context(latest_checkpoint)


def summarize_planning_checkpoint(checkpoint: Dict[str, Any] | None) -> Dict[str, Any] | None:
    """Prepare a dashboard/AI-friendly summary from a persisted checkpoint."""
    if not isinstance(checkpoint, dict):
        return None

    goal_type = str(checkpoint.get("goal_type") or "").strip()
    distance = str(checkpoint.get("distance") or "").strip()
    created_at = checkpoint.get("created_at")
    created_at_label = ""
    if created_at:
        try:
            created_at_label = datetime.fromisoformat(str(created_at)).strftime("%d.%m.%Y %H:%M")
        except ValueError:
            created_at_label = str(created_at)
    plan_adjustment_label = str(checkpoint.get("plan_adjustment_label") or "Нет")
    plan_adjustment_weeks = int(checkpoint.get("plan_adjustment_weeks", 0) or 0)
    headline = str(checkpoint.get("headline") or "").strip()
    title = " • ".join(part for part in [goal_type, distance] if part) or "Последний planning checkpoint"
    peak_tss = int(checkpoint.get("peak_tss", 0) or 0)
    total_tss = int(checkpoint.get("total_tss", 0) or 0)
    interruption_label = str(checkpoint.get("interruption_label") or "Нет")
    load_state_label = str(checkpoint.get("load_state_label") or "").strip()
    snapshot = checkpoint.get("goal_plan_snapshot")
    snapshot_constraint_summary = {}
    if isinstance(snapshot, dict):
        snapshot_constraint_summary = snapshot.get("constraint_summary", {}) or {}
    near_term_edit = summarize_near_term_edit(snapshot_constraint_summary)

    return {
        "title": title,
        "created_at_label": created_at_label,
        "headline": headline,
        "plan_adjustment_label": plan_adjustment_label,
        "plan_adjustment_weeks": plan_adjustment_weeks,
        "peak_tss": peak_tss,
        "total_tss": total_tss,
        "interruption_label": interruption_label,
        "load_state_label": load_state_label,
        "near_term_edit": near_term_edit,
    }


def summarize_execution_feedback_transition(
    previous_checkpoint: Dict[str, Any] | None,
    current_checkpoint: Dict[str, Any] | None,
) -> Dict[str, Any] | None:
    """Summarize the latest persisted execution checkpoint against its previous baseline."""
    current = summarize_planning_checkpoint(current_checkpoint)
    if current is None:
        return None

    plan_adjustment_label = str(current.get("plan_adjustment_label") or "Нет")
    if plan_adjustment_label in NON_ACTIONABLE_PLAN_ADJUSTMENTS:
        return None

    previous = summarize_planning_checkpoint(previous_checkpoint)
    same_goal = (
        previous is not None
        and previous.get("title") == current.get("title")
    )

    previous_peak = int((previous or {}).get("peak_tss", current["peak_tss"]) or 0) if same_goal else int(current["peak_tss"] or 0)
    previous_total = int((previous or {}).get("total_tss", current["total_tss"]) or 0) if same_goal else int(current["total_tss"] or 0)
    current_peak = int(current["peak_tss"] or 0)
    current_total = int(current["total_tss"] or 0)

    return {
        "title": current["title"],
        "created_at_label": current["created_at_label"],
        "plan_adjustment_label": plan_adjustment_label,
        "plan_adjustment_weeks": int(current.get("plan_adjustment_weeks", 0) or 0),
        "peak_tss": current_peak,
        "peak_delta": current_peak - previous_peak,
        "total_tss": current_total,
        "total_delta": current_total - previous_total,
    }


__all__ = [
    "NON_ACTIONABLE_PLAN_ADJUSTMENTS",
    "build_planning_checkpoint",
    "checkpoint_to_goal_plan_context",
    "resolve_goal_plan_context",
    "summarize_execution_feedback_transition",
    "summarize_planning_checkpoint",
]
