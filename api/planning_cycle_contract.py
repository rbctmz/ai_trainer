"""Explicit cycle reads and identity-bearing commands; no implicit activation."""
from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator, model_validator

EventOutcome = Literal["unspecified", "did_not_participate", "participated"]
CycleScope = Literal["athlete", "cycle"]


class CycleExpectedRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_cycle_id: UUID | None
    expected_cycle_revision: int | None = Field(ge=1, strict=True)
    expected_selection_revision: int = Field(ge=0, strict=True)


class CycleRestoreRequest(CycleExpectedRequest):
    expected_cycle_id: UUID
    expected_cycle_revision: int = Field(ge=1, strict=True)
    action: Literal["restore_version", "restore_legacy_version"] = "restore_version"


class CycleEvent(BaseModel):
    model_config = ConfigDict(extra="allow")
    event_key: str
    outcome: EventOutcome
    is_ambiguous: bool
    date: str | None = None
    label: str | None = None
    priority: str | None = None


class CycleWeek(BaseModel):
    number: int
    phase: str | None
    week_start: str | None
    weekly_tss: float | None
    is_historical: bool


class CycleContext(BaseModel):
    model_config = ConfigDict(extra="forbid")
    state: Literal["no_current", "scheduled", "in_progress", "period_ended", "closed", "indeterminate"]
    cycle_id: str | None
    is_selected: bool
    current_cycle_id: str | None
    selection_revision: int
    cycle_revision: int | None
    checkpoint_id: int | None
    start_date: str | None
    end_date: str | None
    athlete_day: str
    athlete_timezone: str
    is_legacy: bool
    has_history: bool
    reason_code: str | None
    allowed_actions: list[Literal["start_new", "browse_history", "close", "edit_current", "inspect", "set_event_outcome"]]
    events: list[CycleEvent]
    current_week: CycleWeek | None
    last_week: CycleWeek | None


class CycleHistoryResponse(BaseModel):
    cycles: list[CycleContext]


class BuildLifecycle(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["start_new", "edit_current"]
    source_cycle_id: UUID | None
    target_cycle_id: UUID
    base_cycle_revision: int | None
    base_selection_revision: int
    base_checkpoint_id: int
    start_date: str
    end_date: str
    closes_cycle_id: UUID | None


class CycleBuildInputs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start_date: str
    calendar_week_start: str
    goal_type: str | None
    distance: str | None
    intent: str | None
    planning_mode: str | None
    focus: str | None
    horizon_weeks: int | None
    event_date: str | None
    events: list[dict[str, Any]]
    manual_phases: list[str] | None
    available_hours: float | None
    available_days: list[str]
    demand: str | None


class CycleBuildContext(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["start_new", "edit_current"]
    inputs: CycleBuildInputs
    input_sources: dict[str, str]
    cycle_context: CycleContext


class CycleBuildRequest(BaseModel):
    action: Literal["start_new", "edit_current"] | None = None
    base_cycle_id: UUID | None = None
    base_cycle_revision: int | None = Field(default=None, ge=1, strict=True)
    base_selection_revision: int | None = Field(default=None, ge=0, strict=True)
    replace_current_cycle: StrictBool | None = None
    start_date: str | None = None

    @model_validator(mode="after")
    def explicit_context(self) -> CycleBuildRequest:
        if self.action is not None and not {
            "base_cycle_id", "base_cycle_revision", "base_selection_revision",
            "base_checkpoint_id", "replace_current_cycle", "start_date",
        }.issubset(self.model_fields_set):
            raise ValueError("Complete lifecycle context required")
        return self


class CycleCommandRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    command_id: UUID
    confirm: StrictBool

    @field_validator("confirm")
    @classmethod
    def confirmed(cls, value: bool) -> bool:
        if value is not True:
            raise ValueError("Explicit confirmation required")
        return value


class EventDeclaration(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_key: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    outcome: EventOutcome


class CloseCycleRequest(CycleCommandRequest):
    expected_selection_revision: int = Field(ge=0, strict=True)
    expected_cycle_revision: int = Field(ge=1, strict=True)
    expected_checkpoint_id: int | None = Field(ge=1, strict=True)
    event_outcomes: list[EventDeclaration] = Field(default_factory=list, max_length=100)

    @field_validator("event_outcomes")
    @classmethod
    def unique_events(cls, values: list[EventDeclaration]) -> list[EventDeclaration]:
        if len({item.event_key for item in values}) != len(values):
            raise ValueError("Duplicate event declaration")
        return sorted(values, key=lambda item: item.event_key)


class SetEventOutcomeRequest(CycleCommandRequest, EventDeclaration):
    expected_cycle_revision: int = Field(ge=1, strict=True)


class ResolveConstraintScopeRequest(CycleCommandRequest):
    constraint_id: int = Field(ge=1, strict=True)
    expected_constraint_fingerprint: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    scope: CycleScope
    cycle_id: UUID | None = None

    @model_validator(mode="after")
    def ownership(self) -> ResolveConstraintScopeRequest:
        if (self.scope == "cycle") != (self.cycle_id is not None):
            raise ValueError("Cycle ID is required only for cycle scope")
        return self


class OutcomeChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_key: str
    checkpoint_id: int
    event_snapshot: dict[str, Any]
    before: EventOutcome
    after: EventOutcome


class ConstraintScopeChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    constraint_id: int
    before_fingerprint: str
    after_fingerprint: str
    scope: CycleScope
    cycle_id: str | None


class CycleCommandResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    effect: Literal["closed", "event_outcome_set", "constraint_scope_resolved"]
    cycle_id: str | None
    cycle_revision: int | None
    checkpoint_id: int | None
    selection_revision: int
    event_outcomes: list[OutcomeChange]
    constraint_scope: ConstraintScopeChange | None


class CycleCommandResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    command_id: str
    kind: Literal["close", "set_event_outcome", "resolve_constraint_scope"]
    replayed: bool
    result: CycleCommandResult
    current_context: CycleContext


