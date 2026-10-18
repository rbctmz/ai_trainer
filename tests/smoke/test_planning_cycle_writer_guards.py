"""Selected-cycle write invariants; only synthetic pre-migration SQLite."""
from datetime import timedelta
from uuid import uuid4
import sqlite3

import pytest

from api import planning_service as ps
from models.planning_build_confirmation import PlanningBuildPreviewError
from models.planning_checkpoints import build_planning_checkpoint, restore_goal_plan_from_checkpoint, with_checkpoint_provenance
from services.planning_cycles import current_cycle_context
from services.planning_cycle_commands import execute_cycle_command
from tests.smoke._planning_cycle_regressions import TODAY, legacy_db, evidence_bytes, client_for
from tests.planning_fixtures import append_history


def close(db):
    context = current_cycle_context(db)
    return execute_cycle_command(db, kind="close", cycle_id=context["cycle_id"], parameters={
        "command_id": str(uuid4()), "confirm": True,
        "expected_selection_revision": context["selection_revision"],
        "expected_cycle_revision": context["cycle_revision"],
        "expected_checkpoint_id": context["checkpoint_id"],
        "event_outcomes": [],
    }, validate_response=lambda value: value)


def child(db):
    base = db.get_current_planning_checkpoint()
    plan = restore_goal_plan_from_checkpoint(base)
    return build_planning_checkpoint(with_checkpoint_provenance(plan, source="execution_adjustment", parent_checkpoint_id=base["id"]))


def test_raw_public_save_cannot_append_or_select(tmp_path, monkeypatch):
    db = legacy_db(tmp_path, monkeypatch, start=TODAY)
    before = evidence_bytes(db)
    with pytest.raises(PlanningBuildPreviewError) as error:
        db.save_planning_checkpoint(child(db))
    assert error.value.code == "cycle_context_required"
    assert evidence_bytes(db) == before


def test_child_checks_close_after_calculation_and_rolls_back(tmp_path, monkeypatch):
    db = legacy_db(tmp_path, monkeypatch, start=TODAY)
    context = db.planning_write_context()
    prepared = child(db)
    close(db)
    before = evidence_bytes(db)
    with pytest.raises(PlanningBuildPreviewError) as error:
        db.save_planning_checkpoint(prepared, cycle_context=context)
    assert error.value.code == "cycle_stale"
    assert evidence_bytes(db) == before


def test_selected_child_advances_only_its_cycle_head(tmp_path, monkeypatch):
    db = legacy_db(tmp_path, monkeypatch, start=TODAY)
    context = db.planning_write_context()
    saved = db.save_planning_checkpoint(child(db), cycle_context=context)
    current = current_cycle_context(db)
    assert current["checkpoint_id"] == saved["id"]
    assert current["cycle_revision"] == context["cycle_revision"] + 1
    assert current["selection_revision"] == context["selection_revision"]


@pytest.mark.parametrize("operation", ["adjustment", "materialization", "raw_build", "demand", "weekly", "bike", "recovery", "transfer", "rollback", "restore", "repair_day", "coach_manual"])
@pytest.mark.parametrize("terminal", ["closed", "period_ended", "replaced"])
def test_closed_cycle_writers_refuse_without_history_changes(tmp_path, monkeypatch, operation, terminal):
    db = legacy_db(tmp_path, monkeypatch, start=TODAY)
    context = db.planning_write_context()
    base = context["checkpoint_id"]
    if terminal == "closed":
        close(db)
    elif terminal == "period_ended":
        from datetime import datetime, timezone
        from tests.smoke._planning_cycle_regressions import pin_clock
        pin_clock(monkeypatch, observed=datetime(2026, 10, 30, 9, tzinfo=timezone.utc))
    else:
        from tests.smoke.test_planning_cycle_build_v2 import prepare, confirm
        confirm(db, prepare(db))
    before = evidence_bytes(db)
    with pytest.raises((PlanningBuildPreviewError, ps.StalePlanningCheckpointError)):
        if operation == "adjustment":
            ps.apply_adjustment(db, rows=[], persist=True, cycle_context=context)
        elif operation == "materialization":
            ps.repair_active_plan_materialization(db, persist=True, cycle_context=context)
        elif operation == "raw_build":
            ps.build_plan(db, goal_type="triathlon", distance="olympic", event_date=(TODAY + timedelta(days=28)).isoformat(), available_hours=10, cycle_context=context)
        elif operation == "demand":
            ps.confirm_demand_change(db, level="aggressive", base_checkpoint_id=base, preview_fingerprint="old")
        elif operation == "weekly":
            ps.confirm_weekly_rebalance(db, base_checkpoint_id=base, preview_fingerprint="old", include_provider=False)
        elif operation == "bike":
            ps.confirm_bike_tss_rebalance(db, base_checkpoint_id=base, preview_fingerprint="old")
        elif operation == "recovery":
            ps.apply_recovery_replan(db, {"base_checkpoint_id": base, "cycle_context": context})
        elif operation == "transfer":
            ps.apply_recovery_replan_transfer(db, base_checkpoint_id=base, session_id="old", target_date=TODAY.isoformat(), cycle_context=context)
        elif operation == "rollback":
            ps.rollback_recovery_replan(db, {"applied_checkpoint_id": base, "rollback_checkpoint_id": base, "cycle_context": context})
        elif operation == "restore":
            ps.restore_history_version(db, checkpoint_id=base, base_checkpoint_id=base)
        elif operation == "repair_day":
            ps.recover_day_after_constraint_retraction(db, base_checkpoint_id=base, date=TODAY.isoformat())
        else:
            ps.preview_coach_constraint_mutation(db, action="create_plan_constraint", params={"date": TODAY.isoformat(), "kind": "manual_delete", "cycle_context": context})
    assert evidence_bytes(db) == before


def restore_fields(db):
    context = current_cycle_context(db)
    return {"expected_cycle_id": context["cycle_id"], "expected_cycle_revision": context["cycle_revision"],
            "expected_selection_revision": context["selection_revision"]}


def test_same_cycle_restore_and_legacy_acknowledgement_are_distinct(tmp_path, monkeypatch):
    db = legacy_db(tmp_path, monkeypatch, start=TODAY)
    unassigned = append_history(db, db.get_current_planning_checkpoint())["id"]
    context = db.planning_write_context()
    saved = db.save_planning_checkpoint(child(db), cycle_context=context)
    first = context["checkpoint_id"]
    fields = restore_fields(db)
    with pytest.raises(PlanningBuildPreviewError):
        ps.restore_history_version(db, checkpoint_id=unassigned, base_checkpoint_id=saved["id"], **fields)
    restored = ps.restore_history_version(db, checkpoint_id=first, base_checkpoint_id=saved["id"], **fields)
    again = ps.restore_history_version(db, checkpoint_id=unassigned, base_checkpoint_id=restored["applied_checkpoint_id"],
                                     action="restore_legacy_version", **restore_fields(db))
    assert again["applied_checkpoint_id"] > restored["applied_checkpoint_id"]
    conn = db._connect()
    try:
        assert conn.execute("SELECT cycle_id FROM planning_cycle_versions WHERE checkpoint_id=?", (unassigned,)).fetchone() is None
    finally:
        conn.close()


def test_restore_cannot_cross_cycles_or_follow_cross_cycle_donor(tmp_path, monkeypatch):
    from tests.smoke.test_planning_cycle_build_v2 import prepare, confirm
    db = legacy_db(tmp_path, monkeypatch, start=TODAY)
    old = db.get_current_planning_checkpoint()
    confirm(db, prepare(db))
    current = db.get_current_planning_checkpoint()
    before = evidence_bytes(db)
    with pytest.raises(PlanningBuildPreviewError) as error:
        ps.restore_history_version(db, checkpoint_id=old["id"], base_checkpoint_id=current["id"], **restore_fields(db))
    assert error.value.code == "cycle_not_current"
    assert ps._find_day_donor(db, {**current, "checkpoint_parent_id": old["id"]}, TODAY.isoformat()) is None
    assert evidence_bytes(db) == before


def test_cycle_revision_invalidates_child_at_same_checkpoint(tmp_path, monkeypatch):
    db = legacy_db(tmp_path, monkeypatch, start=TODAY)
    context = db.planning_write_context()
    prepared = child(db)
    execute_cycle_command(db, "set_event_outcome", {
        "command_id": str(uuid4()), "confirm": True, "expected_cycle_revision": context["cycle_revision"],
        "event_key": context["events"][0]["event_key"], "outcome": "did_not_participate",
    }, cycle_id=context["cycle_id"], validate_response=lambda value: value)
    before = evidence_bytes(db)
    with pytest.raises(PlanningBuildPreviewError, match="Цикл"):
        db.save_planning_checkpoint(prepared, cycle_context=context)
    assert evidence_bytes(db) == before


def test_constraint_scope_change_invalidates_child_without_advancing_head(tmp_path, monkeypatch):
    from models.planning_cycle import constraint_fingerprint
    db = legacy_db(tmp_path, monkeypatch, start=TODAY)
    row = db.save_coach_constraint(date=TODAY.isoformat(), kind="manual_delete")
    context = db.planning_write_context()
    prepared = child(db)
    execute_cycle_command(db, "resolve_constraint_scope", {
        "command_id": str(uuid4()), "confirm": True, "constraint_id": row["id"],
        "expected_constraint_fingerprint": constraint_fingerprint(row), "scope": "athlete", "cycle_id": None,
    }, validate_response=lambda value: value)
    before = evidence_bytes(db)
    with pytest.raises(PlanningBuildPreviewError) as error:
        db.save_planning_checkpoint(prepared, cycle_context=context)
    assert error.value.code == "cycle_stale"
    assert evidence_bytes(db) == before


def test_two_real_writers_close_and_child_have_one_cas_winner(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from models.planning_cycle import CycleCommandError
    db = legacy_db(tmp_path, monkeypatch, start=TODAY)
    context = db.planning_write_context()
    prepared = child(db)
    barrier = Barrier(2)

    def save():
        barrier.wait()
        try:
            db.save_planning_checkpoint(prepared, cycle_context=context)
            return "saved"
        except PlanningBuildPreviewError as exc:
            return exc.code

    def close_expected():
        barrier.wait()
        try:
            execute_cycle_command(db, "close", {
                "command_id": str(uuid4()), "confirm": True, "event_outcomes": [],
                "expected_cycle_revision": context["cycle_revision"],
                "expected_selection_revision": context["selection_revision"],
                "expected_checkpoint_id": context["checkpoint_id"],
            }, cycle_id=context["cycle_id"], validate_response=lambda value: value)
            return "closed"
        except CycleCommandError as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = pool.submit(save), pool.submit(close_expected)
        results = [first.result(timeout=10), second.result(timeout=10)]
    assert results.count("cycle_stale") == 1
    assert sum(result in {"saved", "closed"} for result in results) == 1
    assert len(db.get_recent_planning_checkpoints()) == (2 if "saved" in results else 1)


def test_newer_unassigned_history_never_becomes_a_child_base(tmp_path, monkeypatch):
    db = legacy_db(tmp_path, monkeypatch, start=TODAY)
    context = db.planning_write_context()
    prepared = child(db)
    unrelated = append_history(db, {"goal_type": "Unassigned historical record"})
    saved = db.save_planning_checkpoint(prepared, cycle_context=context)
    assert saved["id"] > unrelated["id"]
    assert current_cycle_context(db)["cycle_id"] == context["cycle_id"]
    assert current_cycle_context(db)["checkpoint_id"] == saved["id"]
    conn = db._connect()
    try:
        assert conn.execute("SELECT cycle_id FROM planning_cycle_versions WHERE checkpoint_id=?", (unrelated["id"],)).fetchone() is None
    finally:
        conn.close()


@pytest.mark.parametrize("stage", ["mapping", "settings"])
def test_mapping_failure_rolls_back_checkpoint_and_settings(tmp_path, monkeypatch, stage):
    db = legacy_db(tmp_path, monkeypatch, start=TODAY)
    context = db.planning_write_context()
    conn = db._connect()
    with conn:
        if stage == "mapping":
            conn.execute("CREATE TRIGGER synthetic_mapping_fault BEFORE INSERT ON planning_cycle_versions BEGIN SELECT RAISE(ABORT, 'synthetic fault'); END")
        else:
            conn.execute("CREATE TRIGGER synthetic_setting_fault BEFORE INSERT ON user_settings BEGIN SELECT RAISE(ABORT, 'synthetic fault'); END")
    conn.close()
    before = evidence_bytes(db)
    with pytest.raises(sqlite3.IntegrityError):
        db.save_planning_checkpoint(child(db), cycle_context=context, settings_write={"planning_demand_level": "aggressive"})
    assert evidence_bytes(db) == before
    assert current_cycle_context(db)["checkpoint_id"] == context["checkpoint_id"]
    assert current_cycle_context(db)["cycle_revision"] == context["cycle_revision"]


def test_coach_constraint_is_scoped_and_close_invalidates_its_proposal(tmp_path, monkeypatch):
    db = legacy_db(tmp_path, monkeypatch, start=TODAY)
    proposal = ps.preview_coach_constraint_mutation(db, action="create_plan_constraint",
        params={"date": TODAY.isoformat(), "kind": "manual_delete"})
    assert proposal["params"]["cycle_scope"] == "cycle"
    close(db)
    before = evidence_bytes(db)
    with pytest.raises(PlanningBuildPreviewError):
        ps.confirm_coach_constraint_mutation(db, action="create_plan_constraint", params=proposal["params"],
                                           preview_fingerprint=proposal["preview"]["preview_fingerprint"])
    assert evidence_bytes(db) == before
    assert db.get_coach_constraints() == []


def test_adjustment_on_modern_partial_week_keeps_namespace_and_bounds(tmp_path, monkeypatch):
    from tests.smoke.test_planning_cycle_build_v2 import prepare, confirm
    from data.planning_cycle_writes import write_token
    db = legacy_db(tmp_path, monkeypatch, start=TODAY)
    confirm(db, prepare(db))
    context = db.planning_write_context()
    old = db.get_current_planning_checkpoint()["goal_plan_snapshot"]
    result = ps.apply_adjustment(db, rows=[], cycle_context=write_token(context))
    current = db.get_current_planning_checkpoint()
    assert current["id"] == int(result["plan_id"])
    snapshot = current["goal_plan_snapshot"]
    assert snapshot["identity_namespace"] == old["identity_namespace"]
    assert snapshot["daily_plan"][0]["date"] == old["daily_plan"][0]["date"]
    assert snapshot["daily_plan"][-1]["date"] == old["daily_plan"][-1]["date"]
    assert result["forecast"]["points"][0]["date"] == TODAY.isoformat()


@pytest.mark.parametrize("route", ["adjust", "constraints", "repair-day", "history/restore"])
def test_http_mutation_checks_expected_cycle_revision_at_same_head(tmp_path, monkeypatch, route):
    db = legacy_db(tmp_path, monkeypatch, start=TODAY)
    context = db.planning_write_context()
    request = {"expected_cycle_id": context["cycle_id"], "expected_cycle_revision": context["cycle_revision"],
               "expected_selection_revision": context["selection_revision"], "base_checkpoint_id": context["checkpoint_id"]}
    request.update({"adjust": {"rows": []}, "constraints": {"date": TODAY.isoformat(), "kind": "forced_rest"},
                    "repair-day": {"date": TODAY.isoformat()}, "history/restore": {"checkpoint_id": context["checkpoint_id"]}}[route])
    execute_cycle_command(db, "set_event_outcome", {
        "command_id": str(uuid4()), "confirm": True, "expected_cycle_revision": context["cycle_revision"],
        "event_key": context["events"][0]["event_key"], "outcome": "did_not_participate",
    }, cycle_id=context["cycle_id"], validate_response=lambda value: value)
    before = evidence_bytes(db)
    with client_for(db) as client:
        response = client.post("/api/planning/" + route, json=request)
    assert response.status_code == 409, response.text
    assert response.json()["code"] == "cycle_stale"
    assert evidence_bytes(db) == before
    assert db.get_coach_constraints() == []


def test_explicit_athlete_constraint_without_current_cycle_never_reactivates_history(tmp_path, monkeypatch):
    db = legacy_db(tmp_path, monkeypatch, start=TODAY)
    close(db)
    context = current_cycle_context(db)
    count = len(db.get_recent_planning_checkpoints())
    with client_for(db) as client:
        response = client.post("/api/planning/constraints", json={
            "date": TODAY.isoformat(), "kind": "sick", "cycle_scope": "athlete",
            "expected_cycle_id": None, "expected_cycle_revision": None,
            "expected_selection_revision": context["selection_revision"], "base_checkpoint_id": 0,
        })
    assert response.status_code == 200, response.text
    assert response.json()["cycle_scope"] == "athlete"
    assert response.json()["active_plan_updated"] is False
    assert current_cycle_context(db)["cycle_id"] is None
    assert len(db.get_recent_planning_checkpoints()) == count
