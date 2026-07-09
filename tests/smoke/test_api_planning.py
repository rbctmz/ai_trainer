"""Smoke tests for Phase 2 planning endpoints.

Contributor-safe: temp SQLite seeded with a little history, no network/AI.
"""
from __future__ import annotations

import importlib
from datetime import datetime, timedelta

import pytest

from data.database import Database


def _seeded_db(tmp_path) -> Database:
    db = Database(str(tmp_path / "plan.db"))
    base = datetime.now()
    rows = []
    for i in range(28):
        rows.append(
            {
                "activity_id": f"s{i}",
                "date": (base - timedelta(days=i)).strftime("%Y-%m-%d"),
                "sport": "cycling" if i % 2 else "running",
                "duration_minutes": 60,
                "distance_km": 25.0,
                "tss": 55.0,
            }
        )
    db.save_activities(rows)
    return db


def test_planning_routes_registered():
    main = importlib.import_module("api.main")
    paths = set(main.app.openapi()["paths"].keys())
    assert {"/api/planning/status", "/api/planning/build"} <= paths


def test_status_shape(tmp_path):
    from api.routers.planning import planning_status

    out = planning_status(db=Database(str(tmp_path / "e.db")))
    assert set(out["metrics"].keys()) == {"ctl", "atl", "tsb", "form"}
    assert out["has_plan"] is False


def _db_with_daily_tss(tmp_path, name: str, daily_tss_oldest_first: list[float]) -> Database:
    # One row per day, oldest first, ending today -- current_status() reads
    # db.get_activities(90), so every sequence here stays well under that.
    db = Database(str(tmp_path / name))
    base = datetime.now()
    n = len(daily_tss_oldest_first)
    rows = [
        {
            "activity_id": f"d{i}",
            "date": (base - timedelta(days=n - 1 - i)).strftime("%Y-%m-%d"),
            "sport": "cycling",
            "duration_minutes": 60,
            "distance_km": 25.0,
            "tss": tss,
        }
        for i, tss in enumerate(daily_tss_oldest_first)
    ]
    db.save_activities(rows)
    return db


def test_status_form_matches_canonical_zone_through_consumer_path(tmp_path):
    # issue #63 review: metrics['form'] is outward-facing (rendered as
    # "Форма" in web/app/planning/page.tsx), so pin it through the actual
    # consumer path (planning_status -> current_status ->
    # BanisterModel.get_current_metrics), not just the internal zone table
    # or BanisterModel in isolation (see tests/smoke/test_banister_tsb_zone.py
    # for that unit-level coverage). Same seeded daily-TSS shapes as that
    # file, confirmed there to land clearly in each of the four zones.
    from api.routers.planning import planning_status
    from models.banister import tsb_zone

    danger_db = _db_with_daily_tss(tmp_path, "danger.db", [50.0] * 60 + [90.0] * 5)
    danger = planning_status(db=danger_db)["metrics"]
    assert tsb_zone(danger["tsb"])["tone"] == "danger"
    assert danger["form"] == "Высокая усталость"

    warning_db = _db_with_daily_tss(tmp_path, "warning.db", [50.0] * 60 + [65.0] * 5)
    warning = planning_status(db=warning_db)["metrics"]
    assert tsb_zone(warning["tsb"])["tone"] == "warning"
    assert warning["form"] == "Накопленная усталость"

    neutral_db = _db_with_daily_tss(tmp_path, "neutral.db", [50.0] * 60 + [20.0] * 4)
    neutral = planning_status(db=neutral_db)["metrics"]
    assert tsb_zone(neutral["tsb"])["tone"] == "neutral"
    assert neutral["form"] == "Стабильная нагрузка"

    success_db = _db_with_daily_tss(tmp_path, "success.db", [55.0] * 60 + [0.0] * 8)
    success = planning_status(db=success_db)["metrics"]
    assert tsb_zone(success["tsb"])["tone"] == "success"
    assert success["form"] == "Свежесть"


def test_build_plan_contract(tmp_path):
    from api.planning_service import build_plan

    db = _seeded_db(tmp_path)
    event = (datetime.now() + timedelta(weeks=9)).strftime("%Y-%m-%d")
    plan = build_plan(
        db,
        goal_type="triathlon",
        distance="olympic",
        event_date=event,
        available_hours=12,
        available_days=["mon", "tue", "wed", "thu", "sat", "sun"],
        persist=False,
    )

    assert plan["goal"]["goal_type"] == "Триатлон"
    assert plan["goal"]["distance"] == "Олимпийка"
    assert plan["goal"]["events"] == [
        {"date": event, "priority": "A", "label": "Триатлон Олимпийка"}
    ]
    assert plan["goal"]["event_date"] == event
    assert plan["goal"]["weeks_to_race"] >= 1
    assert len(plan["weeks"]) == plan["goal"]["weeks_to_race"]
    assert plan["totals"]["total_tss"] > 0
    assert len(plan["forecast"]["points"]) >= 2
    for pt in plan["forecast"]["points"]:
        assert {"date", "ctl", "atl", "tsb"} <= set(pt.keys())


def test_build_plan_applies_active_coach_constraints(tmp_path):
    from api import planning_service as ps
    from models.ai_coach_runtime import create_chat_synthesis_system_prompt

    db = _seeded_db(tmp_path)
    protected_date = (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d")
    db.save_coach_constraint(
        date=protected_date,
        kind="forced_rest",
        source="coach",
        note="Тестовый отдых",
    )

    event = (datetime.now() + timedelta(weeks=9)).strftime("%Y-%m-%d")
    result = ps.build_plan(
        db,
        goal_type="triathlon",
        distance="olympic",
        event_date=event,
        available_hours=12,
        available_days=["mon", "tue", "wed", "thu", "sat", "sun"],
        persist=True,
    )

    assert result["constraint_application"]["applied_count"] == 1
    assert result["constraint_application"]["protected_dates"] == [protected_date]

    active_plan = ps.get_active_plan(db)
    assert active_plan
    assert active_plan["event_date"] == event
    assert active_plan["events"] == [
        {"date": event, "priority": "A", "label": "Триатлон Олимпийка"}
    ]
    latest = db.get_latest_planning_checkpoint()
    assert latest is not None
    assert latest["event_date"] == event
    assert latest["events"] == active_plan["events"]
    assert latest["goal_plan_snapshot"]["event_date"] == event
    prompt = create_chat_synthesis_system_prompt(goal_plan=active_plan)
    assert "ПЛАН И ФАЗА" in prompt
    assert "Текущая фаза" in prompt
    protected_index = next(
        index
        for index, item in enumerate(active_plan["daily_plan"])
        if item[0].strftime("%Y-%m-%d") == protected_date
    )
    assert active_plan["daily_plan"][protected_index][1] == 0
    assert active_plan["session_templates"][protected_index]["session_role"] == "off"
    assert active_plan["session_templates"][protected_index]["protected_by_constraint"] is True
    assert protected_date not in {day["date"] for day in ps.plan_days(active_plan)}


def test_planning_export_and_adjust_routes_registered():
    importlib.import_module("api.main")
    import api.main as main

    paths = set(main.app.openapi()["paths"].keys())
    assert {
        "/api/planning/plan",
        "/api/planning/export/ics",
        "/api/planning/export/workout/{index}",
        "/api/planning/reconciliation",
        "/api/planning/adjust",
    } <= paths


def test_export_and_adjust_active_plan(tmp_path):
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
        persist=True,  # becomes the active plan
    )

    plan = ps.get_active_plan(db)
    assert plan and plan.get("daily_plan")

    days = ps.plan_days(plan)
    assert len(days) > 0

    ics = ps.export_ics(plan)
    assert ics.startswith("BEGIN:VCALENDAR")

    tcx = ps.export_workout(plan, days[0]["index"], "tcx")
    assert tcx["content"].lstrip().startswith("<?xml")
    assert tcx["filename"].endswith(".tcx")

    fit = ps.export_workout(plan, days[0]["index"], "fit_csv")
    assert fit["filename"].endswith(".csv")

    rec = ps.reconciliation(db, weeks=1)
    assert rec["has_plan"] is True
    rows = rec["rows"]
    assert len(rows) >= 1

    for r in rows[:1]:
        r["outcome"] = "skipped"
        r["actual_total_tss"] = 0
    adjusted = ps.apply_adjustment(db, rows=rows, weeks=1, persist=False)
    assert "status" in adjusted["adjustment"]
    assert len(adjusted["weeks"]) >= 1
    assert len(adjusted["forecast"]["points"]) >= 2


def test_apply_adjustment_preserves_active_coach_constraints(tmp_path):
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

    initial_plan = ps.get_active_plan(db)
    assert initial_plan
    today = datetime.now().date()
    protected_index = next(
        index
        for index, item in enumerate(initial_plan["daily_plan"])
        if item[0].date() >= today and float(item[1] or 0) > 0
    )
    protected_date = initial_plan["daily_plan"][protected_index][0].strftime("%Y-%m-%d")
    db.save_coach_constraint(
        date=protected_date,
        kind="sick",
        source="user",
        note="Болею",
    )

    rec = ps.reconciliation(db, weeks=1)
    adjusted = ps.apply_adjustment(db, rows=rec["rows"], weeks=1, persist=True)

    assert adjusted["constraint_application"]["applied_count"] == 1
    assert adjusted["constraint_application"]["protected_dates"] == [protected_date]

    active_plan = ps.get_active_plan(db)
    assert active_plan
    assert active_plan["event_date"] == event
    assert active_plan["daily_plan"][protected_index][1] == 0
    assert active_plan["session_templates"][protected_index]["session_role"] == "off"
    assert active_plan["session_templates"][protected_index]["constraint"]["kind"] == "sick"
    latest = db.get_latest_planning_checkpoint()
    assert latest is not None
    assert latest["event_date"] == event


def test_build_run_goal_maps_distance(tmp_path):
    from api.planning_service import build_plan

    db = _seeded_db(tmp_path)
    event = (datetime.now() + timedelta(weeks=6)).strftime("%Y-%m-%d")
    plan = build_plan(
        db,
        goal_type="run",
        distance="marathon",
        event_date=event,
        available_hours=8,
        available_days=["mon", "wed", "fri", "sun"],
        persist=False,
    )
    assert plan["goal"]["goal_type"] == "Бег"
    assert plan["goal"]["distance"] == "Марафон"


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
