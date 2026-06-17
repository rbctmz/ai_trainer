"""Smoke coverage for dashboard -> AI coach handoff."""
from __future__ import annotations

import pytest

from ui.pages import dashboard


pytestmark = pytest.mark.smoke


class _RerunTriggered(BaseException):
    """Sentinel exception used to stop rerun-based flows."""


class _DummyState:
    def __init__(self) -> None:
        self.selected_page = "📊 Дашборд"
        self.switch_to_chat_tab = False
        self.ai_coach_handoff = None
        self.latest_execution_feedback = {
            "plan_adjustment_label": "Пропущены сессии",
            "plan_adjustment_weeks": 1,
            "total_delta": -40,
            "peak_delta": 0,
        }
        self.goal_plan = None
        self.resolved_goal_plan_context = {
            "constraint_summary": {
                "available_hours": 8.5,
                "available_day_labels": ["Вт", "Чт", "Сб"],
                "available_day_count": 3,
                "recommended_days": 6,
                "interruption_label": "Отпуск",
                "interruption_weeks": 1,
                "catch_up_strategy": "catch_up",
                "plan_adjustment": {
                    "label": "Пропущены сессии",
                    "weeks": 1,
                },
                "plan_adjustment_recovered_tss": 20,
                "near_term_edit": {
                    "is_active": True,
                    "edited_day_count": 3,
                    "horizon_days": 7,
                    "total_delta_tss": -15,
                    "label": "Ручная правка ближнего горизонта",
                },
            }
        }


def test_ai_chat_action_primes_dashboard_handoff(monkeypatch: pytest.MonkeyPatch):
    state = _DummyState()

    def _raise_rerun() -> None:
        raise _RerunTriggered

    monkeypatch.setattr(dashboard.st, "rerun", _raise_rerun)

    with pytest.raises(_RerunTriggered):
        dashboard._handle_quick_action(
            state,
            "ai_chat",
            lambda _days: None,
            {"tsb": 4, "ctl": 70, "atl": 55, "readiness": 80},
        )

    assert state.selected_page == "🤖 AI Коучинг"
    assert state.switch_to_chat_tab is True
    assert state.ai_coach_handoff["source"] == "dashboard"
    assert state.ai_coach_handoff["today_action"]
    assert "checkpoint" in state.ai_coach_handoff["title"].lower()
    assert "Вт, Чт, Сб" in state.ai_coach_handoff["prompt"]
    assert "ручную правку ближнего горизонта" in state.ai_coach_handoff["prompt"]
    assert state.ai_coach_handoff["response_contract"]["mode"] == "operational_brief"
    assert "Сегодня / Ближайшие 2-3 дня / Не делать / Почему" in state.ai_coach_handoff["response_contract"]["preview_label"]


def test_execution_feedback_result_compares_checkpoint_deltas():
    result = dashboard._build_execution_feedback_result(
        {
            "goal_type": "Триатлон",
            "distance": "Олимпийка",
            "peak_tss": 400,
            "total_tss": 1200,
            "plan_adjustment_label": "Нет",
        },
        {
            "goal_type": "Триатлон",
            "distance": "Олимпийка",
            "peak_tss": 380,
            "total_tss": 1140,
            "plan_adjustment_label": "Пропущены сессии",
            "created_at": "2026-06-14 12:00:00",
        },
    )

    assert result["plan_adjustment_label"] == "Пропущены сессии"
    assert result["peak_delta"] == -20
    assert result["total_delta"] == -60
