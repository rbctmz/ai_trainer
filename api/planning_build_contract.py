"""HTTP models for the reviewed, server-owned build confirmation protocol."""
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, StrictBool, field_validator


class BuildConfirmRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    preview_id: UUID
    confirm: StrictBool

    @field_validator("confirm")
    @classmethod
    def must_confirm(cls, value: bool) -> bool:
        if value is not True:
            raise ValueError("explicit confirmation required")
        return value


class BuildParametersResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    goal_type: str
    distance: str
    event_date: str | None
    start_week: str
    planning_mode: Literal["event_goal", "training_goal", "manual"]
    intent: str
    focus: str
    horizon_weeks: int
    manual_phases: list[str] | None
    events: list[dict[str, Any]]
    available_hours: float
    available_days: list[str]
    demand: str
    base_checkpoint_id: int


class BuildConfirmation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    protocol_version: Literal[1]
    preview_id: UUID
    expires_at: str
    status: Literal["pending", "applied"]
    replayed: bool
    is_current: bool | None


class BuiltPlanResponse(BaseModel):
    # Legacy nested payloads stay complete: this protocol adds identity without
    # redefining or stripping existing prescriptions, audits or future additions.
    model_config = ConfigDict(extra="allow")
    plan_id: str | None
    planning_mode: Literal["event_goal", "training_goal", "manual"]
    confirmation_required: bool
    science_audit: dict[str, Any]
    preview: dict[str, Any]
    goal: dict[str, Any]
    event_overlay: dict[str, Any]
    weekly_target: dict[str, Any]
    totals: dict[str, Any]
    weeks: list[dict[str, Any]]
    forecast: dict[str, Any]


class BuildPreviewResponse(BuiltPlanResponse):
    parameters: BuildParametersResponse
    confirmation: BuildConfirmation


class BuildConfirmResponse(BuildPreviewResponse):
    pass
