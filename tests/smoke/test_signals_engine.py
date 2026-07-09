"""Smoke coverage for issue #74 unified signals engine."""
from __future__ import annotations

import re
from datetime import datetime, timedelta

import pandas as pd
import pytest

from data.database import Database
from models.signals_engine import SIGNALS_SOURCE, assemble_signals
from state import StateManager


pytestmark = pytest.mark.smoke


def _headless_state() -> StateManager:
    return StateManager({})


def _seed_daily_tss(db: Database, daily_tss_oldest_first: list[float]) -> None:
    base = datetime.now()
    n = len(daily_tss_oldest_first)
    rows = []
    for i, tss in enumerate(daily_tss_oldest_first):
        rows.append(
            {
                "activity_id": f"signals-{i}",
                "date": (base - timedelta(days=n - 1 - i)).strftime("%Y-%m-%d"),
                "sport": "cycling",
                "duration_minutes": 60,
                "distance_km": 25.0,
                "tss": tss,
            }
        )
    db.save_activities(rows)


def test_assemble_signals_fuses_readiness_instead_of_garmin_override() -> None:
    """Garmin readiness — фактор fusion, а не override (issue #139):
    подавленный HRV снижает итог даже при высоком training_readiness."""
    today = datetime.now().strftime("%Y-%m-%d")
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    activities = pd.DataFrame(
        [{"date": yesterday, "tss": 50.0}, {"date": today, "tss": 20.0}]
    )
    hrv = pd.DataFrame(
        [
            {"date": yesterday, "rmssd": 24.0},
            {"date": today, "rmssd": 26.0},
        ]
    )

    signals = assemble_signals(
        activities_df=activities,
        hrv_df=hrv,
        training_status={"training_readiness": 82},
    )

    assert signals["source"] == SIGNALS_SOURCE
    readiness = signals["readiness"]
    assert readiness["source"] == "fusion"
    # rmssd 26 (низкий абсолютный уровень) тянет итог заметно ниже Garmin 82
    assert readiness["value"] is not None and readiness["value"] < 82
    assert readiness["drivers"], "fusion должен объяснять себя драйверами"
    assert all("evidence" in d for d in readiness["drivers"])
    assert signals["load"]["label"] == signals["load"]["form"]


def test_dashboard_widgets_and_planning_expose_signals_contract(tmp_path) -> None:
    from api.routers.dashboard import dashboard_summary, dashboard_widgets
    from api.routers.planning import planning_status
    from models.ai_tools import AITools

    db = Database(str(tmp_path / "signals.db"))
    _seed_daily_tss(db, [50.0] * 60 + [70.0, 20.0, 65.0, 30.0, 80.0])
    state = _headless_state()

    summary_payload = dashboard_summary(db=db, state=state)
    widgets_payload = dashboard_widgets(db=db, state=state)
    planning_payload = planning_status(db=db)
    coach_metrics = AITools(db).get_performance_metrics(days=90)

    assert summary_payload["signals"]["source"] == SIGNALS_SOURCE
    assert widgets_payload["signals"]["source"] == SIGNALS_SOURCE
    assert planning_payload["signals"]["source"] == SIGNALS_SOURCE
    assert coach_metrics["signals"]["source"] == SIGNALS_SOURCE

    summary_today = summary_payload["summary"]["today"]
    summary_signals = summary_payload["signals"]
    assert summary_today["state_label"] == summary_signals["state"]["label"]
    assert summary_today["tone"] == summary_signals["state"]["tone"]
    assert summary_today["tsb"] == pytest.approx(summary_signals["load"]["tsb"], abs=0.05)

    detail = widgets_payload["training_score"]["load_mgmt"]["detail"]
    match = re.search(r"TSB\s*([-+]?\d+\.?\d*)", detail)
    assert match, f"could not find TSB in load_mgmt detail: {detail!r}"
    assert float(match.group(1)) == pytest.approx(widgets_payload["signals"]["load"]["tsb"], abs=0.05)
    assert widgets_payload["training_score"]["load_mgmt"]["label"] == widgets_payload["signals"]["load"]["label"]

    planning_metrics = planning_payload["metrics"]
    planning_signals = planning_payload["signals"]
    assert planning_metrics["tsb"] == pytest.approx(planning_signals["load"]["tsb"], abs=0.05)
    assert planning_metrics["form"] == planning_signals["load"]["form"]

    assert coach_metrics["tsb"] == pytest.approx(coach_metrics["signals"]["load"]["tsb"], abs=0.05)
    assert coach_metrics["signal_source"] == SIGNALS_SOURCE
