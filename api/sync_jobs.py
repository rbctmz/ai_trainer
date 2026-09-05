"""In-process sync job lifecycle for the FastAPI web API.

Source-aware (slice-spec §5, gate M1-T7): the manager runs ONE sync job at a time
(single-flight across ALL providers — SQLite has a single writer), regardless of
``source``. A second ``start_or_get`` while a job runs returns a snapshot of the
RUNNING job with ``reused=True`` and does NOT start a second job and does NOT
change the running job's ``source``. ``source`` ('garmin' | 'intervals') is carried
through the snapshot and result so the UI and diagnostics know which provider
synced; an idle snapshot carries ``source=None`` (no provider has synced yet).
"""
from __future__ import annotations

from datetime import datetime
from threading import Lock, Thread
import uuid
from typing import Any, Callable

from api.operational_state import build_operational_state, latest_iso_from_database
from models.coach_decisions import NO_REVISIT_REQUIRED
from services.agent_log import (
    PROVIDER_AVAILABLE,
    record_agent_decision,
    scope_for_sync_days,
)
from services.sync_contracts import SyncProgressUpdate


SyncRunner = Callable[[Callable[[SyncProgressUpdate], None]], dict[str, Any]]


class SyncJobManager:
    """Small process-local sync job manager.

    This intentionally avoids external queues because the current product runs
    as a local single-user FastAPI process. The lock protects shared snapshots
    while a background thread performs the slow provider sync. The manager is
    provider-agnostic: ``source`` labels which provider a job targets and is
    surfaced additively (a running job of one source blocks a start of another —
    single-flight across all providers).
    """

    def __init__(self) -> None:
        self._lock = Lock()
        self._job: dict[str, Any] = self._idle_snapshot()

    def start_or_get(
        self,
        *,
        days: int | None,
        run_sync: SyncRunner,
        db: Any | None = None,
        demo: bool = False,
        source: str = "garmin",
    ) -> dict[str, Any]:
        with self._lock:
            if self._job.get("sync_state") == "running":
                # Single-flight across ALL providers: a second request (any source)
                # returns the RUNNING job's snapshot with reused=True — it does NOT
                # start a second job and does NOT change the running job's source.
                return self._public_snapshot_locked(db=db, demo=demo, reused=True)

            job_id = str(uuid.uuid4())[:8]
            self._job = {
                "job_id": job_id,
                "sync_state": "running",
                "status": "running",
                "started_at": _now_iso(),
                "finished_at": None,
                "days": days,
                "source": source,
                "progress": {
                    "percent": 0,
                    "message": _source_message(source, "запущена"),
                    "step_text": None,
                    "stats_message": None,
                },
                "result": None,
                "error": None,
            }

            thread = Thread(
                target=self._run_job,
                args=(job_id, run_sync, source, days, db),
                name=f"sync-{source}-{job_id}",
                daemon=True,
            )
            thread.start()
            return self._public_snapshot_locked(db=db, demo=demo, reused=False)

    def status(self, db: Any | None = None, demo: bool = False) -> dict[str, Any]:
        with self._lock:
            return self._public_snapshot_locked(db=db, demo=demo)

    def reset_for_tests(self) -> None:
        with self._lock:
            self._job = self._idle_snapshot()

    def _run_job(
        self,
        job_id: str,
        run_sync: SyncRunner,
        source: str,
        days: int | None,
        db: Any | None,
    ) -> None:
        def on_progress(update: SyncProgressUpdate) -> None:
            with self._lock:
                if self._job.get("job_id") != job_id:
                    return
                self._job["progress"] = {
                    "percent": int(update.percent),
                    "message": update.message,
                    "step_text": update.step_text,
                    "stats_message": update.stats_message,
                }

        try:
            result = run_sync(on_progress)
            sync_state = str(result.get("sync_state") or "succeeded")
            self._record_provider_sync_decision(
                db=db,
                job_id=job_id,
                source=source,
                days=days,
                sync_state=sync_state,
            )
            with self._lock:
                if self._job.get("job_id") != job_id:
                    return
                self._job.update(
                    {
                        "sync_state": sync_state,
                        "status": sync_state,
                        "finished_at": _now_iso(),
                        "progress": {
                            "percent": 100,
                            "message": result.get("title") or "Синхронизация завершена",
                            "step_text": None,
                            "stats_message": result.get("summary"),
                        },
                        "result": result,
                        "error": None,
                    }
                )
        except Exception as exc:
            message = str(exc)
            self._record_provider_sync_decision(
                db=db,
                job_id=job_id,
                source=source,
                days=days,
                sync_state="failed",
            )
            with self._lock:
                if self._job.get("job_id") != job_id:
                    return
                self._job.update(
                    {
                        "sync_state": "failed",
                        "status": "failed",
                        "finished_at": _now_iso(),
                        "progress": {
                            "percent": 100,
                            "message": _source_message(source, "завершилась ошибкой"),
                            "step_text": None,
                            "stats_message": message,
                        },
                        "result": None,
                        "error": {"message": message},
                    }
                )

    @staticmethod
    def _record_provider_sync_decision(
        *,
        db: Any | None,
        job_id: str,
        source: str,
        days: int | None,
        sync_state: str,
    ) -> None:
        """Record one terminal sync event without changing the sync result."""
        if db is None:
            return
        try:
            failed = sync_state == "failed"
            record_agent_decision(
                db,
                decision_type="Monitor",
                reason=f"Синхронизация {source}: {sync_state}.",
                decision_event_id=f"provider_sync:{source}:{job_id}",
                trigger="provider_sync",
                trigger_source=f"sync_job:{source}:{job_id}",
                scope=scope_for_sync_days(days),
                outcome="failed" if failed else "applied",
                revisit_reason=(
                    PROVIDER_AVAILABLE if failed else NO_REVISIT_REQUIRED
                ),
            )
        except Exception:
            # Sync success/failure is authoritative; an audit write outage must
            # not rewrite a completed provider result into a different state.
            return

    def _public_snapshot(self, db: Any | None = None, demo: bool = False, reused: bool = False) -> dict[str, Any]:
        with self._lock:
            return self._public_snapshot_locked(db=db, demo=demo, reused=reused)

    def _public_snapshot_locked(
        self,
        db: Any | None = None,
        demo: bool = False,
        reused: bool = False,
    ) -> dict[str, Any]:
        snapshot = dict(self._job)
        latest_data_at = latest_iso_from_database(db) if db is not None else None
        has_data = latest_data_at is not None
        sync_state = str(snapshot.get("sync_state") or "idle")
        error = snapshot.get("error")
        snapshot["reused"] = reused
        snapshot["latest_data_at"] = latest_data_at
        snapshot["operational_state"] = build_operational_state(
            db,
            demo=demo,
            has_data=has_data,
            latest_data_at=latest_data_at,
            sync_state=sync_state,
            error=error,
        )
        return snapshot

    @staticmethod
    def _idle_snapshot() -> dict[str, Any]:
        return {
            "job_id": None,
            "sync_state": "idle",
            "status": "idle",
            "started_at": None,
            "finished_at": None,
            "days": None,
            "source": None,  # no provider has synced yet (review P3: idle = None)
            "progress": None,
            "result": None,
            "error": None,
        }


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


# Provider label for generic progress/failure messages. Neither message is
# Garmin-specific anymore (review P6): the job manager is source-aware, so the
# thread name, the start message and the failure message all carry the actual
# provider. The label is pinned for both sources so the wording is stable.
_SOURCE_LABELS = {
    "garmin": "Garmin",
    "intervals": "Intervals.icu",
}


def _source_message(source: str, tail: str) -> str:
    """Generic sync message: ``"Синхронизация {label} {tail}"``. An unknown source
    falls back to a neutral word so the message is never empty."""
    label = _SOURCE_LABELS.get(source, "синхронизации")
    return f"Синхронизация {label} {tail}"


sync_job_manager = SyncJobManager()
