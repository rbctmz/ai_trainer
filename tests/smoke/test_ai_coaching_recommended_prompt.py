"""Smoke tests for the recommended first prompt on the AI coaching page."""
from __future__ import annotations

import pytest

from ui.pages import ai_coaching


pytestmark = pytest.mark.smoke


def test_recommended_prompt_prefers_recovery_when_tsb_is_low():
    prompt = ai_coaching._choose_recommended_first_prompt(
        {
            "summary": {"has_data": True},
            "performance_metrics": {"has_data": True, "banister_model": {"tsb": -24}},
            "hrv": {"has_data": True, "stats": {"recovery_state": "good"}},
            "sleep": {"has_data": True, "sleep_quality": "good"},
            "training_status": {"has_data": True, "latest": {"training_readiness": 55}},
        }
    )

    assert "восстанов" in prompt["title"].lower()
    assert "восстанов" in prompt["prompt"].lower()


def test_recommended_prompt_prefers_week_plan_when_readiness_is_high():
    prompt = ai_coaching._choose_recommended_first_prompt(
        {
            "summary": {"has_data": True},
            "performance_metrics": {"has_data": True, "banister_model": {"tsb": 4}},
            "hrv": {"has_data": True, "stats": {"recovery_state": "good"}},
            "sleep": {"has_data": True, "sleep_quality": "good"},
            "training_status": {"has_data": True, "latest": {"training_readiness": 82}},
        }
    )

    assert "план" in prompt["title"].lower()
    assert "7 дней" in prompt["prompt"]


def test_recommended_prompt_has_safe_fallback_without_data():
    prompt = ai_coaching._choose_recommended_first_prompt(
        {"summary": {"has_data": False}}
    )

    assert "данн" in prompt["title"].lower() or "доступ" in prompt["title"].lower()
    assert "какие данные" in prompt["prompt"].lower()


def test_entry_prompt_prefers_dashboard_handoff_when_available():
    prompt = ai_coaching._resolve_ai_coach_entry_prompt(
        {"summary": {"has_data": False}},
        None,
        {
            "source": "dashboard",
            "icon": "📈",
            "title": "План недели из дашборда",
            "button": "Отправить в AI",
            "description": "Дашборд уже подготовил лучший стартовый вопрос.",
            "reason": "Следующий шаг уже определён по текущим метрикам.",
            "prompt": "Составь мне план недели по окну Вт, Чт, Сб.",
        },
    )

    assert prompt["source"] == "dashboard"
    assert prompt["title"] == "План недели из дашборда"
    assert prompt["prompt"] == "Составь мне план недели по окну Вт, Чт, Сб."
