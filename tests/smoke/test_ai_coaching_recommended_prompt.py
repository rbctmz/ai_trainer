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
                    "execution_adaptation_pressure": {
                        "level": "medium",
                        "score": 45,
                        "follow_up_mode": "hold",
                        "follow_up_label": "Удержать текущий потолок",
                        "rebuild_horizon_weeks": 2,
                        "growth_cap_tss_per_week": 25,
                        "recovery_share_cap": 0.0,
                        "reason": "Окно уже сдвинулось заметно: следующие 1-2 недели лучше удержать текущий потолок.",
                    },
                    "execution_weekly_review": {
                        "headline": "Нагрузка сжалась в меньшее число дней",
                        "review_badge": "Риск компрессии",
                        "deviations": [
                            {
                                "code": "overload_compression",
                                "label": "Нагрузка сжалась в меньшее число дней",
                                "detail": "140/180 TSS осталось в 2 из 3 активных дней",
                            }
                        ],
                        "recommended_response_strategy": "protect_recovery",
                        "recommended_response_label": "Беречь восстановление",
                        "recommended_response_reason": "Похожий объём в меньшем числе дней повышает риск компрессии.",
                        "selected_response_strategy": "protect_recovery",
                        "selected_response_label": "Беречь восстановление",
                    },
                    "execution_corrective_microcycle": {
                        "headline": "Ближайшие 2-3 дня: удержать объём без компрессии недели",
                        "today_action": "Thu 18.06: Сделать контролируемо — Триатлон Олимпийка — Качество • бег (35 TSS).",
                        "next_window": "Fri 19.06: Оставить лёгкой (Триатлон Олимпийка — Легкая • бег)",
                        "guardrail": "Не пытайтесь добрать весь объём в оставшиеся 1-2 дня.",
                        "sessions": [
                            {
                                "action_label": "Сделать контролируемо",
                                "session_name": "Триатлон Олимпийка — Качество • бег",
                            }
                        ],
                    },
                },
            }
        },
        {
            "plan_adjustment_label": "Нагрузка урезана",
            "plan_adjustment_weeks": 1,
            "total_delta": -40,
            "peak_delta": 0,
            "execution_weekly_review": {
                "headline": "Нагрузка сжалась в меньшее число дней",
                "review_badge": "Риск компрессии",
                "deviations": [
                    {
                        "code": "overload_compression",
                        "label": "Нагрузка сжалась в меньшее число дней",
                        "detail": "140/180 TSS осталось в 2 из 3 активных дней",
                    }
                ],
                "recommended_response_strategy": "protect_recovery",
                "recommended_response_label": "Беречь восстановление",
                "recommended_response_reason": "Похожий объём в меньшем числе дней повышает риск компрессии.",
                "selected_response_strategy": "protect_recovery",
                "selected_response_label": "Беречь восстановление",
            },
            "execution_adaptation_pressure": {
                "level": "medium",
                "score": 45,
                "follow_up_mode": "hold",
                "follow_up_label": "Удержать текущий потолок",
                "rebuild_horizon_weeks": 2,
                "growth_cap_tss_per_week": 25,
                "recovery_share_cap": 0.0,
                "reason": "Окно уже сдвинулось заметно: следующие 1-2 недели лучше удержать текущий потолок.",
            },
            "execution_corrective_microcycle": {
                "headline": "Ближайшие 2-3 дня: удержать объём без компрессии недели",
                "today_action": "Thu 18.06: Сделать контролируемо — Триатлон Олимпийка — Качество • бег (35 TSS).",
                "next_window": "Fri 19.06: Оставить лёгкой (Триатлон Олимпийка — Легкая • бег)",
                "guardrail": "Не пытайтесь добрать весь объём в оставшиеся 1-2 дня.",
                "sessions": [
                    {
                        "action_label": "Сделать контролируемо",
                        "session_name": "Триатлон Олимпийка — Качество • бег",
                    }
                ],
            },
        },
    )

    assert "checkpoint" in prompt["title"].lower()
    assert "execution checkpoint" in prompt["prompt"].lower()
    assert "Нагрузка сжалась в меньшее число дней" in prompt["prompt"]
    assert "Беречь восстановление" in prompt["prompt"]
    assert "Execution microcycle" in prompt["prompt"]
    assert "Execution drift pressure" in prompt["prompt"]
    assert "Удержать текущий потолок" in prompt["prompt"]
    assert "Ближайшие 2-3 дня: удержать объём без компрессии недели" in prompt["prompt"]
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
                    "post_edit_strategy": "catch_up",
                    "future_target_tss": 10,
                    "future_delta_tss": 10,
                    "future_weeks": 2,
                    "future_week_count": 1,
                    "origin_kind": "execution_microcycle_override",
                    "origin_checkpoint_id": 40,
                    "origin_checkpoint_source": "execution_feedback",
                    "origin_plan_adjustment_label": "Пропущены сессии",
                    "origin_weekly_review_headline": "Пропущена ключевая сессия",
                    "origin_microcycle_headline": "Ближайшие 2-3 дня: вернуть структуру без второй quality-сессии",
                },
            }
        },
    )

    assert "ручную правку ближнего горизонта" in prompt["prompt"]
    assert "execution microcycle" in prompt["prompt"].lower()
    assert "Δ -15 TSS" in prompt["prompt"]
    assert "Наверстать аккуратно" in prompt["prompt"]


def test_recommended_prompt_mentions_manual_edit_risk_guardrail():
    prompt = ai_coaching._choose_recommended_first_prompt(
        {
            "summary": {"has_data": True},
            "performance_metrics": {"has_data": True, "banister_model": {"tsb": -8}},
            "hrv": {"has_data": True, "stats": {"recovery_state": "normal"}},
            "sleep": {"has_data": True, "sleep_quality": "average"},
            "training_status": {"has_data": True, "latest": {"training_readiness": 61}},
        },
        {
            "constraint_summary": {
                "available_hours": 8.0,
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

    assert "Высокий риск перегруза" in prompt["prompt"]
    assert "лёгкий день" in prompt["prompt"]


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
