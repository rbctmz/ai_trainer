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
