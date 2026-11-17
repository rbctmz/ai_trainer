"""Source-bound swim prescriptions, including ranges and unknown quantities."""

from __future__ import annotations

import hashlib
from typing import Annotated, Any, Literal, Union
from uuid import UUID

from pydantic import Field, StrictInt, StrictStr, field_validator, model_validator

from models.swim_exercise import (
    Equipment,
    Stroke,
    SwimExerciseDocument,
    exercise_fingerprint,
)
from models.swim_program import DocumentPart, Identifier, Instructions, Metres, Name

Seconds = Annotated[StrictInt, Field(gt=0, le=86400)]


class SourceSpan(DocumentPart):
    """Unicode code-point offsets, never UTF-16 or normalized text offsets."""

    start: Annotated[StrictInt, Field(ge=0, le=50000)]
    end: Annotated[StrictInt, Field(gt=0, le=50000)]

    @model_validator(mode="after")
    def increasing(self) -> SourceSpan:
        if self.end <= self.start:
            raise ValueError("source span must be increasing")
        return self


Spans = Annotated[list[SourceSpan], Field(max_length=1000)]


class IntegerRange(DocumentPart):
    minimum: Annotated[StrictInt, Field(ge=1, le=86400)]
    maximum: Annotated[StrictInt, Field(ge=1, le=86400)]

    @model_validator(mode="after")
    def ordered(self) -> IntegerRange:
        if self.minimum > self.maximum:
            raise ValueError("range must be ordered")
        return self


class SubjectiveEffortV2(DocumentPart):
    kind: Literal["subjective"] = "subjective"
    start_percent: Annotated[StrictInt, Field(ge=0, le=100)]
    end_percent: Annotated[StrictInt, Field(ge=0, le=100)]
    scope: Literal["within_node", "across_repetitions"]


class DistanceQuantity(DocumentPart):
    kind: Literal["distance"]
    meters: Metres


class DurationQuantity(DocumentPart):
    kind: Literal["duration"]
    seconds: Seconds


class AttemptsQuantity(DocumentPart):
    kind: Literal["attempts"]
    count: IntegerRange
    distance_hint_meters: Metres | None = None

    @model_validator(mode="after")
    def bounded(self) -> AttemptsQuantity:
        if self.count.maximum > 100:
            raise ValueError("attempt count limit exceeded")
        return self


class OpenQuantity(DocumentPart):
    kind: Literal["open"]


SwimQuantity = Annotated[
    Union[DistanceQuantity, DurationQuantity, AttemptsQuantity, OpenQuantity],
    Field(discriminator="kind"),
]


class SourcedPart(DocumentPart):
    source_spans: Spans = Field(default_factory=list)


class SwimStepV2(SourcedPart):
    kind: Literal["swim"]
    id: Identifier
    name: Name
    quantity: SwimQuantity
    instructions: Instructions = ""
    stroke: Stroke = "unspecified"
    equipment: Annotated[list[Equipment], Field(max_length=6)] = Field(
        default_factory=list
    )
    effort: SubjectiveEffortV2 | None = None

    @field_validator("equipment")
    @classmethod
    def unique_equipment(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("equipment must be unique")
        return value


class RestStepV2(SourcedPart):
    kind: Literal["rest"]
    id: Identifier
    mode: Literal["fixed", "approximate", "open"]
    seconds: IntegerRange | None = None
    breaths: IntegerRange | None = None
    instructions: Instructions = ""

    @model_validator(mode="after")
    def clock_semantics(self) -> RestStepV2:
        if self.breaths and self.breaths.maximum > 100:
            raise ValueError("breath count limit exceeded")
        if self.mode == "open":
            if self.seconds is not None:
                raise ValueError("open rest has no prescribed seconds")
        elif self.seconds is None or self.breaths is not None:
            raise ValueError("timed rest requires seconds without breath conversion")
        elif self.mode == "fixed" and self.seconds.minimum != self.seconds.maximum:
            raise ValueError("fixed rest requires equal second bounds")
        return self


class CountRepeat(DocumentPart):
    kind: Literal["count"]
    count: IntegerRange

    @model_validator(mode="after")
    def bounded(self) -> CountRepeat:
        if self.count.maximum > 100:
            raise ValueError("repeat count limit exceeded")
        return self


class TimedRepeat(DocumentPart):
    kind: Literal["time"]
    seconds: Seconds
    finish: Literal["timer", "current_cycle"]


class SwimGroupV2(SourcedPart):
    kind: Literal["group"]
    id: Identifier
    name: Name
    repeat: Annotated[Union[CountRepeat, TimedRepeat], Field(discriminator="kind")]
    steps: Annotated[list[SwimNodeV2], Field(min_length=1, max_length=100)]
    instructions: Instructions = ""
    last_rest: Literal["include", "omit", "unspecified"] = "unspecified"
    effort: SubjectiveEffortV2 | None = None

    @model_validator(mode="after")
    def trailing_rest(self) -> SwimGroupV2:
        if self.last_rest != "unspecified" and not isinstance(
            self.steps[-1], RestStepV2
        ):
            raise ValueError("last_rest policy requires a trailing rest node")
        return self


class UnresolvedStep(SourcedPart):
    kind: Literal["unresolved"]
    id: Identifier
    instructions: Annotated[StrictStr, Field(min_length=1, max_length=3000)]
    question: Name

    @field_validator("instructions", "question")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip() or "\x00" in value:
            raise ValueError("nonblank text without NUL required")
        return value


SwimNodeV2 = Annotated[
    Union[SwimStepV2, RestStepV2, SwimGroupV2, UnresolvedStep],
    Field(discriminator="kind"),
]
SwimGroupV2.model_rebuild()


class SwimWorkoutV2(SourcedPart):
    id: Identifier
    title: Name
    environment: Literal["pool", "open_water"]
    pool_length_meters: Annotated[StrictInt, Field(ge=10, le=100)] | None = None
    steps: Annotated[list[SwimNodeV2], Field(min_length=1, max_length=100)]

    @model_validator(mode="after")
    def context(self) -> SwimWorkoutV2:
        if (self.environment == "pool") != (self.pool_length_meters is not None):
            raise ValueError("pool requires its length; open water has no pool length")
        return self


class ExerciseBinding(DocumentPart):
    node_id: Identifier
    exercise_id: UUID
    revision: Annotated[StrictInt, Field(ge=1)]
    fingerprint: Annotated[StrictStr, Field(pattern=r"^[a-f0-9]{64}$")]
    document: SwimExerciseDocument

    @model_validator(mode="after")
    def pinned_definition(self) -> ExerciseBinding:
        if (
            self.exercise_id != self.document.id
            or self.fingerprint != exercise_fingerprint(self.document)
        ):
            raise ValueError("exercise snapshot identity or fingerprint mismatch")
        return self


class SwimProgramDocumentV2(SourcedPart):
    schema_version: Literal[2]
    origin: Literal["trainer_authored"]
    id: UUID
    title: Name
    source_id: UUID
    source_text: Annotated[StrictStr, Field(min_length=1, max_length=50000)]
    source_sha256: Annotated[StrictStr, Field(pattern=r"^[a-f0-9]{64}$")]
    source_week_label: Name | None = None
    source_label: Name | None = None
    workouts: Annotated[list[SwimWorkoutV2], Field(min_length=1, max_length=30)]
    exercise_bindings: Annotated[list[ExerciseBinding], Field(max_length=1000)] = Field(
        default_factory=list
    )

    @field_validator("schema_version", mode="before")
    @classmethod
    def exact_version(cls, value: Any) -> Any:
        if type(value) is not int:
            raise ValueError("integer schema version required")
        return value

    @field_validator("source_text", "source_week_label", "source_label")
    @classmethod
    def nonblank_source(cls, value: str | None) -> str | None:
        if value is not None and (not value.strip() or "\x00" in value):
            raise ValueError("nonblank source without NUL required")
        return value

    @model_validator(mode="before")
    @classmethod
    def bounded_raw_tree(cls, value: Any) -> Any:
        if not isinstance(value, dict) or not isinstance(value.get("workouts"), list):
            return value
        if len(value["workouts"]) > 30:
            raise ValueError("workout limit exceeded")
        stack = [(w, 0) for w in value["workouts"]]
        count = 0
        while stack:
            part, depth = stack.pop()
            count += int(depth > 0)
            if count > 1000 or depth > 6:
                raise ValueError("program tree limit exceeded")
            if isinstance(part, dict) and isinstance(part.get("steps"), list):
                if len(part["steps"]) > 100:
                    raise ValueError("step list limit exceeded")
                stack.extend((child, depth + 1) for child in part["steps"])
        return value

    @model_validator(mode="after")
    def identities_and_source(self) -> SwimProgramDocumentV2:
        if hashlib.sha256(self.source_text.encode()).hexdigest() != self.source_sha256:
            raise ValueError("source fingerprint mismatch")
        seen: dict[str, SourcedPart] = {}
        expanded = 0

        def visit(part: SourcedPart, multiplier: int) -> None:
            nonlocal expanded
            for span in part.source_spans:
                if span.end > len(self.source_text):
                    raise ValueError("source span out of bounds")
            if part is not self:
                if part.id in seen:
                    raise ValueError("program identities must be unique")
                seen[part.id] = part
            if isinstance(part, SwimWorkoutV2):
                for child in part.steps:
                    visit(child, 1)
            elif isinstance(part, SwimGroupV2):
                expanded += multiplier
                repeat = (
                    part.repeat.count.maximum
                    if isinstance(part.repeat, CountRepeat)
                    else 1
                )
                for child in part.steps:
                    visit(child, multiplier * repeat)
            elif part is not self:
                expanded += multiplier
            if expanded > 10000:
                raise ValueError("expanded program limit exceeded")

        visit(self, 1)
        for workout in self.workouts:
            visit(workout, 1)
        bound: set[str] = set()
        for binding in self.exercise_bindings:
            if binding.node_id in bound or not isinstance(
                seen.get(binding.node_id), SwimStepV2
            ):
                raise ValueError("exercise must bind a unique swim node")
            bound.add(binding.node_id)
        if summarize_program_v2(self)["known_distance_meters"] > 1000000:
            raise ValueError("program distance limit exceeded")
        return self


def source_gaps(document: SwimProgramDocumentV2) -> list[dict[str, int]]:
    """Uncovered non-whitespace source, without echoing private source text."""
    spans = list(document.source_spans)

    def visit(part: SwimWorkoutV2 | SwimNodeV2) -> None:
        spans.extend(part.source_spans)
        if isinstance(part, (SwimWorkoutV2, SwimGroupV2)):
            for child in part.steps:
                visit(child)

    for workout in document.workouts:
        visit(workout)
    gaps = []
    covered_to = 0
    for span in sorted(spans, key=lambda s: (s.start, s.end)):
        if (
            span.start > covered_to
            and document.source_text[covered_to : span.start].strip()
        ):
            gaps.append({"start": covered_to, "end": span.start})
        covered_to = max(covered_to, span.end)
    if document.source_text[covered_to:].strip():
        gaps.append({"start": covered_to, "end": len(document.source_text)})
    return gaps


def summarize_program_v2(document: SwimProgramDocumentV2) -> dict[str, Any]:
    """Count only prescribed fixed metres; never estimate unknown quantities."""
    warnings: list[dict[str, str]] = []
    workouts = []
    bindings = {binding.node_id: binding for binding in document.exercise_bindings}
    for workout in document.workouts:
        compatible = True

        def metres(node: SwimNodeV2) -> tuple[int, bool]:
            nonlocal compatible

            def warn(code: str) -> None:
                warnings.append(
                    {"code": code, "workout_id": workout.id, "node_id": node.id}
                )

            if isinstance(node, SwimStepV2):
                binding = bindings.get(node.id)
                if binding and workout.environment not in binding.document.environments:
                    warn("exercise_environment_mismatch")
                if isinstance(node.quantity, DistanceQuantity):
                    value = node.quantity.meters
                    if (
                        workout.pool_length_meters
                        and value % workout.pool_length_meters
                    ):
                        compatible = False
                        warn("pool_distance_not_multiple")
                    return value, True
                return 0, False
            if isinstance(node, UnresolvedStep):
                warn("unresolved_source")
                return 0, False
            if isinstance(node, RestStepV2):
                return 0, True
            repeated = (
                isinstance(node.repeat, TimedRepeat) or node.repeat.count.maximum > 1
            )
            if (
                repeated
                and isinstance(node.steps[-1], RestStepV2)
                and node.last_rest == "unspecified"
            ):
                warn("last_rest_unspecified")
            children = [metres(child) for child in node.steps]
            if (
                isinstance(node.repeat, TimedRepeat)
                or node.repeat.count.minimum != node.repeat.count.maximum
            ):
                return 0, False
            return sum(n for n, _ in children) * node.repeat.count.minimum, all(
                exact for _, exact in children
            )

        totals = [metres(node) for node in workout.steps]
        known = sum(n for n, _ in totals)
        workouts.append(
            {
                "workout_id": workout.id,
                "distance_meters": known if all(exact for _, exact in totals) else None,
                "known_distance_meters": known,
                "compatibility": ("compatible" if compatible else "incompatible")
                if workout.environment == "pool"
                else "not_applicable",
            }
        )
    gaps = source_gaps(document)
    if gaps:
        warnings.append({"code": "source_not_covered"})
    known = sum(w["known_distance_meters"] for w in workouts)
    return {
        "distance_meters": known
        if all(w["distance_meters"] is not None for w in workouts)
        else None,
        "known_distance_meters": known,
        "duration_seconds": None,
        "tss": None,
        "workouts": workouts,
        "warnings": warnings,
        "source_gaps": gaps,
    }
