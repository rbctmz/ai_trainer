"""ACWR (acute:chronic workload ratio) — контракт issue #593.

Формула: ACWR = ATL / CTL по дневным EWMA (Williams et al. 2017).
Пороги и статусы: Gabbett 2016.

Тесты фиксируют:
- границы 0.8 / 1.3 / 1.5 с обеих сторон (граница входит в нижнюю зону);
- guard'ы: CTL < 5 или история < 21 дня -> None без исключений;
- сверку с провайдерским acwr_status как cross-check, а не подмену;
- отсутствие регрессий в signals_engine при добавлении ключа.
"""
from __future__ import annotations

import math

import pandas as pd
import pytest

from models.acwr import (
    ACWR_MIN_CHRONIC_LOAD,
    ACWR_MIN_HISTORY_DAYS,
    ACWR_OPTIMAL_MAX,
    ACWR_SAFE_THRESHOLD,
    ACWR_HIGH_RISK_THRESHOLD,
    ACWR_STATUS_TONE,
    acwr_series,
    acwr_signal,
    classify_acwr,
    compare_with_provider_status,
)
from models.signals_engine import assemble_signals


pytestmark = pytest.mark.smoke


# --------------------------------------------------------------------------
# Пороги: односторонняя классификация, граница принадлежит нижней зоне.
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("ratio", "expected"),
    [
        (0.0, "safe"),
        (0.79, "safe"),
        (0.7999999, "safe"),
        (0.8, "optimal"),          # граница -> optimal, не safe
        (1.0, "optimal"),
        (1.2999999, "optimal"),
        (1.3, "moderate_risk"),    # граница -> moderate_risk, не optimal
        (1.49, "moderate_risk"),
        (1.4999999, "moderate_risk"),
        (1.5, "high_risk"),        # граница -> high_risk, не moderate_risk
        (1.51, "high_risk"),
        (3.0, "high_risk"),
    ],
)
def test_classify_acwr_zone_boundaries(ratio: float, expected: str) -> None:
    assert classify_acwr(ratio) == expected


def test_threshold_constants_match_gabbett_2016() -> None:
    assert ACWR_SAFE_THRESHOLD == 0.8
    assert ACWR_OPTIMAL_MAX == 1.3
    assert ACWR_HIGH_RISK_THRESHOLD == 1.5


def test_every_status_has_a_tone() -> None:
    assert set(ACWR_STATUS_TONE) == {
        "safe",
        "optimal",
        "moderate_risk",
        "high_risk",
    }
    assert set(ACWR_STATUS_TONE.values()) <= {"success", "neutral", "warning", "danger"}


# --------------------------------------------------------------------------
# Формула: ACWR = ATL / CTL по дневным EWMA.
# --------------------------------------------------------------------------

def _steady_then(steady_days: int, steady_tss: float, tail: list[float]) -> list[float]:
    return [steady_tss] * steady_days + list(tail)


def test_acwr_series_uses_daily_ewma_ratio() -> None:
    """На стабильной нагрузке отношение сходится к 1.0.

    Сходимость медленная: ATL (tau=7) выходит на плато за ~3 недели, а CTL
    (tau=42) за 6 недель догоняет только до ~0.63 от установившегося уровня.
    Поэтому на полном 42-дневном окне стабильной нагрузки ACWR ~1.0 только к
    концу, и статус обязан попадать в оптимальную зону, а не в риск.
    """
    daily = _steady_then(300, 50.0, [])
    series = acwr_series(daily)

    assert len(series) == len(daily)
    assert series[-1]["acwr"] == pytest.approx(1.0, abs=0.01)


def test_acwr_series_is_one_to_one_with_input_days() -> None:
    daily = _steady_then(60, 40.0, [80.0, 0.0, 120.0])
    series = acwr_series(daily)

    assert len(series) == len(daily)
    for index, point in enumerate(series):
        assert set(point) == {"atl", "ctl", "acwr"}


def test_acwr_series_last_point_matches_atl_over_ctl() -> None:
    """Инвариант: acwr == atl / ctl на каждом шаге."""
    daily = _steady_then(60, 60.0, [90.0, 110.0, 20.0])
    series = acwr_series(daily)

    for point in series:
        if point["ctl"] > 0:
            assert point["acwr"] == pytest.approx(point["atl"] / point["ctl"])


def test_sustained_overload_raises_acwr_above_optimal() -> None:
    """90 дней по 50 TSS, затем 14 дней по 100 TSS — острая нагрузка выше хронической."""
    daily = _steady_then(90, 50.0, [100.0] * 14)
    series = acwr_series(daily)

    assert series[-1]["atl"] > series[-1]["ctl"]
    assert series[-1]["acwr"] > ACWR_OPTIMAL_MAX


def test_taper_lowers_acwr_below_safe_threshold() -> None:
    """После разгрузки острая нагрузка падает быстрее хронической."""
    daily = _steady_then(120, 80.0, [0.0] * 21)
    series = acwr_series(daily)

    assert series[-1]["acwr"] < ACWR_SAFE_THRESHOLD


def test_acwr_series_on_empty_input_is_empty() -> None:
    assert acwr_series([]) == []


def test_acwr_series_respects_canonical_banister_alpha() -> None:
    """EWMA-константы берём из banister.py, не дублируем числа."""
    from datetime import date, timedelta

    from models.banister import BanisterModel

    daily = _steady_then(30, 50.0, [])
    # Реальные непрерывные даты: Banister агрегирует строки по дате, поэтому
    # целочисленные метки дали бы одну точку вместо тридцати.
    base = date(2026, 1, 1)
    dates = [base + timedelta(days=i) for i in range(len(daily))]

    series = acwr_series(daily)
    _, ctl_values, atl_values, _ = BanisterModel().calculate_ctl_atl_tsb(daily, dates)

    assert len(ctl_values) == len(daily)
    assert series[-1]["ctl"] == pytest.approx(ctl_values[-1])
    assert series[-1]["atl"] == pytest.approx(atl_values[-1])


# --------------------------------------------------------------------------
# Guard'ы: лучше None, чем ложная точность.
# --------------------------------------------------------------------------

def test_low_chronic_load_returns_none() -> None:
    """История длинная, но нагрузка мизерная — отношение бессмысленно.

    84 дня по одной короткой сессии в неделю: хроническая нагрузка ~1.2 TSS
    несоизмерима ни с чем, и любая случайная тренировка дала бы ACWR 3.0 и
    ложный «высокий риск». Такой профиль — начинающий, а не перетренированный.
    """
    daily = [10.0 if i % 7 == 0 else 0.0 for i in range(84)]
    signal = acwr_signal(daily)

    assert signal["value"] is None
    assert signal["status"] is None
    assert signal["reason"] == "chronic_load_too_low"
    assert signal["ctl"] < ACWR_MIN_CHRONIC_LOAD


def test_short_history_returns_none() -> None:
    """Короче 84 дней хроническая база ещё не набрана: ACWR завышен стартом с нуля.

    ATL (tau=7) выходит на плато за ~3 недели, CTL (tau=42) отстаёт
    структурно — на ровной нагрузке с нуля отношение показывает «высокий
    риск» (на 42 днях замерено 1.58), что было бы ложной тревогой.
    """
    daily = [50.0] * (ACWR_MIN_HISTORY_DAYS - 1)
    signal = acwr_signal(daily)

    assert signal["value"] is None
    assert signal["status"] is None
    assert signal["reason"] == "insufficient_history"


def test_cold_start_steady_load_is_not_reported_as_high_risk() -> None:
    """Регрессия: ровная нагрузка с нуля не должна объявляться риском."""
    signal = acwr_signal([50.0] * ACWR_MIN_HISTORY_DAYS)

    assert signal["value"] is not None
    assert signal["status"] == "optimal"
    assert signal["status"] != "high_risk"


def test_exactly_minimum_history_with_real_load_computes() -> None:
    daily = [50.0] * ACWR_MIN_HISTORY_DAYS
    signal = acwr_signal(daily)

    assert signal["value"] is not None
    assert signal["reason"] is None
    assert signal["status"] in ACWR_STATUS_TONE


def test_all_zero_history_returns_none_without_exception() -> None:
    signal = acwr_signal([0.0] * 90)

    assert signal["value"] is None
    assert signal["history_days"] == 90


def test_signal_never_raises_on_degenerate_input() -> None:
    for daily in ([], [0.0], [float("nan")] * 30, [None] * 30):  # type: ignore[list-item]
        signal = acwr_signal(daily)
        assert signal["value"] is None
        assert signal["status"] is None


def test_guard_reasons_are_declared_as_constants() -> None:
    assert ACWR_MIN_CHRONIC_LOAD == 5.0
    assert ACWR_MIN_HISTORY_DAYS == 84


# --------------------------------------------------------------------------
# Cross-check с провайдерским значением: сверяем, не подменяем.
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("local", "provider", "expected"),
    [
        ("optimal", "optimal", "match"),
        ("optimal", "OPTIMAL", "match"),
        ("moderate_risk", "optimal", "more_acute"),
        ("high_risk", "moderate_risk", "more_acute"),
        ("optimal", "moderate_risk", "less_acute"),
        ("safe", "high_risk", "less_acute"),
        ("optimal", None, "no_provider_value"),
        ("optimal", "", "no_provider_value"),
        ("optimal", "   ", "no_provider_value"),
        ("optimal", "неизвестный статус", "no_provider_value"),
        (None, "optimal", "insufficient_data"),
        (None, None, "insufficient_data"),
    ],
)
def test_compare_with_provider_status(local: str | None, provider: object, expected: str) -> None:
    assert compare_with_provider_status(local, provider) == expected


def test_signal_carries_provider_cross_check() -> None:
    daily = _steady_then(120, 50.0, [])
    signal = acwr_signal(daily, provider_status="high_risk")

    assert signal["value"] is not None
    # Наше значение основное: провайдерский статус его не перезаписывает.
    assert signal["status"] == "optimal"
    assert signal["cross_check"] == "less_acute"
    assert signal["provider_status"] == "high_risk"


def test_signal_without_provider_value_reports_no_provider_value() -> None:
    signal = acwr_signal([50.0] * 120)

    assert signal["cross_check"] == "no_provider_value"
    assert signal["provider_status"] is None


# --------------------------------------------------------------------------
# Форма сигнала.
# --------------------------------------------------------------------------

def test_signal_shape_is_stable() -> None:
    signal = acwr_signal([50.0] * 120, provider_status="optimal")

    assert set(signal) == {
        "value",
        "percent",
        "status",
        "tone",
        "label",
        "severity",
        "atl",
        "ctl",
        "history_days",
        "reason",
        "cross_check",
        "provider_status",
    }
    assert signal["percent"] == pytest.approx(signal["value"] * 100, abs=0.1)
    assert isinstance(signal["label"], str) and signal["label"]


def test_signal_rounds_for_stable_output() -> None:
    signal = acwr_signal([50.0] * 120)

    assert signal["value"] == round(signal["value"], 2)
    assert signal["atl"] == round(signal["atl"], 1)
    assert signal["ctl"] == round(signal["ctl"], 1)


# --------------------------------------------------------------------------
# Интеграция в signals_engine: аддитивно, без регрессий.
# --------------------------------------------------------------------------

def _activities_frame(daily_tss: list[float]) -> pd.DataFrame:
    base = pd.Timestamp("2026-01-01")
    return pd.DataFrame(
        [
            {"date": (base + pd.Timedelta(days=i)).strftime("%Y-%m-%d"), "tss": tss}
            for i, tss in enumerate(daily_tss)
        ]
    )


def test_signals_engine_exposes_acwr_without_changing_existing_keys() -> None:
    activities = _activities_frame([50.0] * 120)
    signals = assemble_signals(activities_df=activities)

    assert "acwr" in signals["load"]
    # Существующие ключи load не тронуты.
    for key in ("ctl", "atl", "tsb", "form", "label", "tone", "clause", "severity"):
        assert key in signals["load"], f"пропал существующий ключ load.{key}"


def test_signals_engine_acwr_matches_direct_calculation() -> None:
    daily = [50.0] * 100 + [110.0] * 10
    activities = _activities_frame(daily)

    signals = assemble_signals(activities_df=activities)
    direct = acwr_signal(daily)

    assert signals["load"]["acwr"]["value"] == pytest.approx(direct["value"], abs=0.01)
    assert signals["load"]["acwr"]["status"] == direct["status"]


def test_signals_engine_does_not_overwrite_provider_acwr_status() -> None:
    """Значение из Intervals.icu остаётся источником сверки, не подмены."""
    activities = _activities_frame([50.0] * 120)
    provider = {
        "acwr_status": "high_risk",
        "acwr_percent": 172.0,
        "acwr_status_feedback": "Провайдерский текст",
    }

    signals = assemble_signals(activities_df=activities, training_status=provider)

    acwr = signals["load"]["acwr"]
    assert acwr["status"] == "optimal"
    assert acwr["provider_status"] == "high_risk"
    assert acwr["cross_check"] == "less_acute"


def test_signals_engine_acwr_is_none_safe_on_empty_activities() -> None:
    signals = assemble_signals(activities_df=pd.DataFrame())

    assert signals["load"]["acwr"]["value"] is None
    assert signals["load"]["acwr"]["status"] is None


def test_signals_engine_acwr_handles_nan_tss() -> None:
    activities = _activities_frame([50.0] * 119 + [float("nan")])
    signals = assemble_signals(activities_df=activities)

    value = signals["load"]["acwr"]["value"]
    assert value is None or math.isfinite(value)


def test_signals_engine_anchor_before_all_activities_is_empty() -> None:
    """Якорь раньше всех активностей: ряд пуст, метрики деградируют, не падают.

    Регрессия рефакторинга #593: `training_load_metrics` при пустом ряде после
    фильтра по якорю обязан вернуть нулевую форму, а не замороженные значения.
    """
    activities = _activities_frame([50.0] * 120)
    as_of = pd.Timestamp("2025-01-01").date()

    signals = assemble_signals(activities_df=activities, as_of=as_of)

    assert signals["load"]["acwr"]["value"] is None
    assert signals["load"]["atl"] == 0.0
    assert signals["load"]["ctl"] == 0.0
    assert signals["load"]["form"] == "Недостаточно данных"
