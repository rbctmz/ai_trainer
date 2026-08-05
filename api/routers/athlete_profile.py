"""Athlete profile endpoint: FTP/weight/LTHR/run+swim threshold paces.

Pure read over ``athlete_profile`` (synced from intervals.icu when configured,
falling back to the static ``.env`` values otherwise). See
``services/intervals_icu.py::sync_athlete_profile`` and
``data/data_processor.py::resolve_athlete_ftp_lthr``.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from api.deps import get_database
from api.operational_state import build_operational_state
from data.database import Database
from models.threshold_drift import detect_threshold_drift

router = APIRouter(prefix="/api/athlete-profile", tags=["athlete-profile"])


@router.get("")
def athlete_profile(demo: bool = False, db: Database = Depends(get_database)) -> dict[str, Any]:
    profile = db.get_athlete_profile()
    if not profile:
        return {
            "has_data": False,
            "profile": None,
            "warnings": [],
            "operational_state": build_operational_state(db, demo=demo, has_data=False),
        }

    return {
        "has_data": True,
        "profile": {
            "ftp": profile.get("ftp"),
            "weight_kg": profile.get("weight_kg"),
            "lthr": profile.get("lthr"),
            "threshold_pace_seconds_per_km": profile.get(
                "threshold_pace_seconds_per_km"
            ),
            "threshold_pace_source": profile.get("threshold_pace_source"),
            "threshold_pace_synced_at": profile.get(
                "threshold_pace_synced_at"
            ),
            "swim_threshold_pace_seconds_per_100m": profile.get(
                "swim_threshold_pace_seconds_per_100m"
            ),
            "swim_threshold_pace_source": profile.get(
                "swim_threshold_pace_source"
            ),
            "swim_threshold_pace_synced_at": profile.get(
                "swim_threshold_pace_synced_at"
            ),
            "source": profile.get("source"),
            "synced_at": profile.get("synced_at"),
        },
        "warnings": detect_threshold_drift(db),
        "operational_state": build_operational_state(
            db,
            demo=demo,
            has_data=True,
            latest_data_at=profile.get("synced_at"),
        ),
    }
