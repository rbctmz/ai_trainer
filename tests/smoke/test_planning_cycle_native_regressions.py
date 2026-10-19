"""Exact native round-1 regressions for #693 AC1/AC5, synthetic SQLite only."""
from datetime import timedelta
import json
from uuid import uuid4

import pytest

from api import planning_service as ps
from models.ai_tools import AITools
from services.planning_cycles import current_cycle_context
from tests.planning_fixtures import append_history
from tests.smoke._planning_cycle_regressions import TODAY, client_for, evidence_bytes, legacy_db
from tests.smoke.test_planning_cycle_commands import command, post
from tests.smoke.test_planning_cycle_writer_guards import child, close, writer_state

pytestmark = pytest.mark.smoke


@pytest.mark.parametrize("prior", ["participated", "did_not_participate"])
@pytest.mark.parametrize("route", ["event-outcome", "close"])
def test_unspecified_removes_declaration_but_retains_correction_receipt(tmp_path, monkeypatch, prior, route):
    db = legacy_db(tmp_path, monkeypatch)
    before = evidence_bytes(db)
    with client_for(db) as client:
        context = current_cycle_context(db)
        key = context["events"][0]["event_key"]
        response = post(client, context, "event-outcome", {**command(context, "event-outcome"), "outcome": prior})
        assert response.status_code == 200, response.text
        context = response.json()["current_context"]
        body = command(context, route)
        if route == "close":
            body["event_outcomes"] = [{"event_key": key, "outcome": "unspecified"}]
        else:
            body["outcome"] = "unspecified"
        cleared = post(client, context, route, body)
        assert cleared.status_code == 200, cleared.text
        change = cleared.json()["result"]["event_outcomes"][0]
        assert (change["before"], change["after"]) == (prior, "unspecified")
        conn = db._connect()
        try:
            assert json.loads(conn.execute("SELECT event_outcomes_json FROM planning_cycles").fetchone()[0]) == {}
            assert conn.execute("SELECT COUNT(*) FROM planning_cycle_commands").fetchone()[0] == 2
        finally:
            conn.close()
        saved = writer_state(db)
        replay = post(client, context, route, body)
        assert replay.status_code == 200, replay.text
        assert replay.json()["replayed"] is True
        assert replay.json()["result"] == cleared.json()["result"]
        assert writer_state(db) == saved
        historical = client.get(f'/api/planning/cycles/{context["cycle_id"]}').json()
        assert historical["events"][0]["outcome"] == "unspecified"
    assert evidence_bytes(db) == before


@pytest.mark.parametrize("change", ["rename", "remove"])
def test_owned_prior_event_stays_readable_and_correctable_after_edit_and_close(tmp_path, monkeypatch, change):
    db = legacy_db(tmp_path, monkeypatch, start=TODAY)
    with client_for(db) as client:
        context = current_cycle_context(db)
        key = context["events"][0]["event_key"]
        response = post(client, context, "event-outcome", {
            **command(context, "event-outcome"), "outcome": "did_not_participate"})
        assert response.status_code == 200, response.text
        prepared = child(db)
        events = prepared["goal_plan_snapshot"]["events"]
        if change == "rename":
            events[0]["label"] = "Renamed event"
        else:
            events.clear()
        saved = db.save_planning_checkpoint(prepared, cycle_context=db.planning_write_context())
        foreign = child(db)
        foreign["goal_plan_snapshot"]["events"] = [{"label": "Unassigned event", "date": TODAY.isoformat()}]
        append_history(db, foreign)
        before_reads = writer_state(db)
        current = client.get('/api/planning/cycles/current').json()
        historical = client.get(f'/api/planning/cycles/{context["cycle_id"]}').json()
        listed = client.get('/api/planning/cycles').json()["cycles"][0]
        assert writer_state(db) == before_reads
        assert current["events"] == historical["events"] == listed["events"]
        by_key = {event["event_key"]: event for event in historical["events"]}
        assert key in by_key
        assert by_key[key]["label"] == "Synthetic Olympic"
        assert by_key[key]["outcome"] == "did_not_participate"
        assert "Unassigned event" not in {event["label"] for event in historical["events"]}
        if change == "rename":
            assert historical["events"][0]["label"] == "Renamed event"
            assert historical["events"][0]["outcome"] == "unspecified"
        close(db)
        closed = client.get(f'/api/planning/cycles/{context["cycle_id"]}').json()
        assert closed["state"] == "closed"
        assert "set_event_outcome" in closed["allowed_actions"]
        corrected = post(client, closed, "event-outcome", {
            "command_id": str(uuid4()), "confirm": True,
            "expected_cycle_revision": closed["cycle_revision"], "event_key": key, "outcome": "unspecified",
        })
        assert corrected.status_code == 200, corrected.text
        audit = corrected.json()["result"]["event_outcomes"][0]
        assert audit["checkpoint_id"] == context["checkpoint_id"]
        assert audit["event_snapshot"]["label"] == "Synthetic Olympic"
        assert corrected.json()["result"]["checkpoint_id"] == saved["id"]
        assert corrected.json()["current_context"]["state"] == "no_current"


@pytest.mark.parametrize("prior_ambiguous", [False, True])
def test_repeated_owned_event_is_deduplicated_without_false_ambiguity(tmp_path, monkeypatch, prior_ambiguous):
    from models.planning_checkpoints import build_planning_checkpoint
    from tests.smoke._planning_cycle_regressions import plan
    payload = build_planning_checkpoint(plan(start=TODAY))
    if prior_ambiguous:
        payload["goal_plan_snapshot"]["events"] *= 2
    db = legacy_db(tmp_path, monkeypatch, payloads=[payload])
    original = current_cycle_context(db)["events"][0]
    prepared = child(db)
    prepared["goal_plan_snapshot"]["events"] = prepared["goal_plan_snapshot"]["events"][:1]
    saved = db.save_planning_checkpoint(prepared, cycle_context=db.planning_write_context())
    assert current_cycle_context(db)["events"] == [original]
    with client_for(db) as client:
        context = current_cycle_context(db)
        response = post(client, context, "event-outcome", {
            **command(context, "event-outcome"), "outcome": "did_not_participate"})
    assert response.status_code == (404 if prior_ambiguous else 200), response.text
    if prior_ambiguous:
        assert response.json()["code"] == "event_not_found"
    else:
        assert response.json()["result"]["event_outcomes"][0]["checkpoint_id"] == saved["id"]


@pytest.mark.parametrize("terminal", ["closed", "replaced"])
def test_coach_upcoming_reconciles_captured_checkpoint_and_athlete_day(tmp_path, monkeypatch, terminal):
    from models import ai_tools
    from services.planning_cycles import current_plan_snapshot
    from tests.smoke.test_planning_cycle_build_v2 import prepare, confirm

    db = legacy_db(tmp_path, monkeypatch, start=TODAY)
    captured, checkpoint = current_plan_snapshot(db)
    original_reconcile = ps.reconciliation_at

    def snapshot_then_change(database):
        result = current_plan_snapshot(database)
        if terminal == "closed":
            close(database)
        else:
            confirm(database, prepare(database))
        return result

    def reconcile_captured(database, **kwargs):
        assert kwargs.get("checkpoint") == checkpoint
        assert kwargs["as_of"] == TODAY
        return original_reconcile(database, **kwargs)

    monkeypatch.setattr(ai_tools, "current_plan_snapshot", snapshot_then_change)
    monkeypatch.setattr(ai_tools, "athlete_local_date", lambda: TODAY + timedelta(days=1))
    monkeypatch.setattr(ps, "reconciliation_at", reconcile_captured)
    result = AITools(db).get_upcoming_workouts(days=0)
    assert result["cycle_context"] == captured
    assert result["sessions"]
    assert {row["date"] for row in result["sessions"]} == {TODAY.isoformat()}
    assert current_cycle_context(db)["cycle_id"] != captured["cycle_id"]
