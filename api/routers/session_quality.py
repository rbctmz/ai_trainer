"""Headless list/resolve API for shadow session-quality forecasts."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.deps import get_database
from api.session_feedback import (
    project_predictions_with_evaluations,
    resolve_prediction_via_feedback,
)
from api.session_quality_forecast import (
    summarize_session_quality_predictions,
)
from data.database import Database


router = APIRouter(prefix="/api/session-quality-predictions", tags=["session-quality"])


class ResolveSessionQualityRequest(BaseModel):
    activity_ids: list[str] = Field(default_factory=list)
    actual_role: str | None = None
    quality_rating_1_5: int | None = Field(default=None, ge=1, le=5)
    note: str | None = None


@router.get("")
def list_session_quality_predictions(
    days: int = 30,
    db: Database = Depends(get_database),
) -> dict[str, Any]:
    rows = project_predictions_with_evaluations(
        db,
        db.get_session_quality_predictions(days=days),
    )
    return {
        "predictions": rows,
        "summary": summarize_session_quality_predictions(rows),
        "shadow_mode": True,
    }


@router.post("/{prediction_id}/resolve")
def resolve_session_quality(
    prediction_id: int,
    payload: ResolveSessionQualityRequest,
    db: Database = Depends(get_database),
) -> dict[str, Any]:
    try:
        return resolve_prediction_via_feedback(
            db,
            prediction_id,
            activity_ids=payload.activity_ids,
            actual_role=payload.actual_role,
            quality_rating_1_5=payload.quality_rating_1_5,
            note=payload.note,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


__all__ = ["router"]
