"""Canonical race-event helpers shared by planning and coach flows."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, Iterable, List, Mapping


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


_OPTIONAL_EVENT_FIELDS = (
    "source",
    "source_id",
    "category",
    "discipline",
    "discipline_provenance",
    "discipline_confidence",
    "priority_provenance",
    "confirmed",
    "requires_confirmation",
    "distance",
    "description",
)


def _normalize_event(value: Any) -> Dict[str, Any] | None:
    if not isinstance(value, dict):
        return None

    event_date = _isoformat_date(value.get("date"))
    priority = str(value.get("priority") or "").strip().upper()
    if not event_date or priority not in EVENT_PRIORITIES:
        return None

    normalized: Dict[str, Any] = {
        "date": event_date,
        "priority": priority,
        "label": str(value.get("label") or "").strip(),
    }
    for key in _OPTIONAL_EVENT_FIELDS:
        if key in value:
            normalized[key] = value.get(key)
    return normalized


def normalized_events(events: Any) -> List[Dict[str, Any]]:
    """Return valid, serializable A/B/C event dictionaries in input order."""
    if not isinstance(events, Iterable) or isinstance(events, (str, bytes, dict)):
        return []

    normalized: List[Dict[str, Any]] = []
    for value in events:
        event = _normalize_event(value)
        if event is not None:
            normalized.append(event)
    return normalized


def primary_event(events: Any) -> Dict[str, Any] | None:
    """Select highest priority A/B/C event, resolving ties by earliest date."""
    candidates = normalized_events(events)
    if not candidates:
        return None
    return min(candidates, key=lambda event: (EVENT_PRIORITIES[event["priority"]], event["date"]))


def macrocycle_event(events: Any) -> Dict[str, Any] | None:
    """Return the earliest confirmed A event used as the long-term anchor."""
    candidates = [
        event
        for event in normalized_events(events)
        if event["priority"] == "A" and event.get("confirmed", True) is not False
    ]
    return min(candidates, key=lambda event: event["date"]) if candidates else None


def normalize_intervals_event(payload: Mapping[str, Any]) -> Dict[str, Any] | None:
    """Map one Intervals.icu race event to the canonical read-only contract."""
    category = str(payload.get("category") or "").strip().upper()
    if category not in {"RACE_A", "RACE_B", "RACE_C"}:
        return None

    event_date = _isoformat_date(
        payload.get("start_date_local") or payload.get("start_date") or payload.get("date")
    )
    if not event_date:
        return None

    raw_type = str(payload.get("type") or "").strip()
    type_key = raw_type.lower()
    direct_disciplines = {
        "ride": "bike",
        "virtualride": "bike",
        "run": "run",
        "trailrun": "run",
        "swim": "swim",
    }
    discipline = direct_disciplines.get(type_key.replace(" ", ""))
    discipline_provenance = "explicit_type" if discipline else "unknown"
    discipline_confidence = 1.0 if discipline else 0.0

    label = str(payload.get("name") or payload.get("label") or "").strip()
    description = str(payload.get("description") or "").strip()
    evidence = f"{label} {description}".lower()
    multisport_terms = (
        "triathlon",
        "триатлон",
        "ironstar",
        "swim bike run",
        "swim-bike-run",
        "плаван вело бег",
    )
    has_three_legs = all(term in evidence for term in ("swim", "bike", "run"))
    if discipline is None and (any(term in evidence for term in multisport_terms) or has_three_legs):
        discipline = "triathlon"
        discipline_provenance = "name_description_evidence"
        discipline_confidence = 0.9

    requires_confirmation = discipline is None
    event: Dict[str, Any] = {
        "date": event_date,
        "priority": category[-1],
        "label": label,
        "source": "intervals_icu",
        "source_id": str(payload.get("id") or ""),
        "category": category,
        "discipline": discipline,
        "discipline_provenance": discipline_provenance,
        "discipline_confidence": discipline_confidence,
        "priority_provenance": "explicit_category",
        "confirmed": not requires_confirmation,
        "requires_confirmation": requires_confirmation,
    }
    if payload.get("distance") is not None:
        event["distance"] = payload.get("distance")
    if description:
        event["description"] = description
    return event


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
            events = [
                {
                    **legacy_event,
                    "source": "legacy_checkpoint",
                    "priority_provenance": "legacy_assumed",
                    "confirmed": False,
                    "requires_confirmation": True,
                }
            ]

    primary = primary_event(events)
    anchor = macrocycle_event(events)
    planning_mode = str(synchronized.get("planning_mode") or "").strip().lower()
    synchronized["events"] = events
    if planning_mode in {"training_goal", "manual"}:
        synchronized["macrocycle_event_date"] = ""
        synchronized["event_date"] = ""
    elif planning_mode == "event_goal":
        synchronized["macrocycle_event_date"] = anchor["date"] if anchor is not None else ""
        synchronized["event_date"] = synchronized["macrocycle_event_date"]
    else:
        synchronized["event_date"] = primary["date"] if primary is not None else ""
    return synchronized


__all__ = [
    "EVENT_PRIORITIES",
    "build_primary_event",
    "macrocycle_event",
    "normalize_intervals_event",
    "normalized_events",
    "primary_event",
    "synchronize_goal_plan_events",
]
