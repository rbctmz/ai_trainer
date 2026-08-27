"""Rot guards for the native Codex GitHub review integration."""
import re
import subprocess
from pathlib import Path

import pytest


pytestmark = pytest.mark.smoke

WORKFLOW_DIR = Path(".github/workflows")
LOOP_DOC = Path("docs/loop_engineering_instruction.md")
READY_WORKFLOW = WORKFLOW_DIR / "pr-ready-to-merge.yml"
REVIEW_GATE_POLICY = Path(".github/scripts/review-gate.cjs")
REVIEW_GATE_TEST = Path(".github/scripts/review-gate.test.cjs")
CI_WORKFLOW = WORKFLOW_DIR / "ci.yml"


def test_actions_do_not_impersonate_a_connected_user_for_codex_review() -> None:
    assert not (WORKFLOW_DIR / "codex-review.yml").exists()
    assert not (WORKFLOW_DIR / "codex-review.yaml").exists()

    offenders = []
    workflow_paths = (*WORKFLOW_DIR.glob("*.yml"), *WORKFLOW_DIR.glob("*.yaml"))
    for path in workflow_paths:
        text = path.read_text(encoding="utf-8")
        if re.search(r"@codex\s+review\b", text, flags=re.IGNORECASE):
            offenders.append(str(path))

    assert offenders == []


def test_ready_projection_does_not_wait_for_removed_actions_workflow() -> None:
    text = READY_WORKFLOW.read_text(encoding="utf-8")

    assert '"Codex Review"' not in text


def test_ready_projection_requires_an_accepted_bounded_review() -> None:
    text = READY_WORKFLOW.read_text(encoding="utf-8")

    for contract in (
        "issue_comment:",
        "pull_request_review:",
        "pull_request_review_comment:",
        "reviewThreads(first: 100",
        "status: review accepted",
        "status: review budget exceeded",
        "review-budget-exception",
        "countNativeReviewRounds",
        "countNativeReviewRoundsForHead",
        "cleanNativeReviewHead",
        "github.rest.issues.listComments",
        "persistCleanReviewStatuses",
        "evaluateReviewGate",
        "selectReadinessStatusComments",
        "shouldInvalidateAcceptance",
        "latestLabelActor",
        "getCollaboratorPermissionLevel",
        "reviewDecision",
        "stale evaluation skipped",
        'schedule:',
        'cron: "*/15 * * * *"',
        "['workflow_dispatch', 'schedule'].includes(context.eventName)",
        "pr-ready-to-merge-superseded",
    ):
        assert contract in text
    assert "pull_request_target:" in text
    assert "statuses: write" in text
    assert "ref: ${{ github.event.repository.default_branch }}" in text
    assert "github.event_name == 'pull_request'" not in text
    assert "context.payload.comment" in text
    assert "github.event.comment.user.login == 'chatgpt-codex-connector[bot]'" in text
    assert "removeLabel(ACCEPTED_LABEL)" in text
    assert "latestPr.head.sha !== pr.head.sha" in text
    assert "READY_MARKER," in text
    assert "const marker = `${READY_MARKER_PREFIX}${pr.head.sha} -->`;" not in text


def test_review_gate_policy_has_deterministic_node_coverage() -> None:
    assert REVIEW_GATE_POLICY.exists()
    assert REVIEW_GATE_TEST.exists()
    assert "node --test .github/scripts/review-gate.test.cjs" in CI_WORKFLOW.read_text(
        encoding="utf-8"
    )
    policy = REVIEW_GATE_POLICY.read_text(encoding="utf-8")
    assert "cleanNativeReviewStatus" in policy
    assert "persistCleanReviewStatuses" in policy
    assert "github.rest.repos.createCommitStatus" in policy
    assert "github.rest.repos.listCommitStatusesForRef" in policy

    subprocess.run(
        ["node", "--test", str(REVIEW_GATE_TEST)],
        check=True,
        capture_output=True,
        text=True,
    )


def test_loop_documents_native_review_ownership_and_settings() -> None:
    text = LOOP_DOC.read_text(encoding="utf-8")

    assert "https://chatgpt.com/codex/settings/code-review" in text
    assert "Automatic reviews" in text
    assert "github-actions[bot]" in text
    assert "connected GitHub account" in text
