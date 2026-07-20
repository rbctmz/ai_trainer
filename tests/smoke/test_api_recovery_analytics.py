"""FastAPI/read-only contract for Issue #176 recovery analytics."""
from __future__ import annotations

from data.database import Database


def test_recovery_summary_is_collection_first_and_read_only(tmp_path) -> None:
    from api.routers.recovery_analytics import recovery_analytics_summary_view

    db = Database(str(tmp_path / "api-recovery.db"))
    before = db.get_database_stats()

    first = recovery_analytics_summary_view(db=db)
    second = recovery_analytics_summary_view(db=db)

    assert first == second
    assert first["capture_mode"] == "prospective"
    assert first["maturity"] == "collection_only"
    assert first["registry"] == []
    assert first["guardrails"]["affects_decisions"] is False
    assert first["guardrails"]["provider_writeback"] is False
    after = db.get_database_stats()
    assert after["readiness_snapshots"] == before["readiness_snapshots"] == 0
    assert after["recovery_episodes"] == before["recovery_episodes"] == 0


def test_unknown_recovery_cohort_returns_404(tmp_path) -> None:
    from fastapi import HTTPException
    from api.routers.recovery_analytics import recovery_cohort_view

    db = Database(str(tmp_path / "api-recovery.db"))

    try:
        recovery_cohort_view("missing-cohort", db=db)
    except HTTPException as exc:
        assert exc.status_code == 404
        assert "cohort" in str(exc.detail).lower()
    else:
        raise AssertionError("unknown cohort must return 404")


def test_invalid_capture_mode_returns_422(tmp_path) -> None:
    """Issue #242: the router's `HTTPException(422, ...)` guard on
    `capture_mode` was never exercised by a test."""
    from fastapi import HTTPException
    from api.routers.recovery_analytics import recovery_analytics_summary_view

    db = Database(str(tmp_path / "api-recovery-422.db"))

    try:
        recovery_analytics_summary_view(capture_mode="retrospective", db=db)
    except HTTPException as exc:
        assert exc.status_code == 422
    else:
        raise AssertionError("non-prospective capture_mode must return 422")


def test_recovery_routes_are_registered() -> None:
    from api.main import app

    paths = app.openapi()["paths"]

    assert "/api/recovery-analytics" in paths
    assert "/api/recovery-analytics/cohorts/{cohort_id}" in paths
    assert sum(
        getattr(route, "path", None) == "/api/recovery-analytics"
        for route in app.routes
    ) == 1


def test_cohort_evidence_never_exposes_athlete_note(tmp_path) -> None:
    from services.recovery_analytics import (
        recovery_analytics_summary,
        recovery_cohort_detail,
    )

    db = Database(str(tmp_path / "privacy.db"))
    for index in range(10):
        db.save_recovery_episode(
            {
                "fingerprint": f"episode-{index}",
                "target_key": f"session:s{index}",
                "session_id": f"s{index}",
                "session_date": f"2026-07-{index + 1:02d}",
                "iso_week": f"2026-W{27 + index % 2}",
                "capture_mode": "prospective",
                "status": "eligible",
                "rule_version": "recovery_response_v1",
                "stimulus_family": "endurance",
                "sport": "bike",
                "actual_tss": 60,
                "load_bucket": "moderate",
                "adherence": "exact",
                "exclusion_reasons": [],
                "planned": {},
                "actual": {},
                "feedback": {
                    "id": index + 1,
                    "session_rpe_1_10": 5,
                    "quality_rating_1_5": 4,
                    "note": "private athlete note",
                },
                "outcome": {
                    "readiness_deltas": {"d1": -5, "d2": -2, "d3": 1},
                    "recovered_by_day": 1,
                },
                "confounders": {},
            }
        )
    summary = recovery_analytics_summary(db)
    detail = recovery_cohort_detail(db, summary["registry"][0]["cohort_id"])

    assert detail is not None
    assert all("note" not in row["feedback"] for row in detail["included_episodes"])
    assert "private athlete note" not in str(detail)
