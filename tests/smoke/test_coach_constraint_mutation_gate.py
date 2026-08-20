"""RED coverage for coach constraint mutation boundaries (#483).

These tests deliberately describe the apply contract before the runtime fix:
AI tools may calculate a bounded proposal, but they must not write durable
constraints or planning checkpoints.  The lower-level apply paths must also
commit the constraint ledger and checkpoint as one unit.
"""
from __future__ import annotations

from copy import deepcopy
from threading import Event, Lock, Thread

import pytest
from fastapi import HTTPException

from api import planning_service
from api.routers import decisions as decisions_router
from api.routers import planning as planning_router
from data.database import Database
from models.ai_tools import AITools
from models.ai_coach_runtime import resolve_turn_tool_results
from models.planning_checkpoints import (
    build_planning_checkpoint,
    restore_goal_plan_from_checkpoint,
    with_checkpoint_provenance,
)
from tests.smoke.test_constraint_retraction import TARGET, _collapsed_plan, _goal_plan


pytestmark = pytest.mark.smoke


def _db(tmp_path, name: str = "constraint-gate.db") -> Database:
    return Database(str(tmp_path / name))


def _seed_chain(db: Database) -> tuple[dict, dict]:
    """Save an executable donor and a collapsed child checkpoint."""
    donor = db.save_planning_checkpoint(build_planning_checkpoint(_goal_plan()))
    child_plan = with_checkpoint_provenance(
        _collapsed_plan(),
        source="coach_constraint",
        parent_checkpoint_id=donor["id"],
    )
    child = db.save_planning_checkpoint(build_planning_checkpoint(child_plan))
    return donor, child


def _seed_no_donor(db: Database) -> dict:
    """Save a root and child whose target day is already non-executable."""
    root = db.save_planning_checkpoint(build_planning_checkpoint(_collapsed_plan()))
    child_plan = with_checkpoint_provenance(
        deepcopy(_collapsed_plan()),
        source="manual_edit",
        parent_checkpoint_id=root["id"],
    )
    return db.save_planning_checkpoint(build_planning_checkpoint(child_plan))


def _checkpoint_ids(db: Database) -> list[int]:
    return [
        int(row["id"])
        for row in db.get_recent_planning_checkpoints(limit=100)
    ]


def _all_constraints(db: Database) -> list[dict]:
    return db.get_coach_constraints(active_only=False, limit=100)


def _save_tool_proposal(db: Database, payload: dict) -> dict:
    return db.save_coach_proposal(
        action=payload["action"],
        params=payload["params"],
        preview=payload["preview"],
    )


def test_create_constraint_tool_returns_proposal_without_writes(tmp_path) -> None:
    db = _db(tmp_path)
    db.save_planning_checkpoint(build_planning_checkpoint(_goal_plan()))
    before_checkpoints = _checkpoint_ids(db)
    before_constraints = _all_constraints(db)

    result = AITools(db).execute_tool(
        "create_plan_constraint",
        date=TARGET,
        kind="sick",
        note="RED: tool call must not mutate the plan",
    )

    assert result["success"] is True, result.get("error")
    proposal = result["result"]
    assert proposal.get("is_proposal") is True
    assert proposal.get("action") == "create_plan_constraint"
    assert _checkpoint_ids(db) == before_checkpoints
    assert _all_constraints(db) == before_constraints


def test_retract_constraint_tool_returns_proposal_without_writes(tmp_path) -> None:
    db = _db(tmp_path)
    _donor, child = _seed_chain(db)
    constraint = db.save_coach_constraint(
        date=TARGET,
        kind="unavailable",
        source="coach",
    )
    before_checkpoints = _checkpoint_ids(db)
    before_constraints = _all_constraints(db)

    result = AITools(db).execute_tool(
        "retract_plan_constraint",
        id=int(constraint["id"]),
    )

    assert result["success"] is True, result.get("error")
    proposal = result["result"]
    assert proposal.get("is_proposal") is True
    assert proposal.get("action") == "retract_plan_constraint"
    assert _checkpoint_ids(db) == before_checkpoints
    assert _all_constraints(db) == before_constraints
    assert db.get_latest_planning_checkpoint()["id"] == child["id"]


def test_repair_day_tool_returns_proposal_without_writes(tmp_path) -> None:
    db = _db(tmp_path)
    _donor, child = _seed_chain(db)
    before_checkpoints = _checkpoint_ids(db)
    before_constraints = _all_constraints(db)

    result = AITools(db).execute_tool(
        "repair_plan_day",
        date=TARGET,
        exclude_sports=["swim"],
    )

    assert result["success"] is True, result.get("error")
    proposal = result["result"]
    assert proposal.get("is_proposal") is True
    assert proposal.get("action") == "repair_plan_day"
    assert _checkpoint_ids(db) == before_checkpoints
    assert _all_constraints(db) == before_constraints
    assert db.get_latest_planning_checkpoint()["id"] == child["id"]


def test_constraint_apply_rolls_back_ledger_when_checkpoint_insert_fails(
    tmp_path,
) -> None:
    db = _db(tmp_path, "constraint-atomicity.db")
    base = db.save_planning_checkpoint(build_planning_checkpoint(_goal_plan()))

    conn = db._connect()
    conn.execute(
        """
        CREATE TRIGGER fail_confirmed_checkpoint
        BEFORE INSERT ON planning_checkpoints
        BEGIN
            SELECT RAISE(ABORT, 'injected checkpoint insert failure');
        END
        """
    )
    conn.commit()
    conn.close()

    with pytest.raises(Exception, match="checkpoint insert failure"):
        planning_service.apply_constraint_to_active_plan(
            db,
            {
                "date": TARGET,
                "kind": "sick",
                "source": "coach",
                "note": "RED: atomic ledger/checkpoint apply",
            },
            base_checkpoint_id=int(base["id"]),
        )

    assert _checkpoint_ids(db) == [int(base["id"])]
    assert _all_constraints(db) == []


def test_retract_missing_donor_keeps_constraint_active(tmp_path) -> None:
    db = _db(tmp_path, "missing-donor.db")
    _seed_no_donor(db)
    constraint = db.save_coach_constraint(
        date=TARGET,
        kind="unavailable",
        source="coach",
    )
    before_checkpoints = _checkpoint_ids(db)

    with pytest.raises(HTTPException) as exc_info:
        planning_router.retract_constraint(int(constraint["id"]), db=db)

    assert exc_info.value.status_code == 409
    assert db.get_coach_constraint(int(constraint["id"]))["status"] == "active"
    assert _checkpoint_ids(db) == before_checkpoints


def test_stale_approval_writes_no_plan_or_constraint_state(tmp_path) -> None:
    db = _db(tmp_path, "stale-approval.db")
    db.save_planning_checkpoint(build_planning_checkpoint(_goal_plan()))
    payload = AITools(db).execute_tool(
        "create_plan_constraint",
        date=TARGET,
        kind="sick",
    )["result"]
    proposal = db.save_coach_proposal(
        action=payload["action"],
        params=payload["params"],
        preview=payload["preview"],
    )
    db.save_planning_checkpoint(build_planning_checkpoint(_goal_plan()))
    before_checkpoints = _checkpoint_ids(db)
    before_constraints = _all_constraints(db)

    with pytest.raises(HTTPException) as exc_info:
        decisions_router.approve_proposal(int(proposal["id"]), db=db)

    assert exc_info.value.status_code == 409
    assert _checkpoint_ids(db) == before_checkpoints
    assert _all_constraints(db) == before_constraints
    assert db.get_coach_proposal(int(proposal["id"]))["status"] == "failed"


def test_retract_rolls_back_status_when_checkpoint_insert_fails(tmp_path) -> None:
    db = _db(tmp_path, "retract-atomicity.db")
    _seed_chain(db)
    constraint = db.save_coach_constraint(
        date=TARGET,
        kind="unavailable",
        source="coach",
    )
    before_checkpoints = _checkpoint_ids(db)
    proposal_payload = AITools(db).execute_tool(
        "retract_plan_constraint",
        id=int(constraint["id"]),
    )["result"]
    proposal = db.save_coach_proposal(
        action=proposal_payload["action"],
        params=proposal_payload["params"],
        preview=proposal_payload["preview"],
    )
    conn = db._connect()
    conn.execute(
        """
        CREATE TRIGGER fail_retract_checkpoint
        BEFORE INSERT ON planning_checkpoints
        BEGIN
            SELECT RAISE(ABORT, 'injected retract checkpoint failure');
        END
        """
    )
    conn.commit()
    conn.close()

    with pytest.raises(HTTPException) as exc_info:
        decisions_router.approve_proposal(int(proposal["id"]), db=db)

    assert exc_info.value.status_code == 500
    assert db.get_coach_constraint(int(constraint["id"]))["status"] == "active"
    assert _checkpoint_ids(db) == before_checkpoints


def test_approval_claim_serializes_concurrent_double_apply(tmp_path, monkeypatch) -> None:
    """RED: all mutation proposal actions need the atomic applying claim."""
    db = _db(tmp_path, "approval-concurrency.db")
    proposal = db.save_coach_proposal(
        action="build_plan",
        params={"goal_type": "triathlon", "distance": "olympic"},
        preview={"status": "proposal"},
    )

    first_entered = Event()
    release_first = Event()
    call_count = 0
    call_lock = Lock()

    def fake_apply(_db, _proposal, *, variant_kind=None):
        nonlocal call_count
        with call_lock:
            call_count += 1
            call_number = call_count
        if call_number == 1:
            first_entered.set()
            assert release_first.wait(timeout=5)
        return {"applied_checkpoint_id": 42}

    monkeypatch.setattr(decisions_router, "_apply_proposal", fake_apply)
    outcomes: list[object] = []

    def approve_once() -> None:
        try:
            outcomes.append(decisions_router.approve_proposal(int(proposal["id"]), db=db))
        except HTTPException as exc:
            outcomes.append(exc)

    first = Thread(target=approve_once)
    first.start()
    assert first_entered.wait(timeout=5)
    second = Thread(target=approve_once)
    second.start()
    second.join(timeout=5)
    release_first.set()
    first.join(timeout=5)

    assert not first.is_alive() and not second.is_alive()
    successes = [item for item in outcomes if not isinstance(item, HTTPException)]
    failures = [item for item in outcomes if isinstance(item, HTTPException)]
    assert call_count == 1
    assert len(successes) == 1
    assert len(failures) == 1
    assert failures[0].status_code == 409


def test_approved_scoped_create_applies_once_and_preserves_sibling_leg(tmp_path) -> None:
    db = _db(tmp_path, "scoped-create.db")
    base = db.save_planning_checkpoint(build_planning_checkpoint(_goal_plan()))
    payload = AITools(db).execute_tool(
        "create_plan_constraint",
        date=TARGET,
        kind="unavailable",
        sport="swim",
    )["result"]
    proposal = _save_tool_proposal(db, payload)

    approved = decisions_router.approve_proposal(int(proposal["id"]), db=db)

    assert approved["result"]["base_checkpoint_id"] == int(base["id"])
    assert approved["result"]["date"] == TARGET
    assert approved["result"]["sport"] == "swim"
    checkpoint_after = db.get_latest_planning_checkpoint()
    plan = restore_goal_plan_from_checkpoint(checkpoint_after)
    target = next(item for item in plan["session_templates"] if item["date"] == TARGET)
    assert [session["sport"] for session in target["sessions"]] == ["bike"]

    with pytest.raises(HTTPException) as replay:
        decisions_router.approve_proposal(int(proposal["id"]), db=db)
    assert replay.value.status_code == 409
    assert db.get_latest_planning_checkpoint()["id"] == checkpoint_after["id"]
    assert len(_all_constraints(db)) == 1


@pytest.mark.parametrize("action", ["retract_plan_constraint", "repair_plan_day"])
def test_approved_retract_and_repair_use_saved_preview(tmp_path, action) -> None:
    db = _db(tmp_path, f"{action}.db")
    _donor, child = _seed_chain(db)
    if action == "retract_plan_constraint":
        constraint = db.save_coach_constraint(
            date=TARGET,
            kind="unavailable",
            source="coach",
        )
        payload = AITools(db).execute_tool(action, id=int(constraint["id"]))["result"]
    else:
        constraint = None
        payload = AITools(db).execute_tool(action, date=TARGET)["result"]
    proposal = _save_tool_proposal(db, payload)

    approved = decisions_router.approve_proposal(int(proposal["id"]), db=db)

    assert approved["result"]["base_checkpoint_id"] == int(child["id"])
    assert approved["result"]["date"] == TARGET
    assert int(db.get_latest_planning_checkpoint()["id"]) > int(child["id"])
    if constraint is not None:
        assert db.get_coach_constraint(int(constraint["id"]))["status"] == "inactive"


def test_reject_constraint_proposal_writes_no_plan_or_ledger_state(tmp_path) -> None:
    db = _db(tmp_path, "reject.db")
    db.save_planning_checkpoint(build_planning_checkpoint(_goal_plan()))
    payload = AITools(db).execute_tool(
        "create_plan_constraint",
        date=TARGET,
        kind="sick",
    )["result"]
    proposal = _save_tool_proposal(db, payload)
    before_checkpoints = _checkpoint_ids(db)

    rejected = decisions_router.reject_proposal(int(proposal["id"]), db=db)

    assert rejected["proposal"]["status"] == "rejected"
    assert rejected["proposal"]["resolved_at"]
    assert _checkpoint_ids(db) == before_checkpoints
    assert _all_constraints(db) == []


def test_fingerprint_mismatch_fails_before_mutation(tmp_path) -> None:
    db = _db(tmp_path, "fingerprint.db")
    db.save_planning_checkpoint(build_planning_checkpoint(_goal_plan()))
    payload = AITools(db).execute_tool(
        "create_plan_constraint",
        date=TARGET,
        kind="sick",
    )["result"]
    tampered_params = {**payload["params"], "preview_fingerprint": "tampered"}
    proposal = db.save_coach_proposal(
        action=payload["action"],
        params=tampered_params,
        preview=payload["preview"],
    )
    before_checkpoints = _checkpoint_ids(db)

    with pytest.raises(HTTPException) as exc_info:
        decisions_router.approve_proposal(int(proposal["id"]), db=db)

    assert exc_info.value.status_code == 409
    assert _checkpoint_ids(db) == before_checkpoints
    assert _all_constraints(db) == []


def test_reject_loses_race_after_approve_claim(tmp_path, monkeypatch) -> None:
    db = _db(tmp_path, "reject-race.db")
    proposal = db.save_coach_proposal(
        action="build_plan",
        params={"goal_type": "triathlon", "distance": "olympic"},
        preview={"status": "proposal"},
    )
    claimed = Event()
    release = Event()

    def fake_apply(_db, _proposal, *, variant_kind=None):
        claimed.set()
        assert release.wait(timeout=5)
        return {"applied_checkpoint_id": 42}

    monkeypatch.setattr(decisions_router, "_apply_proposal", fake_apply)
    approve_outcome: list[object] = []

    def approve_once() -> None:
        approve_outcome.append(decisions_router.approve_proposal(int(proposal["id"]), db=db))

    thread = Thread(target=approve_once)
    thread.start()
    assert claimed.wait(timeout=5)
    with pytest.raises(HTTPException) as reject_error:
        decisions_router.reject_proposal(int(proposal["id"]), db=db)
    release.set()
    thread.join(timeout=5)

    assert reject_error.value.status_code == 409
    assert not thread.is_alive()
    assert db.get_coach_proposal(int(proposal["id"]))["status"] == "approved"


def test_post_commit_rebind_failure_is_an_approved_warning(tmp_path, monkeypatch) -> None:
    db = _db(tmp_path, "rebind-warning.db")
    _seed_chain(db)
    constraint = db.save_coach_constraint(
        date=TARGET,
        kind="unavailable",
        source="coach",
        sport="swim",
    )
    payload = AITools(db).execute_tool(
        "retract_plan_constraint",
        id=int(constraint["id"]),
    )["result"]
    proposal = _save_tool_proposal(db, payload)

    def fail_rebind(*_args, **_kwargs):
        raise RuntimeError("injected rebind failure")

    monkeypatch.setattr(planning_service, "_rebind_restored_leg_matches", fail_rebind)
    approved = decisions_router.approve_proposal(int(proposal["id"]), db=db)

    assert approved["proposal"]["status"] == "approved"
    assert approved["result"]["warnings"] == [
        "plan/fact rebind deferred: injected rebind failure"
    ]
    assert db.get_coach_constraint(int(constraint["id"]))["status"] == "inactive"


@pytest.mark.parametrize("native", [False, True])
def test_marker_and_native_constraint_calls_only_produce_proposals(tmp_path, native) -> None:
    db = _db(tmp_path, f"runtime-{native}.db")
    db.save_planning_checkpoint(build_planning_checkpoint(_goal_plan()))
    tools = AITools(db)
    before_checkpoints = _checkpoint_ids(db)

    class Provider:
        calls = 0

        def supports_native_tools(self):
            return native

        def is_available(self):
            return True

        def generate_response(self, prompt, system_prompt=""):
            return (
                f"[TOOL: create_plan_constraint, date={TARGET}, kind=sick, "
                "note=только предложение]"
            )

        def generate_with_tools(self, messages, schemas, system_prompt=""):
            self.calls += 1
            if self.calls == 1:
                return {
                    "text": "",
                    "tool_calls": [
                        {
                            "id": "constraint-1",
                            "name": "create_plan_constraint",
                            "arguments": {
                                "date": TARGET,
                                "kind": "sick",
                                "note": "только предложение",
                            },
                        }
                    ],
                }
            return {"text": "Готово к подтверждению", "tool_calls": []}

    turn = resolve_turn_tool_results(
        provider=Provider(),
        ai_tools=tools,
        user_input="ок",
        history_messages=[],
        tool_result_formatter=lambda _name, _data: "proposal",
    )

    assert turn["native"] is native
    assert len(turn["tool_results"]) == 1
    assert turn["tool_results"][0]["raw_result"]["is_proposal"] is True
    assert _checkpoint_ids(db) == before_checkpoints
    assert _all_constraints(db) == []
