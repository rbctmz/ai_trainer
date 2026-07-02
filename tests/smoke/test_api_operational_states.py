"""Contributor-safe smoke tests for explicit web API operational state.

These tests exercise router functions directly with temporary SQLite databases.
They require no Garmin credentials, no network, and no real AI provider.
"""
from __future__ import annotations

import asyncio
import json

from data.database import Database
from services import sync as sync_service


def _events(streaming_response) -> list[dict]:
    async def collect() -> list[dict]:
        out = []
        async for raw in streaming_response.body_iterator:
            text = raw if isinstance(raw, str) else raw.decode()
            if text.startswith("data:"):
                out.append(json.loads(text[5:].strip()))
        return out

    return asyncio.run(collect())


def test_empty_read_endpoints_expose_operational_state(tmp_path):
    from api.routers.activities import list_activities
    from api.routers.dashboard import dashboard_summary
    from api.routers.hrv import hrv_summary
    from api.routers.sleep import sleep_summary
    from api.deps import make_headless_state

    db = Database(str(tmp_path / "empty.db"))
    payloads = [
        dashboard_summary(db=db, state=make_headless_state(database=db)),
        list_activities(days=30, db=db),
        hrv_summary(days=30, db=db),
        sleep_summary(days=30, db=db),
    ]

    for payload in payloads:
        assert payload["has_data"] is False
        state = payload["operational_state"]
        assert state["status"] == "empty"
        assert state["empty"] is True
        assert state["stale"] is False
        assert state["demo"] is False
        assert state["mode"] == "live"
        assert state["latest_data_at"] is None
        assert state["sync_state"] == "idle"
        assert state["error"] is None


def test_demo_payload_exposes_demo_mode_and_latest_timestamp(tmp_path):
    from api.deps import make_headless_state
    from api.routers.activities import list_activities
    from services import demo_mode as demo_service

    db = Database(str(tmp_path / "demo.db"))
    demo_service.activate_demo_mode(make_headless_state(database=db))

    payload = list_activities(days=60, db=db, demo=True)

    assert payload["has_data"] is True
    state = payload["operational_state"]
    assert state["status"] in {"ready", "stale"}
    assert state["mode"] == "demo"
    assert state["demo"] is True
    assert state["empty"] is False
    assert state["latest_data_at"] is not None


def test_old_activity_payload_is_explicitly_stale(tmp_path):
    from api.routers.activities import list_activities

    db = Database(str(tmp_path / "stale.db"))
    db.save_activities(
        [
            {
                "activity_id": "old-1",
                "date": "2000-01-01",
                "sport": "running",
                "duration_minutes": 30,
                "distance_km": 5.0,
                "tss": 25.0,
            }
        ]
    )

    payload = list_activities(days=36500, db=db)

    assert payload["has_data"] is True
    state = payload["operational_state"]
    assert state["status"] == "stale"
    assert state["stale"] is True
    assert state["empty"] is False
    assert state["latest_data_at"].startswith("2000-01-01")


def test_sync_status_contracts_are_machine_readable(tmp_path, monkeypatch):
    from api.routers import system as system_mod

    idle = system_mod.sync_status(db=Database(str(tmp_path / "idle.db")))
    assert idle["sync_state"] == "idle"
    assert idle["operational_state"]["sync_state"] == "idle"
    assert idle["operational_state"]["status"] in {"empty", "ready", "stale"}

    result = sync_service.GarminSyncResult(
        activity_result={"new": 1, "updated": 0, "skipped": 0},
        hrv_result={"new": 0, "updated": 0},
        sleep_result={"new": 0, "updated": 0},
        health_result={"new": 0, "updated": 0},
        training_status_result={"new": 0, "updated": 0},
        mode="incremental",
        days=1,
    )
    db = Database(str(tmp_path / "sync.db"))
    monkeypatch.setattr(system_mod.Settings, "GARMIN_EMAIL", "user@example.com", raising=False)
    monkeypatch.setattr(system_mod.Settings, "GARMIN_PASSWORD", "secret", raising=False)
    monkeypatch.setattr(system_mod, "real_database", lambda: db)
    monkeypatch.setattr(system_mod.garmin_service, "authenticate", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(system_mod.sync_service, "sync_garmin_data", lambda *_args, **_kwargs: result)

    completed = system_mod.sync(system_mod.SyncRequest(days=1))
    assert completed["sync_state"] == "succeeded"
    assert completed["operational_state"]["sync_state"] == "succeeded"
    assert completed["operational_state"]["error"] is None

    partial = sync_service.GarminSyncResult(warnings=["sleep unavailable"], mode="full", days=7)
    monkeypatch.setattr(system_mod.sync_service, "sync_garmin_data", lambda *_args, **_kwargs: partial)
    partial_payload = system_mod.sync(system_mod.SyncRequest(days=7))
    assert partial_payload["sync_state"] == "partial"
    assert partial_payload["operational_state"]["sync_state"] == "partial"


def test_coach_stream_meta_and_history_expose_operational_state(tmp_path, monkeypatch):
    from config.settings import Settings

    monkeypatch.setattr(Settings, "CHATS_DIR", str(tmp_path / "chats"), raising=False)

    from api.routers import coach as coach_mod

    req = coach_mod.ChatRequest(message="Что делать сегодня?", provider="mock")
    resp = coach_mod.coach_chat(req, Database(str(tmp_path / "coach.db")))
    events = _events(resp)

    assert events[0]["type"] == "meta"
    assert events[0]["operational_state"]["status"] == "empty"
    chat_id = events[0]["chat_id"]

    history = coach_mod.coach_history(db=Database(str(tmp_path / "coach.db")))
    assert history["operational_state"]["sync_state"] == "idle"

    detail = coach_mod.coach_history_detail(chat_id, db=Database(str(tmp_path / "coach.db")))
    assert detail["operational_state"]["status"] == "empty"
