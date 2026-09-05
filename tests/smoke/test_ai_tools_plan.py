"""Smoke tests: get_active_plan / get_upcoming_workouts see a seeded plan."""
from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from data.database import Database
from models.ai_tools import AITools
from models.planning_checkpoints import build_planning_checkpoint


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_goal_plan(weeks_ago: int = 0) -> dict:
    """Build a minimal but structurally valid goal plan for seeding.

    weeks_ago shifts the plan start back in time, so today lands in week
    (weeks_ago + 1) of the plan; negative values start the plan in the future.
    """
    today = date.today()
    start_week = today - timedelta(days=today.weekday()) - timedelta(weeks=weeks_ago)

    weekly_tss_plan = [300, 320, 350, 280, 360, 380, 300, 200]
    phases = ["base", "base", "base", "base", "build", "build", "taper", "taper"]

    daily_plan = []
    templates = []
    for week_idx in range(len(weekly_tss_plan)):
        for day_offset in [1, 3, 5]:  # Mon/Wed/Fri pattern
            dt = datetime.combine(
                start_week + timedelta(weeks=week_idx, days=day_offset),
                datetime.min.time(),
            )
            tss = int(weekly_tss_plan[week_idx] / 3)
            daily_plan.append((dt, tss, {"bike": tss}))
            templates.append({
                "sport": "bike",
                "sport_label": "Вело",
                "session_focus": "Аэробная база",
                "export_name": f"Сессия {week_idx * 3 + day_offset}",
                "phase": phases[week_idx],
                "session_role": "easy",
            })

    weekly_summary = [
        {
            "week_start": start_week + timedelta(weeks=i),
            "phase": phases[i],
            "weekly_tss": weekly_tss_plan[i],
            "capacity_tss": weekly_tss_plan[i],
            "adjustment_note": "—",
        }
        for i in range(len(weekly_tss_plan))
    ]

    event_date = start_week + timedelta(weeks=len(weekly_tss_plan))

    return {
        "goal_type": "Триатлон",
        "distance": "Олимпийка",
        "event_date": event_date.isoformat(),
        "events": [
            {
                "date": event_date.isoformat(),
                "priority": "A",
                "label": "Триатлон Олимпийка",
            }
        ],
        "weeks_to_race": len(weekly_tss_plan),
        "start_week": start_week,
        "weekly_tss_plan": weekly_tss_plan,
        "base_weekly_tss_plan": weekly_tss_plan,
        "phases": phases,
        "daily_plan": daily_plan,
        "session_templates": templates,
        "weekly_summary": weekly_summary,
        "constraint_summary": {
            "load_state": "balanced",
            "available_day_indices": [0, 1, 2, 3, 4, 5, 6],
            "notes": [],
        },
        "planner_mix": None,
        "planner_weights": None,
        "plan_revision": datetime.now().isoformat(),
        "near_term_edit_version": 0,
        "near_term_edit_rollback_target_checkpoint_id": None,
    }


def _seed_plan(db: Database, weeks_ago: int = 0) -> None:
    checkpoint = build_planning_checkpoint(_make_goal_plan(weeks_ago))
    db.save_planning_checkpoint(checkpoint)


@pytest.fixture()
def tools_with_plan(tmp_path):
    db = Database(str(tmp_path / "plan.db"))
    _seed_plan(db)
    return AITools(db)


@pytest.fixture()
def tools_no_plan(tmp_path):
    db = Database(str(tmp_path / "empty.db"))
    return AITools(db)


# ---------------------------------------------------------------------------
# get_active_plan tests
# ---------------------------------------------------------------------------

def test_get_active_plan_returns_plan(tools_with_plan: AITools) -> None:
    result = tools_with_plan.get_active_plan()
    assert result["has_plan"] is True
    goal = result["goal"]
    assert goal["goal_type"] == "Триатлон"
    assert goal["distance"] == "Олимпийка"
    assert goal["weeks_to_race"] == 8
    assert result["events"] == [
        {
            "date": goal["event_date"],
            "priority": "A",
            "label": "Триатлон Олимпийка",
        }
    ]
    assert result["totals"]["total_weeks"] == 8
    assert result["totals"]["peak_tss"] == 380
    assert result["totals"]["total_tss"] == sum([300, 320, 350, 280, 360, 380, 300, 200])
    assert "base" in result["phases"]
    assert "build" in result["phases"]
    assert "taper" in result["phases"]
    assert len(result["weekly_tss_plan"]) == 8


def test_get_active_plan_current_week_first_week(tools_with_plan: AITools) -> None:
    """Plan started this week: current week is week 1 with the week-1 TSS."""
    result = tools_with_plan.get_active_plan()

    current = result["current_week"]
    assert current is not None
    assert current["index"] == 1
    assert current["weekly_tss"] == 300
    assert current["phase"] == "base"
    week_start = date.fromisoformat(current["week_start"])
    assert week_start <= date.today() <= week_start + timedelta(days=6)

    timeline = result["timeline"]
    assert timeline["status"] == "active"
    assert timeline["today"] == date.today().isoformat()
    assert timeline["weeks_elapsed"] == 0
    assert timeline["weeks_remaining"] == 8
    assert result["goal"]["weeks_to_race"] == 8

    preview = result["weeks_preview"]
    assert [w["is_current"] for w in preview].count(True) == 1
    assert preview[0]["is_current"] is True
    assert "week_end" in preview[0]


def test_get_active_plan_recomputes_week_after_start(tmp_path) -> None:
    """Plan started a week ago: current week is 2 and weeks_to_race shrinks."""
    db = Database(str(tmp_path / "plan_w2.db"))
    _seed_plan(db, weeks_ago=1)
    result = AITools(db).get_active_plan()

    current = result["current_week"]
    assert current is not None
    assert current["index"] == 2
    assert current["weekly_tss"] == 320

    timeline = result["timeline"]
    assert timeline["weeks_elapsed"] == 1
    assert timeline["weeks_remaining"] == 7
    # weeks_to_race is recomputed from today, not the stale build-time value (8)
    assert result["goal"]["weeks_to_race"] == 7
    assert result["totals"]["total_weeks"] == 8

    assert result["weeks_preview"][1]["is_current"] is True


def test_get_active_plan_legacy_checkpoint_without_event_date_uses_end_fallback(tmp_path) -> None:
    """Old checkpoints had no real race date: keep weeks math, but do not invent goal.event_date."""
    db = Database(str(tmp_path / "plan_legacy_no_event_date.db"))
    goal_plan = _make_goal_plan()
    goal_plan.pop("event_date", None)
    goal_plan.pop("events", None)
    db.save_planning_checkpoint(build_planning_checkpoint(goal_plan))

    result = AITools(db).get_active_plan()

    assert result["has_plan"] is True
    assert result["goal"]["event_date"] == ""
    assert result["goal"]["weeks_to_race"] == 8
    assert result["timeline"]["weeks_remaining"] == 8


def test_get_active_plan_not_started(tmp_path) -> None:
    """Plan starting next week: no current week, status not_started."""
    db = Database(str(tmp_path / "plan_future.db"))
    _seed_plan(db, weeks_ago=-1)
    result = AITools(db).get_active_plan()

    assert result["current_week"] is None
    assert result["timeline"]["status"] == "not_started"
    assert result["timeline"]["weeks_elapsed"] == 0
    assert result["goal"]["weeks_to_race"] == 9


def test_get_active_plan_completed(tmp_path) -> None:
    """Plan fully in the past: status completed, zero weeks remaining."""
    db = Database(str(tmp_path / "plan_done.db"))
    _seed_plan(db, weeks_ago=10)
    result = AITools(db).get_active_plan()

    assert result["current_week"] is None
    assert result["timeline"]["status"] == "completed"
    assert result["goal"]["weeks_to_race"] == 0
    assert result["timeline"]["weeks_remaining"] == 0


def test_get_active_plan_no_plan(tools_no_plan: AITools) -> None:
    result = tools_no_plan.get_active_plan()
    assert result["has_plan"] is False
    assert "message" in result


def test_get_active_plan_via_execute_tool(tools_with_plan: AITools) -> None:
    result = tools_with_plan.execute_tool("get_active_plan")
    assert result["success"] is True
    assert result["result"]["has_plan"] is True


# ---------------------------------------------------------------------------
# get_upcoming_workouts tests
# ---------------------------------------------------------------------------

def test_get_upcoming_workouts_returns_sessions(tools_with_plan: AITools) -> None:
    result = tools_with_plan.get_upcoming_workouts(days=7)
    assert result["has_plan"] is True
    sessions = result["sessions"]
    assert len(sessions) >= 1
    for s in sessions:
        assert "date" in s
        assert "sport" in s
        assert "tss" in s
        assert s["tss"] > 0
        assert s["completion_status"] == "planned"
        assert s["reconciliation_status"] == "unmatched"


def _seed_today_session(
    db: Database,
    *,
    session_id: str = "ats_today",
    replaces_session_id: str | None = None,
) -> dict:
    plan = _make_goal_plan()
    plan["daily_plan"] = [
        (
            datetime.combine(date.today(), datetime.min.time()),
            44,
            {"run": 44},
        )
    ]
    plan["session_templates"] = [
        {
            "date": date.today().isoformat(),
            "phase": "build",
            "sessions": [
                {
                    "session_id": session_id,
                    "replaces_session_id": replaces_session_id,
                    "sport": "run",
                    "sport_label": "бег",
                    "total_tss": 44,
                    "export_name": "Aerobic Endurance Run",
                    "kind": "single",
                }
            ],
        }
    ]
    return db.save_planning_checkpoint(build_planning_checkpoint(plan))


def _seed_today_match(
    db: Database,
    checkpoint: dict,
    *,
    session_id: str = "ats_today",
    match_status: str = "matched",
) -> None:
    if match_status == "matched":
        db.save_activities(
            [
                {
                    "activity_id": 101,
                    "date": date.today().isoformat(),
                    "sport": "running",
                    "duration_minutes": 50.1,
                    "tss": 57.3,
                    "activity_name": "Completed run",
                }
            ]
        )
    db.save_plan_actual_match(
        {
            "fingerprint": f"{session_id}:{match_status}",
            "target_key": f"session:{session_id}",
            "session_id": session_id,
            "base_checkpoint_id": checkpoint["id"],
            "session_date": date.today().isoformat(),
            "match_status": match_status,
            "match_method": "user_confirmed" if match_status == "matched" else "auto",
            "confidence": 1.0 if match_status == "matched" else 0.5,
            "planned_snapshot": {"sport": "run", "tss": 44},
            "actual_activity_ids": ["101"] if match_status == "matched" else [],
            "actual_snapshot": (
                {"sport": "running", "tss": 57.3, "duration_minutes": 50.1}
                if match_status == "matched"
                else {}
            ),
            "evidence": ["test fixture"],
            "rule_version": "test-v1",
        }
    )


def test_get_upcoming_workouts_marks_matched_session_completed(tmp_path) -> None:
    db = Database(str(tmp_path / "matched.db"))
    checkpoint = _seed_today_session(db)
    _seed_today_match(db, checkpoint)

    session = AITools(db).get_upcoming_workouts(days=0)["sessions"][0]

    assert session["completion_status"] == "completed"
    assert session["reconciliation_status"] == "matched"
    assert session["actual"] == {
        "activity_ids": ["101"],
        "tss": 57.3,
        "duration_minutes": 50.1,
        "sport": "run",
    }


def test_get_upcoming_workouts_does_not_mark_ambiguous_session_completed(tmp_path) -> None:
    db = Database(str(tmp_path / "ambiguous.db"))
    _seed_today_session(db)
    db.save_activities(
        [
            {
                "activity_id": activity_id,
                "date": date.today().isoformat(),
                "sport": "running",
                "duration_minutes": 30,
                "tss": 25,
                "activity_name": f"Run {activity_id}",
            }
            for activity_id in (201, 202)
        ]
    )

    session = AITools(db).get_upcoming_workouts(days=0)["sessions"][0]

    assert session["completion_status"] == "planned"
    assert session["reconciliation_status"] == "ambiguous"
    assert "actual" not in session


def test_get_upcoming_workouts_uses_automatic_reconciliation(tmp_path) -> None:
    db = Database(str(tmp_path / "automatic.db"))
    _seed_today_session(db)
    db.save_activities(
        [
            {
                "activity_id": 301,
                "date": date.today().isoformat(),
                "sport": "running",
                "duration_minutes": 48,
                "tss": 46,
                "activity_name": "Synced run",
            }
        ]
    )

    session = AITools(db).get_upcoming_workouts(days=0)["sessions"][0]

    assert session["completion_status"] == "completed"
    assert session["reconciliation_status"] == "matched"
    assert session["match_method"] == "date_sport_heuristic"
    assert session["actual"]["activity_ids"] == ["301"]


def test_get_upcoming_workouts_inherits_confirmed_predecessor_match(tmp_path) -> None:
    db = Database(str(tmp_path / "replacement.db"))
    checkpoint = _seed_today_session(
        db,
        session_id="ats_current",
        replaces_session_id="ats_previous",
    )
    _seed_today_match(db, checkpoint, session_id="ats_previous")

    session = AITools(db).get_upcoming_workouts(days=0)["sessions"][0]

    assert session["session_id"] == "ats_current"
    assert session["completion_status"] == "completed"
    assert session["reconciliation_status"] == "matched"
    assert session["match_method"] == "user_confirmed"
    assert session["actual"]["activity_ids"] == ["101"]


def test_get_upcoming_workouts_no_plan(tools_no_plan: AITools) -> None:
    result = tools_no_plan.get_upcoming_workouts()
    assert result["has_plan"] is False


def test_get_upcoming_workouts_via_execute_tool(tools_with_plan: AITools) -> None:
    result = tools_with_plan.execute_tool("get_upcoming_workouts", days=7)
    assert result["success"] is True
    assert result["result"]["has_plan"] is True


# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------

def test_tools_registered_in_registry(tools_with_plan: AITools) -> None:
    available = tools_with_plan.get_available_tools()
    assert "get_active_plan" in available
    assert "get_upcoming_workouts" in available
    assert "get_active_plan" in tools_with_plan.tools
    assert "get_upcoming_workouts" in tools_with_plan.tools
