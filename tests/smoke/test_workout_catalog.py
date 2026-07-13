from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta

import pytest

from models.workout_catalog import (
    CATALOG_VERSION,
    MATERIALIZER_RULE_VERSION,
    SELECTOR_RULE_VERSION,
    catalog_definitions,
    materialize_workout,
    prepare_weekly_brick_allocations,
    select_workout_template,
)


pytestmark = pytest.mark.smoke


EXPECTED_TEMPLATE_KEYS = {
    "bike_recovery_spin",
    "bike_aerobic_endurance",
    "bike_aerobic_progression",
    "bike_tempo_sweet_spot",
    "bike_threshold_intervals",
    "bike_vo2max_intervals",
    "bike_neuromuscular_sprints",
    "run_recovery",
    "run_aerobic_endurance",
    "run_progression",
    "run_tempo_threshold",
    "run_vo2_neuromuscular",
    "run_race_pace",
    "swim_technique_aerobic",
    "swim_endurance",
    "swim_threshold_repeats",
    "walk_recovery",
    "brick_endurance",
    "brick_race_pace",
}


def _definition(template_key: str):
    return next(item for item in catalog_definitions() if item.template_key == template_key)


def _selection_context(**overrides):
    context = {
        "sport": "bike",
        "session_role": "quality",
        "phase": "Base",
        "goal_type": "triathlon",
        "duration_minutes": 60,
        "target_tss": 60.0,
        "load_state": "balanced",
        "recent_template_keys": [],
    }
    context.update(overrides)
    return context


def test_catalog_is_exact_versioned_and_immutable():
    definitions = catalog_definitions()

    assert CATALOG_VERSION == "workout_catalog_v1"
    assert SELECTOR_RULE_VERSION == "workout_selector_v1"
    assert MATERIALIZER_RULE_VERSION == "workout_materializer_v1"
    assert len(definitions) == 19
    assert {item.template_key for item in definitions} == EXPECTED_TEMPLATE_KEYS
    assert len({(item.template_key, item.version) for item in definitions}) == 19
    assert all(item.min_duration_minutes <= item.max_duration_minutes for item in definitions)
    assert all(item.min_tss_per_hour <= item.max_tss_per_hour for item in definitions)
    assert all(len(item.fatigue_cost) == 3 for item in definitions)

    with pytest.raises(FrozenInstanceError):
        definitions[0].display_name = "mutated"


def test_selector_changes_stimulus_between_base_and_build_for_same_request():
    base = select_workout_template(_selection_context(phase="Base"))
    build = select_workout_template(_selection_context(phase="Build"))

    assert base["status"] == "selected"
    assert build["status"] == "selected"
    assert base["definition"]["template_key"] == "bike_aerobic_progression"
    assert build["definition"]["template_key"] == "bike_threshold_intervals"
    assert base["definition"]["stimulus"] != build["definition"]["stimulus"]
    assert base["selection_evidence"]["rule_version"] == SELECTOR_RULE_VERSION
    assert build["selection_evidence"]["phase"] == "Build"


def test_selector_rotates_recent_exposure_and_guards_deep_fatigue():
    rotated = select_workout_template(
        _selection_context(
            phase="Build",
            recent_template_keys=["bike_threshold_intervals"],
        )
    )
    fatigued = select_workout_template(
        _selection_context(phase="Build", load_state="deep_fatigue")
    )

    assert rotated["definition"]["template_key"] != "bike_threshold_intervals"
    assert "recent_exposure" in rotated["selection_evidence"]["excluded_reasons"]
    assert max(fatigued["definition"]["fatigue_cost"]) < 3
    assert fatigued["definition"]["template_key"] not in {
        "bike_threshold_intervals",
        "bike_vo2max_intervals",
    }


def test_materializer_preserves_exact_seconds_tss_and_ftp_provenance():
    result = materialize_workout(
        _definition("bike_threshold_intervals"),
        {"duration_minutes": 60, "target_tss": 80.0},
        {"ftp": 200, "lthr": 165},
    )

    assert result["materialization_status"] == "materialized"
    assert result["rule_version"] == MATERIALIZER_RULE_VERSION
    assert sum(step["duration_seconds"] for step in result["steps"]) == 3600
    assert sum(step["tss"] for step in result["steps"]) == pytest.approx(80.0, abs=0.01)
    assert result["target_provenance"] == {
        "kind": "ftp",
        "source": "athlete_profile.ftp",
        "value": 200.0,
        "fallback": False,
    }
    work_steps = [step for step in result["steps"] if step["intensity"] == "work"]
    assert work_steps
    assert all(step["target"]["type"] == "power" for step in work_steps)
    assert all(step["target"]["unit"] == "watts" for step in work_steps)


def test_materializer_reports_infeasible_request_without_stretching():
    result = materialize_workout(
        _definition("bike_threshold_intervals"),
        {"duration_minutes": 30, "target_tss": 15.0},
        {"ftp": 200},
    )

    assert result["materialization_status"] == "infeasible"
    assert result["steps"] == []
    assert set(result["failed_bounds"]) == {
        "duration_below_minimum",
        "tss_below_minimum",
        "density_below_minimum",
    }
    assert result["parameter_snapshot"] == {
        "duration_minutes": 30,
        "target_tss": 15.0,
        "tss_per_hour": 30.0,
    }


def test_materializer_records_relative_fallback_when_absolute_zone_is_missing():
    run = materialize_workout(
        _definition("run_tempo_threshold"),
        {"duration_minutes": 60, "target_tss": 70.0},
        {},
    )
    swim = materialize_workout(
        _definition("swim_threshold_repeats"),
        {"duration_minutes": 60, "target_tss": 60.0},
        {},
    )

    assert run["target_provenance"]["kind"] == "relative_rpe"
    assert run["target_provenance"]["fallback"] is True
    assert run["target_provenance"]["missing"] == ["threshold_pace", "lthr"]
    assert swim["target_provenance"]["kind"] == "relative_rpe"
    assert swim["target_provenance"]["missing"] == ["css"]
    assert all(step["target"]["type"] == "relative_rpe" for step in swim["steps"])


def test_brick_allocator_preserves_day_and_week_sport_totals():
    start = datetime(2026, 7, 13)
    raw_parts = [
        {"run": 5.0, "bike": 5.0, "swim": 20.0},
        {"run": 10.0, "bike": 20.0, "swim": 10.0},
        {"run": 12.0, "bike": 18.0, "swim": 10.0},
        {"run": 10.0, "bike": 20.0, "swim": 10.0},
        {"run": 8.0, "bike": 12.0, "swim": 10.0},
        {"run": 20.0, "bike": 50.0, "swim": 10.0},
        {"run": 5.0, "bike": 5.0, "swim": 10.0},
    ]
    daily = [
        (start + timedelta(days=index), sum(parts.values()), parts)
        for index, parts in enumerate(raw_parts)
    ]
    weekly_summary = [
        {
            "phase": "Build",
            "day_roles": ["easy", "quality", "easy", "recovery", "easy", "long", "off"],
        }
    ]

    result = prepare_weekly_brick_allocations(
        daily,
        weekly_summary,
        goal_type="triathlon",
        protected_dates=set(),
        load_state="balanced",
    )

    assert result["status"] == "allocated"
    assert result["brick_day_indices"] == [5]
    adjusted = result["daily_plan"]
    assert [row[1] for row in adjusted] == [row[1] for row in daily]
    assert adjusted[5][2]["swim"] == 0.0
    assert adjusted[5][2]["bike"] > daily[5][2]["bike"]
    assert adjusted[5][2]["run"] > daily[5][2]["run"]
    for sport in ("run", "bike", "swim"):
        before = sum(row[2][sport] for row in daily)
        after = sum(row[2][sport] for row in adjusted)
        assert after == pytest.approx(before, abs=0.1)
    assert result["evidence"]["weekly_totals_preserved"] is True


def test_brick_allocator_is_conservative_when_swim_cannot_move_or_day_is_protected():
    start = datetime(2026, 7, 13)
    daily = [
        (
            start + timedelta(days=index),
            80.0 if index == 5 else 20.0,
            {"run": 20.0, "bike": 50.0, "swim": 10.0}
            if index == 5
            else {"run": 0.0, "bike": 0.0, "swim": 20.0},
        )
        for index in range(7)
    ]
    summary = [{"phase": "Build", "day_roles": ["easy"] * 5 + ["long", "off"]}]

    no_donor = prepare_weekly_brick_allocations(
        daily,
        summary,
        goal_type="triathlon",
        protected_dates=set(),
        load_state="balanced",
    )
    protected = prepare_weekly_brick_allocations(
        daily,
        summary,
        goal_type="triathlon",
        protected_dates={"2026-07-18"},
        load_state="balanced",
    )

    assert no_donor["status"] == "unchanged"
    assert no_donor["daily_plan"] == daily
    assert no_donor["reason"] == "insufficient_unprotected_donor_capacity"
    assert protected["status"] == "unchanged"
    assert protected["reason"] == "no_eligible_long_day"

