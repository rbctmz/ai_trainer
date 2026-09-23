"""Canonical read-only projection for one planned session (Issue #609).

This module composes an existing plan/actual reconciliation snapshot. It does
not match activities, query providers, or persist state. Matching precedence
stays owned by :mod:`models.plan_actual_reconciliation`.
"""
from __future__ import annotations

from datetime import datetime, timezone
import math
from typing import Any, Mapping, Sequence


SESSION_PROJECTION_SCHEMA_VERSION = "session_projection_v1"


class SessionProjectionNotFoundError(LookupError):
    """Raised when a requested parent session is absent from the snapshot."""


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number < 0:
        return None
    return round(number, 1)


def _signed_number(value: Any) -> float | None:
    """Parse a finite numeric delta without discarding valid negative values."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return round(number, 1)


def _integer(value: Any) -> int | None:
    number = _number(value)
    if number is None or not number.is_integer():
        return None
    return int(number)


def _score(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number < 0 or number > 1:
        return None
    return round(number, 2)


def _activity_id(activity: Mapping[str, Any]) -> str:
    return str(activity.get("activity_id") or "").strip()


def _activity_map(rows: Any) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
        return result
    for raw in rows:
        if not isinstance(raw, Mapping):
            continue
        activity = dict(raw)
        identity = _activity_id(activity)
        if identity:
            result.setdefault(identity, activity)
    return result


def _sum_activity_tss(activities: Mapping[str, Mapping[str, Any]]) -> float:
    return round(
        sum(_number(activity.get("tss")) or 0.0 for activity in activities.values()),
        1,
    )


def _ordered_activities(
    rows: Any,
) -> tuple[list[dict[str, Any]], bool]:
    activities = list(_activity_map(rows).values())
    if not activities:
        return [], True
    starts: list[datetime] = []
    for activity in activities:
        raw = str(activity.get("started_at_utc") or "").strip()
        if not raw:
            return activities, False
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return activities, False
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        else:
            parsed = parsed.astimezone(timezone.utc)
        starts.append(parsed)
    if len(set(starts)) != len(starts):
        return activities, False
    return [
        activity
        for _start, activity in sorted(
            zip(starts, activities),
            key=lambda pair: pair[0],
        )
    ], True


def _plan_legs(
    row: Mapping[str, Any],
    session_id: str,
    reasons: list[str],
) -> list[dict[str, Any]]:
    raw_legs = row.get("legs")
    if not isinstance(raw_legs, list):
        if str(row.get("kind") or "") == "composite":
            reasons.append("missing_planned_legs")
        return []
    projected: list[dict[str, Any]] = []
    seen_indexes: set[int] = set()
    for raw in raw_legs:
        if not isinstance(raw, Mapping):
            reasons.append("invalid_planned_leg")
            continue
        index = _integer(raw.get("leg_index"))
        if index is None or index <= 0 or index in seen_indexes:
            reasons.append("invalid_planned_leg_identity")
            continue
        seen_indexes.add(index)
        duration = _number(raw.get("duration_minutes"))
        load = _number(raw.get("target_tss"))
        projected.append(
            {
                "leg_id": str(raw.get("leg_id") or f"{session_id}:{index}"),
                "leg_index": index,
                "sport": str(raw.get("sport") or ""),
                "duration_minutes": duration,
                "load_tss": load,
            }
        )
    return sorted(projected, key=lambda leg: leg["leg_index"])


def _fact_legs(
    row: Mapping[str, Any],
    plan_legs: Sequence[Mapping[str, Any]],
    reasons: list[str],
) -> tuple[list[dict[str, Any]], bool]:
    if str(row.get("kind") or "") != "composite":
        return [], True
    activities, ordered = _ordered_activities(row.get("actual_activities"))
    if activities and not ordered:
        reasons.append("actual_leg_order_unproven")
    projected: list[dict[str, Any]] = []
    complete_cardinality = len(activities) == len(plan_legs)
    for position, activity in enumerate(activities):
        activity_sport = str(activity.get("sport") or "")
        planned: Mapping[str, Any] | None = None
        if ordered and complete_cardinality and position < len(plan_legs):
            # Equal cardinality makes position the evidence. A sport mismatch
            # is a structural deviation, not a reason to erase the planned leg.
            planned = plan_legs[position]
        else:
            sport_candidates = [
                leg
                for leg in plan_legs
                if str(leg.get("sport") or "") == activity_sport
            ]
            if len(sport_candidates) == 1:
                planned = sport_candidates[0]
            else:
                reasons.append("actual_leg_mapping_unproven")
        projected.append(
            {
                "planned_leg_id": planned.get("leg_id") if planned else None,
                "leg_index": planned.get("leg_index") if planned else None,
                "activity_id": _activity_id(activity),
                "sport": activity_sport,
                "duration_minutes": _number(activity.get("duration_minutes")),
                "load_tss": _number(activity.get("tss")),
            }
        )
    return projected, ordered


def _projection_status(
    row: Mapping[str, Any],
    *,
    plan_leg_count: int,
    fact_leg_count: int,
    critical_gap: bool,
) -> str:
    if critical_gap:
        return "data_gap"
    if plan_leg_count > 1 and 0 < fact_leg_count < plan_leg_count:
        return "partial"
    match_status = str(row.get("match_status") or "")
    if match_status == "matched":
        return "matched"
    if match_status == "ambiguous":
        return "needs_confirmation"
    if match_status == "unmatched":
        return "unmatched"
    return "data_gap"


def _confidence_status(row: Mapping[str, Any], projection_status: str) -> str:
    method = str(row.get("match_method") or "")
    if method in {"user_confirmed", "admin_resolve", "user_unmatched"}:
        return "confirmed"
    if projection_status == "partial":
        return "partial_evidence"
    if projection_status == "needs_confirmation":
        return "needs_confirmation"
    if projection_status == "matched":
        return "computed"
    return "data_gap"


def _day_load(
    reconciliation: Mapping[str, Any],
    row: Mapping[str, Any],
) -> dict[str, float | None]:
    session_date = str(row.get("date") or "")[:10]
    target_activities = _activity_map(row.get("actual_activities"))
    target_ids = set(target_activities)

    other_activities: dict[str, dict[str, Any]] = {}
    for raw_other in reconciliation.get("rows") or []:
        if not isinstance(raw_other, Mapping) or raw_other is row:
            continue
        if str(raw_other.get("session_id") or "") == str(row.get("session_id") or ""):
            continue
        if str(raw_other.get("date") or "")[:10] != session_date:
            continue
        for identity, activity in _activity_map(raw_other.get("actual_activities")).items():
            if identity not in target_ids:
                other_activities.setdefault(identity, activity)

    assigned_ids = target_ids | set(other_activities)
    unplanned: dict[str, dict[str, Any]] = {}
    for identity, activity in _activity_map(
        reconciliation.get("unplanned_activities")
    ).items():
        if str(activity.get("date") or "")[:10] != session_date:
            continue
        if identity not in assigned_ids:
            unplanned.setdefault(identity, activity)

    matched = _number(row.get("actual_total_tss"))
    if matched is None:
        matched = _sum_activity_tss(target_activities)
    other_matched = _sum_activity_tss(other_activities)
    additional = _sum_activity_tss(unplanned)
    return {
        "planned_tss": _number(row.get("tss")),
        "matched_tss": matched,
        "other_matched_tss": other_matched,
        "additional_unmatched_tss": additional,
        "day_total_tss": round(matched + other_matched + additional, 1),
    }


def build_session_projection(
    reconciliation: Mapping[str, Any],
    *,
    session_id: str,
    match_revision: Mapping[str, Any] | None = None,
    feedback: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Compose one parent-session DTO from canonical local evidence."""
    target = str(session_id or "").strip()
    row = next(
        (
            raw
            for raw in reconciliation.get("rows") or []
            if isinstance(raw, Mapping)
            and str(raw.get("session_id") or "").strip() == target
        ),
        None,
    )
    if row is None:
        raise SessionProjectionNotFoundError(target)

    reasons: list[str] = []
    planned_duration = _number(row.get("duration_minutes"))
    if planned_duration is None:
        reasons.append("invalid_planned_duration")
    planned_load = _number(row.get("tss"))
    if planned_load is None:
        reasons.append("invalid_planned_load")
    legs = _plan_legs(row, target, reasons)
    fact_legs, _fact_ordered = _fact_legs(row, legs, reasons)
    critical_gap = any(
        reason
        in {
            "invalid_planned_duration",
            "invalid_planned_load",
            "invalid_planned_leg",
            "invalid_planned_leg_identity",
            "missing_planned_legs",
        }
        for reason in reasons
    )
    status = _projection_status(
        row,
        plan_leg_count=len(legs),
        fact_leg_count=len(fact_legs),
        critical_gap=critical_gap,
    )
    if status == "partial" and "missing_planned_leg" not in reasons:
        reasons.append("missing_planned_leg")
    if status == "needs_confirmation" and "ambiguous_match" not in reasons:
        reasons.append("ambiguous_match")

    actual_duration = _number(row.get("actual_duration_minutes"))
    actual_load = _number(row.get("actual_total_tss"))
    duration_delta = (
        round(actual_duration - planned_duration, 1)
        if actual_duration is not None and planned_duration is not None
        else None
    )
    load_delta = (
        round(actual_load - planned_load, 1)
        if actual_load is not None and planned_load is not None
        else None
    )
    composite = (
        row.get("composite_execution")
        if isinstance(row.get("composite_execution"), Mapping)
        else {}
    )
    actual_transition = _number(composite.get("actual_transition_minutes"))
    transition_delta = _signed_number(
        composite.get("transition_delta_minutes")
    )
    structure_match = composite.get("structure_match")
    if status == "partial":
        structure_match = None
        actual_transition = None
        transition_delta = None

    if status == "needs_confirmation":
        cause = {
            "status": "needs_confirmation",
            "code": "ambiguous_match",
            "evidence_refs": [],
        }
    else:
        cause = {
            "status": "unknown",
            "code": "no_explicit_cause_evidence",
            "evidence_refs": [],
        }

    if status == "partial":
        completion_status = "incomplete"
    elif str(row.get("match_status") or "") == "matched":
        completion_status = "complete"
    elif status == "needs_confirmation":
        completion_status = "needs_confirmation"
    else:
        completion_status = "not_observed"

    quality_reasons = list(dict.fromkeys(sorted(reasons)))
    return {
        "schema_version": SESSION_PROJECTION_SCHEMA_VERSION,
        "session_id": target,
        "projection_status": status,
        "evidence_revision": {
            "planning_checkpoint_id": reconciliation.get("base_checkpoint_id"),
            "match_revision_id": (match_revision or {}).get("id"),
            "match_revision": (match_revision or {}).get("revision"),
            "feedback_revision_id": (feedback or {}).get("id"),
            "feedback_revision": (feedback or {}).get("revision"),
            "reconciliation_rule_version": reconciliation.get("rule_version"),
            "as_of": reconciliation.get("as_of"),
            "provider_status": (reconciliation.get("provider") or {}).get("status"),
        },
        "plan": {
            "date": str(row.get("date") or "")[:10],
            "sport": str(row.get("sport") or ""),
            "role": str(row.get("role") or ""),
            "name": str(row.get("name") or ""),
            "duration_minutes": planned_duration,
            "load_tss": planned_load,
            "legs": legs,
            "transition": {
                "planned_minutes": _number(row.get("transition_minutes")),
            },
        },
        "fact": {
            "completion_status": completion_status,
            "actual_activity_ids": list(row.get("actual_activity_ids") or []),
            "candidate_activity_ids": [
                _activity_id(activity)
                for activity in row.get("candidate_activities") or []
                if isinstance(activity, Mapping) and _activity_id(activity)
            ],
            "duration_minutes": actual_duration,
            "load_tss": actual_load,
            "legs": fact_legs,
            "transition": {"actual_minutes": actual_transition},
        },
        "deviation": {
            "adherence": str(row.get("adherence") or "unknown"),
            "duration_delta_minutes": duration_delta,
            "load_delta_tss": load_delta,
            "structure_match": structure_match,
            "transition_delta_minutes": transition_delta,
        },
        "cause": cause,
        "confidence": {
            "status": _confidence_status(row, status),
            "score": _score(row.get("confidence")),
            "match_status": str(row.get("match_status") or ""),
            "match_method": str(row.get("match_method") or ""),
            "evidence": [str(item) for item in row.get("evidence") or []],
        },
        "data_quality": {
            "status": "data_gap" if quality_reasons else "sufficient",
            "reasons": quality_reasons,
        },
        "load": _day_load(reconciliation, row),
    }


__all__ = [
    "SESSION_PROJECTION_SCHEMA_VERSION",
    "SessionProjectionNotFoundError",
    "build_session_projection",
]
