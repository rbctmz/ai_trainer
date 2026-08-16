from __future__ import annotations

import pytest

from services.bike_hr_tss_candidates import avg_hr_tss, hrss_tss, power_tss_target, zones_tss
from services.bike_hr_tss_eval import evaluate_reorder


pytestmark = pytest.mark.smoke


def _pair(**overrides) -> dict:
    """Пара с контролируемыми исходами: target ≈ 50, avgHR-TSS ≈ 50,
    зоны занижают (≈ 22.75)."""
    base = {
        "activity_id": "pair-0",
        "date": "2026-07-01",
        "sport": "cycling",
        "moving_minutes": 60.0,
        "avg_hr": 115.3,  # (115.3/163)^2 * 100 ≈ 50
        "normalized_power": 112.4,  # (112.4/159)^2 * 100 ≈ 50
        "avg_power": 112.4,
        "hr_zone_minutes_z1": 5.0,
        "hr_zone_minutes_z2": 25.0,
        "hr_zone_minutes_z3": 20.0,
        "hr_zone_minutes_z4": 0.0,
        "hr_zone_minutes_z5": 0.0,
        "ftp_on_date": 159.0,
        "ftp_verified": 1,
        "rhr": 50.0,
        "lthr": 163.0,
        "zone_coverage_pct": 100.0,
    }
    base.update(overrides)
    return base


def _series(count: int, **overrides) -> list[dict]:
    return [
        _pair(activity_id=f"pair-{index}", date=f"2026-07-{index + 1:02d}", **overrides)
        for index in range(count)
    ]


def test_candidate_formulas_on_known_pair():
    pair = _pair()
    assert power_tss_target(pair) == pytest.approx(50.0, abs=0.2)
    assert avg_hr_tss(pair) == pytest.approx(50.0, abs=0.2)
    assert zones_tss(pair) == pytest.approx(22.75, abs=0.05)
    # IF = (115.3 - 50) / (163 - 50) ≈ 0.5779 → hrss ≈ 33.4
    assert hrss_tss(pair) == pytest.approx(33.4, abs=0.5)
    assert zones_tss(_pair(hr_zone_minutes_z1=None)) is None
    assert hrss_tss(_pair(rhr=None)) is None


def test_reorder_gate_passes_when_avg_hr_clearly_better():
    verdict = evaluate_reorder(_series(20))
    assert verdict["passed"] is True
    assert verdict["checks"][0]["passed"] is True  # n пар
    assert verdict["n_pairs"] == 20


def test_reorder_gate_fails_with_insufficient_pairs():
    verdict = evaluate_reorder(_series(10))
    assert verdict["passed"] is False
    reasons = [check["id"] for check in verdict["checks"] if not check["passed"]]
    assert "n_pairs" in reasons


def test_reorder_gate_fails_when_zones_win():
    # Зоны точны (38.46 × 1.3 = 50), avgHR завышает вдвое (avg_hr = 163 → TSS 100).
    pairs = _series(
        20,
        hr_zone_minutes_z1=0.0,
        hr_zone_minutes_z2=0.0,
        hr_zone_minutes_z3=0.0,
        hr_zone_minutes_z4=0.0,
        hr_zone_minutes_z5=38.4615,
        avg_hr=163.0,
    )
    verdict = evaluate_reorder(pairs)
    assert verdict["passed"] is False
    reasons = [check["id"] for check in verdict["checks"] if not check["passed"]]
    assert "full_mae" in reasons and "full_bias" in reasons


def test_reorder_gate_fails_when_avg_hr_biased_positive():
    # avgHR лучше зон по MAE (8 vs 27), но смещён на +8 TSS (> порога 5).
    pairs = _series(20, avg_hr=124.2)  # (124.2/163)^2 * 100 ≈ 58
    verdict = evaluate_reorder(pairs)
    assert verdict["passed"] is False
    reasons = [check["id"] for check in verdict["checks"] if not check["passed"]]
    assert "full_bias" in reasons
    assert "full_mae" not in reasons  # MAE avg (≈8) < MAE зон (≈27) — этот чек проходит
