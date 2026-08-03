"""BDD gates for Planning M2 phase roadmap and form projection (#302)."""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from api import planning_service as ps
from api.routers.planning import planning_overview
from data.database import Database
from tests.smoke.test_api_planning import _seeded_db


pytestmark = pytest.mark.smoke
REPO_ROOT = Path(__file__).resolve().parents[2]


def _event_plan_db(tmp_path) -> Database:
    db = _seeded_db(tmp_path)
    today = datetime.now().date()
    ps.build_plan(
        db,
        goal_type="triathlon",
        distance="olympic",
        event_date=None,
        events=[
            {"date": (today + timedelta(weeks=3)).isoformat(), "priority": "B", "label": "Tune-up", "confirmed": True},
            {"date": (today + timedelta(weeks=5)).isoformat(), "priority": "C", "label": "Club race", "confirmed": True},
            {"date": (today + timedelta(weeks=9)).isoformat(), "priority": "A", "label": "Main race", "confirmed": True},
        ],
        planning_mode="event_goal",
        available_hours=10,
        persist=True,
    )
    return db


def test_event_plan_overview_has_complete_roadmap_and_server_boundary(tmp_path):
    overview = planning_overview(db=_event_plan_db(tmp_path))

    roadmap = overview["roadmap"]
    projection = overview["form_projection"]
    assert roadmap["state"] == "available"
    assert roadmap["segments"]
    assert roadmap["segments"][0]["start_date"] == roadmap["horizon_start"]
    assert roadmap["segments"][-1]["end_date"] == roadmap["horizon_end"]
    assert all(
        left["end_date"] < right["start_date"]
        for left, right in zip(roadmap["segments"], roadmap["segments"][1:])
    )
    assert len(
        [segment for segment in roadmap["segments"] if segment["is_current"]]
    ) == 1
    assert {event["priority"] for event in roadmap["events"]} == {"A", "B", "C"}
    a_event = next(event for event in roadmap["events"] if event["priority"] == "A")
    assert a_event["label"] == "Main race"
    assert 90 <= a_event["position_percent"] <= 100

    assert projection["state"] == "available"
    assert projection["boundary_date"] == datetime.now().date().isoformat()
    assert projection["actual_points"]
    assert projection["forecast_points"]
    assert all(point["date"] <= projection["boundary_date"] for point in projection["actual_points"])
    assert all(point["date"] > projection["boundary_date"] for point in projection["forecast_points"])
    assert projection["summary"]["current_ctl"] is not None
    assert projection["summary"]["target_date"] == overview["timeline"]["event"]["date"]
    assert projection["summary"]["days_to_goal"] is not None
    assert any(
        point["date"] == projection["summary"]["target_date"]
        for point in projection["forecast_points"]
    )


def test_roadmap_only_extends_for_the_short_post_plan_event_bridge():
    today = datetime.now().date()
    horizon_start = today - timedelta(days=today.weekday())
    final_planned_date = horizon_start + timedelta(days=27)
    boundary_event = final_planned_date + timedelta(days=1)
    distant_event = final_planned_date + timedelta(days=365)
    goal_plan = {
        "daily_plan": [
            (datetime.combine(horizon_start, datetime.min.time()), 10.0, {"run": 10.0}),
            (datetime.combine(final_planned_date, datetime.min.time()), 10.0, {"run": 10.0}),
        ],
        "weekly_summary": [
            {
                "week_start": (horizon_start + timedelta(weeks=index)).isoformat(),
                "phase": "Base",
            }
            for index in range(4)
        ],
        "events": [
            {"date": boundary_event.isoformat(), "priority": "A", "label": "Boundary race"},
            {"date": distant_event.isoformat(), "priority": "C", "label": "Next season"},
        ],
    }

    roadmap = ps._active_plan_roadmap(goal_plan, today=today)

    assert roadmap["horizon_end"] == boundary_event.isoformat()
    assert [event["label"] for event in roadmap["events"]] == ["Boundary race"]
    assert roadmap["segments"][-1]["end_date"] == boundary_event.isoformat()


def test_rolling_horizon_has_no_synthetic_race_date_or_countdown(tmp_path):
    db = _seeded_db(tmp_path)
    ps.build_plan(
        db,
        goal_type="run",
        distance="10k",
        event_date=None,
        planning_mode="training_goal",
        intent="develop",
        horizon_weeks=6,
        events=[],
        available_hours=8,
        persist=True,
    )

    projection = planning_overview(db=db)["form_projection"]

    assert projection["state"] == "available"
    assert projection["summary"]["target_kind"] == "horizon_end"
    assert projection["summary"]["days_to_goal"] is None
    assert projection["summary"]["target_date"] is not None


def test_missing_activity_history_is_a_projection_data_gap_not_zero_chart(tmp_path):
    db = Database(str(tmp_path / "empty-history.db"))
    event_date = (datetime.now().date() + timedelta(weeks=6)).isoformat()
    ps.build_plan(
        db,
        goal_type="run",
        distance="10k",
        event_date=event_date,
        planning_mode="event_goal",
        available_hours=6,
        persist=True,
    )

    projection = planning_overview(db=db)["form_projection"]

    assert projection["state"] == "data_gap"
    assert projection["actual_points"] == []
    assert projection["forecast_points"] == []
    assert projection["summary"] is None


def test_overview_ui_uses_accessible_server_owned_roadmap_and_projection():
    source = (REPO_ROOT / "web/app/planning/page.tsx").read_text(encoding="utf-8")
    types = (REPO_ROOT / "web/lib/types.ts").read_text(encoding="utf-8")

    assert "PhaseRoadmap" in source
    assert "FormProjection" in source
    assert "Факт до" in source and "Прогноз после" in source
    assert "strokeDasharray" in source
    assert "role=\"img\"" in source
    assert "roadmap" in types and "form_projection" in types
