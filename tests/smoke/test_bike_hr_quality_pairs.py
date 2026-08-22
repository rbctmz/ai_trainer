from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta

import pytest

from config.settings import Settings
from data.database import Database
from services.activity_ingest import ingest_provider_activity, normalize_provider_activity
from services.sync import _sync_activities


pytestmark = pytest.mark.smoke


def _recent_iso(days_ago: int = 1) -> str:
    return (datetime.now() - timedelta(days=days_ago)).strftime("%Y-%m-%dT08:00:00")


def _garmin_ride(activity_id: str, *, with_hr: bool = True) -> dict:
    row = {
        "activityId": activity_id,
        "startTimeLocal": _recent_iso(),
        "activityType": {"typeKey": "cycling"},
        "duration": 8414.07,
        "movingDuration": 8205.007,
        "distance": 47769.49,
        "avgPower": 111.0,
        "maxPower": 619.0,
        "normPower": 134.6,
    }
    if with_hr:
        row.update({
            "averageHR": 128.0,
            "hrTimeInZone_1": 198.0,
            "hrTimeInZone_2": 2535.0,
            "hrTimeInZone_3": 5030.0,
            "hrTimeInZone_4": 648.0,
            "hrTimeInZone_5": 0.0,
        })
    return row


def _pairs(db: Database) -> list[dict]:
    conn = db._connect()
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM bike_hr_quality_pairs ORDER BY date").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def test_garmin_sync_records_bike_hr_pair(tmp_path, monkeypatch):
    monkeypatch.setattr(Settings, "USER_FTP", 250)
    db = Database(str(tmp_path / "pairs.db"))
    db.save_athlete_profile({"ftp": 159.0, "lthr": 163.0, "source": "intervals_icu"})

    _sync_activities(db, [_garmin_ride("bike-pair-1")])

    pairs = _pairs(db)
    assert len(pairs) == 1
    p = pairs[0]
    assert p["activity_id"] == "bike-pair-1"
    assert p["avg_hr"] == pytest.approx(128.0)
    assert p["normalized_power"] == pytest.approx(134.6)
    assert p["avg_power"] == pytest.approx(111.0)
    assert p["ftp_on_date"] == pytest.approx(159.0)
    assert p["ftp_verified"] == 0  # ride predates the only profile snapshot
    assert p["lthr"] == pytest.approx(163.0)
    # zones 198+2535+5030+648+0 = 8411 s vs 8205 s moving ≈ 102.5%
    assert p["zone_coverage_pct"] == pytest.approx(102.5, abs=0.5)


def test_no_pair_without_hr(tmp_path, monkeypatch):
    monkeypatch.setattr(Settings, "USER_FTP", 250)
    db = Database(str(tmp_path / "no_hr.db"))
    db.save_athlete_profile({"ftp": 159.0, "lthr": 163.0, "source": "intervals_icu"})

    _sync_activities(db, [_garmin_ride("bike-no-hr", with_hr=False)])

    assert _pairs(db) == []


def test_pair_upserted_on_resync(tmp_path, monkeypatch):
    monkeypatch.setattr(Settings, "USER_FTP", 250)
    db = Database(str(tmp_path / "resync.db"))
    db.save_athlete_profile({"ftp": 159.0, "lthr": 163.0, "source": "intervals_icu"})

    _sync_activities(db, [_garmin_ride("bike-resync")])
    second = _garmin_ride("bike-resync")
    second["normPower"] = 140.0
    _sync_activities(db, [second])

    pairs = _pairs(db)
    assert len(pairs) == 1
    assert pairs[0]["normalized_power"] == pytest.approx(140.0)


def test_provider_copy_does_not_strip_canonical_pair_features(tmp_path, monkeypatch):
    """A poorer provider copy must not overwrite the projected canonical pair."""
    monkeypatch.setattr(Settings, "USER_FTP", 250)
    monkeypatch.setattr(Settings, "PRIMARY_ACTIVITY_SOURCE", "garmin")
    db = Database(str(tmp_path / "provider_merge.db"))
    db.save_athlete_profile({"ftp": 159.0, "lthr": 163.0, "source": "intervals_icu"})

    activity_id = "bike-provider-merge"
    _sync_activities(db, [_garmin_ride(activity_id)])
    assert _pairs(db)[0]["normalized_power"] == pytest.approx(134.6)

    intervals_copy = normalize_provider_activity(
        {
            "id": "i_provider_copy",
            "external_id": activity_id,
            "source": "GARMIN_CONNECT",
            "type": "Ride",
            "start_date_local": _recent_iso(),
            "moving_time": 8205,
            "elapsed_time": 8414,
            "average_heartrate": 128,
            "icu_average_watts": 111,
        },
        "intervals",
    )
    ingest_provider_activity(db, intervals_copy, primary_source="garmin")

    pairs = _pairs(db)
    assert len(pairs) == 1
    assert pairs[0]["activity_id"] == activity_id
    assert pairs[0]["normalized_power"] == pytest.approx(134.6)
    assert pairs[0]["zone_coverage_pct"] == pytest.approx(102.5, abs=0.5)


def test_pair_ftp_follows_profile_history(tmp_path, monkeypatch):
    monkeypatch.setattr(Settings, "USER_FTP", 250)
    db = Database(str(tmp_path / "ftp_history.db"))
    db.save_athlete_profile({"ftp": 159.0, "lthr": 163.0, "source": "intervals_icu"})
    two_days_ago = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d %H:%M:%S")
    conn = db._connect()
    conn.execute("UPDATE athlete_profile SET synced_at = ?", (two_days_ago,))
    conn.commit()
    conn.close()

    _sync_activities(db, [_garmin_ride("bike-old")])  # dated yesterday
    db.save_athlete_profile({"ftp": 172.0, "lthr": 163.0, "source": "intervals_icu"})
    today = _garmin_ride("bike-new")
    today["startTimeLocal"] = _recent_iso(days_ago=0)
    _sync_activities(db, [today])

    pairs = {p["activity_id"]: p for p in _pairs(db)}
    assert pairs["bike-old"]["ftp_on_date"] == pytest.approx(159.0)
    assert pairs["bike-old"]["ftp_verified"] == 1
    assert pairs["bike-new"]["ftp_on_date"] == pytest.approx(172.0)
    assert pairs["bike-new"]["ftp_verified"] == 1


def test_intervals_ingest_records_pair(tmp_path, monkeypatch):
    monkeypatch.setattr(Settings, "USER_FTP", 250)
    db = Database(str(tmp_path / "intervals.db"))
    db.save_athlete_profile({"ftp": 159.0, "lthr": 163.0, "source": "intervals_icu"})

    candidate = normalize_provider_activity(
        {
            "id": "i_pair_1",
            "type": "Ride",
            "start_date_local": _recent_iso(),
            "moving_time": 8205,
            "elapsed_time": 8414,
            "average_heartrate": 128,
            "icu_average_watts": 111,
        },
        "intervals",
    )
    ingest_provider_activity(db, candidate, primary_source="intervals")

    pairs = _pairs(db)
    assert len(pairs) == 1
    assert pairs[0]["activity_id"] == "intervals_i_pair_1"  # canonical ids get the intervals_ namespace
    assert pairs[0]["avg_power"] == pytest.approx(111.0)
    assert pairs[0]["normalized_power"] is None
    assert pairs[0]["zone_coverage_pct"] is None  # no zone seconds from Intervals


def test_pair_failure_does_not_break_ingest(tmp_path, monkeypatch):
    monkeypatch.setattr(Settings, "USER_FTP", 250)
    db = Database(str(tmp_path / "resilient.db"))
    db.save_athlete_profile({"ftp": 159.0, "lthr": 163.0, "source": "intervals_icu"})

    def boom(*_args, **_kwargs):
        raise RuntimeError("pair store down")

    monkeypatch.setattr(db, "upsert_bike_hr_pair", boom)
    result = _sync_activities(db, [_garmin_ride("bike-resilient")])

    assert result == {"new": 1, "updated": 0, "skipped": 0}
    assert _pairs(db) == []
