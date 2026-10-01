"""Pure, evidence-bound composition for the #610 Today decision story."""
from __future__ import annotations

from copy import deepcopy
from datetime import date
import math
from typing import Any, Mapping, Sequence

from models.readiness import PRIMARY_RECOVERY_KEYS


TODAY_DECISION_STORY_SCHEMA_VERSION = "today_decision_story_v1"
_SESSION_STATES = {"matched", "partial", "needs_confirmation", "unmatched", "data_gap"}


def _has_non_list(value: Any, key: str) -> bool:
    return isinstance(value, Mapping) and key in value and not isinstance(value[key], list)


def _list_value(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def compose_today_decision_story(
    *,
    as_of: str,
    session_projection: Mapping[str, Any] | None,
    readiness: Mapping[str, Any] | None,
    subjective_wellness: Mapping[str, Any] | None,
    primary_action: Mapping[str, Any] | None,
    rule_versions: Mapping[str, Any] | None,
    session_projections: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Compose a deterministic story without I/O, matching, or domain recalculation.

    An explicit current injury self-rating other than ``Нет`` prevents an
    unqualified ``follow_plan`` action. Missing or stale self-report is not
    treated as a negative answer and does not suppress the existing gate action;
    it is surfaced as an explicit caveat rather than clearance.
    """
    if session_projections is not None:
        return _compose_parent_stories(
            as_of=as_of, projections=session_projections, readiness=readiness,
            subjective_wellness=subjective_wellness, primary_action=primary_action,
            rule_versions=rule_versions,
        )
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
    unobserved_plan = _is_unobserved_plan(session, anchor, action_kind)

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
    elif (
        session_projection is not None
        and session_status in {"unmatched", "data_gap"}
        and not unobserved_plan
    ):
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


def _compose_parent_stories(
    *, as_of: str, projections: Sequence[Mapping[str, Any]],
    readiness: Mapping[str, Any] | None,
    subjective_wellness: Mapping[str, Any] | None,
    primary_action: Mapping[str, Any] | None,
    rule_versions: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Summarize independent parents without merging their identity or causes."""
    kwargs = dict(as_of=as_of, readiness=readiness,
                  subjective_wellness=subjective_wellness,
                  primary_action=primary_action, rule_versions=rule_versions)
    stories = [compose_today_decision_story(session_projection=p, **kwargs) for p in projections]
    if not stories:
        return compose_today_decision_story(session_projection=None, **kwargs)
    if len(stories) == 1:
        return stories[0]
    facts = [story["fact"] for story in stories]
    malformed = False
    for fact in facts:
        sid = fact["session_id"]
        if not isinstance(sid, str) or not sid.strip():
            fact["session_id"] = None
            malformed = True
        ids = fact["actual"]["activity_ids"]
        valid_ids = [identity for identity in ids if isinstance(identity, str) and identity.strip()]
        if valid_ids != ids:
            fact["actual"]["activity_ids"] = valid_ids
            malformed = True
    identities = [fact["session_id"] for fact in facts]
    actual_ids = [identity for fact in facts for identity in fact["actual"]["activity_ids"]]
    checkpoints = [fact["evidence_revision"].get("planning_checkpoint_id") for fact in facts]
    malformed_checkpoint = any(type(value) is not int or value <= 0 for value in checkpoints)
    revision_gap = (malformed_checkpoint or len(set(checkpoints)) != 1
                    or any(_date_text(fact["evidence_revision"].get("as_of")) != _date_text(as_of)
                           for fact in facts))
    overlapping = (malformed or revision_gap or len(set(identities)) != len(identities)
                   or len(set(actual_ids)) != len(actual_ids))
    # These are action priorities, not a new gate or a completion matcher.
    def priority(story: Mapping[str, Any]) -> int:
        status = story["interpretation"]["status"]
        return {"data_gap": 0, "needs_confirmation": 1, "conflicting_evidence": 2}.get(status, 3)
    result = deepcopy(min(stories, key=priority))
    states = [fact["projection_status"] for fact in facts]
    completions = [fact["completion_status"] for fact in facts]
    if overlapping or "data_gap" in states:
        state = "data_gap"
    elif "needs_confirmation" in states:
        state = "needs_confirmation"
    elif all(status == "matched" for status in states):
        state = "matched"
    elif all(status == "unmatched" for status in states):
        state = "unmatched"
    else:
        state = "partial"
    if state == "needs_confirmation":
        completion = "needs_confirmation"
    elif all(value == "complete" for value in completions):
        completion = "complete" if state != "data_gap" else "not_observed"
    elif any(value in {"complete", "incomplete"} for value in completions):
        completion = "incomplete"
    else:
        completion = "not_observed"

    def total(values: Sequence[Any]) -> float | None:
        numbers = [_number(value) for value in values]
        return round(sum(numbers), 1) if all(n is not None for n in numbers) else None

    revisions = [fact["evidence_revision"] for fact in facts]
    checkpoint_ids = [r.get("planning_checkpoint_id") for r in revisions]
    result["fact"] = {
        "session_id": None, "sessions": deepcopy(facts),
        "projection_status": state, "completion_status": completion,
        "plan": {"date": _date_text(as_of),
                 "load_tss": total([f["plan"].get("load_tss") for f in facts]),
                 "duration_minutes": total([f["plan"].get("duration_minutes") for f in facts])},
        "actual": {"activity_ids": list(dict.fromkeys(actual_ids)),
                   "load_tss": None if overlapping else total([f["actual"]["load_tss"] for f in facts]),
                   "legs": [], "transition": None},
        "deviation": {},
        "cause": {"status": "unknown", "code": "no_aggregate_cause_evidence", "evidence_refs": []},
        "evidence_revision": {"as_of": _date_text(as_of),
                              "planning_checkpoint_id": checkpoint_ids[0]
                              if not malformed_checkpoint and all(c == checkpoint_ids[0] for c in checkpoint_ids) else None},
    }
    result["evidence"] = [deepcopy(s["evidence"][0]) for s in stories] + deepcopy(stories[0]["evidence"][1:])
    if overlapping:
        # Preserve the source parent facts but do not double count shared activity evidence.
        result["interpretation"]["status"] = "data_gap"
        result["interpretation"]["summary"] = "Сопоставления сессий требуют проверки."
        result["recommendation"] = {"kind": "non_prescriptive_review", "summary": "Уточните связь активностей с планом."}
        result["next_action"].update(kind="inspect_evidence", summary="Проверьте сопоставление независимых сессий.",
                                     changes_plan=False, clearance_claim=False)
        if result["next_action"].get("caveat"):
            result["next_action"]["summary"] = _with_caveat(result["next_action"]["summary"])
    return result


def _is_unobserved_plan(session: Mapping[str, Any], anchor: str | None, action_kind: str) -> bool:
    """Distinguish an upcoming plan from an unmatched observed activity."""
    if action_kind != "follow_plan" or session.get("projection_status") != "unmatched":
        return False
    plan_date = _date_text(_mapping(session.get("plan")).get("date"))
    if not anchor or not plan_date or plan_date < anchor:
        return False
    fact = _mapping(session.get("fact"))
    if fact.get("completion_status") != "not_observed":
        return False
    if any(not isinstance(fact.get(key), list) or fact[key] for key in (
        "actual_activity_ids", "candidate_activity_ids", "legs"
    )):
        return False
    if any(
        value is not None and (type(value) not in (int, float) or value != 0)
        for value in (fact.get("duration_minutes"), fact.get("load_tss"))
    ):
        return False
    if _mapping(fact.get("transition")).get("actual_minutes") is not None:
        return False
    if _mapping(session.get("data_quality")).get("status") != "sufficient":
        return False
    if _mapping(session.get("confidence")).get("match_method") != "date_sport_heuristic":
        return False
    if _mapping(session.get("evidence_revision")).get("feedback_revision_id") is not None:
        return False
    additional_load = _mapping(session.get("load")).get("additional_unmatched_tss")
    return _number(additional_load) == 0


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
    observation_anchor = _date_text(freshness.get("anchor"))
    if observation_anchor and anchor and observation_anchor < anchor:
        return "stale"
    if readiness.get("stale") or freshness.get("state") in {"stale", "outdated"}:
        return "stale"
    keys = ("confirmed_today", "outdated", "unverified", "invalid", "missing")
    if any(not isinstance(freshness.get(key, []), list)
           or any(not isinstance(value, str) for value in freshness.get(key, []))
           for key in keys):
        return "unknown"
    confirmed = _list_value(freshness.get("confirmed_today"))
    primary = set(PRIMARY_RECOVERY_KEYS)
    contradictory = any(primary.intersection(_list_value(freshness.get(key)))
                        for key in ("outdated", "unverified", "invalid", "missing"))
    if (
        observation_anchor == anchor and anchor is not None
        and freshness.get("state") in {"fresh", "confirmed_today"}
        and primary.issubset(confirmed) and not contradictory
        and not freshness.get("blocked_reason")
        and not readiness.get("intervention_blocked_reason")
    ):
        return "current"
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
