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


_WORK_INTENSITY = {"work"}
_WORK_SEGMENT = {"work", "stage"}


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
        "relative_low": _compact_number(target.get("relative_low")),
        "relative_high": _compact_number(target.get("relative_high")),
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


def project_planned_intervals(session: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Project a planned session's ``materialized_steps`` (and brick ``legs``).

    Returns a flat ordered list of compact intervals
    ``{type, duration_seconds, target_zone, segment_kind, name, repeat_index?}``.
    Brick legs are concatenated in order. Empty when the session has no steps
    (e.g. unstructured/free activities). Raises ``ValueError`` only when the
    session itself is not a mapping.
    """
    if not isinstance(session, Mapping):
        raise ValueError("planned session must be a mapping")

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
    match: Any, checkpoint_data: Any
) -> list[dict[str, Any]] | None:
    """Planned intervals for one plan-actual match (#383, read-time recovery).

    Fresh snapshots (created after #383-M2) carry ``planned_snapshot.intervals``
    and win. Legacy snapshots (before #383) don't, so we recover the session
    from the checkpoint by ``session_id`` (exact) then by date, and project its
    ``materialized_steps``. Returns ``None`` when unrecoverable — the card then
    hides the plan-vs-fact section instead of showing an empty plan.
    """
    if not isinstance(match, Mapping):
        return None
    snapshot = match.get("planned_snapshot")
    if not isinstance(snapshot, Mapping):
        return None

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


__all__ = ["planned_intervals_for_match", "project_planned_intervals"]
