"""Helpers for editing the near-term daily plan without rebuilding the whole cycle."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from math import ceil
from typing import Any, Dict, List, Mapping, Sequence

from models.planning_summary import (
    NEAR_TERM_EDIT_POST_STRATEGY_LABELS_RU,
    normalize_near_term_edit_post_strategy,
    summarize_near_term_edit,
)
from models.session_identity import ensure_session_identities
from models.workout_catalog import (
    extract_zone_snapshot,
    planned_session_requires_repair,
    rescale_materialized_session,
)
from models.training_planner import (
    SESSION_ROLE_LABELS_RU,
    SPORT_LABELS_RU,
    WEEKDAY_LABELS_RU,
    materialize_day_sessions,
    project_day_scalars,
    _build_day_focus_label,
    _build_session_description,
    _build_session_export_name,
    _build_week_structure_metadata,
    _dominant_sport,
    _estimate_session_duration_minutes,
    _round_to_5,
)

EDITABLE_NEAR_TERM_HORIZON_MIN = 7
EDITABLE_NEAR_TERM_HORIZON_MAX = 10
EDITABLE_SESSION_ROLES = ["off", "recovery", "easy", "activation", "quality", "long"]
EDITABLE_SPORTS = ["run", "bike", "swim", "brick", "off"]
RISK_LEVEL_RANK = {"low": 0, "medium": 1, "high": 2}


def _normalize_post_edit_strategy(value: Any) -> str:
    return normalize_near_term_edit_post_strategy(value)


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


def _normalize_duration_minutes(value: Any) -> int:
    try:
        return max(0, int(round(float(value or 0.0))))
    except (TypeError, ValueError):
        return 0


def _format_duration_delta(target_minutes: int, current_minutes: int) -> str:
    delta = target_minutes - current_minutes
    if delta == 0:
        return "0 мин"
    return f"{delta:+d} мин"


def _normalize_metric_or_none(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _normalize_horizon_days(
    horizon_days: int | None,
    daily_count: int,
    max_horizon_days: int = EDITABLE_NEAR_TERM_HORIZON_MAX,
) -> int:
    if daily_count <= 0:
        return 0
    raw = int(horizon_days or EDITABLE_NEAR_TERM_HORIZON_MIN)
    resolved_max = max(EDITABLE_NEAR_TERM_HORIZON_MIN, int(max_horizon_days))
    raw = max(EDITABLE_NEAR_TERM_HORIZON_MIN, min(resolved_max, raw))
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


def _append_adjustment_note(
    existing_note: Any,
    extra_note: str,
    removable_prefixes: Sequence[str] | None = None,
) -> str:
    removable = tuple(removable_prefixes or ())
    parts = [
        str(part).strip()
        for part in str(existing_note or "—").split(";")
        if (
            str(part).strip()
            and str(part).strip() != "—"
            and not any(str(part).strip().startswith(prefix) for prefix in removable)
        )
    ]
    if extra_note not in parts:
        parts.append(extra_note)
    return "; ".join(parts) if parts else extra_note


def _resolve_post_edit_target_delta(
    strategy: str,
    horizon_delta: int,
    constraint_summary: Mapping[str, Any],
) -> int:
    if horizon_delta == 0 or strategy == "keep":
        return 0

    load_state = str(constraint_summary.get("load_state", "balanced") or "balanced").lower()
    current_tsb = constraint_summary.get("current_tsb")
    try:
        current_tsb = float(current_tsb) if current_tsb is not None else None
    except (TypeError, ValueError):
        current_tsb = None

    if horizon_delta < 0:
        if strategy == "protect_recovery":
            return 0
        share = 0.50
        if current_tsb is not None and current_tsb <= -15:
            share = min(share, 0.30)
        if load_state == "deep_fatigue":
            share = min(share, 0.25)
        elif load_state == "fatigued":
            share = min(share, 0.35)
        elif load_state == "fresh":
            share = max(share, 0.55)
        return _round_to_5(abs(horizon_delta) * share)

    if strategy == "catch_up":
        share = 0.35
        if current_tsb is not None and current_tsb <= -15:
            share = max(share, 0.45)
        if load_state == "deep_fatigue":
            share = max(share, 0.70)
        elif load_state == "fatigued":
            share = max(share, 0.55)
    else:
        share = 0.60
        if current_tsb is not None and current_tsb <= -15:
            share = max(share, 0.75)
        if load_state == "deep_fatigue":
            share = max(share, 0.80)
        elif load_state == "fatigued":
            share = max(share, 0.65)
    return -_round_to_5(abs(horizon_delta) * share)


def _evaluate_near_term_edit_risk(
    *,
    original_horizon_total: float,
    new_horizon_total: float,
    resolved_horizon: int,
    original_roles: Sequence[str],
    updated_roles: Sequence[str],
    current_tsb: float | None,
    load_state: str,
    load_state_label: str,
    future_delta_tss: int,
    post_edit_strategy: str,
    max_added_day_tss: float,
    max_removed_day_tss: float,
) -> Dict[str, Any]:
    total_delta_tss = int(round(new_horizon_total - original_horizon_total))
    current_off_days = sum(1 for role in original_roles if role == "off")
    updated_off_days = sum(1 for role in updated_roles if role == "off")
    current_quality_days = sum(1 for role in original_roles if role == "quality")
    updated_quality_days = sum(1 for role in updated_roles if role == "quality")
    removed_off_days = max(0, current_off_days - updated_off_days)
    added_quality_days = max(0, updated_quality_days - current_quality_days)
    removed_quality_days = max(0, current_quality_days - updated_quality_days)
    delta_share = abs(float(total_delta_tss)) / max(float(original_horizon_total or 0.0), 1.0)

    focus = "balanced"
    score = 0
    reasons: List[str] = []

    tired_state = load_state in {"fatigued", "deep_fatigue"} or (
        current_tsb is not None and current_tsb <= -10
    )
    deeply_tired = load_state == "deep_fatigue" or (
        current_tsb is not None and current_tsb <= -20
    )

    if total_delta_tss > 0 or (total_delta_tss == 0 and (removed_off_days > 0 or added_quality_days > 0)):
        focus = "overload"
        if total_delta_tss > 0:
            reasons.append(f"в ближайшие {resolved_horizon} дн. добавлено {total_delta_tss:+d} TSS")
            if total_delta_tss >= 25 or delta_share >= 0.12:
                score += 1
            if total_delta_tss >= 40 or delta_share >= 0.18:
                score += 1
        if removed_off_days > 0:
            reasons.append("убран день полного отдыха")
            score += 1
        if added_quality_days > 0:
            reasons.append("в окне стало больше качественных дней")
            score += 1
        if max_added_day_tss >= 25:
            reasons.append(f"один из дней вырос сразу на +{int(round(max_added_day_tss))} TSS")
            score += 1
        if deeply_tired:
            reasons.append(f"стартовое состояние уже «{load_state_label or 'Глубокая усталость'}»")
            score += 2
        elif tired_state:
            reasons.append(f"стартовое состояние уже «{load_state_label or 'Накопленная усталость'}»")
            score += 1
        if post_edit_strategy == "keep" and future_delta_tss == 0 and total_delta_tss > 0:
            reasons.append("добавленный объём остаётся локально без разгрузки следующих недель")
            score += 1
        elif (
            future_delta_tss < 0
            and score > 0
            and total_delta_tss < 35
            and removed_off_days == 0
            and added_quality_days == 0
        ):
            score -= 1
        guardrail = "Верните часть TSS или оставьте один явный лёгкий день, если утреннее самочувствие уже просело."
    elif total_delta_tss < 0 or removed_quality_days > 0:
        if tired_state:
            reasons.append("правка разгружает уже уставшее окно")
            focus = "balanced"
            if future_delta_tss > 0 and abs(future_delta_tss) >= max(15, int(round(abs(total_delta_tss) * 0.6))):
                focus = "overload"
                reasons.append("большая часть снятого объёма быстро возвращается в следующих неделях")
                score += 2
            guardrail = "Сохраняйте разгрузку, пока не увидите нормализацию самочувствия, а возврат объёма делайте ступенчато."
        else:
            focus = "underload"
            reasons.append(f"из ближайших {resolved_horizon} дн. снято {total_delta_tss:+d} TSS")
            if abs(total_delta_tss) >= 25 or delta_share >= 0.12:
                score += 1
            if abs(total_delta_tss) >= 45 or delta_share >= 0.20:
                score += 1
            if removed_quality_days > 0 and updated_quality_days == 0:
                reasons.append("из окна ушёл весь качественный стимул")
                score += 1
            if abs(max_removed_day_tss) >= 25:
                reasons.append(f"один из дней стал легче сразу на {int(round(abs(max_removed_day_tss)))} TSS")
                score += 1
            if post_edit_strategy == "keep" and future_delta_tss == 0:
                reasons.append("снятый объём не планируется вернуть в безопасном окне")
                score += 1
            elif future_delta_tss > 0 and score > 0:
                recovered_share = abs(float(future_delta_tss)) / max(abs(float(total_delta_tss)), 1.0)
                score -= 2 if recovered_share >= 0.35 else 1
                score = max(0, score)
            guardrail = "Если это не вынужденная разгрузка, верните хотя бы один качественный стимул позже в безопасном окне."
    else:
        if added_quality_days > 0 and tired_state:
            focus = "overload"
            score = 2
            reasons = [
                "структура окна стала жёстче без прироста общего TSS",
                f"стартовое состояние уже «{load_state_label or 'Накопленная усталость'}»",
            ]
            guardrail = "Не ставьте второй жёсткий стимул подряд, пока самочувствие не стабилизировалось."
        elif removed_quality_days > 0:
            focus = "underload"
            score = 1
            reasons = ["качественный стимул убран, хотя общий объём почти не изменился"]
            guardrail = "Проверьте, что в окне остаётся хотя бы один ключевой стимул под цель недели."
        else:
            guardrail = "После применения просто сверяйте самочувствие и не компенсируйте следующий день автоматически."

    level = "low"
    if score >= 4:
        level = "high"
    elif score >= 2:
        level = "medium"

    return {
        "risk_level": level,
        "risk_focus": focus,
        "risk_reasons": reasons,
        "risk_guardrail": guardrail,
    }


def _sessions_from_parts(
    parts: Mapping[str, float],
    role: str,
    phase: str,
    goal_type: str,
    distance: str,
    *,
    zone_snapshot: Mapping[str, Any],
    load_state: str,
    recent_template_keys: List[str],
) -> List[Dict[str, Any]]:
    """Rebuild an edited day through the canonical workout materializer."""
    total = round(
        sum(float(parts.get(sport, 0.0) or 0.0) for sport in ("bike", "run", "swim")),
        1,
    )
    if total <= 0:
        return []
    primary_sport = _dominant_sport(parts)
    sessions, _allocated, _meta = materialize_day_sessions(
        parts=parts,
        total=total,
        is_brick=False,
        phase=phase,
        session_role=role,
        day_focus=_build_day_focus_label(role, primary_sport),
        goal_type=goal_type,
        distance=distance,
        zone_snapshot=zone_snapshot,
        load_state=load_state,
        recent_template_keys=recent_template_keys,
    )
    if any(planned_session_requires_repair(session) for session in sessions):
        raise ValueError("edited session has no feasible catalog prescription")
    return sessions


def _recent_template_keys_before(
    session_templates: Sequence[Mapping[str, Any]],
    day_index: int,
) -> List[str]:
    keys: List[str] = []
    for template in session_templates[:day_index]:
        sessions = list(template.get("sessions") or [])
        candidates = sessions or [template]
        for session in candidates:
            if session.get("materialization_status") != "materialized":
                continue
            key = str(session.get("template_key") or "").strip()
            if key:
                keys.append(key)
    return keys


def _rebuild_sessions_after_day_edit(
    next_template: Dict[str, Any],
    current_template: Mapping[str, Any],
    *,
    new_parts: Mapping[str, float],
    role: str,
    sport: str,
    phase: str,
    goal_type: str,
    distance: str,
    zone_snapshot: Mapping[str, Any],
    load_state: str,
    recent_template_keys: List[str],
) -> Dict[str, Any]:
    """Issue #205: an edited day's `sessions` must follow the edit, never stay stale.

    Every previously planned session id is recorded in `replaced_session_ids` —
    a day edit never drops a session silently. Composite (brick) days keep the
    template as the single session via migrate-on-read; other training days get
    sessions rebuilt from the edited parts; off days carry none."""
    replaced = [
        str(session.get("session_id") or "")
        for session in list(current_template.get("sessions") or [])
        if session.get("session_id")
    ]
    for stale_key in ("sessions", "allocated_parts", "brick_status", "brick_status_reason"):
        next_template.pop(stale_key, None)
    if replaced:
        next_template["replaced_session_ids"] = replaced
    is_composite = str(next_template.get("kind") or "") == "composite"
    if not is_composite and role != "off" and sport != "off":
        rebuilt = _sessions_from_parts(
            new_parts,
            role,
            phase,
            goal_type,
            distance,
            zone_snapshot=zone_snapshot,
            load_state=load_state,
            recent_template_keys=recent_template_keys,
        )
        if rebuilt:
            next_template["sessions"] = rebuilt
            # #232: top-level scalars follow the rebuilt primary — the day never
            # keeps the previous catalog session's name/fatigue/recovery/steps.
            project_day_scalars(next_template)
    return next_template


def _apply_week_total_delta(
    daily_plan: List[tuple[datetime, float, Dict[str, float]]],
    session_templates: List[Dict[str, Any]],
    week_index: int,
    week_delta: int,
    goal_type: str,
    distance: str,
    *,
    zone_snapshot: Mapping[str, Any],
    load_state: str,
) -> float:
    start = week_index * 7
    end = min(start + 7, len(daily_plan))
    week_slice = daily_plan[start:end]
    current_week_total = round(sum(total for _dt, total, _parts in week_slice), 1)
    target_week_total = round(max(0.0, current_week_total + float(week_delta)), 1)
    if current_week_total <= 0 or abs(target_week_total - current_week_total) < 0.1:
        return 0.0

    factor = target_week_total / current_week_total
    updated_totals: List[float] = []
    for _dt, total, _parts in week_slice:
        updated_totals.append(round(float(total or 0.0) * factor, 1))

    rounded_total = round(sum(updated_totals), 1)
    diff = round(target_week_total - rounded_total, 1)
    if abs(diff) >= 0.1:
        candidate_indices = [
            idx
            for idx, value in enumerate(updated_totals)
            if value > 0 or week_slice[idx][1] > 0
        ]
        if candidate_indices:
            preferred_idx = max(candidate_indices, key=lambda idx: week_slice[idx][1])
            updated_totals[preferred_idx] = round(max(0.0, updated_totals[preferred_idx] + diff), 1)

    actual_week_total = 0.0
    for offset, day_total in enumerate(updated_totals):
        day_index = start + offset
        dt, current_total, current_parts = daily_plan[day_index]
        current_template = session_templates[day_index]
        sport = _normalize_sport(current_template.get("sport") or _dominant_sport(current_parts))
        role = _normalize_session_role(
            current_template.get("session_role") or ("off" if current_total <= 0 else "easy")
        )

        if day_total <= 0:
            day_total = 0.0
            if sport == "off" or current_total <= 0:
                role = "off"
                sport = "off"

        if day_total > 0 and sport != "off":
            new_parts = _scale_parts_to_total(current_parts, day_total, sport)
        else:
            new_parts = _single_sport_parts(day_total, sport)

        focus = str(current_template.get("session_focus") or _build_day_focus_label(role, sport))
        duration_minutes = _estimate_session_duration_minutes(day_total, sport, role)
        description = _build_session_description(
            goal_type=goal_type,
            distance=distance,
            phase=str(current_template.get("phase", "Base") or "Base"),
            session_role=role,
            session_focus=focus,
            sport=sport,
            total_tss=day_total,
            parts=new_parts,
            duration_minutes=duration_minutes,
        )
        daily_plan[day_index] = (dt, day_total, new_parts)
        next_template = {
            **current_template,
            "date": dt.strftime("%Y-%m-%d"),
            "week_index": day_index // 7,
            "day_index": day_index % 7,
            "sport": sport,
            "sport_label": SPORT_LABELS_RU.get(sport, sport),
            "session_role": role,
            "session_focus": focus,
            "duration_minutes": duration_minutes,
            "description": description,
        }
        is_composite = (
            str(current_template.get("kind") or "") == "composite"
            and day_total > 0
        )
        if is_composite:
            current_sessions = list(current_template.get("sessions") or [])
            composite = (
                dict(current_sessions[0] or {})
                if current_sessions
                else dict(current_template)
            )
            rescaled = rescale_materialized_session(
                composite,
                target_tss=day_total,
                parts=new_parts,
            )
            rescaled.update(
                {
                    "session_role": role,
                    "session_focus": focus,
                    "sport": "brick",
                    "sport_label": SPORT_LABELS_RU["brick"],
                    "total_tss": day_total,
                    "description": description,
                }
            )
            next_template["sessions"] = [rescaled]
            project_day_scalars(next_template)
        else:
            next_template = _rebuild_sessions_after_day_edit(
                next_template,
                current_template,
                new_parts=new_parts,
                role=role,
                sport=sport,
                phase=str(current_template.get("phase", "Base") or "Base"),
                goal_type=goal_type,
                distance=distance,
                zone_snapshot=zone_snapshot,
                load_state=load_state,
                recent_template_keys=_recent_template_keys_before(
                    session_templates,
                    day_index,
                ),
            )
        session_templates[day_index] = next_template
        actual_week_total += day_total

    return round(actual_week_total - current_week_total, 1)


def build_near_term_edit_rows(
    goal_plan: Mapping[str, Any],
    horizon_days: int = EDITABLE_NEAR_TERM_HORIZON_MIN,
    max_horizon_days: int = EDITABLE_NEAR_TERM_HORIZON_MAX,
) -> List[Dict[str, Any]]:
    """Build UI-friendly rows for editing the next 7-10 days."""
    daily_plan = _clone_daily_plan(goal_plan)
    session_templates = _clone_session_templates(goal_plan, daily_plan)
    resolved_horizon = _normalize_horizon_days(
        horizon_days,
        len(daily_plan),
        max_horizon_days=max_horizon_days,
    )
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
                "current_kind": str(template.get("kind") or "single"),
                "current_role": role,
                "current_focus": focus,
                "current_duration_minutes": int(template.get("duration_minutes", 0) or 0),
                "original_parts": dict(parts),
                # Issue #205: expose the day's executable sessions so an edit can
                # address one specific session_id instead of the whole day.
                "sessions": [
                    {
                        "session_id": str(session.get("session_id") or ""),
                        "sport": _normalize_sport(session.get("sport") or "off"),
                        "session_role": _normalize_session_role(session.get("session_role") or "easy"),
                        "session_focus": str(session.get("session_focus") or "—"),
                        "total_tss": round(float(session.get("total_tss") or 0.0), 1),
                        "duration_minutes": int(session.get("duration_minutes") or 0),
                        "kind": str(session.get("kind") or "single"),
                    }
                    for session in list(template.get("sessions") or [])
                ],
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
        if (
            target_sport == "brick"
            and str(row.get("current_kind") or "single") != "composite"
        ):
            target_sport = current_sport
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
    current_total_duration_minutes = sum(
        _normalize_duration_minutes(row.get("current_duration_minutes"))
        for row in normalized_rows
    )
    target_total_duration_minutes = sum(
        _normalize_duration_minutes(row.get("target_duration_minutes"))
        for row in normalized_rows
    )
    off_day_count = sum(1 for row in normalized_rows if _normalize_session_role(row.get("session_role")) == "off")
    quality_day_count = sum(1 for row in normalized_rows if _normalize_session_role(row.get("session_role")) == "quality")

    return {
        "horizon_days": len(normalized_rows),
        "has_changes": bool(changed_rows),
        "changed_day_count": len(changed_rows),
        "current_total_tss": current_total_tss,
        "target_total_tss": target_total_tss,
        "total_delta_tss": target_total_tss - current_total_tss,
        "current_total_duration_minutes": current_total_duration_minutes,
        "target_total_duration_minutes": target_total_duration_minutes,
        "total_delta_duration_minutes": target_total_duration_minutes - current_total_duration_minutes,
        "off_day_count": off_day_count,
        "quality_day_count": quality_day_count,
        "changed_rows": [
            {
                "День": str(row.get("date_label") or ""),
                "Было": str(row.get("current_summary") or ""),
                "Станет": str(row.get("target_summary") or ""),
                "Δ TSS": f"{int(round(float(row.get('delta_tss', 0.0) or 0.0))):+d}",
                "Δ мин": _format_duration_delta(
                    _normalize_duration_minutes(row.get("target_duration_minutes")),
                    _normalize_duration_minutes(row.get("current_duration_minutes")),
                ),
            }
            for row in changed_rows
        ],
    }


def build_near_term_edit_seed_from_goal_plans(
    goal_plan: Mapping[str, Any],
    target_goal_plan: Mapping[str, Any],
    *,
    horizon_days: int = EDITABLE_NEAR_TERM_HORIZON_MIN,
    post_edit_strategy: str = "keep",
    source_label: str | None = None,
) -> Dict[str, Any] | None:
    """Project a target plan variant into a near-term editable draft over the current plan."""
    base_rows = build_near_term_edit_rows(goal_plan, horizon_days=horizon_days)
    if not base_rows:
        return None

    target_daily_plan = _clone_daily_plan(target_goal_plan)
    if not target_daily_plan:
        return None

    target_templates = _clone_session_templates(target_goal_plan, target_daily_plan)
    resolved_horizon = min(len(base_rows), len(target_daily_plan), len(target_templates))
    if resolved_horizon <= 0:
        return None

    overrides_by_index: Dict[int, Dict[str, Any]] = {}
    for idx in range(resolved_horizon):
        _target_dt, target_total_tss, target_parts = target_daily_plan[idx]
        target_template = target_templates[idx]
        normalized_total_tss = _normalize_total_tss(target_total_tss)
        target_sport = _normalize_sport(
            target_template.get("sport") or _dominant_sport(target_parts)
        )
        target_role = _normalize_session_role(
            target_template.get("session_role") or ("off" if normalized_total_tss <= 0 else "easy")
        )
        if target_role == "off" or target_sport == "off" or normalized_total_tss <= 0:
            target_role = "off"
            target_sport = "off"
            normalized_total_tss = 0.0
        overrides_by_index[idx] = {
            "session_role": target_role,
            "sport": target_sport,
            "total_tss": normalized_total_tss,
        }

    draft_rows = build_near_term_edit_draft_rows(
        base_rows[:resolved_horizon],
        goal_type=str(goal_plan.get("goal_type") or ""),
        distance=str(goal_plan.get("distance") or ""),
        overrides_by_index=overrides_by_index,
    )
    draft_summary = summarize_near_term_draft_rows(draft_rows)
    if not draft_summary["has_changes"]:
        return None

    return {
        "source_label": str(source_label or "").strip(),
        "horizon_days": resolved_horizon,
        "post_edit_strategy": _normalize_post_edit_strategy(post_edit_strategy),
        "draft_rows": draft_rows,
        "draft_summary": draft_summary,
        "overrides_by_index": _draft_rows_to_overrides_by_index(draft_rows),
    }


def _draft_rows_to_overrides_by_index(
    draft_rows: Sequence[Mapping[str, Any]],
) -> Dict[int, Dict[str, Any]]:
    return {
        int(row.get("index", -1)): {
            "session_role": _normalize_session_role(row.get("session_role")),
            "sport": _normalize_sport(row.get("sport")),
            "total_tss": _normalize_total_tss(row.get("total_tss", row.get("current_total_tss"))),
        }
        for row in draft_rows
        if int(row.get("index", -1)) >= 0
    }


def _rebuild_draft_rows(
    base_rows: Sequence[Mapping[str, Any]],
    goal_plan: Mapping[str, Any],
    overrides_by_index: Mapping[int, Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    return build_near_term_edit_draft_rows(
        base_rows,
        goal_type=str(goal_plan.get("goal_type") or ""),
        distance=str(goal_plan.get("distance") or ""),
        overrides_by_index=overrides_by_index,
    )


def _apply_draft_and_summarize(
    goal_plan: Mapping[str, Any],
    draft_rows: Sequence[Mapping[str, Any]],
    horizon_days: int,
    post_edit_strategy: str,
) -> tuple[Dict[str, Any], Dict[str, Any] | None]:
    updated_goal_plan = apply_near_term_day_edits(
        goal_plan,
        draft_rows,
        horizon_days=horizon_days,
        post_edit_strategy=post_edit_strategy,
    )
    near_term_edit = summarize_near_term_edit(updated_goal_plan.get("constraint_summary", {}))
    return updated_goal_plan, near_term_edit


def _risk_rank(summary: Mapping[str, Any] | None) -> int:
    if not isinstance(summary, Mapping):
        return -1
    return RISK_LEVEL_RANK.get(str(summary.get("risk_level") or "low"), -1)


def _is_safer_near_term_summary(
    candidate: Mapping[str, Any] | None,
    baseline: Mapping[str, Any] | None,
) -> bool:
    candidate_rank = _risk_rank(candidate)
    baseline_rank = _risk_rank(baseline)
    if candidate_rank < 0:
        return False
    if baseline_rank < 0:
        return True
    if candidate_rank != baseline_rank:
        return candidate_rank < baseline_rank

    candidate_penalty = abs(int(candidate.get("total_delta_tss", 0) or 0)) + abs(int(candidate.get("future_delta_tss", 0) or 0))
    baseline_penalty = abs(int(baseline.get("total_delta_tss", 0) or 0)) + abs(int(baseline.get("future_delta_tss", 0) or 0))
    return candidate_penalty < baseline_penalty


def _pick_overload_softening_override(
    draft_rows: Sequence[Mapping[str, Any]],
) -> tuple[int, Dict[str, Any], str] | None:
    removed_rest_candidates = [
        row
        for row in draft_rows
        if _normalize_session_role(row.get("current_role")) == "off"
        and _normalize_session_role(row.get("session_role")) != "off"
    ]
    if removed_rest_candidates:
        row = max(removed_rest_candidates, key=lambda item: float(item.get("delta_tss", 0.0) or 0.0))
        return (
            int(row["index"]),
            {
                "session_role": row["current_role"],
                "sport": row["current_sport"],
                "total_tss": row["current_total_tss"],
            },
            f"вернуть исходный отдых {row['date_label']}",
        )

    added_quality_candidates = [
        row
        for row in draft_rows
        if _normalize_session_role(row.get("session_role")) == "quality"
        and _normalize_session_role(row.get("current_role")) != "quality"
    ]
    if added_quality_candidates:
        row = max(added_quality_candidates, key=lambda item: float(item.get("delta_tss", 0.0) or 0.0))
        return (
            int(row["index"]),
            {
                "session_role": row["current_role"],
                "sport": row["current_sport"],
                "total_tss": row["current_total_tss"],
            },
            f"убрать лишний качественный стимул {row['date_label']}",
        )

    positive_delta_candidates = [
        row
        for row in draft_rows
        if float(row.get("delta_tss", 0.0) or 0.0) > 0
    ]
    if not positive_delta_candidates:
        return None

    row = max(positive_delta_candidates, key=lambda item: float(item.get("delta_tss", 0.0) or 0.0))
    current_total = _normalize_total_tss(row.get("current_total_tss"))
    target_total = _normalize_total_tss(row.get("total_tss"))
    reduction = max(10.0, float(_round_to_5(max(10.0, (target_total - current_total) / 2.0))))
    new_total = round(max(current_total, target_total - reduction), 1)
    new_role = _normalize_session_role(row.get("session_role"))
    if new_role == "quality" and new_total <= current_total + 5:
        new_role = _normalize_session_role(row.get("current_role"))
    return (
        int(row["index"]),
        {
            "session_role": new_role,
            "sport": row["sport"],
            "total_tss": new_total,
        },
        f"снизить нагрузку {row['date_label']} на {int(round(target_total - new_total))} TSS",
    )


def _pick_underload_softening_override(
    draft_rows: Sequence[Mapping[str, Any]],
) -> tuple[int, Dict[str, Any], str] | None:
    removed_quality_candidates = [
        row
        for row in draft_rows
        if _normalize_session_role(row.get("current_role")) == "quality"
        and _normalize_session_role(row.get("session_role")) != "quality"
    ]
    if removed_quality_candidates:
        row = max(
            removed_quality_candidates,
            key=lambda item: abs(float(item.get("delta_tss", 0.0) or 0.0)),
        )
        return (
            int(row["index"]),
            {
                "session_role": row["current_role"],
                "sport": row["current_sport"],
                "total_tss": row["current_total_tss"],
            },
            f"вернуть ключевой стимул {row['date_label']}",
        )

    removed_load_candidates = [
        row
        for row in draft_rows
        if float(row.get("delta_tss", 0.0) or 0.0) < 0
    ]
    if not removed_load_candidates:
        return None

    row = min(removed_load_candidates, key=lambda item: float(item.get("delta_tss", 0.0) or 0.0))
    current_total = _normalize_total_tss(row.get("current_total_tss"))
    target_total = _normalize_total_tss(row.get("total_tss"))
    increase = max(10.0, float(_round_to_5(max(10.0, (current_total - target_total) / 2.0))))
    new_total = round(min(current_total, target_total + increase), 1)
    new_role = _normalize_session_role(row.get("session_role"))
    if _normalize_session_role(row.get("current_role")) in {"quality", "long"} and new_total >= current_total - 5:
        new_role = _normalize_session_role(row.get("current_role"))
    return (
        int(row["index"]),
        {
            "session_role": new_role,
            "sport": row["sport"] if _normalize_sport(row.get("sport")) != "off" else row["current_sport"],
            "total_tss": new_total,
        },
        f"вернуть часть нагрузки в {row['date_label']} (+{int(round(new_total - target_total))} TSS)",
    )


def build_safer_near_term_draft(
    goal_plan: Mapping[str, Any],
    draft_rows: Sequence[Mapping[str, Any]],
    horizon_days: int = EDITABLE_NEAR_TERM_HORIZON_MIN,
    post_edit_strategy: str = "keep",
) -> Dict[str, Any] | None:
    """Suggest a safer one-click variant for a risky near-term draft."""
    base_rows = [dict(row or {}) for row in draft_rows]
    if not base_rows:
        return None

    normalized_strategy = _normalize_post_edit_strategy(post_edit_strategy)
    _, baseline_summary = _apply_draft_and_summarize(
        goal_plan,
        base_rows,
        horizon_days,
        normalized_strategy,
    )
    if not isinstance(baseline_summary, dict) or _risk_rank(baseline_summary) <= RISK_LEVEL_RANK["low"]:
        return None

    working_rows = base_rows
    working_strategy = normalized_strategy
    best_rows = working_rows
    best_strategy = working_strategy
    best_summary = baseline_summary
    best_actions: List[str] = []
    accumulated_actions: List[str] = []

    for _ in range(5):
        risk_focus = str(best_summary.get("risk_focus") or "balanced")
        total_delta_tss = int(best_summary.get("total_delta_tss", 0) or 0)
        changed = False

        if risk_focus == "overload" or total_delta_tss > 0:
            if working_strategy == "keep":
                working_strategy = "protect_recovery"
                accumulated_actions.append("переключить стратегию после окна на «Беречь восстановление»")
                changed = True
            else:
                overload_override = _pick_overload_softening_override(working_rows)
                if overload_override is not None:
                    row_index, override, action = overload_override
                    overrides_by_index = _draft_rows_to_overrides_by_index(working_rows)
                    if overrides_by_index.get(row_index) != override:
                        overrides_by_index[row_index] = override
                        working_rows = _rebuild_draft_rows(base_rows, goal_plan, overrides_by_index)
                        accumulated_actions.append(action)
                        changed = True
        else:
            if working_strategy == "keep":
                working_strategy = "catch_up"
                accumulated_actions.append("переключить стратегию после окна на «Наверстать аккуратно»")
                changed = True
            else:
                underload_override = _pick_underload_softening_override(working_rows)
                if underload_override is not None:
                    row_index, override, action = underload_override
                    overrides_by_index = _draft_rows_to_overrides_by_index(working_rows)
                    if overrides_by_index.get(row_index) != override:
                        overrides_by_index[row_index] = override
                        working_rows = _rebuild_draft_rows(base_rows, goal_plan, overrides_by_index)
                        accumulated_actions.append(action)
                        changed = True

        if not changed:
            break

        _, candidate_summary = _apply_draft_and_summarize(
            goal_plan,
            working_rows,
            horizon_days,
            working_strategy,
        )
        if _is_safer_near_term_summary(candidate_summary, best_summary):
            best_rows = working_rows
            best_strategy = working_strategy
            best_summary = candidate_summary
            best_actions = list(accumulated_actions)
            if _risk_rank(best_summary) <= RISK_LEVEL_RANK["low"]:
                break

    if not _is_safer_near_term_summary(best_summary, baseline_summary):
        return None

    return {
        "draft_rows": best_rows,
        "draft_summary": summarize_near_term_draft_rows(best_rows),
        "post_edit_strategy": best_strategy,
        "near_term_edit": best_summary,
        "actions": best_actions,
        "description": "; ".join(best_actions[:3]),
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


def _session_parts_contribution(session: Mapping[str, Any]) -> Dict[str, float]:
    """Per-discipline TSS one session contributes to its day (brick → legs)."""
    if str(session.get("kind") or "") == "composite":
        contribution: Dict[str, float] = {}
        for leg in list(session.get("legs") or []):
            sport = str(leg.get("sport") or "")
            contribution[sport] = round(
                contribution.get(sport, 0.0) + float(leg.get("target_tss") or 0.0), 1
            )
        return contribution
    sport = str(session.get("sport") or "")
    if sport in {"", "off", "race"}:
        return {}
    return {sport: round(float(session.get("total_tss") or 0.0), 1)}


def _apply_targeted_session_edit(
    day_sessions: List[Dict[str, Any]],
    position: int,
    raw_row: Mapping[str, Any],
    *,
    phase: str,
    goal_type: str,
    distance: str,
    zone_snapshot: Mapping[str, Any],
    load_state: str,
    recent_template_keys: List[str],
):
    """Issue #205: edit exactly one session inside a day, preserving the rest.

    Returns ``(sessions, new_day_total, new_day_parts)`` or ``None`` when the
    row changes nothing. Setting the session to off/zero removes it from the
    day; the other sessions and the day totals follow."""
    current = day_sessions[position]
    current_role = _normalize_session_role(current.get("session_role") or "easy")
    current_sport = _normalize_sport(current.get("sport") or "off")
    current_tss = round(float(current.get("total_tss") or 0.0), 1)

    target_role = _normalize_session_role(raw_row.get("session_role") or current_role)
    target_sport = _normalize_sport(raw_row.get("sport") or current_sport)
    if target_sport == "brick" and str(current.get("kind") or "") != "composite":
        target_sport = current_sport
    target_tss = (
        _normalize_total_tss(raw_row.get("total_tss"))
        if raw_row.get("total_tss") is not None
        else current_tss
    )
    if target_role == "off" or target_sport == "off":
        target_role, target_sport, target_tss = "off", "off", 0.0

    if (target_role, target_sport, target_tss) == (current_role, current_sport, current_tss):
        return None

    old_id = str(current.get("session_id") or "").strip()
    if target_tss <= 0 or target_role == "off":
        rebuilt = [dict(item) for i, item in enumerate(day_sessions) if i != position]
    else:
        focus = _build_day_focus_label(target_role, target_sport)
        if str(current.get("kind") or "") == "composite" and target_sport == "brick":
            edited_session = rescale_materialized_session(
                current,
                target_tss=target_tss,
                parts={
                    str(leg.get("sport") or ""): round(
                        float(leg.get("target_tss") or 0.0)
                        * target_tss
                        / max(current_tss, 0.1),
                        1,
                    )
                    for leg in list(current.get("legs") or [])
                },
            )
            edited_session.update(
                {
                    "session_role": target_role,
                    "session_focus": focus,
                    "total_tss": target_tss,
                    "export_name": _build_session_export_name(goal_type, distance, focus),
                }
            )
        else:
            materialized = _sessions_from_parts(
                {target_sport: target_tss},
                target_role,
                phase,
                goal_type,
                distance,
                zone_snapshot=zone_snapshot,
                load_state=load_state,
                recent_template_keys=recent_template_keys,
            )
            if not materialized:
                raise ValueError("edited session could not be materialized")
            edited_session = materialized[0]
        if old_id:
            edited_session["replaces_session_id"] = old_id
        rebuilt = [dict(item) for item in day_sessions]
        rebuilt[position] = edited_session

    new_parts: Dict[str, float] = {"run": 0.0, "bike": 0.0, "swim": 0.0}
    for session in rebuilt:
        for sport, tss in _session_parts_contribution(session).items():
            new_parts[sport] = round(new_parts.get(sport, 0.0) + tss, 1)
    new_total = round(sum(new_parts.values()), 1)
    return rebuilt, new_total, new_parts


def rematerialize_non_executable_sessions(
    goal_plan: Mapping[str, Any],
    *,
    recovery_session_ids: Sequence[str] = (),
) -> tuple[Dict[str, Any], List[str]]:
    """Repair modern non-executable leaves without mutating plan history.

    ``recovery_session_ids`` is derived by the persistence-facing service from
    append-only checkpoint ancestry. The pure model never infers lineage from
    the latest plan-wide edit summary: consecutive replans overwrite that
    summary while older broken leaves remain in the active snapshot.
    """
    updated_goal_plan = deepcopy(dict(goal_plan))
    daily_plan = list(updated_goal_plan.get("daily_plan") or [])
    session_templates = [
        dict(template or {})
        for template in list(updated_goal_plan.get("session_templates") or [])
    ]
    zone_snapshot = extract_zone_snapshot(session_templates)
    load_state = str(
        (updated_goal_plan.get("constraint_summary", {}) or {}).get(
            "load_state",
            "balanced",
        )
        or "balanced"
    ).lower()
    goal_type = str(updated_goal_plan.get("goal_type") or "")
    distance = str(updated_goal_plan.get("distance") or "")
    near_term_edit = (
        updated_goal_plan.get("constraint_summary", {}) or {}
    ).get("near_term_edit", {}) or {}
    recovery_ids = {
        str(value).strip()
        for value in recovery_session_ids
        if str(value).strip()
    }
    changed_dates: List[str] = []

    for day_index, template in enumerate(session_templates):
        sessions = [dict(session or {}) for session in list(template.get("sessions") or [])]
        if not sessions and planned_session_requires_repair(template):
            sessions = [dict(template)]
        rebuilt_sessions: List[Dict[str, Any]] = []
        day_changed = False
        recent_template_keys = _recent_template_keys_before(session_templates, day_index)
        for session in sessions:
            if not planned_session_requires_repair(session):
                rebuilt_sessions.append(session)
                key = str(session.get("template_key") or "").strip()
                if session.get("materialization_status") == "materialized" and key:
                    recent_template_keys.append(key)
                continue

            sport = _normalize_sport(session.get("sport"))
            role = _normalize_session_role(session.get("session_role"))
            target_tss = _normalize_total_tss(session.get("total_tss"))
            template_key = str(session.get("template_key") or "")
            original_role = role
            session_id = str(session.get("session_id") or "").strip()
            if (
                session_id in recovery_ids
                and template_key.startswith("manual:")
            ):
                role = "recovery"
            if sport in {"off", "brick"} or role == "off" or target_tss <= 0:
                raise ValueError("non-executable session cannot be repaired from its saved fields")
            materialized = _sessions_from_parts(
                {sport: target_tss},
                role,
                str(template.get("phase", "Base") or "Base"),
                goal_type,
                distance,
                zone_snapshot=zone_snapshot,
                load_state=load_state,
                recent_template_keys=recent_template_keys,
            )
            if not materialized or planned_session_requires_repair(materialized[0]):
                raise ValueError("non-executable session has no feasible catalog prescription")
            repaired_session = materialized[0]
            repaired_session["repair_evidence"] = {
                "kind": "materialization_repair",
                "source": (
                    "recovery_replan_history"
                    if session_id in recovery_ids
                    else str(near_term_edit.get("origin_kind") or "unknown")
                ),
                "original_role": original_role,
                "resolved_role": role,
            }
            old_id = str(session.get("session_id") or "").strip()
            if old_id:
                repaired_session["replaces_session_id"] = old_id
            rebuilt_sessions.append(repaired_session)
            day_changed = True

        if not day_changed:
            continue
        template["sessions"] = rebuilt_sessions
        project_day_scalars(template)
        session_templates[day_index] = template
        if day_index < len(daily_plan):
            value = daily_plan[day_index][0]
            changed_dates.append(
                value.strftime("%Y-%m-%d") if hasattr(value, "strftime") else str(value)[:10]
            )
        else:
            changed_dates.append(str(template.get("date") or "")[:10])

    if not changed_dates:
        return updated_goal_plan, []

    updated_goal_plan["session_templates"] = session_templates
    updated_goal_plan["plan_revision"] = datetime.now().isoformat()
    repaired = ensure_session_identities(
        updated_goal_plan,
        previous_goal_plan=goal_plan,
    )
    return repaired, sorted(set(changed_dates))


def apply_near_term_day_edits(
    goal_plan: Mapping[str, Any],
    edited_rows: Sequence[Mapping[str, Any]],
    horizon_days: int = EDITABLE_NEAR_TERM_HORIZON_MIN,
    post_edit_strategy: str = "keep",
    max_horizon_days: int = EDITABLE_NEAR_TERM_HORIZON_MAX,
) -> Dict[str, Any]:
    """Apply in-place daily edits to the next 7-10 days of an existing goal plan."""
    updated_goal_plan = dict(goal_plan)
    daily_plan = _clone_daily_plan(goal_plan)
    original_daily_plan = _clone_daily_plan(goal_plan)
    session_templates = _clone_session_templates(goal_plan, daily_plan)
    weekly_summary = [dict(row or {}) for row in list(goal_plan.get("weekly_summary", []) or [])]
    resolved_horizon = _normalize_horizon_days(
        horizon_days,
        len(daily_plan),
        max_horizon_days=max_horizon_days,
    )
    goal_type = str(goal_plan.get("goal_type") or "")
    distance = str(goal_plan.get("distance") or "")
    normalized_post_edit_strategy = _normalize_post_edit_strategy(post_edit_strategy)
    post_edit_strategy_label = NEAR_TERM_EDIT_POST_STRATEGY_LABELS_RU[normalized_post_edit_strategy]
    original_session_templates = list(session_templates)
    current_tsb = _normalize_metric_or_none((goal_plan.get("constraint_summary", {}) or {}).get("current_tsb"))
    load_state = str((goal_plan.get("constraint_summary", {}) or {}).get("load_state", "balanced") or "balanced").lower()
    load_state_label = str((goal_plan.get("constraint_summary", {}) or {}).get("load_state_label") or "").strip()
    zone_snapshot = extract_zone_snapshot(session_templates)

    original_horizon_total = round(sum(total for _dt, total, _parts in daily_plan[:resolved_horizon]), 1)
    changed_day_count = 0
    edited_dates: List[str] = []
    touched_week_stats: Dict[int, Dict[str, float]] = {}

    for raw_row in edited_rows:
        day_index = int(raw_row.get("index", -1))
        if day_index < 0 or day_index >= resolved_horizon:
            continue

        dt, current_total, current_parts = daily_plan[day_index]
        current_template = session_templates[day_index]

        # Issue #205: a row may address one specific session by its stable id.
        # A targeted edit changes only that session and preserves the day's
        # other sessions; an unknown id fails closed.
        targeted_session_id = str(raw_row.get("session_id") or "").strip()
        if targeted_session_id:
            day_sessions = [dict(item or {}) for item in list(current_template.get("sessions") or [])]
            position = next(
                (
                    i
                    for i, session in enumerate(day_sessions)
                    if str(session.get("session_id") or "") == targeted_session_id
                ),
                None,
            )
            if position is None:
                raise ValueError(
                    f"near-term edit addresses unknown session_id {targeted_session_id} on {dt.strftime('%Y-%m-%d')}"
                )
            edited = _apply_targeted_session_edit(
                day_sessions,
                position,
                raw_row,
                phase=str(current_template.get("phase", "Base") or "Base"),
                goal_type=goal_type,
                distance=distance,
                zone_snapshot=zone_snapshot,
                load_state=load_state,
                recent_template_keys=_recent_template_keys_before(
                    session_templates,
                    day_index,
                ),
            )
            if edited is None:
                continue
            day_sessions, new_day_total, new_day_parts = edited
            changed_day_count += 1
            edited_dates.append(dt.strftime("%Y-%m-%d"))
            week_stat = touched_week_stats.setdefault(
                day_index // 7,
                {"delta_tss": 0.0, "edited_days": 0.0},
            )
            week_stat["delta_tss"] += round(new_day_total - float(current_total or 0.0), 1)
            week_stat["edited_days"] += 1.0
            daily_plan[day_index] = (dt, new_day_total, new_day_parts)
            next_template = dict(current_template)
            next_template["sessions"] = day_sessions
            # #232: full projection of the edited primary — name/fatigue/recovery
            # and steps stay consistent with session_focus, never stale.
            project_day_scalars(next_template)
            session_templates[day_index] = next_template
            continue

        current_role = _normalize_session_role(current_template.get("session_role") or ("off" if current_total <= 0 else "easy"))
        current_sport = _normalize_sport(current_template.get("sport") or _dominant_sport(current_parts))

        target_role = _normalize_session_role(raw_row.get("session_role"))
        target_sport = _normalize_sport(raw_row.get("sport"))
        if (
            target_sport == "brick"
            and str(current_template.get("kind") or "single") != "composite"
        ):
            target_sport = current_sport
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
        if not changed:
            continue
        changed_day_count += 1
        edited_dates.append(dt.strftime("%Y-%m-%d"))
        week_index = day_index // 7
        week_stat = touched_week_stats.setdefault(
            week_index,
            {"delta_tss": 0.0, "edited_days": 0.0},
        )
        week_stat["delta_tss"] += round(
            target_total_tss - float(current_total or 0.0),
            1,
        )
        week_stat["edited_days"] += 1.0

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
        next_template = {
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
        if (
            str(current_template.get("kind") or "") == "composite"
            and target_sport == "brick"
            and target_total_tss > 0
        ):
            rescaled = rescale_materialized_session(
                current_template,
                target_tss=target_total_tss,
                parts=new_parts,
            )
            next_template.update(rescaled)
            resolved_duration = int(rescaled.get("duration_minutes") or duration_minutes)
            next_template.update(
                {
                    "date": dt.strftime("%Y-%m-%d"),
                    "week_index": day_index // 7,
                    "day_index": day_index % 7,
                    "phase": phase,
                    "session_role": target_role,
                    "session_focus": focus,
                    "sport": "brick",
                    "sport_label": SPORT_LABELS_RU["brick"],
                    "export_name": export_name,
                    "description": _build_session_description(
                        goal_type=goal_type,
                        distance=distance,
                        phase=phase,
                        session_role=target_role,
                        session_focus=focus,
                        sport="brick",
                        total_tss=target_total_tss,
                        parts=new_parts,
                        duration_minutes=resolved_duration,
                    ),
                }
            )
        next_template = _rebuild_sessions_after_day_edit(
            next_template,
            current_template,
            new_parts=new_parts,
            role=target_role,
            sport=target_sport,
            phase=phase,
            goal_type=goal_type,
            distance=distance,
            zone_snapshot=zone_snapshot,
            load_state=load_state,
            recent_template_keys=_recent_template_keys_before(
                session_templates,
                day_index,
            ),
        )
        session_templates[day_index] = next_template

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
    future_target_tss = _resolve_post_edit_target_delta(
        normalized_post_edit_strategy,
        horizon_delta,
        goal_plan.get("constraint_summary", {}) or {},
    )
    future_delta_tss = 0
    future_week_count = 0
    affected_week_count = max(1, int(ceil(resolved_horizon / 7)))

    if future_target_tss != 0:
        remaining = abs(future_target_tss)
        for week_index in range(affected_week_count, min(len(refreshed_weekly_summary), affected_week_count + 2)):
            week_row = refreshed_weekly_summary[week_index]
            phase = str(week_row.get("phase", "") or "").lower()
            if phase == "taper":
                continue

            current_week_total = int(updated_weekly_tss_plan[week_index] or 0)
            if current_week_total <= 0:
                continue

            if future_target_tss > 0:
                weekly_capacity_tss = int(
                    week_row.get("capacity_tss")
                    or (goal_plan.get("constraint_summary", {}) or {}).get("weekly_capacity_tss")
                    or current_week_total + remaining
                )
                extra_capacity = max(0, weekly_capacity_tss - current_week_total)
                ramp_room = max(10, _round_to_5(current_week_total * 0.08))
                week_delta = int(_round_to_5(min(extra_capacity, ramp_room, remaining)))
            else:
                ramp_rate = 0.08 if normalized_post_edit_strategy == "catch_up" else 0.12
                removable_room = max(10, _round_to_5(current_week_total * ramp_rate))
                week_delta = -int(_round_to_5(min(removable_room, remaining)))

            if week_delta == 0:
                continue

            actual_week_delta = _apply_week_total_delta(
                daily_plan,
                session_templates,
                week_index,
                week_delta,
                goal_type,
                distance,
                zone_snapshot=zone_snapshot,
                load_state=load_state,
            )
            actual_week_delta_int = int(round(actual_week_delta))
            if actual_week_delta_int == 0:
                continue

            future_delta_tss += actual_week_delta_int
            remaining = max(0, remaining - abs(actual_week_delta_int))
            future_week_count += 1
            week_start = week_index * 7
            week_end = min(week_start + 7, len(daily_plan))
            week_days = daily_plan[week_start:week_end]
            week_templates = session_templates[week_start:week_end]
            roles = [_normalize_session_role(template.get("session_role")) for template in week_templates]
            focuses = [
                str(
                    template.get("session_focus")
                    or _build_day_focus_label(
                        _normalize_session_role(template.get("session_role")),
                        _normalize_sport(template.get("sport")),
                    )
                )
                for template in week_templates
            ]
            structure_meta = _build_week_structure_metadata(roles, focuses)
            refreshed_weekly_summary[week_index] = {
                **refreshed_weekly_summary[week_index],
                "weekly_tss": int(round(sum(total for _dt, total, _parts in week_days))),
                "bike": round(sum(parts.get("bike", 0.0) for _dt, _total, parts in week_days), 1),
                "run": round(sum(parts.get("run", 0.0) for _dt, _total, parts in week_days), 1),
                "swim": round(sum(parts.get("swim", 0.0) for _dt, _total, parts in week_days), 1),
                **structure_meta,
            }
            updated_weekly_tss_plan[week_index] = int(refreshed_weekly_summary[week_index]["weekly_tss"])
            future_note = (
                f"ручной возврат +{actual_week_delta_int} TSS"
                if actual_week_delta_int > 0
                else f"ручная разгрузка {actual_week_delta_int:+d} TSS"
            )
            refreshed_weekly_summary[week_index]["adjustment_note"] = _append_adjustment_note(
                refreshed_weekly_summary[week_index].get("adjustment_note", "—"),
                future_note,
                removable_prefixes=("ручной возврат ", "ручная разгрузка "),
            )
            if remaining <= 0:
                break

    constraint_summary = dict(goal_plan.get("constraint_summary", {}) or {})
    original_roles = [
        _normalize_session_role(template.get("session_role") or ("off" if original_daily_plan[day_index][1] <= 0 else "easy"))
        for day_index, template in enumerate(original_session_templates[:resolved_horizon])
    ]
    updated_roles = [
        _normalize_session_role(template.get("session_role") or ("off" if daily_plan[day_index][1] <= 0 else "easy"))
        for day_index, template in enumerate(session_templates[:resolved_horizon])
    ]
    max_added_day_tss = max(
        [0.0]
        + [
            round(daily_plan[day_index][1] - original_daily_plan[day_index][1], 1)
            for day_index in range(resolved_horizon)
        ]
    )
    max_removed_day_tss = min(
        [0.0]
        + [
            round(daily_plan[day_index][1] - original_daily_plan[day_index][1], 1)
            for day_index in range(resolved_horizon)
        ]
    )
    risk_summary = _evaluate_near_term_edit_risk(
        original_horizon_total=original_horizon_total,
        new_horizon_total=new_horizon_total,
        resolved_horizon=resolved_horizon,
        original_roles=original_roles,
        updated_roles=updated_roles,
        current_tsb=current_tsb,
        load_state=load_state,
        load_state_label=load_state_label,
        future_delta_tss=future_delta_tss,
        post_edit_strategy=normalized_post_edit_strategy,
        max_added_day_tss=max_added_day_tss,
        max_removed_day_tss=max_removed_day_tss,
    )
    existing_notes = [
        str(note)
        for note in constraint_summary.get("notes", [])
        if (
            note
            and not str(note).startswith("Ручная правка ближнего горизонта:")
            and not str(note).startswith("После ручной правки:")
            and not str(note).startswith("Оценка ручной правки:")
        )
    ]
    manual_note = (
        f"Ручная правка ближнего горизонта: {changed_day_count} дн. "
        f"в ближайших {resolved_horizon} дн., Δ {horizon_delta:+d} TSS."
    )
    follow_up_note = ""
    if normalized_post_edit_strategy == "keep":
        follow_up_note = "После ручной правки: следующие 1-2 недели оставлены без автокоррекции."
    elif horizon_delta < 0 and future_delta_tss > 0:
        follow_up_note = (
            f"После ручной правки: стратегия «{post_edit_strategy_label}» вернула "
            f"{future_delta_tss} из {future_target_tss} TSS в следующих {future_week_count or 2} нед."
        )
    elif horizon_delta < 0:
        follow_up_note = "После ручной правки: стратегия «Беречь восстановление» не догоняет снятый объём автоматически."
    elif horizon_delta > 0 and future_delta_tss < 0:
        follow_up_note = (
            f"После ручной правки: стратегия «{post_edit_strategy_label}» сняла "
            f"{abs(future_delta_tss)} из {abs(future_target_tss)} TSS со следующих {future_week_count or 2} нед."
        )
    elif horizon_delta > 0 and normalized_post_edit_strategy == "catch_up":
        follow_up_note = "После ручной правки: добавленный объём оставлен локально и не перераспределяется автоматически."
    else:
        follow_up_note = f"После ручной правки: стратегия «{post_edit_strategy_label}» не потребовала автокоррекции."
    risk_note = (
        f"Оценка ручной правки: {risk_summary['risk_guardrail']}"
        if risk_summary["risk_level"] != "low"
        else "Оценка ручной правки: риск низкий, достаточно обычного контроля самочувствия."
    )

    constraint_summary["notes"] = existing_notes + [manual_note, follow_up_note, risk_note]
    constraint_summary["near_term_edit"] = {
        "is_active": changed_day_count > 0,
        "edited_day_count": changed_day_count,
        "edited_dates": edited_dates,
        "horizon_days": resolved_horizon,
        "total_delta_tss": horizon_delta,
        "label": "Ручная правка ближнего горизонта",
        "post_edit_strategy": normalized_post_edit_strategy,
        "post_edit_strategy_label": post_edit_strategy_label,
        "future_target_tss": future_target_tss,
        "future_delta_tss": future_delta_tss,
        "future_weeks": 2,
        "future_week_count": future_week_count,
        **risk_summary,
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

    return ensure_session_identities(updated_goal_plan, previous_goal_plan=goal_plan)


__all__ = [
    "EDITABLE_NEAR_TERM_HORIZON_MAX",
    "EDITABLE_NEAR_TERM_HORIZON_MIN",
    "EDITABLE_SESSION_ROLES",
    "EDITABLE_SPORTS",
    "build_near_term_edit_seed_from_goal_plans",
    "build_near_term_edit_draft_rows",
    "build_near_term_edit_rows",
    "build_safer_near_term_draft",
    "apply_near_term_day_edits",
    "rematerialize_non_executable_sessions",
    "summarize_near_term_draft_rows",
]
