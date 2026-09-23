"""Pure, evidence-bound composition for the #610 Today decision story."""
from __future__ import annotations

from copy import deepcopy
from datetime import date
import math
from typing import Any, Mapping


TODAY_DECISION_STORY_SCHEMA_VERSION = "today_decision_story_v1"
_SESSION_STATES = {"matched", "partial", "needs_confirmation", "unmatched", "data_gap"}


def _has_non_list(value: Any, key: str) -> bool:
    return isinstance(value, Mapping) and key in value and not isinstance(value[key], list)


def _list_value(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def compose_today_decision_story(
    *,
    as_of: str,
    session_projection: Mapping[str, Any] | None,
    readiness: Mapping[str, Any] | None,
    subjective_wellness: Mapping[str, Any] | None,
    primary_action: Mapping[str, Any] | None,
    rule_versions: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Compose a deterministic story without I/O, matching, or domain recalculation.

    An explicit current injury self-rating other than ``Нет`` prevents an
    unqualified ``follow_plan`` action. Missing or stale self-report is not
    treated as a negative answer and does not suppress the existing gate action;
    it is surfaced as an explicit caveat rather than clearance.
    """
    anchor = _date_text(as_of)
    session = _mapping(session_projection)
    readiness_data = _mapping(readiness)
    wellness = _mapping(subjective_wellness)
    action = _mapping(primary_action)
    supplied_versions = _mapping(rule_versions)
    malformed_evidence = (
        _has_non_list(session.get("fact"), "actual_activity_ids")
        or _has_non_list(session.get("fact"), "legs")
        or _has_non_list(readiness_data, "eligible_inputs")
    )
    versions = {
        "story": TODAY_DECISION_STORY_SCHEMA_VERSION,
        "readiness": supplied_versions.get("readiness"),
        "gate": supplied_versions.get("gate"),
        "session": supplied_versions.get("session"),
    }

    session_status = str(session.get("projection_status") or "data_gap")
    if session_status not in _SESSION_STATES:
        session_status = "data_gap"
    plan = _mapping(session.get("plan"))
    fact_source = _mapping(session.get("fact"))
    deviation = _mapping(session.get("deviation"))
    cause = _mapping(session.get("cause"))

    injury = _injury_evidence(wellness, anchor)
    action_kind = str(action.get("kind") or "inspect_evidence")
    action_reason = str(action.get("reason") or "Действие требует проверки доказательств.")

    if malformed_evidence:
        session_status = "data_gap"
        interpretation_status = "data_gap"
        recommendation = {
            "kind": "non_prescriptive_review",
            "summary": "Недостаточно данных, чтобы объяснить план и факт.",
        }
        next_action = {
            "kind": "inspect_evidence",
            "summary": "Проверьте данные сессии и сопоставление.",
            "enabled": True,
            "changes_plan": False,
            "clearance_claim": False,
        }
    elif session_status == "needs_confirmation":
        interpretation_status = "needs_confirmation"
        recommendation = {
            "kind": "confirm_match",
            "summary": "Подтвердите, какая активность относится к плановой сессии.",
        }
        next_action = {
            "kind": "confirm_match",
            "summary": "Подтвердите сопоставление активности с планом.",
            "enabled": True,
            "changes_plan": False,
            "clearance_claim": False,
        }
    elif session_projection is not None and session_status in {"unmatched", "data_gap"}:
        interpretation_status = "data_gap"
        recommendation = {
            "kind": "non_prescriptive_review",
            "summary": "Недостаточно данных, чтобы объяснить план и факт.",
        }
        next_action = {
            "kind": "inspect_evidence",
            "summary": "Проверьте данные сессии и сопоставление.",
            "enabled": True,
            "changes_plan": False,
            "clearance_claim": False,
        }
    elif injury["current_negative"] and action_kind == "follow_plan":
        interpretation_status = "conflicting_evidence"
        recommendation = {
            "kind": "non_prescriptive_review",
            "summary": "Свежая самооценка травмы расходится с сигналом готовности.",
            "rule_version": TODAY_DECISION_STORY_SCHEMA_VERSION,
        }
        next_action = {
            "kind": "inspect_evidence",
            "summary": "Проверьте отмеченное самочувствие перед решением по сессии.",
            "enabled": True,
            "changes_plan": False,
            "clearance_claim": False,
        }
    else:
        interpretation_status = "consistent" if action_kind == "follow_plan" else "actionable"
        recommendation = {
            "kind": action_kind,
            "summary": action_reason,
        }
        next_action = {
            "kind": action_kind,
            "summary": action_reason,
            "enabled": bool(action.get("enabled", True)),
            "changes_plan": action_kind in {"apply_plan_change", "deliver_workout"},
            "clearance_claim": False,
        }

    caveat = "no_current_injury_response" if not injury["current_response"] else None
    if caveat:
        next_action["caveat"] = caveat
        next_action["summary"] = _with_caveat(next_action["summary"])

    evidence = [
        {
            "kind": "session",
            "source": "session_projection",
            "ref": session.get("session_id"),
            "observation_date": _date_text(
                _mapping(session.get("evidence_revision")).get("as_of")
            ),
            "freshness": "current"
            if _date_text(_mapping(session.get("evidence_revision")).get("as_of")) == anchor
            else "unknown",
            "status": session_status,
        },
        {
            "kind": "readiness",
            "source": "canonical_snapshot",
            "ref": readiness_data.get("source") or "canonical_snapshot",
            "observation_date": _date_text(
                _mapping(readiness_data.get("freshness")).get("anchor")
                or readiness_data.get("as_of_date")
            ),
            "freshness": _readiness_freshness(readiness_data, anchor),
            "status": readiness_data.get("status") or "unknown",
            "eligible_inputs": _list_value(readiness_data.get("eligible_inputs")),
        },
        injury["evidence"],
    ]

    return {
        "schema_version": TODAY_DECISION_STORY_SCHEMA_VERSION,
        "date": anchor,
        "fact": {
            "session_id": session.get("session_id"),
            "projection_status": session_status,
            "completion_status": fact_source.get("completion_status") or "not_observed",
            "plan": deepcopy(plan),
            "actual": {
                "activity_ids": _list_value(fact_source.get("actual_activity_ids")),
                "load_tss": _number(fact_source.get("load_tss")),
                "legs": deepcopy(_list_value(fact_source.get("legs"))),
                "transition": deepcopy(fact_source.get("transition")),
            },
            "deviation": deepcopy(deviation),
            "cause": deepcopy(cause),
            "evidence_revision": deepcopy(_mapping(session.get("evidence_revision"))),
        },
        "interpretation": {
            "status": interpretation_status,
            "summary": _interpretation_summary(interpretation_status, action_reason),
            "caveat": caveat,
            "rule_versions": deepcopy(versions),
        },
        "recommendation": recommendation,
        "next_action": next_action,
        "evidence": evidence,
    }


def _injury_evidence(wellness: Mapping[str, Any], anchor: str) -> dict[str, Any]:
    items = wellness.get("items")
    item_rows = items if isinstance(items, list) else []
    row = next(
        (
            item
            for item in item_rows
            if isinstance(item, Mapping) and str(item.get("key") or "") == "injury"
        ),
        None,
    )
    row = _mapping(row)
    state = str(row.get("state") or "missing")
    observation_date = _date_text(wellness.get("date"))
    status = str(wellness.get("status") or "missing")
    value = row.get("value")
    valid_value = type(value) is int and 1 <= value <= 4

    if status == "unavailable":
        freshness = "unavailable"
    elif status == "missing" or row is None or state == "missing":
        freshness = "missing"
    elif state == "invalid" or (state == "present" and not valid_value):
        freshness = "invalid"
    elif status == "current" and observation_date == anchor and state == "present":
        freshness = "current"
    else:
        freshness = "stale" if observation_date and observation_date != anchor else "unknown"

    current_response = freshness == "current" and valid_value
    current_negative = bool(current_response and value != 1)
    evidence = {
        "kind": "subjective_wellness",
        "key": "injury",
        "source": str(wellness.get("source") or "unknown"),
        "ref": str(wellness.get("mapping_version") or "intervals_subjective_unknown"),
        "state": state,
        "value": value if valid_value else None,
        "value_label": str(row.get("value_label") or "Нет ответа"),
        "observation_date": observation_date,
        "freshness": freshness,
        "eligible_for_clearance": False,
    }
    return {
        "current_response": bool(current_response),
        "current_negative": current_negative,
        "evidence": evidence,
    }


def _readiness_freshness(readiness: Mapping[str, Any], anchor: str) -> str:
    freshness = _mapping(readiness.get("freshness"))
    if freshness.get("state") == "confirmed_today" and _date_text(freshness.get("anchor")) == anchor:
        return "current"
    if readiness.get("stale") or freshness.get("state") in {"stale", "outdated"}:
        return "stale"
    return "unknown"


def _interpretation_summary(status: str, reason: str) -> str:
    if status == "conflicting_evidence":
        return "Свежая самооценка травмы требует внимания; диагноз и изменение плана не выводятся."
    if status == "needs_confirmation":
        return "Факт активности неоднозначен и требует подтверждения."
    if status == "data_gap":
        return "Данных недостаточно для уверенного вывода."
    return reason


def _with_caveat(summary: str) -> str:
    suffix = " Свежего ответа о травме нет; это не подтверждение отсутствия симптомов."
    return summary if suffix.strip() in summary else f"{summary}{suffix}"


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _date_text(value: Any) -> str | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(str(value)[:10]).isoformat()
    except ValueError:
        return None


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


__all__ = ["TODAY_DECISION_STORY_SCHEMA_VERSION", "compose_today_decision_story"]
