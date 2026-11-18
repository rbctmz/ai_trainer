"""Bind transport preparation to one exact and presently eligible assignment."""

from uuid import UUID, uuid4

import pytest

from data.swim_program_store import confirm_preview, create_preview
from models.planning_build_confirmation import PlanningBuildPreviewError
from models.swim_calendar import SwimCalendarRequest
from services.swim_calendar import confirm_calendar, preview_calendar
from tests.smoke._planning_cycle_regressions import TODAY, legacy_db
from tests.smoke._swim_program_fixtures import changed_program, example_program


@pytest.fixture
def assignment(tmp_path, monkeypatch):
    db = legacy_db(tmp_path, monkeypatch, start=TODAY)
    saved = confirm_preview(db, create_preview(db, example_program(), base_revision=0)["preview_id"])
    check = preview_calendar(db, SwimCalendarRequest.model_validate({
        "request_id": str(uuid4()),
        "expected_checkpoint_id": db.get_current_planning_checkpoint()["id"],
        "operation": {
            "kind": "place",
            "program_id": saved["program_id"],
            "program_revision": saved["revision"],
            "dates": {"one": "2026-10-17"},
        },
    }))
    assigned = check["changes"][0]["after"]
    receipt = confirm_calendar(db, check["preview_id"])
    return db, assigned, receipt["checkpoint_id"]


def test_prepare_uses_selected_assignment_and_pinned_version(assignment):
    from services.swim_delivery import prepare_swim_delivery

    db, assigned, checkpoint_id = assignment
    edited = changed_program()
    edited["workouts"][0]["steps"][0]["distance_meters"] = 600
    second = confirm_preview(db, create_preview(db, edited, base_revision=1)["preview_id"])
    assert second["revision"] == 2

    prepared = prepare_swim_delivery(db, UUID(assigned["assignment_id"]), checkpoint_id)
    assert prepared.assignment.program_revision == 1
    assert prepared.assignment.program_fingerprint == assigned["program_fingerprint"]
    assert prepared.target_date.isoformat() == "2026-10-17"
    assert prepared.compiled.distance_meters == 2200
    assert prepared.payload["description"].endswith("100mtr intensity=active")
    assert prepared.payload["type"] == "Swim"
    assert prepared.payload["start_date_local"] == "2026-10-17T00:00:00"
    from models.intervals_workout_delivery import provider_event_is_owned

    assert not provider_event_is_owned(prepared.payload)
    assert db.get_current_planning_checkpoint()["id"] == checkpoint_id


def test_stale_preview_cannot_prepare_old_date_after_move(assignment):
    from services.swim_delivery import prepare_swim_delivery

    db, assigned, checkpoint_id = assignment
    assignment_id = UUID(assigned["assignment_id"])
    old = prepare_swim_delivery(db, assignment_id, checkpoint_id)
    proposed = preview_calendar(db, SwimCalendarRequest.model_validate({
        "request_id": str(uuid4()),
        "expected_checkpoint_id": checkpoint_id,
        "operation": {"kind": "move", "assignment_id": str(assignment_id), "date": "2026-10-18"},
    }))
    new = confirm_calendar(db, proposed["preview_id"])
    with pytest.raises(PlanningBuildPreviewError) as raised:
        prepare_swim_delivery(db, assignment_id, checkpoint_id)
    assert raised.value.code == "cycle_stale"
    after = prepare_swim_delivery(db, assignment_id, new["checkpoint_id"])
    assert old.payload["external_id"] == after.payload["external_id"]
    assert old.target_date != after.target_date
    assert old.compiled == after.compiled


def test_late_rest_constraint_prevents_transport_preparation(assignment):
    from services.swim_delivery import prepare_swim_delivery

    db, assigned, checkpoint_id = assignment
    db.save_coach_constraint(date=assigned["date"], kind="forced_rest", cycle_scope="athlete")

    with pytest.raises(PlanningBuildPreviewError) as raised:
        prepare_swim_delivery(db, UUID(assigned["assignment_id"]), checkpoint_id)
    assert raised.value.code == "swim_calendar_protected_day"
