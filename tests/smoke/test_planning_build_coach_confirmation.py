"""M4 Coach adapter: only bound frozen builds can be approved or replayed."""
from concurrent.futures import ThreadPoolExecutor
import json
import sqlite3
from threading import Barrier

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from api import planning_service as ps
from api.deps import get_database
from api.routers import decisions
from data.planning_build_preview_store import get_preview
from models.ai_tools import AITools
from models.planning_build_confirmation import BuildParameters, PlanningBuildPreviewError
from tests.smoke._planning_build_confirmation import add_late_activity, checkpoint_payload, cycle_fields, parameters, pin_clock, protected_state, seeded_db
from tests.smoke.test_planning_build_preparation import execute


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    pin_clock(monkeypatch)


def prepared(db):
    request = parameters()
    request.pop("demand")  # current trusted Coach tool does not request a settings write
    return ps.prepare_plan_build(db, parameters=BuildParameters.from_mapping({**request, **cycle_fields(db)}), origin="coach")


def save(db, shown, **kwargs):
    return db.save_coach_proposal(action="build_plan", params={"preview_id": shown["confirmation"]["preview_id"],
        "base_checkpoint_id": shown["preview"]["base_checkpoint_id"]},
        preview={"goal": shown["goal"], "confirmation": shown["confirmation"]}, **kwargs)


def test_tool_prepares_identity_summary_and_actual_base(tmp_path):
    db = seeded_db(tmp_path, existing=True)
    before = protected_state(db)
    raw = AITools(db).propose_plan_build(goal_type="triathlon", distance="olympic", event_date="2026-12-06", **cycle_fields(db))
    assert raw["is_proposal"]
    token = raw["params"]["preview_id"]
    row = get_preview(db, token, origin="coach")
    public = json.loads(row["response_json"])
    assert raw["preview"]["confirmation"]["preview_id"] == token
    assert raw["params"]["base_checkpoint_id"] == raw["preview"]["base_checkpoint_id"] == public["preview"]["base_checkpoint_id"]
    assert raw["preview"]["total_tss"] == public["totals"]["total_tss"]
    assert protected_state(db) == before


@pytest.mark.parametrize("existing", [False, True])
def test_approval_publishes_frozen_coach_result_and_replays(tmp_path, monkeypatch, existing):
    db = seeded_db(tmp_path, existing=existing)
    shown = prepared(db)
    proposal = save(db, shown)
    row = get_preview(db, shown["confirmation"]["preview_id"], origin="coach")
    assert row["coach_proposal_id"] == proposal["id"]
    # Force a distinct old timestamp: an unintended no-op write must be visible.
    execute(db,"UPDATE user_settings SET updated_at='synthetic-old' WHERE key='planning_demand_level'")
    before = protected_state(db)
    monkeypatch.setattr(ps, "build_plan", lambda *a, **k: pytest.fail("Approval must never rebuild"))
    first = decisions.approve_proposal(proposal["id"], db=db)
    assert first["proposal"]["status"] == "approved"
    assert checkpoint_payload(db) == json.loads(row["checkpoint_json"])
    assert protected_state(db)["settings"] == before["settings"], "Coach must not overwrite onboarding/demand"
    after = protected_state(db)
    add_late_activity(db)
    monkeypatch.setattr(decisions, "_record_proposal_approval_decision", lambda *a: pytest.fail("No duplicate audit on replay"))
    replay = decisions.approve_proposal(proposal["id"], db=db)
    assert replay["result"]["plan_id"] == first["result"]["plan_id"]
    assert replay["result"]["confirmation"]["replayed"] is True
    assert protected_state(db) == after


def test_dedup_reuses_bound_identity_and_saved_summary(tmp_path):
    db = seeded_db(tmp_path)
    one, two = prepared(db), prepared(db)
    first = save(db, one, source_key="same-turn")
    second = save(db, two, source_key="same-turn")
    assert second == first
    assert second["params"]["preview_id"] == one["confirmation"]["preview_id"]
    assert get_preview(db, two["confirmation"]["preview_id"], origin="coach")["coach_proposal_id"] is None


def test_binding_cannot_attach_one_preview_to_two_proposals(tmp_path):
    db = seeded_db(tmp_path)
    shown = prepared(db)
    first = save(db, shown)
    with pytest.raises(PlanningBuildPreviewError):
        save(db, shown)
    assert len(db.get_coach_proposals(days=36500)) == 1
    assert get_preview(db, shown["confirmation"]["preview_id"], origin="coach")["coach_proposal_id"] == first["id"]


def test_binding_failure_rolls_back_proposal_insert(tmp_path):
    db = seeded_db(tmp_path)
    shown = prepared(db)
    execute(db, "CREATE TRIGGER fail_bind BEFORE UPDATE OF coach_proposal_id ON planning_build_previews "
                "BEGIN SELECT RAISE(ABORT,'synthetic bind failure'); END")
    with pytest.raises(sqlite3.Error):
        save(db, shown)
    assert not db.get_coach_proposals(days=36500)


@pytest.mark.parametrize("stage", ["receipt", "proposal"])
def test_failure_rolls_back_plan_settings_receipt_and_proposal(tmp_path, stage):
    db = seeded_db(tmp_path)
    shown = prepared(db)
    proposal = save(db, shown)
    table = "coach_proposals" if stage == "proposal" else "planning_build_previews"
    execute(db, f"CREATE TRIGGER fail_apply BEFORE UPDATE ON {table} BEGIN SELECT RAISE(ABORT,'synthetic apply failure'); END")
    before = protected_state(db)
    with pytest.raises(PlanningBuildPreviewError) as error:
        decisions.approve_proposal(proposal["id"], db=db)
    assert error.value.code == "planning_storage_error"
    assert protected_state(db) == before
    assert db.get_coach_proposal(proposal["id"]) == proposal
    assert get_preview(db, shown["confirmation"]["preview_id"], origin="coach")["state"] == "pending"


def test_stale_does_not_claim_or_fail_proposal(tmp_path):
    db = seeded_db(tmp_path)
    shown = prepared(db)
    proposal = save(db, shown)
    add_late_activity(db)
    before = protected_state(db)
    with pytest.raises(PlanningBuildPreviewError) as error:
        decisions.approve_proposal(proposal["id"], db=db)
    assert error.value.code == "preview_stale"
    assert protected_state(db) == before
    assert db.get_coach_proposal(proposal["id"]) == proposal


@pytest.mark.parametrize("tamper", ["rejected", "failed", "superseded", "wrong-id", "wrong-origin", "corrupt-params"])
def test_rejected_or_mismatched_proposal_never_applies(tmp_path, tamper):
    db = seeded_db(tmp_path)
    shown = prepared(db)
    proposal = save(db, shown)
    if tamper in {"rejected", "failed", "superseded"}:
        db.update_coach_proposal_status(proposal["id"], tamper)
    elif tamper == "wrong-id":
        other = prepared(db)
        execute(db, "UPDATE coach_proposals SET params_json=? WHERE id=?",
                (json.dumps({"preview_id": other["confirmation"]["preview_id"]}), proposal["id"]))
    elif tamper == "wrong-origin":
        other = ps.prepare_plan_build(db, parameters=BuildParameters.from_mapping({**parameters(), **cycle_fields(db)}), origin="planning_ui")
        execute(db, "UPDATE coach_proposals SET params_json=? WHERE id=?",
                (json.dumps({"preview_id": other["confirmation"]["preview_id"]}), proposal["id"]))
    else:
        execute(db, "UPDATE coach_proposals SET params_json='{broken' WHERE id=?", (proposal["id"],))
    before = protected_state(db)
    with pytest.raises(PlanningBuildPreviewError):
        decisions.approve_proposal(proposal["id"], db=db)
    assert protected_state(db) == before


def test_legacy_unbound_build_is_rejected_with_safe_http_code(tmp_path):
    db = seeded_db(tmp_path)
    proposal = db.save_coach_proposal(action="build_plan", params=parameters(), preview={})
    app = FastAPI()
    app.include_router(decisions.router)
    app.dependency_overrides[get_database] = lambda: db
    before = protected_state(db)
    with TestClient(app) as client:
        response = client.post(f"/api/decisions/proposals/{proposal['id']}/approve", json={})
    assert response.status_code == 409
    assert response.json()["code"] == "preview_required"
    assert protected_state(db) == before


def test_best_effort_audit_failure_cannot_fail_committed_build(tmp_path, monkeypatch):
    db = seeded_db(tmp_path)
    proposal = save(db, prepared(db))
    monkeypatch.setattr(decisions, "record_agent_decision", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("synthetic audit failure")))
    assert decisions.approve_proposal(proposal["id"], db=db)["proposal"]["status"] == "approved"


def test_approve_reject_race_has_one_ordered_winner(tmp_path):
    db = seeded_db(tmp_path)
    proposal = save(db, prepared(db))
    barrier = Barrier(2)

    def run(kind):
        barrier.wait(5)
        try:
            (decisions.approve_proposal if kind == "approve" else decisions.reject_proposal)(proposal["id"], db=db)
            return kind
        except (PlanningBuildPreviewError, HTTPException):
            return "rejected-attempt"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(run, ["approve", "reject"]))
    final = db.get_coach_proposal(proposal["id"])
    count = len(protected_state(db)["checkpoints"])
    assert (final["status"], count) in {("approved", 1), ("rejected", 0)}
    assert outcomes.count("rejected-attempt") == 1


@pytest.mark.parametrize("level",["moderate","aggressive"])
def test_explicit_coach_demand_is_applied_once_without_profile_write(tmp_path,monkeypatch,level):
    db = seeded_db(tmp_path)
    execute(db,"UPDATE user_settings SET updated_at='synthetic-old' WHERE key='planning_demand_level'")
    before = protected_state(db)
    shown = ps.prepare_plan_build(db,parameters=BuildParameters.from_mapping({**parameters(),**cycle_fields(db),"demand":level}),origin="coach")
    proposal = save(db,shown)
    decisions.approve_proposal(proposal["id"],db=db)
    settings = {row[0]:row for row in protected_state(db)["settings"]}
    original = {row[0]:row for row in before["settings"]}
    assert settings["planning_demand_level"][1] == level
    assert settings["planning_demand_level"][2] != "synthetic-old"
    assert settings["planning_profile"] == original["planning_profile"]
    queries = []
    connect = db._connect

    def traced():
        conn = connect()
        conn.set_trace_callback(queries.append)
        return conn

    monkeypatch.setattr(db,"_connect",traced)
    assert decisions.approve_proposal(proposal["id"],db=db)["result"]["confirmation"]["replayed"] is True
    assert not any(sql.lstrip().upper().startswith(("INSERT","UPDATE","DELETE")) for sql in queries)
