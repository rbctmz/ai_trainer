"""Rot-guards for the repository Evidence Discipline contract (issue #464)."""
from pathlib import Path

import pytest


pytestmark = pytest.mark.smoke


PLANS_PATH = Path(".agent/PLANS.md")
WORKFLOW_PATH = Path("docs/AI_Feature_Development_Workflow.md")
ENTRY_POINT_PATHS = (Path("AGENTS.md"), Path("CLAUDE.md"))


def test_execplan_contract_separates_observation_inference_and_verification() -> None:
    plans = PLANS_PATH.read_text(encoding="utf-8")

    assert "## Evidence Discipline" in plans
    assert "**Observed**:" in plans
    assert "**Inferred**:" in plans
    assert "**Verified by**:" in plans
    assert "NOT YET" in plans
    assert "Minimal disproof before claim" in plans
    assert "before calling something a bug" in plans
    assert "identify and run one cheap check" in plans


def test_execplan_contract_contains_a_filled_three_field_example() -> None:
    plans = PLANS_PATH.read_text(encoding="utf-8")

    example_start = plans.index("Filled example:")
    example = plans[example_start:]
    assert "**Observed**:" in example
    assert "**Inferred**:" in example
    assert "**Verified by**:" in example
    assert "pytest" in example


def test_canonical_workflow_requires_minimal_disproof_before_causal_claim() -> None:
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")

    assert "# EVIDENCE DISCIPLINE" in workflow
    assert "Minimal disproof before claim" in workflow
    assert ".agent/PLANS.md" in workflow
    assert "Observed" in workflow
    assert "Inferred" in workflow
    assert "Verified by" in workflow
    assert "NOT YET" in workflow
    assert "до того как назвать" in workflow
    assert "сформулируй и выполни одну дешёвую проверку" in workflow


@pytest.mark.parametrize("path", ENTRY_POINT_PATHS, ids=lambda path: path.name)
def test_agent_entry_points_link_to_evidence_discipline(path: Path) -> None:
    entry_point = path.read_text(encoding="utf-8")

    assert "Evidence Discipline" in entry_point
    assert ".agent/PLANS.md" in entry_point
    assert "docs/AI_Feature_Development_Workflow.md" in entry_point
