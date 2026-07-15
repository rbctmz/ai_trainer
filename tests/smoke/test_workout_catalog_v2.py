from __future__ import annotations

from dataclasses import replace
import json

import pytest

from data.database import Database
from models.intervals_workout_delivery import build_intervals_workout_description
from models.planning_checkpoints import (
    build_planning_checkpoint,
    restore_goal_plan_from_checkpoint,
)
from models.workout_catalog import (
    CATALOG_VERSION,
    MATERIALIZER_RULE_VERSION,
    SELECTOR_RULE_VERSION,
    catalog_definitions,
    materialize_brick_session,
    materialize_workout,
)


pytestmark = pytest.mark.smoke


def _definition(template_key: str):
    return next(
        definition
        for definition in catalog_definitions()
        if definition.template_key == template_key
    )


def _assert_exact(result: dict, *, seconds: int, tss: float) -> None:
    steps = result["steps"]
    assert steps
    assert all(step["duration_seconds"] > 0 for step in steps)
    assert [step["index"] for step in steps] == list(range(len(steps)))
    assert sum(step["duration_seconds"] for step in steps) == seconds
    assert sum(step["tss"] for step in steps) == pytest.approx(tss, abs=0.01)


def test_v2_versions_only_change_materialization_and_changed_definitions() -> None:
    definitions = {item.template_key: item for item in catalog_definitions()}

    assert CATALOG_VERSION == "workout_catalog_v2"
    assert SELECTOR_RULE_VERSION == "workout_selector_v1"
    assert MATERIALIZER_RULE_VERSION == "workout_materializer_v2"
    assert len(definitions) == 20
    assert definitions["bike_threshold_intervals"].version == 2
    assert definitions["run_tempo_threshold"].version == 2
    assert definitions["brick_race_pace"].version == 2
    assert definitions["swim_threshold_repeats"].version == 1
    assert definitions["walk_recovery"].version == 1
    assert definitions["bike_race_pace"].version == 1


def test_every_catalog_definition_is_exact_and_deterministic_at_feasible_bounds() -> None:
    zone_snapshot = {
        "ftp": 200,
        "threshold_pace": 300,
        "lthr": 165,
        "css": 110,
    }

    for definition in catalog_definitions():
        feasible_cases = 0
        for minutes in {
            definition.min_duration_minutes,
            (definition.min_duration_minutes + definition.max_duration_minutes) // 2,
            definition.max_duration_minutes,
        }:
            low_tss = max(
                definition.min_tss,
                definition.min_tss_per_hour * minutes / 60.0,
            )
            high_tss = min(
                definition.max_tss,
                definition.max_tss_per_hour * minutes / 60.0,
            )
            if low_tss > high_tss:
                continue
            target_tss = round((low_tss + high_tss) / 2.0, 1)
            parameters = {
                "duration_minutes": minutes,
                "target_tss": target_tss,
            }

            first = materialize_workout(definition, parameters, zone_snapshot)
            second = materialize_workout(definition, parameters, zone_snapshot)

            assert first == second, definition.template_key
            assert first["materialization_status"] == "materialized", (
                definition.template_key,
                minutes,
                target_tss,
            )
            _assert_exact(first, seconds=minutes * 60, tss=target_tss)
            if first["structure_evidence"]["repeat_count"] is not None:
                assert first["steps"][0]["segment_kind"] == "warmup"
                assert first["steps"][0]["duration_seconds"] >= 5 * 60
                assert first["steps"][-1]["segment_kind"] == "cooldown"
                assert first["steps"][-1]["duration_seconds"] >= 5 * 60
            feasible_cases += 1
        assert feasible_cases > 0, definition.template_key


def test_bike_threshold_materializes_numbered_repeats_deterministically() -> None:
    definition = _definition("bike_threshold_intervals")
    parameters = {"duration_minutes": 60, "target_tss": 80.0}

    first = materialize_workout(definition, parameters, {"ftp": 200})
    second = materialize_workout(definition, parameters, {"ftp": 200})

    assert first == second
    assert first["structure_status"] == "structured"
    assert first["structure_evidence"] == {
        "rule_version": "workout_structure_v2",
        "prescription_key": "bike_threshold",
        "tier": "medium",
        "repeat_count": 3,
        "simplification_reason": None,
    }
    assert [step["name"] for step in first["steps"]] == [
        "Warm-up",
        "Threshold 1/3",
        "Recovery 1/2",
        "Threshold 2/3",
        "Recovery 2/2",
        "Threshold 3/3",
        "Cool-down",
    ]
    assert [
        step["duration_seconds"]
        for step in first["steps"]
        if step.get("segment_kind") == "work"
    ] == [480, 480, 480]
    assert [
        step["duration_seconds"]
        for step in first["steps"]
        if step.get("segment_kind") == "recovery"
    ] == [240, 240]
    assert all(
        step["target"]["type"] == "power"
        for step in first["steps"]
    )
    _assert_exact(first, seconds=3600, tss=80.0)


@pytest.mark.parametrize(
    ("template_key", "minutes", "tss", "expected_work_name", "expected_count"),
    [
        ("bike_tempo_sweet_spot", 70, 70.0, "Tempo 1/3", 3),
        ("bike_vo2max_intervals", 50, 70.0, "VO2 1/5", 5),
        ("bike_neuromuscular_sprints", 45, 50.0, "Sprint 1/8", 8),
        ("bike_race_pace", 60, 70.0, "Race pace 1/3", 3),
    ],
)
def test_bike_quality_families_have_explicit_work_recovery_repeats(
    template_key: str,
    minutes: int,
    tss: float,
    expected_work_name: str,
    expected_count: int,
) -> None:
    definition = _definition(template_key)
    result = materialize_workout(
        definition,
        {"duration_minutes": minutes, "target_tss": tss},
        {"ftp": 200},
    )

    assert result["materialization_status"] == "materialized"
    assert result["structure_status"] == "structured"
    assert result["structure_evidence"]["repeat_count"] == expected_count
    assert expected_work_name in [step["name"] for step in result["steps"]]
    assert sum(
        step.get("segment_kind") == "work" for step in result["steps"]
    ) == expected_count
    assert sum(
        step.get("segment_kind") == "recovery" for step in result["steps"]
    ) == expected_count - 1
    _assert_exact(result, seconds=minutes * 60, tss=tss)


def test_run_vo2_uses_pace_then_lthr_then_rpe_without_ftp_semantics() -> None:
    definition = _definition("run_vo2_neuromuscular")
    parameters = {"duration_minutes": 60, "target_tss": 70.0}

    pace = materialize_workout(
        definition,
        parameters,
        {"threshold_pace": 300, "lthr": 165, "ftp": 250},
    )
    heart_rate = materialize_workout(
        definition,
        parameters,
        {"lthr": 165, "ftp": 250},
    )
    fallback = materialize_workout(definition, parameters, {"ftp": 250})

    assert pace["target_provenance"]["kind"] == "threshold_pace"
    assert pace["target_provenance"]["scale"] == "absolute_pace_from_threshold"
    assert heart_rate["target_provenance"]["kind"] == "lthr"
    assert heart_rate["target_provenance"]["scale"] == "absolute_hr_from_lthr"
    assert fallback["target_provenance"]["kind"] == "relative_rpe"
    assert fallback["target_provenance"]["scale"] == "relative_rpe"
    assert fallback["target_provenance"]["missing"] == ["threshold_pace", "lthr"]
    assert all(step["target"]["type"] == "pace" for step in pace["steps"])
    assert all(
        step["target"]["type"] == "heart_rate" for step in heart_rate["steps"]
    )
    assert all(
        step["target"]["reference"] == "lthr" for step in heart_rate["steps"]
    )
    assert all(
        step["target"]["type"] == "relative_rpe" for step in fallback["steps"]
    )
    assert [
        step["name"] for step in pace["steps"] if step.get("segment_kind") == "work"
    ] == [f"VO2 {index}/5" for index in range(1, 6)]
    _assert_exact(pace, seconds=3600, tss=70.0)


@pytest.mark.parametrize(
    ("template_key", "expected_names"),
    [
        (
            "run_aerobic_endurance",
            ["Warm-up", "Aerobic endurance", "Steady finish", "Cool-down"],
        ),
        (
            "run_progression",
            ["Warm-up", "Aerobic", "Moderate", "Strong finish", "Cool-down"],
        ),
        (
            "bike_aerobic_progression",
            ["Warm-up", "Aerobic", "Moderate", "Strong finish", "Cool-down"],
        ),
    ],
)
def test_endurance_and_progression_use_ordered_positive_stages(
    template_key: str,
    expected_names: list[str],
) -> None:
    definition = _definition(template_key)
    minutes = max(60, definition.min_duration_minutes)
    tss = min(max(50.0, definition.min_tss), definition.max_tss)
    zones = {"ftp": 200} if definition.sport == "bike" else {"threshold_pace": 300}

    result = materialize_workout(
        definition,
        {"duration_minutes": minutes, "target_tss": tss},
        zones,
    )

    assert result["structure_status"] == "structured"
    assert result["structure_evidence"]["repeat_count"] is None
    assert [step["name"] for step in result["steps"]] == expected_names
    _assert_exact(result, seconds=minutes * 60, tss=tss)


def test_too_short_repeat_budget_fails_closed_to_declared_simpler_structure() -> None:
    threshold = _definition("bike_threshold_intervals")
    synthetic_short = replace(
        threshold,
        min_duration_minutes=10,
        min_tss=1.0,
        min_tss_per_hour=1.0,
    )

    result = materialize_workout(
        synthetic_short,
        {"duration_minutes": 12, "target_tss": 10.0},
        {"ftp": 200},
    )

    assert result["materialization_status"] == "materialized"
    assert result["structure_status"] == "simplified"
    assert result["structure_evidence"]["repeat_count"] is None
    assert result["structure_evidence"]["simplification_reason"] == (
        "repeat_budget_below_short_tier"
    )
    assert [step["name"] for step in result["steps"]] == [
        "Warm-up",
        "Controlled aerobic",
        "Cool-down",
    ]
    _assert_exact(result, seconds=720, tss=10.0)


def test_peak_brick_reuses_race_pace_builders_and_build_reuses_endurance() -> None:
    common = {
        "target_tss": 90.0,
        "parts": {"bike": 60.0, "run": 30.0, "swim": 0.0},
        "estimated_duration_minutes": 120,
        "goal_type": "triathlon",
        "zone_snapshot": {"ftp": 200, "threshold_pace": 300, "lthr": 165},
    }

    build = materialize_brick_session(phase="Build", **common)
    peak = materialize_brick_session(phase="Peak", **common)

    assert [leg["template_key"] for leg in build["legs"]] == [
        "bike_aerobic_endurance",
        "run_aerobic_endurance",
    ]
    assert [leg["template_key"] for leg in peak["legs"]] == [
        "bike_race_pace",
        "run_race_pace",
    ]
    assert [leg["sport"] for leg in peak["legs"]] == ["bike", "run"]
    assert all(leg["materialized_steps"] for leg in peak["legs"])
    assert peak["legs"][0]["target_provenance"]["kind"] == "ftp"
    assert peak["legs"][1]["target_provenance"]["kind"] == "threshold_pace"
    assert sum(leg["target_tss"] for leg in peak["legs"]) == pytest.approx(90.0)
    assert sum(leg["duration_minutes"] for leg in peak["legs"]) + 5 == peak[
        "duration_minutes"
    ]


def test_intervals_text_preserves_repeat_order_and_sport_target_types() -> None:
    bike = materialize_workout(
        _definition("bike_threshold_intervals"),
        {"duration_minutes": 60, "target_tss": 80.0},
        {"ftp": 200},
    )
    run = materialize_workout(
        _definition("run_tempo_threshold"),
        {"duration_minutes": 60, "target_tss": 70.0},
        {"threshold_pace": 300},
    )

    bike_text = build_intervals_workout_description(bike["steps"], title="Bike")
    run_text = build_intervals_workout_description(run["steps"], title="Run")

    assert all(
        line.startswith(f"- {step['name']} ")
        for line, step in zip(bike_text.splitlines()[1:], bike["steps"])
    )
    assert all(
        line.startswith(f"- {step['name']} ")
        for line, step in zip(run_text.splitlines()[1:], run["steps"])
    )
    assert all(line.endswith("w") for line in bike_text.splitlines()[1:])
    assert all(line.endswith("/km") for line in run_text.splitlines()[1:])
    assert "%" not in run_text


def test_intervals_serializes_lthr_fallback_as_supported_lthr_percentage() -> None:
    run = materialize_workout(
        _definition("run_tempo_threshold"),
        {"duration_minutes": 60, "target_tss": 70.0},
        {"lthr": 165},
    )

    text = build_intervals_workout_description(run["steps"], title="Run")

    assert run["target_provenance"]["scale"] == "absolute_hr_from_lthr"
    assert all(line.endswith("% LTHR") for line in text.splitlines()[1:])
    assert "bpm" not in text
    assert "% HR" not in text


def test_restoring_explicit_v1_checkpoint_does_not_upgrade_prescription(tmp_path) -> None:
    v1_template = {
        "date": "2026-07-15",
        "kind": "single",
        "sport": "bike",
        "catalog_version": "workout_catalog_v1",
        "selector_rule_version": "workout_selector_v1",
        "materializer_rule_version": "workout_materializer_v1",
        "template_key": "bike_threshold_intervals",
        "template_version": 1,
        "definition_snapshot": {
            "template_key": "bike_threshold_intervals",
            "version": 1,
            "catalog_version": "workout_catalog_v1",
        },
        "materialized_steps": [
            {
                "index": 0,
                "name": "Threshold intervals",
                "intensity": "work",
                "duration_seconds": 3600,
                "tss": 80.0,
                "target": {"type": "power", "unit": "watts", "low": 194, "high": 206},
            }
        ],
        "prescription_fingerprint": "v1-frozen",
    }
    plan = {
        "goal_type": "Триатлон",
        "distance": "Олимпийка",
        "daily_plan": [("2026-07-15", 80.0, {"run": 0.0, "bike": 80.0, "swim": 0.0})],
        "session_templates": [v1_template],
        "weekly_summary": [],
        "weekly_tss_plan": [],
        "base_weekly_tss_plan": [],
        "phases": [],
        "constraint_summary": {},
    }
    db = Database(str(tmp_path / "v1-checkpoint.db"))
    db.save_planning_checkpoint(build_planning_checkpoint(plan))
    checkpoint = db.get_latest_planning_checkpoint()

    restored = restore_goal_plan_from_checkpoint(checkpoint)

    restored_template = restored["session_templates"][0]
    for key, value in v1_template.items():
        assert json.dumps(restored_template[key], sort_keys=True) == json.dumps(
            value,
            sort_keys=True,
        )
