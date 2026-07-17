from __future__ import annotations

from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta
import json

import pytest

from models.workout_catalog import (
    CATALOG_VERSION,
    MATERIALIZER_RULE_VERSION,
    SELECTOR_RULE_VERSION,
    catalog_definitions,
    materialize_session_template,
    materialize_workout,
    prepare_weekly_brick_allocations,
    select_workout_template,
)
from models.session_identity import ensure_session_identities
from models.planning_near_term import apply_near_term_day_edits
from models.plan_actual_reconciliation import apply_weekly_rebalance_preview
from models.planning_checkpoints import (
    build_planning_checkpoint,
    restore_goal_plan_from_checkpoint,
)
from data.database import Database
from models.training_planner import build_daily_session_templates


pytestmark = pytest.mark.smoke


EXPECTED_TEMPLATE_KEYS = {
    "bike_recovery_spin",
    "bike_aerobic_endurance",
    "bike_aerobic_progression",
    "bike_tempo_sweet_spot",
    "bike_threshold_intervals",
    "bike_vo2max_intervals",
    "bike_neuromuscular_sprints",
    "bike_race_pace",
    "bike_activation",
    "run_activation",
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
        "target_tss": 80.0,
        "load_state": "balanced",
        "recent_template_keys": [],
    }
    context.update(overrides)
    return context


def test_catalog_is_exact_versioned_and_immutable():
    definitions = catalog_definitions()

    assert CATALOG_VERSION == "workout_catalog_v2"
    assert SELECTOR_RULE_VERSION == "workout_selector_v1"
    assert MATERIALIZER_RULE_VERSION == "workout_materializer_v2"
    assert len(definitions) == 22
    assert {item.template_key for item in definitions} == EXPECTED_TEMPLATE_KEYS
    assert len({(item.template_key, item.version) for item in definitions}) == 22
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


def test_taper_long_role_becomes_bounded_sharpening_not_long_endurance():
    result = materialize_session_template(
        phase="Taper",
        session_role="long",
        sport="bike",
        target_tss=60.0,
        estimated_duration_minutes=120,
        goal_type="triathlon",
        zone_snapshot={"ftp": 200},
    )

    assert result["materialization_status"] == "materialized"
    assert result["duration_minutes"] <= 60
    assert result["template_key"] in {
        "bike_vo2max_intervals",
        "bike_neuromuscular_sprints",
    }
    assert result["selection_evidence"]["role_override"] == "long_to_sharpening"


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
        "scale": "absolute_power_from_ftp",
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


def test_session_templates_store_phase_specific_materialized_prescriptions():
    start = datetime(2026, 7, 13)
    daily = [
        (
            start + timedelta(days=index),
            80.0 if index in {0, 7} else 0.0,
            {"run": 0.0, "bike": 80.0 if index in {0, 7} else 0.0, "swim": 0.0},
        )
        for index in range(8)
    ]
    summaries = [
        {
            "phase": "Base",
            "day_roles": ["quality"] + ["off"] * 6,
            "day_focuses": ["Качество • вело"] + ["Отдых"] * 6,
        },
        {"phase": "Build", "day_roles": ["quality"], "day_focuses": ["Качество • вело"]},
    ]

    templates = build_daily_session_templates(
        daily,
        summaries,
        "Триатлон",
        "Олимпийка",
        load_state="balanced",
        zone_snapshot={"ftp": 200},
    )

    base, build = templates[0], templates[7]
    assert base["template_key"] == "bike_aerobic_progression"
    assert build["template_key"] == "bike_threshold_intervals"
    assert base["template_version"] == 2
    assert build["template_version"] == 2
    assert base["catalog_version"] == CATALOG_VERSION
    assert base["kind"] == "single"
    assert build["kind"] == "single"
    assert base["materialization_status"] == "materialized"
    assert build["materialization_status"] == "materialized"
    assert sum(step["duration_seconds"] for step in build["materialized_steps"]) == 3600
    assert sum(step["tss"] for step in build["materialized_steps"]) == pytest.approx(80.0)
    assert build["definition_snapshot"]["template_key"] == "bike_threshold_intervals"
    assert build["selection_evidence"]["phase"] == "Build"


def test_build_templates_represents_brick_as_one_parent_with_ordered_legs():
    start = datetime(2026, 7, 13)
    daily = [
        (start + timedelta(days=index), 20.0, {"run": 5.0, "bike": 5.0, "swim": 10.0})
        for index in range(7)
    ]
    daily[5] = (
        start + timedelta(days=5),
        80.0,
        {"run": 25.0, "bike": 55.0, "swim": 0.0},
    )
    summary = [
        {
            "phase": "Build",
            "day_roles": ["easy", "quality", "easy", "recovery", "easy", "long", "off"],
            "day_focuses": ["Легкая"] * 5 + ["Длительная"] + ["Отдых"],
        }
    ]

    templates = build_daily_session_templates(
        daily,
        summary,
        "Триатлон",
        "Олимпийка",
        load_state="balanced",
        zone_snapshot={"ftp": 200, "lthr": 165},
        brick_day_indices={5},
    )

    brick = templates[5]
    assert brick["kind"] == "composite"
    assert brick["template_key"] == "brick_endurance"
    assert brick["sport"] == "brick"
    assert brick["transition_minutes"] == 5
    assert [leg["sport"] for leg in brick["legs"]] == ["bike", "run"]
    assert [leg["leg_index"] for leg in brick["legs"]] == [1, 2]
    assert sum(leg["target_tss"] for leg in brick["legs"]) == pytest.approx(80.0)
    assert sum(leg["duration_minutes"] for leg in brick["legs"]) + 5 == brick["duration_minutes"]
    assert all(leg["materialized_steps"] for leg in brick["legs"])

    identified = ensure_session_identities(
        {"daily_plan": daily, "session_templates": templates}
    )
    parent = identified["session_templates"][5]
    assert parent["session_id"].startswith("ats_")
    assert [leg["leg_id"] for leg in parent["legs"]] == [
        f"{parent['session_id']}:1",
        f"{parent['session_id']}:2",
    ]


def test_prescription_change_replaces_session_identity():
    dt = datetime(2026, 7, 13)
    daily = [(dt, 80.0, {"run": 0.0, "bike": 80.0, "swim": 0.0})]
    summary = [{"phase": "Build", "day_roles": ["quality"], "day_focuses": ["Качество"]}]
    templates = build_daily_session_templates(
        daily,
        summary,
        "Триатлон",
        "Олимпийка",
        zone_snapshot={"ftp": 200},
    )
    original = ensure_session_identities({"daily_plan": daily, "session_templates": templates})

    changed_templates = deepcopy(original["session_templates"])
    changed_templates[0]["materialized_steps"][1]["target"]["high"] += 1
    changed_templates[0].pop("prescription_fingerprint", None)
    changed = ensure_session_identities(
        {"daily_plan": daily, "session_templates": changed_templates},
        previous_goal_plan=original,
    )

    old = original["session_templates"][0]
    new = changed["session_templates"][0]
    assert new["session_id"] != old["session_id"]
    assert new["replaces_session_id"] == old["session_id"]


def test_export_uses_persisted_seconds_and_honest_target_type():
    from api.planning_service import export_workout

    dt = datetime(2026, 7, 13)
    daily = [(dt, 80.0, {"run": 0.0, "bike": 80.0, "swim": 0.0})]
    summary = [{"phase": "Build", "day_roles": ["quality"], "day_focuses": ["Качество"]}]
    template = build_daily_session_templates(
        daily,
        summary,
        "Триатлон",
        "Олимпийка",
        zone_snapshot={"ftp": 200},
    )[0]
    plan = {"goal_type": "Триатлон", "daily_plan": daily, "session_templates": [template]}

    fit = export_workout(plan, 0, "fit_csv")
    tcx = export_workout(plan, 0, "tcx")
    first_step = template["materialized_steps"][0]

    assert f"duration_time,{first_step['duration_seconds']},s" in fit["content"]
    assert "target_type,4" in fit["content"]  # FIT power, not the legacy HR zone.
    assert "target_hr_zone" not in "\n".join(
        line for line in fit["content"].splitlines() if line.startswith("Data,2,workout_step")
    )
    assert f"<Seconds>{first_step['duration_seconds']}</Seconds>" in tcx["content"]
    assert '<Target xsi:type="None_t" />' in tcx["content"]
    assert "AI Trainer target evidence: power" in tcx["content"]
    assert "<ZoneNumber>2</ZoneNumber>" not in tcx["content"]


def test_composite_export_requires_and_resolves_explicit_leg():
    from api.planning_service import export_workout

    dt = datetime(2026, 7, 18)
    daily = [(dt, 80.0, {"run": 25.0, "bike": 55.0, "swim": 0.0})]
    summary = [{"phase": "Build", "day_roles": ["long"], "day_focuses": ["Длительная"]}]
    template = build_daily_session_templates(
        daily,
        summary,
        "Триатлон",
        "Олимпийка",
        zone_snapshot={"ftp": 200, "lthr": 165},
        brick_day_indices={0},
    )[0]
    identified = ensure_session_identities(
        {"goal_type": "Триатлон", "daily_plan": daily, "session_templates": [template]}
    )

    with pytest.raises(ValueError, match="requires leg=1 or leg=2"):
        export_workout(identified, 0, "tcx")

    bike = export_workout(identified, 0, "fit_csv", leg=1)
    run = export_workout(identified, 0, "tcx", leg=2)
    assert bike["filename"].endswith("_leg1_bike.csv")
    assert "target_type,4" in bike["content"]
    assert run["filename"].endswith("_leg2_run.tcx")
    assert 'Workout Sport="Running"' in run["content"]
    assert identified["session_templates"][0]["legs"][1]["leg_id"].endswith(":2")


def test_recovery_replan_rescales_brick_legs_atomically():
    start = datetime(2026, 7, 13)
    daily = [
        (start + timedelta(days=index), 20.0, {"run": 5.0, "bike": 5.0, "swim": 10.0})
        for index in range(7)
    ]
    daily[5] = (start + timedelta(days=5), 80.0, {"run": 25.0, "bike": 55.0, "swim": 0.0})
    summary = [
        {
            "phase": "Build",
            "weekly_tss": 200,
            "day_roles": ["easy", "quality", "easy", "recovery", "easy", "long", "off"],
            "day_focuses": ["Легкая"] * 5 + ["Длительная"] + ["Отдых"],
        }
    ]
    templates = build_daily_session_templates(
        daily,
        summary,
        "Триатлон",
        "Олимпийка",
        zone_snapshot={"ftp": 200, "lthr": 165},
        brick_day_indices={5},
    )
    original = ensure_session_identities(
        {
            "goal_type": "Триатлон",
            "distance": "Олимпийка",
            "daily_plan": daily,
            "session_templates": templates,
            "weekly_summary": summary,
            "weekly_tss_plan": [200],
            "constraint_summary": {"load_state": "balanced", "notes": []},
        }
    )
    before = original["session_templates"][5]

    updated = apply_near_term_day_edits(
        original,
        [{"index": 5, "session_role": "recovery", "sport": "brick", "total_tss": 60}],
        horizon_days=7,
        post_edit_strategy="protect_recovery",
    )
    after = updated["session_templates"][5]

    assert updated["daily_plan"][5][1] == 60.0
    assert after["kind"] == "composite"
    assert after["sport"] == "brick"
    assert [leg["sport"] for leg in after["legs"]] == ["bike", "run"]
    assert sum(leg["target_tss"] for leg in after["legs"]) == pytest.approx(60.0, abs=0.1)
    assert sum(leg["duration_minutes"] for leg in after["legs"]) + after["transition_minutes"] == after["duration_minutes"]
    assert all(
        sum(step["tss"] for step in leg["materialized_steps"])
        == pytest.approx(leg["target_tss"], abs=0.1)
        for leg in after["legs"]
    )
    assert after["prescription_fingerprint"] != before["prescription_fingerprint"]


def test_weekly_rebalance_refreshes_persisted_prescription_and_identity():
    start = datetime(2026, 7, 13)
    daily = [
        (
            start + timedelta(days=index),
            80.0 if index == 0 else 0.0,
            {"run": 0.0, "bike": 80.0 if index == 0 else 0.0, "swim": 0.0},
        )
        for index in range(7)
    ]
    summary = [
        {
            "phase": "Build",
            "weekly_tss": 80,
            "day_roles": ["quality"] + ["off"] * 6,
            "day_focuses": ["Качество"] + ["Отдых"] * 6,
        }
    ]
    templates = build_daily_session_templates(
        daily,
        summary,
        "Триатлон",
        "Олимпийка",
        zone_snapshot={"ftp": 200},
    )
    original = ensure_session_identities(
        {
            "goal_type": "Триатлон",
            "distance": "Олимпийка",
            "daily_plan": daily,
            "session_templates": templates,
            "weekly_summary": summary,
            "weekly_tss_plan": [80],
            "constraint_summary": {},
        }
    )
    before = original["session_templates"][0]
    preview = {
        "status": "proposal",
        "rule_version": "weekly_rebalance_v1",
        "as_of": "2026-07-13",
        "base_checkpoint_id": 1,
        "preview_fingerprint": "test-preview",
        "future_tss_delta": -20,
        "changes": [{"index": 0, "before_tss": 80.0, "after_tss": 60.0}],
        "reconciliation_snapshot": {},
    }

    updated = apply_weekly_rebalance_preview(original, preview)
    after = updated["session_templates"][0]

    assert after["parameter_snapshot"]["target_tss"] == 60.0
    assert sum(step["tss"] for step in after["materialized_steps"]) == pytest.approx(60.0)
    assert after["prescription_fingerprint"] != before["prescription_fingerprint"]
    assert after["session_id"] != before["session_id"]
    assert after["replaces_session_id"] == before["session_id"]


def test_checkpoint_roundtrip_keeps_immutable_prescription_snapshot(tmp_path, monkeypatch):
    from models import workout_catalog

    dt = datetime(2026, 7, 13)
    daily = [(dt, 80.0, {"run": 0.0, "bike": 80.0, "swim": 0.0})]
    summary = [{"phase": "Build", "day_roles": ["quality"], "day_focuses": ["Качество"]}]
    templates = build_daily_session_templates(
        daily,
        summary,
        "Триатлон",
        "Олимпийка",
        zone_snapshot={"ftp": 200},
    )
    plan = ensure_session_identities(
        {
            "goal_type": "Триатлон",
            "distance": "Олимпийка",
            "daily_plan": daily,
            "session_templates": templates,
            "weekly_summary": summary,
            "weekly_tss_plan": [80],
            "base_weekly_tss_plan": [80],
            "phases": ["Build"],
            "constraint_summary": {},
        }
    )
    db = Database(str(tmp_path / "catalog-checkpoint.db"))
    db.save_planning_checkpoint(build_planning_checkpoint(plan))
    checkpoint = db.get_latest_planning_checkpoint()
    expected = json.dumps(
        {
            "definition_snapshot": plan["session_templates"][0]["definition_snapshot"],
            "parameter_snapshot": plan["session_templates"][0]["parameter_snapshot"],
            "materialized_steps": plan["session_templates"][0]["materialized_steps"],
            "prescription_fingerprint": plan["session_templates"][0]["prescription_fingerprint"],
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()

    mutated = tuple(
        replace(item, display_name="Changed after save")
        if item.template_key == "bike_threshold_intervals"
        else item
        for item in workout_catalog.catalog_definitions()
    )
    monkeypatch.setattr(workout_catalog, "_CATALOG", mutated)
    restored = restore_goal_plan_from_checkpoint(checkpoint)
    actual_template = restored["session_templates"][0]
    actual = json.dumps(
        {
            "definition_snapshot": actual_template["definition_snapshot"],
            "parameter_snapshot": actual_template["parameter_snapshot"],
            "materialized_steps": actual_template["materialized_steps"],
            "prescription_fingerprint": actual_template["prescription_fingerprint"],
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()

    assert actual == expected
    assert actual_template["template_name"] != "Changed after save"
