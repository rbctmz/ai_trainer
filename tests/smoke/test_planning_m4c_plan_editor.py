"""BDD acceptance gates for Planning UI M4c (#337): compact 4-step plan editor.

The stepper must organize the existing build/edit form into four steps, keep
every existing power-user option, hydrate once without clobbering edits, and
start editing an active plan from the checkpoint's saved inputs. The server
owns the input mapping through a read-only edit-context contract.
"""
from __future__ import annotations

import importlib
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from api import planning_service as ps
from data.database import Database
from tests.smoke.test_api_planning import _seeded_db


pytestmark = pytest.mark.smoke
REPO_ROOT = Path(__file__).resolve().parents[2]
BUILDER = REPO_ROOT / "web/components/planning/PlanBuilder.tsx"
PAGE = REPO_ROOT / "web/app/planning/page.tsx"


def _event_plan_db(tmp_path):
    db = _seeded_db(tmp_path)
    event_date = (datetime.now().date() + timedelta(weeks=9)).isoformat()
    ps.build_plan(
        db,
        goal_type="triathlon",
        distance="olympic",
        event_date=event_date,
        available_hours=12,
        available_days=["mon", "tue", "wed", "thu", "sat", "sun"],
        demand="aggressive",
        persist=True,
    )
    return db, event_date


def test_m4c_edit_context_route_registered():
    main = importlib.import_module("api.main")
    paths = set(main.app.openapi()["paths"].keys())

    assert "/api/planning/edit-context" in paths


def test_edit_context_returns_build_inputs_from_checkpoint(tmp_path):
    db, event_date = _event_plan_db(tmp_path)

    result = ps.planning_edit_context(db)

    assert result["has_plan"] is True
    assert result["state"] == "available"
    inputs = result["inputs"]
    assert inputs["goal_type"] == "triathlon"
    assert inputs["distance"] == "olympic"
    assert inputs["planning_mode"] == "event_goal"
    assert inputs["intent"] == "develop"
    assert inputs["event_date"] == event_date
    assert inputs["available_hours"] == 12.0
    assert inputs["available_days"] == ["mon", "tue", "wed", "thu", "sat", "sun"]
    assert inputs["demand"] == "aggressive"
    assert inputs["horizon_weeks"] >= 1
    assert isinstance(inputs["events"], list)


def test_edit_context_without_plan_is_data_gap(tmp_path):
    db = Database(str(tmp_path / "empty.db"))

    result = ps.planning_edit_context(db)

    assert result == {
        "has_plan": False,
        "state": "data_gap",
        "reason": "Активного плана нет.",
        "inputs": None,
    }


def test_m4c_plan_builder_component_exists_with_four_steps():
    assert BUILDER.exists(), "PlanBuilder component must be extracted"
    builder = BUILDER.read_text(encoding="utf-8")

    for step_label in (
        "Подход и цель",
        "Доступность",
        "Нагрузка и preview",
        "Подтверждение",
    ):
        assert step_label in builder
    assert "Назад" in builder
    assert "Далее" in builder
    assert "aria-current" in builder
    assert "Предпросмотр плана" in builder
    assert "Подтвердить и сохранить" in builder


def test_m4c_builder_hydrates_once_and_uses_edit_context():
    builder = BUILDER.read_text(encoding="utf-8")
    page = PAGE.read_text(encoding="utf-8")

    assert "hydrated.current" in builder
    assert "revalidateOnFocus: false" in builder
    assert "/api/planning/edit-context" in builder
    assert "PlanBuilder" in page
    assert "hasPlan" in page
    assert "Изменить план" in page
