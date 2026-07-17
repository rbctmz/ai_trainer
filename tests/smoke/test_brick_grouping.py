"""M5 (Issue #205): bricks are grouped ordered sessions; deep-fatigue
suppression is bounded to the seven-day readiness window.

A brick is one coupled workout — not two coincidental same-day sessions: its
legs share an explicit ``group_id``, carry ``leg_index``, and keep bike-then-run
order, while delivery emits one idempotent event per leg. Today's deep fatigue
may remove the CURRENT week's brick, but never erases Build/Peak bricks weeks
away (readiness-bounding precedent from #201/#202, implemented with M3b).
"""
from __future__ import annotations

from datetime import date

import pytest

from models.session_identity import ensure_session_identities
from models.training_planner import (
    build_daily_session_templates,
    expand_weekly_to_daily_triathlon,
    iter_leaf_sessions,
)
from models.workout_catalog import prepare_weekly_brick_allocations


pytestmark = pytest.mark.smoke

_ZONES = {"ftp": 159, "lthr": 160, "threshold_pace": 300}


def _build_weeks(phases: list[str], load_state: str = "balanced"):
    daily, weekly = expand_weekly_to_daily_triathlon(
        [420] * len(phases),
        phases,
        "Олимпийка",
        date(2026, 8, 3),
        goal_type="Триатлон",
        load_state=load_state,
        available_weekly_hours=10.0,
    )
    allocation = prepare_weekly_brick_allocations(
        daily,
        weekly,
        goal_type="Триатлон",
        protected_dates=set(),
        load_state=load_state,
    )
    templates = build_daily_session_templates(
        allocation["daily_plan"],
        weekly,
        goal_type="Триатлон",
        distance="Олимпийка",
        zone_snapshot=_ZONES,
        brick_day_indices=set(allocation["brick_day_indices"]),
    )
    plan = ensure_session_identities(
        {"daily_plan": allocation["daily_plan"], "session_templates": templates}
    )
    return allocation, weekly, plan["session_templates"]


def _brick_templates(templates):
    return [
        (t, s)
        for t in templates
        for s in (t.get("sessions") or [])
        if str(s.get("kind") or "") == "composite"
    ]


def test_brick_is_one_grouped_ordered_occasion():
    _allocation, _weekly, templates = _build_weeks(["Build"])
    bricks = _brick_templates(templates)
    assert len(bricks) == 1
    template, session = bricks[0]

    # one occasion in the day's sessions — never two coincidental workouts
    assert len(template["sessions"]) == 1
    parent_id = str(session.get("session_id") or "")
    assert parent_id

    legs = session.get("legs") or []
    assert [leg.get("sport") for leg in legs] == ["bike", "run"]
    assert [int(leg.get("leg_index") or 0) for leg in legs] == [1, 2]
    assert [leg.get("leg_id") for leg in legs] == [f"{parent_id}:1", f"{parent_id}:2"]
    assert all(leg.get("materialized_steps") for leg in legs)

    leaves = iter_leaf_sessions(template)
    assert [leaf["kind"] for leaf in leaves] == ["brick_leg", "brick_leg"]
    assert [leaf["sport"] for leaf in leaves] == ["bike", "run"]
    # explicit group identity: both legs share the parent's group_id, and the
    # leaf ids are distinct within the group
    assert {leaf.get("group_id") for leaf in leaves} == {parent_id}
    assert leaves[0]["session_id"] != leaves[1]["session_id"]
    assert [leaf.get("leg_index") for leaf in leaves] == [1, 2]


def test_brick_delivery_emits_one_event_per_leg_in_order():
    from models.intervals_workout_delivery import (
        AI_TRAINER_EXTERNAL_ID_PREFIX,
        build_delivery_events,
    )

    allocation, _weekly, templates = _build_weeks(["Build"])
    template, session = _brick_templates(templates)[0]
    parent_id = str(session.get("session_id") or "")

    events = build_delivery_events(
        {"daily_plan": allocation["daily_plan"], "session_templates": templates},
        [template["date"]],
    )
    assert [e["external_id"] for e in events] == [
        f"{AI_TRAINER_EXTERNAL_ID_PREFIX}{parent_id}:leg:1",
        f"{AI_TRAINER_EXTERNAL_ID_PREFIX}{parent_id}:leg:2",
    ]
    # bike leg starts first; the run leg starts after it (transition gap)
    assert events[0]["start_date_local"] < events[1]["start_date_local"]
    assert events[0]["type"] == "Ride" and events[1]["type"] == "Run"


def test_deep_fatigue_removes_only_the_readiness_window_brick():
    """Current deep fatigue suppresses the brick of the week inside the
    seven-day window from the plan start, and leaves later Build weeks intact
    (previously it erased bricks across the whole macrocycle)."""
    allocation, weekly, templates = _build_weeks(["Build", "Build"], load_state="deep_fatigue")

    # week 1 (inside the window): no brick, and its long day is single-sport —
    # bike+run without an explicit brick is forbidden
    assert all(index >= 7 for index in allocation["brick_day_indices"])
    week1_long = [
        allocation["daily_plan"][i]
        for i in range(7)
        if weekly[0]["day_roles"][i] == "long"
    ]
    assert week1_long
    for _dt, _total, parts in week1_long:
        active = [s for s, v in parts.items() if float(v or 0.0) > 0]
        assert active == ["bike"], parts

    # week 2 (outside the window): the brick is intact
    bricks = _brick_templates(templates)
    assert len(bricks) == 1
    assert bricks[0][0]["week_index"] == 1


def test_balanced_build_weeks_each_keep_their_brick():
    allocation, _weekly, templates = _build_weeks(["Build", "Build"])
    bricks = _brick_templates(templates)
    assert len(bricks) == 2
    assert sorted(t["week_index"] for t, _s in bricks) == [0, 1]


def test_macrocycle_under_deep_fatigue_keeps_future_peak_bricks():
    """The original defect: today's fatigue erased September bricks. A 13-week
    macrocycle built under deep_fatigue must keep every Build/Peak brick
    outside the seven-day window."""
    phases = ["Base"] * 4 + ["Build"] * 4 + ["Peak"] * 2 + ["Taper"] * 2 + ["Race Week"]
    _allocation, _weekly, templates = _build_weeks(phases, load_state="deep_fatigue")
    brick_weeks = sorted({t["week_index"] for t, _s in _brick_templates(templates)})
    # Build weeks are indices 4-7, Peak 8-9 — all outside the first-week window
    assert brick_weeks == [4, 5, 6, 7, 8, 9], brick_weeks
