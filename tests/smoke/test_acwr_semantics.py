"""Безопасная семантика ACWR — контракт issue #608.

ACWR — отношение острой нагрузки к хронической. Само по себе оно **не
устанавливает вероятность травмы**, но публичный словарь статусов утверждал
обратное: `safe` / `optimal` / `moderate_risk` / `high_risk` с подписями
«Умеренный риск» и «Высокий риск». Этот файл фиксирует описательную шкалу
относительно базы атлета и запрет на предписание из одного ACWR.

Числа не меняются: пороги 0.8 / 1.3 / 1.5, формула EWMA и окна остаются
прежними (non-goal #608). Меняется словарь и то, что сигнал о себе сообщает.
"""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import pytest

from models.signals_engine import assemble_signals

from models.acwr import (
    ACWR_STATUS_LABEL,
    ACWR_STATUS_TONE,
    CROSS_CHECK_INSUFFICIENT,
    CROSS_CHECK_MATCH,
    CROSS_CHECK_MORE_ACUTE,
    acwr_signal,
    classify_acwr,
    compare_with_provider_status,
)


pytestmark = pytest.mark.smoke


#: Описательная шкала относительно базы атлета (issue #608).
_EXPECTED_SCALE = {
    "below_baseline",
    "expected_band",
    "elevated",
    "strongly_elevated",
}

#: Слова, которые нельзя использовать в пользовательских подписях ACWR:
#: они утверждают риск, безопасность или вероятность травмы.
_FORBIDDEN_WORDS = (
    "риск",
    "опасн",
    "безопасн",
    "травм",
    "injury",
    "safe",
    "risk",
)


#: Ровная нагрузка 120 дней по 50 TSS — значение 1.06.
_STEADY = [50.0] * 120
#: Блок 100 дней по 60 TSS, затем 14 дней отдыха — значение 0.21.
_LOW = [60.0] * 100 + [0.0] * 14
#: Блок 100 дней по 50 TSS, затем неделя по 200 TSS — значение 2.1.
_HIGH = [50.0] * 100 + [200.0] * 7


def test_no_risk_vocabulary_in_user_facing_status() -> None:
    """Ни один пользовательский статус не называет зону риском или безопасностью."""
    assert set(ACWR_STATUS_TONE) == _EXPECTED_SCALE, (
        f"тона заданы для {sorted(ACWR_STATUS_TONE)}, ожидалась описательная шкала "
        f"{sorted(_EXPECTED_SCALE)}"
    )
    assert set(ACWR_STATUS_LABEL) == _EXPECTED_SCALE

    for status, label in ACWR_STATUS_LABEL.items():
        lowered = label.lower()
        for word in _FORBIDDEN_WORDS:
            assert word not in lowered, (
                f"подпись {label!r} для статуса {status!r} содержит {word!r}: "
                "ACWR не устанавливает риск травмы и не доказывает безопасность"
            )


def test_low_ratio_reads_as_below_baseline() -> None:
    """Низкое отношение — ниже обычной базы атлета, а не доказательство недотренированности."""
    signal = acwr_signal(_LOW)

    assert signal["value"] == pytest.approx(0.21, abs=0.02)
    assert signal["status"] == "below_baseline", (
        f"status={signal['status']!r}: низкое отношение описывается как база, а не риск"
    )


def test_high_ratio_reads_as_elevated_not_injury() -> None:
    """Высокое отношение — повышенная относительная нагрузка, а не вероятность травмы."""
    signal = acwr_signal(_HIGH)

    assert signal["value"] == pytest.approx(2.1, abs=0.05)
    assert signal["status"] == "strongly_elevated", (
        f"status={signal['status']!r}: высокое отношение описывается как нагрузка, а не риск"
    )


def test_steady_ratio_reads_as_expected_band() -> None:
    """Ровная нагрузка — ожидаемый диапазон, а не «оптимальная зона» здоровья."""
    signal = acwr_signal(_STEADY)

    assert signal["status"] == "expected_band", f"status={signal['status']!r}"


def test_signal_exposes_provenance() -> None:
    """Провенанс: история и **обе** постоянные времени EWMA.

    Одного «окна» недостаточно: модель экспоненциальная и использует две
    постоянные, поэтому без них покрытие неоднозначно.
    """
    signal = acwr_signal(_STEADY)

    assert signal["history_days"] == len(_STEADY)
    assert signal["acute_tau_days"] == 7
    assert signal["chronic_tau_days"] == 42
    assert signal["limitation"].strip(), "сигнал обязан нести оговорку о своей природе"


def test_versions_are_separate() -> None:
    """Математика и интерпретация версионируются раздельно.

    Формула, окна и пороги в этом слайсе не меняются, поэтому
    `calculation_version` описывает математику, а `semantics_version` —
    публичную интерпретацию. Смешение читалось бы как смена расчёта.
    """
    signal = acwr_signal(_STEADY)

    # Точные значения, а не просто «непустая строка»: смена словаря не должна
    # двигать версию математики, а смена формулы — версию интерпретации.
    assert signal["calculation_version"] == "acwr-ewma-v1"
    assert signal["semantics_version"] == "descriptive-v2"


def test_limitation_present_in_data_gap() -> None:
    """Оговорка присутствует и там, где значения нет."""
    short = acwr_signal([50.0] * 10)

    assert short["value"] is None
    assert short["reason"]
    assert short["limitation"].strip()
    assert short["intervention_eligible"] is False, (
        "отсутствие значения тоже не даёт права на предписание"
    )
    assert short["history_days"] == 10
    assert short["acute_tau_days"] == 7
    assert short["chronic_tau_days"] == 42
    assert short["calculation_version"].strip()
    assert short["semantics_version"].strip()


def test_acwr_alone_cannot_prescribe() -> None:
    """ACWR-единственный вход не даёт права на предписывающее вмешательство."""
    for daily in (_STEADY, _LOW, _HIGH):
        signal = acwr_signal(daily)
        assert signal["intervention_eligible"] is False, (
            "отношение нагрузки не может быть основанием для снижения или отдыха "
            "без corroborating evidence"
        )


def test_numeric_fixtures_unchanged() -> None:
    """Регрессия: числа и пороги #608 не меняет."""
    assert classify_acwr(0.79) == "below_baseline"
    assert classify_acwr(0.8) == "expected_band"
    assert classify_acwr(1.2999999) == "expected_band"
    assert classify_acwr(1.3) == "elevated"
    assert classify_acwr(1.4999999) == "elevated"
    assert classify_acwr(1.5) == "strongly_elevated"


def test_provider_legacy_vocabulary_still_compares() -> None:
    """Провайдер присылает старый словарь: сверка обязана продолжать работать.

    Intervals.icu отдаёт `acwr_status` в прежней шкале, поэтому шим
    совместимости обязан отображать её в новую, а не терять значение.
    """
    assert compare_with_provider_status("expected_band", "optimal") == CROSS_CHECK_MATCH
    assert (
        compare_with_provider_status("strongly_elevated", "safe")
        == CROSS_CHECK_MORE_ACUTE
    )
    assert compare_with_provider_status(None, "high_risk") == CROSS_CHECK_INSUFFICIENT


def test_provider_status_is_never_legacy() -> None:
    """Старый словарь допустим только на входе, но не в публичном результате.

    Провайдер присылает `high_risk`. Если вернуть его в `provider_status` как
    есть, риск-лексика возвращается в DTO через чёрный ход, и запрет из
    acceptance criteria обходится.
    """
    signal = acwr_signal(_STEADY, provider_status="high_risk")

    assert signal["provider_status"] in _EXPECTED_SCALE, (
        f"provider_status={signal['provider_status']!r}: старый словарь ушёл наружу"
    )
    assert signal["cross_check"] != CROSS_CHECK_INSUFFICIENT

    gap = acwr_signal([50.0] * 10, provider_status="high_risk")
    assert gap["provider_status"] in _EXPECTED_SCALE, (
        "старый словарь не должен проходить наружу даже в data-gap ветке"
    )


def _activities(series: list[float], anchor: date) -> pd.DataFrame:
    rows = []
    for index, tss in enumerate(series):
        day = anchor - timedelta(days=len(series) - 1 - index)
        rows.append({"date": pd.Timestamp(day), "tss": float(tss), "sport": "cycling"})
    return pd.DataFrame(rows)


def test_acwr_change_does_not_move_recommendations() -> None:
    """Инвариант: изменение только ACWR не двигает рекомендации.

    TSB и HRV считаются из `activities_df`, ACWR — из отдельного
    `acwr_activities_df`, поэтому ряд можно поменять, не тронув остальные
    сигналы. Если рекомендации или critical-статус изменятся от одного лишь
    отношения нагрузки, значит ACWR де-факто стал предписывающим входом.
    """
    anchor = date(2026, 9, 20)
    load = _activities([50.0] * 120, anchor)
    steady = _activities([50.0] * 120, anchor)
    spiked = _activities([50.0] * 113 + [250.0] * 7, anchor)

    base = assemble_signals(
        activities_df=load, as_of=anchor, acwr_activities_df=steady, acwr_as_of=anchor
    )
    other = assemble_signals(
        activities_df=load, as_of=anchor, acwr_activities_df=spiked, acwr_as_of=anchor
    )

    assert base["load"]["tsb"] == other["load"]["tsb"], "TSB обязан остаться тем же"
    assert base["load"]["acwr"]["value"] != other["load"]["acwr"]["value"], (
        "фикстуры обязаны различаться по ACWR, иначе тест ничего не проверяет"
    )
    assert base["recommendations"] == other["recommendations"], (
        "ACWR не предписывает: рекомендации не должны зависеть от отношения нагрузки"
    )
    assert base["critical"] == other["critical"]
