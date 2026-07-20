"""ASR-PERF-1 regression gate (Issue #241): /api/today stays fast with 3yr of history.

This is a REGRESSION GATE, not a benchmark: it seeds ~3 years of synthetic
activities/HRV/daily-health rows into a temp SQLite DB, runs the full
`build_today_decision_snapshot` path (the same composition `GET /api/today`
delegates to, see api/routers/today.py), and pins a ceiling so a future
change that reintroduces an O(all-history) scan on this path fails CI
instead of silently regressing until someone notices in production.
Contributor-safe: temp SQLite only, no provider/network calls.
"""
from __future__ import annotations

import math
from datetime import date, timedelta
from time import perf_counter

import pytest

from api.today_snapshot import build_today_decision_snapshot
from data.database import Database

pytestmark = pytest.mark.smoke

# ASR-PERF-1 budget: "Сегодня" must stay under 2s even with 3 years of
# history. Deliberately generous vs. local dev latency (well under this on
# a laptop) so the gate only fires on a genuine regression, not CI jitter.
TODAY_SNAPSHOT_P95_BUDGET_SECONDS = 2.0

_SYNTHETIC_YEARS = 3
_MEASURED_RUNS = 5


def _p95_seconds(samples: list[float]) -> float:
    """Nearest-rank p95 over a small in-process sample.

    Not a statistically rigorous percentile (the sample is intentionally
    small to keep the gate cheap) — smooths out an occasional slow first
    call (import machinery, sqlite page-cache warm-up) without letting a
    single lucky fast run hide a real regression.
    """
    ordered = sorted(samples)
    index = max(0, math.ceil(0.95 * len(ordered)) - 1)
    return ordered[index]


def _seed_three_years_of_history(db: Database, *, today: date) -> None:
    start = today - timedelta(days=365 * _SYNTHETIC_YEARS)
    activities = []
    hrv_data = {}
    health_data = {}

    day = start
    idx = 0
    while day <= today:
        date_str = day.isoformat()
        if idx % 2 == 0:  # realistic training density: workout every other day
            activities.append(
                {
                    "activity_id": f"synthetic-{idx}",
                    "date": date_str,
                    "sport": "bike" if idx % 4 == 0 else "run",
                    "duration_minutes": 45,
                    "moving_duration_minutes": 43,
                    "distance_km": 10.0,
                    "avg_hr": 145,
                    "training_effect": 3.2,
                    "garmin_training_load": 60.0,
                    "source_tss": 55.0,
                    "tss_method": "hr_tss",
                    "tss": 55.0,
                }
            )
        hrv_data[date_str] = {
            "rmssd": 35.0 + (idx % 10),
            "stress_score": 25.0,
            "recovery_score": 70.0,
        }
        health_data[date_str] = {
            "resting_hr": 48 + (idx % 5),
            "steps": 8000 + idx,
        }
        day += timedelta(days=1)
        idx += 1

    db.save_activities(activities)
    db.save_hrv_data(hrv_data)
    db.sync_daily_health(health_data)


def test_today_snapshot_p95_stays_under_budget_with_three_years_of_history(tmp_path):
    today = date(2026, 7, 20)
    db = Database(str(tmp_path / "perf.db"))
    _seed_three_years_of_history(db, today=today)

    samples = []
    for _ in range(_MEASURED_RUNS):
        started = perf_counter()
        snapshot = build_today_decision_snapshot(db, today=today)
        samples.append(perf_counter() - started)

    assert snapshot["snapshot_version"]
    p95 = _p95_seconds(samples)
    assert p95 < TODAY_SNAPSHOT_P95_BUDGET_SECONDS, samples


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
