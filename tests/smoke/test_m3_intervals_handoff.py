"""M3 acceptance: fresh Intervals-only store → sync → onboarding → first plan."""
from __future__ import annotations

import time
from datetime import datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from api.deps import get_database
from api.main import app
from api.routers import system as system_mod
from api.sync_jobs import sync_job_manager
from data.database import Database
from services import intervals_icu, planning_onboarding


pytestmark = pytest.mark.smoke


def _activity_rows() -> list[dict[str, Any]]:
    now = datetime.now()
    return [
        {
            "id": f"m3-{index}",
            "source": "STRAVA",
            "start_date": (now - timedelta(days=index)).isoformat(),
            "start_date_local": (now - timedelta(days=index)).isoformat(),
            "type": "Ride" if index % 2 else "Run",
            "name": f"M3 history {index}",
            "moving_time": 3600,
            "icu_training_load": 45.0 + (index % 4),
        }
        for index in range(28)
    ]


def _wait_for_sync(client: TestClient, timeout: float = 5.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        response = client.get("/api/sync")
        assert response.status_code == 200
        last = response.json()
        if last.get("sync_state") in {"succeeded", "partial", "failed"}:
            return last
        time.sleep(0.02)
    raise AssertionError(f"sync did not finish: {last}")


def test_m3_intervals_only_handoff_reaches_visible_plan(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = Database(str(tmp_path / "m3-handoff.db"))
    rows = _activity_rows()

    def fake_request(
        _self,
        _method: str,
        path: str,
        payload: Any | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        del payload
        if path.endswith("/calendars"):
            return []
        if path.endswith("/activities"):
            assert params is not None
            oldest = datetime.fromisoformat(str(params["oldest"])).date()
            newest = datetime.fromisoformat(str(params["newest"])).date()
            return [
                row
                for row in rows
                if oldest <= datetime.fromisoformat(row["start_date"]).date() <= newest
            ]
        raise AssertionError(f"unexpected Intervals request: {path}")

    sync_job_manager.reset_for_tests()
    monkeypatch.setattr(system_mod, "real_database", lambda: db)
    monkeypatch.setattr(system_mod.Settings, "GARMIN_EMAIL", None, raising=False)
    monkeypatch.setattr(system_mod.Settings, "GARMIN_PASSWORD", None, raising=False)
    monkeypatch.setattr(system_mod.Settings, "INTERVALS_ICU_API_KEY", "fake-m3-key", raising=False)
    monkeypatch.setattr(system_mod.Settings, "INTERVALS_ICU_ATHLETE_ID", "0", raising=False)
    monkeypatch.setattr(system_mod.Settings, "PRIMARY_ACTIVITY_SOURCE", "intervals", raising=False)
    monkeypatch.setattr(intervals_icu.IntervalsICUClient, "_request_json", fake_request)
    monkeypatch.setattr(
        planning_onboarding,
        "discover_intervals_events",
        lambda **_kwargs: {"events": [], "count": 0},
    )
    app.dependency_overrides[get_database] = lambda: db

    try:
        with TestClient(app) as client:
            providers = client.get("/api/sync/providers")
            assert providers.status_code == 200
            assert providers.json()["recommended_source"] == "intervals"

            connection = client.post("/api/sync/providers/intervals/test")
            assert connection.status_code == 200
            assert connection.json() == {
                "ok": True,
                "source": "intervals",
                "calendar_count": 0,
            }

            started = client.post("/api/sync", json={"source": "intervals", "days": 30})
            assert started.status_code == 200
            assert started.json()["source"] == "intervals"
            final = _wait_for_sync(client)
            assert final["sync_state"] == "succeeded"
            assert final["source"] == "intervals"
            assert final["result"]["counts"]["new"] == 28

            onboarding = client.get("/api/onboarding/planning")
            assert onboarding.status_code == 200
            suggested = onboarding.json()["suggested"]
            profile_payload = {key: item["value"] for key, item in suggested.items()}

            saved = client.put("/api/onboarding/planning", json=profile_payload)
            assert saved.status_code == 200
            assert saved.json()["completed"] is True

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

            plan = client.get("/api/planning/plan")
            assert plan.status_code == 200
            assert plan.json()["has_plan"] is True
            assert plan.json()["days"]

            today = client.get("/api/today")
            assert today.status_code == 200
            assert today.json()["state"] != "no_plan"
    finally:
        app.dependency_overrides.pop(get_database, None)
        sync_job_manager.reset_for_tests()

