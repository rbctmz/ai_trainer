"""RED product-surface contract for coach constraint mutation proposals.

Issue #483 keeps constraint mutations in the shared proposal lifecycle.  This
test pins the web-facing contract before implementation: the action union must
be exhaustive, the shared card must dispatch the new actions explicitly, and
the decisions history must give them their own label/summary path instead of
falling through to the adjustment-plan copy.

The repository has no JS component test runner for this surface, so this uses
the same source-contract approach as the existing ProposalCard smoke tests.
"""

from pathlib import Path

import pytest


pytestmark = pytest.mark.smoke
REPO_ROOT = Path(__file__).resolve().parents[2]

CONSTRAINT_ACTIONS = (
    "create_plan_constraint",
    "retract_plan_constraint",
    "repair_plan_day",
)


def _source(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


def _action_lines(source: str, action: str) -> list[str]:
    return [line for line in source.splitlines() if action in line]


def test_coach_proposal_action_union_includes_constraint_mutations() -> None:
    """The SSE/API proposal action must be type-safe for all three tools."""
    source = _source("web/lib/types.ts")
    start = source.index("export type CoachProposalAction")
    action_union = source[start : source.index(";", start) + 1]

    for action in CONSTRAINT_ACTIONS:
        assert f'"{action}"' in action_union, action


def test_proposal_card_explicitly_dispatches_constraint_mutations_before_adjustment() -> None:
    """Constraint actions must not use the generic adjust-plan branch.

    The exact implementation may use action comparisons, a switch, or an
    action-set lookup.  The source contract therefore requires each action to
    occur on an explicit dispatch line before the existing adjustment branch.
    """
    source = _source("web/components/ui/ProposalCard.tsx")
    lines = source.splitlines()
    adjustment_lines = [
        index
        for index, line in enumerate(lines)
        if 'action === "adjust_plan"' in line or 'action === \'adjust_plan\'' in line
    ]
    assert adjustment_lines, "ProposalCard must retain an explicit adjust_plan branch"
    adjustment_line = min(adjustment_lines)

    for action in CONSTRAINT_ACTIONS:
        dispatch_lines = [
            index
            for index, line in enumerate(lines)
            if action in line
            and any(token in line for token in ("action", "case", "ACTIONS", "MUTATION"))
        ]
        assert dispatch_lines, f"missing explicit ProposalCard dispatch for {action}"
        assert min(dispatch_lines) < adjustment_line, (
            f"{action} must not fall through to adjust_plan"
        )


def test_decisions_history_has_constraint_labels_and_summaries() -> None:
    """History must render each mutation action with bounded human copy.

    Action-specific label/summary logic is intentionally checked in the
    history surface as well as in ProposalCard: pending cards and resolved
    history entries are separate render paths.
    """
    source = _source("web/app/decisions/page.tsx")
    assert "const label" in source
    assert "const summary" in source
    assert "proposal.action" in source
    assert "proposal.preview" in source
    assert "proposal.params" in source

    for action in CONSTRAINT_ACTIONS:
        lines = _action_lines(source, action)
        assert lines, f"missing decisions-history handling for {action}"
        assert any("label" in line or "summary" in line for line in lines), action


def test_shared_proposal_card_keeps_approve_and_reject_endpoints() -> None:
    """New actions reuse the bounded existing approval/rejection surface."""
    source = _source("web/components/ui/ProposalCard.tsx")

    assert "postJSON" in source
    assert "`/api/decisions/proposals/${proposalId}/approve`" in source
    assert "`/api/decisions/proposals/${proposalId}/reject`" in source
    assert "handleConfirm" in source
    assert "handleReject" in source


def test_post_commit_warning_is_visible_in_confirmation_message() -> None:
    """Approved-with-warning must not look identical to a fully clean apply."""
    source = _source("web/components/ui/ProposalCard.tsx")

    assert "mutationResult.warnings" in source
    assert 'warnings.join("; ")' in source
    assert "Внимание:" in source
