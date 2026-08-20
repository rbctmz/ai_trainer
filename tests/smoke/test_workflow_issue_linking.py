"""Smoke coverage for GitHub issue-linking automation rules."""
from __future__ import annotations

from pathlib import Path

import pytest


pytestmark = pytest.mark.smoke


WORKFLOW_DIR = Path(".github/workflows")
UNSAFE_TITLE_LINK_PATTERNS = (
    "title.matchAll(/(?:^|\\s)#",
    "new RegExp(`(?:^|\\\\s)#",
)


def test_workflow_files_are_available() -> None:
    assert list(WORKFLOW_DIR.glob("*.yml"))


def test_pr_link_workflow_reruns_when_pr_branch_updates() -> None:
    workflow = (WORKFLOW_DIR / "codex-pr-link.yml").read_text()

    assert "types: [opened, edited, synchronize, closed]" in workflow


def test_title_issue_links_require_explicit_keywords() -> None:
    offenders: list[str] = []

    for path in WORKFLOW_DIR.glob("*.yml"):
        text = path.read_text()
        if any(pattern in text for pattern in UNSAFE_TITLE_LINK_PATTERNS):
            offenders.append(str(path))

    assert offenders == []


def test_branch_marker_links_but_does_not_close_issue() -> None:
    workflow = (WORKFLOW_DIR / "codex-pr-link.yml").read_text()

    branch_match_start = workflow.index("for (const match of branch.matchAll")
    branch_match_end = workflow.index("if (action === 'opened')", branch_match_start)
    branch_match_block = workflow[branch_match_start:branch_match_end]

    assert "linkedIssueNums.add" in branch_match_block
    assert "closingIssueNums.add" not in branch_match_block
    assert "for (const num of linkedIssueNums)" in workflow
    assert "for (const num of closingIssueNums)" in workflow


def test_only_explicit_closing_keywords_populate_closing_issue_set() -> None:
    workflow = (WORKFLOW_DIR / "codex-pr-link.yml").read_text()

    closing_additions = [
        line.strip() for line in workflow.splitlines() if "closingIssueNums.add" in line
    ]

    assert len(closing_additions) == 2
    assert workflow.count("/(?:closes|fixes|resolves)\\s+#(\\d+)/gi") == 2
