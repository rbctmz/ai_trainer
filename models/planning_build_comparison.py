"""Read-only dated comparison of raw saved prescriptions, never regenerated plans."""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from datetime import date, timedelta
import math
from typing import Any, Mapping

from models.planning_build_confirmation import PlanningBuildPreviewError, canonical_json
from models.planning_cycle import stored_day
from services.planning_contracts import DAY_MAP, DISTANCE_MAP, GOAL_TYPE_MAP

VERSION = "plan-comparison-v1"
MAX_DAYS = 366


def _mapping(value: Any) -> Mapping:
    return value if isinstance(value, Mapping) else {}


def _number(value: Any) -> float | None:
    if type(value) not in (int, float):
        return None
    try:
        parsed = float(value)
        return parsed if math.isfinite(parsed) and parsed >= 0 else None
    except (ValueError, OverflowError):
        return None


def _text(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _key(value: Any, choices: Mapping) -> str | None:
    return next((key for key, label in choices.items() if value in (key, label)), None)


def _day(value: Any) -> str | None:
    parsed = stored_day(value)
    return parsed.isoformat() if parsed else None


def _safe(value: Any) -> Any:
    try:
        canonical_json(value)
        return deepcopy(value)
    except (ValueError, TypeError, OverflowError):
        return None


def _valid_session(raw: Mapping) -> bool:
    steps, legs = raw.get("materialized_steps"), raw.get("legs")
    load = raw.get("total_tss") if "total_tss" in raw else raw.get("target_tss")
    if _number(raw.get("duration_minutes")) is None or _number(load) is None:
        return False
    if raw.get("kind") == "composite":
        return isinstance(legs, list) and bool(legs) and all(isinstance(leg, Mapping) and _valid_session(leg) for leg in legs)
    return isinstance(steps, list) and bool(steps) and all(
        isinstance(step, Mapping) and _safe(step) is not None
        and (_number(step.get("duration_seconds")) or 0) > 0
        and isinstance(step.get("target"), Mapping) and bool(step["target"])
        for step in steps
    )


def _session(raw: Mapping) -> dict:
    steps = raw.get("materialized_steps")
    legs = raw.get("legs")
    return {
        "kind": _text(raw.get("kind")), "sport": _text(raw.get("sport")),
        "role": _text(raw.get("session_role")), "focus": _text(raw.get("session_focus")),
        "name": _text(raw.get("template_name")) or _text(raw.get("export_name")),
        "minutes": _number(raw.get("duration_minutes")),
        "tss": _number(raw.get("total_tss") if "total_tss" in raw else raw.get("target_tss")),
        "transition_minutes": _number(raw.get("transition_minutes")),
        "materialization_status": _text(raw.get("materialization_status")),
        "structure_status": _text(raw.get("structure_status")),
        "steps": [{"name": _text(step.get("name")), "intensity": _text(step.get("intensity")),
                   "segment_kind": _text(step.get("segment_kind")), "duration_seconds": _number(step.get("duration_seconds")),
                   "target": _safe(step.get("target"))}
                  for step in steps if isinstance(step, Mapping)] if isinstance(steps, list) else None,
        "legs": [_session(leg) for leg in legs if isinstance(leg, Mapping)] if isinstance(legs, list) else None,
    }


def _events(value: Any) -> list | None:
    if not isinstance(value, list):
        return None
    keys = ("date", "priority", "label", "source", "source_id", "category", "discipline",
            "discipline_provenance", "discipline_confidence", "priority_provenance", "confirmed", "requires_confirmation")
    result = []
    for event in value:
        if not isinstance(event, Mapping) or _day(event.get("date")) is None or event.get("priority") not in {"A", "B", "C"} or not isinstance(event.get("label"), str):
            return None
        clean = {key: _safe(event[key]) for key in keys if key in event}
        clean["date"] = _day(event["date"])
        result.append(clean)
    return result


def _parameters(plan: Mapping, params: Mapping | None) -> dict:
    if params is not None:
        return {key: _events(plan.get("events")) if key == "events" else _safe(params.get(key))
                for key in ("goal_type", "distance", "planning_mode", "intent", "focus", "demand", "available_hours", "available_days", "events")}
    constraints = _mapping(plan.get("constraint_summary"))
    indices = constraints.get("available_day_indices")
    valid_days = isinstance(indices, list) and all(type(i) is int and 0 <= i < 7 for i in indices)
    return {
        "goal_type": _key(plan.get("goal_type"), GOAL_TYPE_MAP),
        "distance": _key(plan.get("distance"), DISTANCE_MAP),
        "planning_mode": _text(plan.get("planning_mode")), "intent": _text(plan.get("planning_intent")),
        "focus": _text(plan.get("planning_focus")), "demand": _text(plan.get("demand_level")),
        "available_hours": _number(constraints.get("available_hours")),
        "available_days": [list(DAY_MAP)[i] for i in sorted(set(indices))] if valid_days else None,
        "events": _events(plan.get("events")),
    }


def _unknown(state: str = "unknown") -> dict:
    return {"state": state, "phase": None, "tss": None, "sessions": None}


def _side(checkpoint: Mapping, expected: Mapping, params: Mapping | None = None) -> tuple[dict, dict, set[str]]:
    plan = _mapping(checkpoint.get("goal_plan_snapshot"))
    parameters = _parameters(plan, params)
    reasons = [f"parameter_missing:{key}" for key, value in parameters.items() if value is None]
    out = {"scope": None, "parameters": parameters, "total_tss": None, "peak_tss": None,
           "schedule_status": "unavailable", "reasons": reasons}
    daily, templates = plan.get("daily_plan"), plan.get("session_templates")
    if not isinstance(daily, list) or not daily:
        reasons.append("saved_days_missing")
        return out, {}, set()
    raw_dates = [_day(_mapping(row).get("date")) for row in daily]
    known_dates = [dt for dt in raw_dates if dt]
    if not known_dates:
        reasons.append("saved_dates_invalid")
        return out, {}, set()
    first, last = min(known_dates), max(known_dates)
    span = (date.fromisoformat(last) - date.fromisoformat(first)).days + 1
    if len(daily) > MAX_DAYS or span > MAX_DAYS or (isinstance(templates, list) and len(templates) > MAX_DAYS):
        reasons.append("schedule_too_large")
        return out, {}, set()
    dates = {(date.fromisoformat(first) + timedelta(days=i)).isoformat() for i in range(span)}
    ordered = len(known_dates) == len(raw_dates) and known_dates == sorted(set(known_dates))
    matched_scope = first == _day(expected.get("start_date")) and last == _day(expected.get("end_date"))
    if not matched_scope:
        reasons.append("scope_unverified")
    if ordered and matched_scope:
        out["scope"] = {"start_date": first, "end_date": last}
    else:
        reasons.append("saved_dates_invalid")
    rows = {dt: row for dt, row in zip(raw_dates, daily) if dt and isinstance(row, Mapping)}
    template_dates = [_day(_mapping(row).get("date")) for row in templates] if isinstance(templates, list) else []
    template_valid = (isinstance(templates, list) and len(template_dates) == len(set(template_dates))
                      and None not in template_dates)
    template_map = dict(zip(template_dates, templates)) if template_valid else {}
    if not template_valid or set(template_map) != set(rows):
        reasons.append("saved_templates_invalid")
    values = {}
    for dt in sorted(dates):
        row = _mapping(rows.get(dt))
        template = _mapping(template_map.get(dt))
        sessions = template.get("sessions")
        load = _number(row.get("total_tss"))
        if not ordered or load is None or not isinstance(sessions, list) or any(not isinstance(s, Mapping) or not _valid_session(s) for s in sessions) or (load > 0 and not sessions):
            values[dt] = _unknown()
            continue
        projected = [_session(s) for s in sessions]
        values[dt] = {"state": "scheduled" if sessions else "rest", "phase": _text(template.get("phase")),
                      "tss": load, "sessions": projected}
    all_loads = [_number(_mapping(row).get("total_tss")) for row in daily]
    dense = ordered and matched_scope and len(rows) == span and all(value is not None for value in all_loads)
    if dense:
        out["total_tss"] = round(math.fsum(all_loads))
        weeks = plan.get("weekly_summary")
        week_dates = [_day(_mapping(w).get("week_start")) for w in weeks] if isinstance(weeks, list) else []
        valid_weeks = bool(week_dates) and None not in week_dates and len(set(week_dates)) == len(week_dates)
        if valid_weeks:
            coverage = {dt: sum(0 <= (date.fromisoformat(dt) - date.fromisoformat(w)).days < 7 for w in week_dates) for dt in dates}
            valid_weeks = all(count == 1 for count in coverage.values()) and all(any(0 <= (date.fromisoformat(dt) - date.fromisoformat(w)).days < 7 for dt in dates) for w in week_dates)
        if valid_weeks:
            out["peak_tss"] = round(max(math.fsum(_number(rows[dt].get("total_tss")) for dt in dates
                                      if 0 <= (date.fromisoformat(dt) - date.fromisoformat(w)).days < 7) for w in week_dates))
        else:
            reasons.append("weekly_scope_unverified")
    else:
        reasons.append("saved_load_incomplete")
    if any(value["state"] == "unknown" for value in values.values()):
        reasons.append("saved_assignments_incomplete")
    if not matched_scope or not ordered or not template_valid or set(template_map) != set(rows):
        reasons.append("saved_schedule_incomplete")
    out["schedule_status"] = "partial" if any(reason.startswith(("saved_", "scope_")) for reason in reasons) else "complete"
    return out, values, dates


def _value(side: dict, values: dict, dt: str) -> dict:
    if dt in values:
        return values[dt]
    scope = side.get("scope")
    if side["schedule_status"] == "complete" and scope and not (scope["start_date"] <= dt <= scope["end_date"]):
        return _unknown("outside")
    return _unknown()


def _change(before: dict, after: dict) -> str:
    if "unknown" in (before["state"], after["state"]):
        return "unknown"
    scheduled_before, scheduled_after = before["state"] == "scheduled", after["state"] == "scheduled"
    if scheduled_before != scheduled_after:
        return "removed" if scheduled_before else "added"
    if not scheduled_before:
        return "changed" if before["state"] == after["state"] == "rest" and before["phase"] != after["phase"] else "unchanged"
    same = before["phase"] == after["phase"] and before["tss"] == after["tss"]
    same = same and sorted(canonical_json(s) for s in before["sessions"]) == sorted(canonical_json(s) for s in after["sessions"])
    return "unchanged" if same else "changed"


def build_plan_comparison(before_checkpoint: Mapping | None, after_checkpoint: Mapping, parameters: Mapping, context: Mapping) -> dict:
    """Compare captured raw baseline to final saved JSON without reads or mutation."""
    lifecycle = _mapping(context.get("lifecycle"))
    ownership = _mapping(context.get("cycle_ownership"))
    expected_id = lifecycle.get("base_checkpoint_id") or 0
    if before_checkpoint is not None and before_checkpoint.get("id") != expected_id:
        raise PlanningBuildPreviewError("preview_stale", "Исходная версия плана изменилась — пересоберите предпросмотр.")
    before = before_values = None
    old_dates: set[str] = set()
    has_baseline = before_checkpoint is not None or bool(expected_id) or lifecycle.get("source_cycle_id") is not None
    if has_baseline:
        before, before_values, old_dates = _side(before_checkpoint or {}, _mapping(ownership.get("cycle")))
    after, after_values, new_dates = _side(after_checkpoint, lifecycle, parameters)
    days = []
    for dt in sorted(old_dates | new_dates):
        old_value = _value(before, before_values, dt) if before else _unknown()
        new_value = _value(after, after_values, dt)
        days.append({"date": dt, "change": _change(old_value, new_value), "before": old_value, "after": new_value})
    reasons = sorted(set([*(before["reasons"] if before else []), *after["reasons"]]))
    status = "no_baseline" if before is None else "partial" if reasons else "complete"
    counts = Counter(day["change"] for day in days)
    return {"version": VERSION, "status": status, "base_checkpoint_id": lifecycle.get("base_checkpoint_id") or None,
            "base_cycle_id": lifecycle.get("source_cycle_id"), "base_cycle_revision": lifecycle.get("base_cycle_revision"),
            "before": before, "after": after, "days": days,
            "counts": {key: counts[key] for key in ("added", "removed", "changed", "unchanged", "unknown")} if status == "complete" else None,
            "reasons": reasons}
