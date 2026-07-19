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


def test_no_single_occasion_absorbs_disproportionate_weekly_share():
    result = _schedule()
    week_total = sum(_sport_week_totals(result).values())
    for day in _occasions(result):
        for occasion in day:
            occasion_total = sum(float(t) for t in occasion["parts"].values())
            assert occasion_total <= 0.40 * week_total, (occasion, week_total)


_PROBE_ZONES = {"ftp": 159, "lthr": 160, "threshold_pace": 300}


def _materialized_week_minutes(result, *, phase: str = "Build") -> int:
    """Measure the week the way the plan will actually materialize it."""
    from models.training_planner import _estimate_session_duration_minutes
    from models.workout_catalog import (
        materialize_brick_session,
        materialize_session_template,
    )

    minutes = 0
    for day in _occasions(result):
        for occasion in day:
            parts = {s: float(t) for s, t in occasion["parts"].items()}
            if occasion["is_brick"]:
                total = round(sum(parts.values()), 1)
                seed = _estimate_session_duration_minutes(total, "bike", "long")
                brick = materialize_brick_session(
                    phase=phase,
                    target_tss=total,
                    parts={"run": 0.0, "swim": 0.0, **parts},
                    estimated_duration_minutes=seed,
                    goal_type="триатлон",
                    zone_snapshot=_PROBE_ZONES,
                    load_state="balanced",
                )
                minutes += int(brick.get("duration_minutes") or seed)
                continue
            sport = occasion["sport"]
            tss = parts.get(sport, 0.0)
            seed = _estimate_session_duration_minutes(tss, sport, occasion["role"])
            template = materialize_session_template(
                phase=phase,
                session_role=occasion["role"],
                sport=sport,
                target_tss=tss,
                estimated_duration_minutes=seed,
                goal_type="триатлон",
                zone_snapshot=_PROBE_ZONES,
                load_state="balanced",
                recent_template_keys=[],
            )
            minutes += int(template.get("duration_minutes") or seed)
    return minutes


def test_hours_check_must_not_cut_budget_that_materializes_within_availability():
    """M3b.1 blocker 1: the 420-TSS Build week materializes to ~455 minutes —
    it already fits 10h+5min, so the scheduler must keep every TSS. Capacity is
    a ceiling, not an obligation to fill; but achievable load must never be cut
    by a steeper surrogate estimator."""
    budget = {"bike": 189.0, "run": 155.4, "swim": 75.6}
    result = _schedule(week_budget=dict(budget), available_weekly_hours=10.0)

    assert _sport_week_totals(result) == pytest.approx(budget, abs=0.11)
    assert result["status"] == "scheduled"
    assert _materialized_week_minutes(result) <= 10 * 60 + 5


def test_actual_hours_trim_sets_reduced_status():
    """M3b.1 blocker 2: any real trim must be visible in the status field
    itself, not only in a note."""
    budget = {"bike": 189.0, "run": 155.4, "swim": 75.6}
    result = _schedule(week_budget=dict(budget), available_weekly_hours=3.0)

    trimmed_total = sum(_sport_week_totals(result).values())
    assert trimmed_total < sum(budget.values()) - 0.5
    assert result["status"] in {"reduced", "infeasible"}
    assert any("снижен" in note or "час" in note for note in result["notes"]), result["notes"]
    assert _materialized_week_minutes(result) <= 3 * 60 + 5


def _vertical_week(phase: str, w_tss: int, hours: float):
    """The real product path: expand → brick allocation → builder."""
    from datetime import date as _date

    from models.training_planner import (
        build_daily_session_templates,
        expand_weekly_to_daily_triathlon,
    )
    from models.workout_catalog import prepare_weekly_brick_allocations

    daily, weekly = expand_weekly_to_daily_triathlon(
        [w_tss],
        [phase],
        "Олимпийка",
        _date(2026, 8, 3),
        goal_type="Триатлон",
        load_state="balanced",
        available_weekly_hours=hours,
    )
    allocation = prepare_weekly_brick_allocations(
        daily,
        weekly,
        goal_type="Триатлон",
        protected_dates=set(),
        load_state="balanced",
    )
    templates = build_daily_session_templates(
        allocation["daily_plan"],
        weekly,
        goal_type="Триатлон",
        distance="Олимпийка",
        zone_snapshot=_PROBE_ZONES,
        brick_day_indices=set(allocation["brick_day_indices"]),
    )
    minutes = sum(
        int(s.get("duration_minutes") or 0)
        for t in templates
        for s in (t.get("sessions") or [])
    )
    return weekly, minutes


@pytest.mark.parametrize(
    ("phase", "w_tss", "hours"),
    [
        ("Build", 420, 3.0),
        ("Taper", 420, 6.0),  # round-3 minimal RED: two-a-day role/order drift
        ("Taper", 550, 6.0),
        ("Peak", 550, 4.0),
        ("Base", 300, 5.0),
    ],
)
def test_persisted_week_respects_hours_end_to_end(phase, w_tss, hours):
    """The hours ceiling must hold on PERSISTED sessions for any phase/budget:
    the scheduler's duration projection must aggregate occasions into the same
    calendar days, the same day role/order, and the same shared weekly template
    rotation the builder uses (single: its duration; composite: the parent;
    brick fallback: both independent sessions)."""
    weekly, minutes = _vertical_week(phase, w_tss, hours)
    assert minutes <= int(hours * 60) + 5, (phase, w_tss, hours, minutes)


def test_reduced_week_materializes_within_availability_end_to_end():
    """M3b.1 round 2: a 3h Build week is explicitly reduced and fits."""
    weekly, minutes = _vertical_week("Build", 420, 3.0)
    assert weekly[0].get("scheduler_status") == "reduced"
    assert minutes <= 3 * 60 + 5, minutes


def test_second_week_respects_hours_despite_template_rotation_drift():
    """M3b.1 round 4: the builder carries recent_template_keys across the WHOLE
    plan, so week 2 selects fresher (sometimes longer) templates. The
    scheduler's projection must start week 2 from week 1's projected rotation —
    minimal RED case: two identical Base 420-TSS weeks at 6h, week 2 persists
    385 min > 365 on the unfixed head."""
    from datetime import date as _date

    from models.training_planner import (
        build_daily_session_templates,
        expand_weekly_to_daily_triathlon,
    )
    from models.workout_catalog import prepare_weekly_brick_allocations

    daily, weekly = expand_weekly_to_daily_triathlon(
        [420, 420],
        ["Base", "Base"],
        "Олимпийка",
        _date(2026, 8, 3),
        goal_type="Триатлон",
        load_state="balanced",
        available_weekly_hours=6.0,
    )
    allocation = prepare_weekly_brick_allocations(
        daily,
        weekly,
        goal_type="Триатлон",
        protected_dates=set(),
        load_state="balanced",
    )
    templates = build_daily_session_templates(
        allocation["daily_plan"],
        weekly,
        goal_type="Триатлон",
        distance="Олимпийка",
        zone_snapshot=_PROBE_ZONES,
        brick_day_indices=set(allocation["brick_day_indices"]),
    )

    for week_index in range(2):
        minutes = sum(
            int(s.get("duration_minutes") or 0)
            for t in templates[week_index * 7 : week_index * 7 + 7]
            for s in (t.get("sessions") or [])
        )
        assert minutes <= 6 * 60 + 5, (week_index, minutes)


def test_absent_and_zero_preferences_reproduce_default_placement():
    """Requested before merge: absent and all-zero day preferences must both
    reproduce the default deterministic placement exactly."""
    base = _schedule()
    absent = _schedule(day_preferences=None)
    zero = _schedule(
        day_preferences={"bike": [0.0] * 7, "run": [0.0] * 7, "swim": [0.0] * 7}
    )
    assert base == absent
    assert base == zero


def test_weights_overrides_become_slot_day_preferences():
    """M3b.1: `weights_overrides` must not be silently ignored — a user's
    Sunday-heavy bike weighting moves the long ride to Sunday."""
    from datetime import date as _date

    from models.training_planner import expand_weekly_to_daily_triathlon

    _daily, weekly = expand_weekly_to_daily_triathlon(
        [420],
        ["Build"],
        "Олимпийка",
        _date(2026, 8, 3),
        weights_overrides={
            "Build": {"bike": [0.0, 0.0, 0.0, 0.0, 0.0, 0.1, 0.9]}
        },
        goal_type="Триатлон",
        load_state="balanced",
    )

    roles = weekly[0]["day_roles"]
    assert roles.index("long") == 6, roles


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
        # a NORMAL week keeps the 7-10 occasion band; only taper or an
        # explicitly reduced week may drop to 5, and only with a stated reason
        phase = str(weekly[week_index].get("phase") or "")
        reduced = bool(weekly[week_index].get("scheduler_notes"))
        if phase in {"Base", "Build", "Peak", "Maintenance"} and not reduced:
            assert 7 <= sum(counts) <= 10, (week_index, phase, counts)
        else:
            assert 5 <= sum(counts) <= 10, (week_index, phase, counts)
            assert reduced or phase in {"Taper", "Race Week", "Recovery"}, (
                week_index,
                phase,
            )
        # weekly hours stay within availability plus ONE scheduler quantum
        minutes = sum(
            int(s.get("duration_minutes") or 0)
            for t in week_templates
            for s in (t.get("sessions") or [])
        )
        assert minutes <= 10 * 60 + 5, (week_index, minutes)


@pytest.mark.parametrize("race_weekday", [5, 6], ids=["saturday", "sunday"])
def test_post_race_spillover_week_is_explicitly_reduced(tmp_path, race_weekday):
    """Issue #226: an A/B race at the END of a week pushes its protected
    recovery days (D+1/D+2) into the NEXT week. That week may honestly hold
    fewer than 7 occasions — but ONLY as an EXPLICIT reduction: its
    scheduler_notes must name the race, and the annotation must survive
    checkpoint persistence (read back through the persisted active plan).
    The race weekday is pinned relative to today, so this holds on every
    calendar day — the original histogram test only tripped on Sundays."""
    from api import planning_service as ps

    db = Database(str(tmp_path / f"scheduler-spill-{race_weekday}.db"))
    today = datetime.now().date()
    days_ahead = (race_weekday - today.weekday()) % 7
    b_date = today + timedelta(days=days_ahead + 7)  # ≥ a week out, pinned weekday
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

    race_index = next(
        index
        for index, template in enumerate(templates)
        if str(template.get("session_role") or "") == "race"
        and str(template.get("date") or "")[:10] == b_date.isoformat()
    )
    spill_week = race_index // 7 + 1
    assert spill_week < len(weekly)

    row = weekly[spill_week]
    notes = [str(note) for note in (row.get("scheduler_notes") or [])]
    assert notes, f"spillover week {spill_week} must state why it is reduced"
    assert any(b_date.isoformat() in note for note in notes), notes

    counts = [
        len(t.get("sessions") or [])
        for t in templates[spill_week * 7 : spill_week * 7 + 7]
    ]
    assert 5 <= sum(counts) <= 10, (spill_week, counts)
