"""Selected-cycle authored swim calendar commands."""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from api.deps import get_database
from api.garmin_swim_delivery_contract import GarminSwimConfirmed, GarminSwimPreview, GarminSwimRead
from api.routers.planning_cycles import CycleRoute
from api.swim_calendar_contract import (
    SwimCalendarConfirm, SwimCalendarPreview, SwimCalendarRead, SwimCalendarReceipt,
)
from api.swim_delivery_contract import (
    SwimDeliveryConfirmed, SwimDeliveryPreview, SwimDeliveryRead, SwimDeliveryRequest,
)
from data.database import Database
from models.planning_build_confirmation import PlanningBuildPreviewError
from models.swim_calendar import SwimCalendarRequest
from services import garmin_swim_delivery, swim_calendar, swim_delivery
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


@router.get("/delivery", response_model=SwimDeliveryRead)
def delivery_read(assignment_id: UUID, db: Database = Depends(get_database)) -> dict[str, Any]:
    return swim_delivery.read_swim_delivery(db, assignment_id)


@router.post("/delivery/preview", response_model=SwimDeliveryPreview)
def delivery_preview(request: SwimDeliveryRequest, db: Database = Depends(get_database)) -> dict[str, Any]:
    return swim_delivery.preview_swim_delivery(
        db, request.request_id, request.assignment_id, request.expected_checkpoint_id,
    )


@router.post("/delivery/confirm", response_model=SwimDeliveryConfirmed)
@backup_boundary("user_command", response=True)
def delivery_confirm(
    request: SwimCalendarConfirm, demo: bool = Query(False), db: Database = Depends(get_database),
) -> dict[str, Any]:
    return swim_delivery.confirm_swim_delivery(db, request.preview_id, demo=demo)


@router.get("/garmin-delivery", response_model=GarminSwimRead)
def garmin_delivery_read(assignment_id: UUID, demo: bool = Query(False),
                         db: Database = Depends(get_database)) -> dict[str, Any]:
    return garmin_swim_delivery.read_garmin_swim(db, assignment_id, demo=demo)


@router.post("/garmin-delivery/preview", response_model=GarminSwimPreview)
def garmin_delivery_preview(request: SwimDeliveryRequest, demo: bool = Query(False),
                            db: Database = Depends(get_database)) -> dict[str, Any]:
    if demo:
        raise PlanningBuildPreviewError("garmin_swim_demo", "Отправка в Garmin отключена в демо-режиме.")
    return garmin_swim_delivery.preview_garmin_swim(
        db, request.request_id, request.assignment_id, request.expected_checkpoint_id,
    )


@router.post("/garmin-delivery/confirm", response_model=GarminSwimConfirmed)
@backup_boundary("user_command", response=True)
def garmin_delivery_confirm(request: SwimCalendarConfirm, demo: bool = Query(False),
                            db: Database = Depends(get_database)) -> dict[str, Any]:
    return garmin_swim_delivery.confirm_garmin_swim(db, request.preview_id, demo=demo)
