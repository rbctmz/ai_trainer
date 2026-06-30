"""Smoke coverage for the AI coach execution runtime boundary."""
from __future__ import annotations

import pytest

from models import ai_coach_runtime
from ui.components.ai_coach_output import format_tool_result
from ui.pages import ai_coaching


pytestmark = pytest.mark.smoke


class _DummyAiTools:
    def __init__(self, responses=None):
        self._responses = responses or {}
        self.calls = []

    def format_tool_descriptions_for_ai(self):
        return "• TEST TOOL: [TOOL: sample_tool, days=7]"

    def execute_tool(self, tool_name, **kwargs):
        self.calls.append((tool_name, kwargs))
        return self._responses[tool_name]


class _DummyProvider:
    def __init__(self, response: str):
        self.response = response
        self.calls = []

    def generate_response(self, prompt: str, system_prompt: str) -> str:
        self.calls.append({"prompt": prompt, "system_prompt": system_prompt})
        return self.response


class _DummyContext:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _DummyPlaceholder:
    def __init__(self):
        self.messages = []

    def markdown(self, text: str) -> None:
        self.messages.append(text)


def test_system_prompt_mandates_hrv_tool_for_recovery_questions():
    prompt = ai_coach_runtime.create_chat_system_prompt_with_tools(None)
    assert "analyze_hrv_trends" in prompt
    assert "Утверждать" in prompt and "HRV нет" in prompt


def test_synthesis_prompt_forbids_hrv_absent_without_tool():
    system_prompt = ai_coach_runtime.create_chat_synthesis_system_prompt()
    assert "НЕЛЬЗЯ" in system_prompt
    assert "не вызывался" in system_prompt


def test_synthesis_prompt_contains_verbosity_rule():
    system_prompt = ai_coach_runtime.create_chat_synthesis_system_prompt()
    assert "300" in system_prompt
    assert "3–5" in system_prompt


def test_synthesis_prompt_injects_phase_when_goal_plan_provided():
    from datetime import date, timedelta
    event_date = (date.today() + timedelta(days=90)).isoformat()
    goal_plan = {"goal_type": "Триатлон", "distance": "Олимпийка",
                 "event_date": event_date, "weeks_to_race": 16}
    prompt = ai_coach_runtime.create_chat_synthesis_system_prompt(goal_plan=goal_plan)
    assert "ПЛАН И ФАЗА" in prompt
    assert "Дней до старта" in prompt
    assert "Текущая фаза" in prompt


def test_synthesis_prompt_no_phase_without_plan():
    prompt = ai_coach_runtime.create_chat_synthesis_system_prompt(goal_plan=None)
    assert "ПЛАН И ФАЗА" not in prompt


def test_runtime_builds_prompt_from_history_and_tools():
    ai_tools = _DummyAiTools()
    provider = _DummyProvider("raw ai response")

    response = ai_coach_runtime.generate_ai_chat_response(
        provider=provider,
        ai_tools=ai_tools,
        user_input="Что делать на следующей неделе?",
        history_messages=[
            {"role": "user", "content": "Как форма сегодня?"},
            {"role": "assistant", "content": "Форма стабильная."},
        ],
    )

    assert response == "raw ai response"
    assert len(provider.calls) == 1
    prompt = provider.calls[0]
    prompt = prompt["prompt"]
    assert "TEST TOOL" in prompt
    assert "USER: Как форма сегодня?" in prompt
    assert "ASSISTANT: Форма стабильная." in prompt
    assert "НОВЫЙ ВОПРОС ПОЛЬЗОВАТЕЛЯ: Что делать на следующей неделе?" in prompt


def test_runtime_appends_response_contract_suffix_to_prompt():
    ai_tools = _DummyAiTools()
    provider = _DummyProvider("raw ai response")

    ai_coach_runtime.generate_ai_chat_response(
        provider=provider,
        ai_tools=ai_tools,
        user_input="Что делать после облегчённой недели?",
        history_messages=[],
        response_contract={
            "mode": "operational_brief",
            "prompt_suffix": "Верни ответ строго в формате: Сегодня / Ближайшие 2-3 дня / Не делать / Почему.",
        },
    )

    prompt = provider.calls[0]
    prompt = prompt["prompt"]
    assert "Что делать после облегчённой недели?" in prompt
    assert "Верни ответ строго в формате" in prompt


def test_runtime_finalizes_tool_calls_and_applies_post_processing():
    ai_tools = _DummyAiTools(
        responses={
            "sample_tool": {
                "success": True,
                "result": {"value": 42},
            }
        }
    )

    final = ai_coach_runtime.finalize_ai_chat_response(
        "Смотри данные: [TOOL: sample_tool, days=7, threshold=1.5, sport='run']",
        ai_tools,
        tool_result_formatter=lambda name, data: f"{name}:{data['value']}",
        response_post_processor=lambda text: text + "\nPOST",
    )

    assert final == "Смотри данные: sample_tool:42\nPOST"
    assert ai_tools.calls == [
        ("sample_tool", {"days": 7, "threshold": 1.5, "sport": "run"})
    ]


def test_runtime_wraps_final_response_into_operational_brief():
    final = ai_coach_runtime.finalize_ai_chat_response(
        "Нагрузку стоит возвращать аккуратно и следить за восстановлением.",
        _DummyAiTools(),
        tool_result_formatter=lambda name, data: f"{name}:{data}",
        response_contract={
            "mode": "operational_brief",
            "today_action": "Сделайте только лёгкую сессию восстановления.",
            "next_window": "Два дня держите лёгкий объём и только потом возвращайте качество.",
            "watchout": "Не компенсируйте пропуск резким скачком интенсивности.",
            "reason": "Checkpoint уже показал, что безопаснее удержать сниженную верхнюю границу.",
        },
    )

    assert "## 🎯 Operational Brief" in final
    assert "### Сегодня" in final
    assert "Сделайте только лёгкую сессию восстановления." in final
    assert "### Ближайшие 2-3 дня" in final
    assert "### Не делать" in final
    assert "### Почему" in final
    assert "### Разбор AI" in final
    assert "Нагрузку стоит возвращать аккуратно" in final


def test_runtime_synthesizes_final_answer_after_tool_execution():
    ai_tools = _DummyAiTools(
        responses={
            "sample_tool": {
                "success": True,
                "result": {"value": 42},
            }
        }
    )
    provider = _DummyProvider("Финальный ответ с конкретной рекомендацией.")

    final = ai_coach_runtime.finalize_ai_chat_response(
        "Сейчас соберу данные: [TOOL: sample_tool, days=7]",
        ai_tools,
        tool_result_formatter=lambda name, data: f"{name}:{data['value']}",
        provider=provider,
        user_input="Что делать сегодня?",
        history_messages=[{"role": "user", "content": "Как форма?"}],
    )

    assert final == "Финальный ответ с конкретной рекомендацией."
    assert ai_tools.calls == [("sample_tool", {"days": 7})]
    assert len(provider.calls) == 1
    assert "РЕЗУЛЬТАТЫ ИНСТРУМЕНТОВ" in provider.calls[0]["prompt"]
    assert "sample_tool:42" in provider.calls[0]["prompt"]
    assert "ЗАВЕРШЁННЫЙ финальный ответ" in provider.calls[0]["system_prompt"]


def test_collect_tool_results_preserves_raw_proposal_payload():
    ai_tools = _DummyAiTools(
        responses={
            "sample_tool": {
                "success": True,
                "result": {
                    "is_proposal": True,
                    "action": "build_plan",
                    "params": {"goal_type": "Триатлон"},
                    "preview": {"total_weeks": 8},
                },
            }
        }
    )

    rendered, tool_results = ai_coach_runtime.collect_tool_results(
        "Предлагаю так: [TOOL: sample_tool]",
        ai_tools,
        tool_result_formatter=lambda name, _data: f"{name}:ok",
    )

    assert rendered == "Предлагаю так: sample_tool:ok"
    assert tool_results[0]["raw_result"]["is_proposal"] is True
    assert tool_results[0]["raw_result"]["preview"]["total_weeks"] == 8


def test_tool_formatter_localizes_activity_payloads():
    rendered = format_tool_result(
        "get_recent_activities",
        {
            "count": 1,
            "activities": [
                {
                    "date": "2026-06-27",
                    "date_label": "Сб 27.06",
                    "sport": "open_water_swimming",
                    "sport_label": "плавание",
                    "duration_minutes": 52,
                    "tss": 21,
                }
            ],
        },
    )

    assert "open_water_swimming" not in rendered
    assert "Сб 27.06" in rendered
    assert "плавание" in rendered


def test_tool_formatter_localizes_training_status_payloads():
    rendered = format_tool_result(
        "get_training_status",
        {
            "period_days": 7,
            "latest": {
                "training_status": "PRODUCTIVE",
                "training_status_label": "Продуктивно",
                "training_readiness": 72,
                "training_load_7d": 355,
                "vo2_max": 40.6,
            },
            "summary": {
                "avg_training_readiness": 68.5,
                "avg_training_load_7d": 340.0,
                "avg_vo2_max": 40.6,
                "status_distribution": {"Продуктивно": 2},
            },
            "history": [
                {"date": "2026-06-27", "date_label": "Сб 27.06", "training_readiness": 72},
            ],
        },
    )

    assert "PRODUCTIVE" not in rendered
    assert "Продуктивно" in rendered
    assert "Сб 27.06" in rendered


def test_page_wrappers_preserve_runtime_contract(monkeypatch: pytest.MonkeyPatch):
    state = type("State", (), {"ai_tools": _DummyAiTools(responses={"sample_tool": {"success": True, "result": {"value": 99}}})})()

    monkeypatch.setattr(ai_coaching, "get_state_manager", lambda: state)
    monkeypatch.setattr(ai_coaching, "format_tool_result", lambda name, data: f"FMT:{name}:{data['value']}")

    prompt = ai_coaching.create_chat_system_prompt_with_tools(None)
    processed = ai_coaching.process_tool_calls("Ответ: [TOOL: sample_tool, days=14]")

    assert "TEST TOOL" in prompt
    assert processed == "Ответ: FMT:sample_tool:99"
    assert state.ai_tools.calls == [("sample_tool", {"days": 14})]


def test_modern_chat_consumes_pending_response_contract_once(monkeypatch: pytest.MonkeyPatch):
    class _DummyChatManager:
        def __init__(self):
            self.messages = []

        def create_new_chat(self):
            return "chat-1"

        def add_message(self, chat_id, role, content):
            self.messages.append({"chat_id": chat_id, "role": role, "content": content})
            return True

        def get_chat_messages(self, chat_id):
            return [
                {"role": message["role"], "content": message["content"]}
                for message in self.messages
                if message["chat_id"] == chat_id
            ]

    state = type(
        "State",
        (),
        {
            "current_chat_id": "chat-1",
            "chat_manager": _DummyChatManager(),
            "ai_tools": _DummyAiTools(),
            "ai_coach": type("Coach", (), {"provider": object()})(),
            "pending_ai_response_contract": {
                "mode": "operational_brief",
                "prompt_suffix": "suffix",
            },
            "_session": {"speechcore_enabled": False},
            "selected_page": "📊 Дашборд",
            "switch_to_chat_tab": False,
        },
    )()

    captured = {"generate": [], "finalize": []}
    placeholder = _DummyPlaceholder()

    monkeypatch.setattr(ai_coaching, "get_state_manager", lambda: state)
    monkeypatch.setattr(ai_coaching.st, "chat_message", lambda _role: _DummyContext())
    monkeypatch.setattr(ai_coaching.st, "write", lambda _text: None)
    monkeypatch.setattr(ai_coaching.st, "empty", lambda: placeholder)
    monkeypatch.setattr(ai_coaching.st, "rerun", lambda: None)
    monkeypatch.setattr(ai_coaching, "simulate_streaming_response", lambda _placeholder, _text: None)
    monkeypatch.setattr(ai_coaching, "maybe_append_progress_report", lambda _state, _user_input, response: response)

    def _capture_generate(**kwargs):
        captured["generate"].append(kwargs.get("response_contract"))
        return "raw"

    def _capture_finalize(*args, **kwargs):
        captured["finalize"].append(kwargs.get("response_contract"))
        return "final"

    monkeypatch.setattr(ai_coaching, "_generate_ai_chat_response_core", _capture_generate)
    monkeypatch.setattr(ai_coaching, "_finalize_ai_chat_response_core", _capture_finalize)

    ai_coaching.process_modern_chat_message("Что делать сегодня?")
    ai_coaching.process_modern_chat_message("А завтра?")

    assert captured["generate"] == [
        {"mode": "operational_brief", "prompt_suffix": "suffix"},
        None,
    ]
    assert captured["finalize"] == [
        {"mode": "operational_brief", "prompt_suffix": "suffix"},
        None,
    ]
    assert state.pending_ai_response_contract is None
    assert state.selected_page == "🤖 AI Коучинг"
    assert state.switch_to_chat_tab is True
