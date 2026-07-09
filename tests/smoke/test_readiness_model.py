"""Smoke: единый сигнал готовности models/readiness.py (issue #139, ExecPlan docs/readiness_today_execplan.md)."""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import pytest

from models.readiness import (
    BASELINE_WINDOW_DAYS,
    LOAD_METRICS_WINDOW_DAYS,
    compute_readiness_today,
)


pytestmark = pytest.mark.smoke

TODAY = date(2026, 7, 9)


def _daily_frame(column: str, values: dict[int, float]) -> pd.DataFrame:
    """Frame with `date` and one value column; keys are day offsets back from TODAY (0 = today)."""
    rows = [
        {"date": pd.Timestamp(TODAY - timedelta(days=offset)), column: value}
        for offset, value in sorted(values.items())
    ]
    return pd.DataFrame(rows)


def _history(column: str, value: float, days: int = 28, start_offset: int = 1) -> dict[int, float]:
    return {offset: value for offset in range(start_offset, start_offset + days)}


def _full_inputs(
    *,
    rmssd_today: float = 37.0,
    rmssd_base: float = 37.0,
    rhr_today: float = 55.0,
    rhr_base: float = 55.0,
    sleep_score: float = 80.0,
    garmin_readiness: float = 80.0,
) -> dict:
    hrv = _daily_frame("rmssd", {0: rmssd_today, **_history("rmssd", rmssd_base)})
    health = _daily_frame("resting_hr", {0: rhr_today, **_history("resting_hr", rhr_base)})
    sleep = _daily_frame("sleep_score", {0: sleep_score})
    training = _daily_frame("training_readiness", {0: garmin_readiness})
    activities = pd.DataFrame(
        [
            {"date": pd.Timestamp(TODAY - timedelta(days=offset)), "tss": 40.0}
            for offset in range(1, 60)
        ]
    )
    return {
        "sleep_df": sleep,
        "hrv_df": hrv,
        "health_df": health,
        "training_df": training,
        "activities_df": activities,
    }


def test_all_good_inputs_give_ready_score_with_full_confidence():
    result = compute_readiness_today(**_full_inputs(), today=TODAY)

    assert result["status"] in {"ready", "strong"}
    assert result["score"] is not None and result["score"] >= 60
    assert result["confidence"] == 1.0
    assert {f["key"] for f in result["factors"]} == {
        "hrv",
        "resting_hr",
        "sleep",
        "training_readiness",
        "tsb",
    }
    assert result["as_of_date"] == TODAY.isoformat()
    assert result["tsb"]["window_days"] == LOAD_METRICS_WINDOW_DAYS


def test_green_garmin_does_not_mask_elevated_rhr_and_suppressed_hrv():
    """Ключевой инвариант issue #139: зелёный Garmin не маскирует недовосстановление."""
    good = compute_readiness_today(**_full_inputs(), today=TODAY)
    strained = compute_readiness_today(
        **_full_inputs(rhr_today=60.0, rmssd_today=31.0),  # RHR +5, HRV ≈ −16%
        today=TODAY,
    )

    assert strained["score"] < good["score"]
    driver_keys = [d["key"] for d in strained["drivers"]]
    assert "resting_hr" in driver_keys
    assert "hrv" in driver_keys
    rhr_driver = next(d for d in strained["drivers"] if d["key"] == "resting_hr")
    assert "55" in rhr_driver["evidence"] and "60" in rhr_driver["evidence"]


def test_baseline_excludes_today():
    """Сегодняшний выброс не должен растить базлайн, с которым сам же сравнивается (#126/#128)."""
    result = compute_readiness_today(
        **_full_inputs(rhr_today=70.0, rhr_base=55.0),
        today=TODAY,
    )

    rhr = next(f for f in result["factors"] if f["key"] == "resting_hr")
    assert rhr["baseline"] == pytest.approx(55.0, abs=0.1)
    assert rhr["deviation"] == pytest.approx(15.0, abs=0.1)
    assert rhr["score"] <= 20


def test_empty_inputs_give_unknown():
    result = compute_readiness_today(None, None, None, None, None, today=TODAY)

    assert result["score"] is None
    assert result["status"] == "unknown"
    assert result["factors"] == []
    assert result["drivers"] == []
    assert result["confidence"] == 0.0


def test_heavy_recent_load_pushes_tsb_factor_down():
    inputs = _full_inputs()
    inputs["activities_df"] = pd.DataFrame(
        [
            {"date": pd.Timestamp(TODAY - timedelta(days=offset)), "tss": 150.0}
            for offset in range(1, 8)
        ]
    )
    result = compute_readiness_today(**inputs, today=TODAY)

    tsb = next(f for f in result["factors"] if f["key"] == "tsb")
    assert tsb["raw_value"] < -10
    assert tsb["score"] <= 55
    assert "TSB" in tsb["evidence"]


def test_missing_garmin_readiness_renormalizes_weights():
    inputs = _full_inputs()
    inputs["training_df"] = None
    result = compute_readiness_today(**inputs, today=TODAY)

    keys = {f["key"] for f in result["factors"]}
    assert "training_readiness" not in keys
    assert result["confidence"] == pytest.approx(0.8)
    assert result["score"] is not None
    assert "training_readiness" in result["missing_inputs"]
    # веса присутствующих факторов в сумме дают 1 после перенормировки
    assert sum(f["weight"] for f in result["factors"]) == pytest.approx(1.0, abs=0.005)


def test_hrv_without_baseline_uses_absolute_bands():
    inputs = _full_inputs()
    inputs["hrv_df"] = _daily_frame("rmssd", {0: 52.0})  # только сегодня, истории нет
    result = compute_readiness_today(**inputs, today=TODAY)

    hrv = next(f for f in result["factors"] if f["key"] == "hrv")
    assert hrv["baseline"] is None
    assert hrv["score"] == 75


def test_stale_input_is_marked_but_used():
    inputs = _full_inputs()
    # HRV только за вчера — используется, но помечен как отставший
    inputs["hrv_df"] = _daily_frame("rmssd", {1: 37.0, **_history("rmssd", 37.0, start_offset=2)})
    result = compute_readiness_today(**inputs, today=TODAY)

    hrv = next(f for f in result["factors"] if f["key"] == "hrv")
    assert hrv["stale_input"] is True
    assert hrv["score"] is not None


def test_baseline_window_is_28_days():
    assert BASELINE_WINDOW_DAYS == 28
