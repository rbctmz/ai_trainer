from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from models.training_planner import (
    apply_race_event_overlays,
    compute_event_aware_phase_schedule,
    current_periodization_phase,
)


pytestmark = pytest.mark.smoke


def _constant_plan(start: date, days: int, tss: float = 40.0):
    daily = []
    for offset in range(days):
        dt = datetime.combine(start + timedelta(days=offset), datetime.min.time())
        daily.append((dt, tss, {"run": 0.0, "bike": tss, "swim": 0.0}))
    summaries = []
    for week in range((days + 6) // 7):
        summaries.append(
            {
                "week_start": start + timedelta(days=week * 7),
                "phase": "Build",
                "weekly_tss": int(tss * min(7, days - week * 7)),
                "bike": tss * min(7, days - week * 7),
                "run": 0.0,
                "swim": 0.0,
                "day_roles": ["easy", "quality", "easy", "quality", "easy", "long", "recovery"],
                "day_focuses": ["Легко"] * 7,
            }
        )
    return daily, summaries


@pytest.mark.parametrize(
    ("weeks", "expected"),
    [
        (1, ["Race Week"]),
        (2, ["Taper", "Race Week"]),
        (3, ["Base", "Taper", "Race Week"]),
    ],
)
def test_short_a_horizon_never_truncates_taper_or_race_week(weeks, expected) -> None:
    phases = compute_event_aware_phase_schedule(
        weeks,
        planning_mode="event_goal",
        intent="develop",
    )
    assert phases == expected


def test_training_goal_has_no_race_phases_and_is_extendable() -> None:
    maintain = compute_event_aware_phase_schedule(
        8, planning_mode="training_goal", intent="maintain"
    )
    develop = compute_event_aware_phase_schedule(
        8, planning_mode="training_goal", intent="develop"
    )

    assert maintain == ["Maintenance", "Maintenance", "Maintenance", "Recovery"] * 2
    assert develop == ["Base", "Base", "Build", "Recovery"] * 2
    assert not {"Taper", "Race Week"}.intersection(maintain + develop)


def test_manual_phases_are_not_replaced() -> None:
    phases = compute_event_aware_phase_schedule(
        3,
        planning_mode="manual",
        intent="develop",
        manual_phases=["Base", "Recovery", "Build"],
    )
    assert phases == ["Base", "Recovery", "Build"]


def test_current_phase_reads_persisted_rolling_plan_without_race_date() -> None:
    monday = date.today() - timedelta(days=date.today().weekday())
    current = current_periodization_phase(
        {
            "planning_mode": "training_goal",
            "start_week": monday,
            "phases": ["Maintenance", "Maintenance", "Maintenance", "Recovery"],
            "event_date": "",
        }
    )

    assert current == {"phase": "Maintenance", "days_to_race": None, "total_weeks": 4}


def test_b_overlay_caps_load_protects_race_and_resumes() -> None:
    start = date(2026, 7, 20)
    daily, weekly = _constant_plan(start, 14)
    adjusted, summaries, metadata = apply_race_event_overlays(
        daily,
        weekly,
        [{"date": "2026-07-26", "priority": "B", "label": "Minsk", "confirmed": True}],
    )
    by_date = {row[0].date().isoformat(): row for row in adjusted}

    assert by_date["2026-07-22"][1] == 30.0  # D-4, 75% cap
    assert by_date["2026-07-25"][1] == 10.0  # D-1, 25% cap
    assert by_date["2026-07-26"][1] == 0.0
    assert by_date["2026-07-27"][1] == 0.0
    assert by_date["2026-07-28"][1] == 0.0
    assert by_date["2026-07-29"][1] == 40.0
    assert metadata["rule_version"] == "race-microcycle-v2"
    assert set(metadata["protected_dates"]) >= {"2026-07-26", "2026-07-27", "2026-07-28"}
    assert summaries[0]["weekly_tss"] < 280


def test_c_event_trains_through_without_week_phase_reset() -> None:
    start = date(2026, 8, 3)
    daily, weekly = _constant_plan(start, 7)
    adjusted, summaries, metadata = apply_race_event_overlays(
        daily,
        weekly,
        [{"date": "2026-08-06", "priority": "C", "label": "Club race", "confirmed": True}],
    )
    by_date = {row[0].date().isoformat(): row for row in adjusted}

    assert summaries[0]["phase"] == "Build"
    assert by_date["2026-08-05"][1] == 28.0
    assert by_date["2026-08-06"][1] == 0.0
    assert by_date["2026-08-07"][1] == 20.0
    assert metadata["overlays"][0]["priority"] == "C"
