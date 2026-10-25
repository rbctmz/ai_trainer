"""Единый пайплайн CTL/ATL/TSB — инварианты issue #731 / #660.

Владелец зафиксировал расхождение (скриншоты 2026-10-25): «План» показывал
CTL 20.8 / ATL 19.4 / TSB 1.4 (planning_service на включительной границе
``get_activities(90)``), «Обзор» и боковая панель «Коуча» — CTL 19.9 / TSB 0.5
(канонический readiness snapshot). Канон — ``models/load_metrics.py``: окно
``load_metrics_window_bounds``, фильтр мультиспорт-конвертов, zero-fill дней
отдыха до athlete-якоря, колонка ``activities.tss``. Инвариант: все
поверхности — снапшот, планирование, dashboard, коуч, standalone-тул — читают
один ряд, а планирование отдаёт persisted ``readiness_snapshots.tsb_json``.
"""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import pytest

from api.planning_service import _current_signals
from api.routers.coach import _load_metrics_context
from data.database import Database
from models.ai_tools import AITools
from models.load_metrics import (
    LOAD_METRICS_WINDOW_DAYS,
    compute_load_metrics,
    compute_load_signal,
    daily_tss_series,
    load_metrics_window_bounds,
)
from models.readiness import _tsb_metrics
from services.readiness_snapshot import build_readiness_snapshot
from utils.athlete_time import athlete_local_date


pytestmark = pytest.mark.smoke

_ANCHOR = date(2026, 10, 24)

#: 3 недели нарастающей нагрузки + 14 дней отдыха — сценарий из acceptance
#: #598: метрики обязаны гаситься к «сегодня», а не замерзать на тренировке.
_BLOCK = [100.0] * 7 + [110.0] * 7 + [120.0] * 7

#: Граничный сценарий #660: ровно 91 дневная строка по 50 TSS — ровно столько,
#: сколько читала включительная граница ``get_activities(90)`` до #731.
_BOUNDARY_ROWS = 91


def _triple(value: dict | None) -> dict:
    value = value or {}
    return {key: value.get(key) for key in ("ctl", "atl", "tsb")}


def _patch_athlete_anchor(monkeypatch: pytest.MonkeyPatch, anchor: date) -> None:
    """Закрепить athlete-якорь и cutoff ``get_activities(N)`` на дату (см. #599)."""
    monkeypatch.setattr("utils.athlete_time.athlete_local_date", lambda: anchor)
    monkeypatch.setattr("api.planning_service.athlete_local_date", lambda: anchor)
    monkeypatch.setattr("models.ai_tools.athlete_local_date", lambda: anchor)
    monkeypatch.setattr("services.readiness_snapshot.athlete_local_date", lambda: anchor)
    monkeypatch.setattr(
        Database,
        "_cutoff_date",
        staticmethod(lambda days: (anchor - timedelta(days=float(days))).isoformat()),
    )


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


def test_all_load_paths_agree_on_91_day_boundary_db(tmp_path, monkeypatch) -> None:
    """Regression #660: каждый путь обязан дать один и тот же ряд на границе.

    Аудит #733 (6b54ff0): standalone ``get_readiness_today`` продолжал читать
    91 дату через ``get_activities(90)`` и давал 44.3/50.0/−5.7 против 44.1/
    50.0/−5.9 у остальных путей. После фикса все пути равны каноническому ряду.
    """
    anchor = _ANCHOR
    _patch_athlete_anchor(monkeypatch, anchor)
    db = Database(str(tmp_path / "boundary.db"))
    db.save_activities(
        [
            {
                "activity_id": f"boundary-{n}",
                "date": (anchor - timedelta(days=n)).isoformat(),
                "sport": "cycling",
                "duration_minutes": 60,
                "distance_km": 25.0,
                "tss": 50.0,
            }
            for n in range(_BOUNDARY_ROWS)
        ]
    )
    canonical = compute_load_metrics(
        pd.DataFrame(db.get_activities_between(*load_metrics_window_bounds(anchor))),
        anchor,
    )
    assert canonical is not None
    # Граница реальна: без фильтра окна было бы 91 дата, с каноном — 90.
    assert len(db.get_activities(LOAD_METRICS_WINDOW_DAYS)) == _BOUNDARY_ROWS

    tools = AITools(db)
    snapshot = build_readiness_snapshot(db, as_of=anchor)
    signals, _df = _current_signals(db, as_of=anchor)
    standalone = tools.get_readiness_today()
    performance = {days: tools.get_performance_metrics(days) for days in (30, 60, 90, 180, 365)}

    paths = {
        "canonical_pipeline": canonical,
        "readiness_snapshot_service": _triple(snapshot.get("tsb")),
        "planning_signals": _triple(signals["load"]),
        "standalone_readiness_tool": _triple(standalone.get("readiness", {}).get("tsb")),
        "coach_meta_context": _triple(_load_metrics_context(tools)),
    }
    paths.update(
        {f"performance_days_{days}": _triple(result) for days, result in performance.items()}
    )
    for name, value in paths.items():
        for key in ("ctl", "atl", "tsb"):
            assert value[key] == pytest.approx(canonical[key], abs=0.05), f"{name}.{key}"

    # Валидный Today context — тул отдаёт snapshot как есть, без пересчёта.
    tools.today_decision_context = {
        "date": anchor.isoformat(),
        "readiness": snapshot,
        "story": {"date": anchor.isoformat()},
    }
    contextual = tools.get_readiness_today()
    assert _triple(contextual["readiness"].get("tsb")) == _triple(snapshot.get("tsb"))
