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
