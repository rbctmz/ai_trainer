"""Smoke coverage for api/planning_service.py's _forecast TSB-zone migration
(issue #63).

_forecast used its own clean 4-way TSB split (5/-10/-30), disagreeing with
the canonical models.banister.tsb_zone() (-20/-10/+10). Since both are
already 4-way, this is a straight boundary swap with no message retired.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from api.planning_service import _TSB_TONE_TO_FORECAST_MESSAGE, _forecast
from models.banister import BanisterModel, tsb_zone


def test_tone_to_message_covers_all_four_canonical_tones():
    assert set(_TSB_TONE_TO_FORECAST_MESSAGE) == {"success", "neutral", "warning", "danger"}
    assert _TSB_TONE_TO_FORECAST_MESSAGE["danger"] == "🔴 Высокий риск переутомления — снизьте нагрузку."
    assert _TSB_TONE_TO_FORECAST_MESSAGE["success"] == "🟢 Отличный прогноз — выход в пиковую форму."


def test_forecast_message_matches_final_tsb_zone_for_heavy_sustained_load():
    banister = BanisterModel()
    start = date(2026, 1, 5)
    daily_plan = [
        (datetime.combine(start, datetime.min.time()) + timedelta(days=i), 120.0, {})
        for i in range(21)
    ]

    result = _forecast(banister, {"ctl": 40, "atl": 40}, daily_plan, start)

    assert tsb_zone(result["final_tsb"])["tone"] == "danger"
    assert result["message"] == _TSB_TONE_TO_FORECAST_MESSAGE["danger"]


def test_forecast_message_matches_final_tsb_zone_for_extended_rest():
    banister = BanisterModel()
    start = date(2026, 1, 5)
    daily_plan = [
        (datetime.combine(start, datetime.min.time()) + timedelta(days=i), 0.0, {})
        for i in range(30)
    ]

    result = _forecast(banister, {"ctl": 50, "atl": 50}, daily_plan, start)

    assert tsb_zone(result["final_tsb"])["tone"] == "success"
    assert result["message"] == _TSB_TONE_TO_FORECAST_MESSAGE["success"]
