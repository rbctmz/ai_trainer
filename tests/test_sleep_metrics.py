"""Test suite for sleep regularity helper utilities."""
from __future__ import annotations

import pandas as pd
import pytest

from utils.sleep_metrics import compute_sleep_regularity


pytestmark = pytest.mark.smoke


def test_sleep_regularity_basic_case():
    df = pd.DataFrame(
        {
            "date": pd.to_datetime(["2025-10-01", "2025-10-02", "2025-10-03"]),
            "bedtime": ["23:30", "23:45", "00:15"],
            "wakeup_time": ["07:00", "07:05", "07:10"],
        }
    )

    metrics = compute_sleep_regularity(df)

    assert metrics["count"] == 3
    bedtime = metrics["bedtime"]
    wake = metrics["wakeup"]
    weekday_profile = metrics["weekday_profile"]

    assert bedtime["status"] == "warning"
    assert wake["status"] == "success"
    assert bedtime["mean_text"] == "23:50"
    assert wake["mean_text"] == "07:05"
    assert not weekday_profile.empty
    assert set(weekday_profile["weekday_label"]) == {"Ср", "Чт", "Пт"}
    assert {"bedtime_hours", "wakeup_hours", "sleep_duration_hours"}.issubset(weekday_profile.columns)


def test_sleep_regularity_not_enough_records():
    df = pd.DataFrame(
        {
            "date": pd.to_datetime(["2025-10-01", "2025-10-02"]),
            "bedtime": ["23:30", "23:45"],
            "wakeup_time": ["07:00", "07:05"],
        }
    )

    metrics = compute_sleep_regularity(df)
    assert metrics["count"] == 2
    assert metrics["bedtime"] is None or metrics["bedtime"]["status"] == "secondary"
    assert metrics["wakeup"] is None or metrics["wakeup"]["status"] == "secondary"
    assert metrics["weekday_profile"].empty or metrics["weekday_profile"]["count"].sum() == 2
