"""Garmin-круги как самостоятельная структура карточки активности."""
from __future__ import annotations

from pathlib import Path

from data.database import Database
from data.garmin_client import GarminClient
from models.activity_intervals import (
    normalize_garmin_splits_payload,
    normalize_intervals_payload,
)
from services.activity_intervals import fetch_activity_intervals
from services.sync import _sync_activities


def _garmin_splits_payload() -> dict:
    return {
        "activityId": 23958642824,
        "eventDTOs": [],
        "lapDTOs": [
            {
                "lapIndex": 1,
                "duration": 300.4,
                "elapsedDuration": 305.2,
                "movingDuration": 298.7,
                "distance": 1000.2,
                "averageHR": 142,
                "maxHR": 155,
                "averagePower": 210,
                "averageRunCadence": 174,
                "averageSpeed": 3.33,
                "intensityType": "WARMUP",
            },
            {
                "lapIndex": 2,
                "duration": 600,
                "elapsedDuration": 610,
                "movingDuration": 595,
                "distance": 2000,
                "averageHR": 151,
                "maxHR": 164,
                "averagePower": None,
                "averageRunCadence": 178,
                "averageSpeed": 3.36,
                "intensityType": "ACTIVE",
            },
        ],
    }


def _garmin_activity(activity_id: str = "23958642824") -> dict:
    return {
        "activityId": activity_id,
        "startTimeLocal": "2026-08-13T09:56:34",
        "startTimeGMT": "2026-08-13T06:56:34",
        "activityType": {"typeKey": "running"},
        "duration": 2107,
        "movingDuration": 2094,
        "distance": 4514,
        "averageHR": 145,
        "activityTrainingLoad": 32.5,
    }


class _SplitsClient:
    def __init__(self, payload=None, error: Exception | None = None) -> None:
        self.payload = payload
        self.error = error
        self.calls: list[str] = []

    def get_activity_splits(self, activity_id: str):
        self.calls.append(str(activity_id))
        if self.error is not None:
            raise self.error
        return self.payload

    def pop_last_error(self):
        return None


class _IntervalsClient:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def is_configured(self) -> bool:
        return True

    def get_activity_intervals(self, activity_id: str) -> dict:
        assert activity_id == "i-current"
        return self.payload


def _seed_intervals_link(db: Database, canonical: str) -> None:
    import sqlite3

    with sqlite3.connect(db.db_path) as conn:
        conn.execute(
            """INSERT INTO activity_provider_links
               (canonical_activity_id, provider, provider_activity_id, match_status)
               VALUES (?, 'intervals', 'i-current', 'matched')""",
            (canonical,),
        )


def test_normalize_garmin_splits_maps_laps_to_shared_card_contract() -> None:
    compact = normalize_garmin_splits_payload(_garmin_splits_payload())

    assert compact["source"] == "garmin"
    assert compact["analyzed"] is None
    assert compact["groups"] == []
    assert len(compact["intervals"]) == 2
    assert compact["intervals"][0] == {
        "start_index": 0,
        "moving_time": 298.7,
        "elapsed_time": 305.2,
        "average_watts": 210,
        "average_heartrate": 142,
        "min_heartrate": None,
        "max_heartrate": 155,
        "average_cadence": 174,
        "zone": None,
        "training_load": None,
        "average_speed": 3.3,
        "distance_km": 1.0,
        "intensity_type": "warmup",
    }
    assert compact["intervals"][1]["start_index"] == 305.2
    assert compact["intervals"][1]["intensity_type"] == "active"


def test_normalize_garmin_splits_fails_closed_on_bad_laps() -> None:
    try:
        normalize_garmin_splits_payload({"lapDTOs": "broken"})
    except ValueError as exc:
        assert "lapDTOs" in str(exc)
    else:  # pragma: no cover - protects the fail-closed contract
        raise AssertionError("malformed Garmin laps must raise ValueError")


def test_intervals_normalizer_marks_provider_source() -> None:
    compact = normalize_intervals_payload({"icu_intervals": []})

    assert compact["source"] == "intervals"


def test_garmin_client_exposes_activity_splits_through_wrapper() -> None:
    client = GarminClient()
    client.is_authenticated = True

    class _Provider:
        def get_activity_splits(self, activity_id: str):
            assert activity_id == "23958642824"
            return _garmin_splits_payload()

    client.client = _Provider()

    assert client.get_activity_splits("23958642824")["lapDTOs"][0]["lapIndex"] == 1


def test_card_service_uses_cached_garmin_laps_without_intervals_link(tmp_path) -> None:
    db = Database(str(tmp_path / "garmin-cache.db"))
    cached = normalize_garmin_splits_payload(_garmin_splits_payload())
    db.save_activity_intervals("garmin-only", cached)

    assert fetch_activity_intervals(db, "garmin-only") == cached


def test_empty_intervals_result_does_not_hide_cached_garmin_laps(tmp_path) -> None:
    db = Database(str(tmp_path / "provider-priority.db"))
    cached = normalize_garmin_splits_payload(_garmin_splits_payload())
    db.save_activity_intervals("garmin-and-intervals", cached)
    _seed_intervals_link(db, "garmin-and-intervals")

    result = fetch_activity_intervals(
        db,
        "garmin-and-intervals",
        client=_IntervalsClient({"icu_intervals": [], "icu_groups": []}),
    )

    assert result == cached
    assert db.get_activity_intervals("garmin-and-intervals") == cached


def test_detected_intervals_keep_cached_garmin_laps_separately(tmp_path) -> None:
    db = Database(str(tmp_path / "provider-enrichment.db"))
    cached = normalize_garmin_splits_payload(_garmin_splits_payload())
    db.save_activity_intervals("garmin-and-intervals", cached)
    _seed_intervals_link(db, "garmin-and-intervals")

    result = fetch_activity_intervals(
        db,
        "garmin-and-intervals",
        client=_IntervalsClient(
            {"icu_intervals": [{"moving_time": 420, "distance": 1000}]}
        ),
    )

    assert result["source"] == "intervals"
    assert result["intervals"][0]["moving_time"] == 420
    assert result["garmin_laps"] == cached["intervals"]
    assert db.get_activity_intervals("garmin-and-intervals") == result


def test_garmin_sync_caches_laps_without_intervals_provider(tmp_path) -> None:
    db = Database(str(tmp_path / "garmin-sync.db"))
    client = _SplitsClient(_garmin_splits_payload())

    counts = _sync_activities(
        db,
        [_garmin_activity()],
        activity_intervals_client=client,
    )

    assert counts == {"new": 1, "updated": 0, "skipped": 0}
    assert client.calls == ["23958642824"]
    assert db.get_activity_intervals("23958642824")["source"] == "garmin"


def test_garmin_split_failure_does_not_lose_main_activity(tmp_path) -> None:
    db = Database(str(tmp_path / "garmin-failure.db"))
    warnings: list[str] = []

    counts = _sync_activities(
        db,
        [_garmin_activity("activity-without-laps")],
        warnings=warnings,
        activity_intervals_client=_SplitsClient(error=RuntimeError("provider down")),
    )

    assert counts == {"new": 1, "updated": 0, "skipped": 0}
    assert db.get_activity("activity-without-laps") is not None
    assert db.get_activity_intervals("activity-without-laps") is None
    assert len(warnings) == 1
    assert "структур" in warnings[0].lower()


def test_garmin_sync_adds_laps_without_overwriting_intervals_structure(tmp_path) -> None:
    db = Database(str(tmp_path / "priority.db"))
    _sync_activities(db, [_garmin_activity()])
    richer = normalize_intervals_payload(
        {
            "analyzed": "2026-08-13T07:30:00Z",
            "icu_intervals": [{"moving_time": 420, "distance": 1000}],
        }
    )
    db.save_activity_intervals("23958642824", richer)
    client = _SplitsClient(_garmin_splits_payload())

    _sync_activities(
        db,
        [_garmin_activity()],
        activity_intervals_client=client,
    )

    stored = db.get_activity_intervals("23958642824")
    expected_laps = normalize_garmin_splits_payload(_garmin_splits_payload())[
        "intervals"
    ]

    assert client.calls == ["23958642824"]
    assert stored["source"] == "intervals"
    assert stored["intervals"] == richer["intervals"]
    assert stored["garmin_laps"] == expected_laps


def test_garmin_sync_does_not_refetch_laps_already_stored_separately(tmp_path) -> None:
    db = Database(str(tmp_path / "combined-cache.db"))
    _sync_activities(db, [_garmin_activity()])
    richer = normalize_intervals_payload(
        {"icu_intervals": [{"moving_time": 420, "distance": 1000}]}
    )
    richer["garmin_laps"] = normalize_garmin_splits_payload(
        _garmin_splits_payload()
    )["intervals"]
    db.save_activity_intervals("23958642824", richer)
    client = _SplitsClient(_garmin_splits_payload())

    _sync_activities(
        db,
        [_garmin_activity()],
        activity_intervals_client=client,
    )

    assert client.calls == []
    assert db.get_activity_intervals("23958642824") == richer


def test_empty_legacy_cache_can_be_replaced_by_garmin_laps(tmp_path) -> None:
    db = Database(str(tmp_path / "empty-cache.db"))
    _sync_activities(db, [_garmin_activity()])
    db.save_activity_intervals(
        "23958642824",
        {"analyzed": None, "intervals": [], "groups": []},
    )
    client = _SplitsClient(_garmin_splits_payload())

    _sync_activities(
        db,
        [_garmin_activity()],
        activity_intervals_client=client,
    )

    assert client.calls == ["23958642824"]
    assert db.get_activity_intervals("23958642824")["source"] == "garmin"


def test_activity_card_names_garmin_laps_and_intervals_source() -> None:
    page = Path("web/app/activities/page.tsx").read_text(encoding="utf-8")
    types = Path("web/lib/types.ts").read_text(encoding="utf-8")

    assert 'source?: "garmin" | "intervals" | null' in types
    assert "garmin_laps?: ActivityInterval[]" in types
    assert 'garmin: "Круги Garmin"' in page
    assert 'intervals: "Интервалы Intervals.icu"' in page
    assert "intervals?.garmin_laps" in page
