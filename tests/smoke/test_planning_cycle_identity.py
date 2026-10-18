"""S2 M1: cycle separation must reach IDs, lineage and historical evidence."""
from copy import deepcopy

import pytest

from models.intervals_workout_delivery import build_delivery_events
from models.planning_checkpoints import build_planning_checkpoint, restore_goal_plan_from_checkpoint
from models.session_identity import ensure_session_identities
from tests.smoke._planning_cycle_regressions import (
    CYCLE_A, CYCLE_B, evidence_bytes, first_session_id, identity_keys,
    legacy_db, namespaced_plan, plan, seed_evidence,
)

pytestmark = pytest.mark.smoke


@pytest.mark.parametrize("kind", ["single", "multisport", "brick"])
def test_behavior_overlapping_cycles_have_disjoint_identity_keys(kind):
    a = ensure_session_identities(namespaced_plan(CYCLE_A, kind=kind))
    b = ensure_session_identities(namespaced_plan(CYCLE_B, kind=kind))
    assert identity_keys(a)
    assert identity_keys(b)
    assert identity_keys(a).isdisjoint(identity_keys(b))


@pytest.mark.parametrize("changed", [False, True], ids=["identical", "changed"])
def test_behavior_previous_cycle_cannot_donate_ids_or_lineage(changed):
    a = ensure_session_identities(namespaced_plan(CYCLE_A))
    candidate = deepcopy(a)  # stale client material, including embedded IDs
    candidate["identity_namespace"] = CYCLE_B
    if changed:
        candidate["session_templates"][0]["duration_minutes"] += 5
        candidate["session_templates"][0]["sessions"][0]["duration_minutes"] += 5
    b = ensure_session_identities(candidate, previous_goal_plan=a)
    # A mistaken previous_goal_plan argument must never create cross-cycle
    # survivor/replaces links, even when the prescription actually changed.
    assert identity_keys(a).isdisjoint(identity_keys(b))
    for template in b["session_templates"]:
        for session in [template, *template.get("sessions", [])]:
            assert not session.get("replaces_session_id")
            assert not session.get("parent_session_id")


@pytest.mark.parametrize("kind", ["single", "multisport", "brick"])
def test_characterization_same_cycle_repeat_and_reorder_keep_ids(kind):
    a = ensure_session_identities(namespaced_plan(CYCLE_A, kind=kind))
    candidate = deepcopy(a)
    for template in candidate["session_templates"]:
        if template.get("sessions"):
            template["sessions"].reverse()
    b = ensure_session_identities(candidate, previous_goal_plan=a)
    assert identity_keys(a) == identity_keys(b)
    assert ensure_session_identities(b, previous_goal_plan=b) == b


def test_behavior_namespace_survives_checkpoint_restore():
    original = ensure_session_identities(namespaced_plan(CYCLE_A))
    restored = restore_goal_plan_from_checkpoint(build_planning_checkpoint(original))
    assert restored.get("identity_namespace") == CYCLE_A
    assert identity_keys(ensure_session_identities(restored)) == identity_keys(original)


def test_characterization_legacy_identity_and_prescription_roundtrip():
    original = ensure_session_identities(plan())
    original["session_templates"][0]["session_id"] = "ats_legacy_frozen_day"
    original["session_templates"][0]["sessions"][0]["session_id"] = "ats_legacy_frozen_day"
    restored = restore_goal_plan_from_checkpoint(build_planning_checkpoint(original))
    assert restored["session_templates"] == original["session_templates"]
    assert restored["daily_plan"] == original["daily_plan"]
    assert "ats_legacy_frozen_day" in identity_keys(ensure_session_identities(restored))


def test_nested_composite_legs_cannot_reuse_other_cycle_ids():
    candidate = namespaced_plan(CYCLE_A, kind="multisport")
    for session in candidate["session_templates"][0]["sessions"]:
        session.update(kind="composite", legs=[{"leg_index": 1, "sport": "bike"}, {"leg_index": 2, "sport": "run"}])
    a = ensure_session_identities(candidate)
    stale = deepcopy(a)
    stale["identity_namespace"] = CYCLE_B
    b = ensure_session_identities(stale, previous_goal_plan=a)
    assert identity_keys(a).isdisjoint(identity_keys(b))
    for session in b["session_templates"][0]["sessions"]:
        assert all(leg["leg_id"].startswith(session["session_id"] + ":") for leg in session["legs"])
    assert ensure_session_identities(b, previous_goal_plan=b) == b


@pytest.mark.parametrize("ledger", ["match", "feedback"])
def test_behavior_new_cycle_does_not_resolve_previous_evidence(tmp_path, monkeypatch, ledger):
    db = legacy_db(tmp_path, monkeypatch)
    a_id = first_session_id(namespaced_plan(CYCLE_A))
    b_id = first_session_id(namespaced_plan(CYCLE_B))
    match, feedback, _delivery = seed_evidence(db, a_id)
    before = evidence_bytes(db)
    if ledger == "match":
        assert db.get_latest_plan_actual_match_for_session(a_id)["id"] == match["id"]
        assert db.get_latest_plan_actual_match_for_session(b_id) is None
    else:
        assert db.get_latest_session_feedback(a_id)["id"] == feedback["id"]
        assert db.get_latest_session_feedback(b_id) is None
    assert evidence_bytes(db) == before


@pytest.mark.parametrize("kind", ["single", "multisport", "brick"])
def test_behavior_new_cycle_provider_keys_cannot_overwrite_previous_cycle(kind):
    a = build_delivery_events(namespaced_plan(CYCLE_A, kind=kind), ["2026-09-28"])
    b = build_delivery_events(namespaced_plan(CYCLE_B, kind=kind), ["2026-09-28"])
    a_keys = {event["external_id"] for event in a}
    b_keys = {event["external_id"] for event in b}
    assert a_keys and b_keys
    assert len(a_keys) == (2 if kind in {"multisport", "brick"} else 1)
    assert a_keys.isdisjoint(b_keys)
