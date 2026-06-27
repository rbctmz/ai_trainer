"""Dashboard endpoints.

Reuses the existing, tested command-center builder
``ui.pages.dashboard._build_dashboard_v2_summary`` so the web dashboard shows
exactly the same numbers as the Streamlit one. No metrics are recomputed here.
"""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends

from api.deps import get_database, get_headless_state
from data.database import Database
from state import StateManager
from ui.pages.dashboard import (
    _build_dashboard_v2_summary,
    _calculate_current_status,
    _get_latest_training_status,
)

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/summary")
def dashboard_summary(
    db: Database = Depends(get_database),
    state: StateManager = Depends(get_headless_state),
) -> Dict[str, Any]:
    """Command-center summary: today's state, workout, week load, next action.

    Returns an empty-but-valid envelope when no activities are cached yet, so
    the frontend can render an onboarding CTA instead of erroring.
    """
    activities_df = db.get_activities(30)
    if activities_df is None or activities_df.empty:
        return {"has_data": False, "summary": None}

    hrv_df = db.get_hrv_data(90)
    sleep_df = db.get_sleep_data(7)

    current_status = _calculate_current_status(activities_df, hrv_df, sleep_df)
    latest_training_status = _get_latest_training_status(db)
    summary = _build_dashboard_v2_summary(
        state,
        current_status,
        latest_training_status,
        activities_df,
    )
    return {"has_data": True, "summary": summary}
