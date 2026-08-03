"""Adherence-лента план vs факт (Issue #228).

Чистая производная поверх снапшота ``services/reconciliation.reconciliation_at``:
никаких чтений БД, provider-вызовов и новой аналитики — только детерминированная
агрегация уже посчитанных матчей в дневную ленту и недельные сводки. Один
модуль-владелец: API-роутер и обе web-поверхности потребляют его вывод, web
никогда не пере-выводит статусы сам.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, List, Mapping, Optional

from models.session_scheduler import HARD_SESSION_ROLES

RIBBON_RULE_VERSION = "adherence-ribbon-v2"

# Худшая честная метка побеждает: лента, усредняющая major_deviation,
# успокаивала бы вместо информирования (принцип явных срезов #205/#226).
# `unknown` — матч есть, но классификация не смогла (нет actual_role):
# любой КЛАССИФИЦИРОВАННЫЙ ярлык дня его перекрывает, но прятать реальный
# матч за unplanned/rest нельзя.
_DAY_STATUS_PRIORITY = ("major_deviation", "missed", "substituted", "exact", "unknown", "pending")


def _parse_date(value: Any) -> Optional[date]:
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def build_adherence_ribbon(
    reconciliation: Mapping[str, Any],
    *,
    as_of: date,
    weeks: int = 4,
) -> Dict[str, Any]:
    """Дневная лента + недельные агрегаты из reconciliation-снапшота.

    Статус дня в приоритете худшей честной метки: major_deviation > missed >
    substituted > exact; ``missed`` — только для плановых сессий с TSS>0;
    день без плана, но с активностью — ``unplanned``; иначе ``rest``.
    """
    base = {
        "has_plan": bool(reconciliation.get("has_plan")),
        "rule_version": str(
            reconciliation.get("rule_version") or ""
        ),
        "ribbon_rule_version": RIBBON_RULE_VERSION,
        "data_quality": dict(reconciliation.get("data_quality") or {}),
    }
    if not base["has_plan"]:
        return {**base, "weeks": [], "days": []}

    resolved_weeks = max(1, int(weeks or 1))
    week_monday = as_of - timedelta(days=as_of.weekday())
    start = week_monday - timedelta(days=(resolved_weeks - 1) * 7)

    # build_reconciliation rows are FLAT: planned fields (date/sport/role/tss)
    # live at the row's top level — verified against a live payload; the
    # nested-"planned" shape was an M1 fixture guess that consumed zero rows.
    planned_by_date: Dict[str, List[Dict[str, Any]]] = {}
    for raw_row in list(reconciliation.get("rows") or []):
        if not isinstance(raw_row, Mapping):
            continue
        row_date = _parse_date(raw_row.get("date"))
        if row_date is None or not (start <= row_date <= as_of):
            continue
        planned_by_date.setdefault(row_date.isoformat(), []).append(
            {
                "date": row_date.isoformat(),
                "sport": str(raw_row.get("sport") or ""),
                "role": str(raw_row.get("role") or "").strip().lower(),
                "planned_tss": round(_float(raw_row.get("tss")), 1),
                "matched": str(raw_row.get("match_status") or "") == "matched",
                "adherence": str(raw_row.get("adherence") or "") or None,
                "actual_tss": round(_float(raw_row.get("actual_total_tss")), 1),
            }
        )

    unplanned_by_date: Dict[str, float] = {}
    for item in list(reconciliation.get("unplanned_activities") or []):
        if not isinstance(item, Mapping):
            continue
        item_date = _parse_date(item.get("date"))
        if item_date is None or not (start <= item_date <= as_of):
            continue
        iso = item_date.isoformat()
        unplanned_by_date[iso] = round(
            unplanned_by_date.get(iso, 0.0) + _float(item.get("tss")), 1
        )

    days: List[Dict[str, Any]] = []
    current = start
    while current <= as_of:
        iso = current.isoformat()
        rows = planned_by_date.get(iso, [])
        labels = {row["adherence"] for row in rows if row["matched"] and row["adherence"]}
        for row in rows:
            if not row["matched"] and row["planned_tss"] > 0:
                # День as_of ещё не закончился: неподтверждённая сессия сегодня
                # — «В процессе», а не «Пропущено» (#268); после перехода
                # календарной границы тот же факт становится пропуском.
                labels.add("pending" if current == as_of else "missed")
        status = next(
            (label for label in _DAY_STATUS_PRIORITY if label in labels),
            "unplanned" if unplanned_by_date.get(iso, 0.0) > 0 else "rest",
        )
        days.append(
            {
                "date": iso,
                "status": status,
                "planned_tss": round(sum(row["planned_tss"] for row in rows), 1),
                "actual_tss": round(
                    sum(row["actual_tss"] for row in rows if row["matched"])
                    + unplanned_by_date.get(iso, 0.0),
                    1,
                ),
            }
        )
        current += timedelta(days=1)

    weeks_out: List[Dict[str, Any]] = []
    for week_index in range(resolved_weeks):
        w_start = start + timedelta(days=week_index * 7)
        w_end = min(w_start + timedelta(days=6), as_of)
        week_rows = [
            row
            for iso, rows in planned_by_date.items()
            for row in rows
            if w_start <= date.fromisoformat(iso) <= w_end
        ]
        week_rows.sort(key=lambda row: (row["date"], row["sport"], row["role"]))
        planned_rows = [row for row in week_rows if row["planned_tss"] > 0]
        matched_rows = [row for row in planned_rows if row["matched"]]
        missed_rows = [
            row
            for row in planned_rows
            if not row["matched"] and date.fromisoformat(row["date"]) < as_of
        ]
        buckets = {
            "exact": 0,
            "substituted": 0,
            "major_deviation": 0,
            "missed": len(missed_rows),
            "unknown": 0,
        }
        for row in matched_rows:
            label = row["adherence"]
            if label in buckets:
                buckets[label] += 1
        unplanned_tss = round(
            sum(
                tss
                for iso, tss in unplanned_by_date.items()
                if w_start <= date.fromisoformat(iso) <= w_end
            ),
            1,
        )
        weeks_out.append(
            {
                "week_start": w_start.isoformat(),
                "planned_sessions": len(planned_rows),
                "matched_sessions": len(matched_rows),
                "adherence": buckets,
                "planned_tss": round(sum(row["planned_tss"] for row in planned_rows), 1),
                "actual_tss": round(sum(row["actual_tss"] for row in matched_rows), 1),
                "unplanned_tss": unplanned_tss,
                "missed_key_sessions": [
                    {"date": row["date"], "sport": row["sport"], "role": row["role"]}
                    for row in missed_rows
                    if row["role"] in HARD_SESSION_ROLES
                ],
            }
        )

    return {**base, "weeks": weeks_out, "days": days}


__all__ = ["RIBBON_RULE_VERSION", "build_adherence_ribbon"]
