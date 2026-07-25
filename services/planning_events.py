"""Read-only discovery of planning events from Intervals.icu."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict

from services.intervals_icu import list_race_events


def discover_intervals_events(*, days: int = 180, today: date | None = None) -> Dict[str, Any]:
    """Read a bounded event preview without persisting or writing externally."""
    resolved_days = max(1, min(365, int(days or 180)))
    start = today or date.today()
    end = start + timedelta(days=resolved_days)
    events = list_race_events(start, end)
    return {
        "oldest": start.isoformat(),
        "newest": end.isoformat(),
        "count": len(events),
        "events": events,
        "read_only": True,
    }


__all__ = ["discover_intervals_events"]
