"""Planning endpoints — Phase 2, "Собрать план" mode.

`GET /api/planning/status`  → current CTL/ATL/TSB + active plan checkpoint.
`POST /api/planning/build`  → build a goal plan + CTL/ATL/TSB forecast.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel

from api import planning_service
from api.deps import get_database
from data.database import Database

router = APIRouter(prefix="/api/planning", tags=["planning"])


class BuildRequest(BaseModel):
    goal_type: str
    distance: str
    event_date: str  # YYYY-MM-DD
    available_hours: float = 10.0
    available_days: Optional[List[str]] = None  # ["mon","tue",...]
    demand: Optional[str] = None
    persist: bool = True


class AdjustRequest(BaseModel):
    rows: List[Dict[str, Any]]
    weeks: int = 1
    persist: bool = True


class DemandRequest(BaseModel):
    level: str


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


@router.post("/build")
def planning_build(req: BuildRequest, db: Database = Depends(get_database)) -> dict[str, Any]:
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
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


# --- Export mode -----------------------------------------------------------
@router.get("/plan")
def planning_plan(db: Database = Depends(get_database)) -> dict[str, Any]:
    plan = planning_service.get_active_plan(db)
    if not plan or not plan.get("daily_plan"):
        return {"has_plan": False, "goal": None, "days": []}
    return {
        "has_plan": True,
        "goal": {"goal_type": plan.get("goal_type"), "distance": plan.get("distance")},
        "days": planning_service.plan_days(plan),
    }


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
    db: Database = Depends(get_database),
) -> Response:
    plan = planning_service.get_active_plan(db)
    if not plan or not plan.get("daily_plan"):
        raise HTTPException(status_code=404, detail="no active plan")
    try:
        result = planning_service.export_workout(plan, index, fmt)
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
    weeks: int = 1, db: Database = Depends(get_database)
) -> dict[str, Any]:
    return planning_service.reconciliation(db, weeks=weeks)


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
