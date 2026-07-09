"""Canonical race-event helpers shared by planning and coach flows."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, Iterable, List


EVENT_PRIORITIES = {"A": 0, "B": 1, "C": 2}


def _isoformat_date(value: Any) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    try:
        return date.fromisoformat(str(value)[:10]).isoformat()
    except (TypeError, ValueError):
        return ""


def _normalize_event(value: Any) -> Dict[str, str] | None:
    if not isinstance(value, dict):
        return None

    event_date = _isoformat_date(value.get("date"))
    priority = str(value.get("priority") or "").strip().upper()
    if not event_date or priority not in EVENT_PRIORITIES:
        return None

    return {
        "date": event_date,
        "priority": priority,
        "label": str(value.get("label") or "").strip(),
    }


def normalized_events(events: Any) -> List[Dict[str, str]]:
    """Return valid, serializable A/B/C event dictionaries in input order."""
    if not isinstance(events, Iterable) or isinstance(events, (str, bytes, dict)):
        return []

    normalized: List[Dict[str, str]] = []
    for value in events:
        event = _normalize_event(value)
        if event is not None:
            normalized.append(event)
    return normalized


def primary_event(events: Any) -> Dict[str, str] | None:
    """Select highest priority A/B/C event, resolving ties by earliest date."""
    candidates = normalized_events(events)
    if not candidates:
        return None
    return min(candidates, key=lambda event: (EVENT_PRIORITIES[event["priority"]], event["date"]))


def build_primary_event(date_value: Any, label: str) -> Dict[str, str] | None:
    """Build the single A event used by existing one-date plan builders."""
    event_date = _isoformat_date(date_value)
    if not event_date:
        return None
    return {"date": event_date, "priority": "A", "label": str(label or "").strip()}


def _legacy_event_label(goal_plan: Dict[str, Any]) -> str:
    label = " ".join(
        str(value).strip()
        for value in (goal_plan.get("goal_type"), goal_plan.get("distance"))
        if str(value or "").strip()
    )
    return label or "Основной старт"


def synchronize_goal_plan_events(goal_plan: Dict[str, Any]) -> Dict[str, Any]:
    """Copy a plan with canonical events and event_date derived from them.

    A checkpoint created before race events existed has only ``event_date``.
    Such a legacy alias becomes one A event during restore/normalization.
    """
    synchronized = dict(goal_plan)
    events = normalized_events(synchronized.get("events"))
    if not events:
        legacy_event = build_primary_event(
            synchronized.get("event_date"),
            _legacy_event_label(synchronized),
        )
        if legacy_event is not None:
            events = [legacy_event]

    primary = primary_event(events)
    synchronized["events"] = events
    synchronized["event_date"] = primary["date"] if primary is not None else ""
    return synchronized


__all__ = [
    "EVENT_PRIORITIES",
    "build_primary_event",
    "normalized_events",
    "primary_event",
    "synchronize_goal_plan_events",
]
