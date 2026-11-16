"""Versioned trainer-authored swim documents; no scheduling or load inference."""
from __future__ import annotations

import hashlib
import json
from typing import Annotated, Any, Literal, Union
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, field_validator, model_validator

Identifier = Annotated[StrictStr, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")]
Name = Annotated[StrictStr, Field(min_length=1, max_length=200)]
Instructions = Annotated[StrictStr, Field(max_length=3000)]
Metres = Annotated[StrictInt, Field(gt=0, le=100000)]


class DocumentPart(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @field_validator("name", "title", check_fields=False)
    @classmethod
    def nonblank_name(cls, value: str) -> str:
        if not value.strip() or "\x00" in value:
            raise ValueError("nonblank name without NUL required")
        return value


class SubjectiveEffort(DocumentPart):
    kind: Literal["subjective"] = "subjective"
    start_percent: Annotated[StrictInt, Field(ge=0, le=100)]
    end_percent: Annotated[StrictInt, Field(ge=0, le=100)]

    @model_validator(mode="after")
    def ordered(self) -> SubjectiveEffort:
        if self.end_percent < self.start_percent:
            raise ValueError("subjective effort progression must be ordered")
        return self


class SwimStep(DocumentPart):
    kind: Literal["swim"]
    id: Identifier
    name: Name
    distance_meters: Metres
    instructions: Instructions = ""
    stroke: Literal["freestyle", "backstroke", "breaststroke", "butterfly", "mixed", "drill", "unspecified"] = "unspecified"
    equipment: Annotated[list[Literal["fins", "pull_buoy", "kickboard", "paddles", "snorkel", "other"]], Field(max_length=6)] = Field(default_factory=list)
    effort: SubjectiveEffort | None = None

    @field_validator("equipment")
    @classmethod
    def unique_equipment(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("equipment must be unique")
        return value


class RestStep(DocumentPart):
    kind: Literal["rest"]
    id: Identifier
    mode: Literal["fixed", "approximate", "open"]
    seconds: Annotated[StrictInt, Field(gt=0, le=86400)] | None = None
    breaths: Annotated[StrictInt, Field(gt=0, le=100)] | None = None
    instructions: Instructions = ""

    @model_validator(mode="after")
    def clock_semantics(self) -> RestStep:
        if self.mode == "open":
            if self.seconds is not None:
                raise ValueError("open rest has no prescribed seconds")
        elif self.seconds is None or self.breaths is not None:
            raise ValueError("timed rest requires seconds and has no breath conversion")
        return self


class SwimGroup(DocumentPart):
    kind: Literal["group"]
    id: Identifier
    name: Name
    repetitions: Annotated[StrictInt, Field(ge=1, le=100)]
    steps: Annotated[list[SwimNode], Field(min_length=1, max_length=100)]
    instructions: Instructions = ""
    last_rest: Literal["include", "omit", "unspecified"] = "unspecified"
    effort: SubjectiveEffort | None = None

    @model_validator(mode="after")
    def trailing_rest(self) -> SwimGroup:
        if self.last_rest != "unspecified" and not isinstance(self.steps[-1], RestStep):
            raise ValueError("last_rest policy requires a trailing rest node")
        return self


SwimNode = Annotated[Union[SwimStep, RestStep, SwimGroup], Field(discriminator="kind")]
SwimGroup.model_rebuild()


class SwimWorkout(DocumentPart):
    id: Identifier
    title: Name
    environment: Literal["pool", "open_water"]
    pool_length_meters: Annotated[StrictInt, Field(ge=10, le=100)] | None = None
    steps: Annotated[list[SwimNode], Field(min_length=1, max_length=100)]

    @model_validator(mode="after")
    def environment_context(self) -> SwimWorkout:
        if (self.environment == "pool") != (self.pool_length_meters is not None):
            raise ValueError("pool requires its length; open water has no pool length")
        return self


class SwimProgramDocument(DocumentPart):
    schema_version: Literal[1]
    origin: Literal["trainer_authored"]
    id: UUID
    title: Name
    source_text: Annotated[StrictStr, Field(min_length=1, max_length=50000)]
    source_week_label: Name | None = None
    source_label: Name | None = None
    workouts: Annotated[list[SwimWorkout], Field(min_length=1, max_length=30)]

    @field_validator("schema_version", mode="before")
    @classmethod
    def exact_version(cls, value: Any) -> Any:
        if type(value) is not int:
            raise ValueError("integer schema version required")
        return value

    @field_validator("title", "source_text", "source_week_label", "source_label")
    @classmethod
    def preserve_nonblank_source(cls, value: str | None) -> str | None:
        if value is not None and (not value.strip() or "\x00" in value):
            raise ValueError("nonblank text without NUL required")
        return value

    @model_validator(mode="before")
    @classmethod
    def bounded_raw_tree(cls, value: Any) -> Any:
        if not isinstance(value, dict) or not isinstance(value.get("workouts"), list):
            return value
        if len(value["workouts"]) > 30:
            raise ValueError("workout limit exceeded")
        stack: list[tuple[Any, int]] = [(w, 0) for w in value["workouts"]]
        count = 0
        while stack:
            part, depth = stack.pop()
            count += int(depth > 0)
            if count > 1000 or depth > 6:
                raise ValueError("program tree limit exceeded")
            if isinstance(part, dict) and isinstance(part.get("steps"), list):
                if len(part["steps"]) > 100:
                    raise ValueError("step list limit exceeded")
                stack.extend((step, depth + 1) for step in part["steps"])
        return value

    @model_validator(mode="after")
    def bounded_identities(self) -> SwimProgramDocument:
        seen: set[str] = set()
        expanded = 0

        def visit(part: SwimNode, multiplier: int) -> None:
            nonlocal expanded
            if part.id in seen:
                raise ValueError("program node identities must be unique")
            seen.add(part.id)
            expanded += multiplier
            if expanded > 10000:
                raise ValueError("expanded program limit exceeded")
            if isinstance(part, SwimGroup):
                for child in part.steps:
                    visit(child, multiplier * part.repetitions)

        for workout in self.workouts:
            if workout.id in seen:
                raise ValueError("program identities must be unique")
            seen.add(workout.id)
            for step in workout.steps:
                visit(step, 1)
        if summarize_program(self)["distance_meters"] > 1000000:
            raise ValueError("program distance limit exceeded")
        return self


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def document_fingerprint(document: SwimProgramDocument) -> str:
    return hashlib.sha256(canonical_json(document.model_dump(mode="json")).encode()).hexdigest()


def summarize_program(document: SwimProgramDocument) -> dict[str, Any]:
    """Exact distance only; unknown clocks/effort never become invented load."""
    warnings: list[dict[str, str]] = []
    workouts = []
    for workout in document.workouts:
        compatible = True

        def metres(node: SwimNode) -> int:
            nonlocal compatible
            if isinstance(node, SwimStep):
                if workout.pool_length_meters and node.distance_meters % workout.pool_length_meters:
                    compatible = False
                    warnings.append({"code": "pool_distance_not_multiple", "workout_id": workout.id, "node_id": node.id})
                return node.distance_meters
            if isinstance(node, SwimGroup):
                if node.repetitions > 1 and isinstance(node.steps[-1], RestStep) and node.last_rest == "unspecified":
                    warnings.append({"code": "last_rest_unspecified", "workout_id": workout.id, "node_id": node.id})
                return node.repetitions * sum(metres(child) for child in node.steps)
            return 0

        total = sum(metres(node) for node in workout.steps)
        workouts.append({"workout_id": workout.id, "distance_meters": total,
                         "compatibility": ("compatible" if compatible else "incompatible") if workout.environment == "pool" else "not_applicable"})
    return {"distance_meters": sum(w["distance_meters"] for w in workouts),
            "duration_seconds": None, "tss": None, "workouts": workouts, "warnings": warnings}
