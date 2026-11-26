"""Project one saved pool workout into a grouped Garmin MCP prescription."""

from datetime import date
from typing import Any

from models.swim_delivery import SwimDeliveryUnsupported, project_swim_delivery
from models.swim_program import RestStep, SwimGroup, SwimNode, SwimStep
from models.swim_program_documents import ProgramDocument
from models.swim_program_v2 import RestStepV2, SwimGroupV2, SwimNodeV2, SwimStepV2, TimedRepeat

_STROKES = {
    "freestyle": "free", "backstroke": "backstroke", "drill": "drill",
    "mixed": "mixed", "unspecified": "any_stroke",
}
_EQUIPMENT = {"fins", "kickboard", "paddles", "pull_buoy"}


def project_garmin_swim(
    document: ProgramDocument, workout_id: str, schedule_date: date,
) -> dict[str, Any]:
    """Keep source hierarchy and reject anything the Garmin draft cannot represent."""
    workout = next((item for item in document.workouts if item.id == workout_id), None)
    if workout is None:
        raise SwimDeliveryUnsupported("workout_not_found", workout_id)
    if workout.environment != "pool":
        raise SwimDeliveryUnsupported("unsupported_environment", workout_id)
    if workout.pool_length_meters not in {25, 50}:
        raise SwimDeliveryUnsupported("unsupported_pool_length", workout_id)
    expanded = project_swim_delivery(document, workout_id, pool_lengths=(25, 50))
    if len(workout.title.strip()) > 80:
        raise SwimDeliveryUnsupported("garmin_name_too_long", workout_id)

    leaves = {step.node.id: step for step in expanded.steps}

    def compile_leaf(node: SwimNode | SwimNodeV2) -> dict[str, Any]:
        if isinstance(node, (RestStep, RestStepV2)):
            bounds = getattr(node.seconds, "minimum", node.seconds), getattr(node.seconds, "maximum", node.seconds)
            low, high = bounds
            if node.mode != "fixed" or low is None or high != low or low > 3600:
                raise SwimDeliveryUnsupported("garmin_unsupported_rest", node.id)
            if len(node.instructions) > 200:
                raise SwimDeliveryUnsupported("garmin_cue_too_long", node.id)
            return {"type": "rest", "duration_seconds": low, "description": node.instructions}
        if not isinstance(node, (SwimStep, SwimStepV2)):
            raise SwimDeliveryUnsupported("unresolved_step", node.id)
        leaf = leaves[node.id]
        if node.effort is not None:
            raise SwimDeliveryUnsupported("garmin_unsupported_effort", node.id)
        stroke = _STROKES.get(node.stroke)
        if stroke is None:
            raise SwimDeliveryUnsupported("garmin_unsupported_stroke", node.id)
        if len(node.equipment) > 1 or set(node.equipment) - _EQUIPMENT:
            raise SwimDeliveryUnsupported("garmin_unsupported_equipment", node.id)
        cues = [node.name]
        if leaf.exercise is not None:
            exercise = leaf.exercise.document
            cues.extend((exercise.variant, exercise.instructions))
        cues.append(node.instructions)
        description = "\n".join(dict.fromkeys(cue for cue in cues if cue))
        if len(description) > 200:
            raise SwimDeliveryUnsupported("garmin_cue_too_long", node.id)
        return {"type": "main", "distance_meters": leaf.distance_meters, "description": description,
                "stroke": stroke, **({"drill": "drill"} if node.stroke == "drill" else {}),
                **({"equipment": node.equipment[0]} if node.equipment else {})}

    steps = []
    for node in workout.steps:
        if not isinstance(node, (SwimGroup, SwimGroupV2)):
            steps.append(compile_leaf(node))
            continue
        if node.instructions or node.effort is not None:
            raise SwimDeliveryUnsupported("garmin_unsupported_group_cue", node.id)
        nested = next((child for child in node.steps if isinstance(child, (SwimGroup, SwimGroupV2))), None)
        if nested is not None:
            raise SwimDeliveryUnsupported("garmin_nested_group", nested.id)
        if isinstance(node, SwimGroup):
            repeats = node.repetitions
        else:
            # project_swim_delivery has already required a fixed count.
            if isinstance(node.repeat, TimedRepeat):
                raise SwimDeliveryUnsupported("unsupported_timed_repeat", node.id)
            repeats = node.repeat.count.minimum
        trailing_rest = isinstance(node.steps[-1], (RestStep, RestStepV2))
        if trailing_rest and node.last_rest == "unspecified" and repeats > 1:
            raise SwimDeliveryUnsupported("garmin_last_rest_unspecified", node.id)
        skip = node.last_rest == "omit"
        children = [compile_leaf(child) for child in node.steps]
        if not any(child["type"] != "rest" for child in children):
            raise SwimDeliveryUnsupported("garmin_empty_swim_group", node.id)
        if repeats == 1:
            steps.extend(children[:-1] if skip else children)
        else:
            steps.append({"type": "repeat", "repetitions": repeats, "skip_last_rest": skip,
                          "steps": children})
    return {"name": workout.title.strip(), "pool_length_meters": expanded.pool_length_meters,
            "schedule_date": schedule_date.isoformat(), "steps": steps}
