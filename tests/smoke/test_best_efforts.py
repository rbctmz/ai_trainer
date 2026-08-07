"""Smoke: best-efforts / power-curve клиентские контракты Intervals.icu (#382).

ExecPlan: docs/best_efforts_execplan.md. Покрывает клиентские методы
``get_activity_best_efforts`` / ``get_activity_power_curve``: пути/параметры,
fail-closed на не-mapping/не-list и — главное — 422 как нормальный «нет данных»
(например watts на плавательной активности), а не ошибка.

Формы ответов зафиксированы живыми запросами 2026-08-07 (спайк для #382).
"""
from __future__ import annotations

import pytest

from services.intervals_icu import IntervalsICUClient, IntervalsICUError


pytestmark = pytest.mark.smoke


# --- helpers ---------------------------------------------------------------


def _patch_client(monkeypatch, response):
    """Stub ``_request_json`` at class level (client is a frozen dataclass)."""
    calls: dict = {}

    def stub(self, method, path, payload=None, params=None):
        calls.update({"method": method, "path": path, "params": params})
        return response

    monkeypatch.setattr(IntervalsICUClient, "_request_json", stub)
    return IntervalsICUClient(api_key="k", athlete_id="1"), calls


def _patch_client_http_error(monkeypatch, status_code: int, message: str):
    """Simulate an upstream HTTP error with a status code on IntervalsICUError."""

    def boom(self, method, path, payload=None, params=None):
        raise IntervalsICUError(
            f"Intervals.icu вернул HTTP {status_code}: {message}",
            status_code=status_code,
        )

    monkeypatch.setattr(IntervalsICUClient, "_request_json", boom)
    return IntervalsICUClient(api_key="k", athlete_id="1")


# --- best-efforts: happy path ---------------------------------------------


def test_client_get_activity_best_efforts_uses_stream_duration_count(monkeypatch):
    response = {
        "efforts": [
            {"start_index": 2151, "end_index": 2211, "average": 155.71666,
             "duration": 60, "distance": None},
        ]
    }
    client, calls = _patch_client(monkeypatch, response)

    result = client.get_activity_best_efforts("i123", stream="watts", duration=60, count=1)

    assert calls["method"] == "GET"
    assert calls["path"] == "/api/v1/activity/i123/best-efforts"
    assert calls["params"] == {"stream": "watts", "duration": "60", "count": "1"}
    assert result == response["efforts"]


def test_client_get_activity_best_efforts_defaults_to_watts_60s(monkeypatch):
    client, calls = _patch_client(monkeypatch, {"efforts": []})

    client.get_activity_best_efforts("i123")

    assert calls["params"] == {"stream": "watts", "duration": "60", "count": "1"}


def test_client_get_activity_best_efforts_count_is_upper_bound(monkeypatch):
    # Live spike: 45min activity asked for 1200s returns just 1 effort.
    client, _ = _patch_client(
        monkeypatch,
        {"efforts": [{"start_index": 1196, "end_index": 2396, "average": 134.7575,
                      "duration": 1200, "distance": None}]},
    )

    result = client.get_activity_best_efforts("i123", duration=1200, count=3)

    assert len(result) == 1


# --- best-efforts: 422 = "no data", not an error --------------------------


def test_client_get_activity_best_efforts_422_returns_empty(monkeypatch):
    # Swim activity asked for watts → 422 "Stream [fixed_watts] not on activity".
    client = _patch_client_http_error(monkeypatch, 422, "Stream [fixed_watts] not on activity")

    assert client.get_activity_best_efforts("i123", stream="watts") == []


def test_client_get_activity_best_efforts_5xx_still_raises(monkeypatch):
    # 5xx is a real failure → must propagate (unlike 422).
    client = _patch_client_http_error(monkeypatch, 503, "upstream down")

    with pytest.raises(IntervalsICUError) as exc_info:
        client.get_activity_best_efforts("i123")

    assert exc_info.value.status_code == 503


# --- best-efforts: fail-closed on bad shapes ------------------------------


def test_client_get_activity_best_efforts_fails_closed_on_non_mapping(monkeypatch):
    client, _ = _patch_client(monkeypatch, ["not", "mapping"])

    with pytest.raises(IntervalsICUError):
        client.get_activity_best_efforts("i123")


def test_client_get_activity_best_efforts_fails_closed_on_non_list_efforts(monkeypatch):
    client, _ = _patch_client(monkeypatch, {"efforts": "oops"})

    with pytest.raises(IntervalsICUError):
        client.get_activity_best_efforts("i123")


def test_client_get_activity_best_efforts_missing_efforts_is_empty(monkeypatch):
    client, _ = _patch_client(monkeypatch, {})

    assert client.get_activity_best_efforts("i123") == []


def test_client_get_activity_best_efforts_drops_non_mapping_entries(monkeypatch):
    client, _ = _patch_client(
        monkeypatch,
        {"efforts": [{"average": 100}, "junk", {"average": 90}]},
    )

    result = client.get_activity_best_efforts("i123")

    assert [e["average"] for e in result] == [100, 90]


# --- power-curves ----------------------------------------------------------


def test_client_get_activity_power_curve_path_and_shape(monkeypatch):
    response = [{
        "id": "i123", "stream_type": "watts", "weight": 95.4,
        "secs": [1, 60, 1200], "values": [234, 200, 150],
        "watts_per_kg": [2.45, 2.1, 1.57],
        "vo2max_5m": 30.55, "compound_score_5m": 235.85,
    }]
    client, calls = _patch_client(monkeypatch, response)

    result = client.get_activity_power_curve("i123")

    assert calls["method"] == "GET"
    assert calls["path"] == "/api/v1/activity/i123/power-curves"
    assert calls["params"] is None
    assert result == response


def test_client_get_activity_power_curve_empty_for_no_power(monkeypatch):
    # Swim/run activity → provider returns [] (200), not an error.
    client, _ = _patch_client(monkeypatch, [])

    assert client.get_activity_power_curve("i123") == []


def test_client_get_activity_power_curve_fails_closed_on_non_list(monkeypatch):
    client, _ = _patch_client(monkeypatch, {"not": "a list"})

    with pytest.raises(IntervalsICUError):
        client.get_activity_power_curve("i123")


def test_client_get_activity_power_curve_drops_non_mapping_entries(monkeypatch):
    client, _ = _patch_client(
        monkeypatch,
        [{"id": "i123"}, "junk", {"id": "i456"}],
    )

    result = client.get_activity_power_curve("i123")

    assert [c["id"] for c in result] == ["i123", "i456"]


# --- IntervalsICUError carries status_code --------------------------------


def test_intervals_icu_error_status_code_defaults_none():
    err = IntervalsICUError("boom")

    assert err.status_code is None
    assert str(err) == "boom"


def test_intervals_icu_error_status_code_set():
    err = IntervalsICUError("boom", status_code=422)

    assert err.status_code == 422
