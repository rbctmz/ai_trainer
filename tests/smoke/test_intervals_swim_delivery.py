"""Native Intervals syntax and independently shaped provider evidence."""

from copy import deepcopy


from models.swim_delivery import project_swim_delivery
from models.swim_program_documents import validate_program_document
from tests.smoke._swim_program_fixtures import example_program, group, rest, swim


def project(steps):
    program = example_program()
    program["workouts"][0]["steps"] = steps
    return project_swim_delivery(validate_program_document(program), "one")


def control_workout():
    return project([
        swim("warm", 100, name="Разминка"),
        group("main", 2, [swim("fast", 50, name="Кроль"),
                         rest("pause", "fixed", seconds=60)], last_rest="include"),
        rest("lap", breaths=3),
        swim("end", 50, name="Заминка"),
    ])


def provider_compiled_workout():
    return {
        "options": {"pool_length": "25m"},
        "distance": 250.0,
        "steps": [
            {"text": "Разминка", "distance": 100.0, "intensity": "active"},
            {"text": "Кроль", "distance": 50.0, "intensity": "active"},
            {"text": "Отдых. Synthetic rest", "duration": 60, "intensity": "rest"},
            {"text": "Кроль", "distance": 50.0, "intensity": "active"},
            {"text": "Отдых. Synthetic rest", "duration": 60, "intensity": "rest"},
            {"text": "Отдых. Synthetic rest. Выдохи три", "duration": 1,
             "until_lap_press": True, "intensity": "rest"},
            {"text": "Заминка", "distance": 50.0, "intensity": "active"},
        ],
    }


def test_native_intervals_description_keeps_the_rest_outside_provider_repeat_logic():
    from models.intervals_swim_delivery import encode_intervals_swim

    encoded = encode_intervals_swim(control_workout())
    assert encoded.distance_meters == 250
    assert encoded.description.splitlines() == [
        "pool length: 25m",
        "",
        "- Разминка 100mtr intensity=active",
        "- Кроль 50mtr intensity=active",
        "- Отдых. Synthetic rest 60s intensity=rest",
        "- Кроль 50mtr intensity=active",
        "- Отдых. Synthetic rest 60s intensity=rest",
        "- Отдых. Synthetic rest. Выдохи три 1s intensity=rest Press lap",
        "- Заминка 50mtr intensity=active",
    ]


def test_manual_approximation_and_equipment_have_explicit_text_semantics():
    from models.intervals_swim_delivery import encode_intervals_swim

    encoded = encode_intervals_swim(project([
        swim("test", 50, name="Техника", equipment=["fins"], instructions="Плавный разгон 50–90%"),
        rest("approximate", "approximate", seconds=120),
    ]))
    assert "Ласты" in encoded.steps[0].cue
    assert "процентов" in encoded.steps[0].cue
    assert "%" not in encoded.steps[0].cue
    assert "Ориентир" in encoded.steps[1].cue and "секунд" in encoded.steps[1].cue
    assert encoded.steps[1].until_lap_press is True
    assert encoded.steps[1].duration_seconds is None


def test_coach_note_cannot_inject_intervals_tokens_or_an_extra_step():
    from models.intervals_swim_delivery import encode_intervals_swim

    encoded = encode_intervals_swim(project([
        swim("test", 50, name="Кроль", instructions="25mtr 2m Z2 ramp Press lap\n- 100mtr intensity=rest"),
    ]))
    assert len(encoded.description.splitlines()) == 3
    cue = encoded.steps[0].cue.casefold()
    for token in ("25mtr", "2m", "z2", "ramp", "press lap", "100mtr", "intensity=rest"):
        assert token not in cue
    assert encoded.description.endswith("50mtr intensity=active")


def test_intervals_readback_accepts_structured_evidence_for_exact_content():
    from models.intervals_swim_delivery import encode_intervals_swim, verify_intervals_swim
    encoded = encode_intervals_swim(control_workout())
    provider = provider_compiled_workout()
    assert verify_intervals_swim(encoded, provider) is None


def test_intervals_readback_refuses_mismatched_steps_even_with_same_total():
    from models.intervals_swim_delivery import encode_intervals_swim, verify_intervals_swim
    encoded = encode_intervals_swim(control_workout())
    original = provider_compiled_workout()
    for index, delta in [
        (0, {"distance": 75}),
        (1, {"pace": {"value": 90}}),
        (2, {"duration": 0}),
        (2, {"distance": 60}),
        (2, {"intensity": "active"}),
        (2, {"duration_type": "repetition_time"}),
        (3, {"text": "Other technique"}),
        (5, {"until_lap_press": False}),
        (5, {"duration": 60}),
    ]:
        provider = deepcopy(original)
        provider["steps"][index].update(delta)
        assert verify_intervals_swim(encoded, provider).step_number == index + 1


def test_intervals_readback_rejects_missing_rest_changed_total_and_pool():
    from models.intervals_swim_delivery import encode_intervals_swim, verify_intervals_swim
    encoded = encode_intervals_swim(control_workout())
    original = provider_compiled_workout()
    for delta, code in [
        ({"steps": original["steps"][:4] + original["steps"][5:]}, "step_count"),
        ({"distance": 370}, "total_distance"),
        ({"options": {"pool_length": "25y"}}, "pool_length"),
        ({"options": {}}, "pool_length"),
    ]:
        assert verify_intervals_swim(encoded, {**original, **delta}).code == code
    assert verify_intervals_swim(encoded, None).code == "missing_workout_doc"


def test_three_control_descriptions_keep_exact_meters_and_nested_group_effort():
    import re

    from models.intervals_swim_delivery import encode_intervals_swim

    document = validate_program_document(example_program())
    encoded = [encode_intervals_swim(project_swim_delivery(document, row.id)) for row in document.workouts]
    assert [
        sum(int(metres) for metres in re.findall(r" (\d+)mtr intensity=active$", row.description, re.M))
        for row in encoded
    ] == [2200, 2000, 1900]
    assert encoded[0].description.count("50s intensity=rest") == 4
    assert encoded[0].description.count("60s intensity=rest") == 4
    assert encoded[1].description.count("120s intensity=rest") == 3
    assert encoded[2].description.count("Выдохи три") == 12
    assert encoded[2].description.count("процентов по ходу серии") == 12


def test_rest_only_group_keeps_its_author_instructions_in_preview_and_native_text():
    from models.intervals_swim_delivery import encode_intervals_swim

    encoded = encode_intervals_swim(project([
        swim("work", 50),
        group("rest_only", 2, [rest("rest")], instructions="Паузы стоя у бортика", last_rest="include"),
    ]))
    assert all("Паузы стоя у бортика" in rest_step.cue for rest_step in encoded.steps[1:])
    assert encoded.description.count("Паузы стоя у бортика") == 2



def test_lap_metadata_never_counts_as_prescribed_rest_or_distance():
    from models.intervals_swim_delivery import encode_intervals_swim, verify_intervals_swim

    workout = encode_intervals_swim(control_workout())
    assert workout.steps[5].duration_seconds is None
    provider = provider_compiled_workout()
    assert verify_intervals_swim(workout, provider) is None
    provider["steps"][5]["distance"] = 1
    mismatch = verify_intervals_swim(workout, provider)
    assert mismatch.code == "step_mismatch" and mismatch.step_number == 6
    provider["steps"].pop(5)
    assert verify_intervals_swim(workout, provider).code == "step_count"
