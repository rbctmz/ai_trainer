"""S3 M2: Recovery eligibility, feasible selection and explicit RPE semantics."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

import pytest

from models import workout_catalog as wc


def _request(**patch):
    return dict(
        phase="Base",
        sport="bike",
        session_role="quality",
        target_tss=25,
        estimated_duration_minutes=45,
        goal_type="triathlon",
        zone_snapshot={"ftp": 200, "threshold_pace": 300},
        **patch,
    )


@pytest.mark.parametrize("sport", ["bike", "run", "swim"])
@pytest.mark.parametrize("role", ["easy", "quality", "long"])
@pytest.mark.parametrize("zones", [{}, {"ftp": 200, "threshold_pace": 300, "css": 110}])
def test_recovery_uses_light_prescriptions_for_every_scheduled_role(sport, role, zones):
    result = wc.materialize_session_template(
        phase="Recovery",
        sport=sport,
        session_role=role,
        target_tss=15,
        estimated_duration_minutes=30,
        goal_type="triathlon",
        zone_snapshot=zones,
    )
    assert result["materialization_status"] == "materialized"
    assert result["materialized_steps"]
    assert result["session_role"] == "recovery"
    assert result["definition_snapshot"]["step_builder_key"] in {
        "recovery",
        "technique",
    }
    assert max(result["fatigue_cost"]) <= 1
    assert not result.get("failed_bounds")
    assert (
        sum(s["duration_seconds"] for s in result["materialized_steps"])
        == result["duration_minutes"] * 60
    )


@pytest.mark.parametrize("sport,target,minutes", [("bike", 25, 45), ("run", 24, 30)])
def test_low_dose_quality_has_explicit_light_fallback_instead_of_invalid_steps(
    sport, target, minutes
):
    result = wc.materialize_session_template(
        **{
            **_request(),
            "sport": sport,
            "target_tss": target,
            "estimated_duration_minutes": minutes,
        }
    )
    assert result["materialization_status"] == "materialized"
    assert result["session_role"] == "easy"
    assert result["selection_evidence"]["requested_role"] == "quality"
    assert result["selection_evidence"]["role_override"] == "quality_to_easy"
    assert result["duration_minutes"] <= minutes
    assert result["parameter_snapshot"]["target_tss"] <= target
    assert not result.get("failed_bounds")


def test_rotation_never_discards_a_feasible_used_quality_prescription():
    result = wc.materialize_session_template(
        **{
            **_request(),
            "target_tss": 35,
            "estimated_duration_minutes": 60,
            "recent_template_keys": ["bike_aerobic_progression"],
        }
    )
    assert result["materialization_status"] == "materialized"
    assert result["template_key"] == "bike_aerobic_progression"
    assert result["selection_evidence"].get("role_override") is None


def test_easy_bike_never_selects_sprints_to_fill_a_load_budget():
    result = wc.materialize_session_template(
        **{
            **_request(),
            "session_role": "easy",
            "target_tss": 24,
            "estimated_duration_minutes": 45,
        }
    )
    assert result["materialization_status"] == "materialized"
    assert result["template_key"] != "bike_neuromuscular_sprints"
    assert result["definition_snapshot"]["step_builder_key"] in {
        "recovery",
        "endurance",
        "technique",
    }


@pytest.mark.parametrize(
    "definition",
    [d for d in wc.catalog_definitions() if d.kind == "single"],
    ids=lambda d: d.template_key,
)
def test_rpe_fallback_is_a_versioned_prescription_for_each_stage(definition):
    minutes = definition.min_duration_minutes
    lo = max(definition.min_tss, definition.min_tss_per_hour * minutes / 60)
    hi = min(definition.max_tss, definition.max_tss_per_hour * minutes / 60)
    result = wc.materialize_workout(
        definition, {"duration_minutes": minutes, "target_tss": (lo + hi) / 2}, {}
    )
    assert result["materialization_status"] == "materialized"
    assert result["target_provenance"]["policy_version"] == "catalog-rpe-v1"
    assert result["target_provenance"]["policy_key"] == definition.template_key
    assert result["definition_snapshot"]["rpe_stage_targets"]
    for s in result["steps"]:
        target = s["target"]
        assert target["type"] == "relative_rpe"
        assert 1 <= target["low"] <= target["high"] <= 10
    if definition.template_key in {
        "swim_recovery_technique",
        "bike_recovery_spin",
        "run_recovery",
        "walk_recovery",
    }:
        assert max(s["target"]["high"] for s in result["steps"]) <= 3


def test_rpe_is_independent_of_fraction_arithmetic():
    definition = next(
        d
        for d in wc.catalog_definitions()
        if d.template_key == "swim_recovery_technique"
    )
    r = wc.materialize_workout(
        definition, {"duration_minutes": 30, "target_tss": 15}, {}
    )
    assert all(s["target"]["high"] <= 3 for s in r["steps"])
    assert r["steps"][2]["target"]["high"] != 8


def test_missing_rpe_policy_is_explicitly_infeasible_not_guessed():
    definition = next(
        d
        for d in wc.catalog_definitions()
        if d.template_key == "swim_recovery_technique"
    )
    definition = replace(definition, rpe_stage_targets=())
    r = wc.materialize_workout(
        definition, {"duration_minutes": 30, "target_tss": 15}, {}
    )
    assert r["materialization_status"] == "infeasible"
    assert "target_semantics_unverified" in r["failed_bounds"]
    assert not r["steps"]


def test_recovery_does_not_admit_threshold_or_activation_definitions():
    for d in wc.catalog_definitions():
        if "Recovery" in d.phase_eligibility:
            assert d.step_builder_key in {"recovery", "technique", "endurance"}


def test_impossible_requests_remain_explicit_and_do_not_mutate_inputs():
    request = _request()
    request.update(target_tss=500, estimated_duration_minutes=30)
    before = deepcopy(request)
    result = wc.materialize_session_template(**request)
    assert result["materialization_status"] != "materialized"
    assert request == before


def test_recovery_primary_role_is_honest_in_builder_description():
    from datetime import datetime
    from models.training_planner import build_daily_session_templates

    templates = build_daily_session_templates(
        [(datetime(2026, 11, 2), 15, {"bike": 15, "run": 0, "swim": 0})],
        [{"phase": "Recovery", "week_start": "2026-11-02"}],
        "Триатлон",
        "Олимпийка",
        zone_snapshot={"ftp": 200},
    )
    session = templates[0]["sessions"][0]
    assert session["materialization_status"] == "materialized"
    assert session["session_role"] == "recovery"
    assert templates[0]["session_role"] == "recovery"


def test_light_replacement_fits_the_failed_power_pair_not_only_schedule_estimate():
    result = wc.materialize_session_template(**_request())
    assert result["selection_evidence"]["role_override"] == "quality_to_easy"
    attempted = result["selection_evidence"]["skipped_candidates"]
    assert attempted
    assert result["duration_minutes"] <= min(a["duration_minutes"] for a in attempted)
    assert result["duration_minutes"] < 45


@pytest.mark.parametrize(
    "version_name",
    ["CATALOG_VERSION", "SELECTOR_RULE_VERSION", "MATERIALIZER_RULE_VERSION"],
)
@pytest.mark.parametrize("applied", [False, True], ids=["pending", "receipt"])
def test_changed_catalog_context_rejects_pending_but_preserves_applied_receipt(
    tmp_path, monkeypatch, version_name, applied
):
    from api import planning_service as ps
    from models.planning_build_confirmation import PlanningBuildPreviewError
    from tests.smoke._planning_build_confirmation import (
        pin_clock,
        protected_state,
        seeded_db,
    )
    from tests.smoke.test_planning_build_commit import prepare, confirm

    pin_clock(monkeypatch)
    db = seeded_db(tmp_path, rested=True)
    with monkeypatch.context() as old:
        old.setattr(ps, version_name, "prior-catalog-test-context")
        shown = prepare(db)
        if applied:
            receipt = confirm(db, shown)
    before = protected_state(db)
    if applied:
        replay = confirm(db, shown)
        assert replay == {
            **receipt,
            "confirmation": {**receipt["confirmation"], "replayed": True},
        }
    else:
        with pytest.raises(PlanningBuildPreviewError) as error:
            confirm(db, shown)
        assert error.value.code == "preview_stale"
    assert protected_state(db) == before


@pytest.mark.parametrize(
    "corruption", ["missing_stage", "reversed_range", "out_of_scale"]
)
def test_incomplete_or_invalid_rpe_policy_never_guesses_a_target(corruption):
    definition = next(
        d
        for d in wc.catalog_definitions()
        if d.template_key == "swim_recovery_technique"
    )
    targets = list(definition.rpe_stage_targets)
    if corruption == "missing_stage":
        targets = targets[:-1]
    else:
        key, _, _ = targets[-1]
        targets[-1] = (key, 4, 2) if corruption == "reversed_range" else (key, 0, 11)
    result = wc.materialize_workout(
        replace(definition, rpe_stage_targets=tuple(targets)),
        {"duration_minutes": 30, "target_tss": 15},
        {},
    )
    assert result["materialization_status"] == "infeasible"
    assert result["failed_bounds"] == ["target_semantics_unverified"]
    assert result["steps"] == []
