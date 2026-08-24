from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta

import pytest

from config.settings import Settings
from data.database import Database
from services.activity_ingest import ingest_provider_activity, normalize_provider_activity
from services.sync import _sync_activities


pytestmark = pytest.mark.smoke

_FIXED_NOW = datetime(2026, 8, 24, 12, 0, 0)


def _recent_iso(days_ago: int = 1) -> str:
    return (_FIXED_NOW - timedelta(days=days_ago)).strftime("%Y-%m-%dT08:00:00")


def _recent_gmt(days_ago: int = 1) -> str:
    return (_FIXED_NOW - timedelta(days=days_ago)).strftime("%Y-%m-%dT12:00:00Z")


def _set_profile_synced_at(db: Database, profile_id: int, synced_at: str) -> None:
    conn = db._connect()
    conn.execute(
        "UPDATE athlete_profile SET synced_at = ? WHERE id = ?",
        (synced_at, profile_id),
    )
    conn.commit()
    conn.close()


def _garmin_ride(activity_id: str, *, with_hr: bool = True) -> dict:
    row = {
        "activityId": activity_id,
        "startTimeLocal": _recent_iso(),
        "startTimeGMT": _recent_gmt(),
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


@pytest.mark.parametrize(
    ("label", "start_time_local"),
    [
        ("utc", "2026-08-23T23:59:00+00:00"),
        ("europe_moscow", "2026-08-24T02:59:00+03:00"),
    ],
)
def test_bike_hr_pair_does_not_verify_profile_after_absolute_activity(
    tmp_path, monkeypatch, label, start_time_local
):
    """Issue #502: verification must compare absolute profile/activity instants.

    The ride starts at 23:59 UTC and the only FTP snapshot arrives at 00:01
    UTC. Neither local date representation may mark the future snapshot verified.
    """
    monkeypatch.setattr(Settings, "USER_FTP", 250)
    db = Database(str(tmp_path / f"pair_timezone_{label}.db"))
    db.save_athlete_profile({"ftp": 159.0, "lthr": 163.0, "source": "intervals_icu"})
    _set_profile_synced_at(db, 1, "2026-08-24T00:01:00Z")

    ride = _garmin_ride(f"bike-502-pair-{label}")
    ride["startTimeLocal"] = start_time_local
    ride["startTimeGMT"] = "2026-08-23T23:59:00Z"
    _sync_activities(db, [ride])

    pair = _pairs(db)[0]
    assert pair["ftp_on_date"] == pytest.approx(159.0)
    assert pair["ftp_verified"] == 0


def test_bike_hr_pair_date_fallback_is_not_verified_without_activity_utc(
    tmp_path, monkeypatch
):
    """Legacy rows keep date-based FTP selection but never claim verification."""
    monkeypatch.setattr(Settings, "USER_FTP", 250)
    db = Database(str(tmp_path / "pair_legacy_date_fallback.db"))
    db.save_athlete_profile({"ftp": 159.0, "lthr": 163.0, "source": "intervals_icu"})
    _set_profile_synced_at(db, 1, "2026-08-22T12:00:00Z")

    ride = _garmin_ride("bike-502-pair-legacy")
    ride.pop("startTimeGMT")
    _sync_activities(db, [ride])

    pair = _pairs(db)[0]
    assert pair["ftp_on_date"] == pytest.approx(159.0)
    assert pair["ftp_verified"] == 0


def test_bike_hr_pair_preserves_subsecond_profile_ordering(tmp_path, monkeypatch):
    """A profile arriving later in the same second is still future evidence."""
    monkeypatch.setattr(Settings, "USER_FTP", 250)
    db = Database(str(tmp_path / "pair_subsecond_boundary.db"))
    db.save_athlete_profile({"ftp": 159.0, "lthr": 163.0, "source": "intervals_icu"})
    _set_profile_synced_at(db, 1, "2026-08-24T00:00:00.900000Z")

    ride = _garmin_ride("bike-502-pair-subsecond")
    ride["startTimeLocal"] = "2026-08-24T00:00:00.500000+00:00"
    ride["startTimeGMT"] = "2026-08-24T00:00:00.500000Z"
    _sync_activities(db, [ride])

    pair = _pairs(db)[0]
    assert pair["ftp_on_date"] == pytest.approx(159.0)
    assert pair["ftp_verified"] == 0


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
    _set_profile_synced_at(db, 1, "2026-08-22T12:00:00Z")

    _sync_activities(db, [_garmin_ride("bike-old")])  # dated yesterday
    db.save_athlete_profile({"ftp": 172.0, "lthr": 163.0, "source": "intervals_icu"})
    _set_profile_synced_at(db, 2, "2026-08-24T12:00:00Z")
    today = _garmin_ride("bike-new")
    today["startTimeLocal"] = _recent_iso(days_ago=0)
    today["startTimeGMT"] = _recent_gmt(days_ago=0)
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
