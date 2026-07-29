"""P1 gates: plan mutations must preserve executable workout truth."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime

import pytest

from data.database import Database
from models.planning_near_term import build_near_term_edit_rows
from tests.smoke.test_api_planning import _seeded_db


def _build_active_plan(db: Database) -> dict:
    from api import planning_service as ps

    ps.build_plan(
        db,
        goal_type="triathlon",
        distance="olympic",
        event_date=None,
        available_hours=10,
        available_days=["mon", "tue", "wed", "thu", "fri", "sat", "sun"],
        planning_mode="training_goal",
        intent="develop",
        horizon_weeks=8,
        events=[],
        persist=True,
    )
    plan = ps.get_active_plan(db)
    assert plan is not None
    return plan


def _downgrade_row(plan: dict, *, excluded_indices: set[int] | None = None) -> dict:
    excluded = excluded_indices or set()
    rows = build_near_term_edit_rows(plan, horizon_days=7)
    row = next(
        item
        for item in rows
        if int(item["index"]) not in excluded
        and item["current_sport"] in {"bike", "run", "swim"}
        and float(item["current_total_tss"]) >= 25
    )
    current_tss = float(row["current_total_tss"])
    return {
        **row,
        "session_role": "recovery",
        "sport": row["current_sport"],
        "total_tss": max(15.0, round(current_tss * 0.6, 1)),
    }


def _apply_confirmed_downgrade(db: Database, plan: dict, row: dict) -> dict:
    from api import planning_service as ps

    latest = db.get_latest_planning_checkpoint()
    assert latest is not None
    ps.apply_recovery_replan(
        db,
        {
            "base_checkpoint_id": latest["id"],
            "draft_rows": [row],
            "horizon_days": 7,
            "post_edit_strategy": "protect_recovery",
            "selected_conflict": {"kind": "readiness_conflict"},
        },
        persist=True,
    )
    updated = ps.get_active_plan(db)
    assert updated is not None
    return updated


def _primary_for_index(plan: dict, index: int) -> dict:
    sessions = list(plan["session_templates"][index].get("sessions") or [])
    assert sessions
    return sessions[0]


def test_confirmed_recovery_downgrade_remains_materialized(tmp_path) -> None:
    db = _seeded_db(tmp_path)
    plan = _build_active_plan(db)
    row = _downgrade_row(plan)

    updated = _apply_confirmed_downgrade(db, plan, row)
    session = _primary_for_index(updated, int(row["index"]))

    assert session["materialization_status"] == "materialized"
    assert session["materialized_steps"]
    assert not str(session.get("template_key") or "").startswith("manual:")
    assert sum(int(step["duration_seconds"]) for step in session["materialized_steps"]) == (
        int(session["duration_minutes"]) * 60
    )


def test_repeated_recovery_downgrades_never_accumulate_manual_stubs(tmp_path) -> None:
    db = _seeded_db(tmp_path)
    plan = _build_active_plan(db)
    first = _downgrade_row(plan)
    plan = _apply_confirmed_downgrade(db, plan, first)
    second = _downgrade_row(plan, excluded_indices={int(first["index"])})
    plan = _apply_confirmed_downgrade(db, plan, second)

    for index in (int(first["index"]), int(second["index"])):
        for session in plan["session_templates"][index].get("sessions") or []:
            assert session["materialization_status"] == "materialized"
            assert session["materialized_steps"]
            assert not str(session.get("template_key") or "").startswith("manual:")


def test_recovery_materialization_drives_export_and_delivery_duration(
    tmp_path,
    monkeypatch,
) -> None:
    from api import planning_service as ps
    from models.intervals_workout_delivery import build_delivery_events

    db = _seeded_db(tmp_path)
    plan = _build_active_plan(db)
    row = _downgrade_row(plan)
    plan = _apply_confirmed_downgrade(db, plan, row)
    index = int(row["index"])
    template = plan["session_templates"][index]
    session = _primary_for_index(plan, index)
    expected_steps = deepcopy(session["materialized_steps"])
    expected_seconds = int(session["duration_minutes"]) * 60
    captured: dict = {}

    def capture_tcx(name, sport, steps, created=None):
        captured.update({"name": name, "sport": sport, "steps": deepcopy(steps)})
        return "tcx"

    monkeypatch.setattr(ps, "generate_tcx_workout", capture_tcx)
    ps.export_workout(
        plan,
        index,
        "tcx",
        session_id=str(session["session_id"]),
    )
    events = build_delivery_events(plan, [str(template["date"])[:10]])
    delivered = next(
        event
        for event in events
        if event["external_id"] == f"ai_trainer:{session['session_id']}"
    )

    assert captured["steps"] == expected_steps
    assert delivered["moving_time"] == expected_seconds


def _multi_session_plan() -> dict:
    bike_steps = [
        {
            "index": 0,
            "name": "Bike endurance",
            "intensity": "moderate",
            "duration_seconds": 2160,
            "tss": 36.0,
            "target": {"type": "power", "low": 100, "high": 120},
        }
    ]
    swim_steps = [
        {
            "index": 0,
            "name": "Swim endurance",
            "intensity": "moderate",
            "duration_seconds": 1620,
            "tss": 24.0,
            "target": {"type": "relative_rpe", "low": 5, "high": 6},
        }
    ]
    sessions = [
        {
            "session_id": "ats_bike_leaf",
            "sport": "bike",
            "sport_label": "вело",
            "session_role": "easy",
            "session_focus": "Bike endurance",
            "duration_minutes": 36,
            "total_tss": 36.0,
            "template_key": "bike_aerobic_endurance",
            "template_name": "Bike endurance",
            "export_name": "Bike endurance",
            "materialization_status": "materialized",
            "materialized_steps": bike_steps,
        },
        {
            "session_id": "ats_swim_leaf",
            "sport": "swim",
            "sport_label": "плавание",
            "session_role": "easy",
            "session_focus": "Swim endurance",
            "duration_minutes": 27,
            "total_tss": 24.0,
            "template_key": "swim_aerobic_endurance",
            "template_name": "Swim endurance",
            "export_name": "Swim endurance",
            "materialization_status": "materialized",
            "materialized_steps": swim_steps,
        },
    ]
    return {
        "goal_type": "Триатлон",
        "distance": "Олимпийка",
        "daily_plan": [
            (
                datetime(2026, 8, 3),
                60.0,
                {"bike": 36.0, "run": 0.0, "swim": 24.0},
            )
        ],
        "session_templates": [
            {
                "date": "2026-08-03",
                "phase": "Base",
                "kind": "single",
                "sport": "bike",
                "sport_label": "вело",
                "session_role": "easy",
                "session_focus": "Bike endurance",
                "duration_minutes": 36,
                "total_tss": 60.0,
                "template_key": "bike_aerobic_endurance",
                "template_name": "Bike endurance",
                "export_name": "Bike endurance",
                "materialization_status": "materialized",
                "materialized_steps": bike_steps,
                "sessions": sessions,
            }
        ],
        "weekly_tss_plan": [60],
        "weekly_summary": [],
        "constraint_summary": {},
    }


def test_plan_days_exposes_every_leaf_and_each_leaf_exports_independently(
    monkeypatch,
) -> None:
    from api import planning_service as ps

    plan = _multi_session_plan()
    day = ps.plan_days(plan)[0]
    assert [session["session_id"] for session in day["sessions"]] == [
        "ats_bike_leaf",
        "ats_swim_leaf",
    ]

    captured: dict = {}

    def capture_tcx(name, sport, steps, created=None):
        captured.update({"name": name, "sport": sport, "steps": deepcopy(steps)})
        return "tcx"

    monkeypatch.setattr(ps, "generate_tcx_workout", capture_tcx)
    ps.export_workout(plan, 0, "tcx", session_id="ats_swim_leaf")

    assert captured["name"] == "Swim endurance"
    assert captured["sport"] == "swim"
    assert captured["steps"][0]["duration_seconds"] == 1620


def _broken_manual_plan() -> dict:
    session = {
        "session_id": "ats_broken_manual",
        "sport": "bike",
        "sport_label": "вело",
        "session_role": "easy",
        "session_focus": "Легкая • вело",
        "duration_minutes": 80,
        "total_tss": 40.0,
        "template_key": "manual:base:easy:bike",
        "export_name": "Легкая • вело",
    }
    return {
        "goal_type": "Триатлон",
        "distance": "Олимпийка",
        "daily_plan": [
            (
                datetime(2026, 8, 1),
                40.0,
                {"bike": 40.0, "run": 0.0, "swim": 0.0},
            )
        ],
        "session_templates": [
            {
                "date": "2026-08-01",
                "phase": "Base",
                "kind": "single",
                **session,
                "sessions": [session],
            }
        ],
        "weekly_tss_plan": [40],
        "weekly_summary": [],
        "constraint_summary": {},
    }


def test_modern_manual_placeholder_fails_closed_before_export_or_delivery() -> None:
    from api import planning_service as ps
    from models.intervals_workout_delivery import build_delivery_events

    plan = _broken_manual_plan()

    with pytest.raises(ValueError, match="not executable"):
        ps.export_workout(plan, 0, "tcx")
    with pytest.raises(ValueError, match="not executable"):
        build_delivery_events(plan, ["2026-08-01"])


def test_repair_is_dry_run_first_append_only_and_idempotent(tmp_path) -> None:
    from api import planning_service as ps
    from models.planning_checkpoints import build_planning_checkpoint

    db = Database(str(tmp_path / "repair.db"))
    broken = _broken_manual_plan()
    base = db.save_planning_checkpoint(build_planning_checkpoint(broken))
    parent_before = deepcopy(db.get_planning_checkpoint(base["id"]))

    preview = ps.repair_active_plan_materialization(db, persist=False)
    assert preview["changed_dates"] == ["2026-08-01"]
    assert preview["plan_id"] is None
    assert db.get_latest_planning_checkpoint()["id"] == base["id"]

    applied = ps.repair_active_plan_materialization(db, persist=True)
    assert applied["changed_dates"] == ["2026-08-01"]
    assert applied["plan_id"] is not None
    repaired = db.get_latest_planning_checkpoint()
    assert repaired["checkpoint_parent_id"] == base["id"]
    assert repaired["checkpoint_source"] == "materialization_repair"
    assert db.get_planning_checkpoint(base["id"]) == parent_before

    repeated = ps.repair_active_plan_materialization(db, persist=True)
    assert repeated["changed_dates"] == []
    assert repeated["plan_id"] is None
    assert db.get_latest_planning_checkpoint()["id"] == repaired["id"]
