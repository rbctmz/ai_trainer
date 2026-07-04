"""Coach decision audit trail endpoint."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from api import planning_service
from api.deps import get_database
from api.operational_state import build_operational_state
from data.database import Database

router = APIRouter(prefix="/api/decisions", tags=["decisions"])


@router.get("")
def list_decisions(
    days: int = 30,
    demo: bool = False,
    db: Database = Depends(get_database),
) -> dict[str, Any]:
    rows = [row for row in db.get_coach_decisions(days=days) if row]
    proposal_rows = [row for row in db.get_coach_proposals(days=days) if row]
    grouped: list[dict[str, Any]] = []
    by_date: dict[str, list[dict[str, Any]]] = {}
    proposal_grouped: list[dict[str, Any]] = []
    proposals_by_date: dict[str, list[dict[str, Any]]] = {}
    pending_proposal_grouped: list[dict[str, Any]] = []
    pending_proposals_by_date: dict[str, list[dict[str, Any]]] = {}
    pending_proposal_count = 0

    for row in rows:
        day = str(row.get("date") or "")[:10]
        if not day:
            continue
        item = dict(row)
        item["time"] = _format_time(item.get("date"))
        if day not in by_date:
            by_date[day] = []
            grouped.append({"date": day, "decisions": by_date[day]})
        by_date[day].append(item)

    for row in proposal_rows:
        day = str(row.get("date") or "")[:10]
        if not day:
            continue
        item = dict(row)
        item["time"] = _format_time(item.get("date"))
        if day not in proposals_by_date:
            proposals_by_date[day] = []
            proposal_grouped.append({"date": day, "proposals": proposals_by_date[day]})
        proposals_by_date[day].append(item)
        if item.get("status") == "pending":
            pending_proposal_count += 1
            if day not in pending_proposals_by_date:
                pending_proposals_by_date[day] = []
                pending_proposal_grouped.append(
                    {"date": day, "proposals": pending_proposals_by_date[day]}
                )
            pending_proposals_by_date[day].append(item)

    has_data = bool(grouped or proposal_grouped)
    latest_data_at = None
    if grouped and proposal_grouped:
        latest_data_at = max(grouped[0]["date"], proposal_grouped[0]["date"])
    elif grouped:
        latest_data_at = grouped[0]["date"]
    elif proposal_grouped:
        latest_data_at = proposal_grouped[0]["date"]
    return {
        "has_data": has_data,
        "count": len(rows),
        "days": grouped,
        "proposal_count": len(proposal_rows),
        "proposal_days": proposal_grouped,
        "pending_proposal_count": pending_proposal_count,
        "pending_proposal_days": pending_proposal_grouped,
        "operational_state": build_operational_state(
            db,
            demo=demo,
            has_data=has_data,
            latest_data_at=latest_data_at,
            stale_after_days=30,
        ),
    }


def _format_time(value: Any) -> str:
    text = str(value or "")
    if "T" in text:
        return text.split("T", 1)[1][:5]
    if " " in text:
        return text.split(" ", 1)[1][:5]
    return ""


@router.post("/proposals/{proposal_id}/approve")
def approve_proposal(
    proposal_id: int,
    db: Database = Depends(get_database),
) -> dict[str, Any]:
    proposal = _pending_proposal_or_error(db, proposal_id)
    try:
        result = _apply_proposal(db, proposal)
    except ValueError as exc:
        db.update_coach_proposal_status(proposal_id, "failed", error=str(exc))
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        db.update_coach_proposal_status(proposal_id, "failed", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))

    updated = db.update_coach_proposal_status(proposal_id, "approved", result=result)
    return {"proposal": updated, "result": result}


@router.post("/proposals/{proposal_id}/reject")
def reject_proposal(
    proposal_id: int,
    db: Database = Depends(get_database),
) -> dict[str, Any]:
    _pending_proposal_or_error(db, proposal_id)
    updated = db.update_coach_proposal_status(
        proposal_id,
        "rejected",
        result={"message": "rejected by user"},
    )
    return {"proposal": updated}


def _pending_proposal_or_error(db: Database, proposal_id: int) -> dict[str, Any]:
    proposal = db.get_coach_proposal(proposal_id)
    if not proposal:
        raise HTTPException(status_code=404, detail="proposal not found")
    if proposal.get("status") != "pending":
        raise HTTPException(status_code=409, detail=f"proposal is already {proposal.get('status')}")
    return proposal


def _apply_proposal(db: Database, proposal: dict[str, Any]) -> dict[str, Any]:
    action = proposal.get("action")
    params = proposal.get("params") or {}
    if not isinstance(params, dict):
        raise ValueError("proposal params are invalid")

    if action == "build_plan":
        available_days = _normalize_available_days(params.get("available_days"))
        return planning_service.build_plan(
            db,
            goal_type=str(params.get("goal_type") or ""),
            distance=str(params.get("distance") or ""),
            event_date=str(params.get("event_date") or ""),
            available_hours=float(params.get("available_hours") or 10.0),
            available_days=available_days,
            demand=params.get("demand"),
            persist=True,
        )

    if action == "adjust_plan":
        rows = params.get("rows") or []
        if not isinstance(rows, list):
            raise ValueError("proposal adjustment rows are invalid")
        return planning_service.apply_adjustment(
            db,
            rows=rows,
            weeks=int(params.get("weeks") or 1),
            persist=True,
        )

    raise ValueError(f"unsupported proposal action: {action}")


def _normalize_available_days(value: Any) -> list[str] | None:
    if value is None:
        return None
    if isinstance(value, str):
        days = [part.strip().lower() for part in value.split(",") if part.strip()]
        return days or None
    if isinstance(value, list):
        days = [str(part).strip().lower() for part in value if str(part).strip()]
        return days or None
    return None
