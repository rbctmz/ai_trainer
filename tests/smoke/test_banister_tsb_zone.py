"""Smoke coverage for the canonical TSB zone table (issue #63).

models.banister.tsb_zone() is the single source of truth every module should
describe a TSB value through. It was relocated here from
api/routers/dashboard.py's private _TSB_ZONES/_tsb_zone (still covered by
tests/smoke/test_dashboard_tsb_zones.py, which now imports this same
function) so models/ and api/ code can both reach it without an inverted
dependency.
"""
from __future__ import annotations

from datetime import datetime

from models.banister import BanisterModel, tsb_zone


def test_tsb_zone_boundaries():
    # Same boundaries as tests/smoke/test_dashboard_tsb_zones.py's
    # test_tsb_zone_boundaries_match_state_label_thresholds — kept in sync
    # deliberately since both pin the one shared implementation.
    assert tsb_zone(-20.1)["tone"] == "danger"
    assert tsb_zone(-20.0)["tone"] == "warning"
    assert tsb_zone(-10.1)["tone"] == "warning"
    assert tsb_zone(-10.0)["tone"] == "neutral"
    assert tsb_zone(9.9)["tone"] == "neutral"
    assert tsb_zone(10.0)["tone"] == "success"


def test_tsb_zone_labels_and_clauses():
    danger = tsb_zone(-25.0)
    assert danger["label"] == "Высокая усталость"
    assert danger["clause"] == "высокая усталость — приоритет восстановлению"

    success = tsb_zone(15.0)
    assert success["label"] == "Свежесть"
    assert success["clause"] == "хорошая свежесть — можно работать на качество"


def test_get_current_metrics_form_uses_canonical_zone_label():
    # A single zero-TSS day settles CTL=ATL=TSB=0, which is the "neutral"
    # zone (-10 <= tsb < 10) -- confirms get_current_metrics wires its
    # 'form' field through tsb_zone() instead of its old, now-removed
    # 5/-10/-30 boundaries.
    metrics = BanisterModel().get_current_metrics([0.0], [datetime(2026, 1, 1)])
    assert metrics["form"] == tsb_zone(0.0)["label"] == "Стабильная нагрузка"


def test_get_training_recommendation_matches_canonical_zone_boundaries():
    banister = BanisterModel()

    danger = banister.get_training_recommendation({"tsb": -20.1, "ctl": 50})
    assert danger["intensity"] == "Очень низкая/Отдых"

    warning = banister.get_training_recommendation({"tsb": -10.1, "ctl": 50})
    assert warning["intensity"] == "Низкая"

    neutral = banister.get_training_recommendation({"tsb": -10.0, "ctl": 50})
    assert neutral["intensity"] == "Умеренная"

    success = banister.get_training_recommendation({"tsb": 10.0, "ctl": 50})
    assert success["intensity"] == "Высокая"
