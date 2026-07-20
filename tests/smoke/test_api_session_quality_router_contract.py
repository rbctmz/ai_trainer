"""Contract smoke tests for api/routers/session_quality.py (issue #242).

`tests/smoke/test_session_quality_forecast.py` exercises the underlying
`api.session_quality_forecast` / `api.session_feedback` service functions
directly; the router's own wrapper functions
(`list_session_quality_predictions`, `resolve_session_quality`) and its
LookupError->404 / ValueError->422 exception mapping were never called.
Covers:
(a) success response with key schema fields (seeded via
    `Database.save_session_quality_prediction`)
(b) empty/degraded state without raising
(c) 422 (invalid `actual_role`) and 404 (unknown prediction) through the
    router's own exception mapping
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from data.database import Database


def _seed_prediction(db: Database, *, fingerprint: str = "pred-fp-1", target_date: str = "2026-07-12") -> dict:
    saved = db.save_session_quality_prediction(
        fingerprint=fingerprint,
        target_key=f"checkpoint:{target_date}:quality",
        rule_version="session_quality_v1",
        target_date=target_date,
        plan_checkpoint_id=1,
        plan_session_index=0,
        planned_session={"role": "quality", "sport": "bike", "tss": 60.0, "duration_minutes": 60},
        forecast={"prediction_pct": 70, "prediction_band": "uncertain"},
        inputs={"rule_version": "session_quality_v1"},
        evidence=["seed"],
    )
    return saved["prediction"]


def test_session_quality_routes_registered():
    import importlib

    main = importlib.import_module("api.main")
    paths = set(main.app.openapi()["paths"].keys())
    assert {
        "/api/session-quality-predictions",
        "/api/session-quality-predictions/{prediction_id}/resolve",
    } <= paths


def test_list_predictions_with_data(tmp_path):
    from api.routers.session_quality import list_session_quality_predictions

    db = Database(str(tmp_path / "a.db"))
    prediction = _seed_prediction(db)

    payload = list_session_quality_predictions(days=36500, db=db)

    assert payload["shadow_mode"] is True
    assert len(payload["predictions"]) == 1
    assert payload["predictions"][0]["id"] == prediction["id"]
    assert payload["predictions"][0]["prediction_pct"] == 70
    assert payload["summary"]["total"] == 1
    assert payload["summary"]["pending"] == 1


def test_list_predictions_empty_db_no_500(tmp_path):
    from api.routers.session_quality import list_session_quality_predictions

    db = Database(str(tmp_path / "b.db"))
    payload = list_session_quality_predictions(days=30, db=db)

    assert payload["predictions"] == []
    assert payload["summary"]["total"] == 0
    assert payload["shadow_mode"] is True


def test_resolve_unknown_prediction_maps_lookuperror_to_404(tmp_path):
    from api.routers.session_quality import ResolveSessionQualityRequest, resolve_session_quality

    db = Database(str(tmp_path / "c.db"))
    req = ResolveSessionQualityRequest(activity_ids=[], actual_role=None)

    with pytest.raises(HTTPException) as exc_info:
        resolve_session_quality(99999, req, db=db)
    assert exc_info.value.status_code == 404


def test_resolve_invalid_actual_role_maps_valueerror_to_422(tmp_path):
    from api.routers.session_quality import ResolveSessionQualityRequest, resolve_session_quality

    db = Database(str(tmp_path / "d.db"))
    prediction = _seed_prediction(db)
    req = ResolveSessionQualityRequest(activity_ids=[], actual_role="not-a-real-role")

    with pytest.raises(HTTPException) as exc_info:
        resolve_session_quality(prediction["id"], req, db=db)
    assert exc_info.value.status_code == 422


def test_resolve_session_quality_request_rejects_out_of_range_rating():
    from pydantic import ValidationError

    from api.routers.session_quality import ResolveSessionQualityRequest

    with pytest.raises(ValidationError):
        ResolveSessionQualityRequest(activity_ids=[], quality_rating_1_5=9)
