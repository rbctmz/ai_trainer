"""Selected-cycle authored swim calendar commands."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query

from api.deps import get_database
from api.routers.planning_cycles import CycleRoute
from api.swim_calendar_contract import (
    SwimCalendarConfirm, SwimCalendarPreview, SwimCalendarRead, SwimCalendarReceipt,
)
from data.database import Database
from models.swim_calendar import SwimCalendarRequest
from services import swim_calendar
from services.snapshot_runtime import backup_boundary


router = APIRouter(prefix="/api/planning/swim-calendar", tags=["planning"], route_class=CycleRoute)


@router.get("", response_model=SwimCalendarRead)
def read(
    db: Database = Depends(get_database),
    checkpoint_id: Annotated[int | None, Query(ge=1)] = None,
) -> dict[str, Any]:
    return swim_calendar.read_calendar(db, checkpoint_id=checkpoint_id)


@router.post("/preview", response_model=SwimCalendarPreview)
def preview(request: SwimCalendarRequest, db: Database = Depends(get_database)) -> dict[str, Any]:
    return swim_calendar.preview_calendar(db, request)


@router.post("/confirm", response_model=SwimCalendarReceipt)
@backup_boundary("user_command", response=True)
def confirm(request: SwimCalendarConfirm, db: Database = Depends(get_database)) -> dict[str, Any]:
    return swim_calendar.confirm_calendar(db, str(request.preview_id))
