"""S2: exact retained lifecycle publication, using synthetic SQLite only."""
from tests.planning_fixtures import append_history
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
import sqlite3
from threading import Barrier
from uuid import uuid4

import pytest

from api import planning_service as ps
from data.planning_build_preview_store import get_preview, store_pending, _applied_response, _receipt_digest
from models.planning_build_confirmation import BuildParameters, PlanningBuildPreviewError, canonical_json, fingerprint
from tests.smoke._planning_build_confirmation import declared_entry_limits, parameters
from tests.smoke._planning_cycle_regressions import TODAY, client_for, evidence_bytes, legacy_db, pin_clock
from tests.smoke.test_planning_cycle_storage import cycle_rows, rows

pytestmark = pytest.mark.smoke


def request_for(db, *, action="start_new", **overrides):
    from services.planning_cycles import current_cycle_context
    context = current_cycle_context(db)
    start = TODAY.isoformat() if action == "start_new" else context["start_date"]
    return {**parameters(), "initial_dose_limits": declared_entry_limits(), "start_week": None, "events": [], "action": action,
            "base_cycle_id": context["cycle_id"], "base_cycle_revision": context["cycle_revision"],
            "base_selection_revision": context["selection_revision"],
            "base_checkpoint_id": context["checkpoint_id"] or 0,
            "replace_current_cycle": action == "start_new" and context["cycle_id"] is not None,
            "start_date": start, **overrides}


def prepare(db, **overrides):
    return ps.prepare_plan_build(db, parameters=BuildParameters.from_mapping(request_for(db, **overrides)), origin="planning_ui")


def confirm(db, shown):
    return ps.confirm_plan_build(db, preview_id=shown["confirmation"]["preview_id"], origin="planning_ui")


@pytest.mark.parametrize("existing", [False, True])
def test_new_cycle_is_reserved_only_in_preview_then_atomically_selected(tmp_path, monkeypatch, existing):
    db = legacy_db(tmp_path, monkeypatch, **({} if existing else {"payloads": []}))
    before, facts = cycle_rows(db), evidence_bytes(db)
    shown = prepare(db)
    assert shown["confirmation"]["protocol_version"] == 2
    lifecycle = shown["lifecycle"]
    row = get_preview(db, shown["confirmation"]["preview_id"], origin="planning_ui")
    assert json.loads(row["cycle_context_json"]) == lifecycle
    assert cycle_rows(db) == before
    assert evidence_bytes(db) == facts
    checkpoint = json.loads(row["checkpoint_json"])
    snapshot = checkpoint["goal_plan_snapshot"]
    assert snapshot["identity_namespace"] == lifecycle["target_cycle_id"]
    assert snapshot["checkpoint_parent_id"] is None
    assert snapshot["daily_plan"][0]["date"][:10] == TODAY.isoformat()
    applied = confirm(db, shown)
    assert applied["lifecycle"] == lifecycle
    assert applied["totals"] == shown["totals"]
    assert applied["weeks"] == shown["weeks"]
    with client_for(db) as client:
        current = client.get("/api/planning/cycles/current").json()
    assert current["cycle_id"] == lifecycle["target_cycle_id"]
    assert current["checkpoint_id"] == int(applied["plan_id"])
    assert current["start_date"] == TODAY.isoformat()
    assert current["cycle_revision"] == 1
    assert len(cycle_rows(db)["planning_cycles"]) == len(before["planning_cycles"]) + 1
    replay = confirm(db, shown)
    assert replay["confirmation"]["replayed"] is True
    assert replay["lifecycle"] == lifecycle


@pytest.mark.parametrize("patch,code", [
    ({"start_date": "2026-10-15"}, "invalid_start_date"),
    ({"start_date": "20261016"}, "invalid_start_date"),
    ({"start_week": "2026-08-03"}, "invalid_start_date"),
    ({"events": [{"date": "2026-10-04", "priority": "A", "confirmed": True}]}, "invalid_start_date"),
    ({"replace_current_cycle": False}, "replacement_confirmation_required"),
    ({"base_selection_revision": 99}, "cycle_stale"),
    ({"base_cycle_revision": 99}, "cycle_stale"),
    ({"base_cycle_id": str(uuid4())}, "cycle_stale"),
])
def test_new_cycle_refuses_invalid_context_before_retaining_token(tmp_path, monkeypatch, patch, code):
    db = legacy_db(tmp_path, monkeypatch)
    before = cycle_rows(db), evidence_bytes(db)
    with client_for(db) as client:
        response = client.post("/api/planning/build", json=request_for(db, **patch))
    assert response.status_code in {409, 422}, response.text
    assert response.json()["code"] == code
    assert rows(db, "planning_build_previews") == []
    assert (cycle_rows(db), evidence_bytes(db)) == before


@pytest.mark.parametrize("scope", ["athlete", "cycle", "unknown", "missing-owner"])
def test_constraints_are_owned_and_unknown_never_disappears(tmp_path, monkeypatch, scope):
    from services.planning_cycles import current_cycle_context
    db = legacy_db(tmp_path, monkeypatch, constraint_kind="manual_delete")
    old = current_cycle_context(db)
    conn = db._connect()
    with conn:
        conn.execute("UPDATE coach_constraints SET cycle_scope=?,cycle_id=? WHERE id=1",
                     ("cycle" if scope == "missing-owner" else scope,
                      str(uuid4()) if scope == "missing-owner" else old["cycle_id"] if scope == "cycle" else None))
    conn.close()
    if scope in {"unknown", "missing-owner"}:
        with client_for(db) as client:
            response = client.post("/api/planning/build", json=request_for(db))
        assert response.status_code == 409
        assert response.json()["code"] == "constraint_scope_required"
        assert response.json()["constraint_ids"] == [1]
        assert rows(db, "planning_build_previews") == []
    else:
        shown = prepare(db)
        retained = get_preview(db, shown["confirmation"]["preview_id"], origin="planning_ui")
        first = json.loads(retained["checkpoint_json"])["goal_plan_snapshot"]["session_templates"][0]
        assert bool(first.get("protected_by_constraint")) is (scope == "athlete")


def test_relevant_scope_change_invalidates_even_without_new_checkpoint(tmp_path, monkeypatch):
    db = legacy_db(tmp_path, monkeypatch, constraint_kind="forced_rest")
    shown = prepare(db)
    checkpoint_before = rows(db, "planning_checkpoints")
    with client_for(db) as client:
        context = client.get("/api/planning/cycles/current").json()
        constraint = client.get("/api/planning/constraints").json()["constraints"][0]
        changed = client.post("/api/planning/cycles/constraint-scope", json={
            "command_id": str(uuid4()), "confirm": True, "constraint_id": 1,
            "expected_constraint_fingerprint": constraint["constraint_fingerprint"],
            "scope": "cycle", "cycle_id": context["cycle_id"],
        })
        assert changed.status_code == 200, changed.text
    with pytest.raises(PlanningBuildPreviewError) as error:
        confirm(db, shown)
    assert error.value.code == "preview_stale"
    assert rows(db, "planning_checkpoints") == checkpoint_before


def test_outcome_change_invalidates_even_without_new_checkpoint(tmp_path, monkeypatch):
    db = legacy_db(tmp_path, monkeypatch)
    shown = prepare(db)
    checkpoint_before = rows(db, "planning_checkpoints")
    with client_for(db) as client:
        context = client.get("/api/planning/cycles/current").json()
        response = client.post(f'/api/planning/cycles/{context["cycle_id"]}/event-outcome', json={
            "command_id": str(uuid4()), "confirm": True, "expected_cycle_revision": context["cycle_revision"],
            "event_key": context["events"][0]["event_key"], "outcome": "did_not_participate",
        })
        assert response.status_code == 200, response.text
    with pytest.raises(PlanningBuildPreviewError) as error:
        confirm(db, shown)
    assert error.value.code == "preview_stale"
    assert rows(db, "planning_checkpoints") == checkpoint_before


@pytest.mark.parametrize("modern", [False, True])
def test_edit_keeps_identity_period_start_and_exact_past_prescriptions(tmp_path, monkeypatch, modern):
    db = legacy_db(tmp_path, monkeypatch, start=date(2026, 10, 12), days=14)
    if modern:
        confirm(db, prepare(db))
        pin_clock(monkeypatch, observed=datetime(2026, 10, 19, 9, tzinfo=timezone.utc))
    old_row = db.get_current_planning_checkpoint()
    old = old_row["goal_plan_snapshot"]
    shown = prepare(db, action="edit_current", available_hours=6.0)
    assert shown["lifecycle"]["target_cycle_id"] == shown["lifecycle"]["source_cycle_id"]
    assert shown["lifecycle"]["start_date"] == old["daily_plan"][0]["date"][:10]
    assert shown["lifecycle"]["end_date"] <= old["daily_plan"][-1]["date"][:10]
    row = get_preview(db, shown["confirmation"]["preview_id"], origin="planning_ui")
    new = json.loads(row["checkpoint_json"])["goal_plan_snapshot"]
    assert new.get("identity_namespace") == old.get("identity_namespace")
    from utils.athlete_time import athlete_local_date
    for index, daily in enumerate(old["daily_plan"]):
        if daily["date"][:10] < athlete_local_date().isoformat():
            assert new["daily_plan"][index] == daily
            assert new["session_templates"][index] == old["session_templates"][index]
    before = cycle_rows(db)
    applied = confirm(db, shown)
    after = cycle_rows(db)
    assert len(after["planning_cycles"]) == len(before["planning_cycles"])
    assert after["planning_cycle_state"] == before["planning_cycle_state"]
    assert db.get_current_planning_checkpoint()["id"] == int(applied["plan_id"])


def test_partial_week_totals_and_forecast_follow_actual_calendar(tmp_path, monkeypatch):
    db = legacy_db(tmp_path, monkeypatch, payloads=[])
    shown = prepare(db, start_date="2026-10-20")
    row = get_preview(db, shown["confirmation"]["preview_id"], origin="planning_ui")
    snapshot = json.loads(row["checkpoint_json"])["goal_plan_snapshot"]
    daily = snapshot["daily_plan"]
    assert daily[0]["date"][:10] == "2026-10-20"
    for week in shown["weeks"]:
        start = date.fromisoformat(week["week_start"][:10])
        load = sum(item["total_tss"] for item in daily if start <= date.fromisoformat(item["date"][:10]) < start + timedelta(days=7))
        assert week["weekly_tss"] == round(load)
    # Whole-plan total rounds the raw effective sum once, not weekly displays.
    assert shown["totals"]["total_tss"] == round(sum(float(item["total_tss"]) for item in snapshot["daily_plan"]))
    assert shown["forecast"]["points"][0]["date"] == TODAY.isoformat()
    assert shown["forecast"]["points"][-1]["date"] == shown["lifecycle"]["end_date"]
    assert shown["science_audit"] == snapshot["science_audit"]


@pytest.mark.parametrize("stage", ["checkpoint", "old-close", "new-cycle", "version-map", "selection", "demand", "profile", "receipt", "coach", "commit"])
def test_publication_fault_rolls_back_every_domain_write(tmp_path, monkeypatch, stage):
    db = legacy_db(tmp_path, monkeypatch)
    origin = "coach" if stage == "coach" else "planning_ui"
    shown = ps.prepare_plan_build(db, parameters=BuildParameters.from_mapping(request_for(db)), origin=origin)
    proposal = (db.save_coach_proposal(action="build_plan", params={"preview_id": shown["confirmation"]["preview_id"]}, preview={})
                if origin == "coach" else None)
    before = cycle_rows(db), evidence_bytes(db), rows(db, "planning_build_previews"), rows(db, "coach_proposals")
    prefix = {"checkpoint": "INSERT INTO planning_checkpoints", "old-close": "UPDATE planning_cycles SET status",
              "new-cycle": "INSERT INTO planning_cycles", "version-map": "INSERT INTO planning_cycle_versions",
              "selection": "UPDATE planning_cycle_state", "demand": "INSERT INTO user_settings",
              "profile": "INSERT INTO user_settings", "receipt": "UPDATE planning_build_previews SET state='applied'",
              "coach": "UPDATE coach_proposals SET status='approved'"}

    class FaultConnection(sqlite3.Connection):
        def execute(self, sql, args=()):
            result = super().execute(sql, args)
            if stage != "commit" and sql.strip().startswith(prefix[stage]):
                if stage not in {"demand", "profile"} or args[0] == {"demand": "planning_demand_level", "profile": "planning_profile"}[stage]:
                    raise sqlite3.IntegrityError("synthetic publication fault")
            return result

        def commit(self):
            if stage == "commit":
                raise sqlite3.IntegrityError("synthetic commit fault")
            return super().commit()

    with monkeypatch.context() as failing:
        failing.setattr(db, "_connect", lambda: sqlite3.connect(db.db_path, factory=FaultConnection))
        with pytest.raises(PlanningBuildPreviewError) as error:
            ps.confirm_plan_build(db, preview_id=shown["confirmation"]["preview_id"], origin=origin,
                                  proposal_id=proposal["id"] if proposal else None)
    assert error.value.code == "planning_storage_error"
    assert (cycle_rows(db), evidence_bytes(db), rows(db, "planning_build_previews"), rows(db, "coach_proposals")) == before


def test_two_replacements_from_one_base_have_one_winner(tmp_path, monkeypatch):
    db = legacy_db(tmp_path, monkeypatch)
    before = cycle_rows(db)
    first, second = prepare(db), prepare(db)
    assert first["lifecycle"]["target_cycle_id"] != second["lifecycle"]["target_cycle_id"]
    barrier = Barrier(2)

    def worker(shown):
        barrier.wait(timeout=5)
        try:
            return confirm(db, shown)
        except PlanningBuildPreviewError as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(worker, [first, second]))
    assert sum(isinstance(result, dict) for result in results) == 1
    assert "preview_stale" in results
    after = cycle_rows(db)
    assert len(after["planning_cycles"]) == len(before["planning_cycles"]) + 1
    assert len(after["planning_cycle_versions"]) == len(before["planning_cycle_versions"]) + 1
    old = next(row for row in after["planning_cycles"] if row[0] == first["lifecycle"]["source_cycle_id"])
    assert old[2] == 2 and old[3] == "closed"


def seed_v1_receipt(db, origin, applied):
    """Represent an actual pre-S2 retained shape; no runtime legacy apply flag."""
    from data.planning_cycles import initialize_cycle_store
    snapshot = ps._capture_plan_build_inputs(db, BuildParameters.from_mapping(parameters()))
    prepared = ps._calculate_plan_build(snapshot)
    now = datetime.now(timezone.utc)
    row = store_pending(db, prepared, origin=origin, now=now, recheck=lambda _conn: snapshot.dependency_digest)
    row["coach_proposal_id"] = None
    assert row["protocol_version"] == 1 and row["cycle_context_json"] is None
    legacy_fields = ("preview_id", "schema_version", "protocol_version", "origin", "created_at", "expires_at",
                     "base_checkpoint_id", "parameters_json", "dependency_context_json", "dependency_digest",
                     "checkpoint_json", "response_json", "settings_write_json")
    assert row["payload_digest"] == fingerprint({key: row[key] for key in legacy_fields})
    checkpoint = append_history(db, json.loads(row["checkpoint_json"])) if applied else None
    conn = db._connect()
    try:
        with conn:
            proposal_id = None
            if origin == "coach":
                cursor = conn.execute("""INSERT INTO coach_proposals(date,action,status,params_json,preview_json)
                    VALUES(?,'build_plan','pending',?,'{}')""", (TODAY.isoformat(), canonical_json({"preview_id": row["preview_id"]})))
                proposal_id = cursor.lastrowid
                row["coach_proposal_id"] = proposal_id
                conn.execute("UPDATE planning_build_previews SET coach_proposal_id=? WHERE preview_id=?", (proposal_id, row["preview_id"]))
            if applied:
                response = _applied_response(row, checkpoint["id"])
                row.update(applied_checkpoint_id=checkpoint["id"], applied_at=now.isoformat(), applied_response_json=canonical_json(response))
                conn.execute("""UPDATE planning_build_previews SET state='applied',applied_checkpoint_id=?,
                    applied_at=?,applied_response_json=?,receipt_digest=? WHERE preview_id=?""",
                    (row["applied_checkpoint_id"], row["applied_at"], row["applied_response_json"], _receipt_digest(row), row["preview_id"]))
                if proposal_id:
                    conn.execute("UPDATE coach_proposals SET status='approved',result_json=?,applied_checkpoint_id=? WHERE id=?",
                                 (row["applied_response_json"], checkpoint["id"], proposal_id))
                conn.execute("DELETE FROM planning_cycle_state")
                initialize_cycle_store(conn)  # fixture depicts import of a successful old plan
        return row, proposal_id
    finally:
        conn.close()


@pytest.mark.parametrize("origin", ["planning_ui", "coach"])
@pytest.mark.parametrize("applied", [False, True])
def test_v1_pending_requires_new_preview_but_successful_receipt_keeps_original_shape(tmp_path, monkeypatch, origin, applied):
    db = legacy_db(tmp_path, monkeypatch, payloads=[])
    retained, proposal_id = seed_v1_receipt(db, origin, applied)
    before = cycle_rows(db), evidence_bytes(db), rows(db, "planning_build_previews")
    if not applied:
        with pytest.raises(PlanningBuildPreviewError) as error:
            ps.confirm_plan_build(db, preview_id=retained["preview_id"], origin=origin, proposal_id=proposal_id)
        assert error.value.code == "preview_required"
    else:
        result = ps.confirm_plan_build(db, preview_id=retained["preview_id"], origin=origin, proposal_id=proposal_id)
        expected = json.loads(retained["applied_response_json"])
        assert result == {**expected, "confirmation": {**expected["confirmation"], "replayed": True, "is_current": True}}
        assert "lifecycle" not in result and result["confirmation"]["protocol_version"] == 1
    assert (cycle_rows(db), evidence_bytes(db), rows(db, "planning_build_previews")) == before


@pytest.mark.parametrize("action", ["start_new", "edit_current"])
def test_close_racing_publication_has_one_ordered_winner(tmp_path, monkeypatch, action):
    from api.planning_cycle_contract import CloseCycleRequest, CycleCommandResponse
    from models.planning_cycle import CycleCommandError
    from services.planning_cycle_commands import execute_cycle_command
    from services.planning_cycles import current_cycle_context
    from tests.smoke.test_planning_cycle_commands import command
    db = legacy_db(tmp_path, monkeypatch, start=date(2026, 10, 12), days=14)
    context = current_cycle_context(db)
    shown = prepare(db, action=action)
    close_body = CloseCycleRequest.model_validate(command(context, "close")).model_dump(mode="json")
    barrier = Barrier(2)

    def worker(kind):
        barrier.wait(timeout=5)
        try:
            if kind == "build":
                return kind, confirm(db, shown)
            return kind, execute_cycle_command(db, "close", close_body, cycle_id=context["cycle_id"],
                                               validate_response=CycleCommandResponse.model_validate)
        except (PlanningBuildPreviewError, CycleCommandError) as exc:
            return kind, exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = dict(pool.map(worker, ["build", "close"]))
    assert sum(isinstance(value, dict) for value in outcomes.values()) == 1
    if isinstance(outcomes["close"], dict):
        assert outcomes["build"] == "preview_stale"
        assert current_cycle_context(db)["state"] == "no_current"
        assert len(rows(db, "planning_checkpoints")) == 1
    else:
        assert outcomes["close"] in {"cycle_closed", "cycle_stale"}
        assert current_cycle_context(db)["is_selected"] is True
        assert len(rows(db, "planning_checkpoints")) == 2


@pytest.mark.parametrize("applied", [False, True])
def test_v2_backup_restore_preserves_reserved_cycle_and_replay(tmp_path, monkeypatch, applied):
    from data.database import Database
    from scripts.sqlite_backup_restore import backup_database, restore_database
    db = legacy_db(tmp_path, monkeypatch)
    shown = prepare(db)
    result = confirm(db, shown) if applied else None
    backup_database(db.db_path, tmp_path / "backup.db", confirm_stopped=True)
    restore_database(tmp_path / "backup.db", tmp_path / "restored.db", confirm_stopped=True)
    restored = Database(str(tmp_path / "restored.db"))
    confirmed = confirm(restored, shown)
    assert confirmed["lifecycle"] == shown["lifecycle"]
    assert confirmed["confirmation"]["replayed"] is applied
    if applied:
        assert confirmed["plan_id"] == result["plan_id"]


@pytest.mark.parametrize("legacy", [False, True])
def test_successful_replay_after_close_never_reselects_old_cycle(tmp_path, monkeypatch, legacy):
    from tests.smoke.test_planning_cycle_commands import close, current
    db = legacy_db(tmp_path, monkeypatch, payloads=[])
    if legacy:
        retained, _ = seed_v1_receipt(db, "planning_ui", True)
        shown = {"confirmation": {"preview_id": retained["preview_id"]}}
    else:
        shown = prepare(db)
        confirm(db, shown)
    with client_for(db) as client:
        closed = close(client, current(client))
        assert closed.status_code == 200, closed.text
    before = cycle_rows(db), evidence_bytes(db), rows(db, "planning_build_previews")
    with client_for(db) as client:
        replay = client.post("/api/planning/build/confirm", json={"preview_id": shown["confirmation"]["preview_id"], "confirm": True})
        assert replay.status_code == 200, replay.text
        assert replay.json()["confirmation"]["replayed"] is True
        assert replay.json()["confirmation"]["is_current"] is False
        assert ("lifecycle" in replay.json()) is not legacy
    assert (cycle_rows(db), evidence_bytes(db), rows(db, "planning_build_previews")) == before


def test_raw_history_append_is_not_a_new_selected_cycle_dependency(tmp_path, monkeypatch):
    db = legacy_db(tmp_path, monkeypatch)
    shown = prepare(db)
    append_history(db, {"goal_type": "synthetic unassigned history"})
    applied = confirm(db, shown)
    assert applied["lifecycle"] == shown["lifecycle"]


def test_unbound_coach_build_cannot_invent_cycle_context(tmp_path, monkeypatch):
    from models.ai_tools import AITools
    from models.ai_coach_runtime import _parse_tool_params
    db = legacy_db(tmp_path, monkeypatch)
    before = cycle_rows(db), evidence_bytes(db)
    result = AITools(db).propose_plan_build(goal_type="triathlon", distance="olympic", event_date="2026-12-06")
    assert result["success"] is False and result["code"] == "cycle_context_required"
    assert rows(db, "planning_build_previews") == []
    assert (cycle_rows(db), evidence_bytes(db)) == before
    assert _parse_tool_params("replace_current_cycle=false, base_cycle_id=null, base_selection_revision=0") == {
        "replace_current_cycle": False, "base_cycle_id": None, "base_selection_revision": 0}


@pytest.mark.parametrize("damage", ["malformed-checkpoint", "null-head"])
def test_explicit_replacement_can_exit_indeterminate_without_fabricated_parent(tmp_path, monkeypatch, damage):
    db = legacy_db(tmp_path, monkeypatch, **({"payloads": ["{broken"]} if damage == "malformed-checkpoint" else {}))
    if damage == "null-head":
        conn = db._connect()
        with conn:
            conn.execute("UPDATE planning_cycles SET current_checkpoint_id=NULL")
        conn.close()
    history = rows(db, "planning_checkpoints")
    shown = prepare(db)
    applied = confirm(db, shown)
    assert applied["lifecycle"]["closes_cycle_id"] is not None
    assert rows(db, "planning_checkpoints")[:len(history)] == history
    assert db.get_current_planning_checkpoint()["goal_plan_snapshot"]["checkpoint_parent_id"] is None


@pytest.mark.parametrize("applied", [False, True])
def test_v2_full_reset_removes_reserved_or_applied_context_without_reimport(tmp_path, monkeypatch, applied):
    from data.database import Database
    from services.planning_cycles import current_cycle_context
    db = legacy_db(tmp_path, monkeypatch)
    shown = prepare(db)
    if applied:
        confirm(db, shown)
    db.clear_all_data()
    reopened = Database(db.db_path)
    assert current_cycle_context(reopened)["state"] == "no_current"
    assert current_cycle_context(reopened)["has_history"] is False
    assert rows(reopened, "planning_build_previews") == []
    assert rows(reopened, "planning_cycle_versions") == []
