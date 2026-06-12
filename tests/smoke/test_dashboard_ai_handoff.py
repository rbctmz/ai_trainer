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
        self.goal_plan = {
            "constraint_summary": {
                "available_hours": 8.5,
                "available_day_labels": ["Вт", "Чт", "Сб"],
                "available_day_count": 3,
                "recommended_days": 6,
                "interruption_label": "Отпуск",
                "interruption_weeks": 1,
                "catch_up_strategy": "catch_up",
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
    assert "Вт, Чт, Сб" in state.ai_coach_handoff["prompt"]
