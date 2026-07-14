"""End-to-end local materialization for prospective recovery episodes."""
from __future__ import annotations

from datetime import date, datetime, timezone

from data.database import Database
from models.planning_checkpoints import build_planning_checkpoint
from models.session_identity import ensure_session_identities
from services.recovery_analytics import (
    record_post_sync_recovery_state,
    refresh_recovery_episodes,
)


def _snapshot(db: Database, day: str, score: float) -> dict:
    canonical = {
        "score": score,
        "status": "ready",
        "computed_at": day,
        "as_of_date": day,
        "rule_version": "readiness_snapshot_v2",
        "confidence": 0.8,
        "stale": False,
        "is_provisional": False,
        "source_completeness": 0.8,
        "missing_inputs": [],
        "factors": [{"key": "hrv", "as_of": day, "stale_input": False}],
        "drivers": [],
        "tsb": {"ctl": 20, "atl": 25, "tsb": -5, "as_of": day},
        "input_provenance": {"as_of_date": day},
    }
    return db.save_readiness_snapshot(
        {
            "fingerprint": f"capture-{day}",
            "target_key": f"readiness:prospective:{day}",
            "capture_mode": "prospective",
            "local_date": day,
            "athlete_timezone": "Europe/Moscow",
            "observed_at_utc": f"{day}T05:00:00Z",
            "capture_run_id": f"run-{day}",
            "rule_version": "readiness_snapshot_v2",
            "score": score,
            "status": "ready",
            "confidence": 0.8,
            "as_of_date": day,
            "is_provisional": False,
            "source_completeness": 0.8,
            "stale": False,
            "eligibility_status": "eligible",
            "eligibility_reasons": [],
            "factors": canonical["factors"],
            "drivers": [],
            "missing_inputs": [],
            "tsb": canonical["tsb"],
            "provenance": canonical["input_provenance"],
            "snapshot": canonical,
        }
    )["snapshot"]


def test_materializer_builds_one_idempotent_episode_without_feedback(tmp_path) -> None:
    db = Database(str(tmp_path / "episode.db"))
    plan = ensure_session_identities(
        {
            "goal_type": "triathlon",
            "distance": "olympic",
            "start_week": date(2026, 7, 6),
            "weekly_tss_plan": [60],
            "phases": ["Build"],
            "daily_plan": [
                (datetime(2026, 7, 10), 60.0, {"bike": 60.0, "run": 0.0, "swim": 0.0})
            ],
            "session_templates": [
                {
                    "date": "2026-07-10",
                    "week_index": 0,
                    "day_index": 4,
                    "phase": "Build",
                    "session_role": "long",
                    "session_focus": "Endurance",
                    "sport": "bike",
                    "duration_minutes": 60,
                    "kind": "single",
                    "template_key": "bike_endurance",
                    "definition_snapshot": {
                        "step_builder_key": "endurance",
                        "catalog_version": "workout_catalog_v1",
                    },
                }
            ],
            "weekly_summary": [],
            "constraint_summary": {},
            "near_term_edit_version": 0,
        }
    )
    saved_checkpoint = db.save_planning_checkpoint(build_planning_checkpoint(plan))
    session = plan["session_templates"][0]
    session_id = session["session_id"]
    db.save_activities(
        [
            {
                "activity_id": "ride-1",
                "date": "2026-07-10",
                "started_at_utc": "2026-07-10T08:00:00Z",
                "sport": "bike",
                "duration_minutes": 60,
                "tss": 60.0,
            }
        ]
    )
    db.save_plan_actual_match(
        {
            "fingerprint": "match-ride-1",
            "target_key": f"session:{session_id}",
            "session_id": session_id,
            "base_checkpoint_id": saved_checkpoint["id"],
            "session_date": "2026-07-10",
            "match_status": "matched",
            "match_method": "user_confirmed",
            "confidence": 1.0,
            "planned_snapshot": {"date": "2026-07-10", "sport": "bike", "role": "long"},
            "actual_activity_ids": ["ride-1"],
            "actual_snapshot": {"tss": 60.0, "sport": "bike", "role": "long"},
            "evidence": ["User explicitly confirmed activity match"],
            "rule_version": "plan_actual_match_v1",
        }
    )
    for day, score in (("2026-07-10", 70), ("2026-07-11", 62), ("2026-07-12", 68), ("2026-07-13", 71)):
        _snapshot(db, day, score)

    first = refresh_recovery_episodes(db, as_of=date(2026, 7, 13))
    retry = refresh_recovery_episodes(db, as_of=date(2026, 7, 13))
    episodes = db.get_recovery_episodes(latest_only=True)

    assert first["created"] == 1
    assert retry["created"] == 0
    assert len(episodes) == 1
    assert episodes[0]["status"] == "eligible"
    assert episodes[0]["stimulus_family"] == "endurance"
    assert episodes[0]["load_bucket"] == "moderate"
    assert episodes[0]["feedback"] == {}
    assert episodes[0]["outcome"]["readiness_deltas"] == {
        "d1": -8.0,
        "d2": -2.0,
        "d3": 1.0,
    }


def test_capture_run_identity_wins_over_retry_clock(tmp_path) -> None:
    db = Database(str(tmp_path / "capture.db"))

    first = record_post_sync_recovery_state(
        db,
        capture_run_id="sync-run-1",
        observed_at_utc=datetime(2026, 7, 14, 5, 0, tzinfo=timezone.utc),
    )
    retry = record_post_sync_recovery_state(
        db,
        capture_run_id="sync-run-1",
        observed_at_utc=datetime(2026, 7, 14, 6, 0, tzinfo=timezone.utc),
    )

    assert first["created"] is True
    assert retry["created"] is False
    assert retry["snapshot"]["id"] == first["snapshot"]["id"]
    assert db.get_database_stats()["readiness_snapshots"] == 1
