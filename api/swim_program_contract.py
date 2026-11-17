"""Explicit HTTP envelopes; document semantics are owned by the Python domain."""

from __future__ import annotations
from typing import Annotated, Literal, Union
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    model_validator,
)
from models.swim_program import SwimProgramDocument
from models.swim_program_v2 import SourceSpan, SwimProgramDocumentV2


class RequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SwimProgramPreviewRequest(RequestModel):
    document: SwimProgramDocument
    base_revision: Annotated[StrictInt, Field(ge=0)]


class SwimProgramConfirmRequest(RequestModel):
    preview_id: UUID
    confirm: StrictBool

    @model_validator(mode="after")
    def explicit_confirmation(self) -> SwimProgramConfirmRequest:
        if self.confirm is not True:
            raise ValueError("explicit confirmation required")
        return self


class SwimProgramWarning(BaseModel):
    code: Literal["pool_distance_not_multiple", "last_rest_unspecified"]
    workout_id: str
    node_id: str


class SwimWorkoutSummary(BaseModel):
    workout_id: str
    distance_meters: int
    compatibility: Literal["compatible", "incompatible", "not_applicable"]


class SwimProgramSummary(BaseModel):
    distance_meters: int
    duration_seconds: None
    tss: None
    workouts: list[SwimWorkoutSummary]
    warnings: list[SwimProgramWarning]


class SwimProgramPreviewResponse(BaseModel):
    preview_id: UUID
    base_revision: int
    document: SwimProgramDocument
    summary: SwimProgramSummary
    fingerprint: str
    expires_at: str


class SwimProgramVersionResponse(BaseModel):
    program_id: UUID
    revision: int
    document: SwimProgramDocument
    summary: SwimProgramSummary
    fingerprint: str
    confirmed_at: str


class SwimProgramWarningV2(BaseModel):
    code: Literal[
        "pool_distance_not_multiple",
        "last_rest_unspecified",
        "exercise_environment_mismatch",
        "unresolved_source",
        "source_not_covered",
    ]
    workout_id: str | None = None
    node_id: str | None = None


class SwimWorkoutSummaryV2(BaseModel):
    workout_id: str
    distance_meters: int | None
    known_distance_meters: int
    compatibility: Literal["compatible", "incompatible", "not_applicable"]


class SwimProgramSummaryV2(BaseModel):
    distance_meters: int | None
    known_distance_meters: int
    duration_seconds: None
    tss: None
    workouts: list[SwimWorkoutSummaryV2]
    warnings: list[SwimProgramWarningV2]
    source_gaps: list[SourceSpan]


class SwimProgramVersionResponseV2(BaseModel):
    program_id: UUID
    revision: int
    document: SwimProgramDocumentV2
    summary: SwimProgramSummaryV2
    fingerprint: str
    confirmed_at: str


SwimProgramAnyVersionResponse = Union[
    SwimProgramVersionResponse, SwimProgramVersionResponseV2
]


class SwimProgramListItem(BaseModel):
    program_id: UUID
    revision: int
    title: str
    source_week_label: str | None
    workout_count: int
    schema_version: Literal[1, 2]
    distance_meters: int | None
    known_distance_meters: int
    updated_at: str


class SwimProgramListResponse(BaseModel):
    items: list[SwimProgramListItem]
