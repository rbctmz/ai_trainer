"""Rich semantics without inventing metres or changing accepted schema1 bytes."""

from copy import deepcopy
import pytest
from pydantic import ValidationError
from models.swim_program import SwimProgramDocument, canonical_json
from models.swim_program_documents import (
    validate_program_document,
    fingerprint_program,
    summarize_document,
)
from models.swim_program_v2 import SwimProgramDocumentV2
from tests.smoke._swim_program_fixtures import example_program
from tests.smoke._swim_import_fixtures import exact_program_v2, rich_program, meters
from tests.smoke.test_swim_exercise import definition
from models.swim_exercise import SwimExerciseDocument, exercise_fingerprint

pytestmark = pytest.mark.smoke


def test_frozen_v1_document_hash_and_summary():
    raw = example_program()
    old = SwimProgramDocument.model_validate(raw)
    adapted = validate_program_document(raw)
    assert adapted.model_dump(mode="json") == old.model_dump(mode="json")
    assert (
        fingerprint_program(adapted)
        == "f8ab86b8a0b02eb8d670958425c0d61b6ba351552a72931a0c7a571d55725272"
    )
    assert canonical_json(summarize_document(adapted)) == canonical_json(
        {
            "distance_meters": 6100,
            "duration_seconds": None,
            "tss": None,
            "workouts": [
                {
                    "workout_id": name,
                    "distance_meters": m,
                    "compatibility": "compatible",
                }
                for name, m in [("one", 2200), ("two", 2000), ("three", 1900)]
            ],
            "warnings": [
                {"code": "last_rest_unspecified", "workout_id": w, "node_id": n}
                for w, n in [
                    ("one", "one.main"),
                    ("two", "two.main"),
                    ("three", "three.rounds"),
                    ("three", "three.reps"),
                ]
            ],
        }
    )


def test_exact_rich_program_keeps_reference_distance_totals():
    document = validate_program_document(exact_program_v2())
    assert isinstance(document, SwimProgramDocumentV2)
    result = summarize_document(document)
    assert result["distance_meters"] == result["known_distance_meters"] == 6100
    assert [w["distance_meters"] for w in result["workouts"]] == [2200, 2000, 1900]
    assert result["duration_seconds"] is None and result["tss"] is None


def test_timed_cycle_preserves_finish_rule_and_unknown_total():
    doc = SwimProgramDocumentV2.model_validate(rich_program())
    result = summarize_document(doc)
    assert result["distance_meters"] is None
    assert result["known_distance_meters"] == 1000
    assert result["duration_seconds"] is None and result["tss"] is None
    repeat = doc.model_dump(mode="json")["workouts"][0]["steps"][1]["repeat"]
    assert repeat == {"kind": "time", "seconds": 1800, "finish": "current_cycle"}
    assert doc.source_text == rich_program()["source_text"]


def test_attempt_hint_never_becomes_prescribed_distance():
    raw = rich_program()
    raw["workouts"][0]["steps"][1] = {
        "kind": "swim",
        "id": "one.skill",
        "name": "Skill attempts",
        "quantity": {
            "kind": "attempts",
            "count": {"minimum": 10, "maximum": 15},
            "distance_hint_meters": 10,
        },
    }
    doc = validate_program_document(raw)
    assert summarize_document(doc)["distance_meters"] is None
    assert summarize_document(doc)["known_distance_meters"] == 1000
    assert doc.model_dump(mode="json")["workouts"][0]["steps"][1]["quantity"][
        "count"
    ] == {"minimum": 10, "maximum": 15}


def test_rest_ranges_and_relative_scope_roundtrip():
    raw = rich_program()
    raw["workouts"][0]["steps"] = [
        meters(
            "one.swim",
            100,
            effort={
                "kind": "subjective",
                "start_percent": 50,
                "end_percent": 90,
                "scope": "within_node",
            },
        ),
        {
            "kind": "rest",
            "id": "one.rest",
            "mode": "approximate",
            "seconds": {"minimum": 60, "maximum": 70},
        },
        {
            "kind": "rest",
            "id": "one.breaths",
            "mode": "open",
            "breaths": {"minimum": 3, "maximum": 4},
        },
    ]
    doc = validate_program_document(raw)
    payload = doc.model_dump(mode="json")
    assert payload["workouts"][0]["steps"][1]["seconds"] == {
        "minimum": 60,
        "maximum": 70,
    }
    assert payload["workouts"][0]["steps"][2]["breaths"] == {"minimum": 3, "maximum": 4}
    assert payload["workouts"][0]["steps"][0]["effort"]["scope"] == "within_node"
    assert summarize_document(doc)["distance_meters"] == 100


def test_repeat_range_is_not_replaced_by_minimum_or_midpoint():
    raw = rich_program()
    raw["workouts"][0]["steps"][1]["repeat"] = {
        "kind": "count",
        "count": {"minimum": 2, "maximum": 4},
    }
    doc = validate_program_document(raw)
    assert summarize_document(doc)["distance_meters"] is None
    assert summarize_document(doc)["known_distance_meters"] == 1000


def test_pinned_exercise_self_validation_and_environment_signal():
    raw = rich_program()
    exercise = SwimExerciseDocument.model_validate(definition())
    raw["exercise_bindings"] = [
        {
            "node_id": "one.fixed",
            "exercise_id": str(exercise.id),
            "revision": 1,
            "fingerprint": exercise_fingerprint(exercise),
            "document": exercise.model_dump(mode="json"),
        }
    ]
    document = validate_program_document(raw)
    saved = document.model_dump(mode="json")
    exercise.instructions = "Later catalog modification"
    assert (
        saved["exercise_bindings"][0]["document"]["instructions"]
        == "Keep original instruction."
    )
    raw["workouts"][0]["environment"] = "open_water"
    raw["workouts"][0]["pool_length_meters"] = None
    result = summarize_document(validate_program_document(raw))
    assert any(w["code"] == "exercise_environment_mismatch" for w in result["warnings"])
    bad = deepcopy(raw)
    bad["exercise_bindings"][0]["document"]["instructions"] = "Untrusted replacement"
    with pytest.raises(ValidationError):
        validate_program_document(bad)


@pytest.mark.parametrize(
    "change",
    [
        "source_hash",
        "span",
        "duplicate_id",
        "bool_metres",
        "rest_clock",
        "fixed_range",
        "unknown_schema",
    ],
)
def test_malformed_rich_documents_are_rejected(change):
    raw = rich_program()
    if change == "source_hash":
        raw["source_text"] += "changed"
    elif change == "span":
        raw["source_spans"] = [{"start": 0, "end": 9999}]
    elif change == "duplicate_id":
        raw["workouts"][0]["steps"][1]["id"] = "one.fixed"
    elif change == "bool_metres":
        raw["workouts"][0]["steps"][0]["quantity"]["meters"] = True
    elif change == "rest_clock":
        raw["workouts"][0]["steps"][0] = {
            "kind": "rest",
            "id": "x",
            "mode": "open",
            "seconds": {"minimum": 10, "maximum": 10},
        }
    elif change == "fixed_range":
        raw["workouts"][0]["steps"][0] = {
            "kind": "rest",
            "id": "x",
            "mode": "fixed",
            "seconds": {"minimum": 10, "maximum": 20},
        }
    else:
        raw["schema_version"] = 3
    with pytest.raises(ValidationError):
        validate_program_document(raw)


def test_unicode_source_coverage_and_unresolved_are_explicit():
    import hashlib

    raw = rich_program()
    raw["source_text"] = "🏊 Разминка\nНеясная часть"
    raw["source_sha256"] = hashlib.sha256(raw["source_text"].encode()).hexdigest()
    raw["source_spans"] = [{"start": 0, "end": 10}]
    raw["workouts"][0]["steps"] = [
        {
            "kind": "unresolved",
            "id": "unclear",
            "instructions": "Retain wording",
            "question": "Which scope?",
            "source_spans": [{"start": 11, "end": 15}],
        }
    ]
    summary = summarize_document(validate_program_document(raw))
    assert summary["distance_meters"] is None
    assert summary["source_gaps"] == [{"start": 15, "end": len(raw["source_text"])}]
    assert {w["code"] for w in summary["warnings"]} == {
        "unresolved_source",
        "source_not_covered",
    }


@pytest.mark.parametrize("version", [True, 2.0, "2"])
def test_version_dispatch_never_coerces(version):
    raw = rich_program()
    raw["schema_version"] = version
    with pytest.raises(ValidationError):
        validate_program_document(raw)


def test_expansion_depth_and_identity_limits():
    raw = rich_program()
    child = meters("leaf", 100)
    for level in range(7):
        child = {
            "kind": "group",
            "id": f"group{level}",
            "name": "Repeat",
            "repeat": {"kind": "count", "count": {"minimum": 100, "maximum": 100}},
            "steps": [child],
        }
    raw["workouts"][0]["steps"] = [child]
    with pytest.raises(ValidationError):
        validate_program_document(raw)
    raw["workouts"][0]["steps"] = [child["steps"][0]["steps"][0]["steps"][0]]
    with pytest.raises(ValidationError, match="expanded program limit"):
        validate_program_document(raw)
