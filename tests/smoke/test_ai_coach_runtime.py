"""Smoke coverage for the AI coach execution runtime boundary."""
from __future__ import annotations

import pytest

from models import ai_coach_runtime
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

    def generate_response(self, prompt: str, _context: str) -> str:
        self.calls.append(prompt)
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
