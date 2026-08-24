"""Shadow bike power+HR quality-pair collection (#444 S1).

Features are derived from canonical activity aggregates plus the athlete
profile history only — no raw per-second series is stored (policy #390).
The canonical ingest stays authoritative: pair recording is best-effort and
never fails the ingest itself (see ``services/activity_ingest``).
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from config.settings import Settings
from data.data_processor import resolve_ftp_for_activity
from utils.product_semantics import normalize_sport_key


ZONE_COLUMNS = (
    "hr_zone_minutes_z1",
    "hr_zone_minutes_z2",
    "hr_zone_minutes_z3",
    "hr_zone_minutes_z4",
    "hr_zone_minutes_z5",
)
ZONE_SECONDS_KEYS = (
    "hr_time_in_zone_1_seconds",
    "hr_time_in_zone_2_seconds",
    "hr_time_in_zone_3_seconds",
    "hr_time_in_zone_4_seconds",
    "hr_time_in_zone_5_seconds",
)


def _f(value) -> Optional[float]:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number else None  # NaN guard


def build_bike_hr_pair(row: dict, ftp_on_date, ftp_verified: bool, rhr, lthr):
    """Derive shadow pair features from a canonical activity row.

    Returns None when the row is not a quality pair: not a bike sport, or no
    positive power, or no positive HR, or no usable duration/date.
    """
    if normalize_sport_key(str(row.get("sport") or "")) != "bike":
        return None
    date_text = str(row.get("date") or "")[:10]
    moving = _f(row.get("moving_duration_minutes")) or _f(row.get("duration_minutes"))
    avg_hr = _f(row.get("avg_hr"))
    power = _f(row.get("normalized_power")) or _f(row.get("avg_power"))
    if not date_text or not moving or moving <= 0 or not avg_hr or avg_hr <= 0:
        return None
    if not power or power <= 0:
        return None

    zone_seconds = [_f(row.get(key)) for key in ZONE_SECONDS_KEYS]
    zone_minutes = [
        None if seconds is None else round(seconds / 60.0, 3)
        for seconds in zone_seconds
    ]
    coverage = None
    if all(minutes is not None for minutes in zone_minutes):
        coverage = round(sum(zone_minutes) / moving * 100.0, 3)

    return {
        "activity_id": row.get("activity_id"),
        "date": date_text,
        "sport": row.get("sport"),
        "moving_minutes": round(moving, 3),
        "avg_hr": avg_hr,
        "normalized_power": _f(row.get("normalized_power")),
        "avg_power": _f(row.get("avg_power")),
        **{column: zone_minutes[i] for i, column in enumerate(ZONE_COLUMNS)},
        "ftp_on_date": ftp_on_date,
        "ftp_verified": 1 if ftp_verified else 0,
        "rhr": rhr,
        "lthr": lthr,
        "zone_coverage_pct": coverage,
    }


def record_bike_hr_pair(database, row: dict) -> bool:
    """Record one shadow pair from a canonical activity row (best-effort).

    Returns True when a pair row was upserted, False when skipped. Raises on
    storage failure so the ingest hook can swallow it without failing the
    canonical write.
    """
    date_text = str(row.get("date") or "")[:10]
    try:
        activity_day = datetime.strptime(date_text, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        activity_day = None

    history = database.get_athlete_ftp_history()
    get_timeline = getattr(database, "get_athlete_ftp_timeline", None)
    timeline = get_timeline() if callable(get_timeline) else []
    ftp_on_date = None
    ftp_verified = False
    if history and activity_day is not None:
        ftp_on_date, ftp_verified = resolve_ftp_for_activity(
            history,
            timeline,
            activity_day,
            activity_started_at_utc=row.get("started_at_utc"),
        )

    profile = database.get_athlete_profile() or {}
    lthr = profile.get("lthr") or Settings.USER_LTHR
    rhr = database.get_rhr_near(date_text) if activity_day is not None else None

    pair = build_bike_hr_pair(row, ftp_on_date, ftp_verified, rhr, lthr)
    if pair is None:
        return False
    database.upsert_bike_hr_pair(pair)
    return True
