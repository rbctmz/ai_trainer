"""Rot guards for the tiered engineering workflow contract (issue #277)."""
from pathlib import Path

import pytest


pytestmark = pytest.mark.smoke

WORKFLOW = Path("docs/AI_Feature_Development_Workflow.md")
LOOP = Path("docs/loop_engineering_instruction.md")
TEMPLATE = Path("docs/templates/slice_spec_review_template.md")
METRICS = Path("docs/engineering_process_metrics.md")
AGENTS = Path("AGENTS.md")
ISSUE_TEMPLATE = Path(".github/ISSUE_TEMPLATE/agent_task.yml")
CODEX_ASSIGN = Path(".github/workflows/codex-assign.yml")


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
    assert "review budget никогда не понижает severity" in text
    assert "merge с открытым P0/P1 или blocking P2" in text
    assert "pure behavior-preserving refactor" in text
    assert "characterization/equivalence baseline" in text
    assert "Class C пропускает отдельные SpecDD, BDD и TDD" in text
    assert "Для Class C без изменения поведения TDD не применяется" in text


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
    assert "mergeStateStatus=CLEAN" in text
    assert "broad tests marked `N/A`" in text
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
    assert "separate working spec" in text
    assert "behavior-preserving refactor" in text
    assert "Review trigger mode: manual / automatic" in text
    assert "## Evidence Boundary Matrix" in text
    assert "## Native Review Rounds" in text
    assert "review-budget-exception" in text


def test_process_metrics_have_definitions_place_and_two_real_baselines() -> None:
    text = METRICS.read_text(encoding="utf-8")

    for metric in (
        "Issue lead time",
        "PR cycle time",
        "Review rounds",
        "Pre-merge P0/P1",
        "Pre-merge blocking P2",
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
    assert "Retrospective class proxy" in text
    assert "Escaped defects" in text.split("## Baseline Retrospective", 1)[1]
    assert "Verified by: NOT YET" in text
    # Class A пилот завершён (#496); Class C остаётся открытым до своего пилота.
    assert "Class A architecture-changing PR: **done — PR #496**" in text
    assert "Class C UI/docs PR: **done — PR #497**" in text
    assert "PR #496" in text
    assert "PR #497" in text
    assert "Review-Loop Incident Retrospective — 2026-08-26" in text
    assert "PR #505" in text
    assert "13 submitted Codex reviews" in text
    assert "10 P1 + 37 P2" in text


def test_agent_entrypoint_links_policy_template_and_metrics() -> None:
    text = AGENTS.read_text(encoding="utf-8")

    assert "Change Class" in text
    assert "docs/templates/slice_spec_review_template.md" in text
    assert "docs/engineering_process_metrics.md" in text


def test_agent_issue_and_queue_contracts_are_change_class_aware() -> None:
    issue_template = ISSUE_TEMPLATE.read_text(encoding="utf-8")
    queue_workflow = CODEX_ASSIGN.read_text(encoding="utf-8")

    assert "label: Change Class" in issue_template
    for change_class in (
        "Class A — Full",
        "Class B — Standard",
        "Class C — Fast track",
    ):
        assert change_class in issue_template
    assert "Class B / Class C" in issue_template
    assert "N/A" in issue_template
    assert "label: Non-goals" in issue_template
    assert "Class A must list them" in issue_template

    assert "recognizedChangeClasses" in queue_workflow
    for change_class in (
        "Class A — Full",
        "Class B — Standard",
        "Class C — Fast track",
    ):
        assert change_class in queue_workflow
    assert "if (!recognizedChangeClasses.has(changeClass)) return" in queue_workflow
    assert "requiredSections.some(value => !value)" in queue_workflow
    assert "changeClass === 'Class A — Full'" in queue_workflow
    assert "isNA(execplan) || isNA(nonGoals)" in queue_workflow
    assert "^N\\s*\\/?\\s*A\\b(.*)$" in queue_workflow
    assert "stripLeadingMarkdown" in queue_workflow
    assert "[-*+>]|\\d+[.)]" in queue_workflow
    assert "hasNARationale" in queue_workflow
    assert "!hasNARationale(execplan) || !hasNARationale(nonGoals)" in queue_workflow
    assert "**Change class:**" in queue_workflow
    assert "Class B/C may use N/A" in queue_workflow
    assert "extract('Non-goals')" in queue_workflow
    assert "**Non-goals:**" in queue_workflow

    metrics = METRICS.read_text(encoding="utf-8")
    assert "fixed, removed by" in metrics
    assert "narrowing scope, or canceled" in metrics
