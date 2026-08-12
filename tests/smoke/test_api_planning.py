"""Smoke tests for Phase 2 planning endpoints.

Contributor-safe: temp SQLite seeded with a little history, no network/AI.
"""
from __future__ import annotations

import importlib
from datetime import date, datetime, timedelta
from time import perf_counter

import pytest

from tests.smoke._reference_dates import pinned_reference_events

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


def _running_leaf_prescriptions(goal_plan):
    """Yield materialized run singles and run brick legs from a stored plan."""
    for raw_template in goal_plan.get("session_templates") or []:
        template = dict(raw_template)
        for raw_session in template.get("sessions") or [template]:
            session = dict(raw_session)
            if session.get("kind") == "composite":
                for raw_leg in session.get("legs") or []:
                    leg = dict(raw_leg)
                    if leg.get("sport") == "run":
                        yield leg
            elif session.get("sport") == "run":
                yield session


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
    b_date, a_date = pinned_reference_events(today)
    db = _seeded_db(tmp_path)
    result = ps.build_plan(
        db,
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
    assert result["preview"]["microcycle_changes"]
    assert result["preview"]["microcycle_changes"] == result["event_overlay"]["microcycle_changes"]
    assert {row["priority"] for row in result["preview"]["microcycle_changes"]} >= {"A", "B"}
    assert all({"phase", "before", "after"} <= set(row) for row in result["preview"]["microcycle_changes"])
    active = ps.get_active_plan(db)
    assert active is not None
    by_date = {
        item[0].date().isoformat(): (item, active["session_templates"][index])
        for index, item in enumerate(active["daily_plan"])
    }
    for change in result["preview"]["microcycle_changes"]:
        daily_row, template = by_date[change["date"]]
        assert daily_row[1] == change["after"]["tss"]
        assert template["session_role"] == change["after"]["role"]
        assert template["sport"] == change["after"]["sport"]
        assert template["session_focus"] == change["after"]["focus"]


def test_event_goal_without_confirmed_a_is_rejected_without_checkpoint(tmp_path):
    from api import planning_service as ps

    db = _seeded_db(tmp_path)
    with pytest.raises(ValueError, match="confirmed A event"):
        ps.build_plan(
            db,
            goal_type="triathlon",
            distance="olympic",
            event_date=None,
            events=[
                {
                    "date": (datetime.now().date() + timedelta(weeks=4)).isoformat(),
                    "priority": "B",
                    "label": "Tune-up",
                    "confirmed": True,
                }
            ],
            planning_mode="event_goal",
            available_hours=10,
            persist=False,
        )

    assert db.get_latest_planning_checkpoint() is None


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


@pytest.mark.parametrize(
    ("threshold_pace", "lthr", "expected_kind", "expected_target_type"),
    [
        (300.0, 165.0, "threshold_pace", "pace"),
        (None, 165.0, "lthr", "heart_rate"),
        (None, None, "relative_rpe", "relative_rpe"),
    ],
)
def test_explicit_plan_build_prefers_running_pace_then_lthr_then_rpe(
    tmp_path,
    threshold_pace,
    lthr,
    expected_kind,
    expected_target_type,
):
    from api import planning_service as ps

    db = Database(str(tmp_path / f"run-target-{expected_kind}.db"))
    db.save_athlete_profile(
        {
            "ftp": 200.0,
            "weight_kg": 80.0,
            "lthr": lthr,
            "threshold_pace_seconds_per_km": threshold_pace,
            "threshold_pace_source": "intervals_icu" if threshold_pace else None,
            "source": "test",
        }
    )

    ps.build_plan(
        db,
        goal_type="run",
        distance="10k",
        event_date=None,
        planning_mode="training_goal",
        intent="develop",
        horizon_weeks=8,
        events=[],
        available_hours=8,
        available_days=["mon", "tue", "wed", "thu", "fri", "sat", "sun"],
        persist=True,
    )

    active = ps.get_active_plan(db)
    run_prescriptions = list(_running_leaf_prescriptions(active))
    assert run_prescriptions
    materialized = [
        item
        for item in run_prescriptions
        if item.get("materialization_status") == "materialized"
    ]
    assert materialized
    assert all(item.get("materialized_steps") for item in materialized)
    assert all(
        item["target_provenance"]["kind"] == expected_kind
        for item in materialized
    )
    if expected_kind == "threshold_pace":
        assert all(
            item["target_provenance"]["source"]
            == "athlete_profile.threshold_pace_seconds_per_km"
            for item in materialized
        )
    assert all(
        step["target"]["type"] == expected_target_type
        for item in materialized
        for step in item.get("materialized_steps") or []
    )


def test_b_overlay_persists_protected_days_and_resumes(tmp_path):
    from api import planning_service as ps

    db = _seeded_db(tmp_path)
    today = datetime.now().date()
    b_date, _a_date = pinned_reference_events(today)
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
    assert active["overlay_rule_version"] == "race-microcycle-v2"
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


def test_sixteen_week_preview_meets_planning_latency_asr(tmp_path):
    from api.planning_service import build_plan

    db = Database(str(tmp_path / "planning-latency.db"))
    event = (datetime.now().date() + timedelta(weeks=16)).isoformat()

    started = perf_counter()
    plan = build_plan(
        db,
        goal_type="triathlon",
        distance="olympic",
        event_date=event,
        available_hours=10,
        available_days=["mon", "tue", "wed", "thu", "fri", "sat", "sun"],
        persist=False,
    )
    elapsed = perf_counter() - started

    assert len(plan["weeks"]) >= 15
    assert elapsed < 4.0
    assert db.get_latest_planning_checkpoint() is None


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
        "/api/planning/delivery/intervals",
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
    from services import reconciliation as reconciliation_service

    db, _plan = _reconciliation_db(tmp_path)
    # Issue #194: _provider_reconciliation_evidence now lives in
    # services/reconciliation.py — reconciliation_at (re-exported, not
    # copied, into api.planning_service) resolves the name against that
    # module's own globals, so the monkeypatch target must live there too.
    monkeypatch.setattr(
        reconciliation_service,
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
        lambda _db, *, as_of=None, target_session_ids=None: refresh_calls.append(
            (as_of, target_session_ids)
        )
        or {"created": 0},
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
    assert refresh_calls == [(date.today(), [target["session_id"]])]

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


def test_confirm_match_without_role_stays_unknown(tmp_path):
    # #401 review P1: the executed role is user evidence, never copied from the
    # plan. Confirming without a role keeps adherence honestly "не оценено".
    from api import planning_service as ps

    db, plan = _reconciliation_db(tmp_path)
    target = next(
        item for item in plan["session_templates"] if item["date"] == "2026-07-12"
    )
    db.save_activities(
        [
            {
                "activity_id": "same-sport",
                "date": "2026-07-12",
                "started_at_utc": "2026-07-12T18:00:00Z",
                "sport": "cycling",
                "duration_minutes": 30,
                "tss": 10.0,
            }
        ]
    )

    saved = ps.record_plan_actual_match(
        db,
        base_checkpoint_id=1,
        session_id=target["session_id"],
        activity_ids=["same-sport"],
        actual_role=None,
        action="confirm",
    )

    assert saved["match_method"] == "user_confirmed"
    assert saved["actual_snapshot"]["role"] is None

    result = ps.reconciliation_at(
        db, as_of="2026-07-13", weeks=1, include_provider=False
    )
    row = next(
        item
        for item in result["rows"]
        if item["session_id"] == target["session_id"]
    )
    assert row["match_method"] == "user_confirmed"
    assert row["adherence"] == "unknown"


def test_confirm_match_with_explicit_role_evaluates_adherence(tmp_path):
    # #401: when the user supplies the executed role, adherence evaluates
    # honestly (same sport + in-bounds load + role match → exact).
    from api import planning_service as ps

    db, plan = _reconciliation_db(tmp_path)
    target = next(
        item for item in plan["session_templates"] if item["date"] == "2026-07-12"
    )
    db.save_activities(
        [
            {
                "activity_id": "same-sport",
                "date": "2026-07-12",
                "started_at_utc": "2026-07-12T18:00:00Z",
                "sport": "cycling",
                "duration_minutes": 30,
                "tss": 10.0,
            }
        ]
    )

    saved = ps.record_plan_actual_match(
        db,
        base_checkpoint_id=1,
        session_id=target["session_id"],
        activity_ids=["same-sport"],
        actual_role="recovery",
        action="confirm",
    )

    assert saved["match_method"] == "user_confirmed"
    assert saved["actual_snapshot"]["role"] == "recovery"

    result = ps.reconciliation_at(
        db, as_of="2026-07-13", weeks=1, include_provider=False
    )
    row = next(
        item
        for item in result["rows"]
        if item["session_id"] == target["session_id"]
    )
    assert row["match_method"] == "user_confirmed"
    assert row["adherence"] == "exact"


@pytest.mark.parametrize("actual_role", ["activation", "race"])
def test_confirm_match_accepts_every_planner_execution_role(tmp_path, actual_role):
    from api import planning_service as ps

    db, plan = _reconciliation_db(tmp_path)
    target = next(
        item for item in plan["session_templates"] if item["date"] == "2026-07-12"
    )
    db.save_activities(
        [
            {
                "activity_id": f"valid-role-{actual_role}",
                "date": "2026-07-12",
                "sport": "cycling",
                "duration_minutes": 30,
                "tss": 10.0,
            }
        ]
    )

    saved = ps.record_plan_actual_match(
        db,
        base_checkpoint_id=1,
        session_id=target["session_id"],
        activity_ids=[f"valid-role-{actual_role}"],
        actual_role=actual_role,
        action="confirm",
    )

    assert saved["actual_snapshot"]["role"] == actual_role


def test_confirm_match_rejects_unknown_actual_role_without_writing(tmp_path):
    from api import planning_service as ps

    db, plan = _reconciliation_db(tmp_path)
    target = next(
        item for item in plan["session_templates"] if item["date"] == "2026-07-12"
    )
    db.save_activities(
        [
            {
                "activity_id": "invalid-role",
                "date": "2026-07-12",
                "sport": "cycling",
                "duration_minutes": 30,
                "tss": 10.0,
            }
        ]
    )

    with pytest.raises(ValueError, match="actual_role must be one of"):
        ps.record_plan_actual_match(
            db,
            base_checkpoint_id=1,
            session_id=target["session_id"],
            activity_ids=["invalid-role"],
            actual_role="not-a-real-role",
            action="confirm",
        )

    assert db.get_latest_plan_actual_matches(
        start_date="2026-07-12", end_date="2026-07-12"
    ) == []


def test_unmatch_creates_user_unmatched_and_frees_activity(tmp_path):
    # #405: unmatch cancels a user_confirmed match — a user_unmatched revision
    # supersedes it, the session returns to "no fact", and the activity is free
    # to be confirmed again.
    from api import planning_service as ps

    db, plan = _reconciliation_db(tmp_path)
    target = next(
        item for item in plan["session_templates"] if item["date"] == "2026-07-12"
    )
    db.save_activities(
        [
            {
                "activity_id": "same-sport",
                "date": "2026-07-12",
                "started_at_utc": "2026-07-12T18:00:00Z",
                "sport": "cycling",
                "duration_minutes": 30,
                "tss": 10.0,
            }
        ]
    )

    confirmed = ps.record_plan_actual_match(
        db,
        base_checkpoint_id=1,
        session_id=target["session_id"],
        activity_ids=["same-sport"],
        actual_role="recovery",
        action="confirm",
    )
    assert confirmed["match_method"] == "user_confirmed"

    unmatched = ps.record_plan_actual_match(
        db,
        base_checkpoint_id=1,
        session_id=target["session_id"],
        activity_ids=[],
        actual_role=None,
        action="unmatch",
    )
    assert unmatched["match_method"] == "user_unmatched"
    assert unmatched["match_status"] == "unmatched"
    assert unmatched["supersedes_match_id"] == confirmed["id"]

    result = ps.reconciliation_at(
        db, as_of="2026-07-13", weeks=1, include_provider=False
    )
    row = next(
        item
        for item in result["rows"]
        if item["session_id"] == target["session_id"]
    )
    assert row["match_status"] == "unmatched"
    assert row["match_method"] == "user_unmatched"
    assert row["actual_activity_ids"] == []
    # #405 review P2: replacement candidates stay available after unmatch.
    assert [item["activity_id"] for item in row["candidate_activities"]] == [
        "same-sport"
    ]

    # Activity freed → confirm works again.
    again = ps.record_plan_actual_match(
        db,
        base_checkpoint_id=1,
        session_id=target["session_id"],
        activity_ids=["same-sport"],
        actual_role="recovery",
        action="confirm",
    )
    assert again["match_method"] == "user_confirmed"


def test_unmatch_tombstones_feedback_derived_from_match(tmp_path):
    # #405 review P1: feedback linked to a canceled match must not stay active —
    # the unmatch flow tombstones it so evaluations are not contaminated.
    import sqlite3

    from api import planning_service as ps

    db, plan = _reconciliation_db(tmp_path)
    target = next(
        item for item in plan["session_templates"] if item["date"] == "2026-07-12"
    )
    db.save_activities(
        [
            {
                "activity_id": "same-sport",
                "date": "2026-07-12",
                "started_at_utc": "2026-07-12T18:00:00Z",
                "sport": "cycling",
                "duration_minutes": 30,
                "tss": 10.0,
            }
        ]
    )
    confirmed = ps.record_plan_actual_match(
        db,
        base_checkpoint_id=1,
        session_id=target["session_id"],
        activity_ids=["same-sport"],
        actual_role="recovery",
        action="confirm",
    )

    conn = sqlite3.connect(db.db_path)
    try:
        conn.execute(
            """INSERT INTO session_feedback
               (fingerprint, target_key, revision, session_id, match_revision_id,
                match_snapshot_json, actual_activity_ids_json, completion_status,
                session_rpe_1_10, quality_rating_1_5, source, session_end_provenance,
                status, rule_version, submitted_at)
               VALUES (?, ?, 1, ?, ?, '{}', '["same-sport"]', 'completed', 6, 5,
                       'user_web', 'local', 'active', 'test', ?)""",
            (
                "fp-unmatch-fb",
                f"session:{target['session_id']}",
                target["session_id"],
                confirmed["id"],
                "2026-08-08T10:00:00Z",
            ),
        )
        conn.commit()
    finally:
        conn.close()

    ps.record_plan_actual_match(
        db,
        base_checkpoint_id=1,
        session_id=target["session_id"],
        activity_ids=[],
        actual_role=None,
        action="unmatch",
    )

    history = db.get_session_feedback_history(target["session_id"])
    assert any(row["status"] == "tombstone" for row in history)


def test_unmatch_tombstones_feedback_from_superseded_match_revision(tmp_path):
    """Role correction must not hide active feedback from the unmatch cleanup."""
    from api import planning_service as ps

    db, plan = _reconciliation_db(tmp_path)
    target = next(
        item for item in plan["session_templates"] if item["date"] == "2026-07-12"
    )
    db.save_activities(
        [
            {
                "activity_id": "same-sport",
                "date": "2026-07-12",
                "started_at_utc": "2026-07-12T18:00:00Z",
                "sport": "cycling",
                "duration_minutes": 30,
                "tss": 10.0,
            }
        ]
    )
    first_match = ps.record_plan_actual_match(
        db,
        base_checkpoint_id=1,
        session_id=target["session_id"],
        activity_ids=["same-sport"],
        actual_role=None,
        action="confirm",
    )
    feedback = db.save_session_feedback(
        {
            "fingerprint": "feedback-before-role-correction",
            "target_key": f"session:{target['session_id']}",
            "session_id": target["session_id"],
            "match_revision_id": first_match["id"],
            "match_snapshot": {
                "planned": {"session_id": target["session_id"]},
                "match_status": "matched",
                "match_method": "user_confirmed",
            },
            "actual_activity_ids": ["same-sport"],
            "completion_status": "completed",
            "session_rpe_1_10": 6,
            "quality_rating_1_5": 5,
            "source": "user_web",
            "session_end_provenance": "local",
            "status": "active",
            "rule_version": "test",
            "submitted_at": "2026-08-08T10:00:00Z",
        }
    )["feedback"]
    corrected_match = ps.record_plan_actual_match(
        db,
        base_checkpoint_id=1,
        session_id=target["session_id"],
        activity_ids=["same-sport"],
        actual_role="recovery",
        action="confirm",
    )
    assert corrected_match["supersedes_match_id"] == first_match["id"]

    ps.record_plan_actual_match(
        db,
        base_checkpoint_id=1,
        session_id=target["session_id"],
        activity_ids=[],
        actual_role=None,
        action="unmatch",
    )

    latest = db.get_latest_session_feedback(target["session_id"])
    assert latest["status"] == "tombstone"
    assert latest["supersedes_feedback_id"] == feedback["id"]

    # Retrying unmatch is safe and does not append another feedback tombstone.
    history_size = len(db.get_session_feedback_history(target["session_id"]))
    ps.record_plan_actual_match(
        db,
        base_checkpoint_id=1,
        session_id=target["session_id"],
        activity_ids=[],
        actual_role=None,
        action="unmatch",
    )
    assert len(db.get_session_feedback_history(target["session_id"])) == history_size
    assert db.get_latest_session_feedback(target["session_id"])["status"] == "tombstone"


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


def test_intervals_delivery_route_rejects_demo_before_provider_and_returns_result(
    tmp_path, monkeypatch
):
    from fastapi import HTTPException
    from api import planning_service as ps
    from api.routers.planning import IntervalsDeliveryRequest, planning_deliver_intervals

    db = _seeded_db(tmp_path)
    calls = []
    monkeypatch.setattr(
        ps,
        "deliver_intervals_plan",
        lambda _db, *, days: calls.append(days) or {
            "status": "success",
            "executable_count": 2,
            "calendar_only_count": 0,
        },
        raising=False,
    )
    request = IntervalsDeliveryRequest(days=7)

    with pytest.raises(HTTPException) as blocked:
        planning_deliver_intervals(request, demo=True, db=db)
    result = planning_deliver_intervals(request, demo=False, db=db)

    assert blocked.value.status_code == 409
    assert calls == [7]
    assert result["executable_count"] == 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
