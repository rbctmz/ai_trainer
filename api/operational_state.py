"""Shared operational-state helpers for FastAPI response envelopes."""
from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd

from services import demo_mode as demo_service


def latest_iso_from_frame(frame: Any, column: str = "date") -> str | None:
    """Return the latest date-like value from a dataframe as ``YYYY-MM-DD``."""
    if frame is None or getattr(frame, "empty", True) or column not in frame:
        return None

    values = pd.to_datetime(frame[column], errors="coerce").dropna()
    if values.empty:
        return None
    return values.max().date().isoformat()


def latest_iso_from_database(db: Any) -> str | None:
    """Return the latest synced date across known local data tables."""
    getter = getattr(db, "get_latest_data_dates", None)
    if not callable(getter):
        return None
    try:
        latest = getter() or {}
    except Exception:
        return None

    known = [str(value) for value in latest.values() if value]
    if not known:
        return None
    return max(known)


def build_operational_state(
    db: Any | None,
    *,
    demo: bool = False,
    has_data: bool,
    latest_data_at: str | None = None,
    sync_state: str = "idle",
    error: dict[str, Any] | None = None,
    stale_after_days: int = 2,
) -> dict[str, Any]:
    """Build the additive state contract every web API client can render.

    ``status`` is intentionally coarse: ``error`` wins first, then ``empty``,
    then ``stale``, otherwise ``ready``. Endpoint-specific payload fields remain
    responsible for the domain data itself.
    """
    latest_data_at = latest_data_at or (latest_iso_from_database(db) if has_data else None)
    is_demo = bool(demo or _dataset_origin(db) == demo_service.DATASET_ORIGIN_DEMO)
    stale = bool(has_data and latest_data_at and _is_stale(latest_data_at, stale_after_days))
    empty = not bool(has_data)

    if error is not None:
        status = "error"
    elif empty:
        status = "empty"
    elif stale:
        status = "stale"
    else:
        status = "ready"

    return {
        "status": status,
        "mode": "demo" if is_demo else "live",
        "demo": is_demo,
        "empty": empty,
        "stale": stale,
        "latest_data_at": latest_data_at,
        "sync_state": sync_state,
        "error": error,
    }


def _dataset_origin(db: Any | None) -> str | None:
    if db is None:
        return None
    getter = getattr(db, "get_user_setting", None)
    if not callable(getter):
        return None
    try:
        value = getter(demo_service.DATASET_ORIGIN_KEY)
    except Exception:
        return None
    return str(value) if value else None


def _is_stale(value: str, stale_after_days: int) -> bool:
    try:
        parsed = datetime.fromisoformat(str(value)[:10])
    except ValueError:
        return False
    age_days = (datetime.now().date() - parsed.date()).days
    return age_days > stale_after_days
