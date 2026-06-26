from __future__ import annotations

from datetime import date, datetime, timedelta
from types import SimpleNamespace

import pandas as pd
import pytest

from ui.pages.dashboard import _build_dashboard_v2_summary


pytestmark = pytest.mark.smoke


def _fake_state(goal_plan: dict | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        ai_coach=object(),
        goal_plan=goal_plan or {},
        resolved_goal_plan_context=goal_plan or {},
        latest_execution_feedback=None,
        latest_planning_checkpoint=None,
    )


def test_dashboard_v2_summary_prioritizes_today_and_week_plan() -> None:
    reference_date = date(2026, 6, 22)
    daily_plan = []
    session_templates = []
    for offset, tss in enumerate([35, 0, 55, 0, 45, 70, 0]):
        day = datetime.combine(reference_date + timedelta(days=offset), datetime.min.time())
        daily_plan.append((day, tss, {"run": tss}))
        session_templates.append(
            {
                "export_name": f"Run session {offset + 1}",
                "sport": "run",
                "duration_minutes": 45 if tss else 0,
            }
        )
    goal_plan = {"daily_plan": daily_plan, "session_templates": session_templates}
    activities_df = pd.DataFrame(
        [
            {"date": reference_date, "tss": 20, "distance_km": 4, "duration_minutes": 30},
            {"date": reference_date + timedelta(days=1), "tss": 10, "distance_km": 2, "duration_minutes": 20},
        ]
    )

    summary = _build_dashboard_v2_summary(
        _fake_state(goal_plan),
        {"readiness": 70, "tsb": -4.2, "ctl": 31.5, "hrv": 39},
        {"training_readiness": 82},
        activities_df,
        reference_date=reference_date,
    )

    assert summary["today"]["state_label"] == "Готов к работе"
    assert summary["today"]["readiness"] == 82
    assert summary["workout"]["title"] == "Run session 1"
    assert summary["workout"]["tss"] == 35
    assert summary["week"]["planned_tss"] == 205
    assert summary["week"]["actual_tss"] == 30
    assert summary["week"]["remaining_tss"] == 175
    assert len(summary["next_days"]) == 7
    assert summary["next_days"][0]["status"] == "done"
    assert summary["next_days"][1]["status"] == "rest"


def test_dashboard_v2_summary_handles_missing_plan_without_noise() -> None:
    reference_date = date(2026, 6, 22)
    summary = _build_dashboard_v2_summary(
        _fake_state(),
        {"readiness": 40, "tsb": -24, "ctl": 22},
        {},
        pd.DataFrame(columns=["date", "tss"]),
        reference_date=reference_date,
    )

    assert summary["today"]["state_label"] == "Нужна разгрузка"
    assert summary["workout"]["title"] == "План на сегодня не найден"
    assert summary["week"]["planned_tss"] == 0
    assert summary["plan"]["status"] == "no_plan"
    assert summary["next_days"][0]["status"] == "empty"
