"""Якорь метрик нагрузки в планировщике — контракт issue #597.

`_current_signals` вызывал `assemble_signals` без `as_of`, поэтому CTL/ATL/TSB
замерзали на дате последней тренировки: дни отдыха не гасили нагрузку. Отсюда
`assess_start_load_state` решал, что отдохнувший спортсмен в глубокой усталости,
и резал план guard-факторами 0.75/0.85/0.95.

Тесты фиксируют:
- разрыв в данных гасит ATL/CTL и поднимает TSB (это и есть предмет #597);
- без разрыва значения не меняются (регрессии нет);
- состояние ограничителя перестаёт быть deep_fatigue после отдыха.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from api import planning_service as ps
from data.database import Database
from models.training_planner import assess_start_load_state


pytestmark = pytest.mark.smoke


_HARD_BLOCK = [100.0] * 7 + [110.0] * 7 + [120.0] * 7  # 3 недели нарастающей нагрузки


def _seed(db: Database, days: list[float], end_offset_days: int) -> None:
    """Записать дневную нагрузку, закончившуюся `end_offset_days` назад."""
    today = datetime.now().date()
    block_end = today - timedelta(days=end_offset_days)
    block_start = block_end - timedelta(days=len(days) - 1)
    rows = []
    for index, tss in enumerate(days):
        day = block_start + timedelta(days=index)
        rows.append(
            {
                "activity_id": f"anchor-{end_offset_days}-{index}",
                "date": day.strftime("%Y-%m-%d"),
                "sport": "cycling",
                "duration_minutes": 90,
                "distance_km": 40.0,
                "tss": float(tss),
            }
        )
    db.save_activities(rows)


def _db(tmp_path, name: str = "anchor.db") -> Database:
    return Database(str(tmp_path / name))


def test_rest_days_decay_metrics_in_current_metrics(tmp_path) -> None:
    """#597: после 14 дней отдыха ATL обязан упасть, а не остаться на уровне блока."""
    db = _db(tmp_path, "rest.db")
    _seed(db, _HARD_BLOCK, end_offset_days=14)

    metrics, _banister, _df = ps._current_metrics(db)

    # Замороженное значение ATL равно последней неделе блока (120) — оно и было
    # дефектом. С якорем острая нагрузка обязана успеть погаснуть.
    assert metrics["atl"] < 60.0, (
        f"ATL={metrics['atl']} не погас за 14 дней отдыха — метрики посчитаны "
        "на дату последней тренировки, а не на сегодня"
    )
    assert metrics["ctl"] > 0.0
    assert metrics["tsb"] > 0.0, f"TSB={metrics['tsb']} должен быть положительным у отдохнувшего"


def test_rest_days_remove_fatigue_state(tmp_path) -> None:
    """Ограничитель плана не должен видеть глубокую усталость у отдохнувшего."""
    db = _db(tmp_path, "state.db")
    _seed(db, _HARD_BLOCK, end_offset_days=14)

    metrics, _banister, _df = ps._current_metrics(db)
    state = assess_start_load_state(
        current_ctl=metrics.get("ctl"),
        current_atl=metrics.get("atl"),
        current_tsb=metrics.get("tsb"),
    )

    assert state["state"] != "deep_fatigue", (
        f"состояние {state['state']} с guard_factors {state['guard_factors']} "
        "означает урезание плана отдохнувшему спортсмену"
    )
    assert state["guard_factors"] == [], (
        "guard_factors должны быть пустыми: усталости нет"
    )


def test_short_rest_keeps_metrics_meaningful(tmp_path) -> None:
    """Через 7 дней отдыха нагрузка тоже должна частично погаснуть."""
    db = _db(tmp_path, "week.db")
    _seed(db, _HARD_BLOCK, end_offset_days=7)

    metrics, _banister, _df = ps._current_metrics(db)

    assert metrics["atl"] < 120.0, "ATL не изменился за неделю отдыха"
    assert metrics["atl"] > 0.0


def test_no_gap_keeps_metrics_unchanged(tmp_path) -> None:
    """Регрессия: когда разрыва нет, якорь ничего не меняет.

    Блок заканчивается сегодня, поэтому достройка нулями ничего не добавляет и
    значения обязаны совпасть с расчётом без якоря: 60 дней по 50 TSS дают
    CTL 38.0, ATL 50.0, TSB −12.0.
    """
    db = _db(tmp_path, "nogap.db")
    _seed(db, [50.0] * 60, end_offset_days=0)

    metrics, _banister, _df = ps._current_metrics(db)

    assert metrics["ctl"] == pytest.approx(38.0, abs=0.5), f"CTL={metrics['ctl']} изменился"
    assert metrics["atl"] == pytest.approx(50.0, abs=0.5), f"ATL={metrics['atl']} изменился"
    assert metrics["tsb"] == pytest.approx(-12.0, abs=1.0), f"TSB={metrics['tsb']} изменился"


def test_current_status_reflects_rest(tmp_path) -> None:
    """Потребитель статуса (дашборд, коуч) тоже должен видеть отдых."""
    db = _db(tmp_path, "status.db")
    _seed(db, _HARD_BLOCK, end_offset_days=14)

    status = ps.current_status(db)

    assert status["metrics"]["atl"] < 60.0, (
        f"current_status.metrics.atl={status['metrics']['atl']} не погас"
    )
    assert status["metrics"]["tsb"] > 0.0, (
        f"current_status.metrics.tsb={status['metrics']['tsb']} должен быть положительным"
    )


def test_signals_expose_anchor_consistent_load(tmp_path) -> None:
    """load.acwr считается из того же якоря, что CTL/ATL — иначе они разойдутся."""
    db = _db(tmp_path, "signals.db")
    _seed(db, _HARD_BLOCK, end_offset_days=14)

    signals, _df = ps._current_signals(db)
    load = signals["load"]

    assert "acwr" in load
    # 35 дней окна меньше 84-дневного guard'а ACWR, поэтому значение отсутствует,
    # но это осознанный отказ, а не ошибка.
    if load["acwr"]["value"] is not None:
        assert load["acwr"]["reason"] is None
    else:
        assert load["acwr"]["reason"] in {"insufficient_history", "chronic_load_too_low"}


def test_long_history_with_rest_yields_acwr(tmp_path) -> None:
    """На длинной истории ACWR считается и после отдыха даёт низкое отношение."""
    db = _db(tmp_path, "long.db")
    _seed(db, [60.0] * 100, end_offset_days=0)

    signals, _df = ps._current_signals(db)
    acwr = signals["load"]["acwr"]

    assert acwr["value"] is not None, f"ожидалось значение, причина: {acwr['reason']}"
    assert acwr["value"] < 1.3, f"ACWR={acwr['value']} вне оптимальной зоны при ровной нагрузке"


def test_anchor_uses_canonical_athlete_date(tmp_path, monkeypatch) -> None:
    """Якорь берётся из athlete_local_date, а не из host clock.

    #577 завёл канонический хелпер атлетской даты. При дефолтном
    ATHLETE_TIMEZONE он совпадает с локальной датой хоста, поэтому ошибку
    не поймать сравнением значений — подменяем сам источник и проверяем,
    что он действительно используется.
    """
    db = _db(tmp_path, "canonical.db")
    _seed(db, [50.0] * 60, end_offset_days=0)

    canonical = datetime.now().date() + timedelta(days=40)
    monkeypatch.setattr(ps, "athlete_local_date", lambda *args, **kwargs: canonical)

    signals, _df = ps._current_signals(db)

    # 40 добавленных нулевых дней гасят острую нагрузку: без канонического
    # источника якорь остался бы на сегодняшней дате и ATL держался бы на 50.
    assert signals["load"]["atl"] < 20.0, (
        f"ATL={signals['load']['atl']}: якорь не взял дату из athlete_local_date"
    )
    assert signals["load"]["tsb"] > 0.0
