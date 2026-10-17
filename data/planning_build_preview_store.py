"""Single-purpose retained Planning previews; no scheduler or provider calls."""
from __future__ import annotations

from datetime import datetime, timedelta
import json
import sqlite3
from typing import Any, Callable, TYPE_CHECKING
from uuid import uuid4

from config.settings import Settings
from models.planning_build_confirmation import (
    PROTOCOL_VERSION, STORAGE_SCHEMA_VERSION, PlanningBuildPreviewError,
    PreparedPlanBuild, canonical_json, fingerprint, utc_text,
)

if TYPE_CHECKING:
    from data.database import Database

_PREPARED_FIELDS = (
    "preview_id", "schema_version", "protocol_version", "origin", "created_at", "expires_at",
    "base_checkpoint_id", "parameters_json", "dependency_context_json", "dependency_digest",
    "checkpoint_json", "response_json", "settings_write_json",
)


def create_planning_build_previews_table(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS planning_build_previews (
            preview_id TEXT PRIMARY KEY NOT NULL,
            schema_version INTEGER NOT NULL,
            protocol_version INTEGER NOT NULL,
            origin TEXT NOT NULL CHECK(origin IN ('planning_ui', 'coach')),
            state TEXT NOT NULL CHECK(state IN ('pending', 'applied', 'invalidated')),
            created_at TEXT NOT NULL, expires_at TEXT NOT NULL,
            base_checkpoint_id INTEGER NOT NULL,
            parameters_json TEXT NOT NULL, dependency_context_json TEXT NOT NULL,
            dependency_digest TEXT NOT NULL, checkpoint_json TEXT NOT NULL,
            response_json TEXT NOT NULL, settings_write_json TEXT NOT NULL,
            payload_digest TEXT NOT NULL,
            coach_proposal_id INTEGER UNIQUE,
            applied_checkpoint_id INTEGER UNIQUE, applied_at TEXT,
            applied_response_json TEXT, receipt_digest TEXT,
            CHECK (
                (state = 'applied' AND applied_checkpoint_id IS NOT NULL AND applied_at IS NOT NULL
                 AND applied_response_json IS NOT NULL AND receipt_digest IS NOT NULL)
                OR
                (state != 'applied' AND applied_checkpoint_id IS NULL AND applied_at IS NULL
                 AND applied_response_json IS NULL AND receipt_digest IS NULL)
            )
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_planning_preview_cleanup "
                 "ON planning_build_previews(state, expires_at)")


def _payload_digest(row: dict[str, Any]) -> str:
    return fingerprint({key: row[key] for key in _PREPARED_FIELDS})


def _corrupt() -> PlanningBuildPreviewError:
    return PlanningBuildPreviewError("preview_corrupt", "Предпросмотр повреждён; требуется проверка.", status=500)


def read_preview(conn: sqlite3.Connection, preview_id: str, *, origin: str) -> dict[str, Any]:
    """Integrity-checked read without cleanup or pending eligibility side effects."""
    cursor = conn.execute("SELECT * FROM planning_build_previews WHERE preview_id = ?", (preview_id,))
    values = cursor.fetchone()
    if values is None:
        raise PlanningBuildPreviewError("preview_not_found", "Предпросмотр не найден.", status=404)
    row = dict(zip((col[0] for col in cursor.description), values))
    if row["origin"] != origin:
        raise PlanningBuildPreviewError("preview_not_found", "Предпросмотр не найден.", status=404)
    try:
        if (row["schema_version"] != STORAGE_SCHEMA_VERSION or row["protocol_version"] != PROTOCOL_VERSION
                or row["state"] not in {"pending", "applied", "invalidated"}
                or (origin == "planning_ui" and row["coach_proposal_id"] is not None)
                or row["payload_digest"] != _payload_digest(row)):
            raise _corrupt()
        for name in ("parameters_json", "dependency_context_json", "checkpoint_json",
                     "response_json", "settings_write_json"):
            if not isinstance(json.loads(row[name]), dict):
                raise _corrupt()
        for name in ("created_at", "expires_at"):
            value = datetime.fromisoformat(row[name].replace("Z", "+00:00"))
            if value.tzinfo is None:
                raise _corrupt()
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, PlanningBuildPreviewError):
            raise
        raise _corrupt() from exc
    return row


def get_preview(db: Database, preview_id: str, *, origin: str) -> dict[str, Any]:
    conn = db._connect()
    try:
        return read_preview(conn, preview_id, origin=origin)
    finally:
        conn.close()


def validate_pending(row: dict[str, Any], *, now: datetime) -> None:
    """Pending eligibility only; successful receipts are not subject to expiry."""
    if row["state"] != "pending":
        raise PlanningBuildPreviewError("preview_invalidated", "Пересоберите предпросмотр.")
    expiry = datetime.fromisoformat(row["expires_at"].replace("Z", "+00:00"))
    if now >= expiry:
        raise PlanningBuildPreviewError("preview_expired", "Предпросмотр устарел — пересоберите его.", status=410)


def store_pending(
    db: Database, prepared: PreparedPlanBuild, *, origin: str, now: datetime,
    recheck: Callable[[sqlite3.Connection], str],
) -> dict[str, Any]:
    if origin not in {"planning_ui", "coach"}:
        raise ValueError("unsupported planning preview origin")
    # Validate/serialize before acquiring a write lock. A broken internal result
    # must not leave a retained token that only fails when it is read back.
    for payload in (prepared.snapshot.parameters.payload_json, prepared.snapshot.context_json,
                    prepared.checkpoint_json, prepared.response_json, prepared.settings_write_json):
        decoded = json.loads(payload)
        if not isinstance(decoded, dict):
            raise ValueError("prepared planning payload must be an object")
        canonical_json(decoded)
    ttl = int(Settings.PLANNING_BUILD_PREVIEW_TTL_SECONDS)
    retention = int(Settings.PLANNING_BUILD_PREVIEW_RETENTION_DAYS)
    if ttl <= 0 or retention <= 0:
        raise ValueError("planning preview TTL/retention must be positive")
    row = {
        "preview_id": str(uuid4()), "schema_version": STORAGE_SCHEMA_VERSION,
        "protocol_version": PROTOCOL_VERSION, "origin": origin, "state": "pending",
        "created_at": utc_text(now), "expires_at": utc_text(now + timedelta(seconds=ttl)),
        "base_checkpoint_id": prepared.snapshot.parameters.as_dict()["base_checkpoint_id"],
        "parameters_json": prepared.snapshot.parameters.payload_json,
        "dependency_context_json": prepared.snapshot.context_json,
        "dependency_digest": prepared.snapshot.dependency_digest,
        "checkpoint_json": prepared.checkpoint_json, "response_json": prepared.response_json,
        "settings_write_json": prepared.settings_write_json,
    }
    row["payload_digest"] = _payload_digest(row)
    conn = db._connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        if recheck(conn) != row["dependency_digest"]:
            raise PlanningBuildPreviewError("preview_stale", "Данные изменились — пересоберите предпросмотр.")
        # One small bounded cleanup; applied receipts are never TTL-deleted.
        conn.execute("""DELETE FROM planning_build_previews WHERE preview_id IN (
            SELECT preview_id FROM planning_build_previews
            WHERE state IN ('pending', 'invalidated') AND expires_at < ?
            ORDER BY expires_at, preview_id LIMIT 100
        )""", (utc_text(now - timedelta(days=retention)),))
        names = list(row)
        conn.execute(f"INSERT INTO planning_build_previews ({', '.join(names)}) "
                     f"VALUES ({', '.join('?' for _ in names)})", tuple(row.values()))
        conn.commit()
        return row
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
