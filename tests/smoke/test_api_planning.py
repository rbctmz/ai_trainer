"""Smoke tests for Phase 2 planning endpoints.

Contributor-safe: temp SQLite seeded with a little history, no network/AI.
"""
from __future__ import annotations

import importlib
from datetime import date, datetime, timedelta

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
    assert {"/api/planning/status", "/api/planning/build", "/api/planning/events"} <= paths


def test_training_goal_builds_rolling_horizon_without_race(tmp_path):
    from api.planning_service import build_plan

    plan = build_plan(
        _seeded_db(tmp_path),
        goal_type="triathlon",
        distance="olympic",
        event_date=None,
        planning_mode="training_goal",
        intent="maintain",
        horizon_weeks=8,
        events=[],
        available_hours=10,
        persist=False,
    )

    assert plan["planning_mode"] == "training_goal"
    assert plan["goal"]["event_date"] == ""
    assert plan["goal"]["macrocycle_event_date"] == ""
    assert plan["goal"]["weeks_to_race"] is None
    assert len(plan["weeks"]) == 8
    assert {week["phase"] for week in plan["weeks"]} <= {"Maintenance", "Recovery"}


def test_later_a_anchors_plan_while_earlier_b_is_local_overlay(tmp_path):
    from api import planning_service as ps

    today = datetime.now().date()
    b_date = today + timedelta(days=13)
    a_date = today + timedelta(weeks=12)
    result = ps.build_plan(
        _seeded_db(tmp_path),
        goal_type="triathlon",
        distance="olympic",
        event_date=None,
        events=[
            {"date": b_date.isoformat(), "priority": "B", "label": "Minsk", "confirmed": True},
            {"date": a_date.isoformat(), "priority": "A", "label": "Sirius", "confirmed": True},
        ],
        planning_mode="event_goal",
        available_hours=12,
        available_days=["mon", "tue", "wed", "thu", "fri", "sat", "sun"],
        persist=True,
    )

    assert result["goal"]["macrocycle_event_date"] == a_date.isoformat()
    assert [week["phase"] for week in result["weeks"]][-2:] == ["Taper", "Race Week"]


def test_build_persists_catalog_prescriptions_and_one_brick_per_eligible_week(tmp_path):
    from api import planning_service as ps
    from models.workout_catalog import CATALOG_VERSION

    # A clean profile keeps the explicit load-state guard balanced; the shared
    # seeded fixture intentionally creates deep fatigue, where bricks are banned.
    db = Database(str(tmp_path / "catalog-plan.db"))
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

    active = ps.get_active_plan(db)
    assert active is not None
    assert active["catalog_version"] == CATALOG_VERSION
    materialized = [
        item
        for item in active["session_templates"]
        if item.get("materialization_status") == "materialized"
    ]
    assert materialized
    assert all(item.get("definition_snapshot") for item in materialized)
    assert all(item.get("prescription_fingerprint") for item in materialized)

    eligible_week_indices = {
        index
        for index, week in enumerate(active["weekly_summary"])
        if week.get("phase") in {"Build", "Peak"}
    }
    bricks = [
        item
        for item in active["session_templates"]
        if item.get("kind") == "composite"
    ]
    assert {int(item["week_index"]) for item in bricks} == eligible_week_indices
    assert len({int(item["week_index"]) for item in bricks}) == len(bricks)
    assert all([leg["sport"] for leg in item["legs"]] == ["bike", "run"] for item in bricks)

    public_days = ps.plan_days(active)
    catalog_day = next(item for item in public_days if item.get("template_key"))
    assert catalog_day["catalog_version"] == CATALOG_VERSION
    assert catalog_day["template_name"]
    assert catalog_day["stimulus"]
    assert catalog_day["fatigue_cost"]
    assert catalog_day["steps"] or catalog_day["legs"]


def test_b_overlay_persists_protected_days_and_resumes(tmp_path):
    from api import planning_service as ps

    db = _seeded_db(tmp_path)
    today = datetime.now().date()
    b_date = today + timedelta(days=13)
    ps.build_plan(
        db,
        goal_type="triathlon",
        distance="olympic",
        event_date=None,
        events=[{"date": b_date.isoformat(), "priority": "B", "label": "Minsk", "confirmed": True}],
        planning_mode="training_goal",
        intent="develop",
        horizon_weeks=8,
        available_hours=12,
        available_days=["mon", "tue", "wed", "thu", "fri", "sat", "sun"],
        persist=True,
    )
    active = ps.get_active_plan(db)
    assert active is not None
    by_date = {row[0].date().isoformat(): row for row in active["daily_plan"]}
    assert by_date[b_date.isoformat()][1] == 0
    assert by_date[(b_date + timedelta(days=1)).isoformat()][1] == 0
    assert by_date[(b_date + timedelta(days=2)).isoformat()][1] == 0
    assert by_date[(b_date + timedelta(days=3)).isoformat()][1] > 0
    assert active["overlay_rule_version"] == "race-overlay-v1"
    assert b_date.isoformat() in active["protected_dates"]


def test_api_build_requires_preview_before_confirm(tmp_path):
    from api.routers.planning import BuildRequest, planning_build

    db = _seeded_db(tmp_path)
    request = BuildRequest(
        goal_type="triathlon",
        distance="olympic",
        event_date=None,
        planning_mode="training_goal",
        intent="develop",
        horizon_weeks=4,
        available_hours=10,
        persist=False,
    )
    preview = planning_build(request, db=db)
    assert preview["plan_id"] is None
    assert preview["confirmation_required"] is True
    assert preview["preview"]["base_checkpoint_id"] == 0
    assert db.get_latest_planning_checkpoint() is None

    confirmed_request = request.model_copy(
        update={
            "persist": True,
            "confirm": True,
            "base_checkpoint_id": preview["preview"]["base_checkpoint_id"],
        }
    )
    confirmed = planning_build(confirmed_request, db=db)
    assert confirmed["plan_id"]
    assert db.get_latest_planning_checkpoint() is not None


def test_preview_is_read_only_and_stale_confirmation_is_rejected(tmp_path):
    from fastapi import HTTPException

    from api.planning_service import PLANNING_DEMAND_SETTING_KEY, build_plan
    from api.routers.planning import BuildRequest, planning_build

    db = _seeded_db(tmp_path)
    request = BuildRequest(
        goal_type="triathlon",
        distance="olympic",
        planning_mode="training_goal",
        intent="develop",
        horizon_weeks=4,
        available_hours=10,
        demand="aggressive",
        persist=False,
    )

    preview = planning_build(request, db=db)
    assert preview["preview"]["base_checkpoint_id"] == 0
    assert db.get_user_setting(PLANNING_DEMAND_SETTING_KEY, None) is None
    assert db.get_latest_planning_checkpoint() is None

    # Another actor appends a checkpoint after the preview was shown.
    build_plan(
        db,
        goal_type="triathlon",
        distance="olympic",
        event_date=None,
        planning_mode="training_goal",
        intent="maintain",
        horizon_weeks=4,
        available_hours=8,
        persist=True,
    )

    stale_confirmation = request.model_copy(
        update={
            "persist": True,
            "confirm": True,
            "base_checkpoint_id": preview["preview"]["base_checkpoint_id"],
        }
    )
    with pytest.raises(HTTPException) as exc_info:
        planning_build(stale_confirmation, db=db)
    assert exc_info.value.status_code == 409


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
        {
            "date": event,
            "priority": "A",
            "label": "Триатлон Олимпийка",
            "source": "user",
            "priority_provenance": "explicit_user",
            "confirmed": True,
            "requires_confirmation": False,
        }
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
        {
            "date": event,
            "priority": "A",
            "label": "Триатлон Олимпийка",
            "source": "user",
            "priority_provenance": "explicit_user",
            "confirmed": True,
            "requires_confirmation": False,
        }
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
        "/api/planning/reconciliation/matches",
        "/api/planning/rebalance/preview",
        "/api/planning/rebalance/confirm",
        "/api/planning/adjust",
    } <= paths


def _reconciliation_db(tmp_path) -> tuple[Database, dict]:
    from models.planning_checkpoints import build_planning_checkpoint
    from models.session_identity import ensure_session_identities
    from tests.smoke.test_plan_actual_reconciliation import _goal_plan

    db = Database(str(tmp_path / "reconciliation.db"))
    plan = ensure_session_identities(_goal_plan())
    db.save_planning_checkpoint(build_planning_checkpoint(plan))
    actuals = [
        ("2026-07-07", "cycling", 40.0),
        ("2026-07-08", "cycling", 42.0),
        ("2026-07-09", "running", 45.0),
        ("2026-07-10", "swimming", 65.0),
        ("2026-07-11", "cycling", 80.0),
    ]
    db.save_activities(
        [
            {
                "activity_id": f"actual-{day}",
                "date": day,
                "started_at_utc": f"{day}T06:00:00Z",
                "sport": sport,
                "duration_minutes": 60,
                "tss": tss,
            }
            for day, sport, tss in actuals
        ]
    )
    return db, plan


def test_reconciliation_preview_confirm_is_future_only_and_stale_safe(tmp_path):
    from api import planning_service as ps

    db, base_plan = _reconciliation_db(tmp_path)
    preview_result = ps.preview_weekly_rebalance(
        db,
        as_of="2026-07-13",
        weeks=1,
        include_provider=False,
    )

    reconciliation = preview_result["reconciliation"]
    preview = preview_result["preview"]
    assert reconciliation["base_checkpoint_id"] == 1
    assert reconciliation["data_quality"]["status"] == "sufficient"
    assert preview["status"] == "proposal"
    assert all(item["date"] > "2026-07-13" for item in preview["changes"])

    confirmed = ps.confirm_weekly_rebalance(
        db,
        base_checkpoint_id=1,
        preview_fingerprint=preview["preview_fingerprint"],
        as_of="2026-07-13",
        weeks=1,
        include_provider=False,
    )
    assert confirmed["applied_checkpoint_id"] == 2
    latest = db.get_latest_planning_checkpoint()
    assert latest["checkpoint_source"] == "weekly_rebalance"
    active = ps.get_active_plan(db)
    for index, item in enumerate(base_plan["daily_plan"]):
        if item[0].date().isoformat() <= "2026-07-13":
            assert active["daily_plan"][index] == item
            assert active["session_templates"][index] == base_plan["session_templates"][index]

    stale_preview = ps.preview_weekly_rebalance(
        db,
        as_of="2026-07-13",
        weeks=1,
        include_provider=False,
    )["preview"]
    db.save_planning_checkpoint(latest)
    with pytest.raises(ps.StalePlanningCheckpointError):
        ps.confirm_weekly_rebalance(
            db,
            base_checkpoint_id=2,
            preview_fingerprint=stale_preview["preview_fingerprint"],
            as_of="2026-07-13",
            weeks=1,
            include_provider=False,
        )
    assert db.get_latest_planning_checkpoint()["id"] == 3


def test_provider_failure_blocks_rebalance_without_hiding_local_evidence(tmp_path, monkeypatch):
    from api import planning_service as ps

    db, _plan = _reconciliation_db(tmp_path)
    monkeypatch.setattr(
        ps,
        "_provider_reconciliation_evidence",
        lambda *_args, **_kwargs: ([], [], {"status": "unavailable", "error": "temporary"}),
    )

    result = ps.preview_weekly_rebalance(db, as_of="2026-07-13", weeks=1)

    assert result["reconciliation"]["rows"]
    assert result["reconciliation"]["provider"]["status"] == "unavailable"
    assert result["reconciliation"]["data_quality"]["status"] == "data_gap"
    assert "provider_unavailable" in result["reconciliation"]["data_quality"]["reasons"]
    assert result["preview"]["status"] == "no_change"
    assert result["preview"]["reason"] == "data_gap"


def test_user_match_correction_appends_ledger_and_changes_reconciliation(
    tmp_path, monkeypatch
):
    from api import planning_service as ps
    from services import recovery_analytics

    db, plan = _reconciliation_db(tmp_path)
    refresh_calls = []
    monkeypatch.setattr(
        recovery_analytics,
        "refresh_recovery_episodes_best_effort",
        lambda _db, *, as_of=None: refresh_calls.append(as_of) or {"created": 0},
    )
    target = next(item for item in plan["session_templates"] if item["date"] == "2026-07-09")
    db.save_activities(
        [
            {
                "activity_id": "cross-sport",
                "date": "2026-07-09",
                "started_at_utc": "2026-07-09T18:00:00Z",
                "sport": "cycling",
                "duration_minutes": 40,
                "tss": 20.0,
            }
        ]
    )

    saved = ps.record_plan_actual_match(
        db,
        base_checkpoint_id=1,
        session_id=target["session_id"],
        activity_ids=["cross-sport"],
        actual_role="easy",
        action="confirm",
    )
    assert saved["match_method"] == "user_confirmed"
    assert saved["revision"] == 1
    assert refresh_calls == [date.today()]

    result = ps.reconciliation_at(
        db,
        as_of="2026-07-13",
        weeks=1,
        include_provider=False,
    )
    row = next(item for item in result["rows"] if item["session_id"] == target["session_id"])
    assert row["match_method"] == "user_confirmed"
    assert row["actual_activity_ids"] == ["cross-sport"]
    assert row["adherence"] == "substituted"

    db.save_activities(
        [{
            "activity_id": "double-booked",
            "date": "2026-07-09",
            "started_at_utc": "2026-07-09T20:00:00Z",
            "sport": "cycling",
            "duration_minutes": 20,
            "tss": 12.0,
        }]
    )
    db.save_plan_actual_match(
        {
            "fingerprint": "other-session-match",
            "target_key": "session:other-session",
            "session_id": "other-session",
            "base_checkpoint_id": 1,
            "session_date": "2026-07-09",
            "match_status": "matched",
            "match_method": "user_confirmed",
            "confidence": 1.0,
            "planned_snapshot": {},
            "actual_activity_ids": ["double-booked"],
            "actual_snapshot": {},
            "evidence": ["existing explicit assignment"],
            "rule_version": "test",
        }
    )
    with pytest.raises(ValueError, match="already matched"):
        ps.record_plan_actual_match(
            db,
            base_checkpoint_id=1,
            session_id=target["session_id"],
            activity_ids=["double-booked"],
            actual_role=None,
            action="confirm",
        )

    with pytest.raises(ValueError, match="at least one activity"):
        ps.record_plan_actual_match(
            db,
            base_checkpoint_id=1,
            session_id=target["session_id"],
            activity_ids=[],
            actual_role=None,
            action="confirm",
        )


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
