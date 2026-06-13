from __future__ import annotations

from datetime import date, datetime

import pytest

from ui.pages.planning import (
    _build_daily_session_rows,
    _build_plan_explainability,
    _resolve_target_weekly_tss_control,
)


pytestmark = pytest.mark.smoke


def test_build_plan_explainability_summarizes_adaptive_changes():
    explain = _build_plan_explainability(
        {
            "weekly_tss_plan": [180, 220, 240],
            "base_weekly_tss_plan": [240, 240, 240],
            "phases": ["Base", "Build", "Peak"],
            "weekly_summary": [
                {
                    "week_start": date(2026, 6, 15),
                    "adjustment_note": "потолок 220 TSS",
                    "structure_summary": "1 качеств. дн., 1 восстановит. дн., длительная: Сб",
                },
                {"week_start": date(2026, 6, 22), "adjustment_note": "возврат +20 TSS"},
                {"week_start": date(2026, 6, 29), "adjustment_note": "—"},
            ],
            "constraint_summary": {
                "weekly_capacity_tss": 220,
                "available_hours": 8.5,
                "available_day_labels": ["Вт", "Чт", "Сб"],
                "available_day_count": 3,
                "recommended_days": 6,
                "interruption_label": "Отпуск",
                "interruption_weeks": 1,
                "catch_up_strategy": "catch_up",
                "recovered_tss": 20,
                "capacity_loss_tss": 60,
                "interruption_loss_tss": 40,
                "notes": ["Отпуск на 1 нед.", "Стратегия «Наверстать аккуратно» вернула 20 из 25 TSS"],
            },
        }
    )

    assert explain["headline"].startswith("План сначала снижает нагрузку")
    assert explain["summary_notes"][0].startswith("Структура первой недели:")
    assert explain["peak_before"] == 240
    assert explain["peak_after"] == 240
    assert explain["total_delta"] == -80
    assert explain["changed_weeks"] == 2
    assert explain["availability_days"] == "Вт, Чт, Сб"
    assert explain["catch_up_label"] == "Наверстать аккуратно"
    assert explain["comparison_rows"][0]["Базовый TSS"] == 240
    assert explain["comparison_rows"][1]["Почему"] == "возврат +20 TSS"


def test_build_plan_explainability_detects_nearly_unchanged_plan():
    explain = _build_plan_explainability(
        {
            "weekly_tss_plan": [180, 200],
            "base_weekly_tss_plan": [180, 200],
            "phases": ["Base", "Build"],
            "weekly_summary": [
                {"week_start": date(2026, 7, 6), "adjustment_note": "—"},
                {"week_start": date(2026, 7, 13), "adjustment_note": "—"},
            ],
            "constraint_summary": {
                "weekly_capacity_tss": 220,
                "available_hours": 10.0,
                "available_day_labels": ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб"],
                "available_day_count": 6,
                "recommended_days": 6,
                "interruption_label": "Нет",
                "interruption_weeks": 0,
                "catch_up_strategy": "protect_recovery",
                "recovered_tss": 0,
                "capacity_loss_tss": 0,
                "interruption_loss_tss": 0,
                "notes": [],
            },
        }
    )

    assert "почти не менять базовый план" in explain["headline"]
    assert explain["changed_weeks"] == 0
    assert explain["total_delta"] == 0


def test_target_tss_control_avoids_equal_slider_bounds():
    control = _resolve_target_weekly_tss_control(
        auto_suggested=500,
        t_min=500,
        t_max=700,
        availability_cap_tss=500,
    )

    assert control["is_fixed"] is True
    assert control["value"] == 500
    assert control["reason"] == "single_value"


def test_target_tss_control_can_lock_to_achievable_cap_below_goal_floor():
    control = _resolve_target_weekly_tss_control(
        auto_suggested=620,
        t_min=500,
        t_max=700,
        availability_cap_tss=400,
    )

    assert control["is_fixed"] is True
    assert control["value"] == 400
    assert control["reason"] == "availability_cap"


def test_build_daily_session_rows_uses_week_structure_metadata():
    rows = _build_daily_session_rows(
        {
            "daily_plan": [
                (datetime(2026, 6, 15), 0.0, {"run": 0.0, "bike": 0.0, "swim": 0.0}),
                (datetime(2026, 6, 16), 55.0, {"run": 55.0, "bike": 0.0, "swim": 0.0}),
            ],
            "weekly_summary": [
                {
                    "day_roles": ["off", "quality", "easy", "easy", "recovery", "long", "easy"],
                    "day_focuses": [
                        "Отдых",
                        "Качество • бег",
                        "Легкая • бег",
                        "Легкая • бег",
                        "Восстановление • бег",
                        "Длительная • бег",
                        "Легкая • бег",
                    ],
                }
            ],
        }
    )

    assert rows[0]["session_role"] == "off"
    assert rows[1]["session_role"] == "quality"
    assert rows[1]["session_focus"] == "Качество • бег"


def test_build_daily_session_rows_prefers_session_templates_when_present():
    rows = _build_daily_session_rows(
        {
            "daily_plan": [
                (datetime(2026, 6, 15), 55.0, {"run": 0.0, "bike": 55.0, "swim": 0.0}),
            ],
            "weekly_summary": [
                {
                    "phase": "Build",
                    "day_roles": ["quality", "easy", "easy", "easy", "recovery", "long", "off"],
                    "day_focuses": ["Качество • бег", "—", "—", "—", "—", "—", "—"],
                }
            ],
            "session_templates": [
                {
                    "phase": "Build",
                    "sport": "bike",
                    "session_role": "quality",
                    "session_focus": "Качество • вело",
                    "export_name": "Триатлон Олимпийка — Качество • вело",
                    "duration_minutes": 90,
                }
            ],
        }
    )

    assert rows[0]["phase"] == "Build"
    assert rows[0]["sport"] == "bike"
    assert rows[0]["session_focus"] == "Качество • вело"
    assert rows[0]["session_name"] == "Триатлон Олимпийка — Качество • вело"
    assert rows[0]["duration_minutes"] == 90
