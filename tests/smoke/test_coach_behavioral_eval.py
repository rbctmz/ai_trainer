"""Smoke coverage for the coach behavioral eval harness (#528)."""
from __future__ import annotations

import pytest

from models.coach_decisions import build_coach_decision
from services.coach_behavioral_eval import (
    CoachEvalCase,
    evaluate_case,
    evaluate_registry,
    safety_no_load_push_under_poor_recovery,
)
from tests.evals.coach.registry import CASES, REGISTRY_VERSION


pytestmark = pytest.mark.smoke


def _case(case_id: str) -> CoachEvalCase:
    return next(c for c in CASES if c.case_id == case_id)


def test_classifier_flags_load_push_intent():
    decision = build_coach_decision("увеличь нагрузку, сделай интервалы", db=None)
    assert decision.decision_type == "Push"


def test_anti_case_poor_recovery_load_push_fails():
    result = evaluate_case(_case("poor-recovery-load-push"))
    assert result["passed"] is False
    assert result["verdict"] == "fail"


def test_registry_reports_documented_gaps_and_no_regressions():
    report = evaluate_registry(CASES)
    assert set(report["documented_gaps"]) == {
        "poor-recovery-load-push",
        "briefing-rejected",
        "brevity-long",
        "fact-plan-unlabeled",
    }
    assert report["regressions"] == []
    assert report["verdict"] == "pass"
    assert report["pass_rate"] == 1.0


def test_safety_property_passes_for_rest_response():
    check = safety_no_load_push_under_poor_recovery(_case("poor-recovery-rest"))
    assert check.passed is True


def test_consistency_check_rejects_boilerplate():
    assert evaluate_case(_case("briefing-preserved"))["passed"] is True
    assert evaluate_case(_case("briefing-rejected"))["passed"] is False


def test_brevity_check_flags_long_answer():
    assert evaluate_case(_case("brevity-short"))["passed"] is True
    assert evaluate_case(_case("brevity-long"))["passed"] is False


def test_clarity_check_requires_fact_plan_labels():
    assert evaluate_case(_case("fact-plan-labeled"))["passed"] is True
    assert evaluate_case(_case("fact-plan-unlabeled"))["passed"] is False


def test_registry_version_is_stable():
    assert REGISTRY_VERSION == "coach_behavioral_eval_v3"
