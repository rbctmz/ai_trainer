from __future__ import annotations

import pytest

from config.settings import Settings
from services import acceptance_mode


pytestmark = pytest.mark.smoke


class _StubDatabase:
    def __init__(
        self,
        db_path: str = "/tmp/acceptance.db",
        stats: dict[str, int] | None = None,
        latest_checkpoint: dict[str, object] | None = None,
    ):
        self.db_path = db_path
        self._stats = stats or {
            "activities": 0,
            "hrv_data": 0,
            "user_settings": 0,
            "sleep_data": 0,
            "daily_health": 0,
            "training_status": 0,
        }
        self._latest_checkpoint = latest_checkpoint

    def get_database_stats(self) -> dict[str, int]:
        return dict(self._stats)

    def get_latest_planning_checkpoint(self) -> dict[str, object] | None:
        return self._latest_checkpoint


class _StubState:
    def __init__(
        self,
        stats: dict[str, int] | None = None,
        latest_checkpoint: dict[str, object] | None = None,
    ):
        self.database = _StubDatabase(stats=stats, latest_checkpoint=latest_checkpoint)
        self.acceptance_bootstrapped = False
        self.demo_mode = False
        self.selected_page = "📊 Дашборд"
        self.selected_provider = None
        self.ai_coach = object()
        self.switch_to_chat_tab = True


def test_runtime_info_reports_isolated_database_path(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(Settings, "ACCEPTANCE_MODE", True)
    monkeypatch.setattr(Settings, "ACCEPTANCE_AUTO_DEMO", True)
    monkeypatch.setattr(Settings, "ACCEPTANCE_DISABLE_GARMIN", True)
    monkeypatch.setattr(Settings, "ACCEPTANCE_LABEL", "Acceptance Mode")

    info = acceptance_mode.runtime_info(_StubState())

    assert info["enabled"] is True
    assert info["auto_demo"] is True
    assert info["garmin_disabled"] is True
    assert info["database_path"] == "/tmp/acceptance.db"


def test_bootstrap_session_seeds_demo_once_for_empty_isolated_database(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(Settings, "ACCEPTANCE_MODE", True)
    monkeypatch.setattr(Settings, "ACCEPTANCE_AUTO_DEMO", True)
    monkeypatch.setattr(Settings, "ACCEPTANCE_DISABLE_GARMIN", True)

    state = _StubState()
    activations: list[str] = []

    monkeypatch.setattr(acceptance_mode.demo_mode_service, "is_demo_mode", lambda _state: False)

    def fake_activate_demo_mode(_state):
        activations.append("activated")
        _state.demo_mode = True
        return {"activities": 12, "hrv_days": 21, "sleep_days": 14}

    monkeypatch.setattr(acceptance_mode.demo_mode_service, "activate_demo_mode", fake_activate_demo_mode)

    first = acceptance_mode.bootstrap_session(state)
    second = acceptance_mode.bootstrap_session(state)

    assert first["seeded"] is True
    assert first["seed_result"]["activities"] == 12
    assert state.acceptance_bootstrapped is True
    assert second["seeded"] is False
    assert activations == ["activated"]


def test_bootstrap_session_can_run_without_auto_demo(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(Settings, "ACCEPTANCE_MODE", True)
    monkeypatch.setattr(Settings, "ACCEPTANCE_AUTO_DEMO", False)
    monkeypatch.setattr(Settings, "ACCEPTANCE_DISABLE_GARMIN", True)

    state = _StubState(stats={"activities": 12, "hrv_data": 21})
    activated: list[str] = []
    monkeypatch.setattr(
        acceptance_mode.demo_mode_service,
        "activate_demo_mode",
        lambda _state: activated.append("activated"),
    )

    info = acceptance_mode.bootstrap_session(state)

    assert info["seeded"] is False
    assert activated == []


def test_bootstrap_session_preserves_existing_isolated_dataset(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(Settings, "ACCEPTANCE_MODE", True)
    monkeypatch.setattr(Settings, "ACCEPTANCE_AUTO_DEMO", True)
    monkeypatch.setattr(Settings, "ACCEPTANCE_DISABLE_GARMIN", True)

    state = _StubState(stats={"activities": 12, "hrv_data": 21, "sleep_data": 14, "daily_health": 14, "training_status": 1})
    activated: list[str] = []
    monkeypatch.setattr(
        acceptance_mode.demo_mode_service,
        "activate_demo_mode",
        lambda _state: activated.append("activated"),
    )
    restored: list[str] = []
    monkeypatch.setattr(
        acceptance_mode.demo_mode_service,
        "restore_demo_mode_session",
        lambda _state: restored.append("restored"),
    )

    info = acceptance_mode.bootstrap_session(state)

    assert info["seeded"] is False
    assert info["preserved_existing_data"] is True
    assert activated == []
    assert restored == ["restored"]


def test_bootstrap_session_preserves_checkpoint_only_database(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(Settings, "ACCEPTANCE_MODE", True)
    monkeypatch.setattr(Settings, "ACCEPTANCE_AUTO_DEMO", True)
    monkeypatch.setattr(Settings, "ACCEPTANCE_DISABLE_GARMIN", True)

    state = _StubState(latest_checkpoint={"id": 1, "goal_type": "Триатлон"})
    activated: list[str] = []
    monkeypatch.setattr(
        acceptance_mode.demo_mode_service,
        "activate_demo_mode",
        lambda _state: activated.append("activated"),
    )
    restored: list[str] = []
    monkeypatch.setattr(
        acceptance_mode.demo_mode_service,
        "restore_demo_mode_session",
        lambda _state: restored.append("restored"),
    )

    info = acceptance_mode.bootstrap_session(state)

    assert info["seeded"] is False
    assert info["preserved_existing_data"] is True
    assert activated == []
    assert restored == ["restored"]


def test_reset_acceptance_dataset_requires_acceptance_mode(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(Settings, "ACCEPTANCE_MODE", False)

    with pytest.raises(RuntimeError):
        acceptance_mode.reset_acceptance_dataset(_StubState())
