"""Smoke coverage for the coach decision audit trail."""
from __future__ import annotations

import asyncio
import json

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


def test_database_persists_coach_decisions(tmp_path):
    db = Database(str(tmp_path / "decisions.db"))

    saved = db.save_coach_decision(
        decision_type="Recovery",
        reason="TSB -24.0: лучше снизить интенсивность сегодня.",
        chat_id="chat-1",
        message_id="msg-1",
    )

    assert saved["id"]
    assert saved["decision_type"] == "Recovery"
    assert saved["reason"] == "TSB -24.0: лучше снизить интенсивность сегодня."
    assert saved["chat_id"] == "chat-1"
    assert saved["message_id"] == "msg-1"
    assert saved["created_at"]

    rows = db.get_coach_decisions(days=30)
    assert len(rows) == 1
    assert rows[0]["id"] == saved["id"]
    assert rows[0]["date"] == saved["date"]


def test_decisions_api_groups_by_day_and_exposes_empty_state(tmp_path):
    from api.routers.decisions import list_decisions

    db = Database(str(tmp_path / "decisions.db"))

    empty = list_decisions(db=db)
    assert empty["has_data"] is False
    assert empty["days"] == []
    assert empty["operational_state"]["status"] == "empty"

    db.save_coach_decision("Monitor", "Недостаточно сильного сигнала для изменения нагрузки.", date="2026-07-02T09:00:00")
    db.save_coach_decision("Push", "TSB +5.0 и readiness 82: можно выполнить качественную работу.", date="2026-07-02T12:00:00")
    db.save_coach_decision("Recovery", "TSB -25.0: восстановительный день приоритетнее.", date="2026-07-01T08:00:00")

    payload = list_decisions(db=db)
    assert payload["has_data"] is True
    assert [day["date"] for day in payload["days"]] == ["2026-07-02", "2026-07-01"]
    assert [item["decision_type"] for item in payload["days"][0]["decisions"]] == ["Push", "Monitor"]
    assert payload["days"][0]["decisions"][0]["time"] == "12:00"
    assert payload["operational_state"]["status"] == "ready"


def test_coach_completion_writes_decision_record(tmp_path, monkeypatch):
    from config.settings import Settings

    monkeypatch.setattr(Settings, "CHATS_DIR", str(tmp_path / "chats"), raising=False)

    from api.routers import coach as coach_mod
    from api.routers.decisions import list_decisions

    db = Database(str(tmp_path / "coach.db"))
    req = coach_mod.ChatRequest(
        message="Что делать сегодня при усталости?",
        provider="mock",
    )

    resp = coach_mod.coach_chat(req, db)
    events = _events(resp)

    assert events[-1]["type"] == "done"
    payload = list_decisions(db=db)
    assert payload["has_data"] is True
    assert len(payload["days"]) == 1
    decision = payload["days"][0]["decisions"][0]
    assert decision["decision_type"] in {"Push", "Moderate", "Recovery", "Monitor"}
    assert decision["reason"]
    assert "\n" not in decision["reason"]
    assert decision["chat_id"] == events[0]["chat_id"]
    assert decision["message_id"] == events[-1]["message_id"]


def test_routes_register_decisions_endpoint():
    import importlib

    main = importlib.import_module("api.main")
    paths = set(main.app.openapi()["paths"].keys())
    assert "/api/decisions" in paths
