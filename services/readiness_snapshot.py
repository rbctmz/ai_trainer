"""Headless, historically bounded readiness snapshot builder.

All product surfaces use this module.  ``api.readiness_snapshot`` remains a
compatibility import only, so API code contains no private business rules.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

import pandas as pd

from data.database import Database
from models.readiness import LOAD_METRICS_WINDOW_DAYS, compute_readiness_today
from models.recovery_response import READINESS_SNAPSHOT_RULE_VERSION


PRIMARY_INPUTS = ("sleep", "hrv", "resting_hr", "training_readiness")
FACTOR_LABELS = {
    "sleep": "Сон",
    "hrv": "HRV",
    "resting_hr": "Пульс покоя",
    "training_readiness": "Garmin readiness",
    "stress": "Стресс",
    "tsb": "Баланс нагрузки (TSB)",
}


def _bounded(frame: pd.DataFrame | None, as_of: date) -> pd.DataFrame | None:
    """Return only rows observable on or before ``as_of``."""
    if frame is None or not isinstance(frame, pd.DataFrame) or frame.empty:
        return frame
    if "date" not in frame.columns:
        return frame.iloc[0:0].copy()
    result = frame.copy()
    parsed = pd.to_datetime(result["date"], errors="coerce")
    return result.loc[parsed.notna() & (parsed.dt.date <= as_of)].copy()


def build_readiness_snapshot(
    db: Database,
    *,
    stale_after_days: int = 2,
    as_of: date | None = None,
    observed_at_utc: datetime | None = None,
) -> dict[str, Any]:
    """Build the canonical JSON-safe readiness fact without look-ahead."""
    anchor = as_of or datetime.now().date()
    observed = observed_at_utc or datetime.now(timezone.utc)
    if observed.tzinfo is None:
        raise ValueError("observed_at_utc must be timezone-aware")
    observed_text = observed.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )
    try:
        sleep_df = _bounded(db.get_sleep_data(36500), anchor)
        hrv_df = _bounded(db.get_hrv_data(36500), anchor)
        health_df = _bounded(db.get_daily_health(36500), anchor)
        training_df = _bounded(db.get_training_status_history(36500), anchor)
        activity_rows = db.get_activities_between(
            (anchor - timedelta(days=LOAD_METRICS_WINDOW_DAYS - 1)).isoformat(),
            anchor.isoformat(),
        )
        activities_df = _bounded(pd.DataFrame(activity_rows), anchor)
    except Exception:
        return _unknown_snapshot(
            reason="Недостаточно данных readiness: не удалось прочитать локальную базу.",
            anchor=anchor,
            observed_at_utc=observed_text,
        )

    result = compute_readiness_today(
        sleep_df,
        hrv_df,
        health_df,
        training_df,
        activities_df,
        today=anchor,
        max_value_age_days=None,
    )
    score = result["score"]
    if score is None:
        return _unknown_snapshot(
            reason="Недостаточно данных для расчёта readiness snapshot.",
            anchor=anchor,
            observed_at_utc=observed_text,
        )

    computed_at = result["as_of_date"]
    stale = bool(computed_at and _is_stale(computed_at, stale_after_days, anchor=anchor))
    factor_keys = {factor["key"] for factor in result["factors"]}
    missing_inputs = [key for key in PRIMARY_INPUTS if key not in factor_keys]
    completeness = round(
        len([key for key in PRIMARY_INPUTS if key in factor_keys]) / len(PRIMARY_INPUTS), 2
    )
    status = "stale" if stale else result["status"]
    is_provisional = bool(stale or missing_inputs or "training_readiness" not in factor_keys)
    factors = [dict(factor) for factor in result["factors"]]
    stress_factor = _stress_reference_factor(hrv_df)
    if stress_factor is not None:
        factors.append(stress_factor)
    tsb = dict(result["tsb"])
    tsb.setdefault("as_of", anchor.isoformat())

    provenance = {
        "as_of_date": anchor.isoformat(),
        "observed_at_utc": observed_text,
        "sources": {
            "sleep": _latest_date(sleep_df),
            "hrv": _latest_date(hrv_df),
            "daily_health": _latest_date(health_df),
            "training_status": _latest_date(training_df),
            "activities": _latest_date(activities_df),
        },
    }
    return {
        "score": score,
        "status": status,
        "computed_at": computed_at,
        "as_of_date": anchor.isoformat(),
        "observed_at_utc": observed_text,
        "rule_version": READINESS_SNAPSHOT_RULE_VERSION,
        "is_provisional": is_provisional,
        "source_completeness": completeness,
        "factors": factors,
        "missing_inputs": missing_inputs,
        "stale": stale,
        "reason": _reason(
            score=score,
            stale=stale,
            missing_inputs=missing_inputs,
            computed_at=computed_at,
        ),
        "drivers": result["drivers"],
        "tsb": tsb,
        "confidence": result["confidence"],
        "input_provenance": provenance,
    }


def _unknown_snapshot(*, reason: str, anchor: date, observed_at_utc: str) -> dict[str, Any]:
    return {
        "score": None,
        "status": "unknown",
        "computed_at": None,
        "as_of_date": anchor.isoformat(),
        "observed_at_utc": observed_at_utc,
        "rule_version": READINESS_SNAPSHOT_RULE_VERSION,
        "is_provisional": True,
        "source_completeness": 0.0,
        "factors": [],
        "missing_inputs": list(PRIMARY_INPUTS),
        "stale": False,
        "reason": reason,
        "drivers": [],
        "tsb": {
            "ctl": None,
            "atl": None,
            "tsb": None,
            "window_days": LOAD_METRICS_WINDOW_DAYS,
            "as_of": anchor.isoformat(),
        },
        "confidence": 0.0,
        "input_provenance": {
            "as_of_date": anchor.isoformat(),
            "observed_at_utc": observed_at_utc,
            "sources": {},
        },
    }


def _latest_date(frame: pd.DataFrame | None) -> str | None:
    if frame is None or not isinstance(frame, pd.DataFrame) or frame.empty or "date" not in frame:
        return None
    parsed = pd.to_datetime(frame["date"], errors="coerce").dropna()
    return parsed.max().date().isoformat() if not parsed.empty else None


def _stress_reference_factor(hrv_df: pd.DataFrame | None) -> dict[str, Any] | None:
    if hrv_df is None or not isinstance(hrv_df, pd.DataFrame) or hrv_df.empty:
        return None
    if "stress_score" not in hrv_df.columns or "date" not in hrv_df.columns:
        return None
    try:
        latest = hrv_df.assign(_date=pd.to_datetime(hrv_df["date"], errors="coerce")).sort_values(
            "_date", ascending=False
        ).iloc[0]
        raw = latest.get("stress_score")
        if raw is None or pd.isna(raw) or pd.isna(latest.get("_date")):
            return None
        source_date = latest["_date"].date().isoformat()
        return {
            "key": "stress",
            "label": FACTOR_LABELS["stress"],
            "score": None,
            "weight": None,
            "raw_value": round(float(raw), 1),
            "baseline": None,
            "deviation": None,
            "evidence": f"Стресс {float(raw):.0f}/100 (справочно, в fusion не входит)",
            "source": "hrv_data.stress_score",
            "stale_input": False,
            "as_of": source_date,
        }
    except Exception:
        return None


def _is_stale(value: str, stale_after_days: int, *, anchor: date) -> bool:
    try:
        parsed = datetime.fromisoformat(str(value)[:10]).date()
    except ValueError:
        return False
    return (anchor - parsed).days > stale_after_days


def _reason(
    *, score: float | None, stale: bool, missing_inputs: list[str], computed_at: str | None
) -> str:
    if score is None:
        return "Недостаточно данных для расчёта readiness snapshot."
    if stale:
        return f"Readiness рассчитан по устаревшим данным от {computed_at}."
    if missing_inputs:
        labels = ", ".join(FACTOR_LABELS.get(key, key) for key in missing_inputs)
        return f"Readiness рассчитан по частичным данным; отсутствуют: {labels}."
    return "Readiness рассчитан по полному набору основных recovery-сигналов."
