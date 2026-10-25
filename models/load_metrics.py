"""Canonical CTL/ATL/TSB pipeline shared by every surface (issue #731).

Owner decision 2026-10-25 (research/today_v2_recon_2026-10-25.md, section Б):
one input pipeline — canonical window bounds, multisport-envelope filtering,
zero-fill of rest days to the athlete-local anchor, the ``activities.tss``
column — so the readiness snapshot, planning status, dashboard and coach tools
show the same numbers. ``source_tss``/``garmin_training_load`` stay
provenance-only; the tss scale itself is verified against Intervals.icu in
issue #731 step A2 before any scale fix.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pandas as pd

from models.activity_lineage import authoritative_training_load_activities
from models.banister import BanisterModel

LOAD_METRICS_WINDOW_DAYS = 90


def load_metrics_window_bounds(anchor: date) -> tuple[str, str]:
    """Inclusive ISO bounds of the canonical CTL/ATL/TSB window ending at `anchor`.

    `Database.get_activities(days)` режет по **включительной** границе
    `today - days`, поэтому отдаёт `days + 1` календарных дат и на краю окна
    расходится с каноническим readiness snapshot, который читает ровно
    `LOAD_METRICS_WINDOW_DAYS` дат (находка ревью #614).
    """
    start = anchor - timedelta(days=LOAD_METRICS_WINDOW_DAYS - 1)
    return start.isoformat(), anchor.isoformat()


def _safe_float(value: Any, default: float = 0.0) -> float:
    """Привести к float; нечисловое и не-конечное значение считаем отсутствием.

    ``inf`` опаснее NaN: он проходит арифметику EWMA, превращает отношение в NaN
    и валит сериализацию ответа, поэтому отсекается до Banister и ACWR.
    """
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return result if result == result and result not in (float("inf"), float("-inf")) else default


def _frame_or_empty(frame: pd.DataFrame | None) -> pd.DataFrame:
    return frame if isinstance(frame, pd.DataFrame) else pd.DataFrame()


def canonical_activities_frame(db: Any, anchor: date) -> pd.DataFrame:
    """Activities of the canonical window, read straight from the database."""
    start, end = load_metrics_window_bounds(anchor)
    return pd.DataFrame(db.get_activities_between(start, end))


def daily_tss_series(
    activities_df: pd.DataFrame | None,
    anchor: date,
) -> tuple[list[float], list[Any]]:
    """Дневной ряд нагрузки ``(tss, dates)`` с нулями дней отдыха до якоря.

    Общий вход Banister (CTL/ATL/TSB): конверты мультиспорта заменяются
    авторитетным источником нагрузки, нечисловая и не-конечная нагрузка
    считается отсутствием, будущие даты отбрасываются, дни после последней
    тренировки достраиваются нулями до якоря (issue #231).
    """
    frame = _frame_or_empty(activities_df)
    if frame.empty or "tss" not in frame.columns or "date" not in frame.columns:
        return [], []

    filtered = authoritative_training_load_activities(frame)
    if filtered.empty:
        return [], []

    parsed = filtered[["date", "tss"]].copy()
    parsed["date"] = pd.to_datetime(parsed["date"], errors="coerce")
    parsed["tss"] = pd.to_numeric(parsed["tss"], errors="coerce")
    parsed = parsed.dropna(subset=["date"])
    if parsed.empty:
        return [], []
    parsed["tss"] = [_safe_float(value) for value in parsed["tss"]]

    anchor_ts = pd.Timestamp(anchor)
    parsed = parsed[parsed["date"] <= anchor_ts]
    if parsed.empty:
        return [], []

    daily = parsed.groupby(parsed["date"].dt.normalize())["tss"].sum().sort_index()
    date_range = pd.date_range(start=daily.index.min(), end=anchor_ts, freq="D")
    daily = daily.reindex(date_range, fill_value=0.0)
    return daily.tolist(), daily.index.tolist()


def compute_load_metrics(
    activities_df: pd.DataFrame | None,
    anchor: date,
) -> dict[str, Any] | None:
    """CTL/ATL/TSB в форме readiness-снапшота; ``None`` — данных для ряда нет."""
    tss_data, dates = daily_tss_series(activities_df, anchor)
    if not tss_data:
        return None
    metrics = BanisterModel().get_current_metrics(tss_data, dates)
    return {
        "ctl": round(float(metrics.get("ctl") or 0.0), 1),
        "atl": round(float(metrics.get("atl") or 0.0), 1),
        "tsb": round(float(metrics.get("tsb") or 0.0), 1),
        "window_days": LOAD_METRICS_WINDOW_DAYS,
        "as_of": anchor.isoformat(),
    }


def compute_load_signal(
    activities_df: pd.DataFrame | None,
    anchor: date,
) -> dict[str, Any]:
    """CTL/ATL/TSB в форме signals-engine (с fitness/fatigue/form)."""
    empty = {
        "ctl": 0.0,
        "atl": 0.0,
        "tsb": 0.0,
        "fitness": 0.0,
        "fatigue": 0.0,
        "form": "Недостаточно данных",
    }
    tss_data, dates = daily_tss_series(activities_df, anchor)
    if not tss_data:
        return empty
    metrics = BanisterModel().get_current_metrics(tss_data, dates)
    return {
        "ctl": metrics.get("ctl"),
        "atl": metrics.get("atl"),
        "tsb": metrics.get("tsb"),
        "fitness": metrics.get("fitness"),
        "fatigue": metrics.get("fatigue"),
        "form": metrics.get("form", "Недостаточно данных"),
    }
