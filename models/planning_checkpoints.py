"""Helpers for compact persisted planning checkpoints."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Optional

from models.planning_execution import (
    summarize_execution_corrective_microcycle,
    summarize_execution_reconciliation,
    summarize_execution_weekly_review,
)
from models.plan_events import synchronize_goal_plan_events
from models.planning_summary import (
    summarize_execution_adaptation_pressure,
    summarize_near_term_edit,
)

NON_ACTIONABLE_PLAN_ADJUSTMENTS = {"", "Нет", "Выполнено по плану"}
CHECKPOINT_SOURCE_LABELS = {
    "initial_plan": "Базовая версия",
    "manual_edit": "Ручная правка",
    "execution_feedback": "Execution replan",
    "execution_adjustment": "Execution replan",
    "coach_constraint": "Ограничение Коуча",
    "restore_version": "Восстановленная версия",
    "legacy_checkpoint": "Сохранённая версия",
}


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


def _parse_datetime(value: Any) -> Any:
    if not value:
        return value
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return value


def _coerce_int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _serialize_daily_plan(daily_plan: List[Any] | None) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for item in daily_plan or []:
        if not isinstance(item, (list, tuple)) or len(item) < 3:
            continue
        dt, total_tss, parts = item
        rows.append(
            {
                "date": _isoformat_date(dt),
                "total_tss": float(total_tss or 0.0),
                "parts": dict(parts or {}),
            }
        )
    return rows


def _restore_daily_plan(rows: List[Any] | None) -> List[tuple[Any, float, Dict[str, float]]]:
    restored: List[tuple[Any, float, Dict[str, float]]] = []
    for item in rows or []:
        if not isinstance(item, dict):
            continue
        restored.append(
            (
                _parse_datetime(item.get("date")),
                float(item.get("total_tss", 0.0) or 0.0),
                dict(item.get("parts", {}) or {}),
            )
        )
    return restored


def with_checkpoint_provenance(
    goal_plan: Dict[str, Any],
    *,
    source: str,
    parent_checkpoint_id: Any = None,
    restored_from_checkpoint_id: Any = None,
) -> Dict[str, Any]:
    """Attach checkpoint lineage metadata to a goal plan before persistence."""
    return {
        **goal_plan,
        "checkpoint_source": str(source or "").strip() or "initial_plan",
        "checkpoint_parent_id": _coerce_int(parent_checkpoint_id),
        "checkpoint_restored_from_checkpoint_id": _coerce_int(restored_from_checkpoint_id),
    }


def _resolve_checkpoint_source(
    source: Any,
    near_term_edit: Dict[str, Any] | None,
    near_term_edit_version: Any,
) -> str:
    normalized = str(source or "").strip()
    if normalized:
        return normalized
    if near_term_edit is not None and int(near_term_edit_version or 0) > 0:
        return "manual_edit"
    return "legacy_checkpoint"


def summarize_checkpoint_provenance(checkpoint: Dict[str, Any] | None) -> Dict[str, Any] | None:
    """Describe how a persisted checkpoint version was produced."""
    if not isinstance(checkpoint, dict):
        return None

    snapshot = checkpoint.get("goal_plan_snapshot")
    snapshot_constraint_summary = {}
    if isinstance(snapshot, dict):
        snapshot_constraint_summary = snapshot.get("constraint_summary", {}) or {}
    near_term_edit = summarize_near_term_edit(snapshot_constraint_summary)

    source_candidate = checkpoint.get("checkpoint_source")
    parent_id = _coerce_int(checkpoint.get("checkpoint_parent_id"))
    restored_from_id = _coerce_int(checkpoint.get("checkpoint_restored_from_checkpoint_id"))
    near_term_edit_version = checkpoint.get("near_term_edit_version")
    if isinstance(snapshot, dict):
        if source_candidate is None:
            source_candidate = snapshot.get("checkpoint_source")
        if parent_id is None:
            parent_id = _coerce_int(snapshot.get("checkpoint_parent_id"))
        if restored_from_id is None:
            restored_from_id = _coerce_int(snapshot.get("checkpoint_restored_from_checkpoint_id"))
        if near_term_edit_version is None:
            near_term_edit_version = snapshot.get("near_term_edit_version")

    source = _resolve_checkpoint_source(
        source_candidate,
        near_term_edit,
        near_term_edit_version,
    )
    label = CHECKPOINT_SOURCE_LABELS.get(source, CHECKPOINT_SOURCE_LABELS["legacy_checkpoint"])
    plan_adjustment_label = str(checkpoint.get("plan_adjustment_label") or "Нет")
    plan_adjustment_weeks = int(checkpoint.get("plan_adjustment_weeks", 0) or 0)

    detail = ""
    if source == "manual_edit":
        detail = (
            near_term_edit.get("compact_label")
            if isinstance(near_term_edit, dict)
            else "Ближайший горизонт изменён вручную"
        )
        if isinstance(near_term_edit, dict) and near_term_edit.get("origin_label"):
            detail += f" · {near_term_edit['origin_label']}"
    elif source == "execution_feedback":
        detail = plan_adjustment_label
        if plan_adjustment_label not in NON_ACTIONABLE_PLAN_ADJUSTMENTS and plan_adjustment_weeks > 0:
            detail += f" на {plan_adjustment_weeks} нед."
    elif source == "restore_version":
        detail = (
            f"Восстановлен checkpoint #{restored_from_id}"
            if restored_from_id is not None
            else "Восстановлена сохранённая версия"
        )
    elif source == "initial_plan":
        detail = "Новый расчёт плана"
    elif source == "coach_constraint":
        detail = "Применено durable-ограничение из Коуча"
    else:
        detail = "Checkpoint без явной provenance-метки"

    return {
        "source": source,
        "label": label,
        "detail": detail,
        "parent_checkpoint_id": parent_id,
        "restored_from_checkpoint_id": restored_from_id,
        "is_execution_feedback": source in {"execution_feedback", "execution_adjustment"},
    }


def build_planning_checkpoint(goal_plan: Dict[str, Any]) -> Dict[str, Any]:
    """Build a compact persisted snapshot from the current goal plan."""
    goal_plan = synchronize_goal_plan_events(goal_plan)
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
    checkpoint_source = _resolve_checkpoint_source(
        goal_plan.get("checkpoint_source"),
        near_term_edit,
        goal_plan.get("near_term_edit_version"),
    )
    checkpoint_parent_id = _coerce_int(goal_plan.get("checkpoint_parent_id"))
    checkpoint_restored_from_id = _coerce_int(goal_plan.get("checkpoint_restored_from_checkpoint_id"))

    goal_plan_snapshot = {
        "goal_type": goal_plan.get("goal_type"),
        "distance": goal_plan.get("distance"),
        "event_date": _isoformat_date(goal_plan.get("event_date")),
        "events": [dict(event) for event in goal_plan.get("events", []) or []],
        "weeks_to_race": goal_plan.get("weeks_to_race"),
        "start_week": _isoformat_date(goal_plan.get("start_week")),
        "weekly_tss_plan": list(goal_plan.get("weekly_tss_plan", []) or []),
        "base_weekly_tss_plan": list(goal_plan.get("base_weekly_tss_plan", []) or []),
        "phases": list(goal_plan.get("phases", []) or []),
        "planner_mix": goal_plan.get("planner_mix"),
        "planner_weights": goal_plan.get("planner_weights"),
        "daily_plan": _serialize_daily_plan(goal_plan.get("daily_plan")),
        "session_templates": list(goal_plan.get("session_templates", []) or []),
        "weekly_summary": weekly_summary_rows,
        "constraint_summary": constraint_summary,
        "demand_level": goal_plan.get("demand_level"),
        "demand_multiplier": goal_plan.get("demand_multiplier"),
        "weekly_target_breakdown": goal_plan.get("weekly_target_breakdown"),
        "plan_revision": goal_plan.get("plan_revision"),
        "near_term_edit_version": int(goal_plan.get("near_term_edit_version", 0) or 0),
        "near_term_edit_horizon_days": int(goal_plan.get("near_term_edit_horizon_days", 0) or 0),
        "near_term_edit_rollback_target_checkpoint_id": goal_plan.get("near_term_edit_rollback_target_checkpoint_id"),
        "checkpoint_source": checkpoint_source,
        "checkpoint_parent_id": checkpoint_parent_id,
        "checkpoint_restored_from_checkpoint_id": checkpoint_restored_from_id,
    }

    plan_adjustment = constraint_summary.get("plan_adjustment", {}) or {}
    execution_adaptation_pressure = summarize_execution_adaptation_pressure(
        plan_adjustment.get("execution_adaptation_pressure")
    )
    adjusted = [int(round(value)) for value in goal_plan_snapshot["weekly_tss_plan"]]
    base = [int(round(value)) for value in goal_plan_snapshot["base_weekly_tss_plan"]]

    return {
        "goal_type": goal_plan.get("goal_type"),
        "distance": goal_plan.get("distance"),
        "event_date": _isoformat_date(goal_plan.get("event_date")),
        "events": [dict(event) for event in goal_plan.get("events", []) or []],
        "weeks_to_race": goal_plan.get("weeks_to_race"),
        "headline": constraint_summary.get("notes", [""])[0] if constraint_summary.get("notes") else "",
        "peak_tss": max(adjusted) if adjusted else 0,
        "base_peak_tss": max(base) if base else 0,
        "total_tss": sum(adjusted),
        "base_total_tss": sum(base),
        "plan_adjustment_label": plan_adjustment.get("label", "Нет"),
        "plan_adjustment_weeks": int(plan_adjustment.get("weeks", 0) or 0),
        "near_term_edit_label": near_term_edit.get("label", "") if near_term_edit else "",
        "near_term_edit_strategy_label": near_term_edit.get("strategy_label", "") if near_term_edit else "",
        "near_term_edit_edited_day_count": near_term_edit.get("edited_day_count", 0) if near_term_edit else 0,
        "near_term_edit_horizon_days": near_term_edit.get("horizon_days", 0) if near_term_edit else 0,
        "near_term_edit_total_delta_tss": near_term_edit.get("total_delta_tss", 0) if near_term_edit else 0,
        "near_term_edit_future_delta_tss": near_term_edit.get("future_delta_tss", 0) if near_term_edit else 0,
        "near_term_edit_risk_level": near_term_edit.get("risk_level", "") if near_term_edit else "",
        "near_term_edit_risk_badge": near_term_edit.get("risk_badge", "") if near_term_edit else "",
        "near_term_edit_origin_kind": near_term_edit.get("origin_kind", "") if near_term_edit else "",
        "near_term_edit_origin_checkpoint_id": near_term_edit.get("origin_checkpoint_id") if near_term_edit else None,
        "near_term_edit_origin_label": near_term_edit.get("origin_label", "") if near_term_edit else "",
        "near_term_edit_rollback_target_checkpoint_id": goal_plan_snapshot.get("near_term_edit_rollback_target_checkpoint_id"),
        "execution_adaptation_pressure_level": execution_adaptation_pressure.get("level", "") if execution_adaptation_pressure else "",
        "execution_adaptation_follow_up_mode": execution_adaptation_pressure.get("follow_up_mode", "") if execution_adaptation_pressure else "",
        "execution_adaptation_follow_up_label": execution_adaptation_pressure.get("follow_up_label", "") if execution_adaptation_pressure else "",
        "checkpoint_source": checkpoint_source,
        "checkpoint_parent_id": checkpoint_parent_id,
        "checkpoint_restored_from_checkpoint_id": checkpoint_restored_from_id,
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

    goal_plan_snapshot = synchronize_goal_plan_events(dict(snapshot))
    goal_plan_snapshot["start_week"] = _parse_date(goal_plan_snapshot.get("start_week"))
    goal_plan_snapshot["daily_plan"] = _restore_daily_plan(goal_plan_snapshot.get("daily_plan"))
    goal_plan_snapshot["session_templates"] = list(goal_plan_snapshot.get("session_templates", []) or [])
    weekly_summary: List[Dict[str, Any]] = []
    for row in goal_plan_snapshot.get("weekly_summary", []) or []:
        normalized_row = dict(row)
        normalized_row["week_start"] = _parse_date(normalized_row.get("week_start"))
        weekly_summary.append(normalized_row)
    goal_plan_snapshot["weekly_summary"] = weekly_summary
    return goal_plan_snapshot


def restore_goal_plan_from_checkpoint(checkpoint: Dict[str, Any] | None) -> Dict[str, Any] | None:
    """Restore a full goal plan from checkpoint snapshot, rebuilding only if legacy snapshots lack daily details."""
    goal_plan_snapshot = checkpoint_to_goal_plan_context(checkpoint)
    if not isinstance(goal_plan_snapshot, dict):
        return None

    if goal_plan_snapshot.get("daily_plan") and goal_plan_snapshot.get("session_templates"):
        return goal_plan_snapshot

    from models.training_planner import (
        build_daily_session_templates,
        expand_weekly_to_daily_triathlon,
    )

    constraint_summary = goal_plan_snapshot.get("constraint_summary", {}) or {}
    weekly_tss_plan = [
        int(round(value))
        for value in (goal_plan_snapshot.get("weekly_tss_plan") or [])
    ]
    phases = list(goal_plan_snapshot.get("phases", []) or [])
    goal_type = str(goal_plan_snapshot.get("goal_type") or "Триатлон")
    distance = str(goal_plan_snapshot.get("distance") or "")
    start_week = goal_plan_snapshot.get("start_week")

    daily_plan, rebuilt_weekly_summary = expand_weekly_to_daily_triathlon(
        weekly_tss_plan,
        phases,
        distance,
        start_week,
        mix_overrides=goal_plan_snapshot.get("planner_mix") or None,
        weights_overrides=goal_plan_snapshot.get("planner_weights") or None,
        available_day_indices=list(constraint_summary.get("available_day_indices", []) or []),
        goal_type=goal_type,
        load_state=str(constraint_summary.get("load_state", "balanced")),
    )
    stored_weekly_summary = list(goal_plan_snapshot.get("weekly_summary", []) or [])
    for idx, week_row in enumerate(rebuilt_weekly_summary):
        stored_row = stored_weekly_summary[idx] if idx < len(stored_weekly_summary) else {}
        week_row["capacity_tss"] = stored_row.get("capacity_tss")
        week_row["adjustment_note"] = stored_row.get("adjustment_note", week_row.get("adjustment_note", "—"))
        week_row["structure_summary"] = stored_row.get("structure_summary", week_row.get("structure_summary", ""))

    session_templates = build_daily_session_templates(
        daily_plan,
        rebuilt_weekly_summary,
        goal_type=goal_type,
        distance=distance,
    )

    return {
        **goal_plan_snapshot,
        "daily_plan": daily_plan,
        "session_templates": session_templates,
        "weekly_summary": rebuilt_weekly_summary,
        "weekly_tss_plan": weekly_tss_plan,
        "goal_type": goal_type,
        "distance": distance,
        "constraint_summary": constraint_summary,
        "phases": phases,
    }


def get_near_term_edit_rollback_target_checkpoint_id(checkpoint: Dict[str, Any] | None) -> int | None:
    """Extract the rollback target checkpoint id for the latest manual near-term edit, if present."""
    if not isinstance(checkpoint, dict):
        return None

    candidate = checkpoint.get("near_term_edit_rollback_target_checkpoint_id")
    if candidate is None:
        snapshot = checkpoint.get("goal_plan_snapshot")
        if isinstance(snapshot, dict):
            candidate = snapshot.get("near_term_edit_rollback_target_checkpoint_id")
    try:
        return int(candidate) if candidate is not None else None
    except (TypeError, ValueError):
        return None


def resolve_goal_plan_context(
    current_goal_plan: Dict[str, Any] | None,
    latest_checkpoint: Dict[str, Any] | None,
) -> Dict[str, Any] | None:
    """Prefer the current full plan; otherwise fall back to the last persisted snapshot."""
    if isinstance(current_goal_plan, dict) and current_goal_plan:
        return synchronize_goal_plan_events(current_goal_plan)
    return checkpoint_to_goal_plan_context(latest_checkpoint)


def summarize_planning_checkpoint(checkpoint: Dict[str, Any] | None) -> Dict[str, Any] | None:
    """Prepare a dashboard/AI-friendly summary from a persisted checkpoint."""
    if not isinstance(checkpoint, dict):
        return None

    checkpoint_id = _coerce_int(checkpoint.get("id"))
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
    plan_adjustment = snapshot_constraint_summary.get("plan_adjustment", {}) or {}
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
    provenance = summarize_checkpoint_provenance(checkpoint)

    return {
        "checkpoint_id": checkpoint_id,
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
        "execution_reconciliation": execution_reconciliation,
        "execution_weekly_review": execution_weekly_review,
        "execution_corrective_microcycle": execution_corrective_microcycle,
        "execution_adaptation_pressure": execution_adaptation_pressure,
        "provenance": provenance,
    }


def summarize_execution_feedback_transition(
    previous_checkpoint: Dict[str, Any] | None,
    current_checkpoint: Dict[str, Any] | None,
) -> Dict[str, Any] | None:
    """Summarize the latest persisted execution checkpoint against its previous baseline."""
    current = summarize_planning_checkpoint(current_checkpoint)
    if current is None:
        return None

    provenance = current.get("provenance") or {}
    if provenance.get("source") not in {"execution_feedback", "execution_adjustment", "legacy_checkpoint"}:
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
        "execution_reconciliation": current.get("execution_reconciliation"),
        "execution_weekly_review": current.get("execution_weekly_review"),
        "execution_corrective_microcycle": current.get("execution_corrective_microcycle"),
        "execution_adaptation_pressure": current.get("execution_adaptation_pressure"),
    }


__all__ = [
    "CHECKPOINT_SOURCE_LABELS",
    "NON_ACTIONABLE_PLAN_ADJUSTMENTS",
    "build_planning_checkpoint",
    "checkpoint_to_goal_plan_context",
    "get_near_term_edit_rollback_target_checkpoint_id",
    "resolve_goal_plan_context",
    "restore_goal_plan_from_checkpoint",
    "summarize_checkpoint_provenance",
    "summarize_execution_feedback_transition",
    "summarize_planning_checkpoint",
    "with_checkpoint_provenance",
]
