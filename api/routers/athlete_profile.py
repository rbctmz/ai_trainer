"""Athlete profile endpoint: current FTP/weight/LTHR and their source.

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

router = APIRouter(prefix="/api/athlete-profile", tags=["athlete-profile"])


@router.get("")
def athlete_profile(demo: bool = False, db: Database = Depends(get_database)) -> dict[str, Any]:
    profile = db.get_athlete_profile()
    if not profile:
        return {
            "has_data": False,
            "profile": None,
            "operational_state": build_operational_state(db, demo=demo, has_data=False),
        }

    return {
        "has_data": True,
        "profile": {
            "ftp": profile.get("ftp"),
            "weight_kg": profile.get("weight_kg"),
            "lthr": profile.get("lthr"),
            "source": profile.get("source"),
            "synced_at": profile.get("synced_at"),
        },
        "operational_state": build_operational_state(
            db,
            demo=demo,
            has_data=True,
            latest_data_at=profile.get("synced_at"),
        ),
    }
