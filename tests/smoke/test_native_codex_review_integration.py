"""Rot guards for the native Codex GitHub review integration."""
from pathlib import Path

import pytest


pytestmark = pytest.mark.smoke

WORKFLOW_DIR = Path(".github/workflows")
LOOP_DOC = Path("docs/loop_engineering_instruction.md")
READY_WORKFLOW = WORKFLOW_DIR / "pr-ready-to-merge.yml"


def test_actions_do_not_impersonate_a_connected_user_for_codex_review() -> None:
    assert not (WORKFLOW_DIR / "codex-review.yml").exists()

    offenders = []
    for path in WORKFLOW_DIR.glob("*.yml"):
        text = path.read_text(encoding="utf-8")
        if "body: '@codex review'" in text or 'body: "@codex review"' in text:
            offenders.append(str(path))

    assert offenders == []


def test_ready_projection_does_not_wait_for_removed_actions_workflow() -> None:
    text = READY_WORKFLOW.read_text(encoding="utf-8")

    assert 'workflows: ["CI", "Link PR to issue", "Project roadmap sync"]' in text
    assert '"Codex Review"' not in text


def test_loop_documents_native_review_ownership_and_settings() -> None:
    text = LOOP_DOC.read_text(encoding="utf-8")

    assert "https://chatgpt.com/codex/settings/code-review" in text
    assert "Automatic reviews" in text
    assert "github-actions[bot]" in text
    assert "connected GitHub account" in text
