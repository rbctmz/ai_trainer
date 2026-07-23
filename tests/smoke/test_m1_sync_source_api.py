"""M1 (#270) §11 шаг 5 — source-aware API/job wiring (gate M1-T7).

Locks the slice-spec §5 contract on the POST/GET /api/sync source field, the
single-flight semantics across providers, the source-aware job-manager contract,
and the intervals payload classification.

Test-isolation hardening (review P1/P2): every test that can reach a provider
runner monkeypatches ``system_mod.real_database`` to a temp DB, because
``POST /api/sync`` calls ``real_database()`` DIRECTLY (not via a FastAPI
dependency). Background jobs are driven to a terminal state (succeeded/failed)
via ``_wait_for_state`` before the test ends, so no runner outlives the test. The
payload-helper gate (review P2) stubs BOTH helpers with sentinel marks and
asserts the marks land INSIDE ``final["result"]``, not just on the snapshot.
"""
from __future__ import annotations

import threading
import time

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.routers import system as system_mod
from api.sync_jobs import sync_job_manager
from data.database import Database
from services.intervals_sync import (
    IntervalsSyncResult,
    build_intervals_sync_status_payload,
)
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
    """Poll the job manager until the job reaches a terminal/expected state.

    Waiting for 'succeeded'/'failed' also serves as teardown: it guarantees the
    background job has finished before the test (and its monkeypatches) go away,
    so no runner outlives the test."""
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
    monkeypatch.setattr(system_mod, "real_database", lambda: db)
    monkeypatch.setattr(
        system_mod.intervals_sync_service,
        "sync_intervals_data",
        lambda *a, **k: IntervalsSyncResult(new=1, updated=0, ingested=1),
    )

    started = system_mod.sync(system_mod.SyncRequest(source="intervals"))
    assert started["source"] == "intervals"
    final = _wait_for_state("succeeded", db=db)
    assert final["source"] == "intervals"
    assert final["result"]["source"] == "intervals"


# --- (в) unknown source → 422 (TestClient, ASGI layer) ------------------------
# 422 is enforced at the ASGI layer BEFORE the handler, so the handler (and thus
# real_database) is never reached — this needs no provider stub.


@pytest.mark.parametrize("bad_source", ["apple", "GARMIN", "intervals ", "", "strava"])
def test_post_sync_rejects_unknown_source_with_422(bad_source):
    """An unknown source is rejected with 422 at the ASGI layer (Pydantic Literal),
    BEFORE the handler runs — symmetric with PRIMARY_ACTIVITY_SOURCE fail-fast.
    The handler (and thus real_database) is never reached, so no DB isolation is
    needed here."""
    tc = TestClient(app)
    resp = tc.post("/api/sync", json={"source": bad_source})
    assert resp.status_code == 422


# --- (г) known sources start a job and reach succeeded (hermetic) -------------
# Drives the router module directly with real_database patched to a temp DB, and
# waits for the terminal state — proving the runner used the temp DB and reached
# 'succeeded', not just an initial HTTP 200 (review P1).


def _fake_garmin_result():
    from services.sync import GarminSyncResult

    return GarminSyncResult(mode="incremental", days=1)


def test_post_sync_known_source_garmin_reaches_succeeded(db, monkeypatch):
    """source=garmin (with fake creds/auth) reaches 'succeeded' using the temp DB."""
    monkeypatch.setattr(system_mod.Settings, "GARMIN_EMAIL", "u@example.com", raising=False)
    monkeypatch.setattr(system_mod.Settings, "GARMIN_PASSWORD", "secret", raising=False)
    monkeypatch.setattr(system_mod, "real_database", lambda: db)
    monkeypatch.setattr(system_mod.garmin_service, "authenticate", lambda *a, **k: True)
    monkeypatch.setattr(system_mod.sync_service, "sync_garmin_data", lambda *a, **k: _fake_garmin_result())

    started = system_mod.sync(system_mod.SyncRequest(source="garmin"))
    assert started["source"] == "garmin"
    final = _wait_for_state("succeeded", db=db)
    assert final["sync_state"] == "succeeded"
    assert final["source"] == "garmin"
    # the live ai_trainer.db was never opened: the handler read latest_data_at from
    # the temp DB (None for an empty fresh DB — proof it was the temp one, not live).
    assert started.get("latest_data_at") is None


def test_post_sync_known_source_intervals_reaches_succeeded(db, monkeypatch):
    """source=intervals reaches 'succeeded' using the temp DB (no Garmin creds)."""
    monkeypatch.setattr(system_mod, "real_database", lambda: db)
    monkeypatch.setattr(
        system_mod.intervals_sync_service,
        "sync_intervals_data",
        lambda *a, **k: IntervalsSyncResult(new=1, ingested=1),
    )

    started = system_mod.sync(system_mod.SyncRequest(source="intervals"))
    assert started["source"] == "intervals"
    final = _wait_for_state("succeeded", db=db)
    assert final["sync_state"] == "succeeded"
    assert final["source"] == "intervals"


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
        return _fake_garmin_result()

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
    monkeypatch.setattr(system_mod.sync_service, "sync_garmin_data", lambda *a, **k: _fake_garmin_result())

    started = system_mod.sync(system_mod.SyncRequest())  # no source field
    assert started["source"] == "garmin"
    final = _wait_for_state("succeeded", db=db)
    assert final["source"] == "garmin"


# --- payload-helper gate: both helpers called, marks INSIDE result (review P2) -


def test_intervals_branch_calls_both_payload_helpers_into_result(db, monkeypatch):
    """Review P2: assert operational_state + shadow-forecast land INSIDE the
    provider RESULT (``final["result"]``), not just on the job snapshot. Both
    helpers are stubbed with sentinel marks so a regression that stops calling
    one is caught immediately."""
    monkeypatch.setattr(system_mod, "real_database", lambda: db)
    monkeypatch.setattr(
        system_mod.intervals_sync_service,
        "sync_intervals_data",
        lambda *a, **k: IntervalsSyncResult(new=2, updated=1, ingested=3, source="intervals"),
    )
    # Sentinel: _sync_payload_with_operational_state stamps a mark into the payload.
    monkeypatch.setattr(
        system_mod,
        "_sync_payload_with_operational_state",
        lambda payload, **k: {**payload, "_op_state_mark": True},
    )
    # Sentinel: _attach_shadow_forecast stamps a mark into the payload.
    monkeypatch.setattr(
        system_mod,
        "_attach_shadow_forecast",
        lambda payload, *a: {**payload, "session_quality_forecast": "MARK", "session_quality_forecast_error": None},
    )

    system_mod.sync(system_mod.SyncRequest(source="intervals"))
    final = _wait_for_state("succeeded", db=db)

    result = final["result"]
    assert result.get("_op_state_mark") is True  # _sync_payload_with_operational_state ran
    assert result.get("session_quality_forecast") == "MARK"  # _attach_shadow_forecast ran
    assert result.get("session_quality_forecast_error") is None
    assert result["source"] == "intervals"


# --- source-aware job-manager contract: messages + thread name (review P4) -----


def test_start_message_is_source_specific_for_both_providers(db, monkeypatch):
    """The job's START progress message carries the actual provider label for both
    sources (review P6/P4): no Garmin hardcode."""
    monkeypatch.setattr(system_mod, "real_database", lambda: db)
    barriers: dict[str, threading.Event] = {"g": threading.Event(), "i": threading.Event()}
    release = threading.Event()

    def slow_garmin(*a, **k):
        barriers["g"].set()
        release.wait(timeout=5)
        return _fake_garmin_result()

    def slow_intervals(*a, **k):
        barriers["i"].set()
        release.wait(timeout=5)
        return IntervalsSyncResult()

    monkeypatch.setattr(system_mod.Settings, "GARMIN_EMAIL", "u", raising=False)
    monkeypatch.setattr(system_mod.Settings, "GARMIN_PASSWORD", "p", raising=False)
    monkeypatch.setattr(system_mod, "real_database", lambda: db)
    monkeypatch.setattr(system_mod.garmin_service, "authenticate", lambda *a, **k: True)
    monkeypatch.setattr(system_mod.sync_service, "sync_garmin_data", slow_garmin)
    monkeypatch.setattr(system_mod.intervals_sync_service, "sync_intervals_data", slow_intervals)

    # Garmin start message
    g = system_mod.sync(system_mod.SyncRequest(source="garmin"))
    assert barriers["g"].wait(timeout=5)
    assert "Garmin" in g["progress"]["message"]
    assert "запущена" in g["progress"]["message"]
    release.set()
    _wait_for_state("succeeded", db=db)

    # Intervals start message
    i = system_mod.sync(system_mod.SyncRequest(source="intervals"))
    assert barriers["i"].wait(timeout=5)
    assert "Intervals.icu" in i["progress"]["message"]
    assert "запущена" in i["progress"]["message"]
    release.set()
    _wait_for_state("succeeded", db=db)


def test_failure_message_is_source_specific(db, monkeypatch):
    """The job's FAILURE progress message carries the actual provider label."""
    monkeypatch.setattr(system_mod.Settings, "GARMIN_EMAIL", "u", raising=False)
    monkeypatch.setattr(system_mod.Settings, "GARMIN_PASSWORD", "p", raising=False)
    monkeypatch.setattr(system_mod, "real_database", lambda: db)
    monkeypatch.setattr(system_mod.garmin_service, "authenticate", lambda *a, **k: True)
    monkeypatch.setattr(system_mod.sync_service, "sync_garmin_data", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))

    system_mod.sync(system_mod.SyncRequest(source="garmin"))
    failed = _wait_for_state("failed", db=db)
    assert "Garmin" in failed["progress"]["message"]
    assert "завершилась ошибкой" in failed["progress"]["message"]


def test_thread_name_is_source_aware(db, monkeypatch):
    """The background thread is named ``sync-{source}-{job_id}`` for each provider
    (review P4/P6) — not a Garmin-only hardcode."""
    captured: list[str] = []
    real_thread_init = threading.Thread.__init__

    def capture_name(self, *a, **k):
        name = k.get("name")
        if name and name.startswith("sync-"):
            captured.append(name)
        return real_thread_init(self, *a, **k)

    monkeypatch.setattr(system_mod.Settings, "GARMIN_EMAIL", "u", raising=False)
    monkeypatch.setattr(system_mod.Settings, "GARMIN_PASSWORD", "p", raising=False)
    monkeypatch.setattr(system_mod, "real_database", lambda: db)
    monkeypatch.setattr(system_mod.garmin_service, "authenticate", lambda *a, **k: True)
    monkeypatch.setattr(system_mod.sync_service, "sync_garmin_data", lambda *a, **k: _fake_garmin_result())
    monkeypatch.setattr(
        system_mod.intervals_sync_service, "sync_intervals_data", lambda *a, **k: IntervalsSyncResult()
    )
    monkeypatch.setattr(threading.Thread, "__init__", capture_name)

    g = system_mod.sync(system_mod.SyncRequest(source="garmin"))
    _wait_for_state("succeeded", db=db)
    assert any(n == f"sync-garmin-{g['job_id']}" for n in captured)

    i = system_mod.sync(system_mod.SyncRequest(source="intervals"))
    _wait_for_state("succeeded", db=db)
    assert any(n == f"sync-intervals-{i['job_id']}" for n in captured)


# --- payload classification matrix (review P3) --------------------------------


def _result(**kw) -> IntervalsSyncResult:
    base = dict(source="intervals", window_start="2026-04-24", window_end="2026-07-23", bootstrapped=False, halted=False, cursor_value="2026-07-23")
    base.update(kw)
    return IntervalsSyncResult(**base)


def test_payload_halted_is_partial_warning():
    p = build_intervals_sync_status_payload(_result(halted=True, warnings=["429"]))
    assert p["sync_state"] == "partial" and p["severity"] == "warning"


def test_payload_warnings_without_halt_is_partial_warning():
    p = build_intervals_sync_status_payload(_result(warnings=["slow"]))
    assert p["sync_state"] == "partial" and p["severity"] == "warning"


def test_payload_new_activities_is_succeeded_success():
    p = build_intervals_sync_status_payload(_result(new=2, updated=1, ingested=3))
    assert p["sync_state"] == "succeeded" and p["severity"] == "success"
    assert p["activity_changes"] == 3


def test_payload_no_changes_is_succeeded_info():
    p = build_intervals_sync_status_payload(_result())
    assert p["sync_state"] == "succeeded" and p["severity"] == "info"


@pytest.mark.parametrize(
    "kw",
    [
        dict(new=5, updated=2, ingested=7, skipped=0),
        dict(new=0, updated=0, ingested=0),
        dict(halted=True, warnings=["x"], new=3, ingested=3),
    ],
)
def test_payload_preserves_counts_source_window_cursor(kw):
    r = _result(**kw)
    p = build_intervals_sync_status_payload(r)
    assert p["counts"] == {"new": r.new, "updated": r.updated, "skipped": r.skipped}
    assert p["source"] == "intervals"
    assert p["window_start"] == r.window_start
    assert p["window_end"] == r.window_end
    assert p["cursor_value"] == r.cursor_value
    assert p["recovery_changes"] == 0
