"""Smoke coverage for dashboard next-step guidance."""
from __future__ import annotations

import pytest

from ui.pages import dashboard


pytestmark = pytest.mark.smoke


class _DummyState:
    def __init__(self, ai_coach=None):
        self.ai_coach = ai_coach


def test_next_step_prioritizes_recovery_when_tsb_is_low():
    state = _DummyState(ai_coach=object())

    next_step = dashboard._choose_primary_next_step(
        state,
        {"tsb": -25, "hrv": 45},
    )

    assert next_step["action"] == "recovery_plan"
    assert "восстанов" in next_step["title"].lower()


def test_next_step_prioritizes_ai_setup_when_coach_missing():
    state = _DummyState(ai_coach=None)

    next_step = dashboard._choose_primary_next_step(
        state,
        {"tsb": 4, "hrv": 40},
    )

    assert next_step["action"] == "ai_chat"
    assert "коуч" in next_step["title"].lower()


def test_next_step_prioritizes_ai_guidance_when_coach_ready():
    state = _DummyState(ai_coach=object())

    next_step = dashboard._choose_primary_next_step(
        state,
        {"tsb": 3, "hrv": 38},
    )

    assert next_step["action"] == "ai_chat"
    assert "рекоменда" in next_step["title"].lower()
