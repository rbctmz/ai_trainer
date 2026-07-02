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

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.deps import demo_database, make_headless_state, real_database
from api.deps import get_database
from api.operational_state import build_operational_state, latest_iso_from_database
from api.sync_jobs import sync_job_manager
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


@router.get("/sync")
def sync_status(
    demo: bool = False,
    db=Depends(get_database),
) -> Dict[str, Any]:
    return sync_job_manager.status(db=db, demo=demo)


@router.post("/sync")
def sync(payload: SyncRequest | None = None, days: int | None = None) -> Dict[str, Any]:
    requested_days = days if days is not None else (payload.days if payload else None)
    db = real_database()

    def run_sync(on_progress):
        if not (Settings.GARMIN_EMAIL and Settings.GARMIN_PASSWORD):
            raise RuntimeError("GARMIN_EMAIL/GARMIN_PASSWORD не заданы в .env")

        state = _state_with_db(db)
        try:
            authed = garmin_service.authenticate(
                state, Settings.GARMIN_EMAIL, Settings.GARMIN_PASSWORD
            )
        except Exception as exc:  # network / 429 / auth changes
            raise RuntimeError(f"Garmin login failed: {exc}") from exc
        if not authed:
            raise RuntimeError("Garmin login failed")

        try:
            result = sync_service.sync_garmin_data(
                state,
                days=requested_days,
                on_progress=on_progress,
            )
        except Exception as exc:
            raise RuntimeError(f"Sync failed: {exc}") from exc

        return _sync_payload_with_operational_state(
            sync_service.build_sync_status_payload(result),
            db=state.database,
        )

    return sync_job_manager.start_or_get(
        days=requested_days,
        run_sync=run_sync,
        db=db,
    )


def _sync_payload_with_operational_state(payload: Dict[str, Any], db, demo: bool = False) -> Dict[str, Any]:
    latest_data_at = latest_iso_from_database(db)
    payload["operational_state"] = build_operational_state(
        db,
        demo=demo,
        has_data=latest_data_at is not None,
        latest_data_at=latest_data_at,
        sync_state=str(payload.get("sync_state") or "succeeded"),
    )
    return payload


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
