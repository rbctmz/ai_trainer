"""Deterministic coach decision audit helpers (Agent Log v2, issue #501)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Mapping, Sequence

DecisionType = Literal["Push", "Moderate", "Recovery", "Monitor"]

# Stable Agent Log v2 metadata values (issue #501). Rows persist these as TEXT
# on coach_decisions; `unknown` marks rows whose metadata predates v2 and is
# therefore not captured. Keep the value sets in sync with the TypeScript
# unions in web/lib/types.ts (contract:extract verifies the TS side only).
DecisionTrigger = Literal[
    "coach_request",
    "scheduled_check",
    "provider_sync",
    "settings_change",
    "proposal_approved",
    "manual",
    "unknown",
]
DecisionScope = Literal["today", "week", "plan", "unknown"]
DecisionOutcome = Literal[
    "applied",
    "proposed",
    "no_change",
    "rejected",
    "failed",
    "rolled_back",
    "unknown",
]

DECISION_TRIGGERS = frozenset(
    {
        "coach_request",
        "scheduled_check",
        "provider_sync",
        "settings_change",
        "proposal_approved",
        "manual",
        "unknown",
    }
)
DECISION_SCOPES = frozenset({"today", "week", "plan", "unknown"})
DECISION_OUTCOMES = frozenset(
    {
        "applied",
        "proposed",
        "no_change",
        "rejected",
        "failed",
        "rolled_back",
        "unknown",
    }
)

# Sentinel for the explicit "this decision needs no revisit" state. A NULL
# revisit_reason/revisit_at pair is reserved for legacy rows where the
# metadata was not captured; new product rows always write this sentinel so
# the log distinguishes "no revisit required" from "unknown" (issue #501 AC4).
NO_REVISIT_REQUIRED = "no_revisit_required"

# Allowed plan-mutation scope by proposal action: what the decision was
# permitted to affect if the action runs. `recovery_replan` may swap sessions
# within the current plan week (keep/downgrade today or transfer 1-3 days).
SCOPE_BY_PROPOSAL_ACTION: dict[str, str] = {
    "build_plan": "plan",
    "adjust_plan": "plan",
    "create_plan_constraint": "plan",
    "retract_plan_constraint": "plan",
    "recovery_replan": "week",
    "repair_plan_day": "today",
}

_SCOPE_WEIGHT = {"today": 0, "week": 1, "plan": 2}


def scope_for_proposal_actions(actions: Sequence[str] | None) -> str:
    """Widest allowed impact scope for proposal actions of one event.

    Chat turns without proposals only advise about the upcoming session, so
    their scope defaults to ``today``.
    """
    scopes = [
        SCOPE_BY_PROPOSAL_ACTION[str(action).strip()]
        for action in (actions or ())
        if str(action or "").strip() in SCOPE_BY_PROPOSAL_ACTION
    ]
    if not scopes:
        return "today"
    return max(scopes, key=lambda scope: _SCOPE_WEIGHT[scope])


def derive_decision_outcome(
    decision: Mapping[str, Any],
    proposals: Sequence[Mapping[str, Any]],
) -> str:
    """Current product outcome for one decision row (read-time refresh).

    Proposal statuses move after the decision row is written (approve, reject
    and rollback are separate later calls), so a stored snapshot can go stale.
    A decision without ``decision_event_id`` cannot be linked to its proposals
    and honestly stays ``unknown``; a decision whose event has proposals is
    derived from their current statuses; an event-linked row without proposals
    falls back to its stored snapshot, then ``unknown``.

    Approved recovery `keep` is an audited no-op (mirrors the special case in
    ``services/coach_drift.py``): nothing changed, so the outcome is no_change.
    """
    event_id = str(decision.get("decision_event_id") or "").strip()
    if not event_id:
        return "unknown"
    linked = [
        proposal
        for proposal in proposals
        if isinstance(proposal, Mapping)
        and str(proposal.get("decision_event_id") or "").strip() == event_id
    ]
    if not linked:
        return str(decision.get("outcome") or "") or "unknown"

    def _is_approved_non_keep(proposal: Mapping[str, Any]) -> bool:
        if str(proposal.get("status") or "") != "approved":
            return False
        if str(proposal.get("action") or "") == "recovery_replan":
            result = proposal.get("result")
            if isinstance(result, Mapping) and str(result.get("selected_kind")) == "keep":
                return False
        return True

    def _has(status: str) -> bool:
        return any(str(p.get("status") or "") == status for p in linked)

    if any(_is_approved_non_keep(p) for p in linked):
        return "applied"
    if _has("approved"):
        return "no_change"
    if _has("rolled_back"):
        return "rolled_back"
    if _has("pending") or _has("applying"):
        return "proposed"
    if _has("superseded"):
        return "no_change"
    if _has("failed"):
        return "failed"
    if _has("rejected"):
        return "rejected"
    return "unknown"


@dataclass(frozen=True)
class CoachDecision:
    decision_type: DecisionType
    reason: str
    workout_id: str | None = None
    trigger: DecisionTrigger | None = None
    trigger_source: str | None = None
    scope: DecisionScope | None = None
    outcome: DecisionOutcome | None = None
    revisit_at: str | None = None
    revisit_reason: str | None = None


def build_coach_decision(final_response: str, db: Any | None = None) -> CoachDecision:
    """Classify the final coach synthesis into a small auditable decision."""
    metrics = _performance_metrics(db)
    tsb = _num(metrics.get("tsb")) if metrics else None
    readiness = _latest_readiness(db)

    if tsb is not None:
        if tsb <= -20:
            return CoachDecision(
                "Recovery",
                _one_line(f"TSB {tsb:+.1f}: восстановление сегодня приоритетнее интенсивности."),
            )
        if tsb <= -8:
            return CoachDecision(
                "Moderate",
                _one_line(f"TSB {tsb:+.1f}: держите нагрузку контролируемой без агрессивной интенсивности."),
            )
        if tsb >= 5 and (readiness is None or readiness >= 55):
            return CoachDecision(
                "Push",
                _one_line(f"TSB {tsb:+.1f}: можно выполнить качественную работу по плану."),
            )

    text = (final_response or "").lower()
    if _has_any(text, ("восстанов", "отдых", "разгруз", "сниз", "уменьш", "устал", "перетрен")):
        return CoachDecision(
            "Recovery",
            "Ответ коуча ставит восстановление и снижение нагрузки выше интенсивности.",
        )
    if _has_any(text, ("умерен", "контрол", "осторож", "лёгк", "легк", "без интенсив")):
        return CoachDecision(
            "Moderate",
            "Ответ коуча рекомендует контролируемую умеренную нагрузку.",
        )
    if _has_any(text, ("интервал", "темпов", "качествен", "увелич", "повыс", "готов")):
        return CoachDecision(
            "Push",
            "Ответ коуча разрешает качественную работу или прогресс нагрузки.",
        )

    return CoachDecision(
        "Monitor",
        "Недостаточно сильного сигнала для изменения нагрузки.",
    )


def _performance_metrics(db: Any | None) -> dict[str, Any]:
    if db is None:
        return {}
    try:
        from models.ai_tools import AITools

        metrics = AITools(db).get_performance_metrics(days=90)
    except Exception:
        return {}
    return metrics if isinstance(metrics, dict) and "tsb" in metrics else {}


def _latest_readiness(db: Any | None) -> float | None:
    if db is None or not hasattr(db, "get_training_status"):
        return None
    try:
        frame = db.get_training_status(days=14)
    except Exception:
        return None
    if frame is None or getattr(frame, "empty", True) or "training_readiness" not in frame:
        return None
    for value in frame["training_readiness"]:
        parsed = _num(value)
        if parsed is not None:
            return parsed
    return None


def _num(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _has_any(text: str, needles: tuple[str, ...]) -> bool:
    return any(needle in text for needle in needles)


def _one_line(text: str, max_len: int = 160) -> str:
    cleaned = " ".join(str(text or "").split())
    if len(cleaned) <= max_len:
        return cleaned
    return cleaned[: max_len - 1].rstrip() + "…"
