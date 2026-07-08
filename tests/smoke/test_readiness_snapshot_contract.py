"""Smoke tests for the shared readiness snapshot API contract.

Contributor-safe: temp SQLite only, no Garmin credentials, no network.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta
from typing import Any

from data.database import Database


def _events(streaming_response) -> list[dict[str, Any]]:
    async def collect() -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        async for raw in streaming_response.body_iterator:
            text = raw if isinstance(raw, str) else raw.decode()
            if text.startswith("data:"):
                out.append(json.loads(text[5:].strip()))
        return out

    return asyncio.run(collect())


def _seed_activity(db: Database, date_str: str | None = None) -> None:
    date_str = date_str or datetime.now().strftime("%Y-%m-%d")
    db.save_activities(
        [
            {
                "activity_id": f"act-{date_str}",
                "date": date_str,
                "sport": "running",
                "duration_minutes": 35,
                "distance_km": 5.5,
                "tss": 32.0,
            }
        ]
    )


def _seed_full_readiness(db: Database, date_str: str | None = None) -> None:
    date_str = date_str or datetime.now().strftime("%Y-%m-%d")
    db.sync_sleep_data(
        {
            date_str: {
                "total_sleep_minutes": 480,
                "sleep_score": 82.0,
                "sleep_efficiency": 94.0,
            }
        }
    )
    db.sync_hrv_data({date_str: {"rmssd": 45.0, "stress_score": 20.0, "recovery_score": 77.0}})
    db.sync_daily_health({date_str: {"resting_hr": 52, "steps": 8500}})
    db.sync_training_status(
        {
            date_str: {
                "training_status": "PRODUCTIVE",
                "training_readiness": 78.0,
                "recovery_time_hours": 14.0,
            }
        }
    )


def test_readiness_snapshot_empty_db_is_unknown_and_provisional(tmp_path):
    from api.readiness_snapshot import build_readiness_snapshot

    snapshot = build_readiness_snapshot(Database(str(tmp_path / "empty.db")))

    assert snapshot["score"] is None
    assert snapshot["status"] == "unknown"
    assert snapshot["computed_at"] is None
    assert snapshot["is_provisional"] is True
    assert snapshot["source_completeness"] == 0.0
    assert set(snapshot["missing_inputs"]) == {
        "sleep",
        "hrv",
        "resting_hr",
        "training_readiness",
    }
    assert snapshot["stale"] is False
    assert snapshot["factors"] == []
    assert "Недостаточно" in snapshot["reason"]


def test_readiness_snapshot_full_data_is_complete_and_anchored(tmp_path):
    from api.readiness_snapshot import build_readiness_snapshot

    db = Database(str(tmp_path / "full.db"))
    _seed_full_readiness(db)

    snapshot = build_readiness_snapshot(db)

    assert snapshot["score"] is not None
    assert snapshot["status"] in {"limited", "ready", "strong"}
    assert snapshot["computed_at"] == datetime.now().strftime("%Y-%m-%d")
    assert snapshot["is_provisional"] is False
    assert snapshot["source_completeness"] == 1.0
    assert snapshot["missing_inputs"] == []
    assert snapshot["stale"] is False
    assert {factor["key"] for factor in snapshot["factors"]} >= {
        "sleep",
        "hrv",
        "resting_hr",
        "training_readiness",
    }


def test_readiness_snapshot_partial_data_lists_missing_inputs(tmp_path):
    from api.readiness_snapshot import build_readiness_snapshot

    db = Database(str(tmp_path / "partial.db"))
    today = datetime.now().strftime("%Y-%m-%d")
    db.sync_sleep_data({today: {"total_sleep_minutes": 420, "sleep_score": 68.0}})
    db.sync_hrv_data({today: {"rmssd": 35.0, "stress_score": 30.0}})

    snapshot = build_readiness_snapshot(db)

    assert snapshot["score"] is not None
    assert snapshot["is_provisional"] is True
    assert snapshot["source_completeness"] == 0.5
    assert snapshot["missing_inputs"] == ["resting_hr", "training_readiness"]
    assert "частичным" in snapshot["reason"]


def test_readiness_snapshot_stale_data_is_marked_stale(tmp_path):
    from api.readiness_snapshot import build_readiness_snapshot

    db = Database(str(tmp_path / "stale.db"))
    old = (datetime.now() - timedelta(days=8)).strftime("%Y-%m-%d")
    _seed_full_readiness(db, old)

    snapshot = build_readiness_snapshot(db, stale_after_days=2)

    assert snapshot["score"] is not None
    assert snapshot["computed_at"] == old
    assert snapshot["stale"] is True
    assert snapshot["status"] == "stale"
    assert snapshot["is_provisional"] is True
    assert "устар" in snapshot["reason"].lower()


def test_dashboard_summary_exposes_readiness_snapshot(tmp_path):
    from api.deps import make_headless_state
    from api.routers.dashboard import dashboard_summary

    db = Database(str(tmp_path / "dashboard.db"))
    _seed_activity(db)
    _seed_full_readiness(db)

    payload = dashboard_summary(db=db, state=make_headless_state(database=db))

    assert payload["has_data"] is True
    snapshot = payload["readiness_snapshot"]
    assert snapshot["score"] is not None
    assert snapshot["source_completeness"] == 1.0


def test_planning_status_exposes_readiness_snapshot(tmp_path):
    from api.routers.planning import planning_status

    db = Database(str(tmp_path / "planning.db"))
    _seed_activity(db)
    _seed_full_readiness(db)

    payload = planning_status(db=db)

    assert payload["metrics"]
    assert payload["readiness_snapshot"]["score"] is not None
    assert payload["readiness_snapshot"]["is_provisional"] is False


def test_coach_stream_meta_exposes_readiness_snapshot(tmp_path, monkeypatch):
    from config.settings import Settings

    monkeypatch.setattr(Settings, "CHATS_DIR", str(tmp_path / "chats"), raising=False)

    from api.routers import coach as coach_mod

    db = Database(str(tmp_path / "coach.db"))
    _seed_activity(db)
    _seed_full_readiness(db)

    req = coach_mod.ChatRequest(message="Как восстановление?", provider="mock")
    events = _events(coach_mod.coach_chat(req, db))

    assert events[0]["type"] == "meta"
    snapshot = events[0]["readiness_snapshot"]
    assert snapshot["score"] is not None
    assert snapshot["source_completeness"] == 1.0
