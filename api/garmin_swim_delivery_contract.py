"""Public preview and receipt for a direct Garmin send."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from api.backup_contract import BackupStatus
from models.swim_calendar import CalendarModel, LocalDay, Revision, SwimCalendarAssignment


class GarminSwimLeaf(CalendarModel):
    type: Literal["main", "rest"]
    description: str
    distance_meters: int | None = None
    duration_seconds: int | None = None
    stroke: str | None = None
    drill: str | None = None
    equipment: str | None = None


class GarminSwimGroup(CalendarModel):
    type: Literal["repeat"]
    repetitions: int
    skip_last_rest: bool
    steps: list[GarminSwimLeaf]


class GarminSwimPreview(CalendarModel):
    preview_id: UUID
    checkpoint_id: Revision
    assignment: SwimCalendarAssignment
    expires_at: datetime
    name: str
    pool_length_meters: int
    schedule_date: LocalDay
    steps: list[GarminSwimLeaf | GarminSwimGroup]
    distance_meters: int
    fixed_rest_count: int
    fixed_rest_seconds: int


class GarminSwimReceipt(CalendarModel):
    preview_id: UUID
    assignment_id: UUID
    target_date: LocalDay
    status: Literal["scheduled", "workout_verified", "uploaded_unverified", "uncertain"]
    workout_id: int | None
    workout_url: str | None
    workout_verified: bool
    calendar_verified: bool
    device_verified: Literal[False]


class GarminSwimConfirmed(GarminSwimReceipt):
    backup: BackupStatus


class GarminSwimRead(CalendarModel):
    enabled: bool
    receipt: GarminSwimReceipt | None
