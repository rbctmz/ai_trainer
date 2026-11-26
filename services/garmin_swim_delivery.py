"""One explicitly confirmed Garmin send for a pinned authored assignment."""

from datetime import datetime, timedelta, timezone
import json
import re
import sqlite3
from uuid import UUID

from config.settings import Settings
from data.database import Database
from models.garmin_swim_delivery import project_garmin_swim
from models.planning_build_confirmation import (
    PlanningBuildPreviewError, canonical_json, fingerprint, utc_text,
)
from models.swim_delivery import SwimDeliveryUnsupported
from services import garmin_swim_mcp
from services.snapshot_runtime import mark_committed
from services.swim_calendar import delivery_source
from services.swim_delivery import _UNSUPPORTED, _transaction

_MESSAGES = {
    **_UNSUPPORTED,
    "unsupported_pool_length": "Прямая отправка поддерживает бассейн 25 или 50 м.",
    "garmin_name_too_long": "Название превышает 80 символов.",
    "garmin_cue_too_long": "Подсказка превышает 200 символов.",
    "garmin_unsupported_rest": "Для Garmin нужен явно заданный таймер отдыха от 1 до 3600 с.",
    "garmin_unsupported_effort": "Этот диапазон усилий нельзя передать в Garmin без потери.",
    "garmin_unsupported_stroke": "Для этого стиля ещё нет проверенного соответствия Garmin.",
    "garmin_unsupported_equipment": "Garmin может принять только одну поддерживаемую позицию инвентаря на шаг.",
    "garmin_unsupported_group_cue": "Garmin не хранит общую подсказку группы. Уточните подсказки в её шагах.",
    "garmin_nested_group": "Прямая отправка пока поддерживает один уровень повторов.",
    "garmin_last_rest_unspecified": "Уточните, нужен ли отдых после последнего повтора.",
    "garmin_empty_swim_group": "В каждом повторе должен быть отрезок плавания.",
}


def _prepare(conn: sqlite3.Connection, assignment_id: UUID, checkpoint_id: int) -> tuple[dict, dict, dict]:
    token, assignment, document = delivery_source(conn, assignment_id, checkpoint_id)
    try:
        spec = project_garmin_swim(document, assignment.workout_id, assignment.date)
    except SwimDeliveryUnsupported as error:
        raise PlanningBuildPreviewError(error.code, f"{_MESSAGES[error.code]} Шаг: {error.node_id}.") from None
    return token, assignment.model_dump(mode="json"), spec


def _attempt(conn: sqlite3.Connection, assignment_id: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM garmin_swim_delivery_previews WHERE assignment_id=? AND attempted=1",
                        (assignment_id,)).fetchone()


def _row(conn: sqlite3.Connection, preview_id: UUID) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM garmin_swim_delivery_previews WHERE preview_id=?",
                        (str(preview_id),)).fetchone()


def _binding(row: sqlite3.Row) -> dict:
    try:
        data = json.loads(row["binding_json"])
    except (ValueError, TypeError):
        data = None
    if not isinstance(data, dict) or fingerprint(data) != row["binding_fingerprint"]:
        raise PlanningBuildPreviewError("garmin_swim_corrupt", "Предпросмотр Garmin повреждён.", status=503)
    return data


def _replay_preview(prior: sqlite3.Row, assignment_id: UUID, checkpoint_id: int) -> dict:
    data = _binding(prior)
    if prior["assignment_id"] != str(assignment_id) or data["token"]["checkpoint_id"] != checkpoint_id:
        raise PlanningBuildPreviewError("garmin_swim_request_conflict", "Этот запрос связан с другим назначением.")
    return data["public"]


def _check_intervals_attempt(conn: sqlite3.Connection, assignment_id: str) -> None:
    if conn.execute("SELECT 1 FROM swim_delivery_previews WHERE assignment_id=? AND attempted=1",
                    (assignment_id,)).fetchone() is not None:
        raise PlanningBuildPreviewError(
            "garmin_swim_intervals_attempt", "Для назначения уже была отправка через Intervals.icu.",
        )


def _existing_attempt() -> PlanningBuildPreviewError:
    return PlanningBuildPreviewError("garmin_swim_existing_attempt", "Для этого назначения уже была отправка в Garmin.")


def _unavailable() -> PlanningBuildPreviewError:
    return PlanningBuildPreviewError("garmin_swim_unavailable", "Локальная отправка в Garmin недоступна.", status=503)


def preview_garmin_swim(db: Database, request_id: UUID, assignment_id: UUID, checkpoint_id: int) -> dict:
    if Settings.ACCEPTANCE_MODE:
        raise _unavailable()
    with _transaction(db) as conn:
        prior = _row(conn, request_id)
        if prior is not None:
            return _replay_preview(prior, assignment_id, checkpoint_id)
        if _attempt(conn, str(assignment_id)) is not None:
            raise _existing_attempt()
        _check_intervals_attempt(conn, str(assignment_id))
        token, assignment, spec = _prepare(conn, assignment_id, checkpoint_id)
    try:
        draft = garmin_swim_mcp.call("preview_swim_workout", {"spec": spec})
    except garmin_swim_mcp.GarminSwimBridgeError:
        raise _unavailable() from None
    draft_id = draft.get("draft_id")
    sha = draft.get("payload_sha256")
    if (not isinstance(draft_id, str) or not re.fullmatch(r"swim-[0-9a-f]{24}", draft_id)
            or not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{64}", sha)
            or draft.get("confirmation_phrase") != f"ОТПРАВИТЬ {draft_id}"
            or any(draft.get(key) != spec[key] for key in spec)
            or any(type(draft.get(key)) is not int for key in
                   ("explicit_distance_meters", "fixed_rest_count", "fixed_rest_seconds"))):
        raise _unavailable()
    now = datetime.now(timezone.utc)
    expires_at = utc_text(now + timedelta(minutes=30))
    public = {"preview_id": str(request_id), "checkpoint_id": checkpoint_id, "assignment": assignment,
              "expires_at": expires_at, **spec, "distance_meters": draft["explicit_distance_meters"],
              "fixed_rest_count": draft["fixed_rest_count"], "fixed_rest_seconds": draft["fixed_rest_seconds"]}
    stored = {"token": token, "spec": spec, "draft_id": draft_id, "sha": sha, "public": public}
    with _transaction(db, write=True) as conn:
        prior = _row(conn, request_id)
        if prior is not None:
            return _replay_preview(prior, assignment_id, checkpoint_id)
        if _attempt(conn, str(assignment_id)) is not None:
            raise _existing_attempt()
        _check_intervals_attempt(conn, str(assignment_id))
        if _prepare(conn, assignment_id, checkpoint_id) != (token, assignment, spec):
            raise PlanningBuildPreviewError("cycle_stale", "Цикл изменился. Обновите предпросмотр.")
        conn.execute("DELETE FROM garmin_swim_delivery_previews WHERE attempted=0 AND expires_at < ?",
                     (utc_text(now - timedelta(days=1)),))
        conn.execute("""INSERT INTO garmin_swim_delivery_previews
            (preview_id, assignment_id, expires_at, binding_json, binding_fingerprint)
            VALUES (?, ?, ?, ?, ?)""",
                     (str(request_id), str(assignment_id), expires_at, canonical_json(stored), fingerprint(stored)))
    return public


def _receipt(stored: dict, result: dict | None = None) -> dict:
    public = stored["public"]
    safe = result or {}
    workout_id = safe.get("workout_id")
    exact_workout = (type(workout_id) is int and workout_id > 0 and safe.get("name") == public["name"]
                     and safe.get("status") in ("uploaded", "uploaded_readback_unverified"))
    workout_verified = exact_workout and safe.get("readback_verified") is True and safe["status"] == "uploaded"
    calendar_verified = (workout_verified and safe.get("calendar_scheduled") is True
                         and safe.get("schedule_status") == "verified" and safe.get("schedule_date") == public["schedule_date"])
    status = ("scheduled" if calendar_verified else "workout_verified" if workout_verified else
              "uploaded_unverified" if exact_workout else "uncertain")
    return {"preview_id": public["preview_id"], "assignment_id": public["assignment"]["assignment_id"],
            "target_date": public["schedule_date"], "status": status,
            "workout_id": workout_id if exact_workout else None,
            "workout_url": (f"https://connect.garmin.com/app/workout/{workout_id}?workoutType=swimming"
                            if exact_workout else None),
            "device_verified": False, "workout_verified": workout_verified,
            "calendar_verified": calendar_verified}


def read_garmin_swim(db: Database, assignment_id: UUID, *, demo: bool) -> dict:
    with _transaction(db) as conn:
        row = _attempt(conn, str(assignment_id))
        receipt = None if row is None else json.loads(row["receipt_json"]) if row["receipt_json"] else _receipt(_binding(row))
    return {"enabled": not demo and not Settings.ACCEPTANCE_MODE and garmin_swim_mcp.configured_script() is not None, "receipt": receipt}


def _read_draft(stored: dict) -> dict | None:
    try:
        draft = garmin_swim_mcp.call("get_swim_workout_draft", {"draft_id": stored["draft_id"]})
    except garmin_swim_mcp.GarminSwimBridgeError:
        return None
    if (draft.get("status") == "uploaded" and draft.get("payload_sha256") == stored["sha"]
            and isinstance(draft.get("result"), dict)):
        return draft["result"]
    return None


def confirm_garmin_swim(db: Database, preview_id: UUID, *, demo: bool) -> dict:
    with _transaction(db, write=True) as conn:
        row = _row(conn, preview_id)
        if row is None:
            raise PlanningBuildPreviewError("garmin_swim_preview_missing", "Предпросмотр Garmin не найден.", status=404)
        stored = _binding(row)
        saved = json.loads(row["receipt_json"]) if row["receipt_json"] else None
        if saved is not None and saved["status"] in {"scheduled", "uploaded_unverified"}:
            return saved
        first = not row["attempted"]
        if first:
            if demo or Settings.ACCEPTANCE_MODE or garmin_swim_mcp.configured_script() is None:
                raise _unavailable()
            if utc_text(datetime.now(timezone.utc)) >= row["expires_at"]:
                raise PlanningBuildPreviewError("garmin_swim_preview_expired", "Срок предпросмотра Garmin истёк.")
            if _attempt(conn, row["assignment_id"]) is not None:
                raise _existing_attempt()
            _check_intervals_attempt(conn, row["assignment_id"])
            token, assignment, spec = _prepare(conn, UUID(row["assignment_id"]), stored["token"]["checkpoint_id"])
            if (token, assignment, spec) != (stored["token"], stored["public"]["assignment"], stored["spec"]):
                raise PlanningBuildPreviewError("cycle_stale", "Назначение изменилось. Обновите предпросмотр.")
            conn.execute("UPDATE garmin_swim_delivery_previews SET attempted=1 WHERE preview_id=?", (str(preview_id),))
    if first:
        mark_committed(db)
        try:
            result = garmin_swim_mcp.call("send_swim_workout", {"draft_id": stored["draft_id"],
                                                              "confirmation": f"ОТПРАВИТЬ {stored['draft_id']}"})
        except garmin_swim_mcp.GarminSwimBridgeError:
            result = _read_draft(stored)
        incoming = _receipt(stored, result)
    elif saved is not None and saved["status"] == "workout_verified":
        if demo or Settings.ACCEPTANCE_MODE or not garmin_swim_mcp.scheduled_on(saved["workout_id"], saved["target_date"]):
            return saved
        incoming = {**saved, "calendar_verified": True, "status": "scheduled"}
    else:
        result = None if demo or Settings.ACCEPTANCE_MODE else _read_draft(stored)
        incoming = _receipt(stored, result)
    with _transaction(db, write=True) as conn:
        current = _row(conn, preview_id)
        if current is not None and current["attempted"]:
            old = json.loads(current["receipt_json"]) if current["receipt_json"] else None
            if old is not None and old["status"] != "uncertain":
                if (old["status"], incoming["status"]) != ("workout_verified", "scheduled") or old["workout_id"] != incoming["workout_id"]:
                    return old
            conn.execute("UPDATE garmin_swim_delivery_previews SET receipt_json=? WHERE preview_id=?",
                         (canonical_json(incoming), str(preview_id)))
    mark_committed(db)
    return incoming
