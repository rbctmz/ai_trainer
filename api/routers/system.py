"""System endpoints: provider-aware sync + demo dataset.

- GET /api/sync/providers → report safe provider configuration metadata.
- POST /api/sync          → pull fresh data from the selected activity provider.
                            Without parameters the legacy default is Garmin; pass
                            {"source": "intervals"} for an Intervals-only sync.
- POST /api/demo/seed     → populate the ISOLATED demo database with the
                            deterministic sample dataset (never touches the real
                            ai_trainer.db).
- POST /api/demo/clear    → wipe the demo database.
"""
from __future__ import annotations

from enum import IntEnum
from typing import Any, Callable, Dict, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from api.deps import demo_database, make_headless_state, real_database
from api.deps import get_database
from api.operational_state import build_operational_state, latest_iso_from_database
from api.session_quality_forecast import record_shadow_session_quality_forecast
from api.sync_jobs import sync_job_manager
from config.settings import Settings
from services import demo_mode as demo_service
from services import garmin as garmin_service
from services import intervals_icu as intervals_icu_service
from services import intervals_sync as intervals_sync_service
from services import sync as sync_service
from services import sync_providers as sync_provider_service
from services.data_coverage import build_data_coverage
from state import StateManager

router = APIRouter(prefix="/api", tags=["system"])


def _state_with_db(db) -> StateManager:
    """Headless StateManager whose lazy .database is the given handle."""
    return make_headless_state(database=db)


class SyncRequest(BaseModel):
    days: int | None = None
    # Which provider to sync. Defaults to 'garmin' for backward compatibility
    # (absent field = as before). An unknown value is rejected with 422 by the
    # Literal (fail-fast, not guess) — symmetric with PRIMARY_ACTIVITY_SOURCE.
    source: Literal["garmin", "intervals"] = "garmin"


class CoverageDays(IntEnum):
    DAYS_30 = 30
    DAYS_90 = 90


class CoverageWindow(BaseModel):
    days: Literal[30, 90]
    start_date: str
    end_date: str


class ActivityCoverage(BaseModel):
    canonical_count: int
    provider_link_counts: Dict[str, int]
    unattributed_count: int
    latest_date: str | None


class DailyMetricCoverage(BaseModel):
    key: Literal["sleep_duration", "sleep_score", "hrv", "resting_hr", "steps"]
    observed_days: int
    missing_days: int
    coverage_pct: float
    latest_date: str | None
    source_days: Dict[str, int]


class DataCoverageResponse(BaseModel):
    window: CoverageWindow
    activities: ActivityCoverage
    daily_metrics: list[DailyMetricCoverage]


@router.get("/sync/providers")
def sync_providers() -> Dict[str, Any]:
    """Return safe provider discovery for the source-aware web sync control.

    Configuration is deliberately separate from connection validity: this
    endpoint never performs provider I/O and never returns credentials. The
    explicit Intervals probe below is user-triggered.
    """

    return sync_provider_service.connection_overview()


@router.get("/sync/coverage", response_model=DataCoverageResponse)
def sync_data_coverage(
    days: CoverageDays = Query(CoverageDays.DAYS_30),
    db=Depends(get_database),
) -> DataCoverageResponse:
    """Return local aggregate coverage; this path performs no provider I/O."""
    return DataCoverageResponse(**build_data_coverage(db, days=int(days)))


@router.post("/sync/providers/{source}/test")
def test_sync_provider_connection(
    source: Literal["intervals"],
) -> Dict[str, Any]:
    """Run the existing Intervals read-only probe and expose only its summary."""

    try:
        return sync_provider_service.test_intervals_connection()
    except intervals_icu_service.IntervalsICUConfigurationError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except intervals_icu_service.IntervalsICUError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/sync")
def sync_status(
    demo: bool = False,
    db=Depends(get_database),
) -> Dict[str, Any]:
    return sync_job_manager.status(db=db, demo=demo)


@router.post("/sync")
def sync(payload: SyncRequest | None = None, days: int | None = None) -> Dict[str, Any]:
    requested_days = days if days is not None else (payload.days if payload else None)
    source = payload.source if payload else "garmin"
    db = real_database()

    run_sync = _build_run_sync(source, requested_days, db)

    return sync_job_manager.start_or_get(
        days=requested_days,
        run_sync=run_sync,
        db=db,
        source=source,
    )


def _build_run_sync(source: str, requested_days: int | None, db) -> "Callable[[Any], Dict[str, Any]]":
    """Pick the provider runner. Both branches flow the result payload through the
    SAME operational-state + shadow-forecast helpers (review P5), so the snapshot
    shape and side-effects are identical regardless of source."""
    if source == "intervals":
        return _run_intervals_sync(db, requested_days)
    return _run_garmin_sync(db, requested_days)


def _run_garmin_sync(db, requested_days: int | None):
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

        response = _sync_payload_with_operational_state(
            sync_service.build_sync_status_payload(result),
            db=state.database,
        )
        return _attach_shadow_forecast(response, state.database)

    return run_sync


def _run_intervals_sync(db, requested_days: int | None):
    """Intervals sync is NOT Garmin-gated (slice-spec §3): the only gate is a
    configured INTERVALS_ICU_API_KEY, enforced by ``sync_intervals_data``'s
    preflight (``IntervalsICUConfigurationError``). A missing key surfaces as a
    failed job (error message), not a 4xx at request time — the endpoint is
    reachable, the provider is just not configured."""
    from services.intervals_icu import IntervalsICUConfigurationError

    def run_sync(on_progress):
        try:
            result = intervals_sync_service.sync_intervals_data(
                db,
                days=requested_days,
                on_progress=on_progress,
            )
        except IntervalsICUConfigurationError as exc:
            raise RuntimeError(str(exc)) from exc
        except Exception as exc:
            raise RuntimeError(f"Sync failed: {exc}") from exc

        response = _sync_payload_with_operational_state(
            intervals_sync_service.build_intervals_sync_status_payload(result, days=requested_days),
            db=db,
        )
        return _attach_shadow_forecast(response, db)

    return run_sync


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


def _attach_shadow_forecast(payload: Dict[str, Any], db) -> Dict[str, Any]:
    """Record Issue D output without ever failing the primary sync."""
    try:
        result = record_shadow_session_quality_forecast(db)
    except Exception as exc:
        payload["session_quality_forecast"] = None
        payload["session_quality_forecast_error"] = str(exc)
        return payload
    payload["session_quality_forecast"] = result
    payload["session_quality_forecast_error"] = None
    return payload


@router.post("/demo/seed")
def demo_seed() -> Dict[str, Any]:
    """Seed the isolated demo DB. Use ?demo=1 on read endpoints to view it."""
    state = _state_with_db(demo_database())
    try:
        counts = demo_service.activate_demo_mode(state)
        counts["plan_days"] = _seed_demo_plan(state.database)
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


def _seed_demo_plan(db) -> int:
    """Give the demo dataset an active plan so /today shows a session card and
    the /planning adjust/adherence tabs and the coach have plan context (#256).

    Deliberately lives in the api layer, NOT services/demo_mode: build_plan is an
    api-level orchestration and services must not import api
    (test_api_architecture::test_services_modules_do_not_depend_on_api, #194).
    Returns the number of planned days (0 if no plan was produced).
    """
    from datetime import datetime, timedelta

    from api import planning_service

    # Deterministic athlete profile so the plan builder has FTP/LTHR regardless
    # of the runner's .env.
    db.save_athlete_profile(
        {"ftp": 240, "weight_kg": 72.0, "lthr": 160, "source": "demo"}
    )
    event_date = (datetime.now().date() + timedelta(weeks=9)).strftime("%Y-%m-%d")
    planning_service.build_plan(
        db,
        goal_type="triathlon",
        distance="olympic",
        event_date=event_date,
        available_hours=10.0,
        available_days=["mon", "tue", "wed", "thu", "sat", "sun"],
        persist=True,
    )
    active = planning_service.get_active_plan(db)
    if not active or not active.get("daily_plan"):
        return 0
    return len(planning_service.plan_days(active))
