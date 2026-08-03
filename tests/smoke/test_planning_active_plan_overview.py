"""BDD acceptance gates for Planning UI M1 (#301).

The overview is a read-only checkpoint projection. These tests deliberately use
temporary SQLite only: displaying the reader default must not contact a provider
or mutate a planning checkpoint.
"""
from __future__ import annotations

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


def _event_plan_db(tmp_path) -> tuple[Database, str]:
    db = _seeded_db(tmp_path)
    event_date = (datetime.now().date() + timedelta(weeks=9)).isoformat()
    ps.build_plan(
        db,
        goal_type="triathlon",
        distance="olympic",
        event_date=event_date,
        available_hours=10,
        persist=True,
    )
    return db, event_date


def test_overview_has_no_fake_hero_without_a_plan(tmp_path):
    overview = planning_overview(db=Database(str(tmp_path / "empty.db")))

    assert overview == {"has_plan": False}


def test_event_plan_overview_uses_confirmed_a_goal_and_checkpoint_timeline(tmp_path):
    db, event_date = _event_plan_db(tmp_path)
    checkpoint_before = db.get_latest_planning_checkpoint()

    overview = planning_overview(db=db)

    assert overview["has_plan"] is True
    assert overview["goal"]["planning_mode"] == "event_goal"
    assert overview["timeline"]["kind"] == "event"
    assert overview["timeline"]["event"]["priority"] == "A"
    assert overview["timeline"]["event"]["confirmed"] is True
    assert overview["timeline"]["event"]["date"] == event_date
    assert overview["timeline"]["days_remaining"] >= 0
    assert overview["current_week"]["number"] >= 1
    assert overview["progress"]["total_weeks"] >= overview["current_week"]["number"]
    assert overview["execution"]["state"] == "data_gap"
    assert db.get_latest_planning_checkpoint() == checkpoint_before


def test_active_plan_overview_never_discovers_provider_events(tmp_path, monkeypatch):
    db, _event_date = _event_plan_db(tmp_path)

    def _provider_call_is_forbidden(**_kwargs):
        raise AssertionError("reader overview must not contact a provider")

    monkeypatch.setattr(ps, "discover_intervals_events", _provider_call_is_forbidden)

    assert planning_overview(db=db)["has_plan"] is True


def test_active_plan_overview_explains_saved_availability_and_weekly_target(tmp_path):
    db, _event_date = _event_plan_db(tmp_path)
    checkpoint_before = db.get_latest_planning_checkpoint()

    overview = planning_overview(db=db)

    availability = overview["availability"]
    assert availability == {
        "state": "available",
        "reason": None,
        "available_hours": 10.0,
        "available_minutes": 600,
        "available_days": ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"],
        "planned_minutes": 2690,
        "planned_hours": 44.8,
        "session_count": 69,
        "daily": {
            "state": "data_gap",
            "reason": "В сохранённом checkpoint нет дневных лимитов доступности.",
            "days": [],
        },
    }

    target = overview["weekly_target_explanation"]
    assert target["state"] == "available"
    assert target["reason"] is None
    assert target["goal_need_tss"] == 600
    assert target["availability_cap_tss"] == 420
    assert target["recent_load_tss"] == 385
    assert target["base_weekly_tss"] == 420
    assert target["final_target_weekly_tss"] == 420
    assert target["demand"] == {"level": "moderate", "label": "Умеренно", "multiplier": 1.0}
    assert [row["key"] for row in target["rows"]] == [
        "goal_need",
        "availability_cap",
        "recent_load",
        "base_weekly_tss",
    ]
    assert db.get_latest_planning_checkpoint() == checkpoint_before


def test_active_plan_overview_marks_missing_saved_reader_context_as_data_gap(tmp_path):
    db, _event_date = _event_plan_db(tmp_path)
    goal_plan = restore_goal_plan_from_checkpoint(db.get_latest_planning_checkpoint())
    assert goal_plan is not None
    goal_plan["constraint_summary"] = {}
    goal_plan.pop("weekly_target_breakdown", None)
    db.save_planning_checkpoint(build_planning_checkpoint(goal_plan))

    overview = planning_overview(db=db)

    assert overview["has_plan"] is True
    assert overview["availability"] == {
        "state": "data_gap",
        "reason": "В сохранённом checkpoint нет недельной доступности.",
        "available_hours": None,
        "available_minutes": None,
        "available_days": [],
        "planned_minutes": None,
        "planned_hours": None,
        "session_count": None,
        "daily": {"state": "data_gap", "reason": "В сохранённом checkpoint нет дневных лимитов доступности.", "days": []},
    }
    assert overview["weekly_target_explanation"] == {
        "state": "data_gap",
        "reason": "В сохранённом checkpoint нет разбивки недельной цели.",
        "rows": [],
        "goal_need_tss": None,
        "availability_cap_tss": None,
        "recent_load_tss": None,
        "base_weekly_tss": None,
        "final_target_weekly_tss": None,
        "demand": None,
    }


def test_training_goal_overview_uses_rolling_horizon_without_race_countdown(tmp_path):
    db = _seeded_db(tmp_path)
    ps.build_plan(
        db,
        goal_type="run",
        distance="10k",
        event_date=None,
        planning_mode="training_goal",
        intent="develop",
        horizon_weeks=6,
        events=[],
        available_hours=8,
        persist=True,
    )

    overview = planning_overview(db=db)

    assert overview["timeline"] == {"kind": "rolling", "horizon_weeks": 6}
    assert overview["goal"]["event"] is None
    assert overview["progress"]["total_weeks"] == 6


def test_planning_page_keeps_reader_and_mutating_actions_separate():
    source = (REPO_ROOT / "web/app/planning/page.tsx").read_text(encoding="utf-8")
    types = (REPO_ROOT / "web/lib/types.ts").read_text(encoding="utf-8")

    assert '"overview", "weeks", "execution"' in source
    assert "Обзор" in source and "Недели" in source and "Выполнение" in source
    assert "Изменить план" in source and "Скорректировать" in source and "Экспорт" in source
    assert 'aria-expanded={expanded}' in source
    assert 'aria-controls="planning-adjustment-history"' in source
    assert 'event.key === "Enter" || event.key === " "' in source
    assert "История изменений" in source
    assert 'searchParams.get("session_id")' in source
    assert "PlanningOverview" in types
    assert "Доступность" in source
    assert "Как рассчитана недельная нагрузка" in source
