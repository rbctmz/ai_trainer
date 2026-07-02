"""Smoke tests for issue #54: TSB zones must agree across StatusRow,
DailyOutlook and the tooltips, and the "phase" shown must be a real
periodization phase (Base/Build/Peak/Taper) — never a fatigue-state label.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from api.routers.dashboard import _generate_daily_outlook
from models.banister import tsb_zone as _tsb_zone
from models.training_planner import current_periodization_phase

_PHASES = {"Base", "Build", "Peak", "Taper"}


def test_tsb_zone_boundaries_match_state_label_thresholds():
    # ui/pages/dashboard.py's state_label uses tsb < -20 ("Нужна разгрузка")
    # and tsb > -10 (part of "Готов к работе"). _TSB_ZONES must share these
    # break points so the СОСТОЯНИЕ card and the TSB tooltip never disagree
    # about where one zone ends and the next begins.
    assert _tsb_zone(-20.1)["tone"] == "danger"
    assert _tsb_zone(-20.0)["tone"] == "warning"
    assert _tsb_zone(-10.1)["tone"] == "warning"
    assert _tsb_zone(-10.0)["tone"] == "neutral"
    assert _tsb_zone(9.9)["tone"] == "neutral"
    assert _tsb_zone(10.0)["tone"] == "success"


def test_daily_outlook_omits_phase_clause_without_goal_plan():
    outlook = _generate_daily_outlook(
        goal_plan=None, ctl=30, tsb=-13.8, hrv=45, sleep_hours=7, readiness=60
    )
    assert "Фаза" not in outlook["text"]
    assert "TSB -13.8" in outlook["text"]


def test_daily_outlook_uses_real_periodization_phase_not_fatigue_label():
    event_date = (date.today() + timedelta(weeks=32)).isoformat()
    goal_plan = {"goal_type": "Триатлон", "distance": "Олимпийка",
                 "event_date": event_date, "weeks_to_race": 32}

    outlook = _generate_daily_outlook(
        goal_plan=goal_plan, ctl=25, tsb=-13.8, hrv=37, sleep_hours=4.1, readiness=55
    )

    assert "Фаза «" in outlook["text"]
    phase_used = outlook["text"].split("Фаза «", 1)[1].split("»", 1)[0]
    assert phase_used in _PHASES, (
        f"daily_outlook phase must be a periodization phase, got {phase_used!r} "
        "— this is the exact bug from issue #54 (load_state_label leaking in as 'phase')"
    )


def test_daily_outlook_tone_reflects_worse_of_tsb_zone_and_flags():
    # Deep-fatigue TSB with no red flags must still surface a danger tone —
    # the tone must not silently downgrade to "neutral" just because sleep/
    # HRV/readiness happen to look fine.
    outlook = _generate_daily_outlook(
        goal_plan=None, ctl=40, tsb=-25.0, hrv=50, sleep_hours=8, readiness=80
    )
    assert outlook["tone"] == "danger"


def test_current_periodization_phase_none_without_active_plan():
    assert current_periodization_phase(None) is None
    assert current_periodization_phase({}) is None


def test_current_periodization_phase_returns_known_phase():
    event_date = (date.today() + timedelta(weeks=10)).isoformat()
    goal_plan = {"event_date": event_date, "weeks_to_race": 16}
    resolved = current_periodization_phase(goal_plan)
    assert resolved is not None
    assert resolved["phase"] in _PHASES
    assert resolved["days_to_race"] >= 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
