"""Smoke contracts for issue #23 planning target math, demand, and history."""
from __future__ import annotations

import importlib
from datetime import datetime, timedelta

import pytest

from data.database import Database


pytestmark = pytest.mark.smoke


def _seeded_db(tmp_path) -> Database:
    db = Database(str(tmp_path / "planning_target.db"))
    today = datetime.now().date()
    weekly_totals = [80, 120, 160, 200, 240, 280]
    rows = []
    for week_index, weekly_tss in enumerate(weekly_totals):
        week_start = today - timedelta(days=today.weekday() + 7 * (len(weekly_totals) - week_index))
        for day_index in range(4):
            value = weekly_tss / 4.0
            rows.append(
                {
                    "activity_id": f"target-{week_index}-{day_index}",
                    "date": (week_start + timedelta(days=day_index)).strftime("%Y-%m-%d"),
                    "sport": "cycling" if day_index % 2 else "running",
                    "duration_minutes": 60,
                    "distance_km": 20.0,
                    "tss": value,
                }
            )
    db.save_activities(rows)
    return db


def test_planning_target_routes_registered():
    main = importlib.import_module("api.main")
    paths = set(main.app.openapi()["paths"].keys())

    assert {
        "/api/planning/target-preview",
        "/api/planning/demand",
        "/api/planning/history",
    } <= paths


def test_weekly_target_breakdown_contract_uses_recent_median(tmp_path):
    from api import planning_service as ps

    db = _seeded_db(tmp_path)
    preview = ps.target_preview(
        db,
        goal_type="triathlon",
        distance="olympic",
        available_hours=10,
        available_days=["mon", "tue", "wed", "thu", "sat", "sun"],
        demand="moderate",
    )

    row_keys = [row["key"] for row in preview["breakdown"]["rows"]]
    assert row_keys == ["goal_need", "availability_cap", "recent_load", "base_weekly_tss"]
    assert preview["breakdown"]["recent_load"]["method"] == "median"
    assert preview["breakdown"]["recent_load"]["median_weekly_tss"] == 180
    assert preview["breakdown"]["availability"]["weekly_capacity_tss"] > 0
    assert preview["weekly_target"]["base_weekly_tss"] > 0
    assert preview["weekly_target"]["final_target_weekly_tss"] == preview["weekly_target"]["base_weekly_tss"]


def test_demand_setting_roundtrips_and_build_uses_multiplier(tmp_path):
    from api import planning_service as ps

    db = _seeded_db(tmp_path)
    event = (datetime.now() + timedelta(weeks=9)).strftime("%Y-%m-%d")

    saved = ps.set_demand(db, "aggressive")
    assert saved["demand"]["level"] == "aggressive"
    assert ps.get_demand(db)["demand"]["level"] == "aggressive"
    assert ps.current_status(db)["demand"]["level"] == "aggressive"

    moderate = ps.build_plan(
        db,
        goal_type="triathlon",
        distance="olympic",
        event_date=event,
        available_hours=12,
        available_days=["mon", "tue", "wed", "thu", "sat", "sun"],
        demand="moderate",
        persist=False,
    )
    aggressive = ps.build_plan(
        db,
        goal_type="triathlon",
        distance="olympic",
        event_date=event,
        available_hours=12,
        available_days=["mon", "tue", "wed", "thu", "sat", "sun"],
        demand="aggressive",
        persist=False,
    )

    assert moderate["weekly_target"]["demand"]["level"] == "moderate"
    assert aggressive["weekly_target"]["demand"]["level"] == "aggressive"
    assert aggressive["weekly_target"]["target_weekly_tss"] > moderate["weekly_target"]["target_weekly_tss"]


def test_planning_history_lists_adjustment_checkpoints(tmp_path):
    from api import planning_service as ps

    db = _seeded_db(tmp_path)
    event = (datetime.now() + timedelta(weeks=9)).strftime("%Y-%m-%d")
    ps.build_plan(
        db,
        goal_type="triathlon",
        distance="olympic",
        event_date=event,
        available_hours=12,
        available_days=["mon", "tue", "wed", "thu", "sat", "sun"],
        persist=True,
    )

    rec = ps.reconciliation(db, weeks=1)
    rows = rec["rows"]
    assert rows
    rows[0]["outcome"] = "skipped"
    rows[0]["actual_total_tss"] = 0
    ps.apply_adjustment(db, rows=rows, weeks=1, persist=True)

    history = ps.planning_history(db, limit=5)

    assert history["has_history"] is True
    assert history["items"]
    latest = history["items"][0]
    assert latest["type"] in {"reduce", "regenerate", "swap"}
    assert latest["date"]
    assert latest["outcome_note"]
    assert latest["source"] in {"execution_feedback", "execution_adjustment"}
