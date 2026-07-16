"""M3b slot-scheduler contract (Issue #205).

The scheduler places each week's sport budget into a bounded number of daily
slots BEFORE materialization: weekly sport budget → roles/slots →
allocated_parts → sessions[] → weekly_summary. These tests pre-register the
quantitative contract confirmed by the athlete for a normal 10-hour week and
are committed RED before the implementation exists.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from data.database import Database


pytestmark = pytest.mark.smoke

# A normal 10h/week triathlon budget (~385 TSS): bike-dominant, all three sports.
_TEN_HOUR_BUDGET = {"bike": 170.0, "run": 140.0, "swim": 75.0}


def _schedule(**overrides):
    from models.session_scheduler import schedule_week_slots

    kwargs = dict(
        week_budget=dict(_TEN_HOUR_BUDGET),
        phase="Build",
        goal_type="Триатлон",
        load_state="balanced",
        available_day_indices=list(range(7)),
    )
    kwargs.update(overrides)
    return schedule_week_slots(**kwargs)


def _occasions(result):
    """Per-day occasion lists; a brick is ONE occasion carrying two sports."""
    return result["occasions"]


def _day_session_counts(result):
    return [len(day) for day in _occasions(result)]


def _sport_week_totals(result):
    totals = {"bike": 0.0, "run": 0.0, "swim": 0.0}
    for day in _occasions(result):
        for occasion in day:
            for sport, tss in occasion["parts"].items():
                totals[sport] = round(totals[sport] + float(tss), 1)
    return totals


def test_scheduler_is_deterministic():
    first = _schedule()
    second = _schedule()
    assert first == second


def test_normal_ten_hour_week_meets_quantitative_contract():
    result = _schedule()
    counts = _day_session_counts(result)
    occasions_total = sum(counts)

    # 7-10 training occasions; ≤2 per day; no 3-session day; ≥1 full rest day
    assert 7 <= occasions_total <= 10, counts
    assert max(counts) <= 2, counts
    assert counts.count(0) >= 1, counts
    # ≤2 two-a-day days per week
    assert sum(1 for c in counts if c == 2) <= 2, counts

    # 2-4 sessions of each discipline (a brick leg counts for its discipline)
    leaves = {"bike": 0, "run": 0, "swim": 0}
    hard_by_day = []
    for day in _occasions(result):
        hard = 0
        for occasion in day:
            if occasion["role"] in {"quality", "long"}:
                hard += 1
            for sport, tss in occasion["parts"].items():
                if float(tss) > 0:
                    leaves[sport] += 1
            # bike+run inside one occasion only as an explicit brick
            active = [s for s, t in occasion["parts"].items() if float(t) > 0]
            if "bike" in active and "run" in active:
                assert occasion["is_brick"], occasion
        hard_by_day.append(hard)
    for sport, count in leaves.items():
        assert 2 <= count <= 4, (sport, leaves)
    # at most one hard session per day
    assert max(hard_by_day) <= 1, hard_by_day

    # two-a-day pairs prefer swim + bike/run: no non-brick day pairs bike+run
    for day in _occasions(result):
        if len(day) == 2:
            sports = {s for occ in day for s, t in occ["parts"].items() if float(t) > 0}
            assert "swim" in sports, day

    # budget conserved exactly per discipline
    assert _sport_week_totals(result) == pytest.approx(_TEN_HOUR_BUDGET, abs=0.11)
    assert result["status"] == "scheduled"


def test_restricted_available_days_are_respected():
    result = _schedule(available_day_indices=[1, 3, 5])
    counts = _day_session_counts(result)
    for idx, count in enumerate(counts):
        if idx not in {1, 3, 5}:
            assert count == 0, counts
    assert max(counts) <= 2
    assert _sport_week_totals(result) == pytest.approx(_TEN_HOUR_BUDGET, abs=0.11)


def test_pinned_protected_days_receive_nothing():
    result = _schedule(pinned_off_days=[5, 6])
    counts = _day_session_counts(result)
    assert counts[5] == 0 and counts[6] == 0
    assert _sport_week_totals(result) == pytest.approx(_TEN_HOUR_BUDGET, abs=0.11)


def test_infeasible_budget_fails_closed_not_silently_inflated():
    result = _schedule(
        week_budget={"bike": 400.0, "run": 300.0, "swim": 200.0},
        available_day_indices=[2, 4],
    )
    # two days × ≤2 occasions cannot honestly hold a 900-TSS triathlon week:
    # the scheduler must say so explicitly, never smear or invent slots.
    assert result["status"] in {"reduced", "infeasible"}
    assert result["notes"], result
    counts = _day_session_counts(result)
    assert max(counts) <= 2
    for idx, count in enumerate(counts):
        if idx not in {2, 4}:
            assert count == 0


def test_small_tss_change_does_not_churn_the_calendar():
    base = _schedule()
    bumped = _schedule(
        week_budget={"bike": 175.0, "run": 140.0, "swim": 75.0}
    )

    def structure(result):
        return [
            [
                (occasion["role"], tuple(sorted(s for s, t in occasion["parts"].items() if float(t) > 0)), occasion["is_brick"])
                for occasion in day
            ]
            for day in _occasions(result)
        ]

    # +5 TSS on the bike must not move days, sports, roles, or brick placement
    assert structure(base) == structure(bumped)


def test_reference_plan_histogram_replaces_three_session_days(tmp_path):
    """Integration: the full 10h B+A reference plan obeys the weekly contract."""
    from api import planning_service as ps

    db = Database(str(tmp_path / "scheduler-reference.db"))
    today = datetime.now().date()
    b_date = today + timedelta(days=13)
    a_date = today + timedelta(weeks=12)
    ps.build_plan(
        db,
        goal_type="triathlon",
        distance="olympic",
        event_date=None,
        events=[
            {"date": b_date.isoformat(), "priority": "B", "label": "B", "confirmed": True},
            {"date": a_date.isoformat(), "priority": "A", "label": "A", "confirmed": True},
        ],
        planning_mode="event_goal",
        available_hours=10,
        available_days=["mon", "tue", "wed", "thu", "fri", "sat", "sun"],
        persist=True,
    )
    active = ps.get_active_plan(db)
    templates = list(active["session_templates"])
    weekly = list(active["weekly_summary"])

    race_weeks = {
        idx
        for idx, week in enumerate(weekly)
        if str(week.get("phase") or "") == "Race Week"
        or any(
            str(t.get("session_role") or "") == "race"
            for t in templates[idx * 7 : idx * 7 + 7]
        )
    }

    for week_index in range(len(weekly)):
        week_templates = templates[week_index * 7 : week_index * 7 + 7]
        counts = [len(t.get("sessions") or []) for t in week_templates]
        # no day anywhere carries three independent sessions
        assert max(counts, default=0) <= 2, (week_index, counts)
        if week_index in race_weeks:
            continue  # overlays may deliberately undershoot
        assert counts.count(0) >= 1, (week_index, counts)
        assert sum(1 for c in counts if c == 2) <= 2, (week_index, counts)
        assert 5 <= sum(counts) <= 10, (week_index, counts)
        # weekly hours stay within availability plus one technical step
        minutes = sum(
            int(s.get("duration_minutes") or 0)
            for t in week_templates
            for s in (t.get("sessions") or [])
        )
        assert minutes <= 10 * 60 + 30, (week_index, minutes)
