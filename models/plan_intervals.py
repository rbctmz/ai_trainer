"""Проекция плановых ``materialized_steps`` в компактные интервалы (#383).

Плановая структура уже материализована как ``materialized_steps`` в
``models/workout_catalog.py`` (каждый шаг: ``{intensity, duration_seconds,
target:{type, low, high, relative_low, relative_high}, segment_kind,
repeat_index}``). Здесь мы НЕ генерируем интервалы заново и НЕ парсим текстовое
описание — проецируем steps в компактную форму для матчинга с фактом.

Для brick-сессий шаги лежат в ``legs[].materialized_steps``; проецируем все ноги
по порядку.

Fail-closed: неожиданная форма поднимает ``ValueError`` (сервис матчинга ловит и
отдаёт пустой матчинг), но мусорные элементы внутри списка пропускаются —
окружающие валидные шаги сохраняются.
"""
from __future__ import annotations

from typing import Any, Mapping

from utils.product_semantics import normalize_sport_key


_WORK_INTENSITY = {"work"}
_WORK_SEGMENT = {"work", "stage"}
_UNSET = object()
_CONFLICT = object()


def _sport_key(value: Any) -> str | None:
    """Canonical sport key, preserving missing as ``None``."""
    text = str(value or "").strip()
    if not text or isinstance(value, bool):
        return None
    normalized = normalize_sport_key(text)
    return normalized if normalized not in {"", "other"} else None


def _is_composite_session(session: Mapping[str, Any]) -> bool:
    """Recognise composite shapes used by current and legacy checkpoints."""
    if str(session.get("kind") or "").strip().lower() == "composite" or _sport_key(session.get("sport")) == "brick":
        return True
    legs = session.get("legs")
    if not isinstance(legs, list):
        parts = session.get("parts")
        if not isinstance(parts, Mapping):
            return False
        return len({_sport_key(key) for key in parts} - {None}) > 1
    sports = {_sport_key(leg.get("sport")) for leg in legs if isinstance(leg, Mapping)}
    return len(sports - {None}) > 1


def _lineage_value(lineage: Mapping[str, Any] | None) -> Any:
    """Read an explicit delivery/plan leg identity, if one was persisted."""
    if not isinstance(lineage, Mapping):
        return _UNSET
    sources = [lineage]
    if isinstance(lineage.get("lineage"), Mapping):
        sources.append(lineage["lineage"])
    index_fields = (
        "planned_leg_index", "leg_index", "delivery_leg_index", "provider_leg_index",
    )
    id_fields = ("planned_leg_id", "leg_id", "delivery_leg_id", "provider_leg_id")
    values: list[str] = []
    for source in sources:
        for field in index_fields:
            if field in source:
                try:
                    values.append(str(int(source[field])))
                except (TypeError, ValueError):
                    return _CONFLICT
        for field in id_fields:
            if field in source:
                text = str(source[field] or "").strip()
                if not text:
                    return _CONFLICT
                values.append(text.rsplit(":leg:", 1)[-1] if ":leg:" in text else text)
        for field in ("external_id", "provider_external_id", "delivery_external_id"):
            text = str(source.get(field) or "").strip()
            if ":leg:" in text:
                values.append(text.rsplit(":leg:", 1)[1])
    identities = set(values)
    if len(identities) > 1:
        return _CONFLICT
    return values[0] if values else _UNSET


def _leg_index(leg: Mapping[str, Any], position: int) -> int | None:
    try:
        index = int(leg.get("leg_index") or position)
    except (TypeError, ValueError):
        return None
    return index if index > 0 else None


def _select_composite_leg(
    session: Mapping[str, Any],
    *,
    sport: Any,
    lineage: Mapping[str, Any] | None = None,
) -> Mapping[str, Any] | None:
    """Select one proven leg for an activity-card projection.

    Explicit leg lineage wins. With no lineage, a unique canonical leg sport is
    a deterministic fallback for the current two-discipline brick. Missing,
    duplicate, or contradictory evidence returns ``None`` (fail closed).
    """
    raw_legs = session.get("legs")
    if not isinstance(raw_legs, list) or not raw_legs:
        return None
    legs = [leg for leg in raw_legs if isinstance(leg, Mapping)]
    if len(legs) != len(raw_legs):
        return None

    actual_sport = _sport_key(sport)
    explicit = _lineage_value(lineage)
    if explicit is _CONFLICT:
        return None
    if explicit is not _UNSET:
        try:
            explicit_index = int(explicit)
        except (TypeError, ValueError):
            explicit_index = None
        candidates = [
            leg
            for position, leg in enumerate(legs, start=1)
            if (
                explicit_index is not None
                and _leg_index(leg, position) == explicit_index
            )
            or (
                explicit_index is None
                and str(leg.get("leg_id") or "").strip() == str(explicit).strip()
            )
        ]
        if len(candidates) != 1:
            return None
        selected_sport = _sport_key(candidates[0].get("sport"))
        if selected_sport is None or (
            actual_sport is not None and selected_sport != actual_sport
        ):
            return None
        return candidates[0]

    if actual_sport is None:
        return None
    candidates = [
        leg
        for leg in legs
        if _sport_key(leg.get("sport")) == actual_sport
    ]
    return candidates[0] if len(candidates) == 1 else None


def _step_type(step: Mapping[str, Any]) -> str:
    """Classify a planned step as ``work`` or ``rest``.

    A step is ``work`` when its ``intensity`` is ``work`` OR its ``segment_kind``
    is a hard effort (``work``/``stage``); otherwise it is warm-up/recovery/
    cool-down → ``rest``.
    """
    intensity = str(step.get("intensity") or "").strip().lower()
    segment = str(step.get("segment_kind") or "").strip().lower()
    if intensity in _WORK_INTENSITY or segment in _WORK_SEGMENT:
        return "work"
    return "rest"


def _target_zone(step: Mapping[str, Any]) -> dict[str, Any] | None:
    """Project a step ``target`` into a compact zone descriptor.

    Returns ``{type, low, high, relative_low, relative_high}`` or ``None`` when
    the step has no target / a malformed one. ``type`` is the provider's metric
    (``power``/``heart_rate``/``pace``/``relative_rpe``).
    """
    target = step.get("target")
    if not isinstance(target, Mapping):
        return None
    kind = str(target.get("type") or "").strip().lower() or None
    return {
        "type": kind,
        "low": _compact_number(target.get("low")),
        "high": _compact_number(target.get("high")),
        "relative_low": _compact_relative_number(target.get("relative_low")),
        "relative_high": _compact_relative_number(target.get("relative_high")),
    }


def _compact_number(value: Any) -> int | float | None:
    """Round a scalar to at most 1 decimal; ints stay ints; junk -> None."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number.is_integer():
        return int(number)
    return round(number, 1)


def _compact_relative_number(value: Any) -> int | float | None:
    """Round a relative fraction to at most 2 decimals; junk -> None."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number.is_integer():
        return int(number)
    return round(number, 2)


def _project_step(step: Any) -> dict[str, Any] | None:
    """Project one step; return None to skip junk (not raise)."""
    if not isinstance(step, Mapping):
        return None
    duration = _compact_number(step.get("duration_seconds"))
    if duration is None or duration <= 0:
        return None
    interval = {
        "type": _step_type(step),
        "duration_seconds": duration,
        "target_zone": _target_zone(step),
        "segment_kind": str(step.get("segment_kind") or "").strip().lower() or None,
        "name": str(step.get("name") or "").strip() or None,
    }
    repeat = step.get("repeat_index")
    if repeat is not None:
        interval["repeat_index"] = _compact_number(repeat)
    return interval


def project_planned_intervals(
    session: Mapping[str, Any],
    *,
    sport: str | None | object = _UNSET,
    activity_lineage: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Project a planned session's ``materialized_steps`` (and brick ``legs``).

    Returns a flat ordered list of compact intervals
    ``{type, duration_seconds, target_zone, segment_kind, name, repeat_index?}``.
    Brick legs are concatenated in order for the parent/reconciliation path.
    When ``sport`` or ``activity_lineage`` is supplied, an activity-card path
    selects exactly one proven composite leg; an ambiguous or missing selection
    returns an empty list. Empty when the session has no steps (e.g.
    unstructured/free activities). Raises ``ValueError`` only when the session
    itself is not a mapping.
    """
    if not isinstance(session, Mapping):
        raise ValueError("planned session must be a mapping")

    if sport is not _UNSET or activity_lineage is not None:
        if _is_composite_session(session):
            selected = _select_composite_leg(
                session,
                sport=None if sport is _UNSET else sport,
                lineage=activity_lineage,
            )
            if selected is None:
                return []
            return [
                interval
                for interval in (
                    _project_step(step)
                    for step in list(selected.get("materialized_steps") or [])
                )
                if interval
            ]

        # A non-composite plan must not be compared with an activity from a
        # different discipline. This is the same fail-closed boundary used for
        # ambiguous composite legs; callers can still render a substitution
        # from the parent match without fabricating interval evidence.
        planned_sport = _sport_key(session.get("sport"))
        actual_sport = _sport_key(None if sport is _UNSET else sport)
        if actual_sport is None or (
            planned_sport is not None and planned_sport != actual_sport
        ):
            return []

    steps_source: list[Any] = []
    direct = session.get("materialized_steps")
    if isinstance(direct, list):
        steps_source.extend(direct)

    legs = session.get("legs")
    if isinstance(legs, list):
        for leg in legs:
            if isinstance(leg, Mapping):
                leg_steps = leg.get("materialized_steps")
                if isinstance(leg_steps, list):
                    steps_source.extend(leg_steps)

    return [interval for interval in (_project_step(s) for s in steps_source) if interval]


def planned_intervals_for_match(
    match: Any,
    checkpoint_data: Any,
    *,
    activity_sport: str | None | object = _UNSET,
    activity_lineage: Mapping[str, Any] | None = None,
    sport: str | None | object = _UNSET,
) -> list[dict[str, Any]] | None:
    """Planned intervals for one plan-actual match (#383, read-time recovery).

    Fresh snapshots (created after #383-M2) carry ``planned_snapshot.intervals``
    and win for the parent/reconciliation path. The activity-card path passes
    ``activity_sport`` (and optional explicit ``activity_lineage``), recovers the
    session from the checkpoint, and projects only the selected leg. Legacy
    snapshots (before #383) don't carry intervals, so we recover the session
    from the checkpoint by ``session_id`` (exact) then by date. Returns ``None``
    when unrecoverable or when leg evidence is ambiguous — the card then hides
    plan-vs-fact instead of showing a cross-sport comparison.
    """
    if not isinstance(match, Mapping):
        return None
    snapshot = match.get("planned_snapshot")
    if not isinstance(snapshot, Mapping):
        return None

    # ``sport`` is a small compatibility alias for internal callers that use
    # the same name as ``project_planned_intervals``. Omitted arguments retain
    # the historical parent projection behavior; an explicit ``None`` is
    # meaningful for an activity card and therefore must fail closed.
    if activity_sport is _UNSET and sport is not _UNSET:
        activity_sport = sport
    scoped_to_activity = activity_sport is not _UNSET or activity_lineage is not None
    actual_sport = None if activity_sport is _UNSET else activity_sport

    if scoped_to_activity:
        session = _find_plan_session(snapshot, checkpoint_data)
        if session is not None:
            projected = project_planned_intervals(
                session,
                sport=actual_sport,
                activity_lineage=activity_lineage,
            )
            # Empty is a valid unstructured plan, but not a safe result for a
            # scoped activity card: None suppresses misleading plan-vs-fact.
            return projected or None

        # Newer/internal snapshots may carry raw leg snapshots even when the
        # checkpoint is no longer available. They are selected by the same
        # evidence gate as checkpoint sessions.
        snapshot_legs = snapshot.get("legs")
        if isinstance(snapshot_legs, list):
            snapshot_session = dict(snapshot)
            snapshot_session["legs"] = snapshot_legs
            projected = project_planned_intervals(
                snapshot_session,
                sport=actual_sport,
                activity_lineage=activity_lineage,
            )
            return projected or None

        # A flat snapshot cannot be safely split into composite legs. For a
        # scalar session, only return it when the snapshot itself proves the
        # sport is the same as the activity.
        if _is_composite_session(snapshot):
            return None
        planned_sport = _sport_key(snapshot.get("sport"))
        if _sport_key(actual_sport) is None or (
            planned_sport is not None and planned_sport != _sport_key(actual_sport)
        ):
            return None
        intervals = snapshot.get("intervals")
        return intervals if isinstance(intervals, list) else None

    intervals = snapshot.get("intervals")
    if intervals is not None:
        return intervals

    session = _find_plan_session(snapshot, checkpoint_data)
    if session is None:
        return None
    try:
        return project_planned_intervals(session)
    except ValueError:
        return None


def _find_plan_session(
    snapshot: Mapping[str, Any], checkpoint_data: Any
) -> Mapping[str, Any] | None:
    """Locate the planned session inside checkpoint data for a legacy match."""
    if not isinstance(checkpoint_data, Mapping):
        return None
    goal_plan = checkpoint_data.get("goal_plan_snapshot")
    templates = goal_plan.get("session_templates") if isinstance(goal_plan, Mapping) else None
    if not isinstance(templates, list):
        return None

    session_id = snapshot.get("session_id")
    session_date = snapshot.get("date") or snapshot.get("session_date")
    by_date: Mapping[str, Any] | None = None
    for template in templates:
        if not isinstance(template, Mapping):
            continue
        if session_id and str(template.get("session_id") or "") == str(session_id):
            return template
        # Multi-session day: the matched session lives in template["sessions"]
        # (reconciliation resolves it via iter_parent_sessions/find_planned_session).
        # Resolve it BEFORE the date fallback, which would otherwise project the
        # day-level template and produce intervals for the wrong session.
        for session in list(template.get("sessions") or []):
            if (
                isinstance(session, Mapping)
                and session_id
                and str(session.get("session_id") or "") == str(session_id)
            ):
                return session
        if (
            by_date is None
            and session_date
            and str(template.get("date") or "") == str(session_date)
        ):
            by_date = template
    return by_date


def planned_leg_summary_for_match(
    match: Any,
    checkpoint_data: Any,
    *,
    activity_sport: Any,
    activity_lineage: Mapping[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Return the selected leg's prescribed duration/TSS for an activity card."""
    if not isinstance(match, Mapping):
        return None
    snapshot = match.get("planned_snapshot")
    if not isinstance(snapshot, Mapping):
        return None
    session = _find_plan_session(snapshot, checkpoint_data) or snapshot
    selected: Mapping[str, Any] | None
    if _is_composite_session(session):
        selected = _select_composite_leg(
            session,
            sport=activity_sport,
            lineage=activity_lineage,
        )
    else:
        planned_sport = _sport_key(session.get("sport"))
        selected = (
            session
            if _sport_key(activity_sport) is not None
            and (planned_sport is None or planned_sport == _sport_key(activity_sport))
            else None
        )
    if selected is None:
        return None
    raw_steps = selected.get("materialized_steps")
    steps = raw_steps if isinstance(raw_steps, list) else []
    duration = _compact_number(selected.get("duration_minutes"))
    if duration is None and steps:
        seconds = sum(
            float(value)
            for step in steps
            if isinstance(step, Mapping)
            and (value := _compact_number(step.get("duration_seconds"))) is not None
        )
        duration = round(seconds / 60.0, 1) if seconds > 0 else None
    tss = _compact_number(
        selected.get("target_tss")
        if selected.get("target_tss") is not None
        else selected.get("total_tss")
        if selected.get("total_tss") is not None
        else selected.get("tss")
    )
    return {
        "sport": _sport_key(selected.get("sport")),
        "planned_duration_minutes": duration,
        "planned_tss": tss,
    }


__all__ = [
    "planned_intervals_for_match",
    "planned_leg_summary_for_match",
    "project_planned_intervals",
]
