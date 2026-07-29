"""Contract smoke tests for api/routers/athlete_profile.py (issue #242).

Before this file, `GET /api/athlete-profile` had zero test coverage of any
kind -- not even a route-registration check. Covers:
(a) success response with key schema fields
(b) empty/degraded state without raising

Only param is `demo: bool`; there is no business-logic validation branch, so
a (c) 422 dimension does not apply to this router.
"""
from __future__ import annotations

from data.database import Database


def test_athlete_profile_route_is_registered():
    import importlib

    main = importlib.import_module("api.main")
    assert "/api/athlete-profile" in main.app.openapi()["paths"]


def test_athlete_profile_empty_envelope(tmp_path):
    from api.routers.athlete_profile import athlete_profile

    payload = athlete_profile(demo=False, db=Database(str(tmp_path / "e.db")))

    assert payload["has_data"] is False
    assert payload["profile"] is None
    assert payload["operational_state"]["status"] == "empty"
    assert payload["operational_state"]["empty"] is True
    assert payload["operational_state"]["demo"] is False


def test_athlete_profile_with_data(tmp_path):
    from api.routers.athlete_profile import athlete_profile

    db = Database(str(tmp_path / "a.db"))
    db.save_athlete_profile(
        {
            "ftp": 250.0,
            "weight_kg": 72.5,
            "lthr": 165.0,
            "threshold_pace_seconds_per_km": 300.0,
            "threshold_pace_source": "intervals_icu",
            "threshold_pace_synced_at": "2026-07-29 06:00:00",
            "source": "intervals_icu",
        }
    )

    payload = athlete_profile(demo=False, db=db)

    assert payload["has_data"] is True
    assert payload["profile"]["ftp"] == 250.0
    assert payload["profile"]["weight_kg"] == 72.5
    assert payload["profile"]["lthr"] == 165.0
    assert payload["profile"]["threshold_pace_seconds_per_km"] == 300.0
    assert payload["profile"]["threshold_pace_source"] == "intervals_icu"
    assert payload["profile"]["threshold_pace_synced_at"] == "2026-07-29 06:00:00"
    assert payload["profile"]["source"] == "intervals_icu"
    assert payload["profile"]["synced_at"] is not None
    assert payload["operational_state"]["status"] in {"ready", "stale"}
    assert payload["operational_state"]["empty"] is False
    assert payload["operational_state"]["latest_data_at"] == payload["profile"]["synced_at"]


def test_athlete_profile_returns_latest_snapshot_not_first(tmp_path):
    from api.routers.athlete_profile import athlete_profile

    db = Database(str(tmp_path / "b.db"))
    db.save_athlete_profile({"ftp": 200.0, "weight_kg": 75.0, "lthr": 160.0, "source": "intervals_icu"})
    db.save_athlete_profile({"ftp": 210.0, "weight_kg": 74.0, "lthr": 161.0, "source": "intervals_icu"})

    payload = athlete_profile(demo=False, db=db)

    assert payload["profile"]["ftp"] == 210.0
