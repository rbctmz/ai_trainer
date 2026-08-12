"""Unified recovery/load signal assembly.

The engine is intentionally a thin contract layer over existing models. It
does not replace Banister, HRV, or Phase 1 readiness math; it calls them and
normalizes their outputs so API/web and Streamlit fallback can consume the same
signal semantics.
"""
from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd

from models.banister import BanisterModel, tsb_zone


SIGNALS_SOURCE = "models.signals_engine"

_TONE_SEVERITY = {"success": 0, "neutral": 1, "warning": 2, "danger": 3}


def tone_severity(tone: str | None) -> int:
    return _TONE_SEVERITY.get(str(tone or "neutral"), 1)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or pd.isna(value):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _frame_or_empty(frame: pd.DataFrame | None) -> pd.DataFrame:
    return frame if isinstance(frame, pd.DataFrame) else pd.DataFrame()


def _latest_row(frame: pd.DataFrame | None) -> dict[str, Any]:
    df = _frame_or_empty(frame)
    if df.empty:
        return {}
    if "date" in df.columns:
        try:
            return df.sort_values("date", ascending=False).iloc[0].to_dict()
        except Exception:
            pass
    return df.iloc[0].to_dict()


def _without_multisport_envelopes(frame: pd.DataFrame) -> pd.DataFrame:
    """Drop a multisport summary when its detailed activities are present.

    Garmin can expose a ``multi_sport`` envelope while Intervals.icu exposes
    the swim/bike/run legs for the same day.  Both carry TSS, so keeping the
    envelope would count the session twice.  A standalone envelope is retained
    because it may be the only available load when a provider sync is partial.
    """
    if frame.empty or "sport" not in frame.columns or "date" not in frame.columns:
        return frame

    sport_keys = (
        frame["sport"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.lower()
        .str.replace(r"[\s-]+", "_", regex=True)
    )
    envelopes = sport_keys.isin({"multi_sport", "multisport"})
    if not envelopes.any():
        return frame

    activity_dates = pd.to_datetime(frame["date"], errors="coerce").dt.normalize()
    detailed_dates = activity_dates[~envelopes & sport_keys.ne("")].dropna()
    superseded = envelopes & activity_dates.isin(detailed_dates)
    return frame.loc[~superseded]


def training_load_metrics(
    activities_df: pd.DataFrame | None,
    *,
    as_of: date | None = None,
) -> dict[str, Any]:
    """Return current CTL/ATL/TSB by wrapping the canonical Banister model.

    Issue #231: with ``as_of`` set, rest days after the last activity are
    zero-filled through the anchor before the EWMA, so CTL/ATL/TSB are a
    "today" signal — matching the canonical readiness snapshot
    (``models/readiness._tsb_metrics``). Without it the model freezes at the
    last workout date (second instance of #139). ``as_of`` defaults to None to
    keep every existing caller's behavior unchanged.
    """
    df = _without_multisport_envelopes(_frame_or_empty(activities_df))
    if df.empty:
        return {
            "ctl": 0.0,
            "atl": 0.0,
            "tsb": 0.0,
            "fitness": 0.0,
            "fatigue": 0.0,
            "form": "Недостаточно данных",
        }

    if as_of is not None:
        frame = df[["date", "tss"]].copy()
        frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
        frame["tss"] = pd.to_numeric(frame["tss"], errors="coerce").fillna(0.0)
        frame = frame.dropna(subset=["date"])
        anchor_ts = pd.Timestamp(as_of)
        frame = frame[frame["date"] <= anchor_ts]
        if not frame.empty:
            daily = frame.groupby(frame["date"].dt.normalize())["tss"].sum().sort_index()
            date_range = pd.date_range(start=daily.index.min(), end=anchor_ts, freq="D")
            daily = daily.reindex(date_range, fill_value=0.0)
            return BanisterModel().get_current_metrics(daily.tolist(), daily.index.tolist())

    tss_data: list[float] = []
    dates: list[Any] = []
    for _, row in df.iterrows():
        tss_data.append(_safe_float(row.get("tss"), 0.0))
        dates.append(row.get("date"))

    return BanisterModel().get_current_metrics(tss_data, dates)


def _training_status_frame(training_status: Any) -> pd.DataFrame | None:
    """Normalize training_status (DataFrame или dict) для fusion-модели."""
    if isinstance(training_status, pd.DataFrame):
        return training_status
    if isinstance(training_status, dict) and training_status:
        value = training_status.get("training_readiness")
        if value is None:
            value = training_status.get("readiness")
        if value is None:
            return None
        row = {"training_readiness": value}
        row["date"] = training_status.get("date") or pd.Timestamp.now().normalize()
        return pd.DataFrame([row])
    return None


def _readiness_signal(
    sleep_df: pd.DataFrame | None,
    hrv_df: pd.DataFrame | None,
    training_status: Any = None,
    activities_df: pd.DataFrame | None = None,
    health_df: pd.DataFrame | None = None,
) -> dict[str, Any]:
    # Единая точка расчёта готовности (issue #139): Garmin readiness — один из
    # факторов fusion, а не override; личные базлайны и TSB внутри модели.
    from models.readiness import compute_readiness_today

    fused = compute_readiness_today(
        sleep_df,
        hrv_df,
        health_df,
        _training_status_frame(training_status),
        activities_df,
        max_value_age_days=None,
    )
    value = fused["score"]
    source = "fusion" if value is not None else "none"
    drivers = fused["drivers"]

    if value is None:
        tone = "neutral"
        label = "Нет данных"
    elif value < 40:
        tone = "danger"
        label = "Низкая готовность"
    elif value < 60:
        tone = "warning"
        label = "Ограниченная готовность"
    elif value >= 75:
        tone = "success"
        label = "Готов к работе"
    else:
        tone = "neutral"
        label = "Контролируемая готовность"

    return {
        "value": round(value, 1) if value is not None else None,
        "label": label,
        "tone": tone,
        "severity": tone_severity(tone),
        "source": source,
        "drivers": drivers,
    }


def _hrv_signal(hrv_df: pd.DataFrame | None) -> dict[str, Any]:
    df = _frame_or_empty(hrv_df)
    if df.empty or "rmssd" not in df.columns:
        return {
            "value": None,
            "baseline": None,
            "label": "Нет данных",
            "tone": "neutral",
            "severity": tone_severity("neutral"),
            "suppressed": False,
        }

    latest_hrv = _safe_float(_latest_row(df).get("rmssd"), 0.0)
    baseline = _safe_float(df["rmssd"].dropna().mean(), 0.0)
    suppressed = bool(baseline > 0 and latest_hrv < baseline * 0.8)
    if suppressed or latest_hrv < 30:
        tone = "warning"
        label = "Низкий HRV"
    elif latest_hrv > 50:
        tone = "success"
        label = "Отличный HRV"
    else:
        tone = "neutral"
        label = "HRV в рабочем диапазоне"

    advanced: dict[str, Any] | None = None
    try:
        from models.hrv_analyzer import HRVAnalyzer

        score, info = HRVAnalyzer.recovery_score_advanced(df)
        if score is not None:
            advanced = {"score": round(float(score), 1), "info": info}
    except Exception:
        advanced = None

    return {
        "value": round(latest_hrv, 1),
        "baseline": round(baseline, 1) if baseline else None,
        "label": label,
        "tone": tone,
        "severity": tone_severity(tone),
        "suppressed": suppressed,
        "advanced": advanced,
    }


def _sleep_signal(sleep_df: pd.DataFrame | None) -> dict[str, Any]:
    row = _latest_row(sleep_df)
    total_mins = _safe_float(row.get("total_sleep_minutes"), 0.0)
    hours = round(total_mins / 60, 1) if total_mins > 0 else None
    score = row.get("sleep_score")
    sleep_score = _safe_float(score, 0.0) if score is not None else None
    score_source = row.get("sleep_score_source")
    if score_source is None or pd.isna(score_source) or not str(score_source).strip():
        score_source = "legacy_unknown"
    else:
        score_source = str(score_source).strip()

    if hours is None:
        tone = "neutral"
        label = "Нет данных"
    elif hours < 6.0:
        tone = "warning"
        label = "Короткий сон"
    elif sleep_score is not None and sleep_score < 55:
        tone = "warning"
        label = "Сон требует внимания"
    else:
        tone = "neutral"
        label = "Сон в норме"

    return {
        "hours": hours,
        "score": round(sleep_score, 1) if sleep_score is not None else None,
        "score_source": score_source,
        "label": label,
        "tone": tone,
        "severity": tone_severity(tone),
    }


def _load_signal(metrics: dict[str, Any]) -> dict[str, Any]:
    tsb = _safe_float(metrics.get("tsb"), 0.0)
    zone = tsb_zone(tsb)
    return {
        "ctl": round(_safe_float(metrics.get("ctl"), 0.0), 1),
        "atl": round(_safe_float(metrics.get("atl"), 0.0), 1),
        "tsb": round(tsb, 1),
        "form": metrics.get("form") or zone["label"],
        "label": zone["label"],
        "tone": zone["tone"],
        "clause": zone["clause"],
        "severity": tone_severity(zone["tone"]),
    }


def _recommendations_for_signals(
    load: dict[str, Any],
    hrv: dict[str, Any],
) -> tuple[str | None, str | None, list[dict[str, str]]]:
    recommendations: list[dict[str, str]] = []
    critical_status: str | None = None
    critical_action: str | None = None
    tsb = _safe_float(load.get("tsb"), 0.0)

    if tsb < -30:
        critical_status = "Критическое переутомление"
        critical_action = "Полный отдых 2-3 дня без тренировок"
        recommendations.extend(
            [
                {
                    "title": "🚨 Немедленный отдых",
                    "description": "TSB критически низкий (-30+). Организм в состоянии переутомления.",
                    "priority": "high",
                },
                {
                    "title": "😴 Качество сна",
                    "description": "Увеличьте сон до 8-9 часов, соблюдайте режим.",
                    "priority": "high",
                },
                {
                    "title": "💧 Восстановление",
                    "description": "Массаж, баня, легкие прогулки. Никаких интенсивных нагрузок.",
                    "priority": "medium",
                },
            ]
        )
    elif tsb < -20:
        critical_status = "Сильная усталость"
        critical_action = "Только легкие восстановительные тренировки в Зоне 1"
        recommendations.extend(
            [
                {
                    "title": "🔄 Активное восстановление",
                    "description": "TSB -20 до -30. Только тренировки в аэробной зоне 1.",
                    "priority": "high",
                },
                {
                    "title": "🍎 Питание",
                    "description": "Увеличьте потребление белка и углеводов для восстановления.",
                    "priority": "medium",
                },
            ]
        )
    elif tsb > 5:
        recommendations.extend(
            [
                {
                    "title": "🚀 Пиковая форма!",
                    "description": "TSB выше +5. Отличное время для соревнований или тестов.",
                    "priority": "low",
                },
                {
                    "title": "🎯 Интенсивные тренировки",
                    "description": "Можно проводить FTP-тесты, интервалы, темповые работы.",
                    "priority": "low",
                },
            ]
        )
    else:
        recommendations.append(
            {
                "title": "💪 Стандартный режим",
                "description": "TSB в норме. Поддерживайте текущий объем тренировок.",
                "priority": "low",
            }
        )

    if hrv.get("suppressed") and critical_status is None:
        critical_status = "Низкий HRV - стресс или недовосстановление"
        critical_action = "Проверьте качество сна и уровень стресса"
        recommendations.append(
            {
                "title": "💓 Низкий HRV",
                "description": (
                    f"HRV ({_safe_float(hrv.get('value')):.1f}) ниже базового "
                    f"({_safe_float(hrv.get('baseline')):.1f}) на 20%+"
                ),
                "priority": "medium",
            }
        )

    hrv_value = hrv.get("value")
    if hrv_value is not None and _safe_float(hrv_value) < 30:
        recommendations.append(
            {
                "title": "⚠️ HRV требует внимания",
                "description": "Низкая вариабельность сердечного ритма. Фокус на восстановлении.",
                "priority": "medium",
            }
        )
    elif hrv_value is not None and _safe_float(hrv_value) > 50:
        recommendations.append(
            {
                "title": "✨ Отличный HRV",
                "description": "Высокая вариабельность - организм готов к нагрузкам.",
                "priority": "low",
            }
        )

    return critical_status, critical_action, recommendations


def _state_signal(
    load: dict[str, Any],
    readiness: dict[str, Any],
    critical_status: str | None,
) -> dict[str, Any]:
    tsb = _safe_float(load.get("tsb"), 0.0)
    readiness_value = readiness.get("value")
    readiness_number = _safe_float(readiness_value, 0.0)

    if critical_status:
        label = critical_status
        tone = "danger"
    elif readiness_number >= 75 and tsb > -10:
        label = "Готов к работе"
        tone = "success"
    elif tsb < -20:
        label = "Нужна разгрузка"
        tone = "warning"
    else:
        label = "Контролируемая нагрузка"
        tone = "neutral"

    return {"label": label, "tone": tone, "severity": tone_severity(tone)}


def assemble_signals(
    activities_df: pd.DataFrame | None = None,
    hrv_df: pd.DataFrame | None = None,
    sleep_df: pd.DataFrame | None = None,
    training_status: Any = None,
    health_df: pd.DataFrame | None = None,
    as_of: date | None = None,
) -> dict[str, Any]:
    """Assemble normalized load/recovery/readiness signals.

    Issue #231: pass ``as_of`` to anchor CTL/ATL/TSB to today (rest days decay
    after the last workout) instead of freezing at the last activity date.
    """
    metrics = training_load_metrics(activities_df, as_of=as_of)
    load = _load_signal(metrics)
    hrv = _hrv_signal(hrv_df)
    sleep = _sleep_signal(sleep_df)
    readiness = _readiness_signal(sleep_df, hrv_df, training_status, activities_df, health_df)
    critical_status, critical_action, recommendations = _recommendations_for_signals(load, hrv)
    state = _state_signal(load, readiness, critical_status)

    return {
        "source": SIGNALS_SOURCE,
        "load": load,
        "hrv": hrv,
        "sleep": sleep,
        "readiness": readiness,
        "state": state,
        "critical": {
            "status": critical_status,
            "action": critical_action,
        },
        "recommendations": recommendations,
    }


def current_status_from_signals(signals: dict[str, Any]) -> dict[str, Any]:
    """Return the historical dashboard current_status shape from signals."""
    load = signals.get("load", {}) or {}
    hrv = signals.get("hrv", {}) or {}
    readiness = signals.get("readiness", {}) or {}
    critical = signals.get("critical", {}) or {}
    state = signals.get("state", {}) or {}
    advanced = hrv.get("advanced")

    status: dict[str, Any] = {
        "critical_status": critical.get("status"),
        "critical_action": critical.get("action"),
        "recommendations": list(signals.get("recommendations", []) or []),
        "tsb": _safe_float(load.get("tsb"), 0.0),
        "hrv": _safe_float(hrv.get("value"), 0.0),
        "readiness": _safe_float(readiness.get("value"), 0.0),
        "ctl": _safe_float(load.get("ctl"), 0.0),
        "atl": _safe_float(load.get("atl"), 0.0),
        "trends": {},
        "signals": signals,
        "state_label": state.get("label"),
        "tone": state.get("tone"),
    }
    if advanced:
        status["hrv_advanced"] = advanced
    return status
