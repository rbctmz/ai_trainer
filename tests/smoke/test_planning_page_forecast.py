"""Smoke coverage for ui/pages/planning.py's forecast-message TSB-zone
migration (issue #63).

Near-duplicate of api/planning_service.py::_forecast (see
tests/smoke/test_planning_service_forecast.py), inside a Streamlit
button handler in ui/pages/planning.py's "Собрать план" simulator, so it
isn't independently callable the way _forecast is. The dict driving its
message selection is still a plain module-level constant and importable on
its own -- this pins that mapping directly. The boundary logic itself
(tsb_zone()) is exhaustively covered by tests/smoke/test_banister_tsb_zone.py.
"""
from __future__ import annotations

from models.banister import tsb_zone
from ui.pages.planning import _TSB_TONE_TO_FORECAST_MESSAGE


def test_tone_to_message_covers_all_four_canonical_tones():
    assert set(_TSB_TONE_TO_FORECAST_MESSAGE) == {"success", "neutral", "warning", "danger"}


def test_tone_to_message_matches_zone_at_each_boundary():
    assert _TSB_TONE_TO_FORECAST_MESSAGE[tsb_zone(-20.1)["tone"]] == "🔴 Предупреждение: высокий риск переутомления!"
    assert _TSB_TONE_TO_FORECAST_MESSAGE[tsb_zone(-10.1)["tone"]] == "🟠 Внимание: возможно накопление усталости."
    assert _TSB_TONE_TO_FORECAST_MESSAGE[tsb_zone(-10.0)["tone"]] == "🟡 Хорошая нагрузка для поддержания формы."
    assert _TSB_TONE_TO_FORECAST_MESSAGE[tsb_zone(10.0)["tone"]] == "🟢 Отличный прогноз! Вы будете в пиковой форме."
