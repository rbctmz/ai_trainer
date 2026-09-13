"""Issue #562 M3: Intervals parity for the shared post-sync recovery capture.

The Intervals vertical must call the same provider-neutral capture exactly once,
carry the job's stable full UUID (or mint its own for direct callers), and keep a
capture failure visible as `partial` with a stable code — without rolling back
the Intervals data it just committed and without changing the public payload.
"""
from __future__ import annotations

from datetime import datetime
import logging
import sqlite3
import uuid

import pytest

from config.settings import Settings
from data.database import Database
from services.intervals_icu import IntervalsICUClient
from services.intervals_sync import build_intervals_sync_status_payload, sync_intervals_data

pytestmark = pytest.mark.smoke

NOW = datetime(2026, 7, 23)


class _FakeIntervalsClient(IntervalsICUClient):
    """Real client with a programmable network layer (same shape as M1 tests)."""

    def __init__(self, responder) -> None:
        super().__init__(api_key="test-key", athlete_id="0")
        self._responder = responder

    def _request_json(self, method, path, payload=None, params=None):
        return self._responder(method, path, params)


def _activity_row(intervals_id: str = "i_777") -> dict:
    return {
        "id": intervals_id,
        "start_date_local": "2026-07-23T08:00:00",
        "type": "Ride",
        "name": "Ride",
        "moving_time": 3600,
        "elapsed_time": 3600,
        "distance": 30000.0,
        "icu_training_load": 60,
    }


def _client() -> _FakeIntervalsClient:
    def responder(method, path, params):
        if path.endswith("/wellness"):
            return []
        return [_activity_row()]

    return _FakeIntervalsClient(responder)


def _activity_count(db: Database) -> int:
    conn = sqlite3.connect(db.db_path)
    try:
        return conn.execute("SELECT COUNT(*) FROM activities").fetchone()[0]
    finally:
        conn.close()


def _capture_spy(monkeypatch, *, block: dict | None = None, raises: Exception | None = None):
    """Replace the shared capture wrapper and record how it was called."""
    from services import recovery_analytics

    calls: list[dict] = []

    def fake_capture(database, *, capture_run_id, provider, **_kwargs):
        calls.append(
            {"database": database, "capture_run_id": capture_run_id, "provider": provider}
        )
        if raises is not None:
            raise raises
        return {
            "snapshot": {"revision": 1},
            "created": True,
            "recovery_capture": block
            or {"status": "saved_before_load", "reason": None, "revision": 1, "created": True},
        }

    monkeypatch.setattr(recovery_analytics, "capture_post_sync_recovery_state", fake_capture)
    return calls


@pytest.fixture(autouse=True)
def _isolated_settings(monkeypatch):
    monkeypatch.setattr(Settings, "INTERVALS_ICU_API_KEY", "test-key")
    monkeypatch.setattr(Settings, "ATHLETE_TIMEZONE", "Europe/Moscow")


def test_intervals_sync_uses_the_shared_capture_once_with_the_job_identity(
    tmp_path, monkeypatch
):
    db = Database(str(tmp_path / "intervals-capture.db"))
    calls = _capture_spy(monkeypatch)
    run_id = str(uuid.uuid4())

    result = sync_intervals_data(db, client=_client(), now=NOW, capture_run_id=run_id)

    assert calls == [{"database": db, "capture_run_id": run_id, "provider": "intervals"}]
    assert result.recovery_capture == {
        "status": "saved_before_load",
        "reason": None,
        "revision": 1,
        "created": True,
    }


def test_intervals_direct_call_mints_its_own_full_uuid(tmp_path, monkeypatch):
    db = Database(str(tmp_path / "intervals-direct.db"))
    calls = _capture_spy(monkeypatch)

    sync_intervals_data(db, client=_client(), now=NOW)

    assert len(calls) == 1
    minted = calls[0]["capture_run_id"]
    assert str(uuid.UUID(minted)) == minted, "direct call обязан сгенерировать полный UUID"


def test_intervals_payload_publishes_the_capture_block_since_m4(tmp_path, monkeypatch):
    """M3 держал блок внутренним; M4 публикует очищенную проекцию (см. ExecPlan).

    `job_id` здесь отсутствует намеренно: короткий display-ID штампует
    `SyncJobManager`, а этот тест вызывает builder напрямую, без job-контекста.
    """
    db = Database(str(tmp_path / "intervals-payload.db"))
    _capture_spy(
        monkeypatch,
        block={
            "provider": "intervals",
            "capture_run_id": "run-internal",
            "status": "saved_before_load",
            "reason": None,
            "eligibility_status": "eligible",
            "eligibility_reasons": [],
            "local_date": "2026-07-23",
            "observed_at_utc": "2026-07-23T05:00:00Z",
            "observed_at_local": "2026-07-23T08:00:00+03:00",
            "cutoff_at_utc": "2026-07-23T09:00:00Z",
            "snapshot_id": 7,
            "revision": 1,
            "created": True,
            "error": None,
        },
    )

    result = sync_intervals_data(db, client=_client(), now=NOW, capture_run_id="run-internal")
    payload = build_intervals_sync_status_payload(result, days=None)

    assert payload["sync_state"] == "succeeded"
    assert payload["notices"] == []
    capture = payload["recovery_capture"]
    assert capture["status"] == "saved_before_load"
    assert capture["capture_run_id"] == "run-internal"
    assert "job_id" not in capture, "display-ID добавляет только граница job'а"


def test_intervals_capture_failure_keeps_saved_data_and_marks_partial(tmp_path, monkeypatch):
    db = Database(str(tmp_path / "intervals-failed.db"))
    _capture_spy(
        monkeypatch,
        block={
            "status": "capture_failed",
            "reason": "snapshot_capture_failed",
            "revision": None,
            "created": False,
        },
    )

    result = sync_intervals_data(db, client=_client(), now=NOW, capture_run_id="run-failed")
    payload = build_intervals_sync_status_payload(result, days=None)

    # Данные Intervals сохранены, несмотря на отказ производного capture.
    assert _activity_count(db) == 1
    assert result.recovery_capture["status"] == "capture_failed"
    warnings = " | ".join(result.warnings)
    assert "snapshot_capture_failed" in warnings
    assert payload["sync_state"] == "partial"
    assert any("snapshot_capture_failed" in notice for notice in payload["notices"])


def test_intervals_defensive_capture_boundary_logs_once_and_marks_partial(
    tmp_path, monkeypatch, caplog
):
    """F3-паритет: защитная ветка Intervals логирует и не раскрывает сырой текст."""
    db = Database(str(tmp_path / "intervals-raise.db"))
    _capture_spy(monkeypatch, raises=RuntimeError("wrapper exploded at /private/athlete.db"))
    caplog.set_level(logging.WARNING, logger="services.intervals_sync")

    result = sync_intervals_data(db, client=_client(), now=NOW, capture_run_id="run-raise")
    payload = build_intervals_sync_status_payload(result, days=None)

    assert _activity_count(db) == 1
    assert result.recovery_capture["status"] == "capture_failed"
    assert result.recovery_capture["eligibility_status"] == "unknown"
    assert result.recovery_capture["eligibility_reasons"] == []
    assert result.recovery_capture["error"] == "snapshot_capture_failed"
    assert result.recovery_capture["local_date"] is None
    assert result.recovery_capture["observed_at_utc"] is None
    assert result.recovery_capture["observed_at_local"] is None
    assert result.recovery_capture["cutoff_at_utc"] is None
    assert result.recovery_capture["snapshot_id"] is None
    assert "athlete.db" not in str(result.recovery_capture)
    records = [
        record
        for record in caplog.records
        if record.name == "services.intervals_sync"
        and record.levelno == logging.WARNING
        and record.exc_info is not None
    ]
    assert len(records) == 1, [record.getMessage() for record in records]
    assert "snapshot_capture_failed" in records[0].getMessage()
    assert "athlete.db" not in records[0].getMessage()
    warnings = " | ".join(result.warnings)
    assert "snapshot_capture_failed" in warnings
    assert "athlete.db" not in warnings
    assert payload["sync_state"] == "partial"
