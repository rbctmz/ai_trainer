"""System endpoints: Garmin sync + demo dataset.

- POST /api/sync          → authenticate via env creds and pull fresh Garmin data
                            into the real local cache. Without parameters the sync
                            is incremental (from the last known data); pass
                            {"days": N} in the body (or ?days=N) for a full reload.
- POST /api/demo/seed     → populate the ISOLATED demo database with the
                            deterministic sample dataset (never touches the real
                            ai_trainer.db).
- POST /api/demo/clear    → wipe the demo database.
"""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api.deps import demo_database, make_headless_state, real_database
from config.settings import Settings
from services import demo_mode as demo_service
from services import garmin as garmin_service
from services import sync as sync_service
from state import StateManager

router = APIRouter(prefix="/api", tags=["system"])


def _state_with_db(db) -> StateManager:
    """Headless StateManager whose lazy .database is the given handle."""
    return make_headless_state(database=db)


class SyncRequest(BaseModel):
    days: int | None = None


@router.post("/sync")
def sync(payload: SyncRequest | None = None, days: int | None = None) -> Dict[str, Any]:
    requested_days = days if days is not None else (payload.days if payload else None)
    if not (Settings.GARMIN_EMAIL and Settings.GARMIN_PASSWORD):
        raise HTTPException(
            status_code=400,
            detail="GARMIN_EMAIL/GARMIN_PASSWORD не заданы в .env",
        )

    state = _state_with_db(real_database())
    try:
        authed = garmin_service.authenticate(
            state, Settings.GARMIN_EMAIL, Settings.GARMIN_PASSWORD
        )
    except Exception as exc:  # network / 429 / auth changes
        raise HTTPException(status_code=502, detail=f"Garmin login failed: {exc}")
    if not authed:
        raise HTTPException(status_code=502, detail="Garmin login failed")

    try:
        result = sync_service.sync_garmin_data(state, days=requested_days)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Sync failed: {exc}")

    return sync_service.build_sync_status_payload(result)


@router.post("/demo/seed")
def demo_seed() -> Dict[str, Any]:
    """Seed the isolated demo DB. Use ?demo=1 on read endpoints to view it."""
    state = _state_with_db(demo_database())
    try:
        counts = demo_service.activate_demo_mode(state)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Demo seed failed: {exc}")
    return {"seeded": True, "counts": counts}


@router.post("/demo/clear")
def demo_clear() -> Dict[str, Any]:
    state = _state_with_db(demo_database())
    try:
        demo_service.deactivate_demo_mode(state)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Demo clear failed: {exc}")
    return {"cleared": True}
