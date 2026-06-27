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
                "sport": "running",
                "duration_minutes": 45,
                "distance_km": 9.0,
                "tss": 40.0,
            }
        ]
    )
    payload = list_activities(days=30, db=db)
    assert payload["has_data"] is True
    assert payload["count"] == 1
    assert payload["items"][0]["sport"] == "running"
    assert payload["totals"]["tss"] == 40.0


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


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
