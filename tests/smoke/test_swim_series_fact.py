"""Authorial series and the clocks supported by ordered device evidence."""

import pytest

from models.swim_delivery import project_swim_delivery
from models.swim_program_documents import validate_program_document
from models.swim_series_fact import SwimObservation, compare_swim_series
from tests.smoke._swim_program_fixtures import example_program


def _plan(workout_id):
    return project_swim_delivery(validate_program_document(example_program()), workout_id)


def _observations(plan):
    actual = []
    for step in plan.steps:
        if step.distance_meters == 0:
            seconds = step.rest_seconds[0] if step.rest_seconds else 21
            actual.append(SwimObservation(0, 0, seconds, seconds))
            continue
        round_number = step.rounds[0].number if step.rounds else 1
        active_per_length = {"two.100a": 32, "two.100b": 31, "two.100c": 30}.get(
            step.node.id, 29 + round_number,
        )
        actual.extend(
            SwimObservation(25, active_per_length, None, active_per_length)
            for _ in range(step.distance_meters // 25)
        )
    return actual


@pytest.mark.parametrize(("workout", "metres"), [("one", 2200), ("two", 2000), ("three", 1900)])
def test_complete_reference_program_uses_sources_once(workout, metres):
    plan = _plan(workout)
    result = compare_swim_series(plan, _observations(plan))
    indices = [index for item in result.steps for index in item.observation_indices]

    assert result.matched_swims == result.planned_swims
    assert result.unassigned_observations == 0
    assert sum(step.distance_meters for step in plan.steps) == metres
    assert indices == list(range(len(indices)))


def test_compare_first_workout_within_each_round():
    plan = _plan("one")
    result = compare_swim_series(plan, _observations(plan))

    assert [(r.rounds[-1].number, r.pace_spread_seconds_per_100m) for r in result.rounds] == [
        (1, 0), (2, 0), (3, 0), (4, 0),
    ]
    swims = [match for match in result.steps if match.planned.node.id == "one.50"]
    assert [m.pace_seconds_per_100m for m in swims] == [120, 124, 128, 132]
    rest = next(m for m in result.steps if m.planned.node.id == "one.rest50")
    assert (rest.active_seconds, rest.rest_seconds, rest.elapsed_seconds) == (0, 50, 50)


def test_compare_second_workout_in_hundreds():
    plan = _plan("two")
    result = compare_swim_series(plan, _observations(plan))
    first_group = [m for m in result.steps if m.planned.rounds and m.planned.rounds[0].number == 1]
    assert [m.pace_seconds_per_100m for m in first_group] == [128, 124, 120, None]


def test_subjective_progression_and_breaths_remain_authored_data():
    plan = _plan("three")
    result = compare_swim_series(plan, _observations(plan))
    step = next(m for m in result.steps if m.planned.node.id == "three.rep")
    effort = step.planned.rounds[-1].effort
    assert (effort.start_percent, effort.end_percent) == (50, 90)
    assert step.pace_seconds_per_100m == 120
    rest = next(m for m in result.steps if m.planned.node.id == "three.breaths")
    assert rest.planned.rest_breaths == (3, 3)
    assert rest.planned.rest_seconds is None
    assert rest.rest_seconds == 21


def test_overlarge_lap_is_not_split_across_hundreds():
    plan = _plan("two")
    observations = _observations(plan)
    start = (300 + 300 + 400) // 25
    observations[start:start + 12] = [SwimObservation(300, 360, None, 360)]
    result = compare_swim_series(plan, observations)
    assert result.matched_swims == 3
    assert all(not m.observation_indices for m in result.steps[3:])
    assert result.rounds[0].pace_spread_seconds_per_100m is None


def test_missing_rest_preserves_next_movement_and_incomplete_clocks_stay_unknown():
    plan = _plan("one")
    actual = _observations(plan)
    rest_index = (500 + 300 + 100 + 50) // 25
    actual.pop(rest_index)
    actual[0] = SwimObservation(25, None, None, 30)
    result = compare_swim_series(plan, actual)

    assert result.matched_swims == result.planned_swims
    assert result.steps[0].active_seconds is None
    assert result.steps[0].elapsed_seconds == 20 * 30
    assert result.steps[0].pace_seconds_per_100m is None
    assert result.steps[4].rest_seconds is None
    assert result.steps[5].observation_indices[0] == rest_index


@pytest.mark.parametrize("distance", [None, 24, -25, float("nan"), float("inf")])
def test_unproven_distance_stops_alignment(distance):
    plan = _plan("one")
    actual = _observations(plan)
    actual[20] = SwimObservation(distance, 25, None, 25)
    result = compare_swim_series(plan, actual)
    assert result.matched_swims == 1
    assert result.steps[0].observation_indices == tuple(range(20))
    assert all(not m.observation_indices for m in result.steps[1:])
