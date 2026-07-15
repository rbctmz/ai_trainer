from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from models.training_planner import apply_race_event_overlays


pytestmark = pytest.mark.smoke


def _constant_plan(
    start: date,
    days: int,
    *,
    tss: float = 40.0,
    phases: tuple[str, ...] = ("Taper", "Race Week"),
):
    daily = [
        (
            datetime.combine(start + timedelta(days=offset), datetime.min.time()),
            tss,
            {"run": 0.0, "bike": tss, "swim": 0.0},
        )
        for offset in range(days)
    ]
    roles = ["easy", "quality", "easy", "quality", "easy", "long", "recovery"]
    summaries = []
    for week_index in range((days + 6) // 7):
        day_count = min(7, days - week_index * 7)
        summaries.append(
            {
                "week_start": start + timedelta(days=week_index * 7),
                "phase": phases[min(week_index, len(phases) - 1)],
                "weekly_tss": int(tss * day_count),
                "bike": tss * day_count,
                "run": 0.0,
                "swim": 0.0,
                "day_roles": list(roles),
                "day_focuses": ["Исходный фокус"] * 7,
            }
        )
    return daily, summaries


def _rows_by_date(daily, summaries):
    rows = {}
    for index, (dt, total, parts) in enumerate(daily):
        week = summaries[index // 7]
        day = index % 7
        rows[dt.date().isoformat()] = {
            "total": total,
            "parts": parts,
            "phase": week["phase"],
            "role": week["day_roles"][day],
            "focus": week["day_focuses"][day],
            "sport": max(parts, key=parts.get) if total > 0 else "off",
        }
    return rows


def test_b_microcycle_replaces_long_day_before_with_run_activation() -> None:
    start = date(2026, 7, 20)
    daily, summaries = _constant_plan(start, 14, phases=("Peak", "Peak"))

    adjusted, after_summaries, metadata = apply_race_event_overlays(
        daily,
        summaries,
        [{"date": "2026-07-26", "priority": "B", "label": "Minsk", "confirmed": True}],
        goal_type="Триатлон",
    )
    rows = _rows_by_date(adjusted, after_summaries)

    assert metadata["rule_version"] == "race-microcycle-v2"
    assert rows["2026-07-25"]["role"] == "activation"
    assert rows["2026-07-25"]["sport"] == "run"
    assert rows["2026-07-25"]["total"] == 10.0
    assert rows["2026-07-24"]["role"] == "off"
    assert rows["2026-07-24"]["total"] == 0.0
    assert not {"long", "quality"}.intersection(
        rows[day]["role"] for day in ("2026-07-22", "2026-07-23", "2026-07-24", "2026-07-25")
    )


def test_a_triathlon_microcycle_is_deterministic_multisport_and_never_increases_load() -> None:
    start = date(2026, 9, 21)
    daily, summaries = _constant_plan(start, 14)
    before_weekly = [row["weekly_tss"] for row in summaries]

    adjusted, after_summaries, metadata = apply_race_event_overlays(
        daily,
        summaries,
        [{"date": "2026-10-04", "priority": "A", "label": "Sirius", "confirmed": True}],
        goal_type="Триатлон",
    )
    rows = _rows_by_date(adjusted, after_summaries)

    expected = {
        "2026-09-27": ("recovery", "swim"),
        "2026-09-28": ("easy", "bike"),
        "2026-09-29": ("easy", "run"),
        "2026-09-30": ("recovery", "swim"),
        "2026-10-01": ("activation", "bike"),
        "2026-10-02": ("off", "off"),
        "2026-10-03": ("activation", "run"),
        "2026-10-04": ("race", "off"),
    }
    assert {day: (rows[day]["role"], rows[day]["sport"]) for day in expected} == expected
    assert rows["2026-10-04"]["total"] == 0.0
    assert all(after[1] <= before[1] for before, after in zip(daily, adjusted))
    assert all(
        int(after["weekly_tss"]) <= int(before)
        for before, after in zip(before_weekly, after_summaries)
    )
    assert {change["after"]["sport"] for change in metadata["microcycle_changes"]} >= {
        "bike",
        "run",
        "swim",
        "off",
    }
    assert all(change["after"]["tss"] <= change["before"]["tss"] for change in metadata["microcycle_changes"])


def test_c_microcycle_keeps_day_before_role_and_sport_train_through() -> None:
    start = date(2026, 8, 3)
    daily, summaries = _constant_plan(start, 7, phases=("Build",))
    before = _rows_by_date(daily, summaries)

    adjusted, after_summaries, metadata = apply_race_event_overlays(
        daily,
        summaries,
        [{"date": "2026-08-06", "priority": "C", "label": "Club", "confirmed": True}],
        goal_type="Триатлон",
    )
    after = _rows_by_date(adjusted, after_summaries)

    assert after["2026-08-05"]["role"] == before["2026-08-05"]["role"]
    assert after["2026-08-05"]["sport"] == before["2026-08-05"]["sport"]
    assert after["2026-08-05"]["total"] == 28.0
    assert after_summaries[0]["phase"] == "Build"
    assert metadata["overlays"][0]["priority"] == "C"


def test_single_sport_goal_keeps_original_pre_race_roles_and_focuses() -> None:
    start = date(2026, 7, 20)
    daily, summaries = _constant_plan(start, 7, phases=("Peak",))
    running_daily = [
        (dt, total, {"run": total, "bike": 0.0, "swim": 0.0})
        for dt, total, _parts in daily
    ]
    before = _rows_by_date(running_daily, summaries)

    adjusted, after_summaries, _metadata = apply_race_event_overlays(
        running_daily,
        summaries,
        [{"date": "2026-07-26", "priority": "B", "label": "10K", "confirmed": True}],
        goal_type="Бег",
    )
    after = _rows_by_date(adjusted, after_summaries)

    for day in ("2026-07-22", "2026-07-23", "2026-07-24", "2026-07-25"):
        assert after[day]["role"] == before[day]["role"]
        assert after[day]["sport"] == "run"
        assert after[day]["focus"] == "Исходный фокус"
        assert after[day]["total"] <= before[day]["total"]


def test_overlapping_event_windows_are_order_independent_and_safety_first() -> None:
    start = date(2026, 9, 28)
    daily, summaries = _constant_plan(start, 7, phases=("Race Week",))
    events = [
        {"date": "2026-10-02", "priority": "B", "label": "Tune-up", "confirmed": True},
        {"date": "2026-10-04", "priority": "A", "label": "Sirius", "confirmed": True},
    ]

    first = apply_race_event_overlays(daily, summaries, events, goal_type="Триатлон")
    second = apply_race_event_overlays(daily, summaries, list(reversed(events)), goal_type="Триатлон")

    assert first == second
    rows = _rows_by_date(first[0], first[1])
    assert rows["2026-10-02"]["role"] == "race"
    assert rows["2026-10-03"]["role"] == "off"
    assert rows["2026-10-04"]["role"] == "race"
    assert {"2026-10-02", "2026-10-03", "2026-10-04"} <= set(first[2]["protected_dates"])


def test_deep_fatigue_removes_a_and_b_activation_without_restoring_hard_work() -> None:
    start = date(2026, 9, 21)
    daily, summaries = _constant_plan(start, 14)

    adjusted, after_summaries, _metadata = apply_race_event_overlays(
        daily,
        summaries,
        [{"date": "2026-10-04", "priority": "A", "label": "Sirius", "confirmed": True}],
        goal_type="Триатлон",
        load_state="deep_fatigue",
        as_of=date(2026, 9, 28),
    )
    rows = _rows_by_date(adjusted, after_summaries)

    for day in ("2026-10-01", "2026-10-03"):
        assert rows[day]["role"] == "off"
        assert rows[day]["total"] == 0.0
    assert not {"quality", "long", "activation"}.intersection(
        rows[day]["role"] for day in rows if "2026-09-27" <= day <= "2026-10-03"
    )


def test_deep_fatigue_does_not_remove_activation_outside_readiness_horizon() -> None:
    start = date(2026, 9, 21)
    daily, summaries = _constant_plan(start, 14)

    adjusted, after_summaries, _metadata = apply_race_event_overlays(
        daily,
        summaries,
        [{"date": "2026-10-04", "priority": "A", "label": "Sirius", "confirmed": True}],
        goal_type="Триатлон",
        load_state="deep_fatigue",
        as_of=date(2026, 7, 14),
    )
    rows = _rows_by_date(adjusted, after_summaries)

    assert rows["2026-10-01"]["role"] == "activation"
    assert rows["2026-10-03"]["role"] == "activation"
