"""Headless orchestration for post-workout feedback and forecast evaluation."""
from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timezone
from typing import Any, Mapping

from api.planning_service import reconciliation_at
from data.database import Database
from models.plan_actual_reconciliation import MATCH_RULE_VERSION, find_planned_session
from models.planning_checkpoints import restore_goal_plan_from_checkpoint
from models.post_workout_feedback import (
    EVALUATION_RULE_VERSION,
    FEEDBACK_RULE_VERSION,
    build_feedback_prompts,
    canonical_fingerprint,
    derive_session_end_utc,
    evaluate_prediction,
    validate_feedback_values,
)
from models.session_quality_forecast import classify_plan_adherence
from utils.product_semantics import normalize_sport_key


class StaleFeedbackError(RuntimeError):
    """Raised when a correction targets a superseded feedback revision."""


_ACTUAL_ROLES = {"off", "recovery", "easy", "activation", "quality", "long"}


def _now(value: datetime | None = None) -> datetime:
    current = value or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


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


def feedback_from_today_evidence(
    db: Database,
    *,
    yesterday: Mapping[str, Any],
    goal_plan: Mapping[str, Any] | None,
    forecasts: list[Mapping[str, Any]],
    now_utc: datetime,
    as_of: str,
) -> dict[str, Any]:
    """Compose feedback prompts from evidence Today already calculated."""
    if yesterday.get("status") == "unavailable":
        return {
            "status": "unavailable",
            "reason": yesterday.get("reason") or "reconciliation unavailable",
            "rule_version": FEEDBACK_RULE_VERSION,
            "prompts": [],
            "primary": None,
            "metrics": {},
        }
    latest_feedback = {
        row["session_id"]: row for row in db.get_latest_session_feedbacks()
    }
    prompt_events = {
        row["session_id"]: row for row in db.get_latest_session_feedback_prompt_events()
    }
    return build_feedback_prompts(
        list(yesterday.get("rows") or []),
        templates=list((goal_plan or {}).get("session_templates") or []),
        latest_feedback_by_session=latest_feedback,
        prompt_events_by_session=prompt_events,
        forecasts=forecasts,
        now_utc=_now(now_utc),
        as_of=as_of,
    )


def _feedback_evidence_for_session(
    db: Database,
    session_id: str,
    *,
    as_of: date | str | None = None,
) -> dict[str, Any]:
    """Revalidate one session from local facts without provider GET calls.

    The reconciliation probe is anchored on the session's OWN planned date
    (resolved from the active checkpoint first), not on `as_of`/today, so a
    session outside the ordinary 12-week lookback horizon can still be
    revalidated -- e.g. for a late correction or tombstone of a session that
    happened months ago (Issue #195). `as_of` still bounds how recent the
    session may be: a session dated after `as_of` fails closed rather than
    resolving, matching the same fail-closed contract
    `services.recovery_analytics`'s targeted refresh uses for the same case.
    """
    resolved_as_of = (
        as_of if isinstance(as_of, date) else date.fromisoformat(str(as_of)[:10]) if as_of else datetime.now().date()
    )
    checkpoint = db.get_latest_planning_checkpoint()
    goal_plan = restore_goal_plan_from_checkpoint(checkpoint) or {}
    # find_planned_session resolves by the PARENT session's own content-
    # derived id inside `sessions[]`, never the day-level scalar projection
    # -- required so a session on a multi-session day (Issue #205/#209)
    # resolves correctly, not just the common single-session-day case.
    day_template, template = find_planned_session(
        goal_plan.get("session_templates") or [], session_id
    )
    if day_template is None or template is None:
        raise LookupError(f"planned session {session_id} not found in active checkpoint")
    session_date_text = str(day_template.get("date") or "")[:10]
    try:
        session_date = date.fromisoformat(session_date_text)
    except ValueError as exc:
        raise LookupError(f"planned session {session_id} has no resolvable date") from exc
    if session_date > resolved_as_of:
        raise LookupError(
            f"planned session {session_id} is dated after {resolved_as_of.isoformat()}"
        )
    payload = reconciliation_at(
        db,
        weeks=1,
        as_of=session_date,
        include_provider=False,
    )
    row = next(
        (
            dict(item)
            for item in payload.get("rows") or []
            if str(item.get("session_id") or "") == str(session_id)
        ),
        None,
    )
    if row is None:
        raise LookupError(f"planned session {session_id} not found in local reconciliation")
    ledger_rows = db.get_latest_plan_actual_matches(
        start_date=session_date_text,
        end_date=session_date_text,
    )
    match_revision = next(
        (
            item
            for item in ledger_rows
            if str(item.get("target_key") or "") == f"session:{session_id}"
        ),
        None,
    )
    return {
        "row": row,
        "template": template,
        "match_revision_id": (match_revision or {}).get("id"),
    }


def _match_snapshot(evidence: Mapping[str, Any]) -> dict[str, Any]:
    row = dict(evidence.get("row") or {})
    return {
        "planned": {
            key: row.get(key)
            for key in (
                "session_id", "target_key", "date", "name", "role", "sport",
                "tss", "duration_minutes", "phase",
            )
        },
        "match_status": row.get("match_status"),
        "match_method": row.get("match_method"),
        "confidence": row.get("confidence"),
        "adherence": row.get("adherence") or "unknown",
        "actual_activity_ids": list(row.get("actual_activity_ids") or []),
        "actual_activities": [
            dict(item)
            for item in row.get("actual_activities") or []
            if isinstance(item, Mapping)
        ],
        "actual_total_tss": row.get("actual_total_tss"),
        "actual_duration_minutes": row.get("actual_duration_minutes"),
        "actual_sport": row.get("actual_sport"),
        "actual_role": row.get("actual_role"),
        "evidence": list(row.get("evidence") or []),
        "match_rule_version": MATCH_RULE_VERSION,
    }


def _ensure_submission_due(
    evidence: Mapping[str, Any],
    *,
    now_utc: datetime,
) -> None:
    projection = build_feedback_prompts(
        [dict(evidence.get("row") or {})],
        templates=[dict(evidence.get("template") or {})],
        latest_feedback_by_session={},
        prompt_events_by_session={},
        forecasts=[],
        now_utc=now_utc,
        as_of=now_utc.date().isoformat(),
    )
    prompt = next(iter(projection.get("prompts") or []), None)
    if not prompt:
        raise LookupError("feedback prompt evidence is unavailable")
    if prompt.get("state") == "pending_match":
        raise ValueError("ambiguous match must be confirmed before feedback")
    if prompt.get("state") != "ready":
        raise ValueError(f"feedback is not due: {prompt.get('reason') or prompt.get('state')}")


def _append_feedback(
    db: Database,
    payload: Mapping[str, Any],
    *,
    evidence: Mapping[str, Any],
    now_utc: datetime,
    source: str,
    supersedes_feedback_id: int | None = None,
    status: str = "active",
) -> dict[str, Any]:
    values = validate_feedback_values(
        completion_status=str(payload.get("completion_status") or ""),
        completion_pct=payload.get("completion_pct"),
        session_rpe_1_10=payload.get("session_rpe_1_10"),
        quality_rating_1_5=payload.get("quality_rating_1_5"),
        require_started_ratings=source == "user_web" and status == "active",
    )
    row = dict(evidence.get("row") or {})
    template = dict(evidence.get("template") or {})
    session_id = str(row.get("session_id") or payload.get("session_id") or "").strip()
    if not session_id:
        raise ValueError("session_id must be non-empty")
    activities = [
        dict(item)
        for item in row.get("actual_activities") or []
        if isinstance(item, Mapping)
    ]
    ended_at, end_provenance = derive_session_end_utc(activities)
    client_fingerprint = str(payload.get("client_submission_fingerprint") or "").strip()
    if not client_fingerprint:
        raise ValueError("client_submission_fingerprint must be non-empty")
    saved = db.save_session_feedback(
        {
            "fingerprint": client_fingerprint,
            "target_key": f"session:{session_id}",
            "supersedes_feedback_id": supersedes_feedback_id,
            "expected_latest_feedback_id": supersedes_feedback_id,
            "session_id": session_id,
            "parent_session_id": session_id if template.get("kind") == "composite" else None,
            "match_revision_id": evidence.get("match_revision_id"),
            "match_snapshot": _match_snapshot(evidence),
            "actual_activity_ids": list(row.get("actual_activity_ids") or []),
            **values,
            "completion_pct_source": (
                ("athlete_entered" if source == "user_web" else "admin_entered")
                if values.get("completion_pct") is not None
                else None
            ),
            "note": payload.get("note"),
            "source": source,
            "session_end_at_utc": ended_at,
            "session_end_provenance": end_provenance,
            "status": status,
            "rule_version": FEEDBACK_RULE_VERSION,
            "submitted_at": _iso(now_utc),
        }
    )
    if saved.get("conflict"):
        raise StaleFeedbackError("feedback revision is no longer current")
    feedback = saved["feedback"]
    evaluations = _evaluate_feedback_predictions(db, feedback)
    from services.recovery_analytics import refresh_recovery_episodes_best_effort

    refresh_recovery_episodes_best_effort(
        db, as_of=now_utc.date(), target_session_ids=[session_id]
    )
    return {"feedback": feedback, "created": saved["created"], "evaluations": evaluations}


def submit_session_feedback(
    db: Database,
    payload: Mapping[str, Any],
    *,
    now_utc: datetime | None = None,
    source: str = "user_web",
) -> dict[str, Any]:
    now = _now(now_utc)
    session_id = str(payload.get("session_id") or "").strip()
    if not session_id:
        raise ValueError("session_id must be non-empty")
    client_fingerprint = str(payload.get("client_submission_fingerprint") or "").strip()
    if not client_fingerprint:
        raise ValueError("client_submission_fingerprint must be non-empty")
    existing = db.get_session_feedback_by_fingerprint(client_fingerprint)
    if existing is not None:
        if str(existing.get("session_id") or "") != session_id:
            raise StaleFeedbackError(
                "client_submission_fingerprint is already used for another session"
            )
        return {
            "feedback": existing,
            "created": False,
            "evaluations": db.get_session_quality_evaluations(
                feedback_ids=[existing["id"]]
            ),
        }
    latest = db.get_latest_session_feedback(session_id)
    if latest is not None and latest.get("status") == "active":
        raise StaleFeedbackError(
            "feedback already exists for this session; use the correction endpoint"
        )
    evidence = _feedback_evidence_for_session(db, session_id, as_of=now.date())
    _ensure_submission_due(evidence, now_utc=now)
    return _append_feedback(db, payload, evidence=evidence, now_utc=now, source=source)


def correct_session_feedback(
    db: Database,
    feedback_id: int,
    payload: Mapping[str, Any],
    *,
    now_utc: datetime | None = None,
) -> dict[str, Any]:
    current = db.get_session_feedback(feedback_id)
    if current is None:
        raise LookupError(f"feedback {feedback_id} not found")
    latest = db.get_latest_session_feedback(current["session_id"])
    if latest is None or int(latest["id"]) != int(feedback_id):
        raise StaleFeedbackError("feedback revision is no longer current")
    now = _now(now_utc)
    evidence = _feedback_evidence_for_session(db, current["session_id"], as_of=now.date())
    return _append_feedback(
        db,
        {"session_id": current["session_id"], **dict(payload)},
        evidence=evidence,
        now_utc=now,
        source="user_web",
        supersedes_feedback_id=int(current["id"]),
    )


def tombstone_session_feedback(
    db: Database,
    feedback_id: int,
    *,
    client_submission_fingerprint: str,
    now_utc: datetime | None = None,
) -> dict[str, Any]:
    current = db.get_session_feedback(feedback_id)
    if current is None:
        raise LookupError(f"feedback {feedback_id} not found")
    latest = db.get_latest_session_feedback(current["session_id"])
    if latest is None or int(latest["id"]) != int(feedback_id):
        raise StaleFeedbackError("feedback revision is no longer current")
    now = _now(now_utc)
    evidence = {
        "row": {
            **dict((current.get("match_snapshot") or {}).get("planned") or {}),
            "session_id": current["session_id"],
            "actual_activity_ids": current.get("actual_activity_ids") or [],
            "actual_activities": (current.get("match_snapshot") or {}).get("actual_activities") or [],
            "match_status": (current.get("match_snapshot") or {}).get("match_status"),
            "match_method": (current.get("match_snapshot") or {}).get("match_method"),
            "confidence": (current.get("match_snapshot") or {}).get("confidence"),
            "adherence": (current.get("match_snapshot") or {}).get("adherence"),
        },
        "template": {"session_id": current["session_id"]},
        "match_revision_id": current.get("match_revision_id"),
    }
    return _append_feedback(
        db,
        {
            "session_id": current["session_id"],
            "client_submission_fingerprint": client_submission_fingerprint,
            "completion_status": "unknown",
            "completion_pct": None,
            "session_rpe_1_10": None,
            "quality_rating_1_5": None,
            "note": "feedback removed by athlete",
        },
        evidence=evidence,
        now_utc=now,
        source="user_web",
        supersedes_feedback_id=int(current["id"]),
        status="tombstone",
    )


def dismiss_feedback_prompt(
    db: Database,
    session_id: str,
    *,
    client_submission_fingerprint: str,
    prompt_fingerprint: str | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    return db.save_session_feedback_prompt_event(
        {
            "fingerprint": client_submission_fingerprint,
            "target_key": f"session:{session_id}",
            "session_id": session_id,
            "prompt_fingerprint": prompt_fingerprint,
            "event": "dismissed",
            "reason": reason,
            "source": "user_web",
            "rule_version": FEEDBACK_RULE_VERSION,
        }
    )


def _session_id_for_prediction(db: Database, prediction: Mapping[str, Any]) -> str | None:
    checkpoint = db.get_planning_checkpoint(prediction.get("plan_checkpoint_id"))
    plan = restore_goal_plan_from_checkpoint(checkpoint) or {}
    try:
        index = int(prediction.get("plan_session_index"))
    except (TypeError, ValueError):
        return None
    templates = list(plan.get("session_templates") or [])
    if index < 0 or index >= len(templates) or not isinstance(templates[index], Mapping):
        return None
    return str(templates[index].get("session_id") or "").strip() or None


def _evaluate_feedback_predictions(
    db: Database,
    feedback: Mapping[str, Any],
) -> list[dict[str, Any]]:
    predictions = [
        row
        for row in db.get_session_quality_predictions(days=36500, limit=5000)
        if _session_id_for_prediction(db, row) == feedback.get("session_id")
    ]
    if not predictions:
        return []
    match_snapshot = dict(feedback.get("match_snapshot") or {})
    starts = [
        _utc(item.get("started_at_utc"))
        for item in match_snapshot.get("actual_activities") or []
        if isinstance(item, Mapping)
    ]
    starts = [item for item in starts if item is not None]
    session_start = min(starts) if starts else None
    latest_by_target: dict[str, int | None] = {}
    for target_key in {str(row.get("target_key") or "") for row in predictions}:
        group = [row for row in predictions if str(row.get("target_key") or "") == target_key]
        eligible = [
            row
            for row in group
            if session_start is not None
            and _utc(row.get("created_at")) is not None
            and _utc(row.get("created_at")) < session_start
        ]
        latest_by_target[target_key] = (
            max(
                eligible,
                key=lambda row: (_utc(row.get("created_at")), int(row.get("id") or 0)),
            )["id"]
            if eligible
            else None
        )
    prior = {
        row["prediction_id"]: row
        for row in db.get_latest_session_quality_evaluations(
            prediction_ids=[row["id"] for row in predictions]
        )
    }
    saved: list[dict[str, Any]] = []
    for prediction in predictions:
        values = evaluate_prediction(
            prediction,
            feedback,
            match_snapshot,
            latest_eligible_id=latest_by_target.get(str(prediction.get("target_key") or "")),
        )
        fingerprint_payload = {
            "rule_version": EVALUATION_RULE_VERSION,
            "prediction_id": prediction["id"],
            "feedback_id": feedback["id"],
            "match_revision_id": feedback.get("match_revision_id"),
        }
        result = db.save_session_quality_evaluation(
            {
                **values,
                "fingerprint": canonical_fingerprint(fingerprint_payload),
                "target_key": f"prediction:{prediction['id']}",
                "supersedes_evaluation_id": (prior.get(prediction["id"]) or {}).get("id"),
            }
        )
        saved.append(result["evaluation"])
    return saved


def project_predictions_with_evaluations(
    db: Database,
    rows: list[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    evaluations = {
        row["prediction_id"]: row
        for row in db.get_latest_session_quality_evaluations(
            prediction_ids=[int(item["id"]) for item in rows]
        )
    }
    projected = []
    for raw in rows:
        item = dict(raw)
        evaluation = evaluations.get(item.get("id"))
        if evaluation:
            feedback = db.get_session_feedback(evaluation["feedback_id"])
            item.update(
                {
                    "status": evaluation["status"],
                    "plan_adherence": evaluation["plan_adherence"],
                    "quality_rating_1_5": evaluation["quality_rating_1_5"],
                    "quality_outcome": evaluation["quality_outcome"],
                    "unscored_reason": evaluation["unscored_reason"],
                    "brier_score": evaluation["brier_score"],
                    "evaluation_id": evaluation["id"],
                    "evaluation_revision": evaluation["revision"],
                    "feedback_id": evaluation["feedback_id"],
                    "actual_activity_ids": (feedback or {}).get("actual_activity_ids") or [],
                    "actual_snapshot": (feedback or {}).get("match_snapshot") or {},
                    "resolved_at": evaluation.get("created_at"),
                    "resolution_provenance": "session_feedback",
                }
            )
        elif item.get("status") in {"scored", "unscored"}:
            item["resolution_provenance"] = "legacy_prediction_resolution"
        projected.append(item)
    return projected


def _admin_match_evidence(
    db: Database,
    prediction: Mapping[str, Any],
    *,
    activity_ids: list[str],
    actual_role: str | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    session_id = _session_id_for_prediction(db, prediction)
    if not session_id:
        raise LookupError("prediction plan session is unavailable")
    activities = db.get_activities_by_ids(activity_ids)
    found = {str(item.get("activity_id")) for item in activities}
    missing = [str(value) for value in activity_ids if str(value) not in found]
    if missing:
        raise LookupError(f"activities not found: {', '.join(missing)}")
    if any(str(item.get("date") or "")[:10] != prediction["target_date"] for item in activities):
        raise ValueError("all activities must belong to the prediction target date")
    sports = {normalize_sport_key(item.get("sport")) for item in activities if item.get("sport")}
    actual_sport = next(iter(sports)) if len(sports) == 1 else "mixed" if sports else ""
    actual_tss = round(sum(float(item.get("tss") or 0.0) for item in activities), 1)
    actual_duration = round(
        sum(float(item.get("duration_minutes") or 0.0) for item in activities), 1
    )
    adherence = classify_plan_adherence(
        prediction["planned_session"],
        {"role": actual_role, "sport": actual_sport, "tss": actual_tss},
    )
    latest_matches = db.get_latest_plan_actual_matches(
        start_date=prediction["target_date"], end_date=prediction["target_date"]
    )
    previous = next(
        (
            row
            for row in latest_matches
            if row.get("target_key") == f"session:{session_id}"
        ),
        None,
    )
    match_payload = {
        "fingerprint": canonical_fingerprint(
            {
                "method": "admin_resolve",
                "session_id": session_id,
                "activity_ids": activity_ids,
                "actual_role": actual_role,
            }
        ),
        "target_key": f"session:{session_id}",
        "supersedes_match_id": (previous or {}).get("id"),
        "session_id": session_id,
        "base_checkpoint_id": prediction["plan_checkpoint_id"],
        "session_date": prediction["target_date"],
        "match_status": "matched" if activities else "unmatched",
        "match_method": "admin_resolve",
        "confidence": 1.0 if activities else 0.0,
        "planned_snapshot": prediction["planned_session"],
        "actual_activity_ids": list(activity_ids),
        "actual_snapshot": {
            "role": actual_role,
            "sport": actual_sport,
            "tss": actual_tss,
            "duration_minutes": actual_duration,
        },
        "evidence": ["Административное сопоставление выбрало явные активности"],
        "rule_version": MATCH_RULE_VERSION,
    }
    match = db.save_plan_actual_match(match_payload)
    checkpoint = db.get_planning_checkpoint(prediction["plan_checkpoint_id"])
    plan = restore_goal_plan_from_checkpoint(checkpoint) or {}
    templates = list(plan.get("session_templates") or [])
    template = templates[prediction["plan_session_index"]] if prediction["plan_session_index"] < len(templates) else {}
    row = {
        **prediction["planned_session"],
        "session_id": session_id,
        "target_key": f"session:{session_id}",
        "name": template.get("template_name") or template.get("session_focus") or "Сессия",
        "match_status": match_payload["match_status"],
        "match_method": "admin_resolve",
        "confidence": match_payload["confidence"],
        "adherence": adherence or "unknown",
        "actual_activity_ids": list(activity_ids),
        "actual_activities": activities,
        "actual_total_tss": actual_tss,
        "actual_duration_minutes": actual_duration,
        "actual_sport": actual_sport,
        "actual_role": actual_role,
        "evidence": match_payload["evidence"],
    }
    return {
        "row": row,
        "template": dict(template),
        "match_revision_id": match["id"],
    }, match


def resolve_prediction_via_feedback(
    db: Database,
    prediction_id: int,
    *,
    activity_ids: list[str],
    actual_role: str | None,
    quality_rating_1_5: int | None,
    note: str | None = None,
    submitted_at: str | None = None,
) -> dict[str, Any]:
    prediction = db.get_session_quality_prediction(prediction_id)
    if prediction is None:
        raise LookupError(f"prediction {prediction_id} not found")
    normalized_role = str(actual_role or "").strip().lower()
    if normalized_role and normalized_role not in _ACTUAL_ROLES:
        raise ValueError(f"actual_role must be one of {sorted(_ACTUAL_ROLES)}")
    if quality_rating_1_5 is not None and quality_rating_1_5 not in {1, 2, 3, 4, 5}:
        raise ValueError("quality_rating_1_5 must be between 1 and 5")
    evidence, match = _admin_match_evidence(
        db,
        prediction,
        activity_ids=[str(value) for value in activity_ids or []],
        actual_role=normalized_role or None,
    )
    timestamp = _utc(submitted_at) or datetime.now(timezone.utc)
    fingerprint = canonical_fingerprint(
        {
            "source": "admin_resolve",
            "prediction_target_key": prediction["target_key"],
            "match_revision_id": match["id"],
            "quality_rating_1_5": quality_rating_1_5,
            "note": str(note or "").strip() or None,
        }
    )
    previous_feedback = db.get_latest_session_feedback(evidence["row"]["session_id"])
    _append_feedback(
        db,
        {
            "session_id": evidence["row"]["session_id"],
            "client_submission_fingerprint": fingerprint,
            "completion_status": "completed" if activity_ids else "unknown",
            "completion_pct": 100 if activity_ids else None,
            "session_rpe_1_10": None,
            "quality_rating_1_5": quality_rating_1_5,
            "note": note,
        },
        evidence=evidence,
        now_utc=_now(timestamp),
        source="admin_resolve",
        supersedes_feedback_id=(previous_feedback or {}).get("id"),
    )
    group = db.get_session_quality_predictions(days=36500, target_key=prediction["target_key"])
    projected = project_predictions_with_evaluations(db, group)
    from api.session_quality_forecast import summarize_session_quality_predictions

    return {
        "predictions": projected,
        "summary": summarize_session_quality_predictions(projected),
    }


def list_feedback_prompts(
    db: Database,
    *,
    as_of: date | str | None = None,
    now_utc: datetime | None = None,
) -> dict[str, Any]:
    current = _now(now_utc)
    anchor = as_of or current.date()
    payload = reconciliation_at(db, weeks=1, as_of=anchor, include_provider=False)
    checkpoint = db.get_latest_planning_checkpoint()
    plan = restore_goal_plan_from_checkpoint(checkpoint) or {}
    forecasts = db.get_session_quality_predictions(days=36500, limit=1000)
    return feedback_from_today_evidence(
        db,
        yesterday={"status": "available", "rows": payload.get("rows") or []},
        goal_plan=plan,
        forecasts=forecasts,
        now_utc=current,
        as_of=str(anchor)[:10],
    )


def feedback_history(db: Database, session_id: str) -> dict[str, Any]:
    rows = db.get_session_feedback_history(session_id)
    feedback_ids = {row["id"] for row in rows}
    evaluations = (
        db.get_session_quality_evaluations(feedback_ids=sorted(feedback_ids))
        if feedback_ids
        else []
    )
    return {
        "session_id": session_id,
        "history": rows,
        "current": rows[-1] if rows else None,
        "evaluations": evaluations,
    }


def feedback_summary(db: Database) -> dict[str, Any]:
    rows = db.get_latest_session_feedbacks()
    active = [row for row in rows if row.get("status") == "active"]
    evaluations = db.get_latest_session_quality_evaluations()
    return {
        "total_sessions": len(rows),
        "active": len(active),
        "tombstoned": len(rows) - len(active),
        "corrections": sum(1 for row in rows if int(row.get("revision") or 0) > 1),
        "completion_statuses": dict(Counter(str(row.get("completion_status")) for row in active)),
        "rpe_distribution": dict(Counter(str(row.get("session_rpe_1_10")) for row in active if row.get("session_rpe_1_10") is not None)),
        "quality_distribution": dict(Counter(str(row.get("quality_rating_1_5")) for row in active if row.get("quality_rating_1_5") is not None)),
        "forecast_scored": sum(1 for row in evaluations if row.get("status") == "scored"),
        "forecast_unscored": sum(1 for row in evaluations if row.get("status") == "unscored"),
        "forecast_unscored_reasons": dict(Counter(str(row.get("unscored_reason") or "unknown") for row in evaluations if row.get("status") == "unscored")),
        "rule_version": FEEDBACK_RULE_VERSION,
    }


__all__ = [
    "StaleFeedbackError",
    "correct_session_feedback",
    "dismiss_feedback_prompt",
    "feedback_from_today_evidence",
    "feedback_history",
    "feedback_summary",
    "list_feedback_prompts",
    "project_predictions_with_evaluations",
    "resolve_prediction_via_feedback",
    "submit_session_feedback",
    "tombstone_session_feedback",
]
