"""Project a saved trainer prescription into its exact execution order."""

from dataclasses import dataclass, replace

from models.swim_program import RestStep, SubjectiveEffort, SwimGroup, SwimNode, SwimStep
from models.swim_program_documents import ProgramDocument
from models.swim_program_v2 import (
    DistanceQuantity,
    ExerciseBinding,
    IntegerRange,
    RestStepV2,
    SubjectiveEffortV2,
    SwimGroupV2,
    SwimNodeV2,
    SwimStepV2,
    TimedRepeat,
    UnresolvedStep,
)

FR255_POOL_METERS = 25
MAX_SWIM_DELIVERY_STEPS = 100


class SwimDeliveryUnsupported(ValueError):
    def __init__(self, code: str, node_id: str):
        super().__init__(code)
        self.code = code
        self.node_id = node_id


@dataclass(frozen=True)
class SwimDeliveryRound:
    group_id: str
    name: str
    number: int
    total: int
    instructions: str
    effort: SubjectiveEffort | SubjectiveEffortV2 | None


@dataclass(frozen=True)
class SwimDeliveryStep:
    node: SwimStep | SwimStepV2 | RestStep | RestStepV2
    distance_meters: int
    exercise: ExerciseBinding | None = None
    rounds: tuple[SwimDeliveryRound, ...] = ()

    @property
    def rest_seconds(self) -> tuple[int, int] | None:
        if isinstance(self.node, (RestStep, RestStepV2)):
            return _bounds(self.node.seconds)
        return None

    @property
    def rest_breaths(self) -> tuple[int, int] | None:
        if isinstance(self.node, (RestStep, RestStepV2)):
            return _bounds(self.node.breaths)
        return None


@dataclass(frozen=True)
class SwimDeliveryWorkout:
    workout_id: str
    title: str
    pool_length_meters: int
    steps: tuple[SwimDeliveryStep, ...]
    unspecified_last_rest_group_ids: tuple[str, ...]

    @property
    def distance_meters(self) -> int:
        return sum(step.distance_meters for step in self.steps)


def _bounds(value: int | IntegerRange | None) -> tuple[int, int] | None:
    if isinstance(value, int):
        return value, value
    if value is not None:
        return value.minimum, value.maximum
    return None


def _repeat_count(group: SwimGroup | SwimGroupV2) -> int:
    if isinstance(group, SwimGroup):
        return group.repetitions
    if isinstance(group.repeat, TimedRepeat):
        raise SwimDeliveryUnsupported("unsupported_timed_repeat", group.id)
    count = group.repeat.count
    if count.minimum != count.maximum:
        raise SwimDeliveryUnsupported("unsupported_repeat_range", group.id)
    return count.minimum


def project_swim_delivery(
    document: ProgramDocument, workout_id: str, *, pool_lengths: tuple[int, ...] = (FR255_POOL_METERS,),
) -> SwimDeliveryWorkout:
    """Resolve one workout for the selected pool profile without changing its saved version."""
    workout = next((item for item in document.workouts if item.id == workout_id), None)
    if workout is None:
        raise SwimDeliveryUnsupported("workout_not_found", workout_id)
    if workout.environment != "pool":
        raise SwimDeliveryUnsupported("unsupported_environment", workout_id)
    pool = workout.pool_length_meters
    if pool is None or pool not in pool_lengths:
        raise SwimDeliveryUnsupported("unsupported_pool_length", workout_id)

    exercises = {
        item.node_id: item for item in getattr(document, "exercise_bindings", ())
    }
    unspecified_last_rest: list[str] = []

    def expand_sequence(
        nodes: list[SwimNode] | list[SwimNodeV2], *, limit: int = MAX_SWIM_DELIVERY_STEPS,
    ) -> list[SwimDeliveryStep]:
        steps: list[SwimDeliveryStep] = []
        for node in nodes:
            steps.extend(expand(node))
            if len(steps) > limit:
                raise SwimDeliveryUnsupported("step_limit", node.id)
        return steps

    def expand(node: SwimNode | SwimNodeV2) -> list[SwimDeliveryStep]:
        if isinstance(node, (SwimGroup, SwimGroupV2)):
            count = _repeat_count(node)
            omit_last = node.last_rest == "omit"
            sequence = expand_sequence(node.steps, limit=MAX_SWIM_DELIVERY_STEPS + int(omit_last))
            if len(sequence) * count - int(omit_last) > MAX_SWIM_DELIVERY_STEPS:
                raise SwimDeliveryUnsupported("step_limit", node.id)
            if (
                count > 1
                and node.last_rest == "unspecified"
                and isinstance(node.steps[-1], (RestStep, RestStepV2))
            ):
                unspecified_last_rest.append(node.id)
            result = []
            for number in range(1, count + 1):
                round_ = SwimDeliveryRound(node.id, node.name, number, count, node.instructions, node.effort)
                kept = sequence[:-1] if omit_last and number == count else sequence
                result.extend(replace(step, rounds=(round_, *step.rounds)) for step in kept)
            return result
        if isinstance(node, (RestStep, RestStepV2)):
            return [SwimDeliveryStep(node, 0)]
        if isinstance(node, UnresolvedStep):
            raise SwimDeliveryUnsupported("unresolved_step", node.id)
        if isinstance(node, SwimStep):
            metres = node.distance_meters
        elif isinstance(node.quantity, DistanceQuantity):
            metres = node.quantity.meters
        else:
            raise SwimDeliveryUnsupported("unsupported_swim_quantity", node.id)
        if metres % pool:
            raise SwimDeliveryUnsupported("distance_not_multiple", node.id)
        return [SwimDeliveryStep(node, metres, exercises.get(node.id))]

    steps = expand_sequence(workout.steps)
    if not any(step.distance_meters for step in steps):
        raise SwimDeliveryUnsupported("no_swim_steps", workout_id)
    return SwimDeliveryWorkout(
        workout_id, workout.title, pool, tuple(steps), tuple(unspecified_last_rest),
    )
