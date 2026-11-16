"""Definitions remain technique; metres and rest belong to their use."""

from copy import deepcopy
import pytest
from pydantic import ValidationError
from models.swim_exercise import SwimExerciseDocument, exercise_fingerprint, make_step

pytestmark = pytest.mark.smoke
EXERCISE_ID = "33333333-3333-4333-8333-333333333333"


def definition():
    return {
        "schema_version": 1,
        "id": EXERCISE_ID,
        "name": "Synthetic technique",
        "variant": "One arm",
        "aliases": ["Example alias"],
        "instructions": "Keep original instruction.",
        "stroke": "drill",
        "equipment": ["fins"],
        "environments": ["pool"],
        "source_label": "Anonymous example",
        "source_text": "  Original excerpt\n",
        "video_cues": [
            {
                "source_label": "Private source label",
                "start_seconds": 10,
                "end_seconds": 25,
            }
        ],
    }


def test_definition_and_assignment_are_independent():
    raw = definition()
    doc = SwimExerciseDocument.model_validate(raw)
    step = make_step(
        doc, node_id="one.drill", distance_meters=50, instructions="Use left arm."
    )
    assert step.distance_meters == 50 and step.equipment == ["fins"]
    assert "One arm" in step.instructions and "Use left arm." in step.instructions
    assert doc.source_text == raw["source_text"]
    assert "distance_meters" not in doc.model_dump()
    changed = deepcopy(raw)
    changed["variant"] = "Different variant"
    assert exercise_fingerprint(doc) != exercise_fingerprint(
        SwimExerciseDocument.model_validate(changed)
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("name", "  "),
        ("variant", ""),
        ("instructions", ""),
        ("aliases", ["alias", "ALIAS"]),
        ("equipment", ["fins", "fins"]),
        ("environments", []),
        ("environments", ["pool", "pool"]),
        ("schema_version", True),
        ("distance_meters", 50),
        ("rest_seconds", 60),
        ("video_cues", [{"source_label": "x", "start_seconds": 10, "end_seconds": 10}]),
        (
            "video_cues",
            [{"source_label": "x", "start_seconds": False, "end_seconds": 20}],
        ),
    ],
)
def test_definition_refuses_ambiguous_or_prescriptive_payload(field, value):
    raw = definition()
    raw[field] = value
    with pytest.raises(ValidationError):
        SwimExerciseDocument.model_validate(raw)
