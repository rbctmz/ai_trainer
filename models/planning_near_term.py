"""Helpers for editing the near-term daily plan without rebuilding the whole cycle."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Mapping, Sequence

from models.training_planner import (
    SESSION_ROLE_LABELS_RU,
    SPORT_LABELS_RU,
    WEEKDAY_LABELS_RU,
    _build_day_focus_label,
    _build_session_description,
    _build_session_export_name,
    _build_week_structure_metadata,
    _dominant_sport,
    _estimate_session_duration_minutes,
)

EDITABLE_NEAR_TERM_HORIZON_MIN = 7
EDITABLE_NEAR_TERM_HORIZON_MAX = 10
EDITABLE_SESSION_ROLES = ["off", "recovery", "easy", "quality", "long"]
EDITABLE_SPORTS = ["run", "bike", "swim", "off"]


def _normalize_session_role(value: Any) -> str:
    role = str(value or "").strip().lower()
    return role if role in EDITABLE_SESSION_ROLES else "easy"


def _normalize_sport(value: Any) -> str:
    sport = str(value or "").strip().lower()
    return sport if sport in EDITABLE_SPORTS else "run"


def _normalize_total_tss(value: Any) -> float:
    try:
        total_tss = float(value)
    except (TypeError, ValueError):
        total_tss = 0.0
    return round(max(0.0, total_tss), 1)


def _normalize_horizon_days(horizon_days: int | None, daily_count: int) -> int:
    if daily_count <= 0:
        return 0
    raw = int(horizon_days or EDITABLE_NEAR_TERM_HORIZON_MIN)
    raw = max(EDITABLE_NEAR_TERM_HORIZON_MIN, min(EDITABLE_NEAR_TERM_HORIZON_MAX, raw))
    return min(raw, daily_count)


def _clone_daily_plan(goal_plan: Mapping[str, Any]) -> List[tuple[datetime, float, Dict[str, float]]]:
    cloned: List[tuple[datetime, float, Dict[str, float]]] = []
    for dt, total, parts in goal_plan.get("daily_plan", []) or []:
        cloned.append((dt, float(total or 0.0), dict(parts or {})))
    return cloned


def _clone_session_templates(goal_plan: Mapping[str, Any], daily_plan: Sequence[tuple[datetime, float, Dict[str, float]]]) -> List[Dict[str, Any]]:
    templates: List[Dict[str, Any]] = []
    source_templates = list(goal_plan.get("session_templates", []) or [])
    for idx, (dt, total, parts) in enumerate(daily_plan):
        if idx < len(source_templates):
            template = dict(source_templates[idx] or {})
        else:
            sport = _dominant_sport(parts)
            role = "off" if sport == "off" or total <= 0 else "easy"
            focus = _build_day_focus_label(role, sport)
            template = {
                "date": dt.strftime("%Y-%m-%d"),
                "week_index": idx // 7,
                "day_index": idx % 7,
                "phase": "Base",
                "session_role": role,
                "session_focus": focus,
                "sport": sport,
                "sport_label": SPORT_LABELS_RU.get(sport, sport),
            }
        templates.append(template)
    return templates


def _scale_parts_to_total(parts: Mapping[str, float], new_total_tss: float, preferred_sport: str) -> Dict[str, float]:
    active_total = sum(float(value or 0.0) for value in parts.values())
    if new_total_tss <= 0 or active_total <= 0:
        return {"run": 0.0, "bike": 0.0, "swim": 0.0}

    scale = new_total_tss / active_total
    scaled = {
        "run": round(float(parts.get("run", 0.0) or 0.0) * scale, 1),
        "bike": round(float(parts.get("bike", 0.0) or 0.0) * scale, 1),
        "swim": round(float(parts.get("swim", 0.0) or 0.0) * scale, 1),
    }
    diff = round(new_total_tss - sum(scaled.values()), 1)
    if abs(diff) >= 0.1:
        target_sport = preferred_sport if preferred_sport in {"run", "bike", "swim"} else _dominant_sport(scaled)
        if target_sport == "off":
            target_sport = "run"
        scaled[target_sport] = round(max(0.0, scaled.get(target_sport, 0.0) + diff), 1)
    return scaled


def _single_sport_parts(total_tss: float, sport: str) -> Dict[str, float]:
    if total_tss <= 0 or sport == "off":
        return {"run": 0.0, "bike": 0.0, "swim": 0.0}
    return {
        "run": round(total_tss, 1) if sport == "run" else 0.0,
        "bike": round(total_tss, 1) if sport == "bike" else 0.0,
        "swim": round(total_tss, 1) if sport == "swim" else 0.0,
    }


def _build_day_summary(role: str, sport: str, total_tss: float) -> str:
    role_label = SESSION_ROLE_LABELS_RU.get(role, role)
    total_label = int(round(float(total_tss or 0.0)))
    if role == "off" or sport == "off" or total_tss <= 0:
        return f"{role_label} · {total_label} TSS"
    sport_label = SPORT_LABELS_RU.get(sport, sport)
    return f"{role_label} • {sport_label} · {total_label} TSS"


def build_near_term_edit_rows(
    goal_plan: Mapping[str, Any],
    horizon_days: int = EDITABLE_NEAR_TERM_HORIZON_MIN,
) -> List[Dict[str, Any]]:
    """Build UI-friendly rows for editing the next 7-10 days."""
    daily_plan = _clone_daily_plan(goal_plan)
    session_templates = _clone_session_templates(goal_plan, daily_plan)
    resolved_horizon = _normalize_horizon_days(horizon_days, len(daily_plan))
    rows: List[Dict[str, Any]] = []

    for idx in range(resolved_horizon):
        dt, total, parts = daily_plan[idx]
        template = session_templates[idx]
        sport = _normalize_sport(template.get("sport") or _dominant_sport(parts))
        role = _normalize_session_role(template.get("session_role") or ("off" if total <= 0 else "easy"))
        focus = str(template.get("session_focus") or _build_day_focus_label(role, sport))
        rows.append(
            {
                "index": idx,
                "date": dt,
                "date_label": f"{WEEKDAY_LABELS_RU[dt.weekday()]} {dt.strftime('%d.%m')}",
                "phase": str(template.get("phase", "Base") or "Base"),
                "current_total_tss": round(float(total or 0.0), 1),
                "current_sport": sport,
                "current_role": role,
                "current_focus": focus,
                "current_duration_minutes": int(template.get("duration_minutes", 0) or 0),
                "original_parts": dict(parts),
            }
        )

    return rows


def build_near_term_edit_draft_rows(
    editable_rows: Sequence[Mapping[str, Any]],
    goal_type: str,
    distance: str,
    overrides_by_index: Mapping[int, Mapping[str, Any]] | None = None,
) -> List[Dict[str, Any]]:
    """Build normalized draft rows for UI preview and later apply."""
    draft_rows: List[Dict[str, Any]] = []
    overrides = overrides_by_index or {}

    for raw_row in editable_rows:
        row = dict(raw_row)
        row_index = int(row.get("index", -1))
        override = dict(overrides.get(row_index, {}) or {})

        current_role = _normalize_session_role(row.get("current_role"))
        current_sport = _normalize_sport(row.get("current_sport"))
        current_total_tss = _normalize_total_tss(row.get("current_total_tss"))

        target_role = _normalize_session_role(override.get("session_role", current_role))
        target_sport = _normalize_sport(override.get("sport", current_sport))
        target_total_tss = _normalize_total_tss(override.get("total_tss", current_total_tss))

        if target_role == "off" or target_sport == "off":
            target_role = "off"
            target_sport = "off"
            target_total_tss = 0.0

        target_focus = _build_day_focus_label(target_role, target_sport)
        target_duration_minutes = _estimate_session_duration_minutes(
            target_total_tss,
            target_sport,
            target_role,
        )
        target_export_name = _build_session_export_name(goal_type, distance, target_focus)
        delta_tss = round(target_total_tss - current_total_tss, 1)
        changed = (
            current_role != target_role
            or current_sport != target_sport
            or current_total_tss != target_total_tss
        )

        draft_rows.append(
            {
                **row,
                "session_role": target_role,
                "sport": target_sport,
                "total_tss": target_total_tss,
                "target_focus": target_focus,
                "target_duration_minutes": target_duration_minutes,
                "target_export_name": target_export_name,
                "delta_tss": delta_tss,
                "changed": changed,
                "current_summary": _build_day_summary(
                    current_role,
                    current_sport,
                    current_total_tss,
                ),
                "target_summary": _build_day_summary(
                    target_role,
                    target_sport,
                    target_total_tss,
                ),
            }
        )

    return draft_rows


def summarize_near_term_draft_rows(
    draft_rows: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    """Summarize the current draft so the UI can show a compact diff preview."""
    normalized_rows = [dict(row or {}) for row in draft_rows]
    changed_rows = [row for row in normalized_rows if bool(row.get("changed", False))]
    current_total_tss = int(round(sum(_normalize_total_tss(row.get("current_total_tss")) for row in normalized_rows)))
    target_total_tss = int(round(sum(_normalize_total_tss(row.get("total_tss", row.get("current_total_tss"))) for row in normalized_rows)))
    off_day_count = sum(1 for row in normalized_rows if _normalize_session_role(row.get("session_role")) == "off")
    quality_day_count = sum(1 for row in normalized_rows if _normalize_session_role(row.get("session_role")) == "quality")

    return {
        "horizon_days": len(normalized_rows),
        "has_changes": bool(changed_rows),
        "changed_day_count": len(changed_rows),
        "current_total_tss": current_total_tss,
        "target_total_tss": target_total_tss,
        "total_delta_tss": target_total_tss - current_total_tss,
        "off_day_count": off_day_count,
        "quality_day_count": quality_day_count,
        "changed_rows": [
            {
                "День": str(row.get("date_label") or ""),
                "Было": str(row.get("current_summary") or ""),
                "Станет": str(row.get("target_summary") or ""),
                "Δ TSS": f"{int(round(float(row.get('delta_tss', 0.0) or 0.0))):+d}",
            }
            for row in changed_rows
        ],
    }


def _merge_adjustment_note(existing_note: Any, manual_note: str) -> str:
    parts = [
        str(part).strip()
        for part in str(existing_note or "—").split(";")
        if str(part).strip() and not str(part).strip().startswith("ручная правка:")
    ]
    if not parts or parts == ["—"]:
        return manual_note
    return "; ".join(parts + [manual_note])


def apply_near_term_day_edits(
    goal_plan: Mapping[str, Any],
    edited_rows: Sequence[Mapping[str, Any]],
    horizon_days: int = EDITABLE_NEAR_TERM_HORIZON_MIN,
) -> Dict[str, Any]:
    """Apply in-place daily edits to the next 7-10 days of an existing goal plan."""
    updated_goal_plan = dict(goal_plan)
    daily_plan = _clone_daily_plan(goal_plan)
    session_templates = _clone_session_templates(goal_plan, daily_plan)
    weekly_summary = [dict(row or {}) for row in list(goal_plan.get("weekly_summary", []) or [])]
    resolved_horizon = _normalize_horizon_days(horizon_days, len(daily_plan))
    goal_type = str(goal_plan.get("goal_type") or "")
    distance = str(goal_plan.get("distance") or "")

    original_horizon_total = round(sum(total for _dt, total, _parts in daily_plan[:resolved_horizon]), 1)
    changed_day_count = 0
    touched_week_stats: Dict[int, Dict[str, float]] = {}

    for raw_row in edited_rows:
        day_index = int(raw_row.get("index", -1))
        if day_index < 0 or day_index >= resolved_horizon:
            continue

        dt, current_total, current_parts = daily_plan[day_index]
        current_template = session_templates[day_index]
        current_role = _normalize_session_role(current_template.get("session_role") or ("off" if current_total <= 0 else "easy"))
        current_sport = _normalize_sport(current_template.get("sport") or _dominant_sport(current_parts))

        target_role = _normalize_session_role(raw_row.get("session_role"))
        target_sport = _normalize_sport(raw_row.get("sport"))
        target_total_tss = _normalize_total_tss(raw_row.get("total_tss"))
        if target_role == "off" or target_sport == "off":
            target_role = "off"
            target_sport = "off"
            target_total_tss = 0.0

        changed = (
            round(float(current_total or 0.0), 1) != target_total_tss
            or current_role != target_role
            or current_sport != target_sport
        )
        if changed:
            changed_day_count += 1

        if target_sport == current_sport and target_total_tss > 0 and current_sport != "off":
            new_parts = _scale_parts_to_total(current_parts, target_total_tss, current_sport)
        else:
            new_parts = _single_sport_parts(target_total_tss, target_sport)

        daily_plan[day_index] = (dt, target_total_tss, new_parts)

        phase = str(current_template.get("phase", weekly_summary[day_index // 7].get("phase", "Base") if day_index // 7 < len(weekly_summary) else "Base") or "Base")
        focus = _build_day_focus_label(target_role, target_sport)
        duration_minutes = _estimate_session_duration_minutes(target_total_tss, target_sport, target_role)
        export_name = _build_session_export_name(goal_type, distance, focus)
        description = _build_session_description(
            goal_type=goal_type,
            distance=distance,
            phase=phase,
            session_role=target_role,
            session_focus=focus,
            sport=target_sport,
            total_tss=target_total_tss,
            parts=new_parts,
            duration_minutes=duration_minutes,
        )
        session_templates[day_index] = {
            **current_template,
            "date": dt.strftime("%Y-%m-%d"),
            "week_index": day_index // 7,
            "day_index": day_index % 7,
            "phase": phase,
            "session_role": target_role,
            "session_focus": focus,
            "sport": target_sport,
            "sport_label": SPORT_LABELS_RU.get(target_sport, target_sport),
            "duration_minutes": duration_minutes,
            "template_key": f"manual:{phase.lower()}:{target_role}:{target_sport}",
            "export_name": export_name,
            "description": description,
        }

        week_index = day_index // 7
        week_stat = touched_week_stats.setdefault(week_index, {"delta_tss": 0.0, "edited_days": 0.0})
        week_stat["delta_tss"] += round(target_total_tss - float(current_total or 0.0), 1)
        week_stat["edited_days"] += 1.0

    refreshed_weekly_summary: List[Dict[str, Any]] = []
    for week_index, week_row in enumerate(weekly_summary):
        start = week_index * 7
        end = min(start + 7, len(daily_plan))
        week_days = daily_plan[start:end]
        week_templates = session_templates[start:end]
        roles = [_normalize_session_role(template.get("session_role")) for template in week_templates]
        focuses = [str(template.get("session_focus") or _build_day_focus_label(_normalize_session_role(template.get("session_role")), _normalize_sport(template.get("sport")))) for template in week_templates]
        structure_meta = _build_week_structure_metadata(roles, focuses)
        weekly_total = int(round(sum(total for _dt, total, _parts in week_days)))
        bike_total = round(sum(parts.get("bike", 0.0) for _dt, _total, parts in week_days), 1)
        run_total = round(sum(parts.get("run", 0.0) for _dt, _total, parts in week_days), 1)
        swim_total = round(sum(parts.get("swim", 0.0) for _dt, _total, parts in week_days), 1)

        refreshed_row = {
            **week_row,
            "weekly_tss": weekly_total,
            "bike": bike_total,
            "run": run_total,
            "swim": swim_total,
            **structure_meta,
        }

        if week_index in touched_week_stats:
            manual_note = (
                f"ручная правка: {int(touched_week_stats[week_index]['edited_days'])} дн., "
                f"Δ {int(round(touched_week_stats[week_index]['delta_tss'])):+d} TSS"
            )
            refreshed_row["adjustment_note"] = _merge_adjustment_note(
                refreshed_row.get("adjustment_note", "—"),
                manual_note,
            )

        refreshed_weekly_summary.append(refreshed_row)

    updated_weekly_tss_plan = [int(row.get("weekly_tss", 0) or 0) for row in refreshed_weekly_summary]
    new_horizon_total = round(sum(total for _dt, total, _parts in daily_plan[:resolved_horizon]), 1)
    horizon_delta = int(round(new_horizon_total - original_horizon_total))

    constraint_summary = dict(goal_plan.get("constraint_summary", {}) or {})
    existing_notes = [
        str(note)
        for note in constraint_summary.get("notes", [])
        if note and not str(note).startswith("Ручная правка ближнего горизонта:")
    ]
    manual_note = (
        f"Ручная правка ближнего горизонта: {changed_day_count} дн. "
        f"в ближайших {resolved_horizon} дн., Δ {horizon_delta:+d} TSS."
    )
    constraint_summary["notes"] = existing_notes + [manual_note]
    constraint_summary["near_term_edit"] = {
        "is_active": changed_day_count > 0,
        "edited_day_count": changed_day_count,
        "horizon_days": resolved_horizon,
        "total_delta_tss": horizon_delta,
        "label": "Ручная правка ближнего горизонта",
    }

    updated_goal_plan["daily_plan"] = daily_plan
    updated_goal_plan["session_templates"] = session_templates
    updated_goal_plan["weekly_summary"] = refreshed_weekly_summary
    updated_goal_plan["weekly_tss_plan"] = updated_weekly_tss_plan
    updated_goal_plan["constraint_summary"] = constraint_summary
    updated_goal_plan["near_term_edit_version"] = int(goal_plan.get("near_term_edit_version", 0) or 0) + 1
    updated_goal_plan["near_term_edit_horizon_days"] = resolved_horizon

    if "plan_revision" not in updated_goal_plan:
        updated_goal_plan["plan_revision"] = datetime.now().isoformat()

    return updated_goal_plan


__all__ = [
    "EDITABLE_NEAR_TERM_HORIZON_MAX",
    "EDITABLE_NEAR_TERM_HORIZON_MIN",
    "EDITABLE_SESSION_ROLES",
    "EDITABLE_SPORTS",
    "build_near_term_edit_draft_rows",
    "build_near_term_edit_rows",
    "apply_near_term_day_edits",
    "summarize_near_term_draft_rows",
]
