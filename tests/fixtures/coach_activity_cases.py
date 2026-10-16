"""Small independent database fixture for shared Coach delivery regressions."""
from datetime import date
from pathlib import Path

from data.database import Database
from services.coach_synthetic_eval import _activity, _link_provider, _provider_cache


def build_analyzed_empty_database(path: str | Path, activity_date: date) -> Database:
    """One linked, analyzed activity; no eval runner or network dependency."""
    database = Database(str(path))
    activity = _activity("syn-run-empty", activity_date, "run", "Синтетика — анализ без отрезков")
    activity.update(duration_minutes=40, distance_km=6, avg_hr=125, avg_power=None, tss=35)
    database.save_activities([activity])
    cache = _provider_cache([])
    cache["analyzed"] = f"{activity_date.isoformat()}T12:00:00Z"
    database.save_activity_intervals("syn-run-empty", cache)
    _link_provider(path, "syn-run-empty", "syn-provider-empty")
    return Database(str(path))
