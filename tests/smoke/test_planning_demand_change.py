"""BDD acceptance gates for Planning UI M4b (#335): demand preview -> confirm.

The demand control on the active-plan Overview must show the expected effect
before anything is written. Preview is read-only; confirm is an explicit,
stale-guarded mutation that creates a new checkpoint with demand_change
provenance. Tests use temporary SQLite only and never contact a provider.
"""
from __future__ import annotations

import importlib
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from api import planning_service as ps
from api.routers.planning import planning_overview
from data.database import Database
from models.planning_checkpoints import build_planning_checkpoint, restore_goal_plan_from_checkpoint
from tests.smoke.test_api_planning import _seeded_db


pytestmark = pytest.mark.smoke
REPO_ROOT = Path(__file__).resolve().parents[2]


def _event_plan_db(tmp_path, *, available_hours=12, demand="moderate"):
    db = _seeded_db(tmp_path)
    event_date = (datetime.now().date() + timedelta(weeks=9)).isoformat()
    ps.build_plan(
        db,
        goal_type="triathlon",
        distance="olympic",
        event_date=event_date,
        available_hours=available_hours,
        available_days=["mon", "tue", "wed", "thu", "sat", "sun"],
        demand=demand,
        persist=True,
    )
    return db, event_date


def test_demand_routes_registered():
    main = importlib.import_module("api.main")
    paths = set(main.app.openapi()["paths"].keys())

    assert {"/api/planning/demand-preview", "/api/planning/demand/confirm"} <= paths


def test_demand_preview_is_read_only_and_shows_delta(tmp_path):
    db, _event_date = _event_plan_db(tmp_path, available_hours=16)
    checkpoint_before = db.get_latest_planning_checkpoint()
    base_id = int(checkpoint_before["id"])

    result = ps.demand_preview(db, "aggressive")

    assert result["has_plan"] is True
    assert result["state"] == "available"
    assert result["reason"] is None
    assert result["base_checkpoint_id"] == base_id
    assert isinstance(result["preview_fingerprint"], str) and result["preview_fingerprint"]
    current = result["current"]
    assert current["level"] == "moderate"
    assert current["label"] == "Умеренно"
    assert current["multiplier"] == 1.0
    preview = result["preview"]
    assert preview["level"] == "aggressive"
    assert preview["label"] == "Агрессивно"
    assert preview["multiplier"] == 1.2
    assert preview["final_target_weekly_tss"] > current["final_target_weekly_tss"]
    assert preview["delta_weekly_tss"] == (
        preview["final_target_weekly_tss"] - current["final_target_weekly_tss"]
    )
    assert preview["availability_cap_tss"] > preview["final_target_weekly_tss"]
    assert preview["capped"] is False
    assert [row["key"] for row in preview["rows"]] == [
        "goal_need",
        "availability_cap",
        "recent_load",
        "base_weekly_tss",
    ]
    # Preview никогда не пишет: id и snapshot активного checkpoint прежние.
    assert db.get_latest_planning_checkpoint() == checkpoint_before


def test_demand_preview_is_honest_when_availability_cap_binds(tmp_path):
    db, _event_date = _event_plan_db(tmp_path, available_hours=10)
    result = ps.demand_preview(db, "aggressive")

    preview = result["preview"]
    assert preview["capped"] is True
    assert preview["final_target_weekly_tss"] == preview["availability_cap_tss"]
    assert preview["final_target_weekly_tss"] == result["current"]["final_target_weekly_tss"]
    assert preview["delta_weekly_tss"] == 0


def test_demand_confirm_writes_new_checkpoint_with_provenance(tmp_path):
    db, _event_date = _event_plan_db(tmp_path)
    base_id = int(db.get_latest_planning_checkpoint()["id"])
    preview = ps.demand_preview(db, "aggressive")

    result = ps.confirm_demand_change(
        db,
        level="aggressive",
        base_checkpoint_id=base_id,
        preview_fingerprint=preview["preview_fingerprint"],
    )

    assert int(result["base_checkpoint_id"]) == base_id
    applied_id = int(result["applied_checkpoint_id"])
    assert applied_id > base_id
    latest = db.get_latest_planning_checkpoint()
    assert int(latest["id"]) == applied_id
    snapshot = latest["goal_plan_snapshot"]
    assert snapshot["checkpoint_source"] == "demand_change"
    assert int(snapshot["checkpoint_parent_id"]) == base_id
    assert snapshot["demand_level"] == "aggressive"
    assert snapshot["weekly_target_breakdown"]["demand"]["level"] == "aggressive"
    assert ps.get_demand(db)["demand"]["level"] == "aggressive"
    assert ps.current_status(db)["demand"]["level"] == "aggressive"
    overview = planning_overview(db=db)
    assert overview["weekly_target_explanation"]["demand"]["level"] == "aggressive"


def test_demand_confirm_preserves_plan_calendar(tmp_path):
    db, _event_date = _event_plan_db(tmp_path)
    before = restore_goal_plan_from_checkpoint(db.get_latest_planning_checkpoint())
    assert before is not None
    base_id = int(db.get_latest_planning_checkpoint()["id"])
    preview = ps.demand_preview(db, "aggressive")

    ps.confirm_demand_change(
        db,
        level="aggressive",
        base_checkpoint_id=base_id,
        preview_fingerprint=preview["preview_fingerprint"],
    )

    after = restore_goal_plan_from_checkpoint(db.get_latest_planning_checkpoint())
    assert after is not None
    assert after["start_week"] == before["start_week"]
    assert after["phases"] == before["phases"]
    assert after["weekly_target_breakdown"]["demand"]["level"] == "aggressive"


def test_demand_confirm_rejects_stale_checkpoint(tmp_path):
    db, _event_date = _event_plan_db(tmp_path)
    preview = ps.demand_preview(db, "aggressive")

    with pytest.raises(ps.StalePlanningCheckpointError):
        ps.confirm_demand_change(
            db,
            level="aggressive",
            base_checkpoint_id=preview["base_checkpoint_id"] + 100,
            preview_fingerprint=preview["preview_fingerprint"],
        )


def test_demand_confirm_rejects_stale_fingerprint(tmp_path):
    db, _event_date = _event_plan_db(tmp_path)
    base_id = int(db.get_latest_planning_checkpoint()["id"])

    with pytest.raises(ps.StalePlanningCheckpointError):
        ps.confirm_demand_change(
            db,
            level="aggressive",
            base_checkpoint_id=base_id,
            preview_fingerprint="stale-fingerprint",
        )


def test_demand_confirm_rejects_same_level(tmp_path):
    db, _event_date = _event_plan_db(tmp_path)
    base_id = int(db.get_latest_planning_checkpoint()["id"])
    preview = ps.demand_preview(db, "moderate")
    assert preview["preview"]["delta_weekly_tss"] == 0

    with pytest.raises(ValueError):
        ps.confirm_demand_change(
            db,
            level="moderate",
            base_checkpoint_id=base_id,
            preview_fingerprint=preview["preview_fingerprint"],
        )


def test_demand_confirm_rejects_unknown_level(tmp_path):
    db, _event_date = _event_plan_db(tmp_path)
    base_id = int(db.get_latest_planning_checkpoint()["id"])

    with pytest.raises(ValueError):
        ps.confirm_demand_change(
            db,
            level="extreme",
            base_checkpoint_id=base_id,
            preview_fingerprint="x",
        )


def test_demand_preview_without_plan_is_data_gap(tmp_path):
    db = Database(str(tmp_path / "empty.db"))

    result = ps.demand_preview(db, "aggressive")

    assert result == {
        "has_plan": False,
        "state": "data_gap",
        "reason": "Активного плана нет.",
        "current": None,
        "preview": None,
        "base_checkpoint_id": None,
        "preview_fingerprint": None,
    }


def test_demand_preview_missing_target_breakdown_is_data_gap(tmp_path):
    db, _event_date = _event_plan_db(tmp_path)
    goal_plan = restore_goal_plan_from_checkpoint(db.get_latest_planning_checkpoint())
    assert goal_plan is not None
    goal_plan.pop("weekly_target_breakdown", None)
    goal_plan["constraint_summary"] = {}
    db.save_planning_checkpoint(build_planning_checkpoint(goal_plan))

    result = ps.demand_preview(db, "aggressive")

    assert result["has_plan"] is True
    assert result["state"] == "data_gap"
    assert result["reason"]
    assert result["current"] is None and result["preview"] is None


def test_demand_preview_never_contacts_provider(tmp_path, monkeypatch):
    db, _event_date = _event_plan_db(tmp_path)

    def _provider_call_is_forbidden(**_kwargs):
        raise AssertionError("demand preview must not contact a provider")

    monkeypatch.setattr(ps, "discover_intervals_events", _provider_call_is_forbidden)

    assert ps.demand_preview(db, "aggressive")["state"] == "available"


def test_planning_page_has_overview_demand_control():
    source = (REPO_ROOT / "web/app/planning/page.tsx").read_text(encoding="utf-8")
    types = (REPO_ROOT / "web/lib/types.ts").read_text(encoding="utf-8")

    assert "Режим нагрузки" in source
    assert "/api/planning/demand-preview" in source
    assert "/api/planning/demand/confirm" in source
    assert "Применить" in source
    assert "DemandPreview" in types
    assert "DemandConfirm" in types
