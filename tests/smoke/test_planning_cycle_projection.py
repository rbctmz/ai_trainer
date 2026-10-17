"""S2 M1: behavioral RED and preliminary HTTP projection obligations."""
from datetime import date, datetime, timezone

import pytest

from api import planning_service as ps
from models.planning_checkpoints import build_planning_checkpoint
from tests.smoke._planning_cycle_regressions import (
    client_for, evidence_bytes, legacy_db, pin_clock, plan,
)

pytestmark = pytest.mark.smoke


@pytest.mark.parametrize("start", [date(2026, 9, 28), date(2026, 10, 19)],
                         ids=["ended", "scheduled"])
def test_behavior_phase_is_not_current_outside_period(tmp_path, monkeypatch, start):
    db = legacy_db(tmp_path, monkeypatch, start=start)
    overview = ps.active_plan_overview(db)
    assert overview["has_plan"] is True
    assert overview.get("current_week") is None, "A past/future week is not the current phase"


@pytest.mark.parametrize(("start", "days", "state"), [
    (date(2026, 10, 19), 7, "scheduled"),
    (date(2026, 10, 16), 7, "in_progress"),
    (date(2026, 10, 12), 5, "in_progress"),
    (date(2026, 10, 12), 4, "period_ended"),
], ids=["before-start", "on-start", "on-end", "day-after-end"])
def test_protocol_selected_projection_boundaries(tmp_path, monkeypatch, start, days, state):
    db = legacy_db(tmp_path, monkeypatch, start=start, days=days)
    before = evidence_bytes(db)
    with client_for(db) as client:
        response = client.get("/api/planning/cycles/current")
    assert response.status_code == 200, response.text
    context = response.json()
    assert context["state"] == state
    assert context["cycle_id"] == context["current_cycle_id"]
    assert context["is_selected"] is True
    assert context["is_legacy"] is True
    assert context["checkpoint_id"] == 1
    assert context["start_date"] == start.isoformat()
    assert context["athlete_day"] == "2026-10-16"
    assert all(event["outcome"] == "unspecified" for event in context["events"])
    assert evidence_bytes(db) == before


def test_protocol_empty_cache_has_no_current_cycle(tmp_path, monkeypatch):
    db = legacy_db(tmp_path, monkeypatch, payloads=[])
    with client_for(db) as client:
        response = client.get("/api/planning/cycles/current")
    assert response.status_code == 200, response.text
    context = response.json()
    assert context["state"] == "no_current"
    assert context["cycle_id"] is None
    assert context["has_history"] is False


@pytest.mark.parametrize("damage", ["missing-days", "invalid-json", "contradictory-days"])
def test_protocol_malformed_latest_does_not_fall_back_to_older_plan(tmp_path, monkeypatch, damage):
    old = build_planning_checkpoint(plan())
    latest = build_planning_checkpoint(plan(date(2026, 10, 12)))
    if damage == "missing-days":
        latest["goal_plan_snapshot"]["daily_plan"] = []
    elif damage == "invalid-json":
        latest = "{not-json"
    else:
        latest["goal_plan_snapshot"]["daily_plan"][0]["date"] = "invalid-date"
    db = legacy_db(tmp_path, monkeypatch, payloads=[old, latest])
    before = evidence_bytes(db)
    with client_for(db) as client:
        response = client.get("/api/planning/cycles/current")
    assert response.status_code == 200, response.text
    context = response.json()
    assert context["state"] == "indeterminate"
    assert context["checkpoint_id"] == 2
    assert context["reason_code"]
    assert evidence_bytes(db) == before


@pytest.mark.parametrize(("zone", "day", "state"), [
    ("Europe/Moscow", "2026-10-17", "period_ended"),
    ("Pacific/Honolulu", "2026-10-16", "in_progress"),
])
def test_protocol_projection_uses_athlete_day(tmp_path, monkeypatch, zone, day, state):
    db = legacy_db(tmp_path, monkeypatch, start=date(2026, 10, 12), days=5)
    pin_clock(monkeypatch, observed=datetime(2026, 10, 16, 21, 30, tzinfo=timezone.utc), zone=zone)
    with client_for(db) as client:
        response = client.get("/api/planning/cycles/current")
    assert response.status_code == 200, response.text
    assert response.json()["athlete_day"] == day
    assert response.json()["state"] == state


def test_protocol_status_has_readable_but_not_actionable_ended_plan(tmp_path, monkeypatch):
    db = legacy_db(tmp_path, monkeypatch)
    with client_for(db) as client:
        response = client.get("/api/planning/status")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["has_plan"] is True
    assert payload.get("has_actionable_plan") is False
    assert payload["cycle_context"]["state"] == "period_ended"


@pytest.mark.parametrize(("kind", "scope"), [
    ("manual_delete", "unknown"), ("disabled_plan_day", "unknown"),
    ("sick", "athlete"), ("unavailable", "athlete"), ("forced_rest", "athlete"),
])
def test_protocol_unbound_legacy_constraint_scope_is_explicit(tmp_path, monkeypatch, kind, scope):
    db = legacy_db(tmp_path, monkeypatch, constraint_kind=kind)
    row = db.get_coach_constraint(1)
    assert row["kind"] == kind
    assert row.get("cycle_scope") == scope
    assert row.get("cycle_id") is None
