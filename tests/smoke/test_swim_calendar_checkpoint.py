"""Authored swimming assignments survive ordinary cycle writes."""

from copy import deepcopy
from datetime import timedelta

import pytest

from api import planning_service
from data.planning_cycles import publish_cycle_checkpoint
from models.planning_build_confirmation import PlanningBuildPreviewError
from models.planning_checkpoints import (
    build_planning_checkpoint,
    restore_goal_plan_from_checkpoint,
    with_checkpoint_provenance,
)
from tests.smoke._planning_cycle_regressions import TODAY, legacy_db, plan
from tests.smoke.test_planning_cycle_writer_guards import writer_state


def authored_calendar():
    return [{
        "assignment_id": "eecfbfac-3780-49d3-833d-6c0c2db2640d",
        "date": (TODAY + timedelta(days=4)).isoformat(),
        "program_id": "1b4e7935-d64c-4d75-9cab-48743c0f4981",
        "program_revision": 1,
        "program_fingerprint": "a" * 64,
        "workout_id": "synthetic-workout",
    }]


@pytest.fixture
def calendar_db(tmp_path, monkeypatch):
    checkpoint = build_planning_checkpoint(plan(TODAY))
    # Seed the format at the storage boundary to test preexisting assignments.
    checkpoint["goal_plan_snapshot"]["swim_calendar"] = authored_calendar()
    return legacy_db(tmp_path, monkeypatch, payloads=[checkpoint])


def ordinary_child(db):
    previous = db.get_current_planning_checkpoint()
    restored = restore_goal_plan_from_checkpoint(previous)
    restored["demand_level"] = "conservative"
    return build_planning_checkpoint(with_checkpoint_provenance(
        restored, source="execution_adjustment", parent_checkpoint_id=previous["id"],
    ))


def test_ordinary_checkpoint_roundtrip_retains_calendar(calendar_db):
    saved = calendar_db.save_planning_checkpoint(
        ordinary_child(calendar_db), cycle_context=calendar_db.planning_write_context(),
    )
    old = calendar_db.get_planning_checkpoint(saved["checkpoint_parent_id"])
    current = calendar_db.get_current_planning_checkpoint()
    assert current["goal_plan_snapshot"]["demand_level"] == "conservative"
    assert current["goal_plan_snapshot"]["swim_calendar"] == authored_calendar()
    assert old["goal_plan_snapshot"]["swim_calendar"] == authored_calendar()


@pytest.mark.parametrize("new_calendar", [[], [{**authored_calendar()[0], "program_revision": 2}]])
def test_generic_writer_cannot_remove_or_substitute_authored_workout(calendar_db, new_calendar):
    context = calendar_db.planning_write_context()
    checkpoint = ordinary_child(calendar_db)
    checkpoint["goal_plan_snapshot"]["swim_calendar"] = deepcopy(new_calendar)
    before = writer_state(calendar_db)
    with pytest.raises(PlanningBuildPreviewError) as error:
        calendar_db.save_planning_checkpoint(checkpoint, cycle_context=context)
    assert error.value.code == "swim_calendar_protected"
    assert writer_state(calendar_db) == before


@pytest.mark.parametrize("drop_calendar", [True, False])
def test_rebuilt_cycle_cannot_drop_or_strand_assignments(calendar_db, drop_calendar):
    db = calendar_db
    current = db.planning_write_context()
    candidate = ordinary_child(db)
    snapshot = candidate["goal_plan_snapshot"]
    if drop_calendar:
        snapshot.pop("swim_calendar", None)
    else:
        snapshot["swim_calendar"] = authored_calendar()
        snapshot["daily_plan"] = snapshot["daily_plan"][:4]
        snapshot["session_templates"] = snapshot["session_templates"][:4]
    lifecycle = {
        "action": "edit_current",
        "source_cycle_id": current["cycle_id"],
        "target_cycle_id": current["cycle_id"],
        "base_selection_revision": current["selection_revision"],
        "base_cycle_revision": current["cycle_revision"],
        "base_checkpoint_id": current["checkpoint_id"],
        "start_date": current["start_date"],
        "end_date": snapshot["daily_plan"][-1]["date"][:10],
        "closes_cycle_id": None,
    }
    before = writer_state(db)
    conn = db._connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        saved = db._insert_planning_checkpoint(conn, candidate)
        with pytest.raises(PlanningBuildPreviewError) as error:
            publish_cycle_checkpoint(conn, lifecycle, candidate, saved["id"], "2026-10-16T09:00:00Z")
        conn.rollback()
    finally:
        conn.close()
    assert error.value.code == "swim_calendar_protected"
    assert writer_state(db) == before


def test_history_restore_keeps_current_assignments(tmp_path, monkeypatch):
    earlier = build_planning_checkpoint(plan(TODAY))
    current = deepcopy(earlier)
    current["goal_plan_snapshot"]["swim_calendar"] = authored_calendar()
    db = legacy_db(tmp_path, monkeypatch, payloads=[earlier, current])
    context = db.planning_write_context()
    result = planning_service.restore_history_version(
        db, checkpoint_id=1, base_checkpoint_id=context["checkpoint_id"],
        expected_cycle_id=context["cycle_id"], expected_cycle_revision=context["cycle_revision"],
        expected_selection_revision=context["selection_revision"], action="restore_legacy_version",
    )
    latest = db.get_current_planning_checkpoint()
    assert latest["id"] == result["applied_checkpoint_id"]
    assert latest["goal_plan_snapshot"]["swim_calendar"] == authored_calendar()
    assert "swim_calendar" not in db.get_planning_checkpoint(1)["goal_plan_snapshot"]


def test_cycle_switch_preserves_old_schedule_without_adopting_it(calendar_db):
    from tests.smoke.test_planning_cycle_build_v2 import confirm, prepare

    old = calendar_db.get_current_planning_checkpoint()
    confirm(calendar_db, prepare(calendar_db))
    latest = calendar_db.get_current_planning_checkpoint()
    assert "swim_calendar" not in latest["goal_plan_snapshot"]
    assert calendar_db.get_planning_checkpoint(old["id"]) == old
