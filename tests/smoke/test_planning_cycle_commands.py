"""Cycle commands use temporary SQLite, explicit identity and retained evidence."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date
import json
import sqlite3
from threading import Barrier
from uuid import uuid4

import pytest

from tests.smoke._planning_cycle_regressions import client_for, evidence_bytes, legacy_db
from tests.smoke.test_planning_cycle_build import close, current
from tests.smoke.test_planning_cycle_storage import cycle_rows, rows

pytestmark = pytest.mark.smoke


def test_close_is_atomic_idempotent_and_preserves_evidence(tmp_path, monkeypatch):
    db = legacy_db(tmp_path, monkeypatch)
    before = evidence_bytes(db)
    command_id = str(uuid4())
    with client_for(db) as client:
        context = current(client)
        first = close(client, context, command_id=command_id)
        assert first.status_code == 200, first.text
        assert first.json()["current_context"]["state"] == "no_current"
        replay = close(client, context, command_id=command_id)
        assert replay.status_code == 200, replay.text
        assert replay.json()["replayed"] is True
        assert replay.json()["result"] == first.json()["result"]
        history = client.get(f'/api/planning/cycles/{context["cycle_id"]}')
        assert history.status_code == 200, history.text
        assert history.json()["state"] == "closed"
    assert evidence_bytes(db) == before


def test_event_declaration_is_explicit_and_does_not_close(tmp_path, monkeypatch):
    db = legacy_db(tmp_path, monkeypatch)
    before = evidence_bytes(db)
    with client_for(db) as client:
        context = current(client)
        response = client.post(f'/api/planning/cycles/{context["cycle_id"]}/event-outcome', json={
            "command_id": str(uuid4()), "confirm": True,
            "expected_cycle_revision": context["cycle_revision"],
            "event_key": context["events"][0]["event_key"], "outcome": "did_not_participate",
        })
        assert response.status_code == 200, response.text
        after = response.json()["current_context"]
        assert after["is_selected"] is True
        assert after["selection_revision"] == context["selection_revision"]
        assert after["cycle_revision"] == context["cycle_revision"] + 1
        assert after["events"][0]["outcome"] == "did_not_participate"
    assert evidence_bytes(db) == before


def test_explicit_constraint_scope_changes_only_ownership(tmp_path, monkeypatch):
    db = legacy_db(tmp_path, monkeypatch, constraint_kind="manual_delete")
    before = db.get_coach_constraint(1)
    with client_for(db) as client:
        constraint = client.get("/api/planning/constraints").json()["constraints"][0]
        response = client.post("/api/planning/cycles/constraint-scope", json={
            "command_id": str(uuid4()), "confirm": True, "constraint_id": 1,
            "expected_constraint_fingerprint": constraint["constraint_fingerprint"],
            "scope": "athlete",
        })
        assert response.status_code == 200, response.text
    after = db.get_coach_constraint(1)
    assert after["cycle_scope"] == "athlete"
    assert {key: value for key, value in after.items() if key not in {"cycle_scope", "cycle_id"}} == {
        key: value for key, value in before.items() if key not in {"cycle_scope", "cycle_id"}}


def command(context, kind, *, command_id=None):
    body = {"command_id": command_id or str(uuid4()), "confirm": True}
    if kind == "close":
        body.update(expected_selection_revision=context["selection_revision"],
                    expected_cycle_revision=context["cycle_revision"],
                    expected_checkpoint_id=context["checkpoint_id"])
    else:
        body.update(expected_cycle_revision=context["cycle_revision"],
                    event_key=context["events"][0]["event_key"], outcome="participated")
    return body


def post(client, context, kind, body):
    return client.post(f'/api/planning/cycles/{context["cycle_id"]}/{kind}', json=body)


@pytest.mark.parametrize("field", ["expected_selection_revision", "expected_cycle_revision", "expected_checkpoint_id"])
def test_stale_close_changes_nothing(tmp_path, monkeypatch, field):
    db = legacy_db(tmp_path, monkeypatch)
    before = cycle_rows(db), evidence_bytes(db)
    with client_for(db) as client:
        context = current(client)
        body = command(context, "close")
        body[field] += 1
        response = post(client, context, "close", body)
    assert response.status_code == 409, response.text
    assert response.json()["code"] == "cycle_stale"
    assert (cycle_rows(db), evidence_bytes(db)) == before


@pytest.mark.parametrize("kind", ["close", "event-outcome"])
@pytest.mark.parametrize("damage", ["false", "string", "numeric", "extra", "missing-id", "numeric-revision"])
def test_invalid_command_is_safe_and_write_free(tmp_path, monkeypatch, kind, damage):
    db = legacy_db(tmp_path, monkeypatch)
    before = cycle_rows(db), evidence_bytes(db)
    with client_for(db) as client:
        context = current(client)
        body = command(context, kind)
        if damage in {"false", "string", "numeric"}:
            body["confirm"] = {"false": False, "string": "true", "numeric": 1}[damage]
        elif damage == "extra":
            body["legacy_internal"] = True
        elif damage == "numeric-revision":
            body["expected_cycle_revision"] = str(context["cycle_revision"])
        else:
            del body["command_id"]
        response = post(client, context, kind, body)
    assert response.status_code == 422, response.text
    assert response.json() == {"detail": "Проверьте параметры команды или цикла.",
                               "code": "invalid_cycle_request", "retryable": False}
    assert (cycle_rows(db), evidence_bytes(db)) == before


def test_same_identity_changed_request_conflicts_before_cas(tmp_path, monkeypatch):
    db = legacy_db(tmp_path, monkeypatch)
    with client_for(db) as client:
        context = current(client)
        body = command(context, "close")
        assert post(client, context, "close", body).status_code == 200
        before = cycle_rows(db)
        body["expected_cycle_revision"] += 1
        conflict = post(client, context, "close", body)
        assert conflict.status_code == 409
        assert conflict.json()["code"] == "idempotency_conflict"
    assert cycle_rows(db) == before


@pytest.mark.parametrize("outcome,status", [("participated", 422), ("did_not_participate", 200)])
def test_future_outcome_requires_honest_declaration(tmp_path, monkeypatch, outcome, status):
    db = legacy_db(tmp_path, monkeypatch, start=date(2026, 10, 19))
    with client_for(db) as client:
        context = current(client)
        body = {**command(context, "event-outcome"), "outcome": outcome}
        response = post(client, context, "event-outcome", body)
        assert response.status_code == status, response.text
        if status == 422:
            assert response.json()["code"] == "invalid_event_outcome"
            assert cycle_rows(db)["planning_cycle_commands"] == []
        else:
            assert response.json()["result"]["event_outcomes"][0]["after"] == outcome


def test_close_with_outcome_increments_once_and_correction_keeps_closed(tmp_path, monkeypatch):
    db = legacy_db(tmp_path, monkeypatch)
    before = evidence_bytes(db)
    with client_for(db) as client:
        context = current(client)
        body = command(context, "close")
        body["event_outcomes"] = [{"event_key": context["events"][0]["event_key"], "outcome": "did_not_participate"}]
        response = post(client, context, "close", body)
        assert response.status_code == 200, response.text
        result = response.json()["result"]
        assert result["cycle_revision"] == context["cycle_revision"] + 1
        corrected = post(client, context, "event-outcome", {
            **command(context, "event-outcome"), "expected_cycle_revision": result["cycle_revision"],
        })
        assert corrected.status_code == 200, corrected.text
        assert corrected.json()["current_context"]["state"] == "no_current"
        historical = client.get(f'/api/planning/cycles/{context["cycle_id"]}').json()
        assert historical["state"] == "closed"
        assert historical["events"][0]["outcome"] == "participated"
        assert historical["selection_revision"] == result["selection_revision"]
    assert evidence_bytes(db) == before


def test_replay_old_close_never_clears_a_new_selection(tmp_path, monkeypatch):
    """Seed a second stored cycle; new-cycle publication belongs to M3b."""
    from tests.smoke._planning_cycle_regressions import CYCLE_B
    db = legacy_db(tmp_path, monkeypatch)
    with client_for(db) as client:
        context = current(client)
        body = command(context, "close")
        applied = post(client, context, "close", body).json()
        conn = db._connect()
        with conn:
            conn.execute("""INSERT INTO planning_cycles(id,current_checkpoint_id,revision,status,origin)
                VALUES(?,NULL,1,'open','explicit')""", (CYCLE_B,))
            conn.execute("UPDATE planning_cycle_state SET current_cycle_id=?,revision=revision+1", (CYCLE_B,))
        conn.close()
        before = cycle_rows(db)
        replay = post(client, context, "close", body)
        assert replay.status_code == 200, replay.text
        assert replay.json()["result"] == applied["result"]
        assert replay.json()["current_context"]["cycle_id"] == CYCLE_B
        assert replay.json()["current_context"]["state"] == "indeterminate"
    assert cycle_rows(db) == before


@pytest.mark.parametrize("kind", ["close", "event-outcome", "constraint-scope"])
@pytest.mark.parametrize("fault", ["state-write", "receipt-write", "before-commit", "response-validation"])
def test_command_fault_rolls_back_every_change(tmp_path, monkeypatch, kind, fault):
    from api.planning_cycle_contract import CycleCommandResponse
    db = legacy_db(tmp_path, monkeypatch, constraint_kind="manual_delete")
    before = cycle_rows(db), evidence_bytes(db), rows(db, "coach_constraints")
    with client_for(db) as client:
        context = current(client)
        if kind == "constraint-scope":
            constraint = client.get("/api/planning/constraints").json()["constraints"][0]
            body = {"command_id": str(uuid4()), "confirm": True, "constraint_id": 1,
                    "expected_constraint_fingerprint": constraint["constraint_fingerprint"], "scope": "athlete"}
        else:
            body = command(context, kind)

        class FaultConnection(sqlite3.Connection):
            def execute(self, sql, *args):
                result = super().execute(sql, *args)
                affected = "UPDATE coach_constraints" if kind == "constraint-scope" else "UPDATE planning_cycles"
                if ((fault == "state-write" and sql.startswith(affected))
                        or (fault == "receipt-write" and sql.startswith("INSERT INTO planning_cycle_commands"))):
                    raise sqlite3.IntegrityError("synthetic private command fault")
                return result

            def commit(self):
                if fault == "before-commit":
                    raise sqlite3.IntegrityError("synthetic private commit fault")
                return super().commit()

        def invalid_response(*args, **kwargs):
            raise RuntimeError("synthetic private serialization fault")

        with monkeypatch.context() as failing:
            failing.setattr(db, "_connect", lambda: sqlite3.connect(db.db_path, factory=FaultConnection))
            if fault == "response-validation":
                failing.setattr(CycleCommandResponse, "model_validate", invalid_response)
            response = (client.post("/api/planning/cycles/constraint-scope", json=body)
                        if kind == "constraint-scope" else post(client, context, kind, body))
        assert response.status_code == 500, response.text
        assert response.json()["code"] == "cycle_storage_error"
        assert "synthetic" not in response.text
        assert (cycle_rows(db), evidence_bytes(db), rows(db, "coach_constraints")) == before
        retry = (client.post("/api/planning/cycles/constraint-scope", json=body)
                 if kind == "constraint-scope" else post(client, context, kind, body))
        assert retry.status_code == 200, retry.text
        assert retry.json()["replayed"] is False


@pytest.mark.parametrize("same_identity", [False, True])
def test_simultaneous_close_has_one_commit_and_safe_replay(tmp_path, monkeypatch, same_identity):
    from api.planning_cycle_contract import CloseCycleRequest, CycleCommandResponse
    from models.planning_cycle import CycleCommandError
    from services.planning_cycle_commands import execute_cycle_command
    from services.planning_cycles import current_cycle_context
    db = legacy_db(tmp_path, monkeypatch)
    context = current_cycle_context(db)
    barrier = Barrier(2)
    body = command(context, "close")

    def worker(index):
        params = {**body}
        if not same_identity and index:
            params["command_id"] = str(uuid4())
        params = CloseCycleRequest.model_validate(params).model_dump(mode="json")
        barrier.wait(timeout=5)
        try:
            return execute_cycle_command(db, "close", params, cycle_id=context["cycle_id"],
                                         validate_response=CycleCommandResponse.model_validate)
        except CycleCommandError as exc:
            return {"error": exc.code}

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(worker, [0, 1]))
    assert len(rows(db, "planning_cycle_commands")) == 1
    assert current_cycle_context(db)["selection_revision"] == context["selection_revision"] + 1
    if same_identity:
        assert sorted(result["replayed"] for result in results) == [False, True]
        assert results[0]["result"] == results[1]["result"]
    else:
        assert sum(result.get("error") == "cycle_closed" for result in results) == 1


def test_missing_or_ambiguous_event_cannot_be_targeted(tmp_path, monkeypatch):
    from models.planning_checkpoints import build_planning_checkpoint
    from tests.smoke._planning_cycle_regressions import plan
    payload = build_planning_checkpoint(plan())
    payload["goal_plan_snapshot"]["events"] *= 2
    db = legacy_db(tmp_path, monkeypatch, payloads=[payload])
    before = cycle_rows(db)
    with client_for(db) as client:
        context = current(client)
        for key in (context["events"][0]["event_key"], "a" * 64):
            response = post(client, context, "event-outcome", {**command(context, "event-outcome"), "event_key": key})
            assert response.status_code == 404, response.text
            assert response.json()["code"] == "event_not_found"
    assert cycle_rows(db) == before


def test_scope_cas_replay_and_changed_scope_identity(tmp_path, monkeypatch):
    db = legacy_db(tmp_path, monkeypatch, constraint_kind="manual_delete")
    with client_for(db) as client:
        context = current(client)
        constraint = client.get("/api/planning/constraints").json()["constraints"][0]
        body = {"command_id": str(uuid4()), "confirm": True, "constraint_id": 1,
                "expected_constraint_fingerprint": constraint["constraint_fingerprint"],
                "scope": "cycle", "cycle_id": context["cycle_id"]}
        first = client.post("/api/planning/cycles/constraint-scope", json=body)
        assert first.status_code == 200, first.text
        before = cycle_rows(db), rows(db, "coach_constraints")
        replay = client.post("/api/planning/cycles/constraint-scope", json=body)
        assert replay.status_code == 200, replay.text
        assert replay.json()["replayed"] is True
        assert replay.json()["result"] == first.json()["result"]
        stale = client.post("/api/planning/cycles/constraint-scope", json={**body, "command_id": str(uuid4())})
        assert stale.status_code == 409 and stale.json()["code"] == "cycle_stale"
        conflict = client.post("/api/planning/cycles/constraint-scope", json={**body, "scope": "athlete", "cycle_id": None})
        assert conflict.status_code == 409 and conflict.json()["code"] == "idempotency_conflict"
    assert (cycle_rows(db), rows(db, "coach_constraints")) == before


def test_receipt_integrity_and_append_only_retention(tmp_path, monkeypatch):
    db = legacy_db(tmp_path, monkeypatch)
    with client_for(db) as client:
        context = current(client)
        body = command(context, "close")
        assert post(client, context, "close", body).status_code == 200
        conn = db._connect()
        try:
            for sql in ("DELETE FROM planning_cycle_commands", "UPDATE planning_cycle_commands SET result_json='{}'"):
                with pytest.raises(sqlite3.IntegrityError, match="immutable"):
                    conn.execute(sql)
                conn.rollback()
            # Simulate external corruption only after demonstrating production's
            # guard; no application path can rewrite the retained receipt.
            with conn:
                conn.execute("DROP TRIGGER planning_cycle_commands_no_update")
                conn.execute("UPDATE planning_cycle_commands SET result_json='{}'")
        finally:
            conn.close()
        before = cycle_rows(db)
        response = post(client, context, "close", body)
        assert response.status_code == 500 and response.json()["code"] == "cycle_corrupt"
        assert response.json()["retryable"] is False
    assert cycle_rows(db) == before


@pytest.mark.parametrize("damage", ["false", "extra", "athlete-with-cycle", "cycle-without-id", "unknown-cycle", "bad-fingerprint"])
def test_invalid_scope_refuses_without_mutation(tmp_path, monkeypatch, damage):
    db = legacy_db(tmp_path, monkeypatch, constraint_kind="manual_delete")
    before = cycle_rows(db), rows(db, "coach_constraints")
    with client_for(db) as client:
        constraint = client.get("/api/planning/constraints").json()["constraints"][0]
        body = {"command_id": str(uuid4()), "confirm": True, "constraint_id": 1,
                "expected_constraint_fingerprint": constraint["constraint_fingerprint"], "scope": "athlete"}
        if damage == "false":
            body["confirm"] = False
        elif damage == "extra":
            body["status"] = "inactive"
        elif damage == "athlete-with-cycle":
            body["cycle_id"] = str(uuid4())
        elif damage == "cycle-without-id":
            body["scope"] = "cycle"
        elif damage == "unknown-cycle":
            body.update(scope="cycle", cycle_id=str(uuid4()))
        else:
            body["expected_constraint_fingerprint"] = "not-a-fingerprint"
        response = client.post("/api/planning/cycles/constraint-scope", json=body)
    assert response.status_code == (404 if damage == "unknown-cycle" else 422), response.text
    assert (cycle_rows(db), rows(db, "coach_constraints")) == before


def test_old_version_event_is_still_declarable_without_reopening(tmp_path, monkeypatch):
    db = legacy_db(tmp_path, monkeypatch)
    before = evidence_bytes(db)
    with client_for(db) as client:
        context = current(client)
        # Seed a second version in the SAME stored cycle, preserving the old
        # snapshot. Actual edit publication/CAS belongs to M3b.
        conn = db._connect()
        with conn:
            raw = conn.execute("SELECT checkpoint_data FROM planning_checkpoints WHERE id=1").fetchone()[0]
            payload = json.loads(raw)
            payload["goal_plan_snapshot"]["events"][0]["label"] = "Different event snapshot"
            cursor = conn.execute("INSERT INTO planning_checkpoints(checkpoint_data) VALUES(?)", (json.dumps(payload),))
            checkpoint_id = cursor.lastrowid
            conn.execute("INSERT INTO planning_cycle_versions VALUES(?,?,'edit')", (checkpoint_id, context["cycle_id"]))
            conn.execute("UPDATE planning_cycles SET current_checkpoint_id=?,revision=revision+1 WHERE id=?",
                         (checkpoint_id, context["cycle_id"]))
        conn.close()
        response = post(client, context, "event-outcome", {
            **command(context, "event-outcome"), "expected_cycle_revision": context["cycle_revision"] + 1,
        })
        assert response.status_code == 200, response.text
        declaration = response.json()["result"]["event_outcomes"][0]
        assert declaration["checkpoint_id"] == 1
        assert declaration["event_snapshot"]["label"] == "Synthetic Olympic"
        assert declaration["before"] == "unspecified" and declaration["after"] == "participated"
        assert response.json()["current_context"]["checkpoint_id"] == checkpoint_id
        assert response.json()["current_context"]["events"][0]["outcome"] == "unspecified"
    after = evidence_bytes(db)
    assert after["planning_checkpoints"][0] == before["planning_checkpoints"][0]
    assert all(after[table] == values for table, values in before.items() if table != "planning_checkpoints")


def test_selection_write_failure_rolls_back_closure(tmp_path, monkeypatch):
    db = legacy_db(tmp_path, monkeypatch)
    before = cycle_rows(db)
    conn = db._connect()
    with conn:
        conn.execute("""CREATE TRIGGER refuse_selection BEFORE UPDATE ON planning_cycle_state
            BEGIN SELECT RAISE(ABORT, 'synthetic selection failure'); END""")
    conn.close()
    with client_for(db) as client:
        context = current(client)
        response = post(client, context, "close", command(context, "close"))
        assert response.status_code == 500 and response.json()["code"] == "cycle_storage_error"
    assert cycle_rows(db) == before


def test_busy_writer_returns_retry_same_identity(tmp_path, monkeypatch):
    db = legacy_db(tmp_path, monkeypatch)
    with client_for(db) as client:
        context = current(client)
        body = command(context, "close")
        locker = db._connect()
        try:
            locker.execute("BEGIN IMMEDIATE")
            with monkeypatch.context() as busy:
                busy.setattr(db, "_connect", lambda: sqlite3.connect(db.db_path, timeout=0))
                response = post(client, context, "close", body)
            assert response.status_code == 503
            assert response.json()["code"] == "planning_busy" and response.json()["retryable"] is True
        finally:
            locker.rollback()
            locker.close()
        retry = post(client, context, "close", body)
        assert retry.status_code == 200, retry.text
        assert retry.json()["replayed"] is False


@pytest.mark.parametrize("kind", ["close", "event-outcome", "constraint-scope"])
def test_successful_receipt_survives_restart_and_backup(tmp_path, monkeypatch, kind):
    from data.database import Database
    from scripts.sqlite_backup_restore import backup_database, restore_database
    db = legacy_db(tmp_path, monkeypatch, constraint_kind="manual_delete")
    with client_for(db) as client:
        context = current(client)
        url = ("/api/planning/cycles/constraint-scope" if kind == "constraint-scope"
               else f'/api/planning/cycles/{context["cycle_id"]}/{kind}')
        if kind == "constraint-scope":
            constraint = client.get("/api/planning/constraints").json()["constraints"][0]
            body = {"command_id": str(uuid4()), "confirm": True, "constraint_id": 1,
                    "expected_constraint_fingerprint": constraint["constraint_fingerprint"], "scope": "athlete"}
        else:
            body = command(context, kind)
        applied = client.post(url, json=body)
        assert applied.status_code == 200, applied.text
    backup_path, restored_path = tmp_path / "receipt-backup.db", tmp_path / "restored.db"
    backup_database(db.db_path, backup_path, confirm_stopped=True)
    restore_database(backup_path, restored_path, confirm_stopped=True)
    reopened = Database(str(restored_path))
    before = cycle_rows(reopened), evidence_bytes(reopened), rows(reopened, "coach_constraints")
    with client_for(reopened) as client:
        replay = client.post(url, json=body)
        assert replay.status_code == 200, replay.text
        assert replay.json()["replayed"] is True
        assert replay.json()["result"] == applied.json()["result"]
    assert (cycle_rows(reopened), evidence_bytes(reopened), rows(reopened, "coach_constraints")) == before


@pytest.mark.parametrize("path,status,code", [
    ("/api/planning/cycles/not-a-uuid", 422, "invalid_cycle_request"),
    ("/api/planning/cycles/00000000-0000-4000-8000-000000000002", 404, "cycle_not_found"),
    ("/api/planning/cycles?limit=51", 422, "invalid_cycle_request"),
    ("/api/planning/cycles?limit=0", 422, "invalid_cycle_request"),
])
def test_cycle_read_errors_are_safe_and_do_not_write(tmp_path, monkeypatch, path, status, code):
    db = legacy_db(tmp_path, monkeypatch)
    before = cycle_rows(db), evidence_bytes(db)
    with client_for(db) as client:
        response = client.get(path)
    assert response.status_code == status and response.json()["code"] == code
    assert response.json()["retryable"] is False
    assert (cycle_rows(db), evidence_bytes(db)) == before


@pytest.mark.parametrize("damage", ["checkpoint-json", "outcome-json", "no-events"])
def test_close_without_outcome_works_for_indeterminate_or_no_event_cycle(tmp_path, monkeypatch, damage):
    from models.planning_checkpoints import build_planning_checkpoint
    from tests.smoke._planning_cycle_regressions import plan
    payload = build_planning_checkpoint(plan())
    if damage == "checkpoint-json":
        payload = "{not-json"
    elif damage == "no-events":
        payload["goal_plan_snapshot"]["events"] = []
    db = legacy_db(tmp_path, monkeypatch, payloads=[payload])
    if damage == "outcome-json":
        conn = db._connect()
        with conn:
            conn.execute("UPDATE planning_cycles SET event_outcomes_json='{broken'")
        conn.close()
    before = evidence_bytes(db)
    with client_for(db) as client:
        context = current(client)
        response = post(client, context, "close", command(context, "close"))
        assert response.status_code == 200, response.text
        assert response.json()["result"]["event_outcomes"] == []
        assert response.json()["current_context"]["state"] == "no_current"
    assert evidence_bytes(db) == before


def test_full_reset_deletes_actual_receipts_and_restores_retention_guards(tmp_path, monkeypatch):
    db = legacy_db(tmp_path, monkeypatch)
    with client_for(db) as client:
        context = current(client)
        assert post(client, context, "close", command(context, "close")).status_code == 200
    db.clear_all_data()
    assert rows(db, "planning_cycle_commands") == []
    conn = db._connect()
    try:
        triggers = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='trigger'")}
        assert {"planning_cycle_commands_no_delete", "planning_cycle_commands_no_update",
                "planning_cycle_commands_no_replace"} <= triggers
    finally:
        conn.close()


def test_nonfinite_response_fails_before_commit(tmp_path, monkeypatch):
    from models.planning_checkpoints import build_planning_checkpoint
    from tests.smoke._planning_cycle_regressions import plan
    from services.planning_cycles import current_cycle_context
    payload = build_planning_checkpoint(plan())
    payload["goal_plan_snapshot"]["weekly_summary"][0]["weekly_tss"] = float("nan")
    db = legacy_db(tmp_path, monkeypatch, payloads=[payload])
    context = current_cycle_context(db)
    before = cycle_rows(db)
    with client_for(db) as client:
        response = post(client, context, "event-outcome", command(context, "event-outcome"))
    assert response.status_code == 500 and response.json()["code"] == "cycle_corrupt"
    assert cycle_rows(db) == before
