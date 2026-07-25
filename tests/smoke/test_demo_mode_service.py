from __future__ import annotations

import pytest

from services import demo_mode


pytestmark = pytest.mark.smoke


class _StubDatabase:
    def __init__(self):
        self.clear_calls = 0
        self.activities = None
        self.hrv = None
        self.sleep = None
        self.health = None
        self.training_status = None
        self.user_settings = {}
        self.backfill_calls: list[int] = []

    def clear_all_data(self):
        self.clear_calls += 1

    def save_activities(self, activities):
        self.activities = activities

    def backfill_activity_provider_links(self, classify):
        # D6 (#270): демо-сид доводит активности до provider-link модели. Стаб
        # фиксирует, СКОЛЬКО активностей уже лежало на момент вызова, — backfill
        # обязан идти после save_activities, иначе связей не будет.
        self.backfill_calls.append(len(self.activities or []))
        return {
            provider: 0 for provider in ("garmin", "demo", "legacy_unknown", "skipped_existing")
        }

    def save_hrv_data(self, hrv_data):
        self.hrv = hrv_data

    def sync_sleep_data(self, sleep_data):
        self.sleep = sleep_data

    def sync_daily_health(self, health_data):
        self.health = health_data

    def sync_training_status(self, training_status):
        self.training_status = training_status

    def set_user_setting(self, key, value):
        self.user_settings[key] = value


class _StubState:
    def __init__(self):
        self.database = _StubDatabase()
        self.ai_coach = object()
        self.chat_messages = ["old-message"]
        self.context_loaded = True
        self.current_chat_id = "existing-chat"
        self.demo_mode = False
        self.selected_page = "🤖 AI Коучинг"
        self.selected_provider = "openai"
        self.reset_calls = 0
        self.switch_to_chat_tab = True
        self.clear_context_calls = 0

    def reset_planner_overrides(self):
        self.reset_calls += 1

    def clear_cached_context(self):
        self.clear_context_calls += 1
        self.context_loaded = False


def test_activate_demo_mode_seeds_temporary_dataset(monkeypatch: pytest.MonkeyPatch):
    state = _StubState()
    cache_clears: list[str] = []

    monkeypatch.setattr(demo_mode, "clear_data_caches", lambda: cache_clears.append("cleared"))

    result = demo_mode.activate_demo_mode(state)

    assert state.demo_mode is True
    assert state.selected_page == "📊 Дашборд"
    assert state.selected_provider == demo_mode.DEMO_PROVIDER
    assert state.ai_coach is None
    assert state.current_chat_id is None
    assert state.chat_messages == []
    assert state.switch_to_chat_tab is False
    assert state.clear_context_calls == 1
    assert state.reset_calls == 1
    assert state.database.clear_calls == 1
    assert len(state.database.activities) == result["activities"] > 0
    assert state.database.backfill_calls == [result["activities"]]
    assert len(state.database.hrv) == result["hrv_days"] > 0
    assert len(state.database.sleep) == result["sleep_days"] > 0
    assert len(state.database.health) == result["health_days"] > 0
    assert len(state.database.training_status) == result["training_status_days"] > 0
    assert state.database.user_settings[demo_mode.DATASET_ORIGIN_KEY] == demo_mode.DATASET_ORIGIN_DEMO
    assert cache_clears == ["cleared"]


def test_deactivate_demo_mode_clears_dataset(monkeypatch: pytest.MonkeyPatch):
    state = _StubState()
    state.demo_mode = True
    state.selected_provider = demo_mode.DEMO_PROVIDER
    cache_clears: list[str] = []

    monkeypatch.setattr(demo_mode, "clear_data_caches", lambda: cache_clears.append("cleared"))

    demo_mode.deactivate_demo_mode(state)

    assert state.demo_mode is False
    assert state.selected_page == "📊 Дашборд"
    assert state.selected_provider is None
    assert state.current_chat_id is None
    assert state.chat_messages == []
    assert state.switch_to_chat_tab is False
    assert state.clear_context_calls == 1
    assert state.reset_calls == 1
    assert state.database.clear_calls == 1
    assert cache_clears == ["cleared"]
