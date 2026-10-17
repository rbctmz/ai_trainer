"""#685 M1: HTTP acceptance RED for the new confirmation protocol.

These are ordinary assertions, deliberately not xfail/skip. M1 records failures
before implementation; do not merge this draft milestone as a completed fix.
The two raw-save tests reach the existing unsafe writer, not just a missing route.
"""
from __future__ import annotations

from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.deps import get_database
from api.routers.planning import router
from tests.smoke._planning_build_confirmation import (
    add_late_activity,
    parameters,
    pin_clock,
    protected_state,
    seeded_db,
)

BUILD = "/api/planning/build"
CONFIRM = "/api/planning/build/confirm"


@pytest.fixture(params=[False, True], ids=["first-plan", "existing-plan"])
def scenario(tmp_path, monkeypatch, request):
    pin_clock(monkeypatch)
    db = seeded_db(tmp_path, existing=request.param)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_database] = lambda: db
    with TestClient(app) as client:
        yield client, db


def preview(client):
    response = client.post(BUILD, json=parameters())
    assert response.status_code == 200, response.text
    return response.json()


def identity(result):
    confirmation = result.get("confirmation")
    assert isinstance(confirmation, dict), "Preparation must return a server-owned preview identity"
    token = confirmation["preview_id"]
    assert str(UUID(token)) == token
    assert confirmation["status"] == "pending"
    return token


def test_legacy_raw_confirm_after_activity_change_cannot_write(scenario):
    client, db = scenario
    shown = preview(client)
    before = protected_state(db)
    add_late_activity(db)
    result = client.post(BUILD, json={
        **parameters(), "persist": True, "confirm": True,
        "base_checkpoint_id": shown["preview"]["base_checkpoint_id"],
    })
    after = protected_state(db)
    saved = result.json().get("totals", {}).get("total_tss")
    assert len(after["checkpoints"]) == len(before["checkpoints"]), (
        f"Raw confirm wrote a checkpoint: preview={shown['totals']['total_tss']}, "
        f"saved={saved}, HTTP={result.status_code}; unchanged base cannot protect activity changes"
    )
    assert after == before
    assert result.status_code == 409
    assert result.json()["code"] == "preview_required"


def test_legacy_unbound_retry_cannot_append_plans_or_change_demand(scenario):
    client, db = scenario
    before = protected_state(db)
    payload = {**parameters(), "demand": "aggressive", "persist": True, "confirm": True}
    first = client.post(BUILD, json=payload)
    second = client.post(BUILD, json=payload)
    after = protected_state(db)
    assert len(after["checkpoints"]) == len(before["checkpoints"]), (
        f"Unbound raw retry appended {len(after['checkpoints']) - len(before['checkpoints'])} "
        f"checkpoints; HTTP={first.status_code},{second.status_code}"
    )
    assert after == before, "Rejected raw requests must not change demand/profile"
    assert [first.status_code, second.status_code] == [409, 409]
    assert first.json()["code"] == second.json()["code"] == "preview_required"


def test_activity_added_after_preview_is_stale(scenario):
    client, db = scenario
    shown = preview(client)
    token = identity(shown)
    before = protected_state(db)
    add_late_activity(db)
    response = client.post(CONFIRM, json={"preview_id": token, "confirm": True})
    assert response.status_code == 409, response.text
    assert response.json()["code"] == "preview_stale"
    assert protected_state(db) == before


def test_confirm_twice_replays_exact_result_and_one_checkpoint(scenario):
    client, db = scenario
    shown = preview(client)
    token = identity(shown)
    before = protected_state(db)
    payload = {"preview_id": token, "confirm": True}
    first = client.post(CONFIRM, json=payload)
    second = client.post(CONFIRM, json=payload)
    assert first.status_code == second.status_code == 200
    applied, replay = first.json(), second.json()
    assert applied["plan_id"] == replay["plan_id"]
    assert applied["confirmation"]["replayed"] is False
    assert replay["confirmation"]["replayed"] is True
    assert replay["confirmation"]["is_current"] is True
    for key in ("goal", "weeks", "totals", "forecast", "science_audit", "preview", "parameters"):
        assert applied[key] == replay[key] == shown[key], key
    after = protected_state(db)
    assert len(after["checkpoints"]) == len(before["checkpoints"]) + 1


@pytest.mark.parametrize("payload", [
    {}, {"confirm": True},
    {"preview_id": "00000000-0000-4000-8000-000000000001", "confirm": False},
    {"preview_id": "00000000-0000-4000-8000-000000000001", "confirm": "true"},
    {"preview_id": "00000000-0000-4000-8000-000000000001", "confirm": 1},
    {"preview_id": "00000000-0000-4000-8000-000000000001", "confirm": True, "persist": True},
], ids=["empty", "missing-id", "false", "string-true", "integer-true", "extra-field"])
def test_strict_confirmation_cannot_write(scenario, payload):
    client, db = scenario
    before = protected_state(db)
    response = client.post(CONFIRM, json=payload)
    assert response.status_code == 422, response.text
    assert response.json()["code"] == "invalid_confirmation"
    assert protected_state(db) == before
