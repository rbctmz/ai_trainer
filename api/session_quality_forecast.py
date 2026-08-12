"""Headless shadow orchestration for session-quality forecasts (Issue D)."""
from __future__ import annotations

from collections import Counter
from datetime import date, datetime
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
