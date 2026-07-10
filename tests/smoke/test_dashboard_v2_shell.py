from __future__ import annotations

from datetime import date, datetime, timedelta
from types import SimpleNamespace

import pandas as pd
import pytest

from models.dashboard_summary import build_dashboard_summary, project_readiness_snapshot
from ui.pages.dashboard import _build_dashboard_v2_summary


pytestmark = pytest.mark.smoke


def test_legacy_dashboard_summary_import_delegates_to_headless_builder() -> None:
    assert _build_dashboard_v2_summary is build_dashboard_summary


def test_readiness_snapshot_projection_overrides_conflicting_dashboard_metrics() -> None:
    current_status = {
        "readiness": 54.0,
        "ctl": 14.8,
        "atl": 37.4,
        "tsb": -22.6,
        "hrv": 32.0,
        "state_label": "Сильная усталость",
        "tone": "danger",
        "signals": {"source": "test"},
    }
    snapshot = {
        "score": 61.1,
        "status": "ready",
        "stale": False,
        "tsb": {"ctl": 18.4, "atl": 37.7, "tsb": -19.2},
        "factors": [{"key": "hrv", "raw_value": 32.0}],
    }

    projected = project_readiness_snapshot(current_status, snapshot)

    assert projected["readiness"] == 61.1
    assert projected["ctl"] == 18.4
    assert projected["atl"] == 37.7
    assert projected["tsb"] == -19.2
    assert projected["hrv"] == 32.0
    assert projected["state_label"] == "Контролируемая готовность"
    assert projected["tone"] == "neutral"
    assert projected["signals"]["source"] == "test"
    assert projected["signals"]["readiness"]["source"] == "canonical_snapshot"
    assert projected["signals"]["load"]["tsb"] == -19.2
    assert current_status["readiness"] == 54.0
    assert current_status["signals"] == {"source": "test"}


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

    assert summary["today"]["state_label"] == "Контролируемая нагрузка"
    assert summary["today"]["readiness"] == 70
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
