"""Атомарный примитив переноса сессии между днями плана (Issue #209).

`apply_session_transfer` — ЕДИНСТВЕННЫЙ механизм перемещения сессии:
клонирует план, снимает сессию с исходного дня, вставляет её сохранённой
структурой (steps байт-в-байт) на целевой день, перестраивает дневные
проекции и недельные бакеты из sessions[], штампует identity через
`ensure_session_identities(previous_goal_plan=...)` и проверяет инварианты.
Near-term редактор переносом НЕ является: он пересобирает сессию из
скаляров и теряет структуру. Preview и confirm вызывают этот один примитив,
поэтому обещание ранкера и применённый результат не могут разойтись.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List, Mapping, Tuple

from models.session_identity import ensure_session_identities

_SPORT_PARTS = ("run", "bike", "swim")
# Зеркальные ключи дня: проекция первичной сессии на верхний уровень шаблона
# (позиционный контракт «один шаблон на день» из #205/#206).
_DAY_MIRROR_KEYS = ("kind", "legs", "transition_minutes", "materialized_steps")


def _session_total_tss(session: Mapping[str, Any]) -> float:
    if str(session.get("kind") or "") == "composite":
        legs = list(session.get("legs") or [])
        if legs:
            return round(sum(float(leg.get("target_tss") or 0.0) for leg in legs), 1)
    return round(float(session.get("total_tss") or 0.0), 1)


def _session_parts(session: Mapping[str, Any]) -> Dict[str, float]:
    parts = {sport: 0.0 for sport in _SPORT_PARTS}
    if str(session.get("kind") or "") == "composite":
        for leg in list(session.get("legs") or []):
            sport = str(leg.get("sport") or "")
            if sport in parts:
                parts[sport] = round(parts[sport] + float(leg.get("target_tss") or 0.0), 1)
        return parts
    sport = str(session.get("sport") or "")
    if sport in parts:
        parts[sport] = round(parts[sport] + _session_total_tss(session), 1)
    return parts


def session_duration_minutes(session: Mapping[str, Any]) -> int:
    """Persisted-длительность сессии: у composite brick — длительность
    родителя (transition уже внутри), у независимой — её duration_minutes."""
    return int(round(float(session.get("duration_minutes") or 0)))


def _rebuild_day_projection(template: Dict[str, Any]) -> Tuple[float, Dict[str, float]]:
    """Пересобирает скаляры дня из sessions[] и возвращает (total, parts)."""
    sessions = list(template.get("sessions") or [])
    parts = {sport: 0.0 for sport in _SPORT_PARTS}
    total = 0.0
    for session in sessions:
        total = round(total + _session_total_tss(session), 1)
        for sport, value in _session_parts(session).items():
            parts[sport] = round(parts[sport] + value, 1)

    primary = dict(sessions[0]) if sessions else {}
    if sessions:
        template["session_role"] = str(primary.get("session_role") or "easy")
        template["sport"] = str(primary.get("sport") or "off")
        template["sport_label"] = str(primary.get("sport_label") or template["sport"])
        template["session_focus"] = str(primary.get("session_focus") or "—")
        template["duration_minutes"] = session_duration_minutes(primary)
        for key in _DAY_MIRROR_KEYS:
            if key in primary:
                template[key] = deepcopy(primary[key])
            else:
                template.pop(key, None)
    else:
        template["session_role"] = "off"
        template["sport"] = "off"
        template["sport_label"] = "off"
        template["session_focus"] = "—"
        template["duration_minutes"] = 0
        for key in _DAY_MIRROR_KEYS:
            template.pop(key, None)
    return total, parts


def _relink_composite_legs(template: Dict[str, Any]) -> None:
    """leg_id ног всегда следуют за АКТУАЛЬНЫМ id родительской сессии —
    после переноса это новый content-derived id (#206: leg не сессия)."""
    for session in list(template.get("sessions") or []):
        if str(session.get("kind") or "") != "composite":
            continue
        parent_id = str(session.get("session_id") or "")
        legs = []
        for position, raw_leg in enumerate(list(session.get("legs") or []), start=1):
            leg = dict(raw_leg or {})
            resolved_index = int(leg.get("leg_index") or position)
            leg["leg_index"] = resolved_index
            leg["leg_id"] = f"{parent_id}:{resolved_index}"
            legs.append(leg)
        session["legs"] = legs


def _plan_total_tss(plan: Mapping[str, Any]) -> float:
    """Суммарный TSS плана из sessions[] — исполняемой правды #206. Инвариант
    консервации намеренно НЕ считается по daily-строкам: перенос сам
    перестраивает дневную проекцию из sessions, и план, чья проекция отстала,
    не должен ронять честный перенос."""
    total = 0.0
    for template in list(plan.get("session_templates") or []):
        if not isinstance(template, Mapping):
            continue
        for session in list(template.get("sessions") or []):
            if isinstance(session, Mapping):
                total = round(total + _session_total_tss(session), 1)
    return total


def _plan_total_duration(plan: Mapping[str, Any]) -> int:
    total = 0
    for template in list(plan.get("session_templates") or []):
        if not isinstance(template, Mapping):
            continue
        for session in list(template.get("sessions") or []):
            total += session_duration_minutes(session)
    return total


def apply_session_transfer(
    goal_plan: Mapping[str, Any],
    *,
    session_id: str,
    target_date: str,
) -> Dict[str, Any]:
    """Атомарно переносит сессию `session_id` на день `target_date`.

    Возвращает ``{"goal_plan": новый план, "old_session_id", "new_session_id",
    "transfer_group_id"}``. Входной план не мутируется; неизвестный id или
    дата — fail-closed ValueError без каких-либо изменений.
    """
    wanted = str(session_id or "").strip()
    templates_in = list(goal_plan.get("session_templates") or [])

    source_index: int | None = None
    session_index: int | None = None
    for t_index, template in enumerate(templates_in):
        if not isinstance(template, Mapping):
            continue
        for s_index, session in enumerate(list(template.get("sessions") or [])):
            if isinstance(session, Mapping) and str(session.get("session_id") or "") == wanted:
                source_index, session_index = t_index, s_index
                break
        if source_index is not None:
            break
    if source_index is None or not wanted:
        raise ValueError(f"transfer source session '{session_id}' not found in plan")

    target_index: int | None = None
    for t_index, template in enumerate(templates_in):
        if isinstance(template, Mapping) and str(template.get("date") or "") == str(target_date):
            target_index = t_index
            break
    if target_index is None:
        raise ValueError(f"no plan day for target date '{target_date}'")

    tss_before = _plan_total_tss(goal_plan)
    duration_before = _plan_total_duration(goal_plan)

    plan = deepcopy(dict(goal_plan))
    templates = [dict(item or {}) for item in list(plan.get("session_templates") or [])]
    plan["session_templates"] = templates

    source_template = templates[source_index]
    source_sessions = [dict(s or {}) for s in list(source_template.get("sessions") or [])]
    moved = source_sessions.pop(session_index)
    source_template["sessions"] = source_sessions

    transfer_group_id = f"tg_{wanted}_{target_date}"
    moved["replaces_session_id"] = wanted
    moved["transfer_group_id"] = transfer_group_id
    for stale_key in ("session_id", "session_material_fingerprint", "session_identity_rule_version"):
        moved.pop(stale_key, None)

    target_template = templates[target_index]
    target_sessions = [dict(s or {}) for s in list(target_template.get("sessions") or [])]
    target_sessions.append(moved)
    target_template["sessions"] = target_sessions

    daily_plan = list(plan.get("daily_plan") or [])
    for index in (source_index, target_index):
        template = templates[index]
        total, parts = _rebuild_day_projection(template)
        if index < len(daily_plan) and isinstance(daily_plan[index], (list, tuple)):
            day_dt = daily_plan[index][0]
            daily_plan[index] = (day_dt, total, parts)
    plan["daily_plan"] = daily_plan

    # Однодневная цель наследует day-identity: replaces фиксируется на шаблоне,
    # чтобы ensure_session_identities спроецировал lineage в sessions[0].
    if len(target_sessions) == 1:
        target_template["replaces_session_id"] = wanted
    if not source_sessions:
        source_template.pop("replaces_session_id", None)

    weekly_summary = [dict(row or {}) for row in list(plan.get("weekly_summary") or [])]
    for week_index, row in enumerate(weekly_summary):
        week_days = daily_plan[week_index * 7 : week_index * 7 + 7]
        row["weekly_tss"] = int(
            round(
                sum(
                    float(item[1] or 0.0)
                    for item in week_days
                    if isinstance(item, (list, tuple)) and len(item) >= 2
                )
            )
        )
    from models.training_planner import derive_weekly_sport_buckets_from_sessions

    plan["weekly_summary"] = derive_weekly_sport_buckets_from_sessions(weekly_summary, templates)

    result_plan = ensure_session_identities(plan, previous_goal_plan=goal_plan)
    for template in list(result_plan.get("session_templates") or []):
        _relink_composite_legs(template)

    new_session_id = ""
    for session in list(result_plan["session_templates"][target_index].get("sessions") or []):
        if str(session.get("transfer_group_id") or "") == transfer_group_id:
            new_session_id = str(session.get("session_id") or "")
            break
    if not new_session_id:
        raise ValueError("transfer invariant violated: moved session lost its identity")

    tss_after = _plan_total_tss(result_plan)
    duration_after = _plan_total_duration(result_plan)
    if abs(tss_after - tss_before) > 0.11 or duration_after != duration_before:
        raise ValueError(
            "transfer invariant violated: totals changed "
            f"(tss {tss_before}→{tss_after}, minutes {duration_before}→{duration_after})"
        )

    return {
        "goal_plan": result_plan,
        "old_session_id": wanted,
        "new_session_id": new_session_id,
        "transfer_group_id": transfer_group_id,
    }


__all__ = ["apply_session_transfer", "session_duration_minutes"]
