"""#673: real saved evidence, parent identity and canonical freshness."""
from copy import deepcopy
from datetime import timedelta

import pytest

from api.today_snapshot import build_today_decision_snapshot, build_today_decision_story_from_sources
from api.readiness_snapshot import build_readiness_snapshot
from data.database import Database
from models.planning_checkpoints import build_planning_checkpoint
from models.plan_actual_reconciliation import iter_parent_sessions
from models.today_decision_story import compose_today_decision_story
from services.session_projection import session_projection_at
from tests.smoke.test_issue_529_match_handoff import DAY, DAY_ISO, _plan, _session, _activity
from tests.smoke.test_readiness_conflicts import _seed_dated_night
from tests.smoke.test_reconciliation_service_migration import _table_snapshots
from tests.smoke.test_today_decision_story import _wellness

pytestmark = pytest.mark.smoke


def _database(tmp_path, *, actual=True):
    db = Database(str(tmp_path / "daily.db"))
    plan = _plan(_session("bike", "easy", 60), _session("run", "easy", 30))
    checkpoint = db.save_planning_checkpoint(build_planning_checkpoint(plan))
    _seed_dated_night(db, DAY_ISO)
    if actual:
        db.save_activities([_activity()])
    db = Database(db.db_path)  # same startup normalization used by a real API server
    ids = [entry["session"]["session_id"] for entry in iter_parent_sessions(plan["session_templates"])]
    return db, plan, checkpoint, ids


def _story(db, plan, checkpoint, ids):
    return build_today_decision_story_from_sources(
        db, as_of=DAY_ISO, session_id=plan["session_templates"][0]["session_id"],
        session_ids=ids, readiness=build_readiness_snapshot(db, as_of=DAY),
        subjective_wellness=_wellness(day=DAY_ISO),
        primary_action={"kind": "follow_plan", "reason": "План на сегодня", "enabled": True},
        expected_checkpoint_id=checkpoint["id"],
    )


def test_two_parent_day_preserves_completed_bike_and_unobserved_run(tmp_path):
    db, plan, checkpoint, ids = _database(tmp_path)
    story = _story(db, plan, checkpoint, ids)
    assert story["next_action"]["kind"] == "follow_plan"
    assert story["fact"]["session_id"] is None
    parents = story["fact"]["sessions"]
    assert [p["session_id"] for p in parents] == ids
    assert parents[0]["completion_status"] == "complete"
    assert parents[0]["actual"]["activity_ids"] == [_activity()["activity_id"]]
    assert parents[1]["completion_status"] == "not_observed"
    assert parents[1]["actual"]["activity_ids"] == []
    assert story["fact"]["actual"]["load_tss"] == 60
    assert story["fact"]["actual"]["activity_ids"] == [_activity()["activity_id"]]
    assert story["fact"]["actual"]["legs"] == []
    for fact, sid in zip(parents, ids):
        projection = session_projection_at(db, session_id=sid, as_of=DAY_ISO)
        assert fact["plan"] == projection["plan"]
        assert fact["deviation"] == projection["deviation"]
        assert fact["cause"] == projection["cause"]
        assert fact["evidence_revision"] == projection["evidence_revision"]


def test_real_today_snapshot_uses_independent_parents(tmp_path):
    db, _, _, ids = _database(tmp_path)
    today = build_today_decision_snapshot(db, today=DAY)
    assert today["decision_story"]["next_action"]["kind"] == "follow_plan"
    assert [p["session_id"] for p in today["decision_story"]["fact"]["sessions"]] == ids


def test_all_unobserved_parents_are_not_an_incomplete_day(tmp_path):
    db, plan, checkpoint, ids = _database(tmp_path, actual=False)
    story = _story(db, plan, checkpoint, ids)
    assert story["next_action"]["kind"] == "follow_plan"
    assert story["fact"]["completion_status"] == "not_observed"
    assert story["fact"]["actual"]["load_tss"] == 0


def test_failed_parent_preserves_known_fact_and_requires_review(tmp_path):
    db, plan, checkpoint, ids = _database(tmp_path)
    story = _story(db, plan, checkpoint, [ids[0], "absent-parent"])
    assert story["next_action"]["kind"] == "inspect_evidence"
    assert story["fact"]["sessions"][0]["actual"]["load_tss"] == 60
    assert story["fact"]["sessions"][1]["session_id"] == "absent-parent"
    assert story["fact"]["sessions"][1]["projection_status"] == "data_gap"
    assert story["fact"]["actual"]["load_tss"] is None


def test_mixed_checkpoint_does_not_project_a_false_known_day(tmp_path):
    db, plan, checkpoint, ids = _database(tmp_path)
    checkpoint["id"] += 1
    story = _story(db, plan, checkpoint, ids)
    assert story["next_action"]["kind"] == "inspect_evidence"
    assert all(p["projection_status"] == "data_gap" for p in story["fact"]["sessions"])


def test_read_adapter_preserves_tracked_tables_and_single_shape(tmp_path):
    db, plan, checkpoint, ids = _database(tmp_path)
    before = _table_snapshots(db)
    _story(db, plan, checkpoint, ids)
    single = _story(db, plan, checkpoint, ids[:1])
    assert single["fact"]["session_id"] == ids[0]
    assert "sessions" not in single["fact"]
    assert before == _table_snapshots(db)


def _evidence(readiness):
    story = compose_today_decision_story(
        as_of=DAY_ISO, session_projection=None, readiness=readiness,
        subjective_wellness=_wellness(day=DAY_ISO),
        primary_action={"kind": "follow_plan", "reason": "OK"}, rule_versions=None,
    )
    return next(e for e in story["evidence"] if e["kind"] == "readiness")


def test_real_canonical_fresh_recovery_measurements_are_current(tmp_path):
    db, _, _, _ = _database(tmp_path)
    readiness = build_readiness_snapshot(db, as_of=DAY)
    assert readiness["freshness"]["state"] == "fresh"
    assert _evidence(readiness)["freshness"] == "current"


@pytest.mark.parametrize("boundary", ["old_anchor", "future_anchor", "missing_primary", "tsb_only", "blocked", "provisional", "stale", "invalid", "unknown_anchor"])
def test_fresh_summary_alone_cannot_confirm_missing_or_blocked_measurements(tmp_path, boundary):
    db, _, _, _ = _database(tmp_path)
    readiness = deepcopy(build_readiness_snapshot(db, as_of=DAY))
    f = readiness["freshness"]
    if boundary == "old_anchor":
        f["anchor"] = (DAY-timedelta(days=1)).isoformat()
    if boundary == "future_anchor":
        f["anchor"] = (DAY+timedelta(days=1)).isoformat()
    if boundary == "unknown_anchor":
        f["anchor"] = None
    if boundary == "missing_primary":
        f["confirmed_today"].remove("sleep")
    if boundary == "tsb_only":
        f["confirmed_today"] = ["tsb"]
    if boundary == "blocked":
        f["blocked_reason"] = "no_primary"
    if boundary == "provisional":
        f["state"] = "provisional"
    if boundary == "stale":
        readiness["stale"] = True
    if boundary == "invalid":
        f["invalid"] = ["sleep"]
    assert _evidence(readiness)["freshness"] != "current"


@pytest.mark.parametrize("boundary", ["unknown_load", "overlap", "ambiguous"])
def test_multi_parent_summary_never_invents_or_double_counts_facts(tmp_path, boundary):
    db, _, _, ids = _database(tmp_path)
    projections = [session_projection_at(db, session_id=sid, as_of=DAY_ISO) for sid in ids]
    if boundary == "unknown_load":
        projections[0]["fact"]["load_tss"] = None
    elif boundary == "overlap":
        projections[1]["fact"]["actual_activity_ids"] = projections[0]["fact"]["actual_activity_ids"][:]
    else:
        projections[1]["projection_status"] = "needs_confirmation"
        projections[1]["fact"]["completion_status"] = "needs_confirmation"
    story = compose_today_decision_story(
        as_of=DAY_ISO, session_projection=None, session_projections=projections,
        readiness=build_readiness_snapshot(db, as_of=DAY),
        subjective_wellness=_wellness(day=DAY_ISO),
        primary_action={"kind": "follow_plan", "reason": "OK"}, rule_versions=None,
    )
    assert story["fact"]["sessions"][0]["actual"]["activity_ids"] == [_activity()["activity_id"]]
    if boundary in {"unknown_load", "overlap"}:
        assert story["fact"]["actual"]["load_tss"] is None
    if boundary == "overlap":
        assert story["next_action"]["kind"] == "inspect_evidence"
    if boundary == "ambiguous":
        assert story["next_action"]["kind"] == "confirm_match"
    before = deepcopy(story)
    projections[0]["fact"]["actual_activity_ids"].append("later")
    assert story == before


@pytest.mark.parametrize("boundary", ["missing_id", "list_id", "mixed_checkpoint", "malformed_checkpoint"])
def test_multi_parent_invalid_identity_or_mixed_revisions_fail_closed(tmp_path, boundary):
    db, _, _, ids = _database(tmp_path)
    projections = [session_projection_at(db, session_id=sid, as_of=DAY_ISO) for sid in ids]
    if boundary == "missing_id":
        projections[1].pop("session_id")
    elif boundary == "list_id":
        projections[1]["session_id"] = ["invalid"]
    elif boundary == "malformed_checkpoint":
        projections[1]["evidence_revision"]["planning_checkpoint_id"] = {"invalid": 1}
    else:
        projections[1]["evidence_revision"]["planning_checkpoint_id"] += 1
    story = compose_today_decision_story(
        as_of=DAY_ISO, session_projection=None, session_projections=projections,
        readiness=build_readiness_snapshot(db, as_of=DAY),
        subjective_wellness=_wellness(day=DAY_ISO),
        primary_action={"kind": "follow_plan", "reason": "OK"}, rule_versions=None,
    )
    assert story["next_action"]["kind"] == "inspect_evidence"
    assert story["fact"]["actual"]["load_tss"] is None
    assert story["fact"]["sessions"][0]["actual"]["load_tss"] == 60


def test_confirmation_changed_during_snapshot_read_does_not_mix_revisions(tmp_path, monkeypatch):
    from api import today_snapshot
    from api.planning_service import record_plan_actual_match
    db, plan, checkpoint, ids = _database(tmp_path)
    original = _activity()
    other = {**original, "activity_id": "alternate-bike", "duration_minutes": 30, "tss": 30}
    db.save_activities([other])
    record_plan_actual_match(db, base_checkpoint_id=checkpoint["id"], session_id=ids[0],
                             activity_ids=[original["activity_id"]], actual_role="easy", action="confirm")
    from services.session_projection import session_projection_from_reconciliation
    expected_run = {}
    real_reconciliation = today_snapshot.reconciliation_at
    def interleaved(*args, **kwargs):
        frozen = real_reconciliation(*args, **kwargs)
        expected_run.update(session_projection_from_reconciliation(db, frozen, session_id=ids[1]))
        record_plan_actual_match(db, base_checkpoint_id=checkpoint["id"], session_id=ids[0],
                                 activity_ids=[other["activity_id"]], actual_role="easy", action="confirm")
        return frozen
    monkeypatch.setattr(today_snapshot, "reconciliation_at", interleaved)
    story = _story(db, plan, checkpoint, ids)
    assert story["next_action"]["kind"] == "inspect_evidence"
    assert story["fact"]["sessions"][0]["projection_status"] == "data_gap"
    assert story["fact"]["sessions"][1]["session_id"] == ids[1]
    run_fact = story["fact"]["sessions"][1]
    assert run_fact["completion_status"] == expected_run["fact"]["completion_status"]
    assert run_fact["evidence_revision"] == expected_run["evidence_revision"]
    assert run_fact["actual"]["activity_ids"] == expected_run["fact"]["actual_activity_ids"]


def test_malformed_confirmed_bucket_does_not_crash_or_confirm(tmp_path):
    db, _, _, _ = _database(tmp_path)
    readiness = build_readiness_snapshot(db, as_of=DAY)
    readiness["freshness"]["confirmed_today"].append({"invalid": "key"})
    assert _evidence(readiness)["freshness"] == "unknown"
