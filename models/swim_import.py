"""Explicit source capture, initial interpretation and one bounded draft edit."""

from __future__ import annotations

from typing import Annotated, Literal, Union
from uuid import UUID

from pydantic import Field, StrictInt, StrictStr, field_validator

from models.swim_program import DocumentPart, Identifier, Instructions, Name
from models.swim_program_v2 import (
    CountRepeat,
    IntegerRange,
    SourceSpan,
    Spans,
    SwimNodeV2,
    SwimQuantity,
    SwimWorkoutV2,
    TimedRepeat,
)

Revision = Annotated[StrictInt, Field(ge=0)]


class CaptureSource(DocumentPart):
    request_id: UUID
    source_text: Annotated[StrictStr, Field(min_length=1, max_length=50000)]
    source_label: Name | None = None
    source_week_label: Name | None = None

    @field_validator("source_text", "source_label", "source_week_label")
    @classmethod
    def nonblank(cls, value: str | None) -> str | None:
        if value is not None and (not value.strip() or "\x00" in value):
            raise ValueError("nonblank source without NUL required")
        return value


class ExerciseReference(DocumentPart):
    node_id: Identifier
    exercise_id: UUID
    revision: Annotated[StrictInt, Field(ge=1)]


class InitialContent(DocumentPart):
    title: Name
    source_spans: Spans = Field(default_factory=list)
    workouts: Annotated[list[SwimWorkoutV2], Field(min_length=1, max_length=30)]
    exercise_references: Annotated[list[ExerciseReference], Field(max_length=1000)] = (
        Field(default_factory=list)
    )


class ParseDraft(DocumentPart):
    expected_revision: Revision
    request_id: UUID
    content: InitialContent


class SetRest(DocumentPart):
    op: Literal["set_rest"]
    node_id: Identifier
    mode: Literal["fixed", "approximate", "open"]
    seconds: IntegerRange | None = None
    breaths: IntegerRange | None = None


class SetQuantity(DocumentPart):
    op: Literal["set_quantity"]
    node_id: Identifier
    quantity: SwimQuantity


class SetInstructions(DocumentPart):
    op: Literal["set_instructions"]
    node_id: Identifier
    instructions: Instructions


class SetRepeat(DocumentPart):
    op: Literal["set_repeat"]
    node_id: Identifier
    repeat: Annotated[Union[CountRepeat, TimedRepeat], Field(discriminator="kind")]


class SetTitle(DocumentPart):
    op: Literal["set_title"]
    title: Name
    workout_id: Identifier | None = None


class SetContext(DocumentPart):
    op: Literal["set_context"]
    workout_id: Identifier
    environment: Literal["pool", "open_water"]
    pool_length_meters: Annotated[StrictInt, Field(ge=10, le=100)] | None = None


class SetBinding(DocumentPart):
    op: Literal["set_binding"]
    node_id: Identifier
    reference: ExerciseReference | None


class AddNode(DocumentPart):
    op: Literal["add_node"]
    parent_id: Identifier
    index: Annotated[StrictInt, Field(ge=0, le=100)]
    node: SwimNodeV2


class RemoveNode(DocumentPart):
    op: Literal["remove_node"]
    node_id: Identifier


class MoveNode(DocumentPart):
    op: Literal["move_node"]
    node_id: Identifier
    parent_id: Identifier
    index: Annotated[StrictInt, Field(ge=0, le=100)]


class ReplaceNode(DocumentPart):
    op: Literal["replace_node", "resolve_node"]
    node_id: Identifier
    node: SwimNodeV2


class SourceAcknowledgement(DocumentPart):
    span: SourceSpan
    reason: Name

    @field_validator("reason")
    @classmethod
    def nonblank_reason(cls, value: str) -> str:
        if not value.strip() or "\x00" in value:
            raise ValueError("nonblank reason without NUL required")
        return value


class AcknowledgeSource(SourceAcknowledgement):
    op: Literal["acknowledge_source"]


PatchOperation = Annotated[
    Union[
        SetRest,
        SetQuantity,
        SetInstructions,
        SetRepeat,
        SetTitle,
        SetContext,
        SetBinding,
        AddNode,
        RemoveNode,
        MoveNode,
        ReplaceNode,
        AcknowledgeSource,
    ],
    Field(discriminator="op"),
]


class PatchDraft(DocumentPart):
    expected_revision: Revision
    request_id: UUID
    operation: PatchOperation


class PrepareDraft(DocumentPart):
    draft_revision: Revision
    base_library_revision: Revision
    request_id: UUID
