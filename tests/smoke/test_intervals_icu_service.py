from __future__ import annotations

import json
from datetime import date, datetime

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


def test_build_planned_events_uses_session_template_metadata_when_available():
    day = (
        datetime(2026, 6, 16, 0, 0, 0),
        58.0,
        {"run": 58.0, "bike": 0.0, "swim": 0.0},
    )

    events = intervals_icu.build_planned_events(
        [day],
        "Бег",
        "Полумарафон",
        session_templates=[
            {
                "sport": "run",
                "export_name": "Бег Полумарафон — Качество • бег",
                "description": "План из AI Trainer\nФаза: Build\nФокус: Качество • бег",
            }
        ],
    )

    assert len(events) == 1
    event = events[0]
    assert event["name"] == "Бег Полумарафон — Качество • бег"
    assert event["type"] == "Run"
    assert "Фокус: Качество • бег" in event["description"]


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
    assert captured["headers"]["User-agent"].startswith("AI-Trainer/")
    assert captured["body"]["icu_training_load"] == 60
    assert captured["timeout"] == 15


def test_list_race_events_is_bounded_read_only_and_normalized(monkeypatch):
    client = intervals_icu.IntervalsICUClient(api_key="secret", athlete_id="0")
    captured = {}

    def fake_request(_self, method, path, payload=None, params=None):
        captured.update(method=method, path=path, payload=payload, params=params)
        return [
            {
                "id": 99,
                "category": "RACE_B",
                "start_date_local": "2026-07-26T09:00:00",
                "name": "Минский Триатлон - ОЛИМПИК 56,5",
                "type": "Other",
                "description": "Triathlon: swim bike run",
            },
            {"id": 100, "category": "WORKOUT", "start_date_local": "2026-07-27T07:00:00"},
        ]

    monkeypatch.setattr(intervals_icu.IntervalsICUClient, "_request_json", fake_request)
    events = client.list_race_events(date(2026, 7, 1), date(2026, 12, 31))

    assert captured == {
        "method": "GET",
        "path": "/api/v1/athlete/0/events",
        "payload": None,
        "params": {"oldest": "2026-07-01", "newest": "2026-12-31"},
    }
    assert len(events) == 1
    assert events[0]["priority"] == "B"
    assert events[0]["discipline"] == "triathlon"


def test_list_race_events_rejects_more_than_one_year() -> None:
    client = intervals_icu.IntervalsICUClient(api_key="secret")
    with pytest.raises(ValueError, match="365"):
        client.list_race_events(date(2026, 1, 1), date(2027, 1, 2))


def test_list_execution_evidence_is_bounded_get_and_keeps_match_fields(monkeypatch):
    client = intervals_icu.IntervalsICUClient(api_key="secret", athlete_id="0")
    calls = []

    def fake_request(_self, method, path, payload=None, params=None):
        calls.append({"method": method, "path": path, "payload": payload, "params": params})
        if path.endswith("/activities"):
            return [
                {
                    "id": "i123",
                    "external_id": "garmin-123",
                    "paired_event_id": "e456",
                    "start_date_local": "2026-07-12T08:00:00",
                    "type": "Ride",
                    "name": "Morning Ride",
                    "icu_training_load": 30.2,
                    "moving_time": 3600,
                }
            ]
        return [
            {
                "id": "e456",
                "external_id": "ai_trainer:ats_123",
                "category": "WORKOUT",
                "start_date_local": "2026-07-12T07:00:00",
                "type": "Ride",
                "name": "Planned Ride",
                "uid": "slot-uid",
                "workout_doc": {"steps": [{"duration": 600}]},
                "moving_time": 3600,
                "oauth_client_id": 173,
                "created_by_id": "athlete-1",
            },
            {"id": "race", "category": "RACE_B", "start_date_local": "2026-07-12T09:00:00"},
        ]

    monkeypatch.setattr(intervals_icu.IntervalsICUClient, "_request_json", fake_request)
    activities = client.list_activities(date(2026, 7, 7), date(2026, 7, 13))
    events = client.list_workout_events(date(2026, 7, 7), date(2026, 7, 13))

    assert calls == [
        {
            "method": "GET",
            "path": "/api/v1/athlete/0/activities",
            "payload": None,
            "params": {"oldest": "2026-07-07", "newest": "2026-07-13"},
        },
        {
            "method": "GET",
            "path": "/api/v1/athlete/0/events",
            "payload": None,
            "params": {"oldest": "2026-07-07", "newest": "2026-07-13"},
        },
    ]
    assert activities == [
        {
            "id": "i123",
            "external_id": "garmin-123",
            "paired_event_id": "e456",
            "start_date_local": "2026-07-12T08:00:00",
            "type": "Ride",
            "name": "Morning Ride",
            "icu_training_load": 30.2,
            "moving_time": 3600,
        }
    ]
    assert events == [
        {
            "id": "e456",
            "external_id": "ai_trainer:ats_123",
            "category": "WORKOUT",
            "start_date_local": "2026-07-12T07:00:00",
            "type": "Ride",
            "name": "Planned Ride",
            "uid": "slot-uid",
            "workout_doc": {"steps": [{"duration": 600}]},
            "moving_time": 3600,
            "oauth_client_id": 173,
            "created_by_id": "athlete-1",
        }
    ]


def test_bulk_upsert_and_delete_use_official_event_contract(monkeypatch):
    client = intervals_icu.IntervalsICUClient(api_key="secret", athlete_id="0")
    calls = []

    def fake_request(_self, method, path, payload=None, params=None):
        calls.append({"method": method, "path": path, "payload": payload, "params": params})
        if path.endswith("bulk-delete"):
            return {"eventsDeleted": len(payload)}
        return [
            {
                **payload[0],
                "id": 123,
                "workout_doc": {"steps": [{"duration": 600}]},
            }
        ]

    monkeypatch.setattr(intervals_icu.IntervalsICUClient, "_request_json", fake_request)
    event = {
        "uid": "4ca85f64-9079-52ac-9915-32e5a625223e",
        "external_id": "ai_trainer:ats_123",
        "category": "WORKOUT",
        "start_date_local": "2026-07-15T07:00:00",
        "name": "Endurance",
        "description": "- Warmup 10m 55-70%",
        "type": "Ride",
    }

    upserted = client.upsert_events_by_uid([event])
    deleted = client.delete_events([{"id": 123, "external_id": "ai_trainer:ats_123"}])

    assert upserted[0]["id"] == 123
    assert deleted == 1
    assert calls == [
        {
            "method": "POST",
            "path": "/api/v1/athlete/0/events/bulk",
            "payload": [event],
            "params": {"upsertOnUid": "true", "updatePlanApplied": "true"},
        },
        {
            "method": "PUT",
            "path": "/api/v1/athlete/0/events/bulk-delete",
            "payload": [{"id": 123, "external_id": "ai_trainer:ats_123"}],
            "params": None,
        },
    ]


def test_execution_evidence_rejects_unbounded_window() -> None:
    client = intervals_icu.IntervalsICUClient(api_key="secret")
    with pytest.raises(ValueError, match="90"):
        client.list_activities(date(2026, 1, 1), date(2026, 4, 2))
    with pytest.raises(ValueError, match="newest"):
        client.list_workout_events(date(2026, 7, 13), date(2026, 7, 12))
