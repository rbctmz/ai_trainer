"""Smoke: локальная power curve (mean-max) для гибридного фолбэка (#382).

ExecPlan: docs/best_efforts_execplan.md (Milestone 4, отложенная интеграция).
``MetricsCalculator.mean_max_power`` — утилитный метод локального расчёта
пиковой средней мощности из стрима watts. В клине #382 НЕ подключён к карточке
(нет источника стримов без персистенции — см. Decision Log); пригодится в #383 и
как фундамент, если стримы будут персиститься.
"""
from __future__ import annotations

import pytest

from utils.metrics import MetricsCalculator


pytestmark = pytest.mark.smoke


def test_mean_max_power_finds_peak_per_duration():
    # 10 seconds: [100]*3 then [200]*4 then [100]*3. Best 1s=200, best 4s=175
    # (avg of the 200-block), best 10s=140 (whole series avg).
    power = [100, 100, 100, 200, 200, 200, 200, 100, 100, 100]
    result = MetricsCalculator.mean_max_power(power, durations_secs=(1, 4, 10))

    assert result[1] == 200
    assert result[4] == 200  # window of 4 over the all-200 block
    assert result[10] == 140


def test_mean_max_power_none_when_shorter_than_duration():
    # 3-point stream: 5s/60s windows cannot be formed.
    result = MetricsCalculator.mean_max_power([100, 200, 150], durations_secs=(5, 60))

    assert result[5] is None
    assert result[60] is None
    assert MetricsCalculator.mean_max_power([100, 200, 150], durations_secs=(3,))[3] == 150


def test_mean_max_power_handles_none_input():
    result = MetricsCalculator.mean_max_power(None, durations_secs=(5, 60))

    assert result == {5: None, 60: None}


def test_mean_max_power_drops_nan_values():
    power = [100, None, 200, 200, 200]  # NaN dropped -> [100,200,200,200]
    result = MetricsCalculator.mean_max_power(power, durations_secs=(3,))

    # Best 3s window among [100,200,200]=166 or [200,200,200]=200.
    assert result[3] == 200


def test_mean_max_power_default_durations():
    # Default durations are the headline set used by the card.
    result = MetricsCalculator.mean_max_power([100] * 3500)

    assert set(result.keys()) == {5, 60, 300, 1200, 3600}
    # 3500 points covers 5/60/300/1200 but not 3600.
    assert result[5] == 100
    assert result[60] == 100
    assert result[1200] == 100
    assert result[3600] is None
