"""Exact library references in an additive planning checkpoint field."""

from datetime import date
from typing import Annotated, Any, Literal, Mapping
from uuid import UUID

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, TypeAdapter, ValidationError

from models.planning_build_confirmation import PlanningBuildPreviewError
from models.planning_cycle import stored_day
from models.swim_program import Identifier


def _parse_day(value: Any) -> date:
    if type(value) is date:
        return value
    if isinstance(value, str):
        parsed = date.fromisoformat(value)
        if parsed.isoformat() == value:
            return parsed
    raise ValueError("expected YYYY-MM-DD")


LocalDay = Annotated[date, BeforeValidator(_parse_day)]
Revision = Annotated[int, Field(strict=True, ge=1)]


class CalendarModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SwimCalendarAssignment(CalendarModel):
    assignment_id: UUID
    date: LocalDay
    program_id: UUID
    program_revision: Revision
    program_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    workout_id: Identifier


class PlaceWorkouts(CalendarModel):
    kind: Literal["place"]
    program_id: UUID
    program_revision: Revision
    dates: dict[Identifier, LocalDay] = Field(min_length=1, max_length=24)


class MoveAssignment(CalendarModel):
    kind: Literal["move"]
    assignment_id: UUID
    date: LocalDay


class SubstituteAssignment(CalendarModel):
    kind: Literal["substitute"]
    assignment_id: UUID
    program_id: UUID
    program_revision: Revision
    workout_id: Identifier


class RemoveAssignment(CalendarModel):
    kind: Literal["remove"]
    assignment_id: UUID


class RollbackCalendar(CalendarModel):
    kind: Literal["rollback"]
    checkpoint_id: Revision


CalendarOperation = Annotated[
    PlaceWorkouts | MoveAssignment | SubstituteAssignment | RemoveAssignment | RollbackCalendar,
    Field(discriminator="kind"),
]


class SwimCalendarRequest(CalendarModel):
    request_id: UUID
    expected_checkpoint_id: Revision
    operation: CalendarOperation


_ASSIGNMENTS = TypeAdapter(list[SwimCalendarAssignment])


def calendar_assignments(snapshot: Mapping[str, Any]) -> list[SwimCalendarAssignment]:
    """Legacy plans have no assignments. Malformed saved state fails closed."""
    try:
        rows = _ASSIGNMENTS.validate_python(snapshot.get("swim_calendar", []))
    except ValidationError:
        raise _invalid_calendar() from None
    if len({row.assignment_id for row in rows}) != len(rows):
        raise _invalid_calendar()
    return rows


def _invalid_calendar() -> PlanningBuildPreviewError:
    return PlanningBuildPreviewError(
        "swim_calendar_corrupt",
        "Не удалось прочитать назначения тренировок тренера.",
        status=500,
    )


def calendar_payload(snapshot: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [row.model_dump(mode="json") for row in calendar_assignments(snapshot)]


def inherit_calendar(target: dict[str, Any], current: Mapping[str, Any]) -> None:
    """Keep current authored assignments during generated-plan rebuild/restore."""
    if "swim_calendar" in current:
        target["swim_calendar"] = calendar_payload(current)
    else:
        target.pop("swim_calendar", None)


def validate_calendar_dates(snapshot: Mapping[str, Any]) -> None:
    rows = calendar_assignments(snapshot)
    if not rows:
        return
    days = {stored_day(day["date"]) for day in snapshot["daily_plan"]}
    if any(row.date not in days for row in rows):
        raise PlanningBuildPreviewError(
            "swim_calendar_protected",
            "Период плана оставляет тренировку тренера без даты. Сначала перенесите её в календаре.",
        )


def guard_generic_calendar_write(
    previous: Mapping[str, Any], candidate: Mapping[str, Any],
) -> None:
    """Call inside the selected-cycle write transaction before publication."""
    if calendar_payload(previous) != calendar_payload(candidate):
        raise PlanningBuildPreviewError(
            "swim_calendar_protected",
            "Изменение тренировок тренера требует отдельного подтверждения в календаре.",
        )
    validate_calendar_dates(candidate)
