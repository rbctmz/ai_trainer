"""Smoke: best-efforts / power-curve из Intervals.icu (#382).

ExecPlan: docs/best_efforts_execplan.md. Покрывает клиентские методы
``get_activity_best_efforts`` / ``get_activity_power_curve`` (пути/параметры,
fail-closed на не-mapping/не-list, 422 как нормальный «нет данных»), чистые
нормализаторы (fail-closed) и кэш ``activity_power_curves`` (roundtrip).

Формы ответов зафиксированы живыми запросами 2026-08-07 (спайк для #382).
"""
from __future__ import annotations

import pytest

from data.database import Database
from models.best_efforts import normalize_best_efforts_payload
from models.power_curve import normalize_power_curve_payload
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


# --- Чистый нормализатор: best-efforts ------------------------------------


def test_normalize_best_efforts_payload_compacts_fields():
    payload = {
        "efforts": [
            {"start_index": 2151, "end_index": 2211, "average": 155.71666,
             "duration": 60, "distance": None},
            {"start_index": 2286, "end_index": 2346, "average": 153.26666,
             "duration": 60, "distance": 10000},
        ]
    }

    compact = normalize_best_efforts_payload(payload, stream="watts", duration=60)

    assert compact == {
        "stream": "watts",
        "duration": 60,
        "efforts": [
            {"start_index": 2151, "end_index": 2211, "average": 155.7,
             "duration": 60, "distance_km": None},
            {"start_index": 2286, "end_index": 2346, "average": 153.3,
             "duration": 60, "distance_km": 10.0},
        ],
    }


def test_normalize_best_efforts_payload_empty_efforts():
    assert normalize_best_efforts_payload({"efforts": []}) == {
        "stream": "watts",
        "duration": 60,
        "efforts": [],
    }


def test_normalize_best_efforts_payload_missing_efforts_is_empty():
    assert normalize_best_efforts_payload({})["efforts"] == []


def test_normalize_best_efforts_payload_fails_closed_on_non_mapping():
    with pytest.raises(ValueError):
        normalize_best_efforts_payload(["not", "mapping"])


def test_normalize_best_efforts_payload_fails_closed_on_non_list_efforts():
    with pytest.raises(ValueError):
        normalize_best_efforts_payload({"efforts": "oops"})


def test_normalize_best_efforts_payload_fails_closed_on_non_mapping_effort():
    with pytest.raises(ValueError):
        normalize_best_efforts_payload({"efforts": [{"average": 100}, "bad"]})


# --- Чистый нормализатор: power curve -------------------------------------


def _sample_power_curve_payload() -> list:
    # Truncated but representative of the live 135-point curve (spike 2026-08-07).
    return [{
        "id": "i123", "stream_type": "watts", "weight": 95.4,
        "secs": [1, 2, 3, 4, 5, 60, 300, 1200, 3600],
        "values": [234, 230, 222, 207, 198, 155, 150, 134, 112],
        "watts_per_kg": [2.45, 2.41, 2.32, 2.17, 2.07, 1.62, 1.57, 1.40, 1.17],
        "vo2max_5m": 30.546541, "compound_score_5m": 235.84906,
    }]


def test_normalize_power_curve_payload_extracts_headline_peaks():
    compact = normalize_power_curve_payload(_sample_power_curve_payload())

    assert compact["weight"] == 95.4
    assert compact["vo2max_5m"] == 30.5
    assert compact["compound_score_5m"] == 235.8
    labels = [p["label"] for p in compact["peaks"]]
    assert labels == ["5s", "1min", "5min", "20min", "60min"]
    by_label = {p["label"]: p for p in compact["peaks"]}
    assert by_label["5s"]["watts"] == 198          # exact match at secs=5
    assert by_label["1min"]["watts"] == 155         # exact match at secs=60
    assert by_label["5min"]["watts"] == 150         # exact match at secs=300
    assert by_label["20min"]["watts"] == 134        # exact match at secs=1200
    assert by_label["60min"]["watts"] == 112        # exact match at secs=3600
    assert by_label["5s"]["watts_per_kg"] == 2.1


def test_normalize_power_curve_payload_empty_list_is_no_data():
    # Swim/run activity → provider returns [] (200).
    assert normalize_power_curve_payload([]) == {
        "weight": None, "peaks": [], "vo2max_5m": None, "compound_score_5m": None,
    }


def test_normalize_power_curve_payload_nearest_match_within_tolerance():
    # No exact 5s; closest is 6s (delta=1, within tolerance).
    payload = [{"secs": [6, 60], "values": [190, 155], "weight": 75.0}]
    compact = normalize_power_curve_payload(payload)
    five_sec = next(p for p in compact["peaks"] if p["label"] == "5s")
    assert five_sec["watts"] == 190


def test_normalize_power_curve_payload_too_far_is_none():
    # Closest to 5s is 60s (delta=55, way beyond tolerance).
    payload = [{"secs": [60], "values": [155], "weight": 75.0}]
    compact = normalize_power_curve_payload(payload)
    five_sec = next(p for p in compact["peaks"] if p["label"] == "5s")
    assert five_sec["watts"] is None


def test_normalize_power_curve_payload_fails_closed_on_non_list():
    with pytest.raises(ValueError):
        normalize_power_curve_payload({"not": "a list"})


def test_normalize_power_curve_payload_fails_closed_on_non_mapping_entry():
    with pytest.raises(ValueError):
        normalize_power_curve_payload(["not-mapping"])


# --- Кэш activity_power_curves --------------------------------------------


def test_db_save_and_get_activity_power_curve_roundtrip(tmp_path):
    db = Database(str(tmp_path / "curve.db"))
    curve = normalize_power_curve_payload(_sample_power_curve_payload())

    assert db.get_activity_power_curve("act-1") is None
    db.save_activity_power_curve("act-1", curve)
    assert db.get_activity_power_curve("act-1") == curve

    updated = normalize_power_curve_payload([])
    db.save_activity_power_curve("act-1", updated)
    assert db.get_activity_power_curve("act-1") == updated


# --- Сервис fetch-on-demand ------------------------------------------------


def _seed_intervals_link(
    db: Database, canonical: str = "act-1", intervals_id: str = "i123"
) -> None:
    import sqlite3

    conn = sqlite3.connect(db.db_path)
    try:
        conn.execute(
            """INSERT INTO activity_provider_links
               (canonical_activity_id, provider, provider_activity_id, match_status)
               VALUES (?, 'intervals', ?, 'matched')""",
            (canonical, intervals_id),
        )
        conn.commit()
    finally:
        conn.close()


def test_fetch_activity_power_curve_fetches_normalizes_and_caches(tmp_path, monkeypatch):
    from services.best_efforts import fetch_activity_power_curve

    db = Database(str(tmp_path / "svc.db"))
    _seed_intervals_link(db)
    client, _ = _patch_client(monkeypatch, _sample_power_curve_payload())

    result = fetch_activity_power_curve(db, "act-1", client=client)

    assert result is not None
    assert result["weight"] == 95.4
    assert [p["label"] for p in result["peaks"]] == ["5s", "1min", "5min", "20min", "60min"]
    assert db.get_activity_power_curve("act-1") == result


def test_fetch_activity_power_curve_serves_cache_on_provider_failure(
    tmp_path, monkeypatch
):
    from services.best_efforts import fetch_activity_power_curve

    db = Database(str(tmp_path / "svc2.db"))
    _seed_intervals_link(db)
    cached = normalize_power_curve_payload(_sample_power_curve_payload())
    db.save_activity_power_curve("act-1", cached)
    client = _patch_client_http_error(monkeypatch, 503, "upstream down")

    assert fetch_activity_power_curve(db, "act-1", client=client) == cached


def test_fetch_activity_power_curve_returns_none_without_cache_on_failure(
    tmp_path, monkeypatch
):
    from services.best_efforts import fetch_activity_power_curve

    db = Database(str(tmp_path / "svc3.db"))
    _seed_intervals_link(db)
    client = _patch_client_http_error(monkeypatch, 503, "upstream down")

    assert fetch_activity_power_curve(db, "act-1", client=client) is None


def test_fetch_activity_power_curve_none_without_intervals_link(tmp_path, monkeypatch):
    from services.best_efforts import fetch_activity_power_curve

    db = Database(str(tmp_path / "svc4.db"))
    client, _ = _patch_client(monkeypatch, _sample_power_curve_payload())

    # No provider link → None (Garmin-only; local fallback is Milestone 4).
    assert fetch_activity_power_curve(db, "act-garmin-only", client=client) is None


def test_fetch_activity_power_curve_422_is_no_power_not_failure(tmp_path, monkeypatch):
    from services.best_efforts import fetch_activity_power_curve

    db = Database(str(tmp_path / "svc5.db"))
    _seed_intervals_link(db)
    # power-curves for a swim activity returns [] (200), not 422 — but a
    # malformed/edge provider response that 422s must still be fail-open.
    client = _patch_client_http_error(monkeypatch, 422, "no power stream")

    # 422 bubbles out of the client as IntervalsICUError(status_code=422); the
    # service catches it (IntervalsICUError) and falls back to cache/None.
    assert fetch_activity_power_curve(db, "act-1", client=client) is None


# --- API: карточка ---------------------------------------------------------


def _seed_activity(db: Database, activity_id: str = "act-1") -> None:
    from datetime import datetime

    db.save_activities(
        [
            {
                "activity_id": activity_id,
                "date": datetime.now().strftime("%Y-%m-%d"),
                "sport": "cycling",
                "duration_minutes": 60,
                "distance_km": 30.0,
                "tss": 60.0,
                "tss_method": "power_tss_v1",
                "avg_hr": 140,
                "max_hr": 175,
            }
        ]
    )


def test_activity_card_includes_power_curve(tmp_path, monkeypatch):
    from api.routers import activities as activities_router

    db = Database(str(tmp_path / "api.db"))
    _seed_activity(db)
    curve = normalize_power_curve_payload(_sample_power_curve_payload())
    monkeypatch.setattr(
        activities_router, "fetch_activity_power_curve", lambda db, aid: curve
    )

    card = activities_router.get_activity_card("act-1", db=db)

    assert card["activity"]["power_curve"]["weight"] == 95.4
    assert card["activity"]["power_curve"]["peaks"][0]["label"] == "5s"


def test_activity_card_power_curve_null_when_unavailable(tmp_path, monkeypatch):
    from api.routers import activities as activities_router

    db = Database(str(tmp_path / "api2.db"))
    _seed_activity(db)
    monkeypatch.setattr(
        activities_router, "fetch_activity_power_curve", lambda db, aid: None
    )

    card = activities_router.get_activity_card("act-1", db=db)

    assert card["activity"]["power_curve"] is None
