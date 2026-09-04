"""Regression coverage for issue #531 explicit unplanned activity correction."""
from __future__ import annotations

from pathlib import Path

import pytest

from api.planning_service import record_plan_actual_match
from data.database import Database
from models.planning_checkpoints import build_planning_checkpoint
from services.reconciliation import reconciliation_at
from tests.smoke.test_issue_529_match_handoff import (
    ACTIVITY_ID,
    DAY_ISO,
    _activity,
    _confirmed_ledger,
    _plan,
    _session,
)


def _current_db(tmp_path, *sessions: dict) -> tuple[Database, dict, int]:
    db = Database(str(tmp_path / "issue-531.db"))
    plan = _plan(*(sessions or (_session("bike", "quality", 60.0),)))
    checkpoint = db.save_planning_checkpoint(build_planning_checkpoint(plan))
    return db, plan, int(checkpoint["id"])


def _session_ids(plan: dict) -> list[str]:
    return [
        str(item["session_id"])
        for item in plan["session_templates"][0]["sessions"]
    ]


def _save_stale_match(
    db: Database,
    checkpoint_id: int,
    *,
    stale_session_id: str = "ats_issue_531_inactive_history",
    activity_ids: list[str] | None = None,
) -> dict:
    selected = list(activity_ids or [ACTIVITY_ID])
    return db.save_plan_actual_match(
        {
            **_confirmed_ledger(stale_session_id),
            "fingerprint": f"issue-531-stale-{stale_session_id}",
            "base_checkpoint_id": checkpoint_id,
            "actual_activity_ids": selected,
            "actual_snapshot": {
                "sport": "bike",
                "role": "quality",
                "tss": 60.0,
            },
        }
    )


def test_explicit_confirmation_reassigns_complete_inactive_historical_match(
    tmp_path,
) -> None:
    db, plan, checkpoint_id = _current_db(tmp_path)
    current_session_id = _session_ids(plan)[0]
    db.save_activities([_activity()])
    stale = _save_stale_match(db, checkpoint_id)

    saved = record_plan_actual_match(
        db,
        base_checkpoint_id=checkpoint_id,
        session_id=current_session_id,
        activity_ids=[ACTIVITY_ID],
        actual_role="quality",
        action="confirm",
    )

    assert saved["target_key"] == f"session:{current_session_id}"
    assert saved["session_id"] == current_session_id
    assert saved["match_method"] == "user_confirmed"
    assert saved["actual_activity_ids"] == [ACTIVITY_ID]
    assert saved["supersedes_match_id"] == stale["id"]

    result = reconciliation_at(
        db,
        weeks=1,
        as_of=DAY_ISO,
        include_provider=False,
    )
    row = next(
        item for item in result["rows"] if item["session_id"] == current_session_id
    )
    assert row["match_status"] == "matched"
    assert row["actual_activity_ids"] == [ACTIVITY_ID]
    assert ACTIVITY_ID not in {
        item["activity_id"] for item in result["unplanned_activities"]
    }
    effective = db.get_plan_actual_match_for_activity(ACTIVITY_ID)
    assert effective is not None
    assert effective["id"] == saved["id"]


def test_reassignment_retry_is_idempotent(tmp_path) -> None:
    db, plan, checkpoint_id = _current_db(tmp_path)
    current_session_id = _session_ids(plan)[0]
    db.save_activities([_activity()])
    _save_stale_match(db, checkpoint_id)
    request = {
        "base_checkpoint_id": checkpoint_id,
        "session_id": current_session_id,
        "activity_ids": [ACTIVITY_ID],
        "actual_role": "quality",
        "action": "confirm",
    }

    first = record_plan_actual_match(db, **request)
    second = record_plan_actual_match(db, **request)

    assert second["id"] == first["id"]
    current_rows = [
        row
        for row in db.get_latest_plan_actual_matches(
            start_date=DAY_ISO,
            end_date=DAY_ISO,
        )
        if row["target_key"] == f"session:{current_session_id}"
    ]
    assert len(current_rows) == 1


def test_active_current_session_owner_remains_a_hard_conflict(tmp_path) -> None:
    db, plan, checkpoint_id = _current_db(
        tmp_path,
        _session("bike", "quality", 60.0),
        _session("run", "easy", 30.0),
    )
    target_session_id, owner_session_id = _session_ids(plan)
    db.save_activities([_activity()])
    db.save_plan_actual_match(
        {
            **_confirmed_ledger(owner_session_id, sport="run"),
            "fingerprint": "issue-531-active-owner",
            "base_checkpoint_id": checkpoint_id,
        }
    )

    with pytest.raises(ValueError, match="already matched"):
        record_plan_actual_match(
            db,
            base_checkpoint_id=checkpoint_id,
            session_id=target_session_id,
            activity_ids=[ACTIVITY_ID],
            actual_role="quality",
            action="confirm",
        )


def test_partial_stale_group_reassignment_fails_closed(tmp_path) -> None:
    db, plan, checkpoint_id = _current_db(tmp_path)
    current_session_id = _session_ids(plan)[0]
    second_activity_id = "issue-531-second-activity"
    second = {
        **_activity(),
        "activity_id": second_activity_id,
        "started_at_utc": f"{DAY_ISO}T08:00:00Z",
        "activity_name": "Second historical leg",
        "tss": 20.0,
    }
    db.save_activities([_activity(), second])
    _save_stale_match(
        db,
        checkpoint_id,
        activity_ids=[ACTIVITY_ID, second_activity_id],
    )

    with pytest.raises(ValueError, match="reassigned together"):
        record_plan_actual_match(
            db,
            base_checkpoint_id=checkpoint_id,
            session_id=current_session_id,
            activity_ids=[ACTIVITY_ID],
            actual_role="quality",
            action="confirm",
        )


def test_multiple_inactive_historical_owners_fail_closed(tmp_path) -> None:
    db, plan, checkpoint_id = _current_db(tmp_path)
    current_session_id = _session_ids(plan)[0]
    second_activity_id = "issue-531-other-owner-activity"
    second = {
        **_activity(),
        "activity_id": second_activity_id,
        "started_at_utc": f"{DAY_ISO}T09:00:00Z",
        "activity_name": "Other stale owner activity",
        "tss": 18.0,
    }
    db.save_activities([_activity(), second])
    _save_stale_match(
        db,
        checkpoint_id,
        stale_session_id="ats_issue_531_old_a",
        activity_ids=[ACTIVITY_ID],
    )
    _save_stale_match(
        db,
        checkpoint_id,
        stale_session_id="ats_issue_531_old_b",
        activity_ids=[second_activity_id],
    )

    with pytest.raises(ValueError, match="multiple historical matches"):
        record_plan_actual_match(
            db,
            base_checkpoint_id=checkpoint_id,
            session_id=current_session_id,
            activity_ids=[ACTIVITY_ID, second_activity_id],
            actual_role="quality",
            action="confirm",
        )


def test_unplanned_web_control_requires_exact_same_date_target_and_role() -> None:
    source = Path("web/app/planning/page.tsx").read_text(encoding="utf-8")

    assert "function UnplannedMatchControl" in source
    assert "row.date === activity.date" in source
    assert 'row.match_status !== "matched"' in source
    assert "[activity.activity_id]" in source
    assert "Роль факта для" in source
    assert "Нет несопоставленной плановой сессии на эту дату" in source
    assert "Сопоставить" in source
