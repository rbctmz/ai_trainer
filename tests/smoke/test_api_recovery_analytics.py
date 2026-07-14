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


def test_recovery_routes_are_registered() -> None:
    from api.main import app

    routes = {getattr(route, "path", None) for route in app.routes}

    assert "/api/recovery-analytics" in routes
    assert "/api/recovery-analytics/cohorts/{cohort_id}" in routes
