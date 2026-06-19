from __future__ import annotations

from datetime import date

import pytest

from models.planning_execution import (
    build_execution_plan_adjustment,
    summarize_execution_corrective_microcycle,
    build_execution_reconciliation_rows,
    rebuild_goal_plan_with_adjustment,
    summarize_execution_reconciliation_rows,
    summarize_execution_weekly_review_rows,
)
from models.training_planner import build_daily_session_templates, expand_weekly_to_daily_triathlon
from ui.components.execution_feedback import (
    _resolve_actual_tss_value,
    _sanitize_actual_tss_value,
)


pytestmark = pytest.mark.smoke


def _sample_goal_plan() -> dict[str, object]:
    daily_plan, weekly_summary = expand_weekly_to_daily_triathlon(
        [220, 240, 210],
        ["Base", "Build", "Peak"],
        "Олимпийка",
        date(2026, 6, 15),
        goal_type="Триатлон",
        load_state="balanced",
    )
    session_templates = build_daily_session_templates(
        daily_plan,
        weekly_summary,
        "Триатлон",
        "Олимпийка",
    )
    return {
        "goal_type": "Триатлон",
        "distance": "Олимпийка",
        "weeks_to_race": 8,
        "start_week": date(2026, 6, 15),
        "weekly_tss_plan": [220, 240, 210],
        "base_weekly_tss_plan": [220, 240, 210],
        "phases": ["Base", "Build", "Peak"],
        "daily_plan": daily_plan,
        "session_templates": session_templates,
        "weekly_summary": weekly_summary,
        "constraint_summary": {
            "available_hours": 8.5,
            "available_day_indices": [1, 3, 5],
            "available_day_labels": ["Вт", "Чт", "Сб"],
            "available_day_count": 3,
            "recommended_days": 6,
            "interruption_type": "none",
            "interruption_label": "Нет",
            "interruption_weeks": 0,
            "catch_up_strategy": "catch_up",
            "current_tsb": -6.0,
            "current_ctl": 60.0,
            "current_atl": 68.0,
            "load_state_label": "Нейтральный старт",
            "notes": [],
        },
        "planner_mix": None,
        "planner_weights": None,
    }


def _positive_tss_row_indices(rows: list[dict[str, object]]) -> list[int]:
    return [
        index
        for index, row in enumerate(rows)
        if int(row.get("planned_total_tss", 0) or 0) > 0
    ]


def test_day_level_execution_rows_can_build_reduced_local_replan_payload():
    goal_plan = _sample_goal_plan()
    rows = build_execution_reconciliation_rows(goal_plan, weeks=1)
    positive_rows = _positive_tss_row_indices(rows)

    rows[positive_rows[0]]["outcome"] = "missed"
    rows[positive_rows[1]]["outcome"] = "reduced"
    rows[positive_rows[1]]["actual_total_tss"] = max(
        0,
        int(rows[positive_rows[1]]["planned_total_tss"]) - 15,
    )

    summary = summarize_execution_reconciliation_rows(rows)
    payload = build_execution_plan_adjustment(goal_plan, rows, weeks=1)
    rebuilt = rebuild_goal_plan_with_adjustment(goal_plan, payload)

    assert summary["status"] == "reduced"
    assert summary["changed_day_count"] == 2
    assert summary["delta_tss"] < 0
    assert payload["execution_reconciliation"]["changed_day_count"] == 2
    assert payload["completion_share"] < 1.0
    assert "checkpoint: факт" in rebuilt["weekly_summary"][0]["adjustment_note"]
    corrective_microcycle = summarize_execution_corrective_microcycle(
        rebuilt["constraint_summary"]["plan_adjustment"].get("execution_corrective_microcycle")
    )
    assert corrective_microcycle is not None
    assert corrective_microcycle["headline"]
    assert corrective_microcycle["sessions"]
    assert corrective_microcycle["today_action"]


def test_day_level_execution_rows_can_escalate_to_unavailable_status():
    goal_plan = _sample_goal_plan()
    rows = build_execution_reconciliation_rows(goal_plan, weeks=1)
    positive_rows = _positive_tss_row_indices(rows)

    rows[positive_rows[0]]["outcome"] = "unavailable"
    rows[positive_rows[1]]["outcome"] = "unavailable"

    summary = summarize_execution_reconciliation_rows(rows)
    payload = build_execution_plan_adjustment(goal_plan, rows, weeks=1)

    assert summary["status"] == "unavailable"
    assert summary["unavailable_day_count"] == 2
    assert payload["status"] == "unavailable"
    assert payload["execution_reconciliation"]["status"] == "unavailable"


def test_execution_weekly_review_detects_lost_key_and_long_sessions():
    goal_plan = _sample_goal_plan()
    rows = build_execution_reconciliation_rows(goal_plan, weeks=1)
    quality_idx = next(
        index
        for index, row in enumerate(rows)
        if row.get("session_role") == "quality" and int(row.get("planned_total_tss", 0) or 0) > 0
    )
    long_idx = next(
        index
        for index, row in enumerate(rows)
        if row.get("session_role") == "long" and int(row.get("planned_total_tss", 0) or 0) > 0
    )

    rows[quality_idx]["outcome"] = "missed"
    rows[long_idx]["outcome"] = "unavailable"

    weekly_review = summarize_execution_weekly_review_rows(
        rows,
        current_response_strategy="catch_up",
    )
    payload = build_execution_plan_adjustment(
        goal_plan,
        rows,
        weeks=1,
        response_strategy_override="catch_up",
    )

    assert weekly_review["recommended_response_strategy"] == "protect_recovery"
    assert any(item["code"] == "missed_key_session" for item in weekly_review["deviations"])
    assert any(item["code"] == "lost_long_session" for item in weekly_review["deviations"])
    assert payload["execution_weekly_review"]["headline"] == weekly_review["headline"]
    assert payload["execution_weekly_review"]["selected_response_strategy"] == "catch_up"
    assert payload["catch_up_strategy_override"] == "catch_up"


def test_rebuild_goal_plan_honors_execution_response_strategy_override():
    goal_plan = _sample_goal_plan()
    goal_plan["constraint_summary"]["catch_up_strategy"] = "protect_recovery"
    rows = build_execution_reconciliation_rows(goal_plan, weeks=1)
    positive_rows = _positive_tss_row_indices(rows)
    rows[positive_rows[0]]["outcome"] = "reduced"
    rows[positive_rows[0]]["actual_total_tss"] = max(
        0,
        int(rows[positive_rows[0]]["planned_total_tss"]) - 10,
    )

    payload = build_execution_plan_adjustment(
        goal_plan,
        rows,
        weeks=1,
        response_strategy_override="catch_up",
    )
    rebuilt = rebuild_goal_plan_with_adjustment(goal_plan, payload)

    assert rebuilt["constraint_summary"]["catch_up_strategy"] == "catch_up"
    assert rebuilt["constraint_summary"]["plan_adjustment"]["catch_up_strategy_override"] == "catch_up"
    corrective_microcycle = rebuilt["constraint_summary"]["plan_adjustment"]["execution_corrective_microcycle"]
    assert corrective_microcycle["selected_response_strategy"] == "catch_up"
    assert corrective_microcycle["window_day_count"] >= 1


def test_execution_feedback_widget_state_is_clamped_to_current_planned_tss():
    assert _sanitize_actual_tss_value(0, 41) == 0
    assert _sanitize_actual_tss_value(35, 41) == 35
    assert _sanitize_actual_tss_value(35, -5) == 0


def test_execution_feedback_actual_tss_value_tracks_selected_outcome():
    assert _resolve_actual_tss_value(35, "as_planned", 5) == 35
    assert _resolve_actual_tss_value(35, "missed", 35) == 0
    assert _resolve_actual_tss_value(35, "unavailable", 35) == 0
    assert _resolve_actual_tss_value(35, "reduced", 41) == 35
    assert _resolve_actual_tss_value(0, "reduced", 41) == 0
