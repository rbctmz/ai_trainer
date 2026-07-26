"""Safe activity-provider discovery for the web/API sync surface.

This service keeps environment inspection and provider probing out of the thin
FastAPI router. Returned dictionaries are deliberately credential-free.
"""
from __future__ import annotations

from typing import Any, Dict

from config.settings import Settings
from services import intervals_icu


def connection_overview() -> Dict[str, Any]:
    """Describe configured sources without performing provider I/O."""

    garmin_configured = bool(
        str(Settings.GARMIN_EMAIL or "").strip()
        and str(Settings.GARMIN_PASSWORD or "").strip()
    )
    intervals_connection = intervals_icu.connection_info()
    intervals_configured = bool(intervals_connection.get("configured"))
    configured = {
        "garmin": garmin_configured,
        "intervals": intervals_configured,
    }

    primary = str(Settings.PRIMARY_ACTIVITY_SOURCE or "garmin")
    recommended = primary
    if not configured.get(primary, False):
        recommended = next(
            (source for source in ("intervals", "garmin") if configured[source]),
            primary,
        )

    return {
        "recommended_source": recommended,
        "providers": [
            {
                "source": "garmin",
                "label": "Garmin Connect",
                "configured": garmin_configured,
                "connection": None,
            },
            {
                "source": "intervals",
                "label": "Intervals.icu",
                "configured": intervals_configured,
                "connection": intervals_connection,
            },
        ],
    }


def test_intervals_connection() -> Dict[str, Any]:
    """Run the read-only Intervals probe and return only its safe summary."""

    client = intervals_icu.get_client()
    if not client.is_configured():
        raise intervals_icu.IntervalsICUConfigurationError(
            "Intervals.icu не настроен. Укажите INTERVALS_ICU_API_KEY в .env."
        )
    result = client.test_connection()
    return {
        "ok": bool(result.get("ok")),
        "source": "intervals",
        "calendar_count": result.get("calendar_count"),
    }


__all__ = ["connection_overview", "test_intervals_connection"]
