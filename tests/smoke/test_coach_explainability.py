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
                    "execution_weekly_review": {
                        "headline": "Пропущена ключевая сессия",
                        "review_badge": "Потеря качества",
                        "deviations": [
                            {
                                "code": "missed_key_session",
                                "label": "Пропущена ключевая сессия",
                                "detail": "Ключевая работа недели",
                            }
                        ],
                        "recommended_response_strategy": "protect_recovery",
                        "recommended_response_label": "Беречь восстановление",
                        "recommended_response_reason": "Сначала лучше вернуть структуру недели.",
                        "selected_response_strategy": "catch_up",
                        "selected_response_label": "Наверстать аккуратно",
                    },
                    "execution_corrective_microcycle": {
                        "headline": "Ближайшие 2-3 дня: вернуть структуру без второй quality-сессии",
                        "today_action": "Thu 18.06: Сделать контролируемо — Триатлон Олимпийка — Качество • бег (35 TSS).",
                        "next_window": "Fri 19.06: Оставить лёгкой (Триатлон Олимпийка — Легкая • бег)",
                        "guardrail": "Не добавляйте вторую интенсивную работу рядом с текущей ключевой сессией.",
                        "sessions": [
                            {
                                "action_label": "Сделать контролируемо",
                                "session_name": "Триатлон Олимпийка — Качество • бег",
                            }
                        ],
                    },
                },
                "plan_adjustment_recovered_tss": 20,
                "catch_up_strategy": "catch_up",
            }
        },
    )

    assert any("checkpoint уже учтён" in signal for signal in summary["signals"])
    assert "checkpoint «Пропущены сессии»" in summary["plan_context"]
    assert "Пропущена ключевая сессия" in summary["plan_context"]
    assert any("Weekly review:" in signal for signal in summary["signals"])
    assert "execution microcycle" in summary["plan_context"].lower()
    assert any("Execution microcycle:" in signal for signal in summary["signals"])


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


def test_coach_explainability_mentions_restored_plan_version():
    summary = build_coach_explainability_summary(
        tsb=2,
        ctl=66,
        atl=58,
        readiness=74,
        goal_plan={
            "checkpoint_source": "restore_version",
            "checkpoint_restored_from_checkpoint_id": 41,
            "constraint_summary": {
                "available_hours": 8.0,
                "available_day_labels": ["Вт", "Чт", "Сб"],
            },
        },
    )

    assert any("восстановлена" in signal.lower() for signal in summary["signals"])
    assert "checkpoint #41" in summary["plan_context"]
    assert "checkpoint #41" in summary["prompt"]


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
            "execution_reconciliation": {
                "planned_total_tss": 180,
                "actual_total_tss": 140,
                "delta_tss": -40,
                "changed_day_count": 2,
                "missed_day_count": 1,
                "reduced_day_count": 1,
                "unavailable_day_count": 0,
                "completion_share": 0.78,
            },
            "execution_weekly_review": {
                "headline": "Пропущена ключевая сессия",
                "review_badge": "Потеря качества",
                "deviations": [
                    {
                        "code": "missed_key_session",
                        "label": "Пропущена ключевая сессия",
                        "detail": "Ключевая работа недели",
                    }
                ],
                "recommended_response_strategy": "protect_recovery",
                "recommended_response_label": "Беречь восстановление",
                "recommended_response_reason": "Сначала лучше вернуть структуру недели.",
                "selected_response_strategy": "protect_recovery",
                "selected_response_label": "Беречь восстановление",
            },
            "execution_corrective_microcycle": {
                "headline": "Ближайшие 2-3 дня: вернуть структуру без второй quality-сессии",
                "today_action": "Thu 18.06: Сделать контролируемо — Триатлон Олимпийка — Качество • бег (35 TSS).",
                "next_window": "Fri 19.06: Оставить лёгкой (Триатлон Олимпийка — Легкая • бег)",
                "guardrail": "Не добавляйте вторую интенсивную работу рядом с текущей ключевой сессией.",
                "sessions": [
                    {
                        "action_label": "Сделать контролируемо",
                        "session_name": "Триатлон Олимпийка — Качество • бег",
                    }
                ],
            },
        },
    )

    assert summary["focus"] == "execution_review"
    assert "checkpoint" in summary["title"].lower()
    assert "execution checkpoint" in summary["prompt"].lower()
    assert "-40 TSS" in summary["prompt"]
    assert "Пропущена ключевая сессия" in summary["prompt"]
    assert "Беречь восстановление" in summary["prompt"]
    assert summary["today_action"].startswith("Thu 18.06: Сделать контролируемо")
    assert summary["next_window"].startswith("Fri 19.06: Оставить лёгкой")
    assert summary["watchout"] == "Не добавляйте вторую интенсивную работу рядом с текущей ключевой сессией."
    assert any("Execution checkpoint" in signal for signal in summary["signals"])
    assert any("140/180 TSS" in signal for signal in summary["signals"])
    assert any("Weekly review:" in signal for signal in summary["signals"])
    assert any("Execution microcycle:" in signal for signal in summary["signals"])


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
            "execution_reconciliation": {
                "planned_total_tss": 180,
                "actual_total_tss": 140,
                "delta_tss": -40,
                "changed_day_count": 2,
                "missed_day_count": 1,
                "reduced_day_count": 1,
                "unavailable_day_count": 0,
                "completion_share": 0.78,
            },
        },
    )

    assert summary["focus"] == "recovery"
    assert "урезан" in summary["next_window"].lower()
    assert "резким ростом интенсивности" in summary["watchout"].lower()


def test_coach_explainability_mentions_fact_window_from_current_plan():
    summary = build_coach_explainability_summary(
        tsb=1,
        ctl=67,
        atl=59,
        readiness=73,
        goal_plan={
            "constraint_summary": {
                "available_hours": 8.0,
                "available_day_labels": ["Вт", "Чт", "Сб"],
                "plan_adjustment": {
                    "label": "Нагрузка урезана",
                    "weeks": 1,
                    "execution_reconciliation": {
                        "planned_total_tss": 180,
                        "actual_total_tss": 140,
                        "delta_tss": -40,
                        "changed_day_count": 2,
                        "missed_day_count": 1,
                        "reduced_day_count": 1,
                        "unavailable_day_count": 0,
                        "completion_share": 0.78,
                    },
                },
            }
        },
    )

    assert any("Факт ближнего окна уже учтён" in signal for signal in summary["signals"])
    assert "140/180 TSS" in summary["plan_context"]
