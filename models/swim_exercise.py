"""Reusable technique definitions; an assignment owns distance and resting."""

from __future__ import annotations

import hashlib
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, StrictInt, StrictStr, field_validator, model_validator
from models.swim_program import DocumentPart, Name, SwimStep, canonical_json

Equipment = Literal["fins", "pull_buoy", "kickboard", "paddles", "snorkel", "other"]
Stroke = Literal[
    "freestyle",
    "backstroke",
    "breaststroke",
    "butterfly",
    "mixed",
    "drill",
    "unspecified",
]


class ExerciseVideoCue(DocumentPart):
    source_label: Name
    start_seconds: Annotated[StrictInt, Field(ge=0, le=86400)]
    end_seconds: Annotated[StrictInt, Field(gt=0, le=86400)]

    @model_validator(mode="after")
    def ordered(self) -> ExerciseVideoCue:
        if (
            not self.source_label.strip()
            or "\x00" in self.source_label
            or self.end_seconds <= self.start_seconds
        ):
            raise ValueError("nonblank source and increasing cue times required")
        return self


class SwimExerciseDocument(DocumentPart):
    schema_version: Literal[1]
    id: UUID
    name: Name
    variant: Name
    aliases: Annotated[list[Name], Field(max_length=20)] = Field(default_factory=list)
    instructions: Annotated[StrictStr, Field(min_length=1, max_length=2000)]
    stroke: Stroke = "drill"
    equipment: Annotated[list[Equipment], Field(max_length=6)] = Field(
        default_factory=list
    )
    environments: Annotated[
        list[Literal["pool", "open_water"]], Field(min_length=1, max_length=2)
    ]
    source_label: Name | None = None
    source_text: Annotated[StrictStr, Field(max_length=6000)] | None = None
    video_cues: Annotated[list[ExerciseVideoCue], Field(max_length=20)] = Field(
        default_factory=list
    )

    @field_validator("schema_version", mode="before")
    @classmethod
    def exact_version(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError("integer schema version required")
        return value

    @field_validator("variant", "instructions", "source_label")
    @classmethod
    def nonblank(cls, value: str | None) -> str | None:
        if value is not None and (not value.strip() or "\x00" in value):
            raise ValueError("nonblank text without NUL required")
        return value

    @field_validator("aliases", "equipment", "environments")
    @classmethod
    def distinct(cls, values: list[str]) -> list[str]:
        normalized = [s.strip().casefold() for s in values]
        if any(not s or "\x00" in s for s in normalized) or len(set(normalized)) != len(
            values
        ):
            raise ValueError("distinct nonblank values required")
        return values


def exercise_fingerprint(document: SwimExerciseDocument) -> str:
    return hashlib.sha256(
        canonical_json(document.model_dump(mode="json")).encode()
    ).hexdigest()


def make_step(
    document: SwimExerciseDocument,
    *,
    node_id: str,
    distance_meters: int,
    instructions: str = "",
) -> SwimStep:
    """Copy explicit content, never infer prescription or follow a mutable head."""
    if not isinstance(instructions, str) or len(instructions) > 500:
        raise ValueError("assignment instruction limit exceeded")
    combined = f"Вариант: {document.variant}\n{document.instructions}"
    if instructions:
        combined += "\n\n" + instructions
    return SwimStep(
        kind="swim",
        id=node_id,
        name=document.name,
        distance_meters=distance_meters,
        instructions=combined,
        stroke=document.stroke,
        equipment=list(document.equipment),
    )
