"""Durable coach constraint helpers for planning flows."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any, Mapping


PROTECTIVE_CONSTRAINT_KINDS = {
    "sick",
    "unavailable",
    "forced_rest",
    "manual_delete",
    "disabled_plan_day",
}


def apply_constraints_to_goal_plan(
    goal_plan: Mapping[str, Any],
    constraints: list[Mapping[str, Any]] | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return a copied goal plan with active matching day constraints applied.

    The helper is intentionally narrow: it protects exact dates by turning the
    matching day into a zero-load day and annotating the matching session
    template. It does not redistribute load or rebuild the full plan.
    """
    updated = deepcopy(dict(goal_plan or {}))
    daily_plan = list(updated.get("daily_plan") or [])
    session_templates = list(updated.get("session_templates") or [])
    active_constraints = _active_constraints_by_date(constraints or [])

    applied: list[dict[str, Any]] = []
    protected_dates: list[str] = []

    for index, item in enumerate(daily_plan):
        if not isinstance(item, (list, tuple)) or len(item) < 3:
            continue
        day = _date_key(item[0])
        if not day or day not in active_constraints:
            continue

        constraint = active_constraints[day]
        _dt, _total, parts = item
        zero_parts = _zero_parts(parts)
        daily_plan[index] = (item[0], 0, zero_parts)
        protected_dates.append(day)
        applied.append(
            {
                "date": day,
                "constraint_id": constraint.get("id"),
                "kind": constraint.get("kind"),
                "source": constraint.get("source"),
            }
        )

        if index < len(session_templates) and isinstance(session_templates[index], dict):
            template = dict(session_templates[index])
            note = _constraint_note(constraint)
            template.update(
                {
                    "session_role": "off",
                    "protected_by_constraint": True,
                    "constraint": {
                        "id": constraint.get("id"),
                        "kind": constraint.get("kind"),
                        "source": constraint.get("source"),
                        "note": constraint.get("note"),
                    },
                    "adjustment_note": note,
                    "export_name": note,
                    "duration_minutes": 0,
                }
            )
            session_templates[index] = template

    updated["daily_plan"] = daily_plan
    updated["session_templates"] = session_templates
    return updated, {
        "applied_count": len(applied),
        "protected_dates": protected_dates,
        "constraints": applied,
    }


def _active_constraints_by_date(
    constraints: list[Mapping[str, Any]],
) -> dict[str, Mapping[str, Any]]:
    by_date: dict[str, Mapping[str, Any]] = {}
    for constraint in constraints:
        if str(constraint.get("status") or "active") != "active":
            continue
        kind = str(constraint.get("kind") or "")
        if kind not in PROTECTIVE_CONSTRAINT_KINDS:
            continue
        day = _date_key(constraint.get("date"))
        if not day:
            continue
        by_date.setdefault(day, constraint)
    return by_date


def _date_key(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if hasattr(value, "isoformat") and not isinstance(value, str):
        return str(value.isoformat())[:10]
    text = str(value).strip()
    return text[:10] if text else None


def _zero_parts(parts: Any) -> dict[str, float]:
    if isinstance(parts, Mapping):
        return {str(key): 0.0 for key in parts.keys()}
    return {}


def _constraint_note(constraint: Mapping[str, Any]) -> str:
    kind_label = {
        "sick": "Болезнь",
        "unavailable": "Недоступен",
        "forced_rest": "Принудительный отдых",
        "manual_delete": "Удалено вручную",
        "disabled_plan_day": "План отключён на день",
    }.get(str(constraint.get("kind") or ""), "Ограничение")
    note = str(constraint.get("note") or "").strip()
    return f"{kind_label}: {note}" if note else kind_label
