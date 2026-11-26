"""Exercise the grouped projection and the one-send application boundary."""

from datetime import date
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from config.settings import Settings
from data.swim_program_store import confirm_preview, create_preview
from models.garmin_swim_delivery import project_garmin_swim
from models.planning_build_confirmation import PlanningBuildPreviewError
from models.swim_calendar import SwimCalendarRequest
from models.swim_delivery import SwimDeliveryUnsupported
from models.swim_program_documents import validate_program_document
from services import garmin_swim_delivery, garmin_swim_mcp, swim_delivery
from services.swim_calendar import confirm_calendar, preview_calendar
from tests.smoke._planning_cycle_regressions import TODAY, legacy_db
from tests.swim_delivery_fixtures import GarminSandbox, IntervalsSandbox, garmin_repeat_program


@pytest.fixture
def delivery(tmp_path, monkeypatch):
    fake = GarminSandbox()
    monkeypatch.setattr(Settings, "ACCEPTANCE_MODE", False)
    monkeypatch.setattr(garmin_swim_mcp, "configured_script", lambda: Path("fake"))
    monkeypatch.setattr(garmin_swim_mcp, "call", fake.call)
    db = legacy_db(tmp_path, monkeypatch, start=TODAY)
    saved = confirm_preview(db, create_preview(db, garmin_repeat_program(), base_revision=0)["preview_id"])
    check = preview_calendar(db, SwimCalendarRequest.model_validate({
        "request_id": str(uuid4()), "expected_checkpoint_id": db.get_current_planning_checkpoint()["id"],
        "operation": {"kind": "place", "program_id": saved["program_id"],
                      "program_revision": saved["revision"], "dates": {"one": "2026-10-17"}},
    }))
    receipt = confirm_calendar(db, check["preview_id"])
    return db, UUID(check["changes"][0]["after"]["assignment_id"]), receipt["checkpoint_id"], fake


def test_keeps_native_groups_and_leaf_fields_without_changing_source():
    raw = garmin_repeat_program()
    doc = validate_program_document(raw)
    result = project_garmin_swim(doc, "one", date(2026, 11, 28))
    group = result["steps"][0]
    assert (group["repetitions"], group["skip_last_rest"]) == (2, True)
    assert group["steps"][0] == {"type": "main", "distance_meters": 25, "stroke": "drill",
                                 "drill": "drill", "equipment": "fins", "description": "Synthetic swim"}
    assert group["steps"][1]["duration_seconds"] == 30
    assert doc == validate_program_document(raw)


@pytest.mark.parametrize(("mutation", "reason"), [("open_rest", "garmin_unsupported_rest"),
    ("unspecified_last_rest", "garmin_last_rest_unspecified"), ("second_equipment", "garmin_unsupported_equipment"),
    ("long_cue", "garmin_cue_too_long")])
def test_unrepresentable_steps_have_specific_errors(mutation, reason):
    raw = garmin_repeat_program()
    group = raw["workouts"][0]["steps"][0]
    if mutation == "open_rest":
        group["steps"][1].update(mode="open", seconds=None)
    elif mutation == "unspecified_last_rest":
        group["last_rest"] = "unspecified"
    elif mutation == "second_equipment":
        group["steps"][0]["equipment"].append("paddles")
    else:
        group["steps"][0]["instructions"] = "x" * 201
    with pytest.raises(SwimDeliveryUnsupported) as raised:
        project_garmin_swim(validate_program_document(raw), "one", date(2026, 11, 28))
    assert raised.value.code == reason


def test_pins_assignment_and_replays_exact_receipt_without_second_send(delivery):
    db, assignment, checkpoint, fake = delivery
    request = uuid4()
    preview = garmin_swim_delivery.preview_garmin_swim(db, request, assignment, checkpoint)
    assert preview == garmin_swim_delivery.preview_garmin_swim(db, request, assignment, checkpoint)
    assert fake.calls == ["preview_swim_workout"]
    assert (preview["distance_meters"], preview["fixed_rest_count"]) == (75, 1)
    assert preview["assignment"]["program_revision"] == 1
    assert preview["schedule_date"] == "2026-10-17"
    other = swim_delivery.preview_swim_delivery(db, uuid4(), assignment, checkpoint)
    receipt = garmin_swim_delivery.confirm_garmin_swim(db, request, demo=False)
    assert receipt["status"] == "scheduled" and receipt["device_verified"] is False
    assert receipt == garmin_swim_delivery.confirm_garmin_swim(db, request, demo=False)
    assert garmin_swim_delivery.read_garmin_swim(db, assignment, demo=False)["receipt"] == receipt
    with pytest.raises(PlanningBuildPreviewError) as error:
        swim_delivery.confirm_swim_delivery(db, UUID(other["preview_id"]), client=IntervalsSandbox())
    assert error.value.code == "swim_delivery_garmin_attempt"
    assert fake.calls.count("send_swim_workout") == 1


def test_timeout_can_recover_only_the_existing_draft(delivery):
    db, assignment, checkpoint, fake = delivery
    request = uuid4()
    garmin_swim_delivery.preview_garmin_swim(db, request, assignment, checkpoint)
    fake.lose_response = fake.hide_result = True
    assert garmin_swim_delivery.confirm_garmin_swim(db, request, demo=False)["status"] == "uncertain"
    with pytest.raises(PlanningBuildPreviewError) as error:
        garmin_swim_delivery.preview_garmin_swim(db, uuid4(), assignment, checkpoint)
    assert error.value.code == "garmin_swim_existing_attempt"
    fake.hide_result = False
    assert garmin_swim_delivery.confirm_garmin_swim(db, request, demo=False)["status"] == "scheduled"
    assert fake.calls == ["preview_swim_workout", "send_swim_workout", "get_swim_workout_draft", "get_swim_workout_draft"]


def test_changed_date_or_demo_does_not_start_send(delivery):
    db, assignment, checkpoint, fake = delivery
    request = uuid4()
    garmin_swim_delivery.preview_garmin_swim(db, request, assignment, checkpoint)
    with pytest.raises(PlanningBuildPreviewError):
        garmin_swim_delivery.confirm_garmin_swim(db, request, demo=True)
    moved = preview_calendar(db, SwimCalendarRequest.model_validate({
        "request_id": str(uuid4()), "expected_checkpoint_id": checkpoint,
        "operation": {"kind": "move", "assignment_id": str(assignment), "date": "2026-10-18"},
    }))
    confirm_calendar(db, moved["preview_id"])
    with pytest.raises(PlanningBuildPreviewError) as error:
        garmin_swim_delivery.confirm_garmin_swim(db, request, demo=False)
    assert error.value.code == "cycle_stale"
    assert fake.calls == ["preview_swim_workout"]


def test_bridge_uses_owned_executable_boundary_and_sanitizes_errors(tmp_path, monkeypatch):
    import json
    import subprocess
    import sys

    fake = tmp_path / "readonly_proxy.py"
    fake.touch()
    monkeypatch.setenv("GARMIN_SWIM_TEST_SECRET", "NEVER_FORWARDED")
    monkeypatch.setattr(Settings, "GARMIN_SWIM_MCP_SCRIPT", str(fake))

    def child(args, *, input, env, **kwargs):
        assert args == [sys.executable, str(fake), "--swim-delivery"]
        assert "GARMIN_SWIM_TEST_SECRET" not in env
        assert kwargs["check"]
        item = json.loads(input)
        if item["name"] != "preview_swim_workout":
            raise subprocess.CalledProcessError(1, args, stderr="Synthetic private stderr")
        return subprocess.CompletedProcess(args, 0, stdout=json.dumps({"result": item["arguments"]}))

    monkeypatch.setattr(garmin_swim_mcp.subprocess, "run", child)
    assert garmin_swim_mcp.call("preview_swim_workout", {"spec": {"name": "Бассейн"}}) == {
        "spec": {"name": "Бассейн"},
    }
    with pytest.raises(garmin_swim_mcp.GarminSwimBridgeError) as error:
        garmin_swim_mcp.call("get_swim_workout_draft", {"draft_id": "unsupported"})
    assert "Synthetic private stderr" not in str(error.value)


def test_delayed_calendar_receipt_is_verified_without_resending(delivery, monkeypatch):
    db, assignment, checkpoint, fake = delivery
    request = uuid4()
    garmin_swim_delivery.preview_garmin_swim(db, request, assignment, checkpoint)
    bridge = fake.call

    def late_ack(action, arguments):
        result = bridge(action, arguments)
        if action == "send_swim_workout":
            return {**result, "calendar_scheduled": False, "schedule_status": "sent_readback_unverified"}
        return result

    monkeypatch.setattr(garmin_swim_mcp, "call", late_ack)
    assert garmin_swim_delivery.confirm_garmin_swim(db, request, demo=False)["status"] == "workout_verified"
    arguments = []

    def scheduled_on(workout_id, day):
        arguments.append((workout_id, day))
        return len(arguments) > 1

    monkeypatch.setattr(garmin_swim_mcp, "scheduled_on", scheduled_on)
    assert garmin_swim_delivery.confirm_garmin_swim(db, request, demo=False)["status"] == "workout_verified"
    assert garmin_swim_delivery.confirm_garmin_swim(db, request, demo=False)["status"] == "scheduled"
    assert garmin_swim_delivery.confirm_garmin_swim(db, request, demo=False)["status"] == "scheduled"
    assert arguments == [(123, "2026-10-17")] * 2
    assert fake.calls.count("send_swim_workout") == 1
