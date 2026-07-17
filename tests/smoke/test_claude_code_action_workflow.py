"""Contract for the trusted interactive Claude Code GitHub workflow (Issue #211)."""

from pathlib import Path

import pytest


pytestmark = pytest.mark.smoke

WORKFLOW = Path(".github/workflows/claude.yml")


def _workflow_text() -> str:
    assert WORKFLOW.exists(), "Claude Code workflow must be committed on the default branch"
    return WORKFLOW.read_text(encoding="utf-8")


def test_claude_action_supports_explicit_issue_and_pr_comment_mentions() -> None:
    workflow = _workflow_text()

    assert "issue_comment:" in workflow
    assert "pull_request_review_comment:" in workflow
    assert "pull_request_review:" in workflow
    assert "contains(github.event.comment.body, '@claude')" in workflow
    assert "contains(github.event.review.body, '@claude')" in workflow


def test_claude_action_is_trusted_actor_only_and_not_automatic_pr_review() -> None:
    workflow = _workflow_text()

    for association in ("OWNER", "MEMBER", "COLLABORATOR"):
        assert association in workflow
    assert "author_association" in workflow
    assert "pull_request_target" not in workflow
    assert "\n  pull_request:" not in workflow
    assert "ref: ${{ github.event.repository.default_branch }}" in workflow
    assert "github.event.pull_request.head" not in workflow


def test_claude_action_uses_only_the_named_oauth_secret_and_minimal_permissions() -> None:
    workflow = _workflow_text()

    assert "secrets.CLAUDE_CODE_OAUTH_TOKEN" in workflow
    assert "secrets.ANTHROPIC_API_KEY" not in workflow
    assert "github_token:" not in workflow
    assert "contents: read" in workflow
    assert "pull-requests: read" in workflow
    assert "issues: read" in workflow
    assert "actions: read" in workflow
    assert "id-token: write" in workflow
    assert "additional_permissions:" in workflow


def test_claude_action_is_pinned_and_bounded() -> None:
    workflow = _workflow_text()

    assert (
        "anthropics/claude-code-action@700e7f8316990de46bed556429765647af760efc"
        in workflow
    )
    assert "timeout-minutes:" in workflow
    assert "--max-turns" in workflow
