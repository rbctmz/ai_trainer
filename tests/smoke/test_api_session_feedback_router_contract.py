"""Contract smoke tests for api/routers/session_feedback.py (issue #242).

`tests/smoke/test_post_workout_feedback.py` thoroughly exercises the
underlying `api/session_feedback.py` service module directly, but never
imports `api.routers.session_feedback` -- the router's own request/response
wiring and exception-translation (`_raise_http`: LookupError->404,
StaleFeedbackError->409, ValueError->422) were never exercised. This file
closes that gap. Covers:
(a) success response with key schema fields (read endpoints, seeded directly
    via `Database.save_session_feedback` -- the same low-level entrypoint
    `tests/smoke/test_post_workout_feedback.py` already relies on)
(b) empty/degraded state without raising (no feedback recorded yet)
(c) 422: Pydantic field-constraint validation on the request models (the
    same convention `tests/smoke/test_briefing_settings.py` uses -- this is
    exactly what FastAPI's own transport-layer validation would reject
    before the handler ever runs), plus LookupError->404 mapping through the
    router for the mutation endpoints.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from data.database import Database


def _feedback_row(fingerprint: str = "client-feedback-1") -> dict:
    return {
        "fingerprint": fingerprint,
        "target_key": "session:ats_quality",
        "session_id": "ats_quality",
        "parent_session_id": None,
        "match_revision_id": None,
        "match_snapshot": {"planned": {"session_id": "ats_quality"}},
        "actual_activity_ids": ["ride-1"],
        "completion_status": "completed",
        "completion_pct": 100,
        "session_rpe_1_10": 6,
        "quality_rating_1_5": 4,
        "completion_pct_source": "athlete_entered",
        "note": None,
        "source": "user_web",
        "session_end_at_utc": "2026-07-12T09:00:00Z",
        "session_end_provenance": "started_at_utc_plus_duration_minutes",
        "status": "active",
        "rule_version": "session_feedback_v1",
        "submitted_at": "2026-07-12T10:00:00Z",
    }


def test_session_feedback_route_lifecycle_is_registered():
    import importlib

    main = importlib.import_module("api.main")
    paths = set(main.app.openapi()["paths"].keys())
    assert {
        "/api/session-feedback/prompts",
        "/api/session-feedback",
        "/api/session-feedback/{feedback_id}/correct",
        "/api/session-feedback/{feedback_id}/tombstone",
        "/api/session-feedback/{session_id}/history",
        "/api/session-feedback/summary/all",
    } <= paths


def test_session_feedback_history_with_data(tmp_path):
    from api.routers.session_feedback import session_feedback_history

    db = Database(str(tmp_path / "a.db"))
    db.save_session_feedback(_feedback_row())

    payload = session_feedback_history("ats_quality", db=db)

    assert payload["session_id"] == "ats_quality"
    assert len(payload["history"]) == 1
    assert payload["current"]["completion_status"] == "completed"
    assert payload["current"]["quality_rating_1_5"] == 4


def test_session_feedback_summary_with_data(tmp_path):
    from api.routers.session_feedback import session_feedback_summary

    db = Database(str(tmp_path / "b.db"))
    db.save_session_feedback(_feedback_row())

    payload = session_feedback_summary(db=db)

    assert payload["total_sessions"] == 1
    assert payload["active"] == 1
    assert payload["tombstoned"] == 0
    assert payload["completion_statuses"] == {"completed": 1}


def test_session_feedback_history_unknown_session_no_500(tmp_path):
    from api.routers.session_feedback import session_feedback_history

    db = Database(str(tmp_path / "c.db"))
    payload = session_feedback_history("does-not-exist", db=db)

    assert payload["session_id"] == "does-not-exist"
    assert payload["history"] == []
    assert payload["current"] is None
    assert payload["evaluations"] == []


def test_pending_feedback_prompts_empty_db_no_500(tmp_path):
    from api.routers.session_feedback import pending_feedback_prompts

    db = Database(str(tmp_path / "d.db"))
    payload = pending_feedback_prompts(as_of=None, db=db)

    assert payload["prompts"] == []


def test_session_feedback_summary_empty_db_no_500(tmp_path):
    from api.routers.session_feedback import session_feedback_summary

    db = Database(str(tmp_path / "e.db"))
    payload = session_feedback_summary(db=db)

    assert payload["total_sessions"] == 0
    assert payload["active"] == 0


def test_submit_feedback_unknown_session_maps_lookuperror_to_404(tmp_path):
    from api.routers.session_feedback import SubmitFeedbackRequest, submit_feedback

    req = SubmitFeedbackRequest(
        session_id="does-not-exist",
        client_submission_fingerprint="fp-1",
        completion_status="completed",
    )
    db = Database(str(tmp_path / "f.db"))
    with pytest.raises(HTTPException) as exc_info:
        submit_feedback(req, db=db)
    assert exc_info.value.status_code == 404


def test_correct_feedback_unknown_id_maps_lookuperror_to_404(tmp_path):
    from api.routers.session_feedback import FeedbackValues, correct_feedback

    req = FeedbackValues(client_submission_fingerprint="fp-1", completion_status="completed")
    db = Database(str(tmp_path / "g.db"))
    with pytest.raises(HTTPException) as exc_info:
        correct_feedback(999, req, db=db)
    assert exc_info.value.status_code == 404


def test_tombstone_feedback_unknown_id_maps_lookuperror_to_404(tmp_path):
    from api.routers.session_feedback import TombstoneRequest, tombstone_feedback

    req = TombstoneRequest(client_submission_fingerprint="fp-1")
    db = Database(str(tmp_path / "h.db"))
    with pytest.raises(HTTPException) as exc_info:
        tombstone_feedback(999, req, db=db)
    assert exc_info.value.status_code == 404


def test_submit_feedback_request_rejects_empty_session_id():
    from api.routers.session_feedback import SubmitFeedbackRequest

    with pytest.raises(ValidationError):
        SubmitFeedbackRequest(
            session_id="",
            client_submission_fingerprint="fp-1",
            completion_status="completed",
        )


def test_feedback_values_rejects_out_of_range_rpe():
    from api.routers.session_feedback import FeedbackValues

    with pytest.raises(ValidationError):
        FeedbackValues(
            client_submission_fingerprint="fp-1", completion_status="completed", session_rpe_1_10=99
        )


def test_feedback_values_rejects_out_of_range_quality_rating():
    from api.routers.session_feedback import FeedbackValues

    with pytest.raises(ValidationError):
        FeedbackValues(
            client_submission_fingerprint="fp-1", completion_status="completed", quality_rating_1_5=0
        )


def test_tombstone_request_rejects_empty_fingerprint():
    from api.routers.session_feedback import TombstoneRequest

    with pytest.raises(ValidationError):
        TombstoneRequest(client_submission_fingerprint="")
