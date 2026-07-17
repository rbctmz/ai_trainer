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


def test_claude_action_can_edit_and_run_only_contributor_safe_pytest() -> None:
    """Regression for run 29586638834: Claude must be able to implement the
    requested change, without receiving unrestricted shell access."""
    workflow = _workflow_text()

    assert '--allowedTools "Edit,Write,' in workflow
    assert "Bash(python -m pytest:*)" in workflow
    assert "Bash(python3 -m pytest:*)" in workflow
    assert "Bash(*)" not in workflow
    assert "Bash(bash:*)" not in workflow
    assert "Bash(sh:*)" not in workflow

    setup_index = workflow.index("actions/setup-python@v5")
    install_index = workflow.index("python -m pip install -r requirements.txt")
    claude_index = workflow.index("anthropics/claude-code-action@")
    assert setup_index < install_index < claude_index


def test_executable_pr_context_is_same_repository_only() -> None:
    """Pytest executes repository code, so external PR heads must fail closed
    even when a trusted maintainer wrote the triggering comment."""
    workflow = _workflow_text()

    assert "id: executable-context" in workflow
    assert "github.event.issue.pull_request" in workflow
    assert "pullRequest.head.repo.full_name" in workflow
    assert "context.repo.owner" in workflow
    assert "context.repo.repo" in workflow
    assert "steps.executable-context.outputs.result == 'true'" in workflow


def test_claude_runs_on_resolved_pr_branch_after_trusted_dependency_install() -> None:
    """Regression for run 29588059065: tag mode hashes changed files from the
    current checkout, so a same-repository PR must be checked out before Claude
    starts. Dependencies still come from the earlier trusted-main checkout."""
    workflow = _workflow_text()

    assert 'core.setOutput("checkout-ref", context.payload.repository.default_branch)' in workflow
    assert 'core.setOutput("checkout-ref", pullRequest.head.ref)' in workflow
    assert "name: Check out executable issue or PR branch" in workflow
    assert "ref: ${{ steps.executable-context.outputs.checkout-ref }}" in workflow
    assert "fetch-depth: 0" in workflow

    install_index = workflow.index("name: Install trusted default-branch dependencies")
    executable_checkout_index = workflow.index(
        "name: Check out executable issue or PR branch"
    )
    claude_index = workflow.index("name: Run Claude Code")
    assert install_index < executable_checkout_index < claude_index
