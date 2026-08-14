"""Behavior contracts for the read-only scientific plan audit."""
from __future__ import annotations

from copy import deepcopy

import pytest

from models.plan_science_audit import SCIENCE_POLICY_VERSION, audit_training_plan
from models.planning_checkpoints import build_planning_checkpoint


pytestmark = pytest.mark.smoke


def _session(
    date: str,
    sport: str,
    role: str,
    duration: int,
    phase: str,
    *,
    brick: bool = False,
    stimulus: str | None = None,
) -> dict:
    leaf = {
        "sport": "brick" if brick else sport,
        "session_role": role,
        "duration_minutes": duration,
        "kind": "composite" if brick else "single",
        "stimulus": stimulus,
    }
    if brick:
        leaf["legs"] = [{"sport": "bike"}, {"sport": "run"}]
    return {
        "date": date,
        "phase": phase,
        "sport": leaf["sport"],
        "session_role": role,
        "duration_minutes": duration,
        "sessions": [leaf],
    }


def _compliant_plan() -> dict:
    return {
        "goal_type": "Триатлон",
        "planning_mode": "event_goal",
        "events": [
            {
                "date": "2026-09-06",
                "priority": "A",
                "confirmed": True,
                "label": "Олимпийская дистанция",
            }
        ],
        "session_templates": [
            _session("2026-08-10", "run", "quality", 50, "Build"),
            _session("2026-08-12", "bike", "long", 120, "Build", brick=True),
            # Load baseline before the two-week taper: 375 minutes.
            _session("2026-08-17", "bike", "quality", 180, "Peak"),
            _session("2026-08-19", "run", "quality", 105, "Peak"),
            _session("2026-08-21", "swim", "quality", 90, "Peak", stimulus="race-specific pace"),
            # First taper week: 300 minutes.
            _session("2026-08-24", "swim", "easy", 60, "Taper"),
            _session("2026-08-26", "bike", "quality", 150, "Taper"),
            _session("2026-08-28", "run", "easy", 90, "Taper"),
            # Final seven days: 150 minutes (60% below the pre-taper baseline).
            _session("2026-08-31", "swim", "activation", 40, "Race Week"),
            _session("2026-09-02", "bike", "quality", 70, "Race Week"),
            _session("2026-09-04", "run", "activation", 40, "Race Week"),
        ],
    }


def _finding(audit: dict, rule_id: str) -> dict:
    return next(item for item in audit["findings"] if item["rule_id"] == rule_id)


def test_compliant_triathlon_plan_passes_all_six_rules_without_mutation():
    plan = _compliant_plan()
    before = deepcopy(plan)

    audit = audit_training_plan(plan)

    assert plan == before
    assert audit["state"] == "available"
    assert audit["policy_version"] == SCIENCE_POLICY_VERSION
    assert audit["source"] == "stored"
    assert audit["summary"] == {
        "passed": 6,
        "attention": 0,
        "data_gap": 0,
        "headline": "Все 6 проверок пройдены",
    }
    assert [item["status"] for item in audit["findings"]] == ["passed"] * 6
    assert all(item["evidence"] for item in audit["findings"])


def test_adjacent_hard_days_are_reported_with_both_dates():
    plan = _compliant_plan()
    plan["session_templates"].append(
        _session("2026-08-18", "run", "quality", 45, "Peak")
    )

    finding = _finding(audit_training_plan(plan), "hard_day_spacing")

    assert finding["status"] == "attention"
    assert finding["severity"] == "warning"
    assert finding["affected_dates"] == ["2026-08-17", "2026-08-18", "2026-08-19"]
    assert finding["evidence"][0]["ref_id"] == "REF-302"


def test_missing_build_or_peak_brick_is_actionable():
    plan = _compliant_plan()
    brick = plan["session_templates"][1]
    brick["sport"] = "bike"
    brick["sessions"][0] = {
        "sport": "bike",
        "session_role": "long",
        "duration_minutes": 120,
        "kind": "single",
    }

    finding = _finding(audit_training_plan(plan), "triathlon_brick_specificity")

    assert finding["status"] == "attention"
    assert "велосипед" in finding["recommendation"].lower()
    assert finding["evidence"][0]["ref_id"] == "REF-655"


def test_final_week_without_volume_reduction_is_reported():
    plan = _compliant_plan()
    for session in plan["session_templates"]:
        if session["date"] >= "2026-08-31":
            session["duration_minutes"] *= 2
            session["sessions"][0]["duration_minutes"] *= 2

    finding = _finding(audit_training_plan(plan), "taper_volume_shape")

    assert finding["status"] == "attention"
    assert finding["metrics"] == {
        "baseline_week_minutes": 375,
        "first_taper_week_minutes": 300,
        "final_week_minutes": 300,
        "reduction_percent": 20,
        "progressive_reduction": False,
    }
    assert finding["evidence"][0]["ref_id"] == "REF-107"


def test_taper_that_rises_before_race_is_reported_even_with_valid_total_reduction():
    plan = _compliant_plan()
    for session in plan["session_templates"]:
        if "2026-08-24" <= session["date"] < "2026-08-31":
            session["duration_minutes"] *= 2
            session["sessions"][0]["duration_minutes"] *= 2

    finding = _finding(audit_training_plan(plan), "taper_volume_shape")

    assert finding["status"] == "attention"
    assert finding["metrics"]["reduction_percent"] == 60
    assert finding["metrics"]["progressive_reduction"] is False


def test_final_week_missing_a_discipline_reports_the_missing_sport():
    plan = _compliant_plan()
    plan["session_templates"] = [
        item
        for item in plan["session_templates"]
        if item["date"] != "2026-08-31"
    ]

    finding = _finding(audit_training_plan(plan), "triathlon_taper_frequency")

    assert finding["status"] == "attention"
    assert finding["metrics"]["missing_sports"] == ["swim"]
    assert "плавание" in finding["summary"].lower()
    assert finding["evidence"][0]["ref_id"] == "REF-536"


def test_peak_without_specific_swim_is_actionable():
    plan = _compliant_plan()
    plan["session_templates"] = [
        item
        for item in plan["session_templates"]
        if not (item["phase"] == "Peak" and item["sport"] == "swim")
    ]

    finding = _finding(audit_training_plan(plan), "triathlon_swim_specificity")

    assert finding["status"] == "attention"
    assert "бассейне" in finding["recommendation"].lower()
    assert finding["evidence"][0]["ref_id"] == "REF-538"


def test_final_week_without_short_intensity_in_each_sport_is_actionable():
    plan = _compliant_plan()
    final_swim = next(item for item in plan["session_templates"] if item["date"] == "2026-08-31")
    final_swim["session_role"] = "easy"
    final_swim["sessions"][0]["session_role"] = "easy"

    finding = _finding(audit_training_plan(plan), "triathlon_taper_activation")

    assert finding["status"] == "attention"
    assert finding["metrics"]["missing_sports"] == ["swim"]
    assert finding["evidence"][0]["ref_id"] == "REF-107"


def test_short_or_rolling_plan_reports_honest_data_gaps():
    plan = _compliant_plan()
    plan["planning_mode"] = "training_goal"
    plan["events"] = []

    audit = audit_training_plan(plan, source="current_policy")

    assert audit["source"] == "current_policy"
    assert audit["summary"]["data_gap"] == 5
    assert _finding(audit, "hard_day_spacing")["status"] == "passed"
    assert _finding(audit, "triathlon_brick_specificity")["status"] == "data_gap"
    assert _finding(audit, "taper_volume_shape")["status"] == "data_gap"
    assert _finding(audit, "triathlon_taper_frequency")["status"] == "data_gap"
    assert _finding(audit, "triathlon_swim_specificity")["status"] == "data_gap"
    assert _finding(audit, "triathlon_taper_activation")["status"] == "data_gap"


def test_every_checkpoint_serialization_refreshes_a_stale_audit_snapshot():
    plan = _compliant_plan()
    plan["science_audit"] = audit_training_plan(plan)
    plan["session_templates"] = [
        item
        for item in plan["session_templates"]
        if not (item["phase"] == "Peak" and item["sport"] == "swim")
    ]

    checkpoint = build_planning_checkpoint(plan)
    stored = checkpoint["goal_plan_snapshot"]["science_audit"]

    assert stored["source"] == "stored"
    assert _finding(stored, "triathlon_swim_specificity")["status"] == "attention"
