"""Router-level contract tests for the planning endpoints (issue #246).

Остаток свипа #242: 13 эндпоинтов `api/routers/planning.py` до сих пор
исполнялись в тестах только через `api.planning_service` напрямую. Сам роутер
— сигнатуры, `Depends`-обвязка, трансляция исключений в HTTP-статусы и
`Response`-возвраты — не исполнялся ни разу, поэтому рефакторинг обвязки
проходил бы молча (ровно сценарий ATAM-карты #201).

Здесь мы вызываем router-функции НАПРЯМУЮ, с временной SQLite `Database`, без
`TestClient` и без live-провайдеров — тот же паттерн, что в
`test_api_planning.py` и `test_api_session_feedback_router_contract.py`.

Что этим НЕ покрывается (осознанно, HTTP-слой отложен): FastAPI-валидация
`Query(ge=…, le=…)` и Pydantic-валидация тела запускаются только при проходе
через ASGI/DI-слой. При прямом вызове router-функции `days: int = Query(180,
ge=1, le=365)` — это просто дефолт-значение, границы не проверяются. Поэтому
здесь пинуются лишь ветки, живущие в теле функции: явные `raise HTTPException`
и `except … → HTTPException`. Полный HTTP round-trip остаётся отдельной темой.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException
from fastapi.responses import Response

from api import planning_service as ps
from api.routers.planning import (
    AdjustRequest,
    DemandRequest,
    MatchCorrectionRequest,
    RebalanceRequest,
    planning_adjust,
    planning_events,
    planning_export_ics,
    planning_export_workout,
    planning_get_demand,
    planning_history,
    planning_plan,
    planning_rebalance_confirm,
    planning_rebalance_preview,
    planning_reconciliation,
    planning_record_match,
    planning_set_demand,
    planning_target_preview,
)
from data.database import Database
from models.planning_targets import demand_profile

# Reuse the seed/fixture helpers already vetted by the sibling suite instead of
# duplicating them (same convention as test_api_planning.py importing _goal_plan).
from tests.smoke.test_api_planning import _reconciliation_db, _seeded_db


def _empty_db(tmp_path) -> Database:
    return Database(str(tmp_path / "empty.db"))


def _active_plan_db(tmp_path) -> Database:
    """A DB whose active checkpoint is a real, persisted olympic-triathlon plan."""
    from datetime import datetime, timedelta

    db = _seeded_db(tmp_path)
    event = (datetime.now() + timedelta(weeks=9)).strftime("%Y-%m-%d")
    ps.build_plan(
        db,
        goal_type="triathlon",
        distance="olympic",
        event_date=event,
        available_hours=12,
        available_days=["mon", "tue", "wed", "thu", "sat", "sun"],
        persist=True,  # becomes the active plan get_active_plan() will return
    )
    return db


# --- Read/degraded envelopes (no active plan, no network) ------------------


def test_target_preview_route_returns_schema_envelope(tmp_path):
    out = planning_target_preview(
        goal_type="triathlon",
        distance="olympic",
        available_hours=10.0,
        available_days="mon,wed,fri",
        demand=None,
        db=_empty_db(tmp_path),
    )
    assert {"goal", "weekly_target", "breakdown", "demand", "options"} <= set(out)
    assert out["goal"]["goal_type"] and out["goal"]["distance"]
    assert isinstance(out["options"], list) and out["options"]


def test_demand_roundtrip_persists_through_router(tmp_path):
    db = _empty_db(tmp_path)
    baseline = planning_get_demand(db=db)
    assert {"demand", "options"} <= set(baseline)

    # normalize_demand_level never raises (unknown → default), so the write path
    # cannot 500; assert instead that a real, non-default level takes effect and
    # survives a fresh read through the router.
    written = planning_set_demand(DemandRequest(level="demanding"), db=db)
    assert written["demand"] == demand_profile("demanding")
    assert planning_get_demand(db=db)["demand"] == demand_profile("demanding")


def test_plan_route_reports_no_active_plan_on_empty_db(tmp_path):
    out = planning_plan(db=_empty_db(tmp_path))
    assert out["has_plan"] is False
    assert out["goal"] is None
    assert out["days"] == []
    assert "delivery" in out  # connection_info() envelope must still be present


def test_history_route_returns_empty_envelope_without_checkpoints(tmp_path):
    out = planning_history(limit=10, db=_empty_db(tmp_path))
    assert out["has_history"] is False
    assert out["items"] == []


# --- Response-returning export routes (serialization + content-type) --------


def test_export_and_plan_routes_expose_active_plan_contract(tmp_path):
    """Pin the Response-returning routes: media type, filename, body bytes.

    #246 flags that /export/ics and /export/workout return `Response`, not a
    dict, so their serialization and content-type were never exercised. One
    build amortizes plan + ics + workout + adjust assertions.
    """
    db = _active_plan_db(tmp_path)
    plan = ps.get_active_plan(db)
    assert plan and plan.get("daily_plan")

    listed = planning_plan(db=db)
    assert listed["has_plan"] is True
    # The router projects goal_type/distance straight from the plan (localized
    # labels); pin the projection shape, not the i18n wording (build_plan's job).
    assert set(listed["goal"]) == {"goal_type", "distance"}
    assert listed["goal"]["goal_type"] and listed["goal"]["distance"]
    assert listed["days"], "active plan must expose planned days"

    # Byte-equality with a re-export is flaky: ICS/TCX embed a generation
    # timestamp. Pin the stable Response contract instead — media type
    # (a constant), disposition filename, and the format's structural marker.
    ics = planning_export_ics(db=db)
    assert isinstance(ics, Response)
    assert ics.media_type == "text/calendar"
    assert ics.body.startswith(b"BEGIN:VCALENDAR")
    assert "training_plan.ics" in ics.headers["content-disposition"]

    index = ps.plan_days(plan)[0]["index"]
    workout = planning_export_workout(index=index, fmt="tcx", leg=None, db=db)
    assert isinstance(workout, Response)
    assert workout.media_type == ps.export_workout(plan, index, "tcx")["mimetype"]
    assert workout.body.lstrip().startswith(b"<?xml")
    assert '.tcx"' in workout.headers["content-disposition"]

    # /adjust with real reconciliation rows exercises the router's happy path.
    rows = ps.reconciliation(db, weeks=1)["rows"]
    adjusted = planning_adjust(AdjustRequest(rows=rows, weeks=1, persist=False), db=db)
    assert "status" in adjusted["adjustment"]
    assert adjusted["weeks"]


def test_export_routes_return_404_without_active_plan(tmp_path):
    db = _empty_db(tmp_path)
    with pytest.raises(HTTPException) as ics_exc:
        planning_export_ics(db=db)
    assert ics_exc.value.status_code == 404
    with pytest.raises(HTTPException) as workout_exc:
        planning_export_workout(index=0, fmt="tcx", leg=None, db=db)
    assert workout_exc.value.status_code == 404


# --- Real reconciliation/rebalance success (hermetic: provider forced off) --


def _force_provider_unavailable(monkeypatch) -> None:
    # Issue #194: reconciliation_at resolves _provider_reconciliation_evidence
    # against services.reconciliation's own globals, so patch it there.
    from services import reconciliation as reconciliation_service

    monkeypatch.setattr(
        reconciliation_service,
        "_provider_reconciliation_evidence",
        lambda *_a, **_k: ([], [], {"status": "unavailable", "error": "test"}),
    )


def test_reconciliation_route_returns_rows_with_provider_offline(tmp_path, monkeypatch):
    _force_provider_unavailable(monkeypatch)
    db, _plan = _reconciliation_db(tmp_path)
    out = planning_reconciliation(weeks=1, as_of="2026-07-13", include_provider=True, db=db)
    assert out["has_plan"] is True
    assert out["rows"]
    assert out["provider"]["status"] == "unavailable"


def test_rebalance_preview_route_returns_proposal_with_provider_offline(tmp_path, monkeypatch):
    _force_provider_unavailable(monkeypatch)
    db, _plan = _reconciliation_db(tmp_path)
    out = planning_rebalance_preview(
        RebalanceRequest(weeks=1, as_of="2026-07-13"), db=db
    )
    assert "reconciliation" in out and "preview" in out
    assert out["preview"]["status"] in {"proposal", "no_change"}


# --- Exception translation (monkeypatch service to raise) -------------------


def test_events_route_translates_provider_error_to_503(tmp_path, monkeypatch):
    from services.intervals_icu import IntervalsICUError

    monkeypatch.setattr(
        ps,
        "discover_intervals_events",
        lambda **_k: (_ for _ in ()).throw(IntervalsICUError("down")),
    )
    with pytest.raises(HTTPException) as exc:
        planning_events(days=180)
    assert exc.value.status_code == 503


def test_events_route_passes_read_only_envelope_through(monkeypatch):
    sentinel = {"count": 0, "events": [], "read_only": True}
    monkeypatch.setattr(ps, "discover_intervals_events", lambda **_k: sentinel)
    assert planning_events(days=30) is sentinel


def test_reconciliation_route_translates_value_error_to_422(tmp_path, monkeypatch):
    monkeypatch.setattr(
        ps,
        "reconciliation_at",
        lambda *_a, **_k: (_ for _ in ()).throw(ValueError("bad window")),
    )
    with pytest.raises(HTTPException) as exc:
        planning_reconciliation(weeks=1, as_of="nope", include_provider=False, db=_empty_db(tmp_path))
    assert exc.value.status_code == 422


def test_match_correction_route_maps_stale_to_409_and_value_to_422(tmp_path, monkeypatch):
    """The 409/422 split is not accidental: StalePlanningCheckpointError
    subclasses ValueError (planning_service.py:95), so the router's
    `except StalePlanningCheckpointError` MUST precede `except ValueError`.
    This pair pins that a stale checkpoint yields 409 (the narrow branch), not
    422 — reorder or drop the branch and a stale write silently degrades to 422.
    """
    db = _empty_db(tmp_path)
    req = MatchCorrectionRequest(base_checkpoint_id=1, session_id="s1")

    monkeypatch.setattr(
        ps,
        "record_plan_actual_match",
        lambda *_a, **_k: (_ for _ in ()).throw(ps.StalePlanningCheckpointError("stale")),
    )
    with pytest.raises(HTTPException) as stale:
        planning_record_match(req, db=db)
    assert stale.value.status_code == 409

    monkeypatch.setattr(
        ps,
        "record_plan_actual_match",
        lambda *_a, **_k: (_ for _ in ()).throw(ValueError("bad")),
    )
    with pytest.raises(HTTPException) as value:
        planning_record_match(req, db=db)
    assert value.value.status_code == 422


def test_rebalance_preview_route_translates_value_error_to_422(tmp_path, monkeypatch):
    monkeypatch.setattr(
        ps,
        "preview_weekly_rebalance",
        lambda *_a, **_k: (_ for _ in ()).throw(ValueError("bad")),
    )
    with pytest.raises(HTTPException) as exc:
        planning_rebalance_preview(RebalanceRequest(weeks=1), db=_empty_db(tmp_path))
    assert exc.value.status_code == 422


def test_rebalance_confirm_requires_fields_then_maps_stale_before_value(tmp_path, monkeypatch):
    """Own-validation (missing fields → 422) fires before any service call, and
    the same StalePlanningCheckpointError-before-ValueError ordering as
    /reconciliation/matches must hold (409 wins over 422).
    """
    db = _empty_db(tmp_path)

    # base_checkpoint_id/preview_fingerprint missing → router's own 422 branch,
    # without touching the service.
    with pytest.raises(HTTPException) as missing:
        planning_rebalance_confirm(RebalanceRequest(weeks=1), db=db)
    assert missing.value.status_code == 422

    complete = RebalanceRequest(weeks=1, base_checkpoint_id=1, preview_fingerprint="fp")
    monkeypatch.setattr(
        ps,
        "confirm_weekly_rebalance",
        lambda *_a, **_k: (_ for _ in ()).throw(ps.StalePlanningCheckpointError("stale")),
    )
    with pytest.raises(HTTPException) as stale:
        planning_rebalance_confirm(complete, db=db)
    assert stale.value.status_code == 409

    monkeypatch.setattr(
        ps,
        "confirm_weekly_rebalance",
        lambda *_a, **_k: (_ for _ in ()).throw(ValueError("bad")),
    )
    with pytest.raises(HTTPException) as value:
        planning_rebalance_confirm(complete, db=db)
    assert value.value.status_code == 422


def test_export_workout_route_translates_value_error_to_422(tmp_path, monkeypatch):
    # Plan must be present, else the 404 branch short-circuits before export.
    monkeypatch.setattr(ps, "get_active_plan", lambda _db: {"daily_plan": [object()]})
    monkeypatch.setattr(
        ps,
        "export_workout",
        lambda *_a, **_k: (_ for _ in ()).throw(ValueError("bad index")),
    )
    with pytest.raises(HTTPException) as exc:
        planning_export_workout(index=999, fmt="tcx", leg=None, db=_empty_db(tmp_path))
    assert exc.value.status_code == 422


def test_adjust_route_translates_value_error_to_422(tmp_path, monkeypatch):
    monkeypatch.setattr(
        ps,
        "apply_adjustment",
        lambda *_a, **_k: (_ for _ in ()).throw(ValueError("bad rows")),
    )
    with pytest.raises(HTTPException) as exc:
        planning_adjust(AdjustRequest(rows=[], weeks=1, persist=False), db=_empty_db(tmp_path))
    assert exc.value.status_code == 422


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
