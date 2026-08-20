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


def _build_active_triathlon_plan(db: Database) -> None:
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


def test_proposal_tools_registered(tmp_path) -> None:
    tools = AITools(Database(str(tmp_path / "registry.db")))
    available = tools.get_available_tools()

    assert "propose_plan_build" in available
    assert "propose_plan_adjustment" in available
    assert "create_plan_constraint" in available
    assert "propose_plan_build" in tools.tools
    assert "propose_plan_adjustment" in tools.tools
    assert "create_plan_constraint" in tools.tools


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
    assert proposal["preview"]["goal"]["events"] == [
        {
            "date": event_date,
            "priority": "A",
            "label": "Триатлон Half (70.3)",
            "source": "user",
            "priority_provenance": "explicit_user",
            "confirmed": True,
            "requires_confirmation": False,
        }
    ]
    assert proposal["preview"].get("total_weeks", 0) > 0
    assert proposal["preview"].get("peak_tss", 0) > 0


def test_propose_plan_adjustment_no_plan(tmp_path) -> None:
    tools = AITools(Database(str(tmp_path / "empty.db")))

    result = tools.execute_tool("propose_plan_adjustment", weeks=1)

    assert result["success"] is False
    assert "план" in result.get("error", "").lower() or "plan" in result.get("error", "").lower()


def test_propose_plan_adjustment_returns_noop_when_plan_is_completed(tmp_path) -> None:
    db = _seeded_db(tmp_path)
    _build_active_triathlon_plan(db)
    tools = AITools(db)

    result = tools.execute_tool("propose_plan_adjustment", weeks=1)

    assert result["success"] is True, result.get("error")
    proposal = result["result"]
    assert proposal.get("is_proposal") is False
    assert proposal.get("status") == "noop"
    assert proposal.get("action") == "adjust_plan"
    assert proposal["params"]["weeks"] == 1
    assert "rows" not in proposal["params"]
    assert proposal["preview"].get("status") == "no_change"
    assert proposal["preview"].get("reason") in {
        "data_gap",
        "no_change_under_plan",
        "no_change_below_threshold",
        "no_eligible_future_sessions",
    }


def test_propose_plan_adjustment_returns_proposal_for_changed_rows(tmp_path, monkeypatch) -> None:
    db = _seeded_db(tmp_path)
    _build_active_triathlon_plan(db)
    def fake_preview(database: Database, weeks: int = 1):
        return {
            "has_plan": True,
            "reconciliation": {
                "data_quality": {
                    "coverage": 0.8,
                    "matched_count": 4,
                    "planned_session_count": 5,
                    "ambiguous_count": 0,
                }
            },
            "preview": {
                "status": "proposal",
                "reason": "over_plan_future_reduction",
                "future_tss_delta": -20,
                "changes": [
                    {
                        "session_id": "ats_1",
                        "date": "2026-07-14",
                        "before_tss": 40,
                        "after_tss": 30,
                    }
                ],
                "as_of": "2026-07-13",
                "base_checkpoint_id": 1,
                "preview_fingerprint": "preview-1",
            },
        }

    monkeypatch.setattr(planning_service, "preview_weekly_rebalance", fake_preview)
    tools = AITools(db)

    result = tools.execute_tool("propose_plan_adjustment", weeks=1)

    assert result["success"] is True, result.get("error")
    proposal = result["result"]
    assert proposal.get("is_proposal") is True
    assert proposal.get("action") == "adjust_plan"
    assert proposal["params"]["weeks"] == 1
    assert "rows" not in proposal["params"]
    assert proposal["params"]["base_checkpoint_id"] == 1
    assert proposal["params"]["preview_fingerprint"] == "preview-1"
    assert proposal["preview"].get("status") == "proposal"
    assert proposal["preview"].get("future_tss_delta") == -20


def test_noop_plan_adjustment_formatter_does_not_request_confirmation() -> None:
    from ui.components.ai_coach_output import format_tool_result

    text = format_tool_result(
        "propose_plan_adjustment",
        {
            "is_proposal": False,
            "status": "noop",
            "params": {"weeks": 1},
            "preview": {
                "adjustment_status": "completed",
                "adjustment_label": "Выполнено по плану",
                "missed_sessions": 0,
                "completion_share": 1.0,
                "peak_tss": 400,
                "total_tss": 880,
            },
        },
    )

    assert "Корректировка плана не нужна" in text
    assert "Подтверди карточку" not in text


def test_create_plan_constraint_without_active_plan_requires_approval(tmp_path) -> None:
    from api.routers.decisions import approve_proposal

    db = Database(str(tmp_path / "constraint_tool_empty.db"))
    tools = AITools(db)

    result = tools.execute_tool(
        "create_plan_constraint",
        date="tomorrow",
        kind="sick",
        note="Температура, без тренировок",
    )

    assert result["success"] is True, result.get("error")
    payload = result["result"]
    expected_date = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

    assert payload["is_proposal"] is True
    assert payload["action"] == "create_plan_constraint"
    assert payload["preview"]["active_plan_updated"] is False
    assert payload["params"]["date"] == expected_date
    assert db.get_coach_constraints(start_date=expected_date, end_date=expected_date) == []

    saved = db.save_coach_proposal(
        action=payload["action"],
        params=payload["params"],
        preview=payload["preview"],
    )
    approved = approve_proposal(int(saved["id"]), db=db)
    constraint = approved["result"]["constraint"]
    assert constraint["date"] == expected_date
    assert constraint["kind"] == "sick"
    assert constraint["status"] == "active"


def test_create_plan_constraint_applies_exact_preview_after_approval(tmp_path) -> None:
    from api.routers.decisions import approve_proposal

    db = _seeded_db(tmp_path)
    _build_active_triathlon_plan(db)
    active_plan = planning_service.get_active_plan(db)
    assert active_plan

    protected_index = next(
        index
        for index, item in enumerate(active_plan["daily_plan"])
        if item[0].date() >= datetime.now().date() and float(item[1] or 0) > 0
    )
    protected_date = active_plan["daily_plan"][protected_index][0].strftime("%Y-%m-%d")
    before_checkpoint_id = int(db.get_latest_planning_checkpoint()["id"])

    result = AITools(db).execute_tool(
        "create_plan_constraint",
        date=protected_date,
        kind="болею",
        note="Болею, нужен отдых",
    )

    assert result["success"] is True, result.get("error")
    payload = result["result"]
    assert payload["is_proposal"] is True
    assert payload["preview"]["active_plan_updated"] is True
    assert payload["preview"]["applied_count"] == 1
    assert payload["preview"]["protected_dates"] == [protected_date]
    assert db.get_latest_planning_checkpoint()["id"] == before_checkpoint_id
    assert db.get_coach_constraints(start_date=protected_date, end_date=protected_date) == []

    saved = db.save_coach_proposal(
        action=payload["action"],
        params=payload["params"],
        preview=payload["preview"],
    )
    approved = approve_proposal(int(saved["id"]), db=db)
    assert approved["result"]["applied_checkpoint_id"] > before_checkpoint_id

    updated_plan = planning_service.get_active_plan(db)
    assert updated_plan
    assert updated_plan["daily_plan"][protected_index][1] == 0
    assert updated_plan["session_templates"][protected_index]["session_role"] == "off"
    assert updated_plan["session_templates"][protected_index]["constraint"]["kind"] == "sick"


def test_create_plan_constraint_rejects_unknown_kind(tmp_path) -> None:
    result = AITools(Database(str(tmp_path / "bad_constraint.db"))).execute_tool(
        "create_plan_constraint",
        date="tomorrow",
        kind="party",
    )

    assert result["success"] is False
    assert "kind" in result.get("error", "").lower()


def test_system_prompt_contains_proposal_tools() -> None:
    prompt = create_chat_system_prompt_with_tools(None)

    assert "propose_plan_build" in prompt
    assert "propose_plan_adjustment" in prompt
    assert "create_plan_constraint" in prompt
