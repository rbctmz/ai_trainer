"""Offline contract for the exact prescription before any provider transport."""

import pytest

from models.swim_program_documents import validate_program_document
from tests.smoke._swim_import_fixtures import exact_program_v2, rich_program
from tests.smoke._swim_program_fixtures import example_program, group, rest, swim


@pytest.mark.parametrize("fixture", [example_program, exact_program_v2])
def test_three_authored_workouts_preserve_their_metres_and_rest_modes(fixture):
    from models.swim_delivery import project_swim_delivery

    document = validate_program_document(fixture())
    snapshot = document.model_dump()
    first, second, third = [
        project_swim_delivery(document, workout.id) for workout in document.workouts
    ]
    assert [item.distance_meters for item in (first, second, third)] == [2200, 2000, 1900]
    assert first.pool_length_meters == 25
    main = first.steps[3:27]
    assert [(row.node.id, row.distance_meters) for row in main] == [
        ("one.50", 50), ("one.rest50", 0), ("one.100", 100), ("one.rest60", 0),
        ("one.150", 150), ("one.open", 0),
    ] * 4
    assert [step.rest_seconds for step in main[1:6:2]] == [(50, 50), (60, 60), None]
    assert [step.node.mode for step in main[1:6:2]] == ["fixed", "fixed", "open"]
    assert main[0].rounds[0].instructions == "Equal pace within each round"
    assert first.steps[0].node.equipment == ["fins"]
    assert second.steps[2].node.instructions == "Buoy at ankles"
    assert [step.rest_seconds for step in second.steps if step.node.kind == "rest"] == [(120, 120)] * 3
    breaths = [step for step in third.steps if step.node.id == "three.breaths"]
    assert [step.rest_breaths for step in breaths] == [(3, 3)] * 12
    assert [[(round_.group_id, round_.number) for round_ in step.rounds] for step in breaths] == [
        [("three.rounds", outer), ("three.reps", inner)]
        for outer in range(1, 5) for inner in range(1, 4)
    ]
    assert breaths[0].rounds[-1].effort.start_percent == 50
    assert breaths[0].rounds[-1].effort.end_percent == 90
    pauses = [step for step in third.steps if step.node.id == "three.round_rest"]
    assert [(step.node.mode, step.rest_seconds) for step in pauses] == [("approximate", (120, 120))] * 4
    assert document.model_dump() == snapshot


@pytest.mark.parametrize("policy,expected", [
    ("include", ["work", "rest", "work", "rest", "work", "rest"]),
    ("omit", ["work", "rest", "work", "rest", "work"]),
    ("unspecified", ["work", "rest", "work", "rest", "work", "rest"]),
])
def test_only_the_explicit_last_rest_changes_the_sequence(policy, expected):
    from models.swim_delivery import project_swim_delivery

    program = example_program()
    program["workouts"][0]["steps"] = [group("outer", 3, [
        swim("work", 25), rest("rest"),
    ], last_rest=policy)]
    result = project_swim_delivery(validate_program_document(program), "one")
    assert [row.node.id for row in result.steps] == expected
    assert result.distance_meters == 75
    assert result.unspecified_last_rest_group_ids == (("outer",) if policy == "unspecified" else ())


def test_nested_last_rest_rule_is_applied_in_each_outer_round():
    from models.swim_delivery import project_swim_delivery

    program = example_program()
    program["workouts"][0]["steps"] = [group("outer", 2, [
        group("inner", 2, [swim("work", 25), rest("inner_rest")], last_rest="omit"),
        rest("outer_rest", "fixed", seconds=120),
    ], last_rest="omit")]
    result = project_swim_delivery(validate_program_document(program), "one")
    assert [row.node.id for row in result.steps] == [
        "work", "inner_rest", "work", "outer_rest", "work", "inner_rest", "work",
    ]
    assert [group_round.number for group_round in result.steps[-1].rounds] == [2, 2]


@pytest.mark.parametrize("workout_patch,steps,expected", [
    ({"pool_length_meters": 50}, [swim("good", 100)], "unsupported_pool_length"),
    ({"environment": "open_water", "pool_length_meters": None}, [swim("good", 100)], "unsupported_environment"),
    ({}, [swim("bad", 15)], "distance_not_multiple"),
    ({}, [group("large", 100, [swim("work", 25), rest("rest")])], "step_limit"),
    ({}, [rest("only_rest")], "no_swim_steps"),
])
def test_incompatible_workouts_have_a_typed_reason(workout_patch, steps, expected):
    from models.swim_delivery import SwimDeliveryUnsupported, project_swim_delivery

    program = example_program()
    program["workouts"][0].update(workout_patch, steps=steps)
    with pytest.raises(SwimDeliveryUnsupported) as raised:
        project_swim_delivery(validate_program_document(program), "one")
    assert raised.value.code == expected


def test_timed_cycle_is_not_substituted_with_guessed_repetitions():
    from models.swim_delivery import SwimDeliveryUnsupported, project_swim_delivery

    with pytest.raises(SwimDeliveryUnsupported) as raised:
        project_swim_delivery(validate_program_document(rich_program()), "one")
    assert raised.value.code == "unsupported_timed_repeat"
    assert raised.value.node_id == "one.timed"


@pytest.mark.parametrize("quantity,expected", [
    ({"kind": "attempts", "count": {"minimum": 10, "maximum": 15}}, "unsupported_swim_quantity"),
    ({"kind": "open"}, "unsupported_swim_quantity"),
    ({"kind": "duration", "seconds": 50}, "unsupported_swim_quantity"),
])
def test_non_distance_work_does_not_become_an_invented_pool_length(quantity, expected):
    from models.swim_delivery import SwimDeliveryUnsupported, project_swim_delivery

    program = exact_program_v2()
    program["workouts"][0]["steps"][0]["quantity"] = quantity
    with pytest.raises(SwimDeliveryUnsupported) as raised:
        project_swim_delivery(validate_program_document(program), "one")
    assert raised.value.code == expected
    assert raised.value.node_id == "one.warm"


def test_repeat_range_requires_an_explicit_count():
    from models.swim_delivery import SwimDeliveryUnsupported, project_swim_delivery

    program = exact_program_v2()
    program["workouts"][0]["steps"][3]["repeat"]["count"]["maximum"] = 5
    with pytest.raises(SwimDeliveryUnsupported) as raised:
        project_swim_delivery(validate_program_document(program), "one")
    assert raised.value.code == "unsupported_repeat_range"
    assert raised.value.node_id == "one.main"
