"""Smoke tests for the recommended first prompt on the AI coaching page."""
from __future__ import annotations

import pytest

from ui.pages import ai_coaching


pytestmark = pytest.mark.smoke


class _DummyContext:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


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


def test_recommended_prompt_prefers_execution_review_when_checkpoint_is_actionable():
    prompt = ai_coaching._choose_recommended_first_prompt(
        {
            "summary": {"has_data": True},
            "performance_metrics": {"has_data": True, "banister_model": {"tsb": 4}},
            "hrv": {"has_data": True, "stats": {"recovery_state": "good"}},
            "sleep": {"has_data": True, "sleep_quality": "good"},
            "training_status": {"has_data": True, "latest": {"training_readiness": 82}},
        },
        {
            "constraint_summary": {
                "available_day_labels": ["Вт", "Чт", "Сб"],
                "plan_adjustment": {
                    "label": "Нагрузка урезана",
                    "weeks": 1,
                },
            }
        },
        {
            "plan_adjustment_label": "Нагрузка урезана",
            "plan_adjustment_weeks": 1,
            "total_delta": -40,
            "peak_delta": 0,
        },
    )

    assert "checkpoint" in prompt["title"].lower()
    assert "execution checkpoint" in prompt["prompt"].lower()
    assert prompt["response_contract"]["mode"] == "operational_brief"
    assert "Сегодня / Ближайшие 2-3 дня / Не делать / Почему" in prompt["response_contract"]["preview_label"]


def test_recommended_prompt_carries_manual_near_term_edit_into_prompt_context():
    prompt = ai_coaching._choose_recommended_first_prompt(
        {
            "summary": {"has_data": True},
            "performance_metrics": {"has_data": True, "banister_model": {"tsb": 4}},
            "hrv": {"has_data": True, "stats": {"recovery_state": "good"}},
            "sleep": {"has_data": True, "sleep_quality": "good"},
            "training_status": {"has_data": True, "latest": {"training_readiness": 78}},
        },
        {
            "constraint_summary": {
                "available_hours": 8.0,
                "available_day_labels": ["Вт", "Чт", "Сб"],
                "near_term_edit": {
                    "is_active": True,
                    "edited_day_count": 3,
                    "horizon_days": 7,
                    "total_delta_tss": -15,
                    "label": "Ручная правка ближнего горизонта",
                },
            }
        },
    )

    assert "ручную правку ближнего горизонта" in prompt["prompt"]
    assert "Δ -15 TSS" in prompt["prompt"]


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
            "response_contract": {
                "mode": "operational_brief",
                "preview_label": "Первый ответ вернётся в формате: Сегодня / Ближайшие 2-3 дня / Не делать / Почему.",
            },
        },
    )

    assert prompt["source"] == "dashboard"
    assert prompt["title"] == "План недели из дашборда"
    assert prompt["prompt"] == "Составь мне план недели по окну Вт, Чт, Сб."
    assert prompt["response_contract"]["mode"] == "operational_brief"


def test_dashboard_handoff_click_primes_pending_response_contract(monkeypatch: pytest.MonkeyPatch):
    state = type(
        "State",
        (),
        {
            "pending_ai_response_contract": None,
            "ai_coach_handoff": {"source": "dashboard"},
        },
    )()
    captured_prompts = []
    handoff = {
        "source": "dashboard",
        "icon": "😴",
        "title": "Разберите execution checkpoint и ближайший план",
        "button": "Спросить про восстановление",
        "description": "Дашборд уже подготовил старт.",
        "reason": "Следующий шаг уже определён.",
        "prompt": "Что делать сегодня и в ближайшие 2-3 дня после облегчённой недели?",
        "today_action": "Сделайте только лёгкую восстановительную сессию.",
        "next_window": "Держите сниженный объём ещё 2-3 дня.",
        "watchout": "Не пытайтесь вернуть объём одним скачком.",
        "plan_context": "Окно: Вт, Чт, Сб",
        "signals": ["TSB низкий", "checkpoint активен"],
        "response_contract": {
            "mode": "operational_brief",
            "preview_label": "Первый ответ вернётся в формате: Сегодня / Ближайшие 2-3 дня / Не делать / Почему.",
            "prompt_suffix": "Верни ответ строго в формате: Сегодня / Ближайшие 2-3 дня / Не делать / Почему.",
        },
    }

    monkeypatch.setattr(ai_coaching.st, "markdown", lambda *args, **kwargs: None)
    monkeypatch.setattr(ai_coaching.st, "write", lambda *args, **kwargs: None)
    monkeypatch.setattr(ai_coaching.st, "caption", lambda *args, **kwargs: None)
    monkeypatch.setattr(ai_coaching.st, "container", lambda **kwargs: _DummyContext())
    monkeypatch.setattr(ai_coaching.st, "columns", lambda _spec: (_DummyContext(), _DummyContext()))
    monkeypatch.setattr(
        ai_coaching.st,
        "button",
        lambda _label, key=None, **kwargs: key == "dashboard_handoff_prompt",
    )

    ai_coaching.render_dashboard_handoff(state, handoff, captured_prompts.append)

    assert state.pending_ai_response_contract == handoff["response_contract"]
    assert state.ai_coach_handoff is None
    assert captured_prompts == [handoff["prompt"]]
