"""Smoke coverage for the Intervals.icu athlete profile.

Issue #102 introduced FTP/weight/LTHR sync. Issue #308 adds running threshold
pace with explicit seconds-per-kilometre units and field-level provenance.
"""
from __future__ import annotations

from copy import deepcopy
import json
import sqlite3

import pytest

from config.settings import Settings
from data.database import Database
from services import intervals_icu


pytestmark = pytest.mark.smoke


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def read(self):
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


# A trimmed but realistic Intervals.icu athlete-profile payload, matching the
# shape observed live on 2026-07-05 for this project's own athlete: four
# sportSettings entries (Ride/Run/Swim/Other), only the Ride entry carries
# eFTPSupported=True and a non-null ftp.
_REAL_SHAPE_PROFILE = {
    "sex": "M",
    "icu_weight": 93.9,
    "icu_resting_hr": 59,
    "sportSettings": [
        {
            "types": ["Ride", "VirtualRide"],
            "ftp": 159,
            "lthr": 163,
            "max_hr": 180,
            "eFTPSupported": True,
        },
        {
            "types": ["Run", "VirtualRun"],
            "ftp": None,
            "lthr": 163,
            "max_hr": 180,
            "threshold_pace": 2.6666667,
            "eFTPSupported": False,
        },
        {
            "types": ["Swim"],
            "ftp": None,
            "lthr": 163,
            "max_hr": 180,
            "eFTPSupported": False,
        },
        {
            "types": ["Other"],
            "ftp": None,
            "lthr": 163,
            "max_hr": 180,
            "eFTPSupported": False,
        },
    ],
}


def test_database_athlete_profile_round_trips_and_reads_latest(tmp_path):
    db = Database(str(tmp_path / "athlete_profile.db"))

    assert db.get_athlete_profile() is None

    db.save_athlete_profile({"ftp": 159.0, "weight_kg": 93.9, "lthr": 163.0, "source": "intervals_icu"})
    first = db.get_athlete_profile()
    assert first["ftp"] == pytest.approx(159.0)
    assert first["weight_kg"] == pytest.approx(93.9)
    assert first["lthr"] == pytest.approx(163.0)
    assert first["source"] == "intervals_icu"
    assert first["synced_at"] is not None

    db.save_athlete_profile(
        {
            "ftp": 161.0,
            "weight_kg": 93.5,
            "lthr": 163.0,
            "threshold_pace_seconds_per_km": 375.0,
            "threshold_pace_source": "intervals_icu",
            "threshold_pace_synced_at": "2026-07-29 06:00:00",
            "source": "intervals_icu",
        }
    )
    latest = db.get_athlete_profile()
    assert latest["ftp"] == pytest.approx(161.0)  # the newer row, not the first one
    assert latest["threshold_pace_seconds_per_km"] == pytest.approx(375.0)
    assert latest["threshold_pace_source"] == "intervals_icu"
    assert latest["threshold_pace_synced_at"] == "2026-07-29 06:00:00"


def test_normalize_athlete_profile_picks_cycling_entry_by_capability_not_index():
    normalized = intervals_icu.normalize_athlete_profile(_REAL_SHAPE_PROFILE)

    assert normalized == {
        "ftp": pytest.approx(159.0),
        "weight_kg": pytest.approx(93.9),
        "lthr": pytest.approx(163.0),
        "threshold_pace_seconds_per_km": pytest.approx(375.0),
    }


def test_normalize_athlete_profile_picks_exact_run_entry_independent_of_order():
    profile = deepcopy(_REAL_SHAPE_PROFILE)
    profile["sportSettings"] = [
        {"types": ["VirtualRun"], "threshold_pace": 4.0},
        profile["sportSettings"][2],
        profile["sportSettings"][1],
        profile["sportSettings"][0],
    ]

    normalized = intervals_icu.normalize_athlete_profile(profile)

    assert normalized["ftp"] == pytest.approx(159.0)
    assert normalized["threshold_pace_seconds_per_km"] == pytest.approx(375.0)


@pytest.mark.parametrize(
    "raw_value",
    [
        True,
        "2.6666667",
        0,
        -1,
        float("nan"),
        float("inf"),
        1000 / 119,
        1000 / 901,
    ],
)
def test_normalize_athlete_profile_rejects_malformed_or_implausible_run_pace(raw_value):
    profile = deepcopy(_REAL_SHAPE_PROFILE)
    profile["sportSettings"][1]["threshold_pace"] = raw_value

    normalized = intervals_icu.normalize_athlete_profile(profile)

    assert normalized["threshold_pace_seconds_per_km"] is None


@pytest.mark.parametrize("seconds_per_km", [120.0, 900.0])
def test_normalize_athlete_profile_accepts_pace_validation_boundaries(seconds_per_km):
    profile = deepcopy(_REAL_SHAPE_PROFILE)
    profile["sportSettings"][1]["threshold_pace"] = 1000 / seconds_per_km

    normalized = intervals_icu.normalize_athlete_profile(profile)

    assert normalized["threshold_pace_seconds_per_km"] == pytest.approx(seconds_per_km)


def test_normalize_athlete_profile_rejects_ambiguous_run_settings():
    profile = deepcopy(_REAL_SHAPE_PROFILE)
    profile["sportSettings"].append(
        {"types": ["Run"], "threshold_pace": 3.0, "eFTPSupported": False}
    )

    normalized = intervals_icu.normalize_athlete_profile(profile)

    assert normalized["threshold_pace_seconds_per_km"] is None


def test_normalize_athlete_profile_degrades_to_none_on_missing_or_malformed_data():
    empty_profile = {
        "ftp": None,
        "weight_kg": None,
        "lthr": None,
        "threshold_pace_seconds_per_km": None,
    }
    assert intervals_icu.normalize_athlete_profile({}) == empty_profile
    assert intervals_icu.normalize_athlete_profile({"sportSettings": []}) == {
        "ftp": None,
        "weight_kg": None,
        "lthr": None,
        "threshold_pace_seconds_per_km": None,
    }
    assert intervals_icu.normalize_athlete_profile(None) == empty_profile
    # A cycling entry with a non-numeric ftp must degrade that one field, not raise.
    malformed = {"icu_weight": 93.9, "sportSettings": [{"eFTPSupported": True, "ftp": "not-a-number", "lthr": 163}]}
    assert intervals_icu.normalize_athlete_profile(malformed) == {
        "ftp": None,
        "weight_kg": pytest.approx(93.9),
        "lthr": pytest.approx(163.0),
        "threshold_pace_seconds_per_km": None,
    }


def test_legacy_athlete_profile_schema_migrates_additively(tmp_path):
    db_path = tmp_path / "legacy_profile.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE athlete_profile (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ftp REAL,
                weight_kg REAL,
                lthr REAL,
                source TEXT,
                synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            "INSERT INTO athlete_profile (ftp, weight_kg, lthr, source) VALUES (?, ?, ?, ?)",
            (159.0, 93.9, 163.0, "intervals_icu"),
        )

    db = Database(str(db_path))
    legacy = db.get_athlete_profile()

    assert legacy["ftp"] == pytest.approx(159.0)
    assert legacy["threshold_pace_seconds_per_km"] is None
    assert legacy["threshold_pace_source"] is None
    assert legacy["threshold_pace_synced_at"] is None

    db.save_athlete_profile(
        {
            "ftp": 159.0,
            "weight_kg": 93.9,
            "lthr": 163.0,
            "threshold_pace_seconds_per_km": 375.0,
            "threshold_pace_source": "intervals_icu",
            "source": "intervals_icu",
        }
    )
    assert db.get_athlete_profile()["threshold_pace_seconds_per_km"] == pytest.approx(375.0)


def test_sync_athlete_profile_success_path_persists_to_database(monkeypatch, tmp_path):
    monkeypatch.setattr(Settings, "INTERVALS_ICU_API_KEY", "secret-key")
    monkeypatch.setattr(Settings, "INTERVALS_ICU_ATHLETE_ID", "0")
    monkeypatch.setattr(Settings, "INTERVALS_ICU_BASE_URL", "https://intervals.icu")
    monkeypatch.setattr(
        intervals_icu.urlrequest,
        "urlopen",
        lambda *_args, **_kwargs: _FakeResponse(_REAL_SHAPE_PROFILE),
    )

    db = Database(str(tmp_path / "sync_success.db"))
    result = intervals_icu.sync_athlete_profile(db)

    assert result["synced"] is True
    assert result["reason"] is None
    assert result["profile"]["ftp"] == pytest.approx(159.0)
    assert result["profile"]["threshold_pace_seconds_per_km"] == pytest.approx(375.0)

    stored = db.get_athlete_profile()
    assert stored["ftp"] == pytest.approx(159.0)
    assert stored["source"] == "intervals_icu"
    assert stored["threshold_pace_seconds_per_km"] == pytest.approx(375.0)
    assert stored["threshold_pace_source"] == "intervals_icu"
    assert stored["threshold_pace_synced_at"] is not None


def test_sync_athlete_profile_partial_response_preserves_last_valid_pace_and_checkpoint(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(Settings, "INTERVALS_ICU_API_KEY", "secret-key")
    monkeypatch.setattr(Settings, "INTERVALS_ICU_ATHLETE_ID", "0")
    monkeypatch.setattr(Settings, "INTERVALS_ICU_BASE_URL", "https://intervals.icu")
    partial = deepcopy(_REAL_SHAPE_PROFILE)
    partial["icu_weight"] = 93.5
    partial["sportSettings"][1]["threshold_pace"] = "malformed"
    monkeypatch.setattr(
        intervals_icu.urlrequest,
        "urlopen",
        lambda *_args, **_kwargs: _FakeResponse(partial),
    )

    db = Database(str(tmp_path / "partial_profile.db"))
    db.save_athlete_profile(
        {
            "ftp": 158.0,
            "weight_kg": 94.0,
            "lthr": 162.0,
            "threshold_pace_seconds_per_km": 380.0,
            "threshold_pace_source": "intervals_icu",
            "threshold_pace_synced_at": "2026-07-28 05:00:00",
            "source": "intervals_icu",
        }
    )
    checkpoint_before = db.save_planning_checkpoint(
        {
            "goal_type": "run",
            "distance": "10k",
            "weeks_to_race": 8,
            "immutable_marker": {"sent": True},
        }
    )

    result = intervals_icu.sync_athlete_profile(db)

    assert result["synced"] is True
    stored = db.get_athlete_profile()
    assert stored["weight_kg"] == pytest.approx(93.5)
    assert stored["threshold_pace_seconds_per_km"] == pytest.approx(380.0)
    assert stored["threshold_pace_source"] == "intervals_icu"
    assert stored["threshold_pace_synced_at"] == "2026-07-28 05:00:00"
    assert db.get_latest_planning_checkpoint() == checkpoint_before


def test_repeated_profile_sync_keeps_same_canonical_pace(monkeypatch, tmp_path):
    monkeypatch.setattr(Settings, "INTERVALS_ICU_API_KEY", "secret-key")
    monkeypatch.setattr(Settings, "INTERVALS_ICU_ATHLETE_ID", "0")
    monkeypatch.setattr(Settings, "INTERVALS_ICU_BASE_URL", "https://intervals.icu")
    monkeypatch.setattr(
        intervals_icu.urlrequest,
        "urlopen",
        lambda *_args, **_kwargs: _FakeResponse(_REAL_SHAPE_PROFILE),
    )
    db = Database(str(tmp_path / "repeat_profile.db"))

    first = intervals_icu.sync_athlete_profile(db)
    second = intervals_icu.sync_athlete_profile(db)

    assert first["profile"]["threshold_pace_seconds_per_km"] == pytest.approx(375.0)
    assert second["profile"]["threshold_pace_seconds_per_km"] == pytest.approx(375.0)
    assert db.get_athlete_profile()["threshold_pace_seconds_per_km"] == pytest.approx(375.0)


def test_sync_athlete_profile_not_configured_leaves_database_untouched(monkeypatch, tmp_path):
    monkeypatch.setattr(Settings, "INTERVALS_ICU_API_KEY", None)

    db = Database(str(tmp_path / "sync_not_configured.db"))
    result = intervals_icu.sync_athlete_profile(db)

    assert result == {"synced": False, "reason": "not_configured", "profile": None}
    assert db.get_athlete_profile() is None


def test_sync_athlete_profile_request_failure_leaves_database_untouched(monkeypatch, tmp_path):
    monkeypatch.setattr(Settings, "INTERVALS_ICU_API_KEY", "secret-key")
    monkeypatch.setattr(Settings, "INTERVALS_ICU_ATHLETE_ID", "0")
    monkeypatch.setattr(Settings, "INTERVALS_ICU_BASE_URL", "https://intervals.icu")

    def _raise(*_args, **_kwargs):
        raise intervals_icu.IntervalsICUError("Не удалось подключиться к Intervals.icu: timeout")

    monkeypatch.setattr(intervals_icu.urlrequest, "urlopen", _raise)

    db = Database(str(tmp_path / "sync_failure.db"))
    result = intervals_icu.sync_athlete_profile(db)

    assert result["synced"] is False
    assert "timeout" in result["reason"]
    assert db.get_athlete_profile() is None
