"""BDD gates for #362: pace-based swim TSS (sTSS) with the CSS threshold.

TrainingPeaks scores swimming by pace: sTSS = hours x IF^3 x 100, where IF is
the ratio of the athlete's threshold pace (CSS) to the workout's average pace.
The exponent is 3, not 2, because water resistance makes physiological stress
grow faster with speed. HR-based swim scoring underestimates load (lower HR
ceiling in water, cooling, dive reflex, wrist-HR inaccuracy), so pace takes
priority whenever both distance and a profile CSS are available. Without a CSS
the existing cascade (HR zones -> HR -> duration heuristic) is unchanged.
"""
from __future__ import annotations

import pytest

from data.data_processor import ActivityProcessor


pytestmark = pytest.mark.smoke


def _swim_row(**overrides):
    """Shape of the 2026-08-03 pool swim (23839956549) plus overrides."""
    row = {
        "sport": "lap_swimming",
        "duration_minutes": 43.47,
        "moving_duration_minutes": 40.886,
        "distance_km": 1.6,
        "avg_hr": 129.0,
    }
    row.update(overrides)
    return row


def test_swim_with_css_uses_pace_tss_cubed():
    resolved = ActivityProcessor.resolve_tss(
        _swim_row(),
        ftp=172.0,
        lthr=163.0,
        swim_threshold_pace_seconds_per_100m=110.0,
    )

    assert resolved["tss_method"] == "pace_tss_swim"
    assert resolved["tss_ftp_used"] is None
    assert resolved["tss_pace_used"] == 110.0
    # avg pace = 40.886 min x 60 / (1.6 km x 10) = 153.32 s/100m;
    # IF = 110 / 153.32 = 0.7174; TSS = 0.6814 h x IF^3 x 100 = 25.2
    assert abs(resolved["tss"] - 25.2) < 0.05


def test_swim_pace_tss_exact_formula():
    resolved = ActivityProcessor.resolve_tss(
        _swim_row(
            duration_minutes=30.0,
            moving_duration_minutes=30.0,
            distance_km=1.0,
        ),
        ftp=172.0,
        lthr=163.0,
        swim_threshold_pace_seconds_per_100m=100.0,
    )

    assert resolved["tss_method"] == "pace_tss_swim"
    # avg pace = 30 min x 60 / 10 = 180 s/100m; IF = 100/180 = 0.5556;
    # TSS = 0.5 h x 0.5556^3 x 100 = 8.6
    assert abs(resolved["tss"] - 8.6) < 0.05


def test_swim_without_css_keeps_hr_cascade():
    resolved = ActivityProcessor.resolve_tss(
        _swim_row(),
        ftp=172.0,
        lthr=163.0,
    )

    assert resolved["tss_method"] == "hr_tss_swim"
    assert resolved["tss_pace_used"] is None
    # IF = 129/163 = 0.7914; TSS = 0.6814 h x IF^2 x 100 = 42.7
    assert abs(resolved["tss"] - 42.7) < 0.05


def test_swim_without_distance_falls_back():
    resolved = ActivityProcessor.resolve_tss(
        _swim_row(distance_km=0.0),
        ftp=172.0,
        lthr=163.0,
        swim_threshold_pace_seconds_per_100m=110.0,
    )

    assert resolved["tss_method"] != "pace_tss_swim"
    assert resolved["tss"] > 0


def test_swim_implausibly_fast_average_pace_falls_back():
    resolved = ActivityProcessor.resolve_tss(
        _swim_row(duration_minutes=1.0, moving_duration_minutes=1.0, distance_km=1.0),
        ftp=172.0,
        lthr=163.0,
        swim_threshold_pace_seconds_per_100m=110.0,
    )

    assert resolved["tss_method"] != "pace_tss_swim"


def test_swim_pace_tss_works_without_hr_data():
    resolved = ActivityProcessor.resolve_tss(
        _swim_row(avg_hr=None),
        ftp=172.0,
        lthr=163.0,
        swim_threshold_pace_seconds_per_100m=110.0,
    )

    assert resolved["tss_method"] == "pace_tss_swim"
    assert abs(resolved["tss"] - 25.2) < 0.05


def test_swim_without_any_signals_falls_back_to_swim_heuristic():
    resolved = ActivityProcessor.resolve_tss(
        _swim_row(avg_hr=None),
        ftp=172.0,
        lthr=163.0,
    )

    assert resolved["tss_method"] == "heuristic_duration_swim"
    # 25 TSS/hour x 0.6814 h = 17.0
    assert abs(resolved["tss"] - 17.0) < 0.05
