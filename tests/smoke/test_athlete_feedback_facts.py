"""BDD/TDD contract for the M0 durable athlete feedback fact ledger."""
from __future__ import annotations

import pytest

from data.database import Database
from models.post_workout_feedback import FEEDBACK_RULE_VERSION


pytestmark = pytest.mark.smoke


def _feedback_payload(
    fingerprint: str = "feedback-fact-1",
    *,
    quality: int | None = 5,
    rpe: int | None = 8,
    status: str = "active",
) -> dict:
    return {
        "fingerprint": fingerprint,
        "target_key": "session:ats_feedback_fact",
        "session_id": "ats_feedback_fact",
        "parent_session_id": None,
        "match_revision_id": 121,
        "match_snapshot": {
            "planned": {
                "session_id": "ats_feedback_fact",
                "date": "2026-08-17",
                "sport": "bike",
                "tss": 55.0,
                "duration_minutes": 40,
            },
            "match_status": "matched",
            "match_method": "user_confirmed",
            "confidence": 1.0,
            "adherence": "exact",
            "actual_activities": [{"activity_id": "ride-fact-1", "tss": 28.6}],
        },
        "actual_activity_ids": ["ride-fact-1"],
        "completion_status": "completed" if status == "active" else "unknown",
        "completion_pct": 100 if status == "active" else None,
        "completion_pct_source": "athlete_entered" if status == "active" else None,
        "session_rpe_1_10": rpe if status == "active" else None,
        "quality_rating_1_5": quality if status == "active" else None,
        "note": "Не копировать эту заметку в athlete fact",
        "source": "user_web",
        "session_end_at_utc": "2026-08-17T08:40:00Z",
        "session_end_provenance": "started_at_utc_plus_duration_minutes",
        "status": status,
        "rule_version": FEEDBACK_RULE_VERSION,
        "submitted_at": "2026-08-18T06:00:00Z",
    }


def _bike_activity() -> dict:
    return {
        "activity_id": "ride-fact-1",
        "date": "2026-08-17",
        "started_at_utc": "2026-08-17T08:00:00Z",
        "sport": "bike",
        "duration_minutes": 40,
        "tss_method": "power_tss",
        "tss": 28.6,
        "tss_ftp_used": 172.0,
    }


def test_feedback_revision_creates_durable_fact_with_source_provenance(tmp_path):
    db_path = tmp_path / "feedback-facts.db"
    db = Database(str(db_path))

    saved = db.save_session_feedback(_feedback_payload())
    fact = Database(str(db_path)).get_latest_athlete_feedback_fact(
        "ats_feedback_fact"
    )

    assert saved["created"] is True
    assert fact["fact_type"] == "session_feedback"
    assert fact["status"] == "active"
    assert fact["feedback_id"] == saved["feedback"]["id"]
    assert fact["value"] == {
        "completion_pct": 100,
        "completion_status": "completed",
        "quality_rating_1_5": 5,
        "session_rpe_1_10": 8,
    }
    assert fact["provenance"] == {
        "label": "athlete-entered",
        "owner": "athlete",
        "source": "session_feedback",
        "source_feedback_fingerprint": "feedback-fact-1",
        "source_feedback_id": saved["feedback"]["id"],
        "source_feedback_revision": 1,
        "source_rule_version": FEEDBACK_RULE_VERSION,
        "match_revision_id": 121,
        "session_end_at_utc": "2026-08-17T08:40:00Z",
        "session_end_provenance": "started_at_utc_plus_duration_minutes",
    }
    assert fact["value"].get("note") is None


def test_fact_retry_is_idempotent_and_correction_preserves_lineage(tmp_path):
    db = Database(str(tmp_path / "feedback-facts-lineage.db"))

    first = db.save_session_feedback(_feedback_payload())
    retry = db.save_session_feedback({**_feedback_payload(), "quality_rating_1_5": 1})
    correction = db.save_session_feedback(
        {
            **_feedback_payload("feedback-fact-2", quality=4, rpe=7),
            "supersedes_feedback_id": first["feedback"]["id"],
            "expected_latest_feedback_id": first["feedback"]["id"],
        }
    )

    assert retry["created"] is False
    history = db.get_athlete_feedback_fact_history("ats_feedback_fact")
    assert len(history) == 2
    assert [row["revision"] for row in history] == [1, 2]
    assert history[1]["supersedes_fact_id"] == history[0]["id"]
    assert history[1]["feedback_id"] == correction["feedback"]["id"]
    assert history[1]["value"]["session_rpe_1_10"] == 7


def test_tombstone_withdraws_latest_fact_without_rewriting_history(tmp_path):
    db = Database(str(tmp_path / "feedback-facts-tombstone.db"))

    first = db.save_session_feedback(_feedback_payload())
    tombstone = db.save_session_feedback(
        {
            **_feedback_payload("feedback-fact-tombstone", status="tombstone"),
            "supersedes_feedback_id": first["feedback"]["id"],
            "expected_latest_feedback_id": first["feedback"]["id"],
        }
    )

    latest = db.get_latest_athlete_feedback_fact("ats_feedback_fact")
    history = db.get_athlete_feedback_fact_history("ats_feedback_fact")
    assert latest["status"] == "withdrawn"
    assert latest["feedback_id"] == tombstone["feedback"]["id"]
    assert latest["value"]["session_rpe_1_10"] is None
    assert latest["value"]["quality_rating_1_5"] is None
    assert latest["provenance"]["source_feedback_revision"] == 2
    assert len(history) == 2
    assert history[0]["status"] == "active"


def test_feedback_fact_does_not_change_activity_tss(tmp_path):
    db = Database(str(tmp_path / "feedback-facts-no-tss-effect.db"))
    db.save_activities([_bike_activity()])
    before = db.get_activity("ride-fact-1")

    db.save_session_feedback(_feedback_payload())

    after = db.get_activity("ride-fact-1")
    assert before["tss"] == 28.6
    assert after["tss"] == before["tss"]
    assert after["tss_method"] == before["tss_method"]
    assert db.get_database_stats()["athlete_feedback_facts"] == 1


def test_feedback_and_fact_roll_back_together(tmp_path, monkeypatch):
    db = Database(str(tmp_path / "feedback-facts-atomicity.db"))

    def fail_append(*_args, **_kwargs):
        raise RuntimeError("fact write failed")

    monkeypatch.setattr(
        "data.database.AthleteFeedbackFactStore.append_from_feedback", fail_append
    )

    with pytest.raises(RuntimeError, match="fact write failed"):
        db.save_session_feedback(_feedback_payload())

    assert db.get_session_feedback_history("ats_feedback_fact") == []
    assert db.get_athlete_feedback_fact_history("ats_feedback_fact") == []
