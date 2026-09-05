"""Pure post-workout feedback, prompt, and forecast-evaluation rules."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
import json
from typing import Any, Mapping, Sequence

from models.plan_actual_reconciliation import (
    iter_parent_sessions,
    project_composite_execution,
)
from models.session_quality_forecast import brier_score


FEEDBACK_RULE_VERSION = "session_feedback_v1"
EVALUATION_RULE_VERSION = "session_quality_evaluation_v1"

COMPLETION_STATUS_ORDER = (
    "completed",
    "partial",
    "stopped_early",
    "did_not_start",
    "unknown",
)
COMPLETION_STATUSES = set(COMPLETION_STATUS_ORDER)
AUTHORITATIVE_MATCH_METHODS = {
    "user_confirmed",
    "admin_resolve",
    "ai_trainer_external_id",
}
MIN_STABLE_MATCH_CONFIDENCE = 0.75


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


def _iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def _day(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value or "")[:10])
    except ValueError:
        return None


def canonical_fingerprint(value: Mapping[str, Any]) -> str:
    """Return a stable SHA-256 identity for immutable journal input."""
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return sha256(raw.encode("utf-8")).hexdigest()


def derive_session_end_utc(
    activities: Sequence[Mapping[str, Any]],
) -> tuple[str | None, str]:
    """Derive the latest source-backed activity end without guessing local time."""
    ends: list[datetime] = []
    for activity in activities:
        started = _utc(activity.get("started_at_utc"))
        try:
            minutes = float(activity.get("duration_minutes"))
        except (TypeError, ValueError):
            minutes = 0.0
        if started is None or minutes <= 0:
            return None, "missing_source_start_or_duration"
        ends.append(started + timedelta(minutes=minutes))
    if not ends:
        return None, "no_activity_evidence"
    return _iso_utc(max(ends)), "started_at_utc_plus_duration_minutes"


def validate_feedback_values(
    *,
    completion_status: str,
    completion_pct: int | float | None,
    session_rpe_1_10: int | None,
    quality_rating_1_5: int | None,
    require_started_ratings: bool = True,
) -> dict[str, Any]:
    """Validate independent athlete-entered observations without inference."""
    status = str(completion_status or "").strip()
    if status not in COMPLETION_STATUSES:
        raise ValueError(f"completion_status must be one of {sorted(COMPLETION_STATUSES)}")
    pct: float | None = None
    if completion_pct is not None:
        try:
            pct = float(completion_pct)
        except (TypeError, ValueError) as exc:
            raise ValueError("completion_pct must be between 0 and 100") from exc
        if not 0 <= pct <= 100:
            raise ValueError("completion_pct must be between 0 and 100")
    if session_rpe_1_10 is not None and session_rpe_1_10 not in range(1, 11):
        raise ValueError("session_rpe_1_10 must be between 1 and 10")
    if quality_rating_1_5 is not None and quality_rating_1_5 not in range(1, 6):
        raise ValueError("quality_rating_1_5 must be between 1 and 5")
    if require_started_ratings and status in {"completed", "partial", "stopped_early"}:
        if session_rpe_1_10 is None:
            raise ValueError("session_rpe_1_10 is required for a started session")
        if quality_rating_1_5 is None:
            raise ValueError("quality_rating_1_5 is required for a started session")
    return {
        "completion_status": status,
        "completion_pct": pct,
        "session_rpe_1_10": session_rpe_1_10,
        "quality_rating_1_5": quality_rating_1_5,
    }


def _tombstone_still_binding(latest: Mapping[str, Any], row: Mapping[str, Any]) -> bool:
    """A tombstone stays binding only while the current match context still
    equals the one the athlete removed. A later re-match (different activity
    ids or method) must re-open the prompt instead of leaving the session a
    permanent dead end."""
    snapshot = dict(latest.get("match_snapshot") or {})
    tombstone_ids = sorted(
        str(value) for value in (snapshot.get("actual_activity_ids") or [])
    )
    current_ids = sorted(
        str(value) for value in (row.get("actual_activity_ids") or [])
    )
    tombstone_method = str(snapshot.get("match_method") or "").strip()
    current_method = str(row.get("match_method") or "").strip()
    return tombstone_ids == current_ids and tombstone_method == current_method


def build_feedback_prompts(
    rows: Sequence[Mapping[str, Any]],
    *,
    templates: Sequence[Mapping[str, Any]],
    latest_feedback_by_session: Mapping[str, Mapping[str, Any]],
    prompt_events_by_session: Mapping[str, Mapping[str, Any]],
    forecasts: Sequence[Mapping[str, Any]],
    now_utc: datetime,
    as_of: str,
) -> dict[str, Any]:
    """Build prompt states from an existing reconciliation snapshot only."""
    now = now_utc if now_utc.tzinfo else now_utc.replace(tzinfo=timezone.utc)
    now = now.astimezone(timezone.utc)
    session_by_id: dict[str, Mapping[str, Any]] = {
        str(entry["session"].get("session_id")): entry["session"]
        for entry in iter_parent_sessions(templates)
        if entry["session"].get("session_id")
    }
    for item in templates:
        # Pre-#205 legacy templates carry no `sessions[]`; the template IS
        # the session. Only fill gaps `iter_parent_sessions` cannot see —
        # never let this shadow a nested session's own content.
        if not isinstance(item, Mapping) or "sessions" in item:
            continue
        legacy_id = str(item.get("session_id") or "")
        if legacy_id and legacy_id not in session_by_id:
            session_by_id[legacy_id] = item
    forecast_dates = {str(item.get("target_date") or "")[:10] for item in forecasts}
    prompts: list[dict[str, Any]] = []
    for raw in rows:
        row = dict(raw)
        session_id = str(row.get("session_id") or "").strip()
        if not session_id:
            continue
        session = session_by_id.get(session_id, {})
        activities = [
            dict(item)
            for item in row.get("actual_activities") or []
            if isinstance(item, Mapping)
        ]
        ended_at, end_provenance = derive_session_end_utc(activities)
        ended = _utc(ended_at)
        session_day = _day(row.get("date"))
        match_status = str(row.get("match_status") or "unmatched")
        match_method = str(row.get("match_method") or "")
        try:
            confidence = float(row.get("confidence") or 0.0)
        except (TypeError, ValueError):
            confidence = 0.0
        stable_match = match_status == "matched" and (
            match_method in AUTHORITATIVE_MATCH_METHODS
            or confidence >= MIN_STABLE_MATCH_CONFIDENCE
        )

        state = "not_eligible"
        reason = "match_not_stable"
        allowed = list(COMPLETION_STATUS_ORDER)
        has_candidates = bool(row.get("candidate_activities"))
        if match_status == "ambiguous":
            state, reason = "pending_match", "ambiguous_match"
        elif match_status == "unmatched" and has_candidates:
            # e.g. the athlete unmade a match: the day's activities still
            # exist and must be re-attributed before feedback makes sense.
            state, reason = "pending_match", "unmatched_session_has_candidates"
        elif match_status == "unmatched" and not activities:
            if session_day is not None and now.date() > session_day:
                state, reason = "ready", "past_session_without_activity"
                allowed = ["did_not_start", "unknown"]
            else:
                state, reason = "not_eligible", "planned_day_not_elapsed"
        elif stable_match:
            if ended is not None and now < ended:
                state, reason = "not_eligible", "session_in_progress"
            elif ended is None and (session_day is None or now.date() <= session_day):
                state, reason = "not_eligible", "session_end_unknown"
            else:
                state, reason = "ready", "matched_session_complete"

        prompt_identity = {
            "rule_version": FEEDBACK_RULE_VERSION,
            "session_id": session_id,
            "match_status": match_status,
            "match_method": match_method,
            "confidence": confidence,
            "actual_activity_ids": list(row.get("actual_activity_ids") or []),
            "session_end_at_utc": ended_at,
        }
        prompt_fingerprint = canonical_fingerprint(prompt_identity)
        latest = latest_feedback_by_session.get(session_id)
        event = prompt_events_by_session.get(session_id)
        if latest and latest.get("status") == "tombstone":
            if _tombstone_still_binding(latest, row):
                state, reason = "superseded", "latest_feedback_tombstoned"
            # Otherwise the tombstone belongs to an older match context:
            # fall through to the match-state logic so the session can be
            # evaluated again after a re-match.
        elif latest:
            state, reason = "submitted", "feedback_saved"
        elif (
            event
            and event.get("event") == "dismissed"
            and (
                not event.get("prompt_fingerprint")
                or event.get("prompt_fingerprint") == prompt_fingerprint
            )
        ):
            state, reason = "dismissed", str(event.get("reason") or "dismissed")

        role = str(row.get("role") or session.get("session_role") or "")
        is_primary = role in {"quality", "long"} or str(row.get("date") or "")[:10] in forecast_dates
        projection_source = {
            **session,
            "tss": row.get("tss", session.get("total_tss")),
            "actual_total_tss": row.get("actual_total_tss"),
            "transition_minutes": row.get(
                "transition_minutes", session.get("transition_minutes")
            ),
        }
        composite_execution = row.get("composite_execution")
        if not isinstance(composite_execution, Mapping):
            composite_execution = project_composite_execution(
                projection_source,
                activities,
            )
        prompts.append(
            {
                "prompt_fingerprint": prompt_fingerprint,
                "session_id": session_id,
                "parent_session_id": session_id if session.get("kind") == "composite" else None,
                "date": str(row.get("date") or "")[:10],
                "name": row.get("name") or session.get("export_name") or session.get("template_name") or "Сессия",
                "role": role,
                "kind": str(session.get("kind") or "single"),
                "planned_sport": str(row.get("sport") or session.get("sport") or ""),
                "state": state,
                "reason": reason,
                "is_primary": is_primary,
                "match_status": match_status,
                "match_method": match_method,
                "match_confidence": confidence,
                "adherence": row.get("adherence") or "unknown",
                "actual_activity_ids": list(row.get("actual_activity_ids") or []),
                "actual_activities": activities,
                "session_end_at_utc": ended_at,
                "session_end_provenance": end_provenance,
                "allowed_completion_statuses": allowed,
                "feedback": dict(latest) if latest else None,
                "provenance_label": (
                    "athlete-entered"
                    if latest and latest.get("source") == "user_web"
                    else "admin-entered" if latest else None
                ),
                "composite_execution": (
                    dict(composite_execution)
                    if isinstance(composite_execution, Mapping)
                    else None
                ),
            }
        )
    prompts.sort(
        key=lambda item: (
            item["state"] != "ready",
            not item["is_primary"],
            item["date"],
            item["session_id"],
        )
    )
    primary = next((item for item in prompts if item["state"] == "ready"), None)
    return {
        "status": "available",
        "rule_version": FEEDBACK_RULE_VERSION,
        "prompts": prompts,
        "primary": primary,
        "metrics": {
            "eligible": sum(1 for item in prompts if item["state"] == "ready"),
            "submitted": sum(1 for item in prompts if item["state"] == "submitted"),
            "dismissed": sum(1 for item in prompts if item["state"] == "dismissed"),
            "pending_match": sum(1 for item in prompts if item["state"] == "pending_match"),
        },
    }


def evaluate_prediction(
    prediction: Mapping[str, Any],
    feedback: Mapping[str, Any],
    match_snapshot: Mapping[str, Any],
    *,
    latest_eligible_id: int | None,
) -> dict[str, Any]:
    """Evaluate one forecast revision from frozen feedback/match evidence."""
    activities = [
        item
        for item in match_snapshot.get("actual_activities") or []
        if isinstance(item, Mapping)
    ]
    starts = [_utc(item.get("started_at_utc")) for item in activities]
    starts = [item for item in starts if item is not None]
    session_start = min(starts) if starts else None
    created = _utc(prediction.get("created_at"))
    prediction_id = int(prediction.get("id") or 0)
    adherence = str(match_snapshot.get("adherence") or "unknown")
    quality = feedback.get("quality_rating_1_5")

    status = "unscored"
    reason: str | None = None
    outcome: str | None = None
    score: float | None = None
    if feedback.get("status") == "tombstone":
        reason = "feedback_tombstoned"
    elif session_start is None:
        reason = "missing_session_start"
    elif created is None or created >= session_start:
        reason = "post_start_prediction"
    elif latest_eligible_id is None or prediction_id != int(latest_eligible_id):
        reason = "superseded"
    elif str(match_snapshot.get("match_status") or "") != "matched":
        reason = "missing_adherence_evidence"
    elif adherence == "major_deviation":
        reason = "major_deviation"
    elif adherence not in {"exact", "substituted"}:
        reason = "missing_adherence_evidence"
    elif quality is None or quality == 3:
        reason = "ambiguous_quality"
    else:
        status = "scored"
        outcome = "success" if int(quality) >= 4 else "failure"
        score = brier_score(float(prediction.get("prediction_pct") or 0.0), int(quality))
    return {
        "prediction_id": prediction_id,
        "prediction_target_key": prediction.get("target_key"),
        "feedback_id": feedback.get("id"),
        "match_revision_id": feedback.get("match_revision_id"),
        "status": status,
        "plan_adherence": adherence,
        "quality_rating_1_5": quality,
        "quality_outcome": outcome,
        "unscored_reason": reason,
        "brier_score": score,
        "evidence": {
            "feedback_rule_version": feedback.get("rule_version") or FEEDBACK_RULE_VERSION,
            "feedback_source": feedback.get("source"),
            "match_status": match_snapshot.get("match_status"),
            "match_method": match_snapshot.get("match_method"),
            "session_start_utc": _iso_utc(session_start) if session_start else None,
        },
        "rule_version": EVALUATION_RULE_VERSION,
    }


__all__ = [
    "EVALUATION_RULE_VERSION",
    "FEEDBACK_RULE_VERSION",
    "build_feedback_prompts",
    "canonical_fingerprint",
    "derive_session_end_utc",
    "evaluate_prediction",
    "validate_feedback_values",
]
