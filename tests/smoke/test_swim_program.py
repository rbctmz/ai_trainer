"""M1 behavioral contract: exact source, series, environment and uncertainty."""
from copy import deepcopy
import pytest
from pydantic import ValidationError
from models.swim_program import SwimProgramDocument, summarize_program
from tests.smoke._swim_program_fixtures import example_program

pytestmark = pytest.mark.smoke


def test_nested_program_preserves_exact_distances_source_and_meaning():
    raw = example_program()
    document = SwimProgramDocument.model_validate(raw)
    summary = summarize_program(document)
    assert [w["distance_meters"] for w in summary["workouts"]] == [2200, 2000, 1900]
    assert summary["distance_meters"] == 6100
    assert summary["duration_seconds"] is None and summary["tss"] is None
    assert document.source_text == raw["source_text"]
    assert document.workouts[2].steps[3].steps[0].effort.start_percent == 50
    breath_rest = document.workouts[2].steps[3].steps[0].steps[1]
    assert breath_rest.mode == "open" and breath_rest.seconds is None and breath_rest.breaths == 3
    assert document.workouts[2].steps[-1].stroke == "butterfly"
    assert document.workouts[2].steps[-1].equipment == ["fins"]
    assert all(w["compatibility"] == "compatible" for w in summary["workouts"])


def test_pool50_marks_25m_parts_without_altering_them():
    raw = example_program()
    raw["workouts"][2]["pool_length_meters"] = 50
    document = SwimProgramDocument.model_validate(raw)
    before = document.model_dump(mode="json")
    summary = summarize_program(document)
    assert summary["workouts"][2]["compatibility"] == "incompatible"
    assert any(w["code"] == "pool_distance_not_multiple" and w["node_id"] == "three.25" for w in summary["warnings"])
    assert document.model_dump(mode="json") == before
    assert summary["distance_meters"] == 6100


@pytest.mark.parametrize("mutation", [
    lambda p: p.update(schema_version=True),
    lambda p: p.update(origin="generated"),
    lambda p: p.update(source_text="   "),
    lambda p: p.update(unexpected="PRIVATE_CANARY"),
    lambda p: p["workouts"][0].update(environment="unknown"),
    lambda p: p["workouts"][0].update(pool_length_meters=None),
    lambda p: p["workouts"][0].update(pool_length_meters=True),
    lambda p: p["workouts"][0]["steps"][0].update(distance_meters=True),
    lambda p: p["workouts"][0]["steps"][0].update(distance_meters=25.5),
    lambda p: p["workouts"][0]["steps"][0].update(distance_meters=0),
    lambda p: p["workouts"][0]["steps"][0].update(id="one"),
    lambda p: p["workouts"][0]["steps"][3].update(repetitions=0),
    lambda p: p["workouts"][0]["steps"][3]["steps"][1].update(seconds=None),
    lambda p: p["workouts"][0]["steps"][3]["steps"][-1].update(seconds=30),
    lambda p: p["workouts"][2]["steps"][3]["steps"][0]["effort"].update(end_percent=20),
])
def test_invalid_documents_refuse_instead_of_coercing_or_inventing(mutation):
    raw = example_program()
    mutation(raw)
    with pytest.raises(ValidationError):
        SwimProgramDocument.model_validate(raw)


def test_open_water_has_no_pool_length_and_preserves_distance():
    raw = example_program()
    raw["workouts"][0].update(environment="open_water", pool_length_meters=None)
    doc = SwimProgramDocument.model_validate(raw)
    assert summarize_program(doc)["workouts"][0]["compatibility"] == "not_applicable"
    raw["workouts"][0]["pool_length_meters"] = 25
    with pytest.raises(ValidationError):
        SwimProgramDocument.model_validate(raw)


def test_recursive_resource_limits_are_checked_before_expansion():
    raw = example_program()
    node = deepcopy(raw["workouts"][0]["steps"][0])
    for i in range(8):
        node = {"kind": "group", "id": f"deep{i}", "name": "Deep", "repetitions": 2, "steps": [node]}
    raw["workouts"][0]["steps"] = [node]
    with pytest.raises(ValidationError):
        SwimProgramDocument.model_validate(raw)
    raw = example_program()
    raw["workouts"][2]["steps"][3]["repetitions"] = 100
    raw["workouts"][2]["steps"][3]["steps"][0]["repetitions"] = 100
    with pytest.raises(ValidationError):
        SwimProgramDocument.model_validate(raw)


def test_stored_node_limit_is_independent_of_workout_count():
    raw = example_program()
    raw['workouts'] = raw['workouts'][:1]
    groups = []
    for i in range(10):
        groups.append({'kind': 'group', 'id': f'g{i}', 'name': 'Set', 'repetitions': 1,
                       'steps': [{'kind': 'swim', 'id': f'n{i}.{j}', 'name': 'Swim',
                                  'distance_meters': 25} for j in range(99)]})
    raw['workouts'][0]['steps'] = groups  # 10 groups + 990 leaves = exactly 1000.
    assert summarize_program(SwimProgramDocument.model_validate(raw))['distance_meters'] == 24750
    raw['workouts'][0]['steps'][0]['steps'].append(
        {'kind': 'swim', 'id': 'extra', 'name': 'Swim', 'distance_meters': 25})
    with pytest.raises(ValidationError, match='program tree limit'):
        SwimProgramDocument.model_validate(raw)


@pytest.mark.parametrize('field', ['title', 'name'])
def test_blank_workout_or_step_labels_are_not_valid_structure(field):
    raw = example_program()
    part = raw['workouts'][0] if field == 'title' else raw['workouts'][0]['steps'][0]
    part[field] = '   '
    with pytest.raises(ValidationError):
        SwimProgramDocument.model_validate(raw)
