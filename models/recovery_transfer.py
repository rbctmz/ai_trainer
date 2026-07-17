"""RecoveryReplan v2: детерминированный ранкер переноса ключевой сессии
на безопасный день D+1…D+3 (Issue #209).

Чистая арифметика над уже загруженным goal plan — ни БД, ни provider
(ASR-PERF-1). Окно считается от даты ИСХОДНОЙ сессии (даты конфликта),
никогда назад. Каждый кандидат сообщает ТОЧНЫЙ набор всех нарушенных
гвардов машинными кодами из `REJECTION_REASON_CODES`; v1 fail-closed —
никакого bounded reduction, соседние сессии не изменяются, cross-week
запрещён (недельный бюджет — якорный инвариант #206).
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date, timedelta
from typing import Any, Dict, List, Mapping, Optional, Sequence

from models.session_scheduler import (
    HARD_SESSION_ROLES,
    MAX_DAY_DURATION_MINUTES,
    MAX_DAY_TSS_POLICY,
)
from models.session_transfer import apply_session_transfer, session_duration_minutes

TRANSFER_RULE_VERSION = "recovery-transfer-v1"

REJECTION_REASON_CODES = frozenset(
    {
        "unavailable",
        "protected",
        "hard_collision",
        "recovery_spacing",
        "occasion_limit",
        "day_tss_ceiling",
        "day_duration_ceiling",
        "cross_week_boundary",
    }
)

_MAX_DAY_OCCASIONS = 2
_WINDOW_OFFSETS = (1, 2, 3)


def _parse_date(value: Any) -> Optional[date]:
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _session_tss(session: Mapping[str, Any]) -> float:
    if str(session.get("kind") or "") == "composite":
        legs = list(session.get("legs") or [])
        if legs:
            return round(sum(float(leg.get("target_tss") or 0.0) for leg in legs), 1)
    return round(float(session.get("total_tss") or 0.0), 1)


def _is_hard(session: Mapping[str, Any]) -> bool:
    return str(session.get("session_role") or "").strip().lower() in HARD_SESSION_ROLES


def _day_sessions(template: Optional[Mapping[str, Any]]) -> List[Mapping[str, Any]]:
    if not isinstance(template, Mapping):
        return []
    return [s for s in list(template.get("sessions") or []) if isinstance(s, Mapping)]


def _find_session(goal_plan: Mapping[str, Any], session_id: str) -> Mapping[str, Any]:
    wanted = str(session_id or "").strip()
    for template in list(goal_plan.get("session_templates") or []):
        for session in _day_sessions(template if isinstance(template, Mapping) else None):
            if str(session.get("session_id") or "") == wanted:
                return session
    raise ValueError(f"conflict session '{session_id}' not found in plan")


def rank_transfer_candidates(
    goal_plan: Mapping[str, Any],
    conflict: Mapping[str, Any],
    *,
    today: date,
    actual_hard_dates: Optional[Sequence[str]] = None,
) -> List[Dict[str, Any]]:
    """Оценивает три даты после даты исходной сессии в фиксированном порядке.

    `actual_hard_dates` — ISO-даты жёсткой УЖЕ ВЫПОЛНЕННОЙ нагрузки, которые
    loop извлекает из своего загруженного reconciliation snapshot; правило
    post-removal касается только плановой конфликтной сессии — реальная
    выполненная нагрузка исходного дня продолжает блокировать соседей.
    """
    moved = _find_session(goal_plan, str(conflict.get("session_id") or ""))
    moved_id = str(moved.get("session_id") or "")
    moved_is_hard = _is_hard(moved)
    moved_tss = _session_tss(moved)
    moved_duration = session_duration_minutes(moved)

    source_date = _parse_date(conflict.get("date"))
    if source_date is None:
        raise ValueError(f"conflict date '{conflict.get('date')}' is not a date")

    templates_by_date: Dict[str, Mapping[str, Any]] = {}
    plan_start: Optional[date] = None
    for template in list(goal_plan.get("session_templates") or []):
        if not isinstance(template, Mapping):
            continue
        day = _parse_date(template.get("date"))
        if day is None:
            continue
        templates_by_date[day.isoformat()] = template
        if plan_start is None or day < plan_start:
            plan_start = day
    if plan_start is None:
        plan_start = source_date

    protected = {str(value) for value in list(goal_plan.get("protected_dates") or [])}
    constraint_summary = goal_plan.get("constraint_summary") or {}
    available_raw = (
        constraint_summary.get("available_day_indices")
        if isinstance(constraint_summary, Mapping)
        else None
    )
    available = {int(v) for v in available_raw} if available_raw is not None else None
    actual_hard = {
        parsed
        for parsed in (_parse_date(value) for value in (actual_hard_dates or []))
        if parsed is not None
    }

    source_week = (source_date - plan_start).days // 7

    def _planned_hard_neighbour(day: date) -> bool:
        """Post-removal смежность ±1 день: перемещаемая ПЛАНОВАЯ сессия
        покидает исходный день и не считается; остальные — считаются."""
        for delta in (-1, 1):
            neighbour = templates_by_date.get((day + timedelta(days=delta)).isoformat())
            for session in _day_sessions(neighbour):
                if str(session.get("session_id") or "") == moved_id:
                    continue
                if _is_hard(session):
                    return True
        return False

    def _actual_hard_near(day: date) -> bool:
        return any(abs((day - executed).days) <= 1 for executed in actual_hard)

    rows: List[Dict[str, Any]] = []
    for offset in _WINDOW_OFFSETS:
        candidate = source_date + timedelta(days=offset)
        candidate_iso = candidate.isoformat()
        template = templates_by_date.get(candidate_iso)
        existing = [s for s in _day_sessions(template) if str(s.get("session_id") or "") != moved_id]
        existing_tss = round(sum(_session_tss(s) for s in existing), 1)
        existing_duration = sum(session_duration_minutes(s) for s in existing)

        reasons: List[str] = []
        if (candidate - plan_start).days // 7 != source_week:
            reasons.append("cross_week_boundary")
        if available is not None and candidate.weekday() not in available:
            reasons.append("unavailable")
        if candidate_iso in protected:
            reasons.append("protected")
        if moved_is_hard and any(_is_hard(s) for s in existing):
            reasons.append("hard_collision")
        if moved_is_hard and (_planned_hard_neighbour(candidate) or _actual_hard_near(candidate)):
            reasons.append("recovery_spacing")
        if len(existing) + 1 > _MAX_DAY_OCCASIONS:
            reasons.append("occasion_limit")
        if round(existing_tss + moved_tss, 1) > float(MAX_DAY_TSS_POLICY):
            reasons.append("day_tss_ceiling")
        if existing_duration + moved_duration > int(MAX_DAY_DURATION_MINUTES):
            reasons.append("day_duration_ceiling")

        rows.append(
            {
                "offset": offset,
                "date": candidate_iso,
                "eligible": not reasons,
                "rejected_reasons": reasons,
                "existing_occasions": len(existing),
                "day_tss_before": existing_tss,
                "day_tss_after": round(existing_tss + moved_tss, 1),
                "day_duration_before": existing_duration,
                "day_duration_after": existing_duration + moved_duration,
                "rule_version": TRANSFER_RULE_VERSION,
            }
        )
    return rows


def build_transfer_variant(
    goal_plan: Mapping[str, Any],
    conflict: Mapping[str, Any],
    *,
    today: date,
    actual_hard_dates: Optional[Sequence[str]] = None,
) -> Optional[Dict[str, Any]]:
    """Строит типизированный вариант `transfer_1_3d` из лучшего кандидата.

    Ранжирование среди eligible: минимальное вмешательство (меньше уже
    существующих сессий на целевом дне), затем ближайшая дата. Нет
    кандидатов — None: контур честно остаётся на downgrade/keep.
    """
    rows = rank_transfer_candidates(
        goal_plan, conflict, today=today, actual_hard_dates=actual_hard_dates
    )
    eligible = [row for row in rows if row["eligible"]]
    if not eligible:
        return None
    best = min(eligible, key=lambda row: (row["existing_occasions"], row["offset"], row["date"]))

    old_id = str(conflict.get("session_id") or "")
    applied = apply_session_transfer(goal_plan, session_id=old_id, target_date=best["date"])
    moved_plan = applied["goal_plan"]

    templates_before = {
        str(t.get("date") or ""): t
        for t in list(goal_plan.get("session_templates") or [])
        if isinstance(t, Mapping)
    }
    templates_after = {
        str(t.get("date") or ""): t
        for t in list(moved_plan.get("session_templates") or [])
        if isinstance(t, Mapping)
    }

    source_iso = str(conflict.get("date") or "")
    day_changes = []
    for day_iso in (source_iso, best["date"]):
        day_changes.append(
            {
                "date": day_iso,
                "before_sessions": deepcopy(list((templates_before.get(day_iso) or {}).get("sessions") or [])),
                "after_sessions": deepcopy(list((templates_after.get(day_iso) or {}).get("sessions") or [])),
            }
        )

    new_session = None
    for session in _day_sessions(templates_after.get(best["date"])):
        if str(session.get("session_id") or "") == applied["new_session_id"]:
            new_session = deepcopy(dict(session))
            break
    if new_session is None:
        raise ValueError("transfer variant invariant violated: new session missing on target day")

    def _plan_duration(plan: Mapping[str, Any]) -> int:
        total = 0
        for template in list(plan.get("session_templates") or []):
            for session in _day_sessions(template if isinstance(template, Mapping) else None):
                total += session_duration_minutes(session)
        return total

    return {
        "kind": "transfer_1_3d",
        "rule_version": TRANSFER_RULE_VERSION,
        "source_date": source_iso,
        "target_date": best["date"],
        "replaced_session_id": old_id,
        "new_session": new_session,
        "transfer_group_id": applied["transfer_group_id"],
        "candidates": rows,
        "day_changes": day_changes,
        "weekly_duration_delta_minutes": _plan_duration(moved_plan) - _plan_duration(goal_plan),
    }


__all__ = [
    "REJECTION_REASON_CODES",
    "TRANSFER_RULE_VERSION",
    "build_transfer_variant",
    "rank_transfer_candidates",
]
