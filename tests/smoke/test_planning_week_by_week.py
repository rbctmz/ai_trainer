"""BDD gates for Planning M3 week-by-week reader (#303)."""
from __future__ import annotations

import copy
from datetime import date, datetime, timedelta
import importlib
from pathlib import Path

import pytest

from api import planning_service as ps
from data.database import Database
from models.planning_checkpoints import build_planning_checkpoint


pytestmark = pytest.mark.smoke
REPO_ROOT = Path(__file__).resolve().parents[2]


def _shift_active_plan_into_past_and_future(db: Database) -> dict:
    """Persist a fixture whose saved horizon includes past/current/future weeks.

    The planner places rest days nondeterministically, so a fixed calendar
    shift can land "today" on a rest day (``plan_days`` omits rest days) and
    the test's ``current`` lookup fails with StopIteration. We try offsets
    0..6 days around the -14 day shift and keep the first plan where today is
    a training day; at most eight of the fifty-six days are rest days, so at
    least one of the seven offsets is guaranteed to work.
    """
    db.save_athlete_profile({"ftp": 200, "lthr": 165, "weight_kg": 80, "source": "test"})
    ps.build_plan(
        db,
        goal_type="triathlon",
        distance="olympic",
        event_date=None,
        planning_mode="training_goal",
        intent="develop",
        horizon_weeks=8,
        events=[],
        available_hours=12,
        available_days=["mon", "tue", "wed", "thu", "fri", "sat", "sun"],
        persist=True,
    )
    plan = ps.get_active_plan(db)
    assert plan is not None
    today = datetime.now().date()

    def shifted(delta: timedelta) -> dict:
        candidate = copy.deepcopy(plan)
        candidate["daily_plan"] = [
            (item[0] + delta, item[1], item[2])
            for item in candidate["daily_plan"]
        ]
        for template in candidate["session_templates"]:
            template["date"] = (
                date.fromisoformat(str(template["date"])[:10]) + delta
            ).isoformat()
            for session in template.get("sessions") or []:
                session["date"] = template["date"]
        for week in candidate["weekly_summary"]:
            week["week_start"] = (
                date.fromisoformat(str(week["week_start"])[:10]) + delta
            ).isoformat()
        return candidate

    def includes_today(candidate: dict) -> bool:
        db.save_planning_checkpoint(build_planning_checkpoint(candidate))
        restored = ps.get_active_plan(db) or {}
        return any(
            date.fromisoformat(str(day.get("date"))[:10]) == today
            for day in ps.plan_days(restored)
        )

    selected = None
    for offset in range(7):
        candidate = shifted(timedelta(days=-14 + offset))
        if includes_today(candidate):
            selected = candidate
            break
    assert selected is not None, "fixture could not place today on a training day"
    plan = selected
    plan["events"] = [
        {"date": (today - timedelta(days=4)).isoformat(), "priority": "B", "label": "Tune-up", "confirmed": True},
        {"date": (today + timedelta(days=3)).isoformat(), "priority": "C", "label": "Club race", "confirmed": True},
        {"date": (today + timedelta(days=10)).isoformat(), "priority": "A", "label": "Main race", "confirmed": True},
    ]
    db.save_planning_checkpoint(build_planning_checkpoint(plan))
    return ps.get_active_plan(db) or {}


def test_week_reader_is_one_server_owned_snapshot_with_truthful_states(tmp_path, monkeypatch):
    db = Database(str(tmp_path / "week-by-week.db"))
    plan = _shift_active_plan_into_past_and_future(db)
    days = ps.plan_days(plan)
    today = datetime.now().date()
    past = next(day for day in days if date.fromisoformat(day["date"]) < today)
    current = next(day for day in days if date.fromisoformat(day["date"]) == today)
    calls: list[dict] = []

    def reconciliation_snapshot(*_args, **kwargs):
        calls.append(kwargs)
        return {
            "has_plan": True,
            "as_of": today.isoformat(),
            "rows": [
                {
                    "session_id": past["sessions"][0]["session_id"],
                    "date": past["date"],
                    "match_status": "matched",
                    "adherence": "exact",
                    "actual_total_tss": past["sessions"][0]["tss"],
                    "actual_duration_minutes": past["sessions"][0]["duration_minutes"],
                    "actual_activity_ids": ["matched-1"],
                },
                {
                    "session_id": current["sessions"][0]["session_id"],
                    "date": current["date"],
                    "match_status": "unmatched",
                    "adherence": "unknown",
                    "actual_total_tss": 0,
                    "actual_duration_minutes": 0,
                    "actual_activity_ids": [],
                },
            ],
            "unplanned_activities": [
                {"activity_id": "free-1", "date": past["date"], "sport": "run", "tss": 19, "duration_minutes": 25, "name": "Extra run"}
            ],
            "data_quality": {"status": "sufficient", "reasons": []},
        }

    monkeypatch.setattr(ps, "reconciliation_at", reconciliation_snapshot)

    payload = ps.week_by_week_plan(db)

    assert calls == [{"weeks": 16, "as_of": today, "include_provider": False}]
    assert payload["state"] == "available"
    assert payload["chart"]["metric"] == "tss"
    assert len([week for week in payload["weeks"] if week["is_current"]]) == 1
    assert {event["priority"] for week in payload["weeks"] for event in week["events"]} == {"A", "B", "C"}

    past_day = next(day for week in payload["weeks"] for day in week["days"] if day["index"] == past["index"])
    assert past_day["state"] == "past"
    assert past_day["actual_tss"] == past["sessions"][0]["tss"]
    assert past_day["unplanned_tss"] == 19
    assert past_day["sessions"][0]["adherence_status"] == "exact"

    current_day = next(day for week in payload["weeks"] for day in week["days"] if day["index"] == current["index"])
    assert current_day["state"] == "current"
    assert current_day["sessions"][0]["adherence_status"] == "in_progress"

    future_week = next(week for week in payload["weeks"] if week["state"] == "future")
    assert future_week["actual_tss"] is None
    assert future_week["completion_percent"] is None
    assert any(
        leaf["session_id"] and leaf["legs"]
        for week in payload["weeks"]
        for day in week["days"]
        for leaf in day["sessions"]
    )


def test_week_reader_no_plan_is_not_a_zero_completion_chart(tmp_path):
    payload = ps.week_by_week_plan(Database(str(tmp_path / "empty.db")))

    assert payload == {"has_plan": False, "state": "no_plan", "weeks": [], "chart": []}


def test_week_reader_route_is_registered():
    main = importlib.import_module("api.main")
    assert "/api/planning/week-by-week" in main.app.openapi()["paths"]


def test_week_reader_ui_is_one_accessible_expandable_reader():
    source = (REPO_ROOT / "web/app/planning/page.tsx").read_text(encoding="utf-8")
    types = (REPO_ROOT / "web/lib/types.ts").read_text(encoding="utf-8")

    assert "WeekByWeekPlan" in source
    assert "/api/planning/week-by-week" in source
    assert "<details" in source and "open={week.is_current}" in source
    assert "role=\"img\"" in source
    assert "Нужно уточнить" in source
    assert "WeekByWeekPlan" in types


def test_week_reader_long_window_keeps_full_ordinals_and_matching_coverage(monkeypatch, tmp_path):
    today = datetime.now().date()
    current_monday = today - timedelta(days=today.weekday())
    start = current_monday - timedelta(weeks=18)
    daily_plan = []
    templates = []
    weekly_summary = []
    for week_index in range(20):
        week_start = start + timedelta(weeks=week_index)
        weekly_summary.append({"week_start": week_start.isoformat(), "phase": "Base", "weekly_tss": 70})
        for day_offset in range(7):
            day = week_start + timedelta(days=day_offset)
            daily_plan.append((datetime.combine(day, datetime.min.time()), 10.0, {"run": 10.0}))
            templates.append({"date": day.isoformat()})
    calls: list[dict] = []
    monkeypatch.setattr(ps, "get_active_plan", lambda _db: {"daily_plan": daily_plan, "session_templates": templates, "weekly_summary": weekly_summary, "events": []})
    monkeypatch.setattr(ps, "reconciliation_at", lambda *_args, **kwargs: calls.append(kwargs) or {"rows": [], "unplanned_activities": [], "data_quality": {}})

    payload = ps.week_by_week_plan(Database(str(tmp_path / "long-window.db")))

    assert calls == [{"weeks": 16, "as_of": today, "include_provider": False}]
    assert len(payload["weeks"]) == 16
    assert payload["weeks"][0]["number"] == 5
    assert payload["weeks"][-1]["number"] == 20


def test_week_reader_chart_scale_includes_actual_above_target(tmp_path, monkeypatch):
    db = Database(str(tmp_path / "high-actual.db"))
    plan = _shift_active_plan_into_past_and_future(db)
    past = next(day for day in ps.plan_days(plan) if date.fromisoformat(day["date"]) < datetime.now().date())
    actual = past["sessions"][0]["tss"] * 100
    monkeypatch.setattr(
        ps,
        "reconciliation_at",
        lambda *_args, **_kwargs: {
            "rows": [{"session_id": past["sessions"][0]["session_id"], "match_status": "matched", "adherence": "exact", "actual_total_tss": actual, "actual_duration_minutes": 60, "actual_activity_ids": ["high"]}],
            "unplanned_activities": [],
            "data_quality": {},
        },
    )

    chart = ps.week_by_week_plan(db)["chart"]

    assert chart["maximum_tss"] >= actual
    assert max(row["actual_percent"] or 0 for row in chart["weeks"]) <= 100


def test_week_chart_marker_and_phase_encoding_are_visible_and_explained():
    source = (REPO_ROOT / "web/app/planning/page.tsx").read_text(encoding="utf-8")

    assert "PHASE_TONES" in source
    assert "phaseLabel" in source
    assert "-top-5" not in source
    assert "top-1" in source
    assert "Фаза" in source
