"""Единый сигнал «готовность на сегодня» (issue #139).

Единственная точка расчёта готовности спортсмена: факторы оцениваются по
отклонению от личных базлайнов (within-athlete trends, not absolutes), TSB
участвует как фактор на стабильном окне, Garmin readiness — один из входов,
а не override. Детали и математика — docs/readiness_today_execplan.md.

Функция чистая: принимает DataFrame'ы, в БД не ходит — потребители
(api/readiness_snapshot.py, models/signals_engine.py, будущий детектор
конфликта готовность×сессия) сами решают, какие данные подать.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import pandas as pd

from models.banister import BanisterModel
from utils.athlete_time import athlete_local_date


# Стабильное окно расчёта CTL/ATL/TSB (issue #134): метрики не должны зависеть
# от того, за сколько дней запрошен отчёт. Каноническое место константы —
# здесь; models/ai_tools.py реэкспортирует её как COACH_LOAD_METRICS_WINDOW_DAYS.
LOAD_METRICS_WINDOW_DAYS = 90

# Личная норма = среднее за 28 завершённых дней (сегодняшний неполный день
# в базлайн не входит — семантика issue #126).
BASELINE_WINDOW_DAYS = 28
MIN_BASELINE_SAMPLES = 5

# Значение старше 2 дней считаем отставшим (но всё ещё пригодным с пометкой).
STALE_AFTER_DAYS = 2

# --- Observation provenance и intervention eligibility (issue #557) ---------
# Наличие строки в базе и наличие *измерения за сегодня* — разные факты:
# вовлекать план можно только по подтверждённо сегодняшнему primary-измерению.
OBSERVATION_CONFIRMED_TODAY = "confirmed_today"
OBSERVATION_OUTDATED = "outdated"
OBSERVATION_UNVERIFIED = "unverified"
OBSERVATION_MISSING = "missing"
# Измерение, датированное позже anchor-даты, не доказывает сегодняшнее состояние:
# это не «свежо», а недостоверно (fail closed).
OBSERVATION_INVALID = "invalid"

# Первичные recovery-измерения: actionable-вмешательство требует хотя бы одного
# подтверждённо сегодняшнего (AC2 issue #557).
PRIMARY_RECOVERY_KEYS: tuple[str, ...] = ("sleep", "hrv", "resting_hr")

EVIDENCE_KIND_MEASUREMENT = "measurement"
EVIDENCE_KIND_DERIVED_STATE = "derived_state"

# Provider-колонки с датой измерения (заполняются ingest'ом в milestone M3).
# Измерение без них не может доказать, когда оно сделано, поэтому остаётся
# описательным: значение показывается с пометкой, но не влияет на вмешательство.
OBSERVATION_DATE_COLUMNS: dict[str, str] = {
    "hrv": "rmssd_observed_at",
    "resting_hr": "resting_hr_observed_at",
    "training_readiness": "training_readiness_observed_at",
}

# Сон имеет две метрики с независимой provenance: `_sleep_factor` предпочитает
# score, и дата измерения обязана принадлежать именно той метрике, которая
# победила (issue #557 review P1).
SLEEP_SCORE_OBSERVED_COLUMN = "sleep_score_observed_at"
SLEEP_DURATION_OBSERVED_COLUMN = "total_sleep_observed_at"

INTERVENTION_BLOCKED_NO_PRIMARY = "no_confirmed_today_primary_recovery_measurement"
INTERVENTION_BLOCKED_NO_ELIGIBLE = "no_intervention_eligible_factors"

INELIGIBLE_REASON_UNVERIFIED = "observation_date_unverified"
INELIGIBLE_REASON_OUTDATED = "observation_outdated"
INELIGIBLE_REASON_INVALID_OBSERVATION = "observation_in_future"

FACTOR_WEIGHTS: dict[str, float] = {
    "hrv": 0.30,
    "resting_hr": 0.20,
    "sleep": 0.20,
    "training_readiness": 0.15,
    "tsb": 0.15,
}

FACTOR_LABELS: dict[str, str] = {
    "hrv": "HRV",
    "resting_hr": "Пульс покоя",
    "sleep": "Сон",
    "training_readiness": "Garmin readiness",
    "tsb": "Баланс нагрузки (TSB)",
}

# Кусочные пороги вместо непрерывных формул: evidence-строку
# «HRV −12% от базлайна → 40 баллов» человек может проверить сам.
# Каждая полоса: (нижняя граница включительно, score).
FACTOR_BANDS: dict[str, list[tuple[float, float]]] = {
    # отклонение rmssd от базлайна, %
    "hrv_deviation_pct": [(5.0, 85), (-5.0, 70), (-10.0, 55), (-20.0, 40), (float("-inf"), 20)],
    # rmssd, мс — когда базлайна ещё нет
    "hrv_absolute": [(50.0, 75), (35.0, 60), (25.0, 45), (float("-inf"), 25)],
    # превышение resting_hr над базлайном, уд/мин (меньше — лучше)
    "rhr_elevation_bpm": [(7.1, 20), (4.1, 35), (2.1, 50), (0.1, 70), (float("-inf"), 85)],
    # resting_hr, уд/мин — когда базлайна нет
    "rhr_absolute": [(70.0, 40), (60.0, 55), (40.0, 70), (float("-inf"), 40)],
    # часы сна — когда нет sleep_score
    "sleep_hours": [(8.0, 85), (7.0, 75), (6.0, 55), (5.0, 40), (float("-inf"), 25)],
    # TSB
    "tsb": [(5.0, 85), (-10.0, 70), (-20.0, 55), (-30.0, 35), (float("-inf"), 15)],
}

_STATUS_THRESHOLDS = [(75.0, "strong"), (60.0, "ready"), (40.0, "limited"), (float("-inf"), "low")]

# Нейтральный уровень фактора: драйверы ранжируются по вкладу отклонения от него.
_NEUTRAL_SCORE = 70.0


def compute_readiness_today(
    sleep_df: pd.DataFrame | None,
    hrv_df: pd.DataFrame | None,
    health_df: pd.DataFrame | None,
    training_df: pd.DataFrame | None,
    activities_df: pd.DataFrame | None,
    *,
    today: date | None = None,
    max_value_age_days: int | None = STALE_AFTER_DAYS,
) -> dict[str, Any]:
    """max_value_age_days=None разрешает сколь угодно старые значения:
    потребитель (например, readiness_snapshot) сам помечает результат stale
    по as_of_date вместо того, чтобы терять score."""
    # Anchor — календарь атлета: даты наблюдений приходят в ATHLETE_TIMEZONE, и
    # серверная дата вокруг полуночи классифицировала бы свежее измерение как
    # будущее, а вчерашнее — как сегодняшнее (issue #557, review P1).
    anchor = today or athlete_local_date()

    factors: list[dict[str, Any]] = []

    hrv_factor = _deviation_factor(
        key="hrv",
        frame=hrv_df,
        column="rmssd",
        anchor=anchor,
        max_age=max_value_age_days,
        deviation_mode="percent",
        deviation_bands="hrv_deviation_pct",
        absolute_bands="hrv_absolute",
        unit="мс",
        higher_is_better=True,
        observation_column=OBSERVATION_DATE_COLUMNS["hrv"],
    )
    if hrv_factor:
        factors.append(hrv_factor)

    rhr_factor = _deviation_factor(
        key="resting_hr",
        frame=health_df,
        column="resting_hr",
        anchor=anchor,
        max_age=max_value_age_days,
        deviation_mode="absolute",
        deviation_bands="rhr_elevation_bpm",
        absolute_bands="rhr_absolute",
        unit="уд/мин",
        higher_is_better=False,
        observation_column=OBSERVATION_DATE_COLUMNS["resting_hr"],
    )
    if rhr_factor:
        factors.append(rhr_factor)

    sleep_factor = _sleep_factor(sleep_df, anchor, max_value_age_days)
    if sleep_factor:
        factors.append(sleep_factor)

    garmin_factor = _garmin_factor(training_df, anchor, max_value_age_days)
    if garmin_factor:
        factors.append(garmin_factor)

    tsb_payload = _tsb_metrics(activities_df, anchor)
    if tsb_payload is not None:
        factors.append(_tsb_factor(tsb_payload))

    if not factors:
        return _empty_result()

    total_weight = sum(FACTOR_WEIGHTS[f["key"]] for f in factors)
    for factor in factors:
        factor["weight"] = round(FACTOR_WEIGHTS[factor["key"]] / total_weight, 3)

    score = round(sum(f["score"] * f["weight"] for f in factors), 1)
    status = readiness_status_for_score(score)

    drivers = sorted(
        factors,
        key=lambda f: f["weight"] * abs(f["score"] - _NEUTRAL_SCORE),
        reverse=True,
    )[:3]

    as_of_dates = [f["as_of"] for f in factors if f.get("as_of")]

    # --- Intervention eligibility (issue #557) ------------------------------
    # Описательные агрегаты выше (score/confidence/as_of_date) остаются ровно
    # такими, как были: их читают session-quality forecast, recovery analytics
    # и другие подсистемы. Вмешательство в план считает отдельно и только по
    # подтверждённо сегодняшним измерениям.
    eligible = [f for f in factors if f.get("intervention_eligible")]
    eligible_keys = [f["key"] for f in eligible]

    def _ineligible_reason(factor: dict[str, Any]) -> str:
        status = factor.get("observation_status")
        if status == OBSERVATION_UNVERIFIED:
            return INELIGIBLE_REASON_UNVERIFIED
        if status == OBSERVATION_INVALID:
            return INELIGIBLE_REASON_INVALID_OBSERVATION
        return INELIGIBLE_REASON_OUTDATED

    ineligible = [
        {
            "key": f["key"],
            "observation_status": f.get("observation_status"),
            "reason": _ineligible_reason(f),
        }
        for f in factors
        if not f.get("intervention_eligible")
    ]
    intervention_confidence = round(len(eligible) / len(FACTOR_WEIGHTS), 2)
    primary_eligible = [
        f
        for f in eligible
        if f["key"] in PRIMARY_RECOVERY_KEYS and f.get("evidence_kind") == EVIDENCE_KIND_MEASUREMENT
    ]
    if not eligible:
        intervention_score = None
        intervention_blocked_reason: str | None = INTERVENTION_BLOCKED_NO_ELIGIBLE
    elif not primary_eligible:
        # Current TSB is a derived load state, not an overnight measurement: it
        # can never open an intervention on its own.
        intervention_score = None
        intervention_blocked_reason = INTERVENTION_BLOCKED_NO_PRIMARY
    else:
        eligible_weight = sum(FACTOR_WEIGHTS[f["key"]] for f in eligible)
        intervention_score = round(
            sum(
                f.get("intervention_score_input", f["score"])
                * FACTOR_WEIGHTS[f["key"]]
                / eligible_weight
                for f in eligible
            ),
            1,
        )
        intervention_blocked_reason = None

    return {
        "score": score,
        "status": status,
        "as_of_date": max(as_of_dates) if as_of_dates else anchor.isoformat(),
        "confidence": round(len(factors) / len(FACTOR_WEIGHTS), 2),
        "factors": factors,
        "drivers": [
            {
                "key": f["key"],
                "label": f["label"],
                "score": f["score"],
                "intervention_score_input": f.get("intervention_score_input"),
                "evidence": f["evidence"],
                "as_of": f.get("as_of"),
                "observation_as_of": f.get("observation_as_of"),
                "age_days": f.get("age_days"),
                "observation_status": f.get("observation_status"),
                "intervention_eligible": bool(f.get("intervention_eligible")),
                "evidence_kind": f.get("evidence_kind"),
                "source": f.get("source"),
            }
            for f in drivers
        ],
        "missing_inputs": [key for key in FACTOR_WEIGHTS if key not in {f["key"] for f in factors}],
        "intervention_score": intervention_score,
        "intervention_confidence": intervention_confidence,
        "eligible_inputs": eligible_keys,
        "ineligible_inputs": ineligible,
        "intervention_blocked_reason": intervention_blocked_reason,
        "tsb": tsb_payload or {"ctl": None, "atl": None, "tsb": None, "window_days": LOAD_METRICS_WINDOW_DAYS},
    }


def _empty_result() -> dict[str, Any]:
    return {
        "score": None,
        "status": "unknown",
        "as_of_date": None,
        "confidence": 0.0,
        "factors": [],
        "drivers": [],
        "missing_inputs": list(FACTOR_WEIGHTS),
        "intervention_score": None,
        "intervention_confidence": 0.0,
        "eligible_inputs": [],
        "ineligible_inputs": [],
        "intervention_blocked_reason": INTERVENTION_BLOCKED_NO_ELIGIBLE,
        "tsb": {"ctl": None, "atl": None, "tsb": None, "window_days": LOAD_METRICS_WINDOW_DAYS},
    }


def _band_score(bands_key: str, value: float) -> float:
    for threshold, score in FACTOR_BANDS[bands_key]:
        if value >= threshold:
            return float(score)
    return float(FACTOR_BANDS[bands_key][-1][1])


@dataclass(frozen=True)
class FactorWindow:
    """Последнее значение фактора в двух независимых каналах (issue #557).

    Legacy-канал (``value``/``as_of``/``age_days``/``stale``/``history``) выбран и
    посчитан по дате строки хранения — ровно так, как это делал расчёт до #557:
    его читают session-quality forecast, recovery analytics и другие подсистемы,
    поэтому он заморожен.

    Provenance-канал (``observation_*``) описывает *измерение* той же выбранной
    строки: когда оно сделано по данным провайдера. Именно он решает, пригоден
    ли фактор для вмешательства в план.
    """

    value: float | None
    as_of: str | None
    age_days: int | None
    stale: bool
    history: pd.Series
    observation_as_of: str | None = None
    observation_age_days: int | None = None
    observation_verified: bool = False
    # Интервенционная серия (issue #557): по одному sample на дату наблюдения,
    # поэтому повторно загруженное наблюдение не считается дважды. Legacy
    # `history` при этом остаётся ровно тем же, что и до среза.
    intervention_history: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))
    intervention_duplicates_collapsed: bool = False


def _split_frame(
    frame: pd.DataFrame | None,
    column: str,
    anchor: date,
    max_age: int | None,
    *,
    observation_column: str | None = None,
) -> FactorWindow:
    """Return the latest stored value (frozen legacy) plus its observation provenance.

    Выбор значения, ``as_of``, ``stale`` и окно базлайна считаются по дате строки
    хранения и остаются байт-в-байт прежними. Даты измерения читаются отдельно и
    только для provenance: они не переключают выбранную строку (issue #557
    delta-review P2).
    """
    empty = FactorWindow(None, None, None, False, pd.Series(dtype=float))
    if frame is None or not isinstance(frame, pd.DataFrame) or frame.empty:
        return empty
    if column not in frame.columns or "date" not in frame.columns:
        return empty

    selected = ["date", column]
    has_observation = bool(observation_column and observation_column in frame.columns)
    if has_observation:
        selected.append(observation_column)
    df = frame[selected].copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"])
    df[column] = pd.to_numeric(df[column], errors="coerce")
    df = df.dropna(subset=[column]).sort_values("date")
    if df.empty:
        return empty

    latest = df.iloc[-1]
    latest_ts = latest["date"]
    latest_date = latest_ts.date()
    baseline_cutoff = latest_ts - pd.Timedelta(days=BASELINE_WINDOW_DAYS)
    history_window = df[(df["date"] < latest_ts) & (df["date"] >= baseline_cutoff)][column]

    age_days = (anchor - latest_date).days

    observation_date: date | None = None
    if has_observation:
        parsed_observation = pd.to_datetime(latest[observation_column], errors="coerce")
        if not pd.isna(parsed_observation):
            observation_date = parsed_observation.date()

    # Интервенционная серия: ключ — дата наблюдения, когда она известна, иначе
    # дата строки; при повторе одной и той же даты побеждает последняя запись.
    if has_observation:
        intervention_keys = pd.to_datetime(
            df[observation_column], errors="coerce"
        ).dt.normalize()
        intervention_keys = intervention_keys.fillna(df["date"].dt.normalize())
    else:
        intervention_keys = df["date"].dt.normalize()
    deduped = (
        df.assign(_intervention_key=intervention_keys)
        .sort_values("date")
        .drop_duplicates(subset=["_intervention_key"], keep="last")
        .sort_values("_intervention_key")
    )
    anchor_key = pd.Timestamp(observation_date).normalize() if observation_date else latest_ts.normalize()
    intervention_window = deduped[
        (deduped["_intervention_key"] < anchor_key)
        & (deduped["_intervention_key"] >= anchor_key - pd.Timedelta(days=BASELINE_WINDOW_DAYS))
    ][column]
    intervention_fields = {
        "intervention_history": intervention_window,
        "intervention_duplicates_collapsed": len(deduped) < len(df),
    }
    observation_age_days = (
        (anchor - observation_date).days if observation_date is not None else None
    )
    observation_fields = {
        "observation_as_of": observation_date.isoformat() if observation_date else None,
        "observation_age_days": observation_age_days,
        "observation_verified": observation_date is not None,
    }

    if max_age is not None and age_days > max_age:
        return FactorWindow(
            None,
            None,
            age_days,
            False,
            history_window,
            **observation_fields,
            **intervention_fields,
        )

    return FactorWindow(
        value=float(latest[column]),
        as_of=latest_date.isoformat(),
        age_days=age_days,
        stale=age_days > 0,
        history=history_window,
        **observation_fields,
        **intervention_fields,
    )


def readiness_status_for_score(score: float | None) -> str:
    """Канонический статус готовности по score (issue #557).

    Единственный источник порогов: и описательный расчёт, и интервенционный
    гейт используют эту функцию, поэтому `low (80/100)` или `ready (38/100)`
    из смешения каналов невозможны.
    """
    # Строго: строка или иное нечисловое значение — это unknown, а не «низкая
    # готовность» (issue #557, review P2). Приведение типов здесь запрещено.
    if score is None or isinstance(score, bool) or not isinstance(score, (int, float)):
        return "unknown"
    parsed = float(score)
    if not math.isfinite(parsed):
        return "unknown"
    return next(label for threshold, label in _STATUS_THRESHOLDS if parsed >= threshold)


def _observation_status(*, verified: bool, age_days: int | None) -> str:
    """Стабильный статус наблюдения фактора (issue #557).

    Пригодным к вмешательству считается только измерение ровно за anchor-дату:
    будущая дата — недостоверные данные, а не «свежие».
    """
    if not verified or age_days is None:
        return OBSERVATION_UNVERIFIED
    if age_days < 0:
        return OBSERVATION_INVALID
    if age_days == 0:
        return OBSERVATION_CONFIRMED_TODAY
    return OBSERVATION_OUTDATED


def _provenance_fields(
    window: FactorWindow, evidence_kind: str
) -> dict[str, Any]:
    status = _observation_status(
        verified=window.observation_verified, age_days=window.observation_age_days
    )
    return {
        "observation_as_of": window.observation_as_of,
        "age_days": window.observation_age_days,
        "observation_status": status,
        "intervention_eligible": status == OBSERVATION_CONFIRMED_TODAY,
        "evidence_kind": evidence_kind,
    }


def _derived_state_provenance(as_of: str | None) -> dict[str, Any]:
    """Provenance производного состояния нагрузки (TSB): дата = anchor."""
    return {
        "observation_as_of": as_of,
        "age_days": 0,
        "observation_status": OBSERVATION_CONFIRMED_TODAY,
        "intervention_eligible": True,
        "evidence_kind": EVIDENCE_KIND_DERIVED_STATE,
    }


def _baseline(history: pd.Series) -> float | None:
    if len(history) < MIN_BASELINE_SAMPLES:
        return None
    return float(history.mean())


def _deviation_factor(
    *,
    key: str,
    frame: pd.DataFrame | None,
    column: str,
    anchor: date,
    max_age: int | None,
    deviation_mode: str,
    deviation_bands: str,
    absolute_bands: str,
    unit: str,
    higher_is_better: bool,
    observation_column: str | None = None,
) -> dict[str, Any] | None:
    window = _split_frame(
        frame,
        column,
        anchor,
        max_age,
        observation_column=observation_column,
    )
    value = window.value
    if value is None:
        return None
    as_of = window.as_of
    baseline = _baseline(window.history)
    if baseline is not None and baseline > 0:
        if deviation_mode == "percent":
            deviation = (value - baseline) / baseline * 100.0
        else:
            deviation = value - baseline
        band_value = deviation if higher_is_better else deviation
        score = _band_score(deviation_bands, band_value)
        sign = "+" if deviation >= 0 else "−"
        magnitude = abs(deviation)
        suffix = "%" if deviation_mode == "percent" else f" {unit}"
        evidence = (
            f"{FACTOR_LABELS[key]} {value:.1f} {unit} против базовых "
            f"{baseline:.1f} ({sign}{magnitude:.1f}{suffix})"
        )
    else:
        deviation = None
        score = _band_score(absolute_bands, value)
        evidence = f"{FACTOR_LABELS[key]} {value:.1f} {unit} (базлайн ещё не накоплен)"

    # Интервенционный вход (issue #557): если одно наблюдение пришло дважды под
    # разными датами запроса, его вклад в базлайн не удваивается. Legacy
    # `score`/`baseline`/`deviation` при этом не меняются.
    intervention_score_input = score
    if window.intervention_duplicates_collapsed:
        intervention_baseline = _baseline(window.intervention_history)
        if intervention_baseline is not None and intervention_baseline > 0:
            if deviation_mode == "percent":
                intervention_deviation = (
                    (value - intervention_baseline) / intervention_baseline * 100.0
                )
            else:
                intervention_deviation = value - intervention_baseline
            intervention_score_input = _band_score(
                deviation_bands, intervention_deviation
            )

    return {
        "key": key,
        "label": FACTOR_LABELS[key],
        "score": score,
        "intervention_score_input": intervention_score_input,
        "weight": None,  # заполняется после перенормировки
        "raw_value": round(value, 1),
        "baseline": round(baseline, 1) if baseline is not None else None,
        "deviation": round(deviation, 1) if deviation is not None else None,
        "evidence": evidence,
        "source": f"{column}",
        "stale_input": window.stale,
        "as_of": as_of,
        **_provenance_fields(window, EVIDENCE_KIND_MEASUREMENT),
    }


def _sleep_factor(
    sleep_df: pd.DataFrame | None, anchor: date, max_age: int | None
) -> dict[str, Any] | None:
    # Дата хранения строки сна — это дата запроса, когда payload не несёт дату,
    # поэтому датой наблюдения считается только явная provider-дата из
    # `sleep_score_observed_at` / `total_sleep_observed_at` (issue #557).
    score_window = _split_frame(
        sleep_df,
        "sleep_score",
        anchor,
        max_age,
        observation_column=SLEEP_SCORE_OBSERVED_COLUMN,
    )
    score_value = score_window.value
    as_of = score_window.as_of
    if score_value is not None:
        metric_source = "legacy_unknown"
        if (
            isinstance(sleep_df, pd.DataFrame)
            and "date" in sleep_df.columns
            and "sleep_score_source" in sleep_df.columns
            and as_of is not None
        ):
            source_rows = sleep_df.copy()
            source_rows["date"] = pd.to_datetime(source_rows["date"], errors="coerce")
            source_rows = source_rows[source_rows["date"].dt.date == date.fromisoformat(as_of)]
            if not source_rows.empty:
                candidate = source_rows.iloc[-1].get("sleep_score_source")
                if candidate is not None and not pd.isna(candidate) and str(candidate).strip():
                    metric_source = str(candidate).strip()

        evidence_by_source = {
            "garmin": f"Сон: оценка Garmin {score_value:.0f}/100",
            "intervals": f"Сон: оценка Intervals.icu {score_value:.0f}/100",
            "derived": f"Сон: расчётная оценка {score_value:.0f}/100",
            "demo": f"Сон: демо-оценка {score_value:.0f}/100",
        }
        return {
            "key": "sleep",
            "label": FACTOR_LABELS["sleep"],
            "score": float(score_value),
            "intervention_score_input": float(score_value),
            "weight": None,
            "raw_value": round(score_value, 1),
            "baseline": None,
            "deviation": None,
            "evidence": evidence_by_source.get(
                metric_source,
                f"Сон: оценка {score_value:.0f}/100 (источник не сохранён)",
            ),
            "source": "sleep_score",
            "metric_source": metric_source,
            "stale_input": score_window.stale,
            "as_of": as_of,
            **_provenance_fields(score_window, EVIDENCE_KIND_MEASUREMENT),
        }

    minutes_window = _split_frame(
        sleep_df,
        "total_sleep_minutes",
        anchor,
        max_age,
        observation_column=SLEEP_DURATION_OBSERVED_COLUMN,
    )
    minutes = minutes_window.value
    if minutes is None or minutes <= 0:
        return None
    hours = minutes / 60.0
    sleep_hours_score = _band_score("sleep_hours", hours)
    return {
        "key": "sleep",
        "label": FACTOR_LABELS["sleep"],
        "score": sleep_hours_score,
        "intervention_score_input": sleep_hours_score,
        "weight": None,
        "raw_value": round(hours, 1),
        "baseline": None,
        "deviation": None,
        "evidence": f"Сон {hours:.1f} ч",
        "source": "total_sleep_minutes",
        "metric_source": "duration",
        "stale_input": minutes_window.stale,
        "as_of": minutes_window.as_of,
        **_provenance_fields(minutes_window, EVIDENCE_KIND_MEASUREMENT),
    }


def _garmin_factor(
    training_df: pd.DataFrame | None, anchor: date, max_age: int | None
) -> dict[str, Any] | None:
    window = _split_frame(
        training_df,
        "training_readiness",
        anchor,
        max_age,
        observation_column=OBSERVATION_DATE_COLUMNS["training_readiness"],
    )
    value = window.value
    if value is None:
        return None
    clamped = max(0.0, min(100.0, value))
    return {
        "key": "training_readiness",
        "label": FACTOR_LABELS["training_readiness"],
        "score": clamped,
        "intervention_score_input": clamped,
        "weight": None,
        "raw_value": round(clamped, 1),
        "baseline": None,
        "deviation": None,
        "evidence": f"Garmin readiness {clamped:.0f}/100",
        "source": "training_readiness",
        "stale_input": window.stale,
        "as_of": window.as_of,
        **_provenance_fields(window, EVIDENCE_KIND_MEASUREMENT),
    }


def _tsb_metrics(activities_df: pd.DataFrame | None, anchor: date) -> dict[str, Any] | None:
    if activities_df is None or not isinstance(activities_df, pd.DataFrame) or activities_df.empty:
        return None
    if "tss" not in activities_df.columns or "date" not in activities_df.columns:
        return None

    df = activities_df[["date", "tss"]].copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["tss"] = pd.to_numeric(df["tss"], errors="coerce").fillna(0.0)
    df = df.dropna(subset=["date"]).sort_values("date")
    anchor_ts = pd.Timestamp(anchor)
    df = df[df["date"] <= anchor_ts]
    if df.empty:
        return None

    # BanisterModel fills gaps only through the last supplied activity date.
    # Readiness is a "today" signal, so rest days after the last workout must
    # decay ATL/TSB as zero-TSS days through the anchor date.
    daily_tss = df.groupby(df["date"].dt.normalize())["tss"].sum().sort_index()
    date_range = pd.date_range(start=daily_tss.index.min(), end=anchor_ts, freq="D")
    daily_tss = daily_tss.reindex(date_range, fill_value=0.0)

    metrics = BanisterModel().get_current_metrics(daily_tss.tolist(), daily_tss.index.tolist())
    return {
        "ctl": round(float(metrics.get("ctl") or 0.0), 1),
        "atl": round(float(metrics.get("atl") or 0.0), 1),
        "tsb": round(float(metrics.get("tsb") or 0.0), 1),
        "window_days": LOAD_METRICS_WINDOW_DAYS,
        "as_of": anchor.isoformat(),
    }


def _tsb_factor(tsb_payload: dict[str, Any]) -> dict[str, Any]:
    tsb = float(tsb_payload["tsb"])
    if tsb > 5:
        note = "свежесть"
    elif tsb >= -10:
        note = "рабочая зона"
    elif tsb >= -20:
        note = "усталость выше нормы"
    else:
        note = "глубокая усталость"
    tsb_score = _band_score("tsb", tsb)
    return {
        "key": "tsb",
        "label": FACTOR_LABELS["tsb"],
        "score": tsb_score,
        "intervention_score_input": tsb_score,
        "weight": None,
        "raw_value": tsb,
        "baseline": None,
        "deviation": None,
        "evidence": f"TSB {tsb:+.1f} ({note})",
        "source": "activities.tss → Banister",
        "stale_input": False,
        "as_of": tsb_payload.get("as_of"),
        **_derived_state_provenance(tsb_payload.get("as_of")),
    }
