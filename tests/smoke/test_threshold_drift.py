"""Smoke: FTP/threshold drift detection (issue #374).

Workouts are prescribed as percentages of FTP. When the FTP used for TSS math
drifts from the athlete's current source profile by more than 10%, the user
must see a warning instead of silently receiving wrong targets. ExecPlan:
docs/threshold_drift_diagnostics_execplan.md.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from data.database import Database
from models.threshold_drift import DRIFT_THRESHOLD_PCT, detect_threshold_drift


pytestmark = pytest.mark.smoke


def _seed_profile(db: Database, *, ftp: float) -> None:
    db.save_athlete_profile(
        {"ftp": ftp, "lthr": 165.0, "weight_kg": 80.0, "source": "intervals_icu"}
    )


def _seed_activity(db: Database, *, ftp_used: float, days_ago: int = 1) -> None:
    activity_date = (datetime.now() - timedelta(days=days_ago)).strftime("%Y-%m-%d")
    db.save_activities(
        [
            {
                "activity_id": f"act-{days_ago}",
                "date": activity_date,
                "sport": "cycling",
                "duration_minutes": 60,
                "distance_km": 30.0,
                "tss": 60.0,
                "tss_ftp_used": ftp_used,
            }
        ]
    )


def test_ftp_drift_warning_when_values_diverge_more_than_10pct(tmp_path):
    db = Database(str(tmp_path / "drift.db"))
    _seed_profile(db, ftp=250.0)
    _seed_activity(db, ftp_used=300.0)

    warnings = detect_threshold_drift(db)

    assert len(warnings) == 1
    warning = warnings[0]
    assert warning["kind"] == "ftp_drift"
    assert warning["source_value"] == 250.0
    assert warning["used_value"] == 300.0
    assert warning["pct"] >= DRIFT_THRESHOLD_PCT
    assert "FTP" in warning["message"]


def test_no_warning_when_drift_below_threshold(tmp_path):
    db = Database(str(tmp_path / "ok.db"))
    _seed_profile(db, ftp=250.0)
    _seed_activity(db, ftp_used=260.0)

    assert detect_threshold_drift(db) == []


def test_no_warning_without_profile_or_recent_activity(tmp_path):
    empty = Database(str(tmp_path / "empty.db"))
    assert detect_threshold_drift(empty) == []

    only_profile = Database(str(tmp_path / "profile-only.db"))
    _seed_profile(only_profile, ftp=250.0)
    assert detect_threshold_drift(only_profile) == []

    stale = Database(str(tmp_path / "stale.db"))
    _seed_profile(stale, ftp=250.0)
    _seed_activity(stale, ftp_used=300.0, days_ago=60)
    assert detect_threshold_drift(stale) == []


def test_athlete_profile_envelope_includes_empty_warnings(tmp_path):
    from api.routers.athlete_profile import athlete_profile

    payload = athlete_profile(demo=False, db=Database(str(tmp_path / "api.db")))

    assert payload["warnings"] == []


def test_athlete_profile_reports_ftp_drift_warning(tmp_path):
    from api.routers.athlete_profile import athlete_profile

    db = Database(str(tmp_path / "api-drift.db"))
    _seed_profile(db, ftp=250.0)
    _seed_activity(db, ftp_used=300.0)

    payload = athlete_profile(demo=False, db=db)

    assert len(payload["warnings"]) == 1
    assert payload["warnings"][0]["kind"] == "ftp_drift"
