"""Smoke coverage for proposal tools (propose_plan_build, propose_plan_adjustment)."""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from api import planning_service
from data.database import Database
from models.ai_coach_runtime import create_chat_system_prompt_with_tools
from models.ai_tools import AITools


pytestmark = pytest.mark.smoke


def _seeded_db(tmp_path) -> Database:
    db = Database(str(tmp_path / "proposal.db"))
    base = datetime.now()
    rows = []
    for i in range(35):
        rows.append(
            {
                "activity_id": f"p{i}",
                "date": (base - timedelta(days=i)).strftime("%Y-%m-%d"),
                "sport": "cycling" if i % 2 else "running",
                "duration_minutes": 60,
                "distance_km": 22.0,
                "tss": 52.0 + (i % 4) * 5.0,
            }
        )
    db.save_activities(rows)
    return db


def test_proposal_tools_registered(tmp_path) -> None:
    tools = AITools(Database(str(tmp_path / "registry.db")))
    available = tools.get_available_tools()

    assert "propose_plan_build" in available
    assert "propose_plan_adjustment" in available
    assert "propose_plan_build" in tools.tools
    assert "propose_plan_adjustment" in tools.tools


def test_propose_plan_build_missing_event_date(tmp_path) -> None:
    tools = AITools(Database(str(tmp_path / "missing.db")))

    result = tools.execute_tool(
        "propose_plan_build",
        goal_type="Триатлон",
        distance="Half",
    )

    assert result["success"] is False
    assert "event_date" in result.get("error", "").lower() or "дат" in result.get("error", "").lower()


def test_propose_plan_build_returns_proposal(tmp_path) -> None:
    tools = AITools(_seeded_db(tmp_path))
    event_date = (datetime.now() + timedelta(weeks=9)).strftime("%Y-%m-%d")

    result = tools.execute_tool(
        "propose_plan_build",
        goal_type="Триатлон",
        distance="Half",
        event_date=event_date,
        available_hours=10,
        available_days="mon,tue,thu,sat,sun",
    )

    assert result["success"] is True, result.get("error")
    proposal = result["result"]
    assert proposal.get("is_proposal") is True
    assert proposal.get("action") == "build_plan"
    assert proposal["params"]["event_date"] == event_date
    assert proposal["params"]["available_days"] == ["mon", "tue", "thu", "sat", "sun"]
    assert proposal["preview"].get("total_weeks", 0) > 0
    assert proposal["preview"].get("peak_tss", 0) > 0


def test_propose_plan_adjustment_no_plan(tmp_path) -> None:
    tools = AITools(Database(str(tmp_path / "empty.db")))

    result = tools.execute_tool("propose_plan_adjustment", weeks=1)

    assert result["success"] is False
    assert "план" in result.get("error", "").lower() or "plan" in result.get("error", "").lower()


def test_propose_plan_adjustment_returns_proposal(tmp_path) -> None:
    db = _seeded_db(tmp_path)
    event_date = (datetime.now() + timedelta(weeks=8)).strftime("%Y-%m-%d")
    planning_service.build_plan(
        db,
        goal_type="triathlon",
        distance="olympic",
        event_date=event_date,
        available_hours=12,
        available_days=["mon", "tue", "wed", "thu", "sat", "sun"],
        persist=True,
    )
    tools = AITools(db)

    result = tools.execute_tool("propose_plan_adjustment", weeks=1)

    assert result["success"] is True, result.get("error")
    proposal = result["result"]
    assert proposal.get("is_proposal") is True
    assert proposal.get("action") == "adjust_plan"
    assert proposal["params"]["weeks"] == 1
    assert isinstance(proposal["params"]["rows"], list)
    assert proposal["preview"].get("peak_tss", 0) > 0
    assert proposal["preview"].get("adjustment_status")


def test_system_prompt_contains_proposal_tools() -> None:
    prompt = create_chat_system_prompt_with_tools(None)

    assert "propose_plan_build" in prompt
    assert "propose_plan_adjustment" in prompt
