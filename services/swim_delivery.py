"""Preview and explicitly deliver a selected-calendar authored workout."""

from contextlib import closing, contextmanager
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
import json
import sqlite3
from uuid import UUID

from config.settings import Settings
from data.database import Database
from models.intervals_swim_delivery import (
    IntervalsSwimStep, IntervalsSwimWorkout, encode_intervals_swim, verify_intervals_swim,
)
from models.planning_build_confirmation import (
    PlanningBuildPreviewError, canonical_json, fingerprint, utc_text,
)
from models.swim_calendar import SwimCalendarAssignment
from models.swim_delivery import SwimDeliveryUnsupported, SwimDeliveryWorkout, project_swim_delivery
from services.intervals_icu import IntervalsICUClient, IntervalsICUError, get_client
from services.snapshot_runtime import backup_boundary, mark_committed
from services.swim_calendar import delivery_source

# Generic plan cleanup owns only the ai_trainer: namespace.
_EXTERNAL_ID_PREFIX = "ai_trainer_swim:"
_UNSUPPORTED = {
    "workout_not_found": "Тренировка отсутствует в сохранённой версии.",
    "unsupported_environment": "Для открытой воды доставка на часы ещё не проверена.",
    "unsupported_pool_length": "Первый профиль доставки на FR255 поддерживает бассейн 25 м.",
    "distance_not_multiple": "Дистанция одного из отрезков не кратна длине бассейна.",
    "step_limit": "Развёрнутая тренировка превышает предел в 100 шагов.",
    "no_swim_steps": "В тренировке нет отрезков плавания.",
    "unsupported_timed_repeat": "Доставка серии с таймером пока несовместима с этим профилем.",
    "unsupported_repeat_range": "Для отправки нужно точное число повторов.",
    "unsupported_swim_quantity": "Этот отрезок без точной дистанции несовместим с профилем бассейна.",
    "unresolved_step": "Перед отправкой нужно уточнить структуру отрезка.",
}


@dataclass(frozen=True)
class PreparedSwimDelivery:
    write_token: dict
    assignment: SwimCalendarAssignment
    workout: SwimDeliveryWorkout
    compiled: IntervalsSwimWorkout

    @property
    def target_date(self) -> date:
        return self.assignment.date

    @property
    def payload(self) -> dict[str, str]:
        return {
            "external_id": f"{_EXTERNAL_ID_PREFIX}{self.assignment.assignment_id}",
            "category": "WORKOUT",
            "type": "Swim",
            "name": self.workout.title,
            "start_date_local": f"{self.target_date.isoformat()}T00:00:00",
            "description": self.compiled.description,
        }

@contextmanager
def _transaction(db: Database, *, write: bool = False):
    try:
        with closing(db._connect()) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            yield conn
            if write:
                conn.commit()
    except sqlite3.Error:
        raise PlanningBuildPreviewError(
            "swim_delivery_storage_unavailable",
            "Не удалось прочитать или сохранить состояние отправки.",
            status=503, retryable=True,
        ) from None


def _prepare(conn: sqlite3.Connection, assignment_id: UUID, checkpoint_id: int) -> PreparedSwimDelivery:
    token, assignment, document = delivery_source(conn, assignment_id, checkpoint_id)
    try:
        workout = project_swim_delivery(document, assignment.workout_id)
    except SwimDeliveryUnsupported as exc:
        raise PlanningBuildPreviewError(exc.code, _UNSUPPORTED[exc.code]) from None
    return PreparedSwimDelivery(token, assignment, workout, encode_intervals_swim(workout))


def prepare_swim_delivery(
    db: Database, assignment_id: UUID, expected_checkpoint_id: int,
) -> PreparedSwimDelivery:
    """Use an owned checkpoint read and the authored prescription, without a write."""
    with _transaction(db) as conn:
        return _prepare(conn, assignment_id, expected_checkpoint_id)


def _retained(conn: sqlite3.Connection, preview_id: UUID) -> tuple[sqlite3.Row, dict]:
    row = conn.execute(
        "SELECT * FROM swim_delivery_previews WHERE preview_id=?", (str(preview_id),),
    ).fetchone()
    if row is None:
        raise PlanningBuildPreviewError("swim_delivery_preview_not_found", "Предпросмотр не найден.", status=404)
    try:
        stored = json.loads(row["binding_json"])
        if fingerprint(stored) != row["binding_fingerprint"]:
            raise ValueError("bad fingerprint")
    except (ValueError, TypeError):
        raise PlanningBuildPreviewError(
            "swim_delivery_preview_corrupt", "Предпросмотр повреждён. Создайте новый.", status=503,
        ) from None
    return row, stored


def _already_attempted(conn: sqlite3.Connection, assignment_id: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM swim_delivery_previews WHERE assignment_id=? AND attempted=1",
        (assignment_id,),
    ).fetchone() is not None


def _existing_attempt() -> PlanningBuildPreviewError:
    return PlanningBuildPreviewError(
        "swim_delivery_existing_attempt",
        "Для этого назначения уже была попытка отправки. Проверьте её результат.",
    )


def _preview(prepared: PreparedSwimDelivery, preview_id: UUID, expires_at: str) -> dict:
    return {
        "preview_id": str(preview_id),
        "checkpoint_id": prepared.write_token["checkpoint_id"],
        "cycle_id": prepared.write_token["cycle_id"],
        "assignment": prepared.assignment.model_dump(mode="json"),
        "target_date": prepared.target_date.isoformat(),
        "title": prepared.workout.title,
        "pool_length_meters": prepared.workout.pool_length_meters,
        "distance_meters": prepared.workout.distance_meters,
        "expires_at": expires_at,
        "unspecified_last_rest_group_ids": list(prepared.workout.unspecified_last_rest_group_ids),
        "steps": [
            {
                "node_id": authored.node.id,
                "rounds": [
                    {"group_id": item.group_id, "name": item.name, "number": item.number, "total": item.total}
                    for item in authored.rounds
                ],
                "cue": encoded.cue,
                "clock": "lap" if encoded.until_lap_press else "time" if encoded.is_rest else "distance",
                "distance_meters": encoded.distance_meters,
                "duration_seconds": encoded.duration_seconds,
                "source_rest_seconds": list(authored.rest_seconds) if authored.rest_seconds else None,
                "source_rest_breaths": list(authored.rest_breaths) if authored.rest_breaths else None,
            }
            for authored, encoded in zip(prepared.workout.steps, prepared.compiled.steps)
        ],
    }


def preview_swim_delivery(
    db: Database, request_id: UUID, assignment_id: UUID, expected_checkpoint_id: int,
) -> dict:
    """Retain the exact workout and publication token reviewed by the athlete."""
    now = datetime.now(timezone.utc)
    with _transaction(db, write=True) as conn:
        prior = conn.execute(
            "SELECT 1 FROM swim_delivery_previews WHERE preview_id=?", (str(request_id),),
        ).fetchone()
        if prior:
            row, stored = _retained(conn, request_id)
            if row["assignment_id"] != str(assignment_id) or stored["write_token"]["checkpoint_id"] != expected_checkpoint_id:
                raise PlanningBuildPreviewError(
                    "swim_delivery_request_conflict", "Этот запрос использован для другого назначения.",
                )
            return stored["public"]
        if _already_attempted(conn, str(assignment_id)):
            raise _existing_attempt()
        prepared = _prepare(conn, assignment_id, expected_checkpoint_id)
        expires_at = utc_text(now + timedelta(minutes=30))
        public = _preview(prepared, request_id, expires_at)
        stored = {
            "write_token": prepared.write_token,
            "payload": prepared.payload,
            "compiled": asdict(prepared.compiled),
            "public": public,
        }
        conn.execute(
            "DELETE FROM swim_delivery_previews WHERE attempted=0 AND expires_at < ?",
            (utc_text(now - timedelta(days=1)),),
        )
        conn.execute(
            """INSERT INTO swim_delivery_previews
            (preview_id, assignment_id, expires_at, binding_json, binding_fingerprint)
            VALUES (?, ?, ?, ?, ?)""",
            (str(request_id), str(assignment_id), expires_at, canonical_json(stored), fingerprint(stored)),
        )
    return public


def read_swim_delivery(db: Database, assignment_id: UUID) -> dict:
    """Return the last attempt for reload and readback without opening a new send."""
    with _transaction(db) as conn:
        attempt = conn.execute(
            "SELECT preview_id FROM swim_delivery_previews WHERE assignment_id=? AND attempted=1",
            (str(assignment_id),),
        ).fetchone()
        if attempt is None:
            return {"receipt": None}
        row, stored = _retained(conn, UUID(attempt["preview_id"]))
        if row["receipt_json"] is None:
            return {"receipt": _receipt(stored, reason="provider_event_unknown")}
        return {"receipt": json.loads(row["receipt_json"])}


def _assert_sendable(conn: sqlite3.Connection, row: sqlite3.Row, stored: dict) -> None:
    if utc_text(datetime.now(timezone.utc)) >= row["expires_at"]:
        raise PlanningBuildPreviewError(
            "swim_delivery_preview_expired", "Срок предпросмотра истёк. Проверьте отправку снова.",
        )
    if _already_attempted(conn, row["assignment_id"]):
        raise _existing_attempt()
    token = stored["write_token"]
    current = _prepare(conn, UUID(row["assignment_id"]), token["checkpoint_id"])
    if current.write_token != token:
        raise PlanningBuildPreviewError("cycle_stale", "Цикл или ограничения изменились. Обновите предпросмотр.")
    if current.payload != stored["payload"]:
        raise PlanningBuildPreviewError(
            "swim_delivery_preview_stale", "Данные отправки изменились. Откройте новый предпросмотр.",
        )


def _owned_matches(client: IntervalsICUClient, stored: dict) -> list[dict]:
    day = date.fromisoformat(stored["public"]["target_date"])
    return [
        event for event in client.list_workout_events(day, day, strict=True)
        if event.get("external_id") == stored["payload"]["external_id"]
    ]


def _provider_id(event: dict) -> int | None:
    event_id = event.get("id")
    return event_id if type(event_id) is int and event_id > 0 else None


def _receipt(
    stored: dict, *, event_id: int | None = None, reason: str | None = None, step_number: int | None = None,
) -> dict:
    preview = stored["public"]
    return {
        "preview_id": preview["preview_id"],
        "assignment_id": preview["assignment"]["assignment_id"],
        "target_date": preview["target_date"],
        "status": "provider_verified" if reason is None else "provider_unverified",
        "provider_event_id": event_id,
        "device_verified": False,
        "reason": reason,
        "step_number": step_number,
        "observed_at": utc_text(datetime.now(timezone.utc)),
    }


def _store_receipt(db: Database, preview_id: UUID, incoming: dict) -> dict:
    with _transaction(db, write=True) as conn:
        row, _ = _retained(conn, preview_id)
        prior = json.loads(row["receipt_json"]) if row["receipt_json"] else None
        if prior and prior["status"] == "provider_verified":
            return prior
        conn.execute(
            "UPDATE swim_delivery_previews SET receipt_json=? WHERE preview_id=? AND attempted=1",
            (canonical_json(incoming), str(preview_id)),
        )
    mark_committed(db)
    return incoming


def _observe_event(client: IntervalsICUClient, stored: dict, event_id: int | None) -> dict:
    try:
        matches = _owned_matches(client, stored)
        if len(matches) != 1:
            return _receipt(
                stored, event_id=event_id,
                reason="provider_event_ambiguous" if matches else "provider_event_unknown",
            )
        listed_id = _provider_id(matches[0])
        if listed_id is None:
            return _receipt(stored, event_id=event_id, reason="provider_event_unknown")
        if event_id is not None and listed_id != event_id:
            return _receipt(stored, event_id=event_id, reason="provider_identity_mismatch")
        event_id = listed_id
        event = client.get_workout_event(event_id)
    except (IntervalsICUError, UnicodeError):
        return _receipt(stored, event_id=event_id, reason="provider_readback_unknown")

    payload = stored["payload"]
    identity_fields = ("external_id", "category", "type", "name")
    start = event.get("start_date_local")
    try:
        same_start = datetime.fromisoformat(start) == datetime.fromisoformat(payload["start_date_local"])
    except (TypeError, ValueError):
        same_start = False
    if not same_start or any(event.get(key) != payload[key] for key in identity_fields):
        return _receipt(stored, event_id=event_id, reason="provider_identity_mismatch")
    if event.get("push_errors"):
        return _receipt(stored, event_id=event_id, reason="provider_push_errors")
    raw = stored["compiled"]
    expected = IntervalsSwimWorkout(
        raw["pool_length_meters"],
        tuple(IntervalsSwimStep(**step) for step in raw["steps"]),
        raw["distance_meters"],
    )
    mismatch = verify_intervals_swim(expected, event.get("workout_doc"))
    if mismatch is not None:
        return _receipt(stored, event_id=event_id, reason=mismatch.code, step_number=mismatch.step_number)
    return _receipt(stored, event_id=event_id)


@backup_boundary("swim_delivery_confirm")
def confirm_swim_delivery(
    db: Database, preview_id: UUID, *, client: IntervalsICUClient | None = None,
    demo: bool = False,
) -> dict:
    """Reserve one create. Later calls may verify that attempt without another write."""
    if demo or (client is None and Settings.ACCEPTANCE_MODE):
        raise PlanningBuildPreviewError("swim_delivery_demo", "Доставка недоступна в учебной базе.")
    with _transaction(db) as conn:
        row, stored = _retained(conn, preview_id)
        attempted = bool(row["attempted"])
        prior = json.loads(row["receipt_json"]) if row["receipt_json"] else None
        if not attempted:
            _assert_sendable(conn, row, stored)
        elif prior and prior["status"] == "provider_verified":
            return prior

    resolved = client or get_client()
    if not resolved.is_configured():
        raise PlanningBuildPreviewError("swim_delivery_not_configured", "Подключите Intervals.icu для отправки.")
    if attempted:
        observed = _observe_event(resolved, stored, prior["provider_event_id"] if prior else None)
        return _store_receipt(db, preview_id, observed)

    try:
        if _owned_matches(resolved, stored):
            raise PlanningBuildPreviewError(
                "swim_delivery_provider_conflict",
                "На эту дату в Intervals.icu уже есть событие этого назначения.",
            )
    except (IntervalsICUError, UnicodeError):
        raise PlanningBuildPreviewError(
            "swim_delivery_preflight_unknown", "Не удалось подтвердить состояние календаря Intervals.icu.",
            status=503, retryable=True,
        ) from None

    with _transaction(db, write=True) as conn:
        row, stored = _retained(conn, preview_id)
        if row["attempted"]:
            return json.loads(row["receipt_json"]) if row["receipt_json"] else _receipt(
                stored, reason="provider_event_unknown",
            )
        _assert_sendable(conn, row, stored)
        conn.execute("UPDATE swim_delivery_previews SET attempted=1 WHERE preview_id=?", (str(preview_id),))
    mark_committed(db)

    try:
        created = resolved.create_event(stored["payload"])
    except (IntervalsICUError, UnicodeError):
        receipt = _receipt(stored, reason="provider_write_unknown")
    else:
        receipt = _observe_event(resolved, stored, _provider_id(created))
    return _store_receipt(db, preview_id, receipt)
