"""Bounded local-data projection for comparable-session evidence (#500)."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Mapping

from models.comparable_sessions import (
    build_comparison_data_gap,
    prefilter_comparable_candidates,
    project_activity_features,
    select_comparable_session,
)
from models.plan_actual_reconciliation import build_reconciliation, find_planned_session
from models.planning_checkpoints import restore_goal_plan_from_checkpoint
from utils.product_semantics import normalize_sport_key


DEFAULT_LOOKBACK_DAYS = 730
_AUTO_RECONCILED_MATCH_METHODS = {
    "ai_trainer_external_id": 1.0,
    "date_sport_heuristic": 0.75,
}


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
        activity_ids = [
            str(value)
            for value in row.get("actual_activity_ids") or []
            if str(value or "").strip()
        ]
        if len(activity_ids) == 1:
            activity_id = activity_ids[0]
            current = result.get(activity_id)
            if current is None or _feedback_recency_key(row) > _feedback_recency_key(
                current
            ):
                result[activity_id] = row
    return result


def _feedback_recency_key(feedback: Mapping[str, Any]) -> tuple[float, int, int]:
    submitted = _instant(feedback.get("submitted_at") or feedback.get("created_at"))
    return (
        submitted.timestamp() if submitted is not None else float("-inf"),
        int(feedback.get("id") or 0),
        int(feedback.get("revision") or 0),
    )


def _match_by_activity(
    database: Any,
    matches: list[Mapping[str, Any]],
) -> dict[str, Mapping[str, Any] | None]:
    """Resolve effective lineage leaves before indexing matched activities."""
    identified: dict[int, Mapping[str, Any]] = {}
    standalone: list[Mapping[str, Any]] = []
    duplicate_ids: set[int] = set()
    for match in matches:
        if not isinstance(match, Mapping):
            continue
        try:
            match_id = int(match.get("id"))
        except (TypeError, ValueError):
            standalone.append(match)
            continue
        if match_id in identified:
            duplicate_ids.add(match_id)
            standalone.extend([identified.pop(match_id), match])
            continue
        if match_id not in duplicate_ids:
            identified[match_id] = match

    match_reader = getattr(database, "get_plan_actual_match", None)
    if callable(match_reader):
        pending = list(identified.values())
        while pending:
            match = pending.pop()
            try:
                parent_id = int(match.get("supersedes_match_id"))
            except (TypeError, ValueError):
                continue
            if parent_id in identified or parent_id in duplicate_ids:
                continue
            try:
                parent = match_reader(parent_id)
            except Exception:
                continue
            if not isinstance(parent, Mapping):
                continue
            try:
                hydrated_id = int(parent.get("id"))
            except (TypeError, ValueError):
                continue
            if hydrated_id != parent_id:
                continue
            identified[parent_id] = parent
            pending.append(parent)

    superseded_ids: set[int] = set()
    for match in identified.values():
        try:
            parent_id = int(match.get("supersedes_match_id"))
        except (TypeError, ValueError):
            continue
        if parent_id in identified:
            superseded_ids.add(parent_id)

    effective: list[Mapping[str, Any]] = list(standalone)
    for match_id, leaf in identified.items():
        if match_id in superseded_ids:
            continue
        lineage: list[Mapping[str, Any]] = []
        seen: set[int] = set()
        current: Mapping[str, Any] | None = leaf
        while current is not None:
            current_id = int(current.get("id"))
            if current_id in seen:
                lineage = []
                break
            seen.add(current_id)
            lineage.append(current)
            try:
                parent_id = int(current.get("supersedes_match_id"))
            except (TypeError, ValueError):
                break
            current = identified.get(parent_id)
        if lineage:
            effective.append({**dict(leaf), "_stimulus_lineage": lineage})

    grouped: dict[str, list[Mapping[str, Any]]] = {}
    blocked_activity_ids: set[str] = set()
    for match in effective:
        if not isinstance(match, Mapping):
            continue
        raw_lineage = match.get("_stimulus_lineage")
        lineage = (
            [row for row in raw_lineage if isinstance(row, Mapping)]
            if isinstance(raw_lineage, list)
            else [match]
        )
        if match.get("match_status") != "matched":
            for lineage_match in lineage:
                lineage_ids = [
                    str(value)
                    for value in lineage_match.get("actual_activity_ids") or []
                    if str(value or "").strip()
                ]
                if len(lineage_ids) == 1:
                    blocked_activity_ids.add(lineage_ids[0])
            continue
        activity_ids = [
            str(value)
            for value in match.get("actual_activity_ids") or []
            if str(value or "").strip()
        ]
        if len(activity_ids) == 1:
            grouped.setdefault(activity_ids[0], []).append(match)
    result = {
        activity_id: rows[0] if len(rows) == 1 else None
        for activity_id, rows in grouped.items()
    }
    for activity_id in blocked_activity_ids:
        if activity_id not in result:
            result[activity_id] = None
    return result


def _stimulus_for_match(
    database: Any,
    match: Mapping[str, Any],
    checkpoint_cache: dict[int, Mapping[str, Any] | None],
) -> str | None:
    raw_lineage = match.get("_stimulus_lineage")
    lineage = (
        [row for row in raw_lineage if isinstance(row, Mapping)]
        if isinstance(raw_lineage, list)
        else [match]
    )
    for lineage_match in lineage:
        try:
            checkpoint_id = int(lineage_match.get("base_checkpoint_id"))
        except (TypeError, ValueError):
            continue
        if checkpoint_id not in checkpoint_cache:
            checkpoint_cache[checkpoint_id] = restore_goal_plan_from_checkpoint(
                database.get_planning_checkpoint(checkpoint_id)
            )
        plan = checkpoint_cache[checkpoint_id] or {}
        _day_template, session = find_planned_session(
            list(plan.get("session_templates") or []),
            str(lineage_match.get("session_id") or ""),
        )
        stimulus = _stimulus_family(session)
        if stimulus:
            return stimulus
    return None


def _instant(value: Any) -> datetime | None:
    text_value = str(value or "").strip()
    if not text_value:
        return None
    try:
        parsed = datetime.fromisoformat(text_value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _with_profile_pace_threshold(
    database: Any,
    activity: Mapping[str, Any],
    history_cache: dict[str, list[Mapping[str, Any]]] | None = None,
) -> dict[str, Any]:
    """Attach the newest source-backed pace threshold known at activity time."""
    projected = dict(activity)
    if projected.get("tss_pace_used") is not None:
        return projected
    sport = normalize_sport_key(projected.get("sport"))
    if sport not in {"run", "swim"}:
        return projected
    history_reader = getattr(database, "get_athlete_pace_threshold_history", None)
    if not callable(history_reader):
        return projected
    activity_day = _day(projected.get("date"))
    activity_instant = _instant(projected.get("started_at_utc"))
    if activity_instant is None and activity_day is not None:
        activity_instant = datetime.combine(
            activity_day, time.max, tzinfo=timezone.utc
        )
    if activity_instant is None:
        return projected
    if history_cache is not None and sport in history_cache:
        history = history_cache[sport]
    else:
        history = [
            raw for raw in history_reader(sport) or [] if isinstance(raw, Mapping)
        ]
        if history_cache is not None:
            history_cache[sport] = history
    eligible: list[tuple[datetime, Mapping[str, Any]]] = []
    for raw in history:
        if not isinstance(raw, Mapping):
            continue
        snapshot_at = _instant(raw.get("snapshot_at"))
        if snapshot_at is not None and snapshot_at <= activity_instant:
            eligible.append((snapshot_at, raw))
    if not eligible:
        return projected
    _snapshot_at, selected = max(eligible, key=lambda item: item[0])
    projected["pace_threshold_used"] = selected.get("value")
    projected["pace_threshold_source"] = str(
        selected.get("source") or "athlete_profile"
    )
    projected["pace_threshold_observed_at"] = (
        selected.get("observed_at") or selected.get("snapshot_at")
    )
    return projected


def _cached_activity_intervals(
    database: Any,
    activity_id: str,
    cache: dict[str, Mapping[str, Any] | None],
) -> Mapping[str, Any] | None:
    if activity_id not in cache:
        raw = database.get_activity_intervals(activity_id)
        cache[activity_id] = raw if isinstance(raw, Mapping) else None
    return cache[activity_id]


def _stable_auto_match(snapshot: Mapping[str, Any]) -> bool:
    if snapshot.get("match_status") != "matched":
        return False
    method = str(snapshot.get("match_method") or "")
    minimum_confidence = _AUTO_RECONCILED_MATCH_METHODS.get(method)
    try:
        confidence = float(snapshot.get("confidence"))
    except (TypeError, ValueError):
        return False
    return minimum_confidence is not None and confidence >= minimum_confidence


def _auto_matches_by_activity(
    database: Any,
    *,
    activities: list[Mapping[str, Any]],
    ledger_rows: list[Mapping[str, Any]],
    target_day: date,
    lookback_days: int,
    latest_plan_cache: dict[str, Any],
) -> dict[str, Mapping[str, Any]]:
    """Rebuild stable local auto-matches once, without provider I/O or writes."""
    if "checkpoint" not in latest_plan_cache:
        reader = getattr(database, "get_latest_planning_checkpoint", None)
        checkpoint = reader() if callable(reader) else None
        latest_plan_cache["checkpoint"] = (
            dict(checkpoint) if isinstance(checkpoint, Mapping) else None
        )
        latest_plan_cache["plan"] = restore_goal_plan_from_checkpoint(checkpoint)
    checkpoint = latest_plan_cache.get("checkpoint")
    plan = latest_plan_cache.get("plan")
    if not isinstance(checkpoint, Mapping) or not isinstance(plan, Mapping):
        return {}
    try:
        checkpoint_id = int(checkpoint.get("id"))
    except (TypeError, ValueError):
        return {}
    try:
        reconciliation = build_reconciliation(
            plan,
            activities,
            as_of=target_day,
            weeks=max(1, (lookback_days + 6) // 7),
            base_checkpoint_id=checkpoint_id,
            ledger_rows=ledger_rows,
        )
    except (TypeError, ValueError):
        return {}
    result: dict[str, Mapping[str, Any]] = {}
    for raw in reconciliation.get("rows") or []:
        if not isinstance(raw, Mapping) or not _stable_auto_match(raw):
            continue
        activity_ids = [
            str(value)
            for value in raw.get("actual_activity_ids") or []
            if str(value or "").strip()
        ]
        if len(activity_ids) != 1:
            continue
        result[activity_ids[0]] = {
            "session_id": raw.get("session_id"),
            "base_checkpoint_id": checkpoint_id,
            "match_status": "matched",
            "match_method": raw.get("match_method"),
            "confidence": raw.get("confidence"),
            "actual_activity_ids": activity_ids,
        }
    return result


def _auto_reconciled_stimulus(
    database: Any,
    *,
    activity: Mapping[str, Any],
    feedback: Mapping[str, Any] | None,
    latest_plan_cache: dict[str, Any],
) -> str | None:
    """Resolve a persisted stable auto-match without inventing a ledger row."""
    if (
        not isinstance(feedback, Mapping)
        or feedback.get("match_revision_id") is not None
    ):
        return None
    activity_id = str(activity.get("activity_id") or "").strip()
    snapshot = dict(feedback.get("match_snapshot") or {})
    if not _stable_auto_match(snapshot):
        return None
    feedback_ids = [
        str(value)
        for value in feedback.get("actual_activity_ids") or []
        if str(value or "").strip()
    ]
    snapshot_ids = [
        str(value)
        for value in snapshot.get("actual_activity_ids") or []
        if str(value or "").strip()
    ]
    if feedback_ids != [activity_id] or snapshot_ids != [activity_id]:
        return None
    planned = dict(snapshot.get("planned") or {})
    session_id = str(planned.get("session_id") or feedback.get("session_id") or "")
    if not session_id:
        return None
    if str(planned.get("date") or "")[:10] != str(activity.get("date") or "")[:10]:
        return None
    planned_sport = normalize_sport_key(planned.get("sport"))
    activity_sport = normalize_sport_key(activity.get("sport"))
    if not planned_sport or planned_sport != activity_sport:
        return None
    if "plan" not in latest_plan_cache:
        reader = getattr(database, "get_latest_planning_checkpoint", None)
        checkpoint = reader() if callable(reader) else None
        latest_plan_cache["checkpoint"] = (
            dict(checkpoint) if isinstance(checkpoint, Mapping) else None
        )
        latest_plan_cache["plan"] = restore_goal_plan_from_checkpoint(checkpoint)
    activity_date = str(activity.get("date") or "")[:10]

    def stimulus_from_plan(plan: Mapping[str, Any] | None) -> str | None:
        if not isinstance(plan, Mapping):
            return None
        day_template, template = find_planned_session(
            list(plan.get("session_templates") or []),
            session_id,
        )
        if not isinstance(template, Mapping):
            return None
        if str((day_template or {}).get("date") or "")[:10] != activity_date:
            return None
        if normalize_sport_key(template.get("sport")) != activity_sport:
            return None
        return _stimulus_family(template)

    current_stimulus = stimulus_from_plan(latest_plan_cache.get("plan"))
    if current_stimulus:
        return current_stimulus
    cache_key = f"historical_stimulus:{session_id}:{activity_date}:{activity_sport}"
    if cache_key in latest_plan_cache:
        cached = latest_plan_cache[cache_key]
        return str(cached) if cached else None
    checkpoint_reader = getattr(
        database,
        "get_planning_checkpoints_for_session",
        None,
    )
    checkpoints = checkpoint_reader(session_id) if callable(checkpoint_reader) else []
    for checkpoint in checkpoints or []:
        plan = restore_goal_plan_from_checkpoint(checkpoint)
        historical_stimulus = stimulus_from_plan(plan)
        if historical_stimulus:
            latest_plan_cache[cache_key] = historical_stimulus
            return historical_stimulus
    latest_plan_cache[cache_key] = None
    return None


def _feedback_matches_target(
    feedback: Mapping[str, Any] | None,
    *,
    activity_ids: list[str],
    match_revision_id: Any,
) -> bool:
    if not isinstance(feedback, Mapping) or feedback.get("status") == "tombstone":
        return False
    feedback_ids = [
        str(value)
        for value in feedback.get("actual_activity_ids") or []
        if str(value or "").strip()
    ]
    if feedback_ids != activity_ids:
        return False
    feedback_revision = feedback.get("match_revision_id")
    if feedback_revision is None:
        return True
    raw_compatible = (
        match_revision_id
        if isinstance(match_revision_id, (list, tuple, set))
        else [match_revision_id]
    )
    compatible = {
        str(value) for value in raw_compatible if value is not None
    }
    return bool(compatible) and str(feedback_revision) in compatible


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
    preflight_target = project_activity_features(
        target_activity,
        stimulus_family=stimulus,
    )
    preflight = select_comparable_session(preflight_target, [])
    if preflight.get("reason_code") != "NO_ELIGIBLE_CANDIDATE":
        return preflight
    feedbacks = _feedback_by_activity(database)
    proposed_feedback = (
        dict(feedback) if isinstance(feedback, Mapping) else feedbacks.get(target_ids[0])
    )
    target_feedback = (
        proposed_feedback
        if _feedback_matches_target(
            proposed_feedback,
            activity_ids=target_ids,
            match_revision_id=evidence.get("match_revision_id"),
        )
        else None
    )
    threshold_history_cache: dict[str, list[Mapping[str, Any]]] = {}
    interval_cache: dict[str, Mapping[str, Any] | None] = {}
    target = project_activity_features(
        _with_profile_pace_threshold(
            database,
            target_activity,
            threshold_history_cache,
        ),
        stimulus_family=stimulus,
        intervals=_cached_activity_intervals(database, target_ids[0], interval_cache),
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
    matches_by_activity = _match_by_activity(database, list(matches or []))
    checkpoint_cache: dict[int, Mapping[str, Any] | None] = {}
    latest_plan_cache: dict[str, Any] = {}
    auto_matches_by_activity = _auto_matches_by_activity(
        database,
        activities=activities,
        ledger_rows=list(matches or []),
        target_day=target_day,
        lookback_days=bounded_lookback,
        latest_plan_cache=latest_plan_cache,
    )
    latest_checkpoint = latest_plan_cache.get("checkpoint")
    latest_plan = latest_plan_cache.get("plan")
    if isinstance(latest_checkpoint, Mapping) and isinstance(latest_plan, Mapping):
        try:
            checkpoint_cache[int(latest_checkpoint.get("id"))] = latest_plan
        except (TypeError, ValueError):
            pass
    candidate_sources: dict[
        str,
        tuple[dict[str, Any], str, Mapping[str, Any] | None],
    ] = {}
    cheap_candidates: list[dict[str, Any]] = []
    for activity in activities:
        activity_id = str(activity.get("activity_id") or "")
        if not activity_id or activity_id in target_ids:
            continue
        match: Mapping[str, Any] | None = None
        if activity_id in matches_by_activity:
            resolved_match = matches_by_activity[activity_id]
            if not isinstance(resolved_match, Mapping):
                continue
            match = resolved_match
            candidate_stimulus = _stimulus_for_match(
                database,
                match,
                checkpoint_cache,
            )
        else:
            auto_match = auto_matches_by_activity.get(activity_id)
            if isinstance(auto_match, Mapping):
                match = auto_match
                candidate_stimulus = _stimulus_for_match(
                    database,
                    match,
                    checkpoint_cache,
                )
            else:
                candidate_stimulus = _auto_reconciled_stimulus(
                    database,
                    activity=activity,
                    feedback=feedbacks.get(activity_id),
                    latest_plan_cache=latest_plan_cache,
                )
        if candidate_stimulus != stimulus:
            continue
        candidate_sources[activity_id] = (activity, candidate_stimulus, match)
        cheap_candidates.append(
            project_activity_features(
                activity,
                stimulus_family=candidate_stimulus,
            )
        )

    compatible_candidates, prefiltered_counts = prefilter_comparable_candidates(
        preflight_target,
        cheap_candidates,
    )
    candidates: list[dict[str, Any]] = []
    for cheap_candidate in compatible_candidates:
        activity_id = str(cheap_candidate.get("activity_id") or "")
        source = candidate_sources.get(activity_id)
        if source is None:
            continue
        activity, candidate_stimulus, match = source
        compatible_revisions = (
            [
                row.get("id")
                for row in match.get("_stimulus_lineage") or [match]
                if isinstance(row, Mapping)
            ]
            if isinstance(match, Mapping)
            else None
        )
        candidates.append(
            project_activity_features(
                _with_profile_pace_threshold(
                    database,
                    activity,
                    threshold_history_cache,
                ),
                stimulus_family=candidate_stimulus,
                intervals=_cached_activity_intervals(
                    database,
                    activity_id,
                    interval_cache,
                ),
                subjective_evidence=_subjective_evidence(
                    feedbacks.get(activity_id)
                    if _feedback_matches_target(
                        feedbacks.get(activity_id),
                        activity_ids=[activity_id],
                        match_revision_id=compatible_revisions,
                    )
                    else None
                ),
            )
        )
    return select_comparable_session(
        target,
        candidates,
        prefiltered_counts=prefiltered_counts,
    )


__all__ = ["DEFAULT_LOOKBACK_DAYS", "project_comparable_session"]
