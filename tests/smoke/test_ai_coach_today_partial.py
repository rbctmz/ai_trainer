"""Smoke: сегодняшний неполный день помечен и не искажает агрегаты коуча (#126)."""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import pytest

from models.ai_tools import AITools
from ui.components.ai_coach_output import format_tool_result
from utils.product_semantics import TODAY_PARTIAL_NOTE_RU


pytestmark = pytest.mark.smoke


class _FakeDB:
    def __init__(self, daily_health=None, activities=None):
        self._daily_health = daily_health if daily_health is not None else pd.DataFrame()
        self._activities = activities if activities is not None else pd.DataFrame()

    def get_daily_health(self, days):
        return self._daily_health

    def get_activities(self, days):
        return self._activities


def _daily_health_frame() -> pd.DataFrame:
    today = date.today()
    rows = [
        {
            # offset=7 — самый старый день; шаги растут к сегодняшнему дню,
            # чтобы тренд по завершённым дням был однозначно "increasing".
            "date": pd.Timestamp(today - timedelta(days=offset)),
            "steps": 10000 - offset * 100,
            "resting_hr": 50,
            "active_minutes": 60,
            "calories_active": 500,
        }
        for offset in range(1, 8)
    ]
    rows.append(
        {
            "date": pd.Timestamp(today),
            "steps": 1200,  # день ещё идёт — мало шагов
            "resting_hr": 50,
            "active_minutes": 5,
            "calories_active": 40,
        }
    )
    return pd.DataFrame(rows)


def _activities_frame() -> pd.DataFrame:
    today = pd.Timestamp(date.today())
    return pd.DataFrame(
        [
            {"date": today, "sport": "running", "duration_minutes": 40.0, "distance_km": 8.0, "tss": 50.0},
            {"date": today - pd.Timedelta(days=1), "sport": "cycling", "duration_minutes": 90.0, "distance_km": 40.0, "tss": 80.0},
        ]
    )


def test_daily_health_stats_exclude_today_from_aggregates_and_mark_partial():
    tools = AITools(_FakeDB(daily_health=_daily_health_frame()))

    result = tools.get_daily_health_stats(days=8)

    # Средние/сумма — только по 7 завершённым дням (9300..9900 шагов).
    assert result["aggregates_exclude_today"] is True
    assert result["stats"]["avg_steps"] == pytest.approx(9600)
    assert result["stats"]["total_steps"] == 67200
    # С сегодняшними 1200 шагами тренд стал бы "decreasing".
    assert result["trend_steps"] == "increasing"

    today_entries = [e for e in result["recent_entries"] if e["is_today_partial"]]
    assert len(today_entries) == 1
    assert TODAY_PARTIAL_NOTE_RU in today_entries[0]["date_label"]
    completed_entries = [e for e in result["recent_entries"] if not e["is_today_partial"]]
    assert completed_entries
    assert all(TODAY_PARTIAL_NOTE_RU not in e["date_label"] for e in completed_entries)


def test_daily_health_stats_formatting_shows_today_partial_note():
    tools = AITools(_FakeDB(daily_health=_daily_health_frame()))

    formatted = format_tool_result("get_daily_health_stats", tools.get_daily_health_stats(days=8))

    assert "Средние значения — без сегодняшнего неполного дня" in formatted
    assert "Шаги: 9600 в день" in formatted
    # Метка стоит ровно на одной строке — сегодняшней.
    assert formatted.count(TODAY_PARTIAL_NOTE_RU) == 1


def test_recent_activities_mark_today_row():
    tools = AITools(_FakeDB(activities=_activities_frame()))

    result = tools.get_recent_activities(limit=5)

    assert [a["is_today_partial"] for a in result["activities"]] == [True, False]
    assert TODAY_PARTIAL_NOTE_RU in result["activities"][0]["date_label"]
    assert TODAY_PARTIAL_NOTE_RU not in result["activities"][1]["date_label"]

    formatted = format_tool_result("get_recent_activities", result)
    assert formatted.count(TODAY_PARTIAL_NOTE_RU) == 1
