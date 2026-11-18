"""Preview and publish authored swimming changes under selected-cycle CAS."""

from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
import json
import sqlite3
from uuid import UUID, uuid4

from data.database import Database
from data.planning_cycle_writes import (
    append_cycle_child, check_restore_owner, guard_write, read_write_context, write_token,
)
from data.planning_cycles import PlanningCycleStore
from data.swim_program_store import SwimProgramError, _version
from models.coach_constraints import PROTECTIVE_CONSTRAINT_KINDS, normalize_constraint_sport
from models.plan_events import normalized_events
from models.planning_build_confirmation import PlanningBuildPreviewError, canonical_json, fingerprint, utc_text
from models.planning_cycle import stored_day
from models.planning_sport_days import sports_allowed_on_day
from models.swim_program_documents import ProgramDocument, validate_program_document
from models.swim_calendar import (
    MoveAssignment, PlaceWorkouts, RemoveAssignment, RollbackCalendar, SubstituteAssignment,
    SwimCalendarAssignment, SwimCalendarRequest, calendar_assignments, calendar_payload,
    validate_calendar_dates,
)
from models.training_planner import apply_race_event_overlays
from services.planning_cycle_build import scoped_constraints
from services.snapshot_runtime import backup_boundary, mark_committed


@contextmanager
def _transaction(db: Database, *, write: bool = False):
    conn = db._connect()
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("BEGIN IMMEDIATE" if write else "BEGIN")
        yield conn
        if write:
            conn.commit()
    except sqlite3.Error as exc:
        raise PlanningBuildPreviewError(
            "swim_calendar_storage_unavailable",
            "Календарь временно недоступен. Повторите запрос.",
            status=503, retryable=True,
        ) from exc
    finally:
        conn.close()


def _error(code: str, message: str, status: int = 409) -> PlanningBuildPreviewError:
    return PlanningBuildPreviewError(code, message, status=status)


def _library_version(conn, program_id, revision):
    try:
        return _version(conn, str(program_id), revision)
    except SwimProgramError as exc:
        raise _error(exc.code, "Версия программы тренера недоступна.", exc.status) from None


def _find_workout(program: dict, workout_id: str) -> dict:
    for workout in program["document"]["workouts"]:
        if workout["id"] == workout_id:
            return workout
    raise _error("swim_calendar_workout_not_found", "Тренировка отсутствует в выбранной версии.", 404)


def _project(conn, row: SwimCalendarAssignment) -> dict:
    program = _library_version(conn, row.program_id, row.program_revision)
    if program["fingerprint"] != row.program_fingerprint:
        raise _error("swim_calendar_corrupt", "Версия назначенной программы не совпадает с сохранённой.", 503)
    workout = _find_workout(program, row.workout_id)
    summary = next(value for value in program["summary"]["workouts"] if value["workout_id"] == row.workout_id)
    return {
        **row.model_dump(mode="json"),
        "origin": "trainer_authored",
        "title": workout["title"],
        "source_week_label": program["document"]["source_week_label"],
        "environment": workout["environment"],
        "pool_length_meters": workout["pool_length_meters"],
        "distance_meters": summary["distance_meters"],
        "known_distance_meters": summary.get("known_distance_meters", summary["distance_meters"]),
        "distance_compatibility": summary["compatibility"],
        "duration_minutes": None,
        "tss": None,
    }


def read_calendar(
    db: Database, *, checkpoint_id: int | None = None, include_current_protection: bool = False,
) -> dict:
    """Read current or explicitly requested cycle-owned checkpoint."""
    with _transaction(db) as conn:
        store = PlanningCycleStore(conn)
        assess_current = checkpoint_id is None or include_current_protection
        if checkpoint_id is None:
            checkpoint = db._get_current_planning_checkpoint(conn)
            if checkpoint is None:
                return {"cycle_id": None, "checkpoint_id": None, "assignments": []}
            checkpoint_id = checkpoint["id"]
        else:
            checkpoint = store.checkpoint(checkpoint_id)
        owner = store.version_cycle(checkpoint_id)
        if not checkpoint or owner is None:
            raise _error("swim_calendar_checkpoint_not_found", "Версия цикла не найдена.", 404)
        snapshot = checkpoint.get("goal_plan_snapshot")
        if not isinstance(snapshot, dict):
            raise _error("swim_calendar_corrupt", "Версия цикла повреждена.", 503)
        assigned = calendar_assignments(snapshot)
        projected = [_project(conn, row) for row in assigned]
        if assigned and assess_current:
            context = read_write_context(conn, allow_inactive=True)
            if context["checkpoint_id"] == checkpoint_id and context["state"] in {"scheduled", "in_progress"}:
                upcoming = {row.date for row in assigned if row.date.isoformat() >= context["athlete_day"]}
                conflicts = _placement_conflicts(conn, owner, snapshot, upcoming)
                for row, projection in zip(assigned, projected):
                    if row.date in conflicts:
                        projection["date_review_reason"] = str(conflicts[row.date])
        return {
            "cycle_id": owner,
            "checkpoint_id": checkpoint_id,
            "assignments": projected,
        }


def delivery_source(
    conn: sqlite3.Connection, assignment_id: UUID, expected_checkpoint_id: int,
) -> tuple[dict, SwimCalendarAssignment, ProgramDocument]:
    """Resolve one current, eligible assignment and exact saved library version."""
    context = read_write_context(conn)
    if context["checkpoint_id"] != expected_checkpoint_id:
        raise _error("cycle_stale", "Цикл изменился. Обновите календарь.")
    checkpoint = PlanningCycleStore(conn).checkpoint(expected_checkpoint_id)
    snapshot = checkpoint["goal_plan_snapshot"]
    assignment = next(
        (item for item in calendar_assignments(snapshot) if item.assignment_id == assignment_id), None,
    )
    if assignment is None:
        raise _error("swim_calendar_assignment_not_found", "Назначение отсутствует в текущем календаре.", 404)
    if assignment.date.isoformat() < context["athlete_day"]:
        raise _error("swim_calendar_past_date", "Прошедшие назначения сохранены в истории.")
    conflicts = _placement_conflicts(conn, context["cycle_id"], snapshot, {assignment.date})
    if assignment.date in conflicts:
        raise conflicts[assignment.date]
    program = _library_version(conn, assignment.program_id, assignment.program_revision)
    if program["fingerprint"] != assignment.program_fingerprint:
        raise _error("swim_calendar_corrupt", "Версия назначенной программы не совпадает с сохранённой.", 503)
    return write_token(context), assignment, validate_program_document(program["document"])


def _prepare_assignments(conn, current, before, operation):
    if isinstance(operation, RollbackCalendar):
        check_restore_owner(conn, current, operation.checkpoint_id)
        donor = PlanningCycleStore(conn).checkpoint(operation.checkpoint_id)
        return calendar_assignments(donor["goal_plan_snapshot"])
    if isinstance(operation, PlaceWorkouts):
        program = _library_version(conn, operation.program_id, operation.program_revision)
        existing = {(row.program_id, row.program_revision, row.workout_id, row.date) for row in before}
        additions = []
        for workout_id, day in sorted(operation.dates.items()):
            _find_workout(program, workout_id)
            if (operation.program_id, operation.program_revision, workout_id, day) in existing:
                raise _error("swim_calendar_duplicate", "Эта тренировка уже назначена на выбранную дату.")
            additions.append(SwimCalendarAssignment(
                assignment_id=uuid4(), date=day, workout_id=workout_id,
                program_id=operation.program_id, program_revision=operation.program_revision,
                program_fingerprint=program["fingerprint"],
            ))
        return [*before, *additions]
    entry = next((row for row in before if row.assignment_id == operation.assignment_id), None)
    if entry is None:
        raise _error("swim_calendar_assignment_not_found", "Назначение не найдено.", 404)
    if isinstance(operation, RemoveAssignment):
        return [row for row in before if row != entry]
    if isinstance(operation, MoveAssignment):
        replacement = entry.model_copy(update={"date": operation.date})
    elif isinstance(operation, SubstituteAssignment):
        program = _library_version(conn, operation.program_id, operation.program_revision)
        _find_workout(program, operation.workout_id)
        replacement = entry.model_copy(update={
            "program_id": operation.program_id, "program_revision": operation.program_revision,
            "program_fingerprint": program["fingerprint"], "workout_id": operation.workout_id,
        })
    else:
        raise TypeError("unexpected calendar operation")
    return [replacement if row == entry else row for row in before]


def _placement_conflicts(
    conn: sqlite3.Connection, cycle_id: str, snapshot: dict, dates: set[date],
) -> dict[date, PlanningBuildPreviewError]:
    if not dates:
        return {}
    known_cycles = {row[0] for row in conn.execute("SELECT id FROM planning_cycles")}
    available = (snapshot.get("constraint_summary") or {}).get("available_day_indices")
    sport_rules = snapshot.get("allowed_sports_by_day") or {}
    events = normalized_events(snapshot.get("events"))
    protected = {
        stored_day(event["date"]) for event in events
        if event.get("confirmed") is True
    }
    # The aggregate includes days emptied by constraints on generated sessions.
    # Recover the race portion for these dates, then check constraint scope below.
    overlay_dates = dates.intersection(stored_day(day) for day in snapshot.get("protected_dates") or [])
    if events and overlay_dates:
        _, _, overlay = apply_race_event_overlays(
            [(datetime.combine(day, datetime.min.time()), 0.0, {}) for day in sorted(overlay_dates)],
            [], events, goal_type=snapshot.get("goal_type") or "",
        )
        protected.update(stored_day(day) for day in overlay["protected_dates"])
    conflicts = {}
    for day in dates:
        if available is not None and day.weekday() not in available:
            conflicts[day] = _error("swim_calendar_unavailable_day", "Этот день отсутствует в доступности плана.")
            continue
        sports = sports_allowed_on_day(sport_rules, day)
        if sports is not None and "swim" not in sports:
            conflicts[day] = _error("swim_calendar_sport_unavailable", "На эту дату плавание исключено настройками плана.")
            continue
        if day in protected:
            conflicts[day] = _error("swim_calendar_protected_day", "Дата защищена в текущем цикле.")
            continue
        constraints = [
            dict(row) for row in conn.execute(
                "SELECT * FROM coach_constraints WHERE date=? AND status='active'", (day.isoformat(),),
            )
            if row["kind"] in PROTECTIVE_CONSTRAINT_KINDS
        ]
        try:
            scoped = scoped_constraints(constraints, cycle_id, known_cycles)
        except PlanningBuildPreviewError as exc:
            conflicts[day] = exc
            continue
        if any(normalize_constraint_sport(row.get("sport")) in {None, "swim"} for row in scoped):
            conflicts[day] = _error("swim_calendar_protected_day", "На эту дату действует ограничение на плавание.")
    return conflicts


def _date_warnings(conn, current, snapshot, changes, after):
    affected = {new.date for _old, new in changes if new}
    conflicts = _placement_conflicts(conn, current["cycle_id"], snapshot, affected)
    for old, new in changes:
        if any(row and row.date.isoformat() < current["athlete_day"] for row in (old, new)):
            raise _error("swim_calendar_past_date", "Прошедшие назначения сохранены в истории.")
        if new and new.date in conflicts:
            raise conflicts[new.date]
    generated_days = {stored_day(day["date"]): day for day in snapshot["daily_plan"]}
    warnings = []
    for day in sorted(affected):
        warnings.append({"date": day.isoformat(), "code": "load_uncertain"})
        if generated_days[day]["total_tss"] > 0 or sum(row.date == day for row in after) > 1:
            warnings.append({"date": day.isoformat(), "code": "other_sessions_on_day"})
    return warnings


def _retained(conn, preview_id):
    row = conn.execute("SELECT * FROM swim_calendar_previews WHERE preview_id=?", (preview_id,)).fetchone()
    if row is None:
        return None, None
    try:
        saved = json.loads(row["preview_json"])
        if saved["preview_id"] != preview_id or fingerprint(saved) != row["preview_digest"]:
            raise ValueError("preview digest mismatch")
    except (KeyError, TypeError, ValueError):
        raise _error("swim_calendar_corrupt", "Предпросмотр календаря повреждён.", 503) from None
    return row, saved


def _public_preview(saved):
    return {key: saved[key] for key in (
        "preview_id", "cycle_id", "base_checkpoint_id", "expires_at", "changes", "warnings",
    )}


def preview_calendar(db: Database, request: SwimCalendarRequest) -> dict:
    preview_id = str(request.request_id)
    digest = fingerprint(request.model_dump(mode="json"))
    with _transaction(db, write=True) as conn:
        retained, saved = _retained(conn, preview_id)
        if retained is not None:
            if retained["request_digest"] != digest:
                raise _error("swim_calendar_request_conflict", "Этот запрос уже использован для другой правки.")
            return _public_preview(saved)
        current = read_write_context(conn)
        if current["checkpoint_id"] != request.expected_checkpoint_id:
            raise _error("cycle_stale", "Цикл изменился. Обновите календарь.")
        checkpoint = PlanningCycleStore(conn).checkpoint(current["checkpoint_id"])
        snapshot = checkpoint["goal_plan_snapshot"]
        before = calendar_assignments(snapshot)
        after = _prepare_assignments(conn, current, before, request.operation)
        placements = {(row.program_id, row.program_revision, row.workout_id, row.date) for row in after}
        if len(placements) != len(after):
            raise _error("swim_calendar_duplicate", "Эта тренировка уже назначена на выбранную дату.")
        encoded = [row.model_dump(mode="json") for row in after]
        validate_calendar_dates({**snapshot, "swim_calendar": encoded})
        previous = {row.assignment_id: row for row in before}
        updated = {row.assignment_id: row for row in after}
        keys = dict.fromkeys([*previous, *updated])
        changes = [(previous.get(key), updated.get(key)) for key in keys if previous.get(key) != updated.get(key)]
        if not changes:
            raise _error("swim_calendar_no_changes", "Назначения уже совпадают.")
        warnings = _date_warnings(conn, current, snapshot, changes, after)
        saved = {
            "preview_id": preview_id, "cycle_id": current["cycle_id"],
            "base_checkpoint_id": current["checkpoint_id"], "write_token": write_token(current),
            "expires_at": utc_text(datetime.now(timezone.utc) + timedelta(hours=24)),
            "assignments": encoded, "warnings": warnings,
            "changes": [
                {"before": _project(conn, old) if old else None, "after": _project(conn, new) if new else None}
                for old, new in changes
            ],
        }
        conn.execute(
            "INSERT INTO swim_calendar_previews VALUES (?, ?, ?, ?, NULL)",
            (preview_id, digest, canonical_json(saved), fingerprint(saved)),
        )
        return _public_preview(saved)


@backup_boundary("swim_calendar_confirm")
def confirm_calendar(db: Database, preview_id: str) -> dict:
    with _transaction(db, write=True) as conn:
        retained, saved = _retained(conn, preview_id)
        if retained is None:
            raise _error("swim_calendar_preview_not_found", "Предпросмотр не найден.", 404)
        if retained["applied_checkpoint_id"] is not None:
            # The immutable receipt must still refer to an owned version.
            checkpoint_id = retained["applied_checkpoint_id"]
            store = PlanningCycleStore(conn)
            checkpoint = store.checkpoint(checkpoint_id)
            if (
                not checkpoint or store.version_cycle(checkpoint_id) != saved["cycle_id"]
                or checkpoint["goal_plan_snapshot"].get("swim_calendar_preview_id") != preview_id
                or calendar_payload(checkpoint["goal_plan_snapshot"]) != saved["assignments"]
            ):
                raise _error("swim_calendar_corrupt", "Квитанция календаря повреждена.", 503)
            return {"cycle_id": saved["cycle_id"], "checkpoint_id": checkpoint_id, "preview_id": preview_id}
        if utc_text(datetime.now(timezone.utc)) >= saved["expires_at"]:
            raise _error("swim_calendar_preview_expired", "Срок предпросмотра истёк. Проверьте даты снова.")
        current = guard_write(conn, saved["write_token"])
        checkpoint = PlanningCycleStore(conn).checkpoint(current["checkpoint_id"])
        checkpoint.pop("id", None)
        snapshot = checkpoint["goal_plan_snapshot"]
        for row in calendar_assignments({"swim_calendar": saved["assignments"]}):
            _project(conn, row)
        provenance = {
            "checkpoint_parent_id": current["checkpoint_id"],
            "checkpoint_source": "swim_calendar",
            "checkpoint_restored_from_checkpoint_id": None,
        }
        checkpoint.update(provenance)
        snapshot.update(provenance, swim_calendar=saved["assignments"], swim_calendar_preview_id=preview_id)
        committed = db._insert_planning_checkpoint(conn, checkpoint)
        checkpoint_id = committed["id"]
        append_cycle_child(
            conn, current, checkpoint, checkpoint_id, reviewed_swim_calendar=saved["assignments"],
        )
        conn.execute(
            "UPDATE swim_calendar_previews SET applied_checkpoint_id=? WHERE preview_id=?",
            (checkpoint_id, preview_id),
        )
    mark_committed(db)
    return {"cycle_id": current["cycle_id"], "checkpoint_id": checkpoint_id, "preview_id": preview_id}
