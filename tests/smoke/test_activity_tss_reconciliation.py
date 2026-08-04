from __future__ import annotations

from datetime import datetime, timedelta
import sqlite3

import pytest

from config.settings import Settings
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


def test_bike_power_tss_uses_normalized_power_not_average(tmp_path, monkeypatch):
    """Issue #101: a variable-intensity ride (surges + coasting) must be scored
    from normalized power, not the flat average, or TSS is badly undercounted.

    Fixture numbers are the real 2026-07-04 ride (activity_id=23477418874):
    avgPower=111, normPower=135 (Garmin's own field, already present in the
    same bulk-list payload we already parse for avgPower/maxPower). With the
    still-current .env FTP=250 this ride was stored as tss=44.9 before this
    fix (average power); the fix must move it to ~66, matching NP²/FTP² math.
    """
    monkeypatch.setattr(Settings, "USER_FTP", 250)
    db = Database(str(tmp_path / "bike_np.db"))

    result = _sync_activities(
        db,
        [
            {
                "activityId": "bike-np-1",
                "startTimeLocal": _recent_iso(),
                "activityType": {"typeKey": "cycling"},
                "duration": 8414.07,
                "movingDuration": 8205.007,
                "distance": 47769.49,
                "avgPower": 111.0,
                "maxPower": 619.0,
                "normPower": 134.6,
            }
        ],
    )

    assert result == {"new": 1, "updated": 0, "skipped": 0}

    row = _activity_row(db, "bike-np-1")
    assert row["normalized_power"] == pytest.approx(134.6)
    assert row["tss_method"] == "power_tss_bike"
    assert row["tss"] == pytest.approx(66.1)
    assert row["tss"] > 44.9  # the pre-fix, avg-power-only value for this exact ride


def test_bike_power_tss_falls_back_to_average_power_without_np(tmp_path, monkeypatch):
    """When Garmin does not report normPower (e.g. no power meter, or an older
    activity), the resolver must keep working from avg_power exactly as before."""
    monkeypatch.setattr(Settings, "USER_FTP", 250)
    db = Database(str(tmp_path / "bike_no_np.db"))

    result = _sync_activities(
        db,
        [
            {
                "activityId": "bike-no-np-1",
                "startTimeLocal": _recent_iso(),
                "activityType": {"typeKey": "cycling"},
                "duration": 8414.07,
                "movingDuration": 8205.007,
                "distance": 47769.49,
                "avgPower": 111.0,
                "maxPower": 619.0,
            }
        ],
    )

    assert result == {"new": 1, "updated": 0, "skipped": 0}

    row = _activity_row(db, "bike-no-np-1")
    assert row["normalized_power"] is None
    assert row["tss_method"] == "power_tss_bike"
    assert row["tss"] == pytest.approx(44.9)


def test_bike_power_tss_uses_synced_ftp_over_stale_env_default(tmp_path, monkeypatch):
    """Issues #101+#102 combined: the real 2026-07-04 ride that started this
    whole investigation. With avgPower=111/normPower=134.6 and the stale
    .env FTP=250 this activity was originally stored as tss=44.9. Once the
    NP fix (#101) and a synced Intervals.icu FTP=159 (#102) are both in
    effect, resolving the same ride should land close to IntervalCoach's
    own reference value of 160 for this activity (verified independently:
    NP recomputed from the ride's raw per-second power stream, and FTP=159
    confirmed live from Intervals.icu's athlete profile API)."""
    monkeypatch.setattr(Settings, "USER_FTP", 250)  # the stale value must NOT win once a profile is synced
    db = Database(str(tmp_path / "bike_synced_ftp.db"))
    db.save_athlete_profile({"ftp": 159.0, "weight_kg": 93.9, "lthr": 163.0, "source": "intervals_icu"})

    result = _sync_activities(
        db,
        [
            {
                "activityId": "23477418874",
                "startTimeLocal": _recent_iso(),
                "activityType": {"typeKey": "cycling"},
                "duration": 8414.07,
                "movingDuration": 8205.007,
                "distance": 47769.49,
                "avgPower": 111.0,
                "maxPower": 619.0,
                "normPower": 134.6,
            }
        ],
    )

    assert result == {"new": 1, "updated": 0, "skipped": 0}

    row = _activity_row(db, "23477418874")
    assert row["tss_ftp_used"] == pytest.approx(159.0)
    assert row["tss"] == pytest.approx(163.3, abs=0.5)
    assert row["tss"] == pytest.approx(160, rel=0.05)  # within 5% of IntervalCoach's reference 160


def test_repair_legacy_activity_tss_uses_synced_profile_on_next_database_open(tmp_path, monkeypatch):
    """The retroactive-recompute path (_repair_legacy_activity_tss, which runs
    on every Database() construction) must pick up a synced profile exactly
    like a fresh sync does, not just trust the static .env default forever."""
    monkeypatch.setattr(Settings, "USER_FTP", 250)
    db_path = str(tmp_path / "bike_repair.db")

    db = Database(db_path)
    _sync_activities(
        db,
        [
            {
                "activityId": "bike-repair-1",
                "startTimeLocal": _recent_iso(),
                "activityType": {"typeKey": "cycling"},
                "duration": 8414.07,
                "movingDuration": 8205.007,
                "distance": 47769.49,
                "avgPower": 111.0,
                "maxPower": 619.0,
                "normPower": 134.6,
            }
        ],
    )
    stored_before = _activity_row(db, "bike-repair-1")
    assert stored_before["tss_ftp_used"] == pytest.approx(250.0)

    db.save_athlete_profile({"ftp": 159.0, "weight_kg": 93.9, "lthr": 163.0, "source": "intervals_icu"})

    # Re-opening the database re-runs init_tables() -> _repair_legacy_activity_tss(),
    # which must now recompute this row's tss against the freshly synced FTP.
    reopened = Database(db_path)
    stored_after = _activity_row(reopened, "bike-repair-1")
    assert stored_after["tss_ftp_used"] == pytest.approx(159.0)
    assert stored_after["tss"] == pytest.approx(163.3, abs=0.5)


def test_repair_swim_tss_writes_used_css_on_next_database_open(tmp_path, monkeypatch):
    """The retroactive-recompute path must persist the CSS used for a swim row
    (tss_pace_used), mirroring tss_ftp_used for bike power rows."""
    monkeypatch.setattr(Settings, "USER_LTHR", 170)
    db_path = str(tmp_path / "swim_repair.db")

    db = Database(db_path)
    _sync_activities(
        db,
        [
            {
                "activityId": "swim-repair-1",
                "startTimeLocal": _recent_iso(),
                "activityType": {"typeKey": "lap_swimming"},
                "duration": 2608.0,
                "movingDuration": 2453.0,
                "distance": 1600.0,
                "averageHR": 129.0,
            }
        ],
    )
    stored_before = _activity_row(db, "swim-repair-1")
    assert stored_before["tss_method"] == "hr_tss_swim"
    assert stored_before["tss_pace_used"] is None

    db.save_athlete_profile(
        {
            "ftp": 172.0,
            "weight_kg": 95.4,
            "lthr": 163.0,
            "swim_threshold_pace_seconds_per_100m": 138.0,
            "swim_threshold_pace_source": "intervals_icu",
            "source": "intervals_icu",
        }
    )

    reopened = Database(db_path)
    stored_after = _activity_row(reopened, "swim-repair-1")
    assert stored_after["tss_method"] == "pace_tss_swim"
    assert stored_after["tss_pace_used"] == pytest.approx(138.0)
    assert stored_after["tss"] == pytest.approx(49.7, abs=0.1)


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


@pytest.mark.parametrize(
    ("activity_id", "payload", "expected_tss"),
    [
        (
            "bike-cal-easy-reference",
            {
                "duration": 2400.5,
                "movingDuration": 2065.0,
                "distance": 8779.99,
                "averageHR": 110,
                "maxHR": 133,
                "activityTrainingLoad": 18.9,
                "hrTimeInZone_1": 552.067,
                "hrTimeInZone_2": 1775.44,
                "hrTimeInZone_3": 73.0,
                "hrTimeInZone_4": 0.0,
                "hrTimeInZone_5": 0.0,
            },
            13.0,
        ),
        (
            "bike-cal-threshold-reference",
            {
                "duration": 1933.5,
                "movingDuration": 1686.0,
                "distance": 8852.63,
                "averageHR": 126,
                "maxHR": 154,
                "activityTrainingLoad": 72.5,
                "hrTimeInZone_1": 208.192,
                "hrTimeInZone_2": 666.0,
                "hrTimeInZone_3": 721.601,
                "hrTimeInZone_4": 335.163,
                "hrTimeInZone_5": 0.0,
            },
            18.0,
        ),
    ],
)
def test_bike_zone_calibration_tracks_validated_ic_examples(tmp_path, activity_id, payload, expected_tss):
    db = Database(str(tmp_path / f"{activity_id}.db"))

    activity = {
        "activityId": activity_id,
        "startTimeLocal": _recent_iso(),
        "activityType": {"typeKey": "cycling"},
        **payload,
    }
    result = _sync_activities(db, [activity])

    assert result == {"new": 1, "updated": 0, "skipped": 0}

    row = _activity_row(db, activity_id)
    assert row["tss_method"] == "hr_zone_tss_bike"
    assert row["tss"] == pytest.approx(expected_tss, abs=1.0)


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
