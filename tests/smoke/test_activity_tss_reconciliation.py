from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from data.database import Database
from services.sync import _sync_activities


pytestmark = pytest.mark.smoke


def _recent_iso(days_ago: int = 1) -> str:
    return (datetime.now() - timedelta(days=days_ago)).strftime("%Y-%m-%dT08:00:00")


def test_source_tss_is_preferred_and_persisted(tmp_path):
    db = Database(str(tmp_path / "source.db"))

    result = _sync_activities(
        db,
        [
            {
                "activityId": "walk-source-1",
                "startTimeLocal": _recent_iso(),
                "activityType": {"typeKey": "walking"},
                "duration": 1680,
                "movingDuration": 1200,
                "distance": 1600,
                "averageHR": 86,
                "activityTrainingLoad": 3.0,
            }
        ],
    )

    assert result == {"new": 1, "updated": 0, "skipped": 0}

    df = db.get_activities(30)
    row = df[df["activity_id"] == "walk-source-1"].iloc[0]
    assert row["tss"] == 3.0
    assert row["source_tss"] == 3.0
    assert row["tss_method"] == "garmin_training_load"
    assert row["moving_duration_minutes"] == 20.0


def test_running_fallback_does_not_use_bike_ftp_power(tmp_path):
    db = Database(str(tmp_path / "run.db"))

    result = _sync_activities(
        db,
        [
            {
                "activityId": "run-fallback-1",
                "startTimeLocal": _recent_iso(),
                "activityType": {"typeKey": "running"},
                "duration": 3000,
                "movingDuration": 2400,
                "distance": 6200,
                "avgPower": 279,
            }
        ],
    )

    assert result == {"new": 1, "updated": 0, "skipped": 0}

    df = db.get_activities(30)
    row = df[df["activity_id"] == "run-fallback-1"].iloc[0]
    assert row["source_tss"] is None
    assert row["tss_method"] == "heuristic_duration_run"
    assert row["tss"] == 33.3
    assert row["tss"] < 60.0

