"""Headless shadow orchestration for session-quality forecasts (Issue D)."""
from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timezone
from hashlib import sha256
import json
from typing import Any, Mapping

from api.readiness_snapshot import build_readiness_snapshot
from data.database import Database
from models.planning_checkpoints import restore_goal_plan_from_checkpoint
from models.session_quality_forecast import (
    ACTUAL_SESSION_ROLES,
    RULE_VERSION,
    build_session_quality_forecast,
)
from utils.product_semantics import normalize_sport_key


TARGET_ROLES = {"quality", "long"}
# Backward-compatible module export; the canonical definition lives in models.
ACTUAL_ROLES = ACTUAL_SESSION_ROLES
FORECAST_HORIZON_DAYS = 7
def _iso_day(value: Any) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value or "")[:10]


def _target_session(goal_plan: Mapping[str, Any], today: date) -> dict[str, Any] | None:
    daily_plan = list(goal_plan.get("daily_plan") or [])
    templates = list(goal_plan.get("session_templates") or [])
    candidates: list[dict[str, Any]] = []
    for index, raw in enumerate(daily_plan):
        if not isinstance(raw, (list, tuple)) or len(raw) < 2:
            continue
        target_date = _iso_day(raw[0])
        try:
            days_until = (date.fromisoformat(target_date) - today).days
        except ValueError:
            continue
        if not 0 <= days_until < FORECAST_HORIZON_DAYS:
            continue
        template = (
            templates[index]
            if index < len(templates) and isinstance(templates[index], Mapping)
            else {}
        )
        role = str(template.get("session_role") or "").strip().lower()
        if role not in TARGET_ROLES:
            continue
        tss = float(raw[1] or 0.0)
        if tss <= 0:
            continue
        sport = normalize_sport_key(template.get("sport"))
        sessions = [item for item in list(template.get("sessions") or []) if isinstance(item, Mapping)]
        primary_session = sessions[0] if len(sessions) == 1 else {}
        candidates.append(
            {
                "date": target_date,
                "days_until": days_until,
                "index": index,
                "role": role,
                "sport": sport,
                "tss": round(tss, 1),
                "duration_minutes": int(template.get("duration_minutes") or 0) or None,
                "name": str(template.get("session_focus") or template.get("export_name") or "Сессия"),
                "phase": str(template.get("phase") or ""),
                "session_id": str(
                    template.get("session_id") or primary_session.get("session_id") or ""
                ).strip()
                or None,
            }
        )
    return min(candidates, key=lambda item: (item["days_until"], item["index"])) if candidates else None


def _fingerprint(inputs: Mapping[str, Any]) -> str:
    canonical = json.dumps(inputs, ensure_ascii=False, sort_keys=True, default=str)
    return sha256(canonical.encode("utf-8")).hexdigest()


def _utc(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _orchestration_time(value: datetime | None) -> datetime:
    current = value or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc)


def _semantic_number(value: Any, *, places: int = 3) -> float | None:
    try:
        # Keep enough precision that a real formula input change cannot be
        # hidden by the fingerprint normalizer; int/float spelling still
        # converges because both are represented as one JSON float.
        return round(float(value), max(places, 9)) if value is not None else None
    except (TypeError, ValueError):
        return None


def _semantic_fingerprint_payload(
    *,
    checkpoint_id: int,
    target_key: str,
    session: Mapping[str, Any],
    readiness: Mapping[str, Any],
    forecast: Mapping[str, Any],
) -> dict[str, Any]:
    """Return only stable values that can change the v1 forecast.

    The complete readiness/report snapshot remains in ``inputs`` for
    provenance.  This allow-list is deliberately separate so observation
    timestamps and other capture metadata cannot create a new revision.
    """
    demand = forecast.get("demand")
    demand = demand if isinstance(demand, Mapping) else {}
    return {
        "rule_version": RULE_VERSION,
        "target": {
            "plan_checkpoint_id": int(checkpoint_id),
            "target_key": str(target_key),
            "target_date": str(session.get("date") or "")[:10],
            "plan_session_index": int(session.get("index") or 0),
            "session_id": str(session.get("session_id") or "").strip() or None,
        },
        "readiness": {
            "score": _semantic_number(readiness.get("score")),
            "confidence": _semantic_number(readiness.get("confidence")),
            "stale": bool(readiness.get("stale")),
        },
        "planned_session": {
            "role": str(session.get("role") or "").strip().lower(),
            "tss": _semantic_number(session.get("tss")) or 0.0,
            "duration_minutes": _semantic_number(session.get("duration_minutes")),
        },
        "forecast": {
            "prediction_pct": int(forecast.get("prediction_pct") or 0),
            "prediction_band": str(forecast.get("prediction_band") or ""),
            "base_probability": _semantic_number(forecast.get("base_probability")),
            "demand_adjustment": _semantic_number(forecast.get("demand_adjustment")),
            "demand": {
                "role": str(demand.get("role") or "").strip().lower(),
                "planned_tss": _semantic_number(demand.get("planned_tss")) or 0.0,
                "planned_duration_minutes": _semantic_number(
                    demand.get("planned_duration_minutes")
                ),
                "density_tss_per_hour": _semantic_number(
                    demand.get("density_tss_per_hour")
                ),
            },
        },
    }


def _forecast_lifecycle_reason(
    db: Database,
    session: Mapping[str, Any],
    *,
    now_utc: datetime,
) -> str | None:
    """Return a terminal lifecycle reason proved by local immutable evidence."""
    session_id = str(session.get("session_id") or "").strip()
    if not session_id:
        return None

    try:
        feedback = db.get_latest_session_feedback(session_id)
    except Exception:
        feedback = None
    # Any active feedback revision closes the pre-start forecast lifecycle.
    # ``unknown`` is still an explicit athlete response and the feedback prompt
    # itself treats it as submitted; generating another pre-start belief after
    # that response would recreate the orphan-pending failure from #517.
    if (
        isinstance(feedback, Mapping)
        and str(feedback.get("status") or "").strip().lower() == "active"
    ):
        return "terminal_feedback_exists"

    try:
        match = db.get_latest_plan_actual_match_for_session(session_id)
    except Exception:
        match = None
    if (
        not isinstance(match, Mapping)
        or str(match.get("match_status") or "").strip().lower() != "matched"
    ):
        return None
    activity_ids = [
        str(value).strip()
        for value in match.get("actual_activity_ids") or []
        if str(value or "").strip()
    ]
    if not activity_ids:
        return None
    try:
        activities = db.get_activities_by_ids(activity_ids)
    except Exception:
        return None
    if any(
        (started := _utc(activity.get("started_at_utc"))) is not None
        and started <= now_utc
        for activity in activities
        if isinstance(activity, Mapping)
    ):
        return "session_started"
    return None


def record_shadow_session_quality_forecast(
    db: Database,
    *,
    report: Mapping[str, Any] | None = None,
    checkpoint: Mapping[str, Any] | None = None,
    readiness_snapshot: Mapping[str, Any] | None = None,
    recovery_decision_id: int | None = None,
    today: date | None = None,
    now_utc: datetime | None = None,
) -> dict[str, Any]:
    """Record one idempotent revision without feeding it into product decisions."""
    anchor = today or datetime.now().date()
    checkpoint = checkpoint or db.get_latest_planning_checkpoint()
    if not isinstance(checkpoint, Mapping) or not checkpoint.get("id"):
        return {"prediction": None, "reason": "no_active_plan"}
    goal_plan = restore_goal_plan_from_checkpoint(checkpoint)
    if not isinstance(goal_plan, Mapping):
        return {"prediction": None, "reason": "no_active_plan"}
    session = _target_session(goal_plan, anchor)
    if session is None:
        return {"prediction": None, "reason": "no_key_session_in_horizon"}

    lifecycle_reason = _forecast_lifecycle_reason(
        db,
        session,
        now_utc=_orchestration_time(now_utc),
    )
    if lifecycle_reason:
        return {"prediction": None, "reason": lifecycle_reason}

    readiness = dict(readiness_snapshot or {})
    if not readiness:
        readiness = build_readiness_snapshot(db)
    if report and isinstance(report.get("readiness"), Mapping):
        # A canonical snapshot remains primary; report provenance is retained separately.
        report_readiness = dict(report.get("readiness") or {})
    else:
        report_readiness = {}
    forecast = build_session_quality_forecast(readiness, session)
    if forecast is None:
        return {"prediction": None, "reason": "readiness_data_gap"}

    checkpoint_id = int(checkpoint["id"])
    target_key = f"{checkpoint_id}:{session['date']}:{session['index']}:{RULE_VERSION}"
    inputs = {
        "rule_version": RULE_VERSION,
        "readiness_source": "canonical_snapshot",
        "readiness": readiness,
        "gate_readiness": report_readiness,
        "gate_as_of": str((report or {}).get("as_of") or "")[:10] or None,
        "plan_checkpoint_id": checkpoint_id,
        "planned_session": session,
    }
    fingerprint_payload = _semantic_fingerprint_payload(
        checkpoint_id=checkpoint_id,
        target_key=target_key,
        session=session,
        readiness=readiness,
        forecast=forecast,
    )
    inputs["semantic_fingerprint_basis"] = fingerprint_payload
    saved = db.save_session_quality_prediction(
        fingerprint=_fingerprint(fingerprint_payload),
        target_key=target_key,
        rule_version=RULE_VERSION,
        target_date=session["date"],
        plan_checkpoint_id=checkpoint_id,
        plan_session_index=session["index"],
        planned_session=session,
        forecast=forecast,
        inputs=inputs,
        evidence=list(forecast.get("evidence") or []),
        recovery_decision_id=recovery_decision_id,
    )
    return {
        "prediction": saved["prediction"],
        "created": saved["created"],
        "reason": None,
    }


def resolve_session_quality_prediction(
    db: Database,
    prediction_id: int,
    *,
    activity_ids: list[str],
    actual_role: str | None,
    quality_rating_1_5: int | None,
    note: str | None = None,
) -> dict[str, Any]:
    """Compatibility facade; feedback is the only source of new resolution facts."""
    normalized_role = str(actual_role or "").strip().lower()
    if normalized_role and normalized_role not in ACTUAL_SESSION_ROLES:
        raise ValueError(f"actual_role must be one of {sorted(ACTUAL_SESSION_ROLES)}")
    from api.session_feedback import resolve_prediction_via_feedback

    return resolve_prediction_via_feedback(
        db,
        prediction_id,
        activity_ids=activity_ids,
        actual_role=normalized_role or None,
        quality_rating_1_5=quality_rating_1_5,
        note=note,
    )


def summarize_session_quality_predictions(rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    scored = [row for row in rows if row.get("status") == "scored"]
    unscored = [row for row in rows if row.get("status") == "unscored"]
    briers = [float(row["brier_score"]) for row in scored if row.get("brier_score") is not None]
    low = [row for row in scored if float(row.get("prediction_pct") or 0) < 60]
    low_failures = sum(1 for row in low if row.get("quality_outcome") == "failure")
    return {
        "total": len(rows),
        "pending": sum(1 for row in rows if row.get("status") == "pending"),
        "scored": len(scored),
        "unscored": len(unscored),
        "unscored_reasons": dict(Counter(str(row.get("unscored_reason") or "unknown") for row in unscored)),
        "mean_brier_score": round(sum(briers) / len(briers), 4) if briers else None,
        "low_forecast_count": len(low),
        "low_forecast_hit_rate": round(low_failures / len(low), 4) if low else None,
        "rule_versions": dict(Counter(str(row.get("rule_version") or "unknown") for row in scored)),
    }


__all__ = [
    "record_shadow_session_quality_forecast",
    "resolve_session_quality_prediction",
    "summarize_session_quality_predictions",
]
