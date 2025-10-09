"""Helpers for analyzing sleep schedule regularity."""
from __future__ import annotations

import math
from datetime import datetime
from typing import Any, Dict, Optional

import pandas as pd

MINUTES_IN_DAY = 24 * 60
_HALF_DAY_MINUTES = 12 * 60
_MIN_VALID_RECORDS = 3
_WEEKDAY_LABELS = {
    0: "Пн",
    1: "Вт",
    2: "Ср",
    3: "Чт",
    4: "Пт",
    5: "Сб",
    6: "Вс",
}


def _parse_time_to_minutes(time_str: str) -> Optional[int]:
    """Convert HH:MM string to minutes since midnight (0-1439)."""
    if not time_str or pd.isna(time_str):
        return None

    try:
        parsed = datetime.strptime(time_str.strip(), "%H:%M")
    except (ValueError, TypeError):
        return None
    return parsed.hour * 60 + parsed.minute


def _bedtime_minutes(time_str: str) -> Optional[int]:
    """Return bedtime minutes adjusted to allow post-midnight consistency."""
    minutes = _parse_time_to_minutes(time_str)
    if minutes is None:
        return None
    if minutes < _HALF_DAY_MINUTES:
        minutes += MINUTES_IN_DAY  # Treat early-morning bedtimes as next day
    return minutes


def _wakeup_minutes(time_str: str) -> Optional[int]:
    return _parse_time_to_minutes(time_str)


def _format_minutes(minutes: float) -> str:
    """Format minutes (possibly > 1440) back to HH:MM."""
    if minutes is None or not math.isfinite(minutes):
        return "—"
    minutes = minutes % MINUTES_IN_DAY
    hours = int(minutes // 60)
    mins = int(round(minutes % 60))
    if mins == 60:
        mins = 0
        hours = (hours + 1) % 24
    return f"{hours:02d}:{mins:02d}"


def _format_minutes_value(value: float) -> str:
    if value is None or not math.isfinite(value):
        return "—"
    return f"{int(round(value))} мин"


def _format_duration(minutes: float) -> str:
    if minutes is None or not math.isfinite(minutes):
        return "—"
    total_minutes = int(round(minutes))
    hours = total_minutes // 60
    mins = total_minutes % 60
    parts = []
    if hours:
        parts.append(f"{hours}ч")
    if mins or not parts:
        parts.append(f"{mins}м")
    return " ".join(parts)


def _classify_regularity(std_minutes: Optional[float]) -> tuple[str, str]:
    """Return (status, label) for ModernUI cards."""
    if std_minutes is None or not math.isfinite(std_minutes):
        return "secondary", "Недостаточно данных"
    if std_minutes <= 15:
        return "success", "Очень стабильно"
    if std_minutes <= 30:
        return "warning", "Есть колебания"
    return "danger", "Существенный дрейф"


def _recommendation(status: str, metric: str) -> str:
    if status == "success":
        return "Режим выдержан — сохраняйте привычные часы." if metric == "bedtime" else "Продолжайте просыпаться в одно и то же время."
    if status == "warning":
        return (
            "Попробуйте начинать подготовку ко сну за час до среднего времени." if metric == "bedtime"
            else "Старайтесь заводить будильник на одно время даже в выходные."
        )
    if status == "danger":
        return (
            "Фиксируйте время отбоя и сокращайте разброс до ±30 минут." if metric == "bedtime"
            else "Выберите целевое время подъёма и придерживайтесь его хотя бы неделю."
        )
    return "Недостаточно данных для рекомендаций."


def compute_sleep_regularity(sleep_df: pd.DataFrame) -> Dict[str, Any]:
    """Calculate regularity metrics for bedtime and wake-up times."""
    result: Dict[str, Any] = {
        "count": 0,
        "bedtime": None,
        "wakeup": None,
        "series": pd.DataFrame(),
        "weekday_profile": pd.DataFrame(),
    }

    if sleep_df is None or sleep_df.empty:
        return result

    df = sleep_df.copy()
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["bedtime", "wakeup_time"])

    if df.empty:
        return result

    df["bedtime_minutes_raw"] = df["bedtime"].apply(_bedtime_minutes)
    df["wakeup_minutes"] = df["wakeup_time"].apply(_wakeup_minutes)
    df["bedtime_minutes_display"] = df["bedtime_minutes_raw"].mod(MINUTES_IN_DAY)
    df["wakeup_minutes_adjusted"] = df["wakeup_minutes"].astype(float)
    mask = df["wakeup_minutes_adjusted"] < _HALF_DAY_MINUTES
    df.loc[mask, "wakeup_minutes_adjusted"] += MINUTES_IN_DAY

    df = df.dropna(subset=["bedtime_minutes_raw", "wakeup_minutes_adjusted"])
    result["count"] = len(df)

    weekday_profile = _build_weekday_profile(df)
    result["weekday_profile"] = weekday_profile

    if len(df) < _MIN_VALID_RECORDS:
        result["series"] = df[["date", "bedtime_minutes_display", "wakeup_minutes", "wakeup_minutes_adjusted"]]
        return result

    bedtime_series = df["bedtime_minutes_raw"].astype(float)
    wake_series = df["wakeup_minutes_adjusted"].astype(float)

    def build_metric(series: pd.Series, metric: str) -> Dict[str, Any]:
        if series.empty or not series.notna().any():
            return {
                "status": "secondary",
                "label": "Недостаточно данных",
                "std_minutes": math.nan,
                "std_text": "—",
                "mad_minutes": math.nan,
                "mad_text": "—",
                "mean_minutes": math.nan,
                "mean_text": "—",
                "recommendation": "Недостаточно данных для рекомендаций.",
            }
        mean = series.mean()
        std = series.std(ddof=0)
        mad = (series - mean).abs().mean()
        status, label = _classify_regularity(std)
        return {
            "status": status,
            "label": label,
            "std_minutes": float(std) if math.isfinite(std) else math.nan,
            "std_text": _format_minutes_value(std),
            "mad_minutes": float(mad) if math.isfinite(mad) else math.nan,
            "mad_text": _format_minutes_value(mad),
            "mean_minutes": float(mean) if math.isfinite(mean) else math.nan,
            "mean_text": _format_minutes(mean),
            "recommendation": _recommendation(status, metric),
        }

    result["bedtime"] = build_metric(bedtime_series, "bedtime")
    result["wakeup"] = build_metric(wake_series, "wakeup")
    result["series"] = df[["date", "bedtime_minutes_display", "wakeup_minutes", "wakeup_minutes_adjusted"]]

    return result


def _build_weekday_profile(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "date" not in df.columns:
        return pd.DataFrame()

    weekday_df = df.dropna(subset=["bedtime_minutes_raw", "wakeup_minutes_adjusted"]).copy()
    if weekday_df.empty:
        return pd.DataFrame()

    weekday_df["weekday"] = weekday_df["date"].dt.weekday

    agg = (
        weekday_df.groupby("weekday")
        .agg(
            count=("weekday", "size"),
            bedtime_minutes_raw=("bedtime_minutes_raw", "mean"),
            wakeup_minutes_raw=("wakeup_minutes_adjusted", "mean"),
        )
        .reset_index()
    )

    if agg.empty:
        return agg

    agg["weekday_label"] = agg["weekday"].map(_WEEKDAY_LABELS)
    agg = agg.sort_values("weekday")

    agg["bedtime_minutes_display"] = agg["bedtime_minutes_raw"].mod(MINUTES_IN_DAY)
    agg["wakeup_minutes_display"] = agg["wakeup_minutes_raw"].mod(MINUTES_IN_DAY)
    agg["bedtime_hours"] = agg["bedtime_minutes_raw"] / 60.0
    agg["wakeup_hours"] = agg["wakeup_minutes_raw"] / 60.0
    agg["bedtime_text"] = agg["bedtime_minutes_display"].apply(_format_minutes)
    agg["wakeup_text"] = agg["wakeup_minutes_display"].apply(_format_minutes)
    agg["sleep_duration_minutes"] = agg["wakeup_minutes_raw"] - agg["bedtime_minutes_raw"]
    agg["sleep_duration_hours"] = agg["sleep_duration_minutes"] / 60.0
    agg["sleep_duration_text"] = agg["sleep_duration_minutes"].apply(_format_duration)

    return agg[
        [
            "weekday",
            "weekday_label",
            "count",
            "bedtime_minutes_raw",
            "bedtime_minutes_display",
            "bedtime_hours",
            "bedtime_text",
            "wakeup_minutes_raw",
            "wakeup_minutes_display",
            "wakeup_hours",
            "wakeup_text",
            "sleep_duration_minutes",
            "sleep_duration_hours",
            "sleep_duration_text",
        ]
    ]


__all__ = ["compute_sleep_regularity"]
