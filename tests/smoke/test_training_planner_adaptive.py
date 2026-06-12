from __future__ import annotations

from datetime import date

import pytest

from models.training_planner import (
    apply_planning_constraints,
    expand_weekly_to_daily_triathlon,
    summarize_availability,
)


pytestmark = pytest.mark.smoke


def test_summarize_availability_softens_capacity_for_fewer_days():
    summary = summarize_availability("Триатлон", 8.0, [1, 3, 5])

    assert summary["available_day_labels"] == ["Вт", "Чт", "Сб"]
    assert summary["recommended_days"] == 6
    assert summary["weekly_capacity_tss"] == 220


def test_expand_weekly_plan_respects_available_days_only():
    daily_plan, _weekly_summary = expand_weekly_to_daily_triathlon(
        [210],
        ["Base"],
        "Олимпийка",
        date(2026, 6, 8),
        mix_overrides={"Base": {"run": 1.0, "bike": 0.0, "swim": 0.0}},
        available_day_indices=[1, 3, 5],
    )

    totals = [day_total for _dt, day_total, _parts in daily_plan]
    assert totals[0] == 0.0
    assert totals[2] == 0.0
    assert totals[4] == 0.0
    assert totals[6] == 0.0
    assert totals[1] > 0.0
    assert totals[3] > 0.0
    assert totals[5] > 0.0


def test_apply_planning_constraints_protects_recovery_after_illness():
    plan, details, summary = apply_planning_constraints(
        [300, 320, 340, 280],
        ["Base", "Base", "Build", "Taper"],
        "Триатлон",
        available_hours=6.0,
        available_day_indices=[1, 3, 5],
        interruption_type="illness",
        interruption_weeks=1,
        catch_up_strategy="protect_recovery",
        current_tsb=-20.0,
    )

    assert plan[0] == 60
    assert plan[1] == 165
    assert summary["weekly_capacity_tss"] == 165
    assert summary["recovered_tss"] == 0
    assert "без компенсации нагрузки" in details[0]["adjustment_note"]


def test_apply_planning_constraints_can_catch_up_after_holiday():
    plan, details, summary = apply_planning_constraints(
        [160, 160, 160, 120],
        ["Base", "Build", "Build", "Taper"],
        "Бег",
        available_hours=10.0,
        available_day_indices=[0, 1, 2, 3, 4],
        interruption_type="holiday",
        interruption_weeks=1,
        catch_up_strategy="catch_up",
        current_tsb=5.0,
    )

    assert plan[0] < 160
    assert summary["recovered_tss"] > 0
    assert any("возврат +" in detail["adjustment_note"] for detail in details[1:3])


def test_apply_planning_constraints_softens_early_weeks_when_starting_deeply_fatigued():
    plan, details, summary = apply_planning_constraints(
        [240, 260, 280, 200],
        ["Base", "Build", "Build", "Taper"],
        "Триатлон",
        available_hours=20.0,
        available_day_indices=[0, 1, 2, 3, 4, 5],
        current_ctl=60.0,
        current_atl=100.0,
        current_tsb=-28.0,
    )

    assert plan[:3] == [180, 220, 265]
    assert summary["load_state"] == "deep_fatigue"
    assert summary["load_guard_loss_tss"] == 115
    assert "Стартовое состояние: глубокая усталость" in " ".join(summary["notes"])
    assert "Глубокая усталость" in details[0]["adjustment_note"]


def test_apply_planning_constraints_recovers_more_after_holiday_when_starting_fresh():
    fresh_plan, _fresh_details, fresh_summary = apply_planning_constraints(
        [160, 160, 160, 120],
        ["Base", "Build", "Build", "Taper"],
        "Бег",
        available_hours=10.0,
        available_day_indices=[0, 1, 2, 3, 4],
        interruption_type="holiday",
        interruption_weeks=1,
        catch_up_strategy="catch_up",
        current_ctl=70.0,
        current_atl=55.0,
        current_tsb=14.0,
    )
    tired_plan, _tired_details, tired_summary = apply_planning_constraints(
        [160, 160, 160, 120],
        ["Base", "Build", "Build", "Taper"],
        "Бег",
        available_hours=10.0,
        available_day_indices=[0, 1, 2, 3, 4],
        interruption_type="holiday",
        interruption_weeks=1,
        catch_up_strategy="catch_up",
        current_ctl=70.0,
        current_atl=92.0,
        current_tsb=-12.0,
    )

    assert fresh_summary["load_state"] == "fresh"
    assert tired_summary["load_state"] == "fatigued"
    assert fresh_summary["recovered_tss"] > tired_summary["recovered_tss"]
    assert sum(fresh_plan) > sum(tired_plan)
