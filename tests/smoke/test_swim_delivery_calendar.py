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


class IntervalsSandbox:
    def __init__(self):
        self.events = []
        self.creates = 0
        self.lose_response = False
        self.mismatch = False

    def is_configured(self):
        return True

    def list_workout_events(self, oldest, newest, *, strict):
        assert strict and oldest == newest
        return [event for event in self.events if event["start_date_local"][:10] == oldest.isoformat()]

    def get_workout_event(self, event_id):
        return next(event for event in self.events if event["id"] == event_id)

    def create_event(self, payload):
        import re
        from services.intervals_icu import IntervalsICUError

        self.creates += 1
        rows = []
        pattern = re.compile(r"- (?P<cue>.+) (?P<amount>\d+)(?P<unit>mtr|s) intensity=(?P<role>active|rest)(?P<lap> Press lap)?$")
        for line in payload["description"].splitlines()[2:]:
            matched = pattern.fullmatch(line)
            assert matched, line
            row = {"text": matched["cue"], "intensity": matched["role"]}
            row["distance" if matched["unit"] == "mtr" else "duration"] = int(matched["amount"])
            if matched["lap"]:
                row["until_lap_press"] = True
            rows.append(row)
        if self.mismatch:
            rows[0]["distance"] -= 25
        record = {
            **payload,
            "id": 101,
            "workout_doc": {
                "options": {"pool_length": "25m"}, "steps": rows,
                "distance": sum(row.get("distance", 0) for row in rows),
            },
        }
        self.events.append(record)
        if self.lose_response:
            raise IntervalsICUError("simulated acknowledgement loss")
        return record


def _preview_delivery(assignment):
    from services.swim_delivery import preview_swim_delivery

    db, row, checkpoint_id = assignment
    return preview_swim_delivery(db, uuid4(), UUID(row["assignment_id"]), checkpoint_id)


def test_preview_and_verified_receipt_preserve_provider_and_calendar_identity(assignment):
    from services.swim_delivery import confirm_swim_delivery

    db, _, checkpoint_id = assignment
    provider = IntervalsSandbox()
    preview = _preview_delivery(assignment)
    assert preview["target_date"] == "2026-10-17"
    assert preview["distance_meters"] == 2200
    assert preview["checkpoint_id"] == checkpoint_id
    assert provider.creates == 0
    assert preview["steps"][3]["distance_meters"] == 50
    assert preview["steps"][4]["clock"] == "time"
    assert preview["steps"][8]["clock"] == "lap"
    receipt = confirm_swim_delivery(db, UUID(preview["preview_id"]), client=provider)
    assert receipt["status"] == "provider_verified"
    assert receipt["provider_event_id"] == 101
    assert receipt["device_verified"] is False
    assert confirm_swim_delivery(db, UUID(preview["preview_id"]), client=provider) == receipt
    assert provider.creates == 1
    assert db.get_current_planning_checkpoint()["id"] == checkpoint_id


def test_confirmation_refuses_late_constraint_before_calling_provider(assignment):
    from services.swim_delivery import confirm_swim_delivery

    db, row, _ = assignment
    preview = _preview_delivery(assignment)
    provider = IntervalsSandbox()
    db.save_coach_constraint(date=row["date"], kind="forced_rest", cycle_scope="athlete")
    with pytest.raises(PlanningBuildPreviewError) as raised:
        confirm_swim_delivery(db, UUID(preview["preview_id"]), client=provider)
    assert raised.value.code in {"cycle_stale", "swim_calendar_protected_day"}
    assert provider.creates == 0


def test_acknowledgement_loss_can_be_reconciled_without_a_second_write(assignment):
    from services.swim_delivery import confirm_swim_delivery

    db, _, _ = assignment
    preview = _preview_delivery(assignment)
    provider = IntervalsSandbox()
    provider.lose_response = True
    first = confirm_swim_delivery(db, UUID(preview["preview_id"]), client=provider)
    assert first["status"] == "provider_unverified"
    assert first["provider_event_id"] is None
    later = confirm_swim_delivery(db, UUID(preview["preview_id"]), client=provider)
    assert later["status"] == "provider_verified"
    assert later["provider_event_id"] == 101
    assert provider.creates == 1


def test_provider_changed_structure_is_reported_and_never_replaced(assignment):
    from services.swim_delivery import confirm_swim_delivery

    db, _, _ = assignment
    preview = _preview_delivery(assignment)
    provider = IntervalsSandbox()
    provider.mismatch = True
    receipt = confirm_swim_delivery(db, UUID(preview["preview_id"]), client=provider)
    assert receipt["status"] == "provider_unverified"
    assert receipt["reason"] == "total_distance"
    with pytest.raises(PlanningBuildPreviewError) as raised:
        other = _preview_delivery(assignment)
        confirm_swim_delivery(db, UUID(other["preview_id"]), client=provider)
    assert raised.value.code == "swim_delivery_existing_attempt"
    assert provider.creates == 1


def test_existing_calendar_event_refuses_first_write(assignment):
    from services.swim_delivery import confirm_swim_delivery, prepare_swim_delivery

    db, row, checkpoint_id = assignment
    preview = _preview_delivery(assignment)
    candidate = prepare_swim_delivery(db, UUID(row["assignment_id"]), checkpoint_id)
    provider = IntervalsSandbox()
    provider.events = [{**candidate.payload, "id": 7345}]
    with pytest.raises(PlanningBuildPreviewError) as raised:
        confirm_swim_delivery(db, UUID(preview["preview_id"]), client=provider)
    assert raised.value.code == "swim_delivery_provider_conflict"
    assert provider.creates == 0
