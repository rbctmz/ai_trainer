"""Read-only, evidence-bounded directional drift report for coach turns."""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from typing import Any, Literal

ActualDirection = Literal["increase", "decrease", "neutral"]


def build_coach_drift_report(
    decisions: list[dict[str, Any]],
    proposals: list[dict[str, Any]],
    get_checkpoint: Callable[[int], dict[str, Any] | None],
) -> dict[str, Any]:
    """Compare only explicitly event-linked, locally applied plan mutations.

    The function intentionally does not use timestamps, chat ids, message ids,
    or provider-delivery outcomes. Missing lineage is returned as a data gap.
    """
    clean_decisions = [row for row in decisions if isinstance(row, dict)]
    clean_proposals = [row for row in proposals if isinstance(row, dict)]
    proposals_by_event: dict[str, list[dict[str, Any]]] = defaultdict(list)
    decisions_by_event: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for proposal in clean_proposals:
        event_id = _event_id(proposal)
        if event_id:
            proposals_by_event[event_id].append(proposal)
    for decision in clean_decisions:
        event_id = _event_id(decision)
        if event_id:
            decisions_by_event[event_id].append(decision)

    mismatches: list[dict[str, Any]] = []
    data_gaps: list[dict[str, Any]] = []
    linked_proposal_count = 0
    compared_count = 0
    no_change_count = 0

    for decision in clean_decisions:
        event_id = _event_id(decision)
        if not event_id:
            data_gaps.append(_gap(decision, reason="unlinked_decision"))
            continue
        if len(decisions_by_event[event_id]) != 1:
            data_gaps.append(_gap(decision, reason="ambiguous_decision_event"))
            continue

        linked = proposals_by_event.get(event_id, [])
        if not linked:
            data_gaps.append(_gap(decision, reason="no_linked_proposal"))
            continue
        linked_proposal_count += len(linked)

        for proposal in linked:
            if proposal.get("source") != "coach_tool":
                data_gaps.append(
                    _gap(
                        decision,
                        proposal=proposal,
                        reason="unattributed_proposal",
                        evidence={"proposal_source": proposal.get("source")},
                    )
                )
                continue
            status = str(proposal.get("status") or "")
            if status != "approved":
                data_gaps.append(
                    _gap(
                        decision,
                        proposal=proposal,
                        reason="proposal_not_active",
                        evidence={"proposal_status": status},
                    )
                )
                continue

            result = proposal.get("result")
            if not isinstance(result, Mapping):
                result = {}
            if (
                proposal.get("action") == "recovery_replan"
                and result.get("selected_kind") == "keep"
            ):
                no_change_count += 1
                continue

            base_id = _optional_int(proposal.get("base_checkpoint_id"))
            applied_id = _optional_int(proposal.get("applied_checkpoint_id"))
            if base_id is None or base_id <= 0 or applied_id is None or applied_id <= 0:
                data_gaps.append(
                    _gap(
                        decision,
                        proposal=proposal,
                        reason="missing_checkpoint_lineage",
                        evidence={
                            "base_checkpoint_id": base_id,
                            "applied_checkpoint_id": applied_id,
                        },
                    )
                )
                continue

            result_base_id = _optional_int(
                result.get("base_checkpoint_id", result.get("rollback_checkpoint_id"))
            )
            if result_base_id != base_id:
                data_gaps.append(
                    _gap(
                        decision,
                        proposal=proposal,
                        reason="result_base_mismatch",
                        evidence={
                            "stored_base_checkpoint_id": base_id,
                            "result_base_checkpoint_id": result_base_id,
                            "applied_checkpoint_id": applied_id,
                        },
                    )
                )
                continue

            base = get_checkpoint(base_id)
            applied = get_checkpoint(applied_id)
            if not isinstance(base, dict) or not isinstance(applied, dict):
                data_gaps.append(
                    _gap(
                        decision,
                        proposal=proposal,
                        reason="checkpoint_missing",
                        evidence={
                            "base_checkpoint_id": base_id,
                            "applied_checkpoint_id": applied_id,
                        },
                    )
                )
                continue

            parent_id = _checkpoint_parent_id(applied)
            if parent_id != base_id:
                data_gaps.append(
                    _gap(
                        decision,
                        proposal=proposal,
                        reason="checkpoint_parent_mismatch",
                        evidence={
                            "base_checkpoint_id": base_id,
                            "applied_checkpoint_id": applied_id,
                            "applied_parent_checkpoint_id": parent_id,
                        },
                    )
                )
                continue

            before_weekly = _checkpoint_weekly_tss(base)
            after_weekly = _checkpoint_weekly_tss(applied)
            if before_weekly is None or after_weekly is None:
                data_gaps.append(
                    _gap(
                        decision,
                        proposal=proposal,
                        reason="weekly_tss_missing",
                        evidence={
                            "base_checkpoint_id": base_id,
                            "applied_checkpoint_id": applied_id,
                        },
                    )
                )
                continue
            if len(before_weekly) != len(after_weekly):
                data_gaps.append(
                    _gap(
                        decision,
                        proposal=proposal,
                        reason="non_comparable_horizon",
                        evidence={
                            "base_checkpoint_id": base_id,
                            "applied_checkpoint_id": applied_id,
                            "weeks_before": len(before_weekly),
                            "weeks_after": len(after_weekly),
                        },
                    )
                )
                continue

            compared_count += 1
            before_total = sum(before_weekly)
            after_total = sum(after_weekly)
            delta = after_total - before_total
            direction: ActualDirection = (
                "increase" if delta > 0 else "decrease" if delta < 0 else "neutral"
            )
            decision_type = str(decision.get("decision_type") or "")
            if _is_mismatch(decision_type, direction):
                mismatches.append(
                    {
                        "decision_id": decision.get("id"),
                        "decision_type": decision_type,
                        "proposal_id": proposal.get("id"),
                        "action": proposal.get("action"),
                        "base_checkpoint_id": base_id,
                        "applied_checkpoint_id": applied_id,
                        "total_tss_before": before_total,
                        "total_tss_after": after_total,
                        "total_tss_delta": delta,
                        "actual_direction": direction,
                    }
                )

    for proposal in clean_proposals:
        event_id = _event_id(proposal)
        if not event_id:
            data_gaps.append(_proposal_gap(proposal, reason="unlinked_proposal"))
        elif event_id not in decisions_by_event:
            data_gaps.append(_proposal_gap(proposal, reason="proposal_without_decision"))

    return {
        "state": "ready" if compared_count > 0 else "data_gap",
        "decision_count": len(clean_decisions),
        "linked_proposal_count": linked_proposal_count,
        "compared_count": compared_count,
        "no_change_count": no_change_count,
        "mismatch_count": len(mismatches),
        "mismatches": mismatches,
        "data_gap_count": len(data_gaps),
        "data_gaps": data_gaps,
    }


def _event_id(row: Mapping[str, Any]) -> str:
    return str(row.get("decision_event_id") or "").strip()


def _gap(
    decision: Mapping[str, Any],
    *,
    reason: str,
    proposal: Mapping[str, Any] | None = None,
    evidence: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "decision_id": decision.get("id"),
        "decision_type": decision.get("decision_type"),
        "reason": reason,
    }
    if proposal is not None:
        item["proposal_id"] = proposal.get("id")
        item["action"] = proposal.get("action")
    if evidence:
        item["evidence"] = dict(evidence)
    return item


def _proposal_gap(
    proposal: Mapping[str, Any],
    *,
    reason: str,
) -> dict[str, Any]:
    return {
        "decision_id": None,
        "decision_type": None,
        "proposal_id": proposal.get("id"),
        "action": proposal.get("action"),
        "reason": reason,
        "evidence": {"proposal_status": proposal.get("status")},
    }


def _checkpoint_parent_id(checkpoint: Mapping[str, Any]) -> int | None:
    direct = _optional_int(checkpoint.get("checkpoint_parent_id"))
    if direct is not None:
        return direct
    snapshot = checkpoint.get("goal_plan_snapshot")
    if isinstance(snapshot, Mapping):
        return _optional_int(snapshot.get("checkpoint_parent_id"))
    return None


def _checkpoint_weekly_tss(checkpoint: Mapping[str, Any]) -> list[int] | None:
    raw: Any = checkpoint.get("weekly_tss_plan")
    if raw is None:
        snapshot = checkpoint.get("goal_plan_snapshot")
        raw = snapshot.get("weekly_tss_plan") if isinstance(snapshot, Mapping) else None
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)) or not raw:
        return None
    weekly: list[int] = []
    for value in raw:
        try:
            weekly.append(int(value))
        except (TypeError, ValueError):
            return None
    return weekly


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _is_mismatch(decision_type: str, direction: ActualDirection) -> bool:
    if decision_type == "Push":
        return direction == "decrease"
    if decision_type in {"Moderate", "Recovery"}:
        return direction == "increase"
    if decision_type == "Monitor":
        return direction != "neutral"
    return False
