"""Prepare selected-calendar authored swimming delivery without provider I/O."""

from contextlib import closing
from dataclasses import dataclass
from datetime import date
import sqlite3
from uuid import UUID

from data.database import Database
from models.intervals_swim_delivery import IntervalsSwimWorkout, encode_intervals_swim
from models.planning_build_confirmation import PlanningBuildPreviewError
from models.swim_calendar import SwimCalendarAssignment
from models.swim_delivery import SwimDeliveryUnsupported, SwimDeliveryWorkout, project_swim_delivery
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


def prepare_swim_delivery(
    db: Database, assignment_id: UUID, expected_checkpoint_id: int,
) -> PreparedSwimDelivery:
    """Use an owned checkpoint read and the authored prescription, without a write."""
    try:
        with closing(db._connect()) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("BEGIN")
            token, assignment, document = delivery_source(conn, assignment_id, expected_checkpoint_id)
    except sqlite3.Error:
        raise PlanningBuildPreviewError(
            "swim_delivery_storage_unavailable",
            "Не удалось прочитать назначение. Повторите запрос.",
            status=503, retryable=True,
        ) from None

    try:
        workout = project_swim_delivery(document, assignment.workout_id)
    except SwimDeliveryUnsupported as exc:
        raise PlanningBuildPreviewError(exc.code, _UNSUPPORTED[exc.code]) from None
    return PreparedSwimDelivery(token, assignment, workout, encode_intervals_swim(workout))
