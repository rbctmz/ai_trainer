"""Fact-only directional drift coverage for coach decisions (issue #468)."""
from __future__ import annotations

from datetime import datetime
import sqlite3

import pytest

from data.database import Database
from services.coach_drift import build_coach_drift_report


def _checkpoint(db: Database, weekly_tss: list[int], *, parent_id: int | None = None) -> int:
    saved = db.save_planning_checkpoint(
        {
            "goal_type": "Триатлон",
            "distance": "Olympic",
            "weeks_to_race": len(weekly_tss),
            "weekly_tss_plan": weekly_tss,
            "checkpoint_parent_id": parent_id,
            "goal_plan_snapshot": {
                "weekly_tss_plan": weekly_tss,
                "checkpoint_parent_id": parent_id,
            },
        }
    )
    return int(saved["id"])


def _linked_approved_pair(
    db: Database,
    *,
    decision_type: str,
    before: list[int],
    after: list[int],
    event_id: str,
) -> tuple[dict, dict]:
    base_id = _checkpoint(db, before)
    applied_id = _checkpoint(db, after, parent_id=base_id)
    decision = db.save_coach_decision(
        decision_type,
        f"{decision_type} fixture",
        decision_event_id=event_id,
    )
    proposal = db.save_coach_proposal(
        action="adjust_plan",
        params={"base_checkpoint_id": base_id},
        preview={"status": "proposal"},
        decision_event_id=event_id,
        source="coach_tool",
    )
    proposal = db.update_coach_proposal_status(
        proposal["id"],
        "approved",
        result={
            "base_checkpoint_id": base_id,
            "applied_checkpoint_id": applied_id,
        },
    )
    return decision, proposal


def _report(db: Database) -> dict:
    return build_coach_drift_report(
        db.get_coach_decisions(days=36500),
        db.get_coach_proposals(days=36500),
        db.get_planning_checkpoint,
    )


def test_drift_report_empty_history_is_honest_data_gap(tmp_path):
    db = Database(str(tmp_path / "empty.db"))

    report = _report(db)

    assert report == {
        "state": "data_gap",
        "decision_count": 0,
        "linked_proposal_count": 0,
        "compared_count": 0,
        "no_change_count": 0,
        "mismatch_count": 0,
        "mismatches": [],
        "data_gap_count": 0,
        "data_gaps": [],
    }


def test_database_migrates_legacy_coach_lineage_columns_additively(tmp_path):
    db_path = tmp_path / "legacy-schema.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE coach_decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                decision_type TEXT NOT NULL,
                reason TEXT NOT NULL,
                workout_id TEXT,
                chat_id TEXT,
                message_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE coach_proposals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                action TEXT NOT NULL,
                status TEXT NOT NULL,
                params_json TEXT NOT NULL,
                preview_json TEXT NOT NULL,
                result_json TEXT,
                error TEXT,
                chat_id TEXT,
                message_id TEXT,
                resolved_at TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

    Database(str(db_path))

    with sqlite3.connect(db_path) as conn:
        decision_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(coach_decisions)")
        }
        proposal_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(coach_proposals)")
        }
    assert "decision_event_id" in decision_columns
    assert {
        "decision_event_id",
        "base_checkpoint_id",
        "applied_checkpoint_id",
        "rollback_checkpoint_id",
    } <= proposal_columns


def test_proposal_checkpoint_lineage_survives_rollback_result_replacement(tmp_path):
    db = Database(str(tmp_path / "rollback-lineage.db"))
    proposal = db.save_coach_proposal(
        action="recovery_replan",
        params={"base_checkpoint_id": 7},
        preview={"variants": [{"kind": "downgrade_today"}]},
        decision_event_id="event-rollback",
        source="coach_tool",
    )
    approved = db.update_coach_proposal_status(
        proposal["id"],
        "approved",
        result={
            "base_checkpoint_id": 7,
            "applied_checkpoint_id": 8,
            "rollback_checkpoint_id": 7,
            "selected_kind": "downgrade_today",
        },
    )
    rolled_back = db.update_coach_proposal_status(
        proposal["id"],
        "rolled_back",
        result={"plan_id": "9", "replaced_checkpoint_id": 8},
    )

    assert approved["base_checkpoint_id"] == 7
    assert approved["applied_checkpoint_id"] == 8
    assert approved["rollback_checkpoint_id"] == 7
    assert rolled_back["base_checkpoint_id"] == 7
    assert rolled_back["applied_checkpoint_id"] == 8
    assert rolled_back["rollback_checkpoint_id"] == 7


def test_drift_report_never_joins_temporally_adjacent_legacy_rows(tmp_path):
    db = Database(str(tmp_path / "legacy.db"))
    timestamp = datetime.now().replace(microsecond=0).isoformat()
    db.save_coach_decision("Recovery", "Legacy decision", date=timestamp)
    proposal = db.save_coach_proposal(
        action="adjust_plan",
        params={"base_checkpoint_id": 1},
        preview={"status": "proposal"},
        date=timestamp,
    )
    db.update_coach_proposal_status(
        proposal["id"],
        "approved",
        result={"base_checkpoint_id": 1, "applied_checkpoint_id": 2},
    )

    report = _report(db)

    assert report["compared_count"] == 0
    assert report["mismatch_count"] == 0
    assert report["state"] == "data_gap"
    assert report["data_gaps"][0]["reason"] == "unlinked_decision"
    assert report["data_gaps"][1]["reason"] == "unlinked_proposal"


def test_drift_report_exposes_proposal_without_completed_decision(tmp_path):
    db = Database(str(tmp_path / "orphan-proposal.db"))
    proposal = db.save_coach_proposal(
        action="adjust_plan",
        params={"base_checkpoint_id": 1},
        preview={"status": "proposal"},
        decision_event_id="event-provider-failed-after-proposal",
        source="coach_tool",
    )

    report = _report(db)

    assert report["state"] == "data_gap"
    assert report["decision_count"] == 0
    assert report["mismatch_count"] == 0
    assert report["data_gaps"] == [
        {
            "decision_id": None,
            "decision_type": None,
            "proposal_id": proposal["id"],
            "action": "adjust_plan",
            "reason": "proposal_without_decision",
            "evidence": {"proposal_status": "pending"},
        }
    ]


def test_drift_report_does_not_attribute_recovery_gate_to_final_recommendation(tmp_path):
    db = Database(str(tmp_path / "recovery-origin.db"))
    event_id = "event-recovery-gate"
    db.save_coach_decision("Push", "Push fixture", decision_event_id=event_id)
    proposal = db.save_coach_proposal(
        action="recovery_replan",
        params={"base_checkpoint_id": 1},
        preview={"status": "proposal"},
        decision_event_id=event_id,
        source="recovery_replan",
    )
    db.update_coach_proposal_status(
        proposal["id"],
        "approved",
        result={"base_checkpoint_id": 1, "applied_checkpoint_id": 2},
    )

    report = _report(db)

    assert report["compared_count"] == 0
    assert report["mismatch_count"] == 0
    assert report["data_gaps"][0]["reason"] == "unattributed_proposal"
    assert report["data_gaps"][0]["evidence"] == {
        "proposal_source": "recovery_replan"
    }


@pytest.mark.parametrize(
    ("decision_type", "before", "after", "expected_mismatch"),
    [
        ("Push", [100, 100], [80, 90], True),
        ("Push", [100, 100], [110, 110], False),
        ("Moderate", [100, 100], [110, 110], True),
        ("Moderate", [100, 100], [90, 90], False),
        ("Recovery", [100, 100], [110, 110], True),
        ("Recovery", [100, 100], [90, 90], False),
        ("Monitor", [100, 100], [110, 110], True),
        ("Monitor", [100, 100], [100, 100], False),
    ],
)
def test_drift_report_uses_conservative_direction_matrix(
    tmp_path,
    decision_type,
    before,
    after,
    expected_mismatch,
):
    db = Database(str(tmp_path / f"{decision_type}-{before[0]}-{after[0]}.db"))
    decision, proposal = _linked_approved_pair(
        db,
        decision_type=decision_type,
        before=before,
        after=after,
        event_id=f"event-{decision_type}",
    )

    report = _report(db)

    assert report["state"] == "ready"
    assert report["compared_count"] == 1
    assert report["mismatch_count"] == int(expected_mismatch)
    if expected_mismatch:
        finding = report["mismatches"][0]
        assert finding["decision_id"] == decision["id"]
        assert finding["decision_type"] == decision_type
        assert finding["proposal_id"] == proposal["id"]
        assert finding["base_checkpoint_id"] == proposal["base_checkpoint_id"]
        assert finding["applied_checkpoint_id"] == proposal["applied_checkpoint_id"]
        assert finding["total_tss_delta"] == sum(after) - sum(before)
        assert finding["actual_direction"] in {"increase", "decrease"}
        assert "interpretation" not in finding
        assert "cause" not in finding
    else:
        assert report["mismatches"] == []


@pytest.mark.parametrize("status", ["pending", "rejected", "failed", "rolled_back"])
def test_drift_report_does_not_claim_non_active_proposal_as_mutation(tmp_path, status):
    db = Database(str(tmp_path / f"status-{status}.db"))
    event_id = f"event-{status}"
    db.save_coach_decision("Recovery", "Recovery fixture", decision_event_id=event_id)
    proposal = db.save_coach_proposal(
        action="adjust_plan",
        params={"base_checkpoint_id": 1},
        preview={"status": "proposal"},
        decision_event_id=event_id,
        source="coach_tool",
    )
    if status != "pending":
        db.update_coach_proposal_status(
            proposal["id"],
            status,
            result={"base_checkpoint_id": 1, "applied_checkpoint_id": 2},
        )

    report = _report(db)

    assert report["compared_count"] == 0
    assert report["mismatch_count"] == 0
    assert report["state"] == "data_gap"


def test_drift_report_treats_approved_recovery_keep_as_verified_no_change(tmp_path):
    db = Database(str(tmp_path / "keep.db"))
    event_id = "event-keep"
    db.save_coach_decision("Recovery", "Recovery fixture", decision_event_id=event_id)
    proposal = db.save_coach_proposal(
        action="recovery_replan",
        params={"base_checkpoint_id": 0},
        preview={"variants": [{"kind": "keep"}]},
        decision_event_id=event_id,
        source="coach_tool",
    )
    db.update_coach_proposal_status(
        proposal["id"],
        "approved",
        result={"selected_kind": "keep", "plan_id": None},
    )

    report = _report(db)

    assert report["state"] == "data_gap"
    assert report["compared_count"] == 0
    assert report["no_change_count"] == 1
    assert report["mismatch_count"] == 0


def test_drift_report_fails_closed_on_wrong_checkpoint_parent(tmp_path):
    db = Database(str(tmp_path / "wrong-parent.db"))
    expected_base = _checkpoint(db, [100])
    other_base = _checkpoint(db, [200])
    applied = _checkpoint(db, [250], parent_id=other_base)
    event_id = "event-wrong-parent"
    db.save_coach_decision("Recovery", "Recovery fixture", decision_event_id=event_id)
    proposal = db.save_coach_proposal(
        action="adjust_plan",
        params={"base_checkpoint_id": expected_base},
        preview={"status": "proposal"},
        decision_event_id=event_id,
        source="coach_tool",
    )
    db.update_coach_proposal_status(
        proposal["id"],
        "approved",
        result={
            "base_checkpoint_id": expected_base,
            "applied_checkpoint_id": applied,
        },
    )

    report = _report(db)

    assert report["state"] == "data_gap"
    assert report["compared_count"] == 0
    assert report["mismatch_count"] == 0
    assert report["data_gaps"][0]["reason"] == "checkpoint_parent_mismatch"


def test_drift_report_fails_closed_when_result_base_disagrees(tmp_path):
    db = Database(str(tmp_path / "result-base-mismatch.db"))
    base = _checkpoint(db, [100])
    applied = _checkpoint(db, [120], parent_id=base)
    event_id = "event-result-base-mismatch"
    db.save_coach_decision("Recovery", "Recovery fixture", decision_event_id=event_id)
    proposal = db.save_coach_proposal(
        action="adjust_plan",
        params={"base_checkpoint_id": base},
        preview={"status": "proposal"},
        decision_event_id=event_id,
        source="coach_tool",
    )
    db.update_coach_proposal_status(
        proposal["id"],
        "approved",
        result={"base_checkpoint_id": base + 100, "applied_checkpoint_id": applied},
    )

    report = _report(db)

    assert report["compared_count"] == 0
    assert report["mismatch_count"] == 0
    assert report["data_gaps"][0]["reason"] == "result_base_mismatch"


def test_drift_report_fails_closed_on_different_plan_horizons(tmp_path):
    db = Database(str(tmp_path / "different-horizon.db"))
    decision, _proposal = _linked_approved_pair(
        db,
        decision_type="Recovery",
        before=[100, 100],
        after=[250],
        event_id="event-different-horizon",
    )

    report = _report(db)

    assert report["state"] == "data_gap"
    assert report["compared_count"] == 0
    assert report["mismatch_count"] == 0
    gap = report["data_gaps"][0]
    assert gap["decision_id"] == decision["id"]
    assert gap["reason"] == "non_comparable_horizon"
    assert gap["evidence"]["weeks_before"] == 2
    assert gap["evidence"]["weeks_after"] == 1


def test_drift_report_keeps_multiple_proposals_in_one_event(tmp_path):
    db = Database(str(tmp_path / "multiple.db"))
    event_id = "event-multiple"
    db.save_coach_decision("Recovery", "Recovery fixture", decision_event_id=event_id)
    for index, after in enumerate(([90], [120]), start=1):
        base = _checkpoint(db, [100])
        applied = _checkpoint(db, list(after), parent_id=base)
        proposal = db.save_coach_proposal(
            action="adjust_plan",
            params={"base_checkpoint_id": base, "index": index},
            preview={"status": "proposal"},
            decision_event_id=event_id,
            source="coach_tool",
        )
        db.update_coach_proposal_status(
            proposal["id"],
            "approved",
            result={"base_checkpoint_id": base, "applied_checkpoint_id": applied},
        )

    report = _report(db)

    assert report["linked_proposal_count"] == 2
    assert report["compared_count"] == 2
    assert report["mismatch_count"] == 1


def test_decisions_api_exposes_additive_drift_report(tmp_path):
    from api.routers.decisions import list_decisions

    db = Database(str(tmp_path / "api.db"))

    payload = list_decisions(db=db)

    assert payload["drift_report"]["state"] == "data_gap"
    assert payload["drift_report"]["mismatches"] == []
