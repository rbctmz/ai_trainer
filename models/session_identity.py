"""Stable material identity for planned training sessions."""
from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime
import hashlib
import json
from typing import Any, Mapping


SESSION_ID_RULE_VERSION = "session_identity_v1"


def _date_text(value: Any) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value or "")[:10]


def _number(value: Any) -> float:
    try:
        return round(float(value or 0.0), 3)
    except (TypeError, ValueError):
        return 0.0


def _prescription_payload(template: Mapping[str, Any]) -> dict[str, Any] | None:
    if not template.get("definition_snapshot") and not template.get("materialized_steps") and not template.get("legs"):
        return None
    legs = []
    for raw_leg in list(template.get("legs") or []):
        leg = dict(raw_leg or {})
        leg.pop("leg_id", None)
        legs.append(leg)
    return {
        "catalog_version": template.get("catalog_version"),
        "selector_rule_version": template.get("selector_rule_version"),
        "materializer_rule_version": template.get("materializer_rule_version"),
        "kind": template.get("kind"),
        "definition_snapshot": template.get("definition_snapshot"),
        "parameter_snapshot": template.get("parameter_snapshot"),
        "materialized_steps": template.get("materialized_steps"),
        "transition_minutes": template.get("transition_minutes"),
        "legs": legs,
    }


def _material_payload(daily_item: Any, template: Mapping[str, Any]) -> dict[str, Any]:
    dt, total, parts = daily_item
    normalized_parts = {
        str(key): _number(value)
        for key, value in sorted(dict(parts or {}).items())
        if _number(value) != 0.0
    }
    return {
        "rule_version": SESSION_ID_RULE_VERSION,
        "date": _date_text(dt),
        "total_tss": _number(total),
        "parts": normalized_parts,
        "phase": str(template.get("phase") or "").strip().lower(),
        "session_role": str(template.get("session_role") or "").strip().lower(),
        "session_focus": str(template.get("session_focus") or "").strip(),
        "sport": str(template.get("sport") or "").strip().lower(),
        "duration_minutes": int(round(_number(template.get("duration_minutes")))),
        "template_key": str(template.get("template_key") or "").strip(),
        "prescription": _prescription_payload(template),
    }


def _fingerprint(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _session_material_payload(date_text: str, session: Mapping[str, Any]) -> dict[str, Any]:
    """Identity material for one session inside a day (Issue #205).

    Derived from the session's content only — date, discipline, role, focus,
    load, and prescription — never from its position in the ``sessions`` array,
    so reordering the array cannot change identities.
    """
    return {
        "rule_version": SESSION_ID_RULE_VERSION,
        "date": date_text,
        "sport": str(session.get("sport") or "").strip().lower(),
        "session_role": str(session.get("session_role") or "").strip().lower(),
        "session_focus": str(session.get("session_focus") or "").strip(),
        "total_tss": _number(session.get("total_tss")),
        "duration_minutes": int(round(_number(session.get("duration_minutes")))),
        "template_key": str(session.get("template_key") or "").strip(),
        "prescription": _prescription_payload(session),
    }


def _session_sort_key(session: Mapping[str, Any]) -> tuple[str, str, float, str, str]:
    return (
        str(session.get("sport") or ""),
        str(session.get("session_role") or ""),
        _number(session.get("total_tss")),
        str(session.get("session_focus") or ""),
        str(session.get("template_key") or ""),
    )


def _session_content_order(date_text: str, sessions: list) -> list[tuple[int, str, str]]:
    """Canonical (position, fingerprint, base fingerprint) for a day's sessions.

    Identical same-day sessions are separated by an occurrence ordinal assigned
    in canonical content order, so reordering the array cannot change the
    fingerprint set. Shared by multi-session stamping and by cross-cardinality
    matching (Issue #209): a session whose content already lived on the same
    date is the SAME session, whatever the day's session count was. Matching
    uses the BASE fingerprint (no ordinal) because a twin's ordinal legitimately
    shifts when its duplicate sibling leaves the day.
    """
    occurrence_counts: dict[str, int] = {}
    ordered = sorted(
        range(len(sessions)),
        key=lambda position: _session_sort_key(sessions[position] or {}),
    )
    result: list[tuple[int, str, str]] = []
    for position in ordered:
        payload = _session_material_payload(date_text, dict(sessions[position] or {}))
        base_fingerprint = _fingerprint(payload)
        ordinal = occurrence_counts.get(base_fingerprint, 0)
        occurrence_counts[base_fingerprint] = ordinal + 1
        fingerprint = (
            _fingerprint({**payload, "occurrence": ordinal}) if ordinal else base_fingerprint
        )
        result.append((position, fingerprint, base_fingerprint))
    return result


# Day-level keys that describe the calendar slot rather than the executable
# session, and so are not copied into a session when migrating a legacy template.
_DAY_ONLY_TEMPLATE_KEYS = frozenset({"date", "week_index", "day_index", "phase", "sessions"})


def _session_from_legacy_template(template: Mapping[str, Any], total_tss: float) -> dict[str, Any]:
    """Wrap a pre-Issue-#205 single day template as one executable session."""
    session = {
        key: deepcopy(value)
        for key, value in template.items()
        if key not in _DAY_ONLY_TEMPLATE_KEYS
    }
    session.setdefault("total_tss", round(float(total_tss or 0.0), 1))
    return session


def ensure_session_identities(
    goal_plan: Mapping[str, Any],
    previous_goal_plan: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a copy whose non-rest templates have deterministic stable IDs."""
    result = deepcopy(dict(goal_plan))
    daily_plan = list(result.get("daily_plan") or [])
    templates = [dict(item or {}) for item in list(result.get("session_templates") or [])]

    # Ids already claimed as lineage by some session in THIS plan may not be
    # reused for a survivor match (Issue #209): the moved session's
    # `replaces_session_id` owns that id's history, and handing it to a
    # surviving identical twin would make the lineage ambiguous.
    claimed_replacements: set[str] = set()
    for claimed_template in templates:
        claimed = str(claimed_template.get("replaces_session_id") or "").strip()
        if claimed:
            claimed_replacements.add(claimed)
        for claimed_session in list(claimed_template.get("sessions") or []):
            claimed = str((claimed_session or {}).get("replaces_session_id") or "").strip()
            if claimed:
                claimed_replacements.add(claimed)

    previous_daily = list((previous_goal_plan or {}).get("daily_plan") or [])
    previous_templates = list((previous_goal_plan or {}).get("session_templates") or [])
    previous_by_date: dict[str, tuple[Any, Mapping[str, Any]]] = {}
    for index, item in enumerate(previous_daily):
        if not isinstance(item, (list, tuple)) or len(item) < 3:
            continue
        template = previous_templates[index] if index < len(previous_templates) else {}
        previous_by_date[_date_text(item[0])] = (item, template if isinstance(template, Mapping) else {})

    for index, item in enumerate(daily_plan):
        if not isinstance(item, (list, tuple)) or len(item) < 3:
            continue
        while len(templates) <= index:
            templates.append({})
        template = templates[index]
        total = _number(item[1])
        sport = str(template.get("sport") or "").strip().lower()
        role = str(template.get("session_role") or "").strip().lower()
        # Issue #205 milestone 2: migrate legacy checkpoints on read. A template
        # saved before this change has no `sessions`; wrap its single session so
        # every downstream consumer sees the nested shape uniformly. A rest or
        # race day carries no deliverable session.
        if "sessions" not in template:
            if total > 0 and sport not in {"", "off", "rest", "race"} and role != "off":
                template["sessions"] = [_session_from_legacy_template(template, total)]
            else:
                template["sessions"] = []
        is_race = role == "race" or bool(template.get("is_race_event"))
        if (total <= 0 and not is_race) or (sport in {"", "off", "rest"} and not is_race) or role == "off":
            template.pop("session_id", None)
            template.pop("session_material_fingerprint", None)
            template.pop("replaces_session_id", None)
            continue

        material = _material_payload(item, template)
        material_fingerprint = _fingerprint(material)
        generated_id = f"ats_{material_fingerprint[:24]}"
        embedded_id = str(template.get("session_id") or "").strip() or None
        embedded_material_fingerprint = str(
            template.get("session_material_fingerprint") or ""
        ).strip() or None
        previous = previous_by_date.get(material["date"])
        previous_id = embedded_id if previous is None else None
        previous_material_fingerprint = embedded_material_fingerprint if previous is None else None
        if previous is not None:
            previous_item, previous_template = previous
            previous_id = str(previous_template.get("session_id") or "").strip() or None
            previous_material_fingerprint = str(
                previous_template.get("session_material_fingerprint") or ""
            ).strip() or _fingerprint(_material_payload(previous_item, previous_template))

        # Issue #209: cross-cardinality survivor matching. When the day
        # fingerprint changed because a sibling session arrived or left, an
        # untouched session must keep its id — match it by content fingerprint
        # against the previous plan's SAME-DATE sessions (whatever their count
        # was) instead of minting a fresh identity with false lineage.
        sessions_now = list(template.get("sessions") or [])
        content_order = _session_content_order(material["date"], sessions_now)
        prev_ids_by_fp: dict[str, list[str]] = {}
        if previous is not None:
            previous_sessions = list(previous_template.get("sessions") or [])
            # Content matching applies ONLY across a cardinality change: with
            # the session count unchanged, a day-material edit must keep its
            # #205/#206 semantics — new identity plus lineage — even when the
            # nested session content happens to be untouched.
            if len(previous_sessions) != len(sessions_now):
                for prev_position, _prev_fingerprint, prev_base in _session_content_order(
                    material["date"], previous_sessions
                ):
                    prev_sid = str(
                        (previous_sessions[prev_position] or {}).get("session_id") or ""
                    ).strip()
                    if prev_sid and prev_sid not in claimed_replacements:
                        prev_ids_by_fp.setdefault(prev_base, []).append(prev_sid)

        reused_content_id: str | None = None
        if not (previous_id and previous_material_fingerprint == material_fingerprint):
            if len(sessions_now) == 1 and content_order:
                survivor_candidates = prev_ids_by_fp.get(content_order[0][2]) or []
                if survivor_candidates:
                    reused_content_id = survivor_candidates[0]

        if previous_id and previous_material_fingerprint == material_fingerprint:
            session_id = previous_id
        elif reused_content_id:
            session_id = reused_content_id
        else:
            session_id = generated_id

        template["session_id"] = session_id
        template["session_identity_rule_version"] = SESSION_ID_RULE_VERSION
        template["session_material_fingerprint"] = material_fingerprint
        if reused_content_id:
            # The survivor is the same session, not a replacement: no new
            # lineage; keep only lineage the session itself already carried.
            survivor_replaces = str(
                (sessions_now[0] or {}).get("replaces_session_id") or ""
            ).strip()
            if survivor_replaces and survivor_replaces != session_id:
                template["replaces_session_id"] = survivor_replaces
            else:
                template.pop("replaces_session_id", None)
        elif previous_id and previous_id != session_id:
            template["replaces_session_id"] = previous_id
        elif previous is not None and not template.get("replaces_session_id"):
            inherited_replacement = str(previous_template.get("replaces_session_id") or "").strip()
            if inherited_replacement and inherited_replacement != session_id:
                template["replaces_session_id"] = inherited_replacement
        elif template.get("replaces_session_id") == session_id:
            template.pop("replaces_session_id", None)

        if str(template.get("kind") or "") == "composite":
            legs = []
            for leg_index, raw_leg in enumerate(list(template.get("legs") or []), start=1):
                leg = dict(raw_leg or {})
                resolved_index = int(leg.get("leg_index") or leg_index)
                leg["leg_index"] = resolved_index
                leg["leg_id"] = f"{session_id}:{resolved_index}"
                legs.append(leg)
            template["legs"] = legs

        # Issue #205 milestone 2: the day's identity is a projection of its
        # primary session. Propagate the stamped id/fingerprint/lineage into
        # sessions[0] so every session carries a stable session_id and position
        # is never identity. Multi-session days (milestone 3) fingerprint each
        # secondary session on its own material.
        sessions = list(template.get("sessions") or [])
        if len(sessions) == 1:
            # A single-session day is the legacy-equivalent shape: the session
            # IS the day, so it inherits the day identity byte-for-byte. This
            # keeps every pre-#205 checkpoint's delivery external_id unchanged.
            # Exception (Issue #209): a session that already carries its own
            # content-level fingerprint (a survivor of a multi-session day)
            # keeps it — overwriting with the day fingerprint would churn on
            # every restamp because the content value is what recomputes.
            primary = dict(sessions[0] or {})
            primary["session_id"] = template["session_id"]
            own_fingerprint = str(primary.get("session_material_fingerprint") or "").strip()
            sole_content_fingerprint = content_order[0][1] if content_order else ""
            if own_fingerprint and own_fingerprint == sole_content_fingerprint:
                primary["session_material_fingerprint"] = own_fingerprint
            else:
                primary["session_material_fingerprint"] = template["session_material_fingerprint"]
            primary["session_identity_rule_version"] = SESSION_ID_RULE_VERSION
            if template.get("replaces_session_id"):
                primary["replaces_session_id"] = template["replaces_session_id"]
            else:
                primary.pop("replaces_session_id", None)
            if str(template.get("kind") or "") == "composite":
                primary["legs"] = template["legs"]
            sessions[0] = primary
            template["sessions"] = sessions
        elif len(sessions) > 1:
            # Issue #205 M3: on a multi-session day EVERY session id derives
            # from that session's own content — never from the day fingerprint
            # (which includes sibling load, so inheriting it would churn an
            # untouched session's identity when a sibling is edited) and never
            # from array position. Issue #209: an id is resolved in priority
            # order — a session already carrying a fingerprint-matching id
            # keeps it; else a content match against the previous plan's
            # same-date sessions reuses that id (a day that just grew its
            # second session must not churn the neighbour that was already
            # there); else the id is freshly content-derived.
            for position, session_fingerprint, session_base in content_order:
                session = dict(sessions[position] or {})
                embedded_sid = str(session.get("session_id") or "").strip()
                embedded_fp = str(session.get("session_material_fingerprint") or "").strip()
                if embedded_sid and embedded_fp == session_fingerprint:
                    resolved_id = embedded_sid
                else:
                    matched = prev_ids_by_fp.get(session_base) or []
                    resolved_id = matched.pop(0) if matched else f"ats_{session_fingerprint[:24]}"
                session["session_id"] = resolved_id
                session["session_material_fingerprint"] = session_fingerprint
                session["session_identity_rule_version"] = SESSION_ID_RULE_VERSION
                sessions[position] = session
            template["sessions"] = sessions

    result["session_templates"] = templates
    result["session_identity_rule_version"] = SESSION_ID_RULE_VERSION
    return result


__all__ = ["SESSION_ID_RULE_VERSION", "ensure_session_identities"]
