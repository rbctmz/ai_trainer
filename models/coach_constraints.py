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

# Issue #473: constraint scope. ``None``/empty means the WHOLE day is protected;
# a canonical sport means only the matching legs of that day are removed and
# every other leg (sessions, TSS parts, their matched feedback) survives.
CONSTRAINT_SPORT_ALIASES = {
    "bike": "bike",
    "cycling": "bike",
    "velo": "bike",
    "вело": "bike",
    "велосипед": "bike",
    "run": "run",
    "running": "run",
    "бег": "run",
    "swim": "swim",
    "swimming": "swim",
    "плавание": "swim",
    "плавания": "swim",
}


def normalize_constraint_sport(value: Any) -> str | None:
    """Map a free-form sport mention to the canonical leg sport, or None.

    ``None`` means WHOLE-DAY scope (the legacy behavior). Unknown non-empty
    values are rejected with ValueError so a typo cannot silently widen an
    athlete's day into a rest day (see issue #473 — that is exactly how a
    cancelled swim once erased a completed bike leg of the same day).
    """
    text = str(value or "").strip().lower()
    if not text:
        return None
    canonical = CONSTRAINT_SPORT_ALIASES.get(text)
    if canonical is None:
        allowed = sorted({alias for alias in CONSTRAINT_SPORT_ALIASES.values()})
        raise ValueError(
            f"sport must map to one of {allowed} (got {value!r}); "
            "pass an empty sport for a whole-day constraint"
        )
    return canonical


def _day_is_composite(template: Mapping[str, Any] | None) -> bool:
    kind = str((template or {}).get("kind") or "").strip().lower()
    return kind == "composite" or "brick" in str((template or {}).get("template_key") or "").lower()


def _whole_day_constrained(constrained_sports: set[str], template: Mapping[str, Any] | None) -> bool:
    """When the scoped removal leaves no executable leg, degrade to a full off-day."""
    if _day_is_composite(template):
        # Brick/composite legs share materialized steps across sports; there is
        # no safe per-leg cut there yet, so stay conservative (whole day).
        return True
    remaining = [
        session
        for session in list((template or {}).get("sessions") or [])
        if isinstance(session, dict)
        and str(session.get("sport") or "").strip().lower() not in constrained_sports
    ]
    return not remaining


def apply_constraints_to_goal_plan(
    goal_plan: Mapping[str, Any],
    constraints: list[Mapping[str, Any]] | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return a copied goal plan with active matching day constraints applied.

    A constraint without ``sport`` zeroes the WHOLE day (legacy behavior, kept
    for sickness/rest-style full-day protection). A constraint WITH ``sport``
    removes only the matching legs of that day and keeps every other leg — its
    session id, steps, TSS parts and any confirmed plan-vs-fact match untouched.
    If removing the legs drains the day of all sessions (or the day is a
    composite/brick), the day still becomes the classic constraint-off day.
    This helper never redistributes load or rebuilds the full plan.
    """
    updated = deepcopy(dict(goal_plan or {}))
    daily_plan = list(updated.get("daily_plan") or [])
    session_templates = list(updated.get("session_templates") or [])
    scoped_by_date = _constraints_with_scope_by_date(constraints or [])

    applied: list[dict[str, Any]] = []
    protected_dates: list[str] = []  # whole days only (rebalance/overlay semantics)

    for index, item in enumerate(daily_plan):
        if not isinstance(item, (list, tuple)) or len(item) < 3:
            continue
        day = _date_key(item[0])
        if not day or day not in scoped_by_date:
            continue

        constraint_rows = scoped_by_date[day]
        whole_sports = sorted({scope for _, scope in constraint_rows if scope is not None})
        has_whole_day_scope = any(scope is None for _, scope in constraint_rows)
        template = (
            session_templates[index]
            if index < len(session_templates) and isinstance(session_templates[index], dict)
            else None
        )

        if has_whole_day_scope or _whole_day_constrained(set(whole_sports), template):
            anchor = next(
                (
                    row
                    for row, scope in constraint_rows
                    if scope is None or not whole_sports
                ),
                constraint_rows[0][0],
            )
            _apply_whole_day_zeroing(daily_plan, index, session_templates, index, anchor)
            protected_dates.append(day)
            summary_sport: str | None = None
        else:
            # A partially drained day keeps its remaining legs verbatim; the
            # full-drain case was routed to whole-day zeroing above.
            # Audit rows name the exact constraint row behind each canceled leg.
            _remove_legs(template, set(whole_sports), constraint_rows)  # mutates copy; audit lands in canceled_legs
            surviving = [s for s in list(template.get("sessions") or []) if isinstance(s, dict)]
            if isinstance(template, dict):
                total_minutes = round(sum(_float(s.get("duration_minutes")) for s in surviving), 1)
                template["duration_minutes"] = total_minutes
            new_total = round(sum(_float(s.get("total_tss")) for s in surviving), 1)
            merged_parts = _zero_parts(item[2])
            for session in surviving:
                if session.get("sport"):
                    sport_key = str(session["sport"]).strip().lower()
                    merged_parts[sport_key] = round(_float(session.get("total_tss")), 1)
            _dt, _old_total, _old_parts = item
            daily_plan[index] = (_dt, float(new_total), merged_parts)
            summary_sport = ",".join(whole_sports) or None

        anchor_for_note = constraint_rows[0][0]
        applied.append(
            {
                "date": day,
                "constraint_id": anchor_for_note.get("id"),
                "kind": anchor_for_note.get("kind"),
                "source": anchor_for_note.get("source"),
                "sport": summary_sport,
            }
        )

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


def _apply_whole_day_zeroing(
    daily_plan: list[Any],
    index: int,
    session_templates: list[Any],
    template_index: int,
    constraint: Mapping[str, Any],
) -> None:
    """Turn one day into the classic zero-load constraint-off day (legacy shape)."""
    item = daily_plan[index]
    _dt, _total, parts = item
    daily_plan[index] = (item[0], 0, _zero_parts(parts))

    if template_index >= len(session_templates) or not isinstance(session_templates[template_index], dict):
        return
    template = dict(session_templates[template_index])
    note = _constraint_note(constraint)
    # Issue #205: a constraint-off day carries no executable sessions.
    # Record the displaced ids instead of leaving stale sessions behind.
    replaced_session_ids = [
        str(session.get("session_id") or "")
        for session in list(template.get("sessions") or [])
        if isinstance(session, dict) and session.get("session_id")
    ]
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
        "allocated_parts",
        "brick_status",
        "brick_status_reason",
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
            "sessions": [],
        }
    )
    if replaced_session_ids:
        template["replaced_session_ids"] = replaced_session_ids
    session_templates[template_index] = template


def _constraints_with_scope_by_date(
    constraints: list[Mapping[str, Any]],
) -> dict[str, list[tuple[Mapping[str, Any], str | None]]]:
    """Active protective constraints grouped by day with their resolved sport scope."""
    by_date: dict[str, list[tuple[Mapping[str, Any], str | None]]] = {}
    for constraint in constraints:
        status = str(constraint.get("status") or "active")
        if status != "active":
            continue
        kind = str(constraint.get("kind") or "")
        if kind not in PROTECTIVE_CONSTRAINT_KINDS:
            continue
        day = _date_key(constraint.get("date"))
        if not day:
            continue
        raw_sport = constraint.get("sport")
        scope = None if raw_sport in (None, "") else normalize_constraint_sport(raw_sport)
        by_date.setdefault(day, []).append((constraint, scope))
    return by_date


def _remove_legs(
    template: Mapping[str, Any] | None,
    constrained_sports: set[str],
    caused_by: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Remove constrained legs from the template (mutates the copy), returns audit rows."""
    if not isinstance(template, dict):
        return []
    candidates: list[tuple[Mapping[str, Any], str | None]] = []
    if isinstance(caused_by, Mapping):
        candidates = [(caused_by, None)]
    elif isinstance(caused_by, (list, tuple)):
        candidates = [item for item in caused_by if isinstance(item, tuple) and len(item) >= 2]
    sessions = list(template.get("sessions") or [])
    kept: list[Any] = []
    removed: list[dict[str, Any]] = []
    for session in sessions:
        if isinstance(session, dict) and str(session.get("sport") or "").strip().lower() in constrained_sports:
            sport_key = str(session.get("sport") or "").strip().lower()
            cause = next(
                ((row, _)[0] for row, _ in candidates if _ == sport_key),
                candidates[0][0] if candidates else {},
            )
            removed.append(
                {
                    "session_id": str(session.get("session_id") or ""),
                    "sport": sport_key,
                    "duration_minutes": _float(session.get("duration_minutes")),
                    "total_tss": _float(session.get("total_tss")),
                    "reason": "constraint",
                    "constraint_id": cause.get("id"),
                    "kind": cause.get("kind"),
                    "note": cause.get("note"),
                }
            )
        else:
            kept.append(session)
    template["sessions"] = kept
    if removed:
        canceled = list(template.get("canceled_legs") or [])
        template["canceled_legs"] = canceled + removed
    allocated_parts = template.get("allocated_parts")
    if isinstance(allocated_parts, dict):
        for sport_key in [key for key in allocated_parts if str(key).strip().lower() in constrained_sports]:
            allocated_parts[sport_key] = 0.0
    return removed


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


def recalc_goal_plan_weekly_totals(goal_plan: dict[str, Any]) -> None:
    """Pure numeric recompute of `weekly_tss_plan` and `weekly_summary` from `daily_plan`.

    Never touches `adjustment_note` — annotation is the caller's concern.
    Used both by constraint application and by constraint-retraction repairs
    so both paths share one arithmetic implementation (#473).
    """
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

    for index, total in enumerate(weekly_tss):
        if index >= len(weekly_summary):
            weekly_summary.append({})
        row = dict(weekly_summary[index] or {})
        row["weekly_tss"] = int(round(total))
        for sport, value in weekly_parts[index].items():
            row[sport] = round(value, 1)
        weekly_summary[index] = row

    goal_plan["weekly_summary"] = weekly_summary


def _refresh_weekly_totals(goal_plan: dict[str, Any], applied: list[dict[str, Any]]) -> None:
    if not applied:
        return

    daily_plan = list(goal_plan.get("daily_plan") or [])
    if not daily_plan:
        return

    recalc_goal_plan_weekly_totals(goal_plan)

    note = _constraint_application_note(applied)
    for row in list(goal_plan.get("weekly_summary") or []):
        row["adjustment_note"] = _append_note(row.get("adjustment_note"), note)


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
