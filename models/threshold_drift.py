"""FTP/threshold drift detection (issue #374).

Workouts are prescribed as percentages of FTP, so every target is wrong when
the FTP used by the app drifts from the athlete's current source profile.
This module compares the profile FTP (last Intervals.icu sync) against the FTP
that recent completed activities were actually scored with (`tss_ftp_used`)
and reports a warning when they differ by more than 10% — the same threshold
IntervalCoach ships (changelog 2026-07-30). ExecPlan:
docs/threshold_drift_diagnostics_execplan.md.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any


DRIFT_THRESHOLD_PCT = 10.0
RECENT_ACTIVITY_DAYS = 30


def _to_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _pct_difference(first: float, second: float) -> float:
    base = min(first, second)
    if base <= 0:
        return 0.0
    return abs(first - second) / base * 100.0


def detect_threshold_drift(database: Any) -> list[dict[str, Any]]:
    """Return drift warnings, or an empty list when there is nothing to warn about.

    A warning is emitted only when all of the following hold: an athlete
    profile exists with a positive FTP, at least one activity within the last
    30 days was scored with a positive `tss_ftp_used`, and the two values
    differ by at least `DRIFT_THRESHOLD_PCT` percent. The check is read-only
    and deterministic: no network, no plan data.
    """
    profile = database.get_athlete_profile()
    if not profile:
        return []
    profile_ftp = _to_float(profile.get("ftp"))
    if profile_ftp is None:
        return []

    today = datetime.now().date()
    rows = database.get_activities_between(
        (today - timedelta(days=RECENT_ACTIVITY_DAYS - 1)).isoformat(),
        today.isoformat(),
    )
    used_values = [
        used
        for row in rows or []
        if (used := _to_float(row.get("tss_ftp_used"))) is not None
    ]
    if not used_values:
        return []

    used_value = used_values[-1]
    pct = _pct_difference(profile_ftp, used_value)
    if pct < DRIFT_THRESHOLD_PCT:
        return []

    return [
        {
            "kind": "ftp_drift",
            "source_value": round(profile_ftp, 1),
            "used_value": round(used_value, 1),
            "pct": round(pct, 1),
            "message": (
                f"FTP источника {round(profile_ftp)} Вт, а тренировки/TSS считались "
                f"по {round(used_value)} Вт (+{round(pct)}%) — проверьте синк профиля"
            ),
        }
    ]


__all__ = ["DRIFT_THRESHOLD_PCT", "RECENT_ACTIVITY_DAYS", "detect_threshold_drift"]
