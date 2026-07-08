"""Shared readiness snapshot contract for API responses."""
from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd

from data.database import Database
from data.data_processor_phase1 import Phase1DataProcessor


PRIMARY_INPUTS = ("sleep", "hrv", "resting_hr", "training_readiness")

FACTOR_LABELS = {
    "sleep": "Сон",
    "hrv": "HRV",
    "resting_hr": "Пульс покоя",
    "training_readiness": "Garmin readiness",
    "stress": "Стресс",
}


def build_readiness_snapshot(
    db: Database,
    *,
    stale_after_days: int = 2,
) -> dict[str, Any]:
    """Build a conservative, JSON-safe readiness contract.

    This does not redesign readiness math. It wraps the existing Phase 1
    readiness calculator and adds provenance fields that API clients can trust.
    """
    try:
        sleep_df = db.get_sleep_data(36500)
        hrv_df = db.get_hrv_data(36500)
        health_df = db.get_daily_health(36500)
        training_df = db.get_training_status_history(36500)
    except Exception:
        return _unknown_snapshot(reason="Недостаточно данных readiness: не удалось прочитать локальную базу.")

    sleep_row = _latest_row(sleep_df)
    hrv_row = _latest_row(hrv_df)
    health_row = _latest_row(health_df)
    training_row = _latest_row(training_df)

    readiness = Phase1DataProcessor.calculate_comprehensive_readiness(
        sleep_row,
        hrv_row,
        health_row,
        training_row,
    )
    score = _safe_float((readiness or {}).get("readiness_score"), default=None)
    factor_scores = dict((readiness or {}).get("factor_scores") or {})

    present_inputs = _present_primary_inputs(sleep_row, hrv_row, health_row, training_row)
    missing_inputs = [key for key in PRIMARY_INPUTS if key not in present_inputs]
    completeness = round(len(present_inputs) / len(PRIMARY_INPUTS), 2)
    computed_at = _latest_date_iso(sleep_row, hrv_row, health_row, training_row)
    stale = bool(computed_at and _is_stale(computed_at, stale_after_days))

    if score is None:
        status = "unknown"
    elif stale:
        status = "stale"
    elif score < 40:
        status = "low"
    elif score < 60:
        status = "limited"
    elif score < 75:
        status = "ready"
    else:
        status = "strong"

    is_provisional = bool(
        score is None
        or stale
        or missing_inputs
        or "training_readiness" not in present_inputs
    )

    factors = _factor_payloads(
        factor_scores=factor_scores,
        sleep_row=sleep_row,
        hrv_row=hrv_row,
        health_row=health_row,
        training_row=training_row,
    )

    return {
        "score": round(score, 1) if score is not None else None,
        "status": status,
        "computed_at": computed_at,
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
    }


def _unknown_snapshot(*, reason: str) -> dict[str, Any]:
    return {
        "score": None,
        "status": "unknown",
        "computed_at": None,
        "is_provisional": True,
        "source_completeness": 0.0,
        "factors": [],
        "missing_inputs": list(PRIMARY_INPUTS),
        "stale": False,
        "reason": reason,
    }


def _latest_row(frame: pd.DataFrame | None) -> dict[str, Any]:
    if frame is None or frame.empty:
        return {}
    if "date" in frame.columns:
        try:
            return frame.sort_values("date", ascending=False).iloc[0].to_dict()
        except Exception:
            pass
    return frame.iloc[0].to_dict()


def _safe_float(value: Any, *, default: float | None = None) -> float | None:
    try:
        if value is None or pd.isna(value):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _has_number(row: dict[str, Any], key: str) -> bool:
    return _safe_float(row.get(key), default=None) is not None


def _present_primary_inputs(
    sleep_row: dict[str, Any],
    hrv_row: dict[str, Any],
    health_row: dict[str, Any],
    training_row: dict[str, Any],
) -> set[str]:
    present: set[str] = set()
    if _has_number(sleep_row, "sleep_score"):
        present.add("sleep")
    if _has_number(hrv_row, "rmssd"):
        present.add("hrv")
    if _has_number(health_row, "resting_hr"):
        present.add("resting_hr")
    if _has_number(training_row, "training_readiness"):
        present.add("training_readiness")
    return present


def _latest_date_iso(*rows: dict[str, Any]) -> str | None:
    values: list[pd.Timestamp] = []
    for row in rows:
        if not row or row.get("date") is None:
            continue
        parsed = pd.to_datetime(row.get("date"), errors="coerce")
        if pd.isna(parsed):
            continue
        values.append(parsed)
    if not values:
        return None
    return max(values).date().isoformat()


def _is_stale(value: str, stale_after_days: int) -> bool:
    try:
        parsed = datetime.fromisoformat(str(value)[:10])
    except ValueError:
        return False
    return (datetime.now().date() - parsed.date()).days > stale_after_days


def _factor_payloads(
    *,
    factor_scores: dict[str, Any],
    sleep_row: dict[str, Any],
    hrv_row: dict[str, Any],
    health_row: dict[str, Any],
    training_row: dict[str, Any],
) -> list[dict[str, Any]]:
    factors: list[dict[str, Any]] = []
    raw_values = {
        "sleep": sleep_row.get("sleep_score"),
        "hrv": hrv_row.get("rmssd"),
        "resting_hr": health_row.get("resting_hr"),
        "training_readiness": training_row.get("training_readiness"),
        "stress": hrv_row.get("stress_score"),
    }
    sources = {
        "sleep": "sleep_data.sleep_score",
        "hrv": "hrv_data.rmssd",
        "resting_hr": "daily_health.resting_hr",
        "training_readiness": "training_status.training_readiness",
        "stress": "hrv_data.stress_score",
    }

    for key in ("sleep", "hrv", "resting_hr", "training_readiness", "stress"):
        score = _safe_float(factor_scores.get(key), default=None)
        raw_value = _safe_float(raw_values.get(key), default=None)
        if score is None and raw_value is None:
            continue
        factors.append(
            {
                "key": key,
                "label": FACTOR_LABELS.get(key, key),
                "score": round(score, 1) if score is not None else None,
                "raw_value": round(raw_value, 1) if raw_value is not None else None,
                "source": sources[key],
            }
        )
    return factors


def _reason(
    *,
    score: float | None,
    stale: bool,
    missing_inputs: list[str],
    computed_at: str | None,
) -> str:
    if score is None:
        return "Недостаточно данных для расчёта readiness snapshot."
    if stale:
        return f"Readiness рассчитан по устаревшим данным от {computed_at}."
    if missing_inputs:
        labels = ", ".join(FACTOR_LABELS.get(key, key) for key in missing_inputs)
        return f"Readiness рассчитан по частичным данным; отсутствуют: {labels}."
    return "Readiness рассчитан по полному набору основных recovery-сигналов."
