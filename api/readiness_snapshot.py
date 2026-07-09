"""Shared readiness snapshot contract for API responses.

Расчёт готовности делегируется models/readiness.py::compute_readiness_today
(единая точка fusion: личные базлайны + TSB, issue #139). Этот модуль отвечает
только за JSON-контракт: provenance, staleness, completeness. Ключи контракта
стабильны (см. tests/smoke/test_readiness_snapshot_contract.py); новые поля
(drivers, tsb, confidence, baseline/deviation/evidence в факторах) — аддитивны.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd

from data.database import Database
from models.readiness import LOAD_METRICS_WINDOW_DAYS, compute_readiness_today


PRIMARY_INPUTS = ("sleep", "hrv", "resting_hr", "training_readiness")

FACTOR_LABELS = {
    "sleep": "Сон",
    "hrv": "HRV",
    "resting_hr": "Пульс покоя",
    "training_readiness": "Garmin readiness",
    "stress": "Стресс",
    "tsb": "Баланс нагрузки (TSB)",
}


def build_readiness_snapshot(
    db: Database,
    *,
    stale_after_days: int = 2,
) -> dict[str, Any]:
    """Build a conservative, JSON-safe readiness contract."""
    try:
        sleep_df = db.get_sleep_data(36500)
        hrv_df = db.get_hrv_data(36500)
        health_df = db.get_daily_health(36500)
        training_df = db.get_training_status_history(36500)
        activities_df = db.get_activities(LOAD_METRICS_WINDOW_DAYS)
    except Exception:
        return _unknown_snapshot(reason="Недостаточно данных readiness: не удалось прочитать локальную базу.")

    # max_value_age_days=None: score считаем даже по старым данным,
    # staleness — ответственность этого контракта (поля stale/status ниже).
    result = compute_readiness_today(
        sleep_df,
        hrv_df,
        health_df,
        training_df,
        activities_df,
        max_value_age_days=None,
    )

    score = result["score"]
    if score is None:
        return _unknown_snapshot(reason="Недостаточно данных для расчёта readiness snapshot.")

    computed_at = result["as_of_date"]
    stale = bool(computed_at and _is_stale(computed_at, stale_after_days))

    factor_keys = {f["key"] for f in result["factors"]}
    missing_inputs = [key for key in PRIMARY_INPUTS if key not in factor_keys]
    completeness = round(
        len([k for k in PRIMARY_INPUTS if k in factor_keys]) / len(PRIMARY_INPUTS), 2
    )

    status = "stale" if stale else result["status"]
    is_provisional = bool(stale or missing_inputs or "training_readiness" not in factor_keys)

    factors = [dict(f) for f in result["factors"]]
    stress_factor = _stress_reference_factor(hrv_df)
    if stress_factor is not None:
        factors.append(stress_factor)

    return {
        "score": score,
        "status": status,
        "computed_at": computed_at,
        "is_provisional": is_provisional,
        "source_completeness": completeness,
        "factors": factors,
        "missing_inputs": missing_inputs,
        "stale": stale,
        "reason": _reason(score=score, stale=stale, missing_inputs=missing_inputs, computed_at=computed_at),
        # Аддитивные поля контракта (issue #139):
        "drivers": result["drivers"],
        "tsb": result["tsb"],
        "confidence": result["confidence"],
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
        "drivers": [],
        "tsb": {"ctl": None, "atl": None, "tsb": None, "window_days": LOAD_METRICS_WINDOW_DAYS},
        "confidence": 0.0,
    }


def _stress_reference_factor(hrv_df: pd.DataFrame | None) -> dict[str, Any] | None:
    """Стресс — справочный фактор (в fusion не входит: тот же источник, что HRV)."""
    if hrv_df is None or not isinstance(hrv_df, pd.DataFrame) or hrv_df.empty:
        return None
    if "stress_score" not in hrv_df.columns or "date" not in hrv_df.columns:
        return None
    try:
        latest = hrv_df.sort_values("date", ascending=False).iloc[0]
        raw = latest.get("stress_score")
        if raw is None or pd.isna(raw):
            return None
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
            "as_of": None,
        }
    except Exception:
        return None


def _is_stale(value: str, stale_after_days: int) -> bool:
    try:
        parsed = datetime.fromisoformat(str(value)[:10])
    except ValueError:
        return False
    return (datetime.now().date() - parsed.date()).days > stale_after_days


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
