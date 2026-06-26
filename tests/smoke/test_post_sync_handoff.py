"""Smoke coverage for the post-sync dashboard handoff."""
from __future__ import annotations

import time

import pytest

import app
from services import sync as sync_service
from ui.pages import dashboard


pytestmark = pytest.mark.smoke


class _RerunTriggered(BaseException):
    """Sentinel exception used to stop the fake Streamlit flow."""


class _FakePlaceholder:
    def container(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def empty(self) -> None:
        return None

    def info(self, *_args, **_kwargs) -> None:
        return None

    def text(self, *_args, **_kwargs) -> None:
        return None


class _FakeProgress:
    def progress(self, *_args, **_kwargs) -> None:
        return None


class _FakeStreamlit:
    def empty(self) -> _FakePlaceholder:
        return _FakePlaceholder()

    def info(self, *_args, **_kwargs) -> None:
        return None

    def progress(self, *_args, **_kwargs) -> _FakeProgress:
        return _FakeProgress()

    def error(self, *_args, **_kwargs) -> None:
        return None

    def rerun(self) -> None:
        raise _RerunTriggered


class _DummyState:
    def __init__(self) -> None:
        self.demo_mode = False
        self.syncing_in_progress = False
        self.last_sync_status = {"stale": True}
        self.selected_page = "⚙️ Управление данными"


def test_sync_data_stores_dashboard_handoff_and_redirects(monkeypatch: pytest.MonkeyPatch):
    state = _DummyState()

    monkeypatch.setattr(app, "st", _FakeStreamlit())
    monkeypatch.setattr(app.garmin_service, "is_authenticated", lambda _state: True)
    monkeypatch.setattr(app.demo_mode_service, "is_demo_mode", lambda _state: False)
    monkeypatch.setattr(time, "sleep", lambda _seconds: None)

    result = sync_service.GarminSyncResult(
        activity_result={"new": 1, "updated": 0, "skipped": 0},
        hrv_result={"new": 2, "updated": 0},
        sleep_result={"new": 1, "updated": 0},
        health_result={"new": 1, "updated": 0},
        training_status_result={"new": 1, "updated": 0},
        success_messages=["🆕 1 новых активностей", "💓 2 новых HRV записей"],
    )
    monkeypatch.setattr(app.sync_service, "sync_garmin_data", lambda *_args, **_kwargs: result)

    with pytest.raises(_RerunTriggered):
        app.sync_data(days=30, state=state)

    assert state.syncing_in_progress is False
    assert state.selected_page == "📊 Дашборд"
    assert state.last_sync_status["severity"] == "success"
    assert state.last_sync_status["activity_changes"] == 1


def test_dashboard_sync_handoff_copy_uses_next_step_button():
    handoff = dashboard._build_sync_handoff_copy(
        {
            "severity": "success",
            "title": "Синхронизация Garmin завершена",
            "summary": "Данные готовы к разбору.",
            "highlights": ["🆕 1 новых активностей"],
            "notices": [],
            "synced_at": "2026-06-07T17:05:00",
        },
        {
            "icon": "🤖",
            "button": "Спросить AI коуча",
            "action": "ai_chat",
            "title": "Получите персональную рекомендацию",
            "desc": "next",
            "reason": "next",
        },
    )

    assert handoff["button_label"] == "Спросить AI коуча"
    assert handoff["severity"] == "success"
    assert handoff["synced_at_label"]
