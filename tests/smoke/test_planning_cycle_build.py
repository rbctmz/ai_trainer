"""S2 M1 preliminary protocol RED; transaction proofs belong to M2/M3."""
from dataclasses import replace
import json
from uuid import uuid4

import pytest

from api import planning_service as ps
from models.planning_build_confirmation import BuildParameters
from tests.smoke._planning_build_confirmation import parameters
from tests.smoke._planning_cycle_regressions import (
    CYCLE_B, TODAY, client_for, evidence_bytes, legacy_db,
)

pytestmark = pytest.mark.smoke


def test_behavior_actual_start_clips_canonical_prescriptions_not_just_week_label(tmp_path, monkeypatch):
    """Exercise the real pure calculator with the approved frozen lifecycle.

    M3 still has to capture/validate this context through HTTP. Injecting it at
    the existing pure calculation seam avoids inventing a public request field
    for the lifecycle action before M3 freezes its Pydantic contract.
    """
    db = legacy_db(tmp_path, monkeypatch, payloads=[])
    request = {**parameters(), "events": [], "start_week": "2026-10-12"}
    snapshot = ps._capture_plan_build_inputs(db, BuildParameters.from_mapping(request))
    context = snapshot.context()
    context["lifecycle"] = {
        "action": "start_new", "source_cycle_id": None, "target_cycle_id": CYCLE_B,
        "base_cycle_revision": None, "base_selection_revision": 0,
        "base_checkpoint_id": 0, "start_date": TODAY.isoformat(),
        "end_date": "2026-12-06", "closes_cycle_id": None,
    }
    prepared = ps._calculate_plan_build(replace(snapshot, context_json=json.dumps(context)))
    daily = json.loads(prepared.checkpoint_json)["goal_plan_snapshot"]["daily_plan"]
    executable = [row["date"][:10] for row in daily if row["total_tss"] > 0]
    assert executable, "A vacuous empty preview does not satisfy start_new"
    assert min(executable) >= TODAY.isoformat(), executable


def current(client):
    response = client.get("/api/planning/cycles/current")
    assert response.status_code == 200, response.text
    return response.json()


def close(client, context, **overrides):
    payload = {
        "command_id": str(uuid4()), "confirm": True,
        "expected_selection_revision": context["selection_revision"],
        "expected_cycle_revision": context["cycle_revision"],
        "expected_checkpoint_id": context["checkpoint_id"],
        **overrides,
    }
    return client.post(f'/api/planning/cycles/{context["cycle_id"]}/close', json=payload)


def test_protocol_start_new_context_clears_old_calendar_and_goal(tmp_path, monkeypatch):
    db = legacy_db(tmp_path, monkeypatch)
    before = evidence_bytes(db)
    with client_for(db) as client:
        response = client.get("/api/planning/build-context", params={"action": "start_new"})
    assert response.status_code == 200, response.text
    inputs = response.json()["inputs"]
    assert inputs["start_date"] == "2026-10-16"
    assert inputs["calendar_week_start"] == "2026-10-12"
    assert inputs["events"] == []
    for key in ("event_date", "manual_phases", "goal_type", "distance", "intent"):
        assert not inputs.get(key), f"start_new inherited {key}"
    assert evidence_bytes(db) == before


def test_protocol_ended_cycle_edit_is_explicit_conflict(tmp_path, monkeypatch):
    db = legacy_db(tmp_path, monkeypatch)
    with client_for(db) as client:
        response = client.get("/api/planning/build-context", params={"action": "edit_current"})
    assert response.status_code == 409, response.text
    assert response.json()["code"] == "cycle_period_ended"


def test_protocol_legacy_build_without_action_requires_cycle_context(tmp_path, monkeypatch):
    db = legacy_db(tmp_path, monkeypatch)
    before = evidence_bytes(db)
    with client_for(db) as client:
        response = client.post("/api/planning/build", json=parameters())
    assert response.status_code == 409, response.text
    assert response.json()["code"] == "cycle_context_required"
    assert evidence_bytes(db) == before


def test_protocol_close_retry_keeps_history_and_null_selection_after_restart(tmp_path, monkeypatch):
    from data.database import Database

    db = legacy_db(tmp_path, monkeypatch)
    before = evidence_bytes(db)
    command_id = str(uuid4())
    with client_for(db) as client:
        context = current(client)
        response = close(client, context, command_id=command_id)
        assert response.status_code == 200, response.text
        applied = response.json()
        assert applied["current_context"]["state"] == "no_current"
        replay = close(client, context, command_id=command_id)
        assert replay.status_code == 200, replay.text
        assert replay.json()["replayed"] is True
        assert replay.json()["result"] == applied["result"]
        historical = client.get(f'/api/planning/cycles/{context["cycle_id"]}')
        assert historical.status_code == 200, historical.text
        assert historical.json()["state"] == "closed"
        assert historical.json()["is_selected"] is False
        assert all(event["outcome"] == "unspecified" for event in historical.json()["events"])
    reopened = Database(str(tmp_path / "plan.db"))
    with client_for(reopened) as client:
        assert current(client)["state"] == "no_current"
        assert client.get("/api/planning/status").json()["has_plan"] is False
    assert evidence_bytes(reopened) == before
    assert reopened.get_latest_planning_checkpoint()["id"] == context["checkpoint_id"]


@pytest.mark.parametrize("confirm", [False, "true", 1, None])
def test_protocol_close_requires_strict_confirmation(tmp_path, monkeypatch, confirm):
    db = legacy_db(tmp_path, monkeypatch)
    before = evidence_bytes(db)
    with client_for(db) as client:
        response = close(client, current(client), confirm=confirm)
        assert response.status_code == 422, response.text
    assert evidence_bytes(db) == before


def test_protocol_changed_command_identity_is_conflict(tmp_path, monkeypatch):
    db = legacy_db(tmp_path, monkeypatch)
    command_id = str(uuid4())
    with client_for(db) as client:
        context = current(client)
        response = close(client, context, command_id=command_id)
        assert response.status_code == 200, response.text
        response = close(client, context, command_id=command_id, expected_checkpoint_id=999)
        assert response.status_code == 409, response.text
        assert response.json()["code"] == "idempotency_conflict"


def test_protocol_historical_outcome_correction_does_not_reopen(tmp_path, monkeypatch):
    db = legacy_db(tmp_path, monkeypatch)
    before = evidence_bytes(db)
    with client_for(db) as client:
        context = current(client)
        response = close(client, context)
        assert response.status_code == 200, response.text
        historical = client.get(f'/api/planning/cycles/{context["cycle_id"]}').json()
        response = client.post(f'/api/planning/cycles/{context["cycle_id"]}/event-outcome', json={
            "command_id": str(uuid4()), "confirm": True,
            "expected_cycle_revision": historical["cycle_revision"],
            "event_key": historical["events"][0]["event_key"], "outcome": "did_not_participate",
        })
        assert response.status_code == 200, response.text
        assert response.json()["current_context"]["state"] == "no_current"
        corrected = client.get(f'/api/planning/cycles/{context["cycle_id"]}').json()
        assert corrected["state"] == "closed"
        assert corrected["events"][0]["outcome"] == "did_not_participate"
    assert evidence_bytes(db) == before
