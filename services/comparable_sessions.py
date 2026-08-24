"""Bounded local-data projection for comparable-session evidence (#500)."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Mapping

from models.comparable_sessions import (
    build_comparison_data_gap,
    project_activity_features,
    select_comparable_session,
)
from models.plan_actual_reconciliation import find_planned_session
from models.planning_checkpoints import restore_goal_plan_from_checkpoint


DEFAULT_LOOKBACK_DAYS = 730


def _day(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value or "")[:10])
    except ValueError:
        return None


def _stimulus_family(template: Mapping[str, Any] | None) -> str | None:
    source = dict(template or {})
    definition = source.get("definition_snapshot")
    definition = dict(definition) if isinstance(definition, Mapping) else {}
    value = definition.get("step_builder_key")
    text = str(value or "").strip()
    return text or None


def _subjective_evidence(feedback: Mapping[str, Any] | None) -> dict[str, Any] | None:
    source = dict(feedback or {})
    if source.get("status") == "tombstone":
        return None
    provenance = (
        "athlete-entered" if source.get("source") == "user_web" else "admin-entered"
    )
    rpe = source.get("session_rpe_1_10")
    note = str(source.get("note") or "").strip()
    if rpe is None and note:
        return {"kind": "athlete_note", "value": note, "provenance": provenance}
    if rpe is not None:
        return {
            "kind": "session_rpe_1_10",
            "value": int(rpe),
            "provenance": provenance,
            **({"note": note} if note else {}),
        }
    return None


def _feedback_by_activity(database: Any) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for raw in database.get_latest_session_feedbacks() or []:
        if not isinstance(raw, Mapping) or raw.get("status") == "tombstone":
            continue
        row = dict(raw)
        for activity_id in row.get("actual_activity_ids") or []:
            result[str(activity_id)] = row
    return result


def _match_by_activity(
    matches: list[Mapping[str, Any]],
) -> dict[str, Mapping[str, Any] | None]:
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for match in matches:
        if not isinstance(match, Mapping) or match.get("match_status") != "matched":
            continue
        for activity_id in match.get("actual_activity_ids") or []:
            grouped.setdefault(str(activity_id), []).append(match)
    return {
        activity_id: rows[0] if len(rows) == 1 else None
        for activity_id, rows in grouped.items()
    }


def _stimulus_for_match(
    database: Any,
    match: Mapping[str, Any],
    checkpoint_cache: dict[int, Mapping[str, Any] | None],
) -> str | None:
    try:
        checkpoint_id = int(match.get("base_checkpoint_id"))
    except (TypeError, ValueError):
        return None
    if checkpoint_id not in checkpoint_cache:
        checkpoint_cache[checkpoint_id] = restore_goal_plan_from_checkpoint(
            database.get_planning_checkpoint(checkpoint_id)
        )
    plan = checkpoint_cache[checkpoint_id] or {}
    _day_template, session = find_planned_session(
        list(plan.get("session_templates") or []),
        str(match.get("session_id") or ""),
    )
    return _stimulus_family(session)


def project_comparable_session(
    database: Any,
    *,
    evidence: Mapping[str, Any],
    feedback: Mapping[str, Any] | None = None,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
) -> dict[str, Any]:
    """Build one comparison from existing local facts, without provider I/O."""
    row = dict(evidence.get("row") or {})
    template = dict(evidence.get("template") or {})
    target_ids = [
        str(value)
        for value in row.get("actual_activity_ids") or []
        if str(value or "").strip()
    ]
    if len(target_ids) != 1:
        return build_comparison_data_gap("TARGET_ACTIVITY_COUNT_UNSUPPORTED")
    if row.get("match_status") != "matched":
        return build_comparison_data_gap("TARGET_MATCH_NOT_STABLE")
    target_activity = database.get_activity(target_ids[0])
    if not isinstance(target_activity, Mapping):
        return build_comparison_data_gap("TARGET_ACTIVITY_NOT_FOUND")
    target_day = _day(target_activity.get("date"))
    if target_day is None:
        return build_comparison_data_gap("TARGET_ACTIVITY_INCOMPLETE")
    stimulus = _stimulus_family(template)
    feedbacks = _feedback_by_activity(database)
    target_feedback = dict(feedback) if isinstance(feedback, Mapping) else feedbacks.get(target_ids[0])
    target = project_activity_features(
        target_activity,
        stimulus_family=stimulus,
        intervals=database.get_activity_intervals(target_ids[0]),
        subjective_evidence=_subjective_evidence(target_feedback),
    )

    bounded_lookback = min(max(1, int(lookback_days or DEFAULT_LOOKBACK_DAYS)), 3650)
    start = target_day - timedelta(days=bounded_lookback)
    activities = [
        dict(item)
        for item in database.get_activities_between(start.isoformat(), target_day.isoformat())
        if isinstance(item, Mapping)
    ]
    matches = database.get_latest_plan_actual_matches(
        start_date=start.isoformat(), end_date=target_day.isoformat()
    )
    matches_by_activity = _match_by_activity(list(matches or []))
    checkpoint_cache: dict[int, Mapping[str, Any] | None] = {}
    candidates: list[dict[str, Any]] = []
    for activity in activities:
        activity_id = str(activity.get("activity_id") or "")
        if not activity_id or activity_id in target_ids:
            continue
        match = matches_by_activity.get(activity_id)
        if not isinstance(match, Mapping):
            continue
        candidate_stimulus = _stimulus_for_match(database, match, checkpoint_cache)
        if candidate_stimulus != stimulus:
            continue
        candidates.append(
            project_activity_features(
                activity,
                stimulus_family=candidate_stimulus,
                intervals=database.get_activity_intervals(activity_id),
                subjective_evidence=_subjective_evidence(feedbacks.get(activity_id)),
            )
        )
    return select_comparable_session(target, candidates)


__all__ = ["DEFAULT_LOOKBACK_DAYS", "project_comparable_session"]
