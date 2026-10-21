"""Typed M4 entry evidence; domain calculations remain in shared Python."""
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from models.planning_entry_load import normalize_entry_inputs

EntrySport = Literal["bike", "run", "swim"]


class EntryModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class HistoryCoverage(EntryModel):
    status: Literal["unknown", "partial", "user_reported_complete"]
    start_date: str | None = None
    end_date_exclusive: str | None = None

    @model_validator(mode="after")
    def valid_interval(self) -> "HistoryCoverage":
        normalize_entry_inputs(self.model_dump(), None)
        return self


class DeclaredEntryDose(EntryModel):
    source: Literal["athlete_declared"]
    weekly_minutes: float = Field(gt=0, strict=True)
    weekly_sessions: int = Field(gt=0, strict=True)
    max_session_minutes: float = Field(gt=0, strict=True)

    @model_validator(mode="after")
    def valid_dose(self) -> "DeclaredEntryDose":
        normalize_entry_inputs(None, {"run": self.model_dump()})
        return self


class EntryWindow(EntryModel):
    start_date: str
    end_date_exclusive: str


class EntryScope(EntryModel):
    start_date: str
    end_date: str


class EntryQualityLimit(EntryModel):
    code: str
    activity_id: str | None
    sport: EntrySport | None
    field: str | None


class EntryWeek(EntryWindow):
    session_count: int
    eligible_duration_session_count: int
    observed_minutes: float
    total_minutes: float | None


class EntryTSS(EntryModel):
    total: float | None
    known_session_count: int
    unknown_session_count: int
    methods: list[str]
    provenance: Literal["estimated", "measured", "mixed", "unverified"]
    coverage: Literal["complete", "partial", "missing"]


class EntryContextExposure(EntryModel):
    session_count: int
    observed_minutes: float


class SportEntryExposure(EntryModel):
    session_count: int
    eligible_duration_session_count: int
    training_days: int
    observed_minutes: float
    total_minutes: float | None
    session_minutes: list[float]
    longest_minutes: float | None
    last_exposure_date: str | None
    days_since_last: int | None
    reference_complete: bool
    bins: list[EntryWeek]
    context: EntryContextExposure
    tss: EntryTSS


class EntryCompleteness(EntryModel):
    status: Literal["unknown", "partial", "user_reported_complete"]
    source: Literal["unknown", "user_report"]
    claimed_interval: EntryWindow | None


class EntryExposureProfile(EntryModel):
    as_of: str
    timezone: str
    window_start: str
    window_end_exclusive: str
    context_start: str
    completeness: EntryCompleteness
    sports: dict[EntrySport, SportEntryExposure]
    quality_limits: list[EntryQualityLimit]


class SourcedEntryLimit(EntryModel):
    source: Literal["observed_reference", "athlete_declared"]
    weekly_minutes: float
    weekly_sessions: int
    max_session_minutes: float
    source_window: EntryWindow | None
    scope: EntryScope
    declared_ceiling: DeclaredEntryDose | None


class EntryLoadReason(EntryModel):
    code: str
    sport: EntrySport | None
    date: str | None
    field: str
    expected: Any
    observed: Any


class EntryLoadWarning(EntryModel):
    code: str
    sport: EntrySport | None
    field: str


class EntryLoadAssessment(EntryModel):
    policy_version: Literal["entry-load-v1"]
    status: Literal["supported", "needs_baseline", "blocked", "unassessed"]
    can_publish: bool
    scope: EntryScope
    profile: EntryExposureProfile
    limits: dict[EntrySport, SourcedEntryLimit]
    blockers: list[EntryLoadReason]
    warnings: list[EntryLoadWarning]
