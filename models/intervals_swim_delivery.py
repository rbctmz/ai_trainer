"""Native Intervals representation and verification of compiled swim steps."""

from collections.abc import Mapping
from dataclasses import dataclass
import re
import unicodedata

from models.swim_delivery import SwimDeliveryStep, SwimDeliveryWorkout
from models.swim_program import RestStep, SubjectiveEffort
from models.swim_program_v2 import RestStepV2, SubjectiveEffortV2

_LAP_CARRIER_SECONDS = 1

_EQUIPMENT = {
    "fins": "Ласты",
    "pull_buoy": "Колобашка",
    "kickboard": "Доска",
    "paddles": "Лопатки",
    "snorkel": "Трубка",
    "other": "Другое снаряжение",
}
_STROKES = {
    "freestyle": "Кроль",
    "backstroke": "На спине",
    "breaststroke": "Брасс",
    "butterfly": "Баттерфляй",
    "mixed": "Смешанный стиль",
    "drill": "Упражнение",
}
_DIGITS = ("ноль", "один", "два", "три", "четыре", "пять", "шесть", "семь", "восемь", "девять")
_CUE_KEYWORDS = {
    "press lap": "кнопка круга",
    "ramp": "плавный разгон",
    "maxeffort": "максимальное усилие",
    "freeride": "свободное усилие",
    "hidepower": "скрыть мощность",
}
_KEYWORD_PATTERN = re.compile(r"\b(?:press\s+lap|ramp|maxeffort|freeride|hidepower)\b", re.I)


@dataclass(frozen=True)
class IntervalsSwimStep:
    cue: str
    distance_meters: int | None
    duration_seconds: int | None
    until_lap_press: bool

    @property
    def is_rest(self) -> bool:
        return self.distance_meters is None

    def native_line(self) -> str:
        if not self.is_rest:
            return f"- {self.cue} {self.distance_meters}mtr intensity=active"
        if self.until_lap_press:
            # Intervals drops a zero-duration step. The positive carrier is
            # parser metadata. Press lap controls the end of the device step.
            return f"- {self.cue} {_LAP_CARRIER_SECONDS}s intensity=rest Press lap"
        return f"- {self.cue} {self.duration_seconds}s intensity=rest"


@dataclass(frozen=True)
class IntervalsSwimWorkout:
    pool_length_meters: int
    steps: tuple[IntervalsSwimStep, ...]
    distance_meters: int

    @property
    def description(self) -> str:
        return "\n".join([
            f"pool length: {self.pool_length_meters}m", "",
            *(step.native_line() for step in self.steps),
        ])


@dataclass(frozen=True)
class IntervalsSwimMismatch:
    code: str
    step_number: int | None = None


def _cue_text(value: str) -> str:
    # Free text precedes the duration in the DSL. Keep prose separate from
    # numeric duration, pace, target, repeat and Markdown control tokens.
    clean = unicodedata.normalize("NFKC", value)
    clean = clean.replace("%", " процентов ").replace("+", " плюс ").replace("/", " из ")
    clean = clean.replace("→", " до ").replace("–", " до ")
    clean = re.sub(r"[\s-]+", " ", clean)
    clean = _KEYWORD_PATTERN.sub(lambda match: _CUE_KEYWORDS[" ".join(match[0].lower().split())], clean)
    parts: list[str] = []
    for char in clean:
        digit = unicodedata.digit(char, None)
        if digit is not None:
            parts.append(f" {_DIGITS[digit]} ")
        else:
            parts.append(char if char.isalpha() or char in " .,()" else " ")
    return " ".join("".join(parts).split())


def _effort_cue(
    effort: SubjectiveEffort | SubjectiveEffortV2, *, repeated: bool = False,
) -> str:
    across = effort.scope == "across_repetitions" if isinstance(effort, SubjectiveEffortV2) else repeated
    scope = " по ходу серии" if across else " внутри отрезка"
    return f"Усилие от {effort.start_percent} до {effort.end_percent} процентов{scope}"


def _range_cue(bounds: tuple[int, int]) -> str:
    start, end = bounds
    return str(start) if start == end else f"от {start} до {end}"


def _encode_step(step: SwimDeliveryStep) -> IntervalsSwimStep:
    node = step.node
    if isinstance(node, (RestStep, RestStepV2)):
        notes = ["Отдых", node.instructions, *(round_.instructions for round_ in step.rounds)]
        if step.rest_breaths is not None:
            notes.append(f"Выдохи {_range_cue(step.rest_breaths)}")
        seconds = step.rest_seconds
        if node.mode == "approximate" and seconds is not None:
            notes.append(f"Ориентир {_range_cue(seconds)} секунд")
        duration = seconds[0] if node.mode == "fixed" and seconds is not None else None
        cue = _cue_text(". ".join(dict.fromkeys(filter(None, notes))))
        return IntervalsSwimStep(cue, None, duration, duration is None)

    notes = [node.name, node.instructions, _STROKES.get(node.stroke, "")]
    notes.extend(_EQUIPMENT[item] for item in node.equipment)
    if step.exercise is not None:
        technique = step.exercise.document
        notes.extend((technique.name, technique.variant, technique.instructions))
    if node.effort is not None:
        notes.append(_effort_cue(node.effort))
    for round_ in step.rounds:
        notes.append(round_.instructions)
        if round_.effort is not None:
            notes.append(_effort_cue(round_.effort, repeated=True))
    cue = _cue_text(". ".join(dict.fromkeys(filter(None, notes)))) or "Плавание"
    return IntervalsSwimStep(cue, step.distance_meters, None, False)


def encode_intervals_swim(workout: SwimDeliveryWorkout) -> IntervalsSwimWorkout:
    """Encode one workout without sending source documents or video labels."""
    return IntervalsSwimWorkout(
        workout.pool_length_meters,
        tuple(_encode_step(step) for step in workout.steps),
        workout.distance_meters,
    )


def _matches_number(value: object, expected: int | None) -> bool:
    return type(value) in {int, float} and value == expected


def _no_number(value: object) -> bool:
    return value is None or _matches_number(value, 0)


def _step_matches(expected: IntervalsSwimStep, actual: object) -> bool:
    if not isinstance(actual, Mapping) or actual.get("steps") or actual.get("reps"):
        return False
    cue = actual.get("text")
    if not isinstance(cue, str) or " ".join(cue.split()) != expected.cue:
        return False
    lap_flag = actual.get("until_lap_press")
    if lap_flag is not expected.until_lap_press and not (lap_flag is None and not expected.until_lap_press):
        return False
    if any(actual.get(key) is not None for key in ("pace", "power", "hr", "cadence", "target")):
        return False
    if any(actual.get(key) for key in ("send_off", "send_off_seconds", "repetition_time")):
        return False

    duration_type = actual.get("duration_type")
    if not expected.is_rest:
        return (
            actual.get("intensity") == "active"
            and duration_type in (None, "distance")
            and _matches_number(actual.get("distance"), expected.distance_meters)
        )
    if (
        actual.get("intensity") != "rest"
        or not _no_number(actual.get("distance"))
        or not _no_number(actual.get("_distance"))
    ):
        return False
    if expected.until_lap_press:
        duration = actual.get("duration")
        return duration_type in (None, "open") and (
            _no_number(duration) or _matches_number(duration, _LAP_CARRIER_SECONDS)
        )
    return duration_type in (None, "time") and _matches_number(actual.get("duration"), expected.duration_seconds)


def verify_intervals_swim(
    expected: IntervalsSwimWorkout, workout_doc: object,
) -> IntervalsSwimMismatch | None:
    """Check provider-compiled structure. Device receipt is a separate result."""
    if not isinstance(workout_doc, Mapping):
        return IntervalsSwimMismatch("missing_workout_doc")
    options = workout_doc.get("options")
    if not isinstance(options, Mapping) or options.get("pool_length") != f"{expected.pool_length_meters}m":
        return IntervalsSwimMismatch("pool_length")
    if not _matches_number(workout_doc.get("distance"), expected.distance_meters):
        return IntervalsSwimMismatch("total_distance")
    steps = workout_doc.get("steps")
    if not isinstance(steps, list) or len(steps) != len(expected.steps):
        return IntervalsSwimMismatch("step_count")
    for index, (desired, actual) in enumerate(zip(expected.steps, steps), start=1):
        if not _step_matches(desired, actual):
            return IntervalsSwimMismatch("step_mismatch", index)
    return None
