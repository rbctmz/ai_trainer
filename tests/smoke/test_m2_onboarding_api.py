"""M2 гейты API-контракта онбординга (#271 §4).

`GET/PUT /api/onboarding/planning` — вход планирования как явный ресурс. Эндпоинт
НЕ строит план: построение остаётся на `POST /api/planning/build` с его preview-гейтом
409, иначе профиль и решение с checkpoint'ом склеятся в один необратимый вызов.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from api.deps import get_database
from api.main import app
from data.database import Database
from services.intervals_icu import IntervalsICUError
from services import planning_onboarding as onboarding_service


pytestmark = pytest.mark.smoke


VALID = {
    "planning_mode": "training_goal",
    "intent": "develop",
    "goal_type": "run",
    "distance": "10k",
    "available_hours": 6.0,
    "available_days": ["tue", "thu", "sun"],
    "horizon_weeks": 6,
}


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Клиент поверх ВРЕМЕННОЙ базы — правило изоляции из ревью M1."""
    db = Database(str(tmp_path / "onboarding_api.db"))
    monkeypatch.setattr(
        onboarding_service,
        "discover_intervals_events",
        lambda **_kwargs: {"events": [], "count": 0},
    )
    app.dependency_overrides[get_database] = lambda: db
    try:
        with TestClient(app) as test_client:
            test_client.db = db  # type: ignore[attr-defined]
            yield test_client
    finally:
        app.dependency_overrides.pop(get_database, None)


def test_get_returns_not_completed_with_suggestion_on_fresh_install(client):
    response = client.get("/api/onboarding/planning")

    assert response.status_code == 200
    body = response.json()
    assert body["completed"] is False
    assert body["profile"] is None
    assert body["suggested"]["planning_mode"]["value"] == "training_goal"
    assert body["suggested"]["available_hours"]["basis"] == "fallback"
    assert body["event_context"]["has_a_race"] is False
    assert body["event_context"]["degraded_reason"] is None


def test_put_persists_profile_and_get_reflects_it(client):
    put = client.put("/api/onboarding/planning", json=VALID)

    assert put.status_code == 200
    assert put.json()["completed"] is True
    assert put.json()["profile"]["available_days"] == ["tue", "thu", "sun"]

    body = client.get("/api/onboarding/planning").json()
    assert body["completed"] is True
    assert body["profile"]["goal_type"] == "run"
    assert body["profile"]["available_hours"] == 6.0
    # Предложение остаётся доступным и после заполнения — атлет вправе пересобрать
    # параметры от предложенных.
    assert body["suggested"]


@pytest.mark.parametrize(
    "patch",
    [
        {"planning_mode": "freestyle"},
        {"intent": "recover"},
        {"goal_type": "curling"},
        {"available_hours": 0},
        {"available_hours": True},
        {"available_days": []},
        {"horizon_weeks": True},
        {"horizon_weeks": 6.5},
        {"horizon_weeks": 500},
    ],
)
def test_put_rejects_invalid_payload_with_422(client, patch):
    response = client.put("/api/onboarding/planning", json={**VALID, **patch})

    assert response.status_code == 422
    assert client.get("/api/onboarding/planning").json()["completed"] is False


def test_put_rejection_does_not_clobber_saved_profile(client):
    client.put("/api/onboarding/planning", json=VALID)

    rejected = client.put("/api/onboarding/planning", json={**VALID, "intent": "recover"})

    assert rejected.status_code == 422
    assert client.get("/api/onboarding/planning").json()["profile"]["intent"] == "develop"


def test_corrupt_stored_profile_does_not_break_the_endpoint(client):
    from services.planning_profile import PLANNING_PROFILE_SETTING_KEY

    client.db.set_user_setting(PLANNING_PROFILE_SETTING_KEY, "{not json")

    response = client.get("/api/onboarding/planning")

    assert response.status_code == 200
    assert response.json()["completed"] is False


def test_intervals_outage_returns_200_with_reason_not_503(client, monkeypatch):
    def _boom(**_kwargs):
        raise IntervalsICUError("Intervals.icu вернул 503.")

    monkeypatch.setattr(onboarding_service, "discover_intervals_events", _boom)

    response = client.get("/api/onboarding/planning")

    assert response.status_code == 200
    body = response.json()
    assert body["event_context"]["degraded_reason"]
    assert body["suggested"]["planning_mode"]["value"] == "training_goal"


def test_confirmed_a_race_is_surfaced_for_event_goal(client, monkeypatch):
    race_day = (date.today() + timedelta(days=90)).isoformat()
    monkeypatch.setattr(
        onboarding_service,
        "discover_intervals_events",
        lambda **_kwargs: {
            "events": [{"date": race_day, "priority": "A", "confirmed": True, "label": "Ironstar"}],
            "count": 1,
        },
    )

    body = client.get("/api/onboarding/planning").json()

    assert body["event_context"]["has_a_race"] is True
    assert body["event_context"]["a_races"][0]["date"] == race_day
    assert body["suggested"]["planning_mode"]["value"] == "event_goal"


def test_onboarding_endpoint_never_builds_a_plan(client):
    """Профиль — это вход, план — решение с checkpoint'ом. Склеивать нельзя."""
    from api import planning_service

    client.put("/api/onboarding/planning", json=VALID)

    assert planning_service.get_active_plan(client.db) is None
