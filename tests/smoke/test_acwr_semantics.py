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

import pytest

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


def test_signal_exposes_provenance_and_version() -> None:
    """Сигнал несёт провенанс: покрытие истории, окно и версию расчёта."""
    signal = acwr_signal(_STEADY)

    assert signal["history_days"] == len(_STEADY)
    assert isinstance(signal["window_days"], int) and signal["window_days"] > 0
    assert isinstance(signal["calculation_version"], str)
    assert signal["calculation_version"].strip()
    assert signal["limitation"].strip(), "сигнал обязан нести оговорку о своей природе"


def test_limitation_present_in_data_gap() -> None:
    """Оговорка присутствует и там, где значения нет."""
    short = acwr_signal([50.0] * 10)

    assert short["value"] is None
    assert short["reason"]
    assert short["limitation"].strip()


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