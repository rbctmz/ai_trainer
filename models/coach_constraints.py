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
            for key in (
                "definition_snapshot",
                "parameter_snapshot",
                "materialized_steps",
                "target_provenance",
                "selection_evidence",
                "prescription_fingerprint",
                "legs",
                "transition_minutes",
                "template_version",
                "template_name",
                "stimulus",
                "fatigue_cost",
                "expected_recovery_hours",
                "mutation_evidence",
            ):
                template.pop(key, None)
            template.update(
                {
                    "session_role": "off",
                    "sport": "off",
                    "sport_label": "отдых",
                    "kind": "single",
                    "template_key": f"constraint:{constraint.get('kind') or 'off'}",
                    "materialization_status": "constraint_off",
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
    if protected_dates:
        updated["protected_dates"] = sorted(
            {
                str(value)[:10]
                for value in list(updated.get("protected_dates") or []) + protected_dates
                if value
            }
        )
        refreshed_changes = []
        for raw_change in list(updated.get("microcycle_changes") or []):
            change = deepcopy(dict(raw_change or {}))
            day = str(change.get("date") or "")[:10]
            if day in protected_dates:
                matching = next((row for row in applied if row.get("date") == day), {})
                change["after"] = {
                    **dict(change.get("after") or {}),
                    "role": "off",
                    "sport": "off",
                    "focus": _constraint_note(matching),
                    "tss": 0.0,
                }
            refreshed_changes.append(change)
        updated["microcycle_changes"] = refreshed_changes
    _refresh_weekly_totals(updated, applied)

    constraint_summary = dict(updated.get("constraint_summary") or {})
    constraint_summary["durable_constraints"] = {
        "applied_count": len(applied),
        "protected_dates": protected_dates,
        "constraints": applied,
    }
    updated["constraint_summary"] = constraint_summary

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


def _refresh_weekly_totals(goal_plan: dict[str, Any], applied: list[dict[str, Any]]) -> None:
    if not applied:
        return

    daily_plan = list(goal_plan.get("daily_plan") or [])
    if not daily_plan:
        return

    weekly_summary = [dict(row or {}) for row in list(goal_plan.get("weekly_summary") or [])]
    week_count = max(len(weekly_summary), (len(daily_plan) + 6) // 7)
    weekly_tss = [0.0 for _ in range(week_count)]
    weekly_parts: list[dict[str, float]] = [dict() for _ in range(week_count)]

    for index, item in enumerate(daily_plan):
        if not isinstance(item, (list, tuple)) or len(item) < 3:
            continue
        week_index = index // 7
        if week_index >= week_count:
            continue
        _dt, total, parts = item
        weekly_tss[week_index] += _float(total)
        if isinstance(parts, Mapping):
            for key, value in parts.items():
                part_key = str(key)
                weekly_parts[week_index][part_key] = weekly_parts[week_index].get(part_key, 0.0) + _float(value)

    goal_plan["weekly_tss_plan"] = [int(round(value)) for value in weekly_tss]

    note = _constraint_application_note(applied)
    for index, total in enumerate(weekly_tss):
        if index >= len(weekly_summary):
            weekly_summary.append({})
        row = dict(weekly_summary[index] or {})
        row["weekly_tss"] = int(round(total))
        for sport, value in weekly_parts[index].items():
            row[sport] = round(value, 1)
        row["adjustment_note"] = _append_note(row.get("adjustment_note"), note)
        weekly_summary[index] = row

    goal_plan["weekly_summary"] = weekly_summary


def _float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _constraint_application_note(applied: list[dict[str, Any]]) -> str:
    dates = [str(row.get("date") or "") for row in applied if row.get("date")]
    if not dates:
        return "durable constraints: protected days applied"
    return f"durable constraints: protected {', '.join(dates)}"


def _append_note(existing: Any, note: str) -> str:
    text = str(existing or "").strip()
    if not text or text == "—":
        return note
    if note in text:
        return text
    return f"{text}; {note}"
