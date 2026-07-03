"""Weekly target and demand contracts for the web planning API."""
from __future__ import annotations

from statistics import median
from typing import Any, Dict, List, Mapping

import pandas as pd

from models.training_planner import (
    goal_target_weekly_tss,
    summarize_availability,
    suggest_target_weekly_tss,
)


DEMAND_PROFILES: Dict[str, Dict[str, Any]] = {
    "easy": {
        "level": "easy",
        "label": "Легко",
        "multiplier": 0.90,
        "description": "Сдержанный рост нагрузки.",
    },
    "moderate": {
        "level": "moderate",
        "label": "Умеренно",
        "multiplier": 1.00,
        "description": "Базовая рекомендация планировщика.",
    },
    "demanding": {
        "level": "demanding",
        "label": "Требовательно",
        "multiplier": 1.10,
        "description": "Немного выше базовой нагрузки.",
    },
    "aggressive": {
        "level": "aggressive",
        "label": "Агрессивно",
        "multiplier": 1.20,
        "description": "Максимально допустимо в рамках доступности.",
    },
}
DEFAULT_DEMAND_LEVEL = "moderate"


def _round_to_5(value: float) -> int:
    return int(round(float(value) / 5.0) * 5)


def normalize_demand_level(value: Any) -> str:
    level = str(value or "").strip().lower()
    return level if level in DEMAND_PROFILES else DEFAULT_DEMAND_LEVEL


def demand_profile(value: Any = None) -> Dict[str, Any]:
    return dict(DEMAND_PROFILES[normalize_demand_level(value)])


def demand_options() -> List[Dict[str, Any]]:
    return [dict(DEMAND_PROFILES[key]) for key in ("easy", "moderate", "demanding", "aggressive")]


def recent_weekly_tss_summary(activities_df: Any) -> Dict[str, Any]:
    """Summarize recent load using a stable weekly median for explainability."""
    if activities_df is None or getattr(activities_df, "empty", True) or "date" not in activities_df.columns:
        return {
            "method": "median",
            "weeks": [],
            "weeks_count": 0,
            "median_weekly_tss": 0,
            "last_week": 0,
            "avg_4": 0,
            "best_8": 0,
        }

    df = activities_df.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"])
    if df.empty:
        return recent_weekly_tss_summary(None)

    if "tss" not in df.columns:
        df["tss"] = 0.0
    df["tss"] = pd.to_numeric(df["tss"], errors="coerce").fillna(0.0)
    week_start = (df["date"] - pd.to_timedelta(df["date"].dt.weekday, unit="D")).dt.date
    weekly = (
        pd.DataFrame({"week_start": week_start, "weekly_tss": df["tss"]})
        .groupby("week_start", as_index=False)["weekly_tss"]
        .sum()
        .sort_values("week_start")
        .tail(12)
    )
    values = [float(value) for value in weekly["weekly_tss"].tolist()]
    if not values:
        return recent_weekly_tss_summary(None)

    return {
        "method": "median",
        "weeks": [
            {"week_start": row.week_start.isoformat(), "weekly_tss": round(float(row.weekly_tss), 1)}
            for row in weekly.itertuples(index=False)
        ],
        "weeks_count": len(values),
        "median_weekly_tss": _round_to_5(float(median(values))),
        "last_week": round(values[-1], 1),
        "avg_4": round(sum(values[-4:]) / min(len(values), 4), 1),
        "best_8": round(max(values[-8:]), 1),
    }


def build_weekly_target_breakdown(
    *,
    goal_type: str,
    distance: str,
    activities_df: Any,
    available_hours: float,
    available_day_indices: List[int] | None = None,
    demand: Any = None,
) -> Dict[str, Any]:
    demand_info = demand_profile(demand)
    availability = summarize_availability(goal_type, available_hours, available_day_indices)
    recent_load = recent_weekly_tss_summary(activities_df)
    suggested = suggest_target_weekly_tss(goal_type, distance, activities_df)
    range_min, range_max = goal_target_weekly_tss(goal_type, distance)
    goal_need = _round_to_5((range_min + range_max) / 2.0)
    availability_cap = int(availability.get("weekly_capacity_tss") or 0)
    suggested_tss = int(suggested.get("suggested") or goal_need)

    if recent_load["median_weekly_tss"] > 0:
        load_floor = min(
            range_max,
            _round_to_5(max(recent_load["median_weekly_tss"], recent_load["last_week"]) * 1.10),
        )
        base_weekly_tss = max(range_min, min(suggested_tss, load_floor))
    else:
        base_weekly_tss = suggested_tss

    if availability_cap > 0:
        base_weekly_tss = min(base_weekly_tss, availability_cap)
    base_weekly_tss = max(50, _round_to_5(base_weekly_tss))

    demand_adjusted = _round_to_5(base_weekly_tss * float(demand_info["multiplier"]))
    final_target = max(50, demand_adjusted)
    if availability_cap > 0:
        final_target = min(final_target, availability_cap)
    final_target = _round_to_5(final_target)

    rows = [
        {
            "key": "goal_need",
            "label": "Потребность цели",
            "value": goal_need,
            "unit": "TSS/нед",
            "detail": f"Диапазон цели {range_min}-{range_max} TSS/нед.",
        },
        {
            "key": "availability_cap",
            "label": "Потолок доступности",
            "value": availability_cap,
            "unit": "TSS/нед",
            "detail": (
                f"{availability['available_hours']} ч × {availability['tss_per_hour']} TSS/ч "
                f"× плотность {availability['density_factor']}"
            ),
        },
        {
            "key": "recent_load",
            "label": "Недавняя нагрузка",
            "value": recent_load["median_weekly_tss"],
            "unit": "TSS/нед",
            "detail": f"Медиана последних {recent_load['weeks_count']} нед.",
        },
        {
            "key": "base_weekly_tss",
            "label": "База недели",
            "value": base_weekly_tss,
            "unit": "TSS/нед",
            "detail": "Минимум из рекомендации и потолка доступности.",
        },
    ]

    return {
        "range_min": range_min,
        "range_max": range_max,
        "goal_need_tss": goal_need,
        "suggested_weekly_tss": suggested_tss,
        "base_weekly_tss": base_weekly_tss,
        "final_target_weekly_tss": final_target,
        "demand": demand_info,
        "availability": availability,
        "recent_load": recent_load,
        "history": {
            "last_week": round(float(suggested.get("last_week") or recent_load["last_week"] or 0), 0),
            "avg_4": round(float(suggested.get("avg_4") or recent_load["avg_4"] or 0), 0),
            "best_8": round(float(suggested.get("best_8") or recent_load["best_8"] or 0), 0),
        },
        "rows": rows,
    }


def public_weekly_target_payload(breakdown: Mapping[str, Any]) -> Dict[str, Any]:
    """Return the stable API shape consumed by web and tests."""
    return {
        "target_weekly_tss": int(breakdown.get("final_target_weekly_tss") or 0),
        "base_weekly_tss": int(breakdown.get("base_weekly_tss") or 0),
        "final_target_weekly_tss": int(breakdown.get("final_target_weekly_tss") or 0),
        "range_min": int(breakdown.get("range_min") or 0),
        "range_max": int(breakdown.get("range_max") or 0),
        "history": dict(breakdown.get("history", {}) or {}),
        "demand": dict(breakdown.get("demand", {}) or {}),
        "breakdown": {
            "rows": list(breakdown.get("rows", []) or []),
            "availability": dict(breakdown.get("availability", {}) or {}),
            "recent_load": dict(breakdown.get("recent_load", {}) or {}),
        },
    }
