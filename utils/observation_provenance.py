"""Provider observation-date resolution for ingest (issue #557).

A stored row date is the *requested* date, so it cannot prove when a metric was
measured. Ingest passes provider fields through here with an explicit source
semantics instead of guessing: `utc` fields are converted into the athlete
timezone, `athlete_local` fields are already athlete-local calendar values.
Anything unusable stays `None` (the factor then reports `unverified`).
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Literal

from utils.athlete_time import athlete_zone

ObservationSource = Literal["utc", "athlete_local"]

_SOURCES = ("utc", "athlete_local")


def observation_local_date(value: Any, *, source: ObservationSource) -> date | None:
    """Resolve one provider value to an observation date, or None when unknown.

    ``source="utc"`` accepts ISO strings (with or without offset), epoch
    milliseconds/seconds and datetimes; naive values are treated as UTC because
    that is the documented semantics of Garmin ``*GMT``/``timestamp`` fields.
    ``source="athlete_local"`` accepts calendar values that are already local
    (``calendarDate``, ``startTimeLocal``, ``sleep_date``) and returns their date
    unchanged. Invalid values, and an unusable ``ATHLETE_TIMEZONE``, give None.
    """
    if source not in _SOURCES:
        raise ValueError(f"unknown observation source: {source!r}")
    parsed = _parse(value, assume_utc=source == "utc")
    if parsed is None:
        return None
    try:
        zone = athlete_zone()
    except ValueError:
        # Unusable athlete timezone: an observation date cannot be established
        # honestly for either source, so the factor must stay unverified.
        return None
    if source == "athlete_local":
        return parsed.date()
    return parsed.astimezone(zone).date()


def _parse(value: Any, *, assume_utc: bool) -> datetime | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime(value.year, value.month, value.day)
    elif isinstance(value, (int, float)):
        seconds = float(value)
        if abs(seconds) > 1e11:  # epoch milliseconds
            seconds /= 1000.0
        try:
            parsed = datetime.fromtimestamp(seconds, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None and assume_utc:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


__all__ = ["ObservationSource", "observation_local_date"]
