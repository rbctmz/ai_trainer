"""Compare authored pool steps with ordered observations from one source."""

from dataclasses import dataclass
from math import inf
from typing import Mapping, Sequence

from models.swim_delivery import SwimDeliveryRound, SwimDeliveryStep, SwimDeliveryWorkout


@dataclass(frozen=True)
class SwimObservation:
    """Measurements available from one original interval, in metres and seconds."""

    distance_meters: float | None
    active_seconds: float | None
    rest_seconds: float | None
    elapsed_seconds: float | None


@dataclass(frozen=True)
class SwimStepFact:
    planned: SwimDeliveryStep
    observation_indices: tuple[int, ...] = ()
    active_seconds: float | None = None
    rest_seconds: float | None = None
    elapsed_seconds: float | None = None

    @property
    def pace_seconds_per_100m(self) -> float | None:
        if not self.planned.distance_meters or not self.active_seconds:
            return None
        return round(self.active_seconds * 100 / self.planned.distance_meters, 1)


@dataclass(frozen=True)
class SwimRoundFact:
    rounds: tuple[SwimDeliveryRound, ...]
    pace_spread_seconds_per_100m: float | None


@dataclass(frozen=True)
class SwimSeriesFact:
    steps: tuple[SwimStepFact, ...]
    rounds: tuple[SwimRoundFact, ...]
    planned_swims: int
    matched_swims: int
    unassigned_observations: int


def _measurement(value: float | None) -> bool:
    return type(value) in (int, float) and 0 <= value < inf


def _observed(value: float | None, elapsed: float | None = None) -> float | None:
    if not _measurement(value):
        return None
    if _measurement(elapsed) and value > elapsed:
        return None
    return value


def _clock_sum(values: Sequence[float | None]) -> float | None:
    if any(not _measurement(value) for value in values):
        return None
    return sum(value for value in values if value is not None)


def _swim_end(
    actual: Sequence[SwimObservation], start: int, metres: int, pool: int,
) -> int | None:
    remaining = metres
    for index in range(start, len(actual)):
        distance = actual[index].distance_meters
        if not _measurement(distance) or not distance or distance % pool or distance > remaining:
            return None
        remaining -= distance
        if remaining == 0:
            return index + 1
    return None


def _match_step(
    step: SwimDeliveryStep, observations: Sequence[SwimObservation], start: int, end: int,
) -> SwimStepFact:
    matching = observations[start:end]
    elapsed = _clock_sum([row.elapsed_seconds for row in matching])
    active = _clock_sum([_observed(row.active_seconds, row.elapsed_seconds) for row in matching])
    rest = _clock_sum([_observed(row.rest_seconds, row.elapsed_seconds) for row in matching])
    return SwimStepFact(step, tuple(range(start, end)), active, rest, elapsed)


def _summarize_rounds(matches: Sequence[SwimStepFact]) -> tuple[SwimRoundFact, ...]:
    series: dict[tuple[tuple[str, int], ...], list[SwimStepFact]] = {}
    for match in matches:
        if match.planned.distance_meters:
            for depth in range(1, len(match.planned.rounds) + 1):
                key = tuple((part.group_id, part.number) for part in match.planned.rounds[:depth])
                series.setdefault(key, []).append(match)
    summaries = []
    for key, steps in series.items():
        paces = [pace for step in steps if (pace := step.pace_seconds_per_100m) is not None]
        spread = (round(max(paces) - min(paces), 1) if len(paces) == len(steps) > 1 else None)
        summaries.append(SwimRoundFact(steps[0].planned.rounds[:len(key)], spread))
    return tuple(summaries)


def compare_swim_series(
    planned: SwimDeliveryWorkout, observations: Sequence[SwimObservation],
) -> SwimSeriesFact:
    """Align exact metres in order and leave the uncertain suffix unassigned."""
    cursor = 0
    stopped = False
    matches = []
    for step in planned.steps:
        end = None
        if not stopped and cursor < len(observations):
            if step.distance_meters:
                end = _swim_end(observations, cursor, step.distance_meters, planned.pool_length_meters)
                stopped = end is None
            else:
                row = observations[cursor]
                if type(row.distance_meters) in (int, float) and row.distance_meters == 0:
                    if _measurement(row.rest_seconds) and not row.active_seconds:
                        end = cursor + 1
                    else:
                        stopped = True
                elif not _measurement(row.distance_meters):
                    stopped = True
        if end is None:
            matches.append(SwimStepFact(step))
        else:
            matches.append(_match_step(step, observations, cursor, end))
            cursor = end

    swims = [match for match in matches if match.planned.distance_meters]
    return SwimSeriesFact(
        tuple(matches), _summarize_rounds(matches), len(swims),
        sum(bool(match.observation_indices) for match in swims),
        len(observations) - cursor,
    )


def swim_observations(
    rows: list, *, source: str,
) -> tuple[SwimObservation, ...]:
    """Keep only separate, source-observed clocks for this comparison."""
    observations = []
    for raw in rows:
        row = raw if isinstance(raw, Mapping) else {}
        active_key = "recorded_moving_time" if source == "garmin" else "moving_time"
        elapsed_key = "recorded_elapsed_time" if source == "garmin" else "elapsed_time"
        distance = _observed(row.get("distance_meters"))
        elapsed = _observed(row.get(elapsed_key))
        active = _observed(row.get(active_key), elapsed)
        rest = None
        if distance == 0 and (active == 0 or (
            row.get("intensity_type") == "rest" and row.get(active_key) is None
        )):
            rest = elapsed
        observations.append(SwimObservation(distance, active, rest, elapsed))
    return tuple(observations)
