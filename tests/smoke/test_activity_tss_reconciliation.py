from __future__ import annotations

from datetime import datetime, timedelta
import sqlite3

import pytest

from data.database import Database
from services.sync import _sync_activities


pytestmark = pytest.mark.smoke


def _recent_iso(days_ago: int = 1) -> str:
    return (datetime.now() - timedelta(days=days_ago)).strftime("%Y-%m-%dT08:00:00")


def test_garmin_load_is_persisted_separately_from_walk_tss(tmp_path):
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
    assert row["tss"] == 2.8
    assert row["garmin_training_load"] == 3.0
    assert row["source_tss"] == 3.0
    assert row["tss_method"] == "heuristic_duration_walk"
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


def test_swim_zone_summary_beats_raw_garmin_load(tmp_path):
    db = Database(str(tmp_path / "swim.db"))

    result = _sync_activities(
        db,
        [
            {
                "activityId": "swim-zone-1",
                "startTimeLocal": _recent_iso(),
                "activityType": {"typeKey": "open_water_swimming"},
                "duration": 3717,
                "movingDuration": 3473,
                "distance": 2200,
                "averageHR": 142,
                "activityTrainingLoad": 155.7,
                "hrTimeInZone_1": 63.027,
                "hrTimeInZone_2": 317.548,
                "hrTimeInZone_3": 515.680,
                "hrTimeInZone_4": 1311.768,
                "hrTimeInZone_5": 1508.927,
            }
        ],
    )

    assert result == {"new": 1, "updated": 0, "skipped": 0}

    df = db.get_activities(30)
    row = df[df["activity_id"] == "swim-zone-1"].iloc[0]
    assert row["garmin_training_load"] == 155.7
    assert row["source_tss"] == 155.7
    assert row["tss_method"] == "hr_zone_tss_swim"
    assert row["tss"] == 62.7
    assert row["tss"] < row["garmin_training_load"]


def test_legacy_garmin_load_rows_are_backfilled_to_computed_tss(tmp_path):
    db_path = tmp_path / "legacy.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        '''
        CREATE TABLE activities (
            activity_id TEXT PRIMARY KEY,
            date DATE,
            sport TEXT,
            duration_minutes REAL,
            moving_duration_minutes REAL,
            distance_km REAL,
            avg_hr REAL,
            max_hr REAL,
            avg_power REAL,
            max_power REAL,
            elevation_gain REAL,
            calories INTEGER,
            training_effect REAL,
            anaerobic_effect REAL,
            activity_name TEXT,
            description TEXT,
            source_tss REAL,
            tss_method TEXT,
            tss REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        '''
    )
    conn.execute(
        '''
        INSERT INTO activities (
            activity_id, date, sport, duration_minutes, moving_duration_minutes,
            distance_km, avg_hr, source_tss, tss_method, tss
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''',
        (
            "legacy-swim-1",
            (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d"),
            "open_water_swimming",
            62.0,
            57.9,
            2.2,
            142,
            155.7,
            "garmin_training_load",
            155.7,
        ),
    )
    conn.commit()
    conn.close()

    db = Database(str(db_path))
    df = db.get_activities(30)
    row = df[df["activity_id"] == "legacy-swim-1"].iloc[0]

    assert row["garmin_training_load"] == 155.7
    assert row["source_tss"] == 155.7
    assert row["tss_method"] == "hr_tss_swim"
    assert row["tss"] == 67.3
    assert row["tss"] < row["garmin_training_load"]
