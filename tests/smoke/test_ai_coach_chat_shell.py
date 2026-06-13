"""Smoke coverage for the AI coaching chat-shell helpers."""
from __future__ import annotations

import pytest

from ui.components import ai_coach_chat


pytestmark = pytest.mark.smoke


class _DummyChatManager:
    def __init__(self, chats=None):
        self._chats = chats or []
        self.created_titles = []

    def create_new_chat(self, title=None):
        self.created_titles.append(title)
        return "demo-chat-id"

    def get_chat_list(self):
        return self._chats


class _DummyState:
    def __init__(self, *, current_chat_id=None, chats=None):
        object.__setattr__(self, "_values", {})
        self.current_chat_id = current_chat_id
        self.chat_manager = _DummyChatManager(chats)
        self.ai_tools = object()

    def __contains__(self, key):
        return key in self._values

    def __getattr__(self, key):
        try:
            return self._values[key]
        except KeyError as exc:  # pragma: no cover - defensive path
            raise AttributeError(key) from exc

    def __setattr__(self, key, value):
        self._values[key] = value


def test_chat_shell_initializes_demo_chat_when_chat_missing(monkeypatch: pytest.MonkeyPatch):
    state = _DummyState(current_chat_id=None)

    monkeypatch.setattr(ai_coach_chat.demo_mode_service, "is_demo_mode", lambda _state: True)

    ai_coach_chat.ensure_ai_chat_session_state(state, database=object())

    assert state.current_chat_id == "demo-chat-id"
    assert state.chat_manager.created_titles == ["Демо AI коуч"]
    assert state.data_context is None
    assert state.context_loaded is False


def test_chat_shell_reuses_first_saved_chat_outside_demo(monkeypatch: pytest.MonkeyPatch):
    state = _DummyState(
        current_chat_id=None,
        chats=[{"id": "chat-42"}, {"id": "chat-99"}],
    )

    monkeypatch.setattr(ai_coach_chat.demo_mode_service, "is_demo_mode", lambda _state: False)

    ai_coach_chat.ensure_ai_chat_session_state(state, database=object())

    assert state.current_chat_id == "chat-42"
    assert state.chat_manager.created_titles == []


def test_quick_question_prompts_keep_expected_actions():
    prompts = ai_coach_chat._build_quick_question_prompts()

    assert len(prompts) == 4
    assert [prompt["key"] for prompt in prompts] == ["form_q", "plan_q", "progress_q", "hrv_q"]
    assert any("прогресс" in prompt["prompt"].lower() for prompt in prompts)
