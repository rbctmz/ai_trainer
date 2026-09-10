"""Neutral athlete-timezone helpers shared by ingest and delivery (issue #557).

Kept free of data/service imports so both the ingest layer (`data/`, `services/`)
and the delivery layer can use it without introducing a cycle or a layering
smell.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from config.settings import Settings


def athlete_local_date(observed_at_utc: datetime | None = None) -> date:
    """Resolve a calendar date in the configured athlete timezone."""
    observed = observed_at_utc or datetime.now(timezone.utc)
    if observed.tzinfo is None:
        raise ValueError("observed_at_utc must be timezone-aware")
    timezone_name = str(Settings.ATHLETE_TIMEZONE or "").strip()
    try:
        zone = ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError("ATHLETE_TIMEZONE must be a valid IANA timezone") from exc
    return observed.astimezone(zone).date()


__all__ = ["athlete_local_date"]
