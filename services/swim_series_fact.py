"""Produce a swim fact comparison from the stored delivery and activity evidence."""

from typing import Any, Mapping

from data.database import Database
from data.swim_program_store import get_version
from models.planning_build_confirmation import PlanningBuildPreviewError
from models.swim_delivery import SwimDeliveryRound, project_swim_delivery
from models.swim_program_documents import validate_program_document
from models.swim_series_fact import SwimSeriesFact, compare_swim_series, swim_observations
from services.swim_delivery import read_verified_swim_assignment


def _rounds(items: tuple[SwimDeliveryRound, ...]) -> list[dict[str, Any]]:
    return [
        {
            "group_id": item.group_id,
            "number": item.number,
            "total": item.total,
            "name": item.name,
            "instructions": item.instructions,
            "effort": item.effort.model_dump(mode="json") if item.effort else None,
        }
        for item in items
    ]


def _coverage(result: SwimSeriesFact) -> tuple[int, int, int]:
    return (
        result.matched_swims,
        sum(step.pace_seconds_per_100m is not None for step in result.steps),
        sum(step.planned.distance_meters == 0 and step.rest_seconds is not None for step in result.steps),
    )


def read_swim_series_fact(db: Database, cached: Any) -> dict[str, Any] | None:
    """A pairing must point to exactly one verified authored event in this DB."""
    if not isinstance(cached, Mapping) or cached.get("source") != "intervals":
        return None
    event_id = cached.get("paired_event_id")
    if type(event_id) is not int or not 0 < event_id < 2**63:
        return None

    try:
        assignment = read_verified_swim_assignment(db, event_id)
        if assignment is None:
            return None
        version = get_version(db, str(assignment.program_id), revision=assignment.program_revision)
        if version["fingerprint"] != assignment.program_fingerprint:
            return None
        plan = project_swim_delivery(validate_program_document(version["document"]), assignment.workout_id)
    except (PlanningBuildPreviewError, ValueError, KeyError, TypeError):
        return None

    raw_laps = cached.get("garmin_laps")
    raw_intervals = cached.get("intervals")
    laps = raw_laps if isinstance(raw_laps, list) else []
    intervals = raw_intervals if isinstance(raw_intervals, list) else []
    source = "garmin" if laps else "intervals" if intervals else None
    result = compare_swim_series(plan, swim_observations(laps or intervals, source=source or "intervals"))
    if source == "garmin" and intervals:
        alternate = compare_swim_series(plan, swim_observations(intervals, source="intervals"))
        if _coverage(alternate) > _coverage(result):
            source, result = "intervals", alternate

    steps = []
    for match in result.steps:
        planned = match.planned
        effort = getattr(planned.node, "effort", None)
        steps.append({
            "node_id": planned.node.id,
            "name": getattr(planned.node, "name", None),
            "instructions": planned.node.instructions,
            "equipment": list(getattr(planned.node, "equipment", [])),
            "planned_distance_meters": planned.distance_meters,
            "planned_rest_mode": getattr(planned.node, "mode", None),
            "planned_rest_seconds": planned.rest_seconds,
            "planned_rest_breaths": planned.rest_breaths,
            "effort": effort.model_dump(mode="json") if effort else None,
            "rounds": _rounds(planned.rounds),
            "observation_indices": match.observation_indices,
            "active_seconds": match.active_seconds,
            "rest_seconds": match.rest_seconds,
            "elapsed_seconds": match.elapsed_seconds,
            "pace_seconds_per_100m": match.pace_seconds_per_100m,
        })

    return {
        "assignment_id": str(assignment.assignment_id),
        "program_revision": assignment.program_revision,
        "workout_id": assignment.workout_id,
        "title": plan.title,
        "target_date": assignment.date.isoformat(),
        "planned_pool_length_meters": plan.pool_length_meters,
        "source": source,
        "used_fallback": source == "intervals",
        "planned_swims": result.planned_swims,
        "matched_swims": result.matched_swims,
        "unassigned_observations": result.unassigned_observations,
        "steps": steps,
        "rounds": [
            {
                "rounds": _rounds(round_.rounds),
                "pace_spread_seconds_per_100m": round_.pace_spread_seconds_per_100m,
            }
            for round_ in result.rounds
        ],
    }
