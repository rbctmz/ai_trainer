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
from datetime import timedelta

import pytest

from models.session_identity import ensure_session_identities
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
    """The primitive clones: the ENTIRE input goal plan — templates, daily_plan,
    weekly_summary, constraint_summary, every nested session — is byte-identical
    before and after (review round 2: whole-plan deep snapshot, not a sample)."""
    plan = _week(d1=[_session("swim", "recovery", 15.0)], d2=[], d3=[])
    conflict = _conflict(plan)
    before = json.dumps(plan, sort_keys=True, default=str)

    _apply(plan, conflict["session_id"], 2)

    assert json.dumps(plan, sort_keys=True, default=str) == before


def test_target_neighbour_keeps_identity_when_day_gains_second_session():
    """Checker M2 blocker 1 (1→2): the untouched existing session on the target
    day keeps its session_id and gains no lineage when the transfer makes the
    day two-session. Its fingerprint legitimately transitions from the day-level
    to its own content-level value (#206: a multi-session day fingerprints each
    session on its own material) — but the ID, which delivery/reconciliation
    key on, must not churn, and the result must be restamp-stable."""
    plan = _week(d1=[_session("swim", "recovery", 15.0)], d2=[], d3=[])
    conflict = _conflict(plan)
    neighbour_before = dict(plan["session_templates"][1]["sessions"][0])
    assert neighbour_before["session_id"]

    result = _apply(plan, conflict["session_id"], 1)
    moved_plan = result["goal_plan"]
    target_sessions = moved_plan["session_templates"][1]["sessions"]
    assert len(target_sessions) == 2
    neighbour_after = next(s for s in target_sessions if s["sport"] == "swim")
    moved_after = next(s for s in target_sessions if s["sport"] == "bike")

    assert neighbour_after["session_id"] == neighbour_before["session_id"]
    assert "replaces_session_id" not in neighbour_after
    assert moved_after["session_id"] != conflict["session_id"]
    assert moved_after["replaces_session_id"] == conflict["session_id"]

    restamped = ensure_session_identities(moved_plan)
    assert restamped["session_templates"] == moved_plan["session_templates"]


def test_source_survivor_keeps_identity_when_day_drops_to_single():
    """Checker M2 blocker 1 (2→1): after the moved session leaves a two-session
    day, the surviving neighbour keeps its exact session_id AND fingerprint and
    gains no lineage — it did not change, only its sibling left."""
    plan = _week(d1=[], d2=[], d3=[])
    plan["session_templates"][0]["sessions"].append(dict(_session("swim", "easy", 20.0)))
    plan = ensure_session_identities(plan)
    conflict = _conflict(plan)
    survivor_before = dict(
        next(s for s in plan["session_templates"][0]["sessions"] if s["sport"] == "swim")
    )

    result = _apply(plan, conflict["session_id"], 2)
    moved_plan = result["goal_plan"]
    source_sessions = moved_plan["session_templates"][0]["sessions"]
    assert len(source_sessions) == 1
    survivor_after = source_sessions[0]

    assert survivor_after["session_id"] == survivor_before["session_id"]
    assert (
        survivor_after["session_material_fingerprint"]
        == survivor_before["session_material_fingerprint"]
    )
    assert "replaces_session_id" not in survivor_after
    assert not moved_plan["session_templates"][0].get("replaces_session_id")

    restamped = ensure_session_identities(moved_plan)
    assert restamped["session_templates"] == moved_plan["session_templates"]


def test_transfer_rebuilds_weekly_day_roles_and_focuses():
    """Checker M2 blocker 4: the weekly structure projection (day_roles /
    day_focuses) must follow the resulting templates, not stay on the old
    dates — otherwise every weekly consumer renders the pre-transfer week."""
    plan = _week(d1=[], d2=[], d3=[])
    conflict = _conflict(plan)

    result = _apply(plan, conflict["session_id"], 2)
    moved_plan = result["goal_plan"]
    week = moved_plan["weekly_summary"][0]
    templates = moved_plan["session_templates"][:7]

    assert week["day_roles"] == [str(t.get("session_role")) for t in templates]
    assert week["day_roles"][0] == "off"
    assert week["day_roles"][2] == "quality"
    assert week["day_focuses"] == [str(t.get("session_focus")) for t in templates]


def test_duplicate_twin_transfer_keeps_survivor_id_unambiguous():
    """Checker M2 remainder 1: with two content-identical sessions on a day,
    transferring the FIRST must not hand its id to the surviving twin — the
    survivor keeps its own ordinal-derived id with no lineage, the moved
    session mints a fresh id whose `replaces_session_id` points at the old
    first id, and the whole result is restamp-stable."""
    twin = _session("bike", "quality", 60.0)
    specs = [{"sessions": [dict(twin), dict(twin)]}] + [{"sessions": []} for _ in range(6)]
    plan = _plan(specs)
    ids_before = [s["session_id"] for s in plan["session_templates"][0]["sessions"]]
    assert len(set(ids_before)) == 2
    conflict = _conflict(plan)
    assert conflict["session_id"] == ids_before[0]

    result = _apply(plan, conflict["session_id"], 2)
    moved_plan = result["goal_plan"]
    source_sessions = moved_plan["session_templates"][0]["sessions"]
    assert len(source_sessions) == 1
    survivor = source_sessions[0]
    assert survivor["session_id"] == ids_before[1]
    assert "replaces_session_id" not in survivor

    moved = moved_plan["session_templates"][2]["sessions"][0]
    assert moved["replaces_session_id"] == ids_before[0]
    assert moved["session_id"] not in ids_before

    restamped = ensure_session_identities(moved_plan)
    assert restamped["session_templates"] == moved_plan["session_templates"]


@pytest.mark.parametrize(
    ("twin_count", "moved_position"),
    [(3, 0), (3, 1), (3, 2), (4, 0), (4, 1), (4, 2), (4, 3)],
)
def test_twin_matrix_transfer_keeps_all_ids_unique_and_survivors_stable(
    twin_count, moved_position
):
    """Checker M2 blocker (round 3): the full twin matrix. Moving ANY one of
    3 or 4 identical sessions must leave every resulting id unique across the
    plan; each survivor keeps exactly its own prior id in day order with no
    lineage; only the moved twin mints a fresh id replacing the old one. An
    embedded-honored survivor must CONSUME its id so a later ordinal-shifted
    twin can never take it again — and the guarantee must hold under restamp."""
    twin = _session("bike", "quality", 30.0)
    specs = [{"sessions": [dict(twin) for _ in range(twin_count)]}] + [
        {"sessions": []} for _ in range(6)
    ]
    plan = _plan(specs)
    before = [s["session_id"] for s in plan["session_templates"][0]["sessions"]]
    assert len(set(before)) == twin_count
    moved_id = before[moved_position]

    result = _apply(plan, moved_id, 2)
    moved_plan = result["goal_plan"]
    source_sessions = moved_plan["session_templates"][0]["sessions"]
    source_ids = [s["session_id"] for s in source_sessions]
    target_sessions = moved_plan["session_templates"][2]["sessions"]
    assert len(target_sessions) == 1
    new_id = target_sessions[0]["session_id"]

    assert len(set(source_ids + [new_id])) == twin_count, "every identity stays unique"
    assert source_ids == [sid for i, sid in enumerate(before) if i != moved_position]
    assert new_id not in before
    assert target_sessions[0]["replaces_session_id"] == moved_id
    for session in source_sessions:
        assert "replaces_session_id" not in session

    restamped = ensure_session_identities(moved_plan)
    assert restamped["session_templates"] == moved_plan["session_templates"]


def test_transfer_rebuilds_weekly_structure_metadata_and_day_lead():
    """Checker M2 remainder 2: the weekly structure metadata (key_sessions /
    recovery_days / structure_summary) follows the resulting templates, and on
    an occupied target day the arriving hard session becomes the day's lead
    (sessions[0] and the day role) instead of hiding behind a recovery
    neighbour."""
    from models.training_planner import WEEKDAY_LABELS_RU

    plan = _week(d1=[], d2=[_session("swim", "recovery", 15.0)], d3=[])
    conflict = _conflict(plan)

    result = _apply(plan, conflict["session_id"], 2)
    moved_plan = result["goal_plan"]

    target = moved_plan["session_templates"][2]
    assert target["sessions"][0]["sport"] == "bike"  # hardest-first ordering
    assert target["session_role"] == "quality"       # the day lead is the hard arrival

    week = moved_plan["weekly_summary"][0]
    roles = [str(t.get("session_role")) for t in moved_plan["session_templates"][:7]]
    assert week["day_roles"] == roles
    assert week["key_sessions"] == f"{WEEKDAY_LABELS_RU[2]} quality bike"
    assert week["recovery_days"] == "—"  # the recovery swim is no longer the day's role
    assert week["structure_summary"] == (
        "1 качеств. дн., 0 активац., 0 восстановит. дн., длительная: —"
    )


def test_transfer_to_same_date_fails_closed():
    """Checker M2 blocker 5: target == source is a reorder/no-op, not a
    transfer — the primitive rejects it before any mutation."""
    plan = _week(d1=[], d2=[], d3=[])
    conflict = _conflict(plan)
    before = json.dumps(plan, sort_keys=True, default=str)

    from models.session_transfer import apply_session_transfer

    with pytest.raises(ValueError, match="source day"):
        apply_session_transfer(
            plan,
            session_id=conflict["session_id"],
            target_date=conflict["date"],
        )
    assert json.dumps(plan, sort_keys=True, default=str) == before


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

    # review round 2: the persisted template must project consistent brick
    # leaves — group_id and leg session_ids follow the NEW parent id
    from models.training_planner import iter_leaf_sessions

    leaves = iter_leaf_sessions(moved_plan["session_templates"][1])
    assert [(leaf["kind"], leaf["group_id"], leaf["session_id"]) for leaf in leaves] == [
        ("brick_leg", new_id, f"{new_id}:1"),
        ("brick_leg", new_id, f"{new_id}:2"),
    ]


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