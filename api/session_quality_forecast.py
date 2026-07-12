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
    RULE_VERSION,
    brier_score,
    build_session_quality_forecast,
    classify_plan_adherence,
)
from utils.product_semantics import normalize_sport_key


TARGET_ROLES = {"quality", "long"}
ACTUAL_ROLES = {"off", "recovery", "easy", "quality", "long"}
FORECAST_HORIZON_DAYS = 7


def _iso_day(value: Any) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value or "")[:10]


def _utc(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


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
        template = templates[index] if index < len(templates) and isinstance(templates[index], dict) else {}
        role = str(template.get("session_role") or "").strip().lower()
        if role not in TARGET_ROLES:
            continue
        tss = float(raw[1] or 0.0)
        if tss <= 0:
            continue
        sport = normalize_sport_key(template.get("sport"))
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
            }
        )
    return min(candidates, key=lambda item: (item["days_until"], item["index"])) if candidates else None


def _fingerprint(inputs: Mapping[str, Any]) -> str:
    canonical = json.dumps(inputs, ensure_ascii=False, sort_keys=True, default=str)
    return sha256(canonical.encode("utf-8")).hexdigest()


def record_shadow_session_quality_forecast(
    db: Database,
    *,
    report: Mapping[str, Any] | None = None,
    checkpoint: Mapping[str, Any] | None = None,
    readiness_snapshot: Mapping[str, Any] | None = None,
    recovery_decision_id: int | None = None,
    today: date | None = None,
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
    saved = db.save_session_quality_prediction(
        fingerprint=_fingerprint(inputs),
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


def _actual_snapshot(
    activities: list[Mapping[str, Any]],
    *,
    actual_role: str | None,
    quality_rating_1_5: int | None,
    note: str | None,
) -> dict[str, Any]:
    tss_values = [float(item["tss"]) for item in activities if item.get("tss") is not None]
    duration_values = [
        float(item["duration_minutes"])
        for item in activities
        if item.get("duration_minutes") is not None
    ]
    sports = [normalize_sport_key(item.get("sport")) for item in activities]
    normalized_sports = sorted({sport for sport in sports if sport})
    actual_sport = normalized_sports[0] if len(normalized_sports) == 1 else "mixed" if normalized_sports else ""
    return {
        "actual_role": str(actual_role or "").strip().lower() or None,
        "actual_sport": actual_sport or None,
        "actual_total_tss": round(sum(tss_values), 1) if tss_values else None,
        "actual_duration_minutes": round(sum(duration_values), 1) if duration_values else None,
        "quality_rating_1_5": quality_rating_1_5,
        "note": str(note or "").strip() or None,
        "activities": [
            {
                "activity_id": item.get("activity_id"),
                "date": _iso_day(item.get("date")),
                "started_at_utc": item.get("started_at_utc"),
                "sport": normalize_sport_key(item.get("sport")),
                "duration_minutes": item.get("duration_minutes"),
                "tss": item.get("tss"),
                "training_effect": item.get("training_effect"),
                "anaerobic_effect": item.get("anaerobic_effect"),
            }
            for item in activities
        ],
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
    """Resolve one target group while preserving every immutable revision."""
    prediction = db.get_session_quality_prediction(prediction_id)
    if prediction is None:
        raise LookupError(f"prediction {prediction_id} not found")
    if quality_rating_1_5 is not None and quality_rating_1_5 not in {1, 2, 3, 4, 5}:
        raise ValueError("quality_rating_1_5 must be between 1 and 5")
    normalized_role = str(actual_role or "").strip().lower()
    if normalized_role and normalized_role not in ACTUAL_ROLES:
        raise ValueError(f"actual_role must be one of {sorted(ACTUAL_ROLES)}")
    target_key = prediction["target_key"]
    group = db.get_session_quality_predictions(days=36500, target_key=target_key)
    if not any(row["status"] == "pending" for row in group):
        return {"predictions": group, "summary": summarize_session_quality_predictions(group)}

    requested_ids = [str(value) for value in activity_ids or []]
    activities = db.get_activities_by_ids(requested_ids)
    found_ids = {str(item.get("activity_id")) for item in activities}
    missing_ids = [value for value in requested_ids if value not in found_ids]
    if missing_ids:
        raise LookupError(f"activities not found: {', '.join(missing_ids)}")
    target_date = str(prediction["target_date"])
    if any(_iso_day(item.get("date")) != target_date for item in activities):
        raise ValueError("all activities must belong to the prediction target date")

    actual = _actual_snapshot(
        activities,
        actual_role=normalized_role or None,
        quality_rating_1_5=quality_rating_1_5,
        note=note,
    )
    started_values = [_utc(item.get("started_at_utc")) for item in activities]
    started_values = [value for value in started_values if value is not None]
    session_start = min(started_values) if started_values else None
    planned = prediction["planned_session"]
    adherence = classify_plan_adherence(
        planned,
        {
            "role": actual.get("actual_role"),
            "sport": actual.get("actual_sport"),
            "tss": actual.get("actual_total_tss"),
        },
    )

    pending = [row for row in group if row["status"] == "pending"]
    eligible = [
        row
        for row in pending
        if session_start is not None and (_utc(row["created_at"]) or session_start) < session_start
    ]
    latest_eligible_id = max(
        eligible,
        key=lambda row: (_utc(row["created_at"]) or datetime.min.replace(tzinfo=timezone.utc), row["id"]),
    )["id"] if eligible else None

    resolutions = []
    for row in pending:
        reason = None
        status = "unscored"
        outcome = None
        score = None
        created = _utc(row["created_at"])
        if session_start is None:
            reason = "missing_session_start"
        elif created is None or created >= session_start:
            reason = "post_start_prediction"
        elif row["id"] != latest_eligible_id:
            reason = "superseded"
        elif adherence is None:
            reason = "missing_adherence_evidence"
        elif adherence == "major_deviation":
            reason = "major_deviation"
        elif quality_rating_1_5 is None or quality_rating_1_5 == 3:
            reason = "ambiguous_quality"
        else:
            status = "scored"
            outcome = "success" if quality_rating_1_5 >= 4 else "failure"
            score = brier_score(row["prediction_pct"], quality_rating_1_5)
        resolutions.append(
            {
                "id": row["id"],
                "status": status,
                "plan_adherence": adherence,
                "quality_rating_1_5": quality_rating_1_5,
                "quality_outcome": outcome,
                "actual_activity_ids": requested_ids,
                "actual_snapshot": actual,
                "unscored_reason": reason,
                "brier_score": score,
            }
        )
    rows = db.resolve_session_quality_prediction_group(target_key, resolutions)
    return {"predictions": rows, "summary": summarize_session_quality_predictions(rows)}


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
