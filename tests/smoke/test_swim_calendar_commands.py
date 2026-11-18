"""Review and confirm calendar changes against the actual selected cycle."""

from datetime import timedelta
from uuid import uuid4

import pytest

from data.swim_program_store import confirm_preview, create_preview
from models.planning_build_confirmation import PlanningBuildPreviewError
from models.planning_checkpoints import build_planning_checkpoint
from tests.smoke._planning_cycle_regressions import TODAY, client_for, legacy_db, plan
from tests.smoke._swim_program_fixtures import example_program


@pytest.fixture
def calendar(tmp_path, monkeypatch):
    db = legacy_db(tmp_path, monkeypatch, start=TODAY)
    preview = create_preview(db, example_program(), base_revision=0)
    saved = confirm_preview(db, preview["preview_id"])
    return db, saved


def place_request(db, saved, offset):
    return {
        "request_id": str(uuid4()),
        "expected_checkpoint_id": db.get_current_planning_checkpoint()["id"],
        "operation": {
            "kind": "place",
            "program_id": saved["program_id"],
            "program_revision": saved["revision"],
            "dates": {"one": (TODAY + timedelta(days=offset)).isoformat()},
        },
    }


def test_review_confirm_move_and_rollback_retain_exact_workout(calendar):
    from models.swim_calendar import SwimCalendarRequest
    from services.swim_calendar import confirm_calendar, preview_calendar, read_calendar

    db, saved = calendar
    initial = db.get_current_planning_checkpoint()
    shown = preview_calendar(db, SwimCalendarRequest.model_validate(place_request(db, saved, 1)))
    assert db.get_current_planning_checkpoint() == initial
    assert shown["changes"][0]["before"] is None
    assignment = shown["changes"][0]["after"]
    assert assignment["program_fingerprint"] == saved["fingerprint"]
    assert assignment["duration_minutes"] is None and assignment["tss"] is None
    assert assignment["distance_meters"] == 2200
    assert assignment["source_week_label"] == "Example block"
    assert assignment["date"] == "2026-10-17"
    confirmed = confirm_calendar(db, shown["preview_id"])
    chosen = confirmed["checkpoint_id"]
    assert confirm_calendar(db, shown["preview_id"]) == confirmed
    assert read_calendar(db)["assignments"] == [assignment]

    moved = preview_calendar(db, SwimCalendarRequest.model_validate({
        "request_id": str(uuid4()),
        "expected_checkpoint_id": chosen,
        "operation": {"kind": "move", "assignment_id": assignment["assignment_id"], "date": "2026-10-18"},
    }))
    assert moved["changes"] == [{"before": assignment, "after": {**assignment, "date": "2026-10-18"}}]
    receipt = confirm_calendar(db, moved["preview_id"])
    assert read_calendar(db, checkpoint_id=chosen)["assignments"] == [assignment]

    restore = preview_calendar(db, SwimCalendarRequest.model_validate({
        "request_id": str(uuid4()),
        "expected_checkpoint_id": receipt["checkpoint_id"],
        "operation": {"kind": "rollback", "checkpoint_id": chosen},
    }))
    confirm_calendar(db, restore["preview_id"])
    assert read_calendar(db)["assignments"] == [assignment]
    assert read_calendar(db, checkpoint_id=initial["id"])["assignments"] == []


def test_competing_confirmation_cannot_apply_to_changed_calendar(calendar):
    from models.swim_calendar import SwimCalendarRequest
    from services.swim_calendar import confirm_calendar, preview_calendar

    db, saved = calendar
    first, second = [
        preview_calendar(db, SwimCalendarRequest.model_validate(place_request(db, saved, offset)))
        for offset in (1, 2)
    ]
    committed = confirm_calendar(db, first["preview_id"])
    with pytest.raises(PlanningBuildPreviewError) as error:
        confirm_calendar(db, second["preview_id"])
    assert error.value.code == "cycle_stale"
    assert db.get_current_planning_checkpoint()["id"] == committed["checkpoint_id"]


def test_http_confirm_is_explicit_and_keeps_receipt(calendar):
    db, saved = calendar
    root = "/api/planning/swim-calendar"
    request = place_request(db, saved, 1)
    request["operation"]["dates"]["two"] = "2026-10-19"
    with client_for(db) as client:
        response = client.post(f"{root}/preview", json=request)
        assert response.status_code == 200, response.text
        shown = response.json()
        assert [change["after"]["distance_meters"] for change in shown["changes"]] == [2200, 2000]
        assert {warning["code"] for warning in shown["warnings"]} == {"load_uncertain", "other_sessions_on_day"}
        assert client.post(f"{root}/preview", json=request).json() == shown
        assert client.get(root).json()["assignments"] == []
        for false_confirm in (False, 1, "true"):
            refused = client.post(f"{root}/confirm", json={"preview_id": shown["preview_id"], "confirm": false_confirm})
            assert refused.status_code == 422, refused.text
        confirmed = client.post(f"{root}/confirm", json={"preview_id": shown["preview_id"], "confirm": True})
        assert confirmed.status_code == 200, confirmed.text
        assert client.get(root).json()["checkpoint_id"] == confirmed.json()["checkpoint_id"]
        assert client.get(f"{root}?checkpoint_id={shown['base_checkpoint_id']}").json()["assignments"] == []


def test_date_specific_sport_rule_overrides_default_weekday(tmp_path, monkeypatch):
    goal = plan(TODAY)
    goal["allowed_sports_by_day"] = {"sat": ["swim"], "2026-10-17": [], "sun": ["bike"], "2026-10-18": ["swim"]}
    db = legacy_db(tmp_path, monkeypatch, payloads=[build_planning_checkpoint(goal)])
    document = create_preview(db, example_program(), base_revision=0)
    saved = confirm_preview(db, document["preview_id"])
    with client_for(db) as client:
        root = "/api/planning/swim-calendar/preview"
        denied = client.post(root, json=place_request(db, saved, 1))
        assert denied.status_code == 409 and denied.json()["code"] == "swim_calendar_sport_unavailable"
        admitted = client.post(root, json=place_request(db, saved, 2))
        assert admitted.status_code == 200, admitted.text
