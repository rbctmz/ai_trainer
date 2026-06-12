from __future__ import annotations

import pytest

from models.coach_explainability import build_coach_explainability_summary


pytestmark = pytest.mark.smoke


def test_coach_explainability_prefers_recovery_when_fatigue_is_high():
    summary = build_coach_explainability_summary(
        tsb=-24,
        ctl=58,
        atl=91,
        readiness=42,
    )

    assert summary["focus"] == "recovery"
    assert "восстанов" in summary["title"].lower()
    assert any("TSB" in signal for signal in summary["signals"])


def test_coach_explainability_prefers_week_plan_when_readiness_is_high():
    summary = build_coach_explainability_summary(
        tsb=3,
        ctl=70,
        atl=55,
        readiness=82,
    )

    assert summary["focus"] == "plan_week"
    assert "7 дней" in summary["prompt"]


def test_coach_explainability_surfaces_planning_constraints():
    summary = build_coach_explainability_summary(
        tsb=-5,
        ctl=64,
        atl=70,
        readiness=68,
        goal_plan={
            "constraint_summary": {
                "load_state_label": "Накопленная усталость",
                "interruption_label": "Отпуск",
                "interruption_weeks": 1,
                "notes": ["Стартовое состояние: накопленная усталость — старт плана сделан мягче"],
            }
        },
    )

    assert any("Последний план учитывает состояние" in signal for signal in summary["signals"])
    assert any("адаптирован под сценарий" in signal for signal in summary["signals"])


def test_coach_explainability_adds_plan_aware_briefing_and_prompt_context():
    summary = build_coach_explainability_summary(
        tsb=2,
        ctl=72,
        atl=58,
        readiness=82,
        goal_plan={
            "constraint_summary": {
                "available_hours": 8.5,
                "available_day_labels": ["Вт", "Чт", "Сб"],
                "available_day_count": 3,
                "recommended_days": 6,
                "interruption_label": "Отпуск",
                "interruption_weeks": 1,
                "catch_up_strategy": "catch_up",
                "notes": ["Стартовое состояние: свежий старт — можно мягко вернуть часть объёма"],
            }
        },
    )

    assert summary["today_action"]
    assert summary["next_window"]
    assert summary["watchout"]
    assert "8.5 ч/нед" in summary["plan_context"]
    assert "Вт, Чт, Сб" in summary["plan_context"]
    assert "Учти контекст текущего плана" in summary["prompt"]
    assert "Наверстать аккуратно" in summary["prompt"]
