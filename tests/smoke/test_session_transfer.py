"""Shared atomic transfer primitive contract (Issue #209, pre-registered RED).

`models/session_transfer.py::apply_session_transfer` is the ONE mechanism that
moves a session: clone plan → validate source id → remove source + insert the
preserved structured session at the target → rebuild both day projections and
weekly buckets → `ensure_session_identities(previous_goal_plan=...)` → verify
invariants. The near-term editor is not a transfer mechanism (it rebuilds
sessions from scalars and loses structure). Preview and confirm both use this
primitive, so what the ranker promised is exactly what gets applied.
"""
from __future__ import annotations

import json
from datetime import date, timedelta

import pytest

from tests.smoke.test_recovery_transfer import (
    _TODAY,
    _brick_session,
    _conflict,
    _plan,
    _session,
    _week,
)


pytestmark = pytest.mark.smoke


def _apply(plan, session_id: str, target_offset: int):
    from models.session_transfer import apply_session_transfer

    return apply_session_transfer(
        plan,
        session_id=session_id,
        target_date=(_TODAY + timedelta(days=target_offset)).isoformat(),
    )


def test_transfer_preserves_structured_steps_byte_for_byte():
    plan = _week(d1=[], d2=[], d3=[])
    conflict = _conflict(plan)
    source_session = plan["session_templates"][0]["sessions"][0]
    original_steps = json.dumps(source_session["materialized_steps"], sort_keys=True)

    result = _apply(plan, conflict["session_id"], 2)
    moved = result["goal_plan"]["session_templates"][2]["sessions"][0]

    assert json.dumps(moved["materialized_steps"], sort_keys=True) == original_steps
    assert moved["sport"] == source_session["sport"]
    assert moved["session_role"] == source_session["session_role"]
    assert float(moved["total_tss"]) == float(source_session["total_tss"])
    assert moved["template_key"] == source_session["template_key"]


def test_transfer_rebuilds_days_and_weekly_buckets_from_sessions():
    """The #206 layering holds after a transfer: daily totals, parts, day
    scalars, and the weekly per-sport buckets are recomputed from the resulting
    sessions — the three-way anchor stays intact by construction."""
    plan = _week(d1=[_session("swim", "recovery", 15.0)], d2=[], d3=[])
    conflict = _conflict(plan)

    result = _apply(plan, conflict["session_id"], 2)
    moved_plan = result["goal_plan"]

    source_day = moved_plan["daily_plan"][0]
    target_day = moved_plan["daily_plan"][2]
    assert source_day[1] == 0.0 and source_day[2]["bike"] == 0.0
    assert target_day[1] == 80.0 and target_day[2]["bike"] == 80.0

    source_template = moved_plan["session_templates"][0]
    target_template = moved_plan["session_templates"][2]
    assert source_template["sessions"] == []
    assert source_template["session_role"] == "off"
    assert target_template["session_role"] == "quality"
    assert target_template["sport"] == "bike"

    week = moved_plan["weekly_summary"][0]
    leaf_bike = sum(
        float(s.get("total_tss") or 0.0)
        for t in moved_plan["session_templates"][:7]
        for s in (t.get("sessions") or [])
        if s.get("sport") == "bike"
    )
    assert float(week["bike"]) == pytest.approx(leaf_bike, abs=0.11)
    assert int(week["weekly_tss"]) == int(
        round(sum(t for _d, t, _p in moved_plan["daily_plan"][:7]))
    )


def test_transfer_is_append_only_on_the_input_plan():
    """The primitive clones: the input goal plan is not mutated."""
    plan = _week(d1=[], d2=[], d3=[])
    conflict = _conflict(plan)
    before = json.dumps(
        [t.get("date") for t in plan["session_templates"]]
        + [str(plan["session_templates"][0]["sessions"])],
        sort_keys=True,
    )

    _apply(plan, conflict["session_id"], 2)

    after = json.dumps(
        [t.get("date") for t in plan["session_templates"]]
        + [str(plan["session_templates"][0]["sessions"])],
        sort_keys=True,
    )
    assert before == after


def test_transfer_fails_closed_on_unknown_session_or_date():
    plan = _week(d1=[], d2=[], d3=[])
    conflict = _conflict(plan)

    from models.session_transfer import apply_session_transfer

    with pytest.raises(ValueError, match="session"):
        apply_session_transfer(
            plan,
            session_id="ats_does_not_exist",
            target_date=(_TODAY + timedelta(days=2)).isoformat(),
        )
    with pytest.raises(ValueError, match="date"):
        apply_session_transfer(
            plan,
            session_id=conflict["session_id"],
            target_date="2030-01-01",
        )


def test_brick_moves_as_parent_with_relinked_leg_ids():
    specs = [
        {"sessions": [_brick_session(60.0, 30.0)]},
        {"sessions": []},
        {"sessions": []},
        {"sessions": []},
        {"sessions": []},
        {"sessions": []},
        {"sessions": []},
    ]
    plan = _plan(specs)
    conflict = _conflict(plan)

    result = _apply(plan, conflict["session_id"], 1)
    moved_plan = result["goal_plan"]
    assert moved_plan["session_templates"][0]["sessions"] == []
    moved = moved_plan["session_templates"][1]["sessions"][0]
    new_id = str(moved["session_id"])
    assert new_id != conflict["session_id"]
    assert [leg["leg_id"] for leg in moved["legs"]] == [f"{new_id}:1", f"{new_id}:2"]
    assert [leg["sport"] for leg in moved["legs"]] == ["bike", "run"]


def test_preview_day_changes_equal_applied_result():
    """What the variant preview shows is byte-identical to what the primitive
    applies — one shared mechanism, no ranker/editor divergence."""
    from models.recovery_transfer import build_transfer_variant
    from models.session_transfer import apply_session_transfer

    plan = _week(d1=[_session("swim", "recovery", 15.0)], d2=[], d3=[])
    conflict = _conflict(plan)

    variant = build_transfer_variant(plan, conflict, today=_TODAY)
    assert variant is not None
    applied = apply_session_transfer(
        plan,
        session_id=conflict["session_id"],
        target_date=variant["target_date"],
    )
    moved_plan = applied["goal_plan"]
    by_date = {t["date"]: t for t in moved_plan["session_templates"]}
    for change in variant["day_changes"]:
        assert change["after_sessions"] == by_date[change["date"]]["sessions"]