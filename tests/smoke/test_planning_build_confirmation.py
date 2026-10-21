"""#685 HTTP acceptance: M1 recorded RED; M3 must keep these assertions GREEN.

The raw-save tests exercise explicit rejection of the former unsafe writer.
"""
from __future__ import annotations

from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.deps import get_database
from api.routers.planning import router
from api.routers.planning_cycles import router as cycles_router
from tests.smoke._planning_build_confirmation import (
    add_late_activity,
    cycle_fields,
    ready_parameters as parameters,
    pin_clock,
    protected_state,
    seeded_db,
)

BUILD = "/api/planning/build"
CONFIRM = "/api/planning/build/confirm"


@pytest.fixture(params=[False, True], ids=["first-plan", "existing-plan"])
def scenario(tmp_path, monkeypatch, request):
    pin_clock(monkeypatch)
    db = seeded_db(tmp_path, existing=request.param, rested=True)
    app = FastAPI()
    app.include_router(router)
    app.include_router(cycles_router)
    app.dependency_overrides[get_database] = lambda: db
    with TestClient(app) as client:
        yield client, db


def preview(client):
    db = client.app.dependency_overrides[get_database]()
    response = client.post(BUILD, json={**parameters(), **cycle_fields(db)})
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


@pytest.mark.parametrize("payload", [
    {"preview_id": "not-a-uuid", "confirm": True},
    {"preview_id": None, "confirm": True},
    {"preview_id": 123, "confirm": True},
    {"preview_id": "00000000-0000-4000-8000-000000000001"},
])
def test_bad_identity_uses_safe_protocol_envelope(scenario, payload):
    client, db = scenario
    before = protected_state(db)
    response = client.post(CONFIRM, json=payload)
    assert response.status_code == 422
    assert response.json() == {"code": "invalid_confirmation", "retryable": False, "detail": "Проверьте подтверждение."}
    assert protected_state(db) == before


@pytest.mark.parametrize("patch,code,status", [
    ({"persist": True}, "preview_required", 409),
    ({"confirm": True}, "invalid_confirmation", 422),
    ({"start_week": "2026-99-99"}, "invalid_start_date", 422),
    ({"available_hours": -1}, "invalid_build_request", 422),
    ({"available_hours": "nan"}, "invalid_build_request", 422),
    ({"origin": "coach"}, "invalid_build_request", 422),
    ({"checkpoint_json": "{}"}, "invalid_build_request", 422),
    ({"base_checkpoint_id": 999}, "cycle_stale", 409),
])
def test_invalid_build_and_legacy_flags_never_write(scenario, patch, code, status):
    client, db = scenario
    before = protected_state(db)
    response = client.post(BUILD, json={**parameters(), **cycle_fields(db), **patch})
    assert response.status_code == status, response.text
    assert response.json()["code"] == code
    assert response.json()["retryable"] is False
    assert isinstance(response.json()["detail"], str)
    assert protected_state(db) == before


def test_unknown_identity_uses_protocol_envelope(scenario):
    client, db = scenario
    before = protected_state(db)
    response = client.post(CONFIRM, json={"preview_id": "00000000-0000-4000-8000-000000000001", "confirm": True})
    assert response.status_code == 404
    assert response.json()["code"] == "preview_not_found"
    assert protected_state(db) == before


def test_malformed_json_is_safe_and_unrelated_route_keeps_validation(scenario):
    client, db = scenario
    for endpoint, code in ((BUILD, "invalid_build_request"), (CONFIRM, "invalid_confirmation")):
        response = client.post(endpoint, content="{broken", headers={"Content-Type": "application/json"})
        assert response.status_code == 422
        assert response.json()["code"] == code
    unrelated = client.post("/api/planning/history/restore", json={})
    assert unrelated.status_code == 422
    assert isinstance(unrelated.json()["detail"], list)
    assert "code" not in unrelated.json()
