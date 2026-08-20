"""Pure Intervals.icu workout-delivery payload rules."""
from __future__ import annotations

from datetime import datetime, timedelta
import re
from typing import Any, Mapping, Sequence

from models.fit_export import build_steps_for_sport
from models.session_identity import ensure_session_identities
from models.workout_catalog import (
    catalog_definitions,
    materialize_workout,
    require_executable_planned_session,
)


AI_TRAINER_EXTERNAL_ID_PREFIX = "ai_trainer:"
_SPORT_TYPES = {"bike": "Ride", "run": "Run", "swim": "Swim"}
_LEG_GAP_SECONDS = 5 * 60
_PACE_TARGET_RE = re.compile(
    r"(?P<first>\d+:\d{2})(?P<first_unit>/(?:km|100m))?"
    r"-(?P<second>\d+:\d{2})(?P<unit>/(?:km|100m))\s+Pace$"
)


def provider_event_is_owned(event: Mapping[str, Any]) -> bool:
    return str(event.get("external_id") or "").startswith(
        AI_TRAINER_EXTERNAL_ID_PREFIX
    )


def provider_event_is_executable(event: Mapping[str, Any]) -> bool:
    workout_doc = event.get("workout_doc")
    return isinstance(workout_doc, Mapping) and bool(workout_doc.get("steps"))


def _pace_seconds(value: str) -> float:
    minutes, seconds = value.split(":", 1)
    return float(minutes) * 60.0 + float(seconds)


def _required_pace_targets(
    desired_event: Mapping[str, Any],
) -> list[tuple[int, float, float, str]]:
    lines = [
        line.strip()
        for line in str(desired_event.get("description") or "").splitlines()
        if line.strip().startswith("- ")
    ]
    required: list[tuple[int, float, float, str]] = []
    for index, line in enumerate(lines):
        match = _PACE_TARGET_RE.search(line)
        if match is None:
            continue
        first_unit = match.group("first_unit")
        unit = match.group("unit")
        if first_unit is not None and first_unit != unit:
            continue
        required.append(
            (
                index,
                _pace_seconds(match.group("first")),
                _pace_seconds(match.group("second")),
                "secs/km" if unit == "/km" else "secs/100m",
            )
        )
    return required


def provider_event_requires_pace_targets(event: Mapping[str, Any]) -> bool:
    """Return whether the provider payload declares structured pace targets."""
    return bool(_required_pace_targets(event))


def provider_event_preserves_required_targets(
    desired_event: Mapping[str, Any],
    provider_event: Mapping[str, Any],
) -> bool:
    """Validate provider read-back against every serialized pace prescription."""
    required = _required_pace_targets(desired_event)
    if not required:
        return True
    workout_doc = provider_event.get("workout_doc")
    if not isinstance(workout_doc, Mapping):
        return False
    steps = workout_doc.get("steps")
    if not isinstance(steps, Sequence) or isinstance(steps, (str, bytes, bytearray)):
        return False
    description_steps = [
        line
        for line in str(desired_event.get("description") or "").splitlines()
        if line.strip().startswith("- ")
    ]
    if len(steps) != len(description_steps):
        return False
    for index, expected_first, expected_second, expected_unit in required:
        step = steps[index]
        if not isinstance(step, Mapping):
            return False
        pace = step.get("pace")
        if not isinstance(pace, Mapping):
            return False
        if str(pace.get("units") or "").lower() != expected_unit:
            return False
        raw_start = pace.get("start", pace.get("value"))
        raw_end = pace.get("end", pace.get("value"))
        try:
            actual = sorted((float(raw_start), float(raw_end)))
        except (TypeError, ValueError):
            return False
        expected = sorted((expected_first, expected_second))
        if any(abs(left - right) > 1.0 for left, right in zip(actual, expected)):
            return False
    return True


def _step_seconds(step: Mapping[str, Any]) -> int:
    explicit = step.get("duration_seconds")
    if explicit is not None:
        return max(1, int(round(float(explicit))))
    return max(300, int(round(float(step.get("tss") or 0.0) * 60)))


def _duration_text(seconds: int) -> str:
    return f"{seconds // 60}m" if seconds % 60 == 0 else f"{seconds}s"


def _clock_text(seconds: float) -> str:
    value = max(0, int(round(seconds)))
    return f"{value // 60}:{value % 60:02d}"


def _target_text(target: Any) -> str:
    if isinstance(target, Mapping):
        target_type = str(target.get("type") or "open")
        if target_type == "power":
            return f"{float(target.get('low') or 0):g}-{float(target.get('high') or 0):g}w"
        if target_type == "heart_rate":
            relative_low = target.get("relative_low")
            relative_high = target.get("relative_high")
            if (
                str(target.get("reference") or "").lower() == "lthr"
                and relative_low is not None
                and relative_high is not None
            ):
                return (
                    f"{float(relative_low) * 100:g}-"
                    f"{float(relative_high) * 100:g}% LTHR"
                )
            return f"{float(target.get('low') or 0):g}-{float(target.get('high') or 0):g}bpm"
        if target_type == "pace":
            fast = float(target.get("fast") or target.get("low") or 0)
            slow = float(target.get("slow") or target.get("high") or fast)
            unit = "/100m" if str(target.get("unit") or "").endswith("100m") else "/km"
            if fast > 0:
                if unit == "/100m":
                    return (
                        f"{_clock_text(fast)}{unit}-"
                        f"{_clock_text(slow)}{unit} Pace"
                    )
                return f"{_clock_text(fast)}-{_clock_text(slow)}{unit} Pace"
        if target_type in {"relative", "relative_rpe", "rpe"}:
            low = target.get("low") or target.get("value") or 3
            high = target.get("high")
            return f"RPE {low}-{high}" if high is not None else f"RPE {low}"
        return "RPE 3"

    token = str(target or "").strip().lower()
    zones = {
        "power_zone_1": "50-60%",
        "power_zone_1_2": "55-75%",
        "power_zone_2_3": "70-90%",
        "power_zone_4": "95-105%",
        "hr_zone_1": "60-70% HR",
        "hr_zone_1_2": "65-80% HR",
        "hr_zone_2_3": "75-90% HR",
        "hr_zone_4": "90-100% HR",
        "pace_easy": "RPE 3",
        "pace_mod": "RPE 5",
        "pace_threshold": "RPE 8",
    }
    return zones.get(token, "RPE 3")


def _normalized_steps(steps: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            **dict(step),
            "duration_seconds": _step_seconds(step),
        }
        for step in steps
    ]


def build_intervals_workout_description(
    steps: Sequence[Mapping[str, Any]],
    *,
    title: str,
) -> str:
    """Serialize catalog steps using Intervals.icu native workout text."""
    normalized = _normalized_steps(steps)
    lines = [str(title).strip() or "AI Trainer workout"]
    for index, step in enumerate(normalized, start=1):
        name = str(step.get("name") or f"Step {index}").strip()
        lines.append(
            f"- {name} {_duration_text(int(step['duration_seconds']))} "
            f"{_target_text(step.get('target'))}"
        )
    return "\n".join(lines)


def _event_payload(
    *,
    session_date: str,
    session_id: str,
    sport: str,
    name: str,
    tss: float,
    steps: Sequence[Mapping[str, Any]],
    start_at: datetime,
    leg_index: int | None,
) -> dict[str, Any]:
    normalized = _normalized_steps(steps)
    external_id = f"{AI_TRAINER_EXTERNAL_ID_PREFIX}{session_id}"
    if leg_index is not None:
        external_id += f":leg:{leg_index}"
    return {
        "external_id": external_id,
        "start_date_local": start_at.strftime("%Y-%m-%dT%H:%M:%S"),
        "category": "WORKOUT",
        "name": name,
        "description": build_intervals_workout_description(normalized, title=name),
        "type": _SPORT_TYPES.get(sport, "Workout"),
        "icu_training_load": int(round(float(tss or 0.0))),
        "moving_time": sum(int(step["duration_seconds"]) for step in normalized),
    }


def _delivery_session_id(session: Mapping[str, Any]) -> str:
    """Return the provider identity, distinct from plan reconciliation id."""
    parameters = dict(session.get("parameter_snapshot") or {})
    rebalance_lineage = None
    if str(parameters.get("requested_tss_source") or "") == "bike_tss_rebalance":
        rebalance_lineage = session.get("replaces_session_id")
    return str(
        session.get("delivery_session_id")
        or rebalance_lineage
        or session.get("session_id")
        or ""
    ).strip()


def _delivery_steps(
    session: Mapping[str, Any],
    *,
    sport: str,
    session_tss: float,
) -> list[dict[str, Any]]:
    """Resolve executable steps, repairing pre-fix rebalance checkpoints."""
    steps = [dict(step or {}) for step in list(session.get("materialized_steps") or [])]
    parameters = dict(session.get("parameter_snapshot") or {})
    if sport != "bike" or str(parameters.get("requested_tss_source") or "") != "bike_tss_rebalance":
        return steps
    try:
        expected_seconds = int(round(float(session.get("duration_minutes") or 0) * 60))
        actual_seconds = sum(int(round(float(step.get("duration_seconds") or 0))) for step in steps)
        duration_minutes = int(round(float(session.get("duration_minutes") or 0)))
        requested_tss = float(parameters.get("requested_tss") or session_tss)
        ftp = float((session.get("target_provenance") or {}).get("value"))
    except (TypeError, ValueError):
        return steps
    if expected_seconds <= 0 or actual_seconds == expected_seconds or duration_minutes <= 0 or ftp <= 0:
        return steps
    template_key = str(session.get("template_key") or "")
    definition = next(
        (item for item in catalog_definitions() if item.template_key == template_key),
        None,
    )
    if definition is None:
        return steps
    repaired = materialize_workout(
        definition,
        {"duration_minutes": duration_minutes, "target_tss": requested_tss},
        {"ftp": ftp},
    )
    if repaired.get("materialization_status") != "materialized":
        return steps
    return [dict(step or {}) for step in list(repaired.get("steps") or [])]


def build_delivery_events(
    goal_plan: Mapping[str, Any],
    dates: Sequence[str],
) -> list[dict[str, Any]]:
    """Build deterministic owned provider events for the selected plan dates."""
    selected_dates = {datetime.fromisoformat(str(value)[:10]).date().isoformat() for value in dates}
    plan = ensure_session_identities(dict(goal_plan))
    daily_plan = list(plan.get("daily_plan") or [])
    templates = list(plan.get("session_templates") or [])
    events: list[dict[str, Any]] = []

    for index, item in enumerate(daily_plan):
        if not isinstance(item, (list, tuple)) or len(item) < 3:
            continue
        dt, total_tss, parts = item
        day = (dt.date() if hasattr(dt, "date") else datetime.fromisoformat(str(dt)).date()).isoformat()
        if day not in selected_dates or float(total_tss or 0.0) <= 0:
            continue
        template = dict(templates[index]) if index < len(templates) else {}
        template_date = str(template.get("date") or "")[:10]
        if template_date != day:
            raise ValueError(
                f"planned session {day} template date mismatch: "
                f"{template_date or 'missing'}"
            )
        # Issue #205 milestone 2.4: one provider event per executable leaf —
        # each single session, and each brick leg. Sessions on a day are laid out
        # sequentially so a multi-session day (milestone 3) gets non-overlapping
        # start times. `ensure_session_identities` above guarantees `sessions`;
        # the None branch is defensive only.
        sessions = template.get("sessions")
        if sessions is None:
            sessions = [template]
        cursor = datetime.fromisoformat(day).replace(hour=7)
        for session in sessions:
            session_id = str(session.get("session_id") or "").strip()
            if not session_id:
                raise ValueError(f"planned session {day} has no stable session_id")
            delivery_session_id = _delivery_session_id(session)
            if not delivery_session_id:
                raise ValueError(f"planned session {day} has no delivery identity")
            require_executable_planned_session(session)
            phase = str(session.get("phase") or template.get("phase") or "")
            role = str(session.get("session_role") or "easy")
            if str(session.get("kind") or "single") == "composite":
                for position, raw_leg in enumerate(session.get("legs") or [], start=1):
                    leg = dict(raw_leg)
                    leg_index = int(leg.get("leg_index") or position)
                    sport = str(leg.get("sport") or "bike")
                    leg_tss = float(leg.get("target_tss") or (parts or {}).get(sport) or 0.0)
                    steps = list(leg.get("materialized_steps") or [])
                    if not steps:
                        steps = build_steps_for_sport(leg_tss, sport, role, phase)
                    name = str(
                        leg.get("template_name")
                        or session.get("export_name")
                        or template.get("export_name")
                        or "Brick leg"
                    )
                    payload = _event_payload(
                        session_date=day,
                        session_id=delivery_session_id,
                        sport=sport,
                        name=f"{name} · leg {leg_index}",
                        tss=leg_tss,
                        steps=steps,
                        start_at=cursor,
                        leg_index=leg_index,
                    )
                    events.append(payload)
                    cursor += timedelta(seconds=int(payload["moving_time"]) + _LEG_GAP_SECONDS)
                continue

            sport = str(session.get("sport") or "").strip()
            if not sport:
                sport = max(
                    ("bike", "run", "swim"),
                    key=lambda key: float((parts or {}).get(key) or 0.0),
                )
            session_tss = (
                float(session.get("total_tss"))
                if session.get("total_tss") is not None
                else float(total_tss or 0.0)
            )
            steps = _delivery_steps(session, sport=sport, session_tss=session_tss)
            if not steps:
                steps = build_steps_for_sport(session_tss, sport, role, phase)
            payload = _event_payload(
                session_date=day,
                session_id=delivery_session_id,
                sport=sport,
                name=str(
                    session.get("export_name")
                    or session.get("template_name")
                    or template.get("export_name")
                    or "AI Trainer workout"
                ),
                tss=session_tss,
                steps=steps,
                start_at=cursor,
                leg_index=None,
            )
            events.append(payload)
            cursor += timedelta(seconds=int(payload["moving_time"]) + _LEG_GAP_SECONDS)
    return events


__all__ = [
    "AI_TRAINER_EXTERNAL_ID_PREFIX",
    "build_delivery_events",
    "build_intervals_workout_description",
    "provider_event_is_executable",
    "provider_event_is_owned",
    "provider_event_preserves_required_targets",
    "provider_event_requires_pace_targets",
]
