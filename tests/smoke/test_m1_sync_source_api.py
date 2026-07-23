"""M1 (#270) §11 шаг 5 — source-aware API/job wiring (gate M1-T7).

Locks the slice-spec §5 contract on the POST/GET /api/sync source field and the
single-flight semantics across providers:

- (а) GET /api/sync carries ``source``; a pristine idle snapshot has ``source=None``
  (review P3 — no provider has synced yet, NOT a 'garmin' default).
- (б) single-flight across ALL providers: while a job of one source is RUNNING, a
  second POST of ANOTHER source returns ``reused=True``, does NOT start a second
  job, and does NOT change the running job's ``source``. The second runner is
  never called (barrier-protected).
- (в) an unknown ``source`` is rejected with 422 by the Pydantic Literal, at the
  ASGI layer before the handler (fail-fast, symmetric with PRIMARY_ACTIVITY_SOURCE).
- (г) ``POST {source: intervals}`` (idle) starts an intervals job; the snapshot
  carries ``source='intervals'`` and the result's ``source`` matches the job's.
- (д) ``POST`` with no body / no field defaults to garmin (backward compatible).

The 422 gate drives a real TestClient + FastAPI dependency-injection path; the
single-flight and source-label gates drive the router module directly (mirroring
test_sync_job_api.py) with a ``threading.Event`` barrier so the first runner is
HELD running while the second POST arrives.
"""
from __future__ import annotations

import threading
import time

import pytest
from fastapi.testclient import TestClient

from api.deps import get_database
from api.main import app
from api.routers import system as system_mod
from api.sync_jobs import sync_job_manager
from data.database import Database
from services.intervals_sync import IntervalsSyncResult
from services.sync_contracts import SyncProgressUpdate

pytestmark = pytest.mark.smoke


# --- fixtures -----------------------------------------------------------------


@pytest.fixture
def db(tmp_path):
    return Database(str(tmp_path / "sync-source.db"))


@pytest.fixture(autouse=True)
def _reset_job_manager():
    sync_job_manager.reset_for_tests()
    yield
    sync_job_manager.reset_for_tests()


def _wait_for_state(expected: str, *, db: Database, timeout: float = 5.0) -> dict:
    deadline = time.monotonic() + timeout
    last: dict = {}
    while time.monotonic() < deadline:
        last = system_mod.sync_status(db=db)
        if last.get("sync_state") == expected:
            return last
        time.sleep(0.02)
    raise AssertionError(f"timed out waiting for {expected}, last={last}")


# --- (а) GET /api/sync carries source; pristine idle = None --------------------


def test_get_sync_idle_source_is_none(db):
    """A pristine idle snapshot carries source=None — NO provider has synced yet
    (review P3). It is NOT a 'garmin' default at idle."""
    status = sync_job_manager.status(db=db)
    assert status["source"] is None
    assert status["sync_state"] == "idle"


def test_get_sync_status_carries_source_after_intervals_job(db, monkeypatch):
    """After an intervals job, the snapshot's source is 'intervals' and the
    result.source matches the job's source."""
    monkeypatch.setattr(
        system_mod.intervals_sync_service,
        "sync_intervals_data",
        lambda *a, **k: IntervalsSyncResult(new=1, updated=0, ingested=1),
    )
    monkeypatch.setattr(system_mod, "real_database", lambda: db)

    started = system_mod.sync(system_mod.SyncRequest(source="intervals"))
    assert started["source"] == "intervals"
    final = _wait_for_state("succeeded", db=db)
    assert final["source"] == "intervals"
    assert final["result"]["source"] == "intervals"


# --- (в) unknown source → 422 (TestClient, ASGI layer) ------------------------


@pytest.fixture
def client(tmp_path):
    """TestClient with a temp SQLite overriding get_database (hermetic: real
    ai_trainer.db is never opened)."""
    test_db = Database(str(tmp_path / "http_source.db"))
    app.dependency_overrides[get_database] = lambda: test_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_database, None)


@pytest.mark.parametrize("bad_source", ["apple", "GARMIN", "intervals ", "", "strava"])
def test_post_sync_rejects_unknown_source_with_422(client, bad_source):
    """An unknown source is rejected with 422 at the ASGI layer (Pydantic Literal),
    BEFORE the handler runs — symmetric with PRIMARY_ACTIVITY_SOURCE fail-fast."""
    resp = client.post("/api/sync", json={"source": bad_source})
    assert resp.status_code == 422


@pytest.mark.parametrize("source", ["garmin", "intervals"])
def test_post_sync_accepts_known_sources(client, monkeypatch, source):
    """Both known sources pass validation (else someone silently narrowed the
    Literal). The runner is stubbed so no real provider is contacted."""
    monkeypatch.setattr(system_mod.intervals_sync_service, "sync_intervals_data", lambda *a, **k: IntervalsSyncResult())
    monkeypatch.setattr(system_mod.garmin_service, "authenticate", lambda *a, **k: True)
    monkeypatch.setattr(system_mod.sync_service, "sync_garmin_data", lambda *a, **k: type("R", (), {"source": "garmin", "warnings": [], "activity_result": {"new": 0, "updated": 0, "skipped": 0}, "hrv_result": {"new": 0, "updated": 0}, "sleep_result": {"new": 0, "updated": 0}, "health_result": {"new": 0, "updated": 0}, "training_status_result": {"new": 0, "updated": 0}, "mode": "incremental", "days": 1, "totals": lambda self: {"new": 0, "updated": 0, "skipped": 0}, "success_messages": [], "details": []})())
    resp = client.post("/api/sync", json={"source": source})
    assert resp.status_code == 200
    assert resp.json()["source"] == source


# --- (б) single-flight across providers (barrier-protected) -------------------


def test_single_flight_second_source_reused_does_not_change_source(db, monkeypatch):
    """While a garmin job is RUNNING, a second POST of source=intervals returns
    reused=True, does NOT start a second job (the intervals runner is never
    called), and does NOT change the running job's source (stays garmin)."""
    monkeypatch.setattr(system_mod.Settings, "GARMIN_EMAIL", "u@example.com", raising=False)
    monkeypatch.setattr(system_mod.Settings, "GARMIN_PASSWORD", "secret", raising=False)
    monkeypatch.setattr(system_mod, "real_database", lambda: db)
    monkeypatch.setattr(system_mod.garmin_service, "authenticate", lambda *a, **k: True)

    started = threading.Event()
    release = threading.Event()

    def slow_garmin(*a, **k):
        if k.get("on_progress"):
            k["on_progress"](SyncProgressUpdate(percent=17, message="garmin"))
        started.set()
        assert release.wait(timeout=5), "test did not release slow_garmin"
        from services.sync import GarminSyncResult
        return GarminSyncResult(mode="incremental", days=1)

    monkeypatch.setattr(system_mod.sync_service, "sync_garmin_data", slow_garmin)

    # intervals runner must NEVER be called while garmin is running
    intervals_called = threading.Event()

    def intervals_should_not_run(*a, **k):
        intervals_called.set()
        return IntervalsSyncResult()

    monkeypatch.setattr(system_mod.intervals_sync_service, "sync_intervals_data", intervals_should_not_run)

    first = system_mod.sync(system_mod.SyncRequest(source="garmin"))
    assert first["source"] == "garmin"
    assert first["sync_state"] == "running"
    assert started.wait(timeout=5)

    # second POST — different source — while garmin runs
    second = system_mod.sync(system_mod.SyncRequest(source="intervals"))
    assert second["reused"] is True
    assert second["sync_state"] == "running"
    assert second["source"] == "garmin"  # unchanged — NOT switched to intervals
    assert second["job_id"] == first["job_id"]

    release.set()
    _wait_for_state("succeeded", db=db)

    assert not intervals_called.is_set(), "the intervals runner must not run while garmin holds the single-flight slot"


# --- (д) default source = garmin (backward compatible) ------------------------


def test_post_sync_without_source_defaults_to_garmin(db, monkeypatch):
    """A POST with no body / no source field starts a garmin job (backward
    compatibility — absent field = as before M1)."""
    monkeypatch.setattr(system_mod.Settings, "GARMIN_EMAIL", "u@example.com", raising=False)
    monkeypatch.setattr(system_mod.Settings, "GARMIN_PASSWORD", "secret", raising=False)
    monkeypatch.setattr(system_mod, "real_database", lambda: db)
    monkeypatch.setattr(system_mod.garmin_service, "authenticate", lambda *a, **k: True)
    from services.sync import GarminSyncResult
    monkeypatch.setattr(system_mod.sync_service, "sync_garmin_data", lambda *a, **k: GarminSyncResult(mode="incremental", days=1))

    started = system_mod.sync(system_mod.SyncRequest())  # no source field
    assert started["source"] == "garmin"
    final = _wait_for_state("succeeded", db=db)
    assert final["source"] == "garmin"


# --- payload shape: intervals job goes through the same helpers ----------------


def test_intervals_result_carries_full_payload_keys(db, monkeypatch):
    """The intervals job's result payload has the same SHAPE as a garmin job
    (operational_state attached, source present) — review P5: both branches flow
    through _sync_payload_with_operational_state + _attach_shadow_forecast."""
    monkeypatch.setattr(
        system_mod.intervals_sync_service,
        "sync_intervals_data",
        lambda *a, **k: IntervalsSyncResult(new=2, updated=1, ingested=3, source="intervals"),
    )
    monkeypatch.setattr(system_mod, "real_database", lambda: db)

    system_mod.sync(system_mod.SyncRequest(source="intervals"))
    final = _wait_for_state("succeeded", db=db)

    result = final["result"]
    # operational_state attached (same helper as garmin)
    assert "operational_state" in final
    # source flows end-to-end
    assert result["source"] == "intervals"
    assert final["source"] == "intervals"
    # intervals-specific payload keys
    for key in ("sync_state", "severity", "title", "summary", "counts", "source", "recovery_changes"):
        assert key in result
    assert result["recovery_changes"] == 0
