"""Canonical Intervals wellness mapping and windowed persistence (M4, #273)."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Mapping

from config.settings import Settings
from data.database import Database, parse_cursor_date
from services.intervals_icu import IntervalsICUClient, IntervalsICUError
from services.sync_cursor import iter_chunks, resolve_window_from_cursor


@dataclass(frozen=True)
class WellnessRecord:
    """One provider-local wellness day mapped to canonical recovery metrics."""

    date: str
    hrv: dict[str, Any] = field(default_factory=dict)
    sleep: dict[str, Any] = field(default_factory=dict)
    health: dict[str, Any] = field(default_factory=dict)

    @property
    def mapped_metric_count(self) -> int:
        return sum(
            key in values
            for values, key in (
                (self.hrv, "rmssd"),
                (self.sleep, "total_sleep_minutes"),
                (self.sleep, "sleep_score"),
                (self.health, "resting_hr"),
                (self.health, "steps"),
            )
        )

    def as_payload(self) -> dict[str, Any]:
        return {
            "date": self.date,
            "hrv": dict(self.hrv),
            "sleep": dict(self.sleep),
            "health": dict(self.health),
        }


@dataclass
class WellnessSyncResult:
    """Provider-agnostic outcome for the independent wellness domain."""

    new: int = 0
    updated: int = 0
    skipped: int = 0
    changes: int = 0
    warnings: list[str] = field(default_factory=list)
    halted: bool = False
    cursor_value: str | None = None
    window_start: str = ""
    window_end: str = ""
    bootstrapped: bool = False


def _number(row: Mapping[str, Any], key: str) -> float | None:
    value = row.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"Intervals wellness {key} must be numeric, got {value!r}")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"Intervals wellness {key} must be finite")
    return result


def normalize_intervals_wellness(row: Mapping[str, Any]) -> WellnessRecord:
    """Map the bounded Intervals wellness contract without provider model leakage.

    ``id`` is a provider-local calendar date. ``hrv`` is rMSSD in milliseconds;
    ``hrvSDNN`` is deliberately ignored. Sleep stages are not invented, and
    provider readiness/CTL/ATL are never mapped into local canonical metrics.
    """
    if not isinstance(row, Mapping):
        raise TypeError("Intervals wellness row must be a mapping")
    day = parse_cursor_date(row.get("id")).isoformat()

    hrv: dict[str, Any] = {}
    rmssd = _number(row, "hrv")
    if rmssd is not None:
        if rmssd <= 0:
            raise ValueError("Intervals wellness hrv must be greater than zero")
        hrv = {"rmssd": rmssd, "rmssd_source": "intervals"}

    sleep: dict[str, Any] = {}
    seconds = _number(row, "sleepSecs")
    if seconds is not None:
        if seconds < 0:
            raise ValueError("Intervals wellness sleepSecs must not be negative")
        sleep.update(
            {
                "total_sleep_minutes": seconds / 60.0,
                "total_sleep_source": "intervals",
            }
        )
    sleep_score = _number(row, "sleepScore")
    if sleep_score is not None:
        if not 0 <= sleep_score <= 100:
            raise ValueError("Intervals wellness sleepScore must be between 0 and 100")
        sleep.update(
            {
                "sleep_score": sleep_score,
                "sleep_score_source": "intervals",
            }
        )

    health: dict[str, Any] = {}
    resting_hr = _number(row, "restingHR")
    if resting_hr is not None:
        if not resting_hr.is_integer() or not 20 <= resting_hr <= 250:
            raise ValueError("Intervals wellness restingHR must be an integer in [20, 250]")
        health = {
            "resting_hr": int(resting_hr),
            "resting_hr_source": "intervals",
        }

    steps = _number(row, "steps")
    if steps is not None:
        if not steps.is_integer() or steps < 0:
            raise ValueError(
                "Intervals wellness steps must be a nonnegative integer"
            )
        health.update(
            {
                "steps": int(steps),
                "steps_source": "intervals",
            }
        )

    return WellnessRecord(date=day, hrv=hrv, sleep=sleep, health=health)


def sync_intervals_wellness(
    database: Database,
    client: IntervalsICUClient,
    *,
    now: datetime,
    window_days: int | None = None,
    chunk_days: int = 90,
) -> WellnessSyncResult:
    """Synchronize Intervals recovery metrics with an independent clean cursor."""
    cursor_value = database.get_sync_cursor("intervals", "wellness")
    if window_days is not None:
        if (
            isinstance(window_days, bool)
            or not isinstance(window_days, int)
            or window_days <= 0
        ):
            raise ValueError("wellness window_days must be a positive int")
        if cursor_value:
            anchor = parse_cursor_date(cursor_value)
            if anchor > now.date():
                raise ValueError("wellness cursor is ahead of now")
        start, end, bootstrapped = now - timedelta(days=window_days), now, False
    else:
        start, end, bootstrapped = resolve_window_from_cursor(
            cursor_value,
            now=now,
            overlap_days=1,
            bootstrap_days=90,
        )

    result = WellnessSyncResult(
        window_start=start.date().isoformat(),
        window_end=end.date().isoformat(),
        bootstrapped=bootstrapped,
    )
    seen: set[str] = set()
    for chunk_start, chunk_end in iter_chunks(start, end, chunk_days):
        try:
            rows = client.list_wellness(chunk_start.date(), chunk_end.date())
            normalized: list[dict[str, Any]] = []
            for row in rows:
                record = normalize_intervals_wellness(row)
                if record.date in seen:
                    continue
                seen.add(record.date)
                normalized.append(record.as_payload())
        except (IntervalsICUError, TypeError, ValueError) as exc:
            result.warnings.append(f"⚠️ Intervals.icu wellness: {exc}")
            result.halted = True
            break

        counts = database.sync_wellness_batch(
            normalized,
            provider="intervals",
            cursor_value=chunk_end.date().isoformat(),
            primary_source=Settings.PRIMARY_WELLNESS_SOURCE,
        )
        result.new += (
            counts["hrv_new"] + counts["sleep_new"] + counts["health_new"]
        )
        result.updated += (
            counts["hrv_updated"]
            + counts["sleep_updated"]
            + counts["health_updated"]
        )
        result.skipped += counts["skipped"]
        result.changes += counts["changes"]

    result.cursor_value = database.get_sync_cursor("intervals", "wellness")
    return result


__all__ = [
    "WellnessRecord",
    "WellnessSyncResult",
    "normalize_intervals_wellness",
    "sync_intervals_wellness",
]
