"""Pure Intervals.icu workout-delivery payload rules."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Mapping, Sequence

from models.fit_export import build_steps_for_sport
from models.session_identity import ensure_session_identities


AI_TRAINER_EXTERNAL_ID_PREFIX = "ai_trainer:"
_SPORT_TYPES = {"bike": "Ride", "run": "Run", "swim": "Swim"}
_LEG_GAP_SECONDS = 5 * 60


def provider_event_is_owned(event: Mapping[str, Any]) -> bool:
    return str(event.get("external_id") or "").startswith(
        AI_TRAINER_EXTERNAL_ID_PREFIX
    )


def provider_event_is_executable(event: Mapping[str, Any]) -> bool:
    workout_doc = event.get("workout_doc")
    return isinstance(workout_doc, Mapping) and bool(workout_doc.get("steps"))


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
                return f"{_clock_text(fast)}-{_clock_text(slow)}{unit}"
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
                        session_id=session_id,
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
            steps = list(session.get("materialized_steps") or [])
            if not steps:
                steps = build_steps_for_sport(session_tss, sport, role, phase)
            payload = _event_payload(
                session_date=day,
                session_id=session_id,
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
]
