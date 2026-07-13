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
    }


def _fingerprint(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def ensure_session_identities(
    goal_plan: Mapping[str, Any],
    previous_goal_plan: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a copy whose non-rest templates have deterministic stable IDs."""
    result = deepcopy(dict(goal_plan))
    daily_plan = list(result.get("daily_plan") or [])
    templates = [dict(item or {}) for item in list(result.get("session_templates") or [])]

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

        if previous_id and previous_material_fingerprint == material_fingerprint:
            session_id = previous_id
        else:
            session_id = generated_id

        template["session_id"] = session_id
        template["session_identity_rule_version"] = SESSION_ID_RULE_VERSION
        template["session_material_fingerprint"] = material_fingerprint
        if previous_id and previous_id != session_id:
            template["replaces_session_id"] = previous_id
        elif previous is not None and not template.get("replaces_session_id"):
            inherited_replacement = str(previous_template.get("replaces_session_id") or "").strip()
            if inherited_replacement and inherited_replacement != session_id:
                template["replaces_session_id"] = inherited_replacement
        elif template.get("replaces_session_id") == session_id:
            template.pop("replaces_session_id", None)

    result["session_templates"] = templates
    result["session_identity_rule_version"] = SESSION_ID_RULE_VERSION
    return result


__all__ = ["SESSION_ID_RULE_VERSION", "ensure_session_identities"]
