"""Single-purpose retained Planning previews; no scheduler or provider calls."""
from __future__ import annotations

from datetime import datetime, timedelta
import json
import sqlite3
from typing import Any, Callable, TYPE_CHECKING
from uuid import uuid4

from config.settings import Settings
from models.planning_build_confirmation import (
    PlanningBuildPreviewError,
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
    columns = {row[1] for row in conn.execute("PRAGMA table_info(planning_build_previews)")}
    if "cycle_context_json" not in columns:
        conn.execute("ALTER TABLE planning_build_previews ADD COLUMN cycle_context_json TEXT")


def _payload_digest(row: dict[str, Any]) -> str:
    fields = (*_PREPARED_FIELDS, "cycle_context_json") if row["schema_version"] == 2 else _PREPARED_FIELDS
    return fingerprint({key: row[key] for key in fields})


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
        if ((row["schema_version"], row["protocol_version"]) not in {(1, 1), (2, 2)}
                or row["state"] not in {"pending", "applied", "invalidated"}
                or (origin == "planning_ui" and row["coach_proposal_id"] is not None)
                or row["payload_digest"] != _payload_digest(row)):
            raise _corrupt()
        receipt_fields = ("applied_checkpoint_id", "applied_at", "applied_response_json", "receipt_digest")
        if row["state"] == "applied":
            if any(row[key] is None for key in receipt_fields):
                raise _corrupt()
        elif any(row[key] is not None for key in receipt_fields):
            raise _corrupt()
        for name in ("parameters_json", "dependency_context_json", "checkpoint_json",
                     "response_json", "settings_write_json"):
            decoded = json.loads(row[name])
            if not isinstance(decoded, dict):
                raise _corrupt()
            canonical_json(decoded)
        if row["schema_version"] == 2:
            lifecycle = json.loads(row["cycle_context_json"])
            if (not isinstance(lifecycle, dict)
                    or lifecycle != json.loads(row["dependency_context_json"]).get("lifecycle")
                    or lifecycle != json.loads(row["response_json"]).get("lifecycle")):
                raise _corrupt()
            canonical_json(lifecycle)
        elif row["cycle_context_json"] is not None:
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
    if row["protocol_version"] == 1:
        raise PlanningBuildPreviewError("preview_required", "Нужен новый предпросмотр с контекстом цикла.")
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
    lifecycle = prepared.snapshot.context().get("lifecycle")
    version = 2 if lifecycle else 1
    row = {
        "preview_id": str(uuid4()), "schema_version": version,
        "protocol_version": version, "origin": origin, "state": "pending",
        "created_at": utc_text(now), "expires_at": utc_text(now + timedelta(seconds=ttl)),
        "base_checkpoint_id": prepared.snapshot.parameters.as_dict()["base_checkpoint_id"],
        "parameters_json": prepared.snapshot.parameters.payload_json,
        "dependency_context_json": prepared.snapshot.context_json,
        "dependency_digest": prepared.snapshot.dependency_digest,
        "checkpoint_json": prepared.checkpoint_json, "response_json": prepared.response_json,
        "settings_write_json": prepared.settings_write_json,
    }
    row["cycle_context_json"] = canonical_json(lifecycle) if lifecycle else None
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


_RECEIPT_FIELDS = (
    "payload_digest", "coach_proposal_id", "applied_checkpoint_id", "applied_at", "applied_response_json",
)


def _receipt_digest(row: dict[str, Any]) -> str:
    return fingerprint({key: row[key] for key in _RECEIPT_FIELDS})


def preview_response(row: dict[str, Any]) -> dict[str, Any]:
    """Public frozen projection shared by preparation and receipt validation."""
    return {**json.loads(row["response_json"]), "parameters": json.loads(row["parameters_json"]),
            "confirmation": {"protocol_version": row["protocol_version"], "preview_id": row["preview_id"],
                             "expires_at": row["expires_at"], "status": "pending",
                             "replayed": False, "is_current": None}}


def _applied_response(row: dict[str, Any], checkpoint_id: int) -> dict[str, Any]:
    result = preview_response(row)
    return {**result, "plan_id": str(checkpoint_id), "confirmation_required": False,
            "confirmation": {**result["confirmation"], "status": "applied", "is_current": True}}


def _read_receipt(conn: sqlite3.Connection, row: dict[str, Any]) -> dict[str, Any]:
    try:
        if row["receipt_digest"] != _receipt_digest(row):
            raise _corrupt()
        applied_at = datetime.fromisoformat(row["applied_at"].replace("Z", "+00:00"))
        if applied_at.tzinfo is None or type(row["applied_checkpoint_id"]) is not int or row["applied_checkpoint_id"] <= 0:
            raise _corrupt()
        result = json.loads(row["applied_response_json"])
        if result != _applied_response(row, row["applied_checkpoint_id"]):
            raise _corrupt()
    except (ValueError, TypeError, KeyError) as exc:
        if isinstance(exc, PlanningBuildPreviewError):
            raise
        raise _corrupt() from exc
    if conn.execute("SELECT id FROM planning_checkpoints WHERE id=?", (row["applied_checkpoint_id"],)).fetchone() is None:
        raise PlanningBuildPreviewError("preview_checkpoint_missing", "Сохранённый план не найден; требуется проверка.")
    selected = conn.execute("""SELECT c.current_checkpoint_id FROM planning_cycle_state s
        JOIN planning_cycles c ON c.id=s.current_cycle_id
        JOIN planning_cycle_versions v ON v.checkpoint_id=c.current_checkpoint_id AND v.cycle_id=c.id
        WHERE s.id=1 AND c.status='open'""").fetchone()
    result["confirmation"] = {**result["confirmation"], "replayed": True,
                              "is_current": selected is not None and selected[0] == row["applied_checkpoint_id"]}
    return result


def _coach_proposal(conn: sqlite3.Connection, proposal_id: int) -> dict[str, Any]:
    cursor = conn.execute("SELECT action,status,params_json,result_json,applied_checkpoint_id FROM coach_proposals WHERE id=?", (proposal_id,))
    values = cursor.fetchone()
    if values is None or values[0] != "build_plan":
        raise PlanningBuildPreviewError("preview_not_found", "Предпросмотр не найден.", status=404)
    try:
        params = json.loads(values[2])
        if not isinstance(params, dict):
            raise _corrupt()
        canonical_json(params)
    except (TypeError, ValueError) as exc:
        if isinstance(exc, PlanningBuildPreviewError):
            raise
        raise _corrupt() from exc
    if not params.get("preview_id"):
        raise PlanningBuildPreviewError("preview_required", "Нужен новый предпросмотр плана в Коуче.")
    return {"status": values[1], "preview_id": params["preview_id"],
            "result_json": values[3], "applied_checkpoint_id": values[4]}


def bind_coach_preview(conn: sqlite3.Connection, proposal: dict[str, Any], *, now: datetime) -> None:
    """Bind only the persisted/deduplicated card, in its insertion transaction."""
    saved = _coach_proposal(conn, proposal["id"])
    row = read_preview(conn, saved["preview_id"], origin="coach")
    if row["coach_proposal_id"] == proposal["id"]:
        return  # dedup reuses the existing card/summary, never the new orphan
    if row["coach_proposal_id"] is not None:
        raise PlanningBuildPreviewError("preview_not_found", "Предпросмотр не найден.", status=404)
    validate_pending(row, now=now)
    if saved["status"] != "pending":
        raise PlanningBuildPreviewError("proposal_not_pending", "Предложение уже закрыто; нужен новый предпросмотр.")
    conn.execute("UPDATE planning_build_previews SET coach_proposal_id=? WHERE preview_id=?",
                 (proposal["id"], saved["preview_id"]))


def apply_preview(
    db: Database, preview_id: str, *, origin: str, now: Callable[[], datetime],
    recheck: Callable[[sqlite3.Connection, dict[str, Any]], bool],
    validate_response: Callable[[dict[str, Any]], None], proposal_id: int | None = None,
) -> dict[str, Any]:
    """Publish frozen data and receipt in one transaction; replay never reactivates."""
    conn = db._connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        proposal = None
        if origin == "coach":
            if proposal_id is None:
                raise PlanningBuildPreviewError("preview_not_found", "Предпросмотр не найден.", status=404)
            proposal = _coach_proposal(conn, proposal_id)
            if proposal["preview_id"] != preview_id:
                raise PlanningBuildPreviewError("preview_not_found", "Предпросмотр не найден.", status=404)
        row = read_preview(conn, preview_id, origin=origin)
        if origin not in {"planning_ui", "coach"} or (proposal is not None and row["coach_proposal_id"] != proposal_id):
            raise PlanningBuildPreviewError("preview_not_found", "Предпросмотр не найден.", status=404)
        if row["state"] == "applied":
            if proposal is not None and (proposal["status"] != "approved"
                    or proposal["applied_checkpoint_id"] != row["applied_checkpoint_id"]
                    or proposal["result_json"] != row["applied_response_json"]):
                raise _corrupt()
            result = _read_receipt(conn, row)
            validate_response(result)
            conn.rollback()  # read-only replay releases the writer lock
            return result
        if proposal is not None and proposal["status"] != "pending":
            raise PlanningBuildPreviewError("proposal_not_pending", "Предложение уже закрыто; нужен новый предпросмотр.")
        # Validate retained public/parameter shape before eligibility checks, so
        # malformed stored data cannot be mistaken for a changed dependency.
        validate_response(preview_response(row))
        instant = now()  # expiry is evaluated after lock acquisition
        validate_pending(row, now=instant)
        from models.planning_entry_publication import validate_retained_entry
        validate_retained_entry(row)
        retained_plan = json.loads(row["checkpoint_json"]).get("goal_plan_snapshot")
        if not isinstance(retained_plan, dict):
            raise _corrupt()
        if ("build_readiness" not in json.loads(row["response_json"])
                and "build_readiness" not in retained_plan):
            raise PlanningBuildPreviewError("preview_required", "Нужен новый предпросмотр с проверкой готовности.")
        if not recheck(conn, row):
            conn.execute("UPDATE planning_build_previews SET state='invalidated' WHERE preview_id=?", (preview_id,))
            conn.commit()
            raise PlanningBuildPreviewError("preview_stale", "Данные изменились — пересоберите предпросмотр.")
        from models.planning_build_readiness import validate_retained_readiness
        validate_retained_readiness(row)
        checkpoint = json.loads(row["checkpoint_json"])
        settings = json.loads(row["settings_write_json"])
        if set(settings) - {"planning_demand_level", "planning_profile"} or not checkpoint:
            raise _corrupt()
        saved = db._insert_planning_checkpoint(conn, checkpoint, payload=row["checkpoint_json"])
        if row["schema_version"] == 2:
            from data.planning_cycles import publish_cycle_checkpoint
            publish_cycle_checkpoint(conn, json.loads(row["cycle_context_json"]), checkpoint,
                                     saved["id"], utc_text(instant))
        result = _applied_response(row, saved["id"])
        validate_response(result)  # serialization/schema failure must precede commit
        for key, value in settings.items():
            if key == "planning_profile":
                value = canonical_json({**value, "updated_at": utc_text(instant)})
            conn.execute(
                "INSERT INTO user_settings(key,value,updated_at) VALUES(?,?,CURRENT_TIMESTAMP) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=CURRENT_TIMESTAMP",
                (key, value),
            )
        row.update(applied_checkpoint_id=saved["id"], applied_at=utc_text(instant),
                   applied_response_json=canonical_json(result))
        conn.execute(
            "UPDATE planning_build_previews SET state='applied', applied_checkpoint_id=?, applied_at=?, "
            "applied_response_json=?, receipt_digest=? WHERE preview_id=?",
            (row["applied_checkpoint_id"], row["applied_at"], row["applied_response_json"], _receipt_digest(row), preview_id),
        )
        if proposal is not None:
            conn.execute(
                "UPDATE coach_proposals SET status='approved', result_json=?, error=NULL, resolved_at=?, "
                "applied_checkpoint_id=? WHERE id=?",
                (row["applied_response_json"], row["applied_at"], row["applied_checkpoint_id"], proposal_id),
            )
        conn.commit()
        return result
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
