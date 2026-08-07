"""Smoke: интервалы и стримы из Intervals.icu (#390).

ExecPlan: docs/intervals_streams_execplan.md. Проверяет чистый нормализатор
(fail-closed), контракты клиента (пути/параметры/fail-closed), кэш
``activity_intervals``, резолв Intervals-id через provider-links, сервис
fetch-on-demand с фолбэком на кэш и поле ``intervals`` в карточке API.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime

import pytest

from data.database import Database
from models.activity_intervals import normalize_intervals_payload
from services.intervals_icu import IntervalsICUClient, IntervalsICUError


pytestmark = pytest.mark.smoke


def _sample_intervals_payload() -> dict:
    return {
        "id": "i123",
        "analyzed": "2026-08-06T10:00:00Z",
        "icu_intervals": [
            {
                "start_index": 0,
                "moving_time": 780,
                "elapsed_time": 790,
                "distance": 500.4,
                "average_heartrate": 115,
                "zone": 1,
            },
            {
                "start_index": 780,
                "moving_time": 15,
                "elapsed_time": 20,
                "distance": 0.6,
                "average_heartrate": 117,
                "zone": 1,
            },
            {
                "start_index": 795,
                "moving_time": 780,
                "elapsed_time": 800,
                "distance": 500.1,
                "average_heartrate": 123,
                "zone": 1,
            },
            {
                "start_index": 1575,
                "moving_time": 240,
                "elapsed_time": 250,
                "distance": 111.1,
                "average_heartrate": 118,
                "zone": 1,
            },
        ],
        "icu_groups": [],
    }


def _seed_intervals_link(
    db: Database, canonical: str = "act-1", intervals_id: str = "i123"
) -> None:
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


def _seed_activity(db: Database, activity_id: str = "act-1") -> None:
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


def _patch_client(monkeypatch, response):
    """Patch ``_request_json`` at class level (client is a frozen dataclass)."""
    calls: dict = {}

    def stub(self, method, path, payload=None, params=None):
        calls.update({"method": method, "path": path, "params": params})
        return response

    monkeypatch.setattr(IntervalsICUClient, "_request_json", stub)
    return IntervalsICUClient(api_key="k", athlete_id="1"), calls


def _patch_client_error(monkeypatch, error):
    def boom(self, method, path, payload=None, params=None):
        raise error

    monkeypatch.setattr(IntervalsICUClient, "_request_json", boom)
    return IntervalsICUClient(api_key="k", athlete_id="1")


# --- Чистый нормализатор ---------------------------------------------------


def test_normalize_intervals_payload_compacts_selected_fields():
    compact = normalize_intervals_payload(_sample_intervals_payload())

    assert compact["analyzed"] == "2026-08-06T10:00:00Z"
    assert len(compact["intervals"]) == 4
    assert compact["groups"] == []

    first = compact["intervals"][0]
    assert first["start_index"] == 0
    assert first["moving_time"] == 780
    assert first["elapsed_time"] == 790
    assert first["distance_km"] == 0.5
    assert first["average_heartrate"] == 115
    assert first["zone"] == 1

    # Реальные данные из карточки: интервалы в метрах, восстановление ~0 м.
    assert compact["intervals"][1]["distance_km"] == 0.0
    assert compact["intervals"][2]["distance_km"] == 0.5
    assert compact["intervals"][3]["distance_km"] == 0.11


def test_normalize_intervals_payload_distance_is_metres_converted_to_km():
    compact = normalize_intervals_payload(
        {"icu_intervals": [{"distance": 1000}, {"distance": 250}]}
    )

    assert compact["intervals"][0]["distance_km"] == 1.0
    assert compact["intervals"][1]["distance_km"] == 0.25
    assert compact["intervals"][0]["moving_time"] is None


def test_normalize_intervals_payload_empty_payload():
    assert normalize_intervals_payload({}) == {
        "analyzed": None,
        "intervals": [],
        "groups": [],
    }


def test_normalize_intervals_payload_missing_intervals_is_empty_list():
    assert normalize_intervals_payload({"analyzed": "2026-08-06T10:00:00Z"})[
        "intervals"
    ] == []


def test_normalize_intervals_payload_fails_closed_on_non_mapping():
    with pytest.raises(ValueError):
        normalize_intervals_payload(["not", "mapping"])


def test_normalize_intervals_payload_fails_closed_on_non_list_intervals():
    with pytest.raises(ValueError):
        normalize_intervals_payload({"icu_intervals": "oops"})


def test_normalize_intervals_payload_fails_closed_on_non_mapping_interval():
    with pytest.raises(ValueError):
        normalize_intervals_payload({"icu_intervals": [{"start_index": 0}, "bad"]})


# --- Контракты клиента -----------------------------------------------------


def test_client_get_activity_intervals_uses_intervals_true(monkeypatch):
    client, calls = _patch_client(monkeypatch, _sample_intervals_payload())

    result = client.get_activity_intervals("i123")

    assert calls["method"] == "GET"
    assert calls["path"] == "/api/v1/activity/i123"
    assert calls["params"] == {"intervals": "true"}
    assert result["id"] == "i123"


def test_client_get_activity_intervals_fails_closed_on_non_mapping(monkeypatch):
    client, _ = _patch_client(monkeypatch, ["not", "mapping"])

    with pytest.raises(IntervalsICUError):
        client.get_activity_intervals("i123")


def test_client_get_activity_streams_requests_types_filter(monkeypatch):
    # Live API returns a LIST of stream objects (spike #382, 2026-08-07), not a
    # dict; the #390 contract (Dict[str, list]) was wrong and raised on a valid
    # payload. Mirror the real shape here.
    response = [
        {"type": "watts", "name": None, "data": [100, 200], "allNull": False},
        {"type": "time", "name": None, "data": [0, 1], "allNull": False},
    ]
    client, calls = _patch_client(monkeypatch, response)

    result = client.get_activity_streams("i123", types="watts")

    assert calls["path"] == "/api/v1/activity/i123/streams.json"
    assert calls["params"] == {"types": "watts"}
    assert isinstance(result, list)
    assert result[0]["type"] == "watts"
    assert result[0]["data"] == [100, 200]
    assert result[1]["type"] == "time"


def test_client_get_activity_streams_without_types(monkeypatch):
    client, calls = _patch_client(
        monkeypatch, [{"type": "watts", "data": [], "allNull": False}]
    )

    client.get_activity_streams("i123")

    assert calls["params"] is None


def test_client_get_activity_streams_fails_closed_on_non_list(monkeypatch):
    # A dict (the old, wrong assumption) now correctly fails closed.
    client, _ = _patch_client(monkeypatch, {"watts": [1, 2]})

    with pytest.raises(IntervalsICUError):
        client.get_activity_streams("i123")


def test_client_get_activity_streams_drops_non_mapping_entries(monkeypatch):
    # Defensive: junk entries inside the list are skipped, not raised — the
    # surrounding valid streams are still returned.
    response = [
        {"type": "watts", "data": [100], "allNull": False},
        "not-a-mapping",
        {"type": "time", "data": [0], "allNull": False},
    ]
    client, _ = _patch_client(monkeypatch, response)

    result = client.get_activity_streams("i123")

    assert [s["type"] for s in result] == ["watts", "time"]


# --- Кэш и резолв Intervals-id ---------------------------------------------


def test_db_save_and_get_activity_intervals_roundtrip(tmp_path):
    db = Database(str(tmp_path / "intervals.db"))
    payload = normalize_intervals_payload(_sample_intervals_payload())

    assert db.get_activity_intervals("act-1") is None
    db.save_activity_intervals("act-1", payload)
    assert db.get_activity_intervals("act-1") == payload

    updated = {"analyzed": "2026-08-06T11:00:00Z", "intervals": [], "groups": []}
    db.save_activity_intervals("act-1", updated)
    assert db.get_activity_intervals("act-1") == updated


def test_db_resolve_intervals_provider_activity_id(tmp_path):
    db = Database(str(tmp_path / "resolve.db"))

    assert db.get_intervals_provider_activity_id("act-1") is None
    _seed_intervals_link(db)
    assert db.get_intervals_provider_activity_id("act-1") == "i123"
    assert db.get_intervals_provider_activity_id("act-other") is None


# --- Сервис fetch-on-demand -------------------------------------------------


def test_fetch_activity_intervals_fetches_normalizes_and_caches(tmp_path, monkeypatch):
    from services.activity_intervals import fetch_activity_intervals

    db = Database(str(tmp_path / "svc.db"))
    _seed_intervals_link(db)
    client, _ = _patch_client(monkeypatch, _sample_intervals_payload())

    result = fetch_activity_intervals(db, "act-1", client=client)

    assert result is not None
    assert result["intervals"][0]["start_index"] == 0
    assert db.get_activity_intervals("act-1") == result


def test_fetch_activity_intervals_serves_cache_on_provider_failure(
    tmp_path, monkeypatch
):
    from services.activity_intervals import fetch_activity_intervals

    db = Database(str(tmp_path / "svc2.db"))
    _seed_intervals_link(db)
    cached = normalize_intervals_payload(_sample_intervals_payload())
    db.save_activity_intervals("act-1", cached)
    client = _patch_client_error(monkeypatch, IntervalsICUError("provider down"))

    assert fetch_activity_intervals(db, "act-1", client=client) == cached


def test_fetch_activity_intervals_returns_none_without_cache_on_failure(
    tmp_path, monkeypatch
):
    from services.activity_intervals import fetch_activity_intervals

    db = Database(str(tmp_path / "svc3.db"))
    _seed_intervals_link(db)
    client = _patch_client_error(monkeypatch, IntervalsICUError("provider down"))

    assert fetch_activity_intervals(db, "act-1", client=client) is None


def test_fetch_activity_intervals_none_without_intervals_link(tmp_path, monkeypatch):
    from services.activity_intervals import fetch_activity_intervals

    db = Database(str(tmp_path / "svc4.db"))
    client, _ = _patch_client(monkeypatch, _sample_intervals_payload())

    assert fetch_activity_intervals(db, "act-garmin-only", client=client) is None


# --- API: карточка ----------------------------------------------------------


def test_activity_card_includes_intervals(tmp_path, monkeypatch):
    from api.routers import activities as activities_router

    db = Database(str(tmp_path / "api.db"))
    _seed_activity(db)
    compact = normalize_intervals_payload(_sample_intervals_payload())
    monkeypatch.setattr(
        activities_router, "fetch_activity_intervals", lambda db, aid: compact
    )

    card = activities_router.get_activity_card("act-1", db=db)

    assert card["activity"]["intervals"]["intervals"][0]["start_index"] == 0


def test_activity_card_intervals_null_when_unavailable(tmp_path, monkeypatch):
    from api.routers import activities as activities_router

    db = Database(str(tmp_path / "api2.db"))
    _seed_activity(db)
    monkeypatch.setattr(
        activities_router, "fetch_activity_intervals", lambda db, aid: None
    )

    card = activities_router.get_activity_card("act-1", db=db)

    assert card["activity"]["intervals"] is None
