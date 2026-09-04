"""Smoke tests for Phase 1 API endpoints: coach, hrv, activities.

Contributor-safe: temp SQLite, temp chats dir, Mock AI provider — no network,
no real Garmin, no real AI keys.
"""
from __future__ import annotations

import asyncio
import importlib
import json
from datetime import date, timedelta

import pytest

from data.database import Database


def _events(streaming_response) -> list[dict]:
    async def collect() -> list[dict]:
        out = []
        async for raw in streaming_response.body_iterator:
            text = raw if isinstance(raw, str) else raw.decode()
            if text.startswith("data:"):
                out.append(json.loads(text[5:].strip()))
        return out

    return asyncio.run(collect())


def test_routes_registered():
    main = importlib.import_module("api.main")
    paths = set(main.app.openapi()["paths"].keys())
    assert {"/api/coach/chat", "/api/coach/history", "/api/hrv/summary", "/api/activities"} <= paths


def test_hrv_empty_envelope(tmp_path):
    from api.routers.hrv import hrv_summary

    payload = hrv_summary(days=30, db=Database(str(tmp_path / "e.db")))
    assert payload["has_data"] is False
    assert payload["trend"] == []


def test_activities_empty_envelope(tmp_path):
    from api.routers.activities import list_activities

    payload = list_activities(days=30, db=Database(str(tmp_path / "e.db")))
    assert payload["has_data"] is False
    assert payload["count"] == 0
    assert payload["totals"] == {}
    assert payload["items"] == []
    assert payload["operational_state"]["status"] == "empty"


def test_activities_with_data(tmp_path):
    from datetime import datetime, timedelta

    from api.routers.activities import list_activities

    db = Database(str(tmp_path / "a.db"))
    db.save_activities(
        [
            {
                "activity_id": "x1",
                "date": (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d"),
                "sport": "open_water_swimming",
                "duration_minutes": 45,
                "moving_duration_minutes": 42,
                "distance_km": 9.0,
                "tss": 28.0,
                "garmin_training_load": 40.0,
                "source_tss": 40.0,
                "tss_method": "hr_tss_swim",
            }
        ]
    )
    payload = list_activities(days=30, db=db)
    assert payload["has_data"] is True
    assert payload["count"] == 1
    assert payload["items"][0]["sport"] == "swim"
    assert payload["items"][0]["sport_label"] == "плавание"
    assert payload["items"][0]["date_label"].count(".") == 2
    assert payload["items"][0]["moving_duration_minutes"] == 42.0
    assert payload["items"][0]["garmin_training_load"] == 40.0
    assert payload["items"][0]["source_tss"] == 40.0
    assert payload["items"][0]["tss_method"] == "hr_tss_swim"
    assert payload["items"][0]["tss_source"] == "heart_rate"
    assert payload["totals"]["tss"] == 28.0


def test_activities_swim_pace_tss_source_exposed(tmp_path):
    from datetime import datetime, timedelta

    from api.routers.activities import list_activities

    db = Database(str(tmp_path / "swim_pace.db"))
    db.save_activities(
        [
            {
                "activity_id": "swim-pace-1",
                "date": (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d"),
                "sport": "lap_swimming",
                "duration_minutes": 43.47,
                "moving_duration_minutes": 40.886,
                "distance_km": 1.6,
                "tss": 49.7,
                "tss_method": "pace_tss_swim",
                "tss_pace_used": 138.0,
            }
        ]
    )

    payload = list_activities(days=30, db=db)

    item = payload["items"][0]
    assert item["tss_method"] == "pace_tss_swim"
    assert item["tss_source"] == "pace"
    assert item["tss_pace_used"] == 138.0


def test_hrv_with_data_exposes_date_labels(tmp_path):
    from api.routers.hrv import hrv_summary

    latest_date = date.today()
    previous_date = latest_date - timedelta(days=1)
    db = Database(str(tmp_path / "h.db"))
    db.save_hrv_data(
        {
            previous_date.isoformat(): {
                "rmssd": 31.0,
                "stress_score": 22.0,
                "recovery_score": 70.0,
            },
            latest_date.isoformat(): {
                "rmssd": 29.5,
                "stress_score": 25.0,
                "recovery_score": 66.0,
            },
        }
    )

    payload = hrv_summary(days=30, db=db)

    assert payload["has_data"] is True
    assert payload["latest"]["date"] == latest_date.isoformat()
    assert payload["latest"]["date_label"] == latest_date.strftime("%d.%m.%Y")
    assert payload["trend"][-1]["date_label"] == latest_date.strftime("%d.%m.%Y")


def test_coach_chat_streams_with_mock(tmp_path, monkeypatch):
    from config.settings import Settings

    monkeypatch.setattr(Settings, "CHATS_DIR", str(tmp_path / "chats"), raising=False)

    from api.routers import coach as coach_mod

    req = coach_mod.ChatRequest(message="Что с восстановлением?", provider="mock")
    resp = coach_mod.coach_chat(req, Database(str(tmp_path / "c.db")))
    events = _events(resp)

    types = [e["type"] for e in events]
    assert types[0] == "meta"
    assert "token" in types
    assert types[-1] == "done"

    chat_id = events[0]["chat_id"]
    # History persisted (user + assistant).
    detail = coach_mod.coach_history_detail(chat_id)
    roles = [m["role"] for m in detail["messages"]]
    assert roles == ["user", "assistant"]


def test_coach_chat_done_event_reports_first_token_ms(tmp_path, monkeypatch):
    """ASR-PERF-2 observation (Issue #241): first_token_ms must be present on
    the SSE `done` event so first-token latency can be watched over time.
    The 5s budget stays an observation, not a gate — provider latency isn't
    deterministic even across live runs of the same provider."""
    from config.settings import Settings

    monkeypatch.setattr(Settings, "CHATS_DIR", str(tmp_path / "chats"), raising=False)

    from api.routers import coach as coach_mod

    req = coach_mod.ChatRequest(message="Что с восстановлением?", provider="mock")
    resp = coach_mod.coach_chat(req, Database(str(tmp_path / "c.db")))
    events = _events(resp)

    done_event = events[-1]
    assert done_event["type"] == "done"
    assert isinstance(done_event["first_token_ms"], (int, float))
    assert done_event["first_token_ms"] >= 0


def test_coach_chat_rejects_empty_final_without_persisting_success(
    tmp_path,
    monkeypatch,
):
    from config.settings import Settings
    from models.chat_manager import ChatManager

    monkeypatch.setattr(Settings, "CHATS_DIR", str(tmp_path / "chats"), raising=False)

    from api.routers import coach as coach_mod

    provider = object()
    monkeypatch.setattr(coach_mod, "resolve_provider", lambda _ptype=None: provider)
    monkeypatch.setattr(coach_mod, "supports_streaming", lambda _provider: True)
    monkeypatch.setattr(
        coach_mod,
        "resolve_turn_tool_results",
        lambda **_kwargs: {
            "rendered_response": "",
            "tool_results": [
                {
                    "tool_name": "get_performance_metrics",
                    "success": True,
                    "raw_result": {"ctl": 30.8},
                    "formatted_result": "CTL 30.8",
                }
            ],
            "native": True,
        },
    )
    monkeypatch.setattr(coach_mod, "stream_tokens", lambda *_args, **_kwargs: iter(()))

    db = Database(str(tmp_path / "empty_final.db"))
    response = coach_mod.coach_chat(
        coach_mod.ChatRequest(message="Дай брифинг"),
        db,
    )
    events = _events(response)

    assert [event["type"] for event in events] == ["meta", "tool_call", "error"]
    assert "пустой ответ" in events[-1]["message"]
    assert not [event for event in events if event["type"] == "token"]
    assert not [event for event in events if event["type"] == "done"]

    chat_id = events[0]["chat_id"]
    saved_messages = ChatManager().get_chat_messages(chat_id)
    assert [message["role"] for message in saved_messages] == ["user"]
    assert db.get_coach_decisions(days=30) == []


def test_coach_chat_synthesizes_final_answer_after_tools(tmp_path, monkeypatch):
    from config.settings import Settings

    monkeypatch.setattr(Settings, "CHATS_DIR", str(tmp_path / "chats"), raising=False)

    from api.routers import coach as coach_mod

    class _DummyProvider:
        def __init__(self):
            self.calls = []

        def generate_response(self, prompt: str, system_prompt: str = "") -> str:
            self.calls.append({"prompt": prompt, "system_prompt": system_prompt})
            if system_prompt:
                return "Финальный actionable ответ без обещаний вернуться позже."
            return "Сейчас соберу данные. [TOOL: get_activities, days=7] Потом вернусь с планом."

    provider = _DummyProvider()
    monkeypatch.setattr(coach_mod, "resolve_provider", lambda _ptype=None: provider)
    monkeypatch.setattr(coach_mod, "supports_streaming", lambda _provider: False)

    req = coach_mod.ChatRequest(message="Что делать сегодня?")
    resp = coach_mod.coach_chat(req, Database(str(tmp_path / "c.db")))
    events = _events(resp)

    assert events[0]["type"] == "meta"
    tool_events = [event for event in events if event["type"] == "tool_call"]
    assert tool_events
    assert tool_events[0]["name"] == "Активности"
    assert tool_events[0]["tool_name"] == "get_activities"
    assert events[-1]["type"] == "done"

    chat_id = events[0]["chat_id"]
    detail = coach_mod.coach_history_detail(chat_id)
    final = detail["messages"][-1]["content"]
    assert final == "Финальный actionable ответ без обещаний вернуться позже."
    assert "вернусь с планом" not in final
    assert len(provider.calls) == 2


def test_coach_chat_rejects_empty_message_with_422(tmp_path):
    """Issue #242: the router's own `HTTPException(422, "message is empty")`
    guard was never exercised -- every existing test sends a non-empty
    message."""
    from fastapi import HTTPException

    from api.routers import coach as coach_mod

    req = coach_mod.ChatRequest(message="   ")
    with pytest.raises(HTTPException) as exc_info:
        coach_mod.coach_chat(req, Database(str(tmp_path / "empty_msg.db")))
    assert exc_info.value.status_code == 422


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
