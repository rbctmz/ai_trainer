"""Pure preparation-cycle projection; dates never imply execution or participation."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
import hashlib
import json
import math
import re
from typing import Any, Mapping


class CycleStateCorrupt(ValueError):
    """Persisted selection is unavailable; a reader must not initialize it."""


class CycleNotFound(ValueError):
    """The explicitly requested historical cycle does not exist."""


class CycleCommandError(ValueError):
    """Safe, structured refusal; no private stored payload in the message."""

    def __init__(self, code: str, detail: str, *, status: int = 409, retryable: bool = False) -> None:
        super().__init__(detail)
        self.code, self.status, self.retryable = code, status, retryable


def constraint_fingerprint(row: Mapping[str, Any]) -> str:
    """CAS over the existing public constraint fields, including scope metadata."""
    fields = ("id", "date", "kind", "status", "source", "note", "plan_id", "session_id",
              "metadata", "resolved_at", "created_at", "sport", "cycle_scope", "cycle_id")
    encoded = json.dumps({key: row.get(key) for key in fields}, sort_keys=True,
                         ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode()).hexdigest()


@dataclass(frozen=True)
class CyclePeriod:
    start: date | None = None
    end: date | None = None
    reason_code: str | None = None


def stored_day(value: Any) -> date | None:
    """Read canonical persisted ISO dates/datetimes without guessing a timezone."""
    if not isinstance(value, str):
        return None
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            return date.fromisoformat(value)
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}T.+", value):
            return datetime.fromisoformat(value).date()
    except ValueError:
        pass
    return None


def checkpoint_period(checkpoint: Mapping[str, Any] | None) -> CyclePeriod:
    """Use actual saved daily dates, never event/creation dates or a rebuilt plan."""
    snapshot = (checkpoint or {}).get("goal_plan_snapshot")
    if not isinstance(snapshot, Mapping):
        return CyclePeriod(reason_code="checkpoint_snapshot_missing")
    daily = snapshot.get("daily_plan")
    if not isinstance(daily, list) or not daily:
        return CyclePeriod(reason_code="checkpoint_days_missing")
    templates = snapshot.get("session_templates")
    if not isinstance(templates, list) or len(templates) != len(daily):
        return CyclePeriod(reason_code="checkpoint_templates_invalid")
    for template in templates:
        if not isinstance(template, Mapping):
            return CyclePeriod(reason_code="checkpoint_templates_invalid")
        sessions = template.get("sessions")
        if sessions is not None and (not isinstance(sessions, list) or any(not isinstance(row, Mapping) for row in sessions)):
            return CyclePeriod(reason_code="checkpoint_templates_invalid")
    days = []
    for row in daily:
        if not isinstance(row, Mapping) or (day := stored_day(row.get("date"))) is None:
            return CyclePeriod(reason_code="checkpoint_days_invalid")
        try:
            load = float(row["total_tss"])
        except (KeyError, TypeError, ValueError, OverflowError):
            return CyclePeriod(reason_code="checkpoint_load_invalid")
        if isinstance(row["total_tss"], bool) or not math.isfinite(load) or load < 0:
            return CyclePeriod(reason_code="checkpoint_load_invalid")
        if days and day <= days[-1]:
            return CyclePeriod(reason_code="checkpoint_days_contradictory")
        days.append(day)
    return CyclePeriod(days[0], days[-1])


def cycle_checkpoint_reason(
    cycle: Mapping[str, Any] | None, checkpoint: Mapping[str, Any] | None,
    *, mapping_valid: bool,
) -> str | None:
    """Reject broken ownership before interpreting a selected plan's dates."""
    if cycle is None:
        return "cycle_missing"
    if cycle.get("status") not in {"open", "closed"}:
        return "cycle_status_invalid"
    if not mapping_valid:
        return "checkpoint_cycle_mismatch"
    if checkpoint is None:
        return "checkpoint_missing"
    period = checkpoint_period(checkpoint)
    if period.reason_code:
        return period.reason_code
    if (stored_day(cycle.get("start_date")), stored_day(cycle.get("end_date"))) != (period.start, period.end):
        return "cycle_bounds_mismatch"
    return None


def cycle_events(cycle: Mapping[str, Any], checkpoint: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    """Derive scoped event keys from stored snapshots, without event discovery."""
    snapshot = (checkpoint or {}).get("goal_plan_snapshot") or {}
    if not isinstance(snapshot, Mapping):
        return []
    declarations = json.loads(cycle.get("event_outcomes_json") or "{}")
    if not isinstance(declarations, dict) or any(
        value not in {"unspecified", "did_not_participate", "participated"}
        for value in declarations.values()
    ):
        raise ValueError("invalid stored outcome")
    events, seen = [], set()
    raw_events = snapshot.get("events")
    if raw_events is not None and not isinstance(raw_events, list):
        raise ValueError("invalid stored events")
    for raw in raw_events or []:
        if not isinstance(raw, Mapping):
            continue
        material = {key: raw.get(key) for key in ("source", "source_id", "id", "date", "priority", "label")}
        encoded = json.dumps([cycle["id"], material], sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        key = hashlib.sha256(encoded.encode()).hexdigest()
        # Duplicate snapshots have no unambiguous target for an outcome command.
        events.append({**raw, "event_key": key, "outcome": declarations.get(key, "unspecified"),
                       "is_ambiguous": key in seen})
        seen.add(key)
    duplicate_keys = {event["event_key"] for event in events if event["is_ambiguous"]}
    for event in events:
        event["is_ambiguous"] = event["event_key"] in duplicate_keys
    return events


def _week(row: Mapping[str, Any], number: int, *, historical: bool) -> dict[str, Any]:
    return {"number": number, "phase": row.get("phase"), "week_start": row.get("week_start"),
            "weekly_tss": row.get("weekly_tss"), "is_historical": historical}


def project_cycle_context(
    *, selection: Mapping[str, Any], cycle: Mapping[str, Any] | None,
    checkpoint: Mapping[str, Any] | None, athlete_day: date, athlete_timezone: str,
    has_history: bool, mapping_valid: bool, queried_cycle_id: str | None = None,
) -> dict[str, Any]:
    """Project a coherent store snapshot; no clock, database, providers or writes."""
    selected_id = selection["current_cycle_id"]
    cycle_id = queried_cycle_id if queried_cycle_id is not None else selected_id
    is_selected = cycle_id is not None and cycle_id == selected_id
    result = {
        "state": "no_current", "cycle_id": cycle_id, "is_selected": is_selected,
        "current_cycle_id": selected_id, "selection_revision": selection["revision"],
        "cycle_revision": (cycle or {}).get("revision"),
        "checkpoint_id": (cycle or {}).get("current_checkpoint_id"),
        "start_date": None, "end_date": None,
        "athlete_day": athlete_day.isoformat(), "athlete_timezone": athlete_timezone,
        "is_legacy": (cycle or {}).get("origin") == "legacy_import", "has_history": has_history,
        "reason_code": None, "allowed_actions": ["start_new", "browse_history"],
        "events": [], "current_week": None, "last_week": None,
    }
    if cycle_id is None:
        return result
    reason = cycle_checkpoint_reason(cycle, checkpoint, mapping_valid=mapping_valid)
    period = checkpoint_period(checkpoint)
    if not reason:
        result.update(start_date=period.start.isoformat(), end_date=period.end.isoformat())
    try:
        result["events"] = cycle_events(cycle, checkpoint) if cycle and mapping_valid else []
    except (ValueError, TypeError):
        reason = reason or "cycle_outcomes_invalid"
    if cycle and cycle["status"] == "closed" and not is_selected:
        state = "closed"
    elif cycle and cycle["status"] == "closed":
        reason, state = "selected_cycle_closed", "indeterminate"
    elif not is_selected:
        reason, state = reason or "cycle_not_selected", "indeterminate"
    elif reason:
        state = "indeterminate"
    elif athlete_day < period.start:
        state = "scheduled"
    elif athlete_day > period.end:
        state = "period_ended"
    else:
        state = "in_progress"
    result.update(state=state, reason_code=reason)
    actions = ["browse_history"]
    if is_selected and cycle and cycle["status"] == "open":
        actions = ["close", "start_new", "browse_history"]
        if state in {"scheduled", "in_progress"}:
            actions.insert(0, "edit_current")
    elif state == "closed":
        actions = ["inspect"]
        if any(not event["is_ambiguous"] for event in result["events"]):
            actions.append("set_event_outcome")
    result["allowed_actions"] = actions
    snapshot = (checkpoint or {}).get("goal_plan_snapshot") or {}
    weeks = snapshot.get("weekly_summary") if isinstance(snapshot, Mapping) else None
    if not reason and isinstance(weeks, list):
        for number, row in enumerate(weeks, 1):
            if not isinstance(row, Mapping) or (start := stored_day(row.get("week_start"))) is None:
                continue
            if start + timedelta(days=7) <= athlete_day:
                result["last_week"] = _week(row, number, historical=True)
            if state == "in_progress" and start <= athlete_day < start + timedelta(days=7):
                result["current_week"] = _week(row, number, historical=False)
        # A partial final week can already be historical when the actual period ended.
        if state in {"period_ended", "closed"} and weeks and isinstance(weeks[-1], Mapping):
            result["last_week"] = _week(weeks[-1], len(weeks), historical=True)
    return result
