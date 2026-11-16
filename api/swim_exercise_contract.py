"""Explicit catalog DTOs; technique definitions and assignment metres are distinct."""

from typing import Annotated
from uuid import UUID
from pydantic import BaseModel, Field, StrictBool, StrictInt, StrictStr, model_validator
from api.swim_program_contract import RequestModel
from models.swim_exercise import SwimExerciseDocument
from models.swim_program import Identifier, Metres, SwimStep


class SwimExercisePreviewRequest(RequestModel):
    document: SwimExerciseDocument


class SwimExercisePreviewResponse(BaseModel):
    document: SwimExerciseDocument
    fingerprint: str


class SwimExerciseConfirmRequest(SwimExercisePreviewRequest):
    fingerprint: Annotated[StrictStr, Field(pattern=r"^[0-9a-f]{64}$")]
    base_revision: Annotated[StrictInt, Field(ge=0)]
    request_id: UUID
    confirm: StrictBool

    @model_validator(mode="after")
    def explicit_confirmation(self) -> "SwimExerciseConfirmRequest":
        if self.confirm is not True:
            raise ValueError("explicit confirmation required")
        return self


class SwimExerciseVersionResponse(SwimExercisePreviewResponse):
    exercise_id: UUID
    revision: int
    confirmed_at: str


class SwimExerciseListResponse(BaseModel):
    items: list[SwimExerciseVersionResponse]


class SwimExerciseResolveRequest(RequestModel):
    exercise_id: UUID
    revision: Annotated[StrictInt, Field(ge=1)]
    node_id: Identifier
    distance_meters: Metres
    instructions: Annotated[StrictStr, Field(max_length=500)] = ""


class SwimExerciseResolveResponse(BaseModel):
    exercise: SwimExerciseVersionResponse
    step: SwimStep
