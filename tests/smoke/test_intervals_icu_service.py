from __future__ import annotations

import json
from datetime import datetime

import pytest

from config.settings import Settings
from services import intervals_icu


pytestmark = pytest.mark.smoke


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def read(self):
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_intervals_connection_info_reports_missing_config(monkeypatch):
    monkeypatch.setattr(Settings, "INTERVALS_ICU_API_KEY", None)
    monkeypatch.setattr(Settings, "INTERVALS_ICU_ATHLETE_ID", "0")
    monkeypatch.setattr(Settings, "INTERVALS_ICU_BASE_URL", "https://intervals.icu")

    info = intervals_icu.connection_info()

    assert info["configured"] is False
    assert info["athlete_id"] == "0"
    assert info["base_url"] == "https://intervals.icu"


def test_build_planned_events_maps_daily_plan_to_intervals_payload():
    day = (
        datetime(2026, 6, 15, 0, 0, 0),
        72.6,
        {"run": 20.0, "bike": 42.6, "swim": 10.0},
    )

    events = intervals_icu.build_planned_events([day], "Триатлон", "Half (70.3)")

    assert len(events) == 1
    event = events[0]
    assert event["category"] == "WORKOUT"
    assert event["type"] == "Ride"
    assert event["icu_training_load"] == 73
    assert event["start_date_local"] == "2026-06-15T07:00:00"
    assert "AI Trainer" in event["description"]


def test_push_planned_events_uses_basic_auth_and_events_endpoint(monkeypatch):
    monkeypatch.setattr(Settings, "INTERVALS_ICU_API_KEY", "secret-key")
    monkeypatch.setattr(Settings, "INTERVALS_ICU_ATHLETE_ID", "0")
    monkeypatch.setattr(Settings, "INTERVALS_ICU_BASE_URL", "https://intervals.icu")

    captured = {}

    def fake_urlopen(request_obj, timeout=0):
        captured["method"] = request_obj.get_method()
        captured["url"] = request_obj.full_url
        captured["headers"] = dict(request_obj.header_items())
        captured["body"] = json.loads(request_obj.data.decode("utf-8"))
        captured["timeout"] = timeout
        return _FakeResponse({"id": 123, "name": captured["body"]["name"]})

    monkeypatch.setattr(intervals_icu.urlrequest, "urlopen", fake_urlopen)

    created = intervals_icu.push_planned_events(
        [
            intervals_icu.build_planned_event_payload(
                datetime(2026, 6, 15),
                60.0,
                {"run": 0.0, "bike": 60.0, "swim": 0.0},
                "Вело",
                "100 км",
            )
        ]
    )

    assert len(created) == 1
    assert created[0]["id"] == 123
    assert captured["method"] == "POST"
    assert captured["url"] == "https://intervals.icu/api/v1/athlete/0/events"
    assert captured["headers"]["Authorization"].startswith("Basic ")
    assert captured["headers"]["Content-type"] == "application/json"
    assert captured["body"]["icu_training_load"] == 60
    assert captured["timeout"] == 15
