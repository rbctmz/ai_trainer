"""BDD/TDD contract for Issue #175 post-workout feedback."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Barrier

import pytest

from data.database import Database
from models.planning_checkpoints import build_planning_checkpoint
from models.session_identity import ensure_session_identities
from models.post_workout_feedback import (
    EVALUATION_RULE_VERSION,
    FEEDBACK_RULE_VERSION,
    build_feedback_prompts,
    derive_session_end_utc,
    evaluate_prediction,
    validate_feedback_values,
)


pytestmark = pytest.mark.smoke


def _activity(
    activity_id: str,
    *,
    started_at_utc: str | None = "2026-07-12T08:00:00Z",
    duration_minutes: float = 60,
    sport: str = "bike",
) -> dict:
    return {
        "activity_id": activity_id,
        "date": "2026-07-12",
        "started_at_utc": started_at_utc,
        "duration_minutes": duration_minutes,
        "sport": sport,
        "tss": 60.0,
    }


def _row(
    *,
    match_status: str = "matched",
    match_method: str = "date_sport_heuristic",
    confidence: float = 0.75,
    adherence: str = "exact",
    activities: list[dict] | None = None,
    candidates: list[dict] | None = None,
) -> dict:
    activities = [_activity("ride-1")] if activities is None else activities
    return {
        "session_id": "ats_quality",
        "target_key": "session:ats_quality",
        "date": "2026-07-12",
        "name": "Threshold Intervals",
        "role": "quality",
        "sport": "bike",
        "tss": 60.0,
        "duration_minutes": 60,
        "match_status": match_status,
        "match_method": match_method,
        "confidence": confidence,
        "adherence": adherence,
        "actual_activity_ids": [item["activity_id"] for item in activities],
        "actual_activities": activities,
        "candidate_activities": list(candidates or []),
        "actual_total_tss": sum(float(item.get("tss") or 0.0) for item in activities),
        "actual_duration_minutes": sum(
            float(item.get("duration_minutes") or 0.0) for item in activities
        ),
        "evidence": ["Unique same-date, same-sport match"],
    }


def _template(*, kind: str = "single") -> dict:
    return {
        "session_id": "ats_quality",
        "date": "2026-07-12",
        "session_role": "quality",
        "kind": kind,
        "template_name": "Threshold Intervals",
        "legs": (
            [
                {"leg_index": 1, "sport": "bike"},
                {"leg_index": 2, "sport": "run"},
            ]
            if kind == "composite"
            else []
        ),
    }


def _feedback_payload(
    fingerprint: str = "client-feedback-1",
    *,
    quality: int | None = 5,
    rpe: int | None = 9,
) -> dict:
    return {
        "fingerprint": fingerprint,
        "target_key": "session:ats_quality",
        "session_id": "ats_quality",
        "parent_session_id": None,
        "match_revision_id": None,
        "match_snapshot": {
            "planned": _row(),
            "match_status": "matched",
            "match_method": "date_sport_heuristic",
            "confidence": 0.75,
            "adherence": "exact",
            "actual_activities": [_activity("ride-1")],
        },
        "actual_activity_ids": ["ride-1"],
        "completion_status": "completed",
        "completion_pct": 100,
        "completion_pct_source": "athlete_entered",
        "session_rpe_1_10": rpe,
        "quality_rating_1_5": quality,
        "note": "Тяжело, но все интервалы ровно",
        "source": "user_web",
        "session_end_at_utc": "2026-07-12T09:00:00Z",
        "session_end_provenance": "started_at_utc_plus_duration_minutes",
        "status": "active",
        "rule_version": FEEDBACK_RULE_VERSION,
        "submitted_at": "2026-07-13T06:00:00Z",
    }


def _prediction(*, prediction_id: int = 7, created_at: str = "2026-07-12T06:00:00Z") -> dict:
    return {
        "id": prediction_id,
        "target_key": "checkpoint:2026-07-12:quality",
        "revision": prediction_id,
        "rule_version": "session_quality_v1",
        "target_date": "2026-07-12",
        "prediction_pct": 70,
        "prediction_band": "uncertain",
        "planned_session": {
            "role": "quality",
            "sport": "bike",
            "tss": 60.0,
            "duration_minutes": 60,
        },
        "created_at": created_at,
    }


def _one_session_plan() -> dict:
    plan = {
        "goal_type": "Триатлон",
        "distance": "Олимпийка",
        "event_date": "2026-10-04",
        "weeks_to_race": 12,
        "start_week": "2026-07-06",
        "weekly_tss_plan": [60],
        "base_weekly_tss_plan": [60],
        "phases": ["Build"],
        "daily_plan": [
            (datetime(2026, 7, 12), 60.0, {"bike": 60.0}),
        ],
        "session_templates": [
            {
                "date": "2026-07-12",
                "week_index": 0,
                "day_index": 6,
                "phase": "Build",
                "session_role": "quality",
                "session_focus": "Threshold Intervals",
                "export_name": "Threshold Intervals",
                "sport": "bike",
                "sport_label": "вело",
                "duration_minutes": 60,
                "kind": "single",
            }
        ],
        "weekly_summary": [],
        "constraint_summary": {},
        "near_term_edit_version": 0,
    }
    return ensure_session_identities(plan)


def test_source_backed_end_uses_latest_leg_and_never_guesses_missing_utc() -> None:
    ended_at, provenance = derive_session_end_utc(
        [
            _activity("bike", duration_minutes=60),
            _activity(
                "run",
                started_at_utc="2026-07-12T09:10:00Z",
                duration_minutes=30,
                sport="run",
            ),
        ]
    )
    missing, missing_provenance = derive_session_end_utc(
        [_activity("local-only", started_at_utc=None)]
    )

    assert ended_at == "2026-07-12T09:40:00Z"
    assert provenance == "started_at_utc_plus_duration_minutes"
    assert missing is None
    assert missing_provenance == "missing_source_start_or_duration"


def test_prompt_lifecycle_is_match_first_in_progress_safe_and_read_only() -> None:
    before_end = build_feedback_prompts(
        [_row()],
        templates=[_template()],
        latest_feedback_by_session={},
        prompt_events_by_session={},
        forecasts=[_prediction()],
        now_utc=datetime(2026, 7, 12, 8, 30, tzinfo=timezone.utc),
        as_of="2026-07-12",
    )
    ready = build_feedback_prompts(
        [_row()],
        templates=[_template()],
        latest_feedback_by_session={},
        prompt_events_by_session={},
        forecasts=[_prediction()],
        now_utc=datetime(2026, 7, 12, 9, 1, tzinfo=timezone.utc),
        as_of="2026-07-12",
    )
    ambiguous = build_feedback_prompts(
        [_row(match_status="ambiguous", confidence=0.35)],
        templates=[_template()],
        latest_feedback_by_session={},
        prompt_events_by_session={},
        forecasts=[],
        now_utc=datetime(2026, 7, 13, 9, 0, tzinfo=timezone.utc),
        as_of="2026-07-13",
    )

    assert before_end["prompts"][0]["state"] == "not_eligible"
    assert before_end["prompts"][0]["reason"] == "session_in_progress"
    assert ready["primary"]["state"] == "ready"
    assert ready["primary"]["is_primary"] is True
    assert ready["primary"]["planned_sport"] == "bike"
    assert ambiguous["prompts"][0]["state"] == "pending_match"


def test_brick_prompts_once_for_parent_with_all_activity_ids() -> None:
    activities = [
        _activity("bike-leg", duration_minutes=60),
        _activity(
            "run-leg",
            started_at_utc="2026-07-12T09:05:00Z",
            duration_minutes=30,
            sport="run",
        ),
    ]
    result = build_feedback_prompts(
        [_row(match_method="user_confirmed", confidence=1.0, activities=activities)],
        templates=[_template(kind="composite")],
        latest_feedback_by_session={},
        prompt_events_by_session={},
        forecasts=[],
        now_utc=datetime(2026, 7, 13, 9, 0, tzinfo=timezone.utc),
        as_of="2026-07-13",
    )

    assert len(result["prompts"]) == 1
    assert result["prompts"][0]["session_id"] == "ats_quality"
    assert result["prompts"][0]["kind"] == "composite"
    assert result["prompts"][0]["actual_activity_ids"] == ["bike-leg", "run-leg"]


def test_no_activity_non_start_waits_until_the_following_calendar_day() -> None:
    unmatched = _row(match_status="unmatched", confidence=0.0, activities=[])
    same_day = build_feedback_prompts(
        [unmatched],
        templates=[_template()],
        latest_feedback_by_session={},
        prompt_events_by_session={},
        forecasts=[],
        now_utc=datetime(2026, 7, 12, 23, 59, tzinfo=timezone.utc),
        as_of="2026-07-12",
    )
    next_day = build_feedback_prompts(
        [unmatched],
        templates=[_template()],
        latest_feedback_by_session={},
        prompt_events_by_session={},
        forecasts=[],
        now_utc=datetime(2026, 7, 13, 0, 1, tzinfo=timezone.utc),
        as_of="2026-07-13",
    )

    assert same_day["prompts"][0]["state"] == "not_eligible"
    assert next_day["prompts"][0]["state"] == "ready"
    assert next_day["prompts"][0]["allowed_completion_statuses"] == [
        "did_not_start",
        "unknown",
    ]


def _tombstone_feedback(*, ids: list[str], method: str = "user_confirmed") -> dict:
    return {
        "id": 35,
        "status": "tombstone",
        "match_snapshot": {
            "match_method": method,
            "actual_activity_ids": list(ids),
        },
    }


def test_unmatched_row_with_candidate_activities_is_pending_match() -> None:
    """After the athlete unmakes a match, the day's activities are still
    candidates: the prompt must ask to clarify the fact instead of offering
    `did_not_start`/`unknown` (the session demonstrably happened)."""
    row = _row(
        match_status="unmatched",
        match_method="user_unmatched",
        confidence=0.0,
        activities=[],
        candidates=[_activity("garmin-run", sport="run")],
    )

    result = build_feedback_prompts(
        [row],
        templates=[_template()],
        latest_feedback_by_session={},
        prompt_events_by_session={},
        forecasts=[],
        now_utc=datetime(2026, 7, 13, 9, 0, tzinfo=timezone.utc),
        as_of="2026-07-13",
    )

    assert result["prompts"][0]["state"] == "pending_match"
    assert result["prompts"][0]["reason"] == "unmatched_session_has_candidates"


def test_tombstone_stays_binding_for_the_same_match_context() -> None:
    """Unmatching the very match a feedback was saved for keeps the prompt
    suppressed — the tombstone still describes the current context."""
    result = build_feedback_prompts(
        [_row(match_method="user_confirmed", confidence=1.0, activities=[_activity("ride-1")])],
        templates=[_template()],
        latest_feedback_by_session={"ats_quality": _tombstone_feedback(ids=["ride-1"])},
        prompt_events_by_session={},
        forecasts=[],
        now_utc=datetime(2026, 7, 13, 9, 0, tzinfo=timezone.utc),
        as_of="2026-07-13",
    )

    assert result["prompts"][0]["state"] == "superseded"
    assert result["prompts"][0]["reason"] == "latest_feedback_tombstoned"


def test_tombstone_reopens_prompt_after_rematch_with_other_activity() -> None:
    """A tombstone written for an older match (e.g. an Intervals mirror id)
    must not block evaluation after the athlete re-matched the session to a
    different activity — otherwise the session becomes a permanent dead end."""
    result = build_feedback_prompts(
        [_row(match_method="user_confirmed", confidence=1.0, activities=[_activity("garmin-run", sport="run")])],
        templates=[_template()],
        latest_feedback_by_session={"ats_quality": _tombstone_feedback(ids=["intervals-run"])},
        prompt_events_by_session={},
        forecasts=[],
        now_utc=datetime(2026, 7, 13, 9, 0, tzinfo=timezone.utc),
        as_of="2026-07-13",
    )

    assert result["prompts"][0]["state"] == "ready"
    assert result["prompts"][0]["reason"] == "matched_session_complete"


def test_rpe_quality_and_completion_are_validated_independently() -> None:
    validated = validate_feedback_values(
        completion_status="completed",
        completion_pct=100,
        session_rpe_1_10=9,
        quality_rating_1_5=5,
    )
    opposite = validate_feedback_values(
        completion_status="completed",
        completion_pct=100,
        session_rpe_1_10=3,
        quality_rating_1_5=1,
    )
    non_start = validate_feedback_values(
        completion_status="did_not_start",
        completion_pct=0,
        session_rpe_1_10=None,
        quality_rating_1_5=None,
    )

    assert validated["session_rpe_1_10"] == 9
    assert validated["quality_rating_1_5"] == 5
    assert opposite["session_rpe_1_10"] == 3
    assert opposite["quality_rating_1_5"] == 1
    assert non_start["quality_rating_1_5"] is None
    with pytest.raises(ValueError, match="session_rpe_1_10"):
        validate_feedback_values(
            completion_status="completed",
            completion_pct=100,
            session_rpe_1_10=11,
            quality_rating_1_5=5,
        )


def test_feedback_journal_is_idempotent_and_corrections_append(tmp_path) -> None:
    db = Database(str(tmp_path / "feedback.db"))
    first = db.save_session_feedback(_feedback_payload())
    retry = db.save_session_feedback({**_feedback_payload(), "quality_rating_1_5": 1})
    correction = db.save_session_feedback(
        {
            **_feedback_payload("client-feedback-2", quality=4, rpe=8),
            "supersedes_feedback_id": first["feedback"]["id"],
        }
    )

    assert first["created"] is True
    assert retry["created"] is False
    assert retry["feedback"]["id"] == first["feedback"]["id"]
    assert retry["feedback"]["quality_rating_1_5"] == 5
    assert correction["feedback"]["revision"] == 2
    assert correction["feedback"]["supersedes_feedback_id"] == first["feedback"]["id"]
    history = db.get_session_feedback_history("ats_quality")
    assert [row["revision"] for row in history] == [1, 2]
    assert db.get_latest_session_feedback("ats_quality")["id"] == correction["feedback"]["id"]


def test_feedback_fingerprint_serializes_two_sqlite_connections(tmp_path) -> None:
    path = str(tmp_path / "feedback-race.db")
    first_db = Database(path)
    second_db = Database(path)
    barrier = Barrier(2)

    def save(db: Database) -> dict:
        barrier.wait()
        return db.save_session_feedback(_feedback_payload())["feedback"]

    with ThreadPoolExecutor(max_workers=2) as executor:
        rows = list(executor.map(save, (first_db, second_db)))

    assert rows[0]["id"] == rows[1]["id"]
    assert len(first_db.get_session_feedback_history("ats_quality")) == 1


def test_feedback_first_submit_is_atomically_single_writer(tmp_path) -> None:
    path = str(tmp_path / "feedback-first-submit-race.db")
    first_db = Database(path)
    second_db = Database(path)
    barrier = Barrier(2)

    def save(item: tuple[Database, str]) -> dict:
        db, fingerprint = item
        barrier.wait()
        return db.save_session_feedback(
            {
                **_feedback_payload(fingerprint),
                "expected_latest_feedback_id": None,
            }
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(
                save,
                ((first_db, "first-submit-a"), (second_db, "first-submit-b")),
            )
        )

    assert sorted(result["created"] for result in results) == [False, True]
    assert sorted(result["conflict"] for result in results) == [False, True]
    assert len(first_db.get_session_feedback_history("ats_quality")) == 1


@pytest.mark.parametrize(
    ("quality", "expected_status", "expected_outcome", "expected_reason"),
    [
        (5, "scored", "success", None),
        (1, "scored", "failure", None),
        (3, "unscored", None, "ambiguous_quality"),
    ],
)
def test_evaluation_uses_quality_only_and_never_rpe(
    quality: int,
    expected_status: str,
    expected_outcome: str | None,
    expected_reason: str | None,
) -> None:
    feedback = _feedback_payload(quality=quality, rpe=9 if quality == 5 else 3)
    result = evaluate_prediction(
        _prediction(),
        feedback,
        feedback["match_snapshot"],
        latest_eligible_id=7,
    )

    assert result["status"] == expected_status
    assert result["quality_outcome"] == expected_outcome
    assert result["unscored_reason"] == expected_reason
    assert result["quality_rating_1_5"] == quality
    assert "session_rpe_1_10" not in result


def test_evaluation_preserves_prestart_and_adherence_guards() -> None:
    feedback = _feedback_payload()
    post_start = evaluate_prediction(
        _prediction(created_at="2026-07-12T08:00:00Z"),
        feedback,
        feedback["match_snapshot"],
        latest_eligible_id=None,
    )
    deviation = evaluate_prediction(
        _prediction(),
        feedback,
        {**feedback["match_snapshot"], "adherence": "major_deviation"},
        latest_eligible_id=7,
    )

    assert post_start["unscored_reason"] == "post_start_prediction"
    assert deviation["unscored_reason"] == "major_deviation"
    assert post_start["brier_score"] is None
    assert deviation["brier_score"] is None

    tombstone = evaluate_prediction(
        _prediction(),
        {**feedback, "status": "tombstone"},
        feedback["match_snapshot"],
        latest_eligible_id=7,
    )
    assert tombstone["status"] == "unscored"
    assert tombstone["unscored_reason"] == "feedback_tombstoned"


def test_evaluation_journal_appends_for_feedback_correction(tmp_path) -> None:
    db = Database(str(tmp_path / "evaluation.db"))
    first_feedback = db.save_session_feedback(_feedback_payload())["feedback"]
    second_feedback = db.save_session_feedback(
        {
            **_feedback_payload("client-feedback-2", quality=1),
            "supersedes_feedback_id": first_feedback["id"],
        }
    )["feedback"]
    first = db.save_session_quality_evaluation(
        {
            "fingerprint": "evaluation-1",
            "target_key": "prediction:7",
            "prediction_id": 7,
            "prediction_target_key": "checkpoint:2026-07-12:quality",
            "feedback_id": first_feedback["id"],
            "match_revision_id": None,
            "status": "scored",
            "plan_adherence": "exact",
            "quality_rating_1_5": 5,
            "quality_outcome": "success",
            "unscored_reason": None,
            "brier_score": 0.09,
            "evidence": {"source": "athlete_entered"},
            "rule_version": EVALUATION_RULE_VERSION,
        }
    )
    second = db.save_session_quality_evaluation(
        {
            "fingerprint": "evaluation-2",
            "target_key": "prediction:7",
            "supersedes_evaluation_id": first["evaluation"]["id"],
            "prediction_id": 7,
            "prediction_target_key": "checkpoint:2026-07-12:quality",
            "feedback_id": second_feedback["id"],
            "match_revision_id": None,
            "status": "scored",
            "plan_adherence": "exact",
            "quality_rating_1_5": 1,
            "quality_outcome": "failure",
            "unscored_reason": None,
            "brier_score": 0.49,
            "evidence": {"source": "athlete_entered"},
            "rule_version": EVALUATION_RULE_VERSION,
        }
    )

    assert first["evaluation"]["revision"] == 1
    assert second["evaluation"]["revision"] == 2
    latest = db.get_latest_session_quality_evaluations(prediction_ids=[7])
    assert latest[0]["feedback_id"] == second_feedback["id"]
    assert latest[0]["supersedes_evaluation_id"] == first["evaluation"]["id"]


def test_new_journals_participate_in_stats_and_clear(tmp_path) -> None:
    db = Database(str(tmp_path / "stats.db"))
    feedback = db.save_session_feedback(_feedback_payload())["feedback"]
    db.save_session_feedback_prompt_event(
        {
            "fingerprint": "dismiss-1",
            "target_key": "session:ats_quality",
            "session_id": "ats_quality",
            "event": "dismissed",
            "reason": "later",
            "source": "user_web",
            "rule_version": FEEDBACK_RULE_VERSION,
        }
    )
    db.save_session_quality_evaluation(
        {
            "fingerprint": "evaluation-stats",
            "target_key": "prediction:7",
            "prediction_id": 7,
            "prediction_target_key": "forecast-target",
            "feedback_id": feedback["id"],
            "match_revision_id": None,
            "status": "unscored",
            "plan_adherence": "unknown",
            "quality_rating_1_5": 3,
            "quality_outcome": None,
            "unscored_reason": "ambiguous_quality",
            "brier_score": None,
            "evidence": {},
            "rule_version": EVALUATION_RULE_VERSION,
        }
    )

    stats = db.get_database_stats()
    assert stats["session_feedback"] == 1
    assert stats["session_feedback_prompt_events"] == 1
    assert stats["session_quality_evaluations"] == 1
    db.clear_all_data()
    cleared = db.get_database_stats()
    assert cleared["session_feedback"] == 0
    assert cleared["session_feedback_prompt_events"] == 0
    assert cleared["session_quality_evaluations"] == 0


def test_today_feedback_projection_consumes_supplied_reconciliation_without_writes(tmp_path) -> None:
    from api.session_feedback import feedback_from_today_evidence

    db = Database(str(tmp_path / "today-feedback.db"))
    before = db.get_database_stats()
    result = feedback_from_today_evidence(
        db,
        yesterday={"status": "available", "rows": [_row()]},
        goal_plan={"session_templates": [_template()]},
        forecasts=[_prediction()],
        now_utc=datetime(2026, 7, 13, 9, 0, tzinfo=timezone.utc),
        as_of="2026-07-13",
    )

    assert result["primary"]["session_id"] == "ats_quality"
    assert result["primary"]["state"] == "ready"
    assert db.get_database_stats() == before


def test_feedback_without_forecast_is_stored_without_synthetic_prediction(
    tmp_path, monkeypatch
) -> None:
    from api import session_feedback as service

    db = Database(str(tmp_path / "no-forecast.db"))
    monkeypatch.setattr(
        service,
        "_feedback_evidence_for_session",
        lambda _db, _session_id, **_kwargs: {
            "row": _row(),
            "template": _template(),
            "match_revision_id": None,
        },
    )
    result = service.submit_session_feedback(
        db,
        {
            "session_id": "ats_quality",
            "client_submission_fingerprint": "web-submit-no-forecast",
            "completion_status": "completed",
            "completion_pct": 100,
            "session_rpe_1_10": 9,
            "quality_rating_1_5": 5,
            "note": "Готово",
        },
        now_utc=datetime(2026, 7, 13, 9, 0, tzinfo=timezone.utc),
    )

    assert result["feedback"]["source"] == "user_web"
    assert result["feedback"]["provenance_label"] == "athlete-entered"
    assert result["evaluations"] == []
    assert db.get_session_quality_predictions(days=36500) == []


def test_admin_resolve_bridges_match_feedback_and_evaluation_without_mutating_forecast(
    tmp_path,
) -> None:
    from api.session_feedback import resolve_prediction_via_feedback

    db = Database(str(tmp_path / "admin-bridge.db"))
    plan = _one_session_plan()
    checkpoint = db.save_planning_checkpoint(build_planning_checkpoint(plan))
    session_id = checkpoint["goal_plan_snapshot"]["session_templates"][0]["session_id"]
    prediction = db.save_session_quality_prediction(
        fingerprint="admin-forecast",
        target_key=f"{checkpoint['id']}:2026-07-12:0:session_quality_v1",
        rule_version="session_quality_v1",
        target_date="2026-07-12",
        plan_checkpoint_id=checkpoint["id"],
        plan_session_index=0,
        planned_session={
            "date": "2026-07-12",
            "index": 0,
            "role": "quality",
            "sport": "bike",
            "tss": 60.0,
            "duration_minutes": 60,
        },
        forecast={"prediction_pct": 70, "prediction_band": "uncertain"},
        inputs={"readiness_source": "canonical_snapshot"},
        evidence=["pre-start"],
        created_at="2026-07-12T06:00:00Z",
    )["prediction"]
    db.save_activities([_activity("ride-1")])

    result = resolve_prediction_via_feedback(
        db,
        prediction["id"],
        activity_ids=["ride-1"],
        actual_role="quality",
        quality_rating_1_5=5,
        note="admin migration bridge",
        submitted_at="2026-07-13T09:00:00Z",
    )

    assert result["predictions"][0]["status"] == "scored"
    assert result["predictions"][0]["quality_outcome"] == "success"
    raw = db.get_session_quality_prediction(prediction["id"])
    assert raw["status"] == "pending"
    assert raw["quality_rating_1_5"] is None
    feedback = db.get_latest_session_feedback(session_id)
    assert feedback["source"] == "admin_resolve"
    matches = db.get_latest_plan_actual_matches(
        start_date="2026-07-12", end_date="2026-07-12"
    )
    assert matches[0]["match_method"] == "admin_resolve"
    assert feedback["match_revision_id"] == matches[0]["id"]
    evaluations = db.get_latest_session_quality_evaluations(
        prediction_ids=[prediction["id"]]
    )
    assert evaluations[0]["feedback_id"] == feedback["id"]

    corrected = resolve_prediction_via_feedback(
        db,
        prediction["id"],
        activity_ids=["ride-1"],
        actual_role="quality",
        quality_rating_1_5=1,
        note="admin corrected rating",
        submitted_at="2026-07-13T09:05:00Z",
    )
    assert corrected["predictions"][0]["quality_outcome"] == "failure"
    history = db.get_session_feedback_history(session_id)
    assert [row["revision"] for row in history] == [1, 2]
    assert history[1]["supersedes_feedback_id"] == history[0]["id"]
    evaluation_history = db.get_session_quality_evaluations(
        prediction_ids=[prediction["id"]]
    )
    assert [row["revision"] for row in evaluation_history] == [1, 2]
    assert evaluation_history[1]["supersedes_evaluation_id"] == evaluation_history[0]["id"]


def test_feedback_correction_appends_new_evaluation_and_preserves_history(
    tmp_path, monkeypatch
) -> None:
    from api import session_feedback as service

    db = Database(str(tmp_path / "correction-service.db"))
    monkeypatch.setattr(
        service,
        "_feedback_evidence_for_session",
        lambda _db, _session_id, **_kwargs: {
            "row": _row(),
            "template": _template(),
            "match_revision_id": None,
        },
    )
    first = service.submit_session_feedback(
        db,
        {
            "session_id": "ats_quality",
            "client_submission_fingerprint": "web-submit-1",
            "completion_status": "completed",
            "completion_pct": 100,
            "session_rpe_1_10": 9,
            "quality_rating_1_5": 5,
            "note": None,
        },
        now_utc=datetime(2026, 7, 13, 9, 0, tzinfo=timezone.utc),
    )["feedback"]
    corrected = service.correct_session_feedback(
        db,
        first["id"],
        {
            "client_submission_fingerprint": "web-submit-2",
            "completion_status": "partial",
            "completion_pct": 70,
            "session_rpe_1_10": 8,
            "quality_rating_1_5": 3,
            "note": "Исправил после проверки",
        },
        now_utc=datetime(2026, 7, 13, 9, 10, tzinfo=timezone.utc),
    )

    assert corrected["feedback"]["revision"] == 2
    assert corrected["feedback"]["supersedes_feedback_id"] == first["id"]
    assert len(db.get_session_feedback_history("ats_quality")) == 2


def test_submit_retry_reuses_fingerprint_and_new_submit_requires_correction(
    tmp_path, monkeypatch
) -> None:
    from api import session_feedback as service

    db = Database(str(tmp_path / "submit-retry.db"))
    evidence_calls = 0

    def evidence(*_args, **_kwargs):
        nonlocal evidence_calls
        evidence_calls += 1
        return {
            "row": _row(),
            "template": _template(),
            "match_revision_id": None,
        }

    monkeypatch.setattr(service, "_feedback_evidence_for_session", evidence)
    payload = {
        "session_id": "ats_quality",
        "client_submission_fingerprint": "stable-web-submit",
        "completion_status": "completed",
        "completion_pct": 100,
        "session_rpe_1_10": 8,
        "quality_rating_1_5": 4,
    }

    first = service.submit_session_feedback(
        db,
        payload,
        now_utc=datetime(2026, 7, 13, 9, 0, tzinfo=timezone.utc),
    )
    retry = service.submit_session_feedback(
        db,
        payload,
        now_utc=datetime(2026, 7, 13, 9, 1, tzinfo=timezone.utc),
    )

    assert first["created"] is True
    assert retry["created"] is False
    assert retry["feedback"]["id"] == first["feedback"]["id"]
    assert evidence_calls == 1
    with pytest.raises(service.StaleFeedbackError, match="another session"):
        service.submit_session_feedback(
            db,
            {**payload, "session_id": "different-session"},
            now_utc=datetime(2026, 7, 13, 9, 2, tzinfo=timezone.utc),
        )
    with pytest.raises(service.StaleFeedbackError, match="correction endpoint"):
        service.submit_session_feedback(
            db,
            {**payload, "client_submission_fingerprint": "accidental-second-submit"},
            now_utc=datetime(2026, 7, 13, 9, 3, tzinfo=timezone.utc),
        )
    history = db.get_session_feedback_history("ats_quality")
    assert [row["revision"] for row in history] == [1]
    assert history[0]["supersedes_feedback_id"] is None


def test_stale_feedback_correction_is_rejected(tmp_path, monkeypatch) -> None:
    from api import session_feedback as service

    db = Database(str(tmp_path / "stale-correction.db"))
    monkeypatch.setattr(
        service,
        "_feedback_evidence_for_session",
        lambda _db, _session_id, **_kwargs: {
            "row": _row(),
            "template": _template(),
            "match_revision_id": None,
        },
    )
    first = service.submit_session_feedback(
        db,
        {
            "session_id": "ats_quality",
            "client_submission_fingerprint": "stale-submit-1",
            "completion_status": "completed",
            "completion_pct": 100,
            "session_rpe_1_10": 6,
            "quality_rating_1_5": 4,
        },
        now_utc=datetime(2026, 7, 13, 9, 0, tzinfo=timezone.utc),
    )["feedback"]
    service.correct_session_feedback(
        db,
        first["id"],
        {
            "client_submission_fingerprint": "stale-submit-2",
            "completion_status": "partial",
            "completion_pct": 80,
            "session_rpe_1_10": 7,
            "quality_rating_1_5": 3,
        },
        now_utc=datetime(2026, 7, 13, 9, 5, tzinfo=timezone.utc),
    )
    with pytest.raises(service.StaleFeedbackError):
        service.correct_session_feedback(
            db,
            first["id"],
            {
                "client_submission_fingerprint": "stale-submit-3",
                "completion_status": "completed",
                "completion_pct": 100,
                "session_rpe_1_10": 5,
                "quality_rating_1_5": 5,
            },
            now_utc=datetime(2026, 7, 13, 9, 10, tzinfo=timezone.utc),
        )


def test_empty_feedback_history_does_not_return_other_evaluations() -> None:
    from api.session_feedback import feedback_history

    class EmptyHistoryDatabase:
        def get_session_feedback_history(self, _session_id):
            return []

        def get_session_quality_evaluations(self, **_kwargs):
            raise AssertionError("evaluation journal must not be queried without feedback IDs")

    result = feedback_history(EmptyHistoryDatabase(), "missing-session")

    assert result == {
        "session_id": "missing-session",
        "history": [],
        "current": None,
        "evaluations": [],
    }


def test_openapi_exposes_feedback_lifecycle_routes() -> None:
    from api.main import app

    paths = app.openapi()["paths"]
    assert "/api/session-feedback" in paths
    assert "/api/session-feedback/prompts" in paths
    assert "/api/session-feedback/{feedback_id}/correct" in paths
    assert "/api/session-feedback/{session_id}/history" in paths
