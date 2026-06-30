from __future__ import annotations

from datetime import datetime, timedelta
import sqlite3

import pytest

from data.database import Database
from services.sync import _sync_activities


pytestmark = pytest.mark.smoke


def _recent_iso(days_ago: int = 1) -> str:
    return (datetime.now() - timedelta(days=days_ago)).strftime("%Y-%m-%dT08:00:00")


def _activity_row(db: Database, activity_id: str):
    df = db.get_activities(30)
    return df[df["activity_id"] == activity_id].iloc[0]


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

    row = _activity_row(db, "walk-source-1")
    assert row["tss"] == 3.0
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

    row = _activity_row(db, "run-fallback-1")
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

    row = _activity_row(db, "swim-zone-1")
    assert row["garmin_training_load"] == 155.7
    assert row["source_tss"] == 155.7
    assert row["tss_method"] == "hr_zone_tss_swim"
    assert row["tss"] == pytest.approx(65.0, abs=1.0)
    assert row["tss"] < row["garmin_training_load"]


@pytest.mark.parametrize(
    ("activity_id", "duration_seconds", "moving_seconds", "distance_meters", "garmin_load", "expected_tss"),
    [
        ("walk-cal-short", 659, 575, 786, 3.3, 2.0),
        ("walk-cal-long", 5437, 5096, 6164, 9.7, 10.0),
    ],
)
def test_walk_calibration_tracks_validated_ic_examples(
    tmp_path,
    activity_id,
    duration_seconds,
    moving_seconds,
    distance_meters,
    garmin_load,
    expected_tss,
):
    db = Database(str(tmp_path / f"{activity_id}.db"))

    result = _sync_activities(
        db,
        [
            {
                "activityId": activity_id,
                "startTimeLocal": _recent_iso(),
                "activityType": {"typeKey": "walking"},
                "duration": duration_seconds,
                "movingDuration": moving_seconds,
                "distance": distance_meters,
                "averageHR": 86,
                "activityTrainingLoad": garmin_load,
            }
        ],
    )

    assert result == {"new": 1, "updated": 0, "skipped": 0}

    row = _activity_row(db, activity_id)
    assert row["tss_method"] == "heuristic_duration_walk"
    assert row["garmin_training_load"] == garmin_load
    assert row["tss"] == pytest.approx(expected_tss, abs=0.4)


@pytest.mark.parametrize(
    ("activity_id", "payload", "expected_tss"),
    [
        (
            "swim-cal-easy-short",
            {
                "activityType": {"typeKey": "open_water_swimming"},
                "duration": 529.493,
                "movingDuration": 506.0,
                "distance": 300,
                "averageHR": 122,
                "activityTrainingLoad": 31.5,
                "hrTimeInZone_1": 0.0,
                "hrTimeInZone_2": 110.0,
                "hrTimeInZone_3": 366.5,
                "hrTimeInZone_4": 53.0,
                "hrTimeInZone_5": 0.0,
            },
            5.0,
        ),
        (
            "swim-cal-easy-mixed",
            {
                "activityType": {"typeKey": "open_water_swimming"},
                "duration": 1532.133,
                "movingDuration": 535.0,
                "distance": 300,
                "averageHR": 109,
                "activityTrainingLoad": 39.1,
                "hrTimeInZone_1": 518.0,
                "hrTimeInZone_2": 393.2,
                "hrTimeInZone_3": 474.9,
                "hrTimeInZone_4": 138.0,
                "hrTimeInZone_5": 8.0,
            },
            8.0,
        ),
        (
            "swim-cal-hard-reference",
            {
                "activityType": {"typeKey": "open_water_swimming"},
                "duration": 3717.0,
                "movingDuration": 3473.0,
                "distance": 2200,
                "averageHR": 142,
                "activityTrainingLoad": 155.7,
                "hrTimeInZone_1": 63.027,
                "hrTimeInZone_2": 317.548,
                "hrTimeInZone_3": 515.680,
                "hrTimeInZone_4": 1311.768,
                "hrTimeInZone_5": 1508.927,
            },
            65.0,
        ),
    ],
)
def test_swim_calibration_tracks_validated_ic_examples(tmp_path, activity_id, payload, expected_tss):
    db = Database(str(tmp_path / f"{activity_id}.db"))

    activity = {
        "activityId": activity_id,
        "startTimeLocal": _recent_iso(),
        **payload,
    }
    result = _sync_activities(db, [activity])

    assert result == {"new": 1, "updated": 0, "skipped": 0}

    row = _activity_row(db, activity_id)
    assert row["tss_method"] == "hr_zone_tss_swim"
    assert row["tss"] == pytest.approx(expected_tss, abs=1.0)
    assert row["tss"] < row["garmin_training_load"]


def test_run_zone_calibration_tracks_validated_ic_example(tmp_path):
    db = Database(str(tmp_path / "run-cal.db"))

    result = _sync_activities(
        db,
        [
            {
                "activityId": "run-cal-1",
                "startTimeLocal": _recent_iso(),
                "activityType": {"typeKey": "running"},
                "duration": 3000,
                "movingDuration": 2988,
                "distance": 6200,
                "averageHR": 142,
                "activityTrainingLoad": 61.6,
                "hrTimeInZone_1": 38.0,
                "hrTimeInZone_2": 393.3,
                "hrTimeInZone_3": 1524.2,
                "hrTimeInZone_4": 1036.2,
                "hrTimeInZone_5": 0.0,
            }
        ],
    )

    assert result == {"new": 1, "updated": 0, "skipped": 0}

    row = _activity_row(db, "run-cal-1")
    assert row["tss_method"] == "hr_zone_tss_run"
    assert row["tss"] == pytest.approx(51.0, abs=1.0)
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


def test_existing_zone_based_rows_are_recalibrated_on_database_open(tmp_path):
    db_path = tmp_path / "recalibrate.db"
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
            garmin_training_load REAL,
            source_tss REAL,
            hr_time_in_zone_1_seconds REAL,
            hr_time_in_zone_2_seconds REAL,
            hr_time_in_zone_3_seconds REAL,
            hr_time_in_zone_4_seconds REAL,
            hr_time_in_zone_5_seconds REAL,
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
            distance_km, avg_hr, garmin_training_load, source_tss,
            hr_time_in_zone_1_seconds, hr_time_in_zone_2_seconds, hr_time_in_zone_3_seconds,
            hr_time_in_zone_4_seconds, hr_time_in_zone_5_seconds, tss_method, tss
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''',
        (
            "existing-swim-zone-1",
            (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d"),
            "open_water_swimming",
            61.9509,
            57.8833,
            2.2,
            142,
            155.7,
            155.7,
            63.027,
            317.548,
            515.680,
            1311.768,
            1508.927,
            "hr_zone_tss_swim",
            62.7,
        ),
    )
    conn.commit()
    conn.close()

    db = Database(str(db_path))
    row = _activity_row(db, "existing-swim-zone-1")

    assert row["tss_method"] == "hr_zone_tss_swim"
    assert row["garmin_training_load"] == 155.7
    assert row["tss"] == pytest.approx(65.0, abs=1.0)
