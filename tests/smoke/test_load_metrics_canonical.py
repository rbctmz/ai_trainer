"""Единый пайплайн CTL/ATL/TSB — инварианты issue #731.

Владелец зафиксировал расхождение (скриншоты 2026-10-25): «План» показывал
CTL 20.8 / ATL 19.4 / TSB 1.4 (planning_service на включительной границе
``get_activities(90)``), «Обзор» и боковая панель «Коуча» — CTL 19.9 / TSB 0.5
(канонический readiness snapshot). Канон — ``models/load_metrics.py``: окно
``load_metrics_window_bounds``, фильтр мультиспорт-конвертов, zero-fill дней
отдыха до athlete-якоря, колонка ``activities.tss``. Инвариант: все
поверхности — снапшот, планирование, dashboard, коуч — читают один ряд.
"""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import pytest

from api.planning_service import _current_signals
from data.database import Database
from models.load_metrics import (
    LOAD_METRICS_WINDOW_DAYS,
    compute_load_metrics,
    compute_load_signal,
    daily_tss_series,
    load_metrics_window_bounds,
)
from models.readiness import _tsb_metrics
from utils.athlete_time import athlete_local_date


pytestmark = pytest.mark.smoke

_ANCHOR = date(2026, 10, 24)

#: 3 недели нарастающей нагрузки + 14 дней отдыха — сценарий из acceptance
#: #598: метрики обязаны гаситься к «сегодня», а не замерзать на тренировке.
_BLOCK = [100.0] * 7 + [110.0] * 7 + [120.0] * 7


def test_window_bounds_cover_exactly_90_days() -> None:
    start, end = load_metrics_window_bounds(_ANCHOR)
    assert end == _ANCHOR.isoformat()
    assert date.fromisoformat(start) == _ANCHOR - timedelta(days=LOAD_METRICS_WINDOW_DAYS - 1)
    assert (date.fromisoformat(end) - date.fromisoformat(start)).days + 1 == LOAD_METRICS_WINDOW_DAYS


def test_daily_series_zero_fills_rest_days_through_anchor() -> None:
    frame = pd.DataFrame(
        [
            {"date": "2026-10-20", "tss": 100.0},
            {"date": "2026-10-23", "tss": 50.0},
        ]
    )

    values, dates = daily_tss_series(frame, _ANCHOR)

    assert [round(value, 1) for value in values] == [100.0, 0.0, 0.0, 50.0, 0.0]
    assert dates[-1] == pd.Timestamp(_ANCHOR)


def test_snapshot_and_signal_share_one_pipeline() -> None:
    """TSB-снапшот и signals-engine обязаны читать один и тот же ряд."""
    frame = pd.DataFrame(
        [
            {"date": "2026-10-20", "tss": 100.0},
            {"date": "2026-10-23", "tss": 50.0},
        ]
    )

    metrics = compute_load_metrics(frame, _ANCHOR)
    signal = compute_load_signal(frame, _ANCHOR)

    assert metrics is not None
    assert metrics["as_of"] == _ANCHOR.isoformat()
    assert metrics["window_days"] == LOAD_METRICS_WINDOW_DAYS
    for key in ("ctl", "atl", "tsb"):
        assert metrics[key] == pytest.approx(signal[key], abs=0.05), key


def test_empty_frame_shapes() -> None:
    assert compute_load_metrics(pd.DataFrame(), _ANCHOR) is None
    assert compute_load_signal(None, _ANCHOR)["form"] == "Недостаточно данных"


def _seed(db: Database, days: list[float], end_offset_days: int) -> Database:
    today = athlete_local_date()
    block_end = today - timedelta(days=end_offset_days)
    block_start = block_end - timedelta(days=len(days) - 1)
    db.save_activities(
        [
            {
                "activity_id": f"issue731-{end_offset_days}-{index}",
                "date": (block_start + timedelta(days=index)).strftime("%Y-%m-%d"),
                "sport": "cycling",
                "duration_minutes": 90,
                "distance_km": 40.0,
                "tss": float(tss),
            }
            for index, tss in enumerate(days)
        ]
    )
    return db


def test_planning_signals_match_canonical_readiness_snapshot(tmp_path) -> None:
    """«План» обязан показывать те же CTL/ATL/TSB, что снапшот готовности.

    До #731 planning_service читал окно включительной границей
    ``get_activities(90)`` (91 дата) — числа расходились с каноническим рядом
    на краю окна и с фильтром мультиспорт-конвертов.
    """
    db = _seed(Database(str(tmp_path / "issue731.db")), _BLOCK, end_offset_days=14)
    anchor = athlete_local_date()

    signals, _df = _current_signals(db)

    canonical = compute_load_metrics(
        pd.DataFrame(db.get_activities_between(*load_metrics_window_bounds(anchor))),
        anchor,
    )
    assert canonical is not None
    assert signals["load"]["ctl"] == pytest.approx(canonical["ctl"], abs=0.1)
    assert signals["load"]["atl"] == pytest.approx(canonical["atl"], abs=0.1)
    assert signals["load"]["tsb"] == pytest.approx(canonical["tsb"], abs=0.1)
    assert _tsb_metrics(
        pd.DataFrame(db.get_activities_between(*load_metrics_window_bounds(anchor))),
        anchor,
    ) == canonical
