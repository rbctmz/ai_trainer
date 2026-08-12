"""Aggregate local data coverage for the source inventory dashboard (#427)."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from data.database import Database


METRIC_KEYS = ("sleep_duration", "sleep_score", "hrv", "resting_hr", "steps")
SUPPORTED_WINDOWS = {30, 90}


def build_data_coverage(
    db: Database,
    *,
    days: int = 30,
    as_of: date | None = None,
) -> dict[str, Any]:
    """Return counts, dates and provenance only; never raw health values."""
    if days not in SUPPORTED_WINDOWS:
        raise ValueError("days must be 30 or 90")

    end_date = as_of or date.today()
    start_date = end_date - timedelta(days=days - 1)
    raw = db.get_data_coverage_rows(start_date.isoformat(), end_date.isoformat())

    provider_counts = {"garmin": 0, "intervals": 0}
    for source, count in raw["activities"]["provider_rows"]:
        if source in provider_counts:
            provider_counts[source] = int(count)

    observed_dates: dict[str, set[str]] = defaultdict(set)
    source_dates: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for key, metric_date, source in raw["metric_rows"]:
        normalized_source = str(source or "legacy_unknown").strip() or "legacy_unknown"
        normalized_date = str(metric_date)
        observed_dates[str(key)].add(normalized_date)
        source_dates[str(key)][normalized_source].add(normalized_date)

    metrics = []
    for key in METRIC_KEYS:
        dates = observed_dates[key]
        count = len(dates)
        metrics.append(
            {
                "key": key,
                "observed_days": count,
                "missing_days": days - count,
                "coverage_pct": round(count * 100 / days, 1),
                "latest_date": max(dates) if dates else None,
                "source_days": {
                    source: len(source_dates[key][source])
                    for source in sorted(source_dates[key])
                },
            }
        )

    activities = raw["activities"]
    return {
        "window": {
            "days": days,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
        },
        "activities": {
            "canonical_count": activities["canonical_count"],
            "provider_link_counts": provider_counts,
            "unattributed_count": activities["unattributed_count"],
            "latest_date": activities["latest_date"],
        },
        "daily_metrics": metrics,
    }
