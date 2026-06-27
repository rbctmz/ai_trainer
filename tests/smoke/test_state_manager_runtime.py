from __future__ import annotations

from types import SimpleNamespace

import pytest

from state import manager as state_manager_module


pytestmark = pytest.mark.smoke


class _FakeSessionState(dict):
    def __getattr__(self, item):
        try:
            return self[item]
        except KeyError as exc:
            raise AttributeError(item) from exc

    def __setattr__(self, key, value):
        self[key] = value


def test_get_state_manager_wraps_current_session_state(monkeypatch: pytest.MonkeyPatch):
    first_session = _FakeSessionState()
    second_session = _FakeSessionState()

    monkeypatch.setattr(state_manager_module, "st", SimpleNamespace(session_state=first_session))
    first_manager = state_manager_module.get_state_manager()
    first_manager.selected_page = "📊 Дашборд"

    monkeypatch.setattr(state_manager_module, "st", SimpleNamespace(session_state=second_session))
    second_manager = state_manager_module.get_state_manager()

    assert first_manager._session is first_session
    assert second_manager._session is second_session
    assert second_manager.selected_page == "📊 Дашборд"
    assert "database" not in second_session
