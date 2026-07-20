"""Contract for the trusted interactive Claude Code GitHub workflow (Issue #211)."""

from pathlib import Path
import re

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


def test_claude_action_has_enough_turns_for_red_green_implementation() -> None:
    """Regressions for runs 29641403550 and 29641929970: valid M5
    implementation runs must not stop at the 60-turn ceiling before push."""
    workflow = _workflow_text()

    match = re.search(r"--max-turns\s+(\d+)", workflow)
    assert match is not None
    assert int(match.group(1)) == 120


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


def test_claude_action_allows_only_safe_git_diagnostics() -> None:
    """Claude may inspect the checked-out PR state without receiving git
    mutation or unrestricted shell capabilities."""
    workflow = _workflow_text()

    for command in (
        "Bash(git status:*)",
        "Bash(git diff:*)",
        "Bash(git log:*)",
        "Bash(git show:*)",
        "Bash(git rev-parse:*)",
    ):
        assert command in workflow

    for command in (
        "Bash(git reset:*)",
        "Bash(git clean:*)",
        "Bash(git checkout:*)",
        "Bash(git push:*)",
        "Bash(git merge:*)",
    ):
        assert command not in workflow


def test_claude_action_persists_red_gate_before_green_implementation() -> None:
    """Long tasks must leave an inspectable RED checkpoint even if a later
    implementation turn exhausts the bounded action budget."""
    workflow = _workflow_text()

    assert "Commit the confirmed RED gate before implementation" in workflow
    assert "Commit the GREEN fix separately" in workflow


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


# --- Issue #222: hardening round 2 -----------------------------------------

NOTIFY = Path(".github/workflows/claude-failure-notify.yml")
AUTO_PR = Path(".github/workflows/claude-auto-draft-pr.yml")
AGENTS = Path("AGENTS.md")


def test_failed_claude_runs_are_reported_with_a_classified_cause() -> None:
    """#222 p.1: a failed run must leave a thread comment naming the cause
    (turn budget / quota / error) — the 2026-07-18 failures were silent for
    hours. The notifier is a separate workflow so the interactive job token
    stays read-only."""
    assert NOTIFY.exists(), "claude-failure-notify.yml must exist"
    text = NOTIFY.read_text(encoding="utf-8")
    assert "workflow_run:" in text
    assert "Claude Code" in text
    assert "completed" in text
    assert "'failure'" in text
    assert "actions: read" in text
    assert "issues: write" in text
    assert "pull-requests: write" in text
    lowered = text.lower()
    assert "turn" in lowered  # turn-budget classification marker
    assert "usage limit" in lowered or "quota" in lowered

    workflow = _workflow_text()
    assert "issues: write" not in workflow
    assert "pull-requests: write" not in workflow


def test_action_branches_get_a_draft_pr_automatically() -> None:
    """#222 p.5: the action cannot create PRs by design (it only prepares a
    prefilled link), so a companion workflow opens the draft PR for pushed
    action branches (claude/issue-N-YYYYMMDD-HHMM) with Closes #N — no manual
    step between 'Action finished' and 'PR awaits review'. Locally named
    branches (claude/issue-N-slug) must NOT match."""
    assert AUTO_PR.exists(), "claude-auto-draft-pr.yml must exist"
    text = AUTO_PR.read_text(encoding="utf-8")
    assert "push:" in text
    assert "claude/issue-*" in text
    assert "pull-requests: write" in text
    assert "draft: true" in text
    assert "\\d{8}-\\d{4}" in text  # action-branch fingerprint, not local slugs
    assert "Closes #" in text


def test_prompt_encodes_slice_commit_discipline_and_agents_norm() -> None:
    """#222 p.2: budget policy over budget inflation — every finished slice is
    pushed immediately, exhaustion stops at a clean boundary; AGENTS.md fixes
    the one-milestone-per-mention norm."""
    workflow = _workflow_text()
    assert "Commit and push every completed RED or GREEN slice immediately" in workflow
    assert "stop at a clean boundary" in workflow

    agents = AGENTS.read_text(encoding="utf-8")
    assert "one milestone per @claude mention" in agents.lower()


def test_web_toolchain_is_available_and_scoped() -> None:
    """#222 p.3: web-touching slices must be verifiable inside the run —
    node is set up, web deps installed, and ONLY the two verification npm
    commands are allowed."""
    workflow = _workflow_text()
    assert "actions/setup-node@" in workflow
    assert "npm --prefix web ci" in workflow
    assert "Bash(npm --prefix web run lint:*)" in workflow
    assert "Bash(npm --prefix web run build:*)" in workflow
    assert "Bash(npm:*)" not in workflow
    assert "Bash(npx:*)" not in workflow

    node_index = workflow.index("actions/setup-node@")
    claude_index = workflow.index("name: Run Claude Code")
    assert node_index < claude_index


def test_dependencies_are_refreshed_from_the_executable_branch() -> None:
    """#222 p.4: a PR that changes requirements*.txt must run against ITS
    dependency set — after the same-repo-guarded checkout the requirements
    are re-installed (pip cache makes the unchanged case cheap). The trusted
    default-branch install order stays pinned by the earlier test."""
    workflow = _workflow_text()
    refresh_index = workflow.index("name: Refresh dependencies from the executable branch")
    checkout_index = workflow.index("name: Check out executable issue or PR branch")
    claude_index = workflow.index("name: Run Claude Code")
    assert checkout_index < refresh_index < claude_index
