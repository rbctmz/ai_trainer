"""RED contract for the public read surface of Issue #609.

The domain projection is already covered separately.  These tests pin the
thin planning-router boundary: route registration, provider-free service
delegation, and stable HTTP translations for absent sessions and bad windows.
"""
from __future__ import annotations

import importlib

import pytest
from fastapi import HTTPException

from data.database import Database
from models.session_projection import SessionProjectionNotFoundError


pytestmark = pytest.mark.smoke


def _route():
    module = importlib.import_module("api.routers.planning")
    route = getattr(module, "planning_session_projection", None)
    assert callable(route), "planning_session_projection route is missing"
    return route


def test_session_projection_route_is_registered() -> None:
    main = importlib.import_module("api.main")
    assert "/api/planning/session-projection/{session_id}" in main.app.openapi()["paths"]


def test_session_projection_route_delegates_to_local_service(tmp_path, monkeypatch) -> None:
    planning_router = importlib.import_module("api.routers.planning")
    service = getattr(planning_router, "session_projection_service", None)
    assert service is not None, "session projection service boundary is missing"
    sentinel = {"schema_version": "session_projection_v1", "session_id": "session-1"}
    observed: dict[str, object] = {}

    def fake_projection(db, *, session_id, as_of, weeks):
        observed.update(db=db, session_id=session_id, as_of=as_of, weeks=weeks)
        return sentinel

    monkeypatch.setattr(service, "session_projection_at", fake_projection)
    db = Database(str(tmp_path / "projection.db"))

    result = _route()(session_id="session-1", as_of="2026-07-08", weeks=2, db=db)

    assert result is sentinel
    assert observed == {
        "db": db,
        "session_id": "session-1",
        "as_of": "2026-07-08",
        "weeks": 2,
    }


@pytest.mark.parametrize(
    ("error", "expected_status"),
    [
        (SessionProjectionNotFoundError("missing"), 404),
        (ValueError("bad window"), 422),
    ],
)
def test_session_projection_route_translates_domain_errors(
    tmp_path,
    monkeypatch,
    error: Exception,
    expected_status: int,
) -> None:
    planning_router = importlib.import_module("api.routers.planning")
    service = getattr(planning_router, "session_projection_service", None)
    assert service is not None, "session projection service boundary is missing"

    def fail(*_args, **_kwargs):
        raise error

    monkeypatch.setattr(service, "session_projection_at", fail)
    db = Database(str(tmp_path / "projection-error.db"))

    with pytest.raises(HTTPException) as exc_info:
        _route()(session_id="missing", as_of="2026-07-08", weeks=1, db=db)

    assert exc_info.value.status_code == expected_status


def test_session_projection_types_and_contract_registry_are_declared() -> None:
    types = open("web/lib/types.ts", encoding="utf-8").read()
    registry = open("tests/contracts/registry.json", encoding="utf-8").read()

    assert "export interface SessionProjection" in types
    assert 'schema_version: "session_projection_v1"' in types
    assert 'projection_status: SessionProjectionStatus' in types
    assert '"/api/planning/session-projection/{session_id}"' in registry
    assert '"interface": "SessionProjection"' in registry


def test_planning_reconciliation_reuses_projection_composer_for_each_row(
    tmp_path,
    monkeypatch,
) -> None:
    planning_router = importlib.import_module("api.routers.planning")
    reconciliation = {
        "has_plan": True,
        "rows": [
            {"session_id": "session-1"},
            {"session_id": "session-2"},
        ],
        "unplanned_activities": [],
    }
    local_reconciliation = {
        **reconciliation,
        "provider": {"status": "disabled"},
        "rows": [dict(row) for row in reconciliation["rows"]],
    }

    def fake_reconciliation(*_args, **kwargs):
        return local_reconciliation if kwargs["include_provider"] is False else reconciliation

    monkeypatch.setattr(
        planning_router.planning_service,
        "reconciliation_at",
        fake_reconciliation,
    )
    compose = getattr(
        planning_router.session_projection_service,
        "session_projection_from_reconciliation",
        None,
    )
    assert callable(compose), "shared projection-from-snapshot boundary is missing"
    observed: list[tuple[object, str]] = []

    def fake_compose(db, snapshot, *, session_id):
        assert snapshot is local_reconciliation
        observed.append((db, session_id))
        return {"schema_version": "session_projection_v1", "session_id": session_id}

    monkeypatch.setattr(
        planning_router.session_projection_service,
        "session_projection_from_reconciliation",
        fake_compose,
    )
    db = Database(str(tmp_path / "planning-consumer.db"))

    result = planning_router.planning_reconciliation(
        weeks=1,
        as_of="2026-07-08",
        include_provider=False,
        db=db,
    )

    assert observed == [(db, "session-1"), (db, "session-2")]
    assert [row["session_projection"]["session_id"] for row in result["rows"]] == [
        "session-1",
        "session-2",
    ]


def test_activity_detail_reuses_projection_for_matched_session(tmp_path, monkeypatch) -> None:
    from api.routers import activities as activities_router
    from tests.smoke.test_plan_intervals import _seed_plan_actual_match_for_activity

    db = Database(str(tmp_path / "activity-consumer.db"))
    db.save_activities(
        [
            {
                "activity_id": "activity-1",
                "date": "2026-07-08",
                "sport": "cycling",
                "duration_minutes": 60,
                "tss": 50.0,
            }
        ]
    )
    _seed_plan_actual_match_for_activity(db, "activity-1", session_id="session-1")
    sentinel = {"schema_version": "session_projection_v1", "session_id": "session-1"}
    service = getattr(activities_router, "session_projection_service", None)
    assert service is not None, "activity projection service boundary is missing"
    monkeypatch.setattr(service, "session_projection_at", lambda *_a, **_k: sentinel)
    monkeypatch.setattr(activities_router, "fetch_activity_intervals", lambda *_a: None)
    monkeypatch.setattr(activities_router, "fetch_activity_power_curve", lambda *_a: None)

    activity = activities_router.get_activity_card("activity-1", db=db)["activity"]

    assert activity["session_id"] == "session-1"
    assert activity["session_projection"] is sentinel


def test_activity_detail_uses_unique_local_reconciliation_parent(tmp_path, monkeypatch) -> None:
    from api.routers import activities as activities_router
    from tests.smoke.test_api_planning import _reconciliation_db

    db, _plan = _reconciliation_db(tmp_path)
    monkeypatch.setattr(activities_router, "fetch_activity_intervals", lambda *_a: None)
    monkeypatch.setattr(activities_router, "fetch_activity_power_curve", lambda *_a: None)

    activity = activities_router.get_activity_card(
        "actual-2026-07-07", db=db
    )["activity"]

    assert activity["session_id"] == "ats_bb49d5a3ba37cce39db5bdd2"
    assert activity["session_projection"]["session_id"] == activity["session_id"]
    assert activity["session_projection"]["projection_status"] == "matched"


def test_activity_detail_fails_closed_for_ambiguous_local_match(tmp_path, monkeypatch) -> None:
    from api.routers import activities as activities_router
    from tests.smoke.test_api_planning import _reconciliation_db

    db, _plan = _reconciliation_db(tmp_path)
    db.save_activities(
        [
            {
                "activity_id": "second-bike-2026-07-07",
                "date": "2026-07-07",
                "sport": "cycling",
                "duration_minutes": 45,
                "tss": 35.0,
            }
        ]
    )
    monkeypatch.setattr(activities_router, "fetch_activity_intervals", lambda *_a: None)
    monkeypatch.setattr(activities_router, "fetch_activity_power_curve", lambda *_a: None)

    activity = activities_router.get_activity_card(
        "actual-2026-07-07", db=db
    )["activity"]

    assert activity["session_id"] is None
    assert activity["session_projection"] is None


def test_today_planning_and_activity_render_one_shared_projection_component() -> None:
    component = open(
        "web/components/session/SessionProjectionSummary.tsx",
        encoding="utf-8",
    ).read()
    today = open("web/app/today/page.tsx", encoding="utf-8").read()
    planning = open("web/app/planning/page.tsx", encoding="utf-8").read()
    activities = open("web/app/activities/page.tsx", encoding="utf-8").read()

    assert "SessionProjectionSummary" in component
    assert "projection.load.planned_tss" in component
    assert "projection.load.matched_tss" in component
    assert "projection.load.day_total_tss" in component
    assert "<SessionProjectionSummary" in today
    assert "session?.sessions !== undefined" in today
    assert ".map((leaf) => leaf.group_id ?? leaf.session_id)" in today
    assert "new Set(" in today
    assert "session.sessions.flatMap" not in today
    assert "<SessionProjectionSummary" in planning
    assert "<SessionProjectionSummary" in activities
