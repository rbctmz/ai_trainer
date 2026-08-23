"""Rot guards for the tiered engineering workflow contract (issue #277)."""
from pathlib import Path

import pytest


pytestmark = pytest.mark.smoke

WORKFLOW = Path("docs/AI_Feature_Development_Workflow.md")
LOOP = Path("docs/loop_engineering_instruction.md")
TEMPLATE = Path("docs/templates/slice_spec_review_template.md")
METRICS = Path("docs/engineering_process_metrics.md")
AGENTS = Path("AGENTS.md")


def test_canonical_workflow_defines_three_change_classes_and_escalation() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    for heading in (
        "## Class A — Full",
        "## Class B — Standard",
        "## Class C — Fast track",
        "## Automatic escalation triggers",
        "## Review severity",
        "## Review budget",
    ):
        assert heading in text
    for trigger in (
        "data migration",
        "identity or provenance",
        "live-provider write",
        "security boundary",
        "irreversible action",
    ):
        assert trigger in text
    for severity in ("P0", "P1", "P2", "P3"):
        assert severity in text
    assert "two spec-review rounds" in text


def test_loop_requires_one_review_bundle_and_owned_merge_cleanup() -> None:
    text = LOOP.read_text(encoding="utf-8")

    assert "## Review Evidence Bundle" in text
    for field in (
        "head SHA",
        "changed invariants",
        "focused and broad tests",
        "unresolved review-thread count",
    ):
        assert field in text
    assert "one bundle" in text
    assert "## Merge And Cleanup Ownership" in text
    assert "merge owner" in text
    assert "mergeState=CLEAN" in text
    assert "sync local `main`" in text
    assert "Never use `--admin`" in text
    assert "## Process Metrics" in text


def test_slice_spec_review_template_covers_required_state_and_review_contracts() -> None:
    text = TEMPLATE.read_text(encoding="utf-8")

    for heading in (
        "## Change Class",
        "## Scope",
        "## Non-goals",
        "## Definition of Done",
        "## Public Contracts",
        "## Failure, Reset, Rollback, Idempotency",
        "## State Boundaries and Identity",
        "## RED Matrix",
        "## ASR / ADR Traceability",
        "## Delivery Slices",
        "## Evidence Bundle",
        "## Review Findings",
        "## Final Verdict",
    ):
        assert heading in text
    assert "new persistent state" in text.lower()
    assert "full reset" in text.lower()
    assert "P0/P1/P2/P3" in text


def test_process_metrics_have_definitions_place_and_two_real_baselines() -> None:
    text = METRICS.read_text(encoding="utf-8")

    for metric in (
        "Issue lead time",
        "PR cycle time",
        "Review rounds",
        "Pre-merge P0/P1",
        "Escaped defects",
        "CI reruns/flakes",
        "Follow-up P2",
        "Agent wait time",
    ):
        assert metric in text
    assert "PR #493" in text
    assert "PR #486" in text
    assert "2026-08-23" in text
    assert "not captured" in text


def test_agent_entrypoint_links_policy_template_and_metrics() -> None:
    text = AGENTS.read_text(encoding="utf-8")

    assert "Change Class" in text
    assert "docs/templates/slice_spec_review_template.md" in text
    assert "docs/engineering_process_metrics.md" in text
