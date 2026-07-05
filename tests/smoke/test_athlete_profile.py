"""Smoke coverage for issue #102: sync athlete profile (FTP/weight/LTHR) from
Intervals.icu instead of trusting a static .env value. See
docs/athlete_profile_sync_execplan.md for the full design."""
from __future__ import annotations

import json

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

    db.save_athlete_profile({"ftp": 161.0, "weight_kg": 93.5, "lthr": 163.0, "source": "intervals_icu"})
    latest = db.get_athlete_profile()
    assert latest["ftp"] == pytest.approx(161.0)  # the newer row, not the first one


def test_normalize_athlete_profile_picks_cycling_entry_by_capability_not_index():
    normalized = intervals_icu.normalize_athlete_profile(_REAL_SHAPE_PROFILE)

    assert normalized == {"ftp": pytest.approx(159.0), "weight_kg": pytest.approx(93.9), "lthr": pytest.approx(163.0)}


def test_normalize_athlete_profile_degrades_to_none_on_missing_or_malformed_data():
    assert intervals_icu.normalize_athlete_profile({}) == {"ftp": None, "weight_kg": None, "lthr": None}
    assert intervals_icu.normalize_athlete_profile({"sportSettings": []}) == {
        "ftp": None,
        "weight_kg": None,
        "lthr": None,
    }
    assert intervals_icu.normalize_athlete_profile(None) == {"ftp": None, "weight_kg": None, "lthr": None}
    # A cycling entry with a non-numeric ftp must degrade that one field, not raise.
    malformed = {"icu_weight": 93.9, "sportSettings": [{"eFTPSupported": True, "ftp": "not-a-number", "lthr": 163}]}
    assert intervals_icu.normalize_athlete_profile(malformed) == {
        "ftp": None,
        "weight_kg": pytest.approx(93.9),
        "lthr": pytest.approx(163.0),
    }


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

    stored = db.get_athlete_profile()
    assert stored["ftp"] == pytest.approx(159.0)
    assert stored["source"] == "intervals_icu"


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
