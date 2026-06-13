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


def test_page_wrappers_preserve_runtime_contract(monkeypatch: pytest.MonkeyPatch):
    state = type("State", (), {"ai_tools": _DummyAiTools(responses={"sample_tool": {"success": True, "result": {"value": 99}}})})()

    monkeypatch.setattr(ai_coaching, "get_state_manager", lambda: state)
    monkeypatch.setattr(ai_coaching, "format_tool_result", lambda name, data: f"FMT:{name}:{data['value']}")

    prompt = ai_coaching.create_chat_system_prompt_with_tools(None)
    processed = ai_coaching.process_tool_calls("Ответ: [TOOL: sample_tool, days=14]")

    assert "TEST TOOL" in prompt
    assert processed == "Ответ: FMT:sample_tool:99"
    assert state.ai_tools.calls == [("sample_tool", {"days": 14})]
