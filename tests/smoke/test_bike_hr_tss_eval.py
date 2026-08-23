from __future__ import annotations

import pytest

from services.bike_hr_tss_candidates import avg_hr_tss, hrss_tss, power_tss_target, zones_tss
from services.bike_hr_tss_eval import (
    build_episode_candidate_rows,
    evaluate_reorder,
    group_dependent_bike_pairs,
)


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
    assert verdict["checks"][0]["passed"] is True  # n независимых эпизодов
    assert verdict["n_pairs"] == 20
    assert verdict["n_episodes"] == 20


def test_reorder_gate_fails_with_insufficient_pairs():
    verdict = evaluate_reorder(_series(10))
    assert verdict["passed"] is False
    reasons = [check["id"] for check in verdict["checks"] if not check["passed"]]
    assert "n_episodes" in reasons


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


def test_contiguous_activity_parts_form_one_evaluation_episode():
    main = _pair(
        activity_id="main",
        date="2026-08-22",
        started_at_utc="2026-08-22T08:15:18Z",
        duration_minutes=106.79,
    )
    ride_home = _pair(
        activity_id="ride-home",
        date="2026-08-22",
        started_at_utc="2026-08-22T10:02:57Z",
        duration_minutes=14.08,
    )

    episodes = group_dependent_bike_pairs([ride_home, main])

    assert len(episodes) == 1
    assert [row["activity_id"] for row in episodes[0]] == ["main", "ride-home"]
    candidate_rows = build_episode_candidate_rows([ride_home, main])
    assert candidate_rows[0]["target"] == pytest.approx(100.0, abs=0.4)
    assert candidate_rows[0]["avg_hr"] == pytest.approx(100.0, abs=0.4)
    assert candidate_rows[0]["zones"] == pytest.approx(45.5, abs=0.1)


def test_same_day_without_time_evidence_does_not_merge_activities():
    first = _pair(activity_id="first", date="2026-08-22")
    second = _pair(activity_id="second", date="2026-08-22")

    episodes = group_dependent_bike_pairs([first, second])

    assert len(episodes) == 2


def test_same_day_activities_beyond_contiguity_window_stay_independent():
    first = _pair(
        activity_id="first",
        date="2026-08-22",
        started_at_utc="2026-08-22T08:00:00Z",
        duration_minutes=60.0,
    )
    second = _pair(
        activity_id="second",
        date="2026-08-22",
        started_at_utc="2026-08-22T09:31:00Z",
        duration_minutes=60.0,
    )

    episodes = group_dependent_bike_pairs([first, second])

    assert len(episodes) == 2


def test_contiguous_activity_parts_across_midnight_form_one_episode():
    before_midnight = _pair(
        activity_id="before-midnight",
        date="2026-08-22",
        started_at_utc="2026-08-22T20:59:00Z",
        duration_minutes=2.0,
    )
    after_midnight = _pair(
        activity_id="after-midnight",
        date="2026-08-23",
        started_at_utc="2026-08-22T21:01:30Z",
        duration_minutes=5.0,
    )

    episodes = group_dependent_bike_pairs([after_midnight, before_midnight])

    assert len(episodes) == 1
    assert [row["activity_id"] for row in episodes[0]] == [
        "before-midnight",
        "after-midnight",
    ]


def test_reorder_gate_counts_and_splits_independent_episodes():
    pairs = _series(19)
    pairs.extend(
        [
            _pair(
                activity_id="main",
                date="2026-08-22",
                started_at_utc="2026-08-22T08:15:18Z",
                duration_minutes=106.79,
            ),
            _pair(
                activity_id="ride-home",
                date="2026-08-22",
                started_at_utc="2026-08-22T10:02:57Z",
                duration_minutes=14.08,
            ),
        ]
    )

    verdict = evaluate_reorder(pairs)

    assert verdict["n_pairs"] == 21
    assert verdict["n_episodes"] == 20
    assert verdict["holdout_n"] == 6
    assert verdict["holdout_activity_n"] == 7
    assert verdict["passed"] is True
