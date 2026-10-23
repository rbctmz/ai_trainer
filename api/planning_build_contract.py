"""HTTP models for the reviewed, server-owned build confirmation protocol."""

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, StrictBool, field_validator
from api.planning_cycle_contract import BuildLifecycle
from api.planning_entry_contract import DeclaredEntryDose, EntryDoseAdjustment, EntryLoadAssessment, EntrySport, HistoryCoverage


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
    history_coverage: HistoryCoverage | None = None
    initial_dose_limits: dict[EntrySport, DeclaredEntryDose] | None = None


class BuildConfirmation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    protocol_version: Literal[1]
    preview_id: UUID
    expires_at: str
    status: Literal["pending", "applied"]
    replayed: bool
    is_current: bool | None


class BuildReadinessScope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start_date: str
    end_date: str


class BuildReadinessReason(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: Literal[
        "prescription_missing",
        "prescription_infeasible",
        "target_semantics_unverified",
        "load_inconsistent",
        "duration_inconsistent",
        "availability_exceeded",
    ]
    date: str | None
    session_id: str | None
    leg_index: int | None
    field: str
    expected: Any
    observed: Any


class BuildReadiness(BaseModel):
    model_config = ConfigDict(extra="forbid")
    policy_version: Literal["plan-build-readiness-v1"] | None
    status: Literal["ready", "blocked", "unassessed"]
    can_confirm: bool
    scope: BuildReadinessScope | None
    assessed_session_count: int
    candidate_fingerprint: str | None
    blockers: list[BuildReadinessReason]
    warnings: list[BuildReadinessReason]
    training_suitability: Literal["not_assessed"]


class BuildProtocolError(BaseModel):
    detail: str
    code: str
    retryable: bool


class BuildReadinessError(BaseModel):
    detail: str
    code: Literal["plan_not_ready"]
    retryable: bool
    build_readiness: BuildReadiness


class PlanComparisonScope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start_date: str
    end_date: str


class PlanComparisonParameters(BaseModel):
    model_config = ConfigDict(extra="forbid")
    goal_type: str | None
    distance: str | None
    planning_mode: str | None
    intent: str | None
    focus: str | None
    demand: str | None
    available_hours: float | None
    available_days: list[str] | None
    events: list[dict[str, Any]] | None


class PlanComparisonSide(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scope: PlanComparisonScope | None
    parameters: PlanComparisonParameters
    total_tss: int | None
    peak_tss: int | None
    schedule_status: Literal["complete", "partial", "unavailable"]
    reasons: list[str]


class PlanComparisonStep(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None
    intensity: str | None
    segment_kind: str | None
    duration_seconds: float | None
    target: Any


class PlanComparisonSession(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: str | None
    sport: str | None
    role: str | None
    focus: str | None
    name: str | None
    minutes: float | None
    tss: float | None
    transition_minutes: float | None
    materialization_status: str | None
    structure_status: str | None
    steps: list[PlanComparisonStep] | None
    legs: list["PlanComparisonSession"] | None


class PlanComparisonDayValue(BaseModel):
    model_config = ConfigDict(extra="forbid")
    state: Literal["scheduled", "rest", "outside", "unknown"]
    phase: str | None
    tss: float | None
    sessions: list[PlanComparisonSession] | None


class PlanComparisonDay(BaseModel):
    model_config = ConfigDict(extra="forbid")
    date: str
    change: Literal["added", "removed", "changed", "unchanged", "unknown"]
    before: PlanComparisonDayValue
    after: PlanComparisonDayValue


class PlanComparisonCounts(BaseModel):
    model_config = ConfigDict(extra="forbid")
    added: int
    removed: int
    changed: int
    unchanged: int
    unknown: int


class PlanBuildComparison(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: Literal["plan-comparison-v1"]
    status: Literal["complete", "partial", "no_baseline"]
    base_checkpoint_id: int | None
    base_cycle_id: str | None
    base_cycle_revision: int | None
    before: PlanComparisonSide | None
    after: PlanComparisonSide
    days: list[PlanComparisonDay]
    counts: PlanComparisonCounts | None
    reasons: list[str]


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
    # Optional only for historical applied receipts; new pending is guarded.
    build_readiness: BuildReadiness | None = None
    # Optional only for historical receipts; M4c guards every new publication.
    entry_load: EntryLoadAssessment | None = None
    entry_adjustments: list[EntryDoseAdjustment] | None = None
    # Historical retained responses may predate comparison; not a new save gate.
    comparison: PlanBuildComparison | None = None


class BuildPreviewResponse(BuiltPlanResponse):
    parameters: BuildParametersResponse
    confirmation: BuildConfirmation


class BuildConfirmResponse(BuildPreviewResponse):
    pass


class BuildConfirmationV2(BuildConfirmation):
    protocol_version: Literal[2]


class BuildPreviewResponseV2(BuiltPlanResponse):
    parameters: BuildParametersResponse
    confirmation: BuildConfirmationV2
    lifecycle: BuildLifecycle


BuildConfirmResponseVersioned = BuildConfirmResponse | BuildPreviewResponseV2
