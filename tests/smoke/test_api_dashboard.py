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

    assert payload["has_data"] is False
    assert payload["summary"] is None
    assert payload["operational_state"]["status"] == "empty"


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


def test_dashboard_widgets_empty_db_envelope(tmp_path):
    """A fresh/empty account must not fabricate a Training Score.

    With zero activities, CTL/ATL/TSB are all zero; the score's defaults
    (TSB 0 → load 85, ramp 0 → prog 45, no plan → cons 50) would otherwise
    render a confident total ~40 "Нормально" plus a Daily Outlook claiming
    "восстановление в норме — ограничений нет", contradicting has_data.
    The contract is: derived widgets are withheld (None) when has_data is False.
    """
    from api.routers.dashboard import dashboard_widgets

    empty_db = Database(str(tmp_path / "empty.db"))
    payload = dashboard_widgets(db=empty_db, state=_headless_state())

    assert payload["has_data"] is False
    # Keys are always present, but the activity-derived widgets are withheld.
    assert payload["training_score"] is None
    assert payload["daily_outlook"] is None
    assert payload["race_projection"] is None


def test_dashboard_widgets_contract_with_data(tmp_path):
    """When activities exist, the Training Score is present and well-formed."""
    from datetime import timedelta

    from api.routers.dashboard import dashboard_widgets

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

    payload = dashboard_widgets(db=db, state=_headless_state())

    assert payload["has_data"] is True
    score = payload["training_score"]
    assert score is not None
    assert isinstance(score["total"], int) and 0 <= score["total"] <= 100
    assert score["label"]
    for sub in ("fitness", "progression", "consistency", "load_mgmt"):
        assert sub in score, f"missing training_score component: {sub}"
        assert set(score[sub]) >= {"score", "label", "detail"}
    outlook = payload["daily_outlook"]
    assert outlook is not None
    assert outlook["text"]
    assert outlook["tone"] in {"danger", "warning", "neutral", "success"}


def test_app_exposes_dashboard_route():
    main = importlib.import_module("api.main")
    paths = set(main.app.openapi()["paths"].keys())
    assert "/api/dashboard/summary" in paths
    assert "/api/health" in paths
    assert "/api/dashboard/widgets" in paths


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
