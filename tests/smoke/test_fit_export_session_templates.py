from __future__ import annotations

import pytest

from models.fit_export import build_steps_for_sport


pytestmark = pytest.mark.smoke


def test_build_steps_for_sport_quality_session_uses_interval_structure():
    steps = build_steps_for_sport(80.0, "run", session_role="quality", phase="Build")

    assert [step["name"] for step in steps] == ["Warmup", "Main Intervals", "Reset", "Cooldown"]
    assert steps[1]["target"] == "hr_zone_4"
    assert round(sum(float(step["tss"]) for step in steps), 1) == 80.0


def test_build_steps_for_sport_recovery_bike_stays_easy():
    steps = build_steps_for_sport(45.0, "bike", session_role="recovery")

    assert steps[1]["name"] == "Recovery Endurance"
    assert steps[0]["target"] == "power_zone_1_2"
    assert steps[1]["target"] == "power_zone_1_2"
    assert steps[-1]["target"] == "power_zone_1"
