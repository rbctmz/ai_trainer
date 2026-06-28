"""Smoke tests for Phase 1 API endpoints: coach, hrv, activities.

Contributor-safe: temp SQLite, temp chats dir, Mock AI provider — no network,
no real Garmin, no real AI keys.
"""
from __future__ import annotations

import asyncio
import importlib
import json

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
    assert payload == {"has_data": False, "count": 0, "totals": {}, "items": []}


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
                "distance_km": 9.0,
                "tss": 40.0,
            }
        ]
    )
    payload = list_activities(days=30, db=db)
    assert payload["has_data"] is True
    assert payload["count"] == 1
    assert payload["items"][0]["sport"] == "swim"
    assert payload["items"][0]["sport_label"] == "плавание"
    assert payload["items"][0]["date_label"].count(".") == 2
    assert payload["totals"]["tss"] == 40.0


def test_hrv_with_data_exposes_date_labels(tmp_path):
    from api.routers.hrv import hrv_summary

    db = Database(str(tmp_path / "h.db"))
    db.save_hrv_data(
        {
            "2026-06-26": {"rmssd": 31.0, "stress_score": 22.0, "recovery_score": 70.0},
            "2026-06-27": {"rmssd": 29.5, "stress_score": 25.0, "recovery_score": 66.0},
        }
    )

    payload = hrv_summary(days=30, db=db)

    assert payload["has_data"] is True
    assert payload["latest"]["date"] == "2026-06-27"
    assert payload["latest"]["date_label"] == "27.06.2026"
    assert payload["trend"][-1]["date_label"] == "27.06.2026"


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


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
