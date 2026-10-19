"""Planning endpoints — Phase 2, "Собрать план" mode.

`GET /api/planning/status`  → current CTL/ATL/TSB + active plan checkpoint.
`POST /api/planning/build`  → build a goal plan + CTL/ATL/TSB forecast.
"""
from __future__ import annotations

from typing import Annotated, Any, Dict, List, Optional, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse, Response
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator

from api.planning_build_contract import BuildConfirmRequest, BuildConfirmResponseVersioned, BuildPreviewResponseV2
from api.planning_cycle_contract import CycleBuildRequest, CycleRestoreRequest, CycleExpectedRequest
from models.planning_build_confirmation import BuildParameters, PlanningBuildPreviewError
from utils.athlete_time import athlete_local_date

from api import planning_service
from api.deps import get_database
from data.database import Database
from models.session_projection import SessionProjectionNotFoundError
from services import session_projection as session_projection_service

class PlanningRoute(APIRoute):
    """Normalize only the two build protocol routes, including body validation."""

    def get_route_handler(self):
        handler = super().get_route_handler()

        async def protocol_handler(request):
            try:
                return await handler(request)
            except RequestValidationError:
                if self.path not in {"/api/planning/build", "/api/planning/build/confirm"}:
                    raise
                is_confirm = self.path.endswith("/confirm")
                return JSONResponse(status_code=422, content={
                    "detail": "Проверьте подтверждение." if is_confirm else "Проверьте параметры плана.",
                    "code": "invalid_confirmation" if is_confirm else "invalid_build_request", "retryable": False,
                })
            except PlanningBuildPreviewError as exc:
                return JSONResponse(status_code=exc.status, content={
                    "detail": str(exc), "code": exc.code, "retryable": exc.retryable,
                    **exc.context,
                })
        return protocol_handler


router = APIRouter(prefix="/api/planning", tags=["planning"], route_class=PlanningRoute)


class BuildRequest(CycleBuildRequest):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    goal_type: str
    distance: str
    event_date: Optional[str] = None  # YYYY-MM-DD; legacy event_goal input
    start_week: Optional[str] = None  # YYYY-MM-DD; preserved plan calendar (M4c)
    planning_mode: str = "event_goal"
    intent: str = "develop"
    focus: str = "balanced_triathlon"
    horizon_weeks: int = 8
    manual_phases: Optional[List[str]] = None
    events: Optional[List[Dict[str, Any]]] = None
    available_hours: float = 10.0
    available_days: Optional[List[str]] = None  # ["mon","tue",...]
    demand: Optional[str] = None
    persist: StrictBool = False
    confirm: StrictBool = False
    base_checkpoint_id: Optional[int] = Field(default=None, ge=0, strict=True)


class AdjustRequest(CycleExpectedRequest):
    expected_cycle_id: UUID
    expected_cycle_revision: int = Field(ge=1, strict=True)
    base_checkpoint_id: int = Field(ge=1, strict=True)
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
    client_request_id: Optional[str] = Field(default=None, min_length=1, max_length=128)


class DemandRequest(BaseModel):
    level: str


class DemandConfirmRequest(BaseModel):
    level: str
    base_checkpoint_id: int
    preview_fingerprint: str


class HistoryRestoreRequest(CycleRestoreRequest):
    checkpoint_id: int
    base_checkpoint_id: int


class RepairDayRequest(CycleExpectedRequest):
    date: str
    exclude_sports: Optional[List[str]] = None
    base_checkpoint_id: int = Field(ge=1, strict=True)


class IntervalsDeliveryRequest(BaseModel):
    days: int = Field(7, ge=7, le=14)


class ConstraintRequest(CycleExpectedRequest):
    date: str
    kind: str
    source: str = "coach"
    note: Optional[str] = None
    plan_id: Optional[str] = None
    session_id: Optional[str] = None
    base_checkpoint_id: int = Field(ge=0, strict=True)
    cycle_scope: Literal["athlete", "cycle"] | None = None
    cycle_id: UUID | None = None
    metadata: Optional[Dict[str, Any]] = None
    sport: Optional[str] = Field(
        default=None,
        description=(
            "Скоуп ограничения (#473): пусто = весь день, или bike/run/swim "
            "(алиасы вело/бег/плавание) = только эта дисциплина дня"
        ),
    )

    @field_validator("sport")
    @classmethod
    def _validate_sport_scope(cls, value: Optional[str]) -> Optional[str]:
        # API-level validation → 422 on unknown sport (review #474); aliases map
        # to the canonical name. The DB-layer normalizer stays as second line of
        # defense for direct callers.
        from models.coach_constraints import normalize_constraint_sport

        if value in (None, ""):
            return None
        return normalize_constraint_sport(value)


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


@router.get("/edit-context")
def planning_edit_context(db: Database = Depends(get_database)) -> dict[str, Any]:
    """Read-only build inputs of the active checkpoint for the edit stepper."""
    return planning_service.planning_edit_context(db)


@router.get("/week-by-week")
def planning_week_by_week(db: Database = Depends(get_database)) -> dict[str, Any]:
    """One bounded, read-only active-plan week/day/session reader projection."""
    return planning_service.week_by_week_plan(db)


@router.get("/constraints")
def list_constraints(days: int = 30, db: Database = Depends(get_database)) -> dict[str, Any]:
    from datetime import timedelta
    from models.planning_cycle import constraint_fingerprint
    from utils.athlete_time import athlete_local_date

    today = athlete_local_date()
    rows = db.get_coach_constraints(
        start_date=today.isoformat(),
        end_date=(today + timedelta(days=max(1, int(days or 1)))).isoformat(),
        active_only=True,
        limit=200,
    )
    return {"count": len(rows), "constraints": [
        {**row, "constraint_fingerprint": constraint_fingerprint(row)} for row in rows
    ]}


@router.post("/constraints")
def create_constraint(req: ConstraintRequest, db: Database = Depends(get_database)) -> dict[str, Any]:
    """Create a durable constraint and apply it to the active plan immediately.

    Pydantic validation on ``sport`` yields 422 for unknown scopes (review #474);
    deeper ``ValueError`` layers map to 422 as well, stale base → 409.
    """
    try:
        return planning_service.apply_constraint_to_active_plan(
            db,
            {
                "date": req.date,
                "kind": req.kind,
                "source": req.source,
                "note": req.note,
                "sport": req.sport,
                "metadata": req.metadata or {},
                "cycle_scope": req.cycle_scope,
                "cycle_id": str(req.cycle_id) if req.cycle_id else None,
                "cycle_context": _request_cycle_context(req),
            },
            plan_id=req.plan_id,
            session_id=req.session_id,
            base_checkpoint_id=req.base_checkpoint_id,
        )
    except planning_service.StalePlanningCheckpointError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except PlanningBuildPreviewError:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.delete("/constraints/{constraint_id}")
def deactivate_constraint(constraint_id: int, db: Database = Depends(get_database)) -> dict[str, Any]:
    row = db.deactivate_coach_constraint(constraint_id)
    if row is None:
        raise HTTPException(status_code=404, detail="constraint not found")
    return row


@router.post("/constraints/{constraint_id}/retract")
def retract_constraint(constraint_id: int, db: Database = Depends(get_database)) -> dict[str, Any]:
    """Deactivate a constraint AND restore its day from the closest usable ancestor (#473).

    Per-sport constraints strip only their own sport from the recovered legs;
    whole-day constraints recover every leg the donor had.
    """
    if db.get_coach_constraint(constraint_id) is None:
        raise HTTPException(status_code=404, detail="constraint not found")
    try:
        proposal = planning_service.preview_coach_constraint_mutation(
            db,
            action="retract_plan_constraint",
            params={"constraint_id": constraint_id},
        )
        result = planning_service.confirm_coach_constraint_mutation(
            db,
            action="retract_plan_constraint",
            params=proposal["params"],
            preview_fingerprint=str(proposal["preview"]["preview_fingerprint"]),
        )
    except planning_service.StalePlanningCheckpointError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except planning_service.NoDonorCheckpointError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except PlanningBuildPreviewError:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return {"constraint": result.get("constraint"), "recover": result}


@router.post("/repair-day")
def repair_day(req: RepairDayRequest, db: Database = Depends(get_database)) -> dict[str, Any]:
    """One-off day recovery (incident tooling); no constraint row involved."""
    try:
        proposal = planning_service.preview_coach_constraint_mutation(
            db,
            action="repair_plan_day",
            params={
                "base_checkpoint_id": _active_checkpoint_id(db, required=req.base_checkpoint_id),
                "cycle_context": _request_cycle_context(req),
                "date": req.date,
                "exclude_sports": list(req.exclude_sports or []),
            },
        )
        return planning_service.confirm_coach_constraint_mutation(
            db,
            action="repair_plan_day",
            params=proposal["params"],
            preview_fingerprint=str(proposal["preview"]["preview_fingerprint"]),
        )
    except planning_service.StalePlanningCheckpointError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except planning_service.NoDonorCheckpointError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except PlanningBuildPreviewError:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


def _request_cycle_context(req) -> dict:
    return {"cycle_id": str(req.expected_cycle_id) if req.expected_cycle_id else None,
            "cycle_revision": req.expected_cycle_revision, "selection_revision": req.expected_selection_revision,
            "checkpoint_id": req.base_checkpoint_id or None, "athlete_day": athlete_local_date().isoformat()}


def _active_checkpoint_id(db: Database, *, required: Optional[int] = None) -> int:
    """Active checkpoint id, or fail fast when the caller pinned a stale base (#473)."""
    latest = db.get_current_planning_checkpoint()
    latest_raw_id = latest.get("id") if isinstance(latest, dict) else None
    latest_id = int(latest_raw_id) if latest_raw_id is not None else None
    if required is not None and latest_id != int(required):
        # The repair primitive checks staleness itself, but the route must not
        # silently substitute the latest base when a client pinned an older one.
        raise planning_service.StalePlanningCheckpointError(
            f"active checkpoint #{latest_id or 'none'} no longer matches repair base #{int(required)}"
        )
    if latest_id is None:
        raise ValueError("no active planning checkpoint to repair from")
    return int(latest_id)


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
    except PlanningBuildPreviewError:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.post("/build", response_model=BuildPreviewResponseV2)
def planning_build(req: BuildRequest, db: Database = Depends(get_database)) -> dict[str, Any]:
    if req.persist:
        raise PlanningBuildPreviewError("preview_required", "Сначала создайте предпросмотр, затем подтвердите его.")
    if req.confirm:
        raise PlanningBuildPreviewError("invalid_confirmation", "Подтвердите сохранённый предпросмотр по его идентификатору.", status=422)
    try:
        return planning_service.prepare_plan_build(
            db, parameters=BuildParameters.from_mapping(req.model_dump(mode="json", exclude={"persist", "confirm"})),
            origin="planning_ui",
        )
    except PlanningBuildPreviewError:
        raise
    except (ValueError, TypeError, KeyError) as exc:
        raise PlanningBuildPreviewError("invalid_build_request", "Проверьте параметры плана.", status=422) from exc


@router.post("/build/confirm", response_model=BuildConfirmResponseVersioned)
def planning_build_confirm(req: BuildConfirmRequest, db: Database = Depends(get_database)) -> dict[str, Any]:
    return planning_service.confirm_plan_build(db, preview_id=str(req.preview_id), origin="planning_ui")


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
    except PlanningBuildPreviewError:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return Response(
        content=result["content"],
        media_type=result["mimetype"],
        headers={"Content-Disposition": f'attachment; filename="{result["filename"]}"'},
    )


# --- Adjust mode -----------------------------------------------------------
@router.get("/session-projection/{session_id}")
def planning_session_projection(
    session_id: str,
    weeks: Annotated[int, Query(ge=1, le=12)] = 1,
    as_of: Optional[str] = None,
    checkpoint_id: Annotated[int | None, Query(ge=1)] = None,
    db: Database = Depends(get_database),
) -> dict[str, Any]:
    """Return the canonical provider-free projection for one plan session."""
    try:
        return session_projection_service.session_projection_at(
            db,
            session_id=session_id,
            as_of=as_of,
            weeks=weeks,
            checkpoint_id=checkpoint_id,
        )
    except SessionProjectionNotFoundError as exc:
        raise HTTPException(status_code=404, detail="planned session not found") from exc
    except PlanningBuildPreviewError:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/reconciliation")
def planning_reconciliation(
    weeks: int = 1,
    as_of: Optional[str] = None,
    include_provider: bool = True,
    db: Database = Depends(get_database),
) -> dict[str, Any]:
    try:
        result = planning_service.reconciliation_at(
            db,
            weeks=weeks,
            as_of=as_of,
            include_provider=include_provider,
        )
        if include_provider:
            # The embedded projection is canonical and provider-free. Keep
            # provider-enriched reconciliation rows intact without attaching
            # a projection composed from a different matching snapshot.
            return result

        projections = {
            str(row.get("session_id") or ""): session_projection_service.session_projection_from_reconciliation(
                db,
                result,
                session_id=str(row.get("session_id") or ""),
            )
            for row in result.get("rows") or []
            if isinstance(row, dict) and str(row.get("session_id") or "")
        }
        for row in result.get("rows") or []:
            if isinstance(row, dict):
                row["session_projection"] = projections.get(
                    str(row.get("session_id") or "")
                )
        return result
    except PlanningBuildPreviewError:
        raise
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
            client_request_id=req.client_request_id,
        )
    except planning_service.StalePlanningCheckpointError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except PlanningBuildPreviewError:
        raise
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
    except PlanningBuildPreviewError:
        raise
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
    except PlanningBuildPreviewError:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.post("/bike-tss/preview")
def planning_bike_tss_preview(
    req: RebalanceRequest,
    db: Database = Depends(get_database),
) -> dict[str, Any]:
    try:
        return planning_service.preview_bike_tss_rebalance(db, as_of=req.as_of)
    except PlanningBuildPreviewError:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.post("/bike-tss/confirm")
def planning_bike_tss_confirm(
    req: RebalanceRequest,
    db: Database = Depends(get_database),
) -> dict[str, Any]:
    if req.base_checkpoint_id is None or not req.preview_fingerprint:
        raise HTTPException(status_code=422, detail="base_checkpoint_id and preview_fingerprint are required")
    try:
        return planning_service.confirm_bike_tss_rebalance(
            db,
            base_checkpoint_id=req.base_checkpoint_id,
            preview_fingerprint=req.preview_fingerprint,
            as_of=req.as_of,
        )
    except planning_service.StalePlanningCheckpointError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except PlanningBuildPreviewError:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.post("/adjust")
def planning_adjust(req: AdjustRequest, db: Database = Depends(get_database)) -> dict[str, Any]:
    try:
        return planning_service.apply_adjustment(
            db, rows=req.rows, weeks=req.weeks, persist=req.persist,
            cycle_context={"cycle_id": str(req.expected_cycle_id), "cycle_revision": req.expected_cycle_revision,
                           "selection_revision": req.expected_selection_revision, "checkpoint_id": req.base_checkpoint_id,
                           "athlete_day": athlete_local_date().isoformat()},
        )
    except PlanningBuildPreviewError:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("/history")
def planning_history(limit: int = 10, db: Database = Depends(get_database)) -> dict[str, Any]:
    return planning_service.planning_history(db, limit=limit)


@router.post("/history/restore")
def planning_history_restore(
    req: HistoryRestoreRequest,
    db: Database = Depends(get_database),
) -> dict[str, Any]:
    """Restore a saved plan version as a new checkpoint on top of the active one."""
    try:
        return planning_service.restore_history_version(
            db,
            checkpoint_id=req.checkpoint_id,
            base_checkpoint_id=req.base_checkpoint_id,
            expected_cycle_id=str(req.expected_cycle_id),
            expected_cycle_revision=req.expected_cycle_revision,
            expected_selection_revision=req.expected_selection_revision,
            action=req.action,
        )
    except planning_service.StalePlanningCheckpointError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except PlanningBuildPreviewError:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
