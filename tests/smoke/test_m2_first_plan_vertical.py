"""M2-T7/T8: профиль → preview → confirm → план виден в Planning и Today.

Весь вертикальный путь работает на временной SQLite и не обращается к провайдерам.
Это приёмочный контракт issue #271, а не повтор unit-тестов отдельных функций.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from api.deps import get_database
from api.main import app
from data.database import Database
from services.activity_ingest import ingest_provider_activity, normalize_provider_activity
from services import planning_onboarding as onboarding_service


pytestmark = pytest.mark.smoke


def _seed_history(db: Database) -> None:
    now = datetime.now()
    for index in range(28):
        started = now - timedelta(days=index)
        candidate = normalize_provider_activity(
            {
                "id": f"m2-history-{index}",
                "source": "STRAVA",
                "start_date": started.isoformat(),
                "start_date_local": started.isoformat(),
                "type": "Ride" if index % 2 else "Run",
                "moving_time": 3600,
                "icu_training_load": 50.0,
            },
            "intervals",
        )
        ingest_provider_activity(db, candidate, primary_source="intervals")


def test_m2_t7_t8_first_plan_vertical_is_persisted_and_visible(tmp_path, monkeypatch):
    db = Database(str(tmp_path / "m2-first-plan.db"))
    _seed_history(db)
    monkeypatch.setattr(
        onboarding_service,
        "discover_intervals_events",
        lambda **_kwargs: {"events": [], "count": 0},
    )
    app.dependency_overrides[get_database] = lambda: db
    try:
        with TestClient(app) as client:
            onboarding = client.get("/api/onboarding/planning")
            assert onboarding.status_code == 200
            assert onboarding.json()["completed"] is False
            assert onboarding.json()["suggested"]["planning_mode"]["value"] == "training_goal"

            profile_payload = {
                key: item["value"]
                for key, item in onboarding.json()["suggested"].items()
            }
            profile = client.put("/api/onboarding/planning", json=profile_payload)
            assert profile.status_code == 200
            assert profile.json()["completed"] is True

            build_payload = {
                **profile_payload,
                "event_date": None,
                "events": [],
                "focus": "balanced_triathlon",
                "demand": "moderate",
                "persist": False,
                "confirm": False,
            }
            preview = client.post("/api/planning/build", json=build_payload)
            assert preview.status_code == 200
            assert preview.json()["plan_id"] is None
            assert db.get_latest_planning_checkpoint() is None

            confirmed = client.post(
                "/api/planning/build",
                json={
                    **build_payload,
                    "persist": True,
                    "confirm": True,
                    "base_checkpoint_id": preview.json()["preview"]["base_checkpoint_id"],
                },
            )
            assert confirmed.status_code == 200
            assert confirmed.json()["plan_id"]
            assert db.get_latest_planning_checkpoint() is not None

            public_plan = client.get("/api/planning/plan")
            assert public_plan.status_code == 200
            assert public_plan.json()["has_plan"] is True
            assert public_plan.json()["days"]

            today = client.get("/api/today")
            assert today.status_code == 200
            assert today.json()["state"] != "no_plan"
    finally:
        app.dependency_overrides.pop(get_database, None)
