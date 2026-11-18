"""Current assignment preview and observed provider delivery receipt."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from api.backup_contract import BackupStatus
from models.swim_calendar import CalendarModel, LocalDay, Revision, SwimCalendarAssignment


class SwimDeliveryRequest(CalendarModel):
    request_id: UUID
    assignment_id: UUID
    expected_checkpoint_id: Revision


class SwimDeliveryRound(CalendarModel):
    group_id: str
    name: str
    number: int
    total: int


class SwimDeliveryStep(CalendarModel):
    node_id: str
    rounds: list[SwimDeliveryRound]
    cue: str
    clock: Literal["distance", "time", "lap"]
    distance_meters: int | None
    duration_seconds: int | None
    source_rest_seconds: tuple[int, int] | None
    source_rest_breaths: tuple[int, int] | None


class SwimDeliveryPreview(CalendarModel):
    preview_id: UUID
    checkpoint_id: Revision
    cycle_id: UUID
    assignment: SwimCalendarAssignment
    target_date: LocalDay
    title: str
    pool_length_meters: int
    distance_meters: int
    expires_at: datetime
    unspecified_last_rest_group_ids: list[str]
    steps: list[SwimDeliveryStep]


class SwimDeliveryReceipt(CalendarModel):
    preview_id: UUID
    assignment_id: UUID
    target_date: LocalDay
    status: Literal["provider_verified", "provider_unverified"]
    provider_event_id: int | None
    device_verified: Literal[False]
    reason: str | None
    step_number: int | None
    observed_at: datetime


class SwimDeliveryConfirmed(SwimDeliveryReceipt):
    backup: BackupStatus


class SwimDeliveryRead(CalendarModel):
    receipt: SwimDeliveryReceipt | None
