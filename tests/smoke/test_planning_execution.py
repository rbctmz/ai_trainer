from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from models.planning_execution import (
    build_execution_plan_adjustment,
    summarize_execution_corrective_microcycle,
    summarize_execution_adaptation_pressure,
    build_execution_reconciliation_rows,
    rebuild_goal_plan_with_adjustment,
    summarize_execution_reconciliation_rows,
    summarize_execution_weekly_review_rows,
)
from models.planning_near_term import build_near_term_edit_seed_from_goal_plans
from models.training_planner import build_daily_session_templates, expand_weekly_to_daily_triathlon
from models.workout_catalog import CATALOG_VERSION
from ui.components.execution_feedback import (
    _build_follow_up_preview_rows,
    _resolve_execution_primary_action,
    _split_execution_row_states,
    _partition_execution_row_states,
    _resolve_actual_tss_value,
    _row_state_needs_attention,
    _sanitize_actual_tss_value,
    _sync_pending_widget_value,
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

    assert rows[0]["date_label"] == "Пн 15.06"
    assert rows[0]["phase_label"] == "База"
    assert rows[0]["sport_label"] == "вело"
    # Issue #205 M3b: the slot scheduler deterministically opens the week with
    # the quality bike, spaced maximally from the Saturday long ride.
    assert rows[0]["session_role_label"] == "Качество"

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
    assert payload["execution_adaptation_pressure"]["follow_up_mode"] in {"hold", "protect_recovery", "catch_up"}
    assert "checkpoint: факт" in rebuilt["weekly_summary"][0]["adjustment_note"]
    assert rebuilt["catalog_version"] == CATALOG_VERSION
    assert any(
        template.get("materialization_status") == "materialized"
        for template in rebuilt["session_templates"]
    )
    assert all(
        template.get("definition_snapshot")
        for template in rebuilt["session_templates"]
        if template.get("materialization_status") == "materialized"
    )
    corrective_microcycle = summarize_execution_corrective_microcycle(
        rebuilt["constraint_summary"]["plan_adjustment"].get("execution_corrective_microcycle")
    )
    assert corrective_microcycle is not None
    assert corrective_microcycle["headline"]
    assert corrective_microcycle["sessions"]
    assert corrective_microcycle["today_action"]
    assert corrective_microcycle["today_action"].startswith("Пн ")


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
    assert payload["execution_adaptation_pressure"]["follow_up_mode"] == "protect_recovery"


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


def test_execution_adaptation_pressure_can_hold_next_week_even_with_catch_up_choice():
    goal_plan = _sample_goal_plan()
    rows = build_execution_reconciliation_rows(goal_plan, weeks=1)
    quality_idx = next(
        index
        for index, row in enumerate(rows)
        if row.get("session_role") == "quality" and int(row.get("planned_total_tss", 0) or 0) > 0
    )
    rows[quality_idx]["outcome"] = "reduced"
    rows[quality_idx]["actual_total_tss"] = max(
        0,
        int(rows[quality_idx]["planned_total_tss"]) - 15,
    )

    payload = build_execution_plan_adjustment(
        goal_plan,
        rows,
        weeks=1,
        response_strategy_override="catch_up",
    )
    pressure = summarize_execution_adaptation_pressure(payload["execution_adaptation_pressure"])
    rebuilt = rebuild_goal_plan_with_adjustment(goal_plan, payload)

    assert pressure is not None
    assert pressure["follow_up_mode"] == "hold"
    assert pressure["growth_cap_tss_per_week"] == 25
    assert rebuilt["constraint_summary"]["execution_adaptation_pressure"]["follow_up_mode"] == "hold"
    assert rebuilt["weekly_tss_plan"][1] <= rebuilt["weekly_tss_plan"][0] + 25
    assert "Execution drift pressure:" in " ".join(rebuilt["constraint_summary"]["notes"])


def test_execution_adaptation_pressure_override_can_relax_rebound_mode_before_save():
    goal_plan = _sample_goal_plan()
    rows = build_execution_reconciliation_rows(goal_plan, weeks=1)
    quality_idx = next(
        index
        for index, row in enumerate(rows)
        if row.get("session_role") == "quality" and int(row.get("planned_total_tss", 0) or 0) > 0
    )
    rows[quality_idx]["outcome"] = "reduced"
    rows[quality_idx]["actual_total_tss"] = max(
        0,
        int(rows[quality_idx]["planned_total_tss"]) - 15,
    )

    recommended_payload = build_execution_plan_adjustment(
        goal_plan,
        rows,
        weeks=1,
        response_strategy_override="catch_up",
    )
    override_payload = build_execution_plan_adjustment(
        goal_plan,
        rows,
        weeks=1,
        response_strategy_override="catch_up",
        follow_up_mode_override="catch_up",
    )
    recommended_rebuilt = rebuild_goal_plan_with_adjustment(goal_plan, recommended_payload)
    override_rebuilt = rebuild_goal_plan_with_adjustment(goal_plan, override_payload)
    override_pressure = summarize_execution_adaptation_pressure(
        override_payload["execution_adaptation_pressure"]
    )

    assert override_pressure is not None
    assert override_pressure["recommended_follow_up_mode"] == "hold"
    assert override_pressure["follow_up_mode"] == "catch_up"
    assert override_pressure["is_user_override"] is True
    assert override_pressure["growth_cap_tss_per_week"] == 40
    assert override_rebuilt["weekly_tss_plan"][2] > recommended_rebuilt["weekly_tss_plan"][2]
    assert override_rebuilt["weekly_tss_plan"][2] <= override_rebuilt["weekly_tss_plan"][1] + 40


def test_execution_adaptation_pressure_can_force_protective_rebound_cap():
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

    payload = build_execution_plan_adjustment(
        goal_plan,
        rows,
        weeks=1,
        response_strategy_override="catch_up",
    )
    pressure = summarize_execution_adaptation_pressure(payload["execution_adaptation_pressure"])
    rebuilt = rebuild_goal_plan_with_adjustment(goal_plan, payload)

    assert pressure is not None
    assert pressure["follow_up_mode"] == "protect_recovery"
    assert pressure["growth_cap_tss_per_week"] == 15
    assert rebuilt["weekly_tss_plan"][1] <= rebuilt["weekly_tss_plan"][0] + 15


def test_follow_up_preview_rows_focus_on_post_window_weeks():
    goal_plan = _sample_goal_plan()
    rows = build_execution_reconciliation_rows(goal_plan, weeks=1)
    quality_idx = next(
        index
        for index, row in enumerate(rows)
        if row.get("session_role") == "quality" and int(row.get("planned_total_tss", 0) or 0) > 0
    )
    rows[quality_idx]["outcome"] = "reduced"
    rows[quality_idx]["actual_total_tss"] = max(
        0,
        int(rows[quality_idx]["planned_total_tss"]) - 15,
    )

    payload = build_execution_plan_adjustment(
        goal_plan,
        rows,
        weeks=1,
        response_strategy_override="catch_up",
        follow_up_mode_override="catch_up",
    )
    rebuilt = rebuild_goal_plan_with_adjustment(goal_plan, payload)
    pressure = summarize_execution_adaptation_pressure(payload["execution_adaptation_pressure"])

    preview_rows = _build_follow_up_preview_rows(
        goal_plan,
        rebuilt,
        affected_weeks=1,
        horizon_weeks=int(pressure["rebuild_horizon_weeks"]),
    )

    assert preview_rows
    assert preview_rows[0]["Неделя"].startswith("Неделя 2")
    assert "Станет TSS" in preview_rows[0]
    assert preview_rows[0]["Комментарий"]


def test_execution_replan_can_open_corrective_microcycle_as_near_term_draft():
    goal_plan = _sample_goal_plan()
    rows = build_execution_reconciliation_rows(goal_plan, weeks=1)
    positive_rows = _positive_tss_row_indices(rows)
    rows[positive_rows[0]]["outcome"] = "missed"
    rows[positive_rows[1]]["outcome"] = "reduced"
    rows[positive_rows[1]]["actual_total_tss"] = max(
        0,
        int(rows[positive_rows[1]]["planned_total_tss"]) - 15,
    )

    payload = build_execution_plan_adjustment(
        goal_plan,
        rows,
        weeks=1,
        response_strategy_override="protect_recovery",
    )
    rebuilt = rebuild_goal_plan_with_adjustment(goal_plan, payload)
    corrective_microcycle = summarize_execution_corrective_microcycle(
        rebuilt["constraint_summary"]["plan_adjustment"].get("execution_corrective_microcycle")
    )

    seed = build_near_term_edit_seed_from_goal_plans(
        goal_plan,
        rebuilt,
        horizon_days=7,
        post_edit_strategy=str(corrective_microcycle["selected_response_strategy"]),
        source_label=str(corrective_microcycle["headline"]),
    )

    assert seed is not None
    assert seed["source_label"] == corrective_microcycle["headline"]
    assert seed["post_edit_strategy"] == corrective_microcycle["selected_response_strategy"]
    assert seed["draft_summary"]["has_changes"] is True
    assert seed["draft_summary"]["changed_day_count"] >= 1


def test_execution_reconciliation_rows_prefill_from_same_day_garmin_activity_dataframe():
    goal_plan = _sample_goal_plan()
    baseline_rows = build_execution_reconciliation_rows(goal_plan, weeks=1)
    target_idx = next(
        index
        for index, row in enumerate(baseline_rows)
        if row.get("sport") in {"run", "bike", "swim"} and int(row.get("planned_total_tss", 0) or 0) > 0
    )
    target_row = baseline_rows[target_idx]
    recent_activities = pd.DataFrame(
        [
            {
                "date": target_row["date"],
                "sport": target_row["sport"],
                "duration_minutes": int(target_row["planned_duration_minutes"]),
                "tss": max(1, int(target_row["planned_total_tss"]) - 5),
            }
        ]
    )

    rows = build_execution_reconciliation_rows(
        goal_plan,
        weeks=1,
        recent_activities=recent_activities,
    )

    assert rows[target_idx]["activity_prefill_source"] == "garmin_local"
    assert rows[target_idx]["activity_prefill_outcome"] == "as_planned"
    assert rows[target_idx]["actual_total_tss"] == int(target_row["planned_total_tss"])
    assert "Garmin sync:" in str(rows[target_idx]["activity_prefill_note"])


def test_execution_reconciliation_rows_prefill_reduced_when_garmin_load_is_lower():
    goal_plan = _sample_goal_plan()
    baseline_rows = build_execution_reconciliation_rows(goal_plan, weeks=1)
    target_idx = next(
        index
        for index, row in enumerate(baseline_rows)
        if row.get("sport") in {"run", "bike", "swim"} and int(row.get("planned_total_tss", 0) or 0) >= 30
    )
    target_row = baseline_rows[target_idx]
    expected_actual_tss = max(1, int(target_row["planned_total_tss"] * 0.5))
    recent_activities = [
        {
            "date": target_row["date"],
            "sport": target_row["sport"],
            "duration_minutes": max(10, int(target_row["planned_duration_minutes"] * 0.5)),
            "tss": expected_actual_tss,
        }
    ]

    rows = build_execution_reconciliation_rows(
        goal_plan,
        weeks=1,
        recent_activities=recent_activities,
    )

    assert rows[target_idx]["activity_prefill_source"] == "garmin_local"
    assert rows[target_idx]["activity_prefill_outcome"] == "reduced"
    assert rows[target_idx]["actual_total_tss"] == expected_actual_tss


def test_execution_reconciliation_rows_ignore_same_day_activity_with_other_sport():
    goal_plan = _sample_goal_plan()
    baseline_rows = build_execution_reconciliation_rows(goal_plan, weeks=1)
    target_idx = next(
        index
        for index, row in enumerate(baseline_rows)
        if row.get("sport") in {"run", "bike", "swim"} and int(row.get("planned_total_tss", 0) or 0) > 0
    )
    target_row = baseline_rows[target_idx]
    other_sport = "swim" if target_row["sport"] != "swim" else "bike"
    recent_activities = [
        {
            "date": target_row["date"],
            "sport": other_sport,
            "duration_minutes": int(target_row["planned_duration_minutes"]),
            "tss": int(target_row["planned_total_tss"]),
        }
    ]

    rows = build_execution_reconciliation_rows(
        goal_plan,
        weeks=1,
        recent_activities=recent_activities,
    )

    assert "activity_prefill_source" not in rows[target_idx]
    assert rows[target_idx]["outcome"] == "as_planned"
    assert rows[target_idx]["actual_total_tss"] == int(target_row["planned_total_tss"])


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


def test_execution_feedback_pending_widget_value_applies_before_widget_init():
    session_state = {"dashboard_execution_feedback_response_strategy_pending": "Беречь восстановление"}

    resolved = _sync_pending_widget_value(
        session_state,
        "dashboard_execution_feedback_response_strategy",
        default_value="Наверстать аккуратно",
    )

    assert resolved == "Беречь восстановление"
    assert session_state["dashboard_execution_feedback_response_strategy"] == "Беречь восстановление"
    assert "dashboard_execution_feedback_response_strategy_pending" not in session_state


def test_execution_feedback_row_state_detects_prefill_and_real_deviation():
    quiet_state = {
        "row": {
            "planned_total_tss": 40,
        },
        "outcome_code": "as_planned",
        "resolved_actual_tss": 40,
    }
    prefilled_state = {
        "row": {
            "planned_total_tss": 40,
            "activity_prefill_source": "garmin_local",
        },
        "outcome_code": "as_planned",
        "resolved_actual_tss": 40,
    }
    changed_state = {
        "row": {
            "planned_total_tss": 40,
        },
        "outcome_code": "reduced",
        "resolved_actual_tss": 30,
    }

    assert _row_state_needs_attention(quiet_state) is False
    assert _row_state_needs_attention(prefilled_state) is True
    assert _row_state_needs_attention(changed_state) is True


def test_execution_feedback_partition_separates_deviation_prefill_and_quiet_rows():
    row_states = [
        {
            "row": {"index": 0, "planned_total_tss": 40},
            "outcome_code": "as_planned",
            "resolved_actual_tss": 40,
        },
        {
            "row": {"index": 1, "planned_total_tss": 55, "activity_prefill_source": "garmin_local"},
            "outcome_code": "as_planned",
            "resolved_actual_tss": 55,
        },
        {
            "row": {"index": 2, "planned_total_tss": 60},
            "outcome_code": "missed",
            "resolved_actual_tss": 0,
        },
        {
            "row": {"index": 3, "planned_total_tss": 25},
            "outcome_code": "as_planned",
            "resolved_actual_tss": 25,
        },
    ]

    deviation_states, prefilled_states, quiet_states = _partition_execution_row_states(row_states)

    assert [item["row"]["index"] for item in deviation_states] == [2]
    assert [item["row"]["index"] for item in prefilled_states] == [1]
    assert [item["row"]["index"] for item in quiet_states] == [0, 3]


def test_execution_feedback_split_can_focus_quiet_day_above_signal_groups():
    row_states = [
        {
            "row": {"index": 0, "date": "2026-06-22", "planned_total_tss": 40},
            "outcome_code": "as_planned",
            "resolved_actual_tss": 40,
        },
        {
            "row": {"index": 1, "date": "2026-06-23", "planned_total_tss": 55, "activity_prefill_source": "garmin_local"},
            "outcome_code": "as_planned",
            "resolved_actual_tss": 55,
        },
        {
            "row": {"index": 2, "date": "2026-06-24", "planned_total_tss": 60},
            "outcome_code": "missed",
            "resolved_actual_tss": 0,
        },
    ]

    focused_state, deviation_states, prefilled_states, quiet_states = _split_execution_row_states(
        row_states,
        focused_date="2026-06-22",
    )

    assert focused_state is not None
    assert focused_state["row"]["index"] == 0
    assert [item["row"]["index"] for item in deviation_states] == [2]
    assert [item["row"]["index"] for item in prefilled_states] == [1]
    assert quiet_states == []


def test_execution_primary_action_prefers_explicit_garmin_confirmation_for_clean_window():
    assert _resolve_execution_primary_action(
        real_deviation_count=0,
        garmin_confirmation_count=2,
        has_corrective_microcycle=False,
    ) == {
        "label": "✅ Подтвердить окно по Garmin",
        "mode": "confirm_garmin_window",
    }
    assert _resolve_execution_primary_action(
        real_deviation_count=1,
        garmin_confirmation_count=2,
        has_corrective_microcycle=True,
    ) == {
        "label": "♻️ Применить local replan как есть",
        "mode": "apply_replan",
    }
