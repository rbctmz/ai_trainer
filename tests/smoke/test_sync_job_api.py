"""Contributor-safe tests for the async Garmin sync job API contract."""
from __future__ import annotations

import threading
import time

from data.database import Database
from services import sync as sync_service


def _sync_result(warnings: list[str] | None = None) -> sync_service.GarminSyncResult:
    return sync_service.GarminSyncResult(
        activity_result={"new": 1, "updated": 0, "skipped": 0},
        hrv_result={"new": 0, "updated": 0},
        sleep_result={"new": 0, "updated": 0},
        health_result={"new": 0, "updated": 0},
        training_status_result={"new": 0, "updated": 0},
        warnings=warnings or [],
        mode="incremental",
        days=1,
    )


def test_post_sync_starts_background_job_and_reuses_running_job(tmp_path, monkeypatch):
    from api.routers import system as system_mod
    from api.sync_jobs import sync_job_manager

    sync_job_manager.reset_for_tests()
    db = Database(str(tmp_path / "sync.db"))
    started = threading.Event()
    release = threading.Event()
    calls: list[int | None] = []

    def fake_sync(_state, days=None, on_progress=None):
        calls.append(days)
        if on_progress:
            on_progress(sync_service.SyncProgressUpdate(percent=17, message="activities"))
        started.set()
        assert release.wait(timeout=5), "test did not release fake sync"
        return _sync_result()

    monkeypatch.setattr(system_mod.Settings, "GARMIN_EMAIL", "user@example.com", raising=False)
    monkeypatch.setattr(system_mod.Settings, "GARMIN_PASSWORD", "secret", raising=False)
    monkeypatch.setattr(system_mod, "real_database", lambda: db)
    monkeypatch.setattr(system_mod.garmin_service, "authenticate", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(system_mod.sync_service, "sync_garmin_data", fake_sync)

    first = system_mod.sync(system_mod.SyncRequest(days=1))
    assert first["sync_state"] == "running"
    assert first["job_id"]
    assert started.wait(timeout=5)

    status = system_mod.sync_status(db=db)
    assert status["sync_state"] == "running"
    assert status["job_id"] == first["job_id"]
    assert status["progress"]["percent"] == 17
    assert status["operational_state"]["sync_state"] == "running"

    second = system_mod.sync(system_mod.SyncRequest(days=30))
    assert second["sync_state"] == "running"
    assert second["job_id"] == first["job_id"]
    assert second["reused"] is True
    assert calls == [1]

    release.set()
    _wait_for_state(system_mod, "succeeded", db=db)
    final = system_mod.sync_status(db=db)
    assert final["job_id"] == first["job_id"]
    assert final["sync_state"] == "succeeded"
    assert final["result"]["counts"]["new"] == 1
    assert final["operational_state"]["sync_state"] == "succeeded"


def test_sync_job_exposes_partial_and_failed_states(tmp_path, monkeypatch):
    from api.routers import system as system_mod
    from api.sync_jobs import sync_job_manager

    sync_job_manager.reset_for_tests()
    db = Database(str(tmp_path / "sync.db"))
    monkeypatch.setattr(system_mod.Settings, "GARMIN_EMAIL", "user@example.com", raising=False)
    monkeypatch.setattr(system_mod.Settings, "GARMIN_PASSWORD", "secret", raising=False)
    monkeypatch.setattr(system_mod, "real_database", lambda: db)
    monkeypatch.setattr(system_mod.garmin_service, "authenticate", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(
        system_mod.sync_service,
        "sync_garmin_data",
        lambda *_args, **_kwargs: _sync_result(warnings=["sleep unavailable"]),
    )

    started = system_mod.sync(system_mod.SyncRequest(days=1))
    partial = _wait_for_state(system_mod, "partial", db=db)
    assert partial["job_id"] == started["job_id"]
    assert partial["result"]["severity"] == "warning"
    assert partial["operational_state"]["sync_state"] == "partial"

    sync_job_manager.reset_for_tests()

    def fail_sync(*_args, **_kwargs):
        raise RuntimeError("Garmin 429")

    monkeypatch.setattr(system_mod.sync_service, "sync_garmin_data", fail_sync)
    failed_started = system_mod.sync(system_mod.SyncRequest(days=1))
    failed = _wait_for_state(system_mod, "failed", db=db)
    assert failed["job_id"] == failed_started["job_id"]
    assert failed["error"]["message"] == "Sync failed: Garmin 429"
    assert failed["operational_state"]["status"] == "error"
    assert failed["operational_state"]["sync_state"] == "failed"


def _wait_for_state(system_mod, expected: str, *, db: Database, timeout: float = 5.0) -> dict:
    deadline = time.monotonic() + timeout
    last = {}
    while time.monotonic() < deadline:
        last = system_mod.sync_status(db=db)
        if last.get("sync_state") == expected:
            return last
        time.sleep(0.02)
    raise AssertionError(f"timed out waiting for {expected}, last={last}")
