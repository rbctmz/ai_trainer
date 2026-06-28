"""Smoke tests for the FastAPI dashboard boundary.

These assert the HTTP envelope contract without needing real Garmin data:
an empty database must yield a valid "no data" envelope, and the route must be
wired into the app. They are contributor-safe (temp SQLite, no network).
"""
from __future__ import annotations

import importlib
from datetime import datetime

import pytest

from data.database import Database
from state import StateManager


def _headless_state() -> StateManager:
    return StateManager({})


def test_dashboard_summary_empty_db_envelope(tmp_path):
    from api.routers.dashboard import dashboard_summary

    empty_db = Database(str(tmp_path / "empty.db"))
    payload = dashboard_summary(db=empty_db, state=_headless_state())

    assert payload == {"has_data": False, "summary": None}


def test_dashboard_summary_contract_with_data(tmp_path):
    """When activities exist, the envelope carries the full summary shape."""
    from api.routers.dashboard import dashboard_summary

    from datetime import datetime, timedelta

    recent = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d")
    db = Database(str(tmp_path / "seeded.db"))
    db.save_activities(
        [
            {
                "activity_id": "a1",
                "date": recent,
                "sport": "cycling",
                "duration_minutes": 60,
                "distance_km": 30.0,
                "tss": 55.0,
            }
        ]
    )

    payload = dashboard_summary(db=db, state=_headless_state())

    assert payload["has_data"] is True
    summary = payload["summary"]
    assert summary is not None
    for key in ("today", "workout", "week", "next_days", "plan", "next_action"):
        assert key in summary, f"missing summary key: {key}"
    assert summary["today"]["tone"] in {"danger", "warning", "success", "neutral"}
    assert summary["today"]["date_label"].split()[0] in {"Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"}
    assert len(summary["next_days"]) == 7
    assert summary["next_days"][0]["label"].split()[0] == ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"][datetime.now().weekday()]
    assert "sport_label" in summary["next_days"][0]


def test_app_exposes_dashboard_route():
    main = importlib.import_module("api.main")
    paths = set(main.app.openapi()["paths"].keys())
    assert "/api/dashboard/summary" in paths
    assert "/api/health" in paths


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
