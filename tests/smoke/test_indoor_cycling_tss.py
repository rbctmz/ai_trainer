"""BDD gates for #360: indoor_cycling must normalize to bike for the TSS cascade.

`indoor_cycling` was missing from `SPORT_KEY_ALIASES`, so power/HR data was
ignored and the workout fell to `heuristic_duration_other` (underestimated TSS).
After the fix the sport maps to `bike` and `ActivityProcessor.resolve_tss` runs
the full bike cascade: power → HR zones → HR → heuristic_duration_bike only as
the last fallback.
"""
from __future__ import annotations

import pytest

from data.data_processor import ActivityProcessor
from utils.product_semantics import normalize_sport_key


pytestmark = pytest.mark.smoke


def _bike_like_row(**overrides):
    row = {
        "sport": "indoor_cycling",
        "duration_minutes": 45.09,
        "avg_power": 112.0,
        "normalized_power": 121.0,
        "avg_hr": 132.0,
    }
    row.update(overrides)
    return row


def test_indoor_cycling_normalizes_to_bike():
    assert normalize_sport_key("indoor_cycling") == "bike"


def test_indoor_cycling_with_power_uses_coggan_power_tss():
    resolved = ActivityProcessor.resolve_tss(
        _bike_like_row(),
        ftp=172.0,
        lthr=163.0,
    )

    assert resolved["tss_method"] == "power_tss_bike"
    assert resolved["tss_ftp_used"] == 172.0
    # IF = 121/172 ≈ 0.7035; TSS = 0.7515 h × IF² × 100 ≈ 37.2
    assert abs(resolved["tss"] - 37.2) < 0.05


def test_indoor_cycling_without_power_uses_hr_cascade():
    resolved = ActivityProcessor.resolve_tss(
        _bike_like_row(avg_power=None, normalized_power=None),
        ftp=172.0,
        lthr=163.0,
    )

    assert resolved["tss_method"] in {"hr_zone_tss_bike", "hr_tss_bike"}
    assert resolved["tss"] > 0


def test_indoor_cycling_without_any_signals_falls_back_to_bike_heuristic():
    resolved = ActivityProcessor.resolve_tss(
        _bike_like_row(avg_power=None, normalized_power=None, avg_hr=None),
        ftp=172.0,
        lthr=163.0,
    )

    assert resolved["tss_method"] == "heuristic_duration_bike"
