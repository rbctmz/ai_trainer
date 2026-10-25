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

from datetime import date, datetime, timedelta, timezone

import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.deps import get_database
from api.planning_service import _current_signals
from api.routers.coach import _load_metrics_context
from api.routers.planning import router
from data.database import Database
from models.ai_tools import AITools
from models.banister import tsb_zone
from models.load_metrics import (
    LOAD_METRICS_WINDOW_DAYS,
    compute_load_metrics,
    compute_load_signal,
    daily_tss_series,
    load_metrics_window_bounds,
    persisted_load_metrics,
    select_persisted_load_snapshot,
)
from models.readiness import _tsb_metrics
from services.readiness_snapshot import build_readiness_snapshot
from services.recovery_analytics import record_post_sync_recovery_state
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
    monkeypatch.setattr("services.planning_cycles.athlete_local_date", lambda: anchor)
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


def _planning_client(db: Database) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_database] = lambda: db
    return TestClient(app)


def test_latest_capture_is_chronological_across_days(tmp_path, monkeypatch) -> None:
    """Regression: revision сбрасывается per target_key — выбор хронологический.

    Дельта-ревью #733 (7abe865): глобальная сортировка ``revision DESC``
    выбирала вчерашнюю rev=3 вместо сегодняшней rev=1, потому что target_key
    содержит local_date и счёт начинается заново каждым днём.
    """
    anchor = _ANCHOR
    _patch_athlete_anchor(monkeypatch, anchor)
    db = Database(str(tmp_path / "crossday.db"))
    db.save_activities(
        [
            {
                "activity_id": f"crossday-{n}",
                "date": (anchor - timedelta(days=n)).isoformat(),
                "sport": "cycling",
                "duration_minutes": 60,
                "distance_km": 25.0,
                "tss": 50.0,
            }
            for n in range(90)
        ]
    )
    for hour in (10, 11, 12):
        record_post_sync_recovery_state(
            db,
            capture_run_id=f"issue731-day1-{hour}",
            observed_at_utc=datetime(2026, 10, 23, hour, tzinfo=timezone.utc),
        )

    # Сегодняшние данные отличаются (та же дата, +100 TSS) — новая capture.
    db.save_activities(
        [
            {
                "activity_id": "crossday-same-day",
                "date": anchor.isoformat(),
                "sport": "cycling",
                "duration_minutes": 120,
                "distance_km": 50.0,
                "tss": 100.0,
            }
        ]
    )
    record_post_sync_recovery_state(
        db,
        capture_run_id="issue731-day2",
        observed_at_utc=datetime(2026, 10, 24, 8, tzinfo=timezone.utc),
    )

    chosen = db.get_latest_readiness_snapshot(
        capture_mode="prospective", local_date_max=anchor.isoformat()
    )
    assert chosen["local_date"] == anchor.isoformat()
    assert chosen["revision"] == 1
    assert chosen["capture_run_id"] == "issue731-day2"
    # Выбранная ревизия содержит сегодняшние числа, а не вчерашние (−5.9).
    assert chosen["tsb"]["tsb"] == pytest.approx(-16.8, abs=0.05)

    latest = persisted_load_metrics(chosen, anchor)
    assert latest is not None
    assert latest["tsb"] == pytest.approx(-16.8, abs=0.05)
    assert latest["revision"] == 1
    assert latest["as_of"] == anchor.isoformat()


def test_planning_endpoint_serves_one_consistent_revision(tmp_path, monkeypatch) -> None:
    """Весь HTTP-ответ строится от выбранной persisted-ревизии.

    Аудит #733 (7abe865): endpoint возвращал одновременно metrics.tsb −5.9
    («Стабильная нагрузка»), signals.load.form «Высокая усталость»,
    readiness_snapshot.tsb −38.7 и critical «Полный отдых 2–3 дня». Теперь
    числа, TSB-зависимые интерпретации, рекомендации и readiness_snapshot
    согласованы с выбранной ревизией, а её provenance едет в metrics.
    """
    anchor = _ANCHOR
    _patch_athlete_anchor(monkeypatch, anchor)
    db = Database(str(tmp_path / "persisted.db"))
    db.save_activities(
        [
            {
                "activity_id": f"persisted-{n}",
                "date": (anchor - timedelta(days=n)).isoformat(),
                "sport": "cycling",
                "duration_minutes": 60,
                "distance_km": 25.0,
                "tss": 50.0,
            }
            for n in range(90)
        ]
    )
    record_post_sync_recovery_state(
        db,
        capture_run_id="issue731-capture",
        observed_at_utc=datetime(2026, 10, 24, 8, tzinfo=timezone.utc),
    )

    def fetch_response() -> dict:
        response = _planning_client(db).get("/api/planning/status")
        assert response.status_code == 200
        return response.json()

    def assert_one_revision(payload: dict, expected: dict) -> None:
        """Числа, интерпретации и provenance — от одной и той же ревизии."""
        metrics = payload["metrics"]
        load = payload["signals"]["load"]
        snapshot = payload["readiness_snapshot"]
        for key in ("ctl", "atl", "tsb"):
            assert metrics[key] == pytest.approx(expected["tsb"][key], abs=0.05), key
            assert load[key] == pytest.approx(expected["tsb"][key], abs=0.05), key
            assert snapshot["tsb"][key] == pytest.approx(expected["tsb"][key], abs=0.05), key
        zone = tsb_zone(float(expected["tsb"]["tsb"]))
        assert metrics["form"] == zone["label"]
        assert load["form"] == zone["label"]
        assert load["label"] == zone["label"]
        assert load["tone"] == zone["tone"]
        # Provenance выбранной ревизии доходит до клиента.
        assert metrics["source"] == "persisted"
        assert metrics["snapshot_id"] == expected["id"]
        assert metrics["revision"] == expected["revision"]
        assert metrics["capture_mode"] == expected["capture_mode"]
        assert metrics["as_of"] == expected["local_date"]
        assert metrics["observed_at_utc"] == expected["observed_at_utc"]
        assert snapshot["id"] == expected["id"]
        assert snapshot["capture_mode"] == expected["capture_mode"]

    # Фаза A: capture есть, данные не менялись.
    saved = db.get_latest_readiness_snapshot(
        capture_mode="prospective", local_date_max=anchor.isoformat()
    )
    payload = fetch_response()
    assert_one_revision(payload, saved)
    assert payload["signals"]["critical"]["status"] is None

    # Фаза B: данные изменились (та же дата, +300 TSS), capture нет —
    # ответ всё ещё целиком от сохранённой ревизии.
    db.save_activities(
        [
            {
                "activity_id": "persisted-same-day",
                "date": anchor.isoformat(),
                "sport": "cycling",
                "duration_minutes": 180,
                "distance_km": 70.0,
                "tss": 300.0,
            }
        ]
    )
    payload = fetch_response()
    assert_one_revision(payload, saved)
    assert payload["signals"]["critical"]["status"] is None

    # Фаза C: новая capture — весь ответ переходит на новую ревизию,
    # включая TSB-зависимые интерпретации (tsb ≈ −38.7 → critical).
    record_post_sync_recovery_state(
        db,
        capture_run_id="issue731-capture-2",
        observed_at_utc=datetime(2026, 10, 24, 9, tzinfo=timezone.utc),
    )
    refreshed = db.get_latest_readiness_snapshot(
        capture_mode="prospective", local_date_max=anchor.isoformat()
    )
    assert refreshed["id"] != saved["id"]
    assert refreshed["tsb"]["tsb"] < -30
    payload = fetch_response()
    assert_one_revision(payload, refreshed)
    assert payload["signals"]["critical"]["status"] == "Критическое переутомление"


def test_planning_metrics_fall_back_live_before_first_capture(tmp_path, monkeypatch) -> None:
    """До первой capture метрики считает живой канонический пайплайн."""
    anchor = _ANCHOR
    _patch_athlete_anchor(monkeypatch, anchor)
    db = Database(str(tmp_path / "fresh.db"))
    db.save_activities(
        [
            {
                "activity_id": f"fresh-{n}",
                "date": (anchor - timedelta(days=n)).isoformat(),
                "sport": "cycling",
                "duration_minutes": 60,
                "distance_km": 25.0,
                "tss": 50.0,
            }
            for n in range(90)
        ]
    )
    assert select_persisted_load_snapshot(db, anchor) is None

    response = _planning_client(db).get("/api/planning/status")
    assert response.status_code == 200
    metrics = response.json()["metrics"]
    canonical = compute_load_metrics(
        pd.DataFrame(db.get_activities_between(*load_metrics_window_bounds(anchor))),
        anchor,
    )
    assert canonical is not None
    for key in ("ctl", "atl", "tsb"):
        assert metrics[key] == pytest.approx(canonical[key], abs=0.05), key
    assert metrics["source"] == "live"
    assert metrics["as_of"] == anchor.isoformat()
