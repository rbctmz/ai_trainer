"""Issue #562 M4: public `recovery_capture` contract over the sync-job API.

Terminal `POST`/`GET /api/sync` must expose a *clean* projection of the internal
capture block for both providers: known fields only, the job's short display id
stamped at the manager boundary, stable reason/error codes, nullable dates for a
failed capture, and never the wrapper result (which carries `episode_refresh`
with raw exception text).
"""
from __future__ import annotations

import json
import time
import uuid

import pytest
from fastapi.testclient import TestClient

from api.deps import get_database
from api.main import app
from data.database import Database
from services import sync as sync_service

pytestmark = pytest.mark.smoke

TERMINAL_STATES = {"succeeded", "partial", "failed"}

# Публичный контракт блока: только эти поля и ничего больше.
EXPECTED_KEYS = {
    "provider",
    "capture_run_id",
    "job_id",
    "status",
    "reason",
    "eligibility_status",
    "eligibility_reasons",
    "local_date",
    "observed_at_utc",
    "observed_at_local",
    "cutoff_at_utc",
    "snapshot_id",
    "revision",
    "created",
    "error",
}


def _internal_block(**overrides) -> dict:
    """Внутренний блок так, как его отдаёт обёртка: с лишними служебными полями."""
    block = {
        "provider": "garmin",
        "capture_run_id": "11111111-2222-3333-4444-555555555555",
        "status": "saved_before_load",
        "reason": None,
        "eligibility_status": "eligible",
        "eligibility_reasons": [],
        "local_date": "2026-07-23",
        "observed_at_utc": "2026-07-23T05:00:00Z",
        "observed_at_local": "2026-07-23T08:00:00+03:00",
        "cutoff_at_utc": "2026-07-23T09:00:00Z",
        "snapshot_id": 41,
        "revision": 1,
        "created": True,
        "error": None,
        # Служебные поля, которые не должны попасть в публичный ответ.
        "episode_refresh": {
            "error": "episode repair failed at /private/athlete.db",
            "created": 0,
        },
        "snapshot": {"score": 72.0},
        "unexpected_key": "secret-internal-value",
    }
    block.update(overrides)
    return block


def _client(db: Database) -> TestClient:
    app.dependency_overrides[get_database] = lambda demo=False: db
    return TestClient(app)


def _wait_terminal(client: TestClient, *, timeout_s: float = 10.0) -> dict:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        payload = client.get("/api/sync").json()
        if str(payload.get("sync_state")) in TERMINAL_STATES:
            return payload
        time.sleep(0.02)
    raise AssertionError("sync job did not reach a terminal state")


@pytest.fixture(autouse=True)
def _reset_jobs():
    from api.sync_jobs import sync_job_manager

    sync_job_manager.reset_for_tests()
    yield
    app.dependency_overrides.pop(get_database, None)


def test_terminal_garmin_payload_carries_clean_capture(tmp_path, monkeypatch):
    from api.routers import system as system_mod

    db = Database(str(tmp_path / "garmin-api.db"))
    block = _internal_block()
    seen_run_ids: list[str | None] = []

    def fake_sync(_state, days=None, on_progress=None, capture_run_id=None):
        seen_run_ids.append(capture_run_id)
        return sync_service.GarminSyncResult(recovery_capture=block)

    monkeypatch.setattr(system_mod.Settings, "GARMIN_EMAIL", "user@example.com", raising=False)
    monkeypatch.setattr(system_mod.Settings, "GARMIN_PASSWORD", "secret", raising=False)
    monkeypatch.setattr(system_mod.garmin_service, "authenticate", lambda *_a, **_k: True)
    monkeypatch.setattr(system_mod, "real_database", lambda: db)
    monkeypatch.setattr(system_mod.sync_service, "sync_garmin_data", fake_sync)

    client = _client(db)
    started = client.post("/api/sync", json={"days": 1, "source": "garmin"}).json()
    payload = _wait_terminal(client)

    capture = payload["result"]["recovery_capture"]
    assert set(capture) == EXPECTED_KEYS, sorted(set(capture) ^ EXPECTED_KEYS)
    assert capture["job_id"] == payload["job_id"] == started["job_id"]
    # Научная идентичность не подменяется коротким display-ID.
    assert capture["capture_run_id"] == block["capture_run_id"]
    assert capture["capture_run_id"] != capture["job_id"]
    assert seen_run_ids and seen_run_ids[0] != started["job_id"]
    assert str(uuid.UUID(seen_run_ids[0])) == seen_run_ids[0]

    raw = json.dumps(payload)
    assert "episode_refresh" not in raw
    assert "athlete.db" not in raw
    assert "secret-internal-value" not in raw


def test_terminal_intervals_payload_carries_clean_capture(tmp_path, monkeypatch):
    from api.routers import system as system_mod
    from services.intervals_sync import IntervalsSyncResult

    db = Database(str(tmp_path / "intervals-api.db"))
    block = _internal_block(provider="intervals")
    seen_run_ids: list[str | None] = []

    def fake_sync(_database, *, days=None, now=None, on_progress=None, client=None,
                  chunk_days=None, capture_run_id=None):
        seen_run_ids.append(capture_run_id)
        return IntervalsSyncResult(new=1, recovery_capture=block)

    monkeypatch.setattr(system_mod, "real_database", lambda: db)
    monkeypatch.setattr(
        system_mod.intervals_sync_service, "sync_intervals_data", fake_sync
    )

    client = _client(db)
    started = client.post("/api/sync", json={"days": 1, "source": "intervals"}).json()
    payload = _wait_terminal(client)

    capture = payload["result"]["recovery_capture"]
    assert set(capture) == EXPECTED_KEYS
    assert capture["provider"] == "intervals"
    assert capture["job_id"] == payload["job_id"] == started["job_id"]
    assert seen_run_ids and seen_run_ids[0] != started["job_id"]
    raw = json.dumps(payload)
    assert "episode_refresh" not in raw
    assert "athlete.db" not in raw


def test_failed_capture_variant_keeps_nulls_and_stable_codes(tmp_path, monkeypatch):
    from api.routers import system as system_mod

    db = Database(str(tmp_path / "failed-api.db"))
    block = _internal_block(
        status="capture_failed",
        reason="snapshot_capture_failed",
        error="snapshot_capture_failed",
        local_date=None,
        observed_at_utc=None,
        observed_at_local=None,
        cutoff_at_utc=None,
        snapshot_id=None,
        revision=None,
        created=False,
    )

    def fake_sync(_state, days=None, on_progress=None, capture_run_id=None):
        return sync_service.GarminSyncResult(recovery_capture=block)

    monkeypatch.setattr(system_mod.Settings, "GARMIN_EMAIL", "user@example.com", raising=False)
    monkeypatch.setattr(system_mod.Settings, "GARMIN_PASSWORD", "secret", raising=False)
    monkeypatch.setattr(system_mod.garmin_service, "authenticate", lambda *_a, **_k: True)
    monkeypatch.setattr(system_mod, "real_database", lambda: db)
    monkeypatch.setattr(system_mod.sync_service, "sync_garmin_data", fake_sync)

    client = _client(db)
    client.post("/api/sync", json={"days": 1, "source": "garmin"})
    payload = _wait_terminal(client)

    capture = payload["result"]["recovery_capture"]
    assert capture["status"] == "capture_failed"
    # Даты не выдумываются ради типа: null доезжает до контракта как null.
    assert capture["local_date"] is None
    assert capture["observed_at_utc"] is None
    assert capture["observed_at_local"] is None
    assert capture["cutoff_at_utc"] is None
    assert capture["reason"] == "snapshot_capture_failed"
    assert capture["error"] == "snapshot_capture_failed"


def test_projection_whitelists_fields_and_passes_none_through():
    from services.recovery_analytics import project_recovery_capture

    assert project_recovery_capture(None) is None
    assert project_recovery_capture({}) is None

    projected = project_recovery_capture(_internal_block())

    # Сервисная проекция не знает job'а: display-ID штампует SyncJobManager.
    assert set(projected) == EXPECTED_KEYS - {"job_id"}
    assert projected["episode_refresh"] if "episode_refresh" in projected else True
    assert "episode_refresh" not in projected
    assert "snapshot" not in projected
    assert "unexpected_key" not in projected
    assert projected["capture_run_id"] == "11111111-2222-3333-4444-555555555555"
    assert projected["revision"] == 1


def test_builder_without_capture_keeps_the_key_absent():
    """Провайдер без блока не получает вымышленный блок."""
    result = sync_service.GarminSyncResult()

    payload = sync_service.build_sync_status_payload(result)

    assert "recovery_capture" not in payload
