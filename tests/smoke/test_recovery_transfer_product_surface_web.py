"""Executable web contract for Issue #209 M6: RecoveryReplan product surface.

Pins the shared `ProposalCard` explicit variant-selection wiring and the
three compact blocks ("Почему вмешиваемся" / "Что меняется" / "Что
защищено") across Today, Decisions, and Coach — plus the Decisions history
rollback/identity contract per variant kind. No JS test runner exists in
this repo (see tests/smoke/test_feedback_planning_handoff.py for the same
source-string-contract pattern), so this file exercises the `.tsx` source
directly rather than mounting components.
"""
from pathlib import Path

import pytest

pytestmark = pytest.mark.smoke
REPO_ROOT = Path(__file__).resolve().parents[2]


def _source(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


def test_proposal_card_sends_selected_variant_kind_to_approve_not_an_empty_payload() -> None:
    """Today `ProposalCard.handleConfirm` posts `{}` for every
    `recovery_replan` approval, regardless of which variant is recommended
    or selected. Server-side, `approve_proposal`'s `variant_kind=None`
    legacy-defaults to `downgrade_today` (api/routers/decisions.py::
    `_resolve_recovery_variant_kind`), so a recommended `transfer_1_3d` is
    silently applied as a downgrade instead. The confirm call must carry
    the explicitly selected `variant_kind`."""
    source = _source("web/components/ui/ProposalCard.tsx")

    assert "variant_kind" in source
    assert "selectedVariantKind" in source
    assert "URLSearchParams" in source
    assert "params.set(\"variant_kind\", effectiveSelectedVariantKind)" in source
    assert "`/api/decisions/proposals/${proposalId}/approve?${params.toString()}`" in source


def test_proposal_card_variant_selection_defaults_to_recommended_and_is_reselectable() -> None:
    """The athlete may choose only among the proposal's own available
    `preview.variants` kinds; the initial selection is whichever variant the
    server flagged `recommended`, and re-selecting must only change the
    rendered `what_changes` preview (never mutate the plan)."""
    source = _source("web/components/ui/ProposalCard.tsx")

    assert "recommended_kind" in source
    assert "availableRecoveryVariants" in source
    assert "selectedVariantKind" in source
    assert '"downgrade_today"' in source
    assert "availableRecoveryVariants.some" in source


def test_recovery_downgrade_label_is_derived_from_target_date() -> None:
    source = _source("web/components/ui/ProposalCard.tsx")

    assert "function recoveryVariantLabel(" in source
    assert 'if (dayOffset === 0) return "Снизить нагрузку сегодня"' in source
    assert 'if (dayOffset === 1) return "Снизить нагрузку завтра"' in source
    assert "asRecord(variant.session).date ?? recommendedSession.date" in source
    assert "params.as_of" in source


def test_proposal_card_selection_is_scoped_to_the_exact_proposal_id() -> None:
    """React may reuse the shared component when an approved recovery proposal
    immediately yields another proposal for the new checkpoint. A selection
    such as `transfer_1_3d` from the old proposal must not survive into a new
    proposal that only offers `keep`/`downgrade_today`."""
    source = _source("web/components/ui/ProposalCard.tsx")

    assert "proposalId" in source
    assert "selectedProposalId" in source
    assert "selectedProposalId === proposalId" in source
    assert "availableRecoveryVariants.some" in source
    assert "setSelectedProposalId(proposalId)" in source


def test_selected_variant_drives_both_change_and_protection_views_without_mutation() -> None:
    source = _source("web/components/ui/ProposalCard.tsx")

    assert "selectedVariant" in source
    assert "selectedProtection" in source
    assert "selectedVariantKind" in source
    assert "whatChanges" in source
    assert "whatIsProtected" in source


def test_proposal_card_has_accessible_inspect_and_collapse_evidence_control() -> None:
    source = _source("web/components/ui/ProposalCard.tsx")

    assert "showEvidence" in source
    assert "setShowEvidence" in source
    assert 'aria-expanded={showEvidence}' in source
    assert "Показать доказательства" in source
    assert "Скрыть доказательства" in source


def test_proposal_card_renders_three_compact_block_headings_exactly() -> None:
    source = _source("web/components/ui/ProposalCard.tsx")

    assert "Почему вмешиваемся" in source
    assert "Что меняется" in source
    assert "Что защищено" in source


def test_proposal_card_renders_rejection_codes_via_machine_keyed_lookup_not_prose_parsing() -> None:
    """`rejected_reasons` must be labeled off the exact machine registry
    (models/recovery_transfer.py::REJECTION_REASON_CODES), matching this
    file's own `DAY_LABELS`-style precedent, never by matching localized
    substrings."""
    source = _source("web/components/ui/ProposalCard.tsx")

    for code in (
        "unavailable",
        "protected",
        "hard_collision",
        "recovery_spacing",
        "occasion_limit",
        "day_tss_ceiling",
        "day_duration_ceiling",
        "cross_week_boundary",
    ):
        assert f'"{code}"' in source or f"{code}:" in source, code


def test_proposal_card_keep_result_does_not_claim_a_checkpoint_or_rollback() -> None:
    """A confirmed `keep` is an audited no-op (no checkpoint, no
    `rollback_checkpoint_id`) — its confirmation copy must not reuse the
    downgrade's checkpoint/rollback message."""
    source = _source("web/components/ui/ProposalCard.tsx")

    assert "keepConfirmedMessage" in source


def test_proposal_card_transfer_confirmation_copy_uses_identity_and_dates_not_near_term_edit_text() -> None:
    """A confirmed `transfer_1_3d` result carries `old_session_id`/
    `new_session_id`/`affected_dates` (api/planning_service.py::
    `apply_recovery_replan_transfer`), not the legacy `near_term_edit`
    downgrade shape `recoveryConfirmedMessage` reads today."""
    source = _source("web/components/ui/ProposalCard.tsx")

    assert "transferConfirmedMessage" in source
    assert "old_session_id" in source
    assert "new_session_id" in source


def test_decisions_history_hides_rollback_control_for_keep_and_names_transfer_identity() -> None:
    """Today `ProposalEntry` in web/app/decisions/page.tsx shows the
    rollback button for ANY approved `recovery_replan` proposal with no
    check on `selected_kind` — an audited `keep` no-op (which never created
    a checkpoint) would offer a rollback with nothing to restore. An
    approved transfer's history entry must also name its identity handoff,
    not just a generic near-term-edit label."""
    source = _source("web/app/decisions/page.tsx")

    assert "MUTATING_RECOVERY_VARIANTS" in source
    assert 'new Set(["downgrade_today", "transfer_1_3d"])' in source
    assert "old_session_id" in source
    assert "new_session_id" in source
    assert "affected_dates" in source


def test_decisions_history_transfer_summary_uses_human_readable_label_not_raw_session_ids() -> None:
    """Issue #223: `ProposalEntry.recoverySummary` for a confirmed
    `transfer_1_3d` must read on the athlete's own language — the
    human-readable `new_session_label` the API assembles at confirm time
    (`api/planning_service.py::apply_recovery_replan_transfer`) — not the raw
    content-derived `ats_...` session ids. The ids stay available on
    `proposal.result` for evidence/tooltip/rollback use (per the identity
    contract pinned above), but the visible summary text must not
    concatenate `oldSessionId → newSessionId` directly."""
    source = _source("web/app/decisions/page.tsx")

    assert "new_session_label" in source
    assert '`${oldSessionId} → ${newSessionId}`' not in source


def test_today_decisions_coach_all_render_through_the_shared_proposal_card() -> None:
    """Regression guard: no duplicated recovery-transfer business logic
    across consumers — all three pages must keep rendering the one shared
    `ProposalCard`, not a per-page copy."""
    for relative_path in (
        "web/app/today/page.tsx",
        "web/app/decisions/page.tsx",
        "web/app/coach/page.tsx",
    ):
        source = _source(relative_path)
        assert 'from "@/components/ui/ProposalCard"' in source
        assert "<ProposalCard" in source
