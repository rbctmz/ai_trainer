from __future__ import annotations

from datetime import date, datetime

import pytest

from models.training_planner import (
    apply_planning_constraints,
    build_daily_session_templates,
    create_ics_from_daily,
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


def test_expand_weekly_plan_adds_recovery_aware_structure_metadata():
    daily_plan, weekly_summary = expand_weekly_to_daily_triathlon(
        [280],
        ["Build"],
        "Полумарафон",
        date(2026, 6, 8),
        mix_overrides={"Build": {"run": 1.0, "bike": 0.0, "swim": 0.0}},
        available_day_indices=[0, 1, 2, 3, 4, 5, 6],
        goal_type="Бег",
        load_state="fatigued",
    )

    roles = weekly_summary[0]["day_roles"]
    totals = [day_total for _dt, day_total, _parts in daily_plan]
    long_day = roles.index("long")
    recovery_days = [idx for idx, role in enumerate(roles) if role == "recovery"]

    assert roles.count("long") == 1
    assert roles.count("quality") == 1
    assert len(recovery_days) >= 1
    assert weekly_summary[0]["structure_summary"]
    assert "длительная" in weekly_summary[0]["key_sessions"]
    assert totals[long_day] > max(totals[idx] for idx in recovery_days)


def test_build_daily_session_templates_aligns_metadata_with_daily_plan():
    daily_plan, weekly_summary = expand_weekly_to_daily_triathlon(
        [220],
        ["Build"],
        "Олимпийка",
        date(2026, 6, 8),
        goal_type="Триатлон",
        load_state="balanced",
    )

    templates = build_daily_session_templates(daily_plan, weekly_summary, "Триатлон", "Олимпийка")

    assert len(templates) == len(daily_plan)
    quality_idx = weekly_summary[0]["day_roles"].index("quality")
    template = templates[quality_idx]
    assert template["session_role"] == "quality"
    assert template["phase"] == "Build"
    assert template["sport"] in {"run", "bike", "swim"}
    assert template["duration_minutes"] >= 30
    assert "Триатлон —" in template["export_name"] or "Триатлон Олимпийка" in template["export_name"]
    assert "Фокус:" in template["description"]


def test_create_ics_from_daily_uses_session_template_metadata():
    daily_plan = [
        (datetime(2026, 6, 15), 72.0, {"run": 18.0, "bike": 54.0, "swim": 0.0}),
    ]
    session_templates = [
        {
            "export_name": "Триатлон Олимпийка — Качество • вело",
            "description": "План из AI Trainer\nФокус: Качество • вело",
            "duration_minutes": 95,
        }
    ]

    ics = create_ics_from_daily(daily_plan, session_templates=session_templates)

    assert "SUMMARY:Триатлон Олимпийка — Качество • вело (TSS 72)" in ics
    assert "DESCRIPTION:План из AI Trainer" in ics
    assert "DTEND:20260615T083500" in ics


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


def test_apply_planning_constraints_locally_replans_after_skipped_sessions():
    plan, details, summary = apply_planning_constraints(
        [200, 200, 200, 180],
        ["Base", "Build", "Build", "Taper"],
        "Бег",
        available_hours=10.0,
        available_day_indices=[0, 1, 2, 3, 4],
        catch_up_strategy="catch_up",
        current_tsb=2.0,
        plan_adjustment={
            "status": "skipped",
            "weeks": 1,
            "missed_sessions": 2,
        },
    )

    assert plan[0] == 130
    assert plan[1] == 215
    assert plan[2] == 215
    assert summary["plan_adjustment"]["status"] == "skipped"
    assert summary["plan_adjustment_loss_tss"] == 70
    assert summary["plan_adjustment_recovered_tss"] == 30
    assert "checkpoint: пропущено 2 сесс." in details[0]["adjustment_note"]
    assert any("локальный возврат +" in detail["adjustment_note"] for detail in details[1:3])
