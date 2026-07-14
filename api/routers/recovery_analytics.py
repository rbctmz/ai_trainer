"""Read-only FastAPI adapter for prospective recovery analytics."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from api.deps import get_database
from data.database import Database
from services.recovery_analytics import (
    recovery_analytics_summary,
    recovery_cohort_detail,
)


router = APIRouter(prefix="/api/recovery-analytics", tags=["recovery-analytics"])


@router.get("")
def recovery_analytics_summary_view(
    capture_mode: str = "prospective",
    db: Database = Depends(get_database),
) -> dict[str, Any]:
    if capture_mode != "prospective":
        raise HTTPException(status_code=422, detail="public recovery analytics supports prospective mode only")
    return recovery_analytics_summary(db)


@router.get("/cohorts/{cohort_id}")
def recovery_cohort_view(
    cohort_id: str,
    db: Database = Depends(get_database),
) -> dict[str, Any]:
    result = recovery_cohort_detail(db, cohort_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Recovery cohort {cohort_id} not found")
    return result


__all__ = ["router", "recovery_analytics_summary_view", "recovery_cohort_view"]
