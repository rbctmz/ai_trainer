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


def test_coach_explainability_mentions_persisted_checkpoint_adjustment():
    summary = build_coach_explainability_summary(
        tsb=1,
        ctl=68,
        atl=60,
        readiness=76,
        goal_plan={
            "constraint_summary": {
                "available_hours": 7.5,
                "available_day_labels": ["Вт", "Чт", "Сб"],
                "plan_adjustment": {
                    "label": "Пропущены сессии",
                    "weeks": 1,
                },
                "plan_adjustment_recovered_tss": 20,
                "catch_up_strategy": "catch_up",
            }
        },
    )

    assert any("checkpoint уже учтён" in signal for signal in summary["signals"])
    assert "checkpoint «Пропущены сессии»" in summary["plan_context"]


def test_coach_explainability_mentions_manual_near_term_edit():
    summary = build_coach_explainability_summary(
        tsb=2,
        ctl=66,
        atl=58,
        readiness=72,
        goal_plan={
            "constraint_summary": {
                "available_day_labels": ["Вт", "Чт", "Сб"],
                "near_term_edit": {
                    "is_active": True,
                    "edited_day_count": 3,
                    "horizon_days": 7,
                    "total_delta_tss": -15,
                    "label": "Ручная правка ближнего горизонта",
                    "post_edit_strategy": "catch_up",
                    "future_target_tss": 10,
                    "future_delta_tss": 10,
                    "future_weeks": 2,
                    "future_week_count": 1,
                },
            }
        },
    )

    assert any("правился вручную" in signal for signal in summary["signals"])
    assert "ручную правку ближнего горизонта" in summary["plan_context"]
    assert "Δ -15 TSS" in summary["plan_context"]
    assert "Наверстать аккуратно" in summary["plan_context"]


def test_coach_explainability_mentions_manual_edit_risk_guardrail():
    summary = build_coach_explainability_summary(
        tsb=-8,
        ctl=66,
        atl=74,
        readiness=61,
        goal_plan={
            "constraint_summary": {
                "available_day_labels": ["Вт", "Чт", "Сб"],
                "near_term_edit": {
                    "is_active": True,
                    "edited_day_count": 2,
                    "horizon_days": 7,
                    "total_delta_tss": 40,
                    "label": "Ручная правка ближнего горизонта",
                    "post_edit_strategy": "keep",
                    "future_target_tss": 0,
                    "future_delta_tss": 0,
                    "future_weeks": 2,
                    "future_week_count": 0,
                    "risk_level": "high",
                    "risk_focus": "overload",
                    "risk_reasons": [
                        "в ближайшие 7 дн. добавлено +40 TSS",
                        "убран день полного отдыха",
                    ],
                    "risk_guardrail": "Верните часть TSS или оставьте один явный лёгкий день.",
                },
            }
        },
    )

    assert any("Риск ручной правки" in signal for signal in summary["signals"])
    assert "Высокий риск перегруза" in summary["plan_context"]
    assert "лёгкий день" in summary["plan_context"]


def test_coach_explainability_prefers_execution_review_after_actionable_checkpoint():
    summary = build_coach_explainability_summary(
        tsb=3,
        ctl=68,
        atl=56,
        readiness=81,
        goal_plan={
            "constraint_summary": {
                "available_hours": 7.5,
                "available_day_labels": ["Вт", "Чт", "Сб"],
                "plan_adjustment": {
                    "label": "Нагрузка урезана",
                    "weeks": 1,
                },
            }
        },
        execution_feedback={
            "plan_adjustment_label": "Нагрузка урезана",
            "plan_adjustment_weeks": 1,
            "total_delta": -40,
            "peak_delta": 0,
        },
    )

    assert summary["focus"] == "execution_review"
    assert "checkpoint" in summary["title"].lower()
    assert "execution checkpoint" in summary["prompt"].lower()
    assert "-40 TSS" in summary["prompt"]
    assert any("Execution checkpoint" in signal for signal in summary["signals"])


def test_coach_explainability_keeps_checkpoint_guardrails_visible_during_recovery_focus():
    summary = build_coach_explainability_summary(
        tsb=-24,
        ctl=58,
        atl=91,
        readiness=42,
        goal_plan={
            "constraint_summary": {
                "available_day_labels": ["Вт", "Чт", "Сб"],
                "plan_adjustment": {
                    "label": "Нагрузка урезана",
                    "weeks": 1,
                },
            }
        },
        execution_feedback={
            "plan_adjustment_label": "Нагрузка урезана",
            "plan_adjustment_weeks": 1,
            "total_delta": -40,
            "peak_delta": 0,
        },
    )

    assert summary["focus"] == "recovery"
    assert "урезан" in summary["next_window"].lower()
    assert "резким ростом интенсивности" in summary["watchout"].lower()
