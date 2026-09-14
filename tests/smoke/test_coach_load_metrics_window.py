"""Smoke coverage for issue #134 stable coach load-metrics window."""
from __future__ import annotations

import asyncio
import json
from datetime import date, datetime, timedelta, timezone
from typing import Any

import pytest

from data.database import Database
from models.ai_tools import AITools, COACH_LOAD_METRICS_WINDOW_DAYS
from models.signals_engine import assemble_signals


pytestmark = pytest.mark.smoke


def _events(streaming_response) -> list[dict[str, Any]]:
    async def collect() -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        async for raw in streaming_response.body_iterator:
            text = raw if isinstance(raw, str) else raw.decode()
            if text.startswith("data:"):
                out.append(json.loads(text[5:].strip()))
        return out

    return asyncio.run(collect())


def _seed_daily_tss(db: Database, daily_tss_oldest_first: list[float]) -> str:
    base = datetime.now()
    n = len(daily_tss_oldest_first)
    for i, tss in enumerate(daily_tss_oldest_first):
        date_str = (base - timedelta(days=n - 1 - i)).strftime("%Y-%m-%d")
        db.save_activities(
            [
                {
                    "activity_id": f"coach-window-{i}",
                    "date": date_str,
                    "sport": "cycling",
                    "duration_minutes": 60,
                    "distance_km": 24.0,
                    "tss": float(tss),
                }
            ]
        )
    return base.strftime("%Y-%m-%d")


def test_performance_metrics_ignore_days_for_ctl_atl_tsb(tmp_path):
    db = Database(str(tmp_path / "metrics_window.db"))
    as_of_date = _seed_daily_tss(db, [20.0] * 40 + [80.0] * 10 + [5.0] * 15)

    metrics_7d = AITools(db).get_performance_metrics(days=7)
    metrics_60d = AITools(db).get_performance_metrics(days=60)

    assert metrics_7d["report_period_days"] == 7
    assert metrics_60d["report_period_days"] == 60
    assert metrics_7d["metrics_window_days"] == COACH_LOAD_METRICS_WINDOW_DAYS
    assert metrics_60d["metrics_window_days"] == COACH_LOAD_METRICS_WINDOW_DAYS
    assert metrics_7d["as_of_date"] == as_of_date
    assert metrics_60d["as_of_date"] == as_of_date
    assert metrics_7d["ctl"] == pytest.approx(metrics_60d["ctl"], abs=0.01)
    assert metrics_7d["atl"] == pytest.approx(metrics_60d["atl"], abs=0.01)
    assert metrics_7d["tsb"] == pytest.approx(metrics_60d["tsb"], abs=0.01)


def test_performance_metrics_anchor_is_athlete_day(tmp_path, monkeypatch):
    """Host pinned to 09-13, athlete already 09-14: the anchor must be 09-14 (#577)."""
    from config.settings import Settings
    from models import ai_tools
    from utils import athlete_time

    class PinnedAthleteInstant(datetime):
        @classmethod
        def now(cls, tz=None):
            instant = datetime(2026, 9, 13, 22, tzinfo=timezone.utc)
            return instant.astimezone(tz) if tz else instant.replace(tzinfo=None)

    class HostDay(date):
        @classmethod
        def today(cls):
            return date(2026, 9, 13)

    monkeypatch.setattr(Settings, "ATHLETE_TIMEZONE", "Europe/Moscow")
    monkeypatch.setattr(athlete_time, "datetime", PinnedAthleteInstant)
    monkeypatch.setattr(ai_tools, "date", HostDay)

    empty = AITools(Database(str(tmp_path / "athlete_empty.db"))).get_performance_metrics()
    assert empty["computed_for"] == "2026-09-14"

    db = Database(str(tmp_path / "athlete_metrics.db"))
    db.save_activities(
        [
            {
                "activity_id": "athlete-anchor-1",
                "date": "2026-09-13",
                "sport": "cycling",
                "duration_minutes": 60,
                "distance_km": 24.0,
                "tss": 50.0,
            }
        ]
    )
    result = AITools(db).get_performance_metrics(days=30)
    assert result["computed_for"] == result["as_of_date"] == "2026-09-14"
    activities = db.get_activities(COACH_LOAD_METRICS_WINDOW_DAYS)
    athlete_load = assemble_signals(activities_df=activities, as_of=date(2026, 9, 14))["load"]
    host_load = assemble_signals(activities_df=activities, as_of=date(2026, 9, 13))["load"]
    assert athlete_load["tsb"] == pytest.approx(-4.6)
    assert host_load["tsb"] == pytest.approx(-5.5)
    assert result["tsb"] == pytest.approx(athlete_load["tsb"])
    assert result["tsb"] != pytest.approx(host_load["tsb"])


def test_coach_meta_and_decision_log_include_load_window(tmp_path, monkeypatch):
    from config.settings import Settings

    monkeypatch.setattr(Settings, "CHATS_DIR", str(tmp_path / "chats"), raising=False)

    from api.routers import coach as coach_mod

    db = Database(str(tmp_path / "coach_window.db"))
    as_of_date = _seed_daily_tss(db, [40.0] * 35)

    req = coach_mod.ChatRequest(message="Дай краткий брифинг", provider="mock")
    events = _events(coach_mod.coach_chat(req, db))

    meta = events[0]
    assert meta["type"] == "meta"
    assert meta["metrics_window_days"] == COACH_LOAD_METRICS_WINDOW_DAYS
    assert meta["as_of_date"] == as_of_date
    assert meta["load_metrics"]["metrics_window_days"] == COACH_LOAD_METRICS_WINDOW_DAYS
    assert meta["load_metrics"]["as_of_date"] == as_of_date

    decisions = db.get_coach_decisions(days=30)
    assert len(decisions) == 1
    assert decisions[0]["metrics_window_days"] == COACH_LOAD_METRICS_WINDOW_DAYS
    assert decisions[0]["as_of_date"] == as_of_date
