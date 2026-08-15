"""Smoke tests for Phase 3 endpoints: sleep + demo + routes.

Demo is exercised against a temp DB so the real cache is never touched.
"""
from __future__ import annotations

import importlib

import pytest

from data.database import Database


def test_phase3_routes_registered():
    main = importlib.import_module("api.main")
    paths = set(main.app.openapi()["paths"].keys())
    assert {"/api/sleep/summary", "/api/sync", "/api/demo/seed", "/api/demo/clear"} <= paths


def test_sleep_empty_envelope(tmp_path):
    from api.routers.sleep import sleep_summary

    out = sleep_summary(days=30, db=Database(str(tmp_path / "e.db")))
    assert out["has_data"] is False
    assert out["trend"] == []


def test_demo_seed_isolated(tmp_path):
    """Demo seeding populates its own DB and must not touch another DB."""
    from api.deps import make_headless_state
    from services import demo_mode as demo_service

    real = Database(str(tmp_path / "real.db"))
    real.save_activities(
        [
            {
                "activity_id": "real1",
                "date": "2026-06-20",
                "sport": "cycling",
                "duration_minutes": 60,
                "distance_km": 30.0,
                "tss": 55.0,
            }
        ]
    )

    demo_db = Database(str(tmp_path / "demo.db"))
    counts = demo_service.activate_demo_mode(make_headless_state(database=demo_db))

    assert counts["activities"] > 0
    assert len(demo_db.get_activities(60)) > 0
    # real DB untouched
    assert len(real.get_activities(60)) == 1


def test_sleep_with_demo_data(tmp_path):
    from api.deps import make_headless_state
    from api.routers.sleep import sleep_summary
    from services import demo_mode as demo_service

    demo_db = Database(str(tmp_path / "demo.db"))
    demo_service.activate_demo_mode(make_headless_state(database=demo_db))

    out = sleep_summary(days=30, db=demo_db)
    assert out["has_data"] is True
    assert out["latest"] is not None
    assert out["latest"]["date_label"].count(".") == 2
    assert out["latest"]["stages_list"][0]["label"] == "Глубокий"
    assert len(out["trend"]) >= 1
    assert out["trend"][0]["date_label"].count(".") == 2


def test_get_database_demo_routing(monkeypatch, tmp_path):
    import api.deps as deps

    monkeypatch.setattr(deps, "DEMO_DB_PATH", str(tmp_path / "demo.db"))
    deps._reset_db_cache()
    real = deps.get_database(demo=False)
    demo = deps.get_database(demo=True)
    assert real.db_path != demo.db_path


def test_demo_seed_and_clear_via_router(monkeypatch, tmp_path):
    """Issue #242: POST /api/demo/seed and /api/demo/clear were only
    covered indirectly (via `services.demo_mode.activate_demo_mode` called
    directly in `test_demo_seed_isolated` above) -- the router's own
    functions, response shape, and 500-wrapping were never called."""
    import api.deps as deps
    from api.routers import system as system_mod

    monkeypatch.setattr(deps, "DEMO_DB_PATH", str(tmp_path / "demo_router.db"))
    deps._reset_db_cache()

    seeded = system_mod.demo_seed()
    assert seeded["seeded"] is True
    assert seeded["counts"]["activities"] > 0
    assert len(deps.demo_database().get_activities(60)) > 0

    cleared = system_mod.demo_clear()
    assert cleared["cleared"] is True
    assert len(deps.demo_database().get_activities(60)) == 0


def test_demo_clear_without_prior_seed_is_idempotent_no_500(monkeypatch, tmp_path):
    import api.deps as deps
    from api.routers import system as system_mod

    monkeypatch.setattr(deps, "DEMO_DB_PATH", str(tmp_path / "demo_never_seeded.db"))
    deps._reset_db_cache()

    result = system_mod.demo_clear()
    assert result["cleared"] is True


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
