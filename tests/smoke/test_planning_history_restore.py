"""BDD acceptance gates for Planning M4d (#339): restore plan version from history.

History rows are read-only today; restoring a saved version must create a NEW
checkpoint on top of the active one (nothing is overwritten), keep provenance
(restore_version, parent = current, restored_from = chosen id), and be guarded
against stale checkpoints. Tests use temporary SQLite only.
"""
from __future__ import annotations

import importlib
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from api import planning_service as ps
from data.database import Database
from models.planning_checkpoints import restore_goal_plan_from_checkpoint
from tests.smoke.test_api_planning import _seeded_db


pytestmark = pytest.mark.smoke
REPO_ROOT = Path(__file__).resolve().parents[2]
PAGE = REPO_ROOT / "web/app/planning/page.tsx"


def _plan_with_history(tmp_path):
    """Two checkpoints: initial moderate plan, then an aggressive demand change."""
    db = _seeded_db(tmp_path)
    event_date = (datetime.now().date() + timedelta(weeks=9)).isoformat()
    ps.build_plan(
        db,
        goal_type="triathlon",
        distance="olympic",
        event_date=event_date,
        available_hours=12,
        available_days=["mon", "tue", "wed", "thu", "sat", "sun"],
        demand="moderate",
        persist=True,
    )
    first_id = int(db.get_latest_planning_checkpoint()["id"])
    preview = ps.demand_preview(db, "aggressive")
    ps.confirm_demand_change(
        db,
        level="aggressive",
        base_checkpoint_id=first_id,
        preview_fingerprint=preview["preview_fingerprint"],
    )
    second_id = int(db.get_latest_planning_checkpoint()["id"])
    return db, first_id, second_id


def test_history_restore_route_registered():
    main = importlib.import_module("api.main")
    paths = set(main.app.openapi()["paths"].keys())

    assert "/api/planning/history/restore" in paths


def test_restore_creates_new_checkpoint_with_provenance(tmp_path):
    db, first_id, second_id = _plan_with_history(tmp_path)
    first_plan = restore_goal_plan_from_checkpoint(db.get_planning_checkpoint(first_id))
    assert first_plan is not None

    result = ps.restore_history_version(
        db,
        checkpoint_id=first_id,
        base_checkpoint_id=second_id,
    )

    assert int(result["base_checkpoint_id"]) == second_id
    assert int(result["restored_from_checkpoint_id"]) == first_id
    assert result["checkpoint_source"] == "restore_version"
    applied_id = int(result["applied_checkpoint_id"])
    assert applied_id > second_id

    latest = db.get_latest_planning_checkpoint()
    assert int(latest["id"]) == applied_id
    snapshot = latest["goal_plan_snapshot"]
    assert snapshot["checkpoint_source"] == "restore_version"
    assert int(snapshot["checkpoint_parent_id"]) == second_id
    assert int(snapshot["checkpoint_restored_from_checkpoint_id"]) == first_id
    restored = restore_goal_plan_from_checkpoint(latest)
    assert restored is not None
    assert restored["start_week"] == first_plan["start_week"]
    assert restored["weekly_tss_plan"] == first_plan["weekly_tss_plan"]
    assert restored["weekly_target_breakdown"]["demand"]["level"] == "moderate"

    history = ps.planning_history(db, limit=5)["items"]
    assert any(
        item["source"] == "restore_version"
        and item["source_label"] == "Восстановленная версия"
        and item["checkpoint_id"] == applied_id
        for item in history
    )


def test_restore_rejects_stale_base(tmp_path):
    db, first_id, second_id = _plan_with_history(tmp_path)

    with pytest.raises(ps.StalePlanningCheckpointError):
        ps.restore_history_version(
            db,
            checkpoint_id=first_id,
            base_checkpoint_id=second_id + 100,
        )
    assert int(db.get_latest_planning_checkpoint()["id"]) == second_id


def test_restore_rejects_active_and_unknown_checkpoints(tmp_path):
    db, first_id, second_id = _plan_with_history(tmp_path)

    with pytest.raises(ValueError):
        ps.restore_history_version(
            db,
            checkpoint_id=second_id,
            base_checkpoint_id=second_id,
        )
    with pytest.raises(ValueError):
        ps.restore_history_version(
            db,
            checkpoint_id=999999,
            base_checkpoint_id=second_id,
        )
    assert int(db.get_latest_planning_checkpoint()["id"]) == second_id


def test_planning_page_has_history_restore_control():
    source = PAGE.read_text(encoding="utf-8")

    assert "/api/planning/history/restore" in source
    assert "Восстановить" in source
    assert "Восстановить версию" in source
