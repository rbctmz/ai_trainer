"""Planning endpoints — Phase 2, "Собрать план" mode.

`GET /api/planning/status`  → current CTL/ATL/TSB + active plan checkpoint.
`POST /api/planning/build`  → build a goal plan + CTL/ATL/TSB forecast.
"""
from __future__ import annotations

from typing import Annotated, Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from api import planning_service
from api.deps import get_database
from data.database import Database

router = APIRouter(prefix="/api/planning", tags=["planning"])


class BuildRequest(BaseModel):
    goal_type: str
    distance: str
    event_date: Optional[str] = None  # YYYY-MM-DD; legacy event_goal input
    planning_mode: str = "event_goal"
    intent: str = "develop"
    focus: str = "balanced_triathlon"
    horizon_weeks: int = 8
    manual_phases: Optional[List[str]] = None
    events: Optional[List[Dict[str, Any]]] = None
    available_hours: float = 10.0
    available_days: Optional[List[str]] = None  # ["mon","tue",...]
    demand: Optional[str] = None
    persist: bool = False
    confirm: bool = False
    base_checkpoint_id: Optional[int] = None


class AdjustRequest(BaseModel):
    rows: List[Dict[str, Any]]
    weeks: int = 1
    persist: bool = True


class RebalanceRequest(BaseModel):
    as_of: Optional[str] = None
    weeks: int = 1
    base_checkpoint_id: Optional[int] = None
    preview_fingerprint: Optional[str] = None


class MatchCorrectionRequest(BaseModel):
    base_checkpoint_id: int
    session_id: str
    activity_ids: List[str] = Field(default_factory=list)
    actual_role: Optional[str] = None
    action: str = "confirm"


class DemandRequest(BaseModel):
    level: str


class DemandConfirmRequest(BaseModel):
    level: str
    base_checkpoint_id: int
    preview_fingerprint: str


class IntervalsDeliveryRequest(BaseModel):
    days: int = Field(7, ge=7, le=14)


class ConstraintRequest(BaseModel):
    date: str
    kind: str
    source: str = "coach"
    note: Optional[str] = None
    plan_id: Optional[str] = None
    session_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


def _parse_available_days(value: Optional[str]) -> Optional[List[str]]:
    if not value:
        return None
    days = [part.strip().lower() for part in value.split(",") if part.strip()]
    return days or None


@router.get("/status")
def planning_status(db: Database = Depends(get_database)) -> dict[str, Any]:
    return planning_service.current_status(db)


@router.get("/overview")
def planning_overview(db: Database = Depends(get_database)) -> dict[str, Any]:
    """Read-only active-plan projection for the Planning reader default."""
    return planning_service.active_plan_overview(db)


@router.get("/week-by-week")
def planning_week_by_week(db: Database = Depends(get_database)) -> dict[str, Any]:
    """One bounded, read-only active-plan week/day/session reader projection."""
    return planning_service.week_by_week_plan(db)


@router.get("/constraints")
def list_constraints(days: int = 30, db: Database = Depends(get_database)) -> dict[str, Any]:
    from datetime import datetime, timedelta

    today = datetime.now().date()
    rows = db.get_coach_constraints(
        start_date=today.isoformat(),
        end_date=(today + timedelta(days=max(1, int(days or 1)))).isoformat(),
        active_only=True,
        limit=200,
    )
    return {"count": len(rows), "constraints": rows}


@router.post("/constraints")
def create_constraint(req: ConstraintRequest, db: Database = Depends(get_database)) -> dict[str, Any]:
    try:
        return db.save_coach_constraint(
            date=req.date,
            kind=req.kind,
            source=req.source,
            note=req.note,
            plan_id=req.plan_id,
            session_id=req.session_id,
            metadata=req.metadata or {},
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.delete("/constraints/{constraint_id}")
def deactivate_constraint(constraint_id: int, db: Database = Depends(get_database)) -> dict[str, Any]:
    row = db.deactivate_coach_constraint(constraint_id)
    if row is None:
        raise HTTPException(status_code=404, detail="constraint not found")
    return row


@router.get("/target-preview")
def planning_target_preview(
    goal_type: str = "triathlon",
    distance: str = "olympic",
    available_hours: float = 10.0,
    available_days: Optional[str] = None,
    demand: Optional[str] = None,
    db: Database = Depends(get_database),
) -> dict[str, Any]:
    return planning_service.target_preview(
        db,
        goal_type=goal_type,
        distance=distance,
        available_hours=available_hours,
        available_days=_parse_available_days(available_days),
        demand=demand,
    )


@router.get("/demand")
def planning_get_demand(db: Database = Depends(get_database)) -> dict[str, Any]:
    return planning_service.get_demand(db)


@router.post("/demand")
def planning_set_demand(req: DemandRequest, db: Database = Depends(get_database)) -> dict[str, Any]:
    return planning_service.set_demand(db, req.level)


@router.get("/demand-preview")
def planning_demand_preview(
    level: str = "moderate",
    db: Database = Depends(get_database),
) -> dict[str, Any]:
    """Read-only expected effect of a demand change on the active plan."""
    return planning_service.demand_preview(db, level)


@router.post("/demand/confirm")
def planning_demand_confirm(
    req: DemandConfirmRequest,
    db: Database = Depends(get_database),
) -> dict[str, Any]:
    """Apply an approved demand change as a new guarded checkpoint."""
    try:
        return planning_service.confirm_demand_change(
            db,
            level=req.level,
            base_checkpoint_id=req.base_checkpoint_id,
            preview_fingerprint=req.preview_fingerprint,
        )
    except planning_service.StalePlanningCheckpointError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.post("/build")
def planning_build(req: BuildRequest, db: Database = Depends(get_database)) -> dict[str, Any]:
    if req.persist and not req.confirm:
        raise HTTPException(status_code=409, detail="Сначала просмотрите план, затем подтвердите сохранение.")
    try:
        return planning_service.build_plan(
            db,
            goal_type=req.goal_type,
            distance=req.distance,
            event_date=req.event_date,
            available_hours=req.available_hours,
            available_days=req.available_days,
            demand=req.demand,
            persist=req.persist,
            planning_mode=req.planning_mode,
            intent=req.intent,
            focus=req.focus,
            horizon_weeks=req.horizon_weeks,
            manual_phases=req.manual_phases,
            events=req.events,
            expected_base_checkpoint_id=req.base_checkpoint_id,
        )
    except planning_service.StalePlanningCheckpointError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("/events")
def planning_events(
    days: int = Query(180, ge=1, le=365),
) -> dict[str, Any]:
    from services.intervals_icu import IntervalsICUError

    try:
        return planning_service.discover_intervals_events(days=days)
    except IntervalsICUError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


# --- Export mode -----------------------------------------------------------
@router.get("/plan")
def planning_plan(db: Database = Depends(get_database)) -> dict[str, Any]:
    from services.intervals_icu import connection_info

    plan = planning_service.get_active_plan(db)
    if not plan or not plan.get("daily_plan"):
        return {
            "has_plan": False,
            "goal": None,
            "days": [],
            "delivery": connection_info(),
        }
    return {
        "has_plan": True,
        "goal": {"goal_type": plan.get("goal_type"), "distance": plan.get("distance")},
        "days": planning_service.plan_days(plan),
        "delivery": connection_info(),
    }


@router.post("/delivery/intervals")
def planning_deliver_intervals(
    req: IntervalsDeliveryRequest,
    demo: bool = False,
    db: Database = Depends(get_database),
) -> dict[str, Any]:
    if demo:
        raise HTTPException(
            status_code=409,
            detail="Demo mode cannot write to Intervals.icu",
        )
    if req.days not in {7, 14}:
        raise HTTPException(status_code=422, detail="days must be 7 or 14")
    return planning_service.deliver_intervals_plan(db, days=req.days)


@router.get("/export/ics")
def planning_export_ics(db: Database = Depends(get_database)) -> Response:
    plan = planning_service.get_active_plan(db)
    if not plan or not plan.get("daily_plan"):
        raise HTTPException(status_code=404, detail="no active plan")
    content = planning_service.export_ics(plan)
    return Response(
        content=content,
        media_type="text/calendar",
        headers={"Content-Disposition": 'attachment; filename="training_plan.ics"'},
    )


@router.get("/export/workout/{index}")
def planning_export_workout(
    index: int,
    fmt: str = Query("tcx", pattern="^(tcx|fit_csv|tcx_activity)$"),
    leg: Optional[int] = Query(None, ge=1, le=2),
    session_id: Annotated[Optional[str], Query(min_length=1)] = None,
    db: Database = Depends(get_database),
) -> Response:
    plan = planning_service.get_active_plan(db)
    if not plan or not plan.get("daily_plan"):
        raise HTTPException(status_code=404, detail="no active plan")
    try:
        result = planning_service.export_workout(
            plan,
            index,
            fmt,
            leg=leg,
            session_id=session_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return Response(
        content=result["content"],
        media_type=result["mimetype"],
        headers={"Content-Disposition": f'attachment; filename="{result["filename"]}"'},
    )


# --- Adjust mode -----------------------------------------------------------
@router.get("/reconciliation")
def planning_reconciliation(
    weeks: int = 1,
    as_of: Optional[str] = None,
    include_provider: bool = True,
    db: Database = Depends(get_database),
) -> dict[str, Any]:
    try:
        return planning_service.reconciliation_at(
            db,
            weeks=weeks,
            as_of=as_of,
            include_provider=include_provider,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.post("/reconciliation/matches")
def planning_record_match(
    req: MatchCorrectionRequest,
    db: Database = Depends(get_database),
) -> dict[str, Any]:
    try:
        return planning_service.record_plan_actual_match(
            db,
            base_checkpoint_id=req.base_checkpoint_id,
            session_id=req.session_id,
            activity_ids=req.activity_ids,
            actual_role=req.actual_role,
            action=req.action,
        )
    except planning_service.StalePlanningCheckpointError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.post("/rebalance/preview")
def planning_rebalance_preview(
    req: RebalanceRequest,
    db: Database = Depends(get_database),
) -> dict[str, Any]:
    try:
        return planning_service.preview_weekly_rebalance(
            db,
            weeks=req.weeks,
            as_of=req.as_of,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.post("/rebalance/confirm")
def planning_rebalance_confirm(
    req: RebalanceRequest,
    db: Database = Depends(get_database),
) -> dict[str, Any]:
    if req.base_checkpoint_id is None or not req.preview_fingerprint:
        raise HTTPException(status_code=422, detail="base_checkpoint_id and preview_fingerprint are required")
    try:
        return planning_service.confirm_weekly_rebalance(
            db,
            base_checkpoint_id=req.base_checkpoint_id,
            preview_fingerprint=req.preview_fingerprint,
            weeks=req.weeks,
            as_of=req.as_of,
        )
    except planning_service.StalePlanningCheckpointError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.post("/adjust")
def planning_adjust(req: AdjustRequest, db: Database = Depends(get_database)) -> dict[str, Any]:
    try:
        return planning_service.apply_adjustment(
            db, rows=req.rows, weeks=req.weeks, persist=req.persist
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("/history")
def planning_history(limit: int = 10, db: Database = Depends(get_database)) -> dict[str, Any]:
    return planning_service.planning_history(db, limit=limit)
