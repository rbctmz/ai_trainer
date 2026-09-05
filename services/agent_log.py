"""Central write boundary for Agent Log v2 product events (#501).

Every new product producer records the same required provenance fields through
this helper.  Low-level persistence remains in :mod:`data.database`; this
module owns the product contract that a new event has an id, source evidence,
bounded scope, outcome, and an explicit revisit condition.
"""
from __future__ import annotations

from typing import Any

from models.coach_decisions import NO_REVISIT_REQUIRED


PROPOSAL_RESOLVED = "proposal_resolved"
NEXT_SCHEDULED_CHECK = "next_scheduled_check"
PROVIDER_AVAILABLE = "provider_available"
SYNC_RETRY_REQUIRED = "sync_retry_required"
REVISIT_REASONS = frozenset(
    {
        NO_REVISIT_REQUIRED,
        PROPOSAL_RESOLVED,
        NEXT_SCHEDULED_CHECK,
        PROVIDER_AVAILABLE,
        SYNC_RETRY_REQUIRED,
    }
)


def scope_for_sync_days(days: int | None) -> str:
    """Map a provider sync window onto the bounded Agent Log scope enum."""
    if days is not None and int(days) <= 1:
        return "today"
    if days is not None and int(days) <= 7:
        return "week"
    return "plan"


def record_agent_decision(
    db: Any,
    *,
    decision_type: str,
    reason: str,
    decision_event_id: str,
    trigger: str,
    trigger_source: str,
    scope: str,
    outcome: str,
    revisit_reason: str,
    revisit_at: str | None = None,
    **context: Any,
) -> dict[str, Any]:
    """Persist one fully sourced Agent Log v2 event.

    Callers must choose the semantic fields explicitly.  Rejecting an empty
    event id or source prevents a new producer from silently creating a v2 row
    that looks explainable but cannot be traced or replayed safely.
    """
    event_id = str(decision_event_id or "").strip()
    source = str(trigger_source or "").strip()
    revisit = str(revisit_reason or "").strip()
    if not event_id:
        raise ValueError("decision_event_id is required for Agent Log v2")
    if not source:
        raise ValueError("trigger_source is required for Agent Log v2")
    if not revisit and not revisit_at:
        raise ValueError("revisit_reason or revisit_at is required for Agent Log v2")
    if revisit and revisit not in REVISIT_REASONS:
        raise ValueError(
            f"revisit_reason must be one of {sorted(REVISIT_REASONS)} "
            f"(got {revisit!r})"
        )
    return db.save_coach_decision(
        decision_type=decision_type,
        reason=reason,
        decision_event_id=event_id,
        trigger=trigger,
        trigger_source=source,
        scope=scope,
        outcome=outcome,
        revisit_at=revisit_at,
        revisit_reason=revisit or None,
        **context,
    )


__all__ = [
    "NEXT_SCHEDULED_CHECK",
    "PROPOSAL_RESOLVED",
    "PROVIDER_AVAILABLE",
    "REVISIT_REASONS",
    "SYNC_RETRY_REQUIRED",
    "record_agent_decision",
    "scope_for_sync_days",
]
