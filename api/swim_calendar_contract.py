"""Typed projections for calendar preview, confirmation and historical read."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import StrictBool, field_validator

from api.backup_contract import BackupStatus
from models.swim_calendar import CalendarModel, LocalDay, Revision, SwimCalendarAssignment


class SwimCalendarRow(SwimCalendarAssignment):
    origin: Literal["trainer_authored"]
    title: str
    source_week_label: str | None
    environment: Literal["pool", "open_water"]
    pool_length_meters: int | None
    distance_meters: int | None
    known_distance_meters: int
    distance_compatibility: Literal["compatible", "incompatible", "not_applicable"]
    duration_minutes: None
    tss: None


class SwimCalendarRead(CalendarModel):
    cycle_id: UUID | None
    checkpoint_id: Revision | None
    assignments: list[SwimCalendarRow]


class SwimCalendarChange(CalendarModel):
    before: SwimCalendarRow | None
    after: SwimCalendarRow | None


class SwimCalendarWarning(CalendarModel):
    date: LocalDay
    code: Literal["load_uncertain", "other_sessions_on_day"]


class SwimCalendarPreview(CalendarModel):
    preview_id: UUID
    cycle_id: UUID
    base_checkpoint_id: Revision
    expires_at: datetime
    changes: list[SwimCalendarChange]
    warnings: list[SwimCalendarWarning]


class SwimCalendarConfirm(CalendarModel):
    preview_id: UUID
    confirm: StrictBool

    @field_validator("confirm")
    @classmethod
    def affirmative(cls, value: bool) -> bool:
        if not value:
            raise ValueError("explicit confirmation required")
        return value


class SwimCalendarReceipt(CalendarModel):
    cycle_id: UUID
    checkpoint_id: Revision
    preview_id: UUID
    backup: BackupStatus
