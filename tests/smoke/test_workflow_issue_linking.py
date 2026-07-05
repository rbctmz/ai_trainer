"""Smoke coverage for GitHub issue-linking automation rules."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml


pytestmark = pytest.mark.smoke


WORKFLOW_DIR = Path(".github/workflows")
UNSAFE_TITLE_LINK_PATTERNS = (
    "title.matchAll(/(?:^|\\s)#",
    "new RegExp(`(?:^|\\\\s)#",
)


def test_workflow_yaml_files_parse() -> None:
    for path in WORKFLOW_DIR.glob("*.yml"):
        yaml.safe_load(path.read_text())


def test_title_issue_links_require_explicit_keywords() -> None:
    offenders: list[str] = []

    for path in WORKFLOW_DIR.glob("*.yml"):
        text = path.read_text()
        if any(pattern in text for pattern in UNSAFE_TITLE_LINK_PATTERNS):
            offenders.append(str(path))

    assert offenders == []
