"""Regression coverage for issue #529 parent-session identity handoff."""
from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timedelta

import pytest

from api.planning_service import (
    confirm_coach_constraint_mutation,
    preview_coach_constraint_mutation,
)
from data.database import Database
from models.plan_actual_reconciliation import MATCH_RULE_VERSION, build_reconciliation
from models.planning_checkpoints import (
    build_planning_checkpoint,
    restore_goal_plan_from_checkpoint,
)
from models.session_identity import ensure_session_identities
from services.reconciliation import reconciliation_at


DAY = date(2026, 8, 31)
DAY_ISO = DAY.isoformat()
ACTIVITY_ID = "issue-529-bike-actual"


def _session(sport: str, role: str, tss: float) -> dict:
    return {
        "sport": sport,
        "sport_label": sport,
        "session_role": role,
        "session_focus": f"{role} {sport}",
        "total_tss": tss,
        "duration_minutes": int(round(tss)),
        "template_key": f"manual:base:{role}:{sport}",
        "materialization_status": "materialized",
        "materialized_steps": [{"name": f"{sport} work"}],
        "definition_snapshot": {"template_key": f"manual:base:{role}:{sport}"},
    }


def _plan(*sessions: dict) -> dict:
    total = round(sum(float(session["total_tss"]) for session in sessions), 1)
    parts = {
        sport: round(
            sum(
                float(session["total_tss"])
                for session in sessions
                if session["sport"] == sport
            ),
            1,
        )
        for sport in ("bike", "run", "swim")
    }
    primary = sessions[0]
    return ensure_session_identities(
        {
            "goal_type": "Триатлон",
            "distance": "Олимпийка",
            "daily_plan": [(datetime.combine(DAY, datetime.min.time()), total, parts)],
            "session_templates": [
                {
                    "date": DAY_ISO,
                    "week_index": 0,
                    "day_index": 0,
                    "phase": "Base",
                    "session_role": primary["session_role"],
                    "session_focus": primary["session_focus"],
                    "sport": primary["sport"],
                    "sport_label": primary["sport_label"],
                    "duration_minutes": sum(
                        int(session["duration_minutes"])
                        for session in sessions
                    ),
                    "sessions": [deepcopy(session) for session in sessions],
                }
            ],
            "weekly_summary": [
                {
                    "week_start": DAY_ISO,
                    "phase": "Base",
                    "weekly_tss": int(round(total)),
                    **parts,
                }
            ],
            "weekly_tss_plan": [int(round(total))],
            "base_weekly_tss_plan": [int(round(total))],
            "constraint_summary": {},
        }
    )


def _activity() -> dict:
    return {
        "activity_id": ACTIVITY_ID,
        "date": DAY_ISO,
        "started_at_utc": f"{DAY_ISO}T06:00:00Z",
        "sport": "bike",
        "duration_minutes": 60.0,
        "activity_name": "Confirmed bike",
        "tss": 60.0,
    }


def _confirmed_ledger(
    session_id: str,
    *,
    sport: str = "bike",
    session_date: str = DAY_ISO,
    match_method: str = "user_confirmed",
    match_revision_id: int = 41,
) -> dict:
    return {
        "id": match_revision_id,
        "fingerprint": f"issue-529-confirmed-{session_id}",
        "target_key": f"session:{session_id}",
        "session_id": session_id,
        "base_checkpoint_id": 1,
        "session_date": session_date,
        "match_status": "matched",
        "match_method": match_method,
        "confidence": 1.0,
        "planned_snapshot": {"sport": sport, "role": "quality", "tss": 60.0},
        "actual_activity_ids": [ACTIVITY_ID],
        "actual_snapshot": {"sport": "bike", "role": "quality", "tss": 60.0},
        "evidence": ["athlete confirmed the bike"],
        "rule_version": MATCH_RULE_VERSION,
    }


def _replacement_plan() -> tuple[dict, str, str]:
    original = _plan(_session("bike", "quality", 60.0))
    old_id = original["session_templates"][0]["sessions"][0]["session_id"]
    changed = deepcopy(original)
    changed["daily_plan"][0] = (
        datetime.combine(DAY, datetime.min.time()),
        45.0,
        {"bike": 45.0, "run": 0.0, "swim": 0.0},
    )
    changed["session_templates"][0]["sessions"][0]["total_tss"] = 45.0
    changed["session_templates"][0]["sessions"][0]["duration_minutes"] = 45
    changed["session_templates"][0]["duration_minutes"] = 45
    changed["weekly_summary"][0].update({"weekly_tss": 45, "bike": 45.0})
    changed["weekly_tss_plan"] = [45]
    current = ensure_session_identities(changed, previous_goal_plan=original)
    current_session = current["session_templates"][0]["sessions"][0]
    new_id = current_session["session_id"]
    assert new_id != old_id
    assert current_session["replaces_session_id"] == old_id
    return current, old_id, new_id


def test_sport_scoped_constraint_persistence_keeps_confirmed_survivor_matched(
    tmp_path,
) -> None:
    db = Database(str(tmp_path / "issue-529-writer.db"))
    original = _plan(
        _session("bike", "quality", 60.0),
        _session("swim", "easy", 30.0),
    )
    first = db.save_planning_checkpoint(build_planning_checkpoint(original))
    restored = restore_goal_plan_from_checkpoint(first)
    assert restored is not None
    bike_id = restored["session_templates"][0]["sessions"][0]["session_id"]
    db.save_activities([_activity()])
    db.save_plan_actual_match(
        {
            **_confirmed_ledger(bike_id),
            "base_checkpoint_id": int(first["id"]),
        }
    )

    proposal = preview_coach_constraint_mutation(
        db,
        action="create_plan_constraint",
        params={
            "date": DAY_ISO,
            "kind": "unavailable",
            "source": "coach",
            "note": "pool closed",
            "sport": "swim",
            "base_checkpoint_id": int(first["id"]),
        },
    )
    applied = confirm_coach_constraint_mutation(
        db,
        action="create_plan_constraint",
        params=proposal["params"],
        preview_fingerprint=proposal["preview"]["preview_fingerprint"],
    )

    latest = db.get_planning_checkpoint(int(applied["applied_checkpoint_id"]))
    updated = restore_goal_plan_from_checkpoint(latest)
    assert updated is not None
    survivors = updated["session_templates"][0]["sessions"]
    assert [session["sport"] for session in survivors] == ["bike"]
    assert survivors[0]["session_id"] == bike_id
    assert not survivors[0].get("replaces_session_id")

    result = reconciliation_at(
        db,
        weeks=1,
        as_of=DAY_ISO,
        include_provider=False,
    )
    row = next(item for item in result["rows"] if item["session_id"] == bike_id)
    assert row["match_status"] == "matched"
    assert row["match_method"] == "user_confirmed"
    assert row["actual_activity_ids"] == [ACTIVITY_ID]
    assert ACTIVITY_ID not in {
        item["activity_id"] for item in result["unplanned_activities"]
    }


@pytest.mark.parametrize("match_method", ["user_confirmed", "admin_resolve"])
def test_valid_parent_replacement_inherits_confirmed_match_without_rewriting_target(
    match_method: str,
) -> None:
    current, old_id, new_id = _replacement_plan()

    result = build_reconciliation(
        current,
        [_activity()],
        as_of=DAY,
        weeks=1,
        base_checkpoint_id=2,
        ledger_rows=[_confirmed_ledger(old_id, match_method=match_method)],
    )

    row = next(item for item in result["rows"] if item["session_id"] == new_id)
    assert row["target_key"] == f"session:{new_id}"
    assert row["match_status"] == "matched"
    assert row["match_method"] == match_method
    assert row["actual_activity_ids"] == [ACTIVITY_ID]
    assert ACTIVITY_ID not in {
        item["activity_id"] for item in result["unplanned_activities"]
    }


def test_current_session_ledger_wins_over_confirmed_predecessor() -> None:
    current, old_id, new_id = _replacement_plan()
    current_decision = {
        **_confirmed_ledger(new_id),
        "fingerprint": "issue-529-current-unmatched",
        "match_status": "unmatched",
        "match_method": "user_unmatched",
        "confidence": 0.0,
        "actual_activity_ids": [],
        "actual_snapshot": {},
    }

    result = build_reconciliation(
        current,
        [_activity()],
        as_of=DAY,
        weeks=1,
        base_checkpoint_id=2,
        ledger_rows=[_confirmed_ledger(old_id), current_decision],
    )

    row = next(item for item in result["rows"] if item["session_id"] == new_id)
    assert row["match_method"] == "user_unmatched"
    assert row["match_status"] == "unmatched"
    assert row["actual_activity_ids"] == []
    assert [item["activity_id"] for item in row["candidate_activities"]] == [
        ACTIVITY_ID
    ]


def test_unmatched_admin_predecessor_does_not_suppress_heuristic_match() -> None:
    current, old_id, new_id = _replacement_plan()
    admin_cleared = {
        **_confirmed_ledger(old_id, match_method="admin_resolve"),
        "match_status": "unmatched",
        "actual_activity_ids": [],
        "actual_snapshot": {},
    }

    result = build_reconciliation(
        current,
        [_activity()],
        as_of=DAY,
        weeks=1,
        base_checkpoint_id=2,
        ledger_rows=[admin_cleared],
    )

    row = next(item for item in result["rows"] if item["session_id"] == new_id)
    assert row["match_status"] == "matched"
    assert row["match_method"] == "date_sport_heuristic"
    assert row["actual_activity_ids"] == [ACTIVITY_ID]


def test_current_replacement_decision_can_reselect_predecessor_activity(tmp_path) -> None:
    from api.planning_service import record_plan_actual_match

    db = Database(str(tmp_path / "issue-529-reselect.db"))
    current, old_id, new_id = _replacement_plan()
    checkpoint = db.save_planning_checkpoint(build_planning_checkpoint(current))
    db.save_activities([_activity()])
    predecessor = db.save_plan_actual_match(
        {
            **_confirmed_ledger(old_id),
            "base_checkpoint_id": int(checkpoint["id"]),
        }
    )
    unmatched = record_plan_actual_match(
        db,
        base_checkpoint_id=int(checkpoint["id"]),
        session_id=new_id,
        activity_ids=[],
        actual_role=None,
        action="unmatch",
    )
    assert unmatched["supersedes_match_id"] == predecessor["id"]
    assert db.get_plan_actual_match_for_activity(ACTIVITY_ID) is None

    reconciliation = build_reconciliation(
        current,
        [_activity()],
        as_of=DAY,
        weeks=1,
        base_checkpoint_id=int(checkpoint["id"]),
        ledger_rows=db.get_latest_plan_actual_matches(
            start_date=DAY_ISO,
            end_date=DAY_ISO,
        ),
    )
    row = next(
        item for item in reconciliation["rows"] if item["session_id"] == new_id
    )
    assert [item["activity_id"] for item in row["candidate_activities"]] == [
        ACTIVITY_ID
    ]

    saved = record_plan_actual_match(
        db,
        base_checkpoint_id=int(checkpoint["id"]),
        session_id=new_id,
        activity_ids=[ACTIVITY_ID],
        actual_role="quality",
        action="confirm",
    )

    assert saved["match_status"] == "matched"
    assert saved["actual_activity_ids"] == [ACTIVITY_ID]
    assert saved["supersedes_match_id"] == unmatched["id"]
    activity_match = db.get_plan_actual_match_for_activity(ACTIVITY_ID)
    assert activity_match is not None
    assert activity_match["id"] == saved["id"]
    assert activity_match["session_id"] == new_id


def test_inherited_revision_reaches_feedback_and_recovery_evidence(tmp_path) -> None:
    from api.session_feedback import (
        _feedback_evidence_for_session,
        _match_revision_id_for_prompt,
    )
    from services.recovery_analytics import refresh_recovery_episodes

    db = Database(str(tmp_path / "issue-529-revision.db"))
    current, old_id, new_id = _replacement_plan()
    checkpoint = db.save_planning_checkpoint(build_planning_checkpoint(current))
    db.save_activities([_activity()])
    predecessor = db.save_plan_actual_match(
        {
            **_confirmed_ledger(old_id),
            "base_checkpoint_id": int(checkpoint["id"]),
        }
    )

    reconciliation = reconciliation_at(
        db,
        weeks=1,
        as_of=DAY_ISO,
        include_provider=False,
    )
    row = next(
        item for item in reconciliation["rows"] if item["session_id"] == new_id
    )
    assert _match_revision_id_for_prompt(db, row, new_id) == predecessor["id"]

    evidence = _feedback_evidence_for_session(db, new_id, as_of=DAY)
    assert evidence["match_revision_id"] == predecessor["id"]

    refreshed = refresh_recovery_episodes(
        db,
        as_of=DAY + timedelta(days=3),
        target_session_ids=[new_id],
    )
    assert refreshed["created"] == 1
    episode = next(
        item
        for item in db.get_recovery_episodes(latest_only=True)
        if item["session_id"] == new_id
    )
    assert episode["match_revision_id"] == predecessor["id"]


@pytest.mark.parametrize(
    ("sport", "session_date"),
    [("run", DAY_ISO), ("bike", "2026-08-30")],
)
def test_incompatible_parent_replacement_does_not_inherit_confirmed_match(
    sport: str,
    session_date: str,
) -> None:
    current, old_id, new_id = _replacement_plan()
    incompatible = _confirmed_ledger(
        old_id,
        sport=sport,
        session_date=session_date,
    )

    result = build_reconciliation(
        current,
        [_activity()],
        as_of=DAY,
        weeks=1,
        base_checkpoint_id=2,
        ledger_rows=[incompatible],
    )

    row = next(item for item in result["rows"] if item["session_id"] == new_id)
    assert row["match_status"] == "unmatched"
    assert row["actual_activity_ids"] == []
    assert ACTIVITY_ID in {
        item["activity_id"] for item in result["unplanned_activities"]
    }


def test_ambiguous_parent_replacement_claims_fail_closed() -> None:
    predecessor_id = "ats_issue_529_shared_predecessor"
    current = _plan(
        _session("bike", "quality", 45.0),
        _session("bike", "easy", 30.0),
    )
    for session in current["session_templates"][0]["sessions"]:
        session["replaces_session_id"] = predecessor_id

    result = build_reconciliation(
        current,
        [_activity()],
        as_of=DAY,
        weeks=1,
        base_checkpoint_id=2,
        ledger_rows=[_confirmed_ledger(predecessor_id)],
    )

    assert all(row["match_status"] == "unmatched" for row in result["rows"])
    assert all(row["actual_activity_ids"] == [] for row in result["rows"])
    assert ACTIVITY_ID in {
        item["activity_id"] for item in result["unplanned_activities"]
    }
